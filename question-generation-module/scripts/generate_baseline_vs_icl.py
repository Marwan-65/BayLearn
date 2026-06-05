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

sys.path.insert(0, str(ROOT.parent))  # Add BayLearn root to path to resolve question_generation_model

from app.services.example_bank import ExampleBank
from app.services.question_service import QuestionGenerationService
from question_generation_model._gen_llm import make_llm_client

OUT_DIR = ROOT / "data" / "processed"
OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT_CSV = OUT_DIR / "baseline_vs_icl_generations.csv"

# Each chunk is structured to include Facts, Algorithms, Behavior, Concepts,
# Metrics, and Trade-offs so the LLM has enough material to construct questions
# at all three difficulty levels (easy/medium/hard) from a single chunk.
TEST_CHUNKS = [
    {
        "id": "scheduling",
        "topic": "CPU scheduling",
        "text": (
            "CPU scheduling selects which ready process runs next on the CPU.\n\n"
            "FACTS: Algorithms are preemptive (can interrupt a running process) or "
            "non-preemptive (process runs until it blocks or finishes). FCFS and "
            "basic SJF are non-preemptive; Round Robin (RR) and SRTF are preemptive. "
            "Each process has an arrival time and a CPU burst time.\n\n"
            "ALGORITHMS: FCFS serves processes in arrival order. SJF picks the "
            "shortest next burst. SRTF preempts when a shorter arrival occurs. RR "
            "assigns each process a fixed time quantum in a circular queue.\n"
            "Worked example — FCFS: P1(burst=5), P2(burst=2), P3(burst=8), all "
            "arrive at t=0. Gantt: [P1:0-5][P2:5-7][P3:7-15]. Waiting: P1=0, "
            "P2=5, P3=7, average=4ms. Turnaround: P1=5, P2=7, P3=15, average=9ms.\n"
            "SJF same processes: order P2→P1→P3. Waiting: P2=0, P1=2, P3=7, "
            "average=3ms — lower than FCFS, illustrating SJF optimality.\n"
            "RR (quantum=3): P1 runs 0-3, P2 runs 3-5 (done), P1 runs 5-8, P3 "
            "runs 8-11, P1 runs 11-13 (done), P3 runs 13-16 (done).\n\n"
            "BEHAVIOR: A timer interrupt (RR/SRTF) or I/O event triggers the "
            "scheduler. The dispatcher performs the context switch: saves the running "
            "process's state into its PCB, restores the next process's state. In "
            "FCFS the convoy effect occurs when a long job blocks shorter jobs. SJF "
            "and Priority scheduling can cause starvation; aging (gradually raising "
            "priority) is the cure.\n\n"
            "CONCEPTS: Criteria include CPU utilization, throughput, turnaround time "
            "(completion − arrival), waiting time (turnaround − burst), and response "
            "time (first response − arrival). The dispatcher is separate from the "
            "scheduler.\n\n"
            "METRICS: Average waiting time under SJF is provably minimal among all "
            "non-preemptive algorithms. Turnaround = completion − arrival. Waiting = "
            "turnaround − burst.\n\n"
            "TRADE-OFFS: A smaller RR quantum improves response time but raises "
            "context-switch overhead and total turnaround. SJF minimizes average "
            "waiting time but requires knowing future burst lengths (impractical). "
            "MLFQ adapts to behavior without advance knowledge but is complex to tune."
        ),
    },
    {
        "id": "deadlock",
        "topic": "deadlock",
        "text": (
            "Deadlock is a state where a set of processes are blocked, each waiting "
            "for a resource held by another.\n\n"
            "FACTS: Four conditions must hold simultaneously: (1) mutual exclusion — "
            "at least one resource is non-shareable; (2) hold-and-wait — a process "
            "holds resources while requesting more; (3) no preemption — resources "
            "cannot be forcibly taken; (4) circular wait — a circular chain exists. "
            "The OS tracks Allocation, Max, Need (Max − Allocation), and Available.\n\n"
            "ALGORITHMS: Banker's algorithm (avoidance): grant a request only if the "
            "resulting state is safe — there exists a sequence where every process can "
            "finish. Safety check: find P where Need[P] ≤ Available; simulate "
            "finish, release Allocation[P] to Available, repeat.\n"
            "Worked example: 2 processes, 2 resource types.\n"
            "  Allocation=[[1,0],[0,1]], Max=[[2,1],[1,2]], "
            "Need=Max-Alloc=[[1,1],[1,1]], Available=[1,1].\n"
            "  P0: Need[0]=[1,1] ≤ [1,1] → P0 runs, Available=[1,1]+[1,0]=[2,1].\n"
            "  P1: Need[1]=[1,1] ≤ [2,1] → P1 runs. Safe sequence: P0,P1.\n"
            "If P0 requests [1,0]: new Allocation[0]=[2,0], Available=[0,1]. "
            "Check: Need[0]=[0,1] ≤ [0,1] → P0 finishes → Available=[2,1]; "
            "Need[1]=[1,1] ≤ [2,1] → safe; request granted.\n"
            "Resource-allocation graph: a cycle with single-instance resources "
            "proves deadlock.\n\n"
            "BEHAVIOR: Prevention eliminates one condition before execution (e.g., "
            "require all resources at once eliminates hold-and-wait; impose a total "
            "ordering on resource types eliminates circular wait). Recovery aborts "
            "processes (all at once or one at a time) or preempts resources, choosing "
            "a victim by cost: priority, resources held, work completed.\n\n"
            "CONCEPTS: A safe state guarantees every process can eventually finish; "
            "an unsafe state may lead to deadlock but is not itself deadlock. Livelock: "
            "processes change state but make no progress.\n\n"
            "METRICS: Banker's safety check runs in O(n²·r) time (n = processes, "
            "r = resource types).\n\n"
            "TRADE-OFFS: Prevention is simple but overly conservative (poor resource "
            "utilization). Avoidance (Banker's) allows more concurrency but requires "
            "advance knowledge of maximum resource needs. Detection/recovery is most "
            "flexible but adds detection overhead and costly recovery."
        ),
    },
    {
        "id": "memory_paging",
        "topic": "virtual memory and paging",
        "text": (
            "Virtual memory lets each process use an address space larger than "
            "physical RAM; paging is the dominant implementation.\n\n"
            "FACTS: The virtual address space is divided into fixed-size pages; "
            "physical memory into equal frames. A page table maps each virtual page "
            "number (VPN) to a physical frame number. The TLB caches recently used "
            "page-table entries. When a referenced page is absent, a page fault is "
            "raised and the OS loads the page from swap space on disk.\n\n"
            "ALGORITHMS: FIFO evicts the oldest page. LRU evicts least recently "
            "used. OPT evicts the page used farthest in the future (theoretical "
            "bound). Clock approximates LRU with a reference bit.\n"
            "Worked numerical examples:\n"
            "  EAT: p=0.001, mem_time=200ns, fault_time=8,000,000ns.\n"
            "    EAT = 0.999×200 + 0.001×8,000,000 = 199.8 + 8,000 = 8,199.8ns.\n"
            "  Max allowable fault rate for EAT ≤ 220ns (10% degradation):\n"
            "    220 = (1-p)×200 + p×8,000,000 → p ≤ 20/7,999,800 ≈ 2.5×10⁻⁶.\n"
            "  Address size: 32-bit address, page=4KB=2¹² bytes → offset=12 bits,"
            " VPN=20 bits → page table has 2²⁰=1,048,576 entries; at 4B each "
            "→ 4MB page table per process.\n\n"
            "BEHAVIOR: Belady's anomaly — FIFO may fault more with more frames (LRU "
            "and OPT are immune). Thrashing: too few frames → continuous faults → "
            "CPU utilization collapses as the OS swaps instead of executing.\n\n"
            "CONCEPTS: Demand paging loads pages only on reference (lazy loading). "
            "The working set is the set of pages actively used in a recent window Δ; "
            "allocating frames to cover the working set prevents thrashing.\n\n"
            "METRICS: For a 32-bit address with 4 KB pages: offset = 12 bits, "
            "VPN = 20 bits → 2²⁰ page table entries. EAT = (1−p)×mem_time + "
            "p×fault_time, where p is the fault rate.\n\n"
            "TRADE-OFFS: Larger page size reduces page table size but increases "
            "internal fragmentation. Smaller page size wastes less space but inflates "
            "the page table. LRU better approximates OPT than FIFO but needs hardware "
            "support (reference bits or access-time registers)."
        ),
    },
    {
        "id": "threads",
        "topic": "threads and multithreading",
        "text": (
            "A thread is the basic unit of CPU execution; a process can contain "
            "one or more threads.\n\n"
            "FACTS: All threads within a process share its code, global data, heap, "
            "and open file descriptors. Each thread has its own stack, registers, "
            "program counter, and thread ID. Models: many-to-one maps all user "
            "threads to one kernel thread (no true parallelism); one-to-one maps "
            "each user thread to a kernel thread (true parallelism, kernel overhead); "
            "many-to-many multiplexes user threads onto a pool of kernel threads.\n\n"
            "ALGORITHMS: PCS (Process-Contention-Scope) scheduling is done by the "
            "user-level thread library among threads of the same process. SCS "
            "(System-Contention-Scope) is done by the kernel across all threads "
            "system-wide. In one-to-one models all scheduling is SCS.\n\n"
            "BEHAVIOR: User-level threads: a blocking syscall blocks the entire "
            "process because the kernel sees only one entity. Kernel-level threads: "
            "a blocking call suspends only the calling thread; others continue. In "
            "one-to-one, threads on different cores execute truly in parallel.\n\n"
            "CONCEPTS: A Lightweight Process (LWP) is a virtual processor the "
            "kernel schedules; the user library maps its threads onto LWPs. Benefits: "
            "responsiveness, resource sharing, economy (cheaper to create than "
            "process), scalability.\n\n"
            "METRICS: Thread creation is ~10–100× faster than process creation "
            "because no address space copy occurs.\n"
            "Worked example — blocking call impact:\n"
            "  Many-to-one: 4 user threads on 1 kernel thread. T1 calls read() "
            "(blocks 50ms) → all 4 threads stall for 50ms; CPU is idle for this "
            "process.\n"
            "  One-to-one: 4 kernel threads on dual-core. T1 blocks → T2 and T3 "
            "run in parallel on 2 cores; T4 is ready. Only T1 stalls.\n"
            "  Creation cost: fork() copies 4GB address space (~10ms); "
            "pthread_create() allocates a 8MB stack (~10μs) — ~1000× cheaper.\n\n"
            "TRADE-OFFS: User threads have low switching cost but no parallelism and "
            "are vulnerable to blocking calls. Kernel threads allow parallelism and "
            "independent blocking but consume kernel resources per thread. Many-to-"
            "many balances both but requires a complex runtime scheduler."
        ),
    },
    {
        "id": "synchronization",
        "topic": "process synchronization",
        "text": (
            "When concurrent processes or threads access shared data without "
            "coordination, correctness cannot be guaranteed.\n\n"
            "FACTS: A race condition occurs when the result of concurrent accesses "
            "depends on the exact interleaving of operations. The critical section "
            "(CS) is the code region accessing shared data. A correct CS solution "
            "must provide: (1) mutual exclusion — at most one process in the CS; "
            "(2) progress — if no process is in the CS some wanting to enter must be "
            "allowed; (3) bounded waiting — no process waits forever. A semaphore S "
            "is an integer changed only via atomic wait (P: decrement or block) and "
            "signal (V: increment, wake one waiter).\n\n"
            "ALGORITHMS: Peterson's (2 processes): turn + flag array; correct but "
            "busy-waits. Semaphore: blocked process joins wait queue; signal wakes "
            "one. Monitor: mutually exclusive by construction.\n"
            "Semaphore trace — S=1, processes P1 and P2:\n"
            "  P1: wait(S) → S becomes 0; P1 enters CS.\n"
            "  P2: wait(S) → S becomes -1; P2 blocks (joins wait queue).\n"
            "  P1: signal(S) → S becomes 0; P2 is woken; P2 enters CS.\n"
            "Deadlock trace — S1=1, S2=1:\n"
            "  P1: wait(S1)→S1=0. P2: wait(S2)→S2=0.\n"
            "  P1: wait(S2)→S2=-1, P1 blocks. P2: wait(S1)→S1=-1, P2 blocks.\n"
            "  Neither can proceed → deadlock.\n\n"
            "BEHAVIOR: Spinlock (busy-wait): wastes CPU on uniprocessors but avoids "
            "context-switch overhead for very short CS on multiprocessors. Blocking "
            "semaphore: blocked thread leaves the run queue, freeing the CPU. "
            "Priority inversion: a low-priority process holds a resource needed by "
            "a high-priority process; priority inheritance raises the low-priority "
            "process's priority temporarily.\n\n"
            "CONCEPTS: Liveness: no deadlock and no starvation. Wrong semaphore "
            "order — P(A) then P(B) in one process, P(B) then P(A) in another — "
            "creates deadlock.\n\n"
            "METRICS: Spinlock: O(1) per check but burns CPU proportional to wait "
            "duration. Context switch: ~1–10 μs overhead.\n\n"
            "TRADE-OFFS: Spinlocks are efficient for tiny critical sections (shorter "
            "than context-switch cost) but wasteful otherwise. Monitors are safer "
            "than raw semaphores (less chance of misuse). Binary semaphores enforce "
            "mutual exclusion; counting semaphores manage resource pools."
        ),
    },
    {
        "id": "filesystem",
        "topic": "file systems",
        "text": (
            "A file system abstracts secondary storage as a named, hierarchical "
            "collection of files and directories.\n\n"
            "FACTS: Each open file is represented by a file descriptor (fd) — an "
            "index into the per-process open-file table in kernel memory. An inode "
            "stores metadata: owner UID, permissions (rwx bits), size, timestamps "
            "(atime, mtime, ctime), and pointers to data blocks (direct, single-"
            "indirect, double-indirect, triple-indirect). lseek() repositions the "
            "file offset and succeeds on regular files; it fails with ESPIPE on "
            "pipes and sockets, which are not seekable streams.\n\n"
            "ALGORITHMS: Contiguous allocation: consecutive blocks (fast sequential "
            "and random access; metadata = start + length). Linked allocation: each "
            "block holds a pointer to the next (no external fragmentation; poor "
            "random access — O(n) traversal). Indexed: one index block holds all "
            "data-block pointers (O(1) random access). Unix inode: 12 direct "
            "pointers + single/double/triple indirect.\n"
            "Worked numerical examples:\n"
            "  Inode capacity (block=4KB, pointer=4B): 12 direct=48KB; single "
            "indirect=4KB/4B × 4KB=4MB; double indirect=1024×4MB=4GB.\n"
            "  Access time comparison (disk seek=10ms per block):\n"
            "    Linked — read 4th block: must traverse blocks 1→2→3→4 = 4 seeks "
            "= 40ms.\n"
            "    Indexed — read index block then block 4 = 2 seeks = 20ms.\n"
            "  Internal fragmentation: 4KB block, file=1KB → 3KB wasted per file.\n\n"
            "BEHAVIOR: Contiguous allocation causes external fragmentation over time. "
            "Linked allocation avoids fragmentation but forces sequential traversal "
            "for random access. Growing a contiguous file may require relocation.\n\n"
            "CONCEPTS: Hard link: a directory entry pointing directly to an inode; "
            "file deleted only when all hard links are removed (link count = 0). "
            "Symbolic link: a special file containing a pathname string; dangling if "
            "the target is deleted. Directory structures: single-level, two-level, "
            "tree, acyclic graph.\n\n"
            "METRICS: Block size trade-off: larger block → higher throughput, worse "
            "internal fragmentation for small files. Indexed vs linked random access: "
            "O(1) vs O(n).\n\n"
            "TRADE-OFFS: Contiguous is fastest but suffers external fragmentation and "
            "requires pre-allocation. Linked is flexible but slow for random access. "
            "Indexed is best for mixed workloads but wastes an index block even on "
            "tiny files."
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
                        include_guidance: bool = False) -> list:
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

            # BASELINE = passage + bare "generate N {level} questions" — NO guidance,
            # NO examples. (Guidance is a separate teammate feature, excluded here so
            # we measure ICL's contribution alone.)
            baseline_service = QuestionGenerationService(
                llm_client=llm_client, chunk_fetcher=fetcher,
                example_bank=None, bloom_classifier=None,
                few_shot_k=0, retry_on_level_mismatch=False,
            )
            for q in await generate_once(baseline_service, bloom_level, args.num_questions,
                                         include_guidance=False):
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
            # ICL = the SAME bare no-guidance prompt + retrieved OS exemplars.
            # The ONLY difference from baseline is the exemplars.
            for q in await generate_once(icl_service, bloom_level, args.num_questions,
                                         include_guidance=False):
                rows.append({"chunk_id": chunk["id"], "bloom_level": bloom_level,
                             "condition": "icl", "question": q.question_text})
            print("  icl done")
            if sleep_secs > 0:
                time.sleep(sleep_secs)

    fieldnames = ["chunk_id", "bloom_level", "condition", "question"]

    if args.update_levels and OUT_CSV.exists():
        # Keep rows from OTHER levels, replace only the levels being regenerated
        update_set = set(bloom_levels)
        with OUT_CSV.open(encoding="utf-8") as f:
            kept = [r for r in csv.DictReader(f) if r["bloom_level"] not in update_set]
        all_rows = kept + rows
        print(f"Replacing {len(rows)} rows for level(s) {bloom_levels}; "
              f"keeping {len(kept)} rows from other levels.")
    else:
        all_rows = rows

    with OUT_CSV.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for row in all_rows:
            w.writerow(row)
    print(f"\nWrote {len(all_rows)} total rows to {OUT_CSV} "
          f"({len(rows)} new, {len(all_rows)-len(rows)} kept)")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--num-questions", type=int, default=3)
    ap.add_argument("--levels", default="remember,apply,evaluate")
    ap.add_argument("--update-levels", action="store_true",
                    help="Replace only the rows for --levels in the existing CSV, "
                         "preserving all other levels (use for partial retests)")
    args = ap.parse_args()
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    sys.exit(main())
