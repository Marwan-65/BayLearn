import re
from typing import Any
import sympy as sp
from ..utils.constants import MAX_EXPRESSION_LENGTH, MAX_latex_LENGTH, PROBLEMATIC_latex_PATTERNS
from .expression_formatter import format_sympy_as_plain_text


def is_latex_syntax_valid(latex_str: str) -> bool:
    """Check whether the latex string is valid
    Args:
        latex_str:latex string
    Returns:
        true when valid latex
    """
    if not latex_str:
        return False
    if latex_str.count("{") != latex_str.count("}"):
        return False
    if latex_str.count("(") != latex_str.count(")"):
        return False
    if any(pattern in latex_str for pattern in PROBLEMATIC_latex_PATTERNS):
        return False
    if len(latex_str) > MAX_latex_LENGTH:
        return False
    return True


def repair_latex_formatting(latex_str: str) -> str:
    """clean latex string to fix some formatting issues
    Args:
        latex_str: Raw latex
    Returns:
        cleaned latex
    """
    if not latex_str:
        return latex_str
    if "\\" not in latex_str and "{" not in latex_str and "}" not in latex_str:
        return latex_str

    latex_str = re.sub(r"\s+", " ", latex_str.strip())
    latex_str = re.sub(r"\{\{+", "{", latex_str)
    latex_str = re.sub(r"\}+\}", "}", latex_str)
    latex_str = re.sub(r"\}\{", "}{", latex_str)
    latex_str = re.sub(r"\\left\\left", r"\\left", latex_str)
    latex_str = re.sub(r"\\right\\right", r"\\right", latex_str)

    open_braces = latex_str.count("{")
    close_braces = latex_str.count("}")
    if open_braces > close_braces:
        latex_str += "}" * (open_braces - close_braces)
    while latex_str.endswith("}") and latex_str.count("}") > latex_str.count("{"):
        latex_str = latex_str[:-1]

    open_parens = latex_str.count("(")
    close_parens = latex_str.count(")")
    if open_parens > close_parens:
        latex_str += ")" * (open_parens - close_parens)
    elif close_parens > open_parens:
        while latex_str.endswith(")") and latex_str.count(")") > latex_str.count("("):
            latex_str = latex_str[:-1]

    return latex_str


def convert_to_safe_latex(expr: Any) -> str:
    """convert expression to clean latex
    Args:
        expr:sympy expression
    Returns:
        cleaned latex
    """
    try:
        latex_str = repair_latex_formatting(sp.latex(expr))
        if not is_latex_syntax_valid(latex_str):
            return format_sympy_as_plain_text(expr)
        return latex_str
    except (TypeError, ValueError):
        try:
            return format_sympy_as_plain_text(expr)
        except (TypeError, ValueError):
            return str(expr)


def split_long_latex_equation(expr: Any, max_length: int = MAX_EXPRESSION_LENGTH) -> str:
    """format long expressions into multi line latex chunks.
    Args:
        expr: sympy expression
        max_length:max line length
    Returns:
        Formatted latex string.
    """
    try:
        latex_str = convert_to_safe_latex(expr)
        if len(latex_str) <= max_length:
            return latex_str

        if "+" in latex_str or "-" in latex_str:
            parts = []
            current_part = ""
            brace_level = 0
            for index, char in enumerate(latex_str):
                if char == "{":
                    brace_level += 1
                elif char == "}":
                    brace_level -= 1
                current_part += char
                if brace_level == 0 and char in ["+", "-"] and index > 0:
                    if current_part.strip():
                        parts.append(current_part.strip())
                        current_part = ""
                elif len(current_part) > max_length and brace_level == 0:
                    parts.append(current_part.strip())
                    current_part = ""
            if current_part.strip():
                parts.append(current_part.strip())
            if len(parts) > 1:
                formatted_parts = []
                for idx, part in enumerate(parts):
                    part = part.strip()
                    if idx > 0 and not part.startswith(("+", "-")):
                        part = "+" + part
                    formatted_parts.append(part)
                return " \\\\\n\\quad ".join(formatted_parts)
        return latex_str
    except (TypeError, ValueError):
        return convert_to_safe_latex(expr)
