# this file forwards the uploaded material to the parsing module via the adapter, so it has routes 
# it recieves also chunks and index them 

import httpx
from fastapi import APIRouter, Request, UploadFile, status
from fastapi.responses import JSONResponse
from core.limiter import limiter
from helpers.config import get_settings
import logging
from typing import Optional
from controllers._nlp_retrieval import _NLPRetrievalMixin
logger = logging.getLogger("uvicorn.error")
input_parsing_router = APIRouter(prefix="/api/v1/parse",)

# to know what to expect about limits and files nature
_EXT_CATEGORY = {
    "pdf": "pdf",
    "png": "image", "jpg": "image", "jpeg": "image",
    "gif": "image", "webp": "image", "bmp": "image", "tiff": "image",
    "mp3": "audio", "wav": "audio", "m4a": "audio",
    "flac": "audio", "ogg": "audio", "aac": "audio",
    "mp4": "video", "webm": "video", "mov": "video",
    "mkv": "video", "avi": "video",
}

def _resolve_max_bytes(filename: str, settings) -> tuple[int, str]:
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

def _count_chunk_types(chunks: list) -> dict:
    counts = {}
    for chunk in chunks:
        chunk_type = chunk.metadata.get("chunk_type", "text")
        counts[chunk_type] = counts.get(chunk_type, 0) + 1
    return counts

def _build_nlp_controller(app):
    from controllers import NLPController
    return NLPController(
        vectordb_client=app.vectordb_client,
        generation_client=app.generation_client,
        embedding_client=app.embedding_client,
        reranker_client=getattr(app, "reranker_client", None),
        bm25_client=getattr(app, "bm25_client", None),
        contextual_cache=getattr(app, "contextual_cache", None),
    )

@input_parsing_router.post("/upload/{project_id}")
@limiter.limit("10/minute")
async def parse_and_store(project_id: str,request: Request,file: UploadFile,
    auto_index: bool = True,user_id: Optional[str] = None,
    course_id: Optional[str] = None,
):
    settings = get_settings()

    if not file.filename:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"signal": "No file provided"},)
    adapter = getattr(request.app, "input_parsing_adapter", None)
    if not adapter or not adapter.is_available:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"signal": "Input parsing module not configured. Set INPUT_PARSING_MODULE_URL in .env"},)
    existing_file_id = await adapter.find_existing_file(
        filename=file.filename,
        course_id=course_id,
        user_id=user_id,)
    if existing_file_id:
        logger.info(
            f"file '{file.filename}' already in DB (file_id={existing_file_id}). "
            "skipping upload, re-indexing for RAG.")
        try:
            rag_chunks = await adapter.fetch_chunks_from_db(file_id=existing_file_id,
                project_id=existing_file_id,
                source_filename=file.filename,
                user_id=user_id,
                course_id=course_id,)
        except Exception as e:
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content={"signal": f"Failed to fetch existing file chunks: {str(e)}"},)
        if not rag_chunks:
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND,
                content={"signal": f"File exists in DB but has no chunks (file_id={existing_file_id})"},)
        result = {"signal": "File already existed in DB — re-indexed for RAG",
            "filename": file.filename,"file_id": existing_file_id,
            "chunks_created": len(rag_chunks),
            "project_id": project_id,
            "chunk_types": _count_chunk_types(rag_chunks),
            "already_existed": True,}
        if auto_index:
            try:
                controller = _build_nlp_controller(request.app)
                indexed_count = await controller.index_project(
                    project_id=existing_file_id,
                    chunks=rag_chunks,
                    do_reset=True,)
                result["indexed"] = True
                result["indexed_count"] = indexed_count
            except Exception as e:
                logger.error(f"Re-indexing failed for existing file: {e}")
                result["indexed"] = False
                result["index_error"] = str(e)
        return JSONResponse(status_code=status.HTTP_200_OK, content=result)
    max_bytes, category = _resolve_max_bytes(file.filename, settings)
    file_content = await file.read()
    if len(file_content) > max_bytes:
        return JSONResponse(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            content={"signal": f"File too large for type '{category}'. Max: {max_bytes // (1024*1024)} MB"},
        )
    if len(file_content) == 0:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"signal": "Empty file"},)
    try:
        rag_chunks, file_id = await adapter.parse_file(
            file_content=file_content,
            filename=file.filename,
            project_id=project_id,
            user_id=user_id,
            course_id=course_id,)
    except ConnectionError as e:
        return JSONResponse(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, content={"signal": str(e)})
    except TimeoutError as e:
        return JSONResponse(status_code=status.HTTP_504_GATEWAY_TIMEOUT, content={"signal": str(e)})
    except Exception as e:
        logger.error(f"Parsing failed for {file.filename}: {e}")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"signal": f"Parsing failed: {str(e)}"},)
    if not rag_chunks:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"signal": "No content could be extracted from this file"},)
    index_key = file_id or project_id
    result = {"signal": "File parsed and indexed successfully",
        "filename": file.filename,
        "file_id": file_id,
        "chunks_created": len(rag_chunks),
        "project_id": project_id,"chunk_types": _count_chunk_types(rag_chunks),"already_existed": False,}
    if auto_index:
        try:
            controller = _build_nlp_controller(request.app)
            indexed_count = await controller.index_project(
                project_id=index_key,
                chunks=rag_chunks,
                do_reset=True,)
            result["indexed"] = True
            result["indexed_count"] = indexed_count
        except Exception as e:
            logger.error(f"Indexing failed for {file.filename}: {e}")
            result["indexed"] = False
            result["index_error"] = str(e)
    return JSONResponse(status_code=status.HTTP_200_OK, content=result)

