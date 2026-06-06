import sympy as sp
from sympy.parsing.sympy_parser import parse_expr
from ..formatting import format_matrix_steps, matrix_to_latex, expr_to_clean_text

def handle_matrix_ops(ai_data: dict) -> str:
    try:
        # cast to sp.Matrix to prevent issues with handling the matrix in sympy
        raw_matrix = parse_expr(str(ai_data["equations"][0]["lhs"]))
        matrix = sp.Matrix(raw_matrix)
        operation = ai_data.get("matrix_operation")
        
        if not operation or operation in ["none", "null"]:
            return "Error: Matrix operation not specified"
            
        valid_ops = ["determinant", "inverse", "eigenvalues", "eigenvectors", "transpose", "rref", "rank", "trace"]
        if operation not in valid_ops:
            return f"Error: Matrix operation '{operation}' not recognized."
            
        if operation == "determinant":
            res = sp.simplify(matrix.det()) # this ensures numbers are clean
            st = format_matrix_steps(matrix, operation, res)
            return f"{st}\n\nFinal Result: Determinant = {expr_to_clean_text(res)}"
            
        elif operation == "inverse":
            res = matrix.inv()
            st = format_matrix_steps(matrix, operation, res)
            return f"{st}\n\nFinal Result: Inverse Matrix =\nLATEX_MATRIX:{matrix_to_latex(res)}"
            
        elif operation == "eigenvalues":
            res = matrix.eigenvals()
            st = format_matrix_steps(matrix, operation, res)
            vals_txt = ", ".join(f"λ{i} = {expr_to_clean_text(v)} (mult {m})" for i, (v, m) in enumerate(res.items(), 1))
            return f"{st}\n\nFinal Result:\nEigenvalues: {vals_txt}"
            
        elif operation == "eigenvectors":
            res = matrix.eigenvects()
            st = format_matrix_steps(matrix, operation, res)
            parts = []
            for val, mult, vecs in res:
                parts.append(f"\nEigenvalue λ = {expr_to_clean_text(val)} (multiplicity {mult})\nEigenvector(s):")
                for vec in vecs:
                    parts.append(f"LATEX_MATRIX:{matrix_to_latex(vec)}")
            
            # join the parts list without any syntax errors
            joined_parts = "\n".join(parts)
            return f"{st}\n\nFinal Result:\n{joined_parts}"
            
        elif operation == "transpose":
            res = matrix.T
            st = format_matrix_steps(matrix, operation, res)
            return f"{st}\n\nFinal Result: Transpose =\nLATEX_MATRIX:{matrix_to_latex(res)}"
            
        elif operation == "rref":
            res, pivots = matrix.rref()
            st = format_matrix_steps(matrix, operation, res)
            note = "\n\n This is the RREF form, NOT the matrix inverse layout!"
            return f"{st}\n\nPivot columns: {pivots}\n\nFinal Result: RREF =\nLATEX_MATRIX:{matrix_to_latex(res)}{note}"
            
        elif operation == "rank":
            res = matrix.rank()
            st = format_matrix_steps(matrix, operation, res)
            return f"{st}\n\nFinal Result: Rank = {res}"
            
        elif operation == "trace":
            res = matrix.trace()
            st = format_matrix_steps(matrix, operation, res)
            return f"{st}\n\nFinal Result: Trace = {expr_to_clean_text(res)}"
            
    except Exception as e:
        return f"Error in matrix operation: {e}"