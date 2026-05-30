from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from sqlalchemy.orm import Session
from typing import Optional

from app.models.database import get_db
from app.services.parsing_service import ParsingService
from app.services.db_service import DBService

router = APIRouter()
parsing_service = ParsingService()
db_service = DBService()


# ── Upload ────────────────────────────────────────────────────────

@router.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    user_id: str = "00000000-0000-0000-0000-000000000001",
    course_id: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """
    Upload a file (PDF, audio, video, image), parse it, and save to DB.
    Pass course_id to assign the file to a course — optional.
    """
    try:
        result = await parsing_service.process(
            file      = file,
            user_id   = user_id,
            course_id = course_id,
            db        = db,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ── Fetch all files for a user ────────────────────────────────────

@router.get("/files/user/{user_id}")
def get_user_files(user_id: str, db: Session = Depends(get_db)):
    """Get all files uploaded by a user across all courses."""
    files = db_service.get_files_by_user(db, user_id)
    return [
        {
            "file_id"     : f.id,
            "title"       : f.title,
            "source_type" : f.source_type,
            "file_name"   : f.file_name,
            "course_id"   : f.course_id,
            "total_chunks": f.total_chunks,
            "uploaded_at" : f.uploaded_at.isoformat(),
        }
        for f in files
    ]


# ── Fetch a single file ───────────────────────────────────────────

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
        "course_id"   : f.course_id,
        "total_chunks": f.total_chunks,
        "uploaded_at" : f.uploaded_at.isoformat(),
    }


# ── Fetch all chunks for a file ───────────────────────────────────

@router.get("/files/{file_id}/chunks")
def get_file_chunks(file_id: str, db: Session = Depends(get_db)):
    """
    Get all chunks for a file in order.
    Main endpoint for RAG and question generation modules.
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


# ── Delete a file ─────────────────────────────────────────────────

@router.delete("/files/{file_id}")
def delete_file(file_id: str, db: Session = Depends(get_db)):
    """Delete a file and all its chunks from the DB."""
    deleted = db_service.delete_file(db, file_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="File not found")
    return {"message": "File deleted successfully"}


# ── Assign file to a course ───────────────────────────────────────

from pydantic import BaseModel
from typing import Optional as Opt

class AssignCourseRequest(BaseModel):
    course_id: Opt[str] = None  # pass null to remove from course

@router.patch("/files/{file_id}/course")
def assign_file_to_course(
    file_id: str,
    body: AssignCourseRequest,
    db: Session = Depends(get_db),
):
    """
    Assign a file to a course or remove it from its current course.
    Pass course_id: null to uncategorize the file.
    """
    f = db_service.assign_file_to_course(db, file_id, body.course_id)
    if not f:
        raise HTTPException(status_code=404, detail="File not found")
    return {
        "file_id"  : f.id,
        "course_id": f.course_id,
        "message"  : "File assigned to course" if f.course_id else "File removed from course",
    }
