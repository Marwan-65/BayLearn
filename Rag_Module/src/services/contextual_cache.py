import hashlib
import json
import logging
import os
from typing import Optional
logger = logging.getLogger(__name__)

class ContextualDescriptionCache:
    def __init__(self, storage_path: str = "contextual_cache.json"):
        self.storage_path = storage_path
        self._cache: dict = {}
        self._load()
    # function belongs to class logically, but doesn’t depend on it
    @staticmethod
    def _make_key(doc_title: str, section: str, chunk_text: str) -> str:
        payload = f"{doc_title}||{section}||{chunk_text[:500]}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def _load(self):
        if not os.path.exists(self.storage_path):
            self._cache = {}
            return
        try:
            with open(self.storage_path, "r", encoding="utf-8") as f:
                self._cache = json.load(f)
            logger.info(
                f"loaded {len(self._cache)} cached contextual descriptions "
                f"from {self.storage_path}"
            )
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(
                f"failed to load contextual cache at {self.storage_path}: {e}. "
                "starting with empty cache."
            )
            self._cache = {}

    def _save(self):
        try:
            with open(self.storage_path, "w", encoding="utf-8") as f:
                json.dump(self._cache, f, ensure_ascii=False)
        except OSError as e:
            logger.warning(f"failed to persist contextual cache: {e}")

    def get(self,doc_title: str,section: str,chunk_text: str,) -> Optional[str]:
        key = self._make_key(doc_title, section, chunk_text)
        return self._cache.get(key)

    def set(self,doc_title: str,section: str,chunk_text: str,description: str,) -> None:
        key = self._make_key(doc_title, section, chunk_text)
        self._cache[key] = description

    def flush(self) -> None:
        self._save()

    def size(self) -> int:
        return len(self._cache)
