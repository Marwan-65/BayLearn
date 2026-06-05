import argparse
import json
import os
import sys
from typing import Dict, List


METRIC_ORDER = [
    ("Faithfulness",     ["Faithfulness", "faithfulness"]),
    ("Answer Rel.",      ["AnswerRelevancy", "answer_relevancy"]),
    ("Context Prec.",    ["ContextPrecision", "context_precision"]),
    ("Context Recall",   ["ContextRecall", "context_recall"]),
    ("Overall",          ["overall"]),
]


def _get(d: Dict, keys: List[str], default=None):
    for k in keys:
        if k in d:
            return d[k]
    return default


def _is_dead(scores: Dict) -> bool:
    """Treat a row as dead (timeout / total failure) if every metric is 0."""
    if scores.get("error"):
        return True
    nums = [
        v for v in scores.values()
        if isinstance(v, (int, float)) and not isinstance(v, bool)
    ]
    return all(abs(v) < 1e-9 for v in nums) if nums else True


def _fmt(v) -> str:
    if not isinstance(v, (int, float)):
        return "—"
    return f"{v:.3f}"


def build_table(entries: List[Dict], filter_prefix: str = None) -> str:
    rows = []
    for e in entries:
        label = str(e.get("label") or "(unnamed)")
        if filter_prefix and not label.startswith(filter_prefix):
            continue
        scores = e.get("scores") or {}
        if _is_dead(scores):
            continue
        row = {
            "label": label.replace("_", r"\_"),
            **{name: _fmt(_get(scores, keys)) for name, keys in METRIC_ORDER},
        }
        rows.append(row)

    if not rows:
        return "% No usable evaluation rows found.\n"

    cols = "l" + "c" * len(METRIC_ORDER)
    out = []
    out.append(r"\begin{table}[h]")
    out.append(r"\centering")
    out.append(r"\small")
    out.append(r"\caption{RAGAS evaluation results. Higher is better; 1.0 is the maximum.}")
    out.append(r"\label{tab:ragas-results}")
    out.append(rf"\begin{{tabular}}{{{cols}}}")
    out.append(r"\toprule")
    header = "Configuration & " + " & ".join(name for name, _ in METRIC_ORDER) + r" \\"
    out.append(header)
    out.append(r"\midrule")
    for r in rows:
        line = r["label"] + " & " + " & ".join(r[name] for name, _ in METRIC_ORDER) + r" \\"
        out.append(line)
    out.append(r"\bottomrule")
    out.append(r"\end{tabular}")
    out.append(r"\end{table}")
    return "\n".join(out) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default="evaluation_results.json")
    ap.add_argument("--filter", default=None,
                    help="Only include rows whose label starts with this prefix "
                         "(e.g. 'ablation_scientific').")
    ap.add_argument("--output", default=None,
                    help="Write to this file instead of stdout.")
    args = ap.parse_args()

    if not os.path.exists(args.input):
        print(f"Input file not found: {args.input}", file=sys.stderr)
        sys.exit(1)

    with open(args.input) as f:
        data = json.load(f)
    if isinstance(data, dict):
        data = [data]

    table = build_table(data, filter_prefix=args.filter)

    if args.output:
        with open(args.output, "w") as f:
            f.write(table)
        print(f"Wrote {args.output}", file=sys.stderr)
    else:
        print(table)


if __name__ == "__main__":
    main()
