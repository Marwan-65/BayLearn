import re
from datetime import datetime

import plotly.graph_objects as go
import sympy as sp
import streamlit as st
from sympy.parsing.sympy_parser import (
    implicit_multiplication_application,
    parse_expr,
    standard_transformations,
)

from level2_solver import level_2_solver

st.set_page_config(
    page_title="BayLearn Math Solver",
    page_icon="📈",
    layout="wide",
)

st.markdown(
    """
    <style>
    :root {
        --bg: #f7fafc;
        --surface: #ffffff;
        --text: #1e2a38;
        --muted: #4b5d73;
        --primary: #0f4c81;
        --primary-soft: #dfeef9;
        --success: #1f7a4d;
        --border: #d7e2ee;
        --accent: #f59e0b;
    }

    .stApp {
        background:
            radial-gradient(circle at 90% 5%, #eef7ff 0%, transparent 32%),
            radial-gradient(circle at 8% 2%, #fff6e9 0%, transparent 30%),
            var(--bg);
        color: var(--text);
    }

    .block-container {
        padding-top: 1.2rem;
        padding-bottom: 1.8rem;
    }

    .hero {
        background: linear-gradient(120deg, #f4f9ff 0%, #ffffff 58%, #fff8ec 100%);
        border: 1px solid var(--border);
        border-radius: 14px;
        padding: 1rem 1.15rem;
        margin-bottom: 0.8rem;
    }

    .hero h1 {
        margin: 0;
        color: #16324f;
        font-size: 1.75rem;
    }

    .hero p {
        margin: 0.35rem 0 0;
        color: var(--muted);
        font-size: 0.97rem;
    }

    .indicator-row {
        display: flex;
        gap: 0.45rem;
        flex-wrap: wrap;
        margin-top: 0.65rem;
    }

    .indicator {
        background: var(--primary-soft);
        border: 1px solid #c8ddf0;
        color: #174368;
        padding: 0.18rem 0.56rem;
        border-radius: 999px;
        font-size: 0.8rem;
        font-weight: 600;
    }

    .stTabs [data-baseweb="tab-list"] {
        gap: 0.3rem;
    }

    .stTabs [data-baseweb="tab"] {
        background: #eef3f8;
        border-radius: 8px 8px 0 0;
        border: 1px solid var(--border);
        border-bottom: none;
        padding: 0.5rem 0.8rem;
        color: var(--text) !important;
    }

    .stTabs [aria-selected="true"] {
        background: #ffffff;
        color: var(--primary);
        font-weight: 700;
    }

    .streamlit-expanderHeader {
        color: var(--text) !important;
    }
    .streamlit-expanderHeader p {
        color: var(--text) !important;
    }
    .streamlit-expanderContent {
        background: #ffffff !important;
        color: var(--text) !important;
    }
    .streamlit-expanderContent > div {
        color: var(--text) !important;
    }

    .stButton button {
        background: #003d7a !important;
        color: #ffffff !important;
        border: 1px solid #001a3d !important;
        font-weight: 600;
    }
    .stButton button:hover {
        background: #002d5e !important;
    }

    section[data-testid="stSidebar"] {
        background: #f3f7fb;
        border-right: 1px solid var(--border);
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    """
    <div class="hero">
      <h1>BayLearn Math Workspace</h1>
      <p>Type a request in natural language, solve it, then inspect graphable equations in a dedicated graph tab.</p>
      <div class="indicator-row">
        <span class="indicator">Light Mode</span>
        <span class="indicator">Structured Steps</span>
        <span class="indicator">Interactive Graphing</span>
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)

if "history" not in st.session_state:
    st.session_state.history = []
if "last_result" not in st.session_state:
    st.session_state.last_result = "Your solution will appear here."
if "user_input" not in st.session_state:
    st.session_state.user_input = "Solve 2x + y = 10 and x - y = 2"
if "last_translation" not in st.session_state:
    st.session_state.last_translation = None


def _to_sympy_expr(text):
    normalized = text.strip().replace("^", "**")
    return sp.sympify(normalized, evaluate=False)


def _parse_math_expr(text):
    transformations = standard_transformations + (implicit_multiplication_application,)
    return parse_expr(text.strip().replace("^", "**"), transformations=transformations)


