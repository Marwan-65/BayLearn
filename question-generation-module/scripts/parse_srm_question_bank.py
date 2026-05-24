"""
Parse SRM Valliammai Engineering College question-bank PDFs into a labeled CSV.

Each PDF has questions in a table with columns (in varying order):
    Q.No | Question | Competence | BT Level    (or)
    Q.No | Question | BT Level   | Competence

The unambiguous anchor is the marker `BTL-N` (N=1..6). We scan line-by-line,
accumulate question text into a buffer, and emit a row each time a BTL-N
marker closes a question.

Maps:
    BTL-1 (Remember)   → easy
    BTL-2 (Understand) → easy
    BTL-3 (Apply)      → medium
    BTL-4 (Analyze)    → medium
    BTL-5 (Evaluate)   → hard
    BTL-6 (Create)     → hard

Run:
    python3 scripts/parse_srm_question_bank.py
Outputs:
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

# ---- Bloom mapping ----------------------------------------------------------
BTL_TO_LEVEL = {1: "easy", 2: "easy", 3: "medium", 4: "medium", 5: "hard", 6: "hard"}
BTL_TO_COMPETENCE = {
    1: "Remember", 2: "Understand", 3: "Apply",
    4: "Analyze", 5: "Evaluate", 6: "Create",
}

# ---- Regexes ----------------------------------------------------------------
BTL_RE = re.compile(r"\bBTL[\s\-]?([1-6])\b", re.IGNORECASE)
# Lines we always discard (headers / boilerplate)
NOISE_RE = re.compile(
    r"^(SRM\s+VALLIAMMAI|SRM\s+Nagar|DEPARTMENT\s+OF|QUESTION\s+BANK|"
    r"SUBJECT\s+CODE|SEM\s*/\s*YEAR|UNIT\s+[IVX]+|PART\s*[-–]?\s*[A-C]|"
    r"Q\.?\s*No|Questions?\b\s*$|BT\s*Level|Competence|"
    r"Page\s*\|?\s*\d+|From\s+SRM\s+VEC|\d+\s*$|"
    r"PART\s*[-–]?\s*[A-C]\b)",
    re.IGNORECASE,
)
# Strong reset markers — any line containing these aborts the current buffer.
RESET_RE = re.compile(r"\bPART\s*[-–]?\s*[A-C]\b", re.IGNORECASE)
# Question number prefix like "1.", "12.", "12)", "12", "12.(i).", "12 (i)"
# Also strips the optional roman-numeral sub-part marker.
QNUM_RE = re.compile(
    r"^\s*\d{1,3}\s*[\.\)]?\s*"            # 1.  12)  12
    r"(?:\(\s*[ivxIVX]+\s*\)\s*\.?\s*)?"    # optional (i).
)
# Mark indicators like "(16)" "(8)" - keep but don't split on
MARKS_RE = re.compile(r"\((?:8|16|2|4)\)")
# Competence words on a BTL line, after the BTL token
COMP_WORDS = (
    "remembering|understanding|applying|analyzing|evaluating|creating|"
    "remember|understand|apply|analyze|evaluate|create"
)
COMP_RE = re.compile(rf"\b({COMP_WORDS})\b", re.IGNORECASE)


def pdftotext(path: Path) -> str:
    """Run `pdftotext -layout` and return the text. Empty string on failure."""
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


def normalize_question(q: str) -> str:
    """For dedup: lowercase, collapse whitespace, strip leading numbering."""
    q = QNUM_RE.sub("", q)
    q = re.sub(r"\s+", " ", q).strip().lower()
    # remove trailing mark indicators
    q = MARKS_RE.sub("", q).strip()
    return q


def looks_like_question_start(line: str) -> bool:
    """Does this line look like the beginning of a new question?"""
    return bool(QNUM_RE.match(line))


def clean_question_text(buffer: list[str]) -> str:
    text = " ".join(buffer).strip()
    text = QNUM_RE.sub("", text, count=1).strip()
    text = re.sub(r"\s+", " ", text)
    # strip trailing column-header crumbs that sometimes leak in
    text = re.sub(r"\b(BTL[\s\-]?[1-6]|" + COMP_WORDS + r")\b.*$", "", text,
                  flags=re.IGNORECASE).strip()
    # strip trailing "CO1".."CO9" course-outcome tags
    text = re.sub(r"\bCO\d\b\s*$", "", text, flags=re.IGNORECASE).strip()
    # strip trailing mark indicator if it ends the sentence
    text = re.sub(r"\(\s*\d{1,2}\s*\)\s*$", "", text).strip()
    return text


def is_quality_question(q: str) -> bool:
    """Reject obviously broken/truncated captures."""
    if len(q) < 12:
        return False
    if len(q.split()) < 3:
        return False
    # Must start with a capital letter or an interrogative
    first = q.lstrip("(").lstrip()[:1]
    if first and not first.isupper():
        return False
    # Reject fragments that look like continuations
    bad_starters = ("with ", "and ", "or ", "but ", "the impact", "diagram.", "turbine.")
    if any(q.lower().startswith(b) for b in bad_starters):
        return False
    return True


def parse_pdf(path: Path) -> list[dict]:
    """Return list of dicts: {question, btl, competence, level, part, subject, source_file}."""
    text = pdftotext(path)
    if not text:
        return []

    subject = subject_from_filename(path)
    rows: list[dict] = []
    buffer: list[str] = []
    current_part = "A"  # default

    for raw in text.splitlines():
        line = raw.rstrip()
        stripped = line.strip()
        if not stripped:
            # blank line — soft boundary; keep buffer if we haven't closed a question
            continue

        # Track Part A / Part B / Part C sections; any PART boundary
        # is a hard reset for the accumulating buffer.
        m_part = re.search(r"\bPART\s*[-–]?\s*([A-C])\b", stripped, re.IGNORECASE)
        if m_part:
            current_part = m_part.group(1).upper()
            buffer = []
            continue

        # Discard pure-noise lines
        if NOISE_RE.match(stripped):
            buffer = []
            continue

        # Does this line contain a BTL marker? That CLOSES the current question.
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

            # The BTL number is the ground-truth Bloom signal in this dataset.
            # We use it to derive competence rather than parsing the (sometimes
            # misaligned) competence word from the line.
            competence = BTL_TO_COMPETENCE[btl_num]

            rows.append({
                "question": question,
                "btl": btl_num,
                "competence": competence,
                "level": BTL_TO_LEVEL[btl_num],
                "part": current_part,
                "subject": subject,
                "source_file": path.name,
            })
            continue

        # Otherwise: this is question text. If it looks like a new question start
        # while the buffer is non-empty, the previous one was probably orphaned
        # (no BTL marker found). Drop the orphan and start fresh.
        if looks_like_question_start(stripped) and buffer:
            buffer = []
        buffer.append(stripped)

    return rows


def main() -> int:
    if not RAW_DIR.exists():
        print(f"ERROR: {RAW_DIR} does not exist", file=sys.stderr)
        return 1

    pdfs = sorted(RAW_DIR.glob("*.pdf"))
    if not pdfs:
        print(f"ERROR: no PDFs in {RAW_DIR}", file=sys.stderr)
        return 1

    all_rows: list[dict] = []
    per_file_counts: dict[str, int] = {}
    failed: list[str] = []

    print(f"Parsing {len(pdfs)} PDFs from {RAW_DIR}...")
    for i, pdf in enumerate(pdfs, 1):
        try:
            rows = parse_pdf(pdf)
        except Exception as e:  # one bad PDF should not kill the whole run
            print(f"  [{i}/{len(pdfs)}] {pdf.name}: ERROR {e}", file=sys.stderr)
            failed.append(pdf.name)
            continue
        per_file_counts[pdf.name] = len(rows)
        all_rows.extend(rows)
        if i % 25 == 0 or i == len(pdfs):
            print(f"  [{i}/{len(pdfs)}] cumulative rows: {len(all_rows)}")

    # ---- Deduplicate by normalized question text -----------------------------
    seen: dict[str, dict] = {}
    dup_count = 0
    for r in all_rows:
        key = normalize_question(r["question"])
        if not key:
            continue
        if key in seen:
            dup_count += 1
            # If the duplicate has a different level, keep the harder one
            # (Part-B 16-mark version of the same question)
            order = {"easy": 0, "medium": 1, "hard": 2}
            if order[r["level"]] > order[seen[key]["level"]]:
                seen[key] = r
            continue
        seen[key] = r

    deduped = list(seen.values())

    # ---- Write CSV -----------------------------------------------------------
    fieldnames = ["question", "level", "btl", "competence", "part", "subject", "source_file"]
    with OUT_CSV.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in deduped:
            w.writerow({k: r[k] for k in fieldnames})

    # ---- Report --------------------------------------------------------------
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
    lines.append(f"Duplicates removed:  {dup_count}")
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
