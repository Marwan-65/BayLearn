"""
for each (test chunk, target_level), this script generates N questions in:
- baseline:  the LLM only sees the chunk + bloom guidance
- ICL:       the baseline + with the few-shot example bank

metrics for measuring performance difference:
For each batch of N questions at requested level L:
    level_match_rate (LMR)    — % of N where BloomBERT prediction == L
                                (higher = better difficulty control)
    mean_confidence            — average BloomBERT confidence on its own
                                predictions (higher = more decisive)
    mean_target_prob           — average BloomBERT P(L) on the target class
                                (higher = closer to requested level even
                                if argmax disagrees)
    mean_words                 — average words per question
                                (should correlate with target level — easy
                                questions should be shorter than hard ones)
   distinct_2gram             — unique 2-grams / total 2-grams across the N
                                 questions (higher = more diverse, less
                                 repetitive output)
   chunk_similarity           — cosine between each question embedding and
                                 the chunk embedding, averaged
                                 (higher = more grounded in source material)
   parse_rate                 — % of LLM responses that parsed as valid JSON
                                 (higher = better format adherence)

What "better" looks like for ICL:
  → higher level_match_rate, mean_confidence, mean_target_prob (better
    Bloom-level control — the main thing ICL is supposed to deliver)
  → higher distinct_2gram (more variety, less repetition between questions)
  → mean_words should be larger for hard than easy (level-appropriate length)
  → chunk_similarity roughly equal or slightly higher (ICL shouldn't make
    questions less grounded)
  → parse_rate roughly equal (format is enforced by the prompt's OUTPUT
    FORMAT spec, not ICL)

run command:
    python scripts/eval_icl_vs_baseline.py
    python scripts/eval_icl_vs_baseline.py --num-questions 3 --levels easy,medium
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import os
import sys
from pathlib import Path
from statistics import mean
import math
from statistics import mean as _mean
from collections import Counter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:
    pass

from app.classifier.bloom_classifier import BloomClassifier, bloom6_to_level 
from app.services.example_bank import ExampleBank                             
from app.services.question_service import QuestionGenerationService           
from app.services.chunk_fetcher import ChunkFetcher                           
from app.llm.groq_client import QuestionGenLLMClient                           

OUT_DIR = ROOT / "data" / "processed"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# test chunks
# Self-contained OS topic chunks. Each is realistic exam material.
# Using fixed chunks (not RAG-fetched) so the eval is reproducible and doesn't
# depend on the RAG module being running.
TEST_CHUNKS = [
    {
        "id": "paging",
        "topic": "virtual memory and paging",
        "text": (
            "In a paging system, the virtual address space is divided into "
            "fixed-size pages and physical memory into frames of the same size. "
            "The page table maps virtual page numbers to physical frame numbers. "
            "When a process references an address whose page is not in memory, "
            "a page fault occurs and the OS must load the page from disk. "
            "Common page replacement algorithms include FIFO, LRU, and Optimal. "
            "FIFO is simple but can suffer from Belady's anomaly. LRU "
            "approximates the optimal policy by evicting the least recently "
            "used page. The TLB (Translation Lookaside Buffer) caches "
            "frequently-used page table entries to speed up address translation."
        ),
    },
    {
        "id": "scheduling",
        "topic": "CPU scheduling",
        "text": (
            "CPU scheduling determines which ready process runs next. "
            "Common policies include FCFS (First-Come First-Served), SJF "
            "(Shortest Job First), Round Robin with time quantum, and "
            "Multilevel Feedback Queue. FCFS is simple but has poor response "
            "time for short jobs behind long ones (convoy effect). SJF "
            "minimizes average waiting time but requires knowing job lengths "
            "and can starve long jobs. Round Robin gives each process a time "
            "slice (quantum); smaller quanta improve responsiveness but "
            "increase context-switch overhead. The dispatcher performs the "
            "context switch by saving and restoring process state."
        ),
    },
    {
        "id": "synchronization",
        "topic": "process synchronization",
        "text": (
            "Concurrent processes accessing shared resources require "
            "synchronization to prevent race conditions. A critical section "
            "is the portion of code that accesses shared data. Solutions must "
            "satisfy mutual exclusion, progress, and bounded waiting. "
            "Semaphores are integer variables accessed only through atomic "
            "wait (P) and signal (V) operations. Mutexes provide mutual "
            "exclusion for a single resource. Monitors are higher-level "
            "constructs that bundle data and operations. Deadlock occurs "
            "when processes hold resources and wait indefinitely for resources "
            "held by others. The four necessary conditions are mutual "
            "exclusion, hold-and-wait, no preemption, and circular wait."
        ),
    },
    {
        "id": "filesystem",
        "topic": "file systems",
        "text": (
            "A file system organizes how data is stored and retrieved on "
            "secondary storage. Files are identified by name and accessed "
            "through file descriptors. Directory structures can be "
            "single-level, two-level, tree, or acyclic graph. Inodes store "
            "file metadata including ownership, permissions, size, and "
            "pointers to data blocks. Allocation methods include contiguous, "
            "linked, and indexed allocation. Contiguous allocation gives "
            "fast access but suffers external fragmentation. Linked "
            "allocation eliminates fragmentation but has poor random-access "
            "performance. Indexed allocation uses an index block to support "
            "direct access while remaining flexible."
        ),
    },
    {
        "id": "deadlock",
        "topic": "deadlock detection and recovery",
        "text": (
            "Deadlock prevention strategies eliminate at least one of the "
            "four necessary conditions. Deadlock avoidance, exemplified by "
            "Banker's algorithm, requires advance knowledge of maximum "
            "resource needs. The system maintains state information to "
            "decide whether granting a resource request leaves the system "
            "in a safe state. Detection algorithms periodically check the "
            "resource allocation graph for cycles. Recovery options include "
            "process termination (abort all or one-at-a-time until cycle "
            "breaks) and resource preemption (taking resources from victims "
            "and rolling back). Selection of victims considers process "
            "priority, computation completed, and resources held."
        ),
    },
]


def make_fake_chunk_fetcher(chunk_text: str, chunk_id: str):
    class _FakeFetcher:
        async def fetch_relevant_chunks(self, project_id, query, limit=20):
            return [{
                "id": 0,
                "payload": {
                    "text": chunk_text,
                    "doc_id": chunk_id,
                    "metadata": {"doc_title": chunk_id},
                },
            }]
    return _FakeFetcher()



def distinct_n_grams(questions: list[str], n: int = 2) -> float:
    grams: list[tuple[str, ...]] = []
    for q in questions:
        toks = q.lower().split()
        grams.extend(tuple(toks[i:i + n]) for i in range(len(toks) - n + 1))
    if not grams:
        return 0.0
    return len(set(grams)) / len(grams)


def _bleu_4(hyp: list[str], refs: list[list[str]]) -> float:
    if not hyp or not refs:
        return 0.0
    weights = [0.25, 0.25, 0.25, 0.25]
    log_precisions = []
    for n in range(1, 5):
        hyp_ngrams = Counter(tuple(hyp[i:i + n]) for i in range(len(hyp) - n + 1))
        if not hyp_ngrams:
            log_precisions.append(math.log(1e-9))
            continue
        max_ref = Counter()
        for ref in refs:
            ref_ngrams = Counter(tuple(ref[i:i + n]) for i in range(len(ref) - n + 1))
            for k, v in ref_ngrams.items():
                if v > max_ref[k]:
                    max_ref[k] = v
        clipped = sum(min(c, max_ref[k]) for k, c in hyp_ngrams.items())
        total = sum(hyp_ngrams.values())
        if clipped == 0:
            # add tiny epsilon so log doesn't explode
            log_precisions.append(math.log(0.5 / max(total, 1)))
        else:
            log_precisions.append(math.log(clipped / total))
    hyp_len = len(hyp)
    closest_ref_len = min((len(r) for r in refs),
                        key=lambda l: (abs(l - hyp_len), l))
    bp = 1.0 if hyp_len > closest_ref_len else math.exp(1 - closest_ref_len / max(hyp_len, 1))
    return bp * math.exp(sum(w * lp for w, lp in zip(weights, log_precisions)))



def avg_self_bleu(questions: list[str]) -> float:
    """
    used as the headline diversity metric in Zhu et al. 2018.
    """
    if len(questions) < 2:
        return 0.0
    tokenized = [q.lower().split() for q in questions]
    scores = []
    for i, hyp in enumerate(tokenized):
        refs = [tokenized[j] for j in range(len(tokenized)) if j != i]
        scores.append(_bleu_4(hyp, refs))
    return _mean(scores)


def cosine_sim(a, b) -> float:
    import numpy as np
    a = np.asarray(a); b = np.asarray(b)
    na = float(np.linalg.norm(a)) or 1.0
    nb = float(np.linalg.norm(b)) or 1.0
    return float(a @ b / (na * nb))


# main eval
async def run_one_condition(service, target_level_b6: str, target_level_3: str,
                            num_questions: int) -> tuple[list, float]:
    """Run generation once, return (questions, parse_success_flag).

    parse_success_flag is 1.0 if the LLM returned valid JSON that parsed into
    GeneratedQuestion objects, 0.0 if it raised, fractional if partial.
    """
    try:
        questions, _ = await service.generate(
            project_id="eval-stub",   # not used by fake fetcher
            num_questions=num_questions,
            difficulty=target_level_b6,
            question_type="short_answer",
            topic=None,
        )
        parse_rate = 1.0 if questions else 0.0
        return questions, parse_rate
    except Exception as e:
        print(f"    [warn] generation failed: {e}")
        return [], 0.0


def summarize_batch(questions, target_level_3: str, classifier,
                    chunk_emb, embedder) -> dict:
    """Compute the metric dict for one batch of generated questions."""
    if not questions:
        return {
            "n": 0, "level_match_rate": 0.0, "mean_confidence": 0.0,
            "mean_target_prob": 0.0, "mean_words": 0.0,
            "distinct_2gram": 0.0, "self_bleu": 0.0, "chunk_similarity": 0.0,
        }
    q_texts = [q.question_text for q in questions]
    preds   = classifier.predict_batch(q_texts)
    match   = [1 if p.level == target_level_3 else 0 for p in preds]
    confs   = [p.confidence for p in preds]
    target_probs = [
        (p.probs or {}).get(target_level_3, 0.0) for p in preds
    ]
    word_counts = [len(q.split()) for q in q_texts]
    # Embed each question and compute cosine vs chunk
    q_emb = embedder.encode(q_texts, convert_to_numpy=True,
                            show_progress_bar=False, normalize_embeddings=True)
    sims = [cosine_sim(qv, chunk_emb) for qv in q_emb]

    return {
        "n":                len(questions),
        "level_match_rate": mean(match),
        "mean_confidence":  mean(confs),
        "mean_target_prob": mean(target_probs),
        "mean_words":       mean(word_counts),
        "distinct_2gram":   distinct_n_grams(q_texts, n=2),
        "self_bleu":        avg_self_bleu(q_texts),
        "chunk_similarity": mean(sims),
    }


async def main_async(args):
    print("Loading BloomBERT classifier")
    classifier = BloomClassifier.load(ROOT / "models" / "bloom_distilbert")
    if classifier.model is None:
        print("classifier in stub mode — train + place weights first.",
              file=sys.stderr)
        return 1

    bank = ExampleBank.load(ROOT / "data" / "processed" / "example_bank.jsonl")
    if not bank.entries:
        print("empty example bank, run build_example_bank.py first.",
              file=sys.stderr)
        return 1
    embedder = bank._lazy_model()  # reuse the bank's embedding model

    # embed each test chunk once
    chunk_embs = {
        ch["id"]: embedder.encode([ch["text"]], convert_to_numpy=True,show_progress_bar=False,
        normalize_embeddings=True)[0]
        for ch in TEST_CHUNKS
    }

    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        print("GROQ_API_KEY not set. Put it in .env or export it.",file=sys.stderr)
        return 1
    model_id = os.environ.get("GROQ_MODEL_ID", "llama-3.1-70b-versatile")
    llm_client = QuestionGenLLMClient(api_key=api_key, model_id=model_id)

    levels_b6 = args.levels.split(",")
    # Map 6-level requested → 3-level target for evaluation
    levels_3 = [bloom6_to_level(l.strip()) for l in levels_b6]

    print(f"\nRunning {len(TEST_CHUNKS)} chunks × {len(levels_b6)} levels × "
          f"{args.num_questions} questions × 2 conditions = "
          f"{len(TEST_CHUNKS) * len(levels_b6) * args.num_questions * 2} "
          f"LLM calls.")

    #  for each (chunk, level), run both conditions 
    all_rows = []
    aggregate = {
        ("baseline", l): [] for l in levels_3
    }
    aggregate.update({("icl", l): [] for l in levels_3})
    parse_rates = {"baseline": [], "icl": []}

    for chunk in TEST_CHUNKS:
        fake_fetcher = make_fake_chunk_fetcher(chunk["text"], chunk["id"])
        for level_b6, level_3 in zip(levels_b6, levels_3):
            print(f"\n[{chunk['id']:<16}] level={level_b6} (3-class: {level_3})")
            #  baseline 
            svc_no_icl = QuestionGenerationService(
                llm_client=llm_client, chunk_fetcher=fake_fetcher,
                example_bank=None, bloom_classifier=None,  # disable retry too
                few_shot_k=0, retry_on_level_mismatch=False,
            )
            qs_base, prate_b = await run_one_condition(
                svc_no_icl, level_b6, level_3, args.num_questions,
            )
            parse_rates["baseline"].append(prate_b)
            m_base = summarize_batch(qs_base, level_3, classifier, chunk_embs[chunk["id"]], embedder)
            aggregate[("baseline", level_3)].append(m_base)
            for q in qs_base:
                all_rows.append({
                    "chunk_id": chunk["id"], "target_level_b6": level_b6,
                    "target_level_3": level_3, "condition": "baseline",
                    "question": q.question_text,
                    "predicted_level": q.predicted_level or "",
                    "level_confidence": q.level_confidence or "",
                    "n_words": len(q.question_text.split()),
                })
            print(f"  baseline: LMR={m_base['level_match_rate']:.2f} "
                f"conf={m_base['mean_confidence']:.2f} "
                f"words={m_base['mean_words']:.0f} "
                f"distinct2={m_base['distinct_2gram']:.2f}")

            # ICL 
            svc_icl = QuestionGenerationService(
                llm_client=llm_client, chunk_fetcher=fake_fetcher,
                example_bank=bank, bloom_classifier=classifier,
                few_shot_k=4, retry_on_level_mismatch=False,
            )
            qs_icl, prate_i = await run_one_condition(
                svc_icl, level_b6, level_3, args.num_questions,
            )
            parse_rates["icl"].append(prate_i)
            m_icl = summarize_batch(qs_icl, level_3, classifier,
                                    chunk_embs[chunk["id"]], embedder)
            aggregate[("icl", level_3)].append(m_icl)
            for q in qs_icl:
                all_rows.append({
                    "chunk_id": chunk["id"], "target_level_b6": level_b6,
                    "target_level_3": level_3, "condition": "icl",
                    "question": q.question_text,
                    "predicted_level": q.predicted_level or "",
                    "level_confidence": q.level_confidence or "",
                    "n_words": len(q.question_text.split()),
                })
            print(f"  icl:      LMR={m_icl['level_match_rate']:.2f} "
                f"conf={m_icl['mean_confidence']:.2f} "
                f"words={m_icl['mean_words']:.0f} "
                f"distinct2={m_icl['distinct_2gram']:.2f}")

    #  print summary 
    print("\n" + "=" * 92)
    print("AGGREGATE RESULTS (averaged across chunks per level)")
    print("=" * 92)
    print(f"{'level':<8}{'condition':<10}{'LMR':>8}{'conf':>8}{'targetP':>9}"
          f"{'words':>8}{'distinct2':>11}{'selfBLEU':>10}{'chunkSim':>10}")
    for lvl in levels_3:
        for cond in ("baseline", "icl"):
            batches = aggregate[(cond, lvl)]
            if not batches:
                continue
            avg = {k: mean(b[k] for b in batches if b["n"] > 0)
                   for k in ("level_match_rate", "mean_confidence",
                             "mean_target_prob", "mean_words",
                             "distinct_2gram", "self_bleu", "chunk_similarity")}
            print(f"{lvl:<8}{cond:<10}"
                  f"{avg['level_match_rate']:>8.3f}"
                  f"{avg['mean_confidence']:>8.3f}"
                  f"{avg['mean_target_prob']:>9.3f}"
                  f"{avg['mean_words']:>8.1f}"
                  f"{avg['distinct_2gram']:>11.3f}"
                  f"{avg['self_bleu']:>10.3f}"
                  f"{avg['chunk_similarity']:>10.3f}")
        print()
    print("Interpretation:")
    print("  LMR / targetP / chunkSim / distinct2  → HIGHER is better")
    print("  self_bleu                              → LOWER  is better (less duplication)")
    print("  conf, words                            → context-dependent (compare per level)")

    print(f"parse_rate (% LLM responses that parsed as valid JSON):")
    print(f"  baseline: {mean(parse_rates['baseline']):.2f}")
    print(f"  icl:      {mean(parse_rates['icl']):.2f}")

    #  write per-question CSV 
    out_csv = OUT_DIR / "eval_icl_vs_baseline_generations.csv"
    with out_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=[
            "chunk_id", "target_level_b6", "target_level_3", "condition",
            "question", "predicted_level", "level_confidence", "n_words",
        ])
        w.writeheader()
        for row in all_rows:
            w.writerow(row)
    print(f"\nPer-question generations written to {out_csv}")
    print("Open it side-by-side with the metrics table above to review "
        "question quality manually.")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--num-questions", type=int, default=5,
                    help="questions per (chunk, level, condition) (default: 5)")
    ap.add_argument("--levels", default="remember,apply,evaluate",
                    help="comma-separated 6-level Bloom names to test "
                        "(default: remember,apply,evaluate — one per 3-class bucket)")
    args = ap.parse_args()
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    sys.exit(main())
