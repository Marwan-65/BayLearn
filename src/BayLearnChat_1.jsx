import { useState, useRef, useEffect } from "react";

const API_BASE = "http://127.0.0.1:8000/api/v1";

const styles = `
  @import url('https://fonts.googleapis.com/css2?family=Syne:wght@400;600;700;800&family=JetBrains+Mono:wght@400;500&family=Inter:wght@300;400;500&display=swap');

  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

  :root {
    --bg: #0a0a0f;
    --bg2: #111118;
    --bg3: #1a1a24;
    --border: rgba(255,255,255,0.07);
    --accent: #6c63ff;
    --accent2: #a78bfa;
    --text: #f0f0f5;
    --text2: #9090a8;
    --text3: #5a5a72;
    --user-bubble: #1e1e2e;
    --ai-bubble: #13131e;
    --score-good: #4ade80;
    --score-mid: #fbbf24;
    --score-bad: #f87171;
    --shadow: 0 8px 32px rgba(108,99,255,0.15);
    --glow: 0 0 20px rgba(108,99,255,0.3);
    transition: all 0.3s ease;
  }

  [data-theme="light"] {
    --bg: #f4f4f8;
    --bg2: #ffffff;
    --bg3: #eeeef5;
    --border: rgba(0,0,0,0.08);
    --text: #0f0f1a;
    --text2: #5a5a72;
    --text3: #9090a8;
    --user-bubble: #e8e8f5;
    --ai-bubble: #ffffff;
    --shadow: 0 8px 32px rgba(108,99,255,0.1);
    --glow: 0 0 20px rgba(108,99,255,0.15);
  }

  body {
    font-family: 'Inter', sans-serif;
    background: var(--bg);
    color: var(--text);
    min-height: 100vh;
    overflow: hidden;
  }

  .app {
    display: flex;
    height: 100vh;
    position: relative;
    overflow: hidden;
  }

  /* Animated background */
  .bg-orb {
    position: fixed;
    border-radius: 50%;
    filter: blur(80px);
    opacity: 0.12;
    pointer-events: none;
    z-index: 0;
    animation: float 8s ease-in-out infinite;
  }
  .bg-orb-1 { width: 400px; height: 400px; background: #6c63ff; top: -100px; left: -100px; }
  .bg-orb-2 { width: 300px; height: 300px; background: #a78bfa; bottom: -50px; right: 200px; animation-delay: -4s; }

  @keyframes float {
    0%, 100% { transform: translateY(0px) scale(1); }
    50% { transform: translateY(-30px) scale(1.05); }
  }

  /* Sidebar */
  .sidebar {
    width: 280px;
    flex-shrink: 0;
    background: var(--bg2);
    border-right: 1px solid var(--border);
    display: flex;
    flex-direction: column;
    padding: 24px 20px;
    position: relative;
    z-index: 1;
  }

  .logo {
    display: flex;
    align-items: center;
    gap: 10px;
    margin-bottom: 32px;
  }

  .logo-icon {
    width: 36px;
    height: 36px;
    background: linear-gradient(135deg, var(--accent), var(--accent2));
    border-radius: 10px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 16px;
    box-shadow: var(--glow);
  }

  .logo-text {
    font-family: 'Syne', sans-serif;
    font-weight: 800;
    font-size: 20px;
    background: linear-gradient(135deg, var(--accent), var(--accent2));
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
  }

  .sidebar-section {
    margin-bottom: 24px;
  }

  .sidebar-label {
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 1.5px;
    text-transform: uppercase;
    color: var(--text3);
    margin-bottom: 10px;
    padding-left: 4px;
  }

  .project-input {
    width: 100%;
    background: var(--bg3);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 10px 14px;
    color: var(--text);
    font-family: 'JetBrains Mono', monospace;
    font-size: 13px;
    outline: none;
    transition: border-color 0.2s, box-shadow 0.2s;
  }

  .project-input:focus {
    border-color: var(--accent);
    box-shadow: 0 0 0 3px rgba(108,99,255,0.15);
  }

  .project-input::placeholder { color: var(--text3); }

  .action-btn {
    width: 100%;
    padding: 11px 16px;
    border-radius: 10px;
    border: 1px solid var(--border);
    background: var(--bg3);
    color: var(--text);
    font-family: 'Inter', sans-serif;
    font-size: 13px;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s;
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 8px;
    text-align: left;
  }

  .action-btn:hover {
    background: var(--accent);
    border-color: var(--accent);
    color: white;
    box-shadow: var(--glow);
    transform: translateY(-1px);
  }

  .action-btn:active { transform: translateY(0); }

  .action-btn.primary {
    background: linear-gradient(135deg, var(--accent), var(--accent2));
    border-color: transparent;
    color: white;
    font-weight: 600;
    box-shadow: var(--shadow);
  }

  .action-btn.primary:hover {
    opacity: 0.9;
    transform: translateY(-2px);
    box-shadow: var(--glow);
  }

  .status-indicator {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 10px 14px;
    border-radius: 10px;
    background: var(--bg3);
    border: 1px solid var(--border);
    font-size: 12px;
    color: var(--text2);
    margin-top: auto;
  }

  .status-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: #4ade80;
    box-shadow: 0 0 8px #4ade80;
    animation: pulse-dot 2s ease-in-out infinite;
  }

  .status-dot.offline { background: var(--text3); box-shadow: none; animation: none; }

  @keyframes pulse-dot {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.4; }
  }

  .theme-toggle {
    width: 40px;
    height: 22px;
    background: var(--bg3);
    border: 1px solid var(--border);
    border-radius: 11px;
    cursor: pointer;
    position: relative;
    transition: background 0.3s;
    margin-left: auto;
    flex-shrink: 0;
  }

  .theme-toggle::after {
    content: '';
    width: 16px;
    height: 16px;
    border-radius: 50%;
    background: var(--accent2);
    position: absolute;
    top: 2px;
    left: 2px;
    transition: transform 0.3s;
  }

  [data-theme="light"] .theme-toggle::after { transform: translateX(18px); }

  /* Main chat area */
  .chat-area {
    flex: 1;
    display: flex;
    flex-direction: column;
    position: relative;
    z-index: 1;
    overflow: hidden;
  }

  .chat-header {
    padding: 20px 32px;
    border-bottom: 1px solid var(--border);
    background: var(--bg2);
    display: flex;
    align-items: center;
    justify-content: space-between;
  }

  .chat-header-title {
    font-family: 'Syne', sans-serif;
    font-size: 18px;
    font-weight: 700;
  }

  .project-badge {
    font-family: 'JetBrains Mono', monospace;
    font-size: 12px;
    padding: 4px 10px;
    background: rgba(108,99,255,0.15);
    border: 1px solid rgba(108,99,255,0.3);
    border-radius: 20px;
    color: var(--accent2);
  }

  .messages {
    flex: 1;
    overflow-y: auto;
    padding: 32px;
    display: flex;
    flex-direction: column;
    gap: 20px;
    scroll-behavior: smooth;
  }

  .messages::-webkit-scrollbar { width: 4px; }
  .messages::-webkit-scrollbar-track { background: transparent; }
  .messages::-webkit-scrollbar-thumb { background: var(--border); border-radius: 2px; }

  /* Empty state */
  .empty-state {
    flex: 1;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 16px;
    color: var(--text3);
    text-align: center;
    padding: 40px;
  }

  .empty-icon {
    width: 64px;
    height: 64px;
    background: var(--bg3);
    border-radius: 20px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 28px;
    border: 1px solid var(--border);
    animation: float 4s ease-in-out infinite;
  }

  .empty-title {
    font-family: 'Syne', sans-serif;
    font-size: 20px;
    font-weight: 700;
    color: var(--text2);
  }

  .empty-sub { font-size: 14px; max-width: 320px; line-height: 1.6; }

  .suggestion-chips {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    justify-content: center;
    margin-top: 8px;
  }

  .chip {
    padding: 8px 16px;
    background: var(--bg3);
    border: 1px solid var(--border);
    border-radius: 20px;
    font-size: 13px;
    cursor: pointer;
    color: var(--text2);
    transition: all 0.2s;
  }

  .chip:hover {
    border-color: var(--accent);
    color: var(--accent2);
    background: rgba(108,99,255,0.1);
  }

  /* Message bubbles */
  .message {
    display: flex;
    gap: 12px;
    animation: slide-up 0.3s ease;
    max-width: 780px;
  }

  @keyframes slide-up {
    from { opacity: 0; transform: translateY(12px); }
    to { opacity: 1; transform: translateY(0); }
  }

  .message.user { align-self: flex-end; flex-direction: row-reverse; }
  .message.assistant { align-self: flex-start; }

  .avatar {
    width: 32px;
    height: 32px;
    border-radius: 10px;
    flex-shrink: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 14px;
    font-weight: 700;
    font-family: 'Syne', sans-serif;
  }

  .avatar.user-avatar { background: var(--accent); color: white; }
  .avatar.ai-avatar {
    background: linear-gradient(135deg, #1a1a2e, #2a2a4e);
    border: 1px solid var(--border);
    font-size: 16px;
  }

  .bubble {
    padding: 14px 18px;
    border-radius: 16px;
    font-size: 14px;
    line-height: 1.7;
    max-width: 680px;
    border: 1px solid var(--border);
  }

  .message.user .bubble {
    background: var(--user-bubble);
    border-radius: 16px 4px 16px 16px;
    color: var(--text);
  }

  .message.assistant .bubble {
    background: var(--ai-bubble);
    border-radius: 4px 16px 16px 16px;
    color: var(--text);
  }

  /* Sources */
  .sources {
    margin-top: 12px;
    display: flex;
    flex-direction: column;
    gap: 6px;
  }

  .sources-label {
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 1px;
    text-transform: uppercase;
    color: var(--text3);
    margin-bottom: 2px;
  }

  .source-item {
    background: var(--bg3);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 8px 12px;
    font-size: 12px;
    color: var(--text2);
    display: flex;
    align-items: flex-start;
    gap: 8px;
    line-height: 1.5;
  }

  .score-pill {
    font-family: 'JetBrains Mono', monospace;
    font-size: 10px;
    padding: 2px 7px;
    border-radius: 10px;
    flex-shrink: 0;
    font-weight: 600;
    margin-top: 1px;
  }

  .score-good { background: rgba(74,222,128,0.15); color: #4ade80; }
  .score-mid { background: rgba(251,191,36,0.15); color: #fbbf24; }
  .score-bad { background: rgba(248,113,113,0.15); color: #f87171; }

  /* Thinking indicator */
  .thinking {
    display: flex;
    gap: 5px;
    align-items: center;
    padding: 14px 18px;
  }

  .dot {
    width: 7px;
    height: 7px;
    border-radius: 50%;
    background: var(--accent2);
    animation: bounce 1.2s ease-in-out infinite;
  }

  .dot:nth-child(2) { animation-delay: 0.2s; }
  .dot:nth-child(3) { animation-delay: 0.4s; }

  @keyframes bounce {
    0%, 60%, 100% { transform: translateY(0); opacity: 0.4; }
    30% { transform: translateY(-8px); opacity: 1; }
  }

  /* Input area */
  .input-area {
    padding: 20px 32px 28px;
    background: var(--bg2);
    border-top: 1px solid var(--border);
  }

  .input-container {
    display: flex;
    gap: 12px;
    align-items: flex-end;
    background: var(--bg3);
    border: 1px solid var(--border);
    border-radius: 16px;
    padding: 12px 16px;
    transition: border-color 0.2s, box-shadow 0.2s;
  }

  .input-container:focus-within {
    border-color: var(--accent);
    box-shadow: 0 0 0 3px rgba(108,99,255,0.1);
  }

  .chat-input {
    flex: 1;
    background: transparent;
    border: none;
    outline: none;
    color: var(--text);
    font-family: 'Inter', sans-serif;
    font-size: 14px;
    resize: none;
    max-height: 120px;
    line-height: 1.5;
    min-height: 24px;
  }

  .chat-input::placeholder { color: var(--text3); }

  .send-btn {
    width: 36px;
    height: 36px;
    border-radius: 10px;
    background: linear-gradient(135deg, var(--accent), var(--accent2));
    border: none;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
    transition: all 0.2s;
    box-shadow: var(--shadow);
  }

  .send-btn:hover { transform: scale(1.05); opacity: 0.9; }
  .send-btn:active { transform: scale(0.96); }
  .send-btn:disabled { opacity: 0.4; cursor: not-allowed; transform: none; }

  .input-hint {
    font-size: 11px;
    color: var(--text3);
    margin-top: 8px;
    text-align: center;
  }

  /* Toast */
  .toast {
    position: fixed;
    bottom: 24px;
    right: 24px;
    background: var(--bg2);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 12px 20px;
    font-size: 13px;
    color: var(--text);
    box-shadow: var(--shadow);
    z-index: 100;
    animation: slide-up 0.3s ease;
    max-width: 300px;
  }

  .toast.error { border-color: rgba(248,113,113,0.4); color: #f87171; }
  .toast.success { border-color: rgba(74,222,128,0.4); color: #4ade80; }
`;

