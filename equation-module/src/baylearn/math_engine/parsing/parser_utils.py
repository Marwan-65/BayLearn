"""Parser utility helpers for typed requests."""

from typing import List

import sympy as sp

from ..models.requests import SolverRequest
from ..utils.sympy_utils import parse_sympy_expression


def parse_equations(request: SolverRequest) -> List[sp.Eq]:
    """Convert request equations into SymPy equations.

    Args:
        request: Typed solver request.

    Returns:
        List of SymPy Eq instances.
    """
    equations: List[sp.Eq] = []
    for eq_data in request.equations:
        lhs_expr = parse_sympy_expression(eq_data.lhs)
        rhs_expr = parse_sympy_expression(eq_data.rhs)
        equations.append(sp.Eq(lhs_expr, rhs_expr))
    return equations


def parse_target_variables(request: SolverRequest) -> List[sp.Symbol]:
    """Convert target-variable names into SymPy symbols.

    Args:
        request: Typed solver request.

    Returns:
        List of SymPy symbols.
    """
    return [sp.Symbol(var) for var in request.target_variables]
