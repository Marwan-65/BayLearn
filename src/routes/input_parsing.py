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

import asyncio
import uuid
from fastapi import APIRouter, BackgroundTasks, Request, UploadFile, status
from fastapi.responses import JSONResponse
from core.limiter import limiter
from helpers.config import get_settings
import logging

logger = logging.getLogger("uvicorn.error")

# ── In-memory parse-job registry ──────────────────────────────────────────────
# Keyed by job_id. Values: {status, project_id, filename, chunks, error}
# status: "pending" | "indexing" | "done" | "error"
_JOBS: dict = {}

input_parsing_router = APIRouter(
    prefix="/api/v1/parse",
)

# Extension → category mapping for per-type size limits.
# Categories map to the UPLOAD_MAX_MB_* settings in helpers/config.py.
_EXT_CATEGORY = {
    # PDFs
    "pdf": "pdf",
    # Images
    "png": "image", "jpg": "image", "jpeg": "image",
    "gif": "image", "webp": "image", "bmp": "image", "tiff": "image",
    # Audio
    "mp3": "audio", "wav": "audio", "m4a": "audio",
    "flac": "audio", "ogg": "audio", "aac": "audio",
    # Video
    "mp4": "video", "webm": "video", "mov": "video",
    "mkv": "video", "avi": "video",
}


def _resolve_max_bytes(filename: str, settings) -> tuple[int, str]:
    """
    Determine the max upload size (in bytes) for the given filename based
    on its extension. Falls back to UPLOAD_MAX_MB_DEFAULT for unknown types.

    Returns (max_bytes, category_label).
    """
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    category = _EXT_CATEGORY.get(ext, "default")

    mb_by_category = {
        "pdf": settings.UPLOAD_MAX_MB_PDF,
        "image": settings.UPLOAD_MAX_MB_IMAGE,
        "audio": settings.UPLOAD_MAX_MB_AUDIO,
        "video": settings.UPLOAD_MAX_MB_VIDEO,
        "default": settings.UPLOAD_MAX_MB_DEFAULT,
    }
    max_mb = mb_by_category.get(category) or settings.UPLOAD_MAX_MB_DEFAULT or 25
    return max_mb * 1024 * 1024, category


async def _parse_and_index_background(
    job_id: str,
    project_id: str,
    filename: str,
    file_content: bytes,
    app,
):
    """Background task: parse → store → index. Updates _JOBS[job_id] in-place."""
    try:
        adapter = getattr(app, "input_parsing_adapter", None)
        rag_chunks = await adapter.parse_file(
            file_content=file_content,
            filename=filename,
            project_id=project_id,
        )
        _JOBS[job_id]["status"] = "indexing"
        _JOBS[job_id]["chunks_created"] = len(rag_chunks)

        # Remove any previously-indexed chunks for this file so stale metadata
        # (e.g. old chunk_type or missing image_path from a pre-fix upload)
        # doesn't survive alongside the fresh chunks and pollute retrieval.
        await app.chunk_repository.delete_chunks_by_source(project_id, filename)
        await app.chunk_repository.add_chunks(project_id, rag_chunks)

        from controllers import NLPController
        controller = NLPController(
            vectordb_client=app.vectordb_client,
            generation_client=app.generation_client,
            embedding_client=app.embedding_client,
            chunk_repository=app.chunk_repository,
            reranker_client=getattr(app, "reranker_client", None),
            bm25_client=getattr(app, "bm25_client", None),
            contextual_cache=getattr(app, "contextual_cache", None),
        )
        indexed_count = await controller.index_project(project_id=project_id, do_reset=True)
        _JOBS[job_id].update({"status": "done", "indexed_count": indexed_count})
        logger.info(f"[job {job_id}] done — {indexed_count} chunks indexed for project {project_id}")

    except Exception as e:
        _JOBS[job_id].update({"status": "error", "error": str(e)})
        logger.error(f"[job {job_id}] background parse failed: {e}")


@input_parsing_router.get("/status/{project_id}")
async def parse_status(project_id: str, filename: str):
    """
    Poll this endpoint after uploading to see when parsing finished.
    Returns the most recent job for (project_id, filename).
    """
    # Find the latest job for this project+filename
    matching = [
        j for j in _JOBS.values()
        if j["project_id"] == project_id and j["filename"] == filename
    ]
    if not matching:
        return JSONResponse(status_code=404, content={"signal": "No job found"})
    job = sorted(matching, key=lambda j: j.get("started_at", ""))[-1]
    return JSONResponse(status_code=200, content=job)


