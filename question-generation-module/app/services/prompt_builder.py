from typing import List, Optional

def format_few_shot_examples(examples: list) -> str:
    if not examples:
        return ""
    lines = [
        "REFERENCE EXAMPLES — study these carefully:\n"
        "These questions were written by expert instructors at the TARGET difficulty level.\n"
        "YOUR TASK: mirror their COGNITIVE TYPE and QUESTION STYLE:\n"
        "  • If examples ask to COMPUTE, CALCULATE, or TRACE an algorithm step-by-step\n"
        "    → your questions must also require computation or tracing (not just recall).\n"
        "  • If examples ask to COMPARE or EXPLAIN a relationship\n"
        "    → your questions should also require analysis, not mere definition.\n"
        "Rules:\n"
        "  - Do NOT copy their exact wording or their specific numbers.\n"
        "  - DO use numbers and scenarios from the SOURCE MATERIAL below to build\n"
        "    similar computation or tracing questions.\n"
        "  - Every question must be answerable strictly from the SOURCE MATERIAL."
    ]
    for i, ex in enumerate(examples, 1):
        lines.append(f"\nExample {i} [level={ex.level}]:")
        lines.append(f"  Q: {ex.question}")
    return "\n".join(lines) + "\n"


# Difficulty levels guidance
DIFFICULTY_GUIDANCE = {
    "easy": {
        "description": "Recall facts, definitions, and basic concepts",
        "instruction": "Ask students to recall or recognize facts, terms, definitions, or basic concepts directly from the material.",
        "examples": "What is..., Define..., List..., Name..., Identify..."
    },
    "medium": {
        "description": "Explain ideas, concepts, and apply knowledge",
        "instruction": "Ask students to explain, describe, interpret concepts, and apply knowledge to solve problems or use procedures in new contexts.",
        "examples": "Explain..., Describe..., Summarize..., Solve..., Compare..., Apply..."
    },
    "hard": {
        "description": "Analyze, evaluate, and create original solutions",
        "instruction": "Ask students to break down information, identify relationships, make judgments based on criteria, and create original ideas or solutions.",
        "examples": "Analyze..., Evaluate..., Compare..., Justify..., Design..., Propose a solution..."
    }
}

# Normalize any difficulty vocabulary (Bloom-6 OR easy/medium/hard) to the
# 3-level keys DIFFICULTY_GUIDANCE uses. Without this, passing "remember" etc.
# silently falls back to "medium" guidance for every level.
_BLOOM6_TO_LEVEL = {
    "remember": "easy", "understand": "easy",
    "apply": "medium", "analyze": "medium",
    "evaluate": "hard", "create": "hard",
}


def _norm_level(difficulty: str) -> str:
    s = (difficulty or "").lower().strip()
    if s in ("easy", "medium", "hard"):
        return s
    return _BLOOM6_TO_LEVEL.get(s, "medium")


def _difficulty_header(kind: str, num_questions: int, difficulty: str,
                       include_guidance: bool) -> str:
    """
    The difficulty section of the prompt.

    include_guidance=True  → explicit difficulty rules + verb patterns (default).
    include_guidance=False → ablation: NO explicit rules; the model must infer the
                             target level from the reference (ICL) questions. Used to
                             isolate whether the examples alone carry the difficulty.
    """
    if include_guidance:
        level = _norm_level(difficulty)
        g = DIFFICULTY_GUIDANCE[level]
        return (
            f"Generate exactly {num_questions} {kind} at the difficulty level: "
            f"{level.upper()} ({g['description']}).\n\n"
            f"LEVEL GUIDANCE: {g['instruction']}\n"
            f"QUESTION PATTERNS TO USE: {g['examples']}"
        )
    # No-guidance mode: state ONLY the target level (easy/medium/hard) with no
    # rules or verb patterns. Works with or without exemplars — the baseline gets
    # just the level word; the ICL arm additionally sees the example questions.
    level = _norm_level(difficulty)
    return f"Generate exactly {num_questions} {kind} at the {level.upper()} difficulty level."


