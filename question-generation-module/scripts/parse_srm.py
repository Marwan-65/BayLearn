"""
parse SRM Valliammai Engineering College question-bank PDFs.
note from pdfs : the end of the question is marked by a "BTL-X" token.

run command:
    python3 scripts/parse_srm.py
outputs:
    data/processed/srm_questions.csv
    data/processed/srm_parse_report.txt   (counts per file, dedup stats)
"""
from __future__ import annotations
import csv
import os
import re
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw_srm"
OUT_DIR = ROOT / "data" / "processed"
OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT_CSV = OUT_DIR / "srm_questions.csv"
REPORT = OUT_DIR / "srm_parse_report.txt"

BTL_TO_LEVEL = {1: "easy", 2: "easy", 3: "medium", 4: "medium", 5: "hard", 6: "hard"}
BTL_TO_COMPETENCE = {
    1: "Remembering", 2: "Understanding", 3: "Applying",
    4: "Analyzing",5: "Evaluating", 6: "Creating",
}

BTL_RE = re.compile(r"\bBTL[\s\-]?([1-6])\b", re.IGNORECASE)
# lines we always discard (sections with no questions)
NOISE_RE = re.compile(
    r"^(SRM\s+VALLIAMMAI|SRM\s+Nagar|DEPARTMENT\s+OF|QUESTION\s+BANK|"
    r"SUBJECT\s+CODE|SEM\s*/\s*YEAR|UNIT\s+[IVX]+|PART\s*[-–]?\s*[A-C]|"
    r"Q\.?\s*No|Questions?\b\s*$|BT\s*Level|Competence|"
    r"Page\s*\|?\s*\d+|From\s+SRM\s+VEC|\d+\s*$|"
    r"PART\s*[-–]?\s*[A-C]\b)",
    re.IGNORECASE,
)

# as if we have question part-b question , we split and start new buffer as there is new question
RESET_RE = re.compile(r"\bPART\s*[-–]?\s*[A-C]\b", re.IGNORECASE)
# here to get start of questions 
QNUM_RE = re.compile(
    r"^\s*\d{1,3}\s*[\.\)]?\s*"            # 1.  12)  12
    r"(?:\(\s*[ivxIVX]+\s*\)\s*\.?\s*)?"    # optional 1. (i).
)

# mark indicators like "(16)" "(8)" -> keep but don't split on
MARKS_RE = re.compile(r"\((?:8|16|2|4)\)")

# words on a BTL line, after the BTL token
COMPETENCE_WORDS = (
    "remembering|understanding|applying|analyzing|evaluating|creating|Designing"
    "remember|understand|apply|analyze|evaluate|create|design"
)

NAME_TO_BTL = {
    "remember": 1, "remembering": 1, "knowledge": 1, "recall": 1,
    "understand": 2, "understanding": 2, "comprehension": 2,
    "apply": 3, "applying": 3, "application": 3,
    "analyze": 4, "analyse": 4, "analyzing": 4, "analysing": 4, "analysis": 4,
    "evaluate": 5, "evaluating": 5, "evaluation": 5,
    "create": 6, "creating": 6, "synthesis": 6, "synthesise": 6, "synthesize": 6, "design": 6, "designing": 6,
}

COMPETENCE_RE = re.compile(rf"\b({COMPETENCE_WORDS})\b", re.IGNORECASE)


def pdftotext(path: Path) -> str:
    try:
        out = subprocess.run(
            ["pdftotext", "-layout", str(path), "-"],
            capture_output=True, text=True, timeout=60,
        )
        if out.returncode != 0:
            return ""
        return out.stdout
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return ""


def subject_from_filename(p: Path) -> str:
    return p.stem.replace("-", " ")


def normalize_question(question: str) -> str:
    question = QNUM_RE.sub("", question)
    question = re.sub(r"\s+", " ", question).strip().lower()
    question = MARKS_RE.sub("", question).strip()
    return question


def looks_like_question_start(line: str) -> bool:
    return bool(QNUM_RE.match(line))


def clean_question_text(buffer: list[str]) -> str:
    text = " ".join(buffer).strip() # if the question on multi lines, join them with space
    text = QNUM_RE.sub("", text, count=1).strip()
    text = re.sub(r"\s+", " ", text)
    # strip trailing column-header crumbs that sometimes leak in
    text = re.sub(r"\b(BTL[\s\-]?[1-6]|" + COMPETENCE_WORDS + r")\b.*$", "", text,
                flags=re.IGNORECASE).strip()
    # strip trailing "CO1" tags
    text = re.sub(r"\bCO\d\b\s*$", "", text, flags=re.IGNORECASE).strip()
    # strip trailing mark indicator if it ends the sentence
    text = re.sub(r"\(\s*\d{1,2}\s*\)\s*$", "", text).strip()
    return text


def is_quality_question(q: str) -> bool:
    if len(q) < 12:
        return False
    if len(q.split()) < 3:
        return False
    bad_starters = ("with ", "and ", "or ", "but ", "the impact", "diagram", "turbine")
    if any(q.lower().startswith(b) for b in bad_starters):
        return False
    return True


