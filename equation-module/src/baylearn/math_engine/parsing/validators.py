"""Validation layer for solver requests."""

from typing import Any

from ..models.requests import SolverRequest
from ..utils.constants import SUPPORTED_OPERATIONS, VALID_MATRIX_OPERATIONS
from ..utils.exceptions import ValidationError


def validate_solver_request(request: SolverRequest) -> None:
    """Validate request structure and operation-specific required fields.

    Args:
        request: Typed solver request.

    Raises:
        ValidationError: If validation fails.
    """
    if not request.operation:
        raise ValidationError("Missing operation in AI translation payload.")

    if request.operation not in SUPPORTED_OPERATIONS:
        # Keep compatibility: unknown operation is allowed to flow to dispatcher fallback.
        return

    if not request.equations:
        raise ValidationError("Malformed request: at least one equation is required.")

    for equation in request.equations:
        if equation.lhs == "":
            raise ValidationError("Malformed equation: lhs cannot be empty.")
        if equation.rhs == "":
            raise ValidationError("Malformed equation: rhs cannot be empty.")

    if request.operation in {"solve", "solve_system", "derive", "integrate", "limit", "series"}:
        if not request.target_variables:
            raise ValidationError("Missing target_variables in request.")

    if request.operation == "matrix_ops":
        _validate_matrix_request(request)

    if request.operation == "series":
        order_value: Any = request.extra_params.get("order", 6)
        try:
            if int(order_value) <= 0:
                raise ValidationError("Invalid series order: must be positive.")
        except (TypeError, ValueError) as exc:
            raise ValidationError("Invalid series order: must be an integer.") from exc


def _validate_matrix_request(request: SolverRequest) -> None:
    """Validate matrix-operation request fields.

    Args:
        request: Typed solver request.

    Raises:
        ValidationError: If matrix operation is invalid.
    """
    operation = request.matrix_operation
    if operation in (None, "", "none", "null"):
        return
    if operation not in VALID_MATRIX_OPERATIONS:
        raise ValidationError(
            f"Invalid matrix operation '{operation}'. "
            f"Supported: {', '.join(VALID_MATRIX_OPERATIONS)}"
        )
