export type GraphableFunction = {
  name?: string;
  expr?: string;
  expression?: string;
  var?: string;
  type?: string;
};

export function getExpression(entry: GraphableFunction) {
  return entry.expression ?? entry.expr ?? "";
}

export function sympyToJavaScript(expr: string) {
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

export function evaluateExpression(expr: string, x: number) {
  try {
    const jsExpr = sympyToJavaScript(expr);
    const evaluator = new Function("x", `return ${jsExpr};`) as (value: number) => number;
    const result = evaluator(x);
    return typeof result === "number" ? result : Number(result);
  } catch {
    return Number.NaN;
  }
}

export function buildPoints(expr: string, xMin: number, xMax: number, samples: number) {
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

export function buildTraceRows(functions: GraphableFunction[], xMin: number, xMax: number, samples: number) {
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
