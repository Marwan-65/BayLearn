import asyncio
import os
import csv
import re
import json
import random
import time
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(ROOT))

import numpy as np
import nltk
from nltk.translate.bleu_score import sentence_bleu, SmoothingFunction
from question_generation_model.llm.groq_client import QuestionGenLLMClient
from app.classifier.bloom_classifier import BloomClassifier, bloom6_to_level
from app.services.example_bank import ExampleBank
from scripts.ablation_harness import AblationHarness
from scripts.generate_baseline_vs_icl import TEST_CHUNKS, make_fake_chunk_fetcher

load_dotenv(ROOT / ".env")

OUT_DIR = ROOT / "data" / "processed" / "ablation"
OUT_DIR.mkdir(parents=True, exist_ok=True)

def cosine_sim(v1, v2):
    return float(np.dot(v1, v2))

def distinct_n_grams(qs, n=2):
    ngrams = set()
    total = 0
    for q in qs:
        words = q.lower().split()
        for i in range(len(words)-n+1):
            ngrams.add(tuple(words[i:i+n]))
            total += 1
    return len(ngrams) / max(1, total) if total > 0 else 0.0

def avg_self_bleu(qs):
    if len(qs) < 2:
        return 0.0
    
    # Tokenize by simple splitting to avoid requiring nltk.download('punkt')
    tokenized_qs = [q.lower().split() for q in qs]
    smoothie = SmoothingFunction().method1
    bleu_scores = []
    
    for i, hyp in enumerate(tokenized_qs):
        refs = [ref for j, ref in enumerate(tokenized_qs) if i != j]
        score = sentence_bleu(refs, hyp, smoothing_function=smoothie)
        bleu_scores.append(score)
        
    return sum(bleu_scores) / len(bleu_scores)

# ── Bespoke Ablation Judge Prompt ─────────────────────────────────────────────
ABLATION_JUDGE_SYSTEM_PROMPT = (
    "You are a strict academic evaluator. Your job is to compare two sets of "
    "multiple-choice questions generated from the same text.\n"
    "Output VALID JSON only — no markdown, no prose outside the JSON.\n"
)

def build_ablation_judge_prompt(chunk_text: str, set_a: list[str], set_b: list[str]) -> str:
    a_block = "\n".join(f"  A{i+1}. {q}" for i, q in enumerate(set_a))
    b_block = "\n".join(f"  B{i+1}. {q}" for i, q in enumerate(set_b))
    return f"""SOURCE MATERIAL:
{chunk_text}

RUBRIC:
1. TOPICAL_DIVERSITY (Tests Context Enrichment): Does the set cover a broad range of concepts from the text? Punish sets that repeatedly ask about the exact same narrow sentence or concept.
2. DISTRACTOR_QUALITY (Tests Semantic Validation): Are the wrong options (distractors) plausible but clearly incorrect? Punish sets that have near-identical options, duplicate labels, or completely off-topic garbage options.
3. SOURCE_GROUNDING (Tests Hallucination): Can the correct answer be explicitly derived from the text provided? Punish sets that invent facts not present in the source material.
4. OVERALL: Which set is strictly better for an exam?

STEP 1 — For each of the 4 dimensions above, decide which set is better ("A", "B", or "tie") and give a one-sentence reason.

SET A:
{a_block}

SET B:
{b_block}

OUTPUT FORMAT — return ONLY this JSON object:
{{
  "topical_diversity":  {{"winner": "A" | "B" | "tie", "reason": "..."}},
  "distractor_quality": {{"winner": "A" | "B" | "tie", "reason": "..."}},
  "source_grounding":   {{"winner": "A" | "B" | "tie", "reason": "..."}},
  "overall":            {{"winner": "A" | "B" | "tie", "reason": "..."}}
}}"""

def parse_ablation_judge_response(text: str) -> dict:
    m = re.search(r"\{.*\}", text.strip(), re.DOTALL)
    return json.loads(m.group(0)) if m else {}


