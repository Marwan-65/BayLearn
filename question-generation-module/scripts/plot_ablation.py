import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JUDGE_CSV = ROOT / "data" / "processed" / "ablation" / "ablation_judge_results.csv"

def plot_judge_results():
    if not JUDGE_CSV.exists():
        print(f"File not found: {JUDGE_CSV}")
        return

    df = pd.read_csv(JUDGE_CSV)

    # We want to evaluate the 3 main criteria
    metrics = ["answerability_winner", "difficulty_winner", "overall_winner"]
    labels = ["Answerability", "Difficulty Match", "Overall Preference"]

    # Loop through the two head-to-head comparisons
    for comp in ["A_vs_B", "B_vs_C"]:
        comp_df = df[df["comparison"] == comp]
        if comp_df.empty:
            continue

        cond1, cond2 = comp.split("_vs_")

        win_counts = {cond1: [], cond2: [], "tie": []}

        for m in metrics:
            counts = comp_df[m].value_counts()
            win_counts[cond1].append(counts.get(cond1, 0))
            win_counts[cond2].append(counts.get(cond2, 0))
            win_counts["tie"].append(counts.get("tie", 0) + counts.get("error", 0))

        x = np.arange(len(metrics))
        width = 0.25

        fig, ax = plt.subplots(figsize=(9, 6))
        ax.bar(x - width, win_counts[cond1], width, label=f'Condition {cond1} Wins', color='lightcoral')
        ax.bar(x, win_counts[cond2], width, label=f'Condition {cond2} Wins', color='mediumseagreen')
        ax.bar(x + width, win_counts["tie"], width, label='Ties', color='lightgray')

        ax.set_ylabel('Number of Wins')
        ax.set_title(f'Ablation Study: {cond1} vs {cond2}')
        ax.set_xticks(x)
        ax.set_xticklabels(labels)
        ax.legend()

        out_file = JUDGE_CSV.parent / f"plot_{comp}.png"
        plt.savefig(out_file, dpi=300, bbox_inches='tight')
        print(f"Saved chart to: {out_file}")

if __name__ == "__main__":
    plot_judge_results()
