import os
import pickle
import string
import logging
from typing import List, Dict

import numpy as np
from rank_bm25 import BM25Okapi
from stores.bm25.BM25Interface import BM25Interface


# Module-level punctuation translator — built once, O(1) per apply.
_PUNCT_TABLE = str.maketrans(string.punctuation, " " * len(string.punctuation))


def _tokenize(text: str) -> List[str]:
    """
    Minimal tokenizer optimized for CPU latency.
    lowercase → replace punctuation with spaces → whitespace split → drop short tokens.
    No stemming, no stopwords — keeps per-query tokenization < 0.3ms.
    """
    if not text:
        return []
    lowered = text.lower().translate(_PUNCT_TABLE)
    return [t for t in lowered.split() if len(t) > 1 or t.isalpha()]


class InMemoryBM25(BM25Interface):
    """
    rank_bm25-backed provider with per-project pickled indexes.

    On-disk format (one .pkl per project):
        {"bm25": BM25Okapi, "ids": [...], "payloads": [...], "version": 1}
    """

    PICKLE_VERSION = 1

    def __init__(self, index_dir: str, k1: float = 1.5, b: float = 0.75):
        self.index_dir = index_dir
        self.k1 = k1
        self.b = b
        self._cache: Dict[str, dict] = {}
        self.logger = logging.getLogger(__name__)

    def _path(self, project_id: str) -> str:
        return os.path.join(self.index_dir, f"{project_id}.pkl")

    def index_exists(self, project_id: str) -> bool:
        return project_id in self._cache or os.path.exists(self._path(project_id))

    def build_index(self, project_id: str, texts: List[str],
                    ids: List, payloads: List[Dict]) -> bool:
        if not texts:
            self.logger.warning(f"BM25 build_index: empty corpus for {project_id}")
            return False
        try:
            tokenized_corpus = [_tokenize(t) for t in texts]
            bm25 = BM25Okapi(tokenized_corpus, k1=self.k1, b=self.b)
            bundle = {
                "bm25": bm25,
                "ids": list(ids),
                "payloads": list(payloads),
                "version": self.PICKLE_VERSION,
            }
            # Atomic write: tmp then rename
            tmp = self._path(project_id) + ".tmp"
            with open(tmp, "wb") as f:
                pickle.dump(bundle, f, protocol=pickle.HIGHEST_PROTOCOL)
            os.replace(tmp, self._path(project_id))
            self._cache[project_id] = bundle
            self.logger.info(
                f"BM25 index built for {project_id}: "
                f"{len(texts)} docs, avgdl={bm25.avgdl:.1f}"
            )
            return True
        except Exception as e:
            self.logger.error(f"BM25 build_index failed for {project_id}: {e}")
            return False

    def load_index(self, project_id: str) -> bool:
        if project_id in self._cache:
            return True
        path = self._path(project_id)
        if not os.path.exists(path):
            return False
        try:
            with open(path, "rb") as f:
                bundle = pickle.load(f)
            if bundle.get("version") != self.PICKLE_VERSION:
                self.logger.warning(
                    f"BM25 index version mismatch for {project_id}, rebuild required"
                )
                return False
            self._cache[project_id] = bundle
            return True
        except Exception as e:
            self.logger.error(f"BM25 load_index failed for {project_id}: {e}")
            return False

    def search(self, project_id: str, query: str, top_k: int = 10) -> List[Dict]:
        if not self.load_index(project_id):
            return []

        bundle = self._cache[project_id]
        bm25: BM25Okapi = bundle["bm25"]
        ids = bundle["ids"]
        payloads = bundle["payloads"]

        tokens = _tokenize(query)
        if not tokens:
            return []

        scores = bm25.get_scores(tokens)
        if len(scores) == 0:
            return []

        k = min(top_k, len(scores))
        # argpartition is O(n) vs argsort O(n log n)
        part = np.argpartition(-scores, k - 1)[:k]
        part_sorted = part[np.argsort(-scores[part])]

        return [
            {
                "id": ids[i],
                "score": float(scores[i]),
                "payload": payloads[i],
            }
            for i in part_sorted if scores[i] > 0.0
        ]

    def delete_index(self, project_id: str) -> bool:
        self._cache.pop(project_id, None)
        path = self._path(project_id)
        if os.path.exists(path):
            try:
                os.remove(path)
                return True
            except Exception as e:
                self.logger.error(f"Failed to delete BM25 index {path}: {e}")
                return False
        return True