def parse_pdf(path: Path) -> list[dict]:
    """return list of dicts like {question, btl, competence, level, part, subject, source_file}"""
    text = pdftotext(path)
    if not text:
        return []
    rows: list[dict] = []
    buffer: list[str] = []
    current_part = "A"  
    for raw in text.splitlines():
        line = raw.rstrip()
        stripped = line.strip()
        if not stripped:
            # keep buffer if we haven't closed a question
            continue

        # track things like Part A any part boundary which is a hard reset for the accumulating buffer.
        m_part = re.search(r"\bPART\s*[-–]?\s*([A-C])\b", stripped, re.IGNORECASE)
        if m_part:
            current_part = m_part.group(1).upper()
            buffer = []
            continue

        # ignore pure-noise lines
        if NOISE_RE.match(stripped):
            buffer = []
            continue

        m_btl = BTL_RE.search(stripped)
        if m_btl:
            btl_num = int(m_btl.group(1))
            # Everything before the BTL marker on this line is still question text
            pre = stripped[: m_btl.start()].rstrip()
            if pre:
                buffer.append(pre)
            question = clean_question_text(buffer)
            buffer = []

            if not is_quality_question(question):
                continue  # bogus capture, skip

            competence = BTL_TO_COMPETENCE[btl_num]
            

            rows.append({
                "question": question,
                "btl": btl_num,
                "competence": competence,
                "level": BTL_TO_LEVEL[btl_num],
                "part": current_part,
                "source_file": path.name,
            })
            continue

        # otherwise: If it looks like a new question start while the buffer is non-empty,
        # the previous one was probably has(no BTL marker found) so drop the orphan (as it has no bloom level)and start fresh.
        if looks_like_question_start(stripped) and buffer:
            buffer = []
        buffer.append(stripped)

    return rows


def main() -> int:
    if not RAW_DIR.exists():
        print(f"{RAW_DIR} does not exist", file=sys.stderr)
        return 1

    pdfs = sorted(RAW_DIR.glob("*.pdf"))
    if not pdfs:
        print(f"no PDF in {RAW_DIR}", file=sys.stderr)
        return 1

    all_rows: list[dict] = []
    per_file_counts: dict[str, int] = {}
    failed: list[str] = []

    for i, pdf in enumerate(pdfs, 1):
        try:
            rows = parse_pdf(pdf)
        except Exception as e:  
            print(f"  [{i}/{len(pdfs)}] {pdf.name}: error {e}", file=sys.stderr)
            failed.append(pdf.name)
            continue
        per_file_counts[pdf.name] = len(rows)
        all_rows.extend(rows)
        if i % 25 == 0 or i == len(pdfs):
            print(f"  [{i}/{len(pdfs)}] cumulative rows: {len(all_rows)}")

    # deduplicate by normalized question text 
    seen: dict[str, dict] = {}
    duplicate_count = 0
    for row in all_rows:
        key = normalize_question(r["question"])
        if not key:
            continue
        if key in seen:
            duplicate_count += 1
            continue
        seen[key] = row

    deduped = list(seen.values())


    fieldnames = ["question", "level", "btl", "competence", "part", "subject", "source_file"]
    with OUT_CSV.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in deduped:
            w.writerow({k: r[k] for k in fieldnames})

    #  report 
    level_counts = Counter(r["level"] for r in deduped)
    btl_counts = Counter(r["btl"] for r in deduped)
    subject_counts = Counter(r["subject"] for r in deduped)

    lines = []
    lines.append(f"SRM Question Bank parse report")
    lines.append(f"==============================")
    lines.append(f"PDFs scanned:        {len(pdfs)}")
    lines.append(f"PDFs failed:         {len(failed)}")
    if failed:
        lines.append("  failed list:")
        for n in failed:
            lines.append(f"    - {n}")
    lines.append(f"Rows extracted:      {len(all_rows)}")
    lines.append(f"Rows after dedup:    {len(deduped)}")
    lines.append("")
    lines.append("Level distribution (3-bucket):")
    for lvl in ("easy", "medium", "hard"):
        pct = 100.0 * level_counts[lvl] / max(1, len(deduped))
        lines.append(f"  {lvl:<6}  {level_counts[lvl]:>6}   ({pct:5.1f}%)")
    lines.append("")
    lines.append("Bloom level (6-class):")
    for btl in range(1, 7):
        pct = 100.0 * btl_counts[btl] / max(1, len(deduped))
        lines.append(f"  BTL-{btl}  {btl_counts[btl]:>6}   ({pct:5.1f}%)")
    lines.append("")
    lines.append(f"Top 15 subjects by row count:")
    for subj, n in subject_counts.most_common(15):
        lines.append(f"  {n:>5}  {subj}")
    lines.append("")
    lines.append(f"Output: {OUT_CSV}")

    REPORT.write_text("\n".join(lines))
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
