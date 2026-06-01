"""Shared symbolic solving helpers."""

from typing import List

import sympy as sp

from ..models.requests import SolverRequest
from ..parsing.parser_utils import parse_equations, parse_target_variables


def build_equations(request: SolverRequest) -> List[sp.Eq]:
    """Build SymPy equations from typed request."""
    return parse_equations(request)


def build_target_variables(request: SolverRequest) -> List[sp.Symbol]:
    """Build SymPy target symbols from typed request."""
    return parse_target_variables(request)