export default function BayLearnChat() {
  const [theme, setTheme] = useState("dark");
  const [projectId, setProjectId] = useState("demo_project");
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [indexing, setIndexing] = useState(false);
  const [toast, setToast] = useState(null);
  const [serverStatus, setServerStatus] = useState("checking");
  const messagesEndRef = useRef(null);
  const textareaRef = useRef(null);

  const suggestions = [
    "What are the main topics covered?",
    "Explain the key concepts",
    "What are the programming languages mentioned?",
    "Summarize the most important points",
  ];

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
  }, [theme]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // Check server status
  useEffect(() => {
    fetch(`${API_BASE}/`)
      .then(() => setServerStatus("online"))
      .catch(() => setServerStatus("offline"));
  }, []);

  const showToast = (msg, type = "info") => {
    setToast({ msg, type });
    setTimeout(() => setToast(null), 3500);
  };

  const handleIndex = async () => {
    if (!projectId.trim()) return showToast("Enter a project ID first", "error");
    setIndexing(true);
    try {
      const res = await fetch(`${API_BASE}/nlp/index/push/${projectId}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ do_reset: 0 }),
      });
      const data = await res.json();
      if (res.ok) {
        showToast(`Indexed ${data.inserted_items_count || 0} chunks ✓`, "success");
      } else {
        showToast(data.signal || "Indexing failed", "error");
      }
    } catch {
      showToast("Cannot reach server", "error");
    } finally {
      setIndexing(false);
    }
  };

  const handleSend = async (text) => {
    const question = (text || input).trim();
    if (!question || loading) return;
    if (!projectId.trim()) return showToast("Enter a project ID first", "error");

    setInput("");
    if (textareaRef.current) textareaRef.current.style.height = "24px";

    setMessages((prev) => [...prev, { role: "user", content: question }]);
    setLoading(true);

    try {
      const res = await fetch(`${API_BASE}/nlp/ask/${projectId}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: question, limit: 5 }),
      });
      const data = await res.json();

      if (res.ok && data.data) {
        setMessages((prev) => [
          ...prev,
          {
            role: "assistant",
            content: data.data.answer,
            sources: data.data.sources || [],
            scores: data.data.scores || [],
            hyde: data.data.hyde_used,
          },
        ]);
      } else {
        setMessages((prev) => [
          ...prev,
          { role: "assistant", content: "Sorry, something went wrong. Please try again.", error: true },
        ]);
      }
    } catch {
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: "Cannot reach the server. Make sure it's running at port 8000.", error: true },
      ]);
    } finally {
      setLoading(false);
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleTextareaChange = (e) => {
    setInput(e.target.value);
    e.target.style.height = "24px";
    e.target.style.height = Math.min(e.target.scrollHeight, 120) + "px";
  };

  const getScoreClass = (score) => {
    if (score >= 0.6) return "score-good";
    if (score >= 0.4) return "score-mid";
    return "score-bad";
  };

  return (
    <>
      <style>{styles}</style>
      <div className="app">
        <div className="bg-orb bg-orb-1" />
        <div className="bg-orb bg-orb-2" />

        {/* Sidebar */}
        <div className="sidebar">
          <div className="logo">
            <div className="logo-icon">🎓</div>
            <span className="logo-text">BayLearn</span>
            <button
              className="theme-toggle"
              onClick={() => setTheme(t => t === "dark" ? "light" : "dark")}
              title="Toggle theme"
            />
          </div>

          <div className="sidebar-section">
            <div className="sidebar-label">Project</div>
            <input
              className="project-input"
              value={projectId}
              onChange={(e) => setProjectId(e.target.value)}
              placeholder="project_id"
            />
          </div>

          <div className="sidebar-section">
            <div className="sidebar-label">Actions</div>
            <button className="action-btn primary" onClick={handleIndex} disabled={indexing}>
              <span>{indexing ? "⏳" : "⚡"}</span>
              {indexing ? "Indexing..." : "Index Project"}
            </button>
            <button
              className="action-btn"
              onClick={() => setMessages([])}
            >
              <span>🗑️</span> Clear Chat
            </button>
          </div>

          <div className="sidebar-section" style={{ marginTop: "auto" }}>
            <div className="sidebar-label">How to use</div>
            <div style={{ fontSize: 12, color: "var(--text3)", lineHeight: 1.7, padding: "4px" }}>
              1. Upload a PDF via API<br />
              2. Process the file<br />
              3. Click <strong style={{ color: "var(--accent2)" }}>Index Project</strong><br />
              4. Start asking questions
            </div>
          </div>

          <div className="status-indicator" style={{ marginTop: 16 }}>
            <div className={`status-dot ${serverStatus === "online" ? "" : "offline"}`} />
            <span>Server {serverStatus}</span>
          </div>
        </div>

        {/* Chat area */}
        <div className="chat-area">
          <div className="chat-header">
            <div className="chat-header-title">Study Assistant</div>
            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
              {projectId && (
                <span className="project-badge">/{projectId}</span>
              )}
              {messages.length > 0 && (
                <span style={{ fontSize: 12, color: "var(--text3)" }}>
                  {messages.filter(m => m.role === "user").length} questions
                </span>
              )}
            </div>
          </div>

          <div className="messages">
            {messages.length === 0 ? (
              <div className="empty-state">
                <div className="empty-icon">📚</div>
                <div className="empty-title">Ask about your materials</div>
                <div className="empty-sub">
                  Index your study materials and ask any question. BayLearn retrieves relevant content and answers accurately.
                </div>
                <div className="suggestion-chips">
                  {suggestions.map((s, i) => (
                    <button key={i} className="chip" onClick={() => handleSend(s)}>
                      {s}
                    </button>
                  ))}
                </div>
              </div>
            ) : (
              messages.map((msg, i) => (
                <div key={i} className={`message ${msg.role}`}>
                  <div className={`avatar ${msg.role === "user" ? "user-avatar" : "ai-avatar"}`}>
                    {msg.role === "user" ? "M" : "🤖"}
                  </div>
                  <div>
                    <div className="bubble">
                      {msg.content}
                      {msg.hyde && (
                        <div style={{ marginTop: 8, fontSize: 11, color: "var(--text3)", display: "flex", alignItems: "center", gap: 4 }}>
                          <span style={{ color: "var(--accent2)" }}>✦</span> HyDE retrieval active
                        </div>
                      )}
                    </div>
                    {msg.sources && msg.sources.length > 0 && (
                      <div className="sources">
                        <div className="sources-label">Sources retrieved</div>
                        {msg.sources.map((src, j) => (
                          <div key={j} className="source-item">
                            <span className={`score-pill ${getScoreClass(msg.scores[j] || 0)}`}>
                              {((msg.scores[j] || 0) * 100).toFixed(0)}%
                            </span>
                            <span style={{ flex: 1, overflow: "hidden" }}>
                              {src.length > 200 ? src.substring(0, 200) + "..." : src}
                            </span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              ))
            )}

            {loading && (
              <div className="message assistant">
                <div className="avatar ai-avatar">🤖</div>
                <div className="bubble">
                  <div className="thinking">
                    <div className="dot" />
                    <div className="dot" />
                    <div className="dot" />
                  </div>
                </div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>

          <div className="input-area">
            <div className="input-container">
              <textarea
                ref={textareaRef}
                className="chat-input"
                placeholder="Ask a question about your study materials..."
                value={input}
                onChange={handleTextareaChange}
                onKeyDown={handleKeyDown}
                rows={1}
              />
              <button
                className="send-btn"
                onClick={() => handleSend()}
                disabled={loading || !input.trim()}
              >
                <svg width="16" height="16" viewBox="0 0 24 24" fill="white">
                  <path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z"/>
                </svg>
              </button>
            </div>
            <div className="input-hint">
              Press Enter to send · Shift+Enter for new line
            </div>
          </div>
        </div>

        {toast && (
          <div className={`toast ${toast.type}`}>{toast.msg}</div>
        )}
      </div>
    </>
  );
}
