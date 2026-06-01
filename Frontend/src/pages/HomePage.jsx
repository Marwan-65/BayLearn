import { useState, useEffect, useRef } from "react";
import { useNavigate } from "react-router-dom";
import BaymaxSvg from "../components/BaymaxSvg";

const API_BASE        = import.meta.env.VITE_API_BASE        || "http://127.0.0.1:8000";
const VISUALIZER_BASE = import.meta.env.VITE_VISUALIZER_BASE || "http://localhost:8010";

const RAG_URL = import.meta.env.VITE_RAG_URL      || "http://localhost:5173";
const EQ_URL  = import.meta.env.VITE_EQUATION_URL || "http://localhost:8501";

const MODULES = [
  {
    id: "rag",
    name: "Chat with Sources",
    emoji: "💬",
    desc: "Ask questions about your study materials",
    gradient: "linear-gradient(135deg,#6c63ff,#a78bfa)",
    color: "#6c63ff",
    fileMode: "many",
    hint: "Select any files you want to chat about",
    url: RAG_URL,
  },
  {
    id: "quiz",
    name: "Question Studio",
    emoji: "🎯",
    desc: "Generate and practice with quiz questions",
    gradient: "linear-gradient(135deg,#059669,#34d399)",
    color: "#059669",
    fileMode: "many",
    hint: "Select source files to generate questions from",
    url: RAG_URL + "?tab=questions",
  },
  {
    id: "animation",
    name: "Animation Lab",
    emoji: "🎬",
    desc: "Visualise algorithms & data structures",
    gradient: "linear-gradient(135deg,#f59e0b,#fcd34d)",
    color: "#d97706",
    fileMode: "one",
    hint: "Select exactly one file to animate",
    url: null, // resolved at runtime via /v1/file-launch
  },
  {
    id: "equation",
    name: "Equation Lab",
    emoji: "∑",
    desc: "Symbolic & numeric equation solver",
    gradient: "linear-gradient(135deg,#0ea5e9,#38bdf8)",
    color: "#0284c7",
    fileMode: "none",
    hint: null,
    url: EQ_URL,
  },
];

async function apiFetch(method, path, body, isForm = false) {
  const opts = {
    method,
    headers: isForm ? {} : { "Content-Type": "application/json" },
    body: isForm ? body : (body ? JSON.stringify(body) : undefined),
  };
  const res = await fetch(`${API_BASE}${path}`, opts);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);
  return data;
}

