
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




# for printed text in embedded images and vector diagrams inside digital PDFs
class PaddleOCR:
    """ Used forprinted text in embedded images and vector diagrams inside digital PDFs
    """

    _instance = None
    _lock = threading.Lock()
    _available: Optional[bool] = None

    @classmethod
    # checks if paddle ocr is installed or not
    def _is_available(cls) -> bool:
        if cls._available is None:
            try:
                import paddleocr  
                cls._available = True
            except ImportError:
                logger.warning(
                    "PaddleOCR not (installed embedded image OCR will return empty strings.) "
                )
                cls._available = False
        return cls._available

    @classmethod
    def _get_instance(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    from paddleocr import PaddleOCR
                    cls._instance = PaddleOCR(ocr_version="PP-OCRv4")
        return cls._instance

    @classmethod
    def _preprocess(cls, image: Image.Image) -> Image.Image:
        """preprocess the image for PaddleOCR
        """
        MIN_LONG_EDGE = int(os.environ.get("PADDLE_MIN_LONG_EDGE_PX", "2400"))
        w, h = image.size
        long_edge = max(w, h)
        if long_edge < MIN_LONG_EDGE:
            scale =   MIN_LONG_EDGE / long_edge
            image =   image.resize(
                (int(w * scale), int(h * scale)), Image.LANCZOS
            )
        return image

    @classmethod
    def ocr_image(cls, image: Image.Image, preprocess: bool =   True) -> str:
        """Run PaddleOCR on a PIL image returns "" if unavailable or fails."""
        if not cls._is_available():
            return ""
        try:
            if preprocess:
                image =   cls._preprocess(image)

            ocr=   cls._get_instance()
            arr=  np.array(image.convert("RGB"))
            min_conf=  float(os.environ.get("PADDLE_MIN_CONFIDENCE", "0.5"))

            result=  ocr.predict(arr)

            if not result:
                return ""

            lines=  []
            for item in result:
                if not item:
                    continue
                if isinstance(item, dict):
                    texts=  item.get("rec_texts", [])
                    scores=  item.get("rec_scores", [])
                    for text, score in zip(texts, scores):
                        if score >= min_conf and text.strip():
                            lines.append(text.strip())
                elif isinstance(item, list):
                    for line in item:
                        try:
                            payload=  line[1] if isinstance(line[0], list) else line
                            text, confidence=  payload[0], payload[1]
                            if float(confidence) >= min_conf and str(text).strip():
                                lines.append(str(text).strip())
                        except Exception:
                            continue

            return "\n".join(lines).strip()
        except Exception as e:
            logger.warning(f"PaddleOCR failed: {e}")
            return ""


# GEMINI OCR 

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
- If a word is unclear, write your best guess followed by (?) - never skip content

TABLE RULES:
- If you see a table or grid, reconstruct it as a markdown table
- For checkmarks and symbols in table cells use ONLY these representations:
  * Any checkmark, tick, filled dot, filled box, bullet, or check symbol -> [x]
  * Any empty box, empty circle, or blank cell -> [ ]
  * Any dash, minus, or explicit "none" -> [-]
  * Be consistent - pick one and use it throughout
- Always include row headers and column headers

STRUCTURE RULES:
- Use >, >>, >>> for indentation levels
- Keep section headers on their own line
- Separate sections with a blank line
- Do NOT confuse diagram boxes/nodes/flowchart shapes with checkboxes

OUTPUT: extracted content only - no commentary, no explanations, no meta-statements.
Ignore watermarks like "Scanned with CamScanner"."""


class GeminiOCR:
    """ Gemini vision API for scanned/handwritten pages."""
    _client  =  None
    _mem_cache: dict  =  {}         
    _cache_lock  =  threading.Lock()
    _quota_blocked_until: float  =  0.0
    _quota_error_logged: bool  =  False
    _rate_lock  =  threading.Lock()
    _next_request_time: float  =  0.0



    @classmethod
    def _image_hash(cls, image_bytes: bytes) -> str:
        return hashlib.sha256(image_bytes).hexdigest()

    @classmethod
    def _is_quota_error(cls, error: Exception) -> bool:
        s  =  str(error).lower()
        return (
            "resource_exhausted" in s
            or "quota exceeded" in s
            or "please retry in" in s
            or (hasattr(error, "status_code") and error.status_code == 429)
        )

    @classmethod
    def _quota_retry_seconds(cls, error: Exception, default: int  =  60) -> int:
        match  =  re.search(r"please retry in\s+(\d+(?:\.\d+)?)s", str(error).lower())
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
            api_key  =  os.environ.get("GEMINI_API_KEY")
            if not api_key:
                raise ValueError("GEMINI_API_KEY not set")
            from google import genai
            cls._client  =  genai.Client(api_key=api_key)
        return cls._client

    @classmethod
    def _wait_for_rate_slot(cls):
        if cls.is_quota_blocked():
            raise RuntimeError("Gemini quota blocked")
        rpm  =  max(1, int(os.environ.get("GEMINI_MAX_REQUESTS_PER_MINUTE", "8")))
        interval  =  60.0 / rpm
        with cls._rate_lock:
            now  =  time.monotonic()
            if now < cls._next_request_time:
                time.sleep(cls._next_request_time - now)
                now  =  time.monotonic()
            cls._next_request_time  =  now + interval

    @classmethod
    def ocr_image(cls, image: Image.Image, prompt: str  =  OCR_PROMPT) -> str:
        """Send image to Gemini. Returns "" on any failure."""
        if cls.is_quota_blocked():
            return ""
        model  =  os.environ.get("GEMINI_MODEL", "gemini-2.5-flash-lite")
        buf  =  BytesIO()
        image.convert("RGB").save(buf, format="JPEG", quality=75, optimize=True)
        image_bytes  =  buf.getvalue()
        cache_key  =  (
            f"{model}:{cls._image_hash(image_bytes)}"
            f":{hashlib.sha1(prompt.encode()).hexdigest()}"
        )

        # Memory cache
        with cls._cache_lock:
            if cache_key in cls._mem_cache:
                print(f"[OCR]   Cache HIT (memory) - skipping Gemini call")
                return cls._mem_cache[cache_key]

        from google.genai import types
        try:
            cls._wait_for_rate_slot()
            response  =  cls._get_client().models.generate_content(
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
            text  =  (response.text or "").strip()
            with cls._cache_lock:
                cls._mem_cache[cache_key]  =  text
            cls._quota_error_logged  =  False
            return text
        except RuntimeError:
            return ""
        except Exception as e:
            if cls._is_quota_error(e):
                wait  =  cls._quota_retry_seconds(e)
                cls._quota_blocked_until  =  time.monotonic() + wait
                if not cls._quota_error_logged:
                    logger.warning(f"Gemini quota exhausted - pausing OCR for {wait}s.")
                    cls._quota_error_logged  =  True
            elif "404" in str(e):
                logger.error(f"Gemini model not found: {e}")
            else:
                logger.error(f"Gemini OCR error: {e}")
            return ""


# GROQ OCR 

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
- If a word is unclear, write your best guess followed by (?) - never skip content

TABLE RULES:
- If you see a table or grid, reconstruct it as a markdown table
- For checkmarks and symbols in table cells use ONLY these representations:
  * Any checkmark, tick, filled dot, filled box, bullet, or check symbol -> [x]
  * Any empty box, empty circle, or blank cell -> [ ]
  * Any dash, minus, or explicit "none" -> [-]
  * Be consistent - pick one and use it throughout
- Always include row headers and column headers

STRUCTURE RULES:
- Use >, >>, >>> for indentation levels
- Keep section headers on their own line
- Separate sections with a blank line
- Do NOT confuse diagram boxes/nodes/flowchart shapes with checkboxes

OUTPUT: extracted content only - no commentary, no explanations, no meta-statements.
Ignore watermarks like "Scanned with CamScanner"."""


class GroqOCR:
    """ Groq vision API for scanned/handwritten pages."""
    _client = None
    _client_lock = threading.Lock()
    _available: Optional[bool] = None
    _quota_blocked_until: float = 0.0
    _rate_blocked_until: float = 0.0
    _quota_error_logged: bool  =      False
    _cache_lock  =      threading.Lock()
    _mem_cache: dict  =      {}

    @classmethod
    def _is_available(cls) -> bool:
        if cls._available is None:
            if not os.environ.get("GROQ_API_KEY", ""):
                logger.info("GROQ_API_KEY not set")
                cls._available  =      False
                return False
            try:
                import groq  
                cls._available  =      True
            except ImportError:
                logger.warning("groq not installed")
                cls._available  =      False
        return cls._available

    @classmethod
    def is_quota_blocked(cls) -> bool:
        now  =      time.monotonic()
        return now < cls._quota_blocked_until or now < cls._rate_blocked_until

    @classmethod
    def _get_client(cls):
        if cls._client is None:
            with cls._client_lock:
                if cls._client is None:
                    from groq import Groq
                    cls._client  =      Groq(api_key=os.environ["GROQ_API_KEY"])
        return cls._client

    @classmethod
    def _image_hash(cls, image_bytes: bytes) -> str:
        return hashlib.sha256(image_bytes).hexdigest()


    @classmethod
    def ocr_image(cls, image: Image.Image, prompt: str  =      GROQ_OCR_PROMPT) -> str:
        """
        send image to Groq  for OCR it returns extracted text or "" on failure
        """
        if not cls._is_available() or cls.is_quota_blocked():
            return ""

        model  =     os.environ.get(
            "GROQ_VISION_MODEL",
            "meta-llama/llama-4-scout-17b-16e-instruct"
        )

        # Resize image to 1600 pixl before sending as Groq has a 4MB limit
        MAX_LONG_EDGE  =     int(os.environ.get("GROQ_MAX_LONG_EDGE_PX", "1600"))
        w, h  =      image.size
        long_edge  =      max(w, h)
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
                print("[OCR]   Cache HIT (memory) - skipping Groq call")
                return cls._mem_cache[cache_key]

        try:
            client =   cls._get_client()
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
                temperature=0.0,   
            )
            text = (response.choices[0].message.content or "").strip()

            with cls._cache_lock:
                cls._mem_cache[cache_key] = text
            cls._quota_error_logged = False
            return text

        except Exception as e:
            err = str(e).lower()
            if "429" in err or "rate" in err or "too many" in err:
                # Rate limit (per-minute) 
                cls._rate_blocked_until = time.monotonic() + 65
                if not cls._quota_error_logged:
                    logger.warning(f"Groq rate limit hit - pausing 65s: {e}")
                    cls._quota_error_logged = True
            elif "quota" in err or "exceeded" in err or "limit" in err:
                # Daily quota exhausted 
                cls._quota_blocked_until = time.monotonic() + 3600
                logger.warning(f"Groq daily quota exhausted: {e}")
            else:
                logger.error(f"Groq OCR error: {e}")
            return ""