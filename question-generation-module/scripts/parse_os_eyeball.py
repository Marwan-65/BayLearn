"""
Parse the hand-curated OS question bank (markdown) into a CSV row per question.

The .md file uses multiple ad-hoc formats:
    1- Question text
    **14. Question text (GATE CS 2000)**
    **15\\. Question text**

Each block contains:
    Answer : <text>        OR  **Solution:** Correct answer is (**X**)
    Level  : <easy|medium|hard>
    (optional) Why ? <explanation>  OR  **Explanation:** <text>

We split the file into blocks at numbered headers, then extract the four fields
from each block. Output schema matches srm_questions.csv plus answer/explanation.

Run:
    python3 scripts/parse_os_eyeball.py /path/to/QuestionBank.md
"""
from __future__ import annotations
import csv
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_CSV = ROOT / "data" / "processed" / "os_eyeball.csv"
OUT_CSV.parent.mkdir(parents=True, exist_ok=True)

# A question header looks like:  "1- ", "1. ", "**14. ", "**15\. ", etc.
# We split the file at every such header. Use lookbehind for start-of-line.
QUESTION_HEADER_RE = re.compile(
    # Accept "1.", "1-", "1)", "1\.", with optional ** wrappers and optional
    # whitespace after the separator (later questions in the .md have no space).
    r"(?m)^\s*\*{0,2}\s*(\d{1,3})\s*[\.\-\\\)]+\s*"
)

ANSWER_PATTERNS = [
    re.compile(r"\*{0,2}Solution\*{0,2}\s*:\s*(.+?)(?=\n|$)", re.IGNORECASE),
    re.compile(r"\bAnswer\s*:\s*(.+?)(?=\n|$)", re.IGNORECASE),
]
LEVEL_RE = re.compile(r"\bLevel\s*:\s*(easy|medium|hard)\b", re.IGNORECASE)
EXPLANATION_PATTERNS = [
    re.compile(r"\*{0,2}Explanation\*{0,2}\s*:\s*(.+?)(?=\n\*{2}|\n\n|\Z)",
               re.IGNORECASE | re.DOTALL),
    re.compile(r"\bWhy\s*\?\s*(.+?)(?=\n\n|\Z)", re.IGNORECASE | re.DOTALL),
]


# Inline image: ![alt](url) — and reference-style: ![alt][ref]
# We keep the full markdown image syntax in the question text so a downstream
# consumer can see "this question references a diagram." We never drop them.
IMAGE_RE = re.compile(r"!\[[^\]]*\](?:\([^)]+\)|\[[^\]]+\])")


def has_image(text: str) -> bool:
    return bool(IMAGE_RE.search(text))


def strip_markdown(text: str) -> str:
    """Light markdown cleanup — remove **, unescape backslash-escaped chars,
    collapse spaces. Image references (![…](…) or ![…][ref]) are PRESERVED
    so that questions with diagrams retain that marker.
    """
    text = re.sub(r"\\([\.\-\\\[\]\(\)])", r"\1", text)   # \\. → .
    text = re.sub(r"\*{1,2}", "", text)                    # drop ** wrappers
    text = re.sub(r"\s+", " ", text).strip()
    return text


_LEADING_NUM_HEADER = re.compile(r"^\s*\*{0,2}\s*\d{1,3}\s*[\.\-\\\)]+\s*")


def extract_question(block: str) -> str:
    """Question = everything from after the leading number header to the
    first Answer/Solution marker (if any), else the whole block."""
    # Find earliest answer marker (none in the new format — full block is question)
    earliest = len(block)
    for pat in ANSWER_PATTERNS:
        m = pat.search(block)
        if m and m.start() < earliest:
            earliest = m.start()
    q = block[:earliest]
    # Strip the question's own leading number ("1- ", "10 \- ", "**14. ", etc.)
    q = _LEADING_NUM_HEADER.sub("", q, count=1)
    return strip_markdown(q)


