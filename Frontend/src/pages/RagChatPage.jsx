// RAG Chat page — integrated "Chat with Sources" (BayLearn ↔ student).
// This is the RAG module's chat, embedded into the MAIN frontend as a route
// instead of opening the standalone RAG app. It reuses the files the student
// already selected on the Home page (localStorage "baylearn:selected_files")
// and talks to the RAG orchestrator backend's /nlp/ask/{file_ids} endpoint.
import { useState, useRef, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import ReactMarkdown from "react-markdown";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";
import "highlight.js/styles/github.css";
import "katex/dist/katex.min.css";

// RAG orchestrator backend (serves /api/v1/nlp/ask/...). Adjust the port here
// or via VITE_RAG_API_BASE to match how you run the orchestrator (see Makefile).
const RAG_API_BASE =
  import.meta.env.VITE_RAG_API_BASE || "http://127.0.0.1:8000/api/v1";

const EQUATION_UI_BASE =
  import.meta.env.VITE_EQUATION_UI_BASE || "http://localhost:3000";

async function jsonFetch(path, opts = {}) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 120_000);
  let res;
  try {
    res = await fetch(`${RAG_API_BASE}${path}`, {
      headers: { "Content-Type": "application/json", ...(opts.headers || {}) },
      signal: controller.signal,
      ...opts,
    });
  } catch (e) {
    clearTimeout(timer);
    const err = new Error(
      e.name === "AbortError" ? "Request timed out." : "Cannot reach the RAG server."
    );
    err.status = 0;
    throw err;
  }
  clearTimeout(timer);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const err = new Error(data.detail || data.error || `HTTP ${res.status}`);
    err.status = res.status;
    throw err;
  }
  return data;
}

// // Very small Markdown-ish renderer (bold + line breaks) so we don't add a dep.
// function renderText(text) {
//   const html = (text || "")
//     .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
//     .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
//     .replace(/\[Source\s+([\d,\s]+)\]/gi, '<sup style="color:#6c63ff">[$1]</sup>')
//     .replace(/\n/g, "<br/>");
//   return { __html: html };
// }

