from abc import ABC, abstractmethod
from typing import List
from models.chunk import Chunk


class AbstractChunkRepository(ABC):

    @abstractmethod
    async def add_chunks(self, project_id: str, chunks: List[Chunk]):
        pass

    @abstractmethod
    async def get_chunks(self, project_id: str) -> List[Chunk]:
        pass

    @abstractmethod
    async def delete_project_chunks(self, project_id: str):
        pass