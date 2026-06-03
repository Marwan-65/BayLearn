import sympy as sp
from ...formatting import format_sympy_as_plain_text, explain_taylor_series_steps
from ...models.requests import SolverRequest
from ...utils.constants import DEFAULT_SERIES_ORDER, DEFAULT_SERIES_POINT
from ...utils.sympy_utils import parse_sympy_expression

def expand_taylor_series(request: SolverRequest) -> str:
    """Compute Taylor/Maclaurin series expansion."""
    try:
        expression = parse_sympy_expression(request.equations[0].lhs)
        variable = sp.Symbol(request.target_variables[0])
        point = int(request.extra_params.get("point", DEFAULT_SERIES_POINT))
        order = int(request.extra_params.get("order", DEFAULT_SERIES_ORDER))
        result = sp.series(expression, variable, point, order).removeO()
        step_text = explain_taylor_series_steps(expression, variable, point, order, result)
        return f"{step_text}\n\nFinal Result: {format_sympy_as_plain_text(result)}"
    except (TypeError, ValueError, NotImplementedError) as exc:
        return f"Error computing series: {exc}"
