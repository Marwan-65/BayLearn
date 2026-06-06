from __future__ import annotations

import os

from question_generation_model.llm.groq_client import QuestionGenLLMClient
try:
    from question_generation_model.llm.gemini_client import GeminiQuestionGenClient
except ImportError:
    GeminiQuestionGenClient = None


LEVEL_DESCRIPTION = {
    "remember":   "easy",
    "understand": "easy",
    "apply":      "medium",
    "analyze":    "medium",
    "evaluate":   "hard",
    "create":     "hard",
    "easy":       "easy",
    "medium":     "medium",
    "hard":       "hard",
}


JUDGE_SYSTEM_PROMPT = (
    "You are a strict academic question quality evaluator.\n"
    "Your job is to compare two sets of exam questions using a fixed, "
    "objective rubric based on Bloom's Taxonomy — NOT personal preference.\n"
    "Output VALID JSON only — no markdown, no prose outside the JSON.\n"
)


_RUBRIC = """
COGNITIVE TYPE CLASSIFICATION (classify each question into exactly one type):
  RECALL   — factual definition, listing, direct knowledge retrieval (no reasoning chain)
  APPLY    — computation, procedural solving, using a method or formula in a new context
  ANALYZE  — explanation of causality, comparison, breakdown of a concept or system
  EVALUATE — trade-off judgment, design decision, justification, or creation of a new scenario

FIXED COGNITIVE TYPE → DIFFICULTY MAPPING (do NOT deviate from this table):
  RECALL                    →  EASY
  APPLY  or  ANALYZE        →  MEDIUM
  EVALUATE                  →  HARD

HOW EACH DIMENSION DETERMINES LEVEL ACCURACY:

1. COGNITIVE_DEPTH  (Bloom Level Accuracy)
   Classify every question in both sets. Count how many in each set map to the
   TARGET DIFFICULTY via the table above.
   — EASY target   : winning set has MORE questions classified as RECALL.
   — MEDIUM target : winning set has MORE questions classified as APPLY or ANALYZE.
   — HARD target   : winning set has MORE questions classified as EVALUATE.
   A question classified to the wrong difficulty level hurts this score.

2. QUESTION_QUALITY  (Clarity & Structure)
   Is each question unambiguous, grammatically correct, and free of multiple
   valid interpretations? Ambiguous phrasing undermines ability to discriminate
   at the target level — a student at the wrong level might answer it by accident.

3. REASONING_DEMAND  (Appropriate cognitive work for the level)
   Does the cognitive work required match the target level?
   — EASY   : a correct answer requires ONLY direct recall. Multi-step reasoning
               means the question is too hard (mislabeled).
   — MEDIUM : a correct answer requires applying a method OR explaining a relationship
               (2+ reasoning steps). Pure recall makes it too easy.
   — HARD   : a correct answer requires weighing trade-offs or justifying a design
               decision across multiple dimensions. Single-step reasoning is insufficient.

4. EDUCATIONAL_VALUE
   Does the question test something a student genuinely needs to understand?
   High value: targets a concept that reveals depth of understanding.
   Low value: checks a trivial peripheral detail any student could guess.
   Educational value is tied to whether the question rewards the cognitive depth
   that defines its target level.

5. DISCRIMINATIVE_POWER
   Would this question separate students who truly understand from those who do not?
   — EASY   : answerable by any student who studied; should NOT require reasoning.
   — MEDIUM : solvable only by students who can apply or explain, not merely recall.
   — HARD   : requires genuine evaluative reasoning; paraphrasing the source fails.

6. BIAS_LEAKAGE_RISK  (lower is better — choose the set with LESS bias)
   Does any question hint at its own answer, use leading phrasing, or embed the
   solution in the question text? High bias/leakage makes a question easier than
   its label claims, distorting the difficulty measurement. The set with LOWER
   bias/leakage risk is the winner for this dimension.
"""


def build_judge_prompt(chunk_text, bloom_level, set_a, set_b):
    target = LEVEL_DESCRIPTION.get(bloom_level, "medium")
    a_block = "\n".join(f"  A{i+1}. {q}" for i, q in enumerate(set_a))
    b_block = "\n".join(f"  B{i+1}. {q}" for i, q in enumerate(set_b))
    return f"""SOURCE MATERIAL:
{chunk_text}

TARGET DIFFICULTY: {target.upper()}

{_RUBRIC}

STEP 1 — For each question in Set A and Set B, silently classify it as
RECALL / APPLY / ANALYZE / EVALUATE, then map to easy/medium/hard.

STEP 2 — For each of the 6 dimensions above, decide which set is better
("A", "B", or "tie") and give a one-sentence reason grounded in the rubric.
Then give an overall verdict.

SET A:
{a_block}

SET B:
{b_block}

OUTPUT FORMAT — return ONLY this JSON object, no other text:
{{
  "cognitive_depth":      {{"winner": "A" | "B" | "tie", "reason": "..."}},
  "question_quality":     {{"winner": "A" | "B" | "tie", "reason": "..."}},
  "reasoning_demand":     {{"winner": "A" | "B" | "tie", "reason": "..."}},
  "educational_value":    {{"winner": "A" | "B" | "tie", "reason": "..."}},
  "discriminative_power": {{"winner": "A" | "B" | "tie", "reason": "..."}},
  "bias_leakage":         {{"winner": "A" | "B" | "tie", "reason": "..."}},
  "overall":              {{"winner": "A" | "B" | "tie", "reason": "..."}}
}}"""


def make_judge_client(provider):
    if provider == "gemini":
        if GeminiQuestionGenClient is None:
            raise RuntimeError("google-genai not installed")
        key = os.environ.get("GEMINI_API_KEY")
        if not key:
            raise RuntimeError("GEMINI_API_KEY missing")
        model = os.environ.get("JUDGE_GEMINI_MODEL",
                               os.environ.get("GEMINI_MODEL_ID", "gemini-2.0-flash"))
        return GeminiQuestionGenClient(api_key=key, model_id=model), 4.0, model
    key = os.environ.get("GROQ_API_KEY")
    if not key:
        raise RuntimeError("GROQ_API_KEY missing")
    model = os.environ.get("JUDGE_GROQ_MODEL", "llama-3.3-70b-versatile")
    return QuestionGenLLMClient(api_key=key, model_id=model), 1.5, model


def run_judge(client, chunk_text, bloom_level, set_a, set_b):
    prompt = build_judge_prompt(chunk_text, bloom_level, set_a, set_b)
    return client.generate(
        system_prompt=JUDGE_SYSTEM_PROMPT,
        user_prompt=prompt,
        temperature=0.1,
        max_tokens=1500,
    )
