
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
import threading
import math
import numpy as np
import cv2
from io import BytesIO
from PIL import Image
from typing import Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

from app.parsers.base_parser import BaseParser
from app.models.unified_content_schema import ParsedContent
from app.wrappers.ocr_engine_wrappers import GeminiOCR, GroqOCR, PaddleOCR

logger = logging.getLogger(__name__)



# PDF PARSER

class PDFParser(BaseParser):

    # TABLE EXTRACTION

    def _extract_tables(self, file_path: str) -> dict:
        if not os.environ.get("ENABLE_IMG2TABLE", "true").lower() in {"1", "true", "yes", "on"}:
            return {}
        # borderless mode for tables with no rigid table grid
        try:
            from img2table.document import PDF as Img2TablePDF
            return Img2TablePDF(src=file_path).extract_tables(
                ocr=None, borderless_tables=True,
                implicit_rows=False, implicit_columns=True,
            )
        
        except Exception as e:
            logger.warning(f"img2table borderless mode failed retrying in safe mode: {e}")
        # safe mode if borderless failed
        try:
            from img2table.document import PDF as Img2TablePDF
            return Img2TablePDF(src=file_path).extract_tables(
                ocr=None, borderless_tables=False,
                implicit_rows=True, implicit_columns=True,
            )
        
        except Exception as e:
            logger.warning(f"img2table both modes failed skipping table extraction: {e}")
            return {}

    def preprocess(self, file_path):
        doc = fitz.open(file_path)
        if doc.page_count == 0:
            doc.close()

            raise ValueError(
                "The uploaded PDF has no pages or it is invalid/corrupted. "
                "Please upload a valid, non-empty PDF file."
            )
        cleaned_path = file_path.replace(".pdf", "_clean.pdf")
        doc.save(cleaned_path)
        doc.close()
        return cleaned_path


    # PAGE TYPE DETECTION (Scanned or Digital)
  
    def is_scanned_page(self, page) -> bool:
        text = page.get_text().strip()
        images = page.get_images(full=True)
        text_length = len(text)

        # check 1: : if text found in page > 50 characters or has zero images then go to check 2 else chexk dominant imgs
        if text_length >= 50 or len(images) == 0:
            page_area = page.rect.width * page.rect.height

            #check 2: if page text is small compared to the page size and it has images then check dominnant imgs else page is digital
            # ya3ni law el page nono skip
            if page_area > 0 and text_length / page_area < 0.00005 and len(images) > 0:
                return self._has_dominant_image(page)
            
            return False
        
        return self._has_dominant_image(page)

    def _has_dominant_image(self, page) -> bool:
        page_area = page.rect.width * page.rect.height
        if page_area == 0:
            return False


        for info in page.get_image_info():
            bounding_box = info.get("bbox")
            if bounding_box:
                img_area = (bounding_box[2] - bounding_box[0]) * (bounding_box[3] - bounding_box[1]) #area = length*width
                # if image is more than 50% of the page then its scanned
                if img_area / page_area > 0.5:
                    return True
                
        return False


    # RENDER PAGE
    
    # convert page to PIL image for OCR 
    # 3ashan ne3raf n ocr it
    def render_page_as_image(self, page, zoom: float = 2.0) -> Image.Image:

        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False) 
        # from vector to pixels with twice resolution for better OCR (RGB not RGBA for memory and speed) 

        mode = "RGB" if pix.n >= 3 else "L"  # RGB or Grayscale
        return Image.frombytes(mode, [pix.width, pix.height], pix.samples) # PIL
    

    # OCR SCORE
    
    _VISION_DESCRIBE_PROMPT = """You are analyzing an image from an academic document.
    Extract and describe ALL content you see, completely and factually.

    Start with [TYPE: diagram|chart|table|graph|photo|text|mixed]

    Then:
    - If it contains TEXT: extract it exactly as written
    - If it is a TABLE or GRID:
    * Reconstruct as markdown table
    * For checkmarks/ticks/filled boxes -> [x], empty boxes -> [ ], dashes -> [-]
    * Include all row and column headers
    - If it is a DIAGRAM or CHART: describe type, labels, axes, flow, key relationships
    - If it is a PHOTO: describe the subject plainly
    - If MIXED (text + visual): extract text first, then describe the visual

    Rules:
    - Be direct and factual - no commentary, no apologies
    - If the image is blank or unreadable: [TYPE: empty]
    - Never say you cannot see the image"""


   # model-generated known fallback patterns
    _HALLUCINATION_PATTERNS = [
        r"i('m| am) ready to",
        r"please provide",
        r"i don't see any",
        r"no (text|image) (was |is |)(provided|given|present)",
        r"i cannot (see|extract|read)",
        r"unfortunately",
        r"i('ll| will) be happy to help",
        r"if you (can|could) provide",
        r"there is no text in the image",
        r"i do not have access",
    ]
    _HALLUCINATION_RE = re.compile(
        "|".join(_HALLUCINATION_PATTERNS), re.IGNORECASE
    )

    def _ocr_quality_score(self, text: str) -> float:
        """
        Score OCR output quality from 0 (garbage) to 1 (real text)
        Low scores: empty output, hallucinated CJK characters
        single characters or short/fragmented text from diagrams 
        High scores:  real words, especially in longer text
        """
        # if empty output -> low score 
        if not text or not text.strip():
            return 0.0
        
        stripped_text_seq = text.strip()

        # if text is single character/number -> low score (noise)
        if len(stripped_text_seq) <= 2:
            return 0.1

        # Count CJK characters (PaddleOCR hallucinates these on diagrams)
        # Chinese/Japanese/Kanji characters.
        # 3ashan el model by3abat w yebda2 yetkalem yabany lama yela2y diagrams 
        cjk = sum(1 for c in stripped_text_seq if '\u4e00' <= c <= '\u9fff')
        
        # if cjk count >30% of single character/number count -> low score (hallucination)
        if len(stripped_text_seq) > 0 and cjk / len(stripped_text_seq) > 0.3:
            return 0.1  

        # Count real english words  
        real_words = re.findall(r'[a-zA-Z]{2,}', stripped_text_seq)

        total_tokens = len(stripped_text_seq.split())

        # if no tokens at all -> low score
        if total_tokens == 0:
            return 0.1

        word_ratio = len(real_words) / max(total_tokens, 1)

        # if very few real english words and short extracted text -> low score (garbage from diagrams)
        if word_ratio < 0.2 and len(stripped_text_seq) < 30:
            return 0.2

        # Short but has real words -> could be a label ya3ni tmam w zay el fol
            return 0.8
        
        # Otherwise 50% score
        return 0.5

    def _needs_better_description(self, paddle_text: str) -> bool:
        """
        Returns True if PaddleOCR output is low quality and we should
        escalate to a vision API for a better meaningful description.
        
        """
        threshold = float(os.environ.get("OCR_QUALITY_THRESHOLD", "0.4"))
        score = self._ocr_quality_score(paddle_text)
        print(f"[OCR]   PaddleOCR quality score: {score:.2f} "
              f"(threshold={threshold}, escalate={score < threshold})")
        return score < threshold

    def _get_better_description(self, image: Image.Image) -> str:
        """
        Use Gemini or Groq to get a better semantic description of an image
        that PaddleOCR failed on.
        """

        # check if response is hallucinated
        def is_hallucnation(text: str) -> bool:
            return bool(self._HALLUCINATION_RE.search(text))

        # Try Gemini first
        if not GeminiOCR.is_quota_blocked():
            print("[OCR]   Escalating to GEMINI for better semantic description")
            result = GeminiOCR.ocr_image(image, prompt=self._VISION_DESCRIBE_PROMPT)

            if result and not is_hallucnation(result) and "[TYPE: empty]" not in result:
                print(f"[OCR]   Gemini description: {len(result)} chars")
                return result
            
            # if resposnse is empty or hallucinated 
            print("[OCR]   Gemini description unusable -> trying Groq")

        # Groq 
        if GroqOCR._is_available() and not GroqOCR.is_quota_blocked():
            print("[OCR]   Escalating to GROQ for better semantic description")

            result = GroqOCR.ocr_image(image, prompt=self._VISION_DESCRIBE_PROMPT)

            if result and not is_hallucnation(result) and "[TYPE: empty]" not in result:
                print(f"[OCR]   Groq description: {len(result)} chars")
                return result
            # if resposnse is empty or hallucinated 
            print("[OCR]   Groq description unusable")

        # returns empty string if everything fails
        return ""

    # HYBRID OCR APPROACH

    def ocr_embeded_content(self, image: Image.Image, page_is_scanned: bool) -> str:
        """
        Hybrid OCR for embedded images and diagrams:

        DIGITAL page embedded images:
          1.PaddleOCR 
          2.Quality check if output has low score is garbage/empty/hallucinated -> escalate to Gemini/Groq for better semantic description
        SCANNED page images:
          1.Gemini 
          2.Groq 
          3.PaddleOCR + quality check + escalation if still bad
        """
        page_type = "SCANNED" if page_is_scanned else "DIGITAL"

        if not page_is_scanned:
            #Digital page: PaddleOCR first
            print(f"[OCR]   embedded image ({page_type}) -> PADDLEOCR")
            paddle_result = PaddleOCR.ocr_image(image)
            print(f"[OCR]   PaddleOCR: {len(paddle_result)} chars" if paddle_result
                  else "[OCR]   PaddleOCR: no text found")

            # Quality check 
            if self._needs_better_description(paddle_result):
                vision_result = self._get_better_description(image)

                if vision_result:
                    return vision_result
                # if vision models also failed then return whatever Paddle got 
                return paddle_result

            return paddle_result

        else:
            # Scanned page
            # Gemini first
            if not GeminiOCR.is_quota_blocked():
                print(f"[OCR]   embedded image ({page_type}) -> GEMINI")
                result = GeminiOCR.ocr_image(image)

                if result:
                    print(f"[OCR]   Gemini result: {len(result)} chars")
                    return result
                
                print("[OCR]   Gemini returned nothing -> trying Groq")
            # Groq second
            if GroqOCR._is_available() and not GroqOCR.is_quota_blocked():
                print(f"[OCR]   embedded image ({page_type}) -> GROQ")
                result = GroqOCR.ocr_image(image)

                if result:
                    print(f"[OCR]   Groq result: {len(result)} chars")
                    return result
                
                print("[OCR]   Groq returned nothing -> PADDLEOCR")

            # PaddleOCR if both gemini and groq failed
            print(f"[OCR]   embedded image ({page_type}) -> PADDLEOCR (last resort)")
            paddle_result = PaddleOCR.ocr_image(image)
            print(f"[OCR]   PaddleOCR: {len(paddle_result)} chars" if paddle_result
                  else "[OCR]   PaddleOCR: no text found")

            # Even on scanned pages check PaddleOCR output quality and try one more time if it's bad
            if self._needs_better_description(paddle_result):
                vision_result = self._get_better_description(image)
                if vision_result:
                    return vision_result

            return paddle_result

    # TEXT CLEANING
 
    def clean_text(self, text: str) -> str:
        return re.sub(r"\s+", " ", text).strip()


    # VECTOR DIAGRAM DETECTION

    def detect_diagram_regons(self, page, min_area=3000, merge_gap=50, max_page_ratio=0.85):
        """
        detect diagrams drawn using vector graphics in digital PDFs not images and return their bounding boxes as a list of fitz.Rect.
        min_area:minimum area in pixels for a region to be considered a diagram (to filter out small decorations)
        merge_gap:maximum gap in pixels to merge nearby shapes into one diagram (to handle diagrams made of multiple shapes)
        max_page_ratio: maximum area ratio for a diagram to filters out huge shapes that are likely not diagrams but page borders. 
        """
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
            # if shape is large then it is not a decorator
            if r.width > 15 and r.height > 15: 
                return False
            
            # any other shape around text taht is not large enouugh is a text decorator
            for tb in text_bboxes:
                    if tb.contains(r):
                        return True
            return False
        
        all_drawing_rects = []
        rects = []
        for d in drawings:
            r =  d.get("rect")
            if not r:
                continue
            r =  fitz.Rect(r)
            if r.is_empty or r.is_infinite:
                continue
            all_drawing_rects.append(r)
            # ignore very small ones
            if r.width < 2 and r.height < 2:
                continue
            # ignore thin shapes around text that are decorators
            if is_thin_text_decorator(r):
                continue
            rects.append(r)

        if not rects:
            return []
        
        # merge small overlapping or near shape within merge gap into a big diagram
        changed   = True
        while changed:
            changed  = False
            merged =  []
            used = [False] * len(rects)

            for i, r in enumerate(rects):
                # skip already merged shapes
                if used[i]:
                    continue
                current = r

                for j in range(i + 1, len(rects)):
                    if used[j]:
                        continue
                    # if 2 shapes are overlapping or within merge_gap then merge them into one big diagram region
                    if (current + (-merge_gap, -merge_gap, merge_gap, merge_gap)).intersects(rects[j]):
                        current = current | rects[j] # union the two rectangles
                        used[j] = True
                        changed = True
                merged.append(current)

            rects = merged

        # validate regions 
        regions = []

        for r in rects:
            r =  r & page_rect
            if r.is_empty or r.is_infinite:
                continue
            area = r.width * r.height
            # filter out regions that are too small or too large compared to the page size (85% of the page -> page border or smthg) 
            if area < min_area or (page_area > 0 and area / page_area > max_page_ratio):
                continue
            # count how many drawing shapes in this regoin 
            density = sum(
                1 for dr in all_drawing_rects if r.contains(dr) or r.intersects(dr)
            )
            # if very few  in a small area then it is not a diagram mostly just a decorative line or box
            if density < 3 and area < 15000:
                continue

            # duplicate check if 2 regions are overlapping of more than 85% then they are the same region keep only one
            found_overlap = False
            for a in regions:
                intersection = r & a

                if not intersection.is_empty:
                    intersection_area = intersection.width * intersection.height

                    if intersection_area / area > 0.85:
                        found_overlap = True
                        break

            if not found_overlap:
                regions.append(r)

        return regions

    # IMAGE QUALITY CHECKING

    def is_garbage_image(self,   pix) -> bool:
        # image is too small basiclly garbage 
        if pix.width * pix.height < 2000:
            return True
        
        arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, -1)
        gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY) if arr.ndim == 3 else arr

        # image is black or white or very low contrast -> garbage (malhash lazma ma3ana)
        return gray.mean() < 15 or gray.mean() > 252 or gray.std() < 5

    def is_duplicate_image(self,  image_bytes: bytes,  seen_hashes: set) -> bool:
        # compute hash of image bytes 
        h = hashlib.md5(image_bytes).hexdigest()
        if h in seen_hashes:
            return True
        
        # add hash to seen set 
        seen_hashes.add(h)
        return False


    # PIXMAP RELATED FUNS
    
    # Extract a fitz.Pixmap from the PDF handling masks and color spaces
    def _extract_pixmap(self, doc, img_tuple):
        # xref is the reference number for the image in the PDF, smask_xref is for the soft mask (transparency)
        xref = img_tuple[0]
        # create a pixmap from the image reference
        pix = fitz.Pixmap(doc, xref)
        # if there's a soft mask, apply it to the pixmap to handle transparency
        smask_xref =  img_tuple[1] if len(img_tuple) > 1 else 0
        if smask_xref:
            try:
                pix   = fitz.Pixmap(pix, fitz.Pixmap(doc, smask_xref))

            except Exception:
                pass
        if pix.colorspace and pix.colorspace.n == 4:
            pix = fitz.Pixmap(fitz.csRGB, pix)

        if pix.alpha:
            pix   = fitz.Pixmap(fitz.csRGB, pix, 0)
        return pix

    def _pixmap_to_pil(self, pix) -> Image.Image:
        mode= "RGB" if pix.colorspace and pix.colorspace.n >= 3 else "L"
        img =  Image.frombytes(mode, [pix.width, pix.height], pix.samples)

        return  img.convert("RGB") if img.mode != "RGB" else img

 
    # TILE DETECTION & STITCHING
  
    def stitch_page_tiles(self, page, collected_imges_with_info: list) -> list:
        """
          Stitches titles after getting its bbox from image info and check if the are close enough to be a part of an image to stitsch them,
          return a new list tile groups replaced by one stitched image non tile images kept as it is
          collected_imges_with_info items are dicts of pil , bbox and xref
        """
    
        TILE_GAP    = float(os.environ.get("TILE_STITCH_GAP_PT", "8")) # max space bet tils to be considered part of the same img

        MIN_TILES =  int(os.environ.get("TILE_MIN_COUNT", "2")) # min no of tiles to stich tghter to make an image
   
        MAX_TILE_DIM   = int(os.environ.get("TILE_MAX_SINGLE_DIM_PX", "512")) # max width or height for it to be a tile they are smol squares
     
        MAX_STRIP_SHORT_DIM   = int(os.environ.get("TILE_MAX_STRIP_SHORT_DIM_PX", "300")) # max width for vertical strip or max height for horizontal strip they are long rectangles strips not tiles

        # build xref (image ids) ->bbox from page image info
        xref_to_bbox: dict = {}
        try:
            for info in page.get_image_info(xrefs=True):
                xref  = info.get("xref", 0)
                bbox =  info.get("bbox")
                if xref and bbox:
                    xref_to_bbox[xref] =  tuple(bbox)
        except Exception :
            return collected_imges_with_info
        
        for item in collected_imges_with_info :
            if item.get("bbox") is None and item.get("xref"):
                item["bbox"] = xref_to_bbox.get(item["xref"])


        for item in collected_imges_with_info :
            img = item["pil"]
            bbox  = item.get("bbox")
            logger.debug(
                f"  image xref={item.get('xref')} "
                f"pixels={img.width}x{img.height} "
                f"bbox={tuple(round(v,1) for v in bbox) if bbox else None}"
            )

        def is_tile_or_strip(item) -> bool:
            """
            Returns True if this image looks like part of a tiled/stripped image:
              - Square tile: both width and height <= MAX_TILE_DIM
              - Horizontal strip: height <= MAX_STRIP_SHORT_DIM (any width)
              - Vertical strip: width  <= MAX_STRIP_SHORT_DIM (any height)

            """
            if item.get("bbox") is None:
                return False
            img = item["pil"]
            w, h = img.width, img.height
            is_square_tile = w <= MAX_TILE_DIM and h <= MAX_TILE_DIM
            is_h_strip = h <= MAX_STRIP_SHORT_DIM          # wide but short
            is_v_strip = w <= MAX_STRIP_SHORT_DIM          # tall but narrow
        
            return is_square_tile or is_h_strip or is_v_strip
        


        # Split into tile/strip candidates vs definite whole images
        strip_tile_cand = []
        non_tiles = []
        for item in collected_imges_with_info:
            if  is_tile_or_strip(item):
                strip_tile_cand.append(item)
            else:
                non_tiles.append(item)

        logger.debug(
            f"Page tile detection: {len(strip_tile_cand)} candidates, "
            f"{len(non_tiles)} whole images, gap={TILE_GAP}pt"
        )

        if len(strip_tile_cand) < MIN_TILES:
            # treat everything as whole images
            return   collected_imges_with_info

        # adj_tiles_collection candidates whose bboxes are spatially adjacent 
        def adjacent(a, b, gap):
            return (
                a[0] - gap <= b[2] and a[2] + gap >= b[0] # horizontal overlap chcek (left-right)
                and a[1] - gap <= b[3] and a[3] + gap >= b[1] # vertical overlap chcek (top-bottom)
            )

        adj_tiles_collections: list = []
        used = [False] * len(strip_tile_cand)
        for i, item in enumerate(strip_tile_cand):
            if used[i]:
                continue
            adj_tiles_collection  = [item]
            used[i] = True
            # Keep expanding adj_tiles_collections until no new neighbours found
            changed = True
            while changed:
                changed = False
                for j in  range(len(strip_tile_cand)):
                    if used[j]:
                        continue
                    is_adjacent = False
                    for m in adj_tiles_collection:
                        if adjacent(m["bbox"], strip_tile_cand[j]["bbox"], TILE_GAP):
                            is_adjacent =True
                            break

                    if is_adjacent:
                        adj_tiles_collection.append(strip_tile_cand[j])
                        used[j]  = True
                        changed   =  True
            adj_tiles_collections.append(adj_tiles_collection)

        result = list(non_tiles)

        for adj_tiles_collection in adj_tiles_collections:
            if len(adj_tiles_collection) < MIN_TILES:
                result.extend(adj_tiles_collection)
                continue

            # Union bbox of the entire adj_tiles_collection
            xs0=min(item["bbox"][0] for item in adj_tiles_collection)
            ys0=min(item["bbox"][1] for item in adj_tiles_collection)
            xs1=max(item["bbox"][2] for item in adj_tiles_collection)
            ys1=max(item["bbox"][3] for item in adj_tiles_collection)

            try:
                # re-render the union stiyched region from the page with twice res for quality
                clip_pix=page.get_pixmap(
                    matrix=fitz.Matrix(2, 2),
                    clip=fitz.Rect(xs0, ys0, xs1, ys1),
                    alpha=False,
                )

                stitched=Image.frombytes(
                    "RGB", [clip_pix.width, clip_pix.height], clip_pix.samples
                )

                logger.debug(
                    f"Stitched {len(adj_tiles_collection)} tiles into "
                    f"{stitched.width}x{stitched.height}px image"
                )

                result.append({
                    "pil": stitched,
                    "bbox": (xs0, ys0, xs1, ys1),
                    "xref": None,
                    "stitched": True,
                })

            except Exception as e:
                logger.warning(f"Tile stitching failed ({len(adj_tiles_collection)} tiles): {e}")
                result.extend(adj_tiles_collection)

        return  result

  
    # TABLE RELATED FUNS
  
    def convert_table_to_markdown(self, table) -> str:
        if not table:
            return ""
        header= table[0]
        lines = [
            "| " + " | ".join(header) + " |",
            "|" + "|".join(["---"] * len(header)) + "|",
        ]
        for row in table[1:]:
            lines.append("| " + " | ".join(row) + " |")
        return "\n".join(lines)

    def normalize_table(self, rows):
        return [["" if c is None else str(c) for c in r] for r in rows]

    # MAIN EXTRACTION

    def extract(self, file_path: str) -> dict:
        doc = fitz.open(file_path)
        sections = []

        # Config
        max_ocr_workers =max(1, int(os.environ.get("GEMINI_OCR_MAX_WORKERS", "1")))
        scanned_page_zoom = float(os.environ.get("SCANNED_PAGE_RENDER_ZOOM", "1.5")) #res
        # OCR_EMBEDDED_IMAGES=true -> PaddleOCR runs on every embedded image/diagram
        ocr_embedded_images = os.environ.get("OCR_EMBEDDED_IMAGES", "true").lower() in {
            "1", "true", "yes", "on"
        }
        # limit Gemini calls to MAX_OCR_CALLS_PER_DOC per doc to avoid hitting quota 
        max_gemini_calls= max(0, int(os.environ.get("MAX_OCR_CALLS_PER_DOC", "5")))
        # to trace countsss
        gemini_call_count= {"calls": 0}


        def can_call_gemini() -> bool:
            if GeminiOCR.is_quota_blocked():
                return False
            return max_gemini_calls == 0 or gemini_call_count["calls"] < max_gemini_calls

        def inc_gemini_call_counts():
            gemini_call_count["calls"] += 1

        # awel 7aga ne3mel el dir w ked
        for folder in ("extracted_images", "extracted_tables"):
            if os.path.exists(folder):
                shutil.rmtree(folder)
            os.makedirs(folder)

        
        extracted_xrefs: set = set()
        seen_hashes: set =set()
        extracted_tables = self._extract_tables(file_path)

        for page_index, page in enumerate(doc):
            page_number = page_index + 1
            blocks = []
            ocr_jobs: list = []  
            is_scanned= self.is_scanned_page(page)
            print(f"[PDF] Page {page_number}/{len(doc)} -> "
                  f"{'SCANNED/HANDWRITTEN' if is_scanned else 'DIGITAL'}")

            #  SCANNED / HANDWRITTEN PAGE -> Gemini -> Groq-> PaddleOCR w bas keda 
            if is_scanned:
                text = ""
                image = self.render_page_as_image(page, zoom=scanned_page_zoom)

                # Gemini
                if can_call_gemini():
                    inc_gemini_call_counts()
                    print(f"[OCR]   Page {page_number}: full page -> GEMINI "
                          f"(call {gemini_call_count['calls']}/{max_gemini_calls or 'unlimited'})")
                    text = GeminiOCR.ocr_image(image)
                    if text:
                        print(f"[OCR]   Page {page_number}: Gemini OK - {len(text)} chars")
                    else:
                        print(f"[OCR]   Page {page_number}: Gemini returned nothing -> trying Groq")
                else:
                    print(f"[OCR]   Page {page_number}: Gemini skipped "
                          f"(blocked={GeminiOCR.is_quota_blocked()}, "
                          f"calls={gemini_call_count['calls']}/{max_gemini_calls}) -> trying Groq")

                #  Groq (7abeeb el malayeen) 
                if not text and GroqOCR._is_available() and not GroqOCR.is_quota_blocked():
                    print(f"[OCR]   Page {page_number}: full page -> GROQ")
                    text = GroqOCR.ocr_image(image)
                    if text:
                        print(f"[OCR]   Page {page_number}: Groq OK - {len(text)} chars")
                    else:
                        print(f"[OCR]   Page {page_number}: Groq returned nothing -> trying PaddleOCR")
                elif not text:
                    print(f"[OCR]   Page {page_number}: Groq skipped "
                          f"(available={GroqOCR._is_available()}, "
                          f"blocked={GroqOCR.is_quota_blocked()})")

                #  PaddleOCR 
                if not text:
                    print(f"[OCR]   Page {page_number}: full page -> PADDLEOCR (last resort)")
                    # Re-render at higher resolution (PaddleOCR needs more pixels for handwriting)
                    paddle_image = self.render_page_as_image(page, zoom=3.0)
                    text = PaddleOCR.ocr_image(paddle_image, preprocess=True)
                    if text:
                        print(f"[OCR]   Page {page_number}: PaddleOCR OK - {len(text)} chars")
                    else:
                        print(f"[OCR]   Page {page_number}: all OCR engines returned nothing")
                        logger.warning(f"Page {page_number}: Gemini + Groq + PaddleOCR all returned nothing")

                if text:
                    blocks.append({
                        "id": str(uuid.uuid4()),
                        "type": "text",
                        "content": text,
                        "embedding_ready_text": text,
                        "bbox": None,
                    })


            # DIGITAL PAGE -> PyMuPDF
            else:
                for block in page.get_text("dict")["blocks"]:
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

            #  EMBEDDED IMAGES -> collect -> stitch -> PaddleOCR 

            # Step1:collect all raw images from the page (no OCR yet)
            img_counter = 0
            raw_collected_imges_with_info: list = []

            # Pass1 to catch resource images 
            for img in page.get_images(full=True):
                xref = img[0]
                if xref in extracted_xrefs:
                    continue
                extracted_xrefs.add(xref)
                try:
                    pix = self._extract_pixmap(doc, img)
                    if self.is_garbage_image(pix):
                        continue
                    raw_collected_imges_with_info.append({
                        "pil": self._pixmap_to_pil(pix),
                        "bbox": None, 
                        "xref": xref,
                    })
                except Exception:
                    continue

            # Pass2  to catch inline images 
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
                    if self.is_garbage_image(pix):
                        continue
                    raw_collected_imges_with_info.append({
                        "pil": self._pixmap_to_pil(pix),
                        "bbox": info.get("bbox"),
                        "xref": xref,
                    })
                except Exception:
                    continue

            # Step2: stitch tiles 
            stitched_collected_imges_with_info = self.stitch_page_tiles(page, raw_collected_imges_with_info)
            print(f"[IMG]   Page {page_number}: {len(raw_collected_imges_with_info)} raw images -> "
                  f"{len(stitched_collected_imges_with_info)} after stitch (OCR queued: {ocr_embedded_images})")

            # Step3: dedup -> save -> add to OCR job
            page_area = page.rect.width * page.rect.height

            # chcek for dups and only save once
            for item in stitched_collected_imges_with_info:
                pil_img = item["pil"]
                bbox = item.get("bbox")
                image_bytes = pil_img.tobytes()  # raw bytes for dedup
                if self.is_duplicate_image(image_bytes, seen_hashes):
                    continue

                # skip saving the image block if this is a scanned page and the image covers most of the page (it is not a image it is a scanned page)
                if is_scanned and bbox is not None:
                    bw = bbox[2] - bbox[0]
                    bh = bbox[3] - bbox[1]

                    if page_area > 0 and (bw * bh) / page_area > 0.4:
                        print(f"[IMG]   Skipping full-page scan image on page {page_number} "
                              f"({pil_img.width}x{pil_img.height}px) - already in text chunk")
                        continue

                image_path = f"extracted_images/page{page_number}_{img_counter}.png"
                pil_img.save(image_path, format="PNG")
                img_counter += 1
                print(f"[IMG]   Saved {image_path} "
                      f"({pil_img.width}x{pil_img.height}px, "
                      f"stitched={item.get('stitched', False)})")
                fallback = f"Image on page {page_number}"
                block = {
                    "id": str(uuid.uuid4()),
                    "type": "image",
                    "content": fallback,
                    "embedding_ready_text": fallback,
                    "image_path": image_path,
                    "bbox": list(bbox) if bbox else None,
                }

                blocks.append(block)

                # add embeded images to paddle ocr jobs
                if ocr_embedded_images and not is_scanned:
                    ocr_jobs.append((block, pil_img, is_scanned, fallback))
                elif is_scanned:
                    print(f"[OCR]   Skipping embedded image OCR on scanned page "
                          f"(already covered by full-page Gemini call)")

            # VECTOR DIAGRAMS (in digital pages) -> PaddleOCR 
            if not is_scanned:
                for region in self.detect_diagram_regons(page):

                    # re-render the diagram region at higher res for better OCR results
                    clip_pix = page.get_pixmap(
                        matrix=fitz.Matrix(2, 2), clip=region, alpha=False
                    )
                    
                    # convert to pil for dedup and OCR
                    image_bytes = clip_pix.tobytes("png")

                    # chcek if dup
                    if self.is_duplicate_image(image_bytes, seen_hashes):
                        continue

                    # reshape to an image array for quality check
                    arr = np.frombuffer(clip_pix.samples, dtype=np.uint8).reshape(
                        clip_pix.height, clip_pix.width, -1
                    )

                    # skip if low contrast or mostly white/black 
                    gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
                    if gray.mean() > 248 or gray.std() < 5:
                        continue

                    # add to extracted images and OCR jobs
                    image_path = f"extracted_images/page{page_number}_{img_counter}.png"
                    with open(image_path, "wb") as f:
                        f.write(image_bytes)
                    img_counter += 1

                    fallback = f"Diagram on page {page_number}"
                    pil_img = Image.frombytes(
                        "RGB", [clip_pix.width, clip_pix.height], clip_pix.samples
                    )

                    block = {
                        "id": str(uuid.uuid4()),
                        "type": "image",
                        "content": fallback,
                        "embedding_ready_text": fallback,
                        "image_path": image_path,
                        "bbox": list(region),
                    }

                    blocks.append(block)
                    if ocr_embedded_images:
                        # diagrams in digital PDFs -> always PaddleOCR (is_scanned=False)
                        ocr_jobs.append((block,   pil_img,   False, fallback))

            # START OCR JOBS (parallel) 
            if ocr_jobs:
                with ThreadPoolExecutor(max_workers=max_ocr_workers) as executor:
                    future_map = {
                        executor.submit(
                            self.ocr_embeded_content, pil_img, page_is_scanned
                        ): (block, fallback)
                        for block, pil_img,   page_is_scanned,   fallback in ocr_jobs
                    }

                    for future in as_completed(future_map):
                        block,   fallback = future_map[future]
                        try:

                            text = future.result() or fallback
                        except Exception:

                            text = fallback
                        block["content"] = text
                        block["embedding_ready_text"] = text

            #  TABLES 
            for idx, table in enumerate(extracted_tables.get(page_number,   [])):
                df = getattr(table,  "df",  None)
                if df is None:
                    continue
                table_data =  self.normalize_table(df.values.tolist())
                has_content  =   False
                for row in table_data:
                    for cell in row:
                        if cell.strip():
                            has_content  =  True
                            break

                    if has_content:
                        break
                if not has_content:
                    continue
                csv_path = f"extracted_tables/page{page_number}_table{idx}.csv"
                with open(csv_path, "w", newline="", encoding="utf-8") as f:
                    csv.writer(f).writerows(table_data)

                blocks.append({
                    "id": str(uuid.uuid4()),
                    "type": "table",
                    "content": table_data,
                    "embedding_ready_text": self.convert_table_to_markdown(table_data),
                    "bbox": None,
                    "csv_path": csv_path,
                })

            heading = self._detect_section_heading(blocks, page_number)

            sections.append({
                "id": str(uuid.uuid4()),
                "heading": heading,
                "page": page_number,
                "blocks": blocks,
            })

        logger.info(

            f"PDF extraction complete - {len(sections)} pages | "
            f"Gemini calls: {gemini_call_count['calls']}/{max_gemini_calls or '∞'} | "
            f"Embedded OCR (PaddleOCR): {'on' if ocr_embedded_images else 'off'}"
        )
        return {"sections": sections, "metadata": doc.metadata}

  
    # SECTION HEADING DETECTION
  
    # Pattern that strongly indicate a section heading
    _HEADING_PATTERNS = [
        # "Chapter 3", "Chapter 3:", "Chapter 3 - Title"
        re.compile(
            r'^(chapter|section|part|unit|module|lecture|lab|week)\s*\d+[\s:\-–—]*(.*)',
            re.IGNORECASE
        ),
        # "Question 1", "Q1", "Problem 2", "Exercise 3"
        re.compile(
            r'^(question|problem|exercise|task|q\.?)\s*\d+[\s:\-–—]*(.*)',
            re.IGNORECASE
        ),
        # "1. Introduction", "1.2 Background", "2) Methods"
        re.compile(
            r'^(\d+[\.\)]\d*[\.\)]?\s+)([A-Z][^\n]{3,60})',
            re.IGNORECASE
        ),
        # Common academic section keywords standing alone
        re.compile(
            r'^(introduction|summary|conclusion|abstract|overview|'
            r'background|motivation|methodology|results|discussion|'
            r'references|appendix|notation|definition|theorem|proof)[\s:]*$',
            re.IGNORECASE
        ),
        # catches all CAPS short heading(ex: "MODEL BASED RL", "MCTS")
        re.compile(
            r'^([A-Z][A-Z\s\-]{2,50})$'
        ),
        #  catches Title-Case short line (3-10 words & starts with capital & no sentence punctuation ex: Model-Based-RL)
        re.compile(
            r'^([A-Z][a-zA-Z\-]+(?:\s+[a-zA-Z\-]+){2,9})$'
        ),
    ]

    def _detect_section_heading(self, blocks: list, page_number: int) -> str:
        """
        dettect section heading
          look at the first 1-3 text blocks for heading-pattern matches
          use font-size  if bbox info is available (larger font = heading)
          fall back to "Page N" if nothing matches
        """
        text_blocks = [b for b in blocks if b.get("type") == "text"]
        if not text_blocks:
            return f"Page {page_number}"

        # Check the first few text blocks for heading patterns
        candidates = []
        for block in text_blocks[:4]:
            text = block.get("embedding_ready_text", "").strip()
            if not text:
                continue

            # Only look at the first line of each block
            first_line = text.split('\n')[0].strip()
            if not first_line or len(first_line) > 120:
                continue

            for pattern in self._HEADING_PATTERNS:
                m = pattern.match(first_line)
                if m:
                    # Clean up the matched heading
                    heading = first_line.rstrip('.:')
                    # Handle multiple spaces
                    heading = re.sub(r'\s+', ' ', heading).strip()
                    candidates.append((heading, block))
                    break

        if not candidates:
            return f"Page {page_number}"

        # if multiple candidates -> prefer the one with the largest font
        if len(candidates) == 1:
            return candidates[0][0]

        # Pick the candidate that appears earliest (smallest bbox y0)
        def bbox_y0(candidate):
            bbox = candidate[1].get("bbox")
            if bbox and len(bbox) >= 2:
                return bbox[1]
            return float('inf')

        candidates.sort(key=bbox_y0)
        heading = candidates[0][0]
        print(f"[HEADING] Page {page_number}: detected '{heading}'")
        return heading

  
    # POST-PROCESSING for RAG CHUNKS
  
    # Regex to remove[TYPE: ] prefix from vision descriptions res
    _TYPE_PREFIX_RE = re.compile(r'^\[TYPE:\s*\w+\]\s*\n?', re.IGNORECASE)

    def _image_content_cleaner(self, text: str) -> str:
        """Strip [TYPE: ...] prefix and keep only the semantic content for RAG."""
        return self._TYPE_PREFIX_RE.sub('', text).strip()

    def _is_noise_chunk(self, text: str) -> bool:
        """
        Returns true for chunks that are noise and adds no values
          -Empty or whitespace only
          -Single characters or digits (page numbers and bullet markers)
          -Very short fragments under MIN_CHUNK_CHARS
        """
        MIN_CHARS = int(os.environ.get("MIN_CHUNK_CHARS", "8"))
        stripped = text.strip()
        if not stripped:
            return True
        if re.fullmatch(r'\d{1,3}', stripped):
            return True
        if len(stripped) <= 2:
            return True
        if len(stripped) < MIN_CHARS:
            return True
        if stripped.startswith("Image on page"):
            return True
        return False

    def _tokenize(self, text: str) -> set:
        """Extract lowercase alphanumeric tokens for overlap comparison."""
        return set(re.findall(r'[a-z0-9]+', text.lower()))

    def _image_duplicates_page_text(
        self, image_text: str, page_text_pool: set, threshold: float = 0.7
    ) -> bool:

        # Vision model descriptions are not duplicates they add semantic info
        # that PyMuPDF text extraction never produces
        if  re.search(r'\[TYPE:\s*(diagram|chart|graph|photo|mixed)\]',
                     image_text, re.IGNORECASE):
            return  False

        img_tokens = self._tokenize(image_text)
        if len(img_tokens) < 5:
            # Too short to make a meaningful comparison let noise filter handle it
            return  False

        overlap = len(img_tokens & page_text_pool) / len(img_tokens)
        is_dup = overlap >= threshold
        if is_dup:
            print(f"[RAG]   Dropped duplicate image chunk "
                  f"(overlap={overlap:.0%} with page text)")
        return is_dup

    def _merge_text_blocks(self, blocks: list) -> list:

        MERGE_THRESHOLD =  int(os.environ.get("TEXT_MERGE_THRESHOLD", "60"))

        merged = []
        pending_texts = []

        def flush_pending():
            if not pending_texts:
                return
            combined = " ".join(t.strip() for t in pending_texts if t.strip())
            if combined and not self._is_noise_chunk(combined):
                merged.append({
                    **pending_texts_meta[0],
                    "content": combined,
                    "embedding_ready_text": combined,
                })
            pending_texts.clear()
            pending_texts_meta.clear()

        pending_texts_meta = []

        for block in blocks:
            if block["type"] != "text":
                flush_pending()
                merged.append(block)
                continue

            text = block.get("embedding_ready_text", "").strip()

            if len(text) >= MERGE_THRESHOLD:
                # Long enough to stand alone - flush pending first
                flush_pending()
                merged.append(block)
            else:
                # Short - accumulate for merging
                pending_texts.append(text)
                pending_texts_meta.append(block)

        flush_pending()
        return merged

  
    # STRUCTURE
  
    def structure(self, raw_data):
        from app.models.unified_content_schema import Section, Chunk

        sections = []
        chunk_counter = 0
        total_chunks = 0

        img_dedup_threshold = float(
            os.environ.get("IMAGE_DEDUP_THRESHOLD", "0.7")
        )

        for section in raw_data["sections"]:
            blocks = self._merge_text_blocks(section["blocks"])

            #  Build a token pool from all text and table blocks on this page.
            #  Used to detect image chunks that duplicate already-extracted content.
            page_text_pool: set = set()
            for block in blocks:
                if block["type"] in ("text", "table"):
                    page_text_pool |= self._tokenize(
                        block.get("embedding_ready_text", "")
                    )

            chunks = []
            for block in blocks:
                raw_text = block["embedding_ready_text"]

                if block["type"] == "image":
                    content = self._image_content_cleaner(raw_text)
                    # Skip if noise
                    if self._is_noise_chunk(content):
                        print(f"[RAG]   Dropped noise image chunk: "
                              f"{repr(content[:50])}")
                        continue
                    # Skip if it just duplicates page text (digital PDF screenshots)
                    if self._image_duplicates_page_text(
                        content, page_text_pool, threshold=img_dedup_threshold
                    ):
                        continue
                else:
                    content = raw_text
                    if self._is_noise_chunk(content):
                        print(f"[RAG]   Dropped noise chunk: "
                              f"{repr(content[:50])}")
                        continue

                chunks.append(
                    Chunk(
                        id=str(uuid.uuid4()),
                        content=content,
                        chunk_index=chunk_counter,
                        metadata={
                            "page": section["page"],
                            "section_heading": section["heading"],
                            "chunk_type": block["type"],
                            **(
                                {"image_path": block["image_path"]}
                                if block["type"] == "image"
                                and "image_path" in block
                                else {}
                            ),
                        },
                    )
                )
                chunk_counter += 1

            if chunks:
                sections.append(
                    Section(
                        id=str(uuid.uuid4()),
                        heading=section["heading"],
                        page=section["page"],
                        chunks=chunks,
                    )
                )
                total_chunks += len(chunks)

        return  ParsedContent(
            source_type="pdf",
            title=raw_data["metadata"].get("title", "PDF Document"),
            sections=sections,
            total_chunks=total_chunks,
        )