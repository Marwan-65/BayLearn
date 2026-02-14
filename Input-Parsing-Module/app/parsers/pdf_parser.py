import fitz
from app.parsers.base_parser import BaseParser
from app.models.unified_content_schema import ParsedContent

class PDFParser(BaseParser):

    def preprocess(self, file_path):
        return file_path

    def extract(self, file_path):
        doc = fitz.open(file_path)
        text = ""
        for page in doc:
            text += page.get_text()
        return text

    def structure(self, raw_text):
        sections = [{
            "heading": "Document Content",
            "content": raw_text,
            "page": 1
        }]

        return ParsedContent(
            source_type="pdf",
            title="PDF Document",
            sections=sections,
            keywords=[],
            difficulty_level=None,
            estimated_duration=None
        )
