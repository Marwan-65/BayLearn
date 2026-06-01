"""LLM parsing entrypoints."""

from typing import Any, Dict


def parse_user_input(user_input: str) -> Dict[str, Any]:
    """Translate user natural-language input into structured solver JSON.

    Args:
        user_input: Natural-language math prompt.

    Returns:
        Translator JSON payload.
    """
    from ...core.llm_client import translate_math_input

    return translate_math_input(user_input)
