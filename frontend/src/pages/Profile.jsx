import { useEffect, useState } from "react";
import { QRCodeSVG } from "qrcode.react";
import { downloadOfflineCard } from "../components/offlineCard.js";
import { downloadHealthCard, printHealthCard } from "../components/healthCard.js";
import { decryptBlob, encryptFile, vaultSupported } from "../vault.js";
import SecurityCenter from "../components/SecurityCenter.jsx";
import PhotoUpload from "../components/PhotoUpload.jsx";
import { deviceName, passkeySupported, registerPasskey } from "../passkey.js";
import { api, tokenStore } from "../api.js";
import { useAuth } from "../auth.jsx";
import { Alert, Badge, Card, Empty, Field, useAsync } from "../components/ui.jsx";

const BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";
const BG = ["", "A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"];
const TABS = ["Overview", "Profile", "Medical history", "Family", "Documents", "Sharing & consent", "Timeline", "Security"];
const KINDS = {
  allergies: { title: "Allergies", fields: [["name", "Allergen"], ["severity", "Severity"], ["reaction", "Reaction"]], line: (i) => `${i.severity || ""} ${i.reaction || ""}` },
  diseases: { title: "Previous diseases / conditions", fields: [["name", "Condition"], ["since", "Since (date)"], ["status", "Status"], ["notes", "Notes"]], line: (i) => `${i.status || ""} ${i.since || ""}` },
  surgeries: { title: "Previous surgeries", fields: [["name", "Surgery"], ["date", "Date"], ["hospital", "Hospital"], ["notes", "Notes"]], line: (i) => `${i.date || ""} ${i.hospital || ""}` },
  vaccinations: { title: "Vaccination history", fields: [["name", "Vaccine"], ["date", "Date"], ["dose", "Dose"], ["next_due", "Next due"]], line: (i) => `${i.dose || ""} ${i.date || ""} ${i.next_due ? "· next " + i.next_due : ""}` },
  emergency_contacts: { title: "Emergency contacts", fields: [["name", "Name"], ["relation", "Relation"], ["phone", "Phone (+91…)"], ["email", "Email"]], line: (i) => `${i.relation || ""} · ${i.phone || ""}` },
};

export default function Profile() {
  const [p, setP] = useState(null);
  const [tab, setTab] = useState("Overview");
  const load = () => api("/patients/me").then(setP).catch(() => {});
  useEffect(() => { load(); }, []);
  if (!p) return <p className="text-slate-500">Loading your health profile…</p>;
  return (
    <>
      <h1 className="text-xl font-bold">My health</h1>
      <div className="flex gap-1 overflow-x-auto border-b border-slate-200">
        {TABS.map((t) => <button key={t} onClick={() => setTab(t)} className={`whitespace-nowrap px-3 py-2 text-sm ${tab === t ? "border-b-2 border-brand-600 font-medium text-brand-700" : "text-slate-500 hover:text-slate-800"}`}>{t}</button>)}
      </div>
      {tab === "Overview" && <Overview p={p} />}
      {tab === "Profile" && <BasicInfo p={p} onSaved={setP} />}
      {tab === "Medical history" && Object.keys(KINDS).map((k) => <Records key={k} kind={k} items={p[k] || []} reload={load} />)}
      {tab === "Family" && <Family />}
      {tab === "Documents" && <Documents />}
      {tab === "Sharing & consent" && <Consents />}
      {tab === "Timeline" && <Timeline />}
      {tab === "Security" && <Security />}
    </>
  );
}

