from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional

from app.models.database import get_db
from app.services.db_service import DBService

router=APIRouter(prefix="/courses", tags=["courses"])
db_service =DBService()


# req bodies

class CreateCourseRequest(BaseModel):
    user_id: str
    name: str
    description: Optional[str] =None

class UpdateCourseRequest(BaseModel):
    name: Optional[str] =   None
    description: Optional[str] =None



def _course_response(course):
    return {
        "course_id"  : course.id,
        "name"  : course.name,
        "description": course.description,
        "created_at" : course.created_at.isoformat(),
    }

def _file_response(f):
    return {
        "file_id"    : f.id,
        "title"      : f.title,
        "source_type": f.source_type,
        "file_name"  : f.file_name,
        "total_chunks": f.total_chunks,
        "uploaded_at": f.uploaded_at.isoformat(),
    }


# endpoints

@router.post("")
def create_course(body: CreateCourseRequest, db: Session = Depends(get_db)):
    """create a new course for a user."""
    course = db_service.create_course(
        db   = db,
        user_id    = body.user_id,
        name  = body.name,
        description = body.description,
    )
    return _course_response(course)


@router.get("/user/{user_id}")
def get_user_courses(user_id: str, db: Session = Depends(get_db)):
    """Get all courses for a user"""
    courses =   db_service.get_courses_by_user(db, user_id)
    return [_course_response(c) for c in courses]


@router.get("/{course_id}")
def get_course(course_id: str, db: Session = Depends(get_db)):
    """Get a single course by ID."""
    course   =db_service.get_course_by_id(db, course_id)
    if not course:

        raise HTTPException(status_code=404, detail="Course not found")
    return _course_response(course)


@router.patch("/{course_id}")
def update_course(course_id: str, body: UpdateCourseRequest, db: Session = Depends(get_db)):
    """Update a course name or description"""

    course =db_service.update_course(
        db   = db,
        course_id  = course_id,
        name   = body.name,
        description = body.description,
    )
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    return _course_response(course)


@router.delete("/{course_id}")
def delete_course(course_id: str, db: Session = Depends(get_db)):
    """delete a course band set file course_id is to NULL 
    """

    deleted= db_service.delete_course(db, course_id)
    if not deleted:

        raise HTTPException(status_code=404, detail="Course not found")
    return {"message": "Course deleted. Files have been moved to uncategorized."}


@router.get("/{course_id}/files")
def get_course_files(course_id: str, db: Session = Depends(get_db)):
    """Get all files uploaded to a course."""

    course= db_service.get_course_by_id(db, course_id)

    if  not course:
        raise HTTPException(status_code=404, detail="Course not found")
    
    files=db_service.get_files_by_course(db, course_id)
    return [_file_response(f) for f in files]