def _numeric_value(expr_value):
    simplified = sp.N(expr_value)
    if getattr(simplified, "is_real", None) is False or simplified.has(sp.I):
        return None
    try:
        return float(simplified)
    except Exception:
        return None


def _expr_to_readable_text(expr):
    """Convert sympy expression to readable text format (not LaTeX)."""
    text = sp.sstr(expr)
    # Replace ** with ^ for better readability
    text = text.replace("**", "^")
    # Clean up spaces around operators
    text = text.replace(" ", "")
    return text


def _render_math_equation(left_text, right_text):
    try:
        left_expr = _to_sympy_expr(left_text)
        right_expr = _to_sympy_expr(right_text)
        st.latex(f"{sp.latex(left_expr)} = {sp.latex(right_expr)}")
    except Exception:
        st.write(f"{left_text} = {right_text}")


def _render_solution_assignments(text):
    chunks = [chunk.strip() for chunk in text.split("|") if chunk.strip()]
    for chunk in chunks:
        if ":" in chunk:
            label, body = chunk.split(":", 1)
            st.markdown(f"**{label.strip()}**")
        else:
            body = chunk

        assignments = [part.strip() for part in body.split(",") if "=" in part]
        if not assignments:
            st.write(chunk)
            continue

        for assignment in assignments:
            left_text, right_text = assignment.split("=", 1)
            _render_math_equation(left_text, right_text)


def render_solver_output(output_text):
    final_match = re.search(r"Final Result:\s*(.+)$", output_text, flags=re.S)
    steps_text = output_text.strip()
    final_text = ""

    if final_match:
        steps_text = output_text[: final_match.start()].strip()
        final_text = final_match.group(1).strip()

    if steps_text:
        with st.expander("Solution Steps", expanded=True):
            for raw_line in steps_text.splitlines():
                line = raw_line.strip()
                if not line:
                    continue

                if line.startswith("Step "):
                    st.markdown(f"**{line}**")
                    continue

                if ":" in line and "=" in line:
                    prefix, expression_part = line.split(":", 1)
                    left_text, right_text = expression_part.split("=", 1)
                    st.write(prefix.strip())
                    _render_math_equation(left_text, right_text)
                    continue

                if line.startswith("Eq") and "=" in line:
                    left_text, right_text = line.split("=", 1)
                    _render_math_equation(left_text, right_text)
                    continue

                if " = " in line:
                    left_text, right_text = line.split("=", 1)
                    _render_math_equation(left_text, right_text)
                    continue

                st.write(line)

    if final_text:
        st.markdown("### Final Result")
        if "=" in final_text and not final_text.startswith("[") and not final_text.startswith("("):
            _render_solution_assignments(final_text)
        else:
            try:
                final_expr = _to_sympy_expr(final_text)
                st.latex(sp.latex(final_expr))
            except Exception:
                st.write(final_text)


def _extract_graph_functions(ai_translation):
    x_symbol, y_symbol = sp.symbols("x y")
    parsed = []

    if not ai_translation:
        return parsed

    for equation_index, eq_data in enumerate(ai_translation.get("equations", []), start=1):
        lhs_text = str(eq_data.get("lhs", "")).strip()
        rhs_text = str(eq_data.get("rhs", "")).strip()
        if not lhs_text and not rhs_text:
            continue

        try:
            lhs_expr = _parse_math_expr(lhs_text)
            rhs_expr = _parse_math_expr(rhs_text)
            equation = sp.Eq(lhs_expr, rhs_expr)
            branches = sp.solve(equation, y_symbol)
        except Exception:
            continue

        for branch_index, branch in enumerate(branches, start=1):
            if branch.has(y_symbol):
                continue
            branch_label = f"Eq {equation_index}" if len(branches) == 1 else f"Eq {equation_index} - branch {branch_index}"
            parsed.append(
                {
                    "label": branch_label,
                    "equation": equation,
                    "expression": sp.simplify(branch),
                    "equation_text": f"{lhs_text} = {rhs_text}",
                }
            )

    return parsed


