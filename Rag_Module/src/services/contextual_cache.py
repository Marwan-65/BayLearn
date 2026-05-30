"""
Contextual Retrieval Description Cache
======================================

Caches the LLM-generated contextual descriptions produced during indexing
(Anthropic's Contextual Retrieval technique, 2024).

Why this cache exists
---------------------
At index time, for every chunk we call the generation LLM with a prompt like:
    "Write a brief description that situates this chunk within the document..."
On a 200-page PDF this is ~400 LLM calls @ 1-2 seconds each = ~10 minutes.

If the user re-indexes the same project (e.g. after tweaking a setting like
RERANKER_ENABLED), we should NOT pay that cost again.

The cache key is a SHA-256 hash of (doc_title + section + chunk_text[:500]).
It is content-addressed — if any of the inputs change, the cache misses.

Storage is a single JSON file on disk, mirroring JsonChunkRepository's
pattern. It can be swapped for Redis later without changing callers.
"""

import hashlib
import json
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)


class ContextualDescriptionCache:
    """
    Content-addressed cache for contextual-retrieval descriptions.

    Interface:
        get(doc_title, section, chunk_text) -> Optional[str]
        set(doc_title, section, chunk_text, description) -> None
    """

    def __init__(self, storage_path: str = "contextual_cache.json"):
        self.storage_path = storage_path
        self._cache: dict = {}
        self._load()

    # ------------------------------------------------------------------
    # Key
    # ------------------------------------------------------------------

    @staticmethod
    def _make_key(doc_title: str, section: str, chunk_text: str) -> str:
        """
        Build a stable content hash. Truncating chunk_text to 500 chars
        keeps keys small while still being collision-safe for real-world
        text (SHA-256 over 500+ chars of input).
        """
        payload = f"{doc_title}||{section}||{chunk_text[:500]}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load(self):
        if not os.path.exists(self.storage_path):
            self._cache = {}
            return
        try:
            with open(self.storage_path, "r", encoding="utf-8") as f:
                self._cache = json.load(f)
            logger.info(
                f"Loaded {len(self._cache)} cached contextual descriptions "
                f"from {self.storage_path}"
            )
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(
                f"Failed to load contextual cache at {self.storage_path}: {e}. "
                "Starting with empty cache."
            )
            self._cache = {}

    def _save(self):
        try:
            with open(self.storage_path, "w", encoding="utf-8") as f:
                json.dump(self._cache, f, ensure_ascii=False)
        except OSError as e:
            logger.warning(f"Failed to persist contextual cache: {e}")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get(
        self,
        doc_title: str,
        section: str,
        chunk_text: str,
    ) -> Optional[str]:
        key = self._make_key(doc_title, section, chunk_text)
        return self._cache.get(key)

    def set(
        self,
        doc_title: str,
        section: str,
        chunk_text: str,
        description: str,
    ) -> None:
        key = self._make_key(doc_title, section, chunk_text)
        self._cache[key] = description

    def flush(self) -> None:
        """Persist the in-memory cache to disk. Call after a batch of sets."""
        self._save()

    def size(self) -> int:
        return len(self._cache)
