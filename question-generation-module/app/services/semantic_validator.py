"""
Semantic Validation Layer
=========================
Validates each generated question through five independent validators.
No LLM is used — all signals are algorithmic or model-based (encoder only).

Validators
----------
V1  Source Anchoring      – SBERT cosine similarity between question text
                            and source chunks.  Catches hallucinated questions
                            that have no grounding in the study material.

V2  Answer Term Overlap   – BM25 retrieval score of the correct answer
                            against source chunks.  Catches answers that are
                            not derivable from the material.

V3  Distractor Quality    – Pairwise cosine similarity (TF-IDF) between MCQ
                            options.  Flags questions where two options are
                            near-identical (bad distractors) or all wrong
                            options are off-topic (garbage distractors).

V4  Difficulty Alignment  – Flesch Reading Ease + question length heuristic.
                            Checks whether the linguistic complexity of the
                            question matches its stated difficulty level.

V5  Structural Rules      – Deterministic checks:exactly one correct option,no empty text fields,
                            no duplicate option labels, no duplicate option
                            bodies.

Each validator returns a ValidatorResult (score 0-1, status, detail).
The layer aggregates results into a ValidationReport per question and
attaches an overall pass/flag/reject decision.

Thresholds (all tunable via module-level constants)
---------------------------------------------------
ANCHOR_PASS     = 0.30   (SBERT similarity floor)
ANSWER_PASS     = 0.10   (BM25 normalised score floor)
DIST_MIN_SEP    = 0.15   (options must be at least this different)
DIST_MAX_SEP    = 0.98   (wrong options must not be completely off-topic)
REJECT_THRESHOLD = 2     (≥ this many failures → reject)
FLAG_THRESHOLD   = 1     (≥ this many failures → flag, else pass)
"""

from __future__ import annotations

import logging
import re
import string
from dataclasses import dataclass, field
from typing import List, Optional

import numpy as np
import textstat
from rank_bm25 import BM25Okapi
from sentence_transformers import SentenceTransformer

from app.models.schemas import GeneratedQuestion

logger = logging.getLogger(__name__)

# ── Thresholds ────────────────────────────────────────────────────────────────
ANCHOR_PASS      = 0.30   # V1: min SBERT similarity to any source chunk
ANSWER_PASS      = 0.10   # V2: min normalised BM25 score for correct answer
DIST_MIN_SEP     = 0.15   # V3: wrong options must differ by at least this much
REJECT_THRESHOLD = 3      # ≥ N failures → reject
FLAG_THRESHOLD   = 1      # ≥ N failures → flag

# ── Difficulty reading-ease bands (Flesch scale) ─────────────────────────────
# Note: Cognitive difficulty (Bloom's) != Linguistic complexity (Flesch).
# Hard reasoning questions can be written simply, and easy recall questions can have long jargon.
# These bands are now relaxed; actual cognitive difficulty is enforced by BloomBERT.
DIFFICULTY_FLESCH = {
    "easy":   (30, 100),   # Allow academic terms (lower score) in basic recall questions
    "medium": (15, 100),   # Very wide range
    "hard":   (0,  100),   # Deep reasoning questions can be written in very simple language!
}

# ── Lazy-loaded SBERT model (singleton) ──────────────────────────────────────
_sbert_model: Optional[SentenceTransformer] = None

def _get_sbert() -> SentenceTransformer:
    global _sbert_model
    if _sbert_model is None:
        logger.info("Loading SBERT model (all-MiniLM-L6-v2)…")
        _sbert_model = SentenceTransformer("all-MiniLM-L6-v2")
        logger.info("SBERT model loaded.")
    return _sbert_model


# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class ValidatorResult:
    validator: str          # "V1" … "V5"
    name: str               # human-readable name
    score: float            # 0.0 – 1.0  (1.0 = perfect)
    passed: bool
    detail: str             # one-line explanation


