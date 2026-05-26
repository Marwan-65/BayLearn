"""
In-memory few-shot example bank for ICL question generation.

Each entry: {question, concept, level, question_type, correct_answer,
             explanation, embedding}.

The bank is loaded once at FastAPI startup from a JSONL file. Embeddings are
computed lazily (only for entries that don't ship one) using the SAME embedding
model the RAG module uses (sentence-transformers/all-MiniLM-L6-v2 by default)
so the chunk-to-example similarity score is comparable.

Run scripts/build_example_bank.py to (re)generate the JSONL.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

EMBEDDING_MODEL_DEFAULT = "sentence-transformers/all-MiniLM-L6-v2"
EMBEDDING_DIM = 384  # for all-MiniLM-L6-v2


@dataclass
class ExampleEntry:
    question: str
    concept: str
    level: str                      # easy | medium | hard
    question_type: str = "short_answer"   # mcq | short_answer | true_false
    correct_answer: str = ""
    explanation: str = ""
    subject: str = ""
    embedding: Optional[np.ndarray] = field(default=None, repr=False)


class ExampleBank:
    """Holds embedded examples; supports cosine retrieval filtered by level."""

    def __init__(self, embedding_model_name: str = EMBEDDING_MODEL_DEFAULT):
        self.entries: list[ExampleEntry] = []
        self._model_name = embedding_model_name
        self._model = None       # lazy-loaded SentenceTransformer
        self._embeddings: Optional[np.ndarray] = None  # (n, dim), L2-normalized
        self._level_index: dict[str, list[int]] = {}  # level → list of entry indices

    # ----------------------------------------------------------------- loading
    @classmethod
    def load(cls, jsonl_path: str | Path,
             embedding_model_name: str = EMBEDDING_MODEL_DEFAULT) -> "ExampleBank":
        bank = cls(embedding_model_name=embedding_model_name)
        path = Path(jsonl_path)
        if not path.exists():
            logger.warning(
                "Example bank file not found at %s — bank will be empty (no ICL).",
                path,
            )
            return bank
        entries: list[ExampleEntry] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError as e:
                logger.warning("Skipping malformed JSONL line: %s", e)
                continue
            emb = d.get("embedding")
            entries.append(ExampleEntry(
                question=d["question"],
                concept=d.get("concept", ""),
                level=d.get("level", "medium").lower(),
                question_type=d.get("question_type", "short_answer"),
                correct_answer=d.get("correct_answer", ""),
                explanation=d.get("explanation", ""),
                subject=d.get("subject", ""),
                embedding=np.asarray(emb, dtype=np.float32) if emb else None,
            ))
        bank.entries = entries
        bank._build_indexes()
        logger.info("Example bank loaded: %d entries from %s", len(entries), path)
        return bank

    # ---------------------------------------------------------------- internal
    def _build_indexes(self) -> None:
        """Embed any entries missing vectors, build matrix + level index."""
        # Identify entries that still need embedding
        missing_idx = [i for i, e in enumerate(self.entries) if e.embedding is None]
        if missing_idx:
            logger.info("Embedding %d new bank entries...", len(missing_idx))
            model = self._lazy_model()
            texts = [self.entries[i].question for i in missing_idx]
            vecs = model.encode(texts, convert_to_numpy=True, show_progress_bar=False,
                                normalize_embeddings=True)
            for i, v in zip(missing_idx, vecs):
                self.entries[i].embedding = v.astype(np.float32)

        # Stack into one matrix (L2-normalize anything not already normalized)
        mat = np.stack([e.embedding for e in self.entries]).astype(np.float32)
        norms = np.linalg.norm(mat, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        self._embeddings = mat / norms

        # Group entry indices by level for O(1) filter
        self._level_index = {}
        for i, e in enumerate(self.entries):
            self._level_index.setdefault(e.level, []).append(i)

    def _lazy_model(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(self._model_name)
        return self._model

    # --------------------------------------------------------------- retrieval
    def embed_query(self, text: str) -> np.ndarray:
        """Embed a query string with the same model used for bank entries."""
        model = self._lazy_model()
        v = model.encode([text], convert_to_numpy=True, show_progress_bar=False,
                         normalize_embeddings=True)[0]
        return v.astype(np.float32)

    def retrieve(self, query_text: str, target_level: str, k: int = 4,
                 question_type: Optional[str] = None,
                 subject_hint: Optional[str] = None) -> list[ExampleEntry]:
        """Return top-K bank entries at `target_level`, ranked by cosine
        similarity to `query_text`.

        Filters apply in this order, each with graceful fallback if the filter
        leaves too few candidates:
          1. target_level (required) — easy / medium / hard
          2. question_type (optional) — mcq / short_answer / true_false
          3. subject_hint (optional) — partial substring match against
             entry.subject (case-insensitive). If specified, candidates whose
             subject string CONTAINS the hint are preferred. If fewer than k
             match the hint, the filter is dropped (we fall back to all
             level-matching entries).

        subject_hint is the mechanism that lets the LLM see OS-relevant
        examples when generating OS questions, instead of being swamped by
        the larger SRM pool covering all engineering subjects. Cosine
        ranking still runs within the filtered set, so the top-K are both
        domain-relevant and topically similar to the chunk.
        """
        if not self.entries or self._embeddings is None:
            return []
        target_level = target_level.lower()
        level_candidates = self._level_index.get(target_level, [])
        if not level_candidates:
            return []

        # Tier 1: apply both question_type and subject_hint where supplied
        candidates = list(level_candidates)
        if question_type:
            candidates = [i for i in candidates
                          if self.entries[i].question_type == question_type]
        if subject_hint:
            hint = subject_hint.lower().strip()
            subj_filtered = [i for i in candidates
                             if hint in (self.entries[i].subject or "").lower()]
            # Only honor the subject filter if it leaves enough candidates;
            # otherwise drop it to avoid returning too few diverse examples.
            if len(subj_filtered) >= k:
                candidates = subj_filtered
            # else: keep the broader candidates list (silent fallback)

        # Fallback tiers if any filter killed everything
        if not candidates:
            candidates = [i for i in level_candidates
                          if not question_type
                          or self.entries[i].question_type == question_type]
        if not candidates:
            candidates = level_candidates  # last resort: just level match

        q = self.embed_query(query_text)
        cand_emb = self._embeddings[candidates]
        sims = cand_emb @ q  # cosine since both are L2-normalized
        top_local = np.argsort(-sims)[:k]
        return [self.entries[candidates[i]] for i in top_local]

    # ----------------------------------------------------------------- stats
    def stats(self) -> dict:
        from collections import Counter
        return {
            "total": len(self.entries),
            "by_level": dict(Counter(e.level for e in self.entries)),
            "by_type": dict(Counter(e.question_type for e in self.entries)),
        }
