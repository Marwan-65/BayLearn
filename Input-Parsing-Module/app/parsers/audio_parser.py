import whisper
from app.parsers.base_parser import BaseParser
from app.models.unified_content_schema import ParsedContent

model = whisper.load_model("base")

class AudioParser(BaseParser):

    def preprocess(self, file_path):
        return file_path

    def extract(self, file_path):
        result = model.transcribe(file_path)
        return result["text"]

    def structure(self, raw_text):
        return ParsedContent(
            source_type="audio",
            title="Audio Transcript",
            sections=[{
                "heading": "Transcript",
                "content": raw_text,
                "page": None
            }],
            keywords=[],
            difficulty_level=None,
            estimated_duration=None
        )