function Overview({ p }) {
  const cardUrl = `${window.location.origin}/card/${p.qr_token}`;
  const ready = p.blood_group && (p.emergency_contacts || []).length > 0;
  return (
    <>
      <div className="grid gap-4 md:grid-cols-3">
        <div className="rounded-xl bg-gradient-to-r from-brand-600 to-brand-900 p-5 text-white shadow md:col-span-2">
          {p.photo_url && <img src={p.photo_url} alt="" className="float-right h-20 w-20 rounded-xl border-2 border-white/60 object-cover" referrerPolicy="no-referrer" />}
          <p className="text-xs uppercase tracking-wider opacity-80">Digital Health ID</p>
          <p className="mt-1 font-mono text-2xl tracking-wider">{p.health_id}</p>
          <p className="mt-3 text-sm">{p.name}{p.age != null && ` · ${p.age} yrs`} · Blood group <b>{p.blood_group || "not set"}</b></p>
          <p className="text-sm">Allergies: <b>{(p.allergies || []).map((a) => a.name).join(", ") || "none recorded"}</b></p>
        </div>
        <Card title="Emergency QR card"><div className="flex flex-col items-center gap-2"><QRCodeSVG value={cardUrl} size={128} /><p className="text-center text-xs text-slate-500">Scan to show blood group, allergies and contacts without login. Print it or save it as your phone lock-screen.</p><a className="text-xs text-brand-700 underline" href={cardUrl} target="_blank" rel="noreferrer">Open card</a><div className="flex flex-wrap justify-center gap-2"><button className="btn-primary py-1 text-xs" onClick={() => downloadHealthCard(p, cardUrl)}>Download card (PNG)</button><button className="btn-ghost py-1 text-xs" onClick={() => printHealthCard(p, cardUrl)}>Print</button><button className="btn-ghost py-1 text-xs" onClick={() => downloadOfflineCard(p)}>Offline page</button></div>{!p.photo_url && <p className="text-center text-xs text-amber-700">Add your photo in the Profile tab so the card shows your face.</p>}</div></Card>
      </div>
      {!ready && <Alert tone="warn">Complete your emergency profile: add your blood group and at least one emergency contact.</Alert>}
      <Card title="At a glance"><p className="text-sm text-slate-700">Height {p.height_cm || "—"} cm · Weight {p.weight_kg || "—"} kg · {(p.diseases || []).length} condition(s) · {(p.vaccinations || []).length} vaccination(s) · {(p.surgeries || []).length} surgery record(s)</p></Card>
    </>
  );
}

function BasicInfo({ p, onSaved }) {
  const { user, setUser } = useAuth();
  const [f, setF] = useState({ phone: p.phone || "", dob: p.dob || "", sex: p.sex || "", blood_group: p.blood_group || "", height_cm: p.height_cm || "", weight_kg: p.weight_kg || "", address: p.address || "", city: p.city || "" });
  const [msg, setMsg] = useState("");
  const { busy, error, run } = useAsync();
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  const save = (e) => {
    e.preventDefault();
    run(async () => {
      const body = {};
      Object.entries(f).forEach(([k, v]) => { if (v !== "") body[k] = ["height_cm", "weight_kg"].includes(k) ? Number(v) : v; });
      const r = await api("/patients/me", { method: "PUT", body }); onSaved(r); setUser({ ...user, phone: r.phone }); setMsg("Saved.");
    });
  };
  return (
    <Card title="Personal details">
      <div className="mb-4 border-b border-slate-100 pb-4">
        <p className="label">Profile photo (shown on your emergency card)</p>
        <PhotoUpload value={p.photo_url} label={p.photo_url ? "Change photo" : "Upload photo"} onDone={(u) => run(async () => { const r = await api("/patients/me", { method: "PUT", body: { photo_url: u } }); onSaved(r); setMsg(u ? "Photo saved." : "Photo removed."); })} />
        <p className="mt-1 text-xs text-slate-500">Anyone who scans your emergency QR can see this photo, so use a clear face photo you are happy to show.</p>
      </div>
      <form onSubmit={save} className="grid gap-3 md:grid-cols-3">
        <Field label="Mobile"><input className="input" value={f.phone} onChange={set("phone")} /></Field>
        <Field label="Date of birth"><input className="input" type="date" value={f.dob} onChange={set("dob")} /></Field>
        <Field label="Sex"><select className="input" value={f.sex} onChange={set("sex")}><option value="">Select</option><option value="male">Male</option><option value="female">Female</option><option value="other">Other</option></select></Field>
        <Field label="Blood group"><select className="input" value={f.blood_group} onChange={set("blood_group")}>{BG.map((b) => <option key={b} value={b}>{b || "Select"}</option>)}</select></Field>
        <Field label="Height (cm)"><input className="input" type="number" step="0.1" value={f.height_cm} onChange={set("height_cm")} /></Field>
        <Field label="Weight (kg)"><input className="input" type="number" step="0.1" value={f.weight_kg} onChange={set("weight_kg")} /></Field>
        <Field label="Address"><input className="input" value={f.address} onChange={set("address")} /></Field>
        <Field label="City"><input className="input" value={f.city} onChange={set("city")} /></Field>
        <div className="flex items-end gap-3"><button className="btn-primary" disabled={busy}>Save</button><span className="text-sm text-emerald-700">{msg}</span></div>
        <div className="md:col-span-3"><Alert tone="error">{error}</Alert></div>
      </form>
    </Card>
  );
}

