// Admin: edit the public hospital website (info, packages, insurers, blog, gallery) and moderate feedback.
import { useEffect, useState } from "react";
import { api } from "../api.js";
import PhotoUpload from "../components/PhotoUpload.jsx";
import { Alert, Badge, Card, Field, textToList, useAsync } from "../components/ui.jsx";

const INFO = [["name", "Hospital name"], ["tagline", "Tagline"], ["address", "Address"], ["phone", "Phone"], ["email", "Email"], ["whatsapp", "WhatsApp number (with country code)"], ["emergency_phone", "Emergency helpline"], ["ambulance_phone", "Ambulance number"],
  ["opd_hours", "OPD hours"], ["visiting_hours", "Visiting hours"], ["parking", "Parking information"], ["map_query", "Map search text (address)"], ["emergency_location", "Emergency department location"]];

export default function SiteAdmin() {
  const [f, setF] = useState(null);
  const [fb, setFb] = useState([]);
  const [msg, setMsg] = useState("");
  const { error, run, busy } = useAsync();
  const load = () => run(async () => {
    const c = await api("/site/home");
    setF({ ...Object.fromEntries(INFO.map(([k]) => [k, c[k] || ""])), packages: c.packages.map((p) => `${p.name} | ${p.price} | ${p.includes.join(", ")}`).join("\n"), insurers: c.insurers.join(", "),
      blog: c.blog.map((b) => `${b.title} | ${b.body.replace(/\n/g, " ")}`).join("\n"), gallery: c.gallery.map((g) => `${g.url} | ${g.caption}`).join("\n") });
    setFb(await api("/site/feedback"));
  });
  useEffect(() => { load(); }, []);
  const save = (e) => {
    e.preventDefault();
    const lines = (s) => s.split("\n").map((x) => x.trim()).filter(Boolean);
    const body = Object.fromEntries(INFO.map(([k]) => [k, f[k]]));
    body.packages = lines(f.packages).map((l) => { const [name, price, inc] = l.split("|").map((x) => x.trim()); return { name, price: +price || 0, includes: textToList(inc || "") }; });
    body.insurers = textToList(f.insurers);
    body.blog = lines(f.blog).map((l) => { const [title, ...rest] = l.split("|"); return { title: title.trim(), body: rest.join("|").trim(), date: new Date().toISOString().slice(0, 10) }; });
    body.gallery = lines(f.gallery).map((l) => { const [url, caption] = l.split("|").map((x) => x.trim()); return { url, caption: caption || "" }; });
    run(async () => { await api("/site/config", { method: "PUT", body }); setMsg("Website updated. Open /hospital to see it."); load(); });
  };
  const toggle = (x) => run(async () => { await api(`/site/feedback/${x.id}?public=${!x.public}`, { method: "PATCH" }); load(); });
  if (!f) return <Alert tone="error">{error}</Alert>;
  return (
    <>
      <h1 className="text-xl font-bold">Hospital website</h1>
      <Alert tone="error">{error}</Alert><Alert tone="ok">{msg}</Alert>
      <form onSubmit={save} className="space-y-4">
        <Card title="Information"><div className="grid gap-3 md:grid-cols-3">{INFO.map(([k, l]) => <Field key={k} label={l}><input className="input" value={f[k]} onChange={(e) => setF({ ...f, [k]: e.target.value })} /></Field>)}</div></Card>
        <Card title="Health checkup packages (one per line: name | price | item, item)"><textarea className="input min-h-[90px]" value={f.packages} onChange={(e) => setF({ ...f, packages: e.target.value })} /></Card>
        <Card title="Accepted insurance / TPA (comma separated)"><textarea className="input" value={f.insurers} onChange={(e) => setF({ ...f, insurers: e.target.value })} /></Card>
        <Card title="Health blog (one post per line: title | text)"><textarea className="input min-h-[90px]" value={f.blog} onChange={(e) => setF({ ...f, blog: e.target.value })} /></Card>
        <Card title="Gallery (one per line: https image link | caption)"><div className="mb-2"><PhotoUpload label="Upload gallery photo" onDone={(u) => u && setF({ ...f, gallery: (f.gallery ? f.gallery + "\n" : "") + u + " | " })} /></div><textarea className="input min-h-[70px]" value={f.gallery} onChange={(e) => setF({ ...f, gallery: e.target.value })} /></Card>
        <button className="btn-primary" disabled={busy}>Save website</button>
      </form>
      <Card title="Feedback & complaints">
        {!fb.length && <p className="text-sm text-slate-500">Nothing yet.</p>}
        <ul className="divide-y divide-slate-100 text-sm">{fb.map((x) => <li key={x.id} className="flex items-start justify-between gap-2 py-2"><span><Badge tone={x.kind === "complaint" ? "warn" : "info"}>{x.kind}</Badge> <b>{x.name}</b> {"★".repeat(x.rating)} {x.email && <span className="text-xs text-slate-500">{x.email}</span>}<br />{x.message}</span>
          {x.kind === "feedback" && <button className="btn-ghost py-1" onClick={() => toggle(x)}>{x.public ? "Hide from website" : "Show on website"}</button>}</li>)}</ul>
      </Card>
    </>
  );
}
