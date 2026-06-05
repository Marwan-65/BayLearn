import pytest
from src.core.operations.matrix import handle_matrix_ops

def test_handle_matrix_determinant():
    ai_data = {
        "operation": "matrix_ops",
        "matrix_operation": "determinant",
        "equations": [{"lhs": "[[1, 2], [3, 4]]", "rhs": ""}]
    }
    result = handle_matrix_ops(ai_data)
    assert "Final Result: Determinant = -2" in result

def test_handle_matrix_inverse():
    ai_data = {
        "operation": "matrix_ops",
        "matrix_operation": "inverse",
        "equations": [{"lhs": "[[1, 2], [3, 4]]", "rhs": ""}]
    }
    result = handle_matrix_ops(ai_data)
    assert "Final Result: Inverse Matrix =" in result
    assert "LATEX_MATRIX" in result

def test_handle_matrix_eigenvalues():
    ai_data = {
        "operation": "matrix_ops",
        "matrix_operation": "eigenvalues",
        "equations": [{"lhs": "[[2, 0], [0, 3]]", "rhs": ""}]
    }
    result = handle_matrix_ops(ai_data)
    assert "Final Result:" in result
    assert "Eigenvalues:" in result

def test_handle_matrix_eigenvectors():
    ai_data = {
        "operation": "matrix_ops",
        "matrix_operation": "eigenvectors",
        "equations": [{"lhs": "[[2, 0], [0, 3]]", "rhs": ""}]
    }
    result = handle_matrix_ops(ai_data)
    assert "Final Result:" in result
    assert "Eigenvector(s):" in result

def test_handle_matrix_transpose():
    ai_data = {
        "operation": "matrix_ops",
        "matrix_operation": "transpose",
        "equations": [{"lhs": "[[1, 2], [3, 4]]", "rhs": ""}]
    }
    result = handle_matrix_ops(ai_data)
    assert "Transpose =" in result

def test_handle_matrix_rref():
    ai_data = {
        "operation": "matrix_ops",
        "matrix_operation": "rref",
        "equations": [{"lhs": "[[1, 2, 3], [4, 5, 6]]", "rhs": ""}]
    }
    result = handle_matrix_ops(ai_data)
    assert "Pivot columns:" in result
    assert "Final Result: RREF =" in result

def test_handle_matrix_rank():
    ai_data = {
        "operation": "matrix_ops",
        "matrix_operation": "rank",
        "equations": [{"lhs": "[[1, 2], [3, 4]]", "rhs": ""}]
    }
    result = handle_matrix_ops(ai_data)
    assert "Final Result: Rank = 2" in result

def test_handle_matrix_trace():
    ai_data = {
        "operation": "matrix_ops",
        "matrix_operation": "trace",
        "equations": [{"lhs": "[[1, 2], [3, 4]]", "rhs": ""}]
    }
    result = handle_matrix_ops(ai_data)
    assert "Final Result: Trace = 5" in result

def test_handle_matrix_missing_op():
    ai_data = {
        "operation": "matrix_ops",
        "equations": [{"lhs": "[[1, 2], [3, 4]]", "rhs": ""}]
    }
    result = handle_matrix_ops(ai_data)
    assert "Error: Matrix operation not specified" in result

def test_handle_matrix_invalid_op():
    ai_data = {
        "operation": "matrix_ops",
        "matrix_operation": "magic",
        "equations": [{"lhs": "[[1, 2], [3, 4]]", "rhs": ""}]
    }
    result = handle_matrix_ops(ai_data)
    assert "not recognized" in result

def test_handle_matrix_parse_error():
    ai_data = {
        "operation": "matrix_ops",
        "matrix_operation": "determinant",
        "equations": [{"lhs": "[[1, 2], [3, +]]", "rhs": ""}]
    }
    result = handle_matrix_ops(ai_data)
    assert "Error in matrix operation:" in result
