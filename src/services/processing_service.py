import re
from parsers.pdf_parser import PDFParser
from models.chunk import Chunk as RAGChunk
import logging
import re
logger = logging.getLogger(__name__)


class ProcessingService:
    """
    Adapter between Rehab's PDF parser and our RAG pipeline.

    WHY this pattern?
    This is called the "Adapter Pattern" — it translates between
    two incompatible interfaces without changing either one.
    Rehab's Chunk: (id:str, content:str, chunk_index:int)
    Our RAG Chunk: (chunk_id:int, text:str, metadata:dict)
    This service translates so both modules stay independent.
    """

    def __init__(self):
        self.pdf_parser = PDFParser()
        self.chunk_counter = 0
        
    def split_large_chunk_by_sections(self, text: str) -> list:
        """
        Split a large chunk into smaller topic-focused chunks.
        """
        section_pattern = r'(?=\b[A-Z][A-Z\s&]{4,}\b)'
        sections = re.split(section_pattern, text)
        
        chunks = []
        for section in sections:
            section = section.strip()
            if len(section) > 80:
                chunks.append(section)
        
        if len(chunks) <= 1:
            bullet_pattern = r'(?=•|\n-|\n\*)'
            chunks = [c.strip() for c in re.split(bullet_pattern, text) if len(c.strip()) > 80]
        
        return chunks if len(chunks) > 1 else [text]

    def process_pdf(self, file_path: str, project_id: str) -> list:
        """
        Parse a PDF and return RAG-ready chunks.
        """
        logger.info(f"Processing PDF: {file_path}")

        # Run Rehab's full pipeline: preprocess → extract → structure
        parsed_content = self.pdf_parser.parse(file_path)
        doc_title = parsed_content.title
        # or os.path.basename(file_path)
        logger.info(f"Parser returned {parsed_content.total_chunks} chunks "
                   f"from {len(parsed_content.sections)} sections")

        rag_chunks = []

        for section in parsed_content.sections:
            for chunk in section.chunks:
            # ── Contextual Header (Anthropic technique, 2024) ──
            # WHY: Prepending context before embedding helps the model
            # understand WHERE this chunk comes from, not just WHAT it says.
            # This reduces embedding ambiguity and improves retrieval by 49%.
                if chunk.metadata.get("chunk_type") != "text":
                    continue
                raw_text = chunk.content
                # Split large chunks by section headers or bullets
                if len(raw_text) > MEDIUM_THRESHOLD:
                    sub_chunks = self.split_large_chunk_by_sections(raw_text)
                else:
                    sub_chunks = [raw_text]               
                for sub_chunk in sub_chunks:
                    contextual_text = (
                        f"Document: {doc_title} | "
                        f"Page: {section.page} | "
                        f"Section: {section.heading}\n\n"
                        f"{sub_chunk}"
                    )
                    metadata = {
                        "source": file_path,
                        "doc_title": doc_title,
                        "page": section.page,
                        "section_heading": section.heading,
                        "chunk_type": "text",
                        "page_kind": chunk.metadata.get("page_kind", "document"),
                        "project_id": project_id,
                    }

                    # If no retriever → pass as-is
                    rag_chunks.append(RAGChunk(
                        chunk_id=self.chunk_counter,
                        text=contextual_text,
                        metadata=metadata
                    ))
                self.chunk_counter += 1

        logger.info(f"Converted to {len(rag_chunks)} RAG chunks")
        return rag_chunks