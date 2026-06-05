#!/usr/bin/env python3
"""
Present the rag_mixed ablation results cleanly (read-only).
Run on wake:  PYTHONPATH=. .venv/bin/python present_results.py

Shows three things reviewers care about:
  1. Main table with EvalSR (evaluation success rate) — comparability gate.
  2. dropna vs honest(None=0) faithfulness — exposes any remaining bias.
  3. Per-question faithfulness grid — where any judge failures landed.
"""
import json, os

RESULTS = "ablation_results.json"
ORDER = ["baseline", "baseline+hyde", "rag_fusion", "+hybrid", "+reranker", "+compression"]
PRETTY = {
    "baseline": "baseline (dense)",
    "baseline+hyde": "+HyDE",
    "rag_fusion": "RAG-Fusion",
    "+hybrid": "+Hybrid (BM25)",
    "+reranker": "+Reranker",
    "+compression": "+Compression",
}


def load():
    if not os.path.exists(RESULTS):
        raise SystemExit(f"{RESULTS} not found.")
    return json.load(open(RESULTS))


def main():
    d = load()
    rows = [(c, d.get(f"os_threads@rag_os_hard::{c}")) for c in ORDER]

    print("=" * 78)
    print("ABLATION RESULTS — rag_os_hard (HARD OS corpus ~420 chunks, same-domain near-distractors, top_k=3, OS-threads questions, 1 per difficulty level)")
    print("=" * 78)
    hdr = (f"{'config':<18} {'Faith':>6} {'Relev':>6} {'Prec':>6} {'Recall':>6} "
           f"{'Overall':>8} {'EvalSR':>7}")
    print(hdr); print("-" * len(hdr))
    best_cfg, best_overall = None, -1
    for cfg, r in rows:
        if not r:
            print(f"{PRETTY.get(cfg,cfg):<18}  (not run)"); continue
        s = r["scores"]
        ov = s.get("overall", 0)
        if ov > best_overall and s.get("eval_success_rate", 0) >= 0.9:
            best_overall, best_cfg = ov, cfg
        print(f"{PRETTY.get(cfg,cfg):<18} {s.get('Faithfulness',0):>6.3f} "
              f"{s.get('AnswerRelevancy',0):>6.3f} {s.get('ContextPrecision',0):>6.3f} "
              f"{s.get('ContextRecall',0):>6.3f} {s.get('overall',0):>8.3f} "
              f"{s.get('eval_success_rate',0):>7.3f}")
    if best_cfg:
        print(f"\nBest config at EvalSR>=0.9: {PRETTY.get(best_cfg,best_cfg)} "
              f"(overall={best_overall:.3f})")
        base = d.get("os_threads@rag_os_hard::baseline", {}).get("scores", {}).get("overall")
        if base is not None:
            delta = best_overall - base
            verdict = "BEATS" if delta > 0 else "does NOT beat"
            print(f"vs baseline {base:.3f}: {verdict} baseline by {delta:+.3f}")

    # ---- dropna vs honest faithfulness ----
    print("\n" + "=" * 78)
    print("FAITHFULNESS: reported(dropna) vs honest(None=0) — bias check")
    print("=" * 78)
    print(f"{'config':<18} {'reported':>9} {'honest':>9} {'scored':>8}")
    print("-" * 46)
    for cfg, r in rows:
        if not r:
            continue
        pq = r.get("per_question", [])
        vals = [p.get("Faithfulness") for p in pq]
        scored = [v for v in vals if v is not None]
        reported = round(sum(scored) / len(scored), 3) if scored else 0.0
        honest = round(sum(v or 0 for v in vals) / len(vals), 3) if vals else 0.0
        print(f"{PRETTY.get(cfg,cfg):<18} {reported:>9.3f} {honest:>9.3f} "
              f"{len(scored):>6}/{len(vals)}")
    print("\nIf reported==honest for every row, no judge-failure bias remains.")

    # ---- per-question faithfulness grid ----
    print("\n" + "=" * 78)
    print("PER-QUESTION FAITHFULNESS GRID  (· = None/judge-failure)")
    print("=" * 78)
    base_pq = d.get("os_threads@rag_os_hard::baseline", {}).get("per_question", [])
    qlabels = [f"Q{i+1}" for i in range(len(base_pq))] or [f"Q{i+1}" for i in range(7)]
    print(f"{'config':<18} " + " ".join(f"{q:>5}" for q in qlabels))
    print("-" * (18 + 6 * len(qlabels)))
    for cfg, r in rows:
        if not r:
            continue
        pq = r.get("per_question", [])
        cells = []
        for p in pq:
            v = p.get("Faithfulness")
            cells.append("    ·" if v is None else f"{v:>5.2f}")
        print(f"{PRETTY.get(cfg,cfg):<18} " + " ".join(cells))


if __name__ == "__main__":
    main()
