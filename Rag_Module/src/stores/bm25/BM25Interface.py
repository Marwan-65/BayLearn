from abc import ABC, abstractmethod
from typing import List, Dict


class BM25Interface(ABC):

    @abstractmethod
    def build_index(self, project_id: str, texts: List[str],
                    ids: List, payloads: List[Dict]) -> bool:
        """
        Build (or rebuild) the BM25 index for a project and persist to disk.

        Args:
            project_id: Unique project identifier.
            texts: The text corpus to index (same contextual texts used for dense embeddings).
            ids: Per-chunk IDs aligned with texts.
            payloads: Per-chunk dicts matching the Qdrant payload shape
                      so downstream code receives identical structures from both retrievers.

        Returns:
            True on success, False on failure.
        """
        pass

    @abstractmethod
    def search(self, project_id: str, query: str, top_k: int = 10) -> List[Dict]:
        """
        BM25 search. Returns results in the same format as QdrantDB.search_by_vector:
            [{"id": ..., "score": <bm25_score>, "payload": {...}}, ...]
        Sorted descending by BM25 score. Returns [] if index missing/empty.
        """
        pass

    @abstractmethod
    def load_index(self, project_id: str) -> bool:
        """Force-load the on-disk index into the in-memory cache."""
        pass

    @abstractmethod
    def index_exists(self, project_id: str) -> bool:
        """Check if a persisted BM25 index exists on disk for this project."""
        pass

    @abstractmethod
    def delete_index(self, project_id: str) -> bool:
        """Delete the persisted index and drop from in-memory cache."""
        pass
