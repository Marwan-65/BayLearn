"""
Replace your eyeball labels on the OS question bank with BloomBERT predictions.

Why: your manual labels were your best guess by eye. BloomBERT learned from
22k educator-labeled questions and should be more consistent. We run the
classifier over your 133 OS questions and write a new CSV that:

  - keeps the original `level` as `eyeball_level` (so you can compare)
  - adds `bloombert_level` (the classifier prediction)
  - adds `bloombert_confidence` (softmax prob)
  - adds `agreement` (True if eyeball matches bloombert)
  - uses `bloombert_level` as the new `level` going forward

Output: data/processed/os_eyeball_relabeled.csv

Also prints an agreement report so you see where your eye and the model
disagree — that's diagnostic information for your project report.

Run:
    python3 scripts/relabel_os_with_bloombert.py
    python3 scripts/relabel_os_with_bloombert.py --model-dir models/bloom_distilbert
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
INPUT_CSV = PROC / "os_eyeball.csv"
OUTPUT_CSV = PROC / "os_eyeball_relabeled.csv"

# Reuse the project's classifier wrapper so behavior matches the API.
sys.path.insert(0, str(ROOT))
from app.classifier.bloom_classifier import BloomClassifier  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model-dir", type=Path, default=DEFAULT_MODEL,
                    help=f"Path to trained BloomBERT (default: {DEFAULT_MODEL})")
    ap.add_argument("--input", type=Path, default=INPUT_CSV,
                    help=f"OS eyeball CSV to relabel (default: {INPUT_CSV})")
    ap.add_argument("--output", type=Path, default=OUTPUT_CSV,
                    help=f"Where to write the relabeled CSV (default: {OUTPUT_CSV})")
    args = ap.parse_args()

    if not args.input.exists():
        print(f"ERROR: input CSV not found: {args.input}", file=sys.stderr)
        return 1
    if not args.model_dir.exists():
        print(f"ERROR: model dir not found: {args.model_dir}\n"
              f"       Download /kaggle/working/bloom_distilbert/ from Kaggle "
              f"and extract here first.", file=sys.stderr)
        return 1

    print(f"Loading BloomBERT from {args.model_dir}...")
    clf = BloomClassifier.load(args.model_dir)
    if clf.model is None:
        print("ERROR: classifier loaded in stub mode — weights missing or "
              "corrupted.", file=sys.stderr)
        return 1

    # Load all questions
    with args.input.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    print(f"Loaded {len(rows)} questions from {args.input.name}")

    # Predict all at once (batched internally)
    questions = [r["question"] for r in rows]
    preds = clf.predict_batch(questions)
    assert len(preds) == len(rows)

    # Annotate and write
    out_fields = [
        "question", "level", "eyeball_level", "bloombert_level",
        "bloombert_confidence", "agreement",
        # Keep any additional columns from the input verbatim:
        "correct_answer", "explanation",
    ]
    # Add any extra input columns we didn't anticipate
    extra_cols = [c for c in (rows[0].keys() if rows else [])
                  if c not in out_fields and c != "level"]
    out_fields.extend(extra_cols)

    agree_counter = Counter()
    confusion: dict[tuple[str, str], int] = Counter()
    bloombert_dist = Counter()
    eyeball_dist = Counter()

    with args.output.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=out_fields)
        w.writeheader()
        for r, p in zip(rows, preds):
            eyeball = (r.get("level") or "").lower().strip()
            bert = p.level or ""
            agreement = eyeball == bert
            agree_counter[agreement] += 1
            confusion[(eyeball, bert)] += 1
            bloombert_dist[bert] += 1
            eyeball_dist[eyeball] += 1

            out_row = {
                "question":             r["question"],
                "level":                bert,                # NEW canonical label
                "eyeball_level":        eyeball,
                "bloombert_level":      bert,
                "bloombert_confidence": f"{p.confidence:.4f}",
                "agreement":            "yes" if agreement else "no",
                "correct_answer":       r.get("correct_answer", ""),
                "explanation":          r.get("explanation", ""),
            }
            for c in extra_cols:
                out_row[c] = r.get(c, "")
            w.writerow(out_row)

    # Report
    total = len(rows)
    agree_pct = 100 * agree_counter[True] / max(1, total)
    print()
    print("=" * 60)
    print(f"Wrote {args.output}")
    print("=" * 60)
    print(f"Total questions:         {total}")
    print(f"BloomBERT == eyeball:    {agree_counter[True]}  ({agree_pct:.1f}%)")
    print(f"BloomBERT != eyeball:    {agree_counter[False]}  ({100-agree_pct:.1f}%)")
    print()
    print("Label distribution shift:")
    print(f"  {'level':<8} {'eyeball':>9} {'bloombert':>11}")
    for lvl in ("easy", "medium", "hard"):
        e_n = eyeball_dist.get(lvl, 0)
        b_n = bloombert_dist.get(lvl, 0)
        print(f"  {lvl:<8} {e_n:>9} {b_n:>11}")
    print()
    print("Disagreement breakdown (eyeball → bloombert):")
    for (eye, ber), n in sorted(confusion.items(), key=lambda x: -x[1]):
        if eye != ber:
            print(f"  {eye:<7} → {ber:<7}  {n:>3}")
    print()
    print(f"Cohen's kappa-equivalent simple agreement: {agree_pct:.1f}%")
    print()
    print("Interpretation:")
    print("  > 80%   strong agreement (your eye matched the model)")
    print("  60-80%  moderate (typical for human Bloom labeling)")
    print("  < 60%   model disagrees a lot — review a sample of disagreements")
    print()
    print(f"Next step: re-run scripts/build_example_bank.py to refresh the bank")
    print(f"with cleaner labels.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
