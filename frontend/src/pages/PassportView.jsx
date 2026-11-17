// Clinician: the passport opened from a scanned QR (/passport/:token). Needs a verified clinical login.
import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api.js";
import { useAuth } from "../auth.jsx";
import { Alert, Badge, Card } from "../components/ui.jsx";

const L = ({ items, empty = "None recorded", render }) => (items?.length ? <ul className="space-y-1 text-sm">{items.map((x, i) => <li key={i}>{render(x)}</li>)}</ul> : <p className="text-sm text-slate-500">{empty}</p>);

export default function PassportView() {
  const { token } = useParams();
  const { user } = useAuth();
  const [p, setP] = useState(null);
  const [err, setErr] = useState("");
  useEffect(() => { api(`/passport/open/${encodeURIComponent(token)}`).then(setP).catch((e) => setErr(e.message)); }, [token]);
  if (user?.role === "patient") return <Alert tone="warn">This is a Health Passport link. Only verified doctors, hospital staff and nurses can open it. <Link className="underline" to="/passport">Go to my passport</Link></Alert>;
  if (err) return <Alert tone="error">{err}</Alert>;
  if (!p) return <p className="text-slate-500">Opening passport…</p>;
  const a = p.patient;
  return (
    <>
      <div className="rounded-xl bg-red-600 p-4 text-white">
        <p className="text-xs uppercase tracking-wide">Smart Health Passport</p>
        <div className="flex items-center gap-3">{a.photo_url && <img src={a.photo_url} alt="" className="h-16 w-16 rounded-xl border-2 border-white/70 object-cover" referrerPolicy="no-referrer" />}<p className="text-2xl font-bold">{a.name}</p></div>
        <p className="text-sm">{[a.age != null && `${a.age} yrs`, a.sex, `Health ID ${a.health_id}`].filter(Boolean).join(" · ")}</p>
        <p className="mt-1 text-lg">Blood group: <b className="text-2xl">{a.blood_group || "unknown"}</b></p>
      </div>
      <Alert tone="warn">{p.note}</Alert>
      <div className="grid gap-4 md:grid-cols-2">
        <Card title="⚠ Allergies"><L items={p.allergies} render={(x) => <><b>{x.name}</b> {x.severity && <Badge tone="bad">{x.severity}</Badge>} {x.reaction && <span className="text-slate-500">{x.reaction}</span>}</>} /></Card>
        <Card title="Medical history / conditions"><L items={p.conditions} render={(x) => <><b>{x.name}</b> {x.since && <span className="text-slate-500">since {x.since}</span>} {x.notes && <span className="text-slate-500">{x.notes}</span>}</>} /></Card>
        <Card title="Current medicines"><L items={p.medicines} empty="No active medicines" render={(m) => <><b>{m.name}</b> {m.dose} <span className="text-slate-500">{(m.times || []).join(", ")}{m.instructions ? ` · ${m.instructions}` : ""}</span></>} /></Card>
        <Card title="Surgeries"><L items={p.surgeries} render={(x) => <><b>{x.name}</b> {x.date && <span className="text-slate-500">{x.date}</span>}</>} /></Card>
        <Card title="Recent prescriptions"><L items={p.prescriptions} render={(r) => <div className="rounded border border-slate-100 p-2"><b>{r.date}</b> · Dr. {r.doctor} · {r.diagnosis}<ul className="ml-4 list-disc text-slate-600">{r.items.map((i, k) => <li key={k}>{i.name} {i.dose} {(i.times || []).join("/")} {i.days ? `· ${i.days} days` : ""}</li>)}</ul></div>} /></Card>
        <Card title="Latest vitals">{p.latest_vitals ? <ul className="text-sm text-slate-700">{Object.entries(p.latest_vitals).filter(([k, v]) => !["id", "patient_id", "ts", "source", "device_id"].includes(k) && v != null && typeof v !== "object").map(([k, v]) => <li key={k}>{k.replace(/_/g, " ")}: <b>{String(v)}</b></li>)}<li className="text-xs text-slate-500">{p.latest_vitals.ts}</li></ul> : <p className="text-sm text-slate-500">No readings</p>}</Card>
        {p.viewer_role !== "nurse" && <Card title="Recent lab reports (abnormal values)"><L items={p.recent_reports} render={(r) => <div><b>{r.title}</b> <span className="text-slate-500">{r.date}</span>{r.abnormal.length ? <ul className="ml-4 list-disc">{r.abnormal.map((f, k) => <li key={k}>{f.test}: {f.value} {f.unit} <Badge tone="warn">{f.status}</Badge></li>)}</ul> : <p className="text-slate-500">All values normal</p>}</div>} /></Card>}
        <Card title="Vaccinations"><L items={p.vaccinations} render={(x) => <><b>{x.name}</b> {x.date && <span className="text-slate-500">{x.date}</span>}</>} /></Card>
        <Card title="Emergency contacts"><L items={p.emergency_contacts} render={(c) => <>{c.name} ({c.relation}) · <a className="font-semibold text-brand-700 underline" href={`tel:${c.phone}`}>{c.phone}</a></>} /></Card>
      </div>
      <p className="text-xs text-slate-500">Valid until {new Date(p.token_expires_at).toLocaleString()}. This access was recorded.</p>
    </>
  );
}
