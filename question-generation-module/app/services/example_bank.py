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
                 question_type: Optional[str] = None) -> list[ExampleEntry]:
        """Return top-K bank entries matching `target_level`, ranked by cosine
        similarity to `query_text`. Optionally filter to a specific
        question_type (mcq / short_answer / true_false) so the LLM sees
        examples in the format it's expected to produce.
        """
        if not self.entries or self._embeddings is None:
            return []
        target_level = target_level.lower()
        candidate_idx = self._level_index.get(target_level, [])
        if question_type:
            candidate_idx = [i for i in candidate_idx
                             if self.entries[i].question_type == question_type]
        if not candidate_idx:
            # Fallback: ignore type filter if it killed all candidates
            candidate_idx = self._level_index.get(target_level, [])
            if not candidate_idx:
                # Fallback 2: any level
                candidate_idx = list(range(len(self.entries)))

        q = self.embed_query(query_text)
        cand_emb = self._embeddings[candidate_idx]
        sims = cand_emb @ q  # cosine since both are L2-normalized
        top_local = np.argsort(-sims)[:k]
        return [self.entries[candidate_idx[i]] for i in top_local]

    # ----------------------------------------------------------------- stats
    def stats(self) -> dict:
        from collections import Counter
        return {
            "total": len(self.entries),
            "by_level": dict(Counter(e.level for e in self.entries)),
            "by_type": dict(Counter(e.question_type for e in self.entries)),
        }