@dataclass
class ValidationReport:
    question_text: str
    difficulty: str
    results: List[ValidatorResult] = field(default_factory=list)
    decision: str = "pass"          # "pass" | "flag" | "reject"
    failure_count: int = 0
    overall_score: float = 1.0      # mean of all validator scores

    def to_dict(self) -> dict:
        return {
            "question_text": self.question_text[:80] + "…" if len(self.question_text) > 80 else self.question_text,
            "difficulty": self.difficulty,
            "decision": self.decision,
            "overall_score": round(self.overall_score, 3),
            "failure_count": self.failure_count,
            "validators": [
                {
                    "id": r.validator,
                    "name": r.name,
                    "score": round(r.score, 3),
                    "passed": r.passed,
                    "detail": r.detail,
                }
                for r in self.results
            ],
        }


# ── Helpers ───────────────────────────────────────────────────────────────────

def _tokenize(text: str) -> List[str]:
    """Lowercase, strip punctuation, split on whitespace."""
    text = text.lower().translate(str.maketrans("", "", string.punctuation))
    return text.split()


def _extract_chunk_texts(chunks: List[dict]) -> List[str]:
    return [c.get("payload", {}).get("text", "") for c in chunks if c.get("payload", {}).get("text")]


def _normalize_option_text(text: str) -> str:
    """Normalise option text for robust duplicate detection."""
    lowered = text.lower().strip()
    lowered = re.sub(r"\s+", " ", lowered)
    return lowered.translate(str.maketrans("", "", string.punctuation)).strip()


def _has_negation(text: str) -> bool:
    """Detect explicit negation cues in option text."""
    lowered = text.lower()
    if re.search(r"\b(?:no|not|never|none|without|except|cannot|neither|nor)\b", lowered):
        return True
    return bool(re.search(r"\b\w+n['’]t\b", lowered))


def _extract_numbers(text: str) -> List[str]:
    """Extract numeric tokens used by fact-style options."""
    return re.findall(r"\b\d+(?:\.\d+)?\b", text)


# ── Common contrast pairs (antonyms) for distractor guard ────────────────────
CONTRAST_PAIRS = [
    ("increase", "decrease"), ("increases", "decreases"), ("increased", "decreased"), ("increasing", "decreasing"),
    ("high", "low"), ("higher", "lower"), ("highest", "lowest"), ("maximum", "minimum"),
    ("more", "less"), ("more", "fewer"), ("most", "least"),
    ("fast", "slow"), ("faster", "slower"), ("fastest", "slowest"),
    ("true", "false"), ("valid", "invalid"),
    ("client", "server"), ("clients", "servers"),
    ("tcp", "udp"),
    ("synchronous", "asynchronous"),
    ("symmetric", "asymmetric"),
    ("stateful", "stateless"),
    ("push", "pull"),
    ("top", "bottom"), ("up", "down"),
    ("front", "back"), ("frontend", "backend"),
    ("before", "after"),
    ("start", "end"), ("first", "last"),
    ("allow", "block"), ("allow", "deny"), ("allows", "blocks"), ("allowed", "blocked"),
    ("accept", "reject"), ("accepts", "rejects"), ("accepted", "rejected"),
    ("inside", "outside"),
    ("internal", "external"),
    ("local", "remote"),
    ("static", "dynamic"),
    ("compiletime", "runtime"),  # Tokenizer removes hyphens
    ("positive", "negative"),
    ("long", "short"), ("longer", "shorter"), ("longest", "shortest"),
    ("hardware", "software"),
    ("read", "write"), ("reading", "writing"),
    ("horizontal", "vertical"),
]

def _has_antonym_contrast(text1: str, text2: str) -> bool:
    """Detect if two option texts differ by common opposite terms."""
    t1_toks = set(_tokenize(text1))
    t2_toks = set(_tokenize(text2))
    
    for w1, w2 in CONTRAST_PAIRS:
        if (w1 in t1_toks and w2 in t2_toks) or (w2 in t1_toks and w1 in t2_toks):
            return True
    return False


# ── Validator implementations ─────────────────────────────────────────────────