export default function HomePage() {
  const navigate = useNavigate();
  const user = (() => {
    try { return JSON.parse(localStorage.getItem("baylearn:user") || "null"); }
    catch { return null; }
  })();

  const [courses, setCourses]           = useState([]);
  const [selectedCourseId, setSelected] = useState(null);
  const [filesMap, setFilesMap]         = useState({});   // courseId → file[]
  const [toast, setToast]               = useState(null);
  const [showCreate, setShowCreate]     = useState(false);
  const [createForm, setCreateForm]     = useState({ name: "", description: "" });
  const [creating, setCreating]         = useState(false);
  const [uploading, setUploading]       = useState(false);
  const [launchModule, setLaunchModule] = useState(null); // module obj
  const [pickedFiles, setPickedFiles]   = useState([]);   // file_ids selected in modal
  const [launching, setLaunching]       = useState(false); // animation API in-flight
  const fileInputRef = useRef(null);

  useEffect(() => {
    if (!user) { navigate("/"); return; }
    loadCourses();
  }, []);

  function showToast(msg, type = "info") {
    setToast({ msg, type });
    setTimeout(() => setToast(null), 3500);
  }

  function logout() {
    localStorage.removeItem("baylearn:user");
    navigate("/");
  }

  async function loadCourses() {
    try {
      const list = await apiFetch("GET", `/courses/user/${user.user_id}`);
      setCourses(list);
      if (list.length > 0 && !selectedCourseId) {
        selectCourse(list[0].course_id, list);
      }
    } catch (err) {
      showToast(err.message, "error");
    }
  }

  async function selectCourse(courseId, courseList = courses) {
    setSelected(courseId);
    if (!filesMap[courseId]) {
      await loadFiles(courseId);
    }
  }

  async function loadFiles(courseId) {
    try {
      const files = await apiFetch("GET", `/courses/${courseId}/files`);
      setFilesMap(prev => ({ ...prev, [courseId]: files }));
    } catch {
      setFilesMap(prev => ({ ...prev, [courseId]: [] }));
    }
  }

  async function createCourse(e) {
    e.preventDefault();
    if (!createForm.name.trim()) return;
    setCreating(true);
    try {
      const course = await apiFetch("POST", "/courses", {
        user_id: user.user_id,
        name: createForm.name.trim(),
        description: createForm.description.trim() || null,
      });
      const updated = [...courses, course];
      setCourses(updated);
      setFilesMap(prev => ({ ...prev, [course.course_id]: [] }));
      setSelected(course.course_id);
      setShowCreate(false);
      setCreateForm({ name: "", description: "" });
      showToast(`"${course.name}" created`, "success");
    } catch (err) {
      showToast(err.message, "error");
    } finally {
      setCreating(false);
    }
  }

  async function deleteCourse(courseId, e) {
    e.stopPropagation();
    if (!confirm("Delete this course? Its files will be kept but uncategorised.")) return;
    try {
      await apiFetch("DELETE", `/courses/${courseId}`);
      const updated = courses.filter(c => c.course_id !== courseId);
      setCourses(updated);
      setFilesMap(prev => { const n = { ...prev }; delete n[courseId]; return n; });
      if (selectedCourseId === courseId) {
        setSelected(updated[0]?.course_id ?? null);
      }
      showToast("Course deleted", "success");
    } catch (err) {
      showToast(err.message, "error");
    }
  }

  async function uploadFile(e) {
    const files = Array.from(e.target.files || []);
    if (!files.length || !selectedCourseId) return;
    setUploading(true);
    try {
      for (const file of files) {
        const form = new FormData();
        form.append("file", file);
        await apiFetch(
          "POST",
          `/upload?user_id=${encodeURIComponent(user.user_id)}&course_id=${encodeURIComponent(selectedCourseId)}`,
          form,
          true
        );
      }
      await loadFiles(selectedCourseId);
      showToast(`Uploaded ${files.length} file${files.length > 1 ? "s" : ""}`, "success");
    } catch (err) {
      showToast(err.message || "Upload failed", "error");
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  }

  async function deleteFile(fileId, e) {
    e.stopPropagation();
    try {
      await apiFetch("DELETE", `/files/${fileId}`);
      setFilesMap(prev => ({
        ...prev,
        [selectedCourseId]: (prev[selectedCourseId] || []).filter(f => f.file_id !== fileId),
      }));
      showToast("File removed", "success");
    } catch (err) {
      showToast(err.message, "error");
    }
  }

  function openLaunch(mod) {
    if (mod.fileMode === "none") {
      localStorage.setItem("baylearn:launch_module", mod.id);
      window.open(mod.url, "_blank", "noopener");
      return;
    }
    setPickedFiles([]);
    setLaunchModule(mod);
  }

  async function launchNow() {
    if (!launchModule) return;
    localStorage.setItem("baylearn:launch_module", launchModule.id);
    localStorage.setItem("baylearn:selected_files", JSON.stringify(pickedFiles));
    if (selectedCourseId) localStorage.setItem("baylearn:pid", selectedCourseId);

    if (launchModule.id === "animation") {
      setLaunching(true);
      try {
        const res = await fetch(`${VISUALIZER_BASE}/v1/file-launch`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ file_id: pickedFiles[0] }),
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);
        setLaunchModule(null);
        window.location.href = data.viewer_url;
      } catch (err) {
        showToast(err.message || "Animation launch failed", "error");
      } finally {
        setLaunching(false);
      }
      return;
    }

    window.open(launchModule.url, "_blank", "noopener");
    setLaunchModule(null);
  }

  const selectedCourse = courses.find(c => c.course_id === selectedCourseId);
  const courseFiles    = filesMap[selectedCourseId] || [];
  const allFiles       = Object.values(filesMap).flat();

  function canLaunch() {
    if (!launchModule) return false;
    if (launchModule.fileMode === "one")  return pickedFiles.length === 1;
    if (launchModule.fileMode === "many") return pickedFiles.length >= 1;
    return true;
  }

  if (!user) return null;

  return (
    <div style={S.page}>
      {/* ── Header ─────────────────────────────────────────────── */}
      <header style={S.header}>
        <div style={S.headerLeft}>
          <div style={S.logo}>B</div>
          <div>
            <div style={{ fontWeight: 700, fontSize: 16, color: "#111827" }}>BayLearn</div>
            <div style={{ fontSize: 11, color: "#888" }}>Adaptive study hub</div>
          </div>
          {/* Small Baymax mascot in header */}
          <div style={S.headerBaymax} title="Hello, I am Baymax. Your personal study companion.">
            <BaymaxSvg size={28} />
          </div>
        </div>
        <div style={S.headerRight}>
          <div style={S.userPill}>
            <div style={S.avatarSmall}>{user.name?.[0]?.toUpperCase()}</div>
            <span style={{ fontSize: 13, fontWeight: 600, color: "#374151" }}>{user.name}</span>
          </div>
          <button onClick={logout} style={S.logoutBtn}>Log out</button>
        </div>
      </header>

      <div style={S.body}>
        {/* ── Sidebar ───────────────────────────────────────────── */}
        <aside style={S.sidebar}>
          <div style={S.sideHeader}>
            <span style={S.sideTitle}>MY COURSES</span>
            <button style={S.addBtn} onClick={() => setShowCreate(true)} title="New course">+</button>
          </div>

          {courses.length === 0 ? (
            <div style={S.sideEmpty}>
              <BaymaxSvg size={60} style={{ opacity: 0.5 }} />
              <div style={{ fontSize: 12, color: "#999", marginTop: 8, textAlign: "center" }}>
                No courses yet.<br />Create one to get started!
              </div>
            </div>
          ) : (
            <div style={S.courseList}>
              {courses.map(c => (
                <div
                  key={c.course_id}
                  onClick={() => selectCourse(c.course_id)}
                  style={{
                    ...S.courseCard,
                    background: selectedCourseId === c.course_id ? "#f0eeff" : "#fafafd",
                    borderColor: selectedCourseId === c.course_id ? "#c4b8ff" : "#e6e6ec",
                  }}
                >
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={S.courseName}>{c.name}</div>
                    {c.description && <div style={S.courseDesc}>{c.description}</div>}
                    <div style={S.courseMeta}>
                      {(filesMap[c.course_id]?.length ?? "…")} file{filesMap[c.course_id]?.length === 1 ? "" : "s"}
                    </div>
                  </div>
                  <button
                    style={S.deleteBtn}
                    onClick={e => deleteCourse(c.course_id, e)}
                    title="Delete course"
                  >×</button>
                </div>
              ))}
            </div>
          )}
        </aside>

        {/* ── Main ──────────────────────────────────────────────── */}
        <main style={S.main}>
          {!selectedCourse ? (
            /* Empty state */
            <div style={S.emptyState}>
              <BaymaxSvg size={110} />
              <div style={{ fontSize: 22, fontWeight: 700, color: "#111827", marginTop: 16 }}>
                Hello, I am Baymax.
              </div>
              <div style={{ fontSize: 14, color: "#6b7280", marginTop: 6, maxWidth: 340, textAlign: "center", lineHeight: 1.7 }}>
                Your personal study companion. Create a course on the left, upload your materials, and choose a module to begin learning.
              </div>
              <button onClick={() => setShowCreate(true)} style={{ ...S.primaryBtn, marginTop: 20 }}>
                + Create your first course
              </button>
            </div>
          ) : (
            <div style={S.mainContent}>
              {/* Course headline */}
              <div style={S.courseHeadline}>
                <div>
                  <div style={{ fontSize: 20, fontWeight: 700, color: "#111827" }}>{selectedCourse.name}</div>
                  {selectedCourse.description && (
                    <div style={{ fontSize: 13, color: "#6b7280", marginTop: 2 }}>{selectedCourse.description}</div>
                  )}
                </div>
              </div>

              {/* ── Materials ─────────────────────────────────── */}
              <section style={S.section}>
                <div style={S.sectionHeader}>
                  <span style={S.sectionTitle}>MATERIALS</span>
                  <button
                    style={{ ...S.primaryBtn, fontSize: 12, padding: "6px 14px", opacity: uploading ? 0.55 : 1 }}
                    onClick={() => fileInputRef.current?.click()}
                    disabled={uploading}
                  >
                    {uploading ? "Uploading…" : "+ Upload file"}
                  </button>
                  <input
                    ref={fileInputRef}
                    type="file"
                    multiple
                    hidden
                    accept=".pdf,.txt,.md,.png,.jpg,.jpeg,.mp3,.wav,.m4a,.mp4,.mov,.webm"
                    onChange={uploadFile}
                  />
                </div>

                {courseFiles.length === 0 ? (
                  <div style={S.filesEmpty}>
                    <span style={{ fontSize: 13, color: "#999" }}>No materials yet — upload a file to get started.</span>
                  </div>
                ) : (
                  <div style={S.filesGrid}>
                    {courseFiles.map(f => (
                      <div key={f.file_id} style={S.fileCard}>
                        <div style={S.fileIcon}>{fileIcon(f.source_type)}</div>
                        <div style={{ flex: 1, minWidth: 0 }}>
                          <div style={S.fileName}>{f.file_name || f.title}</div>
                          <div style={S.fileMeta}>
                            {f.source_type} · {f.total_chunks} chunk{f.total_chunks === 1 ? "" : "s"}
                          </div>
                        </div>
                        <button
                          style={S.deleteBtn}
                          onClick={e => deleteFile(f.file_id, e)}
                          title="Remove file"
                        >×</button>
                      </div>
                    ))}
                  </div>
                )}
              </section>

              {/* ── Launch a Module ───────────────────────────── */}
              <section style={S.section}>
                <div style={S.sectionHeader}>
                  <span style={S.sectionTitle}>LAUNCH A MODULE</span>
                </div>
                <div style={S.modulesGrid}>
                  {MODULES.map(mod => (
                    <ModuleCard key={mod.id} mod={mod} onLaunch={() => openLaunch(mod)} />
                  ))}
                </div>
              </section>
            </div>
          )}
        </main>
      </div>

      {/* ── Create course modal ────────────────────────────────── */}
      {showCreate && (
        <Modal onClose={() => setShowCreate(false)}>
          <div style={{ fontSize: 17, fontWeight: 700, color: "#111827", marginBottom: 4 }}>New course</div>
          <div style={{ fontSize: 13, color: "#6b7280", marginBottom: 18 }}>Organise your study materials into a course</div>
          <form onSubmit={createCourse} style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            <div>
              <label style={S.label}>Course name *</label>
              <input
                autoFocus
                required
                placeholder="e.g. Machine Learning"
                value={createForm.name}
                onChange={e => setCreateForm(p => ({ ...p, name: e.target.value }))}
                style={S.input}
              />
            </div>
            <div>
              <label style={S.label}>Description (optional)</label>
              <input
                placeholder="Short description"
                value={createForm.description}
                onChange={e => setCreateForm(p => ({ ...p, description: e.target.value }))}
                style={S.input}
              />
            </div>
            <button type="submit" disabled={creating || !createForm.name.trim()} style={{ ...S.primaryBtn, marginTop: 4, opacity: creating || !createForm.name.trim() ? 0.55 : 1 }}>
              {creating ? "Creating…" : "Create course"}
            </button>
          </form>
        </Modal>
      )}

      {/* ── File selection / launch modal ─────────────────────── */}
      {launchModule && (
        <Modal onClose={() => setLaunchModule(null)} wide>
          <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 6 }}>
            <div style={{ ...S.modEmoji, background: launchModule.gradient }}>{launchModule.emoji}</div>
            <div>
              <div style={{ fontSize: 17, fontWeight: 700, color: "#111827" }}>Launch {launchModule.name}</div>
              <div style={{ fontSize: 13, color: "#6b7280" }}>{launchModule.hint}</div>
            </div>
          </div>

          {allFiles.length === 0 ? (
            <div style={{ textAlign: "center", padding: "32px 0", color: "#999", fontSize: 13 }}>
              No files uploaded yet. Add materials to a course first.
            </div>
          ) : (
            <div style={{ marginTop: 16, maxHeight: 320, overflowY: "auto", display: "flex", flexDirection: "column", gap: 6 }}>
              {/* Group files by course */}
              {courses.map(c => {
                const cFiles = filesMap[c.course_id] || [];
                if (cFiles.length === 0) return null;
                return (
                  <div key={c.course_id}>
                    <div style={S.fileGroupLabel}>{c.name}</div>
                    {cFiles.map(f => {
                      const checked = pickedFiles.includes(f.file_id);
                      return (
                        <label key={f.file_id} style={{ ...S.filePickRow, background: checked ? "#f0eeff" : "#fafafd", borderColor: checked ? "#c4b8ff" : "#e6e6ec" }}>
                          <input
                            type={launchModule.fileMode === "one" ? "radio" : "checkbox"}
                            name="pick"
                            checked={checked}
                            onChange={() => {
                              if (launchModule.fileMode === "one") {
                                setPickedFiles([f.file_id]);
                              } else {
                                setPickedFiles(prev =>
                                  prev.includes(f.file_id)
                                    ? prev.filter(id => id !== f.file_id)
                                    : [...prev, f.file_id]
                                );
                              }
                            }}
                            style={{ accentColor: launchModule.color, marginRight: 10, flexShrink: 0 }}
                          />
                          <div style={S.fileIcon}>{fileIcon(f.source_type)}</div>
                          <div style={{ flex: 1, minWidth: 0 }}>
                            <div style={S.fileName}>{f.file_name || f.title}</div>
                            <div style={S.fileMeta}>{f.source_type} · {f.total_chunks} chunks</div>
                          </div>
                        </label>
                      );
                    })}
                  </div>
                );
              })}
            </div>
          )}

          {launching && (
            <div style={S.launchingBanner}>
              <span style={S.spinner} />
              Analysing file and generating animation… this may take up to 30 s
            </div>
          )}

          <div style={{ display: "flex", gap: 10, marginTop: 18 }}>
            <button onClick={() => { if (!launching) setLaunchModule(null); }} disabled={launching} style={{ ...S.ghostBtn, opacity: launching ? 0.45 : 1 }}>Cancel</button>
            <button
              onClick={launchNow}
              disabled={!canLaunch() || launching}
              style={{ ...S.primaryBtn, flex: 1, opacity: canLaunch() && !launching ? 1 : 0.45 }}
            >
              {launching ? "Launching…" : `Launch ${launchModule.name} ↗`}
            </button>
          </div>
        </Modal>
      )}

      {/* ── Toast ─────────────────────────────────────────────── */}
      {toast && (
        <div style={{ ...S.toast, borderColor: toast.type === "error" ? "#f87171" : toast.type === "success" ? "#4ade80" : "#d6d6de", color: toast.type === "error" ? "#c53030" : toast.type === "success" ? "#166534" : "#1a1a1a" }}>
          {toast.msg}
        </div>
      )}
    </div>
  );
}

