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

# Timeout for parsing module calls (large PDFs can be slow)
PARSING_TIMEOUT = 120.0


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
    ) -> list:
        """
        Send a file to the Input Parsing Module and convert its
        ParsedContent response into RAG-ready chunks.

        Args:
            file_content: Raw file bytes
            filename: Original filename (used for content-type detection)
            project_id: Project ID for metadata

        Returns:
            List of RAGChunk objects ready for chunk_repository.add_chunks()
        """
        if not self.module_url:
            raise ValueError("Input parsing module URL not configured")

        # Call the input parsing module's /upload endpoint
        parsed_content = await self._call_parsing_module(file_content, filename)

        # Convert ParsedContent -> list[RAGChunk]
        return self._convert_to_rag_chunks(
            parsed_content=parsed_content,
            project_id=project_id,
            source_filename=filename,
        )

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
