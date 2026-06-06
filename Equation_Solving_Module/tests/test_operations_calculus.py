import pytest
from src.core.operations.calculus import (
    handle_derive, 
    handle_integrate, 
    handle_limit, 
    handle_series, 
    handle_partial_derivative
)

def test_handle_derive():
    ai_data = {
        "operation": "derive",
        "equations": [{"lhs": "x**2", "rhs": ""}],
        "target_variables": ["x"]
    }
    result = handle_derive(ai_data)
    assert "Final Result:" in result
    assert "2*x" in result.replace(" ", "")

def test_handle_integrate():
    ai_data = {
        "operation": "integrate",
        "equations": [{"lhs": "2*x", "rhs": ""}],
        "target_variables": ["x"]
    }
    result = handle_integrate(ai_data)
    assert "Final Result:" in result
    assert "x**2" in result.replace(" ", "")

def test_handle_limit():
    ai_data = {
        "operation": "limit",
        "equations": [{"lhs": "sin(x)/x", "rhs": "0"}],
        "target_variables": ["x"]
    }
    result = handle_limit(ai_data)
    assert "Final Result: 1" in result

def test_handle_limit_error():
    ai_data = {
        "operation": "limit",
        "equations": [{"lhs": "sin(x)/+", "rhs": "0"}],
        "target_variables": ["x"]
    }
    result = handle_limit(ai_data)
    assert "Error calculating limit" in result

def test_handle_series():
    ai_data = {
        "operation": "series",
        "equations": [{"lhs": "exp(x)", "rhs": ""}],
        "target_variables": ["x"],
        "extra_params": {"point": "0", "order": "3"}
    }
    result = handle_series(ai_data)
    assert "Final Result:" in result
    assert "x**2/2" in result.replace(" ", "") or "x**2 / 2" in result

def test_handle_series_error():
    ai_data = {
        "operation": "series",
        "equations": [{"lhs": "exp(x)+*", "rhs": ""}],
        "target_variables": ["x"]
    }
    result = handle_series(ai_data)
    assert "Error computing series" in result

def test_handle_partial_derivative():
    ai_data = {
        "operation": "partial_derivative",
        "equations": [{"lhs": "x**2 * y", "rhs": ""}],
        "target_variables": ["x", "y"]
    }
    result = handle_partial_derivative(ai_data)
    assert "Final Result:" in result
    assert "2*x" in result.replace(" ", "")

def test_handle_partial_derivative_error():
    ai_data = {
        "operation": "partial_derivative",
        "equations": [{"lhs": "x**2 * y * +", "rhs": ""}],
        "target_variables": ["x", "y"]
    }
    result = handle_partial_derivative(ai_data)
    assert "Error computing partial derivative" in result
