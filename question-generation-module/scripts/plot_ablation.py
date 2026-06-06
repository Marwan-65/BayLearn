import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JUDGE_CSV = ROOT / "data" / "processed" / "ablation" / "ablation_judge_results.csv"
GEN_CSV = ROOT / "data" / "processed" / "ablation" / "ablation_generation_metrics.csv"
STATS_CSV = ROOT / "data" / "processed" / "ablation" / "ablation_stats.csv"

def plot_judge_results():
    if not JUDGE_CSV.exists():
        print(f"File not found: {JUDGE_CSV}")
        return

    df = pd.read_csv(JUDGE_CSV)

    # We want to evaluate the 4 ablation-specific criteria
    metrics = ["diversity_winner", "distractor_winner", "grounding_winner", "overall_winner"]
    labels = ["Topical Diversity", "Distractor Quality", "Source Grounding", "Overall Preference"]

    # Descriptive names for the report
    condition_names = {
        "A": "Baseline",
        "B": "+Enrichment",
        "C": "+Validator"
    }

    # Loop through the two head-to-head comparisons
    for comp in ["A_vs_B", "B_vs_C"]:
        comp_df = df[df["comparison"] == comp]
        if comp_df.empty:
            continue

        cond1, cond2 = comp.split("_vs_")

        name1 = condition_names.get(cond1, cond1)
        name2 = condition_names.get(cond2, cond2)

        win_counts = {cond1: [], cond2: [], "tie": []}

        for m in metrics:
            counts = comp_df[m].value_counts()
            win_counts[cond1].append(counts.get(cond1, 0))
            win_counts[cond2].append(counts.get(cond2, 0))
            win_counts["tie"].append(counts.get("tie", 0) + counts.get("error", 0))

        x = np.arange(len(metrics))
        width = 0.25

        fig, ax = plt.subplots(figsize=(9, 6))
        ax.bar(x - width, win_counts[cond1], width, label=f'{name1} Wins', color='lightcoral')
        ax.bar(x, win_counts[cond2], width, label=f'{name2} Wins', color='mediumseagreen')
        ax.bar(x + width, win_counts["tie"], width, label='Ties', color='lightgray')

        ax.set_ylabel('Number of Wins')
        ax.set_title(f'Ablation Study: {name1} vs {name2}')
        ax.set_xticks(x)
        ax.set_xticklabels(labels)
        ax.legend()

        out_file = JUDGE_CSV.parent / f"plot_{comp}.png"
        plt.savefig(out_file, dpi=300, bbox_inches='tight')
        print(f"Saved chart to: {out_file}")

def plot_generation_metrics():
    if not GEN_CSV.exists():
        return

    df = pd.read_csv(GEN_CSV)

    # We want to see which validators are failing most often (to tune thresholds)
    # The 'failed_validators' column contains strings like "V1,V3"
    failures = df["failed_validators"].dropna().astype(str)
    counts = {"V1 (Anchoring)": 0, "V2 (BM25)": 0, "V3 (Distractors)": 0, "V4 (Difficulty)": 0, "V5 (Structure)": 0}
    
    for f_str in failures:
        if "V1" in f_str: counts["V1 (Anchoring)"] += 1
        if "V2" in f_str: counts["V2 (BM25)"] += 1
        if "V3" in f_str: counts["V3 (Distractors)"] += 1
        if "V4" in f_str: counts["V4 (Difficulty)"] += 1
        if "V5" in f_str: counts["V5 (Structure)"] += 1
        
    if sum(counts.values()) > 0:
        fig, ax = plt.subplots(figsize=(9, 6))
        ax.bar(counts.keys(), counts.values(), color='salmon', edgecolor='black')
        ax.set_title('Semantic Validator Rejections (All Conditions)')
        ax.set_ylabel('Number of Occurrences')
        plt.xticks(rotation=15)
        
        out_file = GEN_CSV.parent / "plot_validator_failures.png"
        plt.savefig(out_file, dpi=300, bbox_inches='tight')
        print(f"Saved validator failure chart to: {out_file}")

def plot_stats_metrics():
    if not STATS_CSV.exists():
        return

    df = pd.read_csv(STATS_CSV)
    
    # Group by condition and calculate means
    means = df.groupby("condition").mean(numeric_only=True)
    
    metrics = ["distinct_2_grams", "avg_self_bleu", "grounding"]
    labels = ["Distinct 2-Grams\n(Higher = More Diverse)", "Avg Self-BLEU\n(Lower = Less Overlap)", "Grounding\n(Higher = More Relevant)"]
    
    condition_names = {"A": "Baseline", "B": "+Enrichment", "C": "+Validator"}
    conditions = ["A", "B", "C"]
    colors = ['lightcoral', 'skyblue', 'mediumseagreen']
    
    x = np.arange(len(metrics))
    width = 0.25
    
    fig, ax = plt.subplots(figsize=(10, 6))
    
    for i, cond in enumerate(conditions):
        if cond in means.index:
            values = [means.loc[cond, m] for m in metrics]
            # Offset bars so they appear side-by-side
            pos = x - width + (i * width)
            ax.bar(pos, values, width, label=condition_names[cond], color=colors[i], edgecolor='black')
            
    ax.set_ylabel('Average Score')
    ax.set_title('Generation Statistics across Conditions')
    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.legend()
    
    out_file = STATS_CSV.parent / "plot_generation_stats.png"
    plt.savefig(out_file, dpi=300, bbox_inches='tight')
    print(f"Saved stats chart to: {out_file}")

if __name__ == "__main__":
    plot_judge_results()
    plot_generation_metrics()
    plot_stats_metrics()
