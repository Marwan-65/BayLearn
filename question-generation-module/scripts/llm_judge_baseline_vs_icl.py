"""
LLM-as-judge: blinded pairwise comparison of baseline vs ICL question sets.

writes:
    data/processed/llm_judge_per_cell.csv      one row per cell with the judge's verdict
    data/processed/llm_judge_summary.txt       aggregate win rates + interpretation

Run:
    python scripts/llm_judge_baseline_vs_icl.py
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import random
import re
import sys
import time
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:
    pass

from app.llm.groq_client import QuestionGenLLMClient
try:
    from app.llm.gemini_client import GeminiQuestionGenClient
except ImportError:
    GeminiQuestionGenClient = None

GENERATIONS_CSV = ROOT / "data" / "processed" / "eval_icl_vs_baseline_generations.csv"
OUT_PER_CELL   = ROOT / "data" / "processed" / "llm_judge_per_cell.csv"
OUT_SUMMARY    = ROOT / "data" / "processed" / "llm_judge_summary.txt"

TEST_CHUNKS = {
    "paging": ("virtual memory and paging",
        "In a paging system, the virtual address space is divided into "
        "fixed-size pages and physical memory into frames of the same size. "
        "The page table maps virtual page numbers to physical frame numbers. "
        "When a process references an address whose page is not in memory, "
        "a page fault occurs and the OS must load the page from disk. "
        "Common page replacement algorithms include FIFO, LRU, and Optimal. "
        "FIFO is simple but can suffer from Belady's anomaly. LRU "
        "approximates the optimal policy. The TLB caches frequently-used "
        "page table entries."),
    "scheduling": ("CPU scheduling",
        "CPU scheduling determines which ready process runs next. Policies "
        "include FCFS, SJF, Round Robin with time quantum, and Multilevel "
        "Feedback Queue. FCFS suffers convoy effect. SJF minimizes waiting "
        "but starves long jobs. Round Robin balances responsiveness vs "
        "context-switch overhead. The dispatcher performs context switches."),
    "synchronization": ("process synchronization",
        "Concurrent processes need synchronization to prevent races. A "
        "critical section accesses shared data. Solutions need mutual "
        "exclusion, progress, bounded waiting. Semaphores use atomic wait/"
        "signal. Mutexes lock single resources. Monitors bundle data and ops. "
        "Deadlock requires mutual exclusion, hold-and-wait, no preemption, "
        "circular wait."),
    "filesystem": ("file systems",
        "A file system organizes secondary storage. Files have descriptors. "
        "Directories: single, two-level, tree, acyclic graph. Inodes hold "
        "metadata (ownership, permissions, size, data block pointers). "
        "Allocation: contiguous (fast, fragments), linked (no fragments, slow "
        "random), indexed (flexible direct access via index block)."),
    "deadlock": ("deadlock detection and recovery",
        "Deadlock prevention eliminates one of the four conditions. "
        "Avoidance (Banker's algorithm) needs max resource needs in advance. "
        "Detection scans the resource allocation graph for cycles. Recovery: "
        "process termination (abort all or one-at-a-time) or resource "
        "preemption (take from victims, rollback). Victim selection considers "
        "priority and resources held."),
}

LEVEL_DESCRIPTION = {
    "remember":   "easy",
    "understand": "easy",
    "apply":      "medium",
    "analyze":    "medium",
    "evaluate":   "hard",
    "create":     "hard",
}

LEVEL_GUIDANCE = {
    "easy":   "recall, definition, single-fact retrieval — short and direct",
    "medium": "apply a procedure or compare components — multi-step but bounded",
    "hard":   "evaluate / justify / design — requires reasoning over multiple "
            "dimensions, trade-offs, or original synthesis",
}

JUDGE_SYSTEM_PROMPT = (
    "You are an expert computer engineering professor evaluating exam-question "
    "quality. You compare two sets of questions generated from the same "
    "source at the same target difficulty (easy / medium / hard). Be strict, "
    "concise, and reproducible. Output VALID JSON only — no markdown, no "
    "prose outside the JSON.\n"
)


def build_judge_prompt(chunk_text: str, target_b6: str,
                       set_a: list[str], set_b: list[str]) -> str:
    level_description = LEVEL_DESCRIPTION.get(target_b6, "medium")
    level_guidance = LEVEL_GUIDANCE[level_description]
    a_block = "\n".join(f"  A{i+1}. {q}" for i, q in enumerate(set_a))
    b_block = "\n".join(f"  B{i+1}. {q}" for i, q in enumerate(set_b))
    return f"""
