import os
from sqlalchemy.orm import Session

from app.models.db_models import UploadedFile, Section, Chunk
from app.models.unified_content_schema import ParsedContent


class DBService:
    """
    Saves a ParsedContent object (output of any parser) to PostgreSQL.

    Usage:
        db_service = DBService()
        uploaded_file = db_service.save_parsed_content(
            db=db,
            parsed=parsed_content,
            user_id="abc-123",
            file_name="lecture1.mp3",
            file_type="mp3",
            file_path="uploads/user_abc/lecture1.mp3",
        )
    """

    def save_parsed_content(
        self,
        db: Session,
        parsed: ParsedContent,
        user_id: str,
        file_name: str,
        file_type: str,
        file_path: str,
    ) -> UploadedFile:
        """
        Persist a full ParsedContent object to the DB in one transaction.

        Creates:
          - 1 UploadedFile row
          - 1 Section row per section
          - 1 Chunk row per chunk

        Returns the saved UploadedFile ORM object.
        """

        # ── 1. Save the file record ───────────────────────────────
        db_file = UploadedFile(
            user_id     = user_id,
            file_name   = file_name,
            file_type   = file_type,
            source_type = parsed.source_type,
            title       = parsed.title,
            file_path   = file_path,
            total_chunks= parsed.total_chunks,
        )
        db.add(db_file)
        db.flush()  # get db_file.id before inserting children

        # ── 2. Save sections and their chunks ─────────────────────
        for section_index, section in enumerate(parsed.sections):
            db_section = Section(
                id            = section.id,
                file_id       = db_file.id,
                heading       = section.heading,
                page          = section.page,
                section_index = section_index,
            )
            db.add(db_section)
            db.flush()  # get db_section.id before inserting chunks

            for chunk in section.chunks:
                db_chunk = Chunk(
                    id             = chunk.id,
                    section_id     = db_section.id,
                    file_id        = db_file.id,
                    content        = chunk.content,
                    chunk_index    = chunk.chunk_index,
                    chunk_type     = chunk.metadata.get("chunk_type"),
                    chunk_metadata = chunk.metadata,
                )
                db.add(db_chunk)

        # ── 3. Commit everything in one transaction ───────────────
        db.commit()
        db.refresh(db_file)

        return db_file

    def get_files_by_user(self, db: Session, user_id: str) -> list[UploadedFile]:
        """Get all files uploaded by a user, newest first."""
        return (
            db.query(UploadedFile)
            .filter(UploadedFile.user_id == user_id)
            .order_by(UploadedFile.uploaded_at.desc())
            .all()
        )

    def get_chunks_by_file(self, db: Session, file_id: str) -> list[Chunk]:
        """Get all chunks for a file in order — used by RAG and question generation."""
        return (
            db.query(Chunk)
            .filter(Chunk.file_id == file_id)
            .order_by(Chunk.chunk_index)
            .all()
        )

    def get_file_by_id(self, db: Session, file_id: str) -> UploadedFile | None:
        """Get a single file record by its ID."""
        return db.query(UploadedFile).filter(UploadedFile.id == file_id).first()

    def delete_file(self, db: Session, file_id: str) -> bool:
        """
        Delete a file and all its sections and chunks (cascade).
        Returns True if deleted, False if not found.
        """
        db_file = self.get_file_by_id(db, file_id)
        if not db_file:
            return False
        db.delete(db_file)
        db.commit()
        return True