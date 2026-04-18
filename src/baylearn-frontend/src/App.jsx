/**
 * BayLearn — simple NotebookLM-style pipeline UI.
 *
 * Left panel  : Sources (upload + file list) + Module shortcuts
 *               (Equation Lab, Animation Lab → open teammate frontends
 *                in new tabs).
 * Right panel : Chat that hits /nlp/ask/{project_id}.
 *               The backend returns the detected intent — the UI
 *               renders:
 *                 - plain answer + sources for rag_only
 *                 - extracted equation + solver output for
 *                   equation_from_context
 *                 - animation spec for animation_from_context
 *
 * Everything is one file on purpose — the design will be redone later.
 */
import { useEffect, useRef, useState } from "react";

const API_BASE =
  import.meta.env.VITE_API_BASE || "http://127.0.0.1:8000/api/v1";
const EQUATION_URL =
  import.meta.env.VITE_EQUATION_FRONTEND_URL || "http://localhost:8501";
const ANIMATION_URL =
  import.meta.env.VITE_ANIMATION_FRONTEND_URL || "http://localhost:3001";

/* ────────────────────────────────────────────────────────────── */

async function jsonFetch(path, opts = {}) {
  // 90 s client-side timeout so a hung Groq call never leaves the UI
  // spinning forever — the user sees a clear error and can retry.
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 90_000);
  let res;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      headers: { "Content-Type": "application/json", ...(opts.headers || {}) },
      signal: controller.signal,
      ...opts,
    });
  } catch (e) {
    clearTimeout(timer);
    if (e.name === "AbortError") {
      const err = new Error(
        "Request timed out after 90 s. The LLM may be rate-limited or slow — try again."
      );
      err.status = 0;
      throw err;
    }
    throw e;
  }
  clearTimeout(timer);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const err = new Error(data.signal || data.detail || `HTTP ${res.status}`);
    err.status = res.status;
    throw err;
  }
  return data;
}

/** Generate/retrieve a stable per-browser project ID. The user never sees
 *  or types this — it's just the bucket key the backend uses to isolate
 *  one person's uploaded materials from another's. */
function getOrCreateProjectId() {
  let pid = localStorage.getItem("baylearn:pid");
  if (!pid) {
    pid = "p_" + Math.random().toString(36).slice(2, 10) + Date.now().toString(36).slice(-4);
    localStorage.setItem("baylearn:pid", pid);
  }
  return pid;
}