/* ── Sub-components ──────────────────────────────────────────── */

function ModuleCard({ mod, onLaunch }) {
  const [hovered, setHovered] = useState(false);
  return (
    <div
      style={{
        ...S.modCard,
        boxShadow: hovered ? "0 6px 20px rgba(0,0,0,0.10)" : "0 2px 8px rgba(0,0,0,0.05)",
        transform: hovered ? "translateY(-2px)" : "translateY(0)",
      }}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      <div style={{ ...S.modBanner, background: mod.gradient }}>
        <span style={{ fontSize: 28 }}>{mod.emoji}</span>
      </div>
      <div style={S.modBody}>
        <div style={{ fontWeight: 700, fontSize: 14, color: "#111827" }}>{mod.name}</div>
        <div style={{ fontSize: 12, color: "#6b7280", marginTop: 3, lineHeight: 1.5 }}>{mod.desc}</div>
        <div style={{ fontSize: 11, color: "#9ca3af", marginTop: 6 }}>
          {mod.fileMode === "none" && "No files required"}
          {mod.fileMode === "one"  && "Select 1 file"}
          {mod.fileMode === "many" && "Select any files"}
        </div>
      </div>
      <button onClick={onLaunch} style={{ ...S.modLaunchBtn, background: mod.gradient }}>
        {mod.fileMode === "none" ? "Open ↗" : "Select files →"}
      </button>
    </div>
  );
}

