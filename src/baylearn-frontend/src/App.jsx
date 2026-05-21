/**
 * BayLearn — simple NotebookLM-style pipeline UI.
 *
 * Left panel  : Sources (upload + file list) + Module shortcuts
 *               (Equation Lab, Animation Lab → open teammate frontends
 *                in new tabs).
 * Right panel : Chat that hits /nlp/ask/{project_id}.
 *               The backend returns the detected intent — the UI
 *               renders:
 *                 - plain answer + sources (with image previews) for rag_only
 *                 - extracted equation + solver output for equation_from_context
 *               Animation Lab is opened manually via the sidebar button.
 *
 * Everything is one file on purpose — the design will be redone later.
 */
import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkMath from "remark-math";
import remarkGfm from "remark-gfm";
import rehypeKatex from "rehype-katex";
import "katex/dist/katex.min.css";

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

function newProjectId() {
  return "p_" + Math.random().toString(36).slice(2, 10) + Date.now().toString(36).slice(-4);
}

function loadProjects() {
  try {
    const ps = JSON.parse(localStorage.getItem("baylearn:projects") || "[]");
    if (ps.length) return ps;
  } catch {}
  // Migrate legacy single-project storage
  const legacyId = localStorage.getItem("baylearn:pid");
  const legacyFiles = (() => {
    try { return JSON.parse(localStorage.getItem("baylearn:files") || "[]"); } catch { return []; }
  })();
  const id = legacyId || newProjectId();
  return [{ id, name: "My Project", createdAt: new Date().toISOString(), files: legacyFiles }];
}

