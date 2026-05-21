import { useEffect, useMemo, useRef, useState } from "react";

type GraphableFunction = {
  name?: string;
  expr?: string;
  expression?: string;
  var?: string;
  type?: string;
};

type SolveResponse = {
  success: boolean;
  operation: string;
  steps: string[];
  final_result: string;
  graphable_functions: GraphableFunction[];
  ai_translation: Record<string, unknown>;
  metadata: {
    execution_time_ms?: number;
    [key: string]: unknown;
  };
};

const examples = [
  "Solve 2x + y = 10 and x - y = 2",
  "what is the derivative of e^-2x sin(3x) with respect to x",
  "integrate x^2 * exp(x) with respect to x",
  "Solve the differential equation dy/dx = 2*x with respect to y",
  "Find the determinant of [[1, 2], [3, 4]]",
  "Find the limit of (x^2 - 1)/(x - 1) as x approaches 1",
];

const operationLabels: Record<string, string> = {
  dsolve: "DSOLVE",
  matrix_ops: "MATRIX OPS",
  limit: "LIMIT",
  series: "SERIES",
  simplify: "SIMPLIFY",
  partial_derivative: "PARTIAL DERIVATIVE",
  derive: "DERIVATIVE",
  integrate: "INTEGRAL",
  solve: "SOLVE",
  solve_system: "SOLVE SYSTEM",
};

function App() {
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<SolveResponse | null>(null);
  const [activeTab, setActiveTab] = useState<"steps" | "result" | "graph">("steps");
  const stepsRef = useRef<HTMLDivElement | null>(null);
  const resultRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void window.MathJax?.typesetPromise([stepsRef.current, resultRef.current].filter(Boolean) as Element[]);
    }, 150);

    return () => window.clearTimeout(timer);
  }, [result, activeTab]);

  const operation = result?.operation ?? "unknown";
  const executionTime = result?.metadata?.execution_time_ms;
  const graphableFunctions = result?.graphable_functions ?? [];
  const operationLabel = operationLabels[operation] ?? operation.toUpperCase();

  const handleSolve = async (nextQuery: string) => {
    const cleaned = nextQuery.trim();
    if (!cleaned) {
      setError("Please enter a math prompt first.");
      return;
    }

    setLoading(true);
    setError(null);
    setResult(null);

    try {
      const response = await fetch("/run", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ query: cleaned }),
      });

      if (!response.ok) {
        throw new Error(`API error: ${response.status} ${response.statusText}`);
      }

      const data = (await response.json()) as SolveResponse;
      setResult(data);
      setActiveTab("steps");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Something went wrong.");
    } finally {
      setLoading(false);
    }
  };

  const combinedGraph = useMemo(() => graphableFunctions.filter((entry) => getExpression(entry)), [graphableFunctions]);

  return (
    <main className="shell">
      <section className="panel">
        <div className="panel__header">
          <div>
            <h2>Enter a prompt</h2>
            <p>Same backend contract, cleaner front end.</p>
          </div>
        </div>

        <textarea
          className="query"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Solve 3x + 2 = 11"
          rows={5}
          disabled={loading}
        />

        <div className="chips">
          {examples.map((example) => (
            <button
              key={example}
              type="button"
              className="chip"
              onClick={() => setQuery(example)}
              disabled={loading}
            >
              {example}
            </button>
          ))}
        </div>

        <div className="actions">
          <button type="button" className="button button--primary" onClick={() => void handleSolve(query)} disabled={loading}>
            {loading ? "Solving..." : "Solve"}
          </button>
          <button type="button" className="button button--ghost" onClick={() => setQuery("")} disabled={loading}>
            Clear
          </button>
        </div>

        {error ? <div className="alert">{error}</div> : null}
      </section>

      {result ? (
        <>
          <section className="panel panel--results">
            <div className="result-strip">
              <div>
                <span className="result-strip__label">Operation</span>
                <strong>{operationLabel}</strong>
              </div>
              <div>
                <span className="result-strip__label">Execution</span>
                <strong>{executionTime ? `${executionTime} ms` : "—"}</strong>
              </div>
              <div>
                <span className="result-strip__label">Graphable</span>
                <strong>{combinedGraph.length}</strong>
              </div>
            </div>

            <div className="tabs">
              <button
                type="button"
                className={`tab ${activeTab === "steps" ? "tab--active" : ""}`}
                onClick={() => setActiveTab("steps")}
              >
                Steps
              </button>
              <button
                type="button"
                className={`tab ${activeTab === "result" ? "tab--active" : ""}`}
                onClick={() => setActiveTab("result")}
              >
                Final result
              </button>
              <button
                type="button"
                className={`tab ${activeTab === "graph" ? "tab--active" : ""}`}
                onClick={() => setActiveTab("graph")}
              >
                Graphing
              </button>
            </div>

            {activeTab === "steps" ? (
              <div ref={stepsRef} className="steps">
                {result.steps.map((step, index) => (
                  <article key={`${index}-${step.slice(0, 24)}`} className="step-card">
                      <div className="step-content">{step}</div>
                  </article>
                ))}
              </div>
            ) : (
              activeTab === "result" ? (
                <div ref={resultRef} className="result-box">
                  <div className="result-box__label">Final Answer</div>
                    <div className="result-final">{result.final_result}</div>
                </div>
              ) : combinedGraph.length > 0 ? (
                <GraphPanel functions={combinedGraph} />
              ) : (
                <div className="result-box">
                  <div className="result-box__label">Graphing</div>
                  <div className="result-final">No graphable function was detected for this result.</div>
                </div>
              )
            )}
          </section>

          {Object.keys(result.ai_translation ?? {}).length > 0 ? (
            <details className="panel panel--compact">
              <summary>AI translation</summary>
              <pre className="json">{JSON.stringify(result.ai_translation, null, 2)}</pre>
            </details>
          ) : null}
        </>
      ) : null}
    </main>
  );
}

