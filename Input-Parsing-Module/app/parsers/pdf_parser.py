import fitz
import camelot
import pdfplumber
import uuid
import os
import re
import warnings
from app.parsers.base_parser import BaseParser
from app.models.unified_content_schema import ParsedContent

class PDFParser(BaseParser):
    def clean_text(self, text):
        """Clean and normalize text by removing extra whitespace and special characters."""
        text = re.sub(r'\s+', ' ', text)
        return text.strip()

    def convert_table_to_markdown(self, table):
        """Convert a table (list of lists) to markdown format."""
        if not table:
            return ""
        markdown_lines = []
        header = table[0]
        markdown_lines.append("| " + " | ".join(str(cell) if cell else "" for cell in header) + " |")
        markdown_lines.append("|" + "|".join(["---"] * len(header)) + "|")
        for row in table[1:]:
            markdown_lines.append("| " + " | ".join(str(cell) if cell else "" for cell in row) + " |")
        return "\n".join(markdown_lines)

    def sort_blocks_reading_order(self, blocks):
        """Sort text blocks by approximate reading order (top-to-bottom, left-to-right)."""
        def block_key(block):
            bbox = block.get("bbox")
            if not bbox:
                return (float("inf"), float("inf"))
            x0, y0, _, _ = bbox
            return (round(y0 / 10), x0)
        return sorted(blocks, key=block_key)

    def classify_page_layout(self, text_blocks):
        """Heuristically classify page as slide-like or document-like."""
        if not text_blocks:
            return "document"
        texts = [block.get("content", "") for block in text_blocks]
        word_counts = [len(text.split()) for text in texts if text]
        if not word_counts:
            return "document"
        total_words = sum(word_counts)
        avg_words_per_block = total_words / len(word_counts)
        short_blocks_ratio = len([count for count in word_counts if count <= 8]) / len(word_counts)
        if (len(word_counts) >= 4 and avg_words_per_block <= 14 and short_blocks_ratio >= 0.5) or \
           (len(word_counts) >= 8 and total_words <= 180):
            return "slide"
        return "document"

    def merge_text_blocks_for_page(self, text_blocks, page_kind):
        """Merge text blocks differently for slides vs regular documents."""
        ordered_blocks = self.sort_blocks_reading_order(text_blocks)
        if page_kind == "slide":
            return "\n".join(block["content"] for block in ordered_blocks if block.get("content"))
        return " ".join(block["content"] for block in ordered_blocks if block.get("content"))

    def get_chunking_profile(self, page_kind):
        """Return chunking parameters based on page type."""
        if page_kind == "slide":
            return {"max_chunk_size": 1200, "overlap": 120, "min_chunk_size": 220}
        return {"max_chunk_size": 2200, "overlap": 250, "min_chunk_size": 500}

    def detect_footer_texts(self, all_sections, footer_threshold=0.15):
        """Detect repeated footer texts at bottom of pages."""
        footer_candidates = {}
        for section in all_sections:
            text_blocks = [block for block in section.get("blocks", []) if block.get("type") == "text" and block.get("bbox")]
            if not text_blocks:
                continue
            page_height = next((block.get("bbox")[3] for block in text_blocks if block.get("bbox")), None)
            if not page_height:
                continue
            footer_region_threshold = page_height * (1 - footer_threshold)
            for block in text_blocks:
                bbox = block.get("bbox")
                if bbox:
                    y0, y1 = bbox[1], bbox[3]
                    if y0 >= footer_region_threshold:
                        text = block.get("content", "").strip()
                        if text and len(text) < 100:
                            normalized = text.lower()
                            footer_candidates[normalized] = footer_candidates.get(normalized, 0) + 1
        return {text for text, count in footer_candidates.items() if count >= 2}

    def bbox_overlap(self, bbox1, bbox2, threshold=0.5):
        """Check if two bounding boxes overlap significantly."""
        if not bbox1 or not bbox2:
            return False
        x0_1, y0_1, x1_1, y1_1 = bbox1
        x0_2, y0_2, x1_2, y1_2 = bbox2
        x_overlap = max(0, min(x1_1, x1_2) - max(x0_1, x0_2))
        y_overlap = max(0, min(y1_1, y1_2) - max(y0_1, y0_2))
        intersection = x_overlap * y_overlap
        area1 = (x1_1 - x0_1) * (y1_1 - y0_1)
        if area1 == 0:
            return False
        overlap_ratio = intersection / area1
        return overlap_ratio >= threshold

    def preprocess(self, file_path):
        return file_path

    def extract(self, file_path):
        doc = fitz.open(file_path)
        sections = []
        os.makedirs("extracted_images", exist_ok=True)

        with pdfplumber.open(file_path) as plumber_pdf:
            for page_number, page in enumerate(doc, start=1):
                blocks = []
                text_dict = page.get_text("dict")
                table_bboxes = []
                tables_found = []

                # Try Camelot first, fallback to pdfplumber
                with warnings.catch_warnings():
                    warnings.filterwarnings("ignore", message=".*is image-based.*")
                    try:
                        camelot_tables = camelot.read_pdf(file_path, pages=str(page_number), flavor='stream')
                        tables_found = list(camelot_tables)
                    except Exception:
                        tables_found = []

                if not tables_found:
                    pdfplumber_page = plumber_pdf.pages[page_number - 1]
                    pdfplumber_tables = pdfplumber_page.extract_tables()
                    for table in pdfplumber_tables:
                        if table:
                            markdown_table = self.convert_table_to_markdown(table)
                            blocks.append({
                                "id": str(uuid.uuid4()),
                                "type": "table",
                                "content": table,
                                "embedding_ready_text": markdown_table,
                                "bbox": None
                            })
                else:
                    for table in tables_found:
                        df = table.df
                        markdown_table = self.convert_table_to_markdown(df.values.tolist())
                        table_bbox = getattr(table, "_bbox", None)
                        if table_bbox:
                            table_bboxes.append(table_bbox)
                        blocks.append({
                            "id": str(uuid.uuid4()),
                            "type": "table",
                            "content": df.values.tolist(),
                            "embedding_ready_text": markdown_table,
                            "bbox": table_bbox
                        })

                # TEXT BLOCKS
                for block in text_dict.get("blocks", []):
                    if block["type"] == 0:
                        block_bbox = block.get("bbox")
                        is_table_content = any(self.bbox_overlap(block_bbox, tb) for tb in table_bboxes)
                        if not is_table_content:
                            text = " ".join(span["text"] for line in block["lines"] for span in line["spans"])
                            cleaned = self.clean_text(text)
                            if cleaned:
                                blocks.append({
                                    "id": str(uuid.uuid4()),
                                    "type": "text",
                                    "content": cleaned,
                                    "embedding_ready_text": cleaned,
                                    "bbox": block_bbox
                                })

                # IMAGES
                for img_index, img in enumerate(page.get_images(full=True)):
                    xref = img[0]
                    pix = fitz.Pixmap(doc, xref)
                    image_path = f"extracted_images/page{page_number}_{img_index}.png"
                    pix.save(image_path)
                    blocks.append({
                        "id": str(uuid.uuid4()),
                        "type": "image",
                        "content": image_path,
                        "embedding_ready_text": f"Image located on page {page_number}",
                        "bbox": None
                    })

                sections.append({
                    "id": str(uuid.uuid4()),
                    "heading": f"Page {page_number}",
                    "page": page_number,
                    "blocks": blocks
                })

        # Remove footers
        detected_footers = self.detect_footer_texts(sections)
        for section in sections:
            section["blocks"] = [
                block for block in section["blocks"]
                if not (block.get("type") == "text" and block.get("content", "").lower() in detected_footers)
            ]

        return {"sections": sections, "metadata": doc.metadata}

    def split_text_into_chunks(self, text, max_chunk_size=1800, overlap=200, min_chunk_size=400):
        if len(text) <= max_chunk_size:
            return [text]
        sentences = re.split(r'(?<=[.!?])\s+', text)
        chunks, current_chunk = [], ""
        for sentence in sentences:
            if len(current_chunk) + len(sentence) + 1 <= max_chunk_size:
                current_chunk += sentence + " "
            else:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                tail = chunks[-1][-overlap:] if overlap > 0 and chunks else ""
                current_chunk = (tail + " " + sentence).strip() + " "
        if current_chunk:
            chunks.append(current_chunk.strip())
        if len(chunks) > 1 and len(chunks[-1]) < min_chunk_size:
            chunks[-2] += " " + chunks[-1]
            chunks.pop()
        return chunks

    def structure(self, raw_data):
        from app.models.unified_content_schema import Section, Chunk

        structured_sections = []
        total_chunks = 0
        chunk_counter = 0

        for section in raw_data["sections"]:
            chunks = []
            page_num = section.get("page")
            section_heading = section.get("heading")
            section_blocks = section.get("blocks", [])

            # TEXT BLOCKS
            text_blocks = [(idx, block["content"]) for idx, block in enumerate(section_blocks) if block["type"] == "text" and block.get("content")]
            if text_blocks:
                text_block_items = [{"idx": idx, "content": content, "bbox": section_blocks[idx].get("bbox")} for idx, content in text_blocks]
                page_kind = self.classify_page_layout(text_block_items)
                combined_text = self.merge_text_blocks_for_page(text_block_items, page_kind)
                chunking_profile = self.get_chunking_profile(page_kind)
                text_chunks = self.split_text_into_chunks(
                    combined_text,
                    max_chunk_size=chunking_profile["max_chunk_size"],
                    overlap=chunking_profile["overlap"],
                    min_chunk_size=chunking_profile["min_chunk_size"]
                )
                for sub_idx, chunk_text in enumerate(text_chunks):
                    metadata = {"page": page_num, "chunk_type": "text", "page_kind": page_kind, "source_block_count": len(text_blocks)}
                    if len(text_chunks) > 1:
                        metadata["sub_chunk_index"] = sub_idx
                        metadata["total_sub_chunks"] = len(text_chunks)
                    chunks.append(Chunk(
                        id=str(uuid.uuid4()),
                        content=chunk_text,
                        embedding_text=chunk_text,
                        chunk_index=chunk_counter,
                        metadata=metadata
                    ))
                    chunk_counter += 1

            # TABLE & IMAGE BLOCKS
            for block in section_blocks:
                if block["type"] == "table":
                    chunks.append(Chunk(
                        id=str(uuid.uuid4()),
                        content=block["embedding_ready_text"],
                        embedding_text=block["embedding_ready_text"],
                        chunk_index=chunk_counter,
                        metadata={"page": page_num, "chunk_type": "table"}
                    ))
                    chunk_counter += 1
                elif block["type"] == "image":
                    chunks.append(Chunk(
                        id=str(uuid.uuid4()),
                        content=block["embedding_ready_text"],
                        embedding_text=block["embedding_ready_text"],
                        chunk_index=chunk_counter,
                        metadata={"page": page_num, "chunk_type": "image", "image_path": block["content"]}
                    ))
                    chunk_counter += 1

            if chunks:
                structured_sections.append(Section(
                    id=str(uuid.uuid4()),
                    heading=section_heading,
                    page=page_num,
                    chunks=chunks
                ))
                total_chunks += len(chunks)

        return ParsedContent(
            source_type="pdf",
            title=raw_data["metadata"].get("title", "PDF Document"),
            sections=structured_sections,
            keywords=[],
            difficulty_level="Intermediate",
            estimated_duration=None,
            total_chunks=total_chunks
        )