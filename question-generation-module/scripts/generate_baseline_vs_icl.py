"""
generate baseline vs ICL question sets for the LLM-judge comparison.

for each (chunk, bloom_level) it generates N questions twice:
  baseline — chunk + bloom guidance only
  icl      — same prompt plus the few-shot example bank

output: data/processed/baseline_vs_icl_generations.csv
        columns: chunk_id, bloom_level, condition, question

run command:
    python scripts/generate_baseline_vs_icl.py
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:
    pass

from app.services.example_bank import ExampleBank
from app.services.question_service import QuestionGenerationService
from app.llm.groq_client import QuestionGenLLMClient
try:
    from app.llm.gemini_client import GeminiQuestionGenClient
except ImportError:
    GeminiQuestionGenClient = None

OUT_DIR = ROOT / "data" / "processed"
OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT_CSV = OUT_DIR / "baseline_vs_icl_generations.csv"

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


async def generate_once(service, bloom_level: str, num_questions: int,
                        include_guidance: bool = True) -> list:
    try:
        questions, _ = await service.generate(
            project_id="gen-stub",
            num_questions=num_questions,
            difficulty=bloom_level,
            question_type="short_answer",
            topic=None,
            include_guidance=include_guidance,
        )
        return questions
    except Exception as e:
        print(f"    generation failed: {e}")
        return []


def make_llm_client():
    provider = (os.environ.get("LLM_PROVIDER", "groq") or "groq").lower()
    if provider == "gemini":
        if GeminiQuestionGenClient is None:
            raise RuntimeError("google-genai not installed")
        key = os.environ.get("GEMINI_API_KEY")
        if not key:
            raise RuntimeError("GEMINI_API_KEY not set")
        model = os.environ.get("GEMINI_MODEL_ID", "gemini-2.5-flash-lite")
        return GeminiQuestionGenClient(api_key=key, model_id=model), 4.0, model
    key = os.environ.get("GROQ_API_KEY")
    if not key:
        raise RuntimeError("GROQ_API_KEY not set")
    model = os.environ.get("GROQ_MODEL_ID", "meta-llama/llama-4-scout-17b-16e-instruct")
    return QuestionGenLLMClient(api_key=key, model_id=model), 1.0, model


async def main_async(args) -> int:
    bank = ExampleBank.load(ROOT / "data" / "processed" / "example_bank.jsonl")
    if not bank.entries:
        print("empty example bank, run build_example_bank.py first.", file=sys.stderr)
        return 1

    try:
        llm_client, default_sleep, model_id = make_llm_client()
    except RuntimeError as e:
        print(e, file=sys.stderr)
        return 1
    sleep_secs = float(os.environ.get("SLEEP_BETWEEN_CALLS", default_sleep))
    print(f"Using {model_id}, sleeping {sleep_secs:.1f}s between calls")

    bloom_levels = [l.strip() for l in args.levels.split(",")]
    rows = []

    for chunk in TEST_CHUNKS:
        fetcher = make_fake_chunk_fetcher(chunk["text"], chunk["id"])
        for bloom_level in bloom_levels:
            print(f"\n[{chunk['id']}] {bloom_level}")

            baseline_service = QuestionGenerationService(
                llm_client=llm_client, chunk_fetcher=fetcher,
                example_bank=None, bloom_classifier=None,
                few_shot_k=0, retry_on_level_mismatch=False,
            )
            for q in await generate_once(baseline_service, bloom_level, args.num_questions):
                rows.append({"chunk_id": chunk["id"], "bloom_level": bloom_level,
                             "condition": "baseline", "question": q.question_text})
            print("  baseline done")
            if sleep_secs > 0:
                time.sleep(sleep_secs)

            icl_service = QuestionGenerationService(
                llm_client=llm_client, chunk_fetcher=fetcher,
                example_bank=bank, bloom_classifier=None,
                few_shot_k=3, retry_on_level_mismatch=False,
            )
            # ICL = examples + explicit guidance (the current production prompt).
            for q in await generate_once(icl_service, bloom_level, args.num_questions,
                                         include_guidance=True):
                rows.append({"chunk_id": chunk["id"], "bloom_level": bloom_level,
                             "condition": "icl", "question": q.question_text})
            print("  icl done")
            if sleep_secs > 0:
                time.sleep(sleep_secs)

            # Ablation arm: examples ONLY, no explicit difficulty guidance — isolates
            # whether the exemplars alone carry the difficulty signal.
            for q in await generate_once(icl_service, bloom_level, args.num_questions,
                                         include_guidance=False):
                rows.append({"chunk_id": chunk["id"], "bloom_level": bloom_level,
                             "condition": "examples_only", "question": q.question_text})
            print("  examples_only done")
            if sleep_secs > 0:
                time.sleep(sleep_secs)

    with OUT_CSV.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["chunk_id", "bloom_level", "condition", "question"])
        w.writeheader()
        for row in rows:
            w.writerow(row)
    print(f"\nWrote {len(rows)} generations to {OUT_CSV}")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--num-questions", type=int, default=5)
    ap.add_argument("--levels", default="remember,apply,evaluate")
    args = ap.parse_args()
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    sys.exit(main())