function Modal({ children, onClose, wide = false }) {
  return (
    <div style={S.overlay} onClick={e => { if (e.target === e.currentTarget) onClose(); }}>
      <div style={{ ...S.modal, maxWidth: wide ? 560 : 400 }}>
        {children}
        <button onClick={onClose} style={S.modalClose} title="Close">×</button>
      </div>
    </div>
  );
}

function fileIcon(type = "") {
  const t = (type || "").toLowerCase();
  if (t.includes("pdf"))   return "📄";
  if (t.includes("audio")) return "🎵";
  if (t.includes("video")) return "🎥";
  if (t.includes("image")) return "🖼️";
  if (t.includes("text"))  return "📝";
  return "📁";
}

/* ── Styles ──────────────────────────────────────────────────── */
const S = {
  page:         { display: "flex", flexDirection: "column", height: "100vh", overflow: "hidden", background: "#f7f7f8", fontFamily: "-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif" },
  header:       { height: 56, background: "white", borderBottom: "1px solid #e6e6ec", display: "flex", alignItems: "center", justifyContent: "space-between", padding: "0 22px", flexShrink: 0 },
  headerLeft:   { display: "flex", alignItems: "center", gap: 10 },
  headerRight:  { display: "flex", alignItems: "center", gap: 10 },
  logo:         { width: 34, height: 34, borderRadius: 9, background: "linear-gradient(135deg,#6c63ff,#a78bfa)", color: "white", fontWeight: 800, fontSize: 16, display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 },
  headerBaymax: { marginLeft: 4, cursor: "default", display: "flex", alignItems: "flex-end" },
  userPill:     { display: "flex", alignItems: "center", gap: 7, padding: "5px 10px", background: "#f4f4f8", borderRadius: 20, border: "1px solid #e6e6ec" },
  avatarSmall:  { width: 24, height: 24, borderRadius: 6, background: "linear-gradient(135deg,#6c63ff,#a78bfa)", color: "white", fontWeight: 700, fontSize: 11, display: "flex", alignItems: "center", justifyContent: "center" },
  logoutBtn:    { padding: "6px 12px", border: "1px solid #e6e6ec", borderRadius: 8, background: "white", color: "#6b7280", fontSize: 13, fontWeight: 600, cursor: "pointer", fontFamily: "inherit" },

  body:         { display: "flex", flex: 1, minHeight: 0, overflow: "hidden" },

  sidebar:      { width: 260, flexShrink: 0, background: "white", borderRight: "1px solid #e6e6ec", display: "flex", flexDirection: "column", overflowY: "auto", padding: "16px 12px" },
  sideHeader:   { display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 10 },
  sideTitle:    { fontSize: 10, fontWeight: 700, letterSpacing: 1.2, color: "#888" },
  addBtn:       { width: 26, height: 26, border: "1px solid #d6d6de", borderRadius: 6, background: "white", color: "#555", fontSize: 16, cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center", lineHeight: 1, fontFamily: "inherit" },
  sideEmpty:    { display: "flex", flexDirection: "column", alignItems: "center", padding: "24px 8px" },
  courseList:   { display: "flex", flexDirection: "column", gap: 6 },
  courseCard:   { padding: "10px 10px", border: "1px solid #e6e6ec", borderRadius: 8, cursor: "pointer", display: "flex", alignItems: "flex-start", gap: 6, transition: "all 0.15s" },
  courseName:   { fontSize: 13, fontWeight: 600, color: "#111827", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" },
  courseDesc:   { fontSize: 11, color: "#6b7280", marginTop: 2, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" },
  courseMeta:   { fontSize: 10, color: "#9ca3af", marginTop: 3 },
  deleteBtn:    { border: "none", background: "transparent", color: "#9ca3af", fontSize: 16, cursor: "pointer", padding: "0 2px", flexShrink: 0, lineHeight: 1, fontFamily: "inherit" },

  main:         { flex: 1, minWidth: 0, overflowY: "auto" },
  emptyState:   { display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", height: "100%", padding: 40 },
  mainContent:  { padding: "28px 32px", display: "flex", flexDirection: "column", gap: 28 },
  courseHeadline: { paddingBottom: 0 },
  section:      { display: "flex", flexDirection: "column", gap: 12 },
  sectionHeader:{ display: "flex", alignItems: "center", gap: 10 },
  sectionTitle: { fontSize: 10, fontWeight: 700, letterSpacing: 1.2, color: "#888", flex: 1 },
  filesEmpty:   { padding: "20px 16px", border: "1px dashed #d6d6de", borderRadius: 8, textAlign: "center", background: "#fafafd" },
  filesGrid:    { display: "flex", flexDirection: "column", gap: 6 },
  fileCard:     { display: "flex", alignItems: "center", gap: 10, padding: "10px 12px", background: "white", border: "1px solid #e6e6ec", borderRadius: 8 },
  fileIcon:     { fontSize: 18, flexShrink: 0 },
  fileName:     { fontSize: 13, fontWeight: 600, color: "#111827", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" },
  fileMeta:     { fontSize: 11, color: "#9ca3af", marginTop: 1 },

  modulesGrid:  { display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(220px,1fr))", gap: 14 },
  modCard:      { background: "white", border: "1px solid #e6e6ec", borderRadius: 12, overflow: "hidden", display: "flex", flexDirection: "column", transition: "box-shadow 0.2s, transform 0.2s" },
  modBanner:    { height: 64, display: "flex", alignItems: "center", justifyContent: "center" },
  modBody:      { padding: "12px 14px 10px", flex: 1 },
  modEmoji:     { width: 44, height: 44, borderRadius: 10, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 22, flexShrink: 0 },
  modLaunchBtn: { margin: "0 14px 14px", padding: "8px 0", border: "none", borderRadius: 7, color: "white", fontSize: 13, fontWeight: 600, cursor: "pointer", fontFamily: "inherit" },

  primaryBtn:   { padding: "9px 18px", border: "none", borderRadius: 8, background: "linear-gradient(135deg,#6c63ff,#a78bfa)", color: "white", fontSize: 13, fontWeight: 600, cursor: "pointer", fontFamily: "inherit", whiteSpace: "nowrap" },
  ghostBtn:     { padding: "9px 18px", border: "1px solid #e6e6ec", borderRadius: 8, background: "white", color: "#6b7280", fontSize: 13, fontWeight: 600, cursor: "pointer", fontFamily: "inherit" },

  label:        { fontSize: 11, fontWeight: 700, letterSpacing: 0.6, color: "#6b7280", textTransform: "uppercase", marginBottom: 5, display: "block" },
  input:        { width: "100%", padding: "9px 12px", border: "1px solid #d6d6de", borderRadius: 8, fontSize: 14, outline: "none", background: "#fafafd", fontFamily: "inherit", color: "#111827", boxSizing: "border-box" },

  overlay:      { position: "fixed", inset: 0, background: "rgba(0,0,0,0.35)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 200, padding: 16 },
  modal:        { width: "100%", background: "white", borderRadius: 14, padding: "28px 24px 24px", position: "relative", boxShadow: "0 20px 60px rgba(0,0,0,0.18)" },
  modalClose:   { position: "absolute", top: 14, right: 16, background: "none", border: "none", fontSize: 22, color: "#888", cursor: "pointer", lineHeight: 1 },

  fileGroupLabel: { fontSize: 10, fontWeight: 700, letterSpacing: 1, color: "#9ca3af", padding: "8px 0 4px", textTransform: "uppercase" },
  filePickRow:  { display: "flex", alignItems: "center", gap: 8, padding: "8px 10px", border: "1px solid #e6e6ec", borderRadius: 7, cursor: "pointer", transition: "all 0.15s", marginBottom: 4 },

  toast:        { position: "fixed", bottom: 20, right: 20, padding: "10px 16px", background: "white", border: "1px solid #d6d6de", borderRadius: 10, fontSize: 13, boxShadow: "0 4px 12px rgba(0,0,0,0.08)", zIndex: 300, maxWidth: 320 },

  launchingBanner: { marginTop: 16, padding: "10px 14px", background: "#fef3c7", border: "1px solid #fcd34d", borderRadius: 8, fontSize: 13, color: "#92400e", display: "flex", alignItems: "center", gap: 10 },
  spinner:      { display: "inline-block", width: 14, height: 14, border: "2px solid #f59e0b", borderTopColor: "transparent", borderRadius: "50%", animation: "spin 0.7s linear infinite", flexShrink: 0 },
};
