from sqlalchemy.orm import Session
from typing import Optional

from app.parsers.parser_factory import ParserFactory
from app.services.db_service import DBService
from app.utils.file_utils import save_upload_file

db_service = DBService()


class ParsingService:

    async def process(self, file, user_id: str, db: Session, course_id: Optional[str] = None):
        # 1. Save file to disk
        file_path = await save_upload_file(file)

        # 2. Detect file type
        file_type = self.detect_type(file.filename)

        # 3. Parse the file -> ParsedContent
        parser = ParserFactory.get_parser(file_type)
        parsed = parser.parse(file_path)

        # 4. Save to database
        saved_file = db_service.save_parsed_content(
            db        = db,
            parsed    = parsed,
            user_id   = user_id,
            course_id = course_id,
            file_name = file.filename,
            file_type = file_type,
            file_path = file_path,
        )

        # 5. Return file_id + full ParsedContent structure
        return {
            "file_id"    : saved_file.id,
            "course_id"  : saved_file.course_id,
            "source_type": parsed.source_type,
            "title"      : parsed.title,
            "sections"   : [
                {
                    "id"     : section.id,
                    "heading": section.heading,
                    "page"   : section.page,
                    "chunks" : [
                        {
                            "id"         : chunk.id,
                            "content"    : chunk.content,
                            "chunk_index": chunk.chunk_index,
                            "metadata"   : chunk.metadata,
                        }
                        for chunk in section.chunks
                    ],
                }
                for section in parsed.sections
            ],
            "total_chunks": parsed.total_chunks,
        }

    def detect_type(self, filename):
        ext = filename.split(".")[-1].lower()
        if ext in ["pdf"]:
            return "pdf"
        elif ext in ["png", "jpg", "jpeg"]:
            return "image"
        elif ext in ["wav", "mp3"]:
            return "audio"
        elif ext in ["mp4", "mov"]:
            return "video"
        else:
            raise ValueError("Unsupported file type")
