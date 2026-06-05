from abc import ABC, abstractmethod
from typing import List, Dict


class RerankerInterface(ABC):
    @abstractmethod
    def rerank(self, query: str, documents: List[Dict], top_k: int) -> List[Dict]:
        pass
