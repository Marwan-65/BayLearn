"""API-facing response building helpers."""


def build_operation_response(step_text: str, final_result_text: str) -> str:
    """Build solver output string preserving legacy format.

    Args:
        step_text: Formatted educational steps.
        final_result_text: Formatted final result content.

    Returns:
        Combined response text.
    """
    return f"{step_text}\n\nFinal Result: {final_result_text}"
