"""
Aggregate human ratings from the eval template and produce the comparison
table you'll put in your report.

Inputs (both in data/processed/):
    eval_human_ratings_template.csv   ← you fill in the rating columns
    eval_human_ratings_key.csv        ← auto-generated; maps anon_id → condition

Output:
    eval_human_ratings_summary.txt    ← mean per criterion, baseline vs ICL,
                                         with per-rater coverage and gaps

Run:
    python scripts/aggregate_human_ratings.py
"""
from __future__ import annotations

import csv
import sys
from collections import defaultdict
from pathlib import Path
from statistics import mean, stdev

ROOT = Path(__file__).resolve().parents[1]
PROC = ROOT / "data" / "processed"
RATINGS_CSV = PROC / "eval_human_ratings_template.csv"
KEY_CSV     = PROC / "eval_human_ratings_key.csv"
OUT_FILE    = PROC / "eval_human_ratings_summary.txt"

CRITERIA = [
    "fluency_1to5",
    "relevance_to_chunk_1to5",
    "difficulty_match_1to5",
    "originality_1to5",
    "pedagogical_value_1to5",
]


def parse_score(v: str) -> int | None:
    v = (v or "").strip()
    if not v:
        return None
    try:
        n = int(float(v))
    except ValueError:
        return None
    if 1 <= n <= 5:
        return n
    return None


def main() -> int:
    if not RATINGS_CSV.exists():
        print(f"ERROR: ratings file not found: {RATINGS_CSV}\n"
              f"       Run scripts/eval_icl_vs_baseline.py first.", file=sys.stderr)
        return 1
    if not KEY_CSV.exists():
        print(f"ERROR: key file not found: {KEY_CSV}", file=sys.stderr)
        return 1

    # Load the condition key
    cond_by_anon: dict[str, str] = {}
    with KEY_CSV.open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            cond_by_anon[r["anon_id"]] = r["condition"]

    # Load ratings
    rated = 0
    unrated = 0
    by_cond: dict[str, dict[str, list[int]]] = {
        "baseline": defaultdict(list),
        "icl": defaultdict(list),
    }
    with RATINGS_CSV.open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            cond = cond_by_anon.get(r["anon_id"])
            if not cond:
                continue
            any_score = False
            for c in CRITERIA:
                s = parse_score(r.get(c, ""))
                if s is not None:
                    by_cond[cond][c].append(s)
                    any_score = True
            if any_score:
                rated += 1
            else:
                unrated += 1

    if rated == 0:
        print("No rows have been rated yet. Open "
              f"{RATINGS_CSV} and fill the 1-5 columns first.",
              file=sys.stderr)
        return 1

    # Build report
    lines = []
    lines.append("Human rating aggregation")
    lines.append("=" * 60)
    lines.append(f"Total rated rows:   {rated}")
    lines.append(f"Total unrated rows: {unrated}")
    if unrated > 0:
        lines.append(f"WARNING: {unrated} rows are still empty. Results below "
                     "are partial.")
    lines.append("")

    lines.append(f"{'criterion':<28} {'baseline':>14} {'ICL':>14} {'Δ':>10}")
    lines.append("-" * 72)
    for c in CRITERIA:
        b = by_cond["baseline"][c]
        i = by_cond["icl"][c]
        if not b and not i:
            continue
        b_mean = mean(b) if b else float("nan")
        i_mean = mean(i) if i else float("nan")
        b_std  = stdev(b) if len(b) > 1 else 0.0
        i_std  = stdev(i) if len(i) > 1 else 0.0
        delta  = i_mean - b_mean if b and i else float("nan")
        lines.append(
            f"{c:<28} "
            f"{b_mean:.2f}±{b_std:.2f} ({len(b):>2})  "
            f"{i_mean:.2f}±{i_std:.2f} ({len(i):>2})  "
            f"{delta:+.2f}"
        )

    lines.append("")
    lines.append("Reading the table:")
    lines.append("  Each cell shows mean ± stdev (n=number of ratings).")
    lines.append("  Δ = ICL mean - baseline mean. Positive = ICL better.")
    lines.append("  All criteria are scored 1 (worst) to 5 (best). For all")
    lines.append("  five, HIGHER is better — ICL improvement is positive Δ.")
    lines.append("")
    lines.append("Suggested report sentence:")
    lines.append("  \"Across N rated questions, ICL achieved a mean improvement")
    lines.append("   of +X.Y points (on a 5-point scale) over the baseline on")
    lines.append("   <strongest-criterion> and +X.Y on <second-strongest>. The")
    lines.append("   <weakest-criterion> showed no significant change,")
    lines.append("   consistent with the prompt's OUTPUT FORMAT spec doing the")
    lines.append("   work for format adherence rather than the few-shot block.\"")

    print("\n".join(lines))
    OUT_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nReport saved to {OUT_FILE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
