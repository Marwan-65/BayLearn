from sqlalchemy.orm import Session

from app.models.db_models import Course, UploadedFile, Section, Chunk
from app.models.unified_content_schema import ParsedContent


class DBService:

    # ── Courses ───────────────────────────────────────────────────

    def create_course(self, db: Session, user_id: str, name: str, description: str = None) -> Course:
        """Create a new course for a user."""
        course = Course(user_id=user_id, name=name, description=description)
        db.add(course)
        db.commit()
        db.refresh(course)
        return course

    def get_courses_by_user(self, db: Session, user_id: str) -> list[Course]:
        """Get all courses for a user, newest first."""
        return (
            db.query(Course)
            .filter(Course.user_id == user_id)
            .order_by(Course.created_at.desc())
            .all()
        )

    def get_course_by_id(self, db: Session, course_id: str) -> Course | None:
        """Get a single course by ID."""
        return db.query(Course).filter(Course.id == course_id).first()

    def update_course(self, db: Session, course_id: str, name: str = None, description: str = None) -> Course | None:
        """Update a course's name or description."""
        course = self.get_course_by_id(db, course_id)
        if not course:
            return None
        if name is not None:
            course.name = name
        if description is not None:
            course.description = description
        db.commit()
        db.refresh(course)
        return course

    def delete_course(self, db: Session, course_id: str) -> bool:
        """
        Delete a course. Files inside it have course_id set to NULL (not deleted)
        because ondelete="SET NULL" is set on the FK — the material is preserved.
        Returns True if deleted, False if not found.
        """
        course = self.get_course_by_id(db, course_id)
        if not course:
            return False
        db.delete(course)
        db.commit()
        return True

    def get_files_by_course(self, db: Session, course_id: str) -> list[UploadedFile]:
        """Get all files in a course, newest first."""
        return (
            db.query(UploadedFile)
            .filter(UploadedFile.course_id == course_id)
            .order_by(UploadedFile.uploaded_at.desc())
            .all()
        )

    # ── Files ─────────────────────────────────────────────────────

    def save_parsed_content(
        self,
        db: Session,
        parsed: ParsedContent,
        user_id: str,
        file_name: str,
        file_type: str,
        file_path: str,
        course_id: str = None,
    ) -> UploadedFile:
        """
        Persist a full ParsedContent object to the DB in one transaction.
        course_id is optional — pass it to assign the file to a course.
        """
        db_file = UploadedFile(
            user_id      = user_id,
            course_id    = course_id,
            file_name    = file_name,
            file_type    = file_type,
            source_type  = parsed.source_type,
            title        = parsed.title,
            file_path    = file_path,
            total_chunks = parsed.total_chunks,
        )
        db.add(db_file)
        db.flush()

        for section_index, section in enumerate(parsed.sections):
            db_section = Section(
                id            = section.id,
                file_id       = db_file.id,
                heading       = section.heading,
                page          = section.page,
                section_index = section_index,
            )
            db.add(db_section)
            db.flush()

            for chunk in section.chunks:
                db.add(Chunk(
                    id             = chunk.id,
                    section_id     = db_section.id,
                    file_id        = db_file.id,
                    content        = chunk.content,
                    chunk_index    = chunk.chunk_index,
                    chunk_type     = chunk.metadata.get("chunk_type"),
                    chunk_metadata = chunk.metadata,
                ))

        db.commit()
        db.refresh(db_file)
        return db_file

    def get_files_by_user(self, db: Session, user_id: str) -> list[UploadedFile]:
        """Get all files for a user (across all courses), newest first."""
        return (
            db.query(UploadedFile)
            .filter(UploadedFile.user_id == user_id)
            .order_by(UploadedFile.uploaded_at.desc())
            .all()
        )

    def get_file_by_id(self, db: Session, file_id: str) -> UploadedFile | None:
        return db.query(UploadedFile).filter(UploadedFile.id == file_id).first()

    def get_chunks_by_file(self, db: Session, file_id: str) -> list[Chunk]:
        """Get all chunks for a file in order — main entry point for RAG and question generation."""
        return (
            db.query(Chunk)
            .filter(Chunk.file_id == file_id)
            .order_by(Chunk.chunk_index)
            .all()
        )

    def delete_file(self, db: Session, file_id: str) -> bool:
        """Delete a file and all its sections and chunks (cascade)."""
        db_file = self.get_file_by_id(db, file_id)
        if not db_file:
            return False
        db.delete(db_file)
        db.commit()
        return True

    def assign_file_to_course(self, db: Session, file_id: str, course_id) -> UploadedFile | None:
        """
        Assign a file to a course or remove it from its course (pass course_id=None).
        Returns the updated file, or None if file not found.
        """
        db_file = self.get_file_by_id(db, file_id)
        if not db_file:
            return None
        db_file.course_id = course_id
        db.commit()
        db.refresh(db_file)
        return db_file