from sentence_transformers import CrossEncoder
from stores.reranker.RerankerInterface import RerankerInterface
import logging
from typing import List, Dict


class CrossEncoderReranker(RerankerInterface):

    def __init__(self, model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"):
        self.model_name = model_name
        self._model = None
        self.logger = logging.getLogger(__name__)

    def _load_model(self):
        if self._model is None:
            self.logger.info(f"Loading cross-encoder model: {self.model_name}")
            self._model = CrossEncoder(self.model_name)
            self.logger.info("Cross-encoder model loaded successfully.")

    def rerank(self, query: str, documents: List[Dict], top_k: int) -> List[Dict]:
        if not documents:
            return []

        self._load_model()
        pairs = []
        for doc in documents:
            text = doc.get("payload", {}).get("text", "")
            pairs.append((query, text))

        scores = self._model.predict(pairs)
        for i, doc in enumerate(documents):
            doc["rerank_score"] = float(scores[i])
        reranked = sorted(documents, key=lambda d: d["rerank_score"], reverse=True)
        return reranked[:top_k]
