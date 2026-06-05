"""
Answer grading service.

Grades a student's answer against the expected answer and returns is_correct
Design
1. mcq / true_false: deterministic O(1) string comparison. (The frontend grades
these locally for zero latency; this server-side path exists so the /check
endpoint is complete and callers *may* route everything through it.)
2. short_answer: keyword fast path first (cheap substring check), then semantic
similarity using the sentence transformers model already loaded by the
ExampleBank so no extra model in memory meaning around 20 ms per call no API cost
The semantic step is what makes text grading robust it accepts correct
paraphrases that don't literally contain the keyword strings
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

# Cosine threshold for MiniLM L6 v2 (normalized embeddings).
# genuine paraphrases of a correct short answer score ~0.55-0.75
# with this model, while unrelated answers score < 0.2 — so 0.55 captures
# correct paraphrases while leaving a wide margin against wrong answers.
# Leans slightly lenient on purpose: better to accept a correct paraphrase than
# to mark a right answer wrong. attunable for different needs
DEFAULT_SIM_THRESHOLD = 0.55


@dataclass
class GradeResult:
    is_correct: bool
    method: str
    score: Optional[float] = None


class AnswerGrader:
    """
    Grades answers for all three question types.

    embedder is any object exposing embed_query(text) -> np.ndarray that
    returns an L2-normalized vector (the ExampleBank satisfies this). When no
    embedder is available, short-answer grading degrades gracefully to keyword
    + substring matching.
    """

    def __init__(self, embedder=None, sim_threshold: float = DEFAULT_SIM_THRESHOLD):
        self._embedder = embedder
        self.sim_threshold = sim_threshold

    # ── public API ──────────────────────────────────────────────────────────
    def grade(
        self,
        question_type: str,
        user_answer: str,
        correct_answer: str = "",
        keywords: Optional[list] = None,
        options: Optional[list] = None,
    ) -> GradeResult:
        qt = (question_type or "").strip().lower()
        ua = (user_answer or "").strip()

        if qt == "mcq":
            return self._grade_mcq(ua, correct_answer, options)
        if qt == "true_false":
            return self._grade_true_false(ua, correct_answer)
        return self._grade_short_answer(ua, correct_answer, keywords)

    # ── MCQ ─────────────────────────────────────────────────────────────────
    def _grade_mcq(self, ua: str, correct_answer: str, options) -> GradeResult:
        ua_l = ua.lower()
        # Preferred: match the selected option (by label or text) and read its flag.
        if options:
            for opt in options:
                label = str(getattr(opt, "label", None) or (opt.get("label") if isinstance(opt, dict) else "")).strip().lower()
                text = str(getattr(opt, "text", None) or (opt.get("text") if isinstance(opt, dict) else "")).strip().lower()
                is_correct = getattr(opt, "is_correct", None)
                if is_correct is None and isinstance(opt, dict):
                    is_correct = opt.get("is_correct")
                if ua_l and (ua_l == label or ua_l == text):
                    return GradeResult(bool(is_correct), "exact")
        # Fallback: compare against the correct answer string (label or text).
        return GradeResult(bool(ua_l) and ua_l == correct_answer.strip().lower(), "exact")

    # ── True / False ──────────────────────────────────────────────────────────
    def _grade_true_false(self, ua: str, correct_answer: str) -> GradeResult:
        norm = lambda s: "true" if s in ("true", "t", "yes") else ("false" if s in ("false", "f", "no") else s)
        return GradeResult(
            norm(ua.lower()) == norm(correct_answer.strip().lower()) and bool(ua),
            "exact",
        )

    # ── Short answer ──────────────────────────────────────────────────────────
    def _grade_short_answer(self, ua: str, correct_answer: str, keywords) -> GradeResult:
        ua_l = ua.lower().strip()
        if not ua_l:
            return GradeResult(False, "fallback", 0.0)

        # check against keywords first to avoid overprocessing
        hints = [str(k).lower().strip() for k in (keywords or []) if str(k).strip()]
        if hints:
            matched = sum(1 for k in hints if k in ua_l)
            #require all keywords if 2 or fewer, otherwise require 60% of them tune to needs
            required = len(hints) if len(hints) <= 2 else math.ceil(len(hints) * 0.6) 
            ratio = matched / len(hints)
            if matched >= required:
                return GradeResult(True, "keyword", round(ratio, 3))
            # keywords missed let semantic similarity try to rescue below.

        # semantic similarity (reuses the miniLM model)
        if self._embedder is not None and correct_answer.strip():
            try:
                import numpy as np
                u = self._embedder.embed_query(ua)
                c = self._embedder.embed_query(correct_answer)
                sim = float(np.dot(u, c))  # vectors are normalized -> dot == cosine
                return GradeResult(sim >= self.sim_threshold, "semantic", round(sim, 3))
            except Exception as e:
                logger.warning("Semantic grading failed, falling back: %s", e)

        #as a last option check substring or equality fallback.
        cl = correct_answer.lower().strip()
        ok = bool(cl) and (ua_l == cl or cl in ua_l or ua_l in cl)
        return GradeResult(ok, "fallback")
