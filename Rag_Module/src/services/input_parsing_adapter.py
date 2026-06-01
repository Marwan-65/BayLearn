"""
Input Parsing Integration Adapter

Design Pattern: The Adapter design pattern is a structural pattern that acts as a bridge between two 
incompatible interfaces, allowing them to work together without modifying existing code.

This adapter allows the RAG module to consume the Input Parsing Module's
output via HTTP, converting ParsedContent responses into RAG-ready chunks.

Input Parsing Module API:
    POST /upload (multipart/form-data, field="file")
    Returns: ParsedContent JSON with sections/chunks

This adapter:
    1. Forwards uploaded files to the input parsing module
    2. Converts ParsedContent -> list[RAGChunk]
    3. Stores chunks in the chunk_repository
    4. Supports fallback to local parsing if module is unavailable
"""

import httpx
import logging
from typing import Optional
from models.chunk import Chunk as RAGChunk
from routes.schemes.orchestrator import InputParsingResponse

logger = logging.getLogger(__name__)

# Timeout for parsing module calls (large PDFs can be slow).
# Headroom for big digital docs (hundreds of pages render + extract in well under
# this once embedded-image OCR is off). For very large scanned docs, prefer async
# indexing rather than raising this further.
PARSING_TIMEOUT = 300.0


