import pytest
import sympy as sp
from src.core.formatting.latex import sanitize_latex_artifacts, safe_latex, expr_to_clean_text, matrix_to_latex

def test_sanitize_latex_artifacts():
    assert sanitize_latex_artifacts("a \u2212 b") == "a - b"
    assert sanitize_latex_artifacts("a − b") == "a - b"
    assert sanitize_latex_artifacts(r"\sin{\left(x\right)}") == r"\sin\left(x\right)"

def test_safe_latex():
    x = sp.Symbol('x')
    expr = x**2 + 2*x + 1
    result = safe_latex(expr)
    assert "x^{2}" in result
    
    expr_tuple = (x,)
    assert safe_latex(expr_tuple) == "x"

def test_expr_to_clean_text():
    x = sp.Symbol('x')
    expr = x**2 + 2*x + 1
    assert "^" in expr_to_clean_text(expr)

def test_matrix_to_latex():
    mat = sp.Matrix([[1, 2], [3, 4]])
    result = matrix_to_latex(mat)
    assert r"\left[\begin{matrix}1 & 2\\3 & 4\end{matrix}\right]" in result
