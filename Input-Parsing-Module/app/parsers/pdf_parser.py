import fitz
import uuid
import os
import re
import csv
import shutil
import hashlib
import numpy as np
import cv2
from PIL import Image
from paddleocr import PaddleOCR
from img2table.document import PDF as Img2TablePDF
from app.parsers.base_parser import BaseParser
from app.models.unified_content_schema import ParsedContent


class PDFParser(BaseParser):

    _ocr = None

    def preprocess(self, file_path):
        doc = fitz.open(file_path)
        cleaned_path = file_path.replace(".pdf", "_clean.pdf")
        doc.save(cleaned_path)
        doc.close()
        return cleaned_path

    # -------------------------
    # OCR INITIALIZATION
    # -------------------------
    @classmethod
    def _get_ocr(cls):
        if cls._ocr is None:
            cls._ocr = PaddleOCR(
                use_angle_cls=True,
                lang="en",
                det_db_box_thresh=0.3,
                det_db_unclip_ratio=1.8,
                rec_batch_num=6,
            )
        return cls._ocr

    # -------------------------
    # PAGE TYPE DETECTION
    # -------------------------
    def is_scanned_page(self, page):
        """Classify a page as scanned only when a large raster image dominates
        and there is virtually no extractable text.  Small embedded images on
        an otherwise text-light page are NOT treated as scanned so that the
        digital extraction path still runs for each individual image."""

        text = page.get_text().strip()
        images = page.get_images(full=True)
        text_length = len(text)

        if text_length >= 30 or len(images) == 0:
            # Enough text OR no images → digital page
            page_area = page.rect.width * page.rect.height
            if page_area > 0 and text_length / page_area < 0.00005 and len(images) > 0:
                # Very sparse text with images — check if a big scan dominates
                return self._has_dominant_image(page)
            return False

        # Almost no text and at least one image — check if a big image covers
        # most of the page (typical full-page scan).
        return self._has_dominant_image(page)

    def _has_dominant_image(self, page):
        """Return True if any single embedded image covers > 50 % of the page."""
        page_area = page.rect.width * page.rect.height
        if page_area == 0:
            return False
        for info in page.get_image_info():
            bbox = info.get("bbox")
            if bbox:
                img_area = (bbox[2] - bbox[0]) * (bbox[3] - bbox[1])
                if img_area / page_area > 0.5:
                    return True
        return False

    # -------------------------
    # IMAGE PREPROCESSING
    # -------------------------
    def preprocess_image(self, image):
        img = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2GRAY)

        # Light denoising — binarization destroys handwriting strokes
        img = cv2.fastNlMeansDenoising(img, h=10)

        img = cv2.resize(img, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)

        # Convert back to RGB for PaddleOCR
        img = cv2.cvtColor(img, cv2.COLOR_GRAY2RGB)
        return img

    # -------------------------
    # RENDER PAGE FOR OCR
    # -------------------------
    def render_page(self, page):
        pix = page.get_pixmap(matrix=fitz.Matrix(4, 4), alpha=False)
        mode = "RGB" if pix.n >= 3 else "L"
        image = Image.frombytes(mode, [pix.width, pix.height], pix.samples)
        return image

    # -------------------------
    # RUN OCR
    # -------------------------
    def run_ocr(self, image):
        ocr = self._get_ocr()
        img = self.preprocess_image(image)
        result = ocr.ocr(img)

        lines = []
        if not result:
            return ""

        for block in result:
            if block is None:
                continue
            for line in block:
                if len(line) < 2:
                    continue
                text = line[1][0]
                conf = line[1][1]
                if conf > 0.2:
                    lines.append(text)

        return " ".join(lines).strip()

    # -------------------------
    # TEXT CLEANING
    # -------------------------
    def clean_text(self, text):
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    # -------------------------
    # VECTOR DIAGRAM DETECTION
    # -------------------------
    def detect_diagram_regions(
        self, page, min_area=3000, merge_gap=50, max_page_ratio=0.85
    ):
        """Find bounding boxes of vector-drawn diagram regions on the page.

        Strategy
        --------
        1. Collect bboxes of ALL drawing elements (fills, strokes, curves).
        2. Only exclude a drawing element if it is a **thin, small decorator**
           (underline, border) fully inside a text block.  Large shapes that
           *contain* or overlap text — like diagram boxes — are kept.
        3. Merge nearby elements (within *merge_gap* pts) iteratively.
        4. For each merged region, count how many original drawing commands
           fall inside it (drawing density).  Regions with very few commands
           and no fills / curves are likely stray lines, not diagrams.
        5. Reject regions that are too small, cover the whole page, or are
           near-duplicates.
        """

        drawings = page.get_drawings()
        if not drawings:
            return []

        # ---- text-block bboxes (for filtering tiny decorators only) ----
        text_bboxes = []
        try:
            for b in page.get_text("dict")["blocks"]:
                if b.get("type") == 0:
                    text_bboxes.append(fitz.Rect(b["bbox"]))
        except Exception:
            pass

        page_rect = page.rect
        page_area = page_rect.width * page_rect.height

        def is_thin_text_decorator(r):
            """True only for small, thin elements fully inside a text block
            (underlines, strikethroughs, text-box borders).  Large shapes
            that surround text — diagram boxes — are NOT decorators."""
            # Must be thin in at least one dimension
            if r.width > 15 and r.height > 15:
                return False
            for tb in text_bboxes:
                if tb.contains(r):
                    return True
            return False

        # ---- collect drawing rects ----
        all_drawing_rects = []  # every rect (for density counting later)
        rects = []              # rects that participate in merging

        for d in drawings:
            r = d.get("rect")
            if not r:
                continue
            r = fitz.Rect(r)
            if r.is_empty or r.is_infinite:
                continue

            all_drawing_rects.append(r)

            # Skip truly tiny marks (< 2px in both dimensions)
            if r.width < 2 and r.height < 2:
                continue

            # Skip thin decorators inside text blocks (underlines etc.)
            if is_thin_text_decorator(r):
                continue

            rects.append(r)

        if not rects:
            return []

        # ---- iterative greedy merge ----
        changed = True
        while changed:
            changed = False
            merged = []
            used = [False] * len(rects)
            for i, r in enumerate(rects):
                if used[i]:
                    continue
                current = r
                for j in range(i + 1, len(rects)):
                    if used[j]:
                        continue
                    expanded = current + (
                        -merge_gap,
                        -merge_gap,
                        merge_gap,
                        merge_gap,
                    )
                    if expanded.intersects(rects[j]):
                        current = current | rects[j]
                        used[j] = True
                        changed = True
                merged.append(current)
            rects = merged

        # ---- filter, density-check, and deduplicate ----
        regions = []
        for r in rects:
            r = r & page_rect
            if r.is_empty or r.is_infinite:
                continue
            area = r.width * r.height
            if area < min_area:
                continue
            if page_area > 0 and area / page_area > max_page_ratio:
                continue

            # Drawing density: count how many original drawing elements
            # fall inside this merged region.  A real diagram typically has
            # several shapes; a stray horizontal rule has one.
            density = sum(
                1 for dr in all_drawing_rects
                if r.contains(dr) or r.intersects(dr)
            )
            if density < 3 and area < 15000:
                # Very few drawing commands AND small area — likely not a
                # diagram (could be a separator line or border).
                continue

            # Near-duplicate check
            duplicate = False
            for accepted in regions:
                inter = r & accepted
                if not inter.is_empty:
                    overlap = (inter.width * inter.height) / area
                    if overlap > 0.85:
                        duplicate = True
                        break
            if duplicate:
                continue
            regions.append(r)

        return regions

    # -------------------------
    # IMAGE QUALITY FILTERS
    # -------------------------
    def is_garbage_image(self, pix):
        """Return True for images that are too small, nearly blank/black,
        or have an extremely low unique-colour count (solid fills, etc.)."""

        if pix.width * pix.height < 2000:
            return True

        arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(
            pix.height, pix.width, -1
        )

        gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY) if arr.ndim == 3 else arr

        if gray.mean() < 15:
            return True
        if gray.mean() > 252:
            return True
        if gray.std() < 5:
            return True

        return False

    def is_duplicate_image(self, image_bytes, seen_hashes):
        """Return True if this image's content hash was already seen."""
        h = hashlib.md5(image_bytes).hexdigest()
        if h in seen_hashes:
            return True
        seen_hashes.add(h)
        return False

    # -------------------------
    # PIXMAP EXTRACTION HELPERS
    # -------------------------
    def _extract_pixmap(self, doc, img_tuple):
        """Safely extract a Pixmap from a page image entry, handling SMask
        (soft-mask / transparency) and CMYK → RGB conversion."""

        xref = img_tuple[0]
        pix = fitz.Pixmap(doc, xref)

        # Apply soft-mask if present (index 1 in the tuple is the smask xref)
        smask_xref = img_tuple[1] if len(img_tuple) > 1 else 0
        if smask_xref and smask_xref != 0:
            try:
                mask_pix = fitz.Pixmap(doc, smask_xref)
                # Composite the image with its mask
                pix = fitz.Pixmap(pix, mask_pix)
            except Exception:
                pass

        # CMYK → RGB
        if pix.colorspace and pix.colorspace.n == 4:
            pix = fitz.Pixmap(fitz.csRGB, pix)

        # Flatten alpha onto white background
        if pix.alpha:
            bg = fitz.Pixmap(fitz.csRGB, pix, 0)  # drop alpha, white bg
            pix = bg

        return pix

    def _pixmap_to_pil(self, pix):
        """Convert a fitz.Pixmap to a PIL RGB Image."""
        mode = "RGB" if pix.colorspace and pix.colorspace.n >= 3 else "L"
        img = Image.frombytes(mode, [pix.width, pix.height], pix.samples)
        if img.mode != "RGB":
            img = img.convert("RGB")
        return img

    # -------------------------
    # TABLE HELPERS
    # -------------------------
    def convert_table_to_markdown(self, table):
        if not table:
            return ""
        lines = []
        header = table[0]
        lines.append("| " + " | ".join(header) + " |")
        lines.append("|" + "|".join(["---"] * len(header)) + "|")
        for row in table[1:]:
            lines.append("| " + " | ".join(row) + " |")
        return "\n".join(lines)

    def normalize_table(self, rows):
        return [["" if c is None else str(c) for c in r] for r in rows]

    # -------------------------
    # MAIN EXTRACTION
    # -------------------------
    def extract(self, file_path):
        doc = fitz.open(file_path)
        sections = []

        # Clear and recreate output directories on every run
        for folder in ("extracted_images", "extracted_tables"):
            if os.path.exists(folder):
                shutil.rmtree(folder)
            os.makedirs(folder)

        # Track already-extracted xrefs globally to avoid cross-page duplicates
        extracted_xrefs: set = set()

        img2table_pdf = Img2TablePDF(src=file_path)

        try:
            extracted_tables = img2table_pdf.extract_tables(
                ocr=None,
                borderless_tables=True,
                implicit_rows=False,
                implicit_columns=True,
            )
        except Exception:
            print("Table extraction failed, continuing without tables.")
            extracted_tables = {}

        for page_index, page in enumerate(doc):
            page_number = page_index + 1
            blocks = []
            is_scanned = self.is_scanned_page(page)

            # -------------------------
            # SCANNED PAGE — full-page OCR
            # -------------------------
            if is_scanned:
                image = self.render_page(page)
                text = self.run_ocr(image)
                if text:
                    blocks.append(
                        {
                            "id": str(uuid.uuid4()),
                            "type": "text",
                            "content": text,
                            "embedding_ready_text": text,
                            "bbox": None,
                        }
                    )

            # -------------------------
            # DIGITAL PAGE — block-level text
            # -------------------------
            else:
                text_dict = page.get_text("dict")
                for block in text_dict["blocks"]:
                    if block["type"] != 0:
                        continue
                    text = ""
                    for line in block["lines"]:
                        for span in line["spans"]:
                            text += span["text"] + " "
                    text = self.clean_text(text)
                    if not text:
                        continue
                    blocks.append(
                        {
                            "id": str(uuid.uuid4()),
                            "type": "text",
                            "content": text,
                            "embedding_ready_text": text,
                            "bbox": block["bbox"],
                        }
                    )

            # -------------------------
            # IMAGE EXTRACTION (raster XObjects)
            # -------------------------
            img_counter = 0
            seen_hashes: set = set()

            # Pass 1: standard get_images (XObject images)
            for img in page.get_images(full=True):
                xref = img[0]
                if xref in extracted_xrefs:
                    continue
                extracted_xrefs.add(xref)

                try:
                    pix = self._extract_pixmap(doc, img)
                except Exception:
                    continue

                # Skip garbage images (too small, blank, black, low-contrast)
                if self.is_garbage_image(pix):
                    continue

                image_bytes = pix.tobytes("png")

                # Skip duplicate images
                if self.is_duplicate_image(image_bytes, seen_hashes):
                    continue

                image_path = f"extracted_images/page{page_number}_{img_counter}.png"
                with open(image_path, "wb") as f:
                    f.write(image_bytes)
                img_counter += 1

                # OCR: on scanned pages the full-page OCR already ran; for
                # digital pages run OCR on each embedded image individually.
                if is_scanned:
                    embedding_text = f"Image on page {page_number}"
                else:
                    pil_img = self._pixmap_to_pil(pix)
                    img_ocr_text = self.run_ocr(pil_img)
                    embedding_text = (
                        img_ocr_text
                        if img_ocr_text
                        else f"Image on page {page_number}"
                    )

                blocks.append(
                    {
                        "id": str(uuid.uuid4()),
                        "type": "image",
                        "content": embedding_text,
                        "embedding_ready_text": embedding_text,
                        "image_path": image_path,
                        "bbox": None,
                    }
                )

            # Pass 2: catch inline / missed images via get_image_info
            for info in page.get_image_info(xrefs=True):
                xref = info.get("xref", 0)
                if xref == 0 or xref in extracted_xrefs:
                    continue
                extracted_xrefs.add(xref)

                try:
                    pix = fitz.Pixmap(doc, xref)
                    if pix.colorspace and pix.colorspace.n == 4:
                        pix = fitz.Pixmap(fitz.csRGB, pix)
                    if pix.alpha:
                        pix = fitz.Pixmap(fitz.csRGB, pix, 0)
                except Exception:
                    continue

                if self.is_garbage_image(pix):
                    continue

                image_bytes = pix.tobytes("png")
                if self.is_duplicate_image(image_bytes, seen_hashes):
                    continue

                image_path = f"extracted_images/page{page_number}_{img_counter}.png"
                with open(image_path, "wb") as f:
                    f.write(image_bytes)
                img_counter += 1

                if is_scanned:
                    embedding_text = f"Image on page {page_number}"
                else:
                    pil_img = self._pixmap_to_pil(pix)
                    img_ocr_text = self.run_ocr(pil_img)
                    embedding_text = (
                        img_ocr_text
                        if img_ocr_text
                        else f"Image on page {page_number}"
                    )

                blocks.append(
                    {
                        "id": str(uuid.uuid4()),
                        "type": "image",
                        "content": embedding_text,
                        "embedding_ready_text": embedding_text,
                        "image_path": image_path,
                        "bbox": info.get("bbox"),
                    }
                )

            # -------------------------
            # VECTOR DIAGRAM EXTRACTION
            # Runs on ALL pages (scanned and digital) so individual
            # diagrams are captured even on scanned pages.
            # -------------------------
            diagram_regions = self.detect_diagram_regions(page)
            for region in diagram_regions:
                mat = fitz.Matrix(2, 2)
                clip_pix = page.get_pixmap(matrix=mat, clip=region, alpha=False)

                image_bytes = clip_pix.tobytes("png")
                if self.is_duplicate_image(image_bytes, seen_hashes):
                    continue

                arr = np.frombuffer(clip_pix.samples, dtype=np.uint8).reshape(
                    clip_pix.height, clip_pix.width, -1
                )
                gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)

                # Skip near-blank regions (just borders/lines)
                if gray.mean() > 248 or gray.std() < 5:
                    continue

                image_path = f"extracted_images/page{page_number}_{img_counter}.png"
                with open(image_path, "wb") as f:
                    f.write(image_bytes)
                img_counter += 1

                pil_img = Image.frombytes(
                    "RGB", [clip_pix.width, clip_pix.height], clip_pix.samples
                )
                img_ocr_text = self.run_ocr(pil_img)
                embedding_text = (
                    img_ocr_text
                    if img_ocr_text
                    else f"Diagram on page {page_number}"
                )

                blocks.append(
                    {
                        "id": str(uuid.uuid4()),
                        "type": "image",
                        "content": embedding_text,
                        "embedding_ready_text": embedding_text,
                        "image_path": image_path,
                        "bbox": list(region),
                    }
                )

            # -------------------------
            # TABLE EXTRACTION
            # -------------------------
            tables = extracted_tables.get(page_number, [])

            for idx, table in enumerate(tables):
                df = getattr(table, "df", None)
                if df is None:
                    continue

                table_data = self.normalize_table(df.values.tolist())

                csv_path = f"extracted_tables/page{page_number}_table{idx}.csv"
                with open(csv_path, "w", newline="", encoding="utf-8") as f:
                    writer = csv.writer(f)
                    for row in table_data:
                        writer.writerow(row)

                markdown = self.convert_table_to_markdown(table_data)

                blocks.append(
                    {
                        "id": str(uuid.uuid4()),
                        "type": "table",
                        "content": table_data,
                        "embedding_ready_text": markdown,
                        "bbox": None,
                        "csv_path": csv_path,
                    }
                )

            sections.append(
                {
                    "id": str(uuid.uuid4()),
                    "heading": f"Page {page_number}",
                    "page": page_number,
                    "blocks": blocks,
                }
            )

        return {"sections": sections, "metadata": doc.metadata}

    # -------------------------
    # STRUCTURE
    # -------------------------
    def structure(self, raw_data):
        from app.models.unified_content_schema import Section, Chunk

        sections = []
        chunk_counter = 0
        total_chunks = 0

        for section in raw_data["sections"]:
            chunks = []
            for block in section["blocks"]:
                chunks.append(
                    Chunk(
                        id=str(uuid.uuid4()),
                        content=block["embedding_ready_text"],
                        chunk_index=chunk_counter,
                        metadata={
                            "page": section["page"],
                            "chunk_type": block["type"],
                            **(
                                {"image_path": block["image_path"]}
                                if block["type"] == "image" and "image_path" in block
                                else {}
                            ),
                        },
                    )
                )
                chunk_counter += 1

            sections.append(
                Section(
                    id=str(uuid.uuid4()),
                    heading=section["heading"],
                    page=section["page"],
                    chunks=chunks,
                )
            )
            total_chunks += len(chunks)

        return ParsedContent(
            source_type="pdf",
            title=raw_data["metadata"].get("title", "PDF Document"),
            sections=sections,
            total_chunks=total_chunks,
        )