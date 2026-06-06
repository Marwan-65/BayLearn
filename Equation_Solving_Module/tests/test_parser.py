import pytest
from src.core.parser import solve_math_string

def test_solve_math_string_linear():
    result = solve_math_string("2*x = 10")
    assert "x = [5]" in result or "x = 5" in result.replace(" ", "")

def test_solve_math_string_with_spaces():
    result = solve_math_string(" 3 * y - 2 = 7 ")
    assert "y = [3]" in result or "y = 3" in result.replace(" ", "")

def test_solve_math_string_missing_equals():
    result = solve_math_string("2x - 4")
    assert "Error: Equation must contain an '=' sign" in result

def test_solve_math_string_no_variables():
    result = solve_math_string("2 + 2 = 4")
    assert "Error: No variables found" in result

def test_solve_math_string_invalid_syntax():
    result = solve_math_string("2x + = 5")
    assert "Could not parse" in result

def test_solve_math_string_implicit_multiplication():
    result = solve_math_string("2(x+1) = 6")
    assert "x = [2]" in result or "x = 2" in result.replace(" ", "")
