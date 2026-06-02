"""
Objective difficulty-match evaluation: baseline vs ICL.

ICL here is a *difficulty-control* mechanism (it shows expert exemplars at the
requested level). The fair, judge-free way to measure its benefit is: does ICL
produce questions whose BloomBERT-predicted level matches the requested level
more often than baseline?

This avoids the LLM-judge's position bias and its disagreement with BloomBERT's
level definitions.

Reads a generations CSV (columns: chunk_id, bloom_level, condition, question),
runs BloomBERT on every question, and reports level-match accuracy + mean
confidence for baseline vs icl (overall and per requested level).

    python scripts/difficulty_match_baseline_vs_icl.py
    python scripts/difficulty_match_baseline_vs_icl.py --csv data/processed/baseline_vs_icl_generations.csv
"""
import argparse
import csv
from collections import defaultdict
from pathlib import Path

from app.classifier.bloom_classifier import BloomClassifier, bloom6_to_level

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CSV = ROOT / "data" / "processed" / "baseline_vs_icl_generations.csv"
BLOOM_DIR = ROOT / "models" / "bloom_distilbert"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default=str(DEFAULT_CSV))
    args = ap.parse_args()

    rows = list(csv.DictReader(open(args.csv, encoding="utf-8")))
    clf = BloomClassifier.load(BLOOM_DIR)

    preds = clf.predict_batch([r["question"] for r in rows])
    if not preds or preds[0].level is None:
        print("BloomBERT not available (stub). Cannot measure difficulty match.")
        return

    # tallies[condition] = [matches, total, confidence_sum]
    overall = defaultdict(lambda: [0, 0, 0.0])
    per_level = defaultdict(lambda: [0, 0])  # (condition, expected_level) -> [match, total]

    for r, p in zip(rows, preds):
        cond = r["condition"]
        expected = bloom6_to_level(r["bloom_level"])  # easy | medium | hard
        match = int(p.level == expected)
        overall[cond][0] += match
        overall[cond][1] += 1
        overall[cond][2] += (p.confidence or 0.0)
        per_level[(cond, expected)][0] += match
        per_level[(cond, expected)][1] += 1

    # Discover whatever conditions are present (baseline, icl, examples_only, …)
    conditions = sorted({r["condition"] for r in rows})

    print(f"\nDifficulty-match (BloomBERT predicted level == requested level)")
    print(f"CSV: {args.csv}\n")
    print(f"{'condition':16} {'match%':>8} {'mean_conf':>10} {'n':>5}")
    print("-" * 44)
    for cond in conditions:
        m, n, cs = overall[cond]
        if n:
            print(f"{cond:16} {100*m/n:>7.1f}% {cs/n:>10.3f} {n:>5}")

    print(f"\nper requested level (match%):")
    header = f"{'level':10}" + "".join(f"{c:>16}" for c in conditions)
    print(header)
    print("-" * len(header))
    for lvl in ("easy", "medium", "hard"):
        line = f"{lvl:10}"
        for c in conditions:
            t = per_level.get((c, lvl), [0, 0])
            line += f"{(f'{100*t[0]/t[1]:.1f}%' if t[1] else '—'):>16}"
        print(line)


if __name__ == "__main__":
    main()
