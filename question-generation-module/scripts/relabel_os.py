"""output: data/processed/os_labeled.csv

run command:
    python scripts/relabel_os.py --model-dir models/bloom_distilbert
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
INPUT_CSV  = PROC / "os.csv"
OUTPUT_CSV = PROC / "os_labeled.csv"

sys.path.insert(0, str(ROOT))
from app.classifier.bloom_classifier import BloomClassifier  

def main() -> int:
    argparser = argparse.ArgumentParser()
    argparser.add_argument("--model-dir", type=Path, default=DEFAULT_MODEL,
                    help=f"path to trained BloomBERT (default: {DEFAULT_MODEL})")
    argparser.add_argument("--input", type=Path, default=INPUT_CSV,
                    help=f"parsed OS CSV to label (default: {INPUT_CSV})")
    argparser.add_argument("--output", type=Path, default=OUTPUT_CSV,
                    help=f"where to write the labeled CSV (default: {OUTPUT_CSV})")
    args = argparser.parse_args()

    if not args.input.exists():
        print(f"input CSV not found: {args.input}\n"
            f"run scripts/parse_os.py first", file=sys.stderr)
        return 1
    
    if not args.model_dir.exists():
        print(f"model dir not found: {args.model_dir}", file=sys.stderr)
        return 1

    classifier = BloomClassifier.load(args.model_dir)
    if classifier.model is None:
        print("classifier corrupted" , file=sys.stderr)
        return 1

    with args.input.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    print(f"loaded {len(rows)} questions from {args.input.name}")

    questions = [r["question"] for r in rows]
    predictions = classifier.predict_batch(questions)
    assert len(predictions) == len(rows)

    out_fields = ["question", "level", "confidence", "has_image"]
    with args.output.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=out_fields)
        w.writeheader()
        for r, p in zip(rows, predictions):
            w.writerow({
                "question":       r["question"],
                "level":          p.level or "",
                "confidence":     f"{p.confidence:.4f}",
                "has_image":      r.get("has_image", ""),
            })

    # logging
    level_dist = Counter(p.level for p in predictions)
    conf_low  = sum(1 for p in predictions if p.confidence < 0.5)
    conf_high = sum(1 for p in predictions if p.confidence >= 0.8)
    avg_conf  = sum(p.confidence for p in predictions) / len(predictions)

    print("Level distribution (BloomBERT predictions):")
    for level in ("easy", "medium", "hard"):
        n = level_dist.get(level, 0)
        pct = 100 * n / len(rows)
        print(f"  {level:<8} {n:>4}  ({pct:5.1f}%)")
    print()
    print("confidence summary:")
    print(f"mean:                    {avg_conf:.3f}")
    print(f"high-confidence (≥0.80): {conf_high}  ({100*conf_high/len(rows):.0f}%)")
    print(f"low-confidence  (<0.50): {conf_low}  ({100*conf_low/len(rows):.0f}%)")
    print()
    print(f"after that refresh the example bank with these labels:")
    print(f" python scripts/build_example_bank.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
