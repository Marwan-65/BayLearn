import os
import uuid
from PIL import Image

from app.parsers.base_parser import BaseParser
from app.parsers.pdf_parser import PDFParser
from app.models.unified_content_schema import ParsedContent, Section, Chunk


class ImageParser(BaseParser):

    # reuse PDFParser's OCR 
    _pdf_parser = PDFParser()

    def preprocess(self, file_path: str) -> Image.Image:
        """Validate the file make a clean title and path and return a PIL Image."""
        if not  os.path.isfile(file_path):
            raise  FileNotFoundError(f"Image file not found: {file_path}")

        rawname= os.path.splitext(os.path.basename(file_path))[0]
        self._title =   rawname.replace("_", " ").replace("-", " ").title()
        self._image_path  = file_path

        try:
            prep_img =Image.open(file_path).convert("RGB")
        except   Exception as e:
            raise ValueError(f"Could not open image file: {file_path}. Error: {e}")

        return  prep_img

    def extract(self, image: Image.Image) -> str:

        textt = self._pdf_parser.ocr_embedded_content( image=image,   page_is_scanned=True)
        return textt.strip() if textt else ""
    
    def structure(self, text: str) -> ParsedContent:
        """Put the extracted text in a single Section and Chunk."""
        title =  getattr(self, "_title", "Image")

        chunks = []
        if text:
            chunks.append(Chunk(
                id=str(uuid.uuid4()),
                content=text,
                chunk_index=0,
                metadata={
                    "chunk_type": "image_text",
                    "page": 1,
                    "image_path": getattr(self, "_image_path", None),
                },
            ))

        section = Section(
            id=str(uuid.uuid4()),
            heading=title,
            page=1,
            chunks=chunks,
        )

        return ParsedContent(
            source_type="image",
            title=title,
            sections=[section],
            total_chunks=len(chunks),
        )