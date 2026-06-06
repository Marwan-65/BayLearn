"""we split the file into blocks at numbered headers, then extract the four fields
from each block. 

run command:
    python3 scripts/parse_os.py "/path/to/QuestionBank.md"
"""
from __future__ import annotations
import csv
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_CSV = ROOT / "data" / "processed" / "os.csv"
OUT_CSV.parent.mkdir(parents=True, exist_ok=True)

# we split the file at every such header. Use lookbehind for start-of-line.
QUESTION_HEADER_RE = re.compile(
    # accept "1.", "1-", "1)", "1\."
    r"(?m)^\s*\*{0,2}\s*(\d{1,3})\s*[\.\-\\\)]+\s*"
)


# if there is inline image: ![alt](url) and reference-style: ![alt][ref]
# we keep the full markdown image syntax in the question text so a downstream
# consumer can see "this question references a diagram." We never drop them.
IMAGE_RE = re.compile(r"!\[[^\]]*\](?:\([^)]+\)|\[[^\]]+\])")


def has_image(text: str) -> bool:
    return bool(IMAGE_RE.search(text))


def strip_markdown(text: str) -> str:
    text = re.sub(r"\\([\.\-\\\[\]\(\)])", r"\1", text)   # \\. -> .
    text = re.sub(r"\*{1,2}", "", text)                    # drop ** wrappers
    text = re.sub(r"\s+", " ", text).strip()
    return text

_LEADING_NUM_HEADER = re.compile(r"^\s*\*{0,2}\s*\d{1,3}\s*[\.\-\\\)]+\s*")

def extract_question(block: str) -> str:
    q = _LEADING_NUM_HEADER.sub("", block, count=1)
    return strip_markdown(q)


def parse_md(md_path: Path) -> list[dict]:
    text = md_path.read_text(encoding="utf-8")
    # capture both position and question number for each header
    matches = list(QUESTION_HEADER_RE.finditer(text))
    if not matches:
        return []
    starts: list[tuple[int, int | None]] = [
        (m.start(), int(m.group(1))) for m in matches
    ]
    starts.append((len(text), None))

    # build raw blocks: each block carries its own header number
    raw_blocks: list[tuple[int | None, str]] = [
        (starts[i][1], text[starts[i][0]:starts[i + 1][0]])
        for i in range(len(starts) - 1)
    ]
    
    # if a block's number is small and smaller than the last real question's number, 
    # it's treated as an option and merged into the parent.
    merged: list[str] = []
    last_real_num: int = -1
    min_mcq_option_num = 5
    for num, block in raw_blocks:
        is_mcq_option = ( num is not None and num <= min_mcq_option_num 
        and last_real_num > 0 and num < last_real_num)
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
        if not question or len(question) < 8 or len(question.split()) < 3:
            continue
        rows.append({
            "question":       question,
            "level":          "",                  # filled by BloomBERT later
            "has_image":      has_image(question),
            "source_file":    md_path.name,})
    return rows


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("run command is like python3 scripts/parse_os.py <path/to/QuestionBank.md>",
            file=sys.stderr)
        return 1
    src = Path(argv[1]).expanduser()
    if not src.exists():
        print(f"file not found: {src}", file=sys.stderr)
        return 1

    rows = parse_md(src)
    field_names = ["question", "level", "has_image", "source_file"]
    with OUT_CSV.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=field_names)
        w.writeheader()
        for r in rows:
            w.writerow(r)

    print(f"parsed {len(rows)} questions from {src.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
