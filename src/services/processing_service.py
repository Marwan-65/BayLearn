from parsers.pdf_parser import PDFParser
from models.chunk import Chunk as RAGChunk
import logging

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
        chunk_counter = 0

        for section in parsed_content.sections:
            for chunk in section.chunks:
            # ── Contextual Header (Anthropic technique, 2024) ──
            # WHY: Prepending context before embedding helps the model
            # understand WHERE this chunk comes from, not just WHAT it says.
            # This reduces embedding ambiguity and improves retrieval by 49%.
                chunk_type = chunk.metadata.get("chunk_type", "text")
                page = section.page
                if chunk_type == "text":
                    contextual_text = (
                        f"Document: {doc_title} | "
                        f"Page: {page} | "
                        f"Section: {section.heading}\n\n"
                        f"{chunk.content}"
                    )
                elif chunk_type == "table":
                    contextual_text = (
                        f"Table from: {doc_title} | Page: {page}\n\n"
                        f"{chunk.content}"
                    )
                else:
                    contextual_text = chunk.content

                metadata = {
                    "source": file_path,
                    "doc_title": doc_title,
                    "page": page,
                    "section_heading": section.heading,
                    "chunk_type": chunk_type,
                    "page_kind": chunk.metadata.get("page_kind", "document"),
                    "project_id": project_id,
                    #"original_text": chunk.content,  # store original separately
                }
                # Add sub_chunk info if it exists
                if "sub_chunk_index" in chunk.metadata:
                    metadata["sub_chunk_index"] = chunk.metadata["sub_chunk_index"]
                    metadata["total_sub_chunks"] = chunk.metadata["total_sub_chunks"]

                rag_chunks.append(RAGChunk(
                    chunk_id=chunk_counter,
                    text=chunk.content,
                    metadata=metadata
                ))
                chunk_counter += 1

        logger.info(f"Converted to {len(rag_chunks)} RAG chunks")
        return rag_chunks