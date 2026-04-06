"""
PDFParser v3 — Universal PDF parser for learning tutor projects.

OCR Strategy (dual-engine):
  ┌─────────────────────────────────────────────────────────────────┐
  │ Page type         │ Text source     │ Images/Diagrams            │
  ├─────────────────────────────────────────────────────────────────┤
  │ Digital PDF       │ PyMuPDF (free)  │ PaddleOCR (local, free)   │
  │ Scanned/handwrit. │ Gemini API      │ PaddleOCR (Gemini fallback)│
  └─────────────────────────────────────────────────────────────────┘

Why this split:
  - Gemini    → understands handwriting, math notation, layout context
               → burns API quota (20 req/day free) — ONLY used for scans
  - PaddleOCR → local, unlimited, fast for printed text in images/diagrams
               → poor on handwriting/math, great on digital embedded content

Install:
  pip install google-genai PyMuPDF opencv-python-headless pillow numpy img2table
  pip install paddlepaddle paddleocr
  # CPU-only machines: pip install paddlepaddle-cpu paddleocr
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

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════
# PADDLE OCR ENGINE  (local, free, for digital embedded images)
# ═══════════════════════════════════════════════════════════════════

class PaddleOCREngine:
    """
    Lazy-loaded PaddleOCR singleton.

    - Initialises once on first use (~3-5s, downloads models on very first run)
    - If PaddleOCR is not installed, silently returns "" so the parser never crashes
    - Use for: printed text in embedded images and vector diagrams inside digital PDFs
    - Do NOT use for: handwriting, math notation — use Gemini for those
    """

    _instance = None
    _lock = threading.Lock()
    _available: Optional[bool] = None

    @classmethod
    def _is_available(cls) -> bool:
        if cls._available is None:
            try:
                import paddleocr  # noqa: F401
                cls._available = True
            except ImportError:
                logger.warning(
                    "PaddleOCR not installed — embedded image OCR will return empty strings. "
                    "Install with: pip install paddlepaddle paddleocr"
                )
                cls._available = False
        return cls._available

    @classmethod
    def _get_instance(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    from paddleocr import PaddleOCR
                    # PP-OCRv4 uses lightweight mobile det+rec models
                    # vs the default PP-OCRv5_server which is slow on CPU
                    cls._instance = PaddleOCR(ocr_version="PP-OCRv4")
        return cls._instance

    @classmethod
    def _preprocess(cls, image: Image.Image) -> Image.Image:
        """
        Upscale to minimum long edge for PaddleOCR.
        PaddleOCR needs enough pixels to detect text regions accurately.
        No contrast/denoise filtering — those hurt handwritten content.
        """
        MIN_LONG_EDGE = int(os.environ.get("PADDLE_MIN_LONG_EDGE_PX", "2400"))
        w, h = image.size
        long_edge = max(w, h)
        if long_edge < MIN_LONG_EDGE:
            scale = MIN_LONG_EDGE / long_edge
            image = image.resize(
                (int(w * scale), int(h * scale)), Image.LANCZOS
            )
        return image

    @classmethod
    def ocr_image(cls, image: Image.Image, preprocess: bool = True) -> str:
        """Run PaddleOCR on a PIL image. Returns "" if unavailable or fails."""
        if not cls._is_available():
            return ""
        try:
            if preprocess:
                image = cls._preprocess(image)

            ocr = cls._get_instance()
            arr = np.array(image.convert("RGB"))
            min_conf = float(os.environ.get("PADDLE_MIN_CONFIDENCE", "0.5"))

            # PaddleOCR v3: use predict() — ocr(cls=True) is removed
            result = ocr.predict(arr)

            if not result:
                return ""

            lines = []
            # v3 predict() returns a list of dicts with 'rec_texts' and 'rec_scores'
            for item in result:
                if not item:
                    continue
                if isinstance(item, dict):
                    texts = item.get("rec_texts", [])
                    scores = item.get("rec_scores", [])
                    for text, score in zip(texts, scores):
                        if score >= min_conf and text.strip():
                            lines.append(text.strip())
                elif isinstance(item, list):
                    # fallback: v2-style nested list [bbox, (text, conf)]
                    for line in item:
                        try:
                            payload = line[1] if isinstance(line[0], list) else line
                            text, confidence = payload[0], payload[1]
                            if float(confidence) >= min_conf and str(text).strip():
                                lines.append(str(text).strip())
                        except Exception:
                            continue

            return "\n".join(lines).strip()
        except Exception as e:
            logger.warning(f"PaddleOCR failed: {e}")
            return ""


# ═══════════════════════════════════════════════════════════════════
# GEMINI OCR ENGINE  (API, for handwritten / scanned pages ONLY)
# ═══════════════════════════════════════════════════════════════════

OCR_PROMPT = """You are an expert OCR system for academic handwritten notes and documents.
Your job is to extract and reconstruct ALL content from this image as accurately and completely as possible.

TEXT EXTRACTION RULES:
- Extract ALL text exactly as written, preserving the original structure
- Preserve mathematical notation in ASCII math:
  * Subscripts/superscripts: V_i, Q^*, s_{t+1}, gamma^k
  * Arrows: -> (right), <- (left), <-> (both), => (implies)
  * Greek letters spelled out: gamma, pi, alpha, theta, epsilon, lambda, delta
  * Summation: sum_{i=0}^{n}, product: prod, expectation: E[...]
  * Fractions: (num)/(denom)
