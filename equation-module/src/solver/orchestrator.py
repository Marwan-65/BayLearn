import json
from typing import Any, Dict, Tuple, Union
from ..models.requests import SolverRequest
from ..parsing.llm_parser import parse_user_input
from ..parsing.validators import validate_solver_request
from ..utils.exceptions import ValidationError
from .dispatcher import dispatch_operation


def solve_from_ai_data(ai_data: Dict[str, Any]) -> str:
    """Solve from translated AI payload.
    Args:
        ai_data: Translator output dictionary.
    Returns:
        Solver output text.
    """
    request = SolverRequest.from_ai_data(ai_data)
    validate_solver_request(request)
    return dispatch_operation(request)

def level_2_solver(
    user_input: str, show_translation: bool = False, return_translation: bool = False
) -> Union[str, Tuple[str, Dict[str, Any]]]:
    """Public level-2 solver entrypoint.

    Args:
        user_input: User prompt.
        show_translation: Whether to print translator JSON.
        return_translation: Whether to return translator payload with text.

    Returns:
        Solver output string, optionally paired with translation payload.
    """
    try:
        ai_data = parse_user_input(user_input)
        if show_translation:
            print(f"--- AI Translation --- \n{json.dumps(ai_data, indent=2)}\n")
        solved_text = solve_from_ai_data(ai_data)
        if return_translation:
            return solved_text, ai_data
        return solved_text
    except ValidationError as exc:
        if return_translation:
            return f"System Error: {exc}", None
        return f"System Error: {exc}"
    except Exception as exc:  # Boundary guard to preserve legacy API behavior.
        if return_translation:
            return f"System Error: {exc}", None
        return f"System Error: {exc}"
