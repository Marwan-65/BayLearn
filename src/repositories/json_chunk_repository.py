import json
import os
from typing import List
from models.chunk import Chunk
from repositories.chunk_repository import AbstractChunkRepository
import logging

logger = logging.getLogger(__name__)


class JsonChunkRepository(AbstractChunkRepository):
    """
    Persistent chunk storage using a JSON file.
    
    WHY JSON instead of MongoDB for now?
    MongoDB requires a running server and connection setup.
    A JSON file requires nothing — it just works, survives restarts,
    and can be replaced with MongoDB later without changing any other code
    because both implement AbstractChunkRepository.
    
    This is the "Repository Pattern" — the rest of the system doesn't
    care HOW chunks are stored, just that they can be saved and retrieved.
    """

    def __init__(self, storage_path: str = "chunks_storage.json"):
        self.storage_path = storage_path
        self._ensure_file_exists()

    def _ensure_file_exists(self):
        """Create the JSON file if it doesn't exist yet."""
        if not os.path.exists(self.storage_path):
            with open(self.storage_path, "w") as f:
                json.dump({}, f)
            logger.info(f"Created new chunk storage at {self.storage_path}")

    def _load(self) -> dict:
        """Read all data from the JSON file into memory."""
        with open(self.storage_path, "r") as f:
            return json.load(f)

    def _save(self, data: dict):
        """Write all data back to the JSON file."""
        with open(self.storage_path, "w") as f:
            json.dump(data, f, indent=2)

    async def add_chunks(self, project_id: str, chunks: List[Chunk]):
        data = self._load()
        if project_id not in data:
            data[project_id] = []

        # Convert Chunk dataclass to dict for JSON serialization
        # WHY? JSON can only store basic types (strings, numbers, lists, dicts)
        # A Python dataclass object is not a basic type, so we convert it first
        for chunk in chunks:
            data[project_id].append({
                "chunk_id": chunk.chunk_id,
                "text": chunk.text,
                "metadata": chunk.metadata
            })

        self._save(data)
        logger.info(f"Saved {len(chunks)} chunks for project {project_id}")

    async def get_chunks(self, project_id: str) -> List[Chunk]:
        data = self._load()
        raw_chunks = data.get(project_id, [])

        # Convert dicts back to Chunk objects
        return [
            Chunk(
                chunk_id=c["chunk_id"],
                text=c["text"],
                metadata=c["metadata"]
            )
            for c in raw_chunks
        ]

    async def delete_project_chunks(self, project_id: str):
        data = self._load()
        if project_id in data:
            del data[project_id]
            self._save(data)
            logger.info(f"Deleted all chunks for project {project_id}")