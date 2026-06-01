import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";

const QUESTION_API_BASE = import.meta.env.VITE_QUESTION_API_BASE || "http://127.0.0.1:8002/api/v1";

async function jsonFetch(path, opts = {}, baseUrl = QUESTION_API_BASE) {
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

export default function QuestionStudioPage() {
  const navigate = useNavigate();

  const [selectedFileIds, setSelectedFileIds] = useState(() => {
    try {
      return JSON.parse(localStorage.getItem("baylearn:selected_files") || "[]");
    } catch {
      return [];
    }
  });

  const [questionType, setQuestionType] = useState("mcq");
  const [toast, setToast] = useState(null);

  // --- ADAPTIVE MODE STATE ---
  const ADAPTIVE_SESSION = "studio_session";
  const adaptiveVersionRef = React.useRef(0);
  const [adaptiveItem, setAdaptiveItem] = useState(null);

  // Adaptive mode: register the source files for the session whenever the
  // selection or type changes.
  useEffect(() => {
    if (selectedFileIds.length === 0) return;
    jsonFetch(
      `/questions/adaptive/${ADAPTIVE_SESSION}/config`,
      { method: "POST", body: JSON.stringify({ file_ids: selectedFileIds.join(","), question_type: questionType }) },
      QUESTION_API_BASE
    ).catch(() => {});
  }, [selectedFileIds, questionType]);

  // Adaptive mode: poll for the question the RL agent generated and display it.
  useEffect(() => {
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
  }, []);
  // ---------------------------

  function showToast(msg, type = "info") {
    setToast({ msg, type });
    setTimeout(() => setToast(null), 3500);
  }

  return (
    <div style={S.page}>
      <header style={S.header}>
        <button onClick={() => navigate("/home")} style={S.backBtn}>
          ← Back to Home
        </button>
        <div style={{ fontWeight: 700, fontSize: 16, color: "#111827" }}>Question Studio</div>
        <div style={{ width: 100 }}></div> {/* Spacer for centering */}
      </header>

      <div style={S.body}>
        {/* Settings Sidebar */}
        <aside style={S.sidebar}>
          <div style={S.sideHeader}>ADAPTIVE MODE (RL)</div>
          <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
            <div style={{ fontSize: 13, color: "#4b5563", lineHeight: 1.5 }}>
              The RL agent automatically chooses the topic and difficulty to optimise your learning.
            </div>

            <div>
              <label style={S.qLabel}>Question type</label>
              <select
                style={S.qInput}
                value={questionType}
                onChange={(e) => setQuestionType(e.target.value)}
              >
                <option value="mcq">Multiple Choice</option>
                <option value="true_false">True / False</option>
                <option value="short_answer">Short Answer</option>
              </select>
            </div>

            <div
              style={{
                ...S.generateBtn,
                background: "#eef0ff",
                color: "#4b46c4",
                textAlign: "center",
                cursor: "default",
                opacity: 1,
              }}
            >
              {selectedFileIds.length === 0
                ? "Select files first"
                : adaptiveItem
                ? "Answer below — agent is waiting"
                : "Waiting for agent..."}
            </div>

            {selectedFileIds.length === 0 && (
              <div style={{ fontSize: 11, color: "#dc2626", marginTop: -8 }}>
                No files selected. Go back to Home and select files.
              </div>
            )}
          </div>
        </aside>

        {/* Main Content */}
        <main style={S.main}>
          {!adaptiveItem ? (
            <div style={S.emptyState}>
              <div style={{ fontSize: 16, fontWeight: 600, color: "#555" }}>
                {selectedFileIds.length === 0 ? "No sources selected" : "Waiting for the RL agent…"}
              </div>
              <div style={{ fontSize: 13, color: "#999", marginTop: 4 }}>
                {selectedFileIds.length === 0 ? "Select course materials on the Home page to begin." : "The next question will appear here automatically."}
              </div>
            </div>
          ) : (
            <div style={S.carouselContainer}>
              <div style={S.carouselViewport}>
                <div style={{ ...S.carouselSlide, transform: "translateX(0)" }}>
                  <div style={S.carouselSlideItem}>
                    <QuestionCard 
                      key={adaptiveItem.id} 
                      item={adaptiveItem} 
                      sessionId={ADAPTIVE_SESSION} 
                    />
                  </div>
                </div>
              </div>
            </div>
          )}
        </main>
      </div>

      {toast && (
        <div
          style={{
            ...S.toast,
            borderColor: toast.type === "error" ? "#f87171" : toast.type === "success" ? "#4ade80" : "#d6d6de",
            color: toast.type === "error" ? "#c53030" : toast.type === "success" ? "#166534" : "#1a1a1a",
          }}
        >
          {toast.msg}
        </div>
      )}
    </div>
  );
}

// ============================================================================
// QUESTION CARD COMPONENT
// ============================================================================

function QuestionCard({ item, sessionId }) {
  const q = item.question;
  const [selected, setSelected] = useState(null);
  const [shortAnswerText, setShortAnswerText] = useState("");
  const [result, setResult] = useState(null);
  const [checking, setChecking] = useState(false);
  const revealed = selected !== null;
  const isMCQ = item.questionType === "mcq" && Array.isArray(q.options) && q.options.length > 0;
  const isTrueFalse = item.questionType === "true_false";
  const isShortAnswer = item.questionType === "short_answer";

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

  async function gradeAnswer(payload, selectedValue) {
    if (checking || revealed) return;
    setSelected(selectedValue);
    setChecking(true);
    try {
      const body = sessionId ? { ...payload, session_id: sessionId } : payload;
      const data = await jsonFetch("/questions/check", {
        method: "POST",
        body: JSON.stringify(body),
      });
      setResult(data);
    } catch {
      setResult(null);
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
                  border: selected === opt.label && !opt.is_correct ? "1px solid #fca5a5" : optionStyle(opt).border,
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

// ============================================================================
// STYLES
// ============================================================================
const S = {
  page: { display: "flex", flexDirection: "column", height: "100vh", background: "#f7f7f8", fontFamily: "-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif" },
  header: { height: 56, background: "white", borderBottom: "1px solid #e6e6ec", display: "flex", alignItems: "center", justifyContent: "space-between", padding: "0 22px", flexShrink: 0 },
  backBtn: { background: "none", border: "none", color: "#6c63ff", fontSize: 13, fontWeight: 600, cursor: "pointer", fontFamily: "inherit" },
  body: { display: "flex", flex: 1, minHeight: 0 },
  sidebar: { width: 300, background: "white", borderRight: "1px solid #e6e6ec", padding: "24px 20px", display: "flex", flexDirection: "column", overflowY: "auto" },
  sideHeader: { fontSize: 11, fontWeight: 700, letterSpacing: 1.2, color: "#888", marginBottom: 20 },
  qLabel: { fontSize: 11, fontWeight: 700, letterSpacing: 0.6, color: "#6b7280", textTransform: "uppercase", marginBottom: 6, display: "block" },
  qInput: { width: "100%", padding: "10px 12px", border: "1px solid #d6d6de", borderRadius: 8, fontSize: 13, outline: "none", background: "#fafafd", fontFamily: "inherit", color: "#111827", boxSizing: "border-box" },
  generateBtn: { width: "100%", padding: "12px", background: "linear-gradient(135deg,#059669,#34d399)", color: "white", border: "none", borderRadius: 8, fontWeight: 600, fontSize: 14, cursor: "pointer", fontFamily: "inherit", transition: "transform 0.1s" },
  main: { flex: 1, display: "flex", flexDirection: "column", minWidth: 0, position: "relative" },
  emptyState: { flex: 1, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center" },
  carouselContainer: { flex: 1, display: "flex", flexDirection: "column", minHeight: 0, padding: 24 },
  carouselViewport: { flex: 1, minHeight: 0, overflow: "hidden", display: "flex", alignItems: "center", justifyContent: "center" },
  carouselSlide: { display: "flex", width: "100%", transition: "transform 0.3s ease-out" },
  carouselSlideItem: { flex: "0 0 100%", minWidth: 0, minHeight: 0, display: "flex", alignItems: "center", justifyContent: "center", overflow: "auto", padding: "20px" },
  carouselNav: { display: "flex", alignItems: "center", justifyContent: "center", gap: 20, padding: "16px 20px" },
  arrowBtn: { border: "none", background: "white", borderRadius: "50%", width: 36, height: 36, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 16, fontWeight: 600, color: "#555", cursor: "pointer", boxShadow: "0 2px 8px rgba(0,0,0,0.1)" },
  dotContainer: { display: "flex", gap: 8 },
  dot: { width: 8, height: 8, borderRadius: "50%" },
  qCard: { display: "flex", width: "100%", maxWidth: 840, minHeight: 400, background: "white", borderRadius: 16, border: "1px solid #e6e6ec", boxShadow: "0 10px 30px rgba(0,0,0,0.06)", overflow: "hidden" },
  qCardLeft: { flex: 1, padding: 32, display: "flex", flexDirection: "column" },
  qCardRight: { flex: 1, padding: 32, background: "#fafafd", borderLeft: "1px solid #e6e6ec", display: "flex", flexDirection: "column", transition: "all 0.3s ease" },
  qMetaTop: { display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 },
  qTag: { padding: "4px 8px", background: "#f0eeff", color: "#6c63ff", borderRadius: 6, fontSize: 11, fontWeight: 700, textTransform: "uppercase", letterSpacing: 0.5 },
  qTagDifficulty: { padding: "4px 8px", background: "#f3f4f6", color: "#4b5563", borderRadius: 6, fontSize: 11, fontWeight: 600, textTransform: "uppercase", letterSpacing: 0.5 },
  qMetaSmall: { fontSize: 11, color: "#9ca3af", fontWeight: 500, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", maxWidth: 140, textAlign: "right" },
  qText: { fontSize: 17, fontWeight: 600, color: "#111827", lineHeight: 1.5, flex: 1, marginBottom: 24, whiteSpace: "pre-wrap" },
  qOption: { padding: "14px 16px", background: "white", border: "1px solid #d6d6de", borderRadius: 8, fontSize: 14, color: "#374151", transition: "all 0.15s", lineHeight: 1.4 },
  qOptionCorrect: { background: "#ecfdf5", borderColor: "#34d399", color: "#065f46" },
  qOptionWrong: { background: "#fff1f2", borderColor: "#f87171", color: "#991b1b" },
  qMetaBottom: { marginTop: "auto", paddingTop: 20, fontSize: 11, color: "#9ca3af", borderTop: "1px solid #f3f4f6" },
  resultBadge: { display: "flex", flexDirection: "column", alignItems: "center", padding: "16px 20px", borderRadius: 12, border: "2px solid" },
  qAnswer: { fontSize: 14, color: "#374151", fontWeight: 600, padding: "10px 14px", background: "#f3f4f6", borderRadius: 8, marginTop: 4 },
  qExplain: { fontSize: 13, color: "#4b5563", lineHeight: 1.6, padding: "12px 14px", background: "white", border: "1px solid #e6e6ec", borderRadius: 8, marginTop: 4, whiteSpace: "pre-wrap" },
  toast: { position: "fixed", bottom: 20, right: 20, padding: "10px 16px", background: "white", border: "1px solid #d6d6de", borderRadius: 10, fontSize: 13, boxShadow: "0 4px 12px rgba(0,0,0,0.08)", zIndex: 300, maxWidth: 320 },
};
