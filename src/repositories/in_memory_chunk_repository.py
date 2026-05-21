from typing import Dict, List
from models.chunk import Chunk
from repositories.chunk_repository import AbstractChunkRepository


class InMemoryChunkRepository(AbstractChunkRepository):

    def __init__(self):
        # { project_id: [Chunk, Chunk, ...] }
        self._storage: Dict[str, List[Chunk]] = {}

    async def add_chunks(self, project_id: str, chunks: List[Chunk]):
        if project_id not in self._storage:
            self._storage[project_id] = []

        self._storage[project_id].extend(chunks)

    async def get_chunks(self, project_id: str) -> List[Chunk]:
        return self._storage.get(project_id, [])

    async def delete_project_chunks(self, project_id: str):
        if project_id in self._storage:
            del self._storage[project_id]