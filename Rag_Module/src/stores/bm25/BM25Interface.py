from abc import ABC, abstractmethod
from typing import List, Dict


class BM25Interface(ABC):
    @abstractmethod
    def build_index(self, project_id: str, texts: List[str],ids: List, payloads: List[Dict]) -> bool:
        pass

    @abstractmethod
    def search(self, project_id: str, query: str, top_k: int = 10) -> List[Dict]:
        pass

    @abstractmethod
    def load_index(self, project_id: str) -> bool:
        pass

    @abstractmethod
    def index_exists(self, project_id: str) -> bool:
        pass

    @abstractmethod
    def delete_index(self, project_id: str) -> bool:
        pass
