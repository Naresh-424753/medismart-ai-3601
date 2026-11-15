// Public "Get the app" page: install the PWA on Android / iPhone / desktop, with a QR code to open it on a phone.
import { useEffect, useState } from "react";
import { QRCodeSVG } from "qrcode.react";
import { Link } from "react-router-dom";

export default function Install() {
  const [evt, setEvt] = useState(null);
  const [done, setDone] = useState(false);
  const url = typeof window !== "undefined" ? window.location.origin : "";
  const ua = typeof navigator !== "undefined" ? navigator.userAgent : "";
  const ios = /iPhone|iPad|iPod/i.test(ua);
  const standalone = typeof window !== "undefined" && (window.matchMedia?.("(display-mode: standalone)").matches || navigator.standalone);
  useEffect(() => {
    const on = (e) => { e.preventDefault(); setEvt(e); };
    const ins = () => setDone(true);
    window.addEventListener("beforeinstallprompt", on); window.addEventListener("appinstalled", ins);
    return () => { window.removeEventListener("beforeinstallprompt", on); window.removeEventListener("appinstalled", ins); };
  }, []);
  const install = async () => { if (!evt) return; evt.prompt(); await evt.userChoice.catch(() => {}); setEvt(null); };
  return (
    <div className="mx-auto max-w-3xl space-y-6 px-4 py-10">
      <div className="text-center">
        <img src="/icon-192.png" alt="" className="mx-auto h-20 w-20 rounded-2xl shadow" />
        <h1 className="mt-3 text-2xl font-bold text-brand-700">Get the MediSmart AI 360 app</h1>
        <p className="mt-1 text-sm text-slate-600">Free. Works on Android, iPhone and computers. No app store needed.</p>
      </div>
      {standalone || done ? <p className="rounded-lg bg-emerald-50 p-4 text-center text-emerald-800">✔ The app is installed on this device.</p>
        : evt ? <button className="btn-primary mx-auto block px-6 py-3 text-lg" onClick={install}>⬇ Install app</button>
          : <p className="rounded-lg bg-slate-100 p-3 text-center text-sm text-slate-600">{ios ? "On iPhone use the steps below (Safari)." : "If no Install button appears, follow the steps below for your phone."}</p>}
      <div className="grid gap-4 md:grid-cols-2">
        <div className="card"><b>🤖 Android (Chrome)</b><ol className="mt-2 list-decimal space-y-1 pl-5 text-sm text-slate-700"><li>Open this site in Chrome.</li><li>Tap the <b>⋮</b> menu, then <b>Install app</b> (or <b>Add to Home screen</b>).</li><li>Tap <b>Install</b>. The MediSmart icon appears on your home screen.</li></ol></div>
        <div className="card"><b>🍎 iPhone / iPad (Safari)</b><ol className="mt-2 list-decimal space-y-1 pl-5 text-sm text-slate-700"><li>Open this site in <b>Safari</b> (not Chrome).</li><li>Tap the <b>Share</b> button (square with arrow).</li><li>Choose <b>Add to Home Screen</b>, then <b>Add</b>.</li></ol></div>
        <div className="card"><b>💻 Computer (Chrome / Edge)</b><p className="mt-2 text-sm text-slate-700">Click the install icon at the right end of the address bar, then <b>Install</b>.</p></div>
        <div className="card text-center"><b>📱 Open on your phone</b><div className="mt-2 flex justify-center"><QRCodeSVG value={url} size={130} /></div><p className="mt-1 break-all text-xs text-slate-500">{url}</p></div>
      </div>
      <p className="text-center text-sm"><Link className="text-brand-700 underline" to="/login">Login / Register</Link> · <Link className="text-brand-700 underline" to="/hospital">Hospital website</Link></p>
    </div>
  );
}
