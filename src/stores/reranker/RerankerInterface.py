from abc import ABC, abstractmethod
from typing import List, Dict


class RerankerInterface(ABC):
    @abstractmethod
    def rerank(self, query: str, documents: List[Dict], top_k: int) -> List[Dict]:
        """
        Re-score and re-order documents by relevance to the query.

        Args:
            query: The original user question (NOT the HyDE hypothetical).
            documents: List of dicts from vector search, each with
                       {"payload": {"text": ...}, "score": ..., ...}
            top_k: How many documents to return after reranking.

        Returns:
            The top_k documents re-ordered by cross-encoder score,
            each augmented with a "rerank_score" key.
        """
        pass
