import pytest
from src.core.operations.algebra import handle_solve, handle_simplify

def test_handle_solve_linear():
    ai_data = {
        "operation": "solve",
        "equations": [{"lhs": "2*x", "rhs": "10"}],
        "target_variables": ["x"]
    }
    result = handle_solve(ai_data)
    assert "Final Result" in result
    assert "5" in result

def test_handle_solve_system():
    ai_data = {
        "operation": "solve_system",
        "equations": [
            {"lhs": "x + y", "rhs": "5"},
            {"lhs": "x - y", "rhs": "1"}
        ],
        "target_variables": ["x", "y"]
    }
    result = handle_solve(ai_data)
    assert "Final Result" in result
    assert "3" in result # x=3
    assert "2" in result # y=2

def test_handle_simplify():
    ai_data = {
        "operation": "simplify",
        "equations": [{"lhs": "2*x + 3*x", "rhs": ""}]
    }
    result = handle_simplify(ai_data)
    assert "Final Result" in result
    assert "5*x" in result.replace(" ", "")

def test_handle_simplify_error():
    ai_data = {
        "operation": "simplify",
        "equations": [{"lhs": "2*x + *", "rhs": ""}] # Invalid syntax
    }
    result = handle_simplify(ai_data)
    assert "Error simplifying expression" in result
