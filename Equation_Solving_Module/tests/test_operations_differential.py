import pytest
from src.core.operations.differential import handle_dsolve

def test_handle_dsolve():
    ai_data = {
        "operation": "dsolve",
        "equations": [{"lhs": "Derivative(f(x), x, x) - f(x)", "rhs": "0"}],
        "target_variables": ["f"]
    }
    result = handle_dsolve(ai_data)
    assert "Final Result:" in result
    assert "C1" in result or "C2" in result

def test_handle_dsolve_alternative_syntax():
    ai_data = {
        "operation": "dsolve",
        "equations": [{"lhs": "Derivative(f(x), x) - 2*x", "rhs": "0"}],
        "target_variables": ["f"]
    }
    result = handle_dsolve(ai_data)
    assert "Final Result:" in result
    assert "x**2" in result.replace(" ", "")

def test_handle_dsolve_error():
    ai_data = {
        "operation": "dsolve",
        "equations": [{"lhs": "Derivative(f(x), x, x) - f(x) * +", "rhs": "0"}],
        "target_variables": ["f"]
    }
    result = handle_dsolve(ai_data)
    assert "Error solving differential equation" in result or "Error parsing differential equation" in result
