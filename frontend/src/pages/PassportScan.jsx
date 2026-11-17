// Clinician: scan a patient's Health Passport QR with the camera (or paste the link) and open it.
import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Alert, Card } from "../components/ui.jsx";

const tokenOf = (s) => { const m = String(s).match(/passport\/([A-Za-z0-9_-]{20,})/); return m ? m[1] : /^[A-Za-z0-9_-]{20,}$/.test(String(s).trim()) ? String(s).trim() : null; };

export default function PassportScan() {
  const nav = useNavigate();
  const video = useRef(null);
  const [on, setOn] = useState(false);
  const [paste, setPaste] = useState("");
  const [err, setErr] = useState("");
  const supported = typeof window !== "undefined" && "BarcodeDetector" in window && !!navigator.mediaDevices?.getUserMedia;
  const open = (s) => { const t = tokenOf(s); if (!t) { setErr("This is not a Health Passport QR."); return false; } nav(`/passport/${t}`); return true; };
  useEffect(() => {
    if (!on) return undefined;
    let stop = false, stream, timer;
    (async () => {
      try {
        stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" } });
        video.current.srcObject = stream; await video.current.play();
        const det = new window.BarcodeDetector({ formats: ["qr_code"] });
        const tick = async () => {
          if (stop) return;
          try { const r = await det.detect(video.current); if (r[0] && open(r[0].rawValue)) return; } catch { /* keep scanning */ }
          timer = setTimeout(tick, 350);
        };
        tick();
      } catch { setErr("Camera not available. Allow camera access, or paste the link below."); setOn(false); }
    })();
    return () => { stop = true; clearTimeout(timer); stream?.getTracks().forEach((t) => t.stop()); };
  }, [on]);
  return (
    <>
      <h1 className="text-xl font-bold">Scan Health Passport</h1>
      <Alert tone="error">{err}</Alert>
      <Card title="Scan the patient's QR">
        {supported ? (on ? <div><video ref={video} className="mx-auto w-full max-w-sm rounded-lg bg-black" playsInline muted /><button className="btn-ghost mt-2" onClick={() => setOn(false)}>Stop camera</button></div> : <button className="btn-primary" onClick={() => { setErr(""); setOn(true); }}>📷 Start camera</button>)
          : <p className="text-sm text-slate-600">This browser cannot scan inside the app. Use your phone's normal camera app to scan the QR: it opens the passport link here (log in when asked). Or paste the link below.</p>}
      </Card>
      <Card title="Or paste the QR link">
        <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); open(paste); }}><input className="input" placeholder="https://…/passport/…" value={paste} onChange={(e) => setPaste(e.target.value)} /><button className="btn-primary" disabled={!paste.trim()}>Open</button></form>
      </Card>
    </>
  );
}
