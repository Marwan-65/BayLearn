"""
output: data/processed/baseline_vs_icl_generations.csv
run command:python scripts/generate_baseline_vs_icl.py
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
from question_generation_model.test_chunks import TEST_CHUNKS

OUT_DIR = ROOT / "data" / "processed"
OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT_CSV = OUT_DIR / "baseline_vs_icl_generations.csv"



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
