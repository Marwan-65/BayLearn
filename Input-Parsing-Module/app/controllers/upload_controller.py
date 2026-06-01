from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from sqlalchemy.orm import Session

from app.models.database import get_db, DEFAULT_USER_ID
from app.services.parsing_service import ParsingService
from app.services.db_service import DBService

router = APIRouter()
parsing_service = ParsingService()
db_service = DBService()


# ── Upload ────────────────────────────────────────────────────────
@router.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    user_id: str = DEFAULT_USER_ID,  # placeholder user (seeded on startup) — replace with real auth later
    db: Session = Depends(get_db),
):
    """
    Upload a file (PDF, audio, video, image), parse it, and save to DB.
    Returns the file record with its ID for use by other modules.
    """
    try:
        result = await parsing_service.process(file, user_id=user_id, db=db)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ── Fetch all files for a user ────────────────────────────────────
@router.get("/files/{user_id}")
def get_user_files(user_id: str, db: Session = Depends(get_db)):
    """
    Get all files uploaded by a user.
    Used by other modules to list a user's available material.
    """
    files = db_service.get_files_by_user(db, user_id)
    return [
        {
            "file_id"     : f.id,
            "title"       : f.title,
            "source_type" : f.source_type,
            "file_name"   : f.file_name,
            "total_chunks": f.total_chunks,
            "uploaded_at" : f.uploaded_at.isoformat(),
        }
        for f in files
    ]


# ── Fetch all chunks for a file ───────────────────────────────────
@router.get("/files/{file_id}/chunks")
def get_file_chunks(file_id: str, db: Session = Depends(get_db)):
    """
    Get all chunks for a specific file in order.
    This is the main endpoint for RAG and question generation modules.
    """
    chunks = db_service.get_chunks_by_file(db, file_id)
    if not chunks:
        raise HTTPException(status_code=404, detail="File not found or has no chunks")
    return [
        {
            "chunk_id"      : c.id,
            "content"       : c.content,
            "chunk_index"   : c.chunk_index,
            "chunk_type"    : c.chunk_type,
            "chunk_metadata": c.chunk_metadata,
        }
        for c in chunks
    ]


# ── Fetch a single file record ────────────────────────────────────
@router.get("/files/{file_id}")
def get_file(file_id: str, db: Session = Depends(get_db)):
    """Get metadata for a single file by its ID."""
    f = db_service.get_file_by_id(db, file_id)
    if not f:
        raise HTTPException(status_code=404, detail="File not found")
    return {
        "file_id"     : f.id,
        "title"       : f.title,
        "source_type" : f.source_type,
        "file_name"   : f.file_name,
        "file_path"   : f.file_path,
        "total_chunks": f.total_chunks,
        "uploaded_at" : f.uploaded_at.isoformat(),
    }


# ── Delete a file ─────────────────────────────────────────────────
@router.delete("/files/{file_id}")
def delete_file(file_id: str, db: Session = Depends(get_db)):
    """Delete a file and all its chunks from the DB."""
    deleted = db_service.delete_file(db, file_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="File not found")
    return {"message": "File deleted successfully"}
