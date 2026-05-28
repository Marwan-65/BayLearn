"""
we need these files in the 'data/processed' directory:
    data/processed/example_bank.jsonl              
    data/processed/example_bank_embeddings.npy     

flow for retrieval:
  - first filter by `target_level` only (easy/medium/hard).
  - then rank candidates by cosine similarity to the query.
  - then return top-K (default 3).
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
from collections import Counter

import numpy as np

logger = logging.getLogger(__name__)

EMBEDDING_MODEL_DEFAULT = "sentence-transformers/all-MiniLM-L6-v2"


@dataclass
class ExampleEntry:
    question: str
    level: str          
    source: str = ""
    subject: str = ""
    embedding: Optional[np.ndarray] = field(default=None, repr=False)


class ExampleBank:

    def __init__(self, embedding_model_name: str = EMBEDDING_MODEL_DEFAULT):
        self.entries: list[ExampleEntry] = []
        self._model_name = embedding_model_name
        # model is loaded on first use to avoid unnecessary overhead
        self._model = None                             
        self._embeddings: Optional[np.ndarray] = None  
        self._level_idx: dict[str, np.ndarray] = {}

    @classmethod
    def load(cls, jsonl_path: str | Path,embedding_model_name: str = EMBEDDING_MODEL_DEFAULT) -> "ExampleBank":
        bank = cls(embedding_model_name=embedding_model_name)
        jsonl_path = Path(jsonl_path)
        if not jsonl_path.exists():
            logger.warning("Example bank file not found at %s — bank empty.",jsonl_path)
            return bank

        entries: list[ExampleEntry] = []
        for line in jsonl_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError as e:
                logger.warning("Skipping malformed JSONL line: %s", e)
                continue
            entries.append(ExampleEntry(
                question=d["question"],
                level=d.get("level", "").lower(),
                source=d.get("source", ""),
                subject=d.get("subject", ""),
            ))
        bank.entries = entries

        # Load pre-computed embeddings if present, otherwise compute.
        npy_path = jsonl_path.with_name(jsonl_path.stem + "_embeddings.npy")
        if npy_path.exists():
            embs = np.load(npy_path)
            if embs.shape[0] != len(entries):
                logger.warning(
                    "Embeddings file row count (%d) does not match JSONL (%d)"
                    "Re-run scripts/build_example_bank.py to rebuild",
                    embs.shape[0], len(entries),
                )
                embs = bank._embed_all([e.question for e in entries])
            else:
                logger.info("Loaded %d pre-computed embeddings from %s",
                            embs.shape[0], npy_path.name)
        else:
            logger.warning("No %s found — embedding %d entries on startup (slow). Run scripts/build_example_bank.py to pre-compute.", npy_path.name, len(entries))
            embs = bank._embed_all([e.question for e in entries])

        # ensure L2-normalized so what happen for cosine is just dot product which is faster
        # norms = np.linalg.norm(embs, axis=1, keepdims=True)
        # norms[norms == 0] = 1.0
        # bank._embeddings = (embs / norms).astype(np.float32)

        # Pre-bucket indices by level for O(1) candidate selection
        levels = np.array([e.level for e in entries], dtype=object)
        for lvl in ("easy", "medium", "hard"):
            bank._level_idx[lvl] = np.where(levels == lvl)[0]

        logger.info("Example bank ready: %s", bank.stats())
        return bank

    def _lazy_model(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(self._model_name)
        return self._model

    def _embed_all(self, texts: list[str]) -> np.ndarray:
        model = self._lazy_model()
        return model.encode(
            texts, batch_size=64, show_progress_bar=False,
            convert_to_numpy=True, normalize_embeddings=True,
        ).astype(np.float32)

    def embed_query(self, text: str) -> np.ndarray:
        return self._embed_all([text])[0]

    def retrieve(self, query_text: str, target_level: str, k: int = 3) -> list[ExampleEntry]:
        if not self.entries or self._embeddings is None:
            return []
        target_level = target_level.lower()
        idx = self._level_idx.get(target_level)
        if idx is None or len(idx) == 0:
            return []

        q = self.embed_query(query_text)       
        sims = self._embeddings[idx] @ q        
        if len(idx) <= k:
            top_local = np.argsort(-sims)
        else:
            # argpartition is O(N) instead of argsort which is O(N log N) if available questions are big 
            top_local = np.argpartition(-sims, k)[:k]
            top_local = top_local[np.argsort(-sims[top_local])]
        return [self.entries[idx[i]] for i in top_local]

    def stats(self) -> dict:
        return {
            "total": len(self.entries),
            "by_level":  dict(Counter(e.level for e in self.entries)),
            "by_source": dict(Counter(e.source for e in self.entries)),
        }
