"""Backward-compatible solver exports."""

from ..math_engine.main import _extract_graphable_functions, level_2_solver
from ..math_engine.solver.orchestrator import solve_from_ai_data as _solve_from_ai_data

__all__ = ["level_2_solver", "_extract_graphable_functions", "_solve_from_ai_data"]


if __name__ == "__main__":
    examples = [
        "Solve 2x + y = 10 and x - y = 2",
        "what is the derivative of e^-2x sin(3x) with respect to x",
        "Solve the differential equation dy/dx = 2*x with respect to y",
        "Find the determinant of [[1, 2], [3, 4]]",
        "Find the inverse of the matrix [[2, 1], [1, 3]]",
        "Find the limit of (x^2 - 1)/(x - 1) as x approaches 1",
        "Find the Taylor series of e^x at x=0 up to order 5",
        "Simplify (x^2 - 1)/(x - 1)",
        "Find the partial derivative of x^2*y + y^3 with respect to x and then y",
    ]
    for prompt in examples:
        print(level_2_solver(prompt, show_translation=True))
        print("\n" + "=" * 60 + "\n")
