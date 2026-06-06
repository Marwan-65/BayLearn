import { useState, useEffect, useRef } from "react";
import { useNavigate } from "react-router-dom";

// Adaptive backend — session/status, session/results
const ADAPTIVE_API_BASE = import.meta.env.VITE_ADAPTIVE_API_BASE || "http://127.0.0.1:8002";
// Question generator backend — adaptive question polling, grading
const QUESTION_API_BASE = import.meta.env.VITE_QUESTION_API_BASE || "http://127.0.0.1:8001/api/v1";

// ── Fetch helpers ────────────────────────────────────────────────────────────

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
    const err = new Error(data.signal || data.detail || data.error || `HTTP ${res.status}`);
    err.status = res.status;
    throw err;
  }
  return data;
}

async function apiFetch(path, opts = {}) {
  return jsonFetch(path, opts, ADAPTIVE_API_BASE);
}

// ── Main page ────────────────────────────────────────────────────────────────

export default function QuestionStudioPage() {
  const navigate = useNavigate();

  // Read what HomePage stored in localStorage
  const sessionId    = localStorage.getItem("baylearn:session_id")    || null;
  const questionType = localStorage.getItem("baylearn:question_type")  || "mcq";

  const [selectedFileIds] = useState(() => {
    try { return JSON.parse(localStorage.getItem("baylearn:selected_files") || "[]"); }
    catch { return []; }
  });

  const [toast, setToast] = useState(null);

  // ── Adaptive question state ──────────────────────────────────────────────
  const adaptiveVersionRef = useRef(0);
  const [adaptiveItem, setAdaptiveItem] = useState(null);

  // ── Session status polling state ─────────────────────────────────────────
  const [sessionFinished,  setSessionFinished]  = useState(false);
  const [sessionResults,   setSessionResults]   = useState(null);
  const [showResults,      setShowResults]      = useState(false);
  const [stepsCount,       setStepsCount]       = useState(0);
  const [terminating,      setTerminating]      = useState(false);
  const statusPollRef = useRef(null);

  function showToast(msg, type = "info") {
    setToast({ msg, type });
    setTimeout(() => setToast(null), 3500);
  }

  async function terminateSession() {
    if (!sessionId || terminating || sessionFinished) return;
    setTerminating(true);
    try {
      await apiFetch("/session/terminate", {
        method: "POST",
        body: JSON.stringify({ session_id: sessionId }),
      });
      showToast("Session ending — saving your progress…", "info");
    } catch (e) {
      showToast(e.message || "Could not terminate session.", "error");
      setTerminating(false);
    }
  }

  // ── Poll /session/status every 5 s ──────────────────────────────────────
  useEffect(() => {
    if (!sessionId) return;

    async function pollStatus() {
      try {
        const data = await apiFetch(`/session/status?session_id=${sessionId}`);
        setStepsCount(data.steps_so_far ?? 0);

        if (data.finished && !sessionFinished) {
          setSessionFinished(true);
          clearInterval(statusPollRef.current);
          // Fetch rich results
          try {
            const results = await apiFetch(`/session/results?session_id=${sessionId}`);
            setSessionResults(results);
          } catch {
            // fallback: show whatever came back in status
            setSessionResults(data.results ?? null);
          }
          setShowResults(true);
        }
      } catch {
        /* backend temporarily unreachable — keep polling */
      }
    }

    pollStatus(); // immediate first check
    statusPollRef.current = setInterval(pollStatus, 5000);
    return () => clearInterval(statusPollRef.current);
  }, [sessionId]);

  // ── Poll adaptive question ──────────────────────────────────────────────
  useEffect(() => {
    if (!sessionId) return;
    let cancelled = false;
    let timerId;

    async function poll() {
      if (cancelled) return;
      try {
        const data = await jsonFetch(
          `/questions/adaptive/${sessionId}/current`,
          {},
          QUESTION_API_BASE
        );
        if (!cancelled && data?.question && data.version > adaptiveVersionRef.current) {
          adaptiveVersionRef.current = data.version;
          const card = data.question;
          setAdaptiveItem({
            id:           data.version,
            question:     card.question,
            questionType: card.question_type || card.questionType || card.question?.question_type,
            topic:        card.topic,
            difficulty:   card.difficulty,
            chunksUsed:   card.chunks_used || card.chunksUsed,
          });
        }
      } catch {
        /* QG unreachable — keep polling */
      }
      if (!cancelled) {
        timerId = setTimeout(poll, 1500);
      }
    }

    poll();
    return () => { cancelled = true; clearTimeout(timerId); };
  }, [sessionId]);

  // ── Derived ──────────────────────────────────────────────────────────────
  const questionTypeLabel = {
    mcq:          "Multiple Choice",
    true_false:   "True / False",
    short_answer: "Short Answer",
  }[questionType] ?? questionType;

  return (
    <div style={S.page}>
      {/* ── Header ─────────────────────────────────────────────── */}
      <header style={S.header}>
        <button onClick={() => navigate("/home")} style={S.backBtn}>
          ← Back to Home
        </button>
        <div style={{ fontWeight: 700, fontSize: 16, color: "#111827" }}>Question Studio</div>
        <div style={{ width: 100 }} />
      </header>

      <div style={S.body}>
        {/* ── Settings sidebar ─────────────────────────────────── */}
        <aside style={S.sidebar}>
          <div style={S.sideHeader}>ADAPTIVE MODE (RL)</div>
          <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
            <div style={{ fontSize: 13, color: "#4b5563", lineHeight: 1.5 }}>
              The RL agent automatically chooses the topic and difficulty to optimise your learning.
            </div>

            {/* Session info */}
            {sessionId && (
              <div style={{ padding: "10px 12px", background: "#f0fdf4", border: "1px solid #bbf7d0", borderRadius: 8 }}>
                <div style={{ fontSize: 11, fontWeight: 700, color: "#059669", letterSpacing: 0.5, marginBottom: 4 }}>
                  SESSION ACTIVE
                </div>
                <div style={{ fontSize: 12, color: "#065f46" }}>
                  Type: <b>{questionTypeLabel}</b>
                </div>
                <div style={{ fontSize: 12, color: "#065f46", marginTop: 2 }}>
                  Questions answered: <b>{stepsCount}</b>
                </div>
                {sessionFinished && (
                  <div style={{ marginTop: 6, fontSize: 12, color: "#059669", fontWeight: 600 }}>
                    ✓ Session complete
                  </div>
                )}
              </div>
            )}

            {/* End Session button — only while session is running */}
            {sessionId && !sessionFinished && (
              <button
                onClick={terminateSession}
                disabled={terminating}
                style={{
                  ...S.generateBtn,
                  background: terminating ? "#f3f4f6" : "linear-gradient(135deg,#dc2626,#f87171)",
                  color:      terminating ? "#9ca3af" : "white",
                  cursor:     terminating ? "default" : "pointer",
                  opacity:    1,
                }}
              >
                {terminating ? "Ending session…" : "End Session"}
              </button>
            )}

            {/* Status pill */}
            <div style={{
              ...S.generateBtn,
              background: sessionFinished ? "#ecfdf5" : "#eef0ff",
              color:      sessionFinished ? "#059669"  : "#4b46c4",
              textAlign: "center",
              cursor: "default",
              opacity: 1,
            }}>
              {!sessionId
                ? "No session — go back to Home"
                : sessionFinished
                ? "Session finished! 🎉"
                : adaptiveItem
                ? "Answer below — agent is waiting"
                : "Waiting for agent…"}
            </div>

            {/* Results button when finished */}
            {sessionFinished && (
              <button
                onClick={() => setShowResults(true)}
                style={{ ...S.generateBtn, background: "linear-gradient(135deg,#059669,#34d399)", cursor: "pointer" }}
              >
                View Results →
              </button>
            )}

            {!sessionId && (
              <div style={{ fontSize: 11, color: "#dc2626", marginTop: -8 }}>
                No session found. Go back to Home and launch Question Studio again.
              </div>
            )}
          </div>
        </aside>

        {/* ── Main ──────────────────────────────────────────────── */}
        <main style={S.main}>
          {!adaptiveItem ? (
            <div style={S.emptyState}>
              <div style={{ fontSize: 40, marginBottom: 12 }}>
                {sessionFinished ? "🎓" : "⏳"}
              </div>
              <div style={{ fontSize: 16, fontWeight: 600, color: "#555" }}>
                {!sessionId
                  ? "No sources selected"
                  : sessionFinished
                  ? "Session complete!"
                  : "Waiting for the RL agent…"}
              </div>
              <div style={{ fontSize: 13, color: "#999", marginTop: 4 }}>
                {!sessionId
                  ? "Select course materials on the Home page to begin."
                  : sessionFinished
                  ? "Check your results in the sidebar."
                  : "The next question will appear here automatically."}
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
                      sessionId={sessionId}
                      sessionFinished={sessionFinished}
                    />
                  </div>
                </div>
              </div>
            </div>
          )}
        </main>
      </div>

      {/* ── Results overlay ───────────────────────────────────── */}
      {showResults && sessionResults && (
        <ResultsOverlay results={sessionResults} onClose={() => setShowResults(false)} onHome={() => navigate("/home")} />
      )}

      {toast && (
        <div style={{
          ...S.toast,
          borderColor: toast.type === "error" ? "#f87171" : toast.type === "success" ? "#4ade80" : "#d6d6de",
          color:       toast.type === "error" ? "#c53030" : toast.type === "success" ? "#166534" : "#1a1a1a",
        }}>
          {toast.msg}
        </div>
      )}
    </div>
  );
}

