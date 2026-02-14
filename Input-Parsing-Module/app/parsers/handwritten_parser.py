import pytesseract
from PIL import Image
from app.parsers.base_parser import BaseParser
from app.models.unified_content_schema import ParsedContent

class HandwrittenParser(BaseParser):

    def preprocess(self, file_path):
        return Image.open(file_path)

    def extract(self, image):
        return pytesseract.image_to_string(image)

    def structure(self, raw_text):
        return ParsedContent(
            source_type="handwritten",
            title="Handwritten Document",
            sections=[{
                "heading": "Extracted Text",
                "content": raw_text,
                "page": 1
            }],
            keywords=[],
            difficulty_level=None,
            estimated_duration=None
        )
