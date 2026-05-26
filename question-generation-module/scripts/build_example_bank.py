"""
this file builds the few-shot example bank from labeled CSV sources , and you can add more test 
banks by drop your labeled CSV under data/processed/ and append a dict to SOURCES:
    {"name": "<short-id>", "path": "<csv-file>",
    "question_col": "<col>", "level_col": "<col>"}

run command: python scripts/build_example_bank.py

outputs:
    data/processed/example_bank.jsonl                — one JSON per question (question, level, source)
    data/processed/example_bank_embeddings.npy       — (N, 384) float32, L2-normalized so dot product = cosine
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path
from sentence_transformers import SentenceTransformer
from collections import Counter

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
PROC = ROOT / "data" / "processed"
OUT_JSONL = PROC / "example_bank.jsonl"
OUT_NPY   = PROC / "example_bank_embeddings.npy"

csv.field_size_limit(sys.maxsize)

EMBED_MODEL_DEFAULT = "sentence-transformers/all-MiniLM-L6-v2"

SOURCES: list[dict] = [
    {
    "name": "srm",
    "path": "srm_questions.csv",
    "question_col": "question",
    "level_col":    "level"
    },
    
    {
    "name": "os_bank",
    "path": "os_bloombert_labeled.csv",
    "question_col": "question",
    "level_col":    "level"
    },
]

_LEADING_NUM_RE = re.compile(r"^\s*\d{1,3}\s*[\.\-\)\\]+\s*")

def strip_leading_number(q: str) -> str:
    return _LEADING_NUM_RE.sub("", q).strip()

def is_valid_entry_for_question_field(q: str) -> bool:
    """only reject not valid entries"""
    q = strip_leading_number(q)
    return bool(q) and len(q) >= 12 and len(q.split()) >= 3

def load_source(config: dict) -> list[dict]:
    raw_path = config.get("path")
    if not raw_path:
        print(f"skip {config.get('name')}: no 'path' configured")
        return []
    path = Path(raw_path)
    if not path.is_absolute():
        path = PROC / raw_path
    if not path.exists():
        print(f"skip {config['name']}: {path} not found")
        return []

    q_col, l_col = config["question_col"], config["level_col"]
    rows = []
    skipped_level = skipped_validty = 0
    with path.open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            level = (r.get(l_col) or "").lower().strip()
            if level not in {"easy", "medium", "hard"}:
                skipped_level += 1
                continue
            question = r.get(q_col) or ""
            if not is_valid_entry_for_question_field(question):
                skipped_validty += 1
                continue
            rows.append({
                "question": strip_leading_number(question),
                "level":    level,
                "source":   config["name"],
            })
    # logging
    message = f"loaded {len(rows):>6} from {config['name']:<14} ({path.name})"
    if skipped_level + skipped_validty:
        message += f"skipped level={skipped_level} validty={skipped_validty}"
    print(message)
    return rows


def embed_all(texts: list[str], model_name: str) -> np.ndarray:
    """embed every question once """
    model = SentenceTransformer(model_name)
    print(f"  embedding {len(texts)} questions with {model_name}...")
    embs = model.encode(
        texts, batch_size=64, show_progress_bar=True,
        convert_to_numpy=True, normalize_embeddings=True,
    )
    return embs.astype(np.float32)


def main() -> int:
    argument_parser = argparse.ArgumentParser()
    argument_parser.add_argument("--embed-model", default=EMBED_MODEL_DEFAULT,
                    help=f"sentence-transformers model (default: {EMBED_MODEL_DEFAULT})")
    args = argument_parser.parse_args()

    all_rows: list[dict] = []
    for config in SOURCES:
        all_rows.extend(load_source(config))
    if not all_rows:
        print("ERROR: no rows loaded. Check SOURCES paths and column names",
            file=sys.stderr)
        return 1

    # dedupe by question text.
    seen: dict[str, dict] = {}
    for r in all_rows:
        seen.setdefault(r["question"].lower().strip(), r)
    entries = list(seen.values())
    print(f"length after dedupe: {len(entries)}")

    # compute embeddings and save them into .npy
    questions = [r["question"] for r in entries]
    embs = embed_all(questions, args.embed_model)
    np.save(OUT_NPY, embs)

    # write text JSONL file in parallel with the .npy
    with OUT_JSONL.open("w", encoding="utf-8") as f:
        for r in entries:
            f.write(json.dumps({
                "question": r["question"],
                "level":    r["level"],
                "source":   r["source"],
            }, ensure_ascii=False) + "\n")
    
    # check composition
    each_level_counts = Counter(r["level"] for r in entries)
    each_source_source = Counter(r["source"] for r in entries)
    print(f"\nTest Banks composition:")
    print(f"by level:  {dict(each_level_counts)}")
    print(f"by source: {dict(each_source_source)}")
    print(f"total:     {len(entries)} entries")
    return 0

if __name__ == "__main__":
    sys.exit(main())