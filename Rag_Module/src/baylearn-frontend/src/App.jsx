import { useEffect, useRef, useState } from "react";

const API_BASE = import.meta.env.VITE_API_BASE || "http://127.0.0.1:8000/api/v1";
const QUESTION_API_BASE =
  import.meta.env.VITE_QUESTION_API_BASE || "http://127.0.0.1:8002/api/v1";
const EQUATION_URL =
  import.meta.env.VITE_EQUATION_FRONTEND_URL || "http://localhost:8501";
const ANIMATION_URL =
  import.meta.env.VITE_ANIMATION_FRONTEND_URL || "http://localhost:3001";

async function jsonFetch(path, opts = {}, baseUrl = API_BASE) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 90_000);
  let res;

  try {
    res = await fetch(`${baseUrl}${path}`, {
      headers: { "Content-Type": "application/json", ...(opts.headers || {}) },
      signal: controller.signal,
      ...opts,
    });
  } catch (e) {
    clearTimeout(timer);
    if (e.name === "AbortError") {
      const err = new Error("Request timed out after 90s. Please try again.");
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

function getOrCreateProjectId() {
  let pid = localStorage.getItem("baylearn:pid");
  if (!pid) {
    pid =
      "p_" +
      Math.random().toString(36).slice(2, 10) +
      Date.now().toString(36).slice(-4);
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
  // The files the user is currently working with. Chat + question generation are
  // scoped to these files' chunks (keyed by their file_ids, sent comma-joined).
  const [selectedFileIds, setSelectedFileIds] = useState(() => {
    try {
      return JSON.parse(localStorage.getItem("baylearn:selectedFileIds") || "[]");
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

  const [activeTab, setActiveTab] = useState("chat"); // "chat" or "questions"
  const [questionTopic, setQuestionTopic] = useState("");
  const [questionType, setQuestionType] = useState("mcq");
  const [questionDifficulty, setQuestionDifficulty] = useState("easy");
  const [questionLoading, setQuestionLoading] = useState(false);
  const [questionCards, setQuestionCards] = useState([]);
  const [currentQuestionIndex, setCurrentQuestionIndex] = useState(0);

  // Adaptive (agent-driven) mode: the RL module picks topic+difficulty and posts
  // to the QG module; the frontend shows that question and reports the answer.
  const ADAPTIVE_SESSION = "default";
  const [adaptiveMode, setAdaptiveMode] = useState(false);
  const [adaptiveItem, setAdaptiveItem] = useState(null);
  const adaptiveVersionRef = useRef(0);

  const bottomRef = useRef(null);
  const fileInputRef = useRef(null);

  useEffect(() => {
    localStorage.setItem("baylearn:files", JSON.stringify(files));
  }, [files]);

  useEffect(() => {
    localStorage.setItem("baylearn:selectedFileIds", JSON.stringify(selectedFileIds));
  }, [selectedFileIds]);

  // Adaptive mode: register the source files for the session whenever the
  // selection (or type) changes while the mode is on.
  useEffect(() => {
    if (!adaptiveMode || selectedFileIds.length === 0) return;
    jsonFetch(
      `/questions/adaptive/${ADAPTIVE_SESSION}/config`,
      { method: "POST", body: JSON.stringify({ file_ids: selectedFileIds.join(","), question_type: questionType }) },
      QUESTION_API_BASE
    ).catch(() => {});
  }, [adaptiveMode, selectedFileIds, questionType]);

  // Adaptive mode: poll for the question the RL agent generated and display it.
  useEffect(() => {
    if (!adaptiveMode) return;
    let cancelled = false;
    async function tick() {
      try {
        const data = await jsonFetch(
          `/questions/adaptive/${ADAPTIVE_SESSION}/current`,
          {},
          QUESTION_API_BASE
        );
        if (cancelled || !data?.question) return;
        if (data.version > adaptiveVersionRef.current) {
          adaptiveVersionRef.current = data.version;
          const card = data.question; // { question, questionType, topic, difficulty, chunksUsed }
          setAdaptiveItem({
            id: data.version,
            question: card.question,
            questionType: card.questionType,
            topic: card.topic,
            difficulty: card.difficulty,
            chunksUsed: card.chunksUsed,
          });
        }
      } catch {
        /* QG unreachable — keep polling */
      }
    }
    tick();
    const id = setInterval(tick, 1500);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [adaptiveMode]);

  // Toggle a file in/out of the active selection.
  function toggleFileSelection(fileId) {
    if (!fileId) return;
    setSelectedFileIds((prev) =>
      prev.includes(fileId) ? prev.filter((id) => id !== fileId) : [...prev, fileId]
    );
  }

  useEffect(() => {
    if (!loading && messages.length === 0) return;
    bottomRef.current?.scrollIntoView({
      behavior: "smooth",
      block: "end",
      inline: "nearest",
    });
  }, [messages, loading]);

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
            file_id: data.file_id || null,
            size: file.size,
            chunks: data.chunks_created || data.inserted_items_count || data.chunks || 0,
            indexed: data.indexed !== false,
          },
        ]);
        // Auto-include the file just uploaded in the active selection.
        if (data.file_id) {
          setSelectedFileIds((prev) =>
            prev.includes(data.file_id) ? prev : [...prev, data.file_id]
          );
        }
      }
      showToast(`Uploaded ${list.length} file(s).`, "success");
    } catch (err) {
      showToast(err.message || "Upload failed", "error");
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  }

  async function send(textOverride) {
    const q = (textOverride ?? input).trim();
    if (!q || loading) return;

    if (selectedFileIds.length === 0) {
      showToast("Select at least one file to ask about first.", "error");
      return;
    }

    setInput("");
    setMessages((m) => [...m, { role: "user", content: q }]);
    setLoading(true);

    try {
      // Scope to the selected files (comma-joined file_ids; backend merges them).
      const data = await jsonFetch(`/nlp/ask/${selectedFileIds.join(",")}`, {
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
        },
      ]);

      if (d.animation_spec || d.animation) {
        try {
          window.open(ANIMATION_URL, "_blank", "noopener");
        } catch {
          // no-op
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
              ? "Rate limit reached, please retry in a minute."
              : err.message || "Cannot reach server.",
        },
      ]);
    } finally {
      setLoading(false);
    }
  }

  async function generateQuestion() {
    if (questionLoading) return;

    if (files.length === 0) {
      showToast("Upload and index at least one source first.", "error");
      return;
    }

    if (selectedFileIds.length === 0) {
      showToast("Select at least one file to generate questions from.", "error");
      return;
    }

    setQuestionLoading(true);
    try {
      const topic = questionTopic.trim();
      const data = await jsonFetch(
        "/questions/generate",
        {
          method: "POST",
          body: JSON.stringify({
            // Questions are generated from the selected files (comma-joined
            // file_ids; the question module forwards them to RAG search, which
            // merges chunks across the selected files).
            project_id: selectedFileIds.join(","),
            topic: topic || null,
            num_questions: 1,
            difficulty: questionDifficulty,
            question_type: questionType,
          }),
        },
        QUESTION_API_BASE
      );

      const generated = data.questions?.[0];
      if (!generated) {
        throw new Error("Question module returned no question.");
      }

      setQuestionCards((prev) => [
        {
          id: Date.now(),
          topic: topic || "General",
          questionType,
          question: generated,
          chunksUsed: data.chunks_used ?? 0,
        },
        ...prev,
      ]);
      showToast(`Generated one ${questionDifficulty} question.`, "success");
    } catch (err) {
      showToast(err.message || "Question generation failed", "error");
    } finally {
      setQuestionLoading(false);
    }
  }

  function removeFile(filename) {
    setFiles((prev) => {
      const removed = prev.find((f) => f.filename === filename);
      if (removed?.file_id) {
        setSelectedFileIds((ids) => ids.filter((id) => id !== removed.file_id));
      }
      return prev.filter((f) => f.filename !== filename);
    });
  }

  const suggestions = [
    "Summarize the key concepts from my materials",
    "Solve the equation from page 3",
    "Animate a linked list insertion",
    "What are the most important points to review?",
  ];

  return (
    <div style={S.app}>
      <aside style={S.sidebar}>
        <div style={S.brand}>
          <div style={S.logo}>B</div>
          <div>
            <div style={{ fontWeight: 700, fontSize: 15 }}>BayLearn</div>
            <div style={{ fontSize: 11, color: "#888" }}>Adaptive study hub</div>
          </div>
        </div>

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
          <div style={{ fontSize: 13, fontWeight: 600, marginTop: 4 }}>
            {uploading ? "Uploading..." : "Add sources"}
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

        {files.length > 0 && (
          <div style={{ fontSize: 11, color: "#888", margin: "10px 4px 4px" }}>
            Check files to use in chat & questions ({selectedFileIds.length} selected)
          </div>
        )}

        <div style={S.fileList}>
          {files.length === 0 ? (
            <div style={{ fontSize: 12, color: "#999", padding: "8px 4px" }}>
              No sources yet.
            </div>
          ) : (
            files.map((f) => (
              <div
                key={f.filename}
                style={{
                  ...S.fileRow,
                  background: f.file_id && selectedFileIds.includes(f.file_id)
                    ? "#f0f0ff"
                    : S.fileRow?.background,
                }}
              >
                <input
                  type="checkbox"
                  checked={!!f.file_id && selectedFileIds.includes(f.file_id)}
                  disabled={!f.file_id}
                  onChange={() => toggleFileSelection(f.file_id)}
                  title={f.file_id ? "Use this file" : "Re-upload to enable selection"}
                  style={{ cursor: f.file_id ? "pointer" : "not-allowed", marginRight: 8 }}
                />
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={S.fileName}>{f.filename}</div>
                  <div style={S.fileMeta}>
                    {(f.size / 1024).toFixed(0)} KB · {f.chunks} chunks
                    {f.indexed ? " · indexed" : ""}
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

        <label style={{ ...S.label, marginTop: 18 }}>MODULES</label>
        <button onClick={() => window.open(EQUATION_URL, "_blank")} style={S.modCard}>
          <div style={{ flex: 1, textAlign: "left" }}>
            <div style={{ fontSize: 13, fontWeight: 600 }}>Equation Lab</div>
            <div style={{ fontSize: 11, color: "#888" }}>Symbolic + numeric solver</div>
          </div>
          <span style={{ fontSize: 12, color: "#888" }}>↗</span>
        </button>

        <button onClick={() => window.open(ANIMATION_URL, "_blank")} style={S.modCard}>
          <div style={{ flex: 1, textAlign: "left" }}>
            <div style={{ fontSize: 13, fontWeight: 600 }}>Animation Lab</div>
            <div style={{ fontSize: 11, color: "#888" }}>Algorithm visualizer</div>
          </div>
          <span style={{ fontSize: 12, color: "#888" }}>↗</span>
        </button>

        <div style={{ fontSize: 11, color: "#999", marginTop: 10, lineHeight: 1.6 }}>
          Ask in chat for explanations, equation solving, or animation routing.
        </div>

        <div style={{ flex: 1 }} />

        <div style={S.status}>
          <span
            style={{
              ...S.dot,
              background: serverOk ? "#4ade80" : "#f87171",
            }}
          />
          Server {serverOk === null ? "checking" : serverOk ? "online" : "offline"}
        </div>
      </aside>

      <main style={S.main}>
        <header style={S.header}>
          <div style={{ fontSize: 15, fontWeight: 700 }}>Study Assistant</div>
          <div style={{ fontSize: 12, color: "#888" }}>
            {files.length} source{files.length === 1 ? "" : "s"} indexed
          </div>
        </header>

        {/* Tab Switcher */}
        <div style={S.tabBar}>
          <button
            onClick={() => {
              setActiveTab("chat");
            }}
            style={{
              ...S.tabBtn,
              background: activeTab === "chat" ? "white" : "transparent",
              borderBottom: activeTab === "chat" ? "2px solid #6c63ff" : "1px solid #e6e6ec",
            }}
          >
            Chat
          </button>
          <button
            onClick={() => {
              setActiveTab("questions");
            }}
            style={{
              ...S.tabBtn,
              background: activeTab === "questions" ? "white" : "transparent",
              borderBottom: activeTab === "questions" ? "2px solid #6c63ff" : "1px solid #e6e6ec",
            }}
          >
            Question Studio
            {questionCards.length > 0 && (
              <span style={{ marginLeft: 8, fontSize: 11, color: "#888" }}>
                ({currentQuestionIndex + 1}/{questionCards.length})
              </span>
            )}
          </button>
        </div>

        {/* Chat Tab */}
        {activeTab === "chat" && (
          <div style={S.contentShell}>
            <section style={S.chatColumn}>
              <div style={S.messages}>
                {messages.length === 0 ? (
                  <div style={S.empty}>
                    <div style={{ fontSize: 18, fontWeight: 700, marginTop: 8 }}>
                      Three things you can do
                    </div>
                    <div
                      style={{
                        fontSize: 13,
                        color: "#777",
                        marginTop: 6,
                        maxWidth: 460,
                        lineHeight: 1.7,
                        textAlign: "left",
                      }}
                    >
                      <div>1. Drop study materials into Sources on the left.</div>
                      <div>
                        2. Ask in chat and BayLearn answers from your material or routes to modules.
                      </div>
                      <div>3. Switch to Question Studio tab to generate quiz questions.</div>
                    </div>
                    <div style={{ fontSize: 12, color: "#999", marginTop: 14 }}>Try one:</div>
                    <div
                      style={{
                        display: "flex",
                        flexWrap: "wrap",
                        gap: 8,
                        justifyContent: "center",
                        marginTop: 16,
                      }}
                    >
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
                    <div style={S.avatarAI}>AI</div>
                    <div style={S.bubbleAI}>Thinking...</div>
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
                    placeholder="Ask a question, or try solve 2x+3=7"
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
                    Send
                  </button>
                </div>
                <div style={{ fontSize: 11, color: "#999", marginTop: 6, textAlign: "center" }}>
                  Enter to send · Shift+Enter for newline
                </div>
              </div>
            </section>
          </div>
        )}

        {/* Question Studio Tab - Carousel */}
        {activeTab === "questions" && (
          <div style={S.contentShell}>
            <section style={{ ...S.chatColumn, display: "flex", flexDirection: "column" }}>
              <div style={S.questionControls}>
                <label
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 8,
                    fontSize: 12,
                    fontWeight: 600,
                    color: "#444",
                    marginBottom: 10,
                    cursor: "pointer",
                  }}
                >
                  <input
                    type="checkbox"
                    checked={adaptiveMode}
                    onChange={(e) => {
                      adaptiveVersionRef.current = 0;
                      setAdaptiveItem(null);
                      setAdaptiveMode(e.target.checked);
                    }}
                  />
                  Adaptive (RL) mode — the agent picks the questions
                </label>

                <label style={S.qLabel}>Topic (optional)</label>
                <input
                  value={questionTopic}
                  onChange={(e) => setQuestionTopic(e.target.value)}
                  placeholder="e.g. chain rule"
                  style={S.qInput}
                />

                <label style={S.qLabel}>Question type</label>
                <select
                  value={questionType}
                  onChange={(e) => setQuestionType(e.target.value)}
                  style={S.qInput}
                >
                  <option value="mcq">MCQ</option>
                  <option value="short_answer">Short answer</option>
                  <option value="true_false">True/False</option>
                </select>

                <label style={S.qLabel}>Difficulty</label>
                <select
                  value={questionDifficulty}
                  onChange={(e) => setQuestionDifficulty(e.target.value)}
                  style={S.qInput}
                >
                  <option value="easy">easy</option>
                  <option value="medium">medium</option>
                  <option value="hard">hard</option>  
                </select>

                {adaptiveMode ? (
                  <div
                    style={{
                      ...S.generateBtn,
                      background: "#eef0ff",
                      color: "#4b46c4",
                      textAlign: "center",
                      cursor: "default",
                    }}
                  >
                    {selectedFileIds.length === 0
                      ? "Select file(s) above to start"
                      : adaptiveItem
                      ? "Answer below — the agent is waiting"
                      : "Waiting for the RL agent to send a question…"}
                  </div>
                ) : (
                  <button
                    onClick={generateQuestion}
                    disabled={questionLoading}
                    style={{ ...S.generateBtn, opacity: questionLoading ? 0.55 : 1 }}
                  >
                    {questionLoading ? "Generating..." : `Generate (${questionDifficulty})`}
                  </button>
                )}

                <div style={S.qHint}>
                  {adaptiveMode
                    ? "The RL agent chooses topic & difficulty. Your answer is sent back to it automatically."
                    : "Uses current project sources and project id automatically."}
                </div>
              </div>

              {/* Carousel Container */}
              <div style={S.carouselContainer}>
                {adaptiveMode ? (
                  adaptiveItem ? (
                    <div style={S.carouselSlideItem}>
                      {/* key=id remounts a fresh card for each new agent question */}
                      <QuestionCard
                        key={adaptiveItem.id}
                        item={adaptiveItem}
                        sessionId={ADAPTIVE_SESSION}
                      />
                    </div>
                  ) : (
                    <div style={{ ...S.carouselEmpty, display: "flex", alignItems: "center", justifyContent: "center" }}>
                      <div style={{ textAlign: "center" }}>
                        <div style={{ fontSize: 16, fontWeight: 600, color: "#555" }}>Waiting for the RL agent…</div>
                        <div style={{ fontSize: 12, color: "#999", marginTop: 6 }}>
                          The next question will appear here automatically.
                        </div>
                      </div>
                    </div>
                  )
                ) : questionCards.length === 0 ? (
                  <div style={{ ...S.carouselEmpty, display: "flex", alignItems: "center", justifyContent: "center" }}>
                    <div style={{ textAlign: "center" }}>
                      <div style={{ fontSize: 16, fontWeight: 600, color: "#555" }}>No questions yet</div>
                      <div style={{ fontSize: 12, color: "#999", marginTop: 6 }}>
                        Generate your first question above
                      </div>
                    </div>
                  </div>
                ) : (
                  <>
                    {/* Carousel Viewport */}
                    <div style={S.carouselViewport}>
                      <div
                        style={{
                          ...S.carouselSlide,
                          transform: `translateX(-${currentQuestionIndex * 100}%)`,
                        }}
                      >
                        {questionCards.map((item) => (
                          <div key={item.id} style={S.carouselSlideItem}>
                            <QuestionCard item={item} />
                          </div>
                        ))}
                      </div>
                    </div>

                    {/* Navigation Arrows & Dots */}
                    <div style={S.carouselNav}>
                      <button
                        onClick={() =>
                          setCurrentQuestionIndex(Math.max(0, currentQuestionIndex - 1))
                        }
                        disabled={currentQuestionIndex === 0}
                        style={{
                          ...S.arrowBtn,
                          opacity: currentQuestionIndex === 0 ? 0.3 : 1,
                        }}
                      >
                        ←
                      </button>

                      <div style={S.dotContainer}>
                        {questionCards.map((_, idx) => (
                          <button
                            key={idx}
                            onClick={() => setCurrentQuestionIndex(idx)}
                            style={{
                              ...S.dot,
                              background: idx === currentQuestionIndex ? "#6c63ff" : "#d9d9e3",
                            }}
                          />
                        ))}
                      </div>

                      <button
                        onClick={() =>
                          setCurrentQuestionIndex(
                            Math.min(questionCards.length - 1, currentQuestionIndex + 1)
                          )
                        }
                        disabled={currentQuestionIndex === questionCards.length - 1}
                        style={{
                          ...S.arrowBtn,
                          opacity: currentQuestionIndex === questionCards.length - 1 ? 0.3 : 1,
                        }}
                      >
                        →
                      </button>
                    </div>
                  </>
                )}
              </div>
            </section>
          </div>
        )}
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
    </div>
  );
}

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
      <div style={S.avatarAI}>AI</div>
      <div style={{ maxWidth: 680 }}>
        {m.intent && <IntentBadge intent={m.intent} />}
        <div style={{ ...S.bubbleAI, ...(m.error ? { borderColor: "#f87171", color: "#c53030" } : {}) }}>
          {m.content}
        </div>

        {m.equation && (
          <div style={S.card}>
            <div style={S.cardLabel}>Equation</div>
            <code style={S.code}>{m.equation}</code>
            {m.equationResult ? (
              <EquationSolution result={m.equationResult} equation={m.equation} />
            ) : (
              <a
                href={`${EQUATION_URL}/?q=${encodeURIComponent(m.equation)}&autosolve=1`}
                target="_blank"
                rel="noopener noreferrer"
                style={S.launchBtn}
              >
                Open Equation Lab
              </a>
            )}
          </div>
        )}

        {m.animation && (
          <div style={S.card}>
            <div style={S.cardLabel}>Animation spec</div>
            <div style={S.specGrid}>
              {Object.entries(m.animation).map(([k, v]) => (
                <div key={k} style={S.specRow}>
                  <span style={S.specKey}>{k}</span>
                  <span style={S.specVal}>{Array.isArray(v) ? v.join(", ") : String(v)}</span>
                </div>
              ))}
            </div>
            <a href={ANIMATION_URL} target="_blank" rel="noopener noreferrer" style={S.launchBtn}>
              Open Animation Lab
            </a>
          </div>
        )}

        {m.sources && m.sources.length > 0 && (
          <div style={{ marginTop: 8 }}>
            <div style={S.srcLabel}>Sources retrieved</div>
            {m.sources.map((src, j) => {
              const raw = m.scores?.[j] ?? 0;
              const score = Math.max(0, Math.min(1, raw));
              const color =
                score >= 0.6 ? "#16a34a" : score >= 0.4 ? "#ca8a04" : "#dc2626";
              return (
                <div key={j} style={S.src}>
                  <span style={{ ...S.scorePill, color, background: color + "1A" }}>
                    {(score * 100).toFixed(0)}%
                  </span>
                  <span style={{ flex: 1, fontSize: 12, color: "#444" }}>
                    {String(src).length > 240 ? String(src).slice(0, 240) + "..." : String(src)}
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
    return <div style={{ marginTop: 10, color: "#c53030", fontSize: 13 }}>Solver error: {result.error || "unknown"}</div>;
  }

  const steps = Array.isArray(result.steps) ? result.steps : [];
  const final = result.final_result;
  const lab = `${EQUATION_URL}/?q=${encodeURIComponent(equation || "")}&autosolve=1`;

  return (
    <>
      {final && (
        <>
          <div style={{ ...S.cardLabel, marginTop: 10 }}>Answer</div>
          <div style={S.answerBox}>{cleanLatex(final)}</div>
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

      <a href={lab} target="_blank" rel="noopener noreferrer" style={S.launchBtn}>
        Open Equation Lab
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
      {m.label}
    </div>
  );
}

function QuestionCard({ item, sessionId }) {
  const q = item.question;
  const [selected, setSelected] = useState(null); // MCQ: label string, T/F: "true"/"false", SA: "submitted"
  const [shortAnswerText, setShortAnswerText] = useState("");
  const [result, setResult] = useState(null);   // backend grade for ALL types: { is_correct, method, score }
  const [checking, setChecking] = useState(false);
  const revealed = selected !== null;
  const isMCQ = item.questionType === "mcq" && Array.isArray(q.options) && q.options.length > 0;
  const isTrueFalse = item.questionType === "true_false";
  const isShortAnswer = item.questionType === "short_answer";

  // Correctness is decided by the BACKEND (/questions/check) for every type, so
  // it's a single source of truth other modules can rely on. The local branches
  // below are only a fallback used if the backend was unreachable.
  let isCorrect = false;
  if (result) {
    isCorrect = result.is_correct;
  } else if (isMCQ) {
    isCorrect = q.options.find((o) => o.label === selected)?.is_correct || false;
  } else if (isTrueFalse) {
    isCorrect = (q.correct_answer || "").toLowerCase() === (selected || "").toLowerCase();
  } else if (isShortAnswer) {
    const userLower = shortAnswerText.toLowerCase().trim();
    const keywordHints = Array.isArray(q.keywords_to_match)
      ? q.keywords_to_match.map((k) => String(k).toLowerCase().trim()).filter(Boolean)
      : [];
    if (keywordHints.length > 0) {
      const matchedCount = keywordHints.filter((k) => userLower.includes(k)).length;
      const requiredMatches = keywordHints.length <= 2 ? keywordHints.length : Math.ceil(keywordHints.length * 0.6);
      isCorrect = matchedCount >= requiredMatches;
    } else {
      const correctLower = (q.correct_answer || "").toLowerCase().trim();
      isCorrect = userLower === correctLower || correctLower.includes(userLower) || userLower.includes(correctLower);
    }
  }

  function optionStyle(opt) {
    if (!revealed) return S.qOption;
    if (opt.is_correct) return { ...S.qOption, ...S.qOptionCorrect };
    if (opt.label === selected) return { ...S.qOption, ...S.qOptionWrong };
    return { ...S.qOption, opacity: 0.5 };
  }

  // Single grading path for every question type — always asks the backend.
  async function gradeAnswer(payload, selectedValue) {
    if (checking || revealed) return;
    setSelected(selectedValue); // immediate UI feedback (highlight + disable)
    setChecking(true);
    try {
      // In adaptive mode, session_id routes the result back to the RL agent.
      const body = sessionId ? { ...payload, session_id: sessionId } : payload;
      const data = await jsonFetch(
        "/questions/check",
        { method: "POST", body: JSON.stringify(body) },
        QUESTION_API_BASE
      );
      setResult(data); // { is_correct, method, score, correct_answer }
    } catch {
      setResult(null); // backend unreachable -> local fallback grades it
    } finally {
      setChecking(false);
    }
  }

  function handleMCQClick(opt) {
    gradeAnswer(
      {
        question_type: "mcq",
        user_answer: opt.label,
        correct_answer: q.correct_answer || "",
        options: q.options,
      },
      opt.label
    );
  }

  function handleTrueFalseClick(value) {
    gradeAnswer(
      { question_type: "true_false", user_answer: value, correct_answer: q.correct_answer || "" },
      value
    );
  }

  function handleShortAnswerSubmit() {
    const answer = shortAnswerText.trim();
    if (!answer || checking) return;
    gradeAnswer(
      {
        question_type: "short_answer",
        user_answer: answer,
        correct_answer: q.correct_answer || "",
        keywords_to_match: q.keywords_to_match || null,
      },
      "submitted"
    );
  }

  return (
    <div style={S.qCard}>
      {/* LEFT SIDE - QUESTION */}
      <div style={S.qCardLeft}>
        <div style={S.qMetaTop}>
          <div style={{ display: "flex", gap: 6, alignItems: "center", minWidth: 0 }}>
            <span style={S.qTag}>{item.questionType.replace("_", " ")}</span>
            <span style={S.qTagDifficulty}>{item.difficulty || q.difficulty || "understand"}</span>
          </div>
          <span style={S.qMetaSmall}>{item.topic}</span>
        </div>

        <div style={S.qText}>{q.question_text}</div>

        {isMCQ && (
          <div style={{ marginTop: 12, display: "grid", gap: 6 }}>
            {q.options.map((opt) => (
              <button
                key={opt.label}
                disabled={revealed}
                onClick={() => handleMCQClick(opt)}
                style={{
                  ...optionStyle(opt),
                  textAlign: "left",
                  cursor: revealed ? "default" : "pointer",
                  border: selected === opt.label && !opt.is_correct
                    ? "1px solid #fca5a5"
                    : optionStyle(opt).border,
                }}
              >
                <b>{opt.label}.</b> {opt.text}
              </button>
            ))}
          </div>
        )}

        {isTrueFalse && (
          <div style={{ marginTop: 12, display: "flex", gap: 8 }}>
            <button
              disabled={revealed}
              onClick={() => handleTrueFalseClick("true")}
              style={{
                flex: 1,
                padding: "10px 14px",
                borderRadius: 6,
                border: "1px solid #d6d6de",
                background: selected === "true" ? (revealed ? (isCorrect ? "#ecfdf5" : "#fff1f2") : "#e6e6ff") : "#fff",
                color: selected === "true" ? (revealed ? (isCorrect ? "#059669" : "#dc2626") : "#6c63ff") : "#333",
                fontWeight: selected === "true" ? 600 : 500,
                cursor: revealed ? "default" : "pointer",
                fontSize: 13,
              }}
            >
              True
            </button>
            <button
              disabled={revealed}
              onClick={() => handleTrueFalseClick("false")}
              style={{
                flex: 1,
                padding: "10px 14px",
                borderRadius: 6,
                border: "1px solid #d6d6de",
                background: selected === "false" ? (revealed ? (isCorrect ? "#ecfdf5" : "#fff1f2") : "#e6e6ff") : "#fff",
                color: selected === "false" ? (revealed ? (isCorrect ? "#059669" : "#dc2626") : "#6c63ff") : "#333",
                fontWeight: selected === "false" ? 600 : 500,
                cursor: revealed ? "default" : "pointer",
                fontSize: 13,
              }}
            >
              False
            </button>
          </div>
        )}

        {isShortAnswer && (
          <div style={{ marginTop: 12 }}>
            <textarea
              disabled={revealed}
              value={shortAnswerText}
              onChange={(e) => setShortAnswerText(e.target.value)}
              placeholder="Enter your answer..."
              style={{
                width: "100%",
                minHeight: 70,
                padding: 10,
                borderRadius: 6,
                border: "1px solid #d6d6de",
                fontSize: 12,
                fontFamily: "inherit",
                resize: "none",
                cursor: revealed ? "default" : "text",
                opacity: revealed ? 0.6 : 1,
              }}
            />
            <button
              disabled={revealed || checking || !shortAnswerText.trim()}
              onClick={handleShortAnswerSubmit}
              style={{
                ...S.generateBtn,
                marginTop: 8,
                width: "100%",
                opacity: revealed || checking || !shortAnswerText.trim() ? 0.5 : 1,
                cursor: revealed || checking || !shortAnswerText.trim() ? "default" : "pointer",
              }}
            >
              {checking ? "Checking…" : "Submit answer"}
            </button>
          </div>
        )}

        <div style={S.qMetaBottom}>
          {item.difficulty} · {item.chunksUsed} chunk{item.chunksUsed === 1 ? "" : "s"}
        </div>
      </div>

      {/* RIGHT SIDE - ANSWER REVEAL */}
      {revealed && (
        <div style={{ ...S.qCardRight, opacity: revealed ? 1 : 0, transform: revealed ? "translateX(0)" : "translateX(20px)" }}>
          {checking && !result ? (
            <div style={{ ...S.resultBadge, background: "#f5f5f7", borderColor: "#d6d6de" }}>
              <div style={{ fontSize: 13, fontWeight: 600, color: "#6c63ff" }}>Checking…</div>
            </div>
          ) : (
            <div style={{ ...S.resultBadge, background: isCorrect ? "#ecfdf5" : "#fff1f2", borderColor: isCorrect ? "#a7f3d0" : "#fca5a5" }}>
              <span style={{ fontSize: 28, marginBottom: 4 }}>{isCorrect ? "✓" : "✗"}</span>
              <div style={{ fontSize: 14, fontWeight: 700, color: isCorrect ? "#059669" : "#dc2626" }}>
                {isCorrect ? "Correct!" : "Incorrect"}
              </div>
            </div>
          )}

          {result && (
            <div style={{ marginTop: 10, fontSize: 12, color: "#6b7280", display: "flex", alignItems: "center", gap: 6 }}>
              {result.score != null && (
                <b style={{ color: isCorrect ? "#059669" : "#dc2626" }}>
                  {Math.round(result.score * 100)}% match
                </b>
              )}
              <span style={{ opacity: 0.7 }}>
                {result.score != null ? "· " : ""}graded by {result.method === "semantic" ? "meaning" : result.method} (server)
              </span>
            </div>
          )}

          {isShortAnswer && (
            <div style={{ marginTop: 12 }}>
              <div style={S.qLabel}>Your answer</div>
              <div style={{ ...S.qAnswer, background: "#f5f5f7", wordBreak: "break-word" }}>{shortAnswerText}</div>
            </div>
          )}

          <div style={{ marginTop: 16 }}>
            <div style={S.qLabel}>Correct answer</div>
            <div style={S.qAnswer}>{q.correct_answer}</div>
          </div>

          <div style={{ marginTop: 14 }}>
            <div style={S.qLabel}>Explanation</div>
            <div style={S.qExplain}>{q.explanation}</div>
          </div>

          {isShortAnswer && Array.isArray(q.keywords_to_match) && q.keywords_to_match.length > 0 && (
            <div style={{ marginTop: 12 }}>
              <div style={S.qLabel}>Expected key points</div>
              <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                {q.keywords_to_match.map((kw, idx) => (
                  <span key={`${kw}-${idx}`} style={S.qTagDifficulty}>
                    {kw}
                  </span>
                ))}
              </div>
            </div>
          )}

          <div style={{ fontSize: 11, color: "#999", marginTop: 12, textAlign: "center" }}>
            Use arrows or dots below to continue
          </div>
        </div>
      )}
    </div>
  );
}

const S = {
  app: { display: "flex", height: "100vh", width: "100vw", overflow: "hidden", minWidth: 0 },

  sidebar: {
    width: "clamp(200px, 22vw, 280px)",
    flexShrink: 0,
    background: "#ffffff",
    borderRight: "1px solid #e6e6ec",
    padding: "18px 16px",
    display: "flex",
    flexDirection: "column",
    overflowY: "auto",
    minHeight: 0,
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

  main: { flex: 1, minWidth: 0, display: "flex", flexDirection: "column", background: "#f7f7f8", overflow: "hidden" },

  header: {
    height: 52,
    padding: "0 22px",
    borderBottom: "1px solid #e6e6ec",
    background: "white",
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
  },

  tabBar: {
    display: "flex",
    gap: 0,
    background: "#f7f7f8",
    borderBottom: "1px solid #e6e6ec",
    height: 44,
    paddingX: 0,
  },

  tabBtn: {
    flex: 1,
    border: "none",
    background: "transparent",
    borderBottom: "1px solid #e6e6ec",
    fontSize: 13,
    fontWeight: 600,
    color: "#555",
    cursor: "pointer",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    transition: "all 0.2s",
  },

  contentShell: {
    flex: 1,
    minHeight: 0,
    display: "flex",
    flexWrap: "nowrap",
    overflow: "hidden",
  },

  carouselContainer: {
    flex: 1,
    display: "flex",
    flexDirection: "column",
    minHeight: 0,
    position: "relative",
    background: "#f7f7f8",
  },

  carouselEmpty: {
    flex: 1,
    color: "#777",
  },

  carouselViewport: {
    flex: 1,
    minHeight: 0,
    overflow: "hidden",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
  },

  carouselSlide: {
    display: "flex",
    width: "100%",
    transition: "transform 0.3s ease-out",
  },

  carouselSlideItem: {
    flex: "0 0 100%",
    minWidth: 0,
    minHeight: 0,
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    overflow: "auto",
    padding: "20px 20px",
  },

  carouselNav: {
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    gap: 20,
    padding: "16px 20px",
    background: "white",
    borderTop: "1px solid #e6e6ec",
  },

  arrowBtn: {
    border: "none",
    background: "transparent",
    fontSize: 18,
    fontWeight: 600,
    color: "#555",
    cursor: "pointer",
    padding: "8px 12px",
    transition: "opacity 0.2s",
  },

  dotContainer: {
    display: "flex",
    gap: 6,
    alignItems: "center",
  },

  dot: {
    width: 8,
    height: 8,
    borderRadius: "50%",
    border: "none",
    cursor: "pointer",
    background: "#d9d9e3",
    transition: "background 0.2s",
  },

  chatColumn: {
    flex: "1 1 0",
    minWidth: 0,
    minHeight: 0,
    display: "flex",
    flexDirection: "column",
    overflow: "hidden",
  },

  messages: {
    flex: 1,
    overflowY: "auto",
    padding: 24,
    display: "flex",
    flexDirection: "column",
    gap: 16,
  },

  empty: { margin: "auto", textAlign: "center", padding: 40, color: "#777" },

  chip: {
    padding: "7px 14px",
    border: "1px solid #d6d6de",
    borderRadius: 20,
    background: "white",
    fontSize: 12,
    cursor: "pointer",
    color: "#555",
  },

  msg: { display: "flex", gap: 10, maxWidth: 780 },

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
    fontSize: 12,
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

  answerBox: {
    fontSize: 15,
    fontWeight: 600,
    color: "#111827",
    padding: "8px 10px",
    background: "#ecfdf5",
    border: "1px solid #a7f3d0",
    borderRadius: 6,
    fontFamily: "ui-monospace,SFMono-Regular,Menlo,Monaco,monospace",
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

  specGrid: { display: "grid", gap: 4, marginTop: 2 },

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
    height: 34,
    borderRadius: 8,
    border: "none",
    background: "linear-gradient(135deg,#6c63ff,#a78bfa)",
    color: "white",
    cursor: "pointer",
    fontSize: 13,
    flexShrink: 0,
    padding: "0 12px",
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
  },

  questionControls: {
    padding: "8px 10px",
    borderBottom: "1px solid #ececf1",
    display: "grid",
    gap: 4,
    background: "#ffffff",
    flexShrink: 0,
  },

  qLabel: {
    fontSize: 8,
    color: "#6b7280",
    fontWeight: 700,
    letterSpacing: 0.6,
    textTransform: "uppercase",
    marginTop: 1,
  },

  qInput: {
    border: "1px solid #d9d9e3",
    borderRadius: 4,
    padding: "5px 7px",
    fontSize: 11,
    outline: "none",
    background: "#f9f9fd",
  },

  generateBtn: {
    marginTop: 1,
    border: "none",
    borderRadius: 4,
    background: "#111827",
    color: "white",
    padding: "5px 8px",
    fontSize: 11,
    fontWeight: 600,
    cursor: "pointer",
  },

  qHint: { fontSize: 9, color: "#777", lineHeight: 1.3, marginTop: 1 },

  qEmpty: {
    fontSize: 12,
    color: "#8b8b95",
    border: "1px dashed #d9d9e3",
    borderRadius: 8,
    padding: "12px 10px",
    background: "#fff",
  },

  qCard: {
    background: "white",
    border: "1px solid #e6e6ec",
    borderRadius: 10,
    display: "flex",
    flexDirection: "row",
    gap: 20,
    width: "100%",
    maxWidth: "900px",
    boxShadow: "0 2px 8px rgba(0,0,0,0.06)",
    overflow: "hidden",
  },

  qCardLeft: {
    flex: "0 0 50%",
    minWidth: 0,
    display: "flex",
    flexDirection: "column",
    padding: 18,
    overflowY: "auto",
    paddingRight: 12,
  },

  qCardRight: {
    flex: "0 0 50%",
    minWidth: 0,
    display: "flex",
    flexDirection: "column",
    padding: 18,
    paddingLeft: 12,
    overflowY: "auto",
    background: "#fafbff",
    borderLeft: "1px solid #e6e6ec",
    transition: "all 0.4s ease-out",
  },

  resultBadge: {
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    justifyContent: "center",
    padding: 20,
    borderRadius: 10,
    border: "2px solid",
  },

  qMetaTop: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    gap: 6,
    marginBottom: 6,
  },

  qTag: {
    fontSize: 9,
    fontWeight: 700,
    textTransform: "uppercase",
    color: "#4338ca",
    background: "#e0e7ff",
    border: "1px solid #c7d2fe",
    borderRadius: 999,
    padding: "1px 6px",
  },

  qTagDifficulty: {
    fontSize: 9,
    fontWeight: 700,
    textTransform: "uppercase",
    color: "#0f766e",
    background: "#ccfbf1",
    border: "1px solid #99f6e4",
    borderRadius: 999,
    padding: "1px 6px",
  },

  qMetaSmall: {
    fontSize: 10,
    color: "#6b7280",
    overflow: "hidden",
    textOverflow: "ellipsis",
    whiteSpace: "nowrap",
  },

  qText: { fontSize: 13, fontWeight: 600, color: "#111827", lineHeight: 1.5 },

  qOption: {
    display: "flex",
    gap: 6,
    fontSize: 12,
    color: "#1f2937",
    background: "#f9fafb",
    border: "1px solid #e5e7eb",
    borderRadius: 6,
    padding: "6px 8px",
    width: "100%",
    fontFamily: "inherit",
  },

  qOptionCorrect: {
    background: "#ecfdf5",
    border: "1px solid #a7f3d0",
  },

  qOptionWrong: {
    background: "#fff1f2",
    border: "1px solid #fca5a5",
  },

  qAnswer: {
    fontSize: 12,
    color: "#065f46",
    background: "#ecfdf5",
    border: "1px solid #a7f3d0",
    borderRadius: 6,
    padding: "6px 8px",
    lineHeight: 1.5,
  },

  qExplain: {
    fontSize: 11,
    color: "#374151",
    lineHeight: 1.5,
    whiteSpace: "pre-wrap",
  },

  qMetaBottom: {
    marginTop: "auto",
    paddingTop: 10,
    fontSize: 10,
    color: "#6b7280",
    borderTop: "1px solid #f0f0f0",
  },
};
