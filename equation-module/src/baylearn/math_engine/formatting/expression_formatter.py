"""Expression formatting utilities."""

import sympy as sp


def expr_text(expr: sp.Expr) -> str:
    """Convert a SymPy expression to compact readable text.

    Args:
        expr: SymPy expression.

    Returns:
        Readable expression text using caret exponent style.
    """
    try:
        return sp.sstr(sp.simplify(expr)).replace("**", "^")
    except (TypeError, ValueError):
        return sp.sstr(expr).replace("**", "^")


def expr_to_readable_text(expr: sp.Expr) -> str:
    """Convert SymPy expression to normalized plain-text math.

    Args:
        expr: SymPy expression.

    Returns:
        Compact non-LaTeX text representation.
    """
    text = sp.sstr(expr)
    text = text.replace("**", "^")
    text = text.replace(" ", "")
    return text