@input_parsing_router.post("/index-from-db")
async def index_from_db(request: Request,file_id: str,project_id: Optional[str] = None,user_id: Optional[str] = None,course_id: Optional[str] = None,):
    adapter = getattr(request.app, "input_parsing_adapter", None)
    if not adapter or not adapter.is_available:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"signal": "Input parsing module not configured"},
        )
    index_key = project_id or file_id
    try:
        rag_chunks = await adapter.fetch_chunks_from_db(
            file_id=file_id,
            project_id=index_key,
            user_id=user_id,
            course_id=course_id,)
    except Exception as e:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"signal": f"Failed to fetch chunks from DB: {str(e)}"},)
    if not rag_chunks:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"signal": f"No chunks found for file_id={file_id}. Has the file been uploaded?"},)
    try:
        controller = _build_nlp_controller(request.app)
        indexed_count = await controller.index_project(
            project_id=file_id,
            chunks=rag_chunks,
            do_reset=True,)
    except Exception as e:
        logger.error(f"indexing failed for file_id={file_id}: {e}")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"signal": f"indexing failed: {str(e)}"},)

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "signal": "file indexed from DB successfully",
            "file_id": file_id,
            "chunks_indexed": indexed_count,
            "chunk_types": _count_chunk_types(rag_chunks),},)

@input_parsing_router.delete("/file/{file_id}")
async def delete_file(file_id: str, request: Request):
    settings = get_settings()
    collection_name = f"collection_{file_id}"
    request.app.vectordb_client.delete_collection(collection_name)
    bm25 = getattr(request.app, "bm25_client", None)
    if bm25 is not None:
        try:
            bm25.delete_index(file_id)
        except Exception:
            pass
    _NLPRetrievalMixin._image_index_cache.pop(file_id, None)
    _NLPRetrievalMixin._chunks_by_id_cache.pop(file_id, None)
    _NLPRetrievalMixin._chunks_sorted_cache.pop(file_id, None)

    ip_url = getattr(settings, "INPUT_PARSING_MODULE_URL", None)
    db_deleted = False
    db_error = None
    if ip_url:
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.delete(f"{ip_url.rstrip('/')}/files/{file_id}")
                db_deleted = resp.status_code in (200, 204, 404)
                if not db_deleted:
                    db_error = f"DB returned {resp.status_code}"
        except Exception as e:
            db_error = str(e)
            logger.warning(f"Could not delete file from DB: {e}")
    else:
        db_error = "INPUT_PARSING_MODULE_URL not configured"
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "signal": f"File {file_id} removed from RAG index",
            "file_id": file_id,
            "qdrant_deleted": True,
            "db_deleted": db_deleted,
            **({"db_error": db_error} if db_error else {}),},)
