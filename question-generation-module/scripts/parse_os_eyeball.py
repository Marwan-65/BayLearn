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


def strip_markdown(text: str) -> str:
    """Light markdown cleanup — remove **, escape backslashes, collapse spaces."""
    text = re.sub(r"\\([\.\-\\\[\]\(\)])", r"\1", text)  # \\. → .
    text = re.sub(r"\*{1,2}", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def extract_question(block: str) -> str:
    """Question = everything before the first Answer/Solution marker."""
    # Find earliest answer marker
    earliest = len(block)
    for pat in ANSWER_PATTERNS:
        m = pat.search(block)
        if m and m.start() < earliest:
            earliest = m.start()
    q = block[:earliest]
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
    # Find all numbered-header positions
    starts = [m.start() for m in QUESTION_HEADER_RE.finditer(text)]
    if not starts:
        return []
    starts.append(len(text))

    # Build raw blocks
    raw_blocks = [text[starts[i]:starts[i + 1]] for i in range(len(starts) - 1)]

    # Merge blocks that don't contain Answer/Solution/Level into the previous
    # real question block — these are MCQ sub-options ("1- ...", "2- ...").
    merged: list[str] = []
    for block in raw_blocks:
        if _has_answer_or_level(block) or not merged:
            merged.append(block)
        else:
            merged[-1] = merged[-1] + "\n" + block

    rows = []
    for block in merged:
        question = extract_question(block)
        answer = extract_answer(block)
        level = extract_level(block)
        explanation = extract_explanation(block)
        if not question or len(question) < 8:
            continue
        if not (answer or level):
            continue  # not a real question after merging
        rows.append({
            "question": question,
            "level": level or "unknown",
            "btl": "",  # unknown — to be filled by BloomBERT later
            "competence": "",
            "part": "",
            "subject": "operating systems (eyeball)",
            "source_file": md_path.name,
            "correct_answer": answer,
            "explanation": explanation,
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
    fieldnames = ["question", "level", "btl", "competence", "part",
                  "subject", "source_file", "correct_answer", "explanation"]
    with OUT_CSV.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow(r)

    # Report
    from collections import Counter
    level_counts = Counter(r["level"] for r in rows)
    print(f"Parsed {len(rows)} questions from {src.name}")
    print(f"Level distribution:")
    for lvl in ("easy", "medium", "hard", "unknown"):
        print(f"  {lvl:<8} {level_counts.get(lvl, 0)}")
    missing_ans = sum(1 for r in rows if not r["correct_answer"])
    print(f"Missing answer field: {missing_ans}")
    print(f"Output: {OUT_CSV}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
