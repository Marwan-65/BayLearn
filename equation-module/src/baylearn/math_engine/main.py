"""Top-level math engine entrypoints."""

from typing import Any, Dict, List, Tuple, Union

from .solver.orchestrator import level_2_solver as orchestrated_level_2_solver
from .visualization.graph_extractor import extract_graphable_functions


def level_2_solver(
    user_input: str, show_translation: bool = False, return_translation: bool = False
) -> Union[str, Tuple[str, Dict[str, Any]]]:
    """Public solver interface preserving existing signature."""
    return orchestrated_level_2_solver(
        user_input=user_input,
        show_translation=show_translation,
        return_translation=return_translation,
    )


def _extract_graphable_functions(
    operation: str, ai_data: Dict[str, Any], solver_output: str
) -> List[Dict[str, str]]:
    """Compatibility wrapper for graph extraction helper."""
    return extract_graphable_functions(operation, ai_data, solver_output)


__all__ = ["level_2_solver", "_extract_graphable_functions"]
