import httpx
import logging
from typing import List, Optional

logger = logging.getLogger(__name__)

FETCH_TIMEOUT = 30.0

class ChunkFetcher:
    """
    Fetches relevant text chunks from the RAG module's vector search API.
    
    Instead of re-implementing embedding + vector search, we call the
    already-built RAG module at src/. This is the Adapter pattern —
    the same one used in src/services/input_parsing_adapter.py.
    """

    def __init__(self, rag_module_url: str):
        self.rag_module_url = rag_module_url.rstrip("/")

    async def fetch_relevant_chunks(
        self,
        project_id: str,
        topic: str,
        limit: int = 10,
    ) -> List[dict]:
        """
        Call the RAG module's search endpoint to get text chunks
        semantically related to topic

        Returns a list of dicts, each with:
            - "id": chunk_id (int)
            - "score": relevance score (float, 0-1)
            - "payload": { "text": "...", "page": 1, ... }
        """
        url = f"{self.rag_module_url}/api/v1/nlp/index/search/{project_id}"
        payload = {"text": topic, "limit": limit}

        try:
            async with httpx.AsyncClient(timeout=FETCH_TIMEOUT) as client:
                response = await client.post(url, json=payload)
                response.raise_for_status()
                data = response.json()
                return data.get("top_results", [])
        except httpx.ConnectError:
            logger.error(f"RAG module unreachable at {self.rag_module_url}")
            raise ConnectionError("RAG module is not running. Start it first.")
        except httpx.HTTPStatusError as e:
            status = e.response.status_code
            logger.error(f"RAG module returned {status}")

            # The rag search endpoint uses 400 when the project exists but
            # no matching chunks are found for the query. Treat that as an
            # empty retrieval so the route returns a clean response to the user
            # with a validation message instead of a generic 500
            if status == 400:
                return []

            raise RuntimeError(f"RAG module error: {status}")