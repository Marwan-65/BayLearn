import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import LoginPage from "./pages/LoginPage";
import HomePage from "./pages/HomePage";

function getUser() {
  try { return JSON.parse(localStorage.getItem("baylearn:user") || "null"); }
  catch { return null; }
}

function RequireAuth({ children }) {
  return getUser() ? children : <Navigate to="/" replace />;
}

function RedirectIfAuthed({ children }) {
  return getUser() ? <Navigate to="/home" replace /> : children;
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<RedirectIfAuthed><LoginPage /></RedirectIfAuthed>} />
        <Route path="/home" element={<RequireAuth><HomePage /></RequireAuth>} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