@input_parsing_router.post("/upload/{project_id}")
@limiter.limit("10/minute")
async def parse_and_store(
    project_id: str,
    request: Request,
    file: UploadFile,
    background_tasks: BackgroundTasks,
    auto_index: bool = True,
):
    """
    Upload a file and start async parsing in the background.

    Returns immediately with job_id + status="pending".
    The frontend should poll GET /api/v1/parse/status/{project_id}?filename=X
    until status becomes "done" or "error".
    """
    import datetime
    settings = get_settings()

    # Validate file
    if not file.filename:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"signal": "No file provided"},
        )

    # Resolve per-type size limit from extension, then read with that cap.
    max_bytes, category = _resolve_max_bytes(file.filename, settings)
    file_content = await file.read()
    if len(file_content) > max_bytes:
        return JSONResponse(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            content={
                "signal": (
                    f"File too large for type '{category}'. "
                    f"Max size: {max_bytes // (1024*1024)} MB"
                )
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

    # Register job and kick off background parsing
    job_id = str(uuid.uuid4())[:8]
    _JOBS[job_id] = {
        "job_id": job_id,
        "status": "pending",
        "project_id": project_id,
        "filename": file.filename,
        "chunks_created": 0,
        "indexed_count": 0,
        "error": None,
        "started_at": datetime.datetime.now().isoformat(),
    }
    background_tasks.add_task(
        _parse_and_index_background,
        job_id, project_id, file.filename, file_content, request.app,
    )

    return JSONResponse(
        status_code=status.HTTP_202_ACCEPTED,
        content={
            "signal": "Parsing started in background",
            "job_id": job_id,
            "filename": file.filename,
            "project_id": project_id,
            "status": "pending",
            "poll_url": f"/api/v1/parse/status/{project_id}?filename={file.filename}",
        },
    )


# ── Legacy sync path kept for internal/API Dog use ─────────────────────────
@input_parsing_router.post("/upload-sync/{project_id}")
async def parse_and_store_sync(
    project_id: str,
    request: Request,
    file: UploadFile,
    auto_index: bool = False,
):
    """
    Synchronous upload — blocks until parsing completes.
    Only use for small files or direct API calls (not the frontend).
    """
    settings = get_settings()

    if not file.filename:
        return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content={"signal": "No file provided"})

    max_bytes, category = _resolve_max_bytes(file.filename, settings)
    file_content = await file.read()
    if len(file_content) > max_bytes:
        return JSONResponse(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, content={"signal": f"File too large: max {max_bytes//(1024*1024)} MB"})
    if len(file_content) == 0:
        return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content={"signal": "Empty file"})

    input_parsing_adapter = getattr(request.app, "input_parsing_adapter", None)
    if not input_parsing_adapter or not input_parsing_adapter.is_available:
        return JSONResponse(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, content={"signal": "Input parsing module not configured"})

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


@input_parsing_router.delete("/source/{project_id}")
async def delete_source(project_id: str, filename: str, request: Request):
    """
    Remove all chunks that came from `filename` in `project_id`, then
    re-index the project so Qdrant and BM25 no longer contain those chunks.

    Called by the frontend when the user clicks the × on a file.
    """
    from controllers import NLPController

    repo = request.app.chunk_repository
    all_chunks = await repo.get_chunks(project_id)
    remaining = [c for c in all_chunks if c.metadata.get("source") != filename]

    if len(remaining) == len(all_chunks):
        return JSONResponse(
            status_code=200,
            content={"signal": "No chunks matched that filename", "removed": 0},
        )

    removed = len(all_chunks) - len(remaining)

    # Overwrite the project's chunk list with only the remaining chunks
    await repo.delete_project_chunks(project_id)
    if remaining:
        await repo.add_chunks(project_id, remaining)

    # Re-index so Qdrant/BM25 reflect the deletion
    indexed_count = 0
    if remaining:
        controller = NLPController(
            vectordb_client=request.app.vectordb_client,
            generation_client=request.app.generation_client,
            embedding_client=request.app.embedding_client,
            chunk_repository=repo,
            reranker_client=getattr(request.app, "reranker_client", None),
            bm25_client=getattr(request.app, "bm25_client", None),
            contextual_cache=getattr(request.app, "contextual_cache", None),
        )
        indexed_count = await controller.index_project(
            project_id=project_id, do_reset=True
        )
    else:
        # No chunks left — wipe the Qdrant collection
        try:
            request.app.vectordb_client.delete_collection(project_id)
        except Exception:
            pass

    return JSONResponse(
        status_code=200,
        content={
            "signal": f"Removed {removed} chunks for '{filename}' and re-indexed",
            "removed": removed,
            "remaining_chunks": len(remaining),
            "indexed_count": indexed_count,
        },
    )


def _count_chunk_types(chunks: list) -> dict:
    """Count chunks by type for the response."""
    counts = {}
    for chunk in chunks:
        chunk_type = chunk.metadata.get("chunk_type", "text")
        counts[chunk_type] = counts.get(chunk_type, 0) + 1
    return counts
