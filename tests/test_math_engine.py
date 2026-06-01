"""Backend tests for the equation solver stack."""

from __future__ import annotations

from dataclasses import replace

import sympy as sp
from baylearn.core import solver as core_solver
from baylearn.math_engine.api.response_builder import build_operation_response
from baylearn.math_engine.formatting import final_text
from baylearn.math_engine.models.requests import EquationData, SolverRequest
from baylearn.math_engine.parsing.parser_utils import parse_equations, parse_target_variables
from baylearn.math_engine.parsing.validators import validate_solver_request
from baylearn.math_engine.solver import dispatcher, orchestrator
from baylearn.math_engine.solver.operations.algebra import solve_equation
from baylearn.math_engine.solver.operations.calculus import derive_expression, integrate_expression
from baylearn.math_engine.solver.operations.differential_equations import solve_differential_equation
from baylearn.math_engine.solver.operations.limits import compute_limit
from baylearn.math_engine.solver.operations.matrices import handle_matrix_operation
from baylearn.math_engine.solver.operations.partial_derivatives import compute_partial_derivative
from baylearn.math_engine.solver.operations.series import compute_series
from baylearn.math_engine.solver.operations.simplification import simplify_expression
from baylearn.math_engine.utils.exceptions import ValidationError
from baylearn.math_engine.utils.sympy_utils import parse_sympy_expression
from baylearn.math_engine.visualization.graph_extractor import extract_graphable_functions


def make_request(
    operation: str,
    lhs: str,
    rhs: str = "0",
    target_variables: list[str] | None = None,
    **extra: object,
) -> SolverRequest:
    return SolverRequest(
        operation=operation,
        equations=[EquationData(lhs=lhs, rhs=rhs)],
        target_variables=target_variables or ["x"],
        extra_params=dict(extra),
    )


def test_request_normalization_and_parsing():
    request = SolverRequest.from_ai_data(
        {
            "operation": "solve",
            "equations": [{"lhs": "x + 2", "rhs": "0"}],
            "target_variables": ["x"],
            "matrix_operation": None,
            "extra_params": {"foo": "bar"},
        }
    )

    assert request.operation == "solve"
    assert request.equations == [EquationData(lhs="x + 2", rhs="0")]
    assert request.target_variables == ["x"]
    assert request.matrix_operation is None
    assert request.extra_params == {"foo": "bar"}
    assert request.raw_data["operation"] == "solve"

    equations = parse_equations(request)
    variables = parse_target_variables(request)
    assert equations == [sp.Eq(sp.Symbol("x") + 2, 0)]
    assert variables == [sp.Symbol("x")]


def test_validate_solver_request_enforces_core_rules():
    with_exception = [
        SolverRequest(operation="", equations=[], target_variables=[]),
        SolverRequest(operation="solve", equations=[], target_variables=[]),
        SolverRequest(operation="solve", equations=[EquationData(lhs="", rhs="1")], target_variables=["x"]),
        SolverRequest(operation="solve", equations=[EquationData(lhs="x", rhs="")], target_variables=["x"]),
        SolverRequest(operation="series", equations=[EquationData(lhs="x", rhs="0")], target_variables=["x"], extra_params={"order": 0}),
        SolverRequest(
            operation="matrix_ops",
            equations=[EquationData(lhs="[[1,2],[3,4]]", rhs="0")],
            target_variables=["x"],
            matrix_operation="bad",
        ),
    ]

    for request in with_exception:
        try:
            validate_solver_request(request)
        except ValidationError:
            continue
        except Exception as exc:  # pragma: no cover - defensive
            raise AssertionError(f"Unexpected exception: {exc}") from exc
        raise AssertionError("Expected validation to fail")

    validate_solver_request(
        SolverRequest(
            operation="unknown",
            equations=[],
            target_variables=[],
        )
    )


def test_build_operation_response_and_final_text():
    assert build_operation_response("Step 1", "Answer") == "Step 1\n\nFinal Result: Answer"
    assert final_text("solve", [sp.Integer(2)], [sp.Symbol("x")]) == "Solution 1: $x = 2$"


def test_solve_equation_returns_full_result():
    output = solve_equation(make_request("solve", "x - 2", "0", ["x"]))

    assert "Step 1: Rewrite in standard form" in output
    assert "Final Result:" in output
    assert "$x = 2$" in output