export default function App() {
  const [projects, setProjects] = useState(loadProjects);
  const [activeProjectId, setActiveProjectId] = useState(() => {
    const ps = loadProjects();
    const stored = localStorage.getItem("baylearn:activeProject");
    return (stored && ps.find((p) => p.id === stored)) ? stored : (ps[0]?.id || "");
  });
  // Derived — not their own state
  const projectId = activeProjectId;
  const activeProject = projects.find((p) => p.id === activeProjectId) || projects[0] || { files: [] };
  const files = activeProject.files || [];

  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [toast, setToast] = useState(null);
  const [serverOk, setServerOk] = useState(null);
  const bottomRef = useRef(null);
  const fileInputRef = useRef(null);

  useEffect(() => {
    localStorage.setItem("baylearn:projects", JSON.stringify(projects));
  }, [projects]);
  useEffect(() => {
    localStorage.setItem("baylearn:activeProject", activeProjectId);
  }, [activeProjectId]);
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

  /* ── Project management ───────────────────────────────────── */
  function setFiles(updater) {
    setProjects((prev) =>
      prev.map((p) =>
        p.id === activeProjectId
          ? { ...p, files: typeof updater === "function" ? updater(p.files) : updater }
          : p
      )
    );
  }
  function addProject() {
    const p = {
      id: newProjectId(),
      name: `Project ${projects.length + 1}`,
      createdAt: new Date().toISOString(),
      files: [],
    };
    setProjects((prev) => [...prev, p]);
    setActiveProjectId(p.id);
    setMessages([]);
  }
  function switchProject(id) {
    if (id === activeProjectId) return;
    setActiveProjectId(id);
    setMessages([]);
  }
  function renameProject(newName) {
    if (!newName.trim()) return;
    setProjects((prev) =>
      prev.map((p) => (p.id === activeProjectId ? { ...p, name: newName.trim() } : p))
    );
  }
  function deleteProject(id) {
    if (projects.length === 1) return showToast("Cannot delete the only project", "error");
    const remaining = projects.filter((p) => p.id !== id);
    setProjects(remaining);
    if (activeProjectId === id) {
      setActiveProjectId(remaining[0].id);
      setMessages([]);
    }
  }

  /* ── Upload — async: POST returns job_id, then poll until done ─ */
  async function handleUpload(fileList) {
    const list = Array.from(fileList || []);
    if (!list.length) return;
    setUploading(true);

    for (const file of list) {
      // Show the file immediately as "pending" so it never disappears
      setFiles((prev) => [
        ...prev.filter((f) => f.filename !== file.name),
        { filename: file.name, size: file.size, chunks: 0, indexed: false, pending: true },
      ]);

      try {
        const form = new FormData();
        form.append("file", file);
        // POST returns 202 immediately with job_id
        const res = await fetch(
          `${API_BASE}/parse/upload/${projectId}`,
          { method: "POST", body: form }
        );
        const data = await res.json().catch(() => ({}));
        if (!res.ok && res.status !== 202)
          throw new Error(data.signal || `HTTP ${res.status}`);

        // Poll status until done or error
        const pollUrl = `${API_BASE}/parse/status/${projectId}?filename=${encodeURIComponent(file.name)}`;
        let done = false;
        while (!done) {
          await new Promise((r) => setTimeout(r, 6000)); // poll every 6s
          try {
            const sr = await fetch(pollUrl);
            const s = await sr.json().catch(() => ({}));
            if (s.status === "done") {
              setFiles((prev) =>
                prev.map((f) =>
                  f.filename === file.name
                    ? { filename: file.name, size: file.size, chunks: s.indexed_count || 0, indexed: true, pending: false }
                    : f
                )
              );
              showToast(`${file.name} indexed ✓ (${s.indexed_count} chunks)`, "success");
              done = true;
            } else if (s.status === "error") {
              throw new Error(s.error || "Parsing failed");
            }
            // status "pending" or "indexing" → keep polling
          } catch (pollErr) {
            throw pollErr;
          }
        }
      } catch (err) {
        setFiles((prev) =>
          prev.map((f) =>
            f.filename === file.name
              ? { ...f, pending: false, indexed: false, indexError: err.message || "Upload failed" }
              : f
          )
        );
        showToast(`Upload failed for ${file.name}: ${err.message}`, "error");
      }
    }

    setUploading(false);
    if (fileInputRef.current) fileInputRef.current.value = "";
  }

  /* ── Ask (intent-aware) ───────────────────────────────────── */
  async function send(textOverride) {
    const q = (textOverride ?? input).trim();
    if (!q || loading) return;
    setInput("");
    setMessages((m) => [...m, { role: "user", content: q }]);
    setLoading(true);
    try {
      // Send last 6 messages (3 exchanges) as history so the LLM can handle
      // follow-up questions like "I didn't understand".
      const historyToSend = messages
        .slice(-6)
        .filter((m) => m.role === "user" || m.role === "assistant")
        .map((m) => ({ role: m.role, content: (m.content || "").slice(0, 800) }));

      const data = await jsonFetch(`/nlp/ask/${projectId}`, {
        method: "POST",
        body: JSON.stringify({ text: q, limit: 5, chat_history: historyToSend }),
      });
      const d = data.data || {};
      setMessages((m) => [
        ...m,
        {
          role: "assistant",
          content: d.answer || "(empty response)",
          sources: d.sources || [],
          sourceMeta: d.source_meta || [],
          scores: d.scores || [],
          intent: d.intent || null,
          equation: d.equation_text_sent || d.equation || null,
          equationResult: d.equation_result || null,
          raw: d,
        },
      ]);
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

  async function removeFile(filename) {
    // Optimistically remove from UI first
    setFiles((prev) => prev.filter((f) => f.filename !== filename));
    // Then clean up backend chunks + re-index
    try {
      await fetch(
        `${API_BASE}/parse/source/${projectId}?filename=${encodeURIComponent(filename)}`,
        { method: "DELETE" }
      );
    } catch {
      // Non-fatal — the file list is already removed from the UI
    }
  }

  const suggestions = [
    "Summarize the key concepts from my materials",
    "Solve the equation from page 3",
    "What are the most important points to review?",
    "Explain the main algorithm described in the lecture",
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

        {/* Project selector */}
        <label style={S.label}>PROJECT</label>
        <div style={{ display: "flex", gap: 6, alignItems: "center", marginBottom: 4 }}>
          <select
            value={activeProjectId}
            onChange={(e) => switchProject(e.target.value)}
            style={{
              flex: 1, fontSize: 13, padding: "5px 8px", borderRadius: 6,
              border: "1px solid #d6d6de", background: "#fff", color: "#1a1a1a",
              cursor: "pointer",
            }}
          >
            {projects.map((p) => (
              <option key={p.id} value={p.id}>{p.name}</option>
            ))}
          </select>
          <button
            onClick={addProject}
            title="New project"
            style={{
              padding: "5px 10px", borderRadius: 6, border: "1px solid #d6d6de",
              background: "#fff", cursor: "pointer", fontSize: 16, fontWeight: 700,
              color: "#6c63ff",
            }}
          >+</button>
          {projects.length > 1 && (
            <button
              onClick={() => deleteProject(activeProjectId)}
              title="Delete this project"
              style={{
                padding: "5px 8px", borderRadius: 6, border: "1px solid #fca5a5",
                background: "#fff", cursor: "pointer", fontSize: 13, color: "#dc2626",
              }}
            >🗑</button>
          )}
        </div>
        <div style={{ display: "flex", gap: 4, alignItems: "center", marginBottom: 12 }}>
          <input
            key={activeProjectId}
            defaultValue={activeProject.name}
            onBlur={(e) => renameProject(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter") e.target.blur(); }}
            style={{
              flex: 1, fontSize: 12, padding: "3px 8px", borderRadius: 6,
              border: "1px solid #e6e6ec", background: "#fafafd", color: "#555",
            }}
            placeholder="Rename project…"
          />
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
            PDF · TXT
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
                  <div style={{ ...S.fileMeta, color: f.indexError ? "#dc2626" : "#888" }}>
                    {f.pending
                      ? "⏳ parsing…"
                      : f.indexError
                      ? `⚠ ${f.indexError.slice(0, 60)}`
                      : `${(f.size / 1024).toFixed(0)} KB · ${f.chunks} chunks${f.indexed ? " · ✓" : ""}`}
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
          Ask a question or click a module above to open it in a new tab.
          BayLearn detects equation questions and routes them automatically.
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
          <div style={{ fontSize: 15, fontWeight: 700 }}>{activeProject?.name || "Study Assistant"}</div>
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
                <div>② Ask a question below — BayLearn answers from your materials, or routes to the equation module when you ask to solve/derive something.</div>
                <div>③ Open <b>Equation Lab</b> or <b>Animation Lab</b> directly from the sidebar for interactive work.</div>
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
          {m.error ? (
            m.content
          ) : (
            <ReactMarkdown
              remarkPlugins={[remarkMath, remarkGfm]}
              rehypePlugins={[rehypeKatex]}
              components={{
                p: ({ children }) => (
                  <span style={{ display: "block", marginBottom: 6 }}>{children}</span>
                ),
                ul: ({ children }) => (
                  <ul style={{ paddingLeft: 18, margin: "3px 0 6px" }}>{children}</ul>
                ),
                ol: ({ children }) => (
                  <ol style={{ paddingLeft: 18, margin: "3px 0 6px" }}>{children}</ol>
                ),
                li: ({ children }) => (
                  <li style={{ marginBottom: 1, lineHeight: 1.5 }}>{children}</li>
                ),
                h1: ({ children }) => (
                  <span style={{ display: "block", fontWeight: 700, fontSize: 14, marginBottom: 4 }}>{children}</span>
                ),
                h2: ({ children }) => (
                  <span style={{ display: "block", fontWeight: 700, fontSize: 14, marginBottom: 4 }}>{children}</span>
                ),
                h3: ({ children }) => (
                  <span style={{ display: "block", fontWeight: 700, fontSize: 14, marginBottom: 2 }}>{children}</span>
                ),
                strong: ({ children }) => (
                  <strong style={{ fontWeight: 700 }}>{children}</strong>
                ),
                // react-markdown v8+ removed the `inline` prop. Detect block
                // code by: has a language className OR content contains a newline.
                code: ({ children, className }) => {
                  const isBlock = !!className || (typeof children === "string" && children.includes("\n"));
                  return isBlock ? (
                    <pre style={{ background: "#f8f8f8", borderRadius: 6, padding: "8px 10px", overflowX: "auto", fontSize: "0.85em", margin: "4px 0 6px" }}>
                      <code style={{ fontFamily: "monospace" }}>{children}</code>
                    </pre>
                  ) : (
                    <code style={{ background: "#f0f0f0", borderRadius: 3, padding: "1px 4px", fontSize: "0.88em", fontFamily: "monospace" }}>{children}</code>
                  );
                },
                blockquote: ({ children }) => (
                  <blockquote style={{ borderLeft: "3px solid #d0d0e0", margin: "4px 0", paddingLeft: 10, color: "#555" }}>{children}</blockquote>
                ),
              }}
            >
              {m.content}
            </ReactMarkdown>
          )}
        </div>

        {/* Inline figures — show ALL promoted image sources that have an
            image_url (the backend only promotes images from pages that are
            already in the retrieved text sources, so every promoted image
            is relevant by construction).
            We also scan [Source N] citations so we can badge cited images
            with "mentioned in answer" — but we no longer hide uncited ones.
            The LLM sometimes calls a TEXT chunk "the figure" (because the
            text describes a figure) and never cites the promoted IMAGE chunk
            by its correct number — hiding the image in that case is wrong. */}
        {m.sourceMeta && m.sourceMeta.some(meta => meta.chunk_type === "image" && meta.image_url) && (() => {
          // Build the set of source numbers explicitly cited in the answer.
          const referenced = new Set();
          const re = /\[Source\s+([\d,\s&and]+)\]/gi;
          let mm;
          while ((mm = re.exec(m.content || "")) !== null) {
            for (const num of mm[1].match(/\d+/g) || []) {
              referenced.add(parseInt(num, 10));
            }
          }
          // Show ALL image sources that have a URL (cited or not).
          const visible = m.sourceMeta
            .map((meta, j) => ({ meta, srcNum: j + 1 }))
            .filter(({ meta }) => meta.chunk_type === "image" && meta.image_url);
          if (visible.length === 0) return null;
          return (
            <div style={{ marginTop: 8 }}>
              {visible.map(({ meta, srcNum }) => {
                const isCited = referenced.has(srcNum);
                const badge = [
                  meta.page ? `p.${meta.page}` : null,
                  meta.section_heading ? meta.section_heading.slice(0, 40) : null,
                ].filter(Boolean).join(" · ");
                return (
                  <div key={srcNum} style={{ marginBottom: 10 }}>
                    <div style={{ fontSize: 11, color: "#666", marginBottom: 3, display: "flex", alignItems: "center", gap: 6 }}>
                      📷 Figure [Source {srcNum}]{badge ? ` — ${badge}` : ""}
                      {isCited && (
                        <span style={{ background: "#dcfce7", color: "#15803d", borderRadius: 4, padding: "1px 6px", fontSize: 10, fontWeight: 600 }}>
                          mentioned in answer
                        </span>
                      )}
                    </div>
                    <img
                      src={meta.image_url}
                      alt={`Source ${srcNum}`}
                      style={{
                        maxWidth: "100%",
                        maxHeight: 280,
                        borderRadius: 6,
                        border: "1px solid #e0e0e0",
                        display: "block",
                      }}
                    />
                  </div>
                );
              })}
            </div>
          );
        })()}

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
              const meta = m.sourceMeta?.[j] || {};
              const isImage = meta.chunk_type === "image";
              const imgUrl = meta.image_url;
              // Page / section badge
              const badge = [
                meta.page ? `p.${meta.page}` : null,
                meta.section_heading
                  ? meta.section_heading.slice(0, 30)
                  : null,
              ]
                .filter(Boolean)
                .join(" · ");
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
                  <div style={{ flex: 1, minWidth: 0 }}>
                    {badge ? (
                      <div style={{ fontSize: 10, color: "#888", marginBottom: 2 }}>
                        {isImage ? "📷 " : ""}{badge}
                      </div>
                    ) : isImage ? (
                      <div style={{ fontSize: 10, color: "#888", marginBottom: 2 }}>📷 image chunk</div>
                    ) : null}
                    {/* Render image when the parsing module returned a URL */}
                    {isImage && imgUrl && (
                      <img
                        src={imgUrl}
                        alt="source image"
                        style={{
                          maxWidth: "100%",
                          maxHeight: 200,
                          borderRadius: 6,
                          marginBottom: 4,
                          display: "block",
                        }}
                      />
                    )}
                    <span style={{ fontSize: 12, color: "#444" }}>
                      {String(src).length > 240
                        ? String(src).slice(0, 240) + "…"
                        : String(src)}
                    </span>
                  </div>
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
    lineHeight: 1.55,
    color: "#1a1a1a",
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
