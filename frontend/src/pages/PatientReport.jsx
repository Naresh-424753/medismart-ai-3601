import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api.js";
import { Alert } from "../components/ui.jsx";

// Lab-style layout: Test Name | Result | Unit | Biological Ref Interval, grouped under department headings.
const SECTIONS = [
  ["HAEMATOLOGY", "Complete blood count", ["hemoglobin", "wbc", "rbc", "platelets", "hematocrit", "rdw_cv", "rdw_sd", "mpv", "esr"]],
  ["BIOCHEMISTRY", "Liver function test (LFT)", ["bilirubin", "ast", "alt", "alp", "albumin", "ggt"]],
  ["BIOCHEMISTRY", "Kidney function test (KFT)", ["bun", "urea", "creatinine", "egfr", "uric_acid", "calcium", "sodium", "potassium"]],
  ["BIOCHEMISTRY", "Diabetes / blood sugar", ["glucose_fasting", "glucose_pp", "hba1c"]],
  ["BIOCHEMISTRY", "Lipid profile", ["total_cholesterol", "ldl", "hdl", "triglycerides"]],
  ["BIOCHEMISTRY", "Inflammation", ["crp"]],
  ["IMMUNOASSAY", "Thyroid profile", ["tsh", "t3", "t4"]],
  ["IMMUNOASSAY", "Vitamins", ["vitamin_d", "vitamin_b12"]],
  ["CLINICAL PATHOLOGY", "Urine examination", ["urine_ph", "urine_protein", "urine_specific_gravity", "pus_cells"]],
];
const fmt = (n) => (typeof n === "number" && n >= 1000 ? n.toLocaleString("en-IN") : n);
const dt = (s) => (s ? new Date(s).toLocaleString("en-IN", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit", hour12: false }) : "");

function Row({ a, b }) {
  return <div className="flex gap-2"><span className="w-36 shrink-0 text-slate-600">{a}</span><span>: {b || ""}</span></div>;
}

export default function PatientReport() {
  const { rid } = useParams();
  const [d, setD] = useState(null);
  const [err, setErr] = useState("");
  const [ecg, setEcg] = useState({ heart_rate: "", pr_ms: "", qrs_ms: "", qt_ms: "", qtc_ms: "", machine_conclusion: "" });
  const [peaks, setPeaks] = useState([{ peak: "A1c", r_time: "", area_pct: "" }]);
  const [msg, setMsg] = useState("");
  const load = () => api(`/reports/${rid}/full`).then(setD).catch((e) => setErr(e.message || "Could not load the report"));
  useEffect(() => { load(); }, [rid]);
  const num = (v) => (v === "" ? undefined : Number(v));
  const saveEcg = async (e) => {
    e.preventDefault(); setMsg("");
    try { await api(`/reports/${rid}/ecg`, { method: "PUT", body: { heart_rate: num(ecg.heart_rate), pr_ms: num(ecg.pr_ms), qrs_ms: num(ecg.qrs_ms), qt_ms: num(ecg.qt_ms), qtc_ms: num(ecg.qtc_ms), machine_conclusion: ecg.machine_conclusion } }); setMsg("ECG saved."); load(); } catch (x) { setMsg(x.message || "Could not save ECG"); }
  };
  const saveChrom = async (e) => {
    e.preventDefault(); setMsg("");
    try { await api(`/reports/${rid}/chromatogram`, { method: "PUT", body: { peaks: peaks.filter((p) => p.peak && p.area_pct !== "").map((p) => ({ peak: p.peak, r_time: num(p.r_time), area_pct: Number(p.area_pct) })) } }); setMsg("Chromatogram saved."); load(); } catch (x) { setMsg(x.message || "Could not save chromatogram"); }
  };
  if (err) return <Alert tone="error">{err}</Alert>;
  if (!d) return <p className="text-sm text-slate-500">Loading…</p>;
  const { report: r, patient: p } = d;
  const by = Object.fromEntries((r.findings || []).map((f) => [f.key, f]));
  const used = new Set();
  const groups = [];
  for (const [dept, title, keys] of SECTIONS) {
    const rows = keys.filter((k) => by[k]).map((k) => { used.add(k); return by[k]; });
    if (rows.length) groups.push({ dept, title, rows });
  }
  const other = (r.findings || []).filter((f) => !used.has(f.key));
  if (other.length) groups.push({ dept: "OTHER", title: "Other tests", rows: other });
  const abnormal = (r.findings || []).filter((f) => f.status !== "normal");
  let lastDept = "";

  return (
    <>
      <div className="no-print mb-3 flex flex-wrap items-center gap-2">
        <Link className="btn-ghost" to="/reports">← Back</Link>
        <button className="btn-primary" onClick={() => window.print()}>🖨 Print / Save as PDF</button>
        <span className="text-xs text-slate-500">In the print window choose “Save as PDF”.</span>
      </div>
      {msg && <p className="no-print mb-2 text-sm text-slate-600">{msg}</p>}
      <details className="no-print mb-2 rounded-lg border border-slate-200 bg-white p-3 text-sm">
        <summary className="cursor-pointer font-medium">Add / edit ECG (type the values printed on your ECG strip)</summary>
        <form onSubmit={saveEcg} className="mt-3 grid gap-2 md:grid-cols-5">
          {[["heart_rate", "Heart rate (bpm)"], ["pr_ms", "PR (ms)"], ["qrs_ms", "QRS (ms)"], ["qt_ms", "QT (ms)"], ["qtc_ms", "QTc (ms)"]].map(([k, l]) => <label key={k} className="text-xs">{l}<input className="input mt-1" type="number" step="any" value={ecg[k]} onChange={(e) => setEcg({ ...ecg, [k]: e.target.value })} /></label>)}
          <label className="text-xs md:col-span-5">Conclusion printed on the ECG<input className="input mt-1" maxLength={400} value={ecg.machine_conclusion} onChange={(e) => setEcg({ ...ecg, machine_conclusion: e.target.value })} /></label>
          <button className="btn-primary md:col-span-5">Save ECG</button>
        </form>
      </details>
      <details className="no-print mb-3 rounded-lg border border-slate-200 bg-white p-3 text-sm">
        <summary className="cursor-pointer font-medium">Add / edit HbA1c chromatogram peak table</summary>
        <form onSubmit={saveChrom} className="mt-3 space-y-2">
          {peaks.map((p, i) => (
            <div key={i} className="grid grid-cols-3 gap-2">
              <input className="input" placeholder="Peak (e.g. A1c, A0, F)" value={p.peak} onChange={(e) => setPeaks(peaks.map((x, j) => (j === i ? { ...x, peak: e.target.value } : x)))} />
              <input className="input" type="number" step="any" placeholder="R.time" value={p.r_time} onChange={(e) => setPeaks(peaks.map((x, j) => (j === i ? { ...x, r_time: e.target.value } : x)))} />
              <input className="input" type="number" step="any" placeholder="Area %" value={p.area_pct} onChange={(e) => setPeaks(peaks.map((x, j) => (j === i ? { ...x, area_pct: e.target.value } : x)))} />
            </div>
          ))}
          <div className="flex gap-2"><button type="button" className="btn-ghost" onClick={() => setPeaks([...peaks, { peak: "", r_time: "", area_pct: "" }])}>+ Add peak</button><button className="btn-primary">Save chromatogram</button></div>
        </form>
      </details>
      <div className="lab-sheet mx-auto max-w-4xl rounded-xl border border-slate-200 bg-white p-6 text-sm shadow-sm">
        <div className="flex items-center justify-between border-b-2 border-slate-800 pb-3">
          <div><p className="text-2xl font-extrabold tracking-tight text-brand-700">MediSmart AI 360</p><p className="text-xs text-slate-500">…where technology meets patient care</p></div>
          <p className="text-right text-xs text-slate-500">PATIENT HEALTH REPORT<br />{r.source === "lab" ? "Laboratory result" : "Uploaded / analysed report"}</p>
        </div>

        <div className="grid gap-x-8 gap-y-1 border-b border-slate-800 py-3 md:grid-cols-2">
          <div className="space-y-1">
            <Row a="Accession No." b={d.accession_no} />
            <Row a="Patient ID" b={p.patient_id} />
            <Row a="Patient Name" b={p.name} />
            <Row a="Sex / Age" b={`${p.sex || "—"}   ${p.age != null ? p.age + " Yrs" : ""}`} />
            <Row a="Blood group" b={p.blood_group} />
            <Row a="Report title" b={r.title} />
          </div>
          <div className="space-y-1">
            <Row a="Report date" b={r.report_date} />
            <Row a="Report released on" b={dt(d.released_at)} />
            <Row a="Verification" b={d.verified_by ? `Verified by ${d.verified_by}` : "Not lab-verified (automated reading)"} />
          </div>
        </div>

        <table className="mt-3 w-full text-left">
          <thead className="border-b border-slate-800 text-xs"><tr><th className="py-1.5">Test Name</th><th>Result</th><th>Unit</th><th>Biological Ref Interval</th></tr></thead>
          <tbody>
            {groups.map((g) => {
              const head = g.dept !== lastDept; lastDept = g.dept;
              return [
                head && <tr key={g.dept + "h"}><td colSpan={4} className="pt-4 text-center font-bold tracking-wide">{g.dept}</td></tr>,
                <tr key={g.title}><td colSpan={4} className="pt-2 font-bold">{g.title}</td></tr>,
                ...g.rows.map((f) => (
                  <tr key={f.key} className="align-top">
                    <td className="py-1 pr-2">{f.test}</td>
                    <td className={f.status !== "normal" ? "font-bold" : ""}>{fmt(f.value)}{f.status !== "normal" && <span className="ml-1 text-xs">{f.status === "high" ? "H" : "L"}</span>}</td>
                    <td className="text-slate-600">{f.unit}</td>
                    <td className="text-slate-600">{fmt(f.low)} - {fmt(f.high)}</td>
                  </tr>
                )),
              ];
            })}
          </tbody>
        </table>

        {r.chromatogram && (
          <section className="mt-5">
            <p className="text-center font-bold tracking-wide">HbA1c CHROMATOGRAM ({r.chromatogram.method})</p>
            <table className="mt-1 w-full text-left"><thead className="border-b text-xs"><tr><th>Peak</th><th>R.time</th><th>Area %</th><th /></tr></thead>
              <tbody>{r.chromatogram.peaks.map((p, i) => <tr key={i}><td className={String(p.peak).toLowerCase() === "a1c" ? "font-bold" : ""}>{p.peak}</td><td>{p.r_time ?? ""}</td><td>{p.area_pct}</td><td className="w-1/2"><div className="h-2 rounded bg-brand-600" style={{ width: `${Math.min(100, p.area_pct)}%` }} /></td></tr>)}</tbody></table>
            <p className="mt-1 text-xs text-slate-600">Peak areas total {r.chromatogram.check.total_pct}%{r.chromatogram.check.ok ? "" : " (should be about 100%, please re-check the entries)"}. The graph is a bar view of the entered peak table, not the instrument trace.</p>
          </section>
        )}
        {r.ecg && (
          <section className="mt-5">
            <p className="text-center font-bold tracking-wide">ECG</p>
            <div className="mt-1 grid grid-cols-2 gap-x-6 md:grid-cols-5">
              {[["Heart rate", r.ecg.heart_rate, "bpm"], ["PR", r.ecg.pr_ms, "ms"], ["QRS", r.ecg.qrs_ms, "ms"], ["QT", r.ecg.qt_ms, "ms"], ["QTc", r.ecg.qtc_ms, "ms"]].filter((x) => x[1] != null).map(([l, v, u]) => <div key={l}><span className="text-slate-600">{l}: </span><b>{v} {u}</b></div>)}
            </div>
            {r.ecg.machine_conclusion && <p className="mt-1"><b>ECG conclusion (as printed):</b> {r.ecg.machine_conclusion}</p>}
            {r.ecg.check.flags.length > 0 ? <ul className="mt-1 list-disc pl-5">{r.ecg.check.flags.map((f) => <li key={f}>{f}</li>)}</ul> : <p className="mt-1 text-slate-600">Entered intervals are within the usual adult limits.</p>}
            <p className="mt-1 text-xs italic text-slate-500">Interval flags are only a general check. An ECG must be read by a doctor; please correlate clinically.</p>
          </section>
        )}
        <section className="mt-5">
          <p className="font-bold">Interpretation</p>
          <p className="mt-1">{r.summary}</p>
          {abnormal.length > 0 && <ul className="mt-1 list-disc space-y-0.5 pl-5">{abnormal.map((f) => <li key={f.key}><b>{f.test}:</b> {f.note}</li>)}</ul>}
          {r.comparison?.length > 0 && <p className="mt-2 text-slate-600"><b>Compared with previous:</b> {r.comparison.map((c) => `${c.test} ${fmt(c.previous)} → ${fmt(c.current)} (${c.trend})`).join("; ")}</p>}
          <p className="mt-2 text-xs italic text-slate-500">Notes: The result relates only to the sample given and tested. A single test result is not always indicative of a disease; it has to be correlated with clinical data. H = above range, L = below range. Kindly correlate clinically.</p>
        </section>

        <div className="mt-8 flex items-end justify-between">
          <p className="text-xs text-slate-500">*** End of Report ***</p>
          <div className="text-right">
            <p className="font-semibold">{d.verified_by || "Automated analysis"}</p>
            <p className="text-xs text-slate-600">{d.verified_by ? "Verified laboratory staff, MediSmart network" : "Not signed by a pathologist"}</p>
          </div>
        </div>
        <p className="mt-4 border-t pt-2 text-xs text-slate-500">{d.disclaimer}</p>
      </div>
    </>
  );
}
