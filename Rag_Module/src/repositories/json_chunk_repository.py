import json
import os
import re
from typing import List
from models.chunk import Chunk
from repositories.chunk_repository import AbstractChunkRepository
import logging

logger = logging.getLogger(__name__)

# Strip ASCII control characters except \t \n \r, which json handles fine.
# Anything else (NUL, vertical tab, form feed, stray escape bytes from
# PDF/OCR) blows up json.load on the next read.
_CTRL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def _sanitize(text):
    if not isinstance(text, str):
        return text
    return _CTRL_RE.sub("", text)


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
        """Read all data from the JSON file into memory.

        Handles two failure modes gracefully:
        - File deleted at runtime (FileNotFoundError): recreate it and return {}.
        - File corrupted by bad control chars from PDF/OCR (JSONDecodeError):
          quarantine the bad copy and start fresh.
        """
        try:
            with open(self.storage_path, "r") as f:
                return json.load(f)
        except FileNotFoundError:
            logger.warning(
                f"{self.storage_path} was deleted at runtime; recreating it."
            )
            self._ensure_file_exists()
            return {}
        except json.JSONDecodeError as e:
            backup = self.storage_path + ".corrupt"
            try:
                os.replace(self.storage_path, backup)
                logger.error(
                    f"chunks_storage.json was corrupt ({e}); moved to {backup} "
                    "and starting with an empty store."
                )
            except OSError:
                logger.error(
                    f"chunks_storage.json was corrupt ({e}); starting fresh."
                )
            self._ensure_file_exists()
            return {}

    def _save(self, data: dict):
        """Write all data back to the JSON file."""
        self._ensure_file_exists()
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
            # Sanitize text + string metadata values so a stray
            # control character from PDF/OCR can never corrupt the
            # JSON store.
            clean_meta = {
                k: (_sanitize(v) if isinstance(v, str) else v)
                for k, v in (chunk.metadata or {}).items()
            }
            data[project_id].append({
                "chunk_id": chunk.chunk_id,
                "text": _sanitize(chunk.text),
                "metadata": clean_meta,
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

    async def delete_chunks_by_source(self, project_id: str, source_filename: str):
        """Remove all chunks whose metadata["source"] matches source_filename.

        Called before re-uploading a file so stale chunks (e.g. with the old
        chunk_type or missing image_path) don't stay in the buffer alongside
        the freshly-parsed ones and cause Qdrant to return the wrong version.
        """
        data = self._load()
        if project_id not in data:
            return
        before = len(data[project_id])
        data[project_id] = [
            c for c in data[project_id]
            if c.get("metadata", {}).get("source") != source_filename
        ]
        removed = before - len(data[project_id])
        if removed:
            self._save(data)
            logger.info(
                f"Removed {removed} stale chunk(s) for source '{source_filename}' "
                f"in project {project_id}"
            )

    async def delete_project_chunks(self, project_id: str):
        data = self._load()
        if project_id in data:
            del data[project_id]
            self._save(data)
            logger.info(f"Deleted all chunks for project {project_id}")