SOURCE MATERIAL:
{chunk_text}

TARGET DIFFICULTY: {level_description.upper()} ({level_guidance})

Two sets of questions were generated from the source above. Evaluate them
HEAD TO HEAD on four criteria. For each criterion, pick "A", "B", or "tie",
then give a one-sentence reason.

SET A:
{a_block}

SET B:
{b_block}

CRITERIA:
1. answerability       — Can each question be solved using ONLY the source
                         material, without the student needing to guess
                         missing parameters or invent context? Which set
                         scores better overall?
2. difficulty_match    — Which set's questions better match the TARGET
                         DIFFICULTY shown above? Easy questions should be
                         short and direct; medium should apply or compare;
                         hard should require multi-dimensional reasoning,
                         justification, or design.
3. overall             — Which set would you prefer for a real exam?

OUTPUT FORMAT — return ONLY this JSON, no other text:
{{
  "answerability":      {{"winner": "A" | "B" | "tie", "reason": "..."}},
  "difficulty_match":   {{"winner": "A" | "B" | "tie", "reason": "..."}},
  "overall":            {{"winner": "A" | "B" | "tie", "reason": "..."}}
}}
"""


def parse_judge_response(text: str) -> dict | None:
    text = text.strip()
    if text.startswith("```"):
        text = "\n".join(text.split("\n")[1:-1]) if "\n" in text else text
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


def make_judge_client(provider: str):
    if provider == "gemini":
        if GeminiQuestionGenClient is None:
            raise RuntimeError("google-genai not installed")
        key = os.environ.get("GEMINI_API_KEY")
        if not key:
            raise RuntimeError("GEMINI_API_KEY missing")
        model = os.environ.get("JUDGE_GEMINI_MODEL",
                               os.environ.get("GEMINI_MODEL_ID", "gemini-2.5-flash-lite"))
        return GeminiQuestionGenClient(api_key=key, model_id=model), 4.0, model
    else:
        key = os.environ.get("GROQ_API_KEY")
        if not key:
            raise RuntimeError("GROQ_API_KEY missing")
        model = os.environ.get("JUDGE_GROQ_MODEL",
                               os.environ.get("GROQ_MODEL_ID",
                                              "meta-llama/llama-4-scout-17b-16e-instruct"))
        return QuestionGenLLMClient(api_key=key, model_id=model), 1.0, model


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--judge-provider", default=None,
                    choices=["groq", "gemini"],
                    help="LLM provider for the judge (default: env groq)")
    ap.add_argument("--sleep", type=float, default=None,
                    help="seconds between judge calls (default: provider will set its appropriate timing)")
    args = ap.parse_args()

    # if not GENERATIONS_CSV.exists():
    #     print(f"ERROR: {GENERATIONS_CSV} not found. Run eval_icl_vs_baseline.py first.",
    #         file=sys.stderr)
    #     return 1

    provider = (args.judge_provider or os.environ.get("LLM_PROVIDER") or "groq").lower()
    try:
        client, default_sleep, model_name = make_judge_client(provider)
    except RuntimeError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    sleep_secs = args.sleep if args.sleep is not None else default_sleep

    buckets: dict[tuple[str, str, str], list[str]] = defaultdict(list)
    with GENERATIONS_CSV.open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            key = (r["chunk_id"], r["target_level_b6"], r["condition"])
            buckets[key].append(r["question"])

    cells = []
    seen_cells = set()
    for (cid, b6, _cond) in buckets.keys():
        if (cid, b6) in seen_cells:
            continue
        baseline = buckets.get((cid, b6, "baseline"), [])
        icl      = buckets.get((cid, b6, "icl"), [])
        if not baseline or not icl:
            continue
        cells.append((cid, b6, baseline, icl))
        seen_cells.add((cid, b6))
    print(f"{len(cells)} (chunk, level) cells with both baseline and ICL data.")
    if not cells:
        print("Nothing to judge.", file=sys.stderr)
        return 1

    rng = random.Random(2025)  
    CRITERIA = ["answerability","difficulty_match", "overall"]
    per_cell_rows = []
    wins = {c: {"icl": 0, "baseline": 0, "tie": 0} for c in CRITERIA}

    for idx, (cid, b6, base_qs, icl_qs) in enumerate(cells, 1):
        if cid not in TEST_CHUNKS:
            print(f"skip unknown chunk_id {cid!r}")
            continue
        topic, chunk_text = TEST_CHUNKS[cid]

        flip = rng.random() < 0.5
        set_a, set_b = (icl_qs, base_qs) if flip else (base_qs, icl_qs)
        a_is_icl = flip

        prompt = build_judge_prompt(chunk_text, topic, b6, set_a, set_b)
        try:
            response = client.generate(
                system_prompt=JUDGE_SYSTEM_PROMPT,
                user_prompt=prompt,
                temperature=0.2,
                max_tokens=1200,
            )
        except Exception as e:
            print(f"  [{idx}/{len(cells)}] {cid}/{b6}: API error — {e}")
            if sleep_secs > 0:
                time.sleep(sleep_secs)
            continue

        verdict = parse_judge_response(response)
        if verdict is None:
            print(f"  [{idx}/{len(cells)}] {cid}/{b6}: parse failed")
            if sleep_secs > 0:
                time.sleep(sleep_secs)
            continue

        row = {"chunk_id": cid, "target_level_b6": b6,
               "icl_was": "A" if a_is_icl else "B"}
        for c in CRITERIA:
            v = (verdict.get(c) or {})
            raw = (v.get("winner") or "").strip().upper()
            if raw == "A":
                cond_winner = "icl" if a_is_icl else "baseline"
            elif raw == "B":
                cond_winner = "baseline" if a_is_icl else "icl"
            elif raw in ("TIE", "EQUAL"):
                cond_winner = "tie"
            else:
                cond_winner = "tie"   # treat malformed as tie
            wins[c][cond_winner] += 1
            row[f"{c}_winner"] = cond_winner
            row[f"{c}_reason"] = (v.get("reason") or "")[:300]
        per_cell_rows.append(row)
        line = f"  [{idx}/{len(cells)}] {cid}/{b6}: "
        line += " ".join(f"{c}={row[f'{c}_winner']}" for c in CRITERIA)
        print(line)
        if sleep_secs > 0:
            time.sleep(sleep_secs)

    
    fieldnames = ["chunk_id", "target_level_b6", "icl_was"]
    for c in CRITERIA:
        fieldnames.append(f"{c}_winner")
        fieldnames.append(f"{c}_reason")
    with OUT_PER_CELL.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for row in per_cell_rows:
            w.writerow(row)
    print(f"\nPer-cell judgments -> {OUT_PER_CELL}")


    total = len(per_cell_rows)
    lines = []
    lines.append("LLM-as-judge: baseline vs ICL pairwise comparison")
    lines.append("=" * 60)
    lines.append(f"Judge: {provider} ({model_name})")
    lines.append(f"Cells judged: {total}")
    lines.append("")
    lines.append(f"{'criterion':<22}{'ICL wins':>10}{'baseline wins':>16}{'ties':>8}{'ICL %':>10}")
    lines.append("-" * 66)
    for c in CRITERIA:
        i = wins[c]["icl"]; b = wins[c]["baseline"]; t = wins[c]["tie"]
        pct = 100.0 * i / max(1, total)
        lines.append(f"{c:<22}{i:>10}{b:>16}{t:>8}{pct:>9.1f}%")
    lines.append("")
    lines.append("ICL % = how often ICL won that criterion (ties excluded from %).")
    lines.append("Per-criterion patterns: ICL usually wins specificity if")
    lines.append("finding holds, level_match depends on the judge agreeing with")
    lines.append("BloomBERT's training distribution.")
    lines.append("")
    lines.append(f"Per-cell judgments + reasons: {OUT_PER_CELL.name}")
    OUT_SUMMARY.write_text("\n".join(lines), encoding="utf-8")
    print("\n" + "\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