- Preserve line breaks, indentation, and section hierarchy
- If a word is unclear, write your best guess followed by (?) — never skip content

TABLE RULES:
- If you see a table or grid, reconstruct it as a markdown table
- For checkmarks and symbols in table cells use ONLY these representations:
  * Any checkmark, tick, filled dot, filled box, bullet, or check symbol -> [x]
  * Any empty box, empty circle, or blank cell -> [ ]
  * Any dash, minus, or explicit "none" -> [-]
  * Be consistent — pick one and use it throughout
- Always include row headers and column headers

STRUCTURE RULES:
- Use >, >>, >>> for indentation levels
- Keep section headers on their own line
- Separate sections with a blank line
- Do NOT confuse diagram boxes/nodes/flowchart shapes with checkboxes

OUTPUT: extracted content only — no commentary, no explanations, no meta-statements.
Ignore watermarks like "Scanned with CamScanner"."""


class GeminiOCR:
    """Gemini API OCR — reserved for scanned/handwritten pages to protect quota."""

    _client = None
    _mem_cache: dict = {}          # fast in-memory layer
    _cache_lock = threading.Lock()
    _quota_blocked_until: float = 0.0
    _quota_error_logged: bool = False
    _rate_lock = threading.Lock()
    _next_request_time: float = 0.0



    @classmethod
    def _image_hash(cls, image_bytes: bytes) -> str:
        return hashlib.sha256(image_bytes).hexdigest()

    @classmethod
    def _is_quota_error(cls, error: Exception) -> bool:
        s = str(error).lower()
        return (
            "resource_exhausted" in s
            or "quota exceeded" in s
            or "please retry in" in s
            or (hasattr(error, "status_code") and error.status_code == 429)
        )

    @classmethod
    def _quota_retry_seconds(cls, error: Exception, default: int = 60) -> int:
        match = re.search(r"please retry in\s+(\d+(?:\.\d+)?)s", str(error).lower())
        if match:
            try:
                return max(1, int(math.ceil(float(match.group(1)))))
            except ValueError:
                pass
        return default

    @classmethod
    def is_quota_blocked(cls) -> bool:
        return time.monotonic() < cls._quota_blocked_until

    @classmethod
    def _get_client(cls):
        if cls._client is None:
            api_key = os.environ.get("GEMINI_API_KEY")
            if not api_key:
                raise ValueError("GEMINI_API_KEY not set")
            from google import genai
            cls._client = genai.Client(api_key=api_key)
        return cls._client

    @classmethod
    def _wait_for_rate_slot(cls):
        if cls.is_quota_blocked():
            raise RuntimeError("Gemini quota blocked")
        rpm = max(1, int(os.environ.get("GEMINI_MAX_REQUESTS_PER_MINUTE", "8")))
        interval = 60.0 / rpm
        with cls._rate_lock:
            now = time.monotonic()
            if now < cls._next_request_time:
                time.sleep(cls._next_request_time - now)
                now = time.monotonic()
            cls._next_request_time = now + interval

    @classmethod
    def ocr_image(cls, image: Image.Image, prompt: str = OCR_PROMPT) -> str:
        """Send image to Gemini. Returns "" on any failure."""
        if cls.is_quota_blocked():
            return ""
        model = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash-lite")
        buf = BytesIO()
        image.convert("RGB").save(buf, format="JPEG", quality=75, optimize=True)
        image_bytes = buf.getvalue()
        cache_key = (
            f"{model}:{cls._image_hash(image_bytes)}"
            f":{hashlib.sha1(prompt.encode()).hexdigest()}"
        )

        # Memory cache
        with cls._cache_lock:
            if cache_key in cls._mem_cache:
                print(f"[OCR]   Cache HIT (memory) — skipping Gemini call")
                return cls._mem_cache[cache_key]

        from google.genai import types
        try:
            cls._wait_for_rate_slot()
            response = cls._get_client().models.generate_content(
                model=model,
                contents=[
                    types.Content(
                        role="user",
                        parts=[
                            types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"),
                            types.Part.from_text(text=prompt),
                        ],
                    )
                ],
            )
            text = (response.text or "").strip()
            with cls._cache_lock:
                cls._mem_cache[cache_key] = text
            cls._quota_error_logged = False
            return text
        except RuntimeError:
            return ""
        except Exception as e:
            if cls._is_quota_error(e):
                wait = cls._quota_retry_seconds(e)
                cls._quota_blocked_until = time.monotonic() + wait
                if not cls._quota_error_logged:
                    logger.warning(f"Gemini quota exhausted — pausing OCR for {wait}s.")
                    cls._quota_error_logged = True
            elif "404" in str(e):
                logger.error(f"Gemini model not found: {e}")
            else:
                logger.error(f"Gemini OCR error: {e}")
            return ""


# ═══════════════════════════════════════════════════════════════════
# GROQ OCR ENGINE  (~14,400 req/day free on Llama-4-Scout-17B-16E)
# ═══════════════════════════════════════════════════════════════════

GROQ_OCR_PROMPT = """You are an expert OCR system for academic handwritten notes and documents.
Your job is to extract and reconstruct ALL content from this image as accurately and completely as possible.

TEXT EXTRACTION RULES:
- Extract ALL text exactly as written, preserving the original structure
- Preserve mathematical notation in ASCII math:
  * Subscripts/superscripts: V_i, Q^*, s_{t+1}, gamma^k
  * Arrows: -> (right), <- (left), <-> (both), => (implies)
  * Greek letters spelled out: gamma, pi, alpha, theta, epsilon, lambda, delta
  * Summation: sum_{i=0}^{n}, product: prod, expectation: E[...]
  * Fractions: (num)/(denom)