class InputParsingAdapter:
    """
    Adapter between the Input Parsing Module and the RAG pipeline's chunk storage.

    Uses the Adapter Pattern — translates between:
        Input Parsing Module's ParsedContent format
        RAG pipeline's Chunk(chunk_id, text, metadata) format
    """

    def __init__(self, module_url: Optional[str] = None):
        self.module_url = module_url

    @property
    def is_available(self) -> bool:
        """Check if the input parsing module URL is configured."""
        return bool(self.module_url)

    async def check_health(self) -> bool:
        """Check if the input parsing module is reachable."""
        if not self.module_url:
            return False
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{self.module_url.rstrip('/')}/health")
                return resp.status_code == 200
        except Exception:
            return False

    async def parse_file(
        self,
        file_content: bytes,
        filename: str,
        project_id: str,
    ) -> tuple[list, Optional[str]]:
        """
        Upload a file to the Input Parsing Module (which parses it and persists
        it to the shared database), then read the resulting chunks back FROM the
        database via GET /files/{file_id}/chunks and convert them to RAG chunks.

        This makes the database the single source of truth: the file is uploaded
        once, and every module (RAG, question-gen, ...) reads the same chunks via
        the parsing module's get-chunks route rather than keeping private copies.

        Args:
            file_content: Raw file bytes
            filename: Original filename (used for content-type detection)
            project_id: Project ID for metadata

        Returns:
            (rag_chunks, file_id) — rag_chunks is ready for
            chunk_repository.add_chunks(); file_id is the DB id of the saved file
            (None if the parsing module did not return one).
        """
        if not self.module_url:
            raise ValueError("Input parsing module URL not configured")

        # 1. Upload — parsing module parses and saves to the DB, returns file_id.
        parsed_content = await self._call_parsing_module(file_content, filename)
        file_id = parsed_content.get("file_id")

        # 2. Prefer reading chunks back from the DB (single source of truth).
        if file_id:
            rag_chunks = await self.fetch_chunks_from_db(
                file_id=file_id,
                project_id=project_id,
                source_filename=filename,
                source_type=parsed_content.get("source_type", "unknown"),
                doc_title=parsed_content.get("title") or filename,
            )
            if rag_chunks:
                return rag_chunks, file_id

        # 3. Fallback: older parsing module without a file_id / DB — convert the
        #    inline ParsedContent from the upload response directly.
        rag_chunks = self._convert_to_rag_chunks(
            parsed_content=parsed_content,
            project_id=project_id,
            source_filename=filename,
        )
        return rag_chunks, file_id

    async def fetch_chunks_from_db(
        self,
        file_id: str,
        project_id: str,
        source_filename: str = "",
        source_type: str = "unknown",
        doc_title: str = "",
    ) -> list:
        """
        Read a file's chunks from the parsing module's database via
        GET /files/{file_id}/chunks and convert them to RAG chunks.

        The DB chunk shape is:
            {chunk_id, content, chunk_index, chunk_type, chunk_metadata}

        Any module can call this with a file_id to get the canonical chunks
        without re-uploading or re-parsing.
        """
        if not self.module_url:
            raise ValueError("Input parsing module URL not configured")

        url = f"{self.module_url.rstrip('/')}/files/{file_id}/chunks"
        try:
            async with httpx.AsyncClient(timeout=PARSING_TIMEOUT) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                db_chunks = resp.json()
        except httpx.ConnectError:
            logger.error(f"Input parsing module not running at {self.module_url}")
            raise ConnectionError(
                f"Input parsing module is not reachable at {self.module_url}"
            )
        except httpx.TimeoutException:
            logger.error("Input parsing module timed out fetching chunks")
            raise TimeoutError("Input parsing module timed out while fetching chunks.")
        except httpx.HTTPStatusError as e:
            logger.error(
                f"get-chunks returned {e.response.status_code}: {e.response.text[:200]}"
            )
            raise RuntimeError(f"Input parsing get-chunks error: {e.response.status_code}")

        rag_chunks = []
        for i, c in enumerate(db_chunks):
            content = (c.get("content") or "").strip()
            if not content:
                continue
            chunk_metadata = c.get("chunk_metadata") or {}
            metadata = {
                "source": source_filename,
                "source_type": source_type,
                "doc_title": doc_title or source_filename,
                "page": chunk_metadata.get("page"),
                "section_heading": chunk_metadata.get("section_heading"),
                "chunk_type": c.get("chunk_type") or chunk_metadata.get("chunk_type", "text"),
                "project_id": project_id,
                "file_id": file_id,
                "parsing_chunk_id": c.get("chunk_id"),
            }
            if chunk_metadata.get("image_path"):
                metadata["image_path"] = chunk_metadata["image_path"]
            rag_chunks.append(RAGChunk(chunk_id=i, text=content, metadata=metadata))

        logger.info(
            f"Fetched {len(rag_chunks)} chunks from DB for file_id={file_id} "
            f"(project {project_id})"
        )
        return rag_chunks

    async def _call_parsing_module(
        self, file_content: bytes, filename: str
    ) -> dict:
        """
        Forward file to the input parsing module's POST /upload endpoint.

        The module expects multipart/form-data with field name "file".
        Returns the ParsedContent JSON response.
        """
        url = f"{self.module_url.rstrip('/')}/upload"

        try:
            async with httpx.AsyncClient(timeout=PARSING_TIMEOUT) as client:
                files = {"file": (filename, file_content)}
                resp = await client.post(url, files=files)
                resp.raise_for_status()
                # Validate the response shape against our contract.
                # Defensive: if the parsing module drifts, we fail fast here
                # rather than deep inside _convert_to_rag_chunks.
                return InputParsingResponse.model_validate(
                    resp.json()
                ).model_dump()
        except httpx.ConnectError:
            logger.error(
                f"Input parsing module not running at {self.module_url}"
            )
            raise ConnectionError(
                f"Input parsing module is not reachable at {self.module_url}"
            )
        except httpx.TimeoutException:
            logger.error("Input parsing module timed out")
            raise TimeoutError(
                "Input parsing module timed out. The file may be too large."
            )
        except httpx.HTTPStatusError as e:
            logger.error(
                f"Input parsing module returned {e.response.status_code}: "
                f"{e.response.text[:200]}"
            )
            raise RuntimeError(
                f"Input parsing module error: {e.response.status_code}"
            )

    def _convert_to_rag_chunks(
        self,
        parsed_content: dict,
        project_id: str,
        source_filename: str,
    ) -> list:
        """
        Convert the Input Parsing Module's ParsedContent format into
        RAG pipeline Chunk objects.

        ParsedContent format:
        {
            "source_type": "pdf",
            "title": "...",
            "sections": [
                {
                    "id": "uuid",
                    "heading": "Page 1",
                    "page": 1,
                    "chunks": [
                        {
                            "id": "uuid",
                            "content": "...",
                            "chunk_index": 0,
                            "metadata": {
                                "page": 1,
                                "section_heading": "Page 1",
                                "chunk_type": "text" | "image" | "table" | "equation"
                            }
                        }
                    ]
                }
            ],
            "total_chunks": 10
        }

        RAG Chunk format:
            Chunk(chunk_id=int, text=str, metadata=dict)
        """
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

                metadata = {
                    "source": source_filename,
                    "source_type": source_type,
                    "doc_title": doc_title,
                    "page": page or chunk_metadata.get("page"),
                    "section_heading": heading or chunk_metadata.get(
                        "section_heading"
                    ),
                    "chunk_type": chunk_type,
                    "project_id": project_id,
                    "parsing_chunk_id": chunk.get("id"),
                }

                # Preserve image_path for image chunks
                if chunk_metadata.get("image_path"):
                    metadata["image_path"] = chunk_metadata["image_path"]

                rag_chunks.append(RAGChunk(
                    chunk_id=chunk_counter,
                    text=content,
                    metadata=metadata,
                ))
                chunk_counter += 1

        logger.info(
            f"Converted {chunk_counter} chunks from {source_type} "
            f"file '{source_filename}' ({len(sections)} sections)"
        )
        return rag_chunks

    def convert_video_response(
        self,
        parsed_content: dict,
        project_id: str,
        source_filename: str,
    ) -> list:
        """
        Handle the legacy video response format from the input parsing module.

        Video format:
        {
            "source_type": "video",
            "title": "Video Transcript",
            "sections": [
                {"heading": "Transcript", "content": "...", "page": null}
            ]
        }
        """
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
                },
            ))

        logger.info(
            f"Converted {len(rag_chunks)} chunks from video transcript "
            f"'{source_filename}'"
        )
        return rag_chunks
