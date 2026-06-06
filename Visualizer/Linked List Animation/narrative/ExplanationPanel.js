
export class ExplanationPanel {

  constructor(containerEl) {
    this._el = containerEl;
  }


  update(step) {
    this._el.innerHTML = this._format(step.explanation ?? '');
  }

  destroy() {
    this._el.innerHTML = '';
  }


  _format(text) {
    let html = this._escape(text);


    html = html.replace(
      /(⚠️[^.!?\n]+[.!?]?)/g,
      '<span class="exp-warning">$1</span>'
    );
    html = html.replace(
      /(❌[^.!?\n]+[.!?]?)/g,
      '<span class="exp-error">$1</span>'
    );
    html = html.replace(
      /(✅[^.!?\n]+[.!?]?)/g,
      '<span class="exp-success">$1</span>'
    );

    html = html.replace(
      /\b([a-zA-Z_][a-zA-Z0-9_]*)\.([a-zA-Z_][a-zA-Z0-9_]*)\b/g,
      '<code class="exp-prop">$1<span class="exp-dot">.</span>$2</code>'
    );

    html = html.replace(/←/g, '<span class="exp-arrow">←</span>');

    html = html.replace(
      /\bvalue\s*:\s*(\d+)/g,
      'value: <span class="exp-value">$1</span>'
    );
    html = html.replace(
      /O\(([^)]+)\)/g,
      'O(<span class="exp-complexity">$1</span>)'
    );

    html = html.replace(
      /`([^`]+)`/g,
      '<code class="exp-inline-code">$1</code>'
    );

    html = html.replace(/\n/g, '<br>');

    return html;
  }

  _escape(str) {
    return str
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }
}