function Records({ kind, items, reload }) {
  const cfg = KINDS[kind];
  const [open, setOpen] = useState(false);
  const [d, setD] = useState({});
  const { error, run } = useAsync();
  const add = (e) => { e.preventDefault(); run(async () => { await api(`/patients/me/records/${kind}`, { method: "POST", body: { data: d } }); setD({}); setOpen(false); reload(); }); };
  const del = (id) => run(async () => { await api(`/patients/me/records/${kind}/${id}`, { method: "DELETE" }); reload(); });
  return (
    <Card title={cfg.title} action={<button className="btn-ghost py-1" onClick={() => setOpen(!open)}>{open ? "Cancel" : "+ Add"}</button>}>
      {open && (
        <form onSubmit={add} className="mb-3 grid gap-2 rounded-lg bg-slate-50 p-3 md:grid-cols-2">
          {cfg.fields.map(([k, l], i) => <Field key={k} label={l}><input className="input" required={i === 0} type={/date|since|next_due/.test(k) ? "date" : "text"} value={d[k] || ""} onChange={(e) => setD({ ...d, [k]: e.target.value })} /></Field>)}
          <div className="md:col-span-2"><button className="btn-primary">Save</button></div>
        </form>
      )}
      <Alert tone="error">{error}</Alert>
      {items.length === 0 ? <Empty>Nothing recorded yet.</Empty> : <ul className="divide-y divide-slate-100 text-sm">{items.map((i) => <li key={i.id} className="flex items-center justify-between py-2"><span><b>{i.name}</b> <span className="text-slate-500">{cfg.line(i)}</span></span><button className="text-xs text-red-600 hover:underline" onClick={() => del(i.id)}>Remove</button></li>)}</ul>}
    </Card>
  );
}

function Family() {
  const [list, setList] = useState([]);
  const [f, setF] = useState({ name: "", relation: "", dob: "", blood_group: "", notes: "" });
  const { error, run } = useAsync();
  const load = () => api("/patients/me/family").then(setList).catch(() => {});
  useEffect(() => { load(); }, []);
  const add = (e) => { e.preventDefault(); const body = Object.fromEntries(Object.entries(f).filter(([, v]) => v)); run(async () => { await api("/patients/me/family", { method: "POST", body }); setF({ name: "", relation: "", dob: "", blood_group: "", notes: "" }); load(); }); };
  return (
    <Card title="Family member profiles">
      <form onSubmit={add} className="grid gap-2 md:grid-cols-5">
        <input className="input" placeholder="Name" required value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} />
        <input className="input" placeholder="Relation" required value={f.relation} onChange={(e) => setF({ ...f, relation: e.target.value })} />
        <input className="input" type="date" value={f.dob} onChange={(e) => setF({ ...f, dob: e.target.value })} />
        <select className="input" value={f.blood_group} onChange={(e) => setF({ ...f, blood_group: e.target.value })}>{BG.map((b) => <option key={b} value={b}>{b || "Blood group"}</option>)}</select>
        <button className="btn-primary">Add</button>
      </form>
      <Alert tone="error">{error}</Alert>
      <ul className="mt-3 divide-y divide-slate-100 text-sm">{list.map((m) => <li key={m.id} className="flex items-center justify-between py-2"><span><b>{m.name}</b> · {m.relation} {m.blood_group && `· ${m.blood_group}`} {m.dob && `· ${m.dob}`}</span><button className="text-xs text-red-600 hover:underline" onClick={() => run(async () => { await api(`/patients/me/family/${m.id}`, { method: "DELETE" }); load(); })}>Remove</button></li>)}</ul>
    </Card>
  );
}