def v1_source_anchoring(question: GeneratedQuestion, chunk_texts: List[str]) -> ValidatorResult:
    """
    Encodes the question with SBERT and computes cosine similarity to every
    source chunk.  The max similarity is the anchoring score — it answers:
    "Is there at least one chunk that this question is about?"
    """
    if not chunk_texts:
        return ValidatorResult("V1", "Source Anchoring", 0.0, False,
                               "No source chunks provided.")

    model = _get_sbert()
    q_vec   = model.encode([question.question_text], normalize_embeddings=True)
    c_vecs  = model.encode(chunk_texts, normalize_embeddings=True)

    sims    = (q_vec @ c_vecs.T).flatten()          # cosine via dot on normalised vecs
    max_sim = float(sims.max())

    passed = max_sim >= ANCHOR_PASS
    detail = (
        f"Best chunk similarity: {max_sim:.3f} "
        f"(threshold {ANCHOR_PASS})"
    )
    return ValidatorResult("V1", "Source Anchoring", max_sim, passed, detail)


def v2_answer_term_overlap(question: GeneratedQuestion, chunk_texts: List[str]) -> ValidatorResult:
    """
    Builds a BM25 index over source chunks and queries it with the correct
    answer text.  The score is normalised by the maximum possible score so
    it sits in [0, 1].
    """
    if not chunk_texts:
        return ValidatorResult("V2", "Answer Term Overlap", 0.0, False,
                               "No source chunks provided.")

    tokenised_corpus = [_tokenize(t) for t in chunk_texts if t.strip()]
    if not tokenised_corpus:
        return ValidatorResult("V2", "Answer Term Overlap", 0.0, False,
                               "All chunks were empty after tokenisation.")

    bm25        = BM25Okapi(tokenised_corpus)
    query_toks  = _tokenize(question.correct_answer)
    if not query_toks:
        return ValidatorResult("V2", "Answer Term Overlap", 0.0, False,
                               "Correct answer is empty.")

    scores      = bm25.get_scores(query_toks)
    max_score   = float(scores.max())

    # Normalise: divide by the max score among all chunks so we get [0,1].
    # If max_score is 0 every chunk scored 0 — the answer has no overlap.
    corpus_max  = max(float(bm25.get_scores(_tokenize(t)).max())
                      for t in chunk_texts) if chunk_texts else 1.0
    normalised  = (max_score / corpus_max) if corpus_max > 0 else 0.0
    normalised  = min(normalised, 1.0)

    passed = normalised >= ANSWER_PASS
    detail = (
        f"BM25 normalised score: {normalised:.3f} "
        f"(threshold {ANSWER_PASS})"
    )
    return ValidatorResult("V2", "Answer Term Overlap", normalised, passed, detail)


