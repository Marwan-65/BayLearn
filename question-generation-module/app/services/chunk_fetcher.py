import httpx
import logging
from typing import List
logger = logging.getLogger(__name__)

FETCH_TIMEOUT = 30.0

class ChunkFetcher:
    def __init__(self, rag_module_url: str):
        self.rag_module_url = rag_module_url.rstrip("/")

    async def fetch_relevant_chunks(self,project_id: str,topic: str,limit: int = 10,) -> List[dict]:
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
            if status == 400:
                return []

            raise RuntimeError(f"RAG module error: {status}")