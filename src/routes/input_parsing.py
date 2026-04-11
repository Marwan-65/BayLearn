"""
Input Parsing Routes

Provides endpoints for uploading files through the RAG module,
which proxies them to the Input Parsing Module 
and stores the resulting chunks in the RAG pipeline.

This gives the frontend a SINGLE upload endpoint that handles:
  1. Sending the file to the input parsing module for parsing
  2. Converting the parsed output to RAG chunks
  3. Storing chunks in the chunk repository
  4. Optionally indexing them immediately

The input parsing module itself is NOT modified.
"""

from fastapi import APIRouter, Request, UploadFile, status
from fastapi.responses import JSONResponse
from core.limiter import limiter
from helpers.config import get_settings
import logging

logger = logging.getLogger("uvicorn.error")

input_parsing_router = APIRouter(
    prefix="/api/v1/parse",
)

# Max file size for uploads (10 MB) 
MAX_FILE_SIZE = 10 * 1024 * 1024 


@input_parsing_router.post("/upload/{project_id}")
@limiter.limit("10/minute")
async def parse_and_store(
    project_id: str,
    request: Request,
    file: UploadFile,
    auto_index: bool = False,
):
    """
    Upload a file, parse it via the Input Parsing Module, and store
    the resulting chunks in the RAG pipeline.

    This is the SINGLE endpoint the frontend uses for all uploads.

    Flow:
        1. Read uploaded file
        2. Forward to Input Parsing Module's POST /upload
        3. Convert ParsedContent -> RAG chunks
        4. Store in chunk_repository
        5. Optionally index in vector DB + BM25

    Query params:
        auto_index: If true, also runs indexing after storing chunks
    """
    settings = get_settings()

    # Validate file
    if not file.filename:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"signal": "No file provided"},
        )

    # Read file content with size limit
    file_content = await file.read()
    if len(file_content) > MAX_FILE_SIZE:
        return JSONResponse(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            content={
                "signal": f"File too large. Max size: {MAX_FILE_SIZE // (1024*1024)} MB"
            },
        )

    if len(file_content) == 0:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"signal": "Empty file"},
        )

    # Get the input parsing adapter
    input_parsing_adapter = getattr(request.app, "input_parsing_adapter", None)
    if not input_parsing_adapter or not input_parsing_adapter.is_available:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "signal": "Input parsing module not configured. "
                "Set INPUT_PARSING_MODULE_URL in .env"
            },
        )

    # Parse file via the input parsing module
    try:
        rag_chunks = await input_parsing_adapter.parse_file(
            file_content=file_content,
            filename=file.filename,
            project_id=project_id,
        )
    except ConnectionError as e:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"signal": str(e)},
        )
    except TimeoutError as e:
        return JSONResponse(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            content={"signal": str(e)},
        )
    except Exception as e:
        logger.error(f"Parsing failed for {file.filename}: {e}")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"signal": f"Parsing failed: {str(e)}"},
        )

    if not rag_chunks:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"signal": "No content could be extracted from this file"},
        )

    # Store chunks in the repository
    try:
        await request.app.chunk_repository.add_chunks(project_id, rag_chunks)
    except Exception as e:
        logger.error(f"Failed to store chunks: {e}")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"signal": f"Failed to store chunks: {str(e)}"},
        )

    result = {
        "signal": "File parsed and stored successfully",
        "filename": file.filename,
        "chunks_created": len(rag_chunks),
        "project_id": project_id,
        "chunk_types": _count_chunk_types(rag_chunks),
    }

    # Optionally index immediately
    if auto_index:
        try:
            from controllers import NLPController
            controller = NLPController(
                vectordb_client=request.app.vectordb_client,
                generation_client=request.app.generation_client,
                embedding_client=request.app.embedding_client,
                chunk_repository=request.app.chunk_repository,
                reranker_client=getattr(request.app, "reranker_client", None),
                bm25_client=getattr(request.app, "bm25_client", None),
                contextual_cache=getattr(request.app, "contextual_cache", None),
            )
            indexed_count = await controller.index_project(
                project_id=project_id,
                do_reset=True,
            )
            result["indexed"] = True
            result["indexed_count"] = indexed_count
        except Exception as e:
            logger.error(f"Auto-indexing failed: {e}")
            result["indexed"] = False
            result["index_error"] = str(e)

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=result,
    )


def _count_chunk_types(chunks: list) -> dict:
    """Count chunks by type for the response."""
    counts = {}
    for chunk in chunks:
        chunk_type = chunk.metadata.get("chunk_type", "text")
        counts[chunk_type] = counts.get(chunk_type, 0) + 1
    return counts
