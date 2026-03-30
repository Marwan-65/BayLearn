"""
PDFParser v2 — Universal PDF parser for learning tutor projects.

Strategy:
  DIGITAL pages   → PyMuPDF direct text extraction (free, instant, no API)
  SCANNED pages   → Render to image → Gemini Flash API (free tier: 1000 req/day)
  EMBEDDED images → Gemini Flash API for OCR
  TABLES          → img2table (unchanged)
  DIAGRAMS        → vector detection + clip → Gemini Flash API

Why Gemini instead of PaddleOCR/TrOCR:
  - Multimodal LLM sees the WHOLE PAGE with layout context
  - Reads handwriting, math notation, arrows, diagrams as a human would
  - Free tier: Gemini 2.5 Flash-Lite = 1,000 requests/day, 15 req/min
  - No GPU needed — it's an API call
  - PaddleOCR garbled math; TrOCR hallucinated English words

Requirements:
  pip install google-genai PyMuPDF opencv-python-headless pillow numpy img2table
"""

import fitz
import uuid
import os
import re
import csv
import shutil
import hashlib
import logging
import base64
import time
import numpy as np
import cv2
from io import BytesIO
from PIL import Image
from typing import Optional

from app.parsers.base_parser import BaseParser
from app.models.unified_content_schema import ParsedContent

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════
# GEMINI OCR ENGINE
# ═══════════════════════════════════════════════════════════════════

OCR_PROMPT = """You are an expert OCR system for academic handwritten notes.
Extract ALL text from this image exactly as written.

Rules:
- Preserve mathematical notation: use standard ASCII math (e.g., V(s) = sum pi(a|s) * P(s'|s,a) * [R(s,a) + gamma * V(s')])
- For Greek letters write the name: gamma, pi, alpha, theta, epsilon
- For summation write "sum", for product write "prod"
- Preserve subscripts/superscripts using underscore/caret: V_i, Q^*, s_t+1
- Keep arrows as ->
- Preserve line breaks and section structure
- If text is unclear, give your best reading — do NOT skip it
- Do NOT add explanations — output ONLY the extracted text
- Ignore any "Scanned with CamScanner" watermarks"""

EMBEDDED_IMG_PROMPT = """Extract ALL text visible in this image.
If there is mathematical notation, use ASCII math notation (gamma, pi, sum, etc.).
If this is a diagram with labels, extract all labels and describe the structure briefly.
Output ONLY the extracted text, no commentary."""


class GeminiOCR:
    """Thin wrapper around Gemini API for image-to-text."""

    _client = None

    @classmethod
    def _get_client(cls):
        if cls._client is None:
            api_key = os.environ.get("GEMINI_API_KEY")
            if not api_key:
                raise ValueError("GEMINI_API_KEY not set")

            from google import genai
            cls._client = genai.Client(api_key=api_key)

            # ✅ Use cls._client (not client)
            try:
                print("Available models:")
                for m in cls._client.models.list():
                    print(m.name)
            except Exception as e:
                logger.warning(f"Failed to list models: {e}")

        return cls._client

    @classmethod
    def ocr_image(cls, image: Image.Image, prompt: str = OCR_PROMPT,
                  model = "gemini-2.5-flash",
                  max_retries: int = 3) -> str:
        """Send an image to Gemini and get extracted text back.

        Args:
            image: PIL Image
            prompt: The OCR instruction prompt
            model: Gemini model to use (Flash-Lite = 1000 req/day free)
            max_retries: Retry count for rate limit errors
        Returns:
            Extracted text string
        """
        client = cls._get_client()

        # Convert PIL Image to bytes
        buf = BytesIO()
        image.save(buf, format="PNG")
        image_bytes = buf.getvalue()

        from google.genai import types

        for attempt in range(max_retries):
            try:
                response = client.models.generate_content(
                    model=model,
                    contents=[
                        types.Content(
                            role="user",
                            parts=[
                                types.Part.from_bytes(
                                    data=image_bytes,
                                    mime_type="image/png",
                                ),
                                types.Part.from_text(text=prompt),
                            ],
                        )
                    ],
                )
                text = response.text or ""
                return text.strip()

            except Exception as e:
                error_str = str(e).lower()
                if "404" in error_str:
                    logger.error(f"Model not found: {e}")
                    return ""
                if hasattr(e, "status_code") and e.status_code == 429:
                    wait = 2 ** attempt * 5
                    logger.warning(f"Rate limited, retrying in {wait}s... ({e})")
                    time.sleep(wait)
                    continue
                else:
                    logger.error(f"Gemini OCR failed: {e}")
                    return ""

        logger.error("Gemini OCR: max retries exceeded")
        return ""


