"""Operation handlers namespace."""

from .algebra import solve_equation
from .calculus import derive_expression, integrate_expression
from .differential_equations import solve_differential_equation
from .limits import compute_limit
from .matrices import handle_matrix_operation
from .partial_derivatives import compute_partial_derivative
from .series import compute_series
from .simplification import simplify_expression

__all__ = [
    "compute_limit",
    "compute_partial_derivative",
    "compute_series",
    "derive_expression",
    "handle_matrix_operation",
    "integrate_expression",
    "simplify_expression",
    "solve_differential_equation",
    "solve_equation",
]