export default function App() {
  const [projectId] = useState(getOrCreateProjectId);
  const [files, setFiles] = useState(() => {
    try {
      return JSON.parse(localStorage.getItem("baylearn:files") || "[]");
    } catch {
      return [];
    }
  });
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [toast, setToast] = useState(null);
  const [serverOk, setServerOk] = useState(null);
  const bottomRef = useRef(null);
  const fileInputRef = useRef(null);

  useEffect(() => {
    localStorage.setItem("baylearn:files", JSON.stringify(files));
  }, [files]);
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  // Ping backend
  useEffect(() => {
    let cancelled = false;
    async function check() {
      try {
        await jsonFetch("/");
        if (!cancelled) setServerOk(true);
      } catch {
        if (!cancelled) setServerOk(false);
      }
    }
    check();
    const id = setInterval(check, 20000);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, []);

  function showToast(msg, type = "info") {
    setToast({ msg, type });
    setTimeout(() => setToast(null), 3500);
  }

  /* ── Upload (input parsing → chunk → embed → index) ───────── */
  async function handleUpload(fileList) {
    const list = Array.from(fileList || []);
    if (!list.length) return;
    setUploading(true);
    try {
      for (const file of list) {
        const form = new FormData();
        form.append("file", file);
        const res = await fetch(
          `${API_BASE}/parse/upload/${projectId}?auto_index=true`,
          { method: "POST", body: form }
        );
        const data = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(data.signal || `HTTP ${res.status}`);
        setFiles((prev) => [
          ...prev.filter((f) => f.filename !== file.name),
          {
            filename: file.name,
            size: file.size,
            chunks: data.inserted_items_count || data.chunks || 0,
            indexed: true,
          },
        ]);
      }
      showToast(`Uploaded ${list.length} file(s) ✓`, "success");
    } catch (err) {
      showToast(err.message || "Upload failed", "error");
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  }

  /* ── Ask (intent-aware) ───────────────────────────────────── */
  async function send(textOverride) {
    const q = (textOverride ?? input).trim();
    if (!q || loading) return;
    setInput("");
    setMessages((m) => [...m, { role: "user", content: q }]);
    setLoading(true);
    try {
      const data = await jsonFetch(`/nlp/ask/${projectId}`, {
        method: "POST",
        body: JSON.stringify({ text: q, limit: 5 }),
      });
      const d = data.data || {};
      setMessages((m) => [
        ...m,
        {
          role: "assistant",
          content: d.answer || "(empty response)",
          sources: d.sources || [],
          scores: d.scores || [],
          intent: d.intent || null,
          equation: d.equation_text_sent || d.equation || null,
          equationResult: d.equation_result || null,
          animation: d.animation_spec || d.animation || null,
          raw: d,
        },
      ]);
      // Equation intent: do NOT auto-open the lab. The chat bubble shows
      // the steps + "Open Equation Lab ↗" button, and the student clicks
      // through only when they want the interactive workspace. Auto-open
      // was disorienting — every question yanked focus to a new tab.
      // Auto-open the animation lab when we produced an animation spec.
      if (d.animation_spec || d.animation) {
        try {
          window.open(ANIMATION_URL, "_blank", "noopener");
        } catch {
          /* noop */
        }
      }
    } catch (err) {
      setMessages((m) => [
        ...m,
        {
          role: "assistant",
          error: true,
          content:
            err.status === 429
              ? "Rate limit reached — try again in a minute."
              : err.message || "Cannot reach the server.",
        },
      ]);
    } finally {
      setLoading(false);
    }
  }

  function removeFile(filename) {
    setFiles((prev) => prev.filter((f) => f.filename !== filename));
  }

  const suggestions = [
    "Summarize the key concepts from my materials",
    "Solve the equation from page 3",
    "Animate a linked list insertion",
    "What are the most important points to review?",
  ];

  /* ────────────────────── UI ────────────────────── */
  return (
    <div style={S.app}>
      {/* ═════ LEFT — Sources + Modules ═════ */}
      <aside style={S.sidebar}>
        <div style={S.brand}>
          <div style={S.logo}>B</div>
          <div>
            <div style={{ fontWeight: 700, fontSize: 15 }}>BayLearn</div>
            <div style={{ fontSize: 11, color: "#888" }}>Adaptive study hub</div>
          </div>
        </div>

        {/* Upload */}
        <label style={S.label}>SOURCES</label>
        <div
          onClick={() => fileInputRef.current?.click()}
          onDragOver={(e) => {
            e.preventDefault();
            e.currentTarget.style.borderColor = "#6c63ff";
          }}
          onDragLeave={(e) => (e.currentTarget.style.borderColor = "#d6d6de")}
          onDrop={(e) => {
            e.preventDefault();
            e.currentTarget.style.borderColor = "#d6d6de";
            handleUpload(e.dataTransfer.files);
          }}
          style={S.dropzone}
        >
          <div style={{ fontSize: 22 }}>{uploading ? "⏳" : "📄"}</div>
          <div style={{ fontSize: 13, fontWeight: 600, marginTop: 4 }}>
            {uploading ? "Uploading…" : "Add sources"}
          </div>
          <div style={{ fontSize: 11, color: "#888", marginTop: 2 }}>
            PDF · image · audio · video · txt
          </div>
          <input
            ref={fileInputRef}
            type="file"
            multiple
            hidden
            accept=".pdf,.txt,.md,.png,.jpg,.jpeg,.mp3,.wav,.m4a,.mp4,.mov,.webm"
            onChange={(e) => handleUpload(e.target.files)}
          />
        </div>

        {/* File list */}
        <div style={S.fileList}>
          {files.length === 0 ? (
            <div style={{ fontSize: 12, color: "#999", padding: "8px 4px" }}>
              No sources yet.
            </div>
          ) : (
            files.map((f) => (
              <div key={f.filename} style={S.fileRow}>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={S.fileName}>{f.filename}</div>
                  <div style={S.fileMeta}>
                    {(f.size / 1024).toFixed(0)} KB · {f.chunks} chunks{" "}
                    {f.indexed ? "· ✓" : ""}
                  </div>
                </div>
                <button
                  style={S.xBtn}
                  onClick={() => removeFile(f.filename)}
                  title="Remove from list"
                >
                  ×
                </button>
              </div>
            ))
          )}
        </div>

        {/* Module shortcuts */}
        <label style={{ ...S.label, marginTop: 18 }}>MODULES</label>
        <button
          onClick={() => window.open(EQUATION_URL, "_blank")}
          style={S.modCard}
        >
          <span style={{ fontSize: 18 }}>🧮</span>
          <div style={{ flex: 1, textAlign: "left" }}>
            <div style={{ fontSize: 13, fontWeight: 600 }}>Equation Lab</div>
            <div style={{ fontSize: 11, color: "#888" }}>
              Symbolic + numeric solver
            </div>
          </div>
          <span style={{ fontSize: 12, color: "#888" }}>↗</span>
        </button>
        <button
          onClick={() => window.open(ANIMATION_URL, "_blank")}
          style={S.modCard}
        >
          <span style={{ fontSize: 18 }}>🎬</span>
          <div style={{ flex: 1, textAlign: "left" }}>
            <div style={{ fontSize: 13, fontWeight: 600 }}>Animation Lab</div>
            <div style={{ fontSize: 11, color: "#888" }}>
              Algorithm visualizer
            </div>
          </div>
          <span style={{ fontSize: 12, color: "#888" }}>↗</span>
        </button>

        <div style={{ fontSize: 11, color: "#999", marginTop: 10, lineHeight: 1.6 }}>
          Or just ask in chat — BayLearn detects whether you want an
          explanation, a solved equation, or an animation, and routes to
          the right module automatically.
        </div>

        <div style={{ flex: 1 }} />

        <div style={S.status}>
          <span
            style={{
              ...S.dot,
              background: serverOk ? "#4ade80" : "#f87171",
            }}
          />
          Server{" "}
          {serverOk === null ? "checking…" : serverOk ? "online" : "offline"}
        </div>
      </aside>

      {/* ═════ RIGHT — Chat ═════ */}
      <main style={S.main}>
        <header style={S.header}>
          <div style={{ fontSize: 15, fontWeight: 700 }}>Study Assistant</div>
          <div style={{ fontSize: 12, color: "#888" }}>
            {files.length} source{files.length === 1 ? "" : "s"} indexed
          </div>
        </header>

        <div style={S.messages}>
          {messages.length === 0 ? (
            <div style={S.empty}>
              <div style={{ fontSize: 36 }}>🎓</div>
              <div style={{ fontSize: 18, fontWeight: 700, marginTop: 8 }}>
                Three things you can do
              </div>
              <div style={{ fontSize: 13, color: "#777", marginTop: 6, maxWidth: 460, lineHeight: 1.7, textAlign: "left" }}>
                <div>① Drop study materials into <b>Sources</b> on the left.</div>
                <div>② Ask a question below — BayLearn answers from your materials, or routes to the equation/animation module if that's what you asked for.</div>
                <div>③ Or open <b>Equation Lab</b> / <b>Animation Lab</b> directly from the sidebar.</div>
              </div>
              <div style={{ fontSize: 12, color: "#999", marginTop: 14 }}>
                Try one of these:
              </div>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 8, justifyContent: "center", marginTop: 16 }}>
                {suggestions.map((s, i) => (
                  <button key={i} style={S.chip} onClick={() => send(s)}>
                    {s}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            messages.map((m, i) => <Bubble key={i} m={m} />)
          )}
          {loading && (
            <div style={{ ...S.msg, alignSelf: "flex-start" }}>
              <div style={S.avatarAI}>🤖</div>
              <div style={S.bubbleAI}>
                <span style={S.dotAnim} />
                <span style={{ ...S.dotAnim, animationDelay: "0.2s" }} />
                <span style={{ ...S.dotAnim, animationDelay: "0.4s" }} />
              </div>
            </div>
          )}
          <div ref={bottomRef} />
        </div>

        <div style={S.inputWrap}>
          <div style={S.inputBox}>
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  send();
                }
              }}
              placeholder="Ask a question, or try 'solve 2x+3=7' or 'animate a stack push'…"
              rows={1}
              style={S.textarea}
            />
            <button
              onClick={() => send()}
              disabled={loading || !input.trim()}
              style={{
                ...S.sendBtn,
                opacity: loading || !input.trim() ? 0.4 : 1,
              }}
            >
              ➤
            </button>
          </div>
          <div style={{ fontSize: 11, color: "#999", marginTop: 6, textAlign: "center" }}>
            Enter to send · Shift+Enter for newline
          </div>
        </div>
      </main>

      {toast && (
        <div
          style={{
            ...S.toast,
            borderColor:
              toast.type === "error"
                ? "#f87171"
                : toast.type === "success"
                ? "#4ade80"
                : "#d6d6de",
            color:
              toast.type === "error"
                ? "#c53030"
                : toast.type === "success"
                ? "#166534"
                : "#1a1a1a",
          }}
        >
          {toast.msg}
        </div>
      )}

      <style>{`
        @keyframes bl-bounce {
          0%, 60%, 100% { transform: translateY(0); opacity: 0.4; }
          30% { transform: translateY(-6px); opacity: 1; }
        }
        @keyframes bl-slide {
          from { opacity: 0; transform: translateY(6px); }
          to { opacity: 1; transform: translateY(0); }
        }
      `}</style>
    </div>
  );
}

