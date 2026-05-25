"""
Analyze WHY BloomBERT disagreed with your eyeball labels on the OS bank.

We can't open up the model's reasoning directly, but we can compute simple
question features (length, code presence, sub-part count, leading verb,
numerical content) and group them by (eyeball_level → bloombert_level)
bucket. Patterns in these features reveal the implicit criteria the model
learned from the SRM + Devane training data.

Output:
  - prints a per-bucket feature summary (counts + averages)
  - prints sample questions per bucket so you can read them
  - writes data/processed/relabel_feature_analysis.csv
    (one row per question, with all engineered features + both labels)

Run:
    python scripts/analyze_relabel_disagreements.py
    python scripts/analyze_relabel_disagreements.py --samples 5
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean

ROOT = Path(__file__).resolve().parents[1]
INPUT_CSV  = ROOT / "data" / "processed" / "os_eyeball_relabeled.csv"
OUTPUT_CSV = ROOT / "data" / "processed" / "relabel_feature_analysis.csv"

# Bloom verb groups (approximate — used to guess what verb the model "saw")
BLOOM_VERBS = {
    "easy_R": ["define", "list", "name", "state", "identify", "recall", "what is", "which", "label", "write the"],
    "easy_U": ["explain", "describe", "summarize", "discuss", "interpret", "classify", "give"],
    "med_A":  ["calculate", "compute", "solve", "use", "show", "apply", "demonstrate", "execute", "find"],
    "med_An": ["compare", "contrast", "differentiate", "distinguish", "analyze", "trace", "examine"],
    "hard_E": ["evaluate", "justify", "critique", "defend", "assess", "judge", "argue", "which is better"],
    "hard_C": ["design", "construct", "develop", "formulate", "propose", "devise", "create", "generate"],
}
ALL_VERB_BUCKETS = list(BLOOM_VERBS.keys())


def detect_verb_bucket(q: str) -> str:
    q_lower = q.lower()
    for bucket in ALL_VERB_BUCKETS:
        for verb in BLOOM_VERBS[bucket]:
            if re.search(rf"\b{re.escape(verb)}\b", q_lower):
                return bucket
    return "(no_match)"


def featurize(q: str) -> dict:
    words = q.split()
    n_words = len(words)
    # Code presence: heuristics — language keywords, semicolons, braces, parens with patterns
    has_code = bool(
        re.search(r"\b(int |void |return |if\s*\(|while\s*\(|for\s*\(|printf|pthread|malloc|struct |class )", q)
        or q.count("{") >= 1 and q.count("}") >= 1
        or q.count(";") >= 3
    )
    # Multi-part: enumerations like "1-", "2-", "i)", "(a)", etc.
    sub_part_count = max(
        len(re.findall(r"(?m)^\s*\d+[\.\)\-]", q)),
        len(re.findall(r"(?m)^\s*\([ivx]+\)", q.lower())),
        len(re.findall(r"(?m)^\s*\([a-d]\)", q.lower())),
    )
    # Numerical content: numbers, math symbols
    has_numbers = bool(re.search(r"\b\d+\b", q))
    has_math = bool(re.search(r"[=+\-*/<>%]", q))
    # Question length tiers (matches what the model "sees" — token-ish proxy)
    if n_words < 15:        length_tier = "short"
    elif n_words < 40:      length_tier = "medium"
    else:                   length_tier = "long"
    return {
        "n_words":        n_words,
        "length_tier":    length_tier,
        "has_code":       has_code,
        "sub_parts":      sub_part_count,
        "has_numbers":    has_numbers,
        "has_math":       has_math,
        "verb_bucket":    detect_verb_bucket(q),
    }


def load_rows():
    if not INPUT_CSV.exists():
        print(f"ERROR: {INPUT_CSV} not found. Run relabel_os_with_bloombert.py first.",
              file=sys.stderr)
        sys.exit(1)
    rows = []
    with INPUT_CSV.open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            r["features"] = featurize(r["question"])
            rows.append(r)
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--samples", type=int, default=3,
                    help="how many sample questions to print per bucket (default 3)")
    args = ap.parse_args()

    rows = load_rows()
    total = len(rows)

    # Write per-question CSV with all features
    fieldnames = ["question", "eyeball_level", "bloombert_level", "bloombert_confidence", "agreement",
                  "n_words", "length_tier", "has_code", "sub_parts", "has_numbers", "has_math", "verb_bucket"]
    with OUTPUT_CSV.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow({
                "question":              r["question"],
                "eyeball_level":         r.get("eyeball_level", ""),
                "bloombert_level":       r.get("bloombert_level", ""),
                "bloombert_confidence":  r.get("bloombert_confidence", ""),
                "agreement":             r.get("agreement", ""),
                **r["features"],
            })
    print(f"Wrote per-question features → {OUTPUT_CSV}\n")

    # Group by (eyeball → bloombert) bucket
    buckets: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for r in rows:
        buckets[(r["eyeball_level"], r["bloombert_level"])].append(r)

    print("=" * 72)
    print("PER-BUCKET FEATURE ANALYSIS")
    print("=" * 72)
    print(f"Total questions: {total}\n")

    # Print buckets ordered by size (biggest disagreements first)
    sorted_buckets = sorted(buckets.items(), key=lambda kv: -len(kv[1]))
    for (eye, bert), items in sorted_buckets:
        agree = "✓ AGREE" if eye == bert else "✗ DISAGREE"
        print(f"\n--- {agree}: eyeball={eye!r}  →  bloombert={bert!r}  (n={len(items)})")
        feats = [it["features"] for it in items]
        if not feats:
            continue
        avg_words   = mean(f["n_words"]   for f in feats)
        avg_parts   = mean(f["sub_parts"] for f in feats)
        pct_code    = 100 * sum(f["has_code"]    for f in feats) / len(feats)
        pct_math    = 100 * sum(f["has_math"]    for f in feats) / len(feats)
        pct_numbers = 100 * sum(f["has_numbers"] for f in feats) / len(feats)
        verb_dist = Counter(f["verb_bucket"] for f in feats).most_common(3)
        length_dist = Counter(f["length_tier"] for f in feats)

        print(f"  avg words: {avg_words:.1f}   avg sub-parts: {avg_parts:.2f}")
        print(f"  has code: {pct_code:.0f}%   has math symbols: {pct_math:.0f}%   has numbers: {pct_numbers:.0f}%")
        print(f"  length tiers: {dict(length_dist)}")
        print(f"  top verb buckets: {verb_dist}")

        # Print a few sample questions
        print(f"  samples:")
        for it in items[:args.samples]:
            q = it["question"][:140].replace("\n", " ")
            conf = it.get("bloombert_confidence", "")
            print(f"    [conf={conf}] {q}{'...' if len(it['question']) > 140 else ''}")

    # Overall feature → predicted-level correlations
    print("\n" + "=" * 72)
    print("FEATURE → MODEL PREDICTION CORRELATIONS")
    print("=" * 72)
    print("\nWhich features predict that the model assigns each level?\n")
    for level in ("easy", "medium", "hard"):
        items = [r for r in rows if r.get("bloombert_level") == level]
        if not items:
            continue
        feats = [it["features"] for it in items]
        print(f"\nModel said {level!r}  (n={len(items)}):")
        print(f"  avg words: {mean(f['n_words'] for f in feats):.1f}")
        print(f"  avg sub-parts: {mean(f['sub_parts'] for f in feats):.2f}")
        print(f"  has code: {100*sum(f['has_code'] for f in feats)/len(feats):.0f}%")
        print(f"  has math: {100*sum(f['has_math'] for f in feats)/len(feats):.0f}%")
        print(f"  top verbs: {Counter(f['verb_bucket'] for f in feats).most_common(3)}")

    print("\nDone.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
