"""
LLM-as-judge: blinded pairwise comparison of baseline vs ICL question sets.

Judge uses a fixed Bloom-taxonomy rubric with 6 quality dimensions + overall.
Counterbalanced ordering cancels position bias.

writes:
    data/processed/llm_judge_per_cell.csv      one row per cell with the judge's verdict
    data/processed/llm_judge_summary.txt       aggregate win rates + interpretation

Run:
    python scripts/llm_judge_baseline_vs_icl.py [--judge-provider gemini|groq]
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import random
import re
import sys
import time
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:
    pass

sys.path.insert(0, str(ROOT.parent))  # Add BayLearn root to path to resolve question_generation_model

from question_generation_model._judge_llm import make_judge_client, run_judge

GENERATIONS_CSV = ROOT / "data" / "processed" / "baseline_vs_icl_generations.csv"
OUT_PER_CELL    = ROOT / "data" / "processed" / "llm_judge_per_cell.csv"
OUT_SUMMARY     = ROOT / "data" / "processed" / "llm_judge_summary.txt"

# Import the exact chunks used during generation so the judge sees the same
# source text behind each (chunk_id, level) cell.
try:
    from generate_baseline_vs_icl import TEST_CHUNKS as _GEN_CHUNKS
    TEST_CHUNKS = {c["id"]: (c["topic"], c["text"]) for c in _GEN_CHUNKS}
except Exception as _e:
    print(f"(using built-in chunk fallback: {_e})")
    TEST_CHUNKS = {}

CRITERIA = [
    "cognitive_depth",
    "question_quality",
    "reasoning_demand",
    "educational_value",
    "discriminative_power",
    "bias_leakage",
    "overall",
]


def parse_judge_response(text: str) -> dict | None:
    text = text.strip()
    if text.startswith("```"):
        text = "\n".join(text.split("\n")[1:-1]) if "\n" in text else text
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


def _load_fieldnames() -> list[str]:
    fieldnames = ["chunk_id", "bloom_level"]
    for c in CRITERIA:
        fieldnames += [f"{c}_winner", f"{c}_orders", f"{c}_reason"]
    return fieldnames


def _write_summary(provider: str, model_name: str) -> None:
    """Recompute and write summary from whatever rows are already in OUT_PER_CELL."""
    if not OUT_PER_CELL.exists():
        return
    wins = {c: {"icl": 0, "baseline": 0, "tie": 0} for c in CRITERIA}
    total = 0
    with OUT_PER_CELL.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            total += 1
            for c in CRITERIA:
                w = row.get(f"{c}_winner", "tie")
                if w in wins[c]:
                    wins[c][w] += 1
    lines = [
        "LLM-as-judge: baseline vs ICL pairwise comparison",
        "=" * 70,
        f"Judge model : {provider} ({model_name})",
        f"Cells judged: {total}",
        f"Rubric      : fixed Bloom taxonomy (Recall→easy, Apply/Analyze→medium, Evaluate→hard)",
        "",
        f"{'criterion':<26}{'ICL wins':>10}{'baseline wins':>16}{'ties':>8}{'ICL %':>10}",
        "-" * 70,
    ]
    for c in CRITERIA:
        i = wins[c]["icl"]; b = wins[c]["baseline"]; t = wins[c]["tie"]
        pct = 100.0 * i / max(1, i + b) if (i + b) > 0 else 0.0
        lines.append(f"{c:<26}{i:>10}{b:>16}{t:>8}{pct:>9.1f}%")
    lines += [
        "",
        "ICL % = ICL wins / (ICL wins + baseline wins) — ties excluded.",
        "Counterbalanced judging: verdict recorded only when both orderings agree.",
        "",
        f"Per-cell judgments + reasons: {OUT_PER_CELL.name}",
    ]
    OUT_SUMMARY.write_text("\n".join(lines), encoding="utf-8")
    print("\n" + "\n".join(lines))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--judge-provider", default=None,
                    choices=["groq", "gemini"],
                    help="LLM provider for the judge. Default: JUDGE_PROVIDER env → groq")
    ap.add_argument("--sleep", type=float, default=None,
                    help="seconds between judge calls")
    ap.add_argument("--start", type=int, default=0,
                    help="0-based index of first cell to judge (default: 0)")
    ap.add_argument("--end", type=int, default=None,
                    help="0-based index one past the last cell to judge (default: all remaining)")
    ap.add_argument("--filter-levels", default=None,
                    help="comma-separated bloom levels to (re-)judge, e.g. apply. "
                         "Replaces those rows in the existing CSV, keeps all others.")
    args = ap.parse_args()

    # Prefer JUDGE_PROVIDER over LLM_PROVIDER so generation and judging use
    # different models by default (key design requirement of the ablation).
    provider = (
        args.judge_provider
        or os.environ.get("JUDGE_PROVIDER")
        or os.environ.get("LLM_PROVIDER")
        or "groq"
    ).lower()

    try:
        client, default_sleep, model_name = make_judge_client(provider)
    except RuntimeError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    sleep_secs = args.sleep if args.sleep is not None else default_sleep
    print(f"Judge: {provider} ({model_name}), sleep={sleep_secs:.1f}s between calls")

    if not GENERATIONS_CSV.exists():
        print(f"ERROR: {GENERATIONS_CSV} not found. Run generate_baseline_vs_icl.py first.",
              file=sys.stderr)
        return 1

    buckets: dict[tuple[str, str, str], list[str]] = defaultdict(list)
    with GENERATIONS_CSV.open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            key = (r["chunk_id"], r["bloom_level"], r["condition"])
            buckets[key].append(r["question"])

    all_cells = []
    seen_cells: set[tuple[str, str]] = set()
    for (cid, bloom_level, _cond) in buckets.keys():
        if (cid, bloom_level) in seen_cells:
            continue
        baseline = buckets.get((cid, bloom_level, "baseline"), [])
        icl      = buckets.get((cid, bloom_level, "icl"), [])
        if not baseline or not icl:
            continue
        all_cells.append((cid, bloom_level, baseline, icl))
        seen_cells.add((cid, bloom_level))

    total_cells = len(all_cells)
    start = args.start
    end   = args.end if args.end is not None else total_cells
    cells = all_cells[start:end]

    # Level filter: only judge the specified bloom levels
    filter_levels = (
        {l.strip() for l in args.filter_levels.split(",")}
        if args.filter_levels else None
    )
    if filter_levels:
        cells = [(c, l, b, i) for c, l, b, i in cells if l in filter_levels]
        print(f"Level filter active: {filter_levels} — {len(cells)} cells to judge")
    else:
        print(f"{total_cells} total cells | running cells {start}–{end - 1} ({len(cells)} cells)")

    if not cells:
        print("Nothing to judge in this range.", file=sys.stderr)
        return 1

    # Append mode when resuming a previous batch; write mode (with header) for
    # the first batch or a fresh run.
    append_mode = start > 0 and OUT_PER_CELL.exists()
    fieldnames  = _load_fieldnames()

    per_cell_rows = []

    for batch_idx, (cid, bloom_level, base_qs, icl_qs) in enumerate(cells, 1):
        global_idx = start + batch_idx
        if cid not in TEST_CHUNKS:
            print(f"skip unknown chunk_id {cid!r}")
            continue
        _topic, chunk_text = TEST_CHUNKS[cid]

        def _judge(set_a, set_b):
            resp = run_judge(client, chunk_text, bloom_level, set_a, set_b)
            return parse_judge_response(resp)

        try:
            v1 = _judge(base_qs, icl_qs)   # order 1: A=baseline, B=icl
            if sleep_secs > 0:
                time.sleep(sleep_secs)
            v2 = _judge(icl_qs, base_qs)   # order 2: A=icl,      B=baseline
        except Exception as e:
            print(f"  [cell {global_idx}/{total_cells}] {cid}/{bloom_level}: API error — {e}")
            if sleep_secs > 0:
                time.sleep(sleep_secs)
            continue
        if v1 is None or v2 is None:
            print(f"  [cell {global_idx}/{total_cells}] {cid}/{bloom_level}: parse failed")
            if sleep_secs > 0:
                time.sleep(sleep_secs)
            continue

        row = {"chunk_id": cid, "bloom_level": bloom_level}
        for c in CRITERIA:
            r1 = ((v1.get(c) or {}).get("winner") or "").strip().upper()
            r2 = ((v2.get(c) or {}).get("winner") or "").strip().upper()
            w1 = {"A": "baseline", "B": "icl"}.get(r1, "tie")
            w2 = {"A": "icl",      "B": "baseline"}.get(r2, "tie")
            cond_winner = w1 if (w1 == w2 and w1 != "tie") else "tie"
            row[f"{c}_winner"] = cond_winner
            row[f"{c}_orders"] = f"{w1}|{w2}"
            row[f"{c}_reason"] = ((v1.get(c) or {}).get("reason") or "")[:300]
        per_cell_rows.append(row)
        print(f"  [cell {global_idx}/{total_cells}] {cid}/{bloom_level}: "
              + " ".join(f"{c}={row[f'{c}_winner']}" for c in CRITERIA))
        if sleep_secs > 0:
            time.sleep(sleep_secs)

    # Write / append / replace depending on mode
    if filter_levels and OUT_PER_CELL.exists():
        # Replace rows for the filtered levels, keep everything else
        with OUT_PER_CELL.open(encoding="utf-8") as f:
            kept_rows = [r for r in csv.DictReader(f)
                         if r["bloom_level"] not in filter_levels]
        all_out_rows = kept_rows + per_cell_rows
        with OUT_PER_CELL.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames)
            w.writeheader()
            for row in all_out_rows:
                w.writerow(row)
        print(f"\nReplaced {len(filter_levels)} level(s): "
              f"{len(per_cell_rows)} new rows, {len(kept_rows)} kept → {OUT_PER_CELL}")
    else:
        open_mode = "a" if append_mode else "w"
        with OUT_PER_CELL.open(open_mode, newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames)
            if not append_mode:
                w.writeheader()
            for row in per_cell_rows:
                w.writerow(row)
        action = "Appended" if append_mode else "Wrote"
        print(f"\n{action} {len(per_cell_rows)} rows → {OUT_PER_CELL}")

    # Summary always reflects the full CSV so partial runs show cumulative totals
    _write_summary(provider, model_name)
    return 0


if __name__ == "__main__":
    sys.exit(main())
