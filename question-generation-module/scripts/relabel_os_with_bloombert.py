"""
Label the OS question bank using the trained BloomBERT classifier.

The OS .md file was originally labeled by eye, but those labels are not trusted
ground truth. This script runs the fine-tuned classifier over every question
and writes a CLEAN output CSV whose `level` column is the authoritative model
prediction. Eyeball labels are dropped from the output (they're kept in
os_eyeball.csv for traceability if you want to compare manually).

Output: data/processed/os_bloombert_labeled.csv
        Columns: question, level, confidence, subject, correct_answer, explanation
        This file is what scripts/build_example_bank.py consumes for the ICL bank.

Run:
    python scripts/relabel_os_with_bloombert.py
    python scripts/relabel_os_with_bloombert.py --model-dir models/bloom_distilbert
"""
from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROC = ROOT / "data" / "processed"
DEFAULT_MODEL = ROOT / "models" / "bloom_distilbert"
INPUT_CSV  = PROC / "os_eyeball.csv"
OUTPUT_CSV = PROC / "os_bloombert_labeled.csv"

sys.path.insert(0, str(ROOT))
from app.classifier.bloom_classifier import BloomClassifier  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model-dir", type=Path, default=DEFAULT_MODEL,
                    help=f"Path to trained BloomBERT (default: {DEFAULT_MODEL})")
    ap.add_argument("--input", type=Path, default=INPUT_CSV,
                    help=f"Parsed OS CSV to label (default: {INPUT_CSV})")
    ap.add_argument("--output", type=Path, default=OUTPUT_CSV,
                    help=f"Where to write the labeled CSV (default: {OUTPUT_CSV})")
    args = ap.parse_args()

    if not args.input.exists():
        print(f"ERROR: input CSV not found: {args.input}\n"
              f"       Run scripts/parse_os_eyeball.py first.", file=sys.stderr)
        return 1
    if not args.model_dir.exists():
        print(f"ERROR: model dir not found: {args.model_dir}", file=sys.stderr)
        return 1

    print(f"Loading BloomBERT from {args.model_dir}...")
    clf = BloomClassifier.load(args.model_dir)
    if clf.model is None:
        print("ERROR: classifier loaded in stub mode — weights missing or "
              "corrupted.", file=sys.stderr)
        return 1

    with args.input.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    print(f"Loaded {len(rows)} questions from {args.input.name}")

    # Predict in batch
    questions = [r["question"] for r in rows]
    preds = clf.predict_batch(questions)
    assert len(preds) == len(rows)

    # Write CLEAN output — only canonical BloomBERT labels, plus has_image
    # passthrough so downstream consumers know which questions need diagrams.
    out_fields = ["question", "level", "confidence", "has_image",
                  "subject", "correct_answer", "explanation"]
    with args.output.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=out_fields)
        w.writeheader()
        for r, p in zip(rows, preds):
            w.writerow({
                "question":       r["question"],
                "level":          p.level or "",
                "confidence":     f"{p.confidence:.4f}",
                "has_image":      r.get("has_image", ""),
                "subject":        r.get("subject", "operating systems"),
                "correct_answer": r.get("correct_answer", ""),
                "explanation":    r.get("explanation", ""),
            })

    # Console summary
    level_dist = Counter(p.level for p in preds)
    conf_low  = sum(1 for p in preds if p.confidence < 0.5)
    conf_high = sum(1 for p in preds if p.confidence >= 0.8)
    avg_conf  = sum(p.confidence for p in preds) / len(preds)

    print()
    print("=" * 60)
    print(f"Wrote {args.output}")
    print("=" * 60)
    print(f"Total questions labeled: {len(rows)}")
    print()
    print("Level distribution (BloomBERT predictions):")
    for lvl in ("easy", "medium", "hard"):
        n = level_dist.get(lvl, 0)
        pct = 100 * n / len(rows)
        print(f"  {lvl:<8} {n:>4}  ({pct:5.1f}%)")
    print()
    print("Confidence summary:")
    print(f"  mean:                    {avg_conf:.3f}")
    print(f"  high-confidence (≥0.80): {conf_high}  ({100*conf_high/len(rows):.0f}%)")
    print(f"  low-confidence  (<0.50): {conf_low}  ({100*conf_low/len(rows):.0f}%)  ← review these")
    print()
    print(f"Next step: refresh the example bank with these labels:")
    print(f"  python scripts/build_example_bank.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