function Documents() {
  const [list, setList] = useState([]);
  const [file, setFile] = useState(null);
  const [title, setTitle] = useState("");
  const [cat, setCat] = useState("report");
  const { busy, error, run } = useAsync();
  const load = () => api("/patients/me/documents").then(setList).catch(() => {});
  useEffect(() => { load(); }, []);
  const [vault, setVault] = useState(false);
  const [pass, setPass] = useState("");
  const [unlock, setUnlock] = useState(null); // { id, pass }
  const upload = (e) => { e.preventDefault(); run(async () => {
    const form = new FormData();
    form.append("title", title || file.name); form.append("category", cat);
    if (vault) {
      if (pass.length < 12) throw new Error("Vault passphrase must be at least 12 characters");
      form.append("file", await encryptFile(file, pass), "vault.bin"); form.append("orig_name", file.name); form.append("orig_type", file.type || "application/octet-stream");
      await api("/patients/me/documents/vault", { method: "POST", form }); setPass("");
    } else { form.append("file", file); await api("/patients/me/documents", { method: "POST", form }); } setFile(null); setTitle(""); e.target.reset(); load(); }); };
  const download = (d) => run(async () => {
    const res = await fetch(`${BASE}/patients/documents/${d.id}/download`, { headers: { Authorization: `Bearer ${tokenStore.get()}` } });
    if (!res.ok) throw new Error("Download failed");
    let blob = await res.blob();
    if (d.e2ee) { blob = await decryptBlob(blob, unlock?.pass || "", d.orig_type); setUnlock(null); } // decrypted only in this browser
    const url = URL.createObjectURL(blob); const a = document.createElement("a"); a.href = url; a.download = d.filename; a.click(); URL.revokeObjectURL(url);
  });
  return (
    <Card title="Medical documents (encrypted at rest)">
      <form onSubmit={upload} className="grid gap-2 md:grid-cols-4">
        <input className="input" placeholder="Title" value={title} onChange={(e) => setTitle(e.target.value)} />
        <select className="input" value={cat} onChange={(e) => setCat(e.target.value)}>{["report", "prescription", "scan", "discharge summary", "insurance", "other"].map((c) => <option key={c}>{c}</option>)}</select>
        <input className="input" type="file" required accept=".pdf,.png,.jpg,.jpeg,.txt,.dcm" onChange={(e) => setFile(e.target.files[0])} />
        <button className="btn-primary" disabled={busy || !file}>Upload</button>
        {vaultSupported() && (
          <label className="flex items-start gap-2 text-sm md:col-span-4">
            <input type="checkbox" className="mt-1" checked={vault} onChange={(e) => setVault(e.target.checked)} />
            <span><b>Private Vault</b> - encrypt in my browser so even the server and admins cannot read this file. Not available to the AI analyzer or for doctors unless you share the passphrase.</span>
          </label>
        )}
        {vault && <div className="md:col-span-4"><input className="input" type="password" autoComplete="new-password" placeholder="Vault passphrase (12+ characters)" value={pass} onChange={(e) => setPass(e.target.value)} /><p className="mt-1 text-xs text-amber-700">There is no recovery. If you forget this passphrase the file can never be opened, by anyone.</p></div>}
      </form>
      <Alert tone="error">{error}</Alert>
      {list.length === 0 ? <div className="mt-3"><Empty>No documents.</Empty></div> : <ul className="mt-3 divide-y divide-slate-100 text-sm">{list.map((d) => <li key={d.id} className="flex items-center justify-between py-2"><span><b>{d.title}</b> <span className="text-slate-500">{d.category} · {(d.size / 1024).toFixed(0)} KB · {d.created_at.slice(0, 10)}</span></span><span className="flex gap-2">{d.e2ee && <span className="rounded bg-emerald-100 px-1.5 py-0.5 text-xs text-emerald-800">vault</span>}{d.e2ee && unlock?.id === d.id && <input className="input py-1 text-xs" type="password" autoFocus placeholder="Passphrase" value={unlock.pass} onChange={(e) => setUnlock({ id: d.id, pass: e.target.value })} />}<button className="btn-ghost py-1" onClick={() => (d.e2ee && unlock?.id !== d.id ? setUnlock({ id: d.id, pass: "" }) : download(d))}>{d.e2ee && unlock?.id === d.id ? "Unlock & download" : "Download"}</button><button className="text-xs text-red-600 hover:underline" onClick={() => run(async () => { await api(`/patients/me/documents/${d.id}`, { method: "DELETE" }); load(); })}>Delete</button></span></li>)}</ul>}
    </Card>
  );
}