def extract_answer(block: str) -> str:
    for pat in ANSWER_PATTERNS:
        m = pat.search(block)
        if m:
            return strip_markdown(m.group(1))
    return ""


def extract_level(block: str) -> str:
    m = LEVEL_RE.search(block)
    return m.group(1).lower() if m else ""


def extract_explanation(block: str) -> str:
    for pat in EXPLANATION_PATTERNS:
        m = pat.search(block)
        if m:
            return strip_markdown(m.group(1))[:500]
    return ""


def _has_answer_or_level(block: str) -> bool:
    """A real question block contains at least Answer/Solution OR Level."""
    if LEVEL_RE.search(block):
        return True
    for pat in ANSWER_PATTERNS:
        if pat.search(block):
            return True
    return False


def parse_md(md_path: Path) -> list[dict]:
    text = md_path.read_text(encoding="utf-8")
    # Capture both position AND question number for each header
    matches = list(QUESTION_HEADER_RE.finditer(text))
    if not matches:
        return []
    starts: list[tuple[int, int | None]] = [
        (m.start(), int(m.group(1))) for m in matches
    ]
    starts.append((len(text), None))

    # Build raw blocks: each block carries its own header number
    raw_blocks: list[tuple[int | None, str]] = [
        (starts[i][1], text[starts[i][0]:starts[i + 1][0]])
        for i in range(len(starts) - 1)
    ]

    # Merge MCQ sub-options into their parent question.
    #
    # Updated format: MCQ options now use letters (a-, b-, ..., e-) which
    # don't match the numeric question-header regex, so they're naturally
    # part of the parent question's text — no special merging required.
    #
    # We still defensively keep the numeric MCQ-option safety net for the
    # OLD format (where options used "1-", "2-", "5-"): if a block's number
    # is small (<=10) AND smaller than the last real question's number, it's
    # treated as an option and merged into the parent.
    merged: list[str] = []
    last_real_num: int = -1
    for num, block in raw_blocks:
        is_mcq_option = (
            num is not None
            and num <= 10
            and last_real_num > 0
            and num < last_real_num
        )
        if is_mcq_option:
            if merged:
                merged[-1] = merged[-1] + "\n" + block
            continue
        merged.append(block)
        if num is not None:
            last_real_num = num

    rows = []
    for block in merged:
        question = extract_question(block)
        answer = extract_answer(block)
        level = extract_level(block)              # may be "" — no longer required
        explanation = extract_explanation(block)
        if not question or len(question) < 8 or len(question.split()) < 3:
            continue
        # The OS bank is now PURELY test input — never trained on, never used
        # as ICL bank source. The `level` column is left blank so BloomBERT can
        # fill it via scripts/relabel_os_with_bloombert.py.
        rows.append({
            "question":       question,
            "level":          "",                  # filled by BloomBERT later
            "has_image":      has_image(question),
            "subject":        "operating systems",
            "source_file":    md_path.name,
            "correct_answer": answer,
            "explanation":    explanation,
        })
    return rows


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("Usage: python3 scripts/parse_os_eyeball.py <path/to/QuestionBank.md>",
              file=sys.stderr)
        return 1
    src = Path(argv[1]).expanduser()
    if not src.exists():
        print(f"ERROR: file not found: {src}", file=sys.stderr)
        return 1

    rows = parse_md(src)
    fieldnames = ["question", "level", "has_image", "subject", "source_file",
                  "correct_answer", "explanation"]
    with OUT_CSV.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow(r)

    # Report
    n_with_img = sum(1 for r in rows if r["has_image"])
    missing_ans = sum(1 for r in rows if not r["correct_answer"])
    print(f"Parsed {len(rows)} questions from {src.name}")
    print(f"  questions with image references: {n_with_img}")
    print(f"  questions missing answer field:  {missing_ans}")
    print(f"Output: {OUT_CSV}")
    print(f"NOTE: 'level' column is blank by design — run "
          "scripts/relabel_os_with_bloombert.py to fill it from BloomBERT.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
