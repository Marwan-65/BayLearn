import fitz
import re
from app.parsers.base_parser import BaseParser
from app.models.unified_content_schema import ParsedContent


class PDFParser(BaseParser):

    def preprocess(self, file_path):
        return file_path

    def extract(self, file_path):
        doc = fitz.open(file_path)
        pages = []

        for page_number, page in enumerate(doc, start=1):
            text = page.get_text("text")
            cleaned_text = self.clean_text(text)

            pages.append({
                "page": page_number,
                "content": cleaned_text
            })

        return pages

    def clean_text(self, text):
        # Remove repeated footer date patterns
        text = re.sub(r"\d{1,2}\s\w+\s\d{4}", "", text)

        # Remove repeated instructor name
        text = re.sub(r"AYMAN ABOELHASSAN", "", text, flags=re.IGNORECASE)

        # Remove extra blank lines
        text = re.sub(r"\n\s*\n", "\n\n", text)

        return text.strip()

    def structure(self, pages):
        sections = []

        for page in pages:
            lines = page["content"].split("\n")

            if not lines:
                continue

            heading = lines[0].strip()

            sections.append({
                "heading": heading,
                "content": page["content"],
                "page": page["page"]
            })

        return ParsedContent(
            source_type="pdf",
            title=sections[0]["heading"] if sections else "PDF Document",
            sections=sections,
            keywords=[],
            difficulty_level=None,
            estimated_duration=None
        )