// ── Results Overlay ──────────────────────────────────────────────────────────

function ResultsOverlay({ results, onClose, onHome }) {
  const r = results;

  function pct(val) {
    return val != null ? `${Math.round(val * 100)}%` : "—";
  }

  function aprBar(val) {
    const w = val != null ? Math.min(Math.round(val * 100), 100) : 0;
    const color = w >= 85 ? "#059669" : w >= 70 ? "#16a34a" : w >= 55 ? "#d97706" : w >= 40 ? "#f59e0b" : "#dc2626";
    return (
      <div style={{ marginTop: 6, height: 8, background: "#e5e7eb", borderRadius: 99, overflow: "hidden" }}>
        <div style={{ width: `${w}%`, height: "100%", background: color, borderRadius: 99, transition: "width 0.6s ease" }} />
      </div>
    );
  }

  return (
    <div style={RS.overlay}>
      <div style={RS.card}>
        {/* Header */}
        <div style={RS.cardHeader}>
          <div style={{ fontSize: 32, marginBottom: 4 }}>
            {r.goal_met ? "🏆" : r.goal_achieved_pct >= 75 ? "🌟" : "📊"}
          </div>
          <div style={{ fontSize: 20, fontWeight: 800, color: "#111827" }}>Session Complete</div>
          <div style={{ fontSize: 13, color: "#6b7280", marginTop: 2 }}>Here's how you did</div>
        </div>

        <div style={RS.body}>
          {/* Progress summary message */}
          <div style={{
            ...RS.messageBanner,
            background: r.goal_met ? "#f0fdf4" : "#fefce8",
            borderColor: r.goal_met ? "#bbf7d0" : "#fde68a",
            color:       r.goal_met ? "#065f46" : "#92400e",
          }}>
            {r.progress_summary}
          </div>

          {/* Goal */}
          <div style={RS.section}>
            <div style={RS.sectionLabel}>GOAL</div>
            <div style={{ fontSize: 13, color: "#374151" }}>{r.goal_description}</div>
            <div style={{ marginTop: 10 }}>
              <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12, color: "#6b7280", marginBottom: 2 }}>
                <span>Goal progress</span>
                <span style={{ fontWeight: 700, color: r.goal_met ? "#059669" : "#d97706" }}>
                  {r.goal_achieved_pct}%
                </span>
              </div>
              <div style={{ height: 8, background: "#e5e7eb", borderRadius: 99, overflow: "hidden" }}>
                <div style={{
                  width: `${Math.min(r.goal_achieved_pct, 100)}%`,
                  height: "100%",
                  background: r.goal_met ? "#059669" : "#f59e0b",
                  borderRadius: 99,
                  transition: "width 0.6s ease",
                }} />
              </div>
            </div>
          </div>

          {/* Stats row */}
          <div style={RS.statsRow}>
            <div style={RS.stat}>
              <div style={RS.statVal}>{r.steps_taken ?? "—"}</div>
              <div style={RS.statLabel}>Questions</div>
            </div>
            <div style={RS.stat}>
              <div style={RS.statVal}>{r.concepts_mastered ?? 0}</div>
              <div style={RS.statLabel}>Concepts mastered</div>
            </div>
            <div style={RS.stat}>
              <div style={{ ...RS.statVal, color: "#6c63ff" }}>{r.level ?? "—"}</div>
              <div style={RS.statLabel}>Level</div>
            </div>
          </div>

          {/* APR improvement */}
          <div style={RS.section}>
            <div style={RS.sectionLabel}>KNOWLEDGE LEVEL</div>
            <div style={{ fontSize: 12, color: "#6b7280" }}>{r.level_message}</div>
            {aprBar(r.global_apr)}
            {r.actual_improvement_pct != null && (
              <div style={{ fontSize: 12, color: "#6b7280", marginTop: 6 }}>
                Improved by{" "}
                <b style={{ color: r.actual_improvement_pct > 0 ? "#059669" : "#dc2626" }}>
                  {r.actual_improvement_pct > 0 ? "+" : ""}{r.actual_improvement_pct}%
                </b>{" "}
                this session
              </div>
            )}
          </div>

          {/* Mastery message */}
          {r.mastery_message && (
            <div style={{ ...RS.messageBanner, background: "#eff6ff", borderColor: "#bfdbfe", color: "#1e40af" }}>
              🎓 {r.mastery_message}
            </div>
          )}

          {/* Concept insights */}
          {(r.strongest_concepts?.length > 0 || r.weakest_concepts?.length > 0) && (
            <div style={{ display: "flex", gap: 12 }}>
              {r.strongest_concepts?.length > 0 && (
                <div style={{ flex: 1 }}>
                  <div style={RS.sectionLabel}>STRONGEST</div>
                  {r.strongest_concepts.map(c => (
                    <div key={c.name} style={RS.conceptRow}>
                      <span style={{ flex: 1, fontSize: 12, color: "#374151", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{c.name}</span>
                      <span style={{ fontSize: 11, fontWeight: 700, color: "#059669", flexShrink: 0 }}>{Math.round(c.p_hard * 100)}%</span>
                    </div>
                  ))}
                </div>
              )}
              {r.weakest_concepts?.length > 0 && (
                <div style={{ flex: 1 }}>
                  <div style={RS.sectionLabel}>NEEDS WORK</div>
                  {r.weakest_concepts.map(c => (
                    <div key={c.name} style={RS.conceptRow}>
                      <span style={{ flex: 1, fontSize: 12, color: "#374151", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{c.name}</span>
                      <span style={{ fontSize: 11, fontWeight: 700, color: "#dc2626", flexShrink: 0 }}>{Math.round(c.p_hard * 100)}%</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Next step */}
          {r.next_step && (
            <div style={{ ...RS.messageBanner, background: "#faf5ff", borderColor: "#e9d5ff", color: "#6b21a8" }}>
              💡 {r.next_step}
            </div>
          )}
        </div>

        {/* Footer buttons */}
        <div style={RS.footer}>
          <button onClick={onClose} style={RS.ghostBtn}>Keep reviewing</button>
          <button onClick={onHome}  style={RS.primaryBtn}>Back to Home →</button>
        </div>
      </div>
    </div>
  );
}

// ── Question Card ────────────────────────────────────────────────────────────

function QuestionCard({ item, sessionId, sessionFinished }) {
  const q = item.question;
  const [selected,        setSelected]        = useState(null);
  const [shortAnswerText, setShortAnswerText] = useState("");
  const [result,          setResult]          = useState(null);
  const [checking,        setChecking]        = useState(false);
  const revealed     = selected !== null;
  const isMCQ        = item.questionType === "mcq"        && Array.isArray(q.options) && q.options.length > 0;
  const isTrueFalse  = item.questionType === "true_false";
  const isShortAnswer= item.questionType === "short_answer";

  let isCorrect = false;
  if (result) {
    isCorrect = result.is_correct;
  } else if (isMCQ) {
    isCorrect = q.options.find(o => o.label === selected)?.is_correct || false;
  } else if (isTrueFalse) {
    isCorrect = (q.correct_answer || "").toLowerCase() === (selected || "").toLowerCase();
  } else if (isShortAnswer) {
    const userLower    = shortAnswerText.toLowerCase().trim();
    const keywordHints = Array.isArray(q.keywords_to_match)
      ? q.keywords_to_match.map(k => String(k).toLowerCase().trim()).filter(Boolean)
      : [];
    if (keywordHints.length > 0) {
      const matched  = keywordHints.filter(k => userLower.includes(k)).length;
      const required = keywordHints.length <= 2 ? keywordHints.length : Math.ceil(keywordHints.length * 0.6);
      isCorrect = matched >= required;
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
      const data = await jsonFetch("/questions/check", { method: "POST", body: JSON.stringify(body) });
      setResult(data);
    } catch {
      setResult(null);
    } finally {
      setChecking(false);
    }
  }

  function handleMCQClick(opt) {
    gradeAnswer({
      question_type:  "mcq",
      user_answer:    opt.label,
      correct_answer: q.correct_answer || "",
      options:        q.options,
    }, opt.label);
  }

  function handleTrueFalseClick(value) {
    gradeAnswer({ question_type: "true_false", user_answer: value, correct_answer: q.correct_answer || "" }, value);
  }

  function handleShortAnswerSubmit() {
    const answer = shortAnswerText.trim();
    if (!answer || checking) return;
    gradeAnswer({
      question_type:    "short_answer",
      user_answer:      answer,
      correct_answer:   q.correct_answer || "",
      keywords_to_match: q.keywords_to_match || null,
    }, "submitted");
  }

  return (
    <div style={S.qCard}>
      <div style={S.qCardLeft}>
        <div style={S.qMetaTop}>
          <div style={{ display: "flex", gap: 6, alignItems: "center", minWidth: 0 }}>
            <span style={S.qTag}>{(item.questionType || "").replace("_", " ")}</span>
            <span style={S.qTagDifficulty}>{item.difficulty || q.difficulty || "understand"}</span>
          </div>
          <span style={S.qMetaSmall}>{item.topic}</span>
        </div>

        <div style={S.qText}>{q.question_text}</div>

        {isMCQ && (
          <div style={{ marginTop: 12, display: "grid", gap: 6 }}>
            {q.options.map(opt => (
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
            {["true", "false"].map(val => (
              <button
                key={val}
                disabled={revealed}
                onClick={() => handleTrueFalseClick(val)}
                style={{
                  flex: 1, padding: "10px 14px", borderRadius: 6,
                  border: "1px solid #d6d6de",
                  background: selected === val ? (revealed ? (isCorrect ? "#ecfdf5" : "#fff1f2") : "#e6e6ff") : "#fff",
                  color:      selected === val ? (revealed ? (isCorrect ? "#059669" : "#dc2626") : "#6c63ff") : "#333",
                  fontWeight: selected === val ? 600 : 500,
                  cursor: revealed ? "default" : "pointer", fontSize: 13,
                }}
              >
                {val.charAt(0).toUpperCase() + val.slice(1)}
              </button>
            ))}
          </div>
        )}

        {isShortAnswer && (
          <div style={{ marginTop: 12 }}>
            <textarea
              disabled={revealed}
              value={shortAnswerText}
              onChange={e => setShortAnswerText(e.target.value)}
              placeholder="Enter your answer..."
              style={{
                width: "100%", minHeight: 70, padding: 10, borderRadius: 6,
                border: "1px solid #d6d6de", fontSize: 12, fontFamily: "inherit",
                resize: "none", cursor: revealed ? "default" : "text", opacity: revealed ? 0.6 : 1,
              }}
            />
            <button
              disabled={revealed || checking || !shortAnswerText.trim()}
              onClick={handleShortAnswerSubmit}
              style={{
                ...S.generateBtn, marginTop: 8, width: "100%",
                opacity: revealed || checking || !shortAnswerText.trim() ? 0.5 : 1,
                cursor:  revealed || checking || !shortAnswerText.trim() ? "default" : "pointer",
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
                  <span key={`${kw}-${idx}`} style={S.qTagDifficulty}>{kw}</span>
                ))}
              </div>
            </div>
          )}

          {result && !sessionFinished && (
            <div style={{ marginTop: 24, display: "flex", alignItems: "center", gap: 10, color: "#92400e", fontSize: 14, fontWeight: 600, padding: "14px 16px", background: "#fefce8", border: "1px solid #fde68a", borderRadius: 10 }}>
              <span style={{ fontSize: 20 }}>⏳</span>
              Getting your next question ready...
            </div>
          )}

          {result && sessionFinished && (
            <div style={{ marginTop: 24, display: "flex", alignItems: "center", gap: 10, color: "#065f46", fontSize: 14, fontWeight: 600, padding: "14px 16px", background: "#f0fdf4", border: "1px solid #bbf7d0", borderRadius: 10 }}>
              <span style={{ fontSize: 20 }}>🎓</span>
              Session complete! Check your results in the sidebar.
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ── Styles ───────────────────────────────────────────────────────────────────
const S = {
  page:            { display: "flex", flexDirection: "column", height: "100vh", background: "#f7f7f8", fontFamily: "-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif" },
  header:          { height: 56, background: "white", borderBottom: "1px solid #e6e6ec", display: "flex", alignItems: "center", justifyContent: "space-between", padding: "0 22px", flexShrink: 0 },
  backBtn:         { background: "none", border: "none", color: "#6c63ff", fontSize: 13, fontWeight: 600, cursor: "pointer", fontFamily: "inherit" },
  body:            { display: "flex", flex: 1, minHeight: 0 },
  sidebar:         { width: 300, background: "white", borderRight: "1px solid #e6e6ec", padding: "24px 20px", display: "flex", flexDirection: "column", overflowY: "auto" },
  sideHeader:      { fontSize: 11, fontWeight: 700, letterSpacing: 1.2, color: "#888", marginBottom: 20 },
  qLabel:          { fontSize: 11, fontWeight: 700, letterSpacing: 0.6, color: "#6b7280", textTransform: "uppercase", marginBottom: 6, display: "block" },
  qInput:          { width: "100%", padding: "10px 12px", border: "1px solid #d6d6de", borderRadius: 8, fontSize: 13, outline: "none", background: "#fafafd", fontFamily: "inherit", color: "#111827", boxSizing: "border-box" },
  generateBtn:     { width: "100%", padding: "12px", background: "linear-gradient(135deg,#059669,#34d399)", color: "white", border: "none", borderRadius: 8, fontWeight: 600, fontSize: 14, cursor: "pointer", fontFamily: "inherit", transition: "transform 0.1s" },
  main:            { flex: 1, display: "flex", flexDirection: "column", minWidth: 0, position: "relative" },
  emptyState:      { flex: 1, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center" },
  carouselContainer:{ flex: 1, display: "flex", flexDirection: "column", minHeight: 0, padding: 24 },
  carouselViewport:{ flex: 1, minHeight: 0, overflow: "hidden", display: "flex", alignItems: "center", justifyContent: "center" },
  carouselSlide:   { display: "flex", width: "100%", transition: "transform 0.3s ease-out" },
  carouselSlideItem:{ flex: "0 0 100%", minWidth: 0, minHeight: 0, display: "flex", alignItems: "center", justifyContent: "center", overflow: "auto", padding: "20px" },
  qCard:           { display: "flex", width: "100%", maxWidth: 840, minHeight: 400, background: "white", borderRadius: 16, border: "1px solid #e6e6ec", boxShadow: "0 10px 30px rgba(0,0,0,0.06)", overflow: "hidden" },
  qCardLeft:       { flex: 1, padding: 32, display: "flex", flexDirection: "column" },
  qCardRight:      { flex: 1, padding: 32, background: "#fafafd", borderLeft: "1px solid #e6e6ec", display: "flex", flexDirection: "column", transition: "all 0.3s ease" },
  qMetaTop:        { display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 },
  qTag:            { padding: "4px 8px", background: "#f0eeff", color: "#6c63ff", borderRadius: 6, fontSize: 11, fontWeight: 700, textTransform: "uppercase", letterSpacing: 0.5 },
  qTagDifficulty:  { padding: "4px 8px", background: "#f3f4f6", color: "#4b5563", borderRadius: 6, fontSize: 11, fontWeight: 600, textTransform: "uppercase", letterSpacing: 0.5 },
  qMetaSmall:      { fontSize: 11, color: "#9ca3af", fontWeight: 500, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", maxWidth: 140, textAlign: "right" },
  qText:           { fontSize: 17, fontWeight: 600, color: "#111827", lineHeight: 1.5, flex: 1, marginBottom: 24, whiteSpace: "pre-wrap" },
  qOption:         { padding: "14px 16px", background: "white", border: "1px solid #d6d6de", borderRadius: 8, fontSize: 14, color: "#374151", transition: "all 0.15s", lineHeight: 1.4 },
  qOptionCorrect:  { background: "#ecfdf5", borderColor: "#34d399", color: "#065f46" },
  qOptionWrong:    { background: "#fff1f2", borderColor: "#f87171", color: "#991b1b" },
  qMetaBottom:     { marginTop: "auto", paddingTop: 20, fontSize: 11, color: "#9ca3af", borderTop: "1px solid #f3f4f6" },
  resultBadge:     { display: "flex", flexDirection: "column", alignItems: "center", padding: "16px 20px", borderRadius: 12, border: "2px solid" },
  qAnswer:         { fontSize: 14, color: "#374151", fontWeight: 600, padding: "10px 14px", background: "#f3f4f6", borderRadius: 8, marginTop: 4 },
  qExplain:        { fontSize: 13, color: "#4b5563", lineHeight: 1.6, padding: "12px 14px", background: "white", border: "1px solid #e6e6ec", borderRadius: 8, marginTop: 4, whiteSpace: "pre-wrap" },
  toast:           { position: "fixed", bottom: 20, right: 20, padding: "10px 16px", background: "white", border: "1px solid #d6d6de", borderRadius: 10, fontSize: 13, boxShadow: "0 4px 12px rgba(0,0,0,0.08)", zIndex: 300, maxWidth: 320 },
};

// Results overlay styles
const RS = {
  overlay:      { position: "fixed", inset: 0, background: "rgba(0,0,0,0.50)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 500, padding: 16 },
  card:         { width: "100%", maxWidth: 560, maxHeight: "90vh", background: "white", borderRadius: 20, boxShadow: "0 24px 80px rgba(0,0,0,0.25)", display: "flex", flexDirection: "column", overflow: "hidden" },
  cardHeader:   { padding: "28px 28px 20px", textAlign: "center", borderBottom: "1px solid #f3f4f6", background: "#fafafa", flexShrink: 0 },
  body:         { flex: 1, overflowY: "auto", padding: "20px 28px", display: "flex", flexDirection: "column", gap: 16 },
  footer:       { padding: "16px 28px", borderTop: "1px solid #f3f4f6", display: "flex", gap: 10, flexShrink: 0 },
  section:      { display: "flex", flexDirection: "column", gap: 4 },
  sectionLabel: { fontSize: 10, fontWeight: 700, letterSpacing: 1.2, color: "#9ca3af", textTransform: "uppercase", marginBottom: 4 },
  messageBanner:{ padding: "10px 14px", border: "1px solid", borderRadius: 10, fontSize: 13, lineHeight: 1.5 },
  statsRow:     { display: "flex", gap: 10 },
  stat:         { flex: 1, padding: "12px 10px", background: "#f9fafb", borderRadius: 10, textAlign: "center", border: "1px solid #f3f4f6" },
  statVal:      { fontSize: 22, fontWeight: 800, color: "#111827" },
  statLabel:    { fontSize: 11, color: "#6b7280", marginTop: 2 },
  conceptRow:   { display: "flex", alignItems: "center", gap: 8, padding: "5px 8px", background: "#fafafa", borderRadius: 6, marginBottom: 4, overflow: "hidden" },
  primaryBtn:   { flex: 1, padding: "10px 18px", border: "none", borderRadius: 8, background: "linear-gradient(135deg,#6c63ff,#a78bfa)", color: "white", fontSize: 13, fontWeight: 600, cursor: "pointer", fontFamily: "inherit" },
  ghostBtn:     { padding: "10px 18px", border: "1px solid #e6e6ec", borderRadius: 8, background: "white", color: "#6b7280", fontSize: 13, fontWeight: 600, cursor: "pointer", fontFamily: "inherit" },
};