def build_mcq_prompt(chunks_text: str, num_questions: int, difficulty: str,
                     few_shot_examples: Optional[list] = None,
                     include_guidance: bool = True) -> tuple[str, str]:
    """
    Returns (system_prompt, user_prompt) for MCQ generation.

    chunks_text: All retrieved chunk texts joined together
    difficulty: Difficulty level (easy, medium, hard)
    few_shot_examples: Optional list of ExampleEntry objects (from ExampleBank.retrieve)
    include_guidance: include explicit difficulty rules (see _difficulty_header)
    """
    header = _difficulty_header("multiple choice questions", num_questions, difficulty, include_guidance)
    examples_block = format_few_shot_examples(few_shot_examples or [])

    system_prompt = (
        "You are an expert university professor who creates high-quality quiz questions.\n"
        "You ONLY generate questions based on the provided study material — never from general knowledge.\n"
        "Output ONLY valid JSON. No extra text, no markdown code blocks.\n"
    )

    user_prompt = f"""
{header}

{examples_block}
IMPORTANT: Each question must cover a DIFFERENT concept, topic, or aspect from the material.
Do NOT generate near-duplicate or redundant questions. Vary question structure and content.

The EXAMPLES above are reference questions at the target level. Ignore their
format — generate your questions strictly in the multiple choice question format defined
in the OUTPUT FORMAT section below.

STUDY MATERIAL:
{chunks_text}

OUTPUT FORMAT — return a JSON array with exactly 1 item, nothing else:
[
  {{
    "question_text": "What does Ohm's law state?",
    "options": [
      {{"label": "A", "text": "V = IR", "is_correct": true}},
      {{"label": "B", "text": "V = I/R", "is_correct": false}},
      {{"label": "C", "text": "V = I + R", "is_correct": false}},
      {{"label": "D", "text": "V = IR²", "is_correct": false}}
    ],
    "correct_answer": "V = IR",
    "explanation": "Ohm's law defines the relationship between voltage, current and resistance.",
    "difficulty": "{difficulty}"
  }}
]

Generate 1 question now:
"""
    return system_prompt, user_prompt

    
def build_short_answer_prompt(chunks_text: str, num_questions: int, difficulty: str,
                            few_shot_examples: Optional[list] = None,
                            include_guidance: bool = True) -> tuple[str, str]:

    header = _difficulty_header("short-answer questions", num_questions, difficulty, include_guidance)
    examples_block = format_few_shot_examples(few_shot_examples or [])

    system_prompt = (
        "You are an expert university professor creating short-answer exam questions.\n"
        "Base all questions ONLY on the provided study material.\n"
        "Output ONLY valid JSON. No extra text.\n"
    )

    user_prompt = f"""
{header}

{examples_block}
IMPORTANT: Each question must cover a DIFFERENT concept, topic, or aspect from the material.
Do NOT generate near-duplicate or redundant questions. Vary question focus and structure.

OUTPUT STRUCTURE NOTE: The examples above may not be in JSON — that is fine.
Use the OUTPUT FORMAT defined below for your JSON structure.
But you MUST mirror the examples' COGNITIVE STYLE (compute, trace, analyze, etc.).

STUDY MATERIAL:
{chunks_text}

OUTPUT FORMAT — return a JSON array with exactly 1 item, nothing else:
[
  {{
    "question_text": "What is the relationship between voltage, current, and resistance?",
    "correct_answer": "V = IR (Ohm's law): voltage equals current times resistance.",
        "keywords_to_match": ["ohm's law", "v = ir", "voltage", "current", "resistance"],
    "explanation": "This is the fundamental equation in circuit analysis.",
    "difficulty": "{difficulty}"
  }}
]

IMPORTANT FOR SHORT ANSWER GRADING:
- Include "keywords_to_match" for every question.
- Provide 3 to 6 concise keywords or short phrases that must appear in a correct answer.
- Keywords should capture core meaning, not exact sentence wording.
- Use lowercase strings when possible.

Generate 1 question now:
"""
    return system_prompt, user_prompt


    
def build_true_false_prompt(chunks_text: str, num_questions: int, difficulty: str,
                            few_shot_examples: Optional[list] = None,
                            include_guidance: bool = True) -> tuple[str, str]:

    header = _difficulty_header("true/false questions", num_questions, difficulty, include_guidance)
    examples_block = format_few_shot_examples(few_shot_examples or [])

    system_prompt = (
        "You are an expert university professor creating true/false quiz questions.\n"
        "Base all questions ONLY on the provided study material.\n"
        "Output ONLY valid JSON. No extra text.\n"
    )

    user_prompt = f"""
{header}

{examples_block}
IMPORTANT: Each question must cover a DIFFERENT concept, topic, or aspect from the material.
Do NOT generate near-duplicate or redundant questions. Vary question focus and content.

The EXAMPLES above are reference questions at the target level. Ignore their
format — generate your questions strictly in the true/false question format defined
in the OUTPUT FORMAT section below.

STUDY MATERIAL:
{chunks_text}

OUTPUT FORMAT — return a JSON array with exactly 1 item, nothing else:
[
  {{
    "question_text": "Ohm's law states that voltage equals current divided by resistance.",
    "correct_answer": "false",
    "explanation": "Ohm's law states V = IR (voltage = current × resistance, not divided).",
    "difficulty": "{difficulty}"
  }}
]

IMPORTANT: correct_answer must be exactly "true" or "false" (lowercase strings).

Generate 1 question now:
"""
    return system_prompt, user_prompt