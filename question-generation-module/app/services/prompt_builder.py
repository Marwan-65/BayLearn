from typing import List, Optional

# ── Few-shot ICL helper ─────────────────────────────────────────────────────
# Renders retrieved example bank entries into a string block that the LLM
# imitates. Kept tiny so it doesn't blow up the prompt budget.

def format_few_shot_examples(examples: list, question_type: str) -> str:
    """Render up to K example entries as a labeled block for the LLM.

    Each example shows the question, level tag, and (when available) the
    expected answer/explanation, so the LLM learns the OUTPUT FORMAT it
    should produce — not just the question style.
    """
    if not examples:
        return ""
    lines = ["EXAMPLES of questions at the requested level "
             "(imitate their style, depth, and answer format):"]
    for i, ex in enumerate(examples, 1):
        lines.append(f"\nExample {i} [level={ex.level}]:")
        lines.append(f"  Q: {ex.question}")
        if ex.correct_answer:
            lines.append(f"  A: {ex.correct_answer[:280]}")
        if ex.explanation:
            lines.append(f"  Why: {ex.explanation[:200]}")
    return "\n".join(lines) + "\n"


# Bloom's Taxonomy guidance for each level
BLOOM_GUIDANCE = {
    "remember": {
        "description": "Recall facts and definitions",
        "instruction": "Ask students to recall or recognize facts, terms, definitions, or basic concepts directly from the material.",
        "examples": "What is..., Define..., List..., Name..., Identify..."
    },
    "understand": {
        "description": "Explain ideas or concepts",
        "instruction": "Ask students to explain, describe, or interpret concepts. Questions should require understanding but not application.",
        "examples": "Explain..., Describe..., Summarize..., Classify..., Compare..."
    },
    "apply": {
        "description": "Use information in a new situation",
        "instruction": "Ask students to apply knowledge to solve problems or use procedures in new contexts.",
        "examples": "Calculate..., Solve..., Demonstrate..., Show how..., Construct..."
    },
    "analyze": {
        "description": "Distinguish between different parts",
        "instruction": "Ask students to break down information, identify relationships, or distinguish between components.",
        "examples": "Analyze..., Compare..., Contrast..., Distinguish..., What is the relationship between..."
    },
    "evaluate": {
        "description": "Justify a decision or choice",
        "instruction": "Ask students to make judgments based on criteria, justify choices, or critique ideas.",
        "examples": "Evaluate..., Justify..., Critique..., Defend..., Which is better and why..."
    },
    "create": {
        "description": "Combine elements to produce original work",
        "instruction": "Ask students to combine elements to produce something new, design solutions, or generate original ideas.",
        "examples": "Design..., Create..., Devise..., Generate..., Propose a solution..."
    }
}

def build_mcq_prompt(chunks_text: str, num_questions: int, difficulty: str,
                     few_shot_examples: Optional[list] = None) -> tuple[str, str]:
    """
    Returns (system_prompt, user_prompt) for MCQ generation.

    chunks_text: All retrieved chunk texts joined together
    difficulty: Bloom level (remember, understand, apply, analyze, evaluate, create)
    few_shot_examples: Optional list of ExampleEntry objects (from ExampleBank.retrieve)
    """
    bloom = BLOOM_GUIDANCE.get(difficulty.lower(), BLOOM_GUIDANCE["understand"])
    examples_block = format_few_shot_examples(few_shot_examples or [], "mcq")

    system_prompt = (
        "You are an expert university professor who creates high-quality quiz questions.\n"
        "You ONLY generate questions based on the provided study material — never from general knowledge.\n"
        "Output ONLY valid JSON. No extra text, no markdown code blocks.\n"
    )

    user_prompt = f"""
Generate exactly {num_questions} multiple choice questions at the Bloom's level: {difficulty.upper()} ({bloom['description']}).

LEVEL GUIDANCE: {bloom['instruction']}
QUESTION PATTERNS TO USE: {bloom['examples']}

{examples_block}
IMPORTANT: Each question must cover a DIFFERENT concept, topic, or aspect from the material.
Do NOT generate near-duplicate or redundant questions. Vary question structure and content.

STUDY MATERIAL:
{chunks_text}

OUTPUT FORMAT — return a JSON array, nothing else:
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

Generate {num_questions} diverse questions now:
"""
    return system_prompt, user_prompt


def build_short_answer_prompt(chunks_text: str, num_questions: int, difficulty: str,
                              few_shot_examples: Optional[list] = None) -> tuple[str, str]:
    bloom = BLOOM_GUIDANCE.get(difficulty.lower(), BLOOM_GUIDANCE["understand"])
    examples_block = format_few_shot_examples(few_shot_examples or [], "short_answer")

    system_prompt = (
        "You are an expert university professor creating short-answer exam questions.\n"
        "Base all questions ONLY on the provided study material.\n"
        "Output ONLY valid JSON. No extra text.\n"
    )

    user_prompt = f"""
Generate exactly {num_questions} short-answer questions at the Bloom's level: {difficulty.upper()} ({bloom['description']}).

LEVEL GUIDANCE: {bloom['instruction']}
QUESTION PATTERNS TO USE: {bloom['examples']}

{examples_block}
IMPORTANT: Each question must cover a DIFFERENT concept, topic, or aspect from the material.
Do NOT generate near-duplicate or redundant questions. Vary question focus and structure.

STUDY MATERIAL:
{chunks_text}

OUTPUT FORMAT — return a JSON array, nothing else:
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

Generate {num_questions} diverse questions now:
"""
    return system_prompt, user_prompt


def build_true_false_prompt(chunks_text: str, num_questions: int, difficulty: str,
                            few_shot_examples: Optional[list] = None) -> tuple[str, str]:
    bloom = BLOOM_GUIDANCE.get(difficulty.lower(), BLOOM_GUIDANCE["understand"])
    examples_block = format_few_shot_examples(few_shot_examples or [], "true_false")

    system_prompt = (
        "You are an expert university professor creating true/false quiz questions.\n"
        "Base all questions ONLY on the provided study material.\n"
        "Output ONLY valid JSON. No extra text.\n"
    )

    user_prompt = f"""
Generate exactly {num_questions} true/false questions at the Bloom's level: {difficulty.upper()} ({bloom['description']}).

LEVEL GUIDANCE: {bloom['instruction']}
QUESTION PATTERNS TO USE: {bloom['examples']}

{examples_block}
IMPORTANT: Each question must cover a DIFFERENT concept, topic, or aspect from the material.
Do NOT generate near-duplicate or redundant questions. Vary question focus and content.

STUDY MATERIAL:
{chunks_text}

OUTPUT FORMAT — return a JSON array, nothing else:
[
  {{
    "question_text": "Ohm's law states that voltage equals current divided by resistance.",
    "correct_answer": "false",
    "explanation": "Ohm's law states V = IR (voltage = current × resistance, not divided).",
    "difficulty": "{difficulty}"
  }}
]

IMPORTANT: correct_answer must be exactly "true" or "false" (lowercase strings).

Generate {num_questions} diverse questions now:
"""
    return system_prompt, user_prompt