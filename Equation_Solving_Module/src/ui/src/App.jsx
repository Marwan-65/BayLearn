import React, { useState, useMemo } from "react";
import axios from "axios";
import { evaluate } from "mathjs";
import PlotlyPlot from "react-plotly.js";
import { BlockMath, InlineMath } from "react-katex"; 
import "katex/dist/katex.min.css";

const Plot = PlotlyPlot.default || PlotlyPlot;

// --- UTILITY: Safe Math Wrapper ---
const SafeMath = ({ math, block = false }) => {
  try {
    return block ? <BlockMath math={math} /> : <InlineMath math={math} />;
  } catch (e) {
    console.error("KaTeX Parsing Error:", e, "Input:", math);
    return <code style={{ background: '#fee2e2', color: '#991b1b', padding: '2px 4px' }}>{math}</code>;
  }
};

const SAMPLE_PROMPTS = {
  "Select a quick example...": "",
  "Linear system": "Solve 2x + y = 10 and x - y = 2",
  "Derivative": "what is the derivative of e^-2x sin(3x) with respect to x",
  "Integral": "integrate x^2 * exp(x) with respect to x",
  "Quadratic": "solve y = x^2 - 4x + 1",
  "Differential Equation": "Solve the differential equation dy/dx = 2*x with respect to y",
  "Matrix Determinant": "Find the determinant of [[1, 2], [3, 4]]",
  "Matrix Inverse": "Calculate the inverse of [[2, 1], [1, 3]]",
  "Limit": "Find the limit of (x^2 - 1)/(x - 1) as x approaches 1",
  "Taylor Series": "Taylor series of sin(x) at x=0 up to order 5",
  "Simplify": "Simplify (x^2 - 9)/(x - 3)",
  "Partial Derivative": "Find the partial derivative of x^2*y + y^3 with respect to x"
};

