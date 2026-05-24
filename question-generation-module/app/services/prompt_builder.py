from typing import List

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

def build_mcq_prompt(chunks_text: str, num_questions: int, difficulty: str) -> tuple[str, str]:
    """
    Returns (system_prompt, user_prompt) for MCQ generation.
    
    chunks_text: All retrieved chunk texts joined together
    difficulty: Difficulty level (easy, medium, hard)
    """
    diff_guide = DIFFICULTY_GUIDANCE.get(difficulty.lower(), DIFFICULTY_GUIDANCE["medium"])
    
    system_prompt = (
        "You are an expert university professor who creates high-quality quiz questions.\n"
        "You ONLY generate questions based on the provided study material — never from general knowledge.\n"
        "Output ONLY valid JSON. No extra text, no markdown code blocks.\n"
    )

    user_prompt = f"""
Generate exactly {num_questions} multiple choice questions at the difficulty level: {difficulty.upper()} ({diff_guide['description']}).

LEVEL GUIDANCE: {diff_guide['instruction']}
QUESTION PATTERNS TO USE: {diff_guide['examples']}

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


def build_short_answer_prompt(chunks_text: str, num_questions: int, difficulty: str) -> tuple[str, str]:
    diff_guide = DIFFICULTY_GUIDANCE.get(difficulty.lower(), DIFFICULTY_GUIDANCE["medium"])
    
    system_prompt = (
        "You are an expert university professor creating short-answer exam questions.\n"
        "Base all questions ONLY on the provided study material.\n"
        "Output ONLY valid JSON. No extra text.\n"
    )

    user_prompt = f"""
Generate exactly {num_questions} short-answer questions at the difficulty level: {difficulty.upper()} ({diff_guide['description']}).

LEVEL GUIDANCE: {diff_guide['instruction']}
QUESTION PATTERNS TO USE: {diff_guide['examples']}

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


def build_true_false_prompt(chunks_text: str, num_questions: int, difficulty: str) -> tuple[str, str]:
    diff_guide = DIFFICULTY_GUIDANCE.get(difficulty.lower(), DIFFICULTY_GUIDANCE["medium"])
    
    system_prompt = (
        "You are an expert university professor creating true/false quiz questions.\n"
        "Base all questions ONLY on the provided study material.\n"
        "Output ONLY valid JSON. No extra text.\n"
    )

    user_prompt = f"""
Generate exactly {num_questions} true/false questions at the difficulty level: {difficulty.upper()} ({diff_guide['description']}).

LEVEL GUIDANCE: {diff_guide['instruction']}
QUESTION PATTERNS TO USE: {diff_guide['examples']}

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