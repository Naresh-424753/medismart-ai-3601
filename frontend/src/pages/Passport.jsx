// Patient: Smart Health Passport QR. Doctors / hospital staff scan it and log in to see the full medical summary.
import { useEffect, useRef, useState } from "react";
import { QRCodeCanvas } from "qrcode.react";
import { api } from "../api.js";
import { Alert, Badge, Card, Field, useAsync } from "../components/ui.jsx";

const DAYS = [[1, "24 hours"], [7, "7 days"], [30, "30 days"], [365, "1 year"]];

export default function Passport() {
  const [d, setD] = useState(null);
  const [days, setDays] = useState(30);
  const [msg, setMsg] = useState("");
  const box = useRef(null);
  const { error, run, busy } = useAsync();
  const load = () => run(async () => setD(await api("/passport/me")));
  useEffect(() => { load(); }, []);
  const issue = () => run(async () => { await api("/passport/token", { method: "POST", body: { days: +days } }); setMsg("New Health Passport QR created. The old QR no longer works."); load(); });
  const revoke = () => { if (!window.confirm("Stop this QR from working?")) return; run(async () => { await api("/passport/token", { method: "DELETE" }); setMsg("Health Passport QR switched off."); load(); }); };
  const link = d?.token ? `${window.location.origin}/passport/${d.token}` : "";
  const save = () => { const c = box.current?.querySelector("canvas"); if (!c) return; const a = document.createElement("a"); a.href = c.toDataURL("image/png"); a.download = "health-passport-qr.png"; a.click(); };
  return (
    <>
      <h1 className="text-xl font-bold">Smart Health Passport</h1>
      <Alert tone="error">{error}</Alert><Alert tone="ok">{msg}</Alert>
      <div className="grid gap-4 md:grid-cols-2">
        <Card title="Your QR code">
          {d?.active ? (
            <div className="flex flex-col items-center gap-2">
              <div ref={box} className="rounded-xl border bg-white p-3"><QRCodeCanvas value={link} size={220} includeMargin /></div>
              <p className="text-sm font-semibold">Health ID {d.health_id}</p>
              <p className="text-xs text-slate-500">Valid until {new Date(d.expires_at).toLocaleString()}</p>
              <div className="flex flex-wrap justify-center gap-2"><button className="btn-primary py-1" onClick={save}>Save QR image</button><button className="btn-ghost py-1" onClick={() => window.print()}>Print</button><button className="btn-ghost py-1 text-red-700" onClick={revoke}>Switch off</button></div>
              <p className="text-center text-xs text-slate-500">Keep this image on your phone lock screen or print it for your wallet.</p>
            </div>
          ) : <p className="text-sm text-slate-600">{d?.needs_regenerate ? "Your QR needs to be created again." : "You have no active Health Passport QR yet."}</p>}
          <div className="mt-4 flex items-end gap-2 border-t pt-3">
            <Field label="Valid for"><select className="input" value={days} onChange={(e) => setDays(e.target.value)}>{DAYS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select></Field>
            <button className="btn-primary" disabled={busy} onClick={issue}>{d?.active ? "Regenerate QR" : "Create QR"}</button>
          </div>
        </Card>
        <Card title="How it works">
          <ul className="list-disc space-y-1 pl-5 text-sm text-slate-700">
            <li>A doctor at any hospital scans the QR and <b>logs in</b> with an admin-verified MediSmart doctor, hospital or nurse account.</li>
            <li>They see your blood group, allergies, conditions, surgeries, vaccinations, current medicines, recent prescriptions, latest vitals and abnormal lab results.</li>
            <li>A nurse sees less (no lab reports). People without a verified account see nothing.</li>
            <li>You see every access below and get a notification. <b>Regenerate</b> if you lose your phone, <b>switch off</b> any time.</li>
            <li>The emergency card in My Health stays separate: it shows only blood group, allergies and contacts to anyone, even without login.</li>
          </ul>
        </Card>
      </div>
      <Card title="Who opened my passport">
        {d && !d.views.length && <p className="text-sm text-slate-500">Nobody yet.</p>}
        <ul className="divide-y divide-slate-100 text-sm">{d?.views.map((v) => <li key={v.id} className="flex items-center justify-between py-1.5"><span>{v.viewer_name} <Badge>{v.viewer_role}</Badge></span><span className="text-xs text-slate-500">{new Date(v.ts).toLocaleString()}</span></li>)}</ul>
      </Card>
    </>
  );
}
