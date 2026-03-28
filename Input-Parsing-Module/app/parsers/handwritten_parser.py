import uuid
from paddleocr import PaddleOCR
from app.parsers.base_parser import BaseParser
from app.models.unified_content_schema import ParsedContent

class HandwrittenParser(BaseParser):
    _ocr = None

    @classmethod
    def _get_ocr(cls):
        if cls._ocr is None:
            init_options = [
                {"use_angle_cls": True, "lang": "en", "show_log": False},
                {"use_angle_cls": True, "lang": "en"},
                {"lang": "en"},
                {},
            ]

            last_error = None
            for options in init_options:
                try:
                    cls._ocr = PaddleOCR(**options)
                    break
                except Exception as error:
                    last_error = error

            if cls._ocr is None and last_error is not None:
                raise last_error
        return cls._ocr

    def preprocess(self, file_path):
        return file_path

    def extract(self, file_path):
        ocr_engine = self._get_ocr()
        try:
            if hasattr(ocr_engine, "predict"):
                result = ocr_engine.predict(file_path)
            else:
                result = ocr_engine.ocr(file_path)
        except Exception:
            result = []

        text_lines = []
        for page_result in result or []:
            for line in page_result or []:
                if len(line) < 2:
                    continue
                recognized = line[1]
                if not recognized or len(recognized) < 1:
                    continue
                text = recognized[0].strip() if isinstance(recognized[0], str) else ""
                if text:
                    text_lines.append(text)

        return "\n".join(text_lines).strip()

    def structure(self, raw_text):
        from app.models.unified_content_schema import Section, Chunk

        text = raw_text.strip()
        chunks = []
        if text:
            chunks.append(Chunk(
                id=str(uuid.uuid4()),
                content=text,
                chunk_index=0,
                metadata={"page": 1, "chunk_type": "text", "source": "paddleocr"}
            ))

        return ParsedContent(
            source_type="handwritten",
            title="Handwritten Document",
            sections=[Section(
                id=str(uuid.uuid4()),
                heading="Extracted Text",
                page=1,
                chunks=chunks
            )],
            total_chunks=len(chunks)
        )
