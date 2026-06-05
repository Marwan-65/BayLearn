#!/usr/bin/env python3
"""
PHASE 2 — Judge the saved generations (no re-generation).
=========================================================
Reads `ablation_generations.json` (answers + contexts + FROZEN latency from
phase 1) and scores each config with RAGAS. Judge providers are tried in order
until one returns a clean result (overall>0 AND eval_success_rate>=0.85):

    1. Groq  (llama-3.1-8b-instant)   — fast, free, primary judge
    2. Cerebras gpt-oss-120b (fresh)  — fallback
    3. Gemini gemini-2.5-flash-lite   — fallback

Writes final scored configs into `ablation_results.json`, carrying over the
latency/timings UNCHANGED from phase 1 (judging never touches latency).
Resumable: a config already saved with EvalSR>=0.85 is skipped.

Run:  PYTHONPATH=. .venv/bin/python ablation_judge.py
"""
import os, sys, json, asyncio, logging
os.environ["TOKENIZERS_PARALLELISM"] = "false"
logging.basicConfig(level=logging.WARNING)
SRC = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SRC)

from helpers.config import get_settings
from evaluation.ragas_evaluator import RAGASEvaluator

GEN_FILE = "ablation_generations.json"
RESULTS = "ablation_results.json"

# Judge provider rotation. Each entry is tried in order until one returns a
# clean result. Multiple Groq/Gemini keys give extra rate-limit headroom.
GROQ_KEYS = [
    "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",   # FRESH (key #1 exhausted its 500k/day)
    "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",
]
CEREBRAS_KEYS = [
    "csk-r94w8j23ettr9eex9m2trre3end329ekfvwyy2h3dmd53ern",
]
GEMINI_KEYS = [
    "AQ.Ab8RN6LwO99GLldKhxAXk2t6j4bthenjY2TpeHEBf4f8zfhSnA",
    "AQ.Ab8RN6LQnAkkHi99-8KjF4-Zjt6XPHDKtX8mx2UOKvu3rqWU6w",
    "AQ.Ab8RN6KyKwpoP_2mOUSnG71vSOXJ_r_tgbQJeOdkxdIodPUNTg",
    "AQ.Ab8RN6KLdw9-nG6r9vQ-7sMcD5cFGCv9Oy7-JabO3cHOOtivOg",
]
# (provider_kind, key) rotation order: Groq first (fast), then Cerebras, then Gemini.
PROVIDERS = (
    [("groq", k) for k in GROQ_KEYS]
    + [("cerebras", k) for k in CEREBRAS_KEYS]
    + [("gemini", k) for k in GEMINI_KEYS]
)


def make_evaluator(provider, s):
    """Build a RAGASEvaluator pinned to ONE judge (kind, key) so each fallback
    is deterministic."""
    kind, key = provider
    if kind == "groq":
        ev = RAGASEvaluator(groq_api_key=key, timeout=900)
        ev.oc_api_key = None; ev.gemini_api_key = None
        ev._use_openai_compat = False; ev._use_gemini = False
    elif kind == "cerebras":
        ev = RAGASEvaluator(
            openai_compat_api_key=key,
            openai_compat_base_url="https://api.cerebras.ai/v1",
            openai_compat_model="gpt-oss-120b", timeout=1800)
        ev.gemini_api_key = None
        ev._use_openai_compat = True; ev._use_gemini = False
    elif kind == "gemini":
        ev = RAGASEvaluator(gemini_api_key=key, timeout=1800)
        ev.oc_api_key = None
        ev._use_openai_compat = False; ev._use_gemini = True
    else:
        raise ValueError(kind)
    return ev


def load(path, default):
    if os.path.exists(path):
        try:
            return json.load(open(path))
        except Exception:
            return default
    return default


def is_good(scores):
    return scores.get("overall", 0) > 0 and scores.get("eval_success_rate", 0) >= 0.85


async def main():
    s = get_settings()
    gens = load(GEN_FILE, {})
    if not gens:
        raise SystemExit(f"{GEN_FILE} not found — run ablation_generate.py first.")
    results = load(RESULTS, {})

    for key, gen in gens.items():
        cfg = gen["config"]
        if key in results and is_good(results[key].get("scores", {})):
            print(f"SKIP {cfg} (already judged, EvalSR ok)", flush=True)
            continue

        test_cases = gen["test_cases"]
        best = None
        for prov in PROVIDERS:
            kind, api_key = prov   # NOT `key` — that holds the config name (results dict key)
            tag = f"{kind}(...{api_key[-4:]})"
            print(f"JUDGE {cfg} via {tag} ...", flush=True)
            ev = make_evaluator(prov, s)
            # evaluate() mutates its input — pass deep-ish copies
            tcs = [dict(tc) for tc in test_cases]
            try:
                scores = await ev.evaluate(tcs)
            except Exception as e:
                print(f"  {tag} ERROR: {type(e).__name__}: {e}", flush=True)
                continue
            per_q_scores = list(getattr(ev, "last_per_question", []) or [])
            sr = scores.get("eval_success_rate", 0)
            print(f"  {tag}: overall={scores.get('overall')}, EvalSR={sr}, "
                  f"none={scores.get('none_counts')}", flush=True)
            if best is None or (scores.get("overall", 0) > 0 and
                                scores.get("eval_success_rate", 0) >
                                best[1].get("eval_success_rate", 0)):
                best = (kind, scores, per_q_scores)
            if is_good(scores):
                best = (kind, scores, per_q_scores)
                break
            print(f"  -> insufficient, trying next provider", flush=True)

        prov, scores, per_q_scores = best
        # Merge judge per-question metric scores with answer/contexts/gt
        per_q = []
        for i, tc in enumerate(test_cases):
            rec = dict(per_q_scores[i]) if i < len(per_q_scores) else {}
            rec["answer"] = tc.get("answer", "")
            rec["ground_truth"] = tc.get("ground_truth", "")
            rec["contexts"] = tc.get("contexts", [])
            per_q.append(rec)

        results[key] = {
            "dataset": gen["dataset"], "config": cfg, "collection": gen["collection"],
            "flags": gen["flags"],
            "scores": scores,
            "judge_provider": prov,                      # provenance
            "avg_latency_ms": gen["avg_latency_ms"],     # FROZEN from phase 1
            "batch_ms": gen["batch_ms"],
            "num_cases": gen["num_cases"],
            "per_question": per_q,
            "test_details": gen["test_details"],         # frozen timings
        }
        json.dump(results, open(RESULTS, "w"), indent=2)
        print(f"SAVED {cfg}: judge={prov}, overall={scores.get('overall')}, "
              f"EvalSR={scores.get('eval_success_rate')}\n", flush=True)

    print("JUDGING DONE.", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
