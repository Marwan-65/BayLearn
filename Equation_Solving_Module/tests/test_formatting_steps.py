import pytest
import sympy as sp
from src.core.formatting.steps import format_base_steps, format_student_linear_steps, build_final_text_block

def test_format_base_steps_solve():
    x = sp.Symbol('x')
    eq = sp.Eq(2*x, 10)
    result = [5]
    
    steps = format_base_steps("solve", [eq], [x], result)
    assert "Step 1: Parsed input" in steps
    assert "Target variables: ['x']" in steps

def test_format_student_linear_steps():
    x = sp.Symbol('x')
    eq = sp.Eq(2*x, 10)
    
    steps = format_student_linear_steps([eq], [x], [5])
    assert steps is not None
    assert "Step 1: Rewrite in standard form" in steps
    assert "Step 2: Isolate the variable" in steps

def test_format_student_linear_steps_nonlinear():
    x = sp.Symbol('x')
    eq = sp.Eq(x**2, 4)
    
    steps = format_student_linear_steps([eq], [x], [-2, 2])
    assert steps is None

def test_build_final_text_block():
    x = sp.Symbol('x')
    result = build_final_text_block("solve", [5], [x])
    assert result == r"$\text{Sol 1: } x = 5$"
    
    result2 = build_final_text_block("derive", 2*x, [x])
    assert "2 x" in result2.replace(" ", "")