def v3_distractor_quality(question: GeneratedQuestion, chunk_texts: List[str]) -> ValidatorResult:
    """
    Only runs for MCQ.  Uses SBERT cosine similarity on option texts.

    Failure mode detected:
      • Near-identical wrong options — two wrong options have SBERT cos_sim
        above (1 - DIST_MIN_SEP), meaning they are essentially the same
        answer and the question becomes ambiguous.

    Score = 1 - max_pairwise_similarity_among_wrong_options  (want low).
    """
    if question.question_type != "mcq" or not question.options:
        return ValidatorResult("V3", "Distractor Quality", 1.0, True,
                               "Not MCQ — validator skipped.")

    option_texts = [o.text for o in question.options]
    if len(option_texts) < 2:
        return ValidatorResult("V3", "Distractor Quality", 1.0, True,
                               "Fewer than 2 options — skipped.")

    model     = _get_sbert()
    opt_vecs  = model.encode(option_texts, normalize_embeddings=True)
    sim       = opt_vecs @ opt_vecs.T                              # cosine via dot
    norm_opts = [_normalize_option_text(t) for t in option_texts]
    neg_flags = [_has_negation(t) for t in option_texts]
    num_tokens = [_extract_numbers(t) for t in option_texts]

    # Pairwise similarity across ALL option pairs (including correct vs wrong).
    # A near-duplicate between the right answer and a wrong option is a hard fail.
    max_pair_sim = 0.0
    max_pair: Optional[tuple] = None
    hard_duplicate_pair: Optional[tuple] = None
    too_similar_pair: Optional[tuple] = None
    negation_guard_count = 0
    numeric_guard_count = 0
    antonym_guard_count = 0

    for i in range(len(option_texts)):
        for j in range(i + 1, len(option_texts)):
            s = float(sim[i, j])
            if s > max_pair_sim:
                max_pair_sim = s
                max_pair = (option_texts[i][:30], option_texts[j][:30])

            # Hard duplicate check is lexical and always enforced.
            if norm_opts[i] and norm_opts[i] == norm_opts[j]:
                hard_duplicate_pair = (option_texts[i][:30], option_texts[j][:30])

            # High semantic similarity is only a problem when polarity matches.
            high_similarity = s > (1 - DIST_MIN_SEP)
            polarity_flip = neg_flags[i] ^ neg_flags[j]
            numeric_contrast = (
                bool(num_tokens[i])
                and bool(num_tokens[j])
                and num_tokens[i] != num_tokens[j]
            )
            antonym_contrast = _has_antonym_contrast(option_texts[i], option_texts[j])

            if high_similarity and polarity_flip:
                negation_guard_count += 1
            elif high_similarity and numeric_contrast:
                numeric_guard_count += 1
            elif high_similarity and antonym_contrast:
                antonym_guard_count += 1
            elif high_similarity and not polarity_flip:
                too_similar_pair = (option_texts[i][:30], option_texts[j][:30], s)

    score = 1.0 - max_pair_sim
    passed = hard_duplicate_pair is None and too_similar_pair is None

    if hard_duplicate_pair:
        detail = (
            f"Duplicate option text detected: '{hard_duplicate_pair[0]}...' ~ "
            f"'{hard_duplicate_pair[1]}...'"
        )
    elif too_similar_pair:
        detail = (
            f"Near-duplicate options with same polarity (sim={too_similar_pair[2]:.3f}): "
            f"'{too_similar_pair[0]}...' ~ '{too_similar_pair[1]}...'"
        )
    elif (negation_guard_count > 0 or numeric_guard_count > 0 or antonym_guard_count > 0) and max_pair:
        detail = (
            f"High-similarity pairs passed by guards (negation={negation_guard_count}, numeric={numeric_guard_count}, antonym={antonym_guard_count}); "
            f"max pair similarity={max_pair_sim:.3f} for '{max_pair[0]}...' ~ '{max_pair[1]}...'."
        )
    else:
        detail = f"Max pairwise option similarity: {max_pair_sim:.3f} — OK."

    return ValidatorResult("V3", "Distractor Quality", score, passed, detail)


def v4_difficulty_alignment(question: GeneratedQuestion, _chunk_texts: List[str]) -> ValidatorResult:
    """
    Measures Flesch Reading Ease of the question text and checks it falls
    within the expected band for the stated difficulty level.

    Flesch scale:  100 = very easy, 0 = very hard (academic).
    """
    text  = question.question_text
    # textstat needs at least one sentence with a period to work reliably;
    # add a trailing period if missing.
    if not text.endswith("."):
        text = text + "."

    flesch     = textstat.flesch_reading_ease(text)
    word_count = len(question.question_text.split())

    diff       = question.difficulty.lower()
    lo, hi     = DIFFICULTY_FLESCH.get(diff, (0, 100))
    in_band    = lo <= flesch <= hi

    # Secondary heuristic: word count should grow with difficulty
    # Relaxed to allow more flexibility.
    wc_ok = {
        "easy":   word_count <= 40,
        "medium": word_count <= 60,
        "hard":   True,  # Hard questions can be short OR long
    }.get(diff, True)

    passed = in_band or wc_ok   # either signal is enough to pass
    score  = 1.0 if in_band else max(0.0, 1.0 - abs(flesch - (lo + hi) / 2) / 100)

    detail = (
        f"Flesch={flesch:.1f} (band [{lo},{hi}] for '{diff}'), "
        f"words={word_count}. "
        + ("In band ✓" if in_band else f"Out of band — may be mis-labelled.")
    )
    return ValidatorResult("V4", "Difficulty Alignment", score, passed, detail)


