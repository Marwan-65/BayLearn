"""
The bank's purpose: give the LLM Bloom-level-tagged example questions for
in-context learning. Examples MUST have a `level` (easy/medium/hard).
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

Run:
    python scripts/build_example_bank.py
    python scripts/build_example_bank.py --per-level 100   # bigger bank
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

# SRM rows are long so we increased the default csv field size limit to avoid errors.
csv.field_size_limit(sys.maxsize)

# SOURCE REGISTRY — add new banks by appending a config dict here.
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
SOURCES: list[dict] = [
    {
        "name":            "srm",
        "path":            "srm_questions.csv",
        "question_col":    "question",
        "level_col":       "level",
    },
    {
        "name":            "os_bank",
        "path":            "os_bloombert_labeled.csv",
        "question_col":    "question",
        "level_col":       "level",
    },
]


# utilities
_LEADING_NUM_RE = re.compile(r"^\s*\d{1,3}\s*[\.\-\)\\]+\s*")

def strip_leading_number(q: str) -> str:
    """Remove leading prefixes in questions """
    return _LEADING_NUM_RE.sub("", q).strip()

def is_quality_question(q: str) -> bool:
    q = strip_leading_number(q)
    if not q or len(q) < 12 or len(q.split()) < 3:
        return False
    if not q[:1].isupper() and not q.startswith("("):
        return False
    return True

def load_source(config: dict) -> list[dict]:
    """read the csv source in config dictionary and return it with normalized keys"""
    raw_path = config.get("path")
    if not raw_path:
        print(f"skip this source {config.get('name')} as it has no 'path'")
        return []
    path = Path(raw_path)
    if not path.is_absolute():
        path = PROC / raw_path
    if not path.exists():
        print(f"skip {config['name']}: file not found at {path}")
        return []

    q_col = config["question_col"]
    l_col = config["level_col"]

    rows: list[dict] = []
    skipped_level   = 0
    skipped_quality = 0
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
            rows.append({
                "question":       strip_leading_number(question),
                "level":          level,
                "source":         config["name"],
            })
    summary = f"  loaded {len(rows):>6} from {config['name']:<20} ({path.name})"
    if skipped_level + skipped_quality > 0:
        summary += (f"  [skipped: level={skipped_level} "
                    f"quality={skipped_quality}]")
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


def sample_per_source_per_level(rows: list[dict], n_per_cell: int,
                                seed: int = 42) -> list[dict]:
    """Source × level stratified sampling.

    Guarantees each (source, level) cell contributes up to `n_per_cell`
    entries (or all of them if the cell has fewer than n_per_cell). Use this
    when one source dwarfs the others by volume and you want balanced
    representation.
    """
    rng = random.Random(seed)
    by_cell: dict[tuple[str, str], list[dict]] = {}
    for r in rows:
        key = (r["source"], r["level"])
        by_cell.setdefault(key, []).append(r)
    sampled = []
    for (src, lvl), items in sorted(by_cell.items()):
        items.sort(key=lambda r: (
            -bool(r.get("correct_answer")),
            -bool(r.get("explanation")),
            rng.random(),
        ))
        kept = items[:n_per_cell]
        sampled.extend(kept)
        if len(kept) < n_per_cell:
            print(f"    [warn] source={src!r} level={lvl!r}: only "
                  f"{len(kept)}/{n_per_cell} available")
    return sampled


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-level", type=int, default=50,
                    help="examples per level when sampling from the combined "
                         "pool (default: 50 → 150 total). Ignored if "
                         "--per-source-per-level is set.")
    ap.add_argument("--per-source-per-level", type=int, default=None,
                    help="If set, sample N entries from each (source, level) "
                         "cell. Use this to give smaller sources fair "
                         "representation. Example: --per-source-per-level 25 "
                         "with 2 sources and 3 levels → 25×2×3 = 150 entries, "
                         "evenly split between the sources.")
    ap.add_argument("--require-answer", action="store_true",
                    help="Filter to examples that ship an explicit correct_answer.")
    args = ap.parse_args()

    print("Loading sources from SOURCES registry...")
    all_rows: list[dict] = []
    for cfg in SOURCES:
        all_rows.extend(load_source(cfg))
    if not all_rows:
        print("ERROR: no rows loaded. Check SOURCES paths and column names.",
              file=sys.stderr)
        return 1

    seen: dict[str, dict] = {}
    for r in all_rows:
        key = r["question"].lower().strip()
        if key in seen:
            if not seen[key].get("correct_answer") and r.get("correct_answer"):
                seen[key] = r
            continue
        seen[key] = r
    pool = list(seen.values())
    print(f"  pool after dedupe: {len(pool)}")

    if args.require_answer:
        before = len(pool)
        pool = [r for r in pool if r.get("correct_answer")]
        print(f"  filtered to entries WITH answers: {len(pool)}/{before}")
    else:
        print(f"  using all entries regardless of answer presence")

    if args.per_source_per_level is not None:
        print(f"  balanced sampling: {args.per_source_per_level} per "
              f"(source, level) cell")
        sampled = sample_per_source_per_level(pool, args.per_source_per_level)
    else:
        sampled = sample_balanced(pool, per_level=args.per_level)
        print(f"  pool sampling: {args.per_level} per level "
              f"(use --per-source-per-level to balance across sources)")
    print(f"  sampled {len(sampled)} entries")

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