def _build_trace_rows(branches, x_values):
    x_symbol = sp.Symbol("x")
    rows = []
    
    # Pre-compute column headers for all branches
    column_headers = {}
    for index, branch in enumerate(branches):
        equation_str = _expr_to_readable_text(branch["expression"])
        # Use shorter column name with just the label
        column_headers[index] = f"{branch['label']}"

    for x_val in x_values:
        row = {"x": float(x_val)}
        for index, branch in enumerate(branches):
            value = _numeric_value(branch["expression"].subs(x_symbol, x_val))
            col_header = column_headers[index]
            row[col_header] = value if value is not None else "undefined"
        rows.append(row)

    return rows


def _build_plot(branches, x_values):
    x_symbol = sp.Symbol("x")
    fig = go.Figure()
    colors = ["#0f4c81", "#d97706", "#059669", "#7c3aed", "#dc2626", "#14b8a6"]

    for branch_index, branch in enumerate(branches):
        y_values = []
        for x_val in x_values:
            value = _numeric_value(branch["expression"].subs(x_symbol, x_val))
            y_values.append(value)

        # Create legend entry with equation in readable text format
        equation_str = _expr_to_readable_text(branch["expression"])
        trace_name = f"{branch['label']}: y = {equation_str}"

        fig.add_trace(
            go.Scatter(
                x=x_values,
                y=y_values,
                mode="lines+markers",
                name=trace_name,
                line=dict(color=colors[branch_index % len(colors)], width=2.5),
                marker=dict(size=4),
                hovertemplate="<b>" + trace_name + "</b><br>x=%{x:.3f}<br>y=%{y:.3f}<extra></extra>",
            )
        )

    fig.update_layout(
        title="Equation Graph",
        xaxis_title="x",
        yaxis_title="y",
        paper_bgcolor="#ffffff",
        plot_bgcolor="#ffffff",
        hovermode="x unified",
        margin=dict(l=24, r=24, t=52, b=120),
        legend=dict(
            orientation="v",
            yanchor="top",
            y=0.99,
            xanchor="left",
            x=0.01,
            bgcolor="rgba(255, 255, 255, 0.85)",
            bordercolor="#d7e2ee",
            borderwidth=1,
            font=dict(color="#1e2a38", size=12),
        ),
    )
    fig.update_xaxes(showgrid=True, gridcolor="#e5edf4")
    fig.update_yaxes(showgrid=True, gridcolor="#e5edf4", zeroline=True, zerolinecolor="#cdd8e5")

    return fig


tab_solver, tab_graph = st.tabs(["Equation Solver", "Graphing + Tracing"])

with tab_solver:
    sample_prompts = {
        "Linear system": "Solve 2x + y = 10 and x - y = 2",
        "Derivative": "what is the derivative of e^-2x sin(3x) with respect to x",
        "Integral": "integrate x^2 * exp(x) with respect to x",
        "Quadratic": "solve y = x^2 - 4x + 1",
    }

    col_example, col_toggle = st.columns([1.2, 1])
    with col_example:
        selected_example = st.selectbox("Quick examples", list(sample_prompts.keys()))
    with col_toggle:
        show_translation = st.toggle("Show AI translation JSON", value=False)

    if st.button("Use selected example"):
        st.session_state.user_input = sample_prompts[selected_example]

    user_input = st.text_area(
        "Enter your math request",
        value=st.session_state.user_input,
        height=145,
        placeholder="Example: Solve 3x + 2 = 11",
    )

    solve_clicked = st.button("Solve", type="primary")

    if solve_clicked:
        cleaned_input = user_input.strip()
        st.session_state.user_input = cleaned_input
        if not cleaned_input:
            st.warning("Please enter a math prompt first.")
        else:
            with st.spinner("Solving..."):
                solved_text, translation_data = level_2_solver(
                    cleaned_input,
                    show_translation=show_translation,
                    return_translation=True,
                )
                st.session_state.last_result = solved_text
                st.session_state.last_translation = translation_data
                st.session_state.history.append(
                    {
                        "prompt": cleaned_input,
                        "result": solved_text,
                        "translation": translation_data,
                        "timestamp": datetime.now().strftime("%H:%M"),
                    }
                )
                if len(st.session_state.history) > 20:
                    st.session_state.history = st.session_state.history[-20:]

    if st.session_state.last_translation and isinstance(st.session_state.last_translation, dict):
        operation = st.session_state.last_translation.get("operation", "unknown")
        graphable_count = len(_extract_graph_functions(st.session_state.last_translation))
        status_col1, status_col2 = st.columns(2)
        with status_col1:
            op_display = operation.upper()
            if operation == "dsolve":
                st.success(f"Operation: {op_display} (Differential Equation)")
            else:
                st.info(f"Detected operation: {op_display}")
        with status_col2:
            if operation == "dsolve":
                st.caption("Graphing: View general solution in Graphing tab")
            elif graphable_count > 0:
                st.success(f"Graphable equations: {graphable_count}")
            else:
                st.caption(f"Graphable equations: {graphable_count}")

    render_solver_output(st.session_state.last_result)

    if show_translation and st.session_state.last_translation:
        st.markdown("### AI Translation JSON")
        st.json(st.session_state.last_translation)