export default function EquationLab() {
  const [input, setInput] = useState("");
  const [isSolving, setIsSolving] = useState(false);
  const [activeTab, setActiveTab] = useState("steps");
  const [error, setError] = useState(null);

  const [steps, setSteps] = useState([]);
  const [finalResult, setFinalResult] = useState(null);
  const [graphableFunctions, setGraphableFunctions] = useState([]);
  const [operationInfo, setOperationInfo] = useState(null);

  const [xMin, setXMin] = useState(-10);
  const [xMax, setXMax] = useState(10);
  const [samplePoints, setSamplePoints] = useState(150);
  const [tracePoints, setTracePoints] = useState(9);

  const handleSolve = async (e) => {
    if (e) e.preventDefault();
    if (!input.trim()) return;
    
    setIsSolving(true);
    setError(null);
    
    try {
      const response = await axios.post('http://localhost:9001/run', { query: input });
      const { data } = response;
      
      if (data.success) {
        setSteps(data.steps || []);
        setFinalResult(data.final_result);
        setGraphableFunctions(data.graphable_functions || []);
        setOperationInfo(data.operation);
        setActiveTab("steps");
      }
    } catch (err) {
      console.error("Solver Error:", err);
      const errorDetail = err.response?.data?.detail;
      setError(typeof errorDetail === 'string' ? errorDetail : "Failed to connect to the backend API.");
    } finally {
      setIsSolving(false);
    }
  };

  const cleanMath = (str) => {
    if (!str) return "";
    let s = str.replace(/\*\*/g, '^');
    s = s.replace(/[−\u2212]/g, '-');
    s = s.replace(/d[¸,.]ot/g, '\\cdot ');
    // Strip \tmspace tokens SymPy sometimes emits (unsupported in KaTeX)
    s = s.replace(/\\tmspace\s*\+\s*[\d.]+[a-z]+/g, '\\,');
    s = s.replace(/\\tmspace\b[^}]*/g, '\\,');
    s = s.replace(/\\nobreakspace\b/g, '~');
    // SymPy wraps trig args: \sin{\left(x\right)} → \sin\left(x\right)
    // KaTeX rejects \sin{...} containing \left — remove the extra braces
    const trig = '(?:sin|cos|tan|cot|sec|csc|sinh|cosh|tanh|log|ln|exp|arcsin|arccos|arctan)';
    s = s.replace(new RegExp(`(\\\\${trig})\\{(\\\\left\\b)`, 'g'), '$1$2');
    s = s.replace(/(\\right\s*[)\]|])\}/g, '$1');
    return s.trim();
  };

  // Strip exactly one layer of $ or $$ delimiters from a final result string
  const stripMathDelimiters = (str) => {
    if (!str) return "";
    if (str.startsWith('$$') && str.endsWith('$$')) return str.slice(2, -2);
    if (str.startsWith('$') && str.endsWith('$') && str.length > 1) return str.slice(1, -1);
    return str;
  };

  const renderStep = (stepText, idx) => {
    const lines = stepText.split('\n');

    return (
      <div key={idx} style={S.stepBlock}>
        {lines.map((line, i) => {
          const trimmed = line.trim();
          if (!trimmed) return null;

          if (trimmed.toLowerCase().startsWith('step')) {
            return (
              <div key={i} style={{ fontWeight: 700, marginBottom: 12, color: '#111827', fontSize: 16 }}>
                {trimmed}
              </div>
            );
          }

          // If the line has no $ delimiters but contains LaTeX commands (e.g. \quad, \frac),
          // wrap the whole thing as inline math so KaTeX renders it instead of showing raw text.
          const hasLatexCommands = /\\[a-zA-Z]/.test(trimmed);
          const hasMathDelimiters = /\$/.test(trimmed);
          if (hasLatexCommands && !hasMathDelimiters) {
            return (
              <div key={i} style={{ marginBottom: 8, color: '#374151', lineHeight: '1.6' }}>
                <SafeMath math={cleanMath(trimmed)} />
              </div>
            );
          }

          // Split line into math and text segments.
          // Match $$...$$ first (block), then $...$ (inline). Use a non-greedy match.
          const parts = trimmed.split(/(\$\$[\s\S]+?\$\$|\$[^$]+?\$)/g);

          return (
            <div key={i} style={{ marginBottom: 8, color: '#374151', lineHeight: '1.6' }}>
              {parts.map((part, pIdx) => {
                if (part.startsWith('$$') && part.endsWith('$$')) {
                  return <SafeMath key={pIdx} block math={cleanMath(part.slice(2, -2))} />;
                }
                if (part.startsWith('$') && part.endsWith('$')) {
                  return <SafeMath key={pIdx} math={cleanMath(part.slice(1, -1))} />;
                }
                return <span key={pIdx}>{part}</span>;
              })}
            </div>
          );
        })}
      </div>
    );
  };

  const plotData = useMemo(() => {
    if (!graphableFunctions || graphableFunctions.length === 0) return [];
    const stepSize = (xMax - xMin) / (samplePoints - 1);
    const xValues = Array.from({ length: samplePoints }, (_, i) => xMin + i * stepSize);
    const colors = ["#0ea5e9", "#f59e0b", "#10b981", "#8b5cf6"];

    return graphableFunctions.map((func, index) => {
      const safeExpr = func.expression.replace(/\*\*/g, '^');
      const yValues = xValues.map(x => {
        try { return evaluate(safeExpr, { [func.var]: x }); } catch (e) { return null; }
      });
      return {
        x: xValues, y: yValues, type: 'scatter', mode: 'lines', name: func.name,
        line: { color: colors[index % colors.length], width: 2.5 },
      };
    });
  }, [graphableFunctions, xMin, xMax, samplePoints]);

  const traceRows = useMemo(() => {
    if (!graphableFunctions || graphableFunctions.length === 0) return [];
    const stepSize = (xMax - xMin) / (tracePoints - 1);
    const traceXValues = Array.from({ length: tracePoints }, (_, i) => xMin + i * stepSize);
    return traceXValues.map(xVal => {
       const row = { x: xVal };
       graphableFunctions.forEach(func => {
           const safeExpr = func.expression.replace(/\*\*/g, '^');
           try { row[func.name] = evaluate(safeExpr, { [func.var]: xVal }); } catch(e) { row[func.name] = null; }
       });
       return row;
    });
  }, [graphableFunctions, xMin, xMax, tracePoints]);

  return (
    <div style={S.page}>
      <header style={S.header}>
        <div style={S.headerLeft}>
          <div style={S.logo}>∑</div>
          <div>
            <div style={{ fontWeight: 700, fontSize: 16, color: "#111827" }}>Equation Lab</div>
            <div style={{ fontSize: 11, color: "#888" }}>Symbolic & numeric solver</div>
          </div>
        </div>
      </header>

      <main style={S.main}>
        <div style={S.container}>
          <div style={S.card}>
            <label style={S.label}>Natural Language Request</label>
            <form onSubmit={handleSolve} style={S.inputRow}>
              <input value={input} onChange={(e) => setInput(e.target.value)} placeholder="e.g. Solve 3x + 2 = 11" style={S.input} />
              <button type="submit" disabled={isSolving || !input.trim()} style={{ ...S.primaryBtn, opacity: isSolving || !input.trim() ? 0.7 : 1 }}>
                {isSolving ? "Solving..." : "Solve Equation"}
              </button>
            </form>
            {error && <div style={S.errorBanner}>{error}</div>}
            <div style={{ display: "flex", gap: 12, marginTop: 16, alignItems: "center" }}>
              <span style={{ fontSize: 12, color: "#9ca3af", fontWeight: 600, textTransform: "uppercase" }}>Quick Examples</span>
              <select style={S.selectMenu} onChange={(e) => { if(e.target.value) setInput(e.target.value); }}>
                {Object.entries(SAMPLE_PROMPTS).map(([label, query]) => <option key={label} value={query}>{label}</option>)}
              </select>
            </div>
          </div>

          {finalResult && (
            <div style={S.card}>
              <div style={S.tabs}>
                <button style={{ ...S.tab, ...(activeTab === "steps" ? S.activeTab : {}) }} onClick={() => setActiveTab("steps")}>Solution Steps</button>
                <button style={{ ...S.tab, ...(activeTab === "graph" ? S.activeTab : {}) }} onClick={() => setActiveTab("graph")}>Graphing Canvas</button>
              </div>

              {activeTab === "steps" && (
                <div style={S.resultArea}>
                  {operationInfo && <div style={S.operationTag}>Operation: {operationInfo.replace('_', ' ')}</div>}
                  {steps.length > 0 && (
                    <>
                      <h3 style={S.sectionTitle}>Execution Pathway</h3>
                      <div style={S.stepsContainer}>{steps.map((step, idx) => renderStep(step, idx))}</div>
                    </>
                  )}
                  <h3 style={{ ...S.sectionTitle, marginTop: 24 }}>Final Result</h3>
                  <div style={S.finalResultBlock}>
                    <SafeMath block math={cleanMath(stripMathDelimiters(finalResult))} />
                  </div>
                </div>
              )}

              {activeTab === "graph" && (
                <div style={S.resultArea}>
                  {graphableFunctions.length === 0 ? (
                    <div style={S.emptyState}>No graphable data.</div>
                  ) : (
                    <>
                      <div style={S.graphControls}>
                        <div style={S.controlGroup}>
                          <label style={S.controlLabel}>X Min</label>
                          <input type="number" value={xMin} onChange={e => setXMin(Number(e.target.value))} style={S.controlInput} />
                        </div>
                        <div style={S.controlGroup}>
                          <label style={S.controlLabel}>X Max</label>
                          <input type="number" value={xMax} onChange={e => setXMax(Number(e.target.value))} style={S.controlInput} />
                        </div>
                        <div style={S.controlGroup}>
                          <label style={S.controlLabel}>Sample Points</label>
                          <input type="number" value={samplePoints} onChange={e => setSamplePoints(Number(e.target.value))} style={S.controlInput} />
                        </div>
                      </div>
                      
                      <div style={S.plotContainer}>
                        <Plot
                          data={plotData}
                          layout={{ autosize: true, margin: { l: 40, r: 20, t: 20, b: 40 }, paper_bgcolor: 'transparent', plot_bgcolor: '#fafafd', hovermode: 'x unified', showlegend: true, legend: { orientation: "h", y: -0.2 } }}
                          useResizeHandler={true}
                          style={{ width: '100%', height: '100%' }}
                          config={{ displayModeBar: false }}
                        />
                      </div>

                      <div style={{ marginTop: 32 }}>
                        <h3 style={S.sectionTitle}>Curve Analysis</h3>
                        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(250px, 1fr))", gap: 16 }}>
                          {graphableFunctions.map((func, idx) => {
                            if (!func.analysis) return null;
                            return (
                              <div key={idx} style={{ background: "#f0f9ff", border: "1px solid #bae6fd", borderRadius: 8, padding: 16 }}>
                                <div style={{ fontSize: 13, fontWeight: 700, color: "#0369a1", marginBottom: 12 }}>{func.name} Properties</div>
                                <div style={{ fontSize: 14, color: "#374151", display: "flex", flexDirection: "column", gap: 8 }}>
                                  <div><span style={{ fontWeight: 600 }}>Symmetry:</span> {func.analysis.symmetry}</div>
                                  {func.analysis.y_intercept && <div><span style={{ fontWeight: 600 }}>Y-Intercept:</span> y = {func.analysis.y_intercept}</div>}
                                  {func.analysis.x_intercepts?.length > 0 && <div><span style={{ fontWeight: 600 }}>X-Intercepts:</span> {func.analysis.x_intercepts.join(', ')}</div>}
                                </div>
                              </div>
                            );
                          })}
                        </div>
                      </div>

                      <div style={{ marginTop: 32 }}>
                        <h3 style={S.sectionTitle}>Tracing Table</h3>
                        <input type="range" min="3" max="40" value={tracePoints} onChange={e => setTracePoints(Number(e.target.value))} style={{ width: '100%' }} />
                        <table style={{ width: '100%', marginTop: 12, borderCollapse: 'collapse', fontSize: 13 }}>
                           <thead><tr style={{ background: '#f9fafb' }}><th style={{ padding: 8, border: '1px solid #e6e6ec' }}>x</th>{graphableFunctions.map((f, i) => <th key={i} style={{ padding: 8, border: '1px solid #e6e6ec' }}>{f.name}</th>)}</tr></thead>
                           <tbody>{traceRows.map((row, i) => <tr key={i}>{Object.values(row).map((val, j) => <td key={j} style={{ padding: 8, border: '1px solid #e6e6ec' }}>{typeof val === 'number' ? val.toFixed(2) : val}</td>)}</tr>)}</tbody>
                        </table>
                      </div>
                    </>
                  )}
                </div>
              )}
            </div>
          )}
        </div>
      </main>
    </div>
  );
}

