#!/usr/bin/env python3
"""
PHASE 1 — Generation only (no judging).
=======================================
Runs retrieval + answer generation for every config via the GENERATION_BACKEND
(Gemini) and SAVES answers + contexts + ground_truth + per-question timings +
latency to `ablation_generations.json`.

This is the slow-to-reproduce, latency-bearing part — so we do it ONCE and
persist it. Judging (phase 2) reads this file and never re-generates, so:
  • generations are never lost,
  • LATENCY is measured here and frozen (judging cannot corrupt it).

Run:  PYTHONPATH=. .venv/bin/python ablation_generate.py
Fast: generation is Gemini (~1-2s/question), all 6 configs in a couple minutes.
"""
import os, sys, json, time, logging
os.environ["TOKENIZERS_PARALLELISM"] = "false"
logging.basicConfig(level=logging.WARNING)
SRC = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SRC)

from helpers.config import get_settings
from ablation.ab_run import build_controller
from evaluation.test_set import get_test_cases
from routes._nlp_handlers import _run_batch, _avg_latency

OUT = "ablation_generations.json"
COLLECTION = "rag_os_hard"   # ~420-chunk OS corpus, same-domain near-distractors
DATASET = "os_threads"       # keyword-rich threads questions (pthread, Amdahl, OpenMP)
TOP_K = 3                    # tight: ranking errors are costly -> exposes the layers

# 6-config ladder (matches ab_run LADDER, minus +contextual which needs a ctx index)
LADDER = [
    ("baseline",      dict(mq=False, hy=False, rr=False, cp=False, hd=False)),
    ("baseline+hyde", dict(mq=False, hy=False, rr=False, cp=False, hd=True)),
    ("rag_fusion",    dict(mq=True,  hy=False, rr=False, cp=False, hd=False)),
    ("+hybrid",       dict(mq=True,  hy=True,  rr=False, cp=False, hd=False)),
    ("+reranker",     dict(mq=True,  hy=True,  rr=True,  cp=False, hd=False)),
    ("+compression",  dict(mq=True,  hy=True,  rr=True,  cp=True,  hd=False)),
]


def per_level_subset(cases):
    seen, sub = set(), []
    for c in cases:
        if c["level"] not in seen:
            seen.add(c["level"]); sub.append(c)
    return sub


def main():
    settings = get_settings()
    print(f"GENERATION_BACKEND = {settings.GENERATION_BACKEND}", flush=True)
    controller, vdb = build_controller(settings)
    cases = per_level_subset(get_test_cases(dataset=DATASET))
    print(f"{len(cases)} questions (per-level). Generating {len(LADDER)} configs.\n", flush=True)

    out = {}
    if os.path.exists(OUT):
        try:
            out = json.load(open(OUT))
        except Exception:
            out = {}

    for cfg_name, fl in LADDER:
        key = f"{DATASET}@{COLLECTION}::{cfg_name}"
        # resume: skip a config already generated with all-real answers
        if key in out and out[key].get("all_real"):
            print(f"SKIP {cfg_name} (already generated, all real)", flush=True)
            continue
        print(f"GEN  {cfg_name} ...", end=" ", flush=True)
        t0 = time.time()
        test_cases, test_details = _run_batch(
            controller=controller, project_id=COLLECTION, cases=cases,
            enable_multi_query=fl["mq"], enable_hybrid=fl["hy"],
            enable_reranker=fl["rr"], enable_compression=fl["cp"],
            enable_hyde=fl["hd"], limit=TOP_K, per_q_timeout=240,
        )
        batch_ms = round((time.time() - t0) * 1000)
        real = sum(
            1 for tc in test_cases
            if not (("wasn" in tc["answer"] and "able to generate" in tc["answer"])
                    or tc["answer"].strip() == "GENERATION_TIMEOUT"
                    or len(tc["answer"].strip()) < 5)
        )
        out[key] = {
            "dataset": DATASET, "config": cfg_name, "collection": COLLECTION,
            "flags": fl,
            "avg_latency_ms": _avg_latency(test_details),   # FROZEN latency
            "batch_ms": batch_ms,
            "num_cases": len(test_cases),
            "all_real": real == len(test_cases),
            "real_count": real,
            "test_cases": test_cases,        # answer/contexts/ground_truth for judging
            "test_details": test_details,    # per-question timings
        }
        json.dump(out, open(OUT, "w"), indent=2)
        print(f"{real}/{len(test_cases)} real answers, {batch_ms}ms", flush=True)

    vdb.disconnect()
    total_real = all(v.get("all_real") for v in out.values())
    print(f"\nGENERATION DONE -> {OUT}. All configs fully real: {total_real}", flush=True)


if __name__ == "__main__":
    main()
