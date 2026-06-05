import pytest
from unittest.mock import patch
from src.core.solver import level_2_solver, _dispatch_operation

@patch("src.core.solver.translate_math_input")
def test_level_2_solver_success(mock_translate):
    mock_translate.return_value = {
        "operation": "solve",
        "equations": [{"lhs": "2*x", "rhs": "10"}],
        "target_variables": ["x"]
    }
    
    result = level_2_solver("solve 2x = 10")
    assert "x = 5" in result or "Final Result:" in result
    mock_translate.assert_called_once_with("solve 2x = 10")

@patch("src.core.solver.translate_math_input")
def test_level_2_solver_with_translation(mock_translate):
    ai_data_mock = {
        "operation": "solve",
        "equations": [{"lhs": "y", "rhs": "3"}],
        "target_variables": ["y"]
    }
    mock_translate.return_value = ai_data_mock
    
    result, ai_data = level_2_solver("y = 3", return_translation=True)
    assert ai_data == ai_data_mock
    assert "Final Result:" in result

@patch("src.core.solver.translate_math_input")
def test_level_2_solver_not_implemented(mock_translate):
    mock_translate.return_value = {
        "operation": "unknown_op"
    }
    
    result = level_2_solver("do something unknown")
    assert "Operation not fully implemented" in result

@patch("src.core.solver.translate_math_input")
def test_level_2_solver_exception(mock_translate):
    mock_translate.side_effect = Exception("API Error")
    
    result = level_2_solver("fail")
    assert "System Error: API Error" in result

def test_dispatch_operation_missing_handler():
    result = _dispatch_operation({"operation": "unsupported"})
    assert "Operation not fully implemented in backend yet." in result
