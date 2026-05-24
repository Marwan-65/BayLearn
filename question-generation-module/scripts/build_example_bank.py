"""
Build the few-shot example bank from already-labeled data sources.

Sources (in priority order):
  1. data/processed/os_eyeball.csv      — your hand-labeled OS questions
  2. data/processed/srm_questions.csv   — SRM educator-labeled (filtered to CE subjects)

Output: data/processed/example_bank.jsonl
        One JSON object per line, schema = ExampleEntry from app/services/example_bank.py

Selection strategy:
  * Per level, sample N examples that have both an `answer` (when available)
    and look like complete questions.
  * Prefer entries with explanations (richer few-shot signal for the LLM).
  * Bias toward CE-related subjects so domain transfer is closer.

After BloomBERT is trained, regenerate OS-eyeball labels with the classifier
and re-run this script — the bank picks up the cleaner labels automatically.

Run:
    python3 scripts/build_example_bank.py
    python3 scripts/build_example_bank.py --per-level 30   # bigger bank
"""
from __future__ import annotations

import argparse
import csv
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROC = ROOT / "data" / "processed"
OUT_JSONL = PROC / "example_bank.jsonl"

# Subjects we consider "CE-relevant" — bank examples should match the domain
# of the LLM's expected inputs. Conservative list; expand as needed.
CE_SUBJECTS = {
    "operating systems", "operating systems (eyeball)",
    "database management systems", "database design and management",
    "data communication and networks", "computer networks",
    "design and analysis of algorithms",
    "programming and data structures", "c programming and data structures",
    "object oriented programming 1", "object oriented analysis and design",
    "compiler design", "theory of computation",
    "digital principles and computer organization", "digital logic circuits",
    "microprocessors and microcontrollers",
    "software engineering", "software project management 1",
    "artificial intelligence", "artificial intelligence and machine learning",
    "machine learning", "machine learning techniques ii",
    "deep learning and its applications", "neural networks",
    "cryptography and network security 1",
    "distributed computing", "cloud computing",
}


import re

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


def load_os_eyeball() -> list[dict]:
    # Prefer the BloomBERT-relabeled file if it exists (cleaner labels).
    # Fall back to the original eyeball-labeled file otherwise.
    relabeled = PROC / "os_eyeball_relabeled.csv"
    path = relabeled if relabeled.exists() else (PROC / "os_eyeball.csv")
    if path == relabeled:
        print("  using BloomBERT-relabeled OS questions (cleaner labels)")
    if not path.exists():
        return []
    rows = []
    with path.open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r.get("level") not in {"easy", "medium", "hard"}:
                continue
            if not is_quality_question(r["question"]):
                continue
            rows.append({
                "question":       strip_leading_number(r["question"]),
                "concept":        "operating systems",   # whole bank is OS topic
                "level":          r["level"],
                "question_type":  "short_answer",
                "correct_answer": r.get("correct_answer", ""),
                "explanation":    r.get("explanation", ""),
                "subject":        "operating systems",
                "source":         "os_eyeball",
            })
    print(f"  loaded {len(rows)} from os_eyeball.csv")
    return rows


def load_srm_ce() -> list[dict]:
    path = PROC / "srm_questions.csv"
    if not path.exists():
        return []
    rows = []
    with path.open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            subj = (r.get("subject") or "").strip().lower()
            if subj not in CE_SUBJECTS:
                continue
            if r.get("level") not in {"easy", "medium", "hard"}:
                continue
            if not is_quality_question(r["question"]):
                continue
            rows.append({
                "question":       r["question"],
                "concept":        subj,
                "level":          r["level"],
                "question_type":  "short_answer",
                "correct_answer": "",                    # SRM has no answers
                "explanation":    "",
                "subject":        subj,
                "source":         "srm",
            })
    print(f"  loaded {len(rows)} from srm_questions.csv (CE subjects only)")
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
    ap.add_argument("--per-level", type=int, default=20,
                    help="examples per level (default: 20 → 60 total)")
    ap.add_argument("--allow-no-answer", action="store_true",
                    help="Allow examples without correct_answer field. "
                         "Default: require an answer (better LLM format learning).")
    args = ap.parse_args()

    print("Loading labeled sources...")
    all_rows: list[dict] = []
    all_rows.extend(load_os_eyeball())
    all_rows.extend(load_srm_ce())

    # Dedupe by normalized question text
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

    # Quality gate: require answers by default. The few-shot block in the LLM
    # prompt shows Q + A so the LLM imitates both. Examples without an answer
    # leave the output-format signal incomplete.
    if not args.allow_no_answer:
        before = len(pool)
        pool = [r for r in pool if r.get("correct_answer")]
        print(f"  filtered to entries WITH answers: {len(pool)}/{before} "
              f"(pass --allow-no-answer to disable)")

    sampled = sample_balanced(pool, per_level=args.per_level)
    print(f"  sampled {len(sampled)} (per_level={args.per_level})")
    if len(sampled) < 3 * args.per_level:
        print(f"  WARNING: per_level={args.per_level} requested but pool was too small "
              f"for one or more levels. Consider lowering per_level or "
              f"--allow-no-answer.")

    # Write JSONL (without embeddings — the ExampleBank will fill them at load)
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

    # Quick distribution print
    from collections import Counter
    lvl = Counter(r["level"] for r in sampled)
    typ = Counter(r["question_type"] for r in sampled)
    print(f"  by level: {dict(lvl)}")
    print(f"  by type:  {dict(typ)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