- Preserve line breaks, indentation, and section hierarchy
- If a word is unclear, write your best guess followed by (?) — never skip content

TABLE RULES:
- If you see a table or grid, reconstruct it as a markdown table
- For checkmarks and symbols in table cells use ONLY these representations:
  * Any checkmark, tick, filled dot, filled box, bullet, or check symbol -> [x]
  * Any empty box, empty circle, or blank cell -> [ ]
  * Any dash, minus, or explicit "none" -> [-]
  * Be consistent — pick one and use it throughout
- Always include row headers and column headers

STRUCTURE RULES:
- Use >, >>, >>> for indentation levels
- Keep section headers on their own line
- Separate sections with a blank line
- Do NOT confuse diagram boxes/nodes/flowchart shapes with checkboxes

OUTPUT: extracted content only — no commentary, no explanations, no meta-statements.
Ignore watermarks like "Scanned with CamScanner"."""


class GroqOCR:
    """
    Groq vision API — high-quota fallback for scanned/handwritten pages.

    Free tier (as of 2025):
      meta-llama/llama-4-scout-17b-16e-instruct  — 500 req/day, 30 req/min
      meta-llama/llama-4-maverick-17b-128e-instruct — 1000 req/day

    Install:  pip install groq
    API key:  https://console.groq.com  (free, no credit card)
    Env var:  GROQ_API_KEY=your_key
    """

    _client = None
    _client_lock = threading.Lock()
    _available: Optional[bool] = None
    _quota_blocked_until: float = 0.0
    _rate_blocked_until: float = 0.0
    _quota_error_logged: bool = False
    _cache_lock = threading.Lock()
    _mem_cache: dict = {}

    @classmethod
    def _is_available(cls) -> bool:
        if cls._available is None:
            if not os.environ.get("GROQ_API_KEY", ""):
                logger.info("GROQ_API_KEY not set — Groq OCR disabled")
                cls._available = False
                return False
            try:
                import groq  # noqa: F401
                cls._available = True
            except ImportError:
                logger.warning("groq not installed — run: pip install groq")
                cls._available = False
        return cls._available

    @classmethod
    def is_quota_blocked(cls) -> bool:
        now = time.monotonic()
        return now < cls._quota_blocked_until or now < cls._rate_blocked_until

    @classmethod
    def _get_client(cls):
        if cls._client is None:
            with cls._client_lock:
                if cls._client is None:
                    from groq import Groq
                    cls._client = Groq(api_key=os.environ["GROQ_API_KEY"])
        return cls._client

    @classmethod
    def _image_hash(cls, image_bytes: bytes) -> str:
        return hashlib.sha256(image_bytes).hexdigest()


    @classmethod
    def ocr_image(cls, image: Image.Image, prompt: str = GROQ_OCR_PROMPT) -> str:
        """
        Send image to Groq vision model for OCR.
        Returns extracted text or "" on failure.
        """
        if not cls._is_available() or cls.is_quota_blocked():
            return ""

        model = os.environ.get(
            "GROQ_VISION_MODEL",
            "meta-llama/llama-4-scout-17b-16e-instruct"
        )

        # Resize image before sending — Groq has a 4MB base64 limit
        # and smaller images are faster. 1600px long edge is plenty for OCR.
        MAX_LONG_EDGE = int(os.environ.get("GROQ_MAX_LONG_EDGE_PX", "1600"))
        w, h = image.size
        long_edge = max(w, h)
        if long_edge > MAX_LONG_EDGE:
            scale = MAX_LONG_EDGE / long_edge
            image = image.resize((int(w * scale), int(h * scale)), Image.LANCZOS)

        buf = BytesIO()
        image.convert("RGB").save(buf, format="JPEG", quality=85, optimize=True)
        image_bytes = buf.getvalue()
        b64 = base64.b64encode(image_bytes).decode("utf-8")
        cache_key = f"{model}:{cls._image_hash(image_bytes)}:{hashlib.sha1(prompt.encode()).hexdigest()}"

        # Memory cache
        with cls._cache_lock:
            if cache_key in cls._mem_cache:
                print("[OCR]   Cache HIT (memory) — skipping Groq call")
                return cls._mem_cache[cache_key]

        try:
            client = cls._get_client()
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{b64}"
                                },
                            },
                            {
                                "type": "text",
                                "text": prompt,
                            },
                        ],
                    }
                ],
                max_tokens=4096,
                temperature=0.0,   # deterministic — we want exact transcription
            )
            text = (response.choices[0].message.content or "").strip()

            with cls._cache_lock:
                cls._mem_cache[cache_key] = text
            cls._quota_error_logged = False
            return text

        except Exception as e:
            err = str(e).lower()
            if "429" in err or "rate" in err or "too many" in err:
                # Rate limit (per-minute) — short block
                cls._rate_blocked_until = time.monotonic() + 65
                if not cls._quota_error_logged:
                    logger.warning(f"Groq rate limit hit — pausing 65s: {e}")
                    cls._quota_error_logged = True
            elif "quota" in err or "exceeded" in err or "limit" in err:
                # Daily quota exhausted — block for the rest of the day
                cls._quota_blocked_until = time.monotonic() + 3600
                logger.warning(f"Groq daily quota exhausted: {e}")
            else:
                logger.error(f"Groq OCR error: {e}")
            return ""


# ═══════════════════════════════════════════════════════════════════
# PDF PARSER
# ═══════════════════════════════════════════════════════════════════

class PDFParser(BaseParser):

    # ─────────────────────────────────────────────────────────────
    # TABLE EXTRACTION
    # ─────────────────────────────────────────────────────────────
    def _extract_tables_with_fallback(self, file_path: str) -> dict:
        if not os.environ.get("ENABLE_IMG2TABLE", "true").lower() in {"1", "true", "yes", "on"}:
            return {}
        try:
            from img2table.document import PDF as Img2TablePDF
            return Img2TablePDF(src=file_path).extract_tables(
                ocr=None, borderless_tables=True,
                implicit_rows=False, implicit_columns=True,
            )
        except Exception as e:
            logger.warning(f"img2table borderless mode failed, retrying in safe mode: {e}")
        try:
            from img2table.document import PDF as Img2TablePDF
            return Img2TablePDF(src=file_path).extract_tables(
                ocr=None, borderless_tables=False,
                implicit_rows=True, implicit_columns=True,
            )
        except Exception as e:
            logger.warning(f"img2table both modes failed — skipping table extraction: {e}")
            return {}

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
    # OCR QUALITY SCORING
    # ─────────────────────────────────────────────────────────────
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
- Be direct and factual — no commentary, no apologies
- If the image is blank or unreadable: [TYPE: empty]
- Never say you cannot see the image"""

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
        Score OCR output quality from 0.0 (garbage) to 1.0 (good).

        Low scores indicate: empty output, hallucinated CJK characters,
        single characters, or suspiciously short/fragmented text from
        what is likely a diagram or figure.
        """
        if not text or not text.strip():
            return 0.0

        stripped = text.strip()

        # Single character or just a number — almost certainly noise
        if len(stripped) <= 2:
            return 0.1

        # Count CJK characters (PaddleOCR hallucinates these on diagrams)
        cjk = sum(1 for c in stripped if '\u4e00' <= c <= '\u9fff')
        if len(stripped) > 0 and cjk / len(stripped) > 0.3:
            return 0.1  # >30% CJK in a non-CJK doc = hallucination

        # Count real English words (crude but effective)
        words = re.findall(r'[a-zA-Z]{2,}', stripped)
        total_tokens = len(stripped.split())

        if total_tokens == 0:
            return 0.1

        word_ratio = len(words) / max(total_tokens, 1)

        # Very few real words — likely noise or scattered diagram labels
        if word_ratio < 0.2 and len(stripped) < 30:
            return 0.2

        # Short but has real words — could be a label, acceptable
        if len(words) >= 2:
            return 0.8

        return 0.5

    def _needs_vision_description(self, paddle_text: str) -> bool:
        """
        Returns True if PaddleOCR output is low quality and we should
        escalate to a vision API for a semantic description.
        """
        threshold = float(os.environ.get("OCR_QUALITY_THRESHOLD", "0.4"))
        score = self._ocr_quality_score(paddle_text)
        print(f"[OCR]   PaddleOCR quality score: {score:.2f} "
              f"(threshold={threshold}, escalate={score < threshold})")
        return score < threshold

    def _get_vision_description(self, image: Image.Image) -> str:
        """
        Use Gemini or Groq to get a concise semantic description of an image
        that PaddleOCR failed on. Filters hallucinated/meta responses.
        Only called when quota is available.
        """
        def is_hallucination(text: str) -> bool:
            return bool(self._HALLUCINATION_RE.search(text))

        # Try Gemini first
        if not GeminiOCR.is_quota_blocked():
            print("[OCR]   Escalating to GEMINI for semantic description")
            result = GeminiOCR.ocr_image(image, prompt=self._VISION_DESCRIBE_PROMPT)
            if result and not is_hallucination(result) and "[TYPE: empty]" not in result:
                print(f"[OCR]   Gemini description: {len(result)} chars")
                return result
            print("[OCR]   Gemini description unusable -> trying Groq")

        # Groq fallback — override its default OCR prompt with the describe prompt
        if GroqOCR._is_available() and not GroqOCR.is_quota_blocked():
            print("[OCR]   Escalating to GROQ for semantic description")
            result = GroqOCR.ocr_image(image, prompt=self._VISION_DESCRIBE_PROMPT)
            if result and not is_hallucination(result) and "[TYPE: empty]" not in result:
                print(f"[OCR]   Groq description: {len(result)} chars")
                return result
            print("[OCR]   Groq description unusable")

        return ""

    # ─────────────────────────────────────────────────────────────
    # DUAL OCR ROUTING  (PaddleOCR + quality-gated vision escalation)
    # ─────────────────────────────────────────────────────────────
    def ocr_embedded_content(self, image: Image.Image, page_is_scanned: bool) -> str:
        """
        Hybrid OCR routing for embedded images and diagrams:

        DIGITAL page images:
          1. PaddleOCR (free, local, fast for printed text)
          2. Quality check — if output is garbage/empty/hallucinated:
             escalate to Gemini/Groq for semantic description (quota-gated)

        SCANNED page images:
          1. Gemini (best for handwriting/math)
          2. Groq fallback
          3. PaddleOCR + quality check + escalation if still bad
        """
        page_type = "SCANNED" if page_is_scanned else "DIGITAL"

        if not page_is_scanned:
            # ── Digital page: PaddleOCR first ────────────────────
            print(f"[OCR]   embedded image ({page_type}) -> PADDLEOCR")
            paddle_result = PaddleOCREngine.ocr_image(image)
            print(f"[OCR]   PaddleOCR: {len(paddle_result)} chars" if paddle_result
                  else "[OCR]   PaddleOCR: no text found")

            # Quality gate — escalate bad/empty results to vision API
            if self._needs_vision_description(paddle_result):
                vision_result = self._get_vision_description(image)
                if vision_result:
                    return vision_result
                # Vision also failed — return whatever Paddle got (even if bad)
                # so the chunk isn't completely empty
                return paddle_result

            return paddle_result

        else:
            # ── Scanned page: API engines first ──────────────────
            if not GeminiOCR.is_quota_blocked():
                print(f"[OCR]   embedded image ({page_type}) -> GEMINI")
                result = GeminiOCR.ocr_image(image)
                if result:
                    print(f"[OCR]   Gemini result: {len(result)} chars")
                    return result
                print("[OCR]   Gemini returned nothing -> trying Groq")

            if GroqOCR._is_available() and not GroqOCR.is_quota_blocked():
                print(f"[OCR]   embedded image ({page_type}) -> GROQ")
                result = GroqOCR.ocr_image(image)
                if result:
                    print(f"[OCR]   Groq result: {len(result)} chars")
                    return result
                print("[OCR]   Groq returned nothing -> PADDLEOCR")

            print(f"[OCR]   embedded image ({page_type}) -> PADDLEOCR (last resort)")
            paddle_result = PaddleOCREngine.ocr_image(image)
            print(f"[OCR]   PaddleOCR: {len(paddle_result)} chars" if paddle_result
                  else "[OCR]   PaddleOCR: no text found")

            # Even on scanned pages, quality-check PaddleOCR output
            if self._needs_vision_description(paddle_result):
                vision_result = self._get_vision_description(image)
                if vision_result:
                    return vision_result

            return paddle_result

    # TEXT CLEANING
    # ─────────────────────────────────────────────────────────────
    def clean_text(self, text: str) -> str:
        return re.sub(r"\s+", " ", text).strip()

    # ─────────────────────────────────────────────────────────────
    # VECTOR DIAGRAM DETECTION
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
            return any(tb.contains(r) for tb in text_bboxes)

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
                    if (current + (-merge_gap, -merge_gap, merge_gap, merge_gap)).intersects(rects[j]):
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
            density = sum(
                1 for dr in all_drawing_rects if r.contains(dr) or r.intersects(dr)
            )
            if density < 3 and area < 15000:
                continue
            if not any(
                not (r & a).is_empty and (r & a).width * (r & a).height / area > 0.85
                for a in regions
            ):
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

    def is_duplicate_image(self, image_bytes: bytes, seen_hashes: set) -> bool:
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
        if smask_xref:
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
    # TILE DETECTION & STITCHING
    # ─────────────────────────────────────────────────────────────
    def stitch_page_tiles(self, page, collected: list) -> list:
        """
        Many PDFs store large images as a grid of small tiles (e.g. 256x256px)
        or horizontal strips. PyMuPDF extracts each tile separately, producing
        dozens of tiny images instead of one coherent picture.

        This method:
          1. Gets the actual bbox of every image on the page from PyMuPDF
          2. Groups images whose bboxes are adjacent (within TILE_GAP pt)
          3. Stitches each group by re-rendering the union region from the page
          4. Returns a new list — tile groups replaced by one stitched image,
             non-tile images kept as-is

        `collected` items are dicts:
            {"pil": PIL.Image, "bbox": tuple|None, "xref": int|None}
        """
        TILE_GAP = float(os.environ.get("TILE_STITCH_GAP_PT", "8"))
        MIN_TILES = int(os.environ.get("TILE_MIN_COUNT", "2"))
        # Square tiles: both dims must be under this
        MAX_TILE_DIM = int(os.environ.get("TILE_MAX_SINGLE_DIM_PX", "512"))
        # Strips: short in ONE dimension (height for h-strips, width for v-strips)
        MAX_STRIP_SHORT_DIM = int(os.environ.get("TILE_MAX_STRIP_SHORT_DIM_PX", "300"))

        # Build xref->bbox map from page image info
        xref_to_bbox: dict = {}
        try:
            for info in page.get_image_info(xrefs=True):
                xref = info.get("xref", 0)
                bbox = info.get("bbox")
                if xref and bbox:
                    xref_to_bbox[xref] = tuple(bbox)
        except Exception:
            return collected

        for item in collected:
            if item.get("bbox") is None and item.get("xref"):
                item["bbox"] = xref_to_bbox.get(item["xref"])

        # Log what we see so you can tune thresholds
        for item in collected:
            img = item["pil"]
            bbox = item.get("bbox")
            logger.debug(
                f"  image xref={item.get('xref')} "
                f"pixels={img.width}x{img.height} "
                f"bbox={tuple(round(v,1) for v in bbox) if bbox else None}"
            )

        def is_tile_or_strip(item) -> bool:
            """
            Returns True if this image looks like part of a tiled/stripped image:
              - Square tile:     both width and height <= MAX_TILE_DIM
              - Horizontal strip: height <= MAX_STRIP_SHORT_DIM (any width)
              - Vertical strip:   width  <= MAX_STRIP_SHORT_DIM (any height)
            Must also have a known bbox so we can cluster by position.
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
        candidates = []
        non_tiles = []
        for item in collected:
            if is_tile_or_strip(item):
                candidates.append(item)
            else:
                non_tiles.append(item)

        logger.debug(
            f"Page tile detection: {len(candidates)} candidates, "
            f"{len(non_tiles)} whole images, gap={TILE_GAP}pt"
        )

        if len(candidates) < MIN_TILES:
            # Not enough fragments — treat everything as whole images
            return collected

        # Cluster candidates whose bboxes are spatially adjacent.
        # "Adjacent" means the bboxes touch or overlap when each is expanded by TILE_GAP.
        def adjacent(a, b, gap):
            return (
                a[0] - gap <= b[2] and a[2] + gap >= b[0]
                and a[1] - gap <= b[3] and a[3] + gap >= b[1]
            )

        clusters: list = []
        used = [False] * len(candidates)
        for i, item in enumerate(candidates):
            if used[i]:
                continue
            cluster = [item]
            used[i] = True
            # Keep expanding cluster until no new neighbours found
            changed = True
            while changed:
                changed = False
                for j in range(len(candidates)):
                    if used[j]:
                        continue
                    if any(adjacent(m["bbox"], candidates[j]["bbox"], TILE_GAP)
                           for m in cluster):
                        cluster.append(candidates[j])
                        used[j] = True
                        changed = True
            clusters.append(cluster)

        result = list(non_tiles)

        for cluster in clusters:
            if len(cluster) < MIN_TILES:
                result.extend(cluster)
                continue

            # Union bbox of the entire cluster
            xs0 = min(item["bbox"][0] for item in cluster)
            ys0 = min(item["bbox"][1] for item in cluster)
            xs1 = max(item["bbox"][2] for item in cluster)
            ys1 = max(item["bbox"][3] for item in cluster)

            try:
                # Re-render the union region from the page at 2x for quality
                clip_pix = page.get_pixmap(
                    matrix=fitz.Matrix(2, 2),
                    clip=fitz.Rect(xs0, ys0, xs1, ys1),
                    alpha=False,
                )
                stitched = Image.frombytes(
                    "RGB", [clip_pix.width, clip_pix.height], clip_pix.samples
                )
                logger.debug(
                    f"Stitched {len(cluster)} tiles into "
                    f"{stitched.width}x{stitched.height}px image"
                )
                result.append({
                    "pil": stitched,
                    "bbox": (xs0, ys0, xs1, ys1),
                    "xref": None,
                    "stitched": True,
                })
            except Exception as e:
                logger.warning(f"Tile stitching failed ({len(cluster)} tiles): {e}")
                result.extend(cluster)

        return result

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

        # ── Config ───────────────────────────────────────────────
        max_ocr_workers = max(1, int(os.environ.get("GEMINI_OCR_MAX_WORKERS", "1")))
        scanned_page_zoom = float(os.environ.get("SCANNED_PAGE_RENDER_ZOOM", "1.5"))
        # OCR_EMBEDDED_IMAGES=true → PaddleOCR runs on every embedded image/diagram
        # in digital pages. No quota cost. Safe to leave on.
        ocr_embedded_images = os.environ.get("OCR_EMBEDDED_IMAGES", "true").lower() in {
            "1", "true", "yes", "on"
        }
        # Gemini budget — only full scanned-page calls count against this
        max_gemini_calls = max(0, int(os.environ.get("MAX_OCR_CALLS_PER_DOC", "5")))

        # Mutable dict so the closure always reads the live count (not a stale int copy)
        gemini_state = {"calls": 0}

        def can_call_gemini() -> bool:
            if GeminiOCR.is_quota_blocked():
                return False
            return max_gemini_calls == 0 or gemini_state["calls"] < max_gemini_calls

        def charge_gemini():
            gemini_state["calls"] += 1

        # ── Setup dirs ───────────────────────────────────────────
        for folder in ("extracted_images", "extracted_tables"):
            if os.path.exists(folder):
                shutil.rmtree(folder)
            os.makedirs(folder)

        extracted_xrefs: set = set()
        seen_hashes: set = set()
        extracted_tables = self._extract_tables_with_fallback(file_path)

        for page_index, page in enumerate(doc):
            page_number = page_index + 1
            blocks = []
            ocr_jobs: list = []  # (block, pil_image, page_is_scanned, fallback_text)
            is_scanned = self.is_scanned_page(page)
            print(f"[PDF] Page {page_number}/{len(doc)} -> "
                  f"{'SCANNED/HANDWRITTEN' if is_scanned else 'DIGITAL'}")

            # ── SCANNED / HANDWRITTEN PAGE → Mistral → Gemini → PaddleOCR ──
            if is_scanned:
                text = ""
                # Standard zoom for API engines (smaller = faster upload)
                image = self.render_page(page, zoom=scanned_page_zoom)

                # 1. Gemini — 20 req/day free, best for handwriting/math
                if can_call_gemini():
                    charge_gemini()
                    print(f"[OCR]   Page {page_number}: full page -> GEMINI "
                          f"(call {gemini_state['calls']}/{max_gemini_calls or 'unlimited'})")
                    text = GeminiOCR.ocr_image(image)
                    if text:
                        print(f"[OCR]   Page {page_number}: Gemini OK - {len(text)} chars")
                    else:
                        print(f"[OCR]   Page {page_number}: Gemini returned nothing -> trying Groq")
                else:
                    print(f"[OCR]   Page {page_number}: Gemini skipped "
                          f"(blocked={GeminiOCR.is_quota_blocked()}, "
                          f"calls={gemini_state['calls']}/{max_gemini_calls}) -> trying Groq")

                # 2. Groq — ~1000 req/day free, Llama 4 vision
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

                # 3. PaddleOCR — local, unlimited, last resort
                # Re-render at higher zoom: PaddleOCR needs more pixels for handwriting
                if not text:
                    print(f"[OCR]   Page {page_number}: full page -> PADDLEOCR (last resort)")
                    paddle_image = self.render_page(page, zoom=3.0)
                    text = PaddleOCREngine.ocr_image(paddle_image, preprocess=True)
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
            # ── DIGITAL PAGE → PyMuPDF direct text ───────────────
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

            # ── EMBEDDED IMAGES → collect → stitch → PaddleOCR ──
            # Step 1: collect all raw images from the page (no OCR yet)
            # Step 2: stitch tiled images back into whole images
            # Step 3: save + queue OCR jobs
            img_counter = 0
            raw_collected: list = []  # {"pil", "bbox", "xref"}

            # Pass 1: resource images
            for img in page.get_images(full=True):
                xref = img[0]
                if xref in extracted_xrefs:
                    continue
                extracted_xrefs.add(xref)
                try:
                    pix = self._extract_pixmap(doc, img)
                    if self.is_garbage_image(pix):
                        continue
                    raw_collected.append({
                        "pil": self._pixmap_to_pil(pix),
                        "bbox": None,  # filled by stitch_page_tiles via image_info
                        "xref": xref,
                    })
                except Exception:
                    continue

            # Pass 2: inline images (catches anything missed by pass 1)
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
                    raw_collected.append({
                        "pil": self._pixmap_to_pil(pix),
                        "bbox": info.get("bbox"),
                        "xref": xref,
                    })
                except Exception:
                    continue

            # Step 2: stitch tiles — replaces clusters of small adjacent images
            # with a single re-rendered image of their combined region
            stitched_collected = self.stitch_page_tiles(page, raw_collected)
            print(f"[IMG]   Page {page_number}: {len(raw_collected)} raw images -> "
                  f"{len(stitched_collected)} after stitch (OCR queued: {ocr_embedded_images})")

            # Step 3: dedup, save, queue OCR
            page_area = page.rect.width * page.rect.height
            for item in stitched_collected:
                pil_img = item["pil"]
                bbox = item.get("bbox")
                image_bytes = pil_img.tobytes()  # raw bytes for dedup
                if self.is_duplicate_image(image_bytes, seen_hashes):
                    continue

                # Skip saving the image block if this is a scanned page AND
                # the image covers most of the page — it IS the scanned page,
                # already fully OCR'd by Gemini as a text chunk above.
                # Saving it would produce a duplicate image chunk with no extra value.
                if is_scanned and bbox is not None:
                    bw = bbox[2] - bbox[0]
                    bh = bbox[3] - bbox[1]
                    if page_area > 0 and (bw * bh) / page_area > 0.4:
                        print(f"[IMG]   Skipping full-page scan image on page {page_number} "
                              f"({pil_img.width}x{pil_img.height}px) — already in text chunk")
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
                if ocr_embedded_images and not is_scanned:
                    # SCANNED pages: skip — the full-page Gemini call already
                    # extracted all text. The embedded image IS the page itself,
                    # so OCR-ing it again is a duplicate that burns quota.
                    # DIGITAL pages: queue PaddleOCR for embedded images.
                    ocr_jobs.append((block, pil_img, is_scanned, fallback))
                elif is_scanned:
                    print(f"[OCR]   Skipping embedded image OCR on scanned page "
                          f"(already covered by full-page Gemini call)")

            # ── VECTOR DIAGRAMS → PaddleOCR ──────────────────────
            # Only on digital pages — scanned pages are already handled as
            # a full-page image by Gemini above.
            if not is_scanned:
                for region in self.detect_diagram_regions(page):
                    clip_pix = page.get_pixmap(
                        matrix=fitz.Matrix(2, 2), clip=region, alpha=False
                    )
                    image_bytes = clip_pix.tobytes("png")
                    if self.is_duplicate_image(image_bytes, seen_hashes):
                        continue
                    arr = np.frombuffer(clip_pix.samples, dtype=np.uint8).reshape(
                        clip_pix.height, clip_pix.width, -1
                    )
                    gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
                    if gray.mean() > 248 or gray.std() < 5:
                        continue

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
                        # Diagrams in digital PDFs → always PaddleOCR (is_scanned=False)
                        ocr_jobs.append((block, pil_img, False, fallback))

            # ── FLUSH OCR JOBS (parallel) ─────────────────────────
            if ocr_jobs:
                with ThreadPoolExecutor(max_workers=max_ocr_workers) as executor:
                    future_map = {
                        executor.submit(
                            self.ocr_embedded_content, pil_img, page_is_scanned
                        ): (block, fallback)
                        for block, pil_img, page_is_scanned, fallback in ocr_jobs
                    }
                    for future in as_completed(future_map):
                        block, fallback = future_map[future]
                        try:
                            text = future.result() or fallback
                        except Exception:
                            text = fallback
                        block["content"] = text
                        block["embedding_ready_text"] = text

            # ── TABLES ────────────────────────────────────────────
            for idx, table in enumerate(extracted_tables.get(page_number, [])):
                df = getattr(table, "df", None)
                if df is None:
                    continue
                table_data = self.normalize_table(df.values.tolist())
                if not any(cell.strip() for row in table_data for cell in row):
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
            f"PDF extraction complete — {len(sections)} pages | "
            f"Gemini calls: {gemini_state['calls']}/{max_gemini_calls or '∞'} | "
            f"Embedded OCR (PaddleOCR): {'on' if ocr_embedded_images else 'off'}"
        )
        return {"sections": sections, "metadata": doc.metadata}

    # ─────────────────────────────────────────────────────────────
    # SECTION HEADING DETECTION
    # ─────────────────────────────────────────────────────────────

    # Patterns that strongly indicate a section heading, in priority order.
    # Each is (compiled_regex, format_string).
    # format_string uses match.group(0) if None, or named groups otherwise.
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
        # ALL CAPS short heading: "MODEL BASED RL", "MCTS"
        re.compile(
            r'^([A-Z][A-Z\s\-]{2,50})$'
        ),
        # Title-case short line (3-10 words, starts with capital, no sentence punctuation)
        # Catches slide titles like "Model-Based Design in Industry"
        re.compile(
            r'^([A-Z][a-zA-Z\-]+(?:\s+[a-zA-Z\-]+){2,9})$'
        ),
    ]

    def _detect_section_heading(self, blocks: list, page_number: int) -> str:
        """
        Detect a meaningful section heading from the page's text blocks.

        Strategy:
          1. Look at the first 1-3 text blocks for heading-pattern matches
          2. Use font-size heuristic if bbox info is available (larger = heading)
          3. Fall back to "Page N" if nothing matches

        Returns a heading string like "Question 1", "Chapter 2: Model-Based RL",
        or "Page 3" as fallback.
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
                    # Collapse multiple spaces
                    heading = re.sub(r'\s+', ' ', heading).strip()
                    candidates.append((heading, block))
                    break

        if not candidates:
            return f"Page {page_number}"

        # If multiple candidates, prefer the one with the largest font
        # (bbox top coord is smaller = higher on page = likely a title)
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

    # ─────────────────────────────────────────────────────────────
    # RAG POST-PROCESSING
    # ─────────────────────────────────────────────────────────────
    # Regex to strip [TYPE: ...] prefix from vision descriptions
    _TYPE_PREFIX_RE = re.compile(r'^\[TYPE:\s*\w+\]\s*\n?', re.IGNORECASE)

    def _clean_image_content(self, text: str) -> str:
        """Strip [TYPE: ...] prefix — keep only the semantic content for RAG."""
        return self._TYPE_PREFIX_RE.sub('', text).strip()

    def _is_noise_chunk(self, text: str) -> bool:
        """
        Returns True for chunks that add no value to a RAG pipeline:
          - Empty or whitespace only
          - Single characters or digits (page numbers, bullet markers)
          - Very short fragments under MIN_CHUNK_CHARS
          - Fallback placeholder text
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
        """
        Returns True if the image's OCR text is largely covered by text already
        extracted from the same page via PyMuPDF.

        This catches the common digital PDF pattern where an image is just a
        screenshot of content that PyMuPDF already extracted perfectly as text
        (e.g. a table screenshot, a formula screenshot, a text block rendered
        as an image by the PDF authoring tool).

        Uses token-level Jaccard-style overlap:
          overlap = |image_tokens ∩ page_tokens| / |image_tokens|
        If >= threshold of the image's tokens already exist in the page text → duplicate.
        """
        # Vision descriptions are not duplicates — they add semantic info
        # that PyMuPDF text extraction never produces
        if re.search(r'\[TYPE:\s*(diagram|chart|graph|photo|mixed)\]',
                     image_text, re.IGNORECASE):
            return False

        img_tokens = self._tokenize(image_text)
        if len(img_tokens) < 5:
            # Too short to make a meaningful comparison — let noise filter handle it
            return False

        overlap = len(img_tokens & page_text_pool) / len(img_tokens)
        is_dup = overlap >= threshold
        if is_dup:
            print(f"[RAG]   Dropped duplicate image chunk "
                  f"(overlap={overlap:.0%} with page text)")
        return is_dup

    def _merge_text_blocks(self, blocks: list) -> list:
        """
        Merge consecutive short text blocks on the same page into one chunk.
        This prevents scattered diagram labels (each on their own line from
        PyMuPDF) from becoming dozens of useless single-word chunks.

        A block is a merge candidate if it's a text block under MERGE_THRESHOLD chars.
        Image and table blocks are never merged.
        """
        MERGE_THRESHOLD = int(os.environ.get("TEXT_MERGE_THRESHOLD", "60"))

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
                # Long enough to stand alone — flush pending first
                flush_pending()
                merged.append(block)
            else:
                # Short — accumulate for merging
                pending_texts.append(text)
                pending_texts_meta.append(block)

        flush_pending()
        return merged

    # ─────────────────────────────────────────────────────────────
    # STRUCTURE
    # ─────────────────────────────────────────────────────────────
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

            # Build a token pool from all text and table blocks on this page.
            # Used to detect image chunks that duplicate already-extracted content.
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
                    content = self._clean_image_content(raw_text)
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

        return ParsedContent(
            source_type="pdf",
            title=raw_data["metadata"].get("title", "PDF Document"),
            sections=sections,
            total_chunks=total_chunks,
        )