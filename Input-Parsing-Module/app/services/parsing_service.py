import os
from app.parsers.parser_factory import ParserFactory
from app.utils.file_utils import save_upload_file

class ParsingService:

    async def process(self, file):
        file_path = await save_upload_file(file)

        file_type = self.detect_type(file.filename)

        parser = ParserFactory.get_parser(file_type)

        result = parser.parse(file_path)

        return result

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
