import { useEffect, useState } from "react";
import { api, tokenStore } from "../api.js";
import { useAuth } from "../auth.jsx";
import { Alert, Badge, Card, useAsync } from "./ui.jsx";

const when = (t) => (t || "").replace("T", " ").slice(0, 16);
const device = (ua = "") => (/iPhone|iPad/.test(ua) ? "iPhone / iPad" : /Android/.test(ua) ? "Android" : /Windows/.test(ua) ? "Windows PC" : /Mac/.test(ua) ? "Mac" : /Linux/.test(ua) ? "Linux" : ua ? ua.slice(0, 40) : "Unknown device");

// Active devices, login history, log out everywhere, data export and account deletion (privacy controls).
export default function SecurityCenter() {
  const { user, logout } = useAuth();
  const [sessions, setSessions] = useState([]);
  const [history, setHistory] = useState([]);
  const [access, setAccess] = useState([]);
  const [msg, setMsg] = useState("");
  const [del, setDel] = useState({ open: false, password: "", confirm: "" });
  const { error, run } = useAsync();
  const load = () => {
    api("/privacy/sessions").then(setSessions).catch(() => {});
    api("/privacy/login-history").then(setHistory).catch(() => {});
    api("/privacy/access-log").then(setAccess).catch(() => {});
  };
  useEffect(load, []);
  const endOne = (id) => run(async () => { await api(`/privacy/sessions/${id}`, { method: "DELETE" }); setMsg("Device logged out."); load(); });
  const endAll = () => {
    if (!window.confirm("Log out from ALL devices, including this one?")) return;
    run(async () => { await api("/privacy/logout-all", { method: "POST" }); tokenStore.clear(); window.location.href = "/login"; });
  };
  const exportData = () => run(async () => {
    const data = await api("/privacy/export");
    const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }));
    const a = Object.assign(document.createElement("a"), { href: url, download: "my-medismart-data.json" });
    a.click(); URL.revokeObjectURL(url);
  });
  const deleteAcct = (e) => {
    e.preventDefault();
    run(async () => { await api("/privacy/delete-account", { method: "POST", body: { password: del.password, confirm: del.confirm } }); await logout(); window.location.href = "/"; });
  };
  const admin = user.role === "admin" || user.role === "super_admin";
  return (
    <>
      <Card title="Active devices">
        <div className="space-y-2 text-sm">
          {sessions.length === 0 ? <p className="text-slate-500">No active sessions found.</p> : (
            <ul className="divide-y divide-slate-100">
              {sessions.map((s) => (
                <li key={s.id} className="flex items-center justify-between gap-2 py-1.5">
                  <span><b>{device(s.ua)}</b> {s.current && <Badge tone="good">this device</Badge>}<br /><span className="text-xs text-slate-500">{s.ip || "unknown IP"} · signed in {when(s.created)} · {s.method}</span></span>
                  {!s.current && <button className="text-xs text-red-700 underline" onClick={() => endOne(s.id)}>Log out</button>}
                </li>
              ))}
            </ul>
          )}
          <button className="btn-ghost" onClick={endAll}>Log out from all devices</button>
          <p className="text-xs text-slate-500">Lost your phone or see a device you don't recognise? Log out everywhere, then change your password.</p>
        </div>
      </Card>
      <Card title="Login history">
        <div className="max-h-64 overflow-auto text-sm">
          <table className="w-full"><thead><tr className="text-left text-xs text-slate-500"><th>When</th><th>Result</th><th>IP</th><th>Device</th></tr></thead>
            <tbody>{history.map((h) => <tr key={h.id} className="border-t border-slate-100"><td className="py-1">{when(h.ts)}</td><td><Badge tone={h.success ? "good" : "bad"}>{h.success ? "success" : "failed"}</Badge></td><td>{h.ip || "-"}</td><td>{device(h.ua)}</td></tr>)}</tbody></table>
        </div>
      </Card>
      {user.role === "patient" && (
        <Card title="Who accessed my records">
          <div className="max-h-64 overflow-auto text-sm">
            {access.length === 0 ? <p className="text-slate-500">Nobody else has opened your records.</p> : (
              <table className="w-full"><thead><tr className="text-left text-xs text-slate-500"><th>When</th><th>Who</th><th>What</th></tr></thead>
                <tbody>{access.map((a, i) => <tr key={i} className="border-t border-slate-100"><td className="py-1">{when(a.when)}</td><td>{a.who} <span className="text-xs text-slate-500">({a.role})</span></td><td>{a.action === "phi_denied" ? <Badge tone="bad">blocked</Badge> : a.action.replace("phi_", "").replace("_", " ")} {a.what}</td></tr>)}</tbody></table>
            )}
          </div>
          <p className="mt-2 text-xs text-slate-500">This list is part of a tamper-proof log: entries cannot be edited or removed without detection.</p>
        </Card>
      )}
      <Card title="Your data">
        <div className="space-y-3 text-sm">
          <div className="flex items-center justify-between"><span>Download a copy of everything we hold about you (JSON).</span><button className="btn-ghost" onClick={exportData}>Download my data</button></div>
          {admin ? <p className="text-xs text-slate-500">Admin accounts are deleted by a super admin, not from here. Admin login always needs an email code (2FA).</p> : (
            <>
              <button className="text-sm text-red-700 underline" onClick={() => setDel({ ...del, open: !del.open })}>Delete my account</button>
              {del.open && (
                <form onSubmit={deleteAcct} className="space-y-2 rounded-lg border border-red-200 bg-red-50 p-3">
                  <p className="text-xs text-red-800">This permanently erases your profile, records, reports and documents. It cannot be undone. A security audit entry is kept.</p>
                  <input className="input" type="password" placeholder="Your password" required value={del.password} onChange={(e) => setDel({ ...del, password: e.target.value })} />
                  <input className="input" placeholder='Type DELETE to confirm' required value={del.confirm} onChange={(e) => setDel({ ...del, confirm: e.target.value })} />
                  <button className="btn-primary bg-red-600 hover:bg-red-700" disabled={del.confirm !== "DELETE"}>Permanently delete</button>
                </form>
              )}
            </>
          )}
        </div>
      </Card>
      <Alert tone="error">{error}</Alert><Alert tone="ok">{msg}</Alert>
    </>
  );
}