function GraphPanel({ functions }: { functions: GraphableFunction[] }) {
  const graphRef = useRef<HTMLDivElement | null>(null);
  const [xMin, setXMin] = useState(-10);
  const [xMax, setXMax] = useState(10);
  const [samples, setSamples] = useState(120);

  useEffect(() => {
    const element = graphRef.current;
    const plotly = window.Plotly;

    if (!element || !plotly) {
      return;
    }

    const traces = functions.map((item, index) => {
      const expr = getExpression(item);
      const points = buildPoints(expr, xMin, xMax, samples);
      return {
        x: points.map((point) => point.x),
        y: points.map((point) => point.y),
        mode: "lines",
        type: "scatter",
        name: item.name ?? `Function ${index + 1}`,
        line: {
          width: 2.5,
          color: palette[index % palette.length],
        },
        hovertemplate: `<b>${item.name ?? `Function ${index + 1}`}</b><br>x=%{x:.3f}<br>y=%{y:.6f}<extra></extra>`,
      };
    });

    void plotly.newPlot(
      element,
      traces,
      {
        margin: { l: 48, r: 24, t: 18, b: 48 },
        paper_bgcolor: "transparent",
        plot_bgcolor: "transparent",
        xaxis: {
          title: "x",
          gridcolor: "rgba(148,163,184,0.18)",
          zerolinecolor: "rgba(148,163,184,0.3)",
        },
        yaxis: {
          title: "y",
          gridcolor: "rgba(148,163,184,0.18)",
          zerolinecolor: "rgba(148,163,184,0.3)",
        },
        legend: {
          orientation: "h",
          y: -0.18,
        },
      },
      { responsive: true, displayModeBar: false },
    );

    return () => {
      plotly.purge(element);
    };
  }, [functions, xMin, xMax, samples]);

  const rows = useMemo(() => buildTraceRows(functions, xMin, xMax, samples), [functions, xMin, xMax, samples]);

  return (
    <div className="graph-panel">
      <div className="panel__header">
        <div>
          <h2>Graphing</h2>
          <p>Combined view of all graphable functions.</p>
        </div>
        <div className="controls">
          <label>
            <span>x min</span>
            <input type="number" value={xMin} onChange={(event) => setXMin(Number(event.target.value))} />
          </label>
          <label>
            <span>x max</span>
            <input type="number" value={xMax} onChange={(event) => setXMax(Number(event.target.value))} />
          </label>
          <label>
            <span>samples</span>
            <input type="number" min={20} max={300} value={samples} onChange={(event) => setSamples(Number(event.target.value))} />
          </label>
        </div>
      </div>

      <div ref={graphRef} className="graph" />

      <div className="table-wrap">
        <table className="trace-table">
          <thead>
            <tr>
              <th>x</th>
              {functions.map((item, index) => (
                <th key={item.name ?? index} style={{ color: palette[index % palette.length] }}>
                  {item.name ?? `Function ${index + 1}`}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, index) => (
              <tr key={index}>
                <td>
                  <strong>{row.x}</strong>
                </td>
                {functions.map((item, funcIndex) => (
                  <td key={`${index}-${funcIndex}`}>{row.values[funcIndex]}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function buildTraceRows(functions: GraphableFunction[], xMin: number, xMax: number, samples: number) {
  const rows: Array<{ x: string; values: string[] }> = [];
  const count = Math.max(samples, 2);

  for (let i = 0; i < count; i += 1) {
    const x = xMin + ((xMax - xMin) * i) / (count - 1);
    rows.push({
      x: x.toFixed(4),
      values: functions.map((item) => {
        const value = evaluateExpression(getExpression(item), x);
        return Number.isFinite(value) ? value.toFixed(6) : "N/A";
      }),
    });
  }

  return rows;
}

function buildPoints(expr: string, xMin: number, xMax: number, samples: number) {
  const points: Array<{ x: number; y: number }> = [];
  const count = Math.max(samples, 2);

  for (let i = 0; i < count; i += 1) {
    const x = xMin + ((xMax - xMin) * i) / (count - 1);
    const y = evaluateExpression(expr, x);
    if (Number.isFinite(y)) {
      points.push({ x, y });
    }
  }

  return points;
}

function evaluateExpression(expr: string, x: number) {
  try {
    const jsExpr = sympyToJavaScript(expr);
    const evaluator = new Function("x", `return ${jsExpr};`) as (value: number) => number;
    const result = evaluator(x);
    return typeof result === "number" ? result : Number(result);
  } catch {
    return Number.NaN;
  }
}

function getExpression(entry: GraphableFunction) {
  return entry.expression ?? entry.expr ?? "";
}

function sympyToJavaScript(expr: string) {
  let js = expr.replace(/\s+/g, "");
  js = js.replace(/\bexp\(/g, "Math.exp(");
  js = js.replace(/\blog\(/g, "Math.log(");
  js = js.replace(/\bsin\(/g, "Math.sin(");
  js = js.replace(/\bcos\(/g, "Math.cos(");
  js = js.replace(/\btan\(/g, "Math.tan(");
  js = js.replace(/\bsqrt\(/g, "Math.sqrt(");
  js = js.replace(/\babs\(/g, "Math.abs(");
  js = js.replace(/\bpi\b/g, "Math.PI");
  js = js.replace(/\bE\b/g, "Math.E");

  const powerPattern = /(\([^()]+\)|[A-Za-z_][A-Za-z0-9_]*|-?\d+(?:\.\d+)?)\*\*(\([^()]+\)|[A-Za-z_][A-Za-z0-9_]*|-?\d+(?:\.\d+)?)/;
  let previous = "";
  while (js.includes("**") && js !== previous) {
    previous = js;
    js = js.replace(powerPattern, "Math.pow($1,$2)");
  }

  return js;
}

const palette = ["#1d4ed8", "#db2777", "#059669", "#d97706", "#7c3aed", "#0891b2"];

export default App;
