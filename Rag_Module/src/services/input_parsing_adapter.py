"""adapter design pattern is a structural pattern that acts as a bridge between two 
incompatible interfaces,allowing them to work together without modifying existing code.
"""
import httpx
import logging
from typing import Optional
from models.chunk import Chunk as RAGChunk
from routes.schemes.orchestrator import InputParsingResponse
logger = logging.getLogger(__name__)
# after testing parsing large files takes some time and we do not want it to timeout and cancel the process
PARSING_TIMEOUT = 900.0

class InputParsingAdapter:
    def __init__(self, module_url: Optional[str] = None):
        self.module_url = module_url

    @property
    def is_available(self) -> bool:
        return bool(self.module_url)

    async def check_health(self) -> bool:
        if not self.module_url:
            return False
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{self.module_url.rstrip('/')}/health")
                return resp.status_code == 200
        except Exception:
            return False

    async def parse_file(self,file_content: bytes,filename: str,project_id: str,user_id: Optional[str] = None,course_id: Optional[str] = None,) -> tuple[list, Optional[str]]:
        if not self.module_url:
            raise ValueError("Input parsing module URL not configured")

        parsed_content = await self._call_parsing_module(file_content, filename, user_id, course_id)
        file_id = parsed_content.get("file_id")

        if file_id:
            rag_chunks = await self.fetch_chunks_from_db(file_id=file_id,
                project_id=project_id,
                source_filename=filename,
                source_type=parsed_content.get("source_type", "unknown"),
                doc_title=parsed_content.get("title") or filename,
                user_id=user_id,
                course_id=course_id)
            if rag_chunks:
                return rag_chunks, file_id

        rag_chunks = self._convert_to_rag_chunks(
            parsed_content=parsed_content,
            project_id=project_id,
            source_filename=filename,
            user_id=user_id,
            course_id=course_id
        )
        return rag_chunks, file_id

    async def find_existing_file(self,filename: str,course_id: Optional[str] = None,user_id: Optional[str] = None,) -> Optional[str]:
        if not self.module_url:
            return None
        if not course_id and not user_id:
            return None
        url = (f"{self.module_url.rstrip('/')}/courses/{course_id}/files"
            if course_id
            else f"{self.module_url.rstrip('/')}/files/user/{user_id}")
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(url)
                if resp.status_code != 200:
                    return None
                files = resp.json()
                if not isinstance(files, list):
                    return None
                for f in files:
                    if f.get("file_name") == filename:
                        return f.get("file_id")
        except Exception as e:
            logger.warning(f"file existence check in db failed: {e}")
        return None

    async def fetch_chunks_from_db(self,file_id: str,project_id: str,source_filename: str = "",source_type: str = "unknown",doc_title: str = "",user_id: Optional[str] = None,course_id: Optional[str] = None,) -> list:
        if not self.module_url:
            raise ValueError("parsing module URL not configured")

        url = f"{self.module_url.rstrip('/')}/files/{file_id}/chunks"
        try:
            async with httpx.AsyncClient(timeout=PARSING_TIMEOUT) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                db_chunks = resp.json()
        except httpx.ConnectError:
            logger.error(f"parsing module not running at {self.module_url}")
            raise ConnectionError(f"parsing module is not reachable at {self.module_url}")
        except httpx.TimeoutException:
            logger.error("parsing module timed out fetching chunks")
            raise TimeoutError("parsing module timed out while fetching chunks.")
        except httpx.HTTPStatusError as e:
            logger.error(f"get-chunks returned {e.response.status_code}: {e.response.text[:200]}")
            raise RuntimeError(f"parsing get-chunks error: {e.response.status_code}")
        rag_chunks = []
        chunk_counter = 0
        final_source_type = db_chunks.get("source_type") or source_type
        final_doc_title = db_chunks.get("title") or doc_title or source_filename
        sections = db_chunks.get("sections", [])
        for section in sections:
            heading = section.get("heading", "")
            page = section.get("page")
            for c in section.get("chunks", []):
                content = (c.get("content") or "").strip()
                if not content:
                    continue
                chunk_metadata = c.get("metadata") or {}
                metadata = {"source": source_filename,
                    "source_type": final_source_type,
                    "doc_title": final_doc_title,
                    "page": page or chunk_metadata.get("page"),
                    "section_heading": heading or chunk_metadata.get("section_heading"),
                    "chunk_type": chunk_metadata.get("chunk_type", "text"),
                    "project_id": project_id,
                    "user_id": user_id,
                    "course_id": course_id,
                    "file_id": file_id,
                    "parsing_chunk_id": c.get("id"),}
                if chunk_metadata.get("image_path"):
                    metadata["image_path"] = chunk_metadata["image_path"]
                rag_chunks.append(RAGChunk(chunk_id=chunk_counter, text=content, metadata=metadata))
                chunk_counter += 1
        logger.info(f"Fetched {len(rag_chunks)} chunks from DB for file_id={file_id} "
            f"(project {project_id})")
        return rag_chunks

    async def _call_parsing_module(
        self, file_content: bytes, filename: str, user_id: Optional[str] = None, course_id: Optional[str] = None
    ) -> dict:
        url = f"{self.module_url.rstrip('/')}/upload"
        params = {}
        if user_id: params["user_id"] = user_id
        if course_id: params["course_id"] = course_id
        try:
            async with httpx.AsyncClient(timeout=PARSING_TIMEOUT) as client:
                files = {"file": (filename, file_content)}
                resp = await client.post(url, files=files, params=params)
                resp.raise_for_status()
                return InputParsingResponse.model_validate(
                    resp.json()
                ).model_dump()
        except httpx.ConnectError:
            logger.error(f"Input parsing module not running at {self.module_url}")
            raise ConnectionError(f"Input parsing module is not reachable at {self.module_url}")
        except httpx.TimeoutException:
            logger.error("Input parsing module timed out")
            raise TimeoutError("Input parsing module timed out. The file may be too large.")
        except httpx.HTTPStatusError as e:
            logger.error(f"Input parsing module returned {e.response.status_code}: "
                f"{e.response.text[:200]}")
            raise RuntimeError(f"Input parsing module error: {e.response.status_code}")

    def _convert_to_rag_chunks(self,parsed_content: dict,project_id: str,source_filename: str,user_id: Optional[str] = None,course_id: Optional[str] = None,) -> list:
        source_type = parsed_content.get("source_type", "unknown")
        doc_title = parsed_content.get("title") or source_filename
        sections = parsed_content.get("sections", [])
        rag_chunks = []
        chunk_counter = 0
        for section in sections:
            heading = section.get("heading", "")
            page = section.get("page")
            for chunk in section.get("chunks", []):
                content = chunk.get("content", "")
                chunk_metadata = chunk.get("metadata", {})
                chunk_type = chunk_metadata.get("chunk_type", "text")
                if not content or not content.strip():
                    continue
                metadata = {"source": source_filename,
                    "source_type": source_type,
                    "doc_title": doc_title,
                    "page": page or chunk_metadata.get("page"),
                    "section_heading": heading or chunk_metadata.get(
                        "section_heading"),
                    "chunk_type": chunk_type,
                    "project_id": project_id,
                    "user_id": user_id,
                    "course_id": course_id,
                    "parsing_chunk_id": chunk.get("id"),}
                if chunk_metadata.get("image_path"):
                    metadata["image_path"] = chunk_metadata["image_path"]
                rag_chunks.append(RAGChunk(
                    chunk_id=chunk_counter,
                    text=content,
                    metadata=metadata,
                ))
                chunk_counter += 1
        logger.info(f"Converted {chunk_counter} chunks from {source_type} "
            f"file '{source_filename}' ({len(sections)} sections)")
        return rag_chunks

    def convert_video_response(self,parsed_content: dict,project_id: str,source_filename: str,user_id: Optional[str] = None,course_id: Optional[str] = None,) -> list:
        doc_title = parsed_content.get("title") or source_filename
        sections = parsed_content.get("sections", [])
        rag_chunks = []
        for idx, section in enumerate(sections):
            content = section.get("content", "")
            if not content or not content.strip():
                continue
            rag_chunks.append(RAGChunk(
                chunk_id=idx,
                text=content,
                metadata={
                    "source": source_filename,
                    "source_type": "video",
                    "doc_title": doc_title,
                    "page": None,
                    "section_heading": section.get("heading", "Transcript"),
                    "chunk_type": "text",
                    "project_id": project_id,
                    "user_id": user_id,
                    "course_id": course_id,
                },
            ))
        logger.info(
            f"Converted {len(rag_chunks)} chunks from video transcript "
            f"'{source_filename}'"
        )
        return rag_chunks
