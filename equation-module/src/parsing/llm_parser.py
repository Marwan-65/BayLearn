from typing import Any, Dict


def translate_natural_language_to_math_json(user_input: str) -> Dict[str, Any]:
    """translate natural language input into structured json.
    Args:
        user_input: Natural language math prompt

    Returns:
        Translator json payload
    """
    from ...core.llm_client import translate_math_input

    return translate_math_input(user_input)
