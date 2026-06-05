"""
this file builds the few-shot example bank from labeled CSV sources , and you can add more test 
banks by drop your labeled CSV under data/processed/ and append a dict to SOURCES:
    {"name": "<short-id>", "path": "<csv-file>",
    "question_col": "<col>", "level_col": "<col>"}

run command: python scripts/build_example_bank.py

outputs:
    data/processed/example_bank.jsonl                — one JSON per question (question, level, source)
    data/processed/example_bank_embeddings.npy       — (N, 384) float32, L2-normalized so dot product = cosine
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path
from sentence_transformers import SentenceTransformer
from collections import Counter

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
PROC = ROOT / "data" / "processed"
OUT_JSONL = PROC / "example_bank.jsonl"
OUT_NPY   = PROC / "example_bank_embeddings.npy"

csv.field_size_limit(sys.maxsize)

EMBED_MODEL_DEFAULT = "sentence-transformers/all-MiniLM-L6-v2"

SOURCES: list[dict] = [
    # {
    # "name": "srm",
    # "path": "srm_questions.csv",
    # "question_col": "question",
    # "level_col":    "level"
    # },
    
    {
    "name": "os_bank",
    "path": "os_labeled.csv",
    "question_col": "question",
    "level_col":    "level"
    },
]

# Curated high-quality OS questions added to enrich the bank and improve
# ICL retrieval quality across all 6 topics × 3 difficulty levels.
# Source: expert-authored questions aligned to Bloom's Taxonomy.
CURATED_ENTRIES: list[dict] = [
    # ── EASY (Recall) ──────────────────────────────────────────────────────────
    {"question": "What is the convoy effect in FCFS scheduling and why does it degrade performance?", "level": "easy"},
    {"question": "Define turnaround time and waiting time for a process in CPU scheduling.", "level": "easy"},
    {"question": "State the four necessary conditions for deadlock.", "level": "easy"},
    {"question": "What is a safe state in the context of deadlock avoidance?", "level": "easy"},
    {"question": "What is a page fault and under what condition does it occur?", "level": "easy"},
    {"question": "What does the TLB stand for and what is its purpose in virtual memory?", "level": "easy"},
    {"question": "List the resources that threads within the same process share and the resources each thread owns privately.", "level": "easy"},
    {"question": "What is the difference between PCS and SCS scheduling in multithreaded systems?", "level": "easy"},
    {"question": "Define mutual exclusion as a requirement for a critical section solution.", "level": "easy"},
    {"question": "What two atomic operations can be performed on a semaphore, and what does each do?", "level": "easy"},
    {"question": "What metadata does an inode store about a file?", "level": "easy"},
    {"question": "Why does the lseek() system call fail on pipes and sockets?", "level": "easy"},

    # ── MEDIUM — Apply (computation / procedural / tracing) ───────────────────
    {"question": "Processes P1 (burst=5ms), P2 (burst=2ms), P3 (burst=8ms) all arrive at t=0. Draw the Gantt chart under FCFS and compute the average waiting time.", "level": "medium"},
    {"question": "Using Round Robin with time quantum=3ms, schedule P1(burst=9ms), P2(burst=4ms), P3(burst=6ms) all arriving at t=0. Compute the completion time of each process.", "level": "medium"},
    {"question": "Given Allocation=[[1,0],[0,1]], Max=[[2,1],[1,2]], Available=[1,1], apply Banker's algorithm step-by-step to find the safe sequence.", "level": "medium"},
    {"question": "Process P0 requests [1,0] resources. Allocation=[[0,1],[1,0]], Max=[[2,1],[1,1]], Available=[1,0]. Use Banker's algorithm to determine if the request should be granted.", "level": "medium"},
    {"question": "A virtual memory system has memory access time=200ns and page-fault service time=8ms. If page-fault rate p=0.001, calculate the effective access time.", "level": "medium"},
    {"question": "A system uses 32-bit virtual addresses with a page size of 8KB. How many bits are used for the page offset? How many entries does the page table have?", "level": "medium"},
    {"question": "A process has 4 user-level threads mapped to 1 kernel thread (many-to-one). Thread T1 makes a blocking I/O call lasting 50ms. How many of the 4 threads can execute during this period? Explain why.", "level": "medium"},
    {"question": "On a dual-core system using one-to-one threading, a process has 3 kernel threads: T1 (running), T2 (ready), T3 (blocked on I/O). How many threads run in parallel? What changes when T3's I/O completes?", "level": "medium"},
    {"question": "Semaphore S is initialized to 1. Trace the semaphore value and process states step-by-step as P1 calls wait(S), then P2 calls wait(S), then P1 calls signal(S).", "level": "medium"},
    {"question": "Two processes execute: P1 does wait(A) then wait(B); P2 does wait(B) then wait(A). A=1, B=1. Trace an interleaving that leads to deadlock, showing semaphore values at each step.", "level": "medium"},
    {"question": "A file has 5 data blocks. Using linked allocation with disk seek time=10ms per block, calculate the total time to read the 5th block. Repeat for indexed allocation and compare.", "level": "medium"},
    {"question": "An inode has 12 direct pointers and 1 single-indirect pointer. Block size=4KB, pointer size=4B. Calculate the maximum file size this inode can address using only direct and single-indirect blocks.", "level": "medium"},
    # ── MEDIUM — Analyze (explain / compare / relationship) ───────────────────
    {"question": "Explain how Round Robin with a very small time quantum differs from SRTF in terms of context-switch overhead and average turnaround time.", "level": "medium"},
    {"question": "Compare deadlock prevention and deadlock avoidance: which of the four necessary conditions does each strategy target, and how does each affect resource utilization?", "level": "medium"},
    {"question": "Explain why FIFO page replacement can suffer from Belady's anomaly while LRU cannot.", "level": "medium"},
    {"question": "Compare user-level threads and kernel-level threads in terms of what happens when one thread makes a blocking system call.", "level": "medium"},
    {"question": "Compare spinlocks and blocking semaphores in terms of CPU utilization and the conditions under which each is more appropriate.", "level": "medium"},
    {"question": "Compare linked file allocation and indexed file allocation for a workload that requires frequent random access to large files.", "level": "medium"},

    # ── HARD (Evaluate) ────────────────────────────────────────────────────────
    {"question": "Evaluate the suitability of Round Robin versus SRTF for a real-time operating system. Address predictability, worst-case response time, and context-switch overhead, then justify your choice.", "level": "hard"},
    {"question": "A system designer must choose between SJF and Multilevel Feedback Queue scheduling. Analyze the trade-offs regarding knowledge requirements, starvation risk, and adaptability, and recommend one with justification.", "level": "hard"},
    {"question": "Design a resource-allocation policy for a database server that prevents deadlock without Banker's algorithm. Justify why your chosen prevention strategy is practical for this workload.", "level": "hard"},
    {"question": "Evaluate the trade-offs between deadlock detection with recovery and deadlock avoidance with Banker's algorithm. Under what system conditions would you choose detection over avoidance?", "level": "hard"},
    {"question": "Design a frame-allocation and page-replacement strategy for an OS experiencing thrashing. Justify your choices and explain how the working-set model guides frame allocation decisions.", "level": "hard"},
    {"question": "Evaluate the impact of doubling the page size from 4 KB to 8 KB on page table size, TLB hit rate, and internal fragmentation. Under what workload would larger pages be beneficial?", "level": "hard"},
    {"question": "Evaluate whether the one-to-one threading model is always preferable to the many-to-many model on modern multicore hardware. Describe a scenario where many-to-many remains justified.", "level": "hard"},
    {"question": "A server must handle 10,000 simultaneous connections with blocking I/O. Design a threading strategy, choose a threading model, and justify every design decision considering kernel overhead and responsiveness.", "level": "hard"},
    {"question": "Evaluate the risks of using binary semaphores versus monitors for protecting a complex shared data structure. Justify which mechanism provides safer concurrency control and under what conditions.", "level": "hard"},
    {"question": "Design a solution to the dining philosophers problem using semaphores that avoids both deadlock and starvation. Justify every semaphore operation order and initialization value.", "level": "hard"},
    {"question": "Evaluate the suitability of contiguous, linked, and indexed file allocation for a multimedia streaming service that reads large files sequentially and occasionally appends. Justify which method or hybrid you would choose.", "level": "hard"},
    {"question": "Evaluate how the Unix inode design (direct pointers + single/double/triple indirect) handles files ranging from 1 KB to 10 GB. Identify any structural limitations and propose a mitigation.", "level": "hard"},
]

_LEADING_NUM_RE = re.compile(r"^\s*\d{1,3}\s*[\.\-\)\\]+\s*")

def strip_leading_number(q: str) -> str:
    return _LEADING_NUM_RE.sub("", q).strip()

def is_valid_entry_for_question_field(q: str) -> bool:
    """only reject not valid entries"""
    q = strip_leading_number(q)
    return bool(q) and len(q) >= 12 and len(q.split()) >= 3

def load_source(config: dict) -> list[dict]:
    raw_path = config.get("path")
    if not raw_path:
        print(f"skip {config.get('name')}: no 'path' configured")
        return []
    path = Path(raw_path)
    if not path.is_absolute():
        path = PROC / raw_path
    if not path.exists():
        print(f"skip {config['name']}: {path} not found")
        return []

    q_col, l_col = config["question_col"], config["level_col"]
    rows = []
    skipped_level = skipped_validty = 0
    with path.open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            level = (r.get(l_col) or "").lower().strip()
            if level not in {"easy", "medium", "hard"}:
                skipped_level += 1
                continue
            question = r.get(q_col) or ""
            if not is_valid_entry_for_question_field(question):
                skipped_validty += 1
                continue
            rows.append({
                "question": strip_leading_number(question),
                "level":    level,
                "source":   config["name"],
            })
    # logging
    message = f"loaded {len(rows):>6} from {config['name']:<14} ({path.name})"
    if skipped_level + skipped_validty:
        message += f"skipped level={skipped_level} validty={skipped_validty}"
    print(message)
    return rows


def embed_all(texts: list[str], model_name: str) -> np.ndarray:
    """embed every question once """
    model = SentenceTransformer(model_name)
    print(f"  embedding {len(texts)} questions with {model_name}...")
    embs = model.encode(
        texts, batch_size=64, show_progress_bar=True,
        convert_to_numpy=True, normalize_embeddings=True,
    )
    return embs.astype(np.float32)


def main() -> int:
    argument_parser = argparse.ArgumentParser()
    argument_parser.add_argument("--embed-model", default=EMBED_MODEL_DEFAULT,
                    help=f"sentence-transformers model (default: {EMBED_MODEL_DEFAULT})")
    args = argument_parser.parse_args()

    all_rows: list[dict] = []
    for config in SOURCES:
        all_rows.extend(load_source(config))

    # Add curated questions (validated inline, not from CSV)
    curated = [
        {"question": e["question"], "level": e["level"], "source": "curated_os"}
        for e in CURATED_ENTRIES
        if is_valid_entry_for_question_field(e["question"])
    ]
    print(f"loaded {len(curated):>6} from curated_os      (inline)")
    all_rows.extend(curated)

    if not all_rows:
        print("ERROR: no rows loaded. Check SOURCES paths and column names",
            file=sys.stderr)
        return 1

    # dedupe by question text.
    seen: dict[str, dict] = {}
    for r in all_rows:
        seen.setdefault(r["question"].lower().strip(), r)
    entries = list(seen.values())
    print(f"length after dedupe: {len(entries)}")

    # compute embeddings and save them into .npy
    questions = [r["question"] for r in entries]
    embs = embed_all(questions, args.embed_model)
    np.save(OUT_NPY, embs)

    # write text JSONL file in parallel with the .npy
    with OUT_JSONL.open("w", encoding="utf-8") as f:
        for r in entries:
            f.write(json.dumps({
                "question": r["question"],
                "level":    r["level"],
                "source":   r["source"],
            }, ensure_ascii=False) + "\n")
    
    # check composition
    each_level_counts = Counter(r["level"] for r in entries)
    each_source_source = Counter(r["source"] for r in entries)
    print(f"\nTest Banks composition:")
    print(f"by level:  {dict(each_level_counts)}")
    print(f"by source: {dict(each_source_source)}")
    print(f"total:     {len(entries)} entries")
    return 0

if __name__ == "__main__":
    sys.exit(main())