# ═══════════════════════════════════════════════════════════════════
# PDF PARSER
# ═══════════════════════════════════════════════════════════════════

class PDFParser(BaseParser):

    def preprocess(self, file_path):
        doc = fitz.open(file_path)
        cleaned_path = file_path.replace(".pdf", "_clean.pdf")
        doc.save(cleaned_path)
        doc.close()
        return cleaned_path

    # ─────────────────────────────────────────────────────────────
    # PAGE TYPE DETECTION
    # ─────────────────────────────────────────────────────────────
    def is_scanned_page(self, page) -> bool:
        text = page.get_text().strip()
        images = page.get_images(full=True)
        text_length = len(text)

        if text_length >= 50 or len(images) == 0:
            page_area = page.rect.width * page.rect.height
            if page_area > 0 and text_length / page_area < 0.00005 and len(images) > 0:
                return self._has_dominant_image(page)
            return False
        return self._has_dominant_image(page)

    def _has_dominant_image(self, page) -> bool:
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

    # ─────────────────────────────────────────────────────────────
    # RENDER PAGE
    # ─────────────────────────────────────────────────────────────
    def render_page(self, page, zoom: float = 2.0) -> Image.Image:
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
        mode = "RGB" if pix.n >= 3 else "L"
        return Image.frombytes(mode, [pix.width, pix.height], pix.samples)

    # ─────────────────────────────────────────────────────────────
    # OCR VIA GEMINI
    # ─────────────────────────────────────────────────────────────
    def run_ocr(self, image: Image.Image, prompt: str = OCR_PROMPT) -> str:
        return GeminiOCR.ocr_image(image, prompt=prompt)

    # ─────────────────────────────────────────────────────────────
    # TEXT CLEANING
    # ─────────────────────────────────────────────────────────────
    def clean_text(self, text: str) -> str:
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    # ─────────────────────────────────────────────────────────────
    # VECTOR DIAGRAM DETECTION (unchanged from v1)
    # ─────────────────────────────────────────────────────────────
    def detect_diagram_regions(self, page, min_area=3000, merge_gap=50, max_page_ratio=0.85):
        drawings = page.get_drawings()
        if not drawings:
            return []

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
            if r.width > 15 and r.height > 15:
                return False
            for tb in text_bboxes:
                if tb.contains(r):
                    return True
            return False

        all_drawing_rects = []
        rects = []
        for d in drawings:
            r = d.get("rect")
            if not r:
                continue
            r = fitz.Rect(r)
            if r.is_empty or r.is_infinite:
                continue
            all_drawing_rects.append(r)
            if r.width < 2 and r.height < 2:
                continue
            if is_thin_text_decorator(r):
                continue
            rects.append(r)

        if not rects:
            return []

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
                    expanded = current + (-merge_gap, -merge_gap, merge_gap, merge_gap)
                    if expanded.intersects(rects[j]):
                        current = current | rects[j]
                        used[j] = True
                        changed = True
                merged.append(current)
            rects = merged

        regions = []
        for r in rects:
            r = r & page_rect
            if r.is_empty or r.is_infinite:
                continue
            area = r.width * r.height
            if area < min_area or (page_area > 0 and area / page_area > max_page_ratio):
                continue
            density = sum(1 for dr in all_drawing_rects if r.contains(dr) or r.intersects(dr))
            if density < 3 and area < 15000:
                continue
            dup = any(
                not (r & a).is_empty and (r & a).width * (r & a).height / area > 0.85
                for a in regions
            )
            if not dup:
                regions.append(r)
        return regions

    # ─────────────────────────────────────────────────────────────
    # IMAGE QUALITY FILTERS
    # ─────────────────────────────────────────────────────────────
    def is_garbage_image(self, pix) -> bool:
        if pix.width * pix.height < 2000:
            return True
        arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, -1)
        gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY) if arr.ndim == 3 else arr
        return gray.mean() < 15 or gray.mean() > 252 or gray.std() < 5

    def is_duplicate_image(self, image_bytes, seen_hashes) -> bool:
        h = hashlib.md5(image_bytes).hexdigest()
        if h in seen_hashes:
            return True
        seen_hashes.add(h)
        return False

    # ─────────────────────────────────────────────────────────────
    # PIXMAP HELPERS
    # ─────────────────────────────────────────────────────────────
    def _extract_pixmap(self, doc, img_tuple):
        xref = img_tuple[0]
        pix = fitz.Pixmap(doc, xref)
        smask_xref = img_tuple[1] if len(img_tuple) > 1 else 0
        if smask_xref and smask_xref != 0:
            try:
                pix = fitz.Pixmap(pix, fitz.Pixmap(doc, smask_xref))
            except Exception:
                pass
        if pix.colorspace and pix.colorspace.n == 4:
            pix = fitz.Pixmap(fitz.csRGB, pix)
        if pix.alpha:
            pix = fitz.Pixmap(fitz.csRGB, pix, 0)
        return pix

    def _pixmap_to_pil(self, pix) -> Image.Image:
        mode = "RGB" if pix.colorspace and pix.colorspace.n >= 3 else "L"
        img = Image.frombytes(mode, [pix.width, pix.height], pix.samples)
        return img.convert("RGB") if img.mode != "RGB" else img

    # ─────────────────────────────────────────────────────────────
    # TABLE HELPERS
    # ─────────────────────────────────────────────────────────────
    def convert_table_to_markdown(self, table) -> str:
        if not table:
            return ""
        header = table[0]
        lines = [
            "| " + " | ".join(header) + " |",
            "|" + "|".join(["---"] * len(header)) + "|",
        ]
        for row in table[1:]:
            lines.append("| " + " | ".join(row) + " |")
        return "\n".join(lines)

    def normalize_table(self, rows):
        return [["" if c is None else str(c) for c in r] for r in rows]

    # ═══════════════════════════════════════════════════════════════
    # MAIN EXTRACTION
    # ═══════════════════════════════════════════════════════════════
    def extract(self, file_path: str) -> dict:
        doc = fitz.open(file_path)
        sections = []

        for folder in ("extracted_images", "extracted_tables"):
            if os.path.exists(folder):
                shutil.rmtree(folder)
            os.makedirs(folder)

        extracted_xrefs: set = set()

        # Table extraction
        extracted_tables = {}
        try:
            from img2table.document import PDF as Img2TablePDF
            img2table_pdf = Img2TablePDF(src=file_path)
            extracted_tables = img2table_pdf.extract_tables(
                ocr=None, borderless_tables=True,
                implicit_rows=False, implicit_columns=True,
            )
        except Exception as e:
            logger.warning(f"img2table failed: {e}")

        for page_index, page in enumerate(doc):
            page_number = page_index + 1
            blocks = []
            is_scanned = self.is_scanned_page(page)

            # ─── SCANNED PAGE → Gemini OCR ───────────────────────
            if is_scanned:
                image = self.render_page(page, zoom=2.0)
                text = self.run_ocr(image, prompt=OCR_PROMPT)
                if text:
                    blocks.append({
                        "id": str(uuid.uuid4()),
                        "type": "text",
                        "content": text,
                        "embedding_ready_text": text,
                        "bbox": None,
                    })

            # ─── DIGITAL PAGE → PyMuPDF direct extraction ────────
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
                    if text:
                        blocks.append({
                            "id": str(uuid.uuid4()),
                            "type": "text",
                            "content": text,
                            "embedding_ready_text": text,
                            "bbox": block["bbox"],
                        })

            # ─── IMAGE EXTRACTION + OCR ──────────────────────────
            img_counter = 0
            seen_hashes: set = set()

            for img in page.get_images(full=True):
                xref = img[0]
                if xref in extracted_xrefs:
                    continue
                extracted_xrefs.add(xref)

                try:
                    pix = self._extract_pixmap(doc, img)
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
                    img_ocr_text = self.run_ocr(pil_img, prompt=EMBEDDED_IMG_PROMPT)
                    embedding_text = img_ocr_text or f"Image on page {page_number}"

                blocks.append({
                    "id": str(uuid.uuid4()),
                    "type": "image",
                    "content": embedding_text,
                    "embedding_ready_text": embedding_text,
                    "image_path": image_path,
                    "bbox": None,
                })

            # Pass 2: inline images
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
                    img_ocr_text = self.run_ocr(pil_img, prompt=EMBEDDED_IMG_PROMPT)
                    embedding_text = img_ocr_text or f"Image on page {page_number}"

                blocks.append({
                    "id": str(uuid.uuid4()),
                    "type": "image",
                    "content": embedding_text,
                    "embedding_ready_text": embedding_text,
                    "image_path": image_path,
                    "bbox": info.get("bbox"),
                })

            # ─── VECTOR DIAGRAMS ─────────────────────────────────
            diagram_regions = self.detect_diagram_regions(page)
            for region in diagram_regions:
                clip_pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), clip=region, alpha=False)
                image_bytes = clip_pix.tobytes("png")
                if self.is_duplicate_image(image_bytes, seen_hashes):
                    continue

                arr = np.frombuffer(clip_pix.samples, dtype=np.uint8).reshape(
                    clip_pix.height, clip_pix.width, -1)
                gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
                if gray.mean() > 248 or gray.std() < 5:
                    continue

                image_path = f"extracted_images/page{page_number}_{img_counter}.png"
                with open(image_path, "wb") as f:
                    f.write(image_bytes)
                img_counter += 1

                pil_img = Image.frombytes("RGB", [clip_pix.width, clip_pix.height], clip_pix.samples)
                img_ocr_text = self.run_ocr(pil_img, prompt=EMBEDDED_IMG_PROMPT)
                embedding_text = img_ocr_text or f"Diagram on page {page_number}"

                blocks.append({
                    "id": str(uuid.uuid4()),
                    "type": "image",
                    "content": embedding_text,
                    "embedding_ready_text": embedding_text,
                    "image_path": image_path,
                    "bbox": list(region),
                })

            # ─── TABLES ──────────────────────────────────────────
            tables = extracted_tables.get(page_number, [])
            for idx, table in enumerate(tables):
                df = getattr(table, "df", None)
                if df is None:
                    continue
                table_data = self.normalize_table(df.values.tolist())
                non_empty = sum(1 for row in table_data for cell in row if cell.strip())
                if non_empty == 0:
                    continue

                csv_path = f"extracted_tables/page{page_number}_table{idx}.csv"
                with open(csv_path, "w", newline="", encoding="utf-8") as f:
                    writer = csv.writer(f)
                    for row in table_data:
                        writer.writerow(row)

                markdown = self.convert_table_to_markdown(table_data)
                blocks.append({
                    "id": str(uuid.uuid4()),
                    "type": "table",
                    "content": table_data,
                    "embedding_ready_text": markdown,
                    "bbox": None,
                    "csv_path": csv_path,
                })

            sections.append({
                "id": str(uuid.uuid4()),
                "heading": f"Page {page_number}",
                "page": page_number,
                "blocks": blocks,
            })

        return {"sections": sections, "metadata": doc.metadata}

    # ─────────────────────────────────────────────────────────────
    # STRUCTURE
    # ─────────────────────────────────────────────────────────────
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
                            **({"image_path": block["image_path"]}
                               if block["type"] == "image" and "image_path" in block
                               else {}),
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