const S = {
  page: { display: "flex", flexDirection: "column", minHeight: "100vh", background: "#f7f7f8", fontFamily: "-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif" },
  header: { height: 56, background: "white", borderBottom: "1px solid #e6e6ec", display: "flex", alignItems: "center", padding: "0 22px", flexShrink: 0 },
  headerLeft: { display: "flex", alignItems: "center", gap: 10 },
  logo: { width: 34, height: 34, borderRadius: 9, background: "linear-gradient(135deg,#0ea5e9,#38bdf8)", color: "white", fontWeight: 800, fontSize: 18, display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 },
  main: { flex: 1, overflowY: "auto", padding: "32px" },
  container: { width: "100%", margin: "0 auto", display: "flex", flexDirection: "column", gap: 24 },
  card: { background: "white", border: "1px solid #e6e6ec", borderRadius: 12, padding: 24, boxShadow: "0 2px 8px rgba(0,0,0,0.02)" },
  label: { fontSize: 11, fontWeight: 700, letterSpacing: 0.6, color: "#6b7280", textTransform: "uppercase", marginBottom: 8, display: "block" },
  inputRow: { display: "flex", gap: 12 },
  input: { flex: 1, padding: "12px 14px", border: "1px solid #d6d6de", borderRadius: 8, fontSize: 15, outline: "none", background: "#fafafd", fontFamily: "inherit", color: "#111827", boxSizing: "border-box" },
  primaryBtn: { padding: "0 24px", border: "none", borderRadius: 8, background: "linear-gradient(135deg,#0ea5e9,#38bdf8)", color: "white", fontSize: 14, fontWeight: 600, cursor: "pointer", fontFamily: "inherit", whiteSpace: "nowrap" },
  selectMenu: { flex: 1, padding: "8px 12px", borderRadius: 8, border: "1px solid #e6e6ec", background: "#fafafd", color: "#4b5563", fontSize: 13, outline: "none", cursor: "pointer" },
  errorBanner: { marginTop: 12, padding: "10px 14px", background: "#fef2f2", color: "#991b1b", border: "1px solid #fecaca", borderRadius: 8, fontSize: 13 },
  tabs: { display: "flex", gap: 16, borderBottom: "1px solid #e6e6ec", marginBottom: 24 },
  tab: { padding: "8px 4px", border: "none", background: "transparent", color: "#9ca3af", fontSize: 14, fontWeight: 600, cursor: "pointer", borderBottom: "2px solid transparent", marginBottom: "-1px" },
  activeTab: { color: "#0284c7", borderBottom: "2px solid #0284c7" },
  resultArea: { display: "flex", flexDirection: "column" },
  operationTag: { alignSelf: "flex-start", padding: "4px 10px", background: "#f0f9ff", color: "#0369a1", borderRadius: 6, fontSize: 12, fontWeight: 600, marginBottom: 20, textTransform: "uppercase" },
  sectionTitle: { fontSize: 14, fontWeight: 700, color: "#374151", marginBottom: 12, borderBottom: "1px solid #f3f4f6", paddingBottom: 8 },
  stepsContainer: { display: "flex", flexDirection: "column", gap: 16 },
  stepBlock: { padding: "16px 20px", background: "#fafafd", border: "1px solid #f3f4f6", borderRadius: 8, color: "#1f2937", fontSize: 15 },
  finalResultBlock: { padding: "24px", background: "#f0f9ff", border: "1px solid #bae6fd", borderRadius: 8, color: "#0c4a6e", fontSize: 18, textAlign: "center", overflowX: "auto" },
  emptyState: { padding: "60px 20px", textAlign: "center", background: "#fafafd", borderRadius: 8, border: "1px dashed #d6d6de" },
  graphControls: { display: "flex", gap: 16, marginBottom: 20, padding: 16, background: "#fafafd", borderRadius: 8, border: "1px solid #f3f4f6" },
  controlGroup: { display: "flex", flexDirection: "column", flex: 1, gap: 4 },
  controlLabel: { fontSize: 11, fontWeight: 600, color: "#6b7280", textTransform: "uppercase" },
  controlInput: { padding: "8px 12px", border: "1px solid #d6d6de", borderRadius: 6, fontSize: 13, outline: "none" },
  plotContainer: { height: 450, border: "1px solid #e6e6ec", borderRadius: 8, overflow: "hidden" }
};