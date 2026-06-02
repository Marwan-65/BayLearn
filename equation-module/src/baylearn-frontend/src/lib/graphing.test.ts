import { describe, expect, it } from "vitest";
import { buildPoints, buildTraceRows, evaluateExpression, getExpression, sympyToJavaScript } from "./graphing";

describe("graphing helpers", () => {
  it("converts common sympy expressions to JavaScript", () => {
    expect(sympyToJavaScript("sin(x) + cos(x) + exp(x) + pi + E")).toBe(
      "Math.sin(x)+Math.cos(x)+Math.exp(x)+Math.PI+Math.E",
    );
  });

  it("supports powers and evaluation", () => {
    expect(sympyToJavaScript("x**2 + 3")).toBe("Math.pow(x,2)+3");
    expect(evaluateExpression("x**2 + 3", 4)).toBe(19);
  });

  it("builds finite points for valid expressions", () => {
    expect(buildPoints("x**2", -1, 1, 3)).toEqual([
      { x: -1, y: 1 },
      { x: 0, y: 0 },
      { x: 1, y: 1 },
    ]);
  });

  it("filters out invalid points when expressions cannot be evaluated", () => {
    expect(buildPoints("1/(x-1)", 0, 2, 3)).toEqual([
      { x: 0, y: -1 },
      { x: 2, y: 1 },
    ]);
  });

  it("normalizes graphable function expressions and trace rows", () => {
    expect(getExpression({ expression: "x+1" })).toBe("x+1");
    expect(getExpression({ expr: "x+2" })).toBe("x+2");
    expect(getExpression({})).toBe("");

    expect(buildTraceRows([{ name: "f", expr: "x+1" }, { name: "g", expression: "x**2" }], 0, 2, 3)).toEqual([
      { x: "0.0000", values: ["1.000000", "0.000000"] },
      { x: "1.0000", values: ["2.000000", "1.000000"] },
      { x: "2.0000", values: ["3.000000", "4.000000"] },
    ]);
  });
});