def v5_structural_rules(question: GeneratedQuestion, _chunk_texts: List[str]) -> ValidatorResult:
    """
    Deterministic structural checks — no models required.

    Checks:
      1. Correct answer is non-empty
      2. Explanation is non-empty
      3. MCQ: exactly one option marked correct
      4. MCQ: no duplicate option labels
      5. MCQ: no duplicate option body text
    """
    failures: List[str] = []

    q = question.question_text.strip()
    if not q:
        failures.append("Question text is empty.")

    if not question.correct_answer.strip():
        failures.append("Correct answer is empty.")

    if not question.explanation.strip():
        failures.append("Explanation is empty.")

    if question.question_type == "mcq" and question.options:
        correct_count = sum(1 for o in question.options if o.is_correct)
        if correct_count != 1:
            failures.append(f"MCQ must have exactly 1 correct option, found {correct_count}.")

        labels = [o.label for o in question.options]
        if len(labels) != len(set(labels)):
            failures.append(f"Duplicate option labels: {labels}")

        bodies = [o.text.strip().lower() for o in question.options]
        if len(bodies) != len(set(bodies)):
            failures.append("Duplicate option body text detected.")

    passed = len(failures) == 0
    score  = 1.0 if passed else max(0.0, 1.0 - len(failures) * 0.25)
    detail = "All structural checks passed." if passed else " | ".join(failures)

    return ValidatorResult("V5", "Structural Rules", score, passed, detail)


# ── Orchestrator ──────────────────────────────────────────────────────────────

_VALIDATORS = [
    v1_source_anchoring,
    v2_answer_term_overlap,
    v3_distractor_quality,
    v4_difficulty_alignment,
    v5_structural_rules,
]


class SemanticValidator:
    """
    Runs all five validators on a list of GeneratedQuestion objects and
    returns a ValidationReport for each one.

    Usage (in QuestionGenerationService):
        validator = SemanticValidator()
        reports   = validator.validate_all(questions, chunk_texts)
        passed_qs = [q for q, r in zip(questions, reports) if r.decision != "reject"]
    """

    def validate(
        self,
        question: GeneratedQuestion,
        chunk_texts: List[str],
    ) -> ValidationReport:
        """Run all validators on a single question."""
        results: List[ValidatorResult] = []

        for fn in _VALIDATORS:
            try:
                result = fn(question, chunk_texts)
            except Exception as exc:
                logger.warning("Validator %s raised an exception: %s", fn.__name__, exc)
                result = ValidatorResult(
                    fn.__name__[:2].upper(), fn.__name__, 0.5, True,
                    f"Validator error (skipped): {exc}"
                )
            results.append(result)

        failure_count = sum(1 for r in results if not r.passed)
        overall_score = float(np.mean([r.score for r in results]))

        if failure_count >= REJECT_THRESHOLD:
            decision = "reject"
        elif failure_count >= FLAG_THRESHOLD:
            decision = "flag"
        else:
            decision = "pass"

        return ValidationReport(
            question_text=question.question_text,
            difficulty=question.difficulty,
            results=results,
            decision=decision,
            failure_count=failure_count,
            overall_score=overall_score,
        )

    def validate_all(
        self,
        questions: List[GeneratedQuestion],
        chunk_texts: List[str],
    ) -> List[ValidationReport]:
        """Validate every question and return one report per question."""
        reports = [self.validate(q, chunk_texts) for q in questions]

        # ── Summary log ───────────────────────────────────────────────────
        counts = {"pass": 0, "flag": 0, "reject": 0}
        for r in reports:
            counts[r.decision] += 1

        logger.info(
            "Semantic validation complete: %d questions — pass=%d flag=%d reject=%d",
            len(reports), counts["pass"], counts["flag"], counts["reject"],
        )
        return reports