with tab_graph:
    st.markdown("### Graphing Module")
    st.caption("This tab uses equations extracted from the latest AI translation JSON.")

    graph_functions = _extract_graph_functions(st.session_state.last_translation)
    
    # Check if this is a differential equation solution
    is_diff_eq = st.session_state.last_translation and st.session_state.last_translation.get("operation") == "dsolve"

    if not st.session_state.last_translation:
        st.warning("Solve a prompt first to generate AI translation JSON.")
    elif is_diff_eq:
        st.info("📊 **Differential Equation Solution Detected**")
        st.write("Differential equations produce **general solutions** with arbitrary constants (like C1, C2, etc.).")
        st.write("To graph the solution, specify values for these constants below:")
        
        # Extract the general solution from the result
        if st.session_state.last_result:
            st.markdown("**General Solution:**")
            st.code(st.session_state.last_result.split('\n')[-1], language="text")
            
            # Try to extract constant symbols from the solution text
            solution_text = st.session_state.last_result
            import re as regex
            constants = sorted(set(regex.findall(r'\bC\d+\b', solution_text)))
            
            if constants:
                st.markdown("**Specify constant values for plotting:**")
                const_values = {}
                cols = st.columns(min(3, len(constants)))
                for idx, const in enumerate(constants):
                    with cols[idx % len(cols)]:
                        const_values[const] = st.number_input(
                            f"Value of {const}",
                            value=1.0,
                            step=0.1,
                            key=f"const_{const}"
                        )
                
                # Graph control parameters
                st.markdown("**Graph Parameters:**")
                graph_col1, graph_col2, graph_col3 = st.columns(3)
                with graph_col1:
                    x_min_diff = st.number_input("x min", value=-10.0, step=1.0, key="diff_x_min")
                with graph_col2:
                    x_max_diff = st.number_input("x max", value=10.0, step=1.0, key="diff_x_max")
                with graph_col3:
                    points_diff = st.slider("Sample points", min_value=50, max_value=300, value=150, step=10, key="diff_points")
                
                if st.button("Plot solution", type="primary", key="plot_diff_eq"):
                    try:
                        # Extract the solution expression from "Final Result: Eq(y(x), expression)"
                        final_result_line = st.session_state.last_result.split("Final Result: ")[-1].strip()
                        
                        # Parse the equation to extract the RHS
                        # Format: Eq(y(x), expression) or similar
                        if "Eq(" in final_result_line:
                            # Extract content between the commas
                            eq_content = final_result_line[final_result_line.find("Eq(") + 3 : final_result_line.rfind(")")]
                            parts = eq_content.split(",", 1)
                            if len(parts) == 2:
                                solution_expr_str = parts[1].strip()
                            else:
                                solution_expr_str = parts[0].strip()
                        else:
                            solution_expr_str = final_result_line
                        
                        # Create symbols for parsing
                        x_sym = sp.Symbol("x")
                        const_symbols = {const: sp.Symbol(const) for const in constants}
                        
                        # Parse the expression
                        solution_expr = parse_expr(
                            solution_expr_str,
                            transformations=(standard_transformations + (implicit_multiplication_application,)),
                            local_dict={"x": x_sym, **const_symbols}
                        )
                        
                        # Substitute constant values
                        substitutions = {sp.Symbol(const): const_values[const] for const in constants}
                        solution_with_values = solution_expr.subs(substitutions)
                        
                        # Create x values
                        if x_min_diff >= x_max_diff:
                            st.error("x min must be smaller than x max.")
                        else:
                            x_values = [x_min_diff + (x_max_diff - x_min_diff) * i / (points_diff - 1) for i in range(points_diff)]
                            
                            # Compute y values
                            y_values = []
                            for x_val in x_values:
                                try:
                                    y_val = float(solution_with_values.subs(x_sym, x_val))
                                    y_values.append(y_val)
                                except (TypeError, ValueError):
                                    y_values.append(None)
                            
                            # Create the plot
                            fig = go.Figure()
                            
                            # Add the solution curve
                            const_str = ", ".join([f"{c}={const_values[c]}" for c in constants])
                            label = f"y(x) with {const_str}"
                            
                            fig.add_trace(
                                go.Scatter(
                                    x=x_values,
                                    y=y_values,
                                    mode="lines+markers",
                                    name=label,
                                    line=dict(color="#0f4c81", width=2.5),
                                    marker=dict(size=4),
                                    hovertemplate="<b>" + label + "</b><br>x=%{x:.3f}<br>y=%{y:.3f}<extra></extra>",
                                )
                            )
                            
                            fig.update_layout(
                                title=f"Differential Equation Solution",
                                xaxis_title="x",
                                yaxis_title="y(x)",
                                paper_bgcolor="#ffffff",
                                plot_bgcolor="#ffffff",
                                hovermode="x unified",
                                margin=dict(l=24, r=24, t=52, b=52),
                                legend=dict(
                                    orientation="v",
                                    yanchor="top",
                                    y=0.99,
                                    xanchor="left",
                                    x=0.01,
                                    bgcolor="rgba(255, 255, 255, 0.85)",
                                    bordercolor="#d7e2ee",
                                    borderwidth=1,
                                    font=dict(color="#1e2a38", size=12),
                                ),
                            )
                            fig.update_xaxes(showgrid=True, gridcolor="#e5edf4")
                            fig.update_yaxes(showgrid=True, gridcolor="#e5edf4", zeroline=True, zerolinecolor="#cdd8e5")
                            
                            st.plotly_chart(fig, use_container_width=True)
                            
                            # Show the evaluated solution
                            st.success("✅ Solution plotted successfully!")
                            st.write(f"**Plotted solution:** y(x) = {_expr_to_readable_text(solution_with_values)}")
                    
                    except Exception as e:
                        st.error(f"Error plotting solution: {str(e)}")
                        st.write("Make sure the general solution is in the format: Eq(y(x), expression)")
            else:
                st.write("General solution found. Use the solve tab to see the complete solution with steps.")
    elif not graph_functions:
        st.warning("No y(x) equations were found in the latest translation. Try a graphable equation such as y = x^2 - 3x.")
    else:
        for item in graph_functions:
            st.latex(f"{item['label']}:\\quad y = {sp.latex(item['expression'])}")

        control_col1, control_col2, control_col3 = st.columns(3)
        with control_col1:
            x_min = st.number_input("x min", value=-10.0, step=1.0)
        with control_col2:
            x_max = st.number_input("x max", value=10.0, step=1.0)
        with control_col3:
            points = st.slider("Sample points", min_value=30, max_value=400, value=160, step=10)

        if x_min >= x_max:
            st.error("x min must be smaller than x max.")
        else:
            x_values = [x_min + (x_max - x_min) * i / (points - 1) for i in range(points)]
            figure = _build_plot(graph_functions, x_values)
            st.plotly_chart(figure, use_container_width=True)

            st.markdown("### Tracing Table")
            
            # Show equation legend
            st.write("**Column Definitions:**")
            for branch in graph_functions:
                equation_str = _expr_to_readable_text(branch["expression"])
                st.write(f"- **{branch['label']}**: y = {equation_str}")
            
            trace_points = st.slider("Tracing points", min_value=3, max_value=40, value=9, step=1)
            trace_x = [x_min + (x_max - x_min) * i / (trace_points - 1) for i in range(trace_points)]
            table_rows = _build_trace_rows(graph_functions, trace_x)
            st.dataframe(table_rows, use_container_width=True)

st.caption("Powered by Groq and SymPy")
