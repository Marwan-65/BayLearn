from typing import Dict, Optional
import sympy as sp
from sympy.parsing.sympy_parser import parse_expr
from .exceptions import EquationParsingError

def parse_sympy_expression(expression: str, local_dict: Optional[Dict] = None) -> sp.Expr:
    """Parse a string into a SymPy expression.
    Args:
        expression: Raw expression text.
        local_dict: Optional local symbol/function mapping.
    Returns:
        Parsed SymPy expression.
    Raises:
        EquationParsingError: If parsing fails.
    """
    try:
        return parse_expr(str(expression), local_dict=local_dict)
    except (SyntaxError, TypeError, ValueError) as exc:
        raise EquationParsingError(f"Could not parse expression '{expression}': {exc}") from exc
