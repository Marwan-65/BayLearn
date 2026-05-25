"""
Build the few-shot example bank from labeled CSV sources.

The bank's purpose: give the LLM Bloom-level-tagged example questions for
in-context learning. Examples MUST have a `level` (easy/medium/hard).
Answers and explanations are optional (the LLM imitates question style/depth
for level transfer; answer format is enforced separately by the prompt's
OUTPUT FORMAT block).

ADDING A NEW SOURCE
===================
The bank pulls from any number of CSV sources registered in the SOURCES list
below. To add a new dataset:

    1. Drop your labeled CSV anywhere under data/processed/ (relative paths)
       or use an absolute path.
    2. Append a config dict to SOURCES with at minimum:
         { "name": "<short-id>", "path": "<csv-filename>",
           "question_col": "<col>", "level_col": "<col>" }
       Optional fields: `subject_col`, `answer_col`, `explanation_col`,
       `subject_filter` (set of subject names to keep — None means keep all).
    3. Re-run: python scripts/build_example_bank.py

No code changes needed beyond appending to SOURCES.

NOTE: This bank is fed by sources that have CANONICAL Bloom labels (from
educators or the trained classifier). The OS test bank (hand-curated + your
test questions) is NEVER pulled in here — it's used downstream as evaluation
input, not training material for the bank.

Run:
    python scripts/build_example_bank.py
    python scripts/build_example_bank.py --per-level 100   # bigger bank
    python scripts/build_example_bank.py --require-answer   # only Q+A entries
"""
from __future__ import annotations

import argparse
import csv
import json
import random
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROC = ROOT / "data" / "processed"
OUT_JSONL = PROC / "example_bank.jsonl"

# Increase Python's CSV field-size limit — SRM rows can be long
csv.field_size_limit(sys.maxsize)

# ============================================================================
# SOURCE REGISTRY — add new banks by appending a config dict here.
# ============================================================================
# Each config describes ONE CSV file and how to read it.
#
# Required keys:
#   name           short identifier ("srm", "my_bank", etc.)
#   path           file path (relative to data/processed/, or absolute)
#   question_col   column name for the question text
#   level_col      column name for easy/medium/hard label
#
# Optional keys:
#   subject_col       column for subject/topic (used for `concept` + filtering)
#   answer_col        column for correct_answer (default: no answer)
#   explanation_col   column for explanation/why (default: no explanation)
#   subject_filter    set of allowed subject names (lowercased). If None,
#                     keep all subjects.
#
SOURCES: list[dict] = [
    {
        "name":            "srm",
        "path":            "srm_questions.csv",
        "question_col":    "question",
        "level_col":       "level",
        "subject_col":     "subject",
        "answer_col":      None,            # SRM ships no answers
        "explanation_col": None,
        "subject_filter":  None,            # None = use ALL SRM subjects (~30k)
    },
    # Example of how you'd add another source later:
    # {
    #     "name":            "my_extra_bank",
    #     "path":            "my_extra_questions.csv",
    #     "question_col":    "Question",
    #     "level_col":       "Difficulty",
    #     "subject_col":     "Topic",
    #     "answer_col":      "Answer",
    #     "explanation_col": "Why",
    #     "subject_filter":  None,
    # },
]


# ----------------------------------------------------------------- utilities
_LEADING_NUM_RE = re.compile(r"^\s*\d{1,3}\s*[\.\-\)\\]+\s*")


def strip_leading_number(q: str) -> str:
    """Remove '1- ', '12. ', '5) ', '7\\. ' style prefixes."""
    return _LEADING_NUM_RE.sub("", q).strip()


def is_quality_question(q: str) -> bool:
    q = strip_leading_number(q)
    if not q or len(q) < 12 or len(q.split()) < 3:
        return False
    if not q[:1].isupper() and not q.startswith("("):
        return False
    return True


