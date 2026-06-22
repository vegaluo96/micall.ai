import { useState, type CSSProperties } from "react";
import { DcView } from "./dc/DcView";
import { useAdmin } from "./logic/useAdmin";
import { AdminLogin } from "./AdminLogin";
import { isAuthed, logout } from "./logic/auth";
import template from "./app.template.html?raw";

function Console({ onLogout }: { onLogout: () => void }) {
  const logic = useAdmin();
  return (
    <>
      <DcView template={template} vals={logic.renderVals()} />
      {/* 退出登录：浮层按钮，不改原型内部 UI */}
      <button style={logoutBtn} onClick={onLogout} title="退出登录">退出</button>
    </>
  );
}

export default function App() {
  const [authed, setAuthed] = useState(isAuthed());
  if (!authed) return <AdminLogin onSuccess={() => setAuthed(true)} />;
  return <Console onLogout={() => { logout(); setAuthed(false); }} />;
}

const logoutBtn: CSSProperties = {
  position: "fixed",
  left: 12,
  bottom: 12,
  zIndex: 2147483600,
  border: "1px solid #E6E7EB",
  background: "rgba(255,255,255,.92)",
  color: "#5A5E6B",
  fontSize: 12,
  fontWeight: 600,
  borderRadius: 10,
  padding: "6px 12px",
  cursor: "pointer",
  boxShadow: "0 4px 12px rgba(0,0,0,.08)",
  fontFamily: "-apple-system,BlinkMacSystemFont,'SF Pro Display','Helvetica Neue',sans-serif",
};
