// Patient: hospital bills, UPI QR payment, receipt download, insurance details.
import { useEffect, useState } from "react";
import { QRCodeSVG } from "qrcode.react";
import { api, download } from "../api.js";
import { Alert, Badge, Card, Empty, Field, Stat, useAsync } from "../components/ui.jsx";

export default function Bills() {
  const [d, setD] = useState(null);
  const [qr, setQr] = useState(null); // { id, info, utr }
  const [ins, setIns] = useState({ provider: "", policy_no: "", tpa: "", valid_till: "" });
  const [msg, setMsg] = useState("");
  const { error, run, busy } = useAsync();
  const load = () => run(async () => { const r = await api("/site/my-bills"); setD(r); setIns({ provider: "", policy_no: "", tpa: "", valid_till: "", ...r.insurance }); });
  useEffect(() => { load(); }, []);
  const showQr = (id) => run(async () => setQr({ id, info: await api(`/site/my-bills/${id}/pay`), utr: "" }));
  const report = (id) => run(async () => { await api(`/site/my-bills/${id}/pay`, { method: "POST", body: { utr: qr.utr } }); setQr(null); setMsg("Thanks. The bill turns PAID once the hospital confirms your payment."); load(); });
  const saveIns = (e) => { e.preventDefault(); run(async () => { await api("/site/my-insurance", { method: "PUT", body: ins }); setMsg("Insurance details saved."); }); };
  return (
    <>
      <h1 className="text-xl font-bold">Bills & payments</h1>
      <Alert tone="error">{error}</Alert><Alert tone="ok">{msg}</Alert>
      {d && <div className="grid grid-cols-2 gap-4 md:grid-cols-3"><Stat label="Pending amount (₹)" value={d.pending_total} /><Stat label="Bills" value={d.bills.length} /></div>}
      <Card title="Hospital bills">
        {d && !d.bills.length && <Empty>No bills yet. The hospital adds your bill using your Health ID.</Empty>}
        <ul className="divide-y divide-slate-100 text-sm">
          {d?.bills.map((b) => (
            <li key={b.id} className="py-2">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span><b>{b.hospital_name}</b> · {b.created_at.slice(0, 10)} · ₹{b.total}<br /><span className="text-xs text-slate-500">{b.items.map((i) => `${i.name} ₹${i.amount}`).join(", ")}</span></span>
                {b.status === "paid" ? <span className="flex items-center gap-2"><Badge tone="good">paid</Badge><button className="btn-ghost py-1" onClick={() => download(`/site/my-bills/${b.id}/receipt`, `receipt-${b.id.slice(0, 8)}.pdf`).catch((e) => setMsg(e.message))}>Receipt PDF</button></span>
                  : <span className="flex items-center gap-2"><Badge tone="warn">{b.utr ? "awaiting hospital confirmation" : "unpaid"}</Badge>{!b.utr && <button className="btn-primary py-1" onClick={() => (qr?.id === b.id ? setQr(null) : showQr(b.id))}>Pay with QR</button>}</span>}
              </div>
              {qr?.id === b.id && (
                <div className="mt-2 flex flex-col items-center gap-2 rounded-lg border border-slate-200 p-3">
                  <QRCodeSVG value={qr.info.upi_uri} size={170} />
                  <p className="text-center text-xs">Scan with GPay / PhonePe / Paytm and pay <b>₹{qr.info.amount}</b> to <b>{qr.info.payee}</b> ({qr.info.vpa})</p>
                  {qr.info.demo && <p className="text-xs text-amber-700">Demo QR: this hospital has no UPI ID set, so scanning cannot move money.</p>}
                  <div className="flex w-full gap-2"><input className="input" inputMode="numeric" maxLength={12} placeholder="12-digit UPI ref (UTR) after paying" value={qr.utr} onChange={(e) => setQr({ ...qr, utr: e.target.value.replace(/\D/g, "") })} />
                    <button className="btn-primary py-1" disabled={busy || qr.utr.length !== 12} onClick={() => report(b.id)}>I have paid</button></div>
                  <p className="text-xs text-slate-500">The bill shows PAID only after the hospital checks its UPI app and confirms.</p>
                </div>)}
            </li>))}
        </ul>
      </Card>
      <Card title="Health insurance information">
        <form onSubmit={saveIns} className="grid gap-3 md:grid-cols-4">
          <Field label="Insurance company"><input className="input" value={ins.provider} onChange={(e) => setIns({ ...ins, provider: e.target.value })} /></Field>
          <Field label="Policy number"><input className="input" value={ins.policy_no} onChange={(e) => setIns({ ...ins, policy_no: e.target.value })} /></Field>
          <Field label="TPA"><input className="input" value={ins.tpa} onChange={(e) => setIns({ ...ins, tpa: e.target.value })} /></Field>
          <Field label="Valid till"><input className="input" type="date" value={ins.valid_till} onChange={(e) => setIns({ ...ins, valid_till: e.target.value })} /></Field>
          <div className="md:col-span-4"><button className="btn-primary" disabled={busy}>Save insurance</button></div>
        </form>
      </Card>
    </>
  );
}