export default function RagChatPage() {
  const navigate = useNavigate();

  // Files the student picked on the Home page before launching this module.
  const fileIds = (() => {
    try { return JSON.parse(localStorage.getItem("baylearn:selected_files") || "[]"); }
    catch { return []; }
  })();

  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const endRef = useRef(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  async function send(textOverride) {
    const q = (textOverride ?? input).trim();
    if (!q || loading) return;
    if (fileIds.length === 0) {
      setMessages((m) => [...m, {
        role: "assistant", error: true,
        content: "No sources selected. Go back to Home, pick files, then open Chat.",
      }]);
      return;
    }
    setInput("");
    setMessages((m) => [...m, { role: "user", content: q }]);
    setLoading(true);
    try {
      const data = await jsonFetch(`/nlp/ask/${fileIds.join(",")}`, {
        method: "POST",
        body: JSON.stringify({ text: q, limit: 5 }),
      });
      const d = data.data || data || {};
      setMessages((m) => [...m, {
        role: "assistant",
        content: d.answer || "(empty response)",
        sources: d.sources || [],
        intent: d.intent || null,
        equationText: d.equation_text_sent || d.query || q,
        equationResult: d.equation_result || null,
      }]);
    } catch (err) {
      setMessages((m) => [...m, {
        role: "assistant", error: true,
        content: err.status === 429
          ? "Rate limit reached — please retry in a minute."
          : (err.message || "Cannot reach server."),
      }]);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={S.page}>
      {/* Header */}
      <header style={S.header}>
        <button style={S.back} onClick={() => navigate("/home")}>← Home</button>
        <div>
          <h1 style={S.title}>💬 Chat with Sources</h1>
          <p style={S.sub}>
            {fileIds.length > 0
              ? `Answering from ${fileIds.length} selected file(s)`
              : "No files selected — pick sources on the Home page first"}
          </p>
        </div>
      </header>

      {/* Messages */}
      <main style={S.messages}>
        {messages.length === 0 && (
          <div style={S.empty}>
            Ask a question about your selected study materials. Every answer is
            grounded in your sources and cites them.
          </div>
        )}
        {messages.map((m, i) => (
          <div key={i} style={{ ...S.row, justifyContent: m.role === "user" ? "flex-end" : "flex-start" }}>
            <div style={{
              ...S.bubble,
              ...(m.role === "user" ? S.userBubble : S.botBubble),
              ...(m.error ? S.errBubble : {}),
            }}>
              {m.role === "assistant" && m.intent && (
                <span style={S.badge}>{m.intent === "equation_from_context" ? "Equation mode" : "Answering from sources"}</span>
              )}
              <ReactMarkdown
                remarkPlugins={[remarkMath]}
                rehypePlugins={[rehypeKatex]}
              >
                {m.content}
              </ReactMarkdown>
              {m.intent === "equation_from_context" && m.equationText && (
                <button
                  style={S.eqBtn}
                  onClick={() =>
                    window.open(
                      `${EQUATION_UI_BASE}/?q=${encodeURIComponent(m.equationText)}`,
                      "_blank",
                      "noopener"
                    )
                  }
                >
                  Open in Equation Lab ↗
                </button>
              )}
              {m.sources && m.sources.length > 0 && (
                <details style={S.sources}>
                  <summary style={S.sourcesSum}>{m.sources.length} source(s)</summary>
                  {m.sources.map((s, j) => (
                    <div key={j} style={S.sourceItem}>{String(s).slice(0, 300)}…</div>
                  ))}
                </details>
              )}
            </div>
          </div>
        ))}
        {loading && <div style={{ ...S.row, justifyContent: "flex-start" }}>
          <div style={{ ...S.bubble, ...S.botBubble }}>Thinking…</div>
        </div>}
        <div ref={endRef} />
      </main>

      {/* Input */}
      <footer style={S.footer}>
        <input
          style={S.input}
          value={input}
          placeholder="Ask about your materials…"
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && send()}
          disabled={loading}
        />
        <button style={S.sendBtn} onClick={() => send()} disabled={loading || !input.trim()}>
          Send
        </button>
      </footer>
    </div>
  );
}

const S = {
  page: { display: "flex", flexDirection: "column", height: "100vh", background: "#f5f5fb", fontFamily: "system-ui, Arial, sans-serif" },
  header: { display: "flex", alignItems: "center", gap: 16, padding: "14px 20px", background: "#fff", borderBottom: "1px solid #e5e7eb" },
  back: { border: "none", background: "#eef", color: "#6c63ff", padding: "8px 12px", borderRadius: 8, cursor: "pointer", fontWeight: 600 },
  title: { margin: 0, fontSize: 20 },
  sub: { margin: 0, fontSize: 13, color: "#666" },
  messages: { flex: 1, overflowY: "auto", padding: 20, display: "flex", flexDirection: "column", gap: 12 },
  empty: { color: "#888", textAlign: "center", marginTop: 40, fontSize: 15 },
  row: { display: "flex" },
  bubble: { maxWidth: "70%", padding: "12px 16px", borderRadius: 14, lineHeight: 1.5, fontSize: 15, boxShadow: "0 1px 3px rgba(0,0,0,.08)" },
  userBubble: { background: "#6c63ff", color: "#fff", borderBottomRightRadius: 4 },
  botBubble: { background: "#fff", color: "#1f2937", borderBottomLeftRadius: 4 },
  errBubble: { background: "#fee2e2", color: "#991b1b" },
  badge: { display: "inline-block", fontSize: 11, fontWeight: 700, color: "#6c63ff", background: "#eef", padding: "2px 8px", borderRadius: 999, marginBottom: 6 },
  eqBtn: { display: "inline-block", marginTop: 10, padding: "8px 14px", borderRadius: 8, border: "none", background: "linear-gradient(135deg,#0ea5e9,#38bdf8)", color: "#fff", fontWeight: 600, fontSize: 13, cursor: "pointer" },
  sources: { marginTop: 8, fontSize: 13 },
  sourcesSum: { cursor: "pointer", color: "#6c63ff", fontWeight: 600 },
  sourceItem: { marginTop: 6, padding: 8, background: "#f3f4f6", borderRadius: 8, color: "#374151", fontSize: 12 },
  footer: { display: "flex", gap: 10, padding: 16, background: "#fff", borderTop: "1px solid #e5e7eb" },
  input: { flex: 1, padding: "12px 14px", borderRadius: 10, border: "1px solid #d1d5db", fontSize: 15, outline: "none" },
  sendBtn: { padding: "12px 22px", borderRadius: 10, border: "none", background: "#6c63ff", color: "#fff", fontWeight: 700, cursor: "pointer" },
};