const SCOPES = ["summary", "vitals", "reports", "documents", "medicines"];
function Consents() {
  const [list, setList] = useState([]);
  const [email, setEmail] = useState("");
  const [scopes, setScopes] = useState(["summary"]);
  const [expires, setExpires] = useState("");
  const { error, run } = useAsync();
  const load = () => api("/patients/me/consents").then(setList).catch(() => {});
  useEffect(() => { load(); }, []);
  const grant = (e) => { e.preventDefault(); run(async () => { await api("/patients/me/consents", { method: "POST", body: { grantee_email: email, scopes, ...(expires ? { expires } : {}) } }); setEmail(""); load(); }); };
  return (
    <Card title="Who can see my health data">
      <p className="mb-3 text-sm text-slate-500">Doctors you book can see your summary automatically. Give family or any other person access by email; revoke any time. Every access is logged.</p>
      <form onSubmit={grant} className="grid gap-2 md:grid-cols-4">
        <input className="input" type="email" placeholder="Their registered email" required value={email} onChange={(e) => setEmail(e.target.value)} />
        <input className="input" type="date" value={expires} onChange={(e) => setExpires(e.target.value)} title="Optional expiry" />
        <div className="flex flex-wrap items-center gap-2 text-sm md:col-span-2">{SCOPES.map((s) => <label key={s} className="flex items-center gap-1"><input type="checkbox" checked={scopes.includes(s)} onChange={(e) => setScopes(e.target.checked ? [...scopes, s] : scopes.filter((x) => x !== s))} />{s}</label>)}</div>
        <button className="btn-primary" disabled={!scopes.length}>Grant access</button>
      </form>
      <Alert tone="error">{error}</Alert>
      <ul className="mt-3 divide-y divide-slate-100 text-sm">
        {list.map((c) => <li key={c.id} className="flex items-center justify-between py-2"><span><b>{c.grantee_email}</b> · {c.scopes.join(", ")} {c.expires && `· until ${c.expires}`} {c.active ? <Badge tone="good">active</Badge> : <Badge>revoked</Badge>}</span>{c.active && <button className="btn-ghost py-1" onClick={() => run(async () => { await api(`/patients/me/consents/${c.id}`, { method: "DELETE" }); load(); })}>Revoke</button>}</li>)}
      </ul>
    </Card>
  );
}

function Timeline() {
  const [ev, setEv] = useState([]);
  useEffect(() => { api("/patients/me/timeline").then(setEv).catch(() => {}); }, []);
  return (
    <Card title="Health timeline">
      {ev.length === 0 ? <Empty>Your activity appears here.</Empty> : (
        <ol className="relative ml-2 border-l border-slate-200">{ev.map((e) => <li key={e.id} className="mb-3 ml-4"><span className="absolute -left-1.5 mt-1.5 h-3 w-3 rounded-full bg-brand-500" /><p className="text-sm"><Badge tone="info">{e.kind}</Badge> {e.title}</p><p className="text-xs text-slate-400">{e.ts.slice(0, 16).replace("T", " ")} UTC</p></li>)}</ol>
      )}
    </Card>
  );
}

