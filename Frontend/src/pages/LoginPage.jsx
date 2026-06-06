import { useState } from "react";
import { useNavigate } from "react-router-dom";

const API_BASE = import.meta.env.VITE_PARSER_API_BASE || "http://127.0.0.1:8100";

async function jsonPost(path, body) {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const err = new Error(data.detail || `HTTP ${res.status}`);
    err.status = res.status;
    throw err;
  }
  return data;
}

export default function LoginPage() {
  const navigate = useNavigate();
  const [tab, setTab] = useState("login");
  const [toast, setToast] = useState(null);
  const [loading, setLoading] = useState(false);

  function showToast(msg, type = "info") {
    setToast({ msg, type });
    setTimeout(() => setToast(null), 3500);
  }

  async function handleLogin(e) {
    e.preventDefault();
    const fd = new FormData(e.currentTarget);
    setLoading(true);
    try {
      const data = await jsonPost("/users/login", {
        email: fd.get("email"),
        password: fd.get("password"),
      });
      localStorage.setItem("baylearn:user", JSON.stringify(data));
      navigate("/home");
    } catch (err) {
      showToast(err.message || "Login failed", "error");
    } finally {
      setLoading(false);
    }
  }

  async function handleSignup(e) {
    e.preventDefault();
    const fd = new FormData(e.currentTarget);
    if (fd.get("password") !== fd.get("confirm")) {
      showToast("Passwords do not match", "error");
      return;
    }
    setLoading(true);
    try {
      await jsonPost("/users/signup", {
        name: fd.get("name"),
        email: fd.get("email"),
        password: fd.get("password"),
      });
      showToast("Account created! Please log in.", "success");
      setTab("login");
    } catch (err) {
      showToast(err.message || "Sign up failed", "error");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={S.page}>
      <div style={S.card}>
        {/* Brand */}
        <div style={S.brand}>
          <div style={S.logo}>B</div>
          <div>
            <div style={{ fontWeight: 700, fontSize: 17, color: "#111827" }}>BayLearn</div>
            <div style={{ fontSize: 12, color: "#888" }}>Adaptive study hub</div>
          </div>
        </div>

        {/* Tab switcher */}
        <div style={S.tabBar}>
          <button
            style={{ ...S.tabBtn, borderBottom: tab === "login" ? "2px solid #6c63ff" : "2px solid transparent", color: tab === "login" ? "#6c63ff" : "#888" }}
            onClick={() => setTab("login")}
          >Log in</button>
          <button
            style={{ ...S.tabBtn, borderBottom: tab === "signup" ? "2px solid #6c63ff" : "2px solid transparent", color: tab === "signup" ? "#6c63ff" : "#888" }}
            onClick={() => setTab("signup")}
          >Sign up</button>
        </div>

        {tab === "login" ? (
          <form onSubmit={handleLogin} style={S.form}>
            <div style={S.heading}>Welcome back</div>
            <div style={S.subheading}>Sign in to continue to your study hub</div>
            <label style={S.label}>Email</label>
            <input name="email" type="email" required placeholder="you@example.com" style={S.input} />
            <label style={S.label}>Password</label>
            <input name="password" type="password" required placeholder="••••••••" style={S.input} />
            <button type="submit" disabled={loading} style={{ ...S.submitBtn, opacity: loading ? 0.55 : 1 }}>
              {loading ? "Signing in…" : "Log in"}
            </button>
            <div style={S.switchRow}>
              Don't have an account?{" "}
              <button type="button" onClick={() => setTab("signup")} style={S.linkBtn}>Sign up</button>
            </div>
          </form>
        ) : (
          <form onSubmit={handleSignup} style={S.form}>
            <div style={S.heading}>Create an account</div>
            <div style={S.subheading}>Join BayLearn and start studying smarter</div>
            <label style={S.label}>Name</label>
            <input name="name" type="text" required placeholder="Your name" style={S.input} />
            <label style={S.label}>Email</label>
            <input name="email" type="email" required placeholder="you@example.com" style={S.input} />
            <label style={S.label}>Password</label>
            <input name="password" type="password" required placeholder="••••••••" style={S.input} />
            <label style={S.label}>Confirm password</label>
            <input name="confirm" type="password" required placeholder="••••••••" style={S.input} />
            <button type="submit" disabled={loading} style={{ ...S.submitBtn, opacity: loading ? 0.55 : 1 }}>
              {loading ? "Creating account…" : "Sign up"}
            </button>
            <div style={S.switchRow}>
              Already have an account?{" "}
              <button type="button" onClick={() => setTab("login")} style={S.linkBtn}>Log in</button>
            </div>
          </form>
        )}
      </div>

      {toast && (
        <div style={{ ...S.toast, borderColor: toast.type === "error" ? "#f87171" : toast.type === "success" ? "#4ade80" : "#d6d6de", color: toast.type === "error" ? "#c53030" : toast.type === "success" ? "#166534" : "#1a1a1a" }}>
          {toast.msg}
        </div>
      )}
    </div>
  );
}

const S = {
  page: { minHeight: "100vh", background: "#f7f7f8", display: "flex", alignItems: "center", justifyContent: "center", padding: "24px 16px" },
  card: { width: "100%", maxWidth: 420, background: "#fff", border: "1px solid #e6e6ec", borderRadius: 16, padding: "28px 28px 24px", boxShadow: "0 4px 24px rgba(0,0,0,0.07)" },
  brand: { display: "flex", alignItems: "center", gap: 10, marginBottom: 22 },
  logo: { width: 36, height: 36, borderRadius: 10, background: "linear-gradient(135deg,#6c63ff,#a78bfa)", color: "white", fontWeight: 800, fontSize: 17, display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 },
  tabBar: { display: "flex", borderBottom: "1px solid #e6e6ec", marginBottom: 20 },
  tabBtn: { flex: 1, background: "transparent", border: "none", padding: "10px 0", fontSize: 14, fontWeight: 600, cursor: "pointer", transition: "color 0.15s", fontFamily: "inherit" },
  form: { display: "flex", flexDirection: "column", gap: 4 },
  heading: { fontSize: 18, fontWeight: 700, color: "#111827", marginBottom: 2 },
  subheading: { fontSize: 13, color: "#6b7280", marginBottom: 14 },
  label: { fontSize: 11, fontWeight: 700, letterSpacing: 0.6, color: "#6b7280", textTransform: "uppercase", marginTop: 10, marginBottom: 4, display: "block" },
  input: { width: "100%", padding: "9px 12px", border: "1px solid #d6d6de", borderRadius: 8, fontSize: 14, outline: "none", background: "#fafafd", fontFamily: "inherit", color: "#111827" },
  submitBtn: { marginTop: 18, width: "100%", padding: "10px 0", border: "none", borderRadius: 8, background: "linear-gradient(135deg,#6c63ff,#a78bfa)", color: "white", fontSize: 14, fontWeight: 600, cursor: "pointer", fontFamily: "inherit" },
  switchRow: { marginTop: 14, textAlign: "center", fontSize: 13, color: "#6b7280" },
  linkBtn: { background: "none", border: "none", color: "#6c63ff", fontSize: 13, fontWeight: 600, cursor: "pointer", padding: 0, fontFamily: "inherit" },
  toast: { position: "fixed", bottom: 20, right: 20, padding: "10px 16px", background: "white", border: "1px solid #d6d6de", borderRadius: 10, fontSize: 13, boxShadow: "0 4px 12px rgba(0,0,0,0.08)", zIndex: 100 },
};