/* ────────────── Message bubble with intent rendering ────────────── */
function Bubble({ m }) {
  if (m.role === "user") {
    return (
      <div style={{ ...S.msg, alignSelf: "flex-end", flexDirection: "row-reverse" }}>
        <div style={S.avatarUser}>M</div>
        <div style={S.bubbleUser}>{m.content}</div>
      </div>
    );
  }
  return (
    <div style={{ ...S.msg, alignSelf: "flex-start" }}>
      <div style={S.avatarAI}>🤖</div>
      <div style={{ maxWidth: 680 }}>
        {m.intent && <IntentBadge intent={m.intent} />}
        <div
          style={{
            ...S.bubbleAI,
            ...(m.error ? { borderColor: "#f87171", color: "#c53030" } : {}),
          }}
        >
          {m.content}
        </div>

        {/* Equation module result — rendered nicely, not as raw JSON */}
        {m.equation && (
          <div style={S.card}>
            <div style={S.cardLabel}>🧮 Equation</div>
            <code style={S.code}>{m.equation}</code>
            {m.equationResult ? (
              <EquationSolution result={m.equationResult} equation={m.equation} />
            ) : (
              // Even if the equation module didn't return a result (not
              // running, error, or LLM answered conversationally), still
              // give the user a one-click path into the lab pre-filled
              // with their equation.
              <a
                href={`${EQUATION_URL}/?q=${encodeURIComponent(m.equation)}&autosolve=1`}
                target="_blank"
                rel="noopener noreferrer"
                style={S.launchBtn}
              >
                Open Equation Lab ↗
              </a>
            )}
          </div>
        )}

        {/* Animation module result */}
        {m.animation && (
          <div style={S.card}>
            <div style={S.cardLabel}>🎬 Animation spec</div>
            <div style={S.specGrid}>
              {Object.entries(m.animation).map(([k, v]) => (
                <div key={k} style={S.specRow}>
                  <span style={S.specKey}>{k}</span>
                  <span style={S.specVal}>
                    {Array.isArray(v) ? v.join(", ") : String(v)}
                  </span>
                </div>
              ))}
            </div>
            <a
              href={ANIMATION_URL}
              target="_blank"
              rel="noopener noreferrer"
              style={S.launchBtn}
            >
              Open Animation Lab ↗
            </a>
          </div>
        )}

        {/* Sources */}
        {m.sources && m.sources.length > 0 && (
          <div style={{ marginTop: 8 }}>
            <div style={S.srcLabel}>Sources retrieved</div>
            {m.sources.map((src, j) => {
              // Scores may be cosine similarity (0–1) OR RRF scores
              // (unbounded). Clamp to [0, 1] so the pill never shows 500%.
              const raw = m.scores?.[j] ?? 0;
              const score = Math.max(0, Math.min(1, raw));
              const color =
                score >= 0.6 ? "#16a34a" : score >= 0.4 ? "#ca8a04" : "#dc2626";
              return (
                <div key={j} style={S.src}>
                  <span
                    style={{
                      ...S.scorePill,
                      color,
                      background: color + "1A",
                    }}
                  >
                    {(score * 100).toFixed(0)}%
                  </span>
                  <span style={{ flex: 1, fontSize: 12, color: "#444" }}>
                    {String(src).length > 240
                      ? String(src).slice(0, 240) + "…"
                      : String(src)}
                  </span>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}

/** Strip the $…$ and a few LaTeX commands so steps read as plain math
 *  in the chat. We don't need full LaTeX rendering for the demo — just
 *  something readable instead of a JSON dump. */
function cleanLatex(s) {
  if (!s) return "";
  return String(s)
    .replace(/\\cdot/g, "·")
    .replace(/\\frac\{([^{}]+)\}\{([^{}]+)\}/g, "($1)/($2)")
    .replace(/\\left|\\right/g, "")
    .replace(/\\,/g, " ")
    .replace(/\$/g, "")
    .replace(/\s+\n/g, "\n");
}

function EquationSolution({ result, equation }) {
  if (!result || typeof result !== "object") return null;
  if (result.success === false) {
    return (
      <div style={{ marginTop: 10, color: "#c53030", fontSize: 13 }}>
        Solver error: {result.error || "unknown"}
      </div>
    );
  }
  const steps = Array.isArray(result.steps) ? result.steps : [];
  const final = result.final_result;
  const lab = `${
    import.meta.env.VITE_EQUATION_FRONTEND_URL || "http://localhost:8501"
  }/?q=${encodeURIComponent(equation || "")}&autosolve=1`;

  return (
    <>
      {final && (
        <>
          <div style={{ ...S.cardLabel, marginTop: 10 }}>Answer</div>
          <div
            style={{
              fontSize: 15,
              fontWeight: 600,
              color: "#111827",
              padding: "8px 10px",
              background: "#ecfdf5",
              border: "1px solid #a7f3d0",
              borderRadius: 6,
              fontFamily:
                "ui-monospace, SFMono-Regular, Menlo, Monaco, monospace",
            }}
          >
            {cleanLatex(final)}
          </div>
        </>
      )}
      {steps.length > 0 && (
        <>
          <div style={{ ...S.cardLabel, marginTop: 10 }}>Steps</div>
          <ol style={{ paddingLeft: 18, margin: 0, fontSize: 13, lineHeight: 1.55 }}>
            {steps.map((s, i) => (
              <li key={i} style={{ marginBottom: 6, whiteSpace: "pre-wrap" }}>
                {cleanLatex(s)}
              </li>
            ))}
          </ol>
        </>
      )}
      <a
        href={lab}
        target="_blank"
        rel="noopener noreferrer"
        style={S.launchBtn}
      >
        Open Equation Lab ↗
      </a>
    </>
  );
}

function IntentBadge({ intent }) {
  const map = {
    rag_only: { label: "Answering from sources", color: "#6c63ff" },
    equation_from_context: { label: "Equation mode", color: "#f59e0b" },
    animation_from_context: { label: "Animation mode", color: "#10b981" },
  };
  const m = map[intent] || { label: intent, color: "#6b7280" };
  return (
    <div
      style={{
        display: "inline-block",
        fontSize: 10,
        fontWeight: 700,
        letterSpacing: 1,
        textTransform: "uppercase",
        color: m.color,
        background: m.color + "1A",
        border: `1px solid ${m.color}40`,
        padding: "2px 8px",
        borderRadius: 10,
        marginBottom: 6,
      }}
    >
      ✦ {m.label}
    </div>
  );
}

/* ───────────────────── styles ───────────────────── */
const S = {
  app: { display: "flex", height: "100vh", width: "100vw", overflow: "hidden" },
  sidebar: {
    width: 300,
    flexShrink: 0,
    background: "#ffffff",
    borderRight: "1px solid #e6e6ec",
    padding: "18px 16px",
    display: "flex",
    flexDirection: "column",
    overflowY: "auto",
  },
  brand: { display: "flex", alignItems: "center", gap: 10, marginBottom: 18 },
  logo: {
    width: 34,
    height: 34,
    borderRadius: 9,
    background: "linear-gradient(135deg,#6c63ff,#a78bfa)",
    color: "white",
    fontWeight: 800,
    fontSize: 16,
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
  },
  label: {
    fontSize: 10,
    fontWeight: 700,
    letterSpacing: 1.2,
    color: "#888",
    marginTop: 14,
    marginBottom: 6,
    display: "block",
  },
  dropzone: {
    border: "2px dashed #d6d6de",
    borderRadius: 10,
    padding: "16px 10px",
    textAlign: "center",
    cursor: "pointer",
    background: "#fafafd",
    transition: "border-color 0.2s",
  },
  fileList: { marginTop: 8, display: "flex", flexDirection: "column", gap: 4 },
  fileRow: {
    display: "flex",
    alignItems: "center",
    gap: 6,
    padding: "6px 8px",
    background: "#fafafd",
    border: "1px solid #eee",
    borderRadius: 6,
  },
  fileName: {
    fontSize: 12,
    fontWeight: 600,
    overflow: "hidden",
    textOverflow: "ellipsis",
    whiteSpace: "nowrap",
  },
  fileMeta: { fontSize: 10, color: "#888" },
  xBtn: {
    border: "none",
    background: "transparent",
    color: "#888",
    cursor: "pointer",
    fontSize: 16,
    padding: "0 4px",
  },
  modCard: {
    display: "flex",
    alignItems: "center",
    gap: 10,
    padding: "10px 12px",
    background: "#fafafd",
    border: "1px solid #e6e6ec",
    borderRadius: 8,
    cursor: "pointer",
    marginBottom: 6,
    width: "100%",
  },
  status: {
    marginTop: 12,
    padding: "8px 12px",
    background: "#fafafd",
    border: "1px solid #e6e6ec",
    borderRadius: 8,
    fontSize: 12,
    color: "#555",
    display: "flex",
    alignItems: "center",
    gap: 8,
  },
  dot: { width: 8, height: 8, borderRadius: "50%" },

  main: { flex: 1, display: "flex", flexDirection: "column", background: "#f7f7f8" },
  header: {
    height: 52,
    padding: "0 22px",
    borderBottom: "1px solid #e6e6ec",
    background: "white",
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
  },
  messages: {
    flex: 1,
    overflowY: "auto",
    padding: 24,
    display: "flex",
    flexDirection: "column",
    gap: 16,
  },
  empty: {
    margin: "auto",
    textAlign: "center",
    padding: 40,
    color: "#777",
  },
  chip: {
    padding: "7px 14px",
    border: "1px solid #d6d6de",
    borderRadius: 20,
    background: "white",
    fontSize: 12,
    cursor: "pointer",
    color: "#555",
  },
  msg: {
    display: "flex",
    gap: 10,
    maxWidth: 780,
    animation: "bl-slide 0.25s ease",
  },
  avatarUser: {
    width: 30,
    height: 30,
    borderRadius: 8,
    background: "#6c63ff",
    color: "white",
    fontWeight: 700,
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    fontSize: 13,
    flexShrink: 0,
  },
  avatarAI: {
    width: 30,
    height: 30,
    borderRadius: 8,
    background: "#ede9fe",
    border: "1px solid #d8d4f0",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    fontSize: 14,
    flexShrink: 0,
  },
  bubbleUser: {
    padding: "10px 14px",
    background: "#6c63ff",
    color: "white",
    borderRadius: "14px 4px 14px 14px",
    fontSize: 14,
    lineHeight: 1.6,
  },
  bubbleAI: {
    padding: "10px 14px",
    background: "white",
    border: "1px solid #e6e6ec",
    borderRadius: "4px 14px 14px 14px",
    fontSize: 14,
    lineHeight: 1.6,
    color: "#1a1a1a",
    whiteSpace: "pre-wrap",
  },
  dotAnim: {
    display: "inline-block",
    width: 7,
    height: 7,
    borderRadius: "50%",
    background: "#a78bfa",
    margin: "0 3px",
    animation: "bl-bounce 1.2s ease-in-out infinite",
  },

  card: {
    marginTop: 8,
    padding: 12,
    background: "white",
    border: "1px solid #e6e6ec",
    borderRadius: 10,
  },
  cardLabel: {
    fontSize: 10,
    fontWeight: 700,
    letterSpacing: 1,
    color: "#888",
    marginBottom: 6,
  },
  code: {
    display: "block",
    fontFamily: "ui-monospace,Menlo,monospace",
    fontSize: 13,
    background: "#f4f4f8",
    padding: "8px 10px",
    borderRadius: 6,
  },
  pre: {
    fontFamily: "ui-monospace,Menlo,monospace",
    fontSize: 11,
    background: "#f4f4f8",
    padding: "8px 10px",
    borderRadius: 6,
    overflowX: "auto",
    whiteSpace: "pre-wrap",
  },
  launchBtn: {
    display: "inline-block",
    marginTop: 10,
    padding: "6px 12px",
    background: "#111827",
    color: "white",
    fontSize: 12,
    fontWeight: 600,
    borderRadius: 6,
    textDecoration: "none",
  },
  specGrid: {
    display: "grid",
    gap: 4,
    marginTop: 2,
  },
  specRow: {
    display: "flex",
    gap: 10,
    fontSize: 13,
    padding: "4px 8px",
    background: "#f9fafb",
    borderRadius: 4,
  },
  specKey: {
    minWidth: 120,
    fontWeight: 600,
    color: "#6b7280",
    fontFamily: "ui-monospace,Menlo,monospace",
    fontSize: 12,
  },
  specVal: {
    flex: 1,
    color: "#111827",
    fontFamily: "ui-monospace,Menlo,monospace",
    fontSize: 12,
  },
  srcLabel: {
    fontSize: 10,
    fontWeight: 700,
    letterSpacing: 1,
    color: "#888",
    margin: "10px 0 4px",
  },
  src: {
    display: "flex",
    gap: 8,
    padding: "6px 10px",
    background: "#fafafd",
    border: "1px solid #eee",
    borderRadius: 6,
    marginBottom: 4,
    alignItems: "flex-start",
  },
  scorePill: {
    fontFamily: "ui-monospace,Menlo,monospace",
    fontSize: 10,
    padding: "1px 6px",
    borderRadius: 8,
    fontWeight: 700,
    flexShrink: 0,
  },

  inputWrap: {
    padding: "14px 22px 18px",
    borderTop: "1px solid #e6e6ec",
    background: "white",
  },
  inputBox: {
    display: "flex",
    alignItems: "flex-end",
    gap: 10,
    border: "1px solid #d6d6de",
    borderRadius: 14,
    padding: "10px 12px",
    background: "#fafafd",
  },
  textarea: {
    flex: 1,
    border: "none",
    outline: "none",
    resize: "none",
    background: "transparent",
    fontFamily: "inherit",
    fontSize: 14,
    lineHeight: 1.5,
    minHeight: 22,
    maxHeight: 120,
  },
  sendBtn: {
    width: 34,
    height: 34,
    borderRadius: 8,
    border: "none",
    background: "linear-gradient(135deg,#6c63ff,#a78bfa)",
    color: "white",
    cursor: "pointer",
    fontSize: 15,
    flexShrink: 0,
  },

  toast: {
    position: "fixed",
    bottom: 20,
    right: 20,
    padding: "10px 16px",
    background: "white",
    border: "1px solid #d6d6de",
    borderRadius: 10,
    fontSize: 13,
    boxShadow: "0 4px 12px rgba(0,0,0,0.08)",
    zIndex: 100,
    animation: "bl-slide 0.25s ease",
  },
};
