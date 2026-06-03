import sympy as sp
from sympy.parsing.sympy_parser import parse_expr
from ...formatting import format_sympy_as_plain_text, explain_matrix_operation_steps, convert_to_safe_latex
from ...models.requests import SolverRequest
from ...utils.constants import VALID_MATRIX_OPERATIONS

def perform_matrix_operation(request: SolverRequest) -> str:
    """Handle all supported matrix operations.
    Args:
        request: Typed solver request.
    Returns:
        Matrix operation output text.
    """
    try:
        matrix = parse_expr(str(request.equations[0].lhs))
        if isinstance(matrix, list):
            matrix = matrix[0] if matrix and isinstance(matrix[0], list) and len(matrix) == 1 else matrix
            matrix = sp.Matrix(matrix)
        operation = request.matrix_operation

        if not operation or operation == "none" or operation == "null":
            return (
                "Error: Matrix operation not specified. Please specify what to do with the matrix.\n"
                "Available operations: determinant, inverse, eigenvalues, eigenvectors, transpose, rref, rank, trace.\n"
                "Example: 'Find the determinant of [[1,2],[3,4]]'"
            )

        if operation not in VALID_MATRIX_OPERATIONS:
            return (
                f"Error: Matrix operation '{operation}' not recognized.\n"
                f"Valid operations: {', '.join(VALID_MATRIX_OPERATIONS)}"
            )

        if operation == "determinant":
            result = matrix.det()
            step_text = explain_matrix_operation_steps(matrix, operation, result)
            return f"{step_text}\n\nFinal Result: Determinant = {format_sympy_as_plain_text(result)}"

        if operation == "inverse":
            det_value = sp.simplify(matrix.det())
            if det_value == 0:
                step_text = explain_matrix_operation_steps(matrix, operation, None)
                return f"{step_text}\n\nFinal Result: Inverse does not exist because det(A) = 0."

            result = matrix.inv()
            step_text = explain_matrix_operation_steps(matrix, operation, result)
            result_latex = convert_to_safe_latex(result)
            return f"{step_text}\n\nFinal Result: Inverse Matrix = ${result_latex}$"

        if operation == "eigenvalues":
            result = matrix.eigenvals()
            step_text = explain_matrix_operation_steps(matrix, operation, result)
            eigenval_text = ", ".join(
                f"λ{i} = {format_sympy_as_plain_text(val)} (multiplicity {mult})"
                for i, (val, mult) in enumerate(result.items(), 1)
            )
            return f"{step_text}\n\nFinal Result:\nEigenvalues: {eigenval_text}"

        if operation == "eigenvectors":
            result = matrix.eigenvects()
            step_text = explain_matrix_operation_steps(matrix, operation, result)
            eigenvec_parts = []
            for val, mult, vecs in result:
                eigenvec_parts.append(f"\nEigenvalue λ = {format_sympy_as_plain_text(val)} (multiplicity {mult})")
                eigenvec_parts.append("Eigenvector(s):")
                for vec in vecs:
                    vec_latex = convert_to_safe_latex(vec)
                    eigenvec_parts.append(f"${vec_latex}$")
            eigenvec_text = "\n".join(eigenvec_parts)
            return f"{step_text}\n\nFinal Result:{eigenvec_text}"

        if operation == "transpose":
            result = matrix.T
            step_text = explain_matrix_operation_steps(matrix, operation, result)
            result_latex = convert_to_safe_latex(result)
            return f"{step_text}\n\nFinal Result: Transpose = ${result_latex}$"

        if operation == "rref":
            result, pivot_cols = matrix.rref()
            step_text = explain_matrix_operation_steps(matrix, operation, result)
            result_latex = convert_to_safe_latex(result)
            note = "\n\n⚠️  Note: This is the RREF (Row Reduced Echelon Form), NOT the inverse!"
            note += "\nTo find the inverse, use: 'Calculate the inverse of [[...]]'"
            return (
                f"{step_text}\n\nPivot columns: {pivot_cols}\n\n"
                f"Final Result: RREF = ${result_latex}${note}"
            )

        if operation == "rank":
            result = matrix.rank()
            step_text = explain_matrix_operation_steps(matrix, operation, result)
            return f"{step_text}\n\nFinal Result: Rank = {result}"

        if operation == "trace":
            result = matrix.trace()
            step_text = explain_matrix_operation_steps(matrix, operation, result)
            return f"{step_text}\n\nFinal Result: Trace = {format_sympy_as_plain_text(result)}"

        return f"Matrix operation '{operation}' not recognized"

    except (TypeError, ValueError, ArithmeticError) as exc:
        return f"Error in matrix operation: {exc}"
