from typing import List

def build_mcq_prompt(chunks_text: str, num_questions: int, difficulty: str) -> tuple[str, str]:
    """
    Returns (system_prompt, user_prompt) for MCQ generation.
    
    chunks_text: All retrieved chunk texts joined together
    """
    system_prompt = (
        "You are an expert university professor who creates high-quality quiz questions.\n"
        "You ONLY generate questions based on the provided study material — never from general knowledge.\n"
        "Output ONLY valid JSON. No extra text, no markdown code blocks.\n"
    )

    user_prompt = f"""
Generate exactly {num_questions} multiple choice questions at {difficulty} difficulty from the study material below.

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

Generate {num_questions} questions now:
"""
    return system_prompt, user_prompt


def build_short_answer_prompt(chunks_text: str, num_questions: int, difficulty: str) -> tuple[str, str]:
    system_prompt = (
        "You are an expert university professor creating short-answer exam questions.\n"
        "Base all questions ONLY on the provided study material.\n"
        "Output ONLY valid JSON. No extra text.\n"
    )

    user_prompt = f"""
Generate exactly {num_questions} short-answer questions at {difficulty} difficulty from the study material below.

STUDY MATERIAL:
{chunks_text}

OUTPUT FORMAT — return a JSON array, nothing else:
[
  {{
    "question_text": "What is the relationship between voltage, current, and resistance?",
    "correct_answer": "V = IR (Ohm's law): voltage equals current times resistance.",
    "explanation": "This is the fundamental equation in circuit analysis.",
    "difficulty": "{difficulty}"
  }}
]

Generate {num_questions} questions now:
"""
    return system_prompt, user_prompt


def build_true_false_prompt(chunks_text: str, num_questions: int, difficulty: str) -> tuple[str, str]:
    system_prompt = (
        "You are an expert university professor creating true/false quiz questions.\n"
        "Base all questions ONLY on the provided study material.\n"
        "Output ONLY valid JSON. No extra text.\n"
    )

    user_prompt = f"""
Generate exactly {num_questions} true/false questions at {difficulty} difficulty from the study material below.

STUDY MATERIAL:
{chunks_text}

OUTPUT FORMAT — return a JSON array, nothing else:
[
  {{
    "question_text": "Ohm's law states that voltage equals current divided by resistance.",
    "correct_answer": "False",
    "explanation": "Ohm's law states V = IR (voltage = current × resistance, not divided).",
    "difficulty": "{difficulty}"
  }}
]

Generate {num_questions} questions now:
"""
    return system_prompt, user_prompt