# ---------------------------------------------------------- generic loader
def load_source(cfg: dict) -> list[dict]:
    """Read one source CSV per its config; return normalized row dicts."""
    raw_path = cfg.get("path")
    if not raw_path:
        print(f"  [skip] source {cfg.get('name')} has no 'path'")
        return []
    path = Path(raw_path)
    if not path.is_absolute():
        path = PROC / raw_path
    if not path.exists():
        print(f"  [skip] {cfg['name']}: file not found at {path}")
        return []

    q_col = cfg["question_col"]
    l_col = cfg["level_col"]
    s_col = cfg.get("subject_col")
    a_col = cfg.get("answer_col")
    e_col = cfg.get("explanation_col")
    subj_filter = cfg.get("subject_filter")
    if subj_filter is not None:
        subj_filter = {s.lower().strip() for s in subj_filter}

    rows: list[dict] = []
    skipped_level   = 0
    skipped_quality = 0
    skipped_subject = 0
    with path.open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            level = (r.get(l_col) or "").lower().strip()
            if level not in {"easy", "medium", "hard"}:
                skipped_level += 1
                continue
            question = r.get(q_col) or ""
            if not is_quality_question(question):
                skipped_quality += 1
                continue
            subject = ""
            if s_col:
                subject = (r.get(s_col) or "").strip().lower()
                if subj_filter and subject not in subj_filter:
                    skipped_subject += 1
                    continue
            rows.append({
                "question":       strip_leading_number(question),
                "concept":        subject or cfg["name"],
                "level":          level,
                "question_type":  "short_answer",
                "correct_answer": r.get(a_col, "") if a_col else "",
                "explanation":    r.get(e_col, "") if e_col else "",
                "subject":        subject or cfg["name"],
                "source":         cfg["name"],
            })
    summary = f"  loaded {len(rows):>6} from {cfg['name']:<20} ({path.name})"
    if skipped_level + skipped_quality + skipped_subject > 0:
        summary += (f"  [skipped: level={skipped_level} "
                    f"quality={skipped_quality} subject={skipped_subject}]")
    print(summary)
    return rows


def sample_balanced(rows: list[dict], per_level: int, seed: int = 42) -> list[dict]:
    rng = random.Random(seed)
    by_level: dict[str, list[dict]] = {"easy": [], "medium": [], "hard": []}
    for r in rows:
        by_level[r["level"]].append(r)
    sampled = []
    for lvl, items in by_level.items():
        # Prefer entries that have answers and explanations (richer few-shot)
        items.sort(key=lambda r: (
            -bool(r.get("correct_answer")),
            -bool(r.get("explanation")),
            rng.random(),
        ))
        sampled.extend(items[:per_level])
    return sampled


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-level", type=int, default=50,
                    help="examples per level (default: 50 → 150 total)")
    ap.add_argument("--require-answer", action="store_true",
                    help="Filter to examples that ship an explicit correct_answer. "
                         "Default OFF: include question-only examples too. "
                         "(The prompt's OUTPUT FORMAT spec enforces answer "
                         "structure separately, so examples don't need answers "
                         "to teach Bloom level.)")
    args = ap.parse_args()

    print("Loading sources from SOURCES registry...")
    all_rows: list[dict] = []
    for cfg in SOURCES:
        all_rows.extend(load_source(cfg))
    if not all_rows:
        print("ERROR: no rows loaded. Check SOURCES paths and column names.",
              file=sys.stderr)
        return 1

    # Dedupe by normalized question text
    seen: dict[str, dict] = {}
    for r in all_rows:
        key = r["question"].lower().strip()
        if key in seen:
            # If duplicate, prefer the entry that has an answer
            if not seen[key].get("correct_answer") and r.get("correct_answer"):
                seen[key] = r
            continue
        seen[key] = r
    pool = list(seen.values())
    print(f"  pool after dedupe: {len(pool)}")

    if args.require_answer:
        before = len(pool)
        pool = [r for r in pool if r.get("correct_answer")]
        print(f"  filtered to entries WITH answers: {len(pool)}/{before} "
              f"(--require-answer was passed)")
    else:
        print(f"  using all entries regardless of answer presence")

    sampled = sample_balanced(pool, per_level=args.per_level)
    print(f"  sampled {len(sampled)} (per_level={args.per_level})")
    if len(sampled) < 3 * args.per_level:
        print(f"  WARNING: per_level={args.per_level} requested but pool was too small "
              f"for one or more levels. Consider lowering per_level or "
              f"--require-answer.")

    # Write JSONL (embeddings filled lazily by ExampleBank at FastAPI startup)
    with OUT_JSONL.open("w", encoding="utf-8") as f:
        for r in sampled:
            f.write(json.dumps({
                "question":       r["question"],
                "concept":        r["concept"],
                "level":          r["level"],
                "question_type":  r["question_type"],
                "correct_answer": r.get("correct_answer", ""),
                "explanation":    r.get("explanation", ""),
                "subject":        r["subject"],
            }, ensure_ascii=False) + "\n")
    print(f"\nWrote {OUT_JSONL}")

    from collections import Counter
    lvl = Counter(r["level"] for r in sampled)
    typ = Counter(r["question_type"] for r in sampled)
    src = Counter(r["source"] for r in sampled)
    print(f"  by level:  {dict(lvl)}")
    print(f"  by type:   {dict(typ)}")
    print(f"  by source: {dict(src)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
