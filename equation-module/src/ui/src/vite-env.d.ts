/// <reference types="vite/client" />

type PlotlyModule = {
  newPlot: (el: HTMLElement, data: unknown[], layout: Record<string, unknown>, config?: Record<string, unknown>) => Promise<unknown> | void;
  purge: (el: HTMLElement) => void;
};

interface Window {
  Plotly?: PlotlyModule;
  MathJax?: {
    typesetPromise: (elements?: Element[]) => Promise<void>;
  };
}