def test_derivative_and_integral_handlers_include_graphable_sections():
    derivative_output = derive_expression(make_request("derive", "x**2", "0", ["x"]))
    integral_output = integrate_expression(make_request("integrate", "x", "0", ["x"]))

    assert "Graphable Functions:" in derivative_output
    assert "Derivative" in derivative_output
    assert "Graphable Functions:" in integral_output
    assert "+ C" in integral_output


def test_limit_series_simplify_and_partial_derivative_handlers_work():
    limit_output = compute_limit(
        make_request("limit", "(x**2 - 1)/(x - 1)", "1", ["x"], direction="+-")
    )
    series_output = compute_series(
        make_request("series", "exp(x)", "0", ["x"], point=0, order=4)
    )
    simplify_output = simplify_expression(make_request("simplify", "(x**2 - 1)/(x - 1)", "0", ["x"]))
    partial_output = compute_partial_derivative(
        make_request("partial_derivative", "x**2*y", "0", ["x", "y"])
    )

    assert "Final Result:" in limit_output
    assert "1" in limit_output
    assert "Final Result:" in series_output
    assert "x" in series_output
    assert "x + 1" in simplify_output
    assert "Final Result:" in partial_output
    assert "2*x" in partial_output


def test_matrix_and_differential_equation_handlers_work():
    determinant_output = handle_matrix_operation(
        SolverRequest(
            operation="matrix_ops",
            equations=[EquationData(lhs="[[1,2],[3,4]]", rhs="0")],
            target_variables=[],
            matrix_operation="determinant",
        )
    )
    dsolve_output = solve_differential_equation(
        SolverRequest(
            operation="dsolve",
            equations=[EquationData(lhs="Derivative(y(x), x)", rhs="y(x)")],
            target_variables=["y"],
        )
    )

    assert "Final Result: Determinant = -2" in determinant_output
    assert "Final Result:" in dsolve_output
    assert "y" in dsolve_output


def test_graph_extractor_returns_backend_graphable_functions():
    derived = extract_graphable_functions(
        "derive",
        {"equations": [{"lhs": "x**2"}], "target_variables": ["x"]},
        "ignored",
    )
    system_graphs = extract_graphable_functions(
        "solve_system",
        {
            "equations": [{"lhs": "y", "rhs": "x + 1"}, {"lhs": "y", "rhs": "x**2"}],
            "target_variables": ["x", "y"],
        },
        "ignored",
    )

    assert [item["name"] for item in derived] == ["Original Function", "Derivative"]
    assert system_graphs and all(item["var"] == "x" for item in system_graphs)


def test_orchestrator_and_public_wrappers_cover_the_full_backend_flow(monkeypatch):
    payload = {
        "operation": "solve",
        "equations": [{"lhs": "x - 2", "rhs": "0"}],
        "target_variables": ["x"],
    }

    monkeypatch.setattr(orchestrator, "parse_user_input", lambda _: payload)

    solved_text, returned_payload = orchestrator.level_2_solver("solve x - 2", return_translation=True)
    assert "$x = 2$" in solved_text
    assert returned_payload == payload

    monkeypatch.setattr(
        "baylearn.math_engine.main.orchestrated_level_2_solver",
        lambda **kwargs: ("wrapped", kwargs),
    )
    assert core_solver.level_2_solver("query", show_translation=True, return_translation=True) == (
        "wrapped",
        {"user_input": "query", "show_translation": True, "return_translation": True},
    )

    monkeypatch.setattr(
        "baylearn.math_engine.main.extract_graphable_functions",
        lambda operation, ai_data, solver_output: [{"operation": operation, "solver_output": solver_output}],
    )
    assert core_solver._extract_graphable_functions("solve", payload, "output") == [
        {"operation": "solve", "solver_output": "output"}
    ]


def test_dispatcher_falls_back_for_unknown_operations():
    request = replace(make_request("solve", "x - 2"), operation="not-implemented")
    assert dispatcher.dispatch_operation(request) == "Operation not fully implemented in backend yet."


def test_parse_sympy_expression_surfaces_invalid_input():
    expr = parse_sympy_expression("x + 1")
    assert expr == sp.Symbol("x") + 1