def safe_judge_generate(client, sys_prompt, user_prompt, max_retries=3):
    """Wraps the LLM judge call with exponential backoff for network/rate-limit errors."""
    for attempt in range(max_retries):
        try:
            return client.generate(sys_prompt, user_prompt, temperature=0.2, max_tokens=1200)
        except Exception as e:
            print(f"      [!] Judge API Error (attempt {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                sleep_time = (2 ** attempt) * 5
                print(f"      Retrying in {sleep_time} seconds...")
                time.sleep(sleep_time)
    print("      [!] Max retries reached for Judge. Returning empty JSON.")
    return "{}"

async def main():
    print("=" * 60)
    print("BayLearn Ablation Study: Execution Pipeline")
    print("=" * 60)

    # 1. Initialize Core Models
    api_key = os.environ.get("GROQ_API_KEY")
    
    # Decouple generating model from judging model to avoid self-bias
    gen_model = os.environ.get("GROQ_MODEL_ID", "llama-3.1-8b-instant")
    llm_client = QuestionGenLLMClient(api_key=api_key, model_id=gen_model)
    
    judge_model = os.environ.get("JUDGE_GROQ_MODEL", "llama-3.3-70b-versatile")
    if judge_model == gen_model: # Force them to be different
        judge_model = "llama-3.3-70b-versatile" if gen_model != "llama-3.3-70b-versatile" else "llama-3.1-8b-instant"
    judge_client = QuestionGenLLMClient(api_key=api_key, model_id=judge_model)
    print(f"Generator Model: {gen_model}")
    print(f"Judge Model: {judge_model}")
    
    classifier = BloomClassifier.load(ROOT / "models" / "bloom_distilbert")
    bank = ExampleBank.load(ROOT / "data" / "processed" / "example_bank.jsonl")
    embedder = bank._lazy_model()

    # Pre-embed the test chunks for similarity scoring
    chunk_embs = {
        ch["id"]: embedder.encode([ch["text"]], convert_to_numpy=True, show_progress_bar=False, normalize_embeddings=True)[0]
        for ch in TEST_CHUNKS
    }

    difficulties = ["remember", "apply", "evaluate"] # mapped to easy, medium, hard
    num_trials = 3 # number of questions per cell
    
    generation_records = []
    judge_records = []
    stats_records = []

    for chunk in TEST_CHUNKS:
        topic = chunk["topic"]
        chunk_text = chunk["text"]
        chunk_id = chunk["id"]
        
        # Inject the specific chunk text into the mock fetcher
        fake_fetcher = make_fake_chunk_fetcher(chunk_text, chunk_id)
        
        # Initialize the Harness with the fake fetcher for this chunk
        harness = AblationHarness(
            llm_client=llm_client, 
            chunk_fetcher=fake_fetcher, 
            example_bank=bank, 
            bloom_classifier=classifier, 
            project_id="eval-stub"
        )

        for diff_b6 in difficulties:
            diff_3 = bloom6_to_level(diff_b6)
            print(f"\nProcessing Chunk: [{chunk_id}] | Level: {diff_b6} ({diff_3})")
            
            cell_questions = {"A": [], "B": [], "C": []}

            # Phase 1-3: Generate for all conditions
            for condition in ["A", "B", "C"]:
                print(f"  Running Condition {condition}...")
                for trial in range(num_trials):
                    trial_id = f"{chunk_id}_{diff_b6}_{condition}_{trial}"
                    record = await harness.run_trial(trial_id, condition, topic, diff_b6, "mcq")
                    generation_records.append(record)
                    
                    # Store generated text for judging and metric calculation
                    if not record.empty_output:
                        q_text = record.question_text
                        cell_questions[condition].append(q_text)

            # Phase 4: Compute Statistical Diversity/Grounding Metrics per condition
            for condition in ["A", "B", "C"]:
                qs = cell_questions[condition]
                if not qs: continue
                
                q_embs = embedder.encode(qs, convert_to_numpy=True, show_progress_bar=False, normalize_embeddings=True)
                sims = [cosine_sim(qv, chunk_embs[chunk_id]) for qv in q_embs]
                
                d2g = distinct_n_grams(qs)
                bleu = avg_self_bleu(qs)
                grnd = sum(sims)/len(sims)
                print(f"    Cond {condition} Stats: Distinct 2-Grams: {d2g:.2f} | Avg Self-BLEU: {bleu:.2f} | Grounding: {grnd:.2f}")
                stats_records.append({
                    "chunk": chunk_id, "level": diff_b6, "condition": condition,
                    "distinct_2_grams": d2g, "avg_self_bleu": bleu, "grounding": grnd
                })

            # Phase 5: LLM Judge Head-to-Head
            rng = random.Random(42)
            
            # The judge prompt internally refers to the two sets as "A" and "B" (or "1" and "2").
            # This helper translates the judge's placeholder output back to the actual condition labels.
            def resolve_winner(w, cond_1, cond_2):
                if not w or str(w).lower() == "error": return "error"
                w_up = str(w).upper().strip()
                if "TIE" in w_up: return "tie"
                if w_up in ["A", "MODEL A", "MODEL_A", "SET A", "SET_A", "1"]: return cond_1
                if w_up in ["B", "MODEL B", "MODEL_B", "SET B", "SET_B", "2"]: return cond_2
                if "A" in w_up or "1" in w_up: return cond_1
                if "B" in w_up or "2" in w_up: return cond_2
                return "tie"

            # Comparison 1: A vs B (Impact of Context Enrichment)
            if cell_questions["A"] and cell_questions["B"]:
                flip = rng.random() < 0.5
                cond_1, cond_2 = ("B", "A") if flip else ("A", "B")
                set_1, set_2 = cell_questions[cond_1], cell_questions[cond_2]
                prompt = build_ablation_judge_prompt(chunk_text, set_1, set_2)
                response = safe_judge_generate(judge_client, ABLATION_JUDGE_SYSTEM_PROMPT, prompt)
                verdict = parse_ablation_judge_response(response)
                
                judge_records.append({
                    "chunk": chunk_id, "level": diff_b6, "comparison": "A_vs_B",
                    "base_condition_was": "set_2" if flip else "set_1",
                    "diversity_winner": resolve_winner(verdict.get("topical_diversity", {}).get("winner"), cond_1, cond_2) if verdict else "error",
                    "diversity_reason": verdict.get("topical_diversity", {}).get("reason", ""),
                    "distractor_winner": resolve_winner(verdict.get("distractor_quality", {}).get("winner"), cond_1, cond_2) if verdict else "error",
                    "distractor_reason": verdict.get("distractor_quality", {}).get("reason", ""),
                    "grounding_winner": resolve_winner(verdict.get("source_grounding", {}).get("winner"), cond_1, cond_2) if verdict else "error",
                    "grounding_reason": verdict.get("source_grounding", {}).get("reason", ""),
                    "overall_winner": resolve_winner(verdict.get("overall", {}).get("winner"), cond_1, cond_2) if verdict else "error",
                    "overall_reason": verdict.get("overall", {}).get("reason", ""),
                })

            # Comparison 2: B vs C (Impact of Semantic Validation)
            if cell_questions["B"] and cell_questions["C"]:
                flip = rng.random() < 0.5
                cond_1, cond_2 = ("C", "B") if flip else ("B", "C")
                set_1, set_2 = cell_questions[cond_1], cell_questions[cond_2]
                prompt = build_ablation_judge_prompt(chunk_text, set_1, set_2)
                response = safe_judge_generate(judge_client, ABLATION_JUDGE_SYSTEM_PROMPT, prompt)
                verdict = parse_ablation_judge_response(response)
                
                judge_records.append({
                    "chunk": chunk_id, "level": diff_b6, "comparison": "B_vs_C",
                    "base_condition_was": "set_2" if flip else "set_1",
                    "diversity_winner": resolve_winner(verdict.get("topical_diversity", {}).get("winner"), cond_1, cond_2) if verdict else "error",
                    "diversity_reason": verdict.get("topical_diversity", {}).get("reason", ""),
                    "distractor_winner": resolve_winner(verdict.get("distractor_quality", {}).get("winner"), cond_1, cond_2) if verdict else "error",
                    "distractor_reason": verdict.get("distractor_quality", {}).get("reason", ""),
                    "grounding_winner": resolve_winner(verdict.get("source_grounding", {}).get("winner"), cond_1, cond_2) if verdict else "error",
                    "grounding_reason": verdict.get("source_grounding", {}).get("reason", ""),
                    "overall_winner": resolve_winner(verdict.get("overall", {}).get("winner"), cond_1, cond_2) if verdict else "error",
                    "overall_reason": verdict.get("overall", {}).get("reason", ""),
                })

    # Export
    harness.export_results(str(OUT_DIR / "ablation_generation_metrics.csv"))
    
    if judge_records:
        with open(OUT_DIR / "ablation_judge_results.csv", "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=judge_records[0].keys())
            writer.writeheader()
            writer.writerows(judge_records)
        
    if stats_records:
        with open(OUT_DIR / "ablation_stats.csv", "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=stats_records[0].keys())
            writer.writeheader()
            writer.writerows(stats_records)
            
    print("\nStudy complete. Artifacts saved to data/processed/ablation/")

if __name__ == "__main__":
    asyncio.run(main())