function Security() {
  const { user, setUser } = useAuth();
  const [pw, setPw] = useState({ old_password: "", new_password: "", otp: "" });
  const [sent, setSent] = useState(false);
  const [msg, setMsg] = useState("");
  const { error, run } = useAsync();
  const change = (e) => {
    e.preventDefault();
    run(async () => {
      if (!sent) { const r = await api("/auth/change-password/request", { method: "POST", body: pw }); setSent(true); setMsg(r.message); return; }
      await api("/auth/change-password", { method: "POST", body: pw });
      setPw({ old_password: "", new_password: "", otp: "" }); setSent(false); setMsg("Password changed.");
    });
  };
  const twofa = () => run(async () => { await api(`/auth/two-factor?enable=${!user.two_factor}`, { method: "POST" }); setUser(await api("/auth/me")); });
  const [keys, setKeys] = useState([]);
  const [kname, setKname] = useState(deviceName());
  const loadKeys = () => api("/auth/passkey").then(setKeys).catch(() => {});
  useEffect(() => { loadKeys(); }, []);
  const addKey = () => run(async () => { await registerPasskey(kname); setMsg("Fingerprint / face login added for this device."); loadKeys(); });
  const delKey = (id) => { if (!window.confirm("Remove this device?")) return; run(async () => { await api(`/auth/passkey/${id}`, { method: "DELETE" }); loadKeys(); }); };
  return (
    <>
      <Card title="Fingerprint / face login">
        {passkeySupported() ? (
          <div className="space-y-3 text-sm">
            <p className="text-slate-600">Log in with your phone's fingerprint, face unlock or screen-lock PIN instead of typing your password. Your fingerprint or face never leaves your device.</p>
            {keys.length === 0 ? <p className="text-slate-500">No device added yet.</p> : <ul className="divide-y divide-slate-100">{keys.map((k) => <li key={k.id} className="flex items-center justify-between py-1.5"><span><b>{k.name}</b> <span className="text-xs text-slate-500">added {k.created_at.slice(0, 10)}{k.last_used ? ` · last used ${k.last_used.slice(0, 10)}` : ""}</span></span><button className="text-xs text-red-700 underline" onClick={() => delKey(k.id)}>Remove</button></li>)}</ul>}
            <div className="flex gap-2"><input className="input max-w-[200px]" value={kname} maxLength={40} onChange={(e) => setKname(e.target.value)} aria-label="Device name" /><button className="btn-primary" onClick={addKey}>Add this device</button></div>
            <p className="text-xs text-slate-500">Up to 5 devices. If you change the website address, add your devices again. Keep your password safe as a backup.</p>
          </div>
        ) : <p className="text-sm text-slate-600">This browser or connection does not support fingerprint / face login. Open the app over https in Chrome, Safari or Edge.</p>}
      </Card>
      <Card title="Two-factor authentication"><div className="flex items-center justify-between text-sm"><span>Email/SMS code at login: <Badge tone={user.two_factor || user.role === "admin" || user.role === "super_admin" ? "good" : "muted"}>{user.role === "admin" || user.role === "super_admin" ? "required" : user.two_factor ? "on" : "off"}</Badge></span>{user.role !== "admin" && user.role !== "super_admin" && <button className="btn-ghost" onClick={twofa}>{user.two_factor ? "Turn off" : "Turn on"}</button>}</div></Card>
      <Card title="Change password">
        <form onSubmit={change} className="grid gap-2 md:grid-cols-3"><input className="input" type="password" placeholder="Current password" required value={pw.old_password} onChange={(e) => setPw({ ...pw, old_password: e.target.value })} /><input className="input" type="password" placeholder="New password (10+, Aa1!)" minLength={10} required value={pw.new_password} onChange={(e) => setPw({ ...pw, new_password: e.target.value })} />{sent && <input className="input" inputMode="numeric" placeholder="OTP" required value={pw.otp} onChange={(e) => setPw({ ...pw, otp: e.target.value })} />}<button className="btn-primary">{sent ? "Verify OTP & update" : "Send OTP"}</button></form>
        <Alert tone="error">{error}</Alert><Alert tone="ok">{msg}</Alert>
      </Card>
      <SecurityCenter />
    </>
  );
}
