"""Operation dispatcher for modular math handlers."""

from typing import Callable, Dict

from ..models.requests import SolverRequest
from .operations import (
    compute_limit,
    compute_partial_derivative,
    compute_series,
    derive_expression,
    handle_matrix_operation,
    integrate_expression,
    simplify_expression,
    solve_differential_equation,
    solve_equation,
)

OperationHandler = Callable[[SolverRequest], str]

OPERATION_HANDLERS: Dict[str, OperationHandler] = {
    "solve": solve_equation,
    "solve_system": solve_equation,
    "derive": derive_expression,
    "integrate": integrate_expression,
    "dsolve": solve_differential_equation,
    "matrix_ops": handle_matrix_operation,
    "limit": compute_limit,
    "series": compute_series,
    "simplify": simplify_expression,
    "partial_derivative": compute_partial_derivative,
}


def dispatch_operation(request: SolverRequest) -> str:
    """Dispatch request to operation handler.

    Args:
        request: Typed solver request.

    Returns:
        Operation response text.
    """
    handler = OPERATION_HANDLERS.get(request.operation)
    if handler is None:
        return "Operation not fully implemented in backend yet."
    return handler(request)
