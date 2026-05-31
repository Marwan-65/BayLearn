import json
import re
from pathlib import Path
from typing import Dict, List, Any


def _clean_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    # Collapse excessive spaces/tabs inside lines
    text = re.sub(r"[ \t]+", " ", text)
    # Collapse 3+ newlines to 2
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _is_noise_line(line: str) -> bool:
    line = line.strip()
    if not line:
        return True
    # Common repeating PDF header/footer patterns (tweak as needed)
    if re.match(r"^Frontiers in Humanities and Social Sciences.*$", line, re.IGNORECASE):
        return True
    if re.match(r"^ISSN:\s*\d{4}-\d{4}.*$", line, re.IGNORECASE):
        return True
    return False


def reconstruct_full_text(parsed: Dict[str, Any], keep_section_markers: bool = True) -> str:
    """
    Converts parser output (sections/chunks) into one clean plain-text document string,
    preserving reading order and light structure.
    """
    sections = parsed.get("sections", [])
    blocks: List[str] = []

    for section in sections:
        heading = (section.get("heading") or "").strip()
        page = section.get("page")
        chunks = section.get("chunks", [])

        # Ensure order even if source is not sorted
        chunks = sorted(chunks, key=lambda c: c.get("chunk_index", 10**9))

        if keep_section_markers:
            marker = f"SECTION: {heading or 'Untitled'}"
            if page is not None:
                marker += f" | PAGE: {page}"
            blocks.append(marker)

        for chunk in chunks:
            content = _clean_text(str(chunk.get("content", "")))
            if content:
                blocks.append(content)

    # Remove obvious noise lines and duplicate consecutive lines
    cleaned_lines: List[str] = []
    prev = None
    for raw_line in "\n\n".join(blocks).split("\n"):
        line = raw_line.strip()
        if _is_noise_line(line):
            continue
        if line == prev:
            continue
        cleaned_lines.append(line)
        prev = line

    full_text = _clean_text("\n".join(cleaned_lines))
    return full_text


def build_windows(text: str, max_chars: int = 12000, overlap_chars: int = 1200) -> List[str]:
    """
    Splits long text into sequential windows for LLM APIs with context limits.
    Keeps paragraph boundaries where possible.
    """
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    windows: List[str] = []
    current = ""

    for p in paragraphs:
        candidate = (current + "\n\n" + p).strip() if current else p
        if len(candidate) <= max_chars:
            current = candidate
            continue

        if current:
            windows.append(current)

            # Keep tail overlap from previous window for continuity
            tail = current[-overlap_chars:] if overlap_chars > 0 else ""
            current = (tail + "\n\n" + p).strip()
        else:
            # Very large single paragraph fallback
            start = 0
            while start < len(p):
                end = min(start + max_chars, len(p))
                windows.append(p[start:end])
                if end == len(p):
                    current = ""
                    break
                start = max(0, end - overlap_chars)

    if current:
        windows.append(current)

    return windows


def prepare_llm_payload(parsed: Dict[str, Any], max_chars_per_window: int = 12000) -> Dict[str, Any]:
    """
    Returns:
    - full_text: best single-document input for extraction
    - windows: fallback chunked inputs for long docs
    - metadata: lightweight metadata
    """
    full_text = reconstruct_full_text(parsed, keep_section_markers=True)
    windows = build_windows(full_text, max_chars=max_chars_per_window, overlap_chars=1200)

    return {
        "document_id": parsed.get("title") or "untitled-document",
        "source_type": parsed.get("source_type", "unknown"),
        "title": parsed.get("title") or "",
        "full_text": full_text,
        "windows": windows,
        "window_count": len(windows),
        "total_chunks_from_parser": parsed.get("total_chunks"),
    }


if __name__ == "__main__":
    # Example usage:
    # python prepare_llm_input.py parsed_test.json llm_payload.json
    import sys

    if len(sys.argv) < 3:
        print("Usage: python prepare_llm_input.py <input_parsed_json> <output_payload_json>")
        raise SystemExit(1)

    input_path = Path(sys.argv[1])
    output_path = Path(sys.argv[2])

    parsed_json = json.loads(input_path.read_text(encoding="utf-8"))
    payload = prepare_llm_payload(parsed_json)

    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved payload to: {output_path}")
    print(f"Full text chars: {len(payload['full_text'])}")
    print(f"Windows: {payload['window_count']}")