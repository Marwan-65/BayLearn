#!/usr/bin/env python3
"""
update_latex.py — fill in ablation results in rag_experiments.tex.

Usage:
    python update_latex.py

Reads evaluation_results.json, finds the latest 4 ablation_scientific_*
entries, and patches the \todo{X.XX} placeholders in rag_experiments.tex.
"""
import json, re, sys, os
from datetime import date

RESULTS_FILE = "evaluation_results.json"
LATEX_FILE   = "rag_experiments.tex"

# Map run name → LaTeX row label
ROW_MAP = {
    "baseline":     "Baseline",
    "+hybrid":      "+Hybrid",
    "+reranker":    "+Reranker",
    "+compression": "+Compression",
}

METRIC_KEYS = {
    "Faithfulness":     ["Faithfulness", "faithfulness"],
    "AnswerRelevancy":  ["AnswerRelevancy", "answer_relevancy"],
    "ContextPrecision": ["ContextPrecision", "context_precision"],
    "ContextRecall":    ["ContextRecall", "context_recall"],
}


def get_val(scores, keys):
    for k in keys:
        v = scores.get(k)
        if v is not None and v != 0.0:
            return v
    return None


def load_results():
    with open(RESULTS_FILE) as f:
        data = json.load(f)

    today = date.today().isoformat()
    # Collect latest scientific ablation entries
    scientific = {}
    for e in data:
        label = e.get("label", "")
        if not label.startswith("ablation_scientific_"):
            continue
        run_name = label[len("ablation_scientific_"):]
        sc = e.get("scores", {})
        if sc.get("error") == "timeout":
            continue
        # Only accept non-zero results
        overall = sc.get("overall", 0)
        if overall <= 0:
            continue
        # Keep latest (last occurrence wins)
        scientific[run_name] = {"scores": sc, "entry": e}

    return scientific


def fmt(v):
    if v is None:
        return "N/A"
    return f"{v:.3f}"


def patch_latex(scientific):
    with open(LATEX_FILE, encoding="utf-8") as f:
        content = f.read()

    # Build replacement table rows
    rows_text = []
    run_order = ["baseline", "+hybrid", "+reranker", "+compression"]
    for run_key in run_order:
        if run_key not in scientific:
            print(f"  [WARN] No result for '{run_key}' — skipping", file=sys.stderr)
            continue
        sc = scientific[run_key]["scores"]
        faith = fmt(get_val(sc, METRIC_KEYS["Faithfulness"]))
        relev = fmt(get_val(sc, METRIC_KEYS["AnswerRelevancy"]))
        prec  = fmt(get_val(sc, METRIC_KEYS["ContextPrecision"]))
        rec   = fmt(get_val(sc, METRIC_KEYS["ContextRecall"]))
        label = ROW_MAP[run_key]
        row   = f"    {label:<20} & {faith} & {relev} & {prec} & {rec} & \\todo{{XXXX}} \\\\"
        rows_text.append((run_key, label, faith, relev, prec, rec))
        print(f"  {label}: F={faith} AR={relev} CP={prec} CR={rec}")

    # Replace the ablation table in the LaTeX
    # Find the table block for tab:results_scientific_ablation
    # Pattern: replace the \midrule ... \bottomrule section inside that table
    table_pattern = re.compile(
        r"(\\label\{tab:results_scientific_ablation\}.*?\\midrule\n)"
        r"(.*?)"
        r"(\\bottomrule)",
        re.DOTALL,
    )

    def make_new_body(rows_text):
        lines = []
        run_names = ["baseline", "+hybrid", "+reranker", "+compression"]
        label_map = {
            "baseline":     "Baseline",
            "+hybrid":      "+Hybrid",
            "+reranker":    "+Reranker",
            "+compression": "+Compression",
        }
        for r, label, faith, relev, prec, rec in rows_text:
            lines.append(
                f"    {label_map.get(r, label):<20} & {faith} & {relev} & {prec} & {rec} & --- \\\\\n"
            )
        return "".join(lines)

    new_body = make_new_body(rows_text)

    def replacer(m):
        return m.group(1) + new_body + m.group(3)

    new_content, n = table_pattern.subn(replacer, content, count=1)
    if n == 0:
        print("[WARN] Could not find the ablation table in LaTeX — check label", file=sys.stderr)
        return content

    return new_content


def main():
    print("Loading results...")
    scientific = load_results()

    if not scientific:
        print("No valid (non-zero, non-timeout) ablation results found yet.")
        print("Re-run this script after the ablation evaluation completes.")

        # Show what's available
        with open(RESULTS_FILE) as f:
            data = json.load(f)
        print("\nAll ablation_scientific entries:")
        for e in data:
            label = e.get("label", "")
            if "ablation_scientific" in label:
                sc = e.get("scores", {})
                print(f"  {label}: overall={sc.get('overall',0):.3f} err={sc.get('error','')!r}")
        sys.exit(1)

    print(f"\nFound {len(scientific)} valid ablation runs:")
    for k in scientific:
        print(f"  {k}: overall={scientific[k]['scores'].get('overall',0):.3f}")

    print("\nPatching LaTeX...")
    new_content = patch_latex(scientific)

    backup = LATEX_FILE + ".bak"
    import shutil
    shutil.copy(LATEX_FILE, backup)
    print(f"  Backup saved to {backup}")

    with open(LATEX_FILE, "w", encoding="utf-8") as f:
        f.write(new_content)
    print(f"  Updated {LATEX_FILE}")

    # Also dump the eval_to_latex output
    print("\n--- RAGAS Table (paste into paper) ---")
    from evaluation.eval_to_latex import build_table
    with open(RESULTS_FILE) as f:
        data = json.load(f)
    table = build_table(data, filter_prefix="ablation_scientific")
    print(table)


if __name__ == "__main__":
    main()
