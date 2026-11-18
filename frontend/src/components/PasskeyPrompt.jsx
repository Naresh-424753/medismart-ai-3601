import { useEffect, useState } from "react";
import { api } from "../api.js";
import { deviceName, passkeySupported, registerPasskey } from "../passkey.js";

const KEY = "ms_pk_prompt_dismissed";
const read = () => { try { return localStorage.getItem(KEY); } catch { return null; } };

// One-tap banner after login: "Turn on fingerprint / face login" for devices that have none registered.
export default function PasskeyPrompt() {
  const [show, setShow] = useState(false);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  useEffect(() => {
    if (!passkeySupported() || read()) return;
    api("/auth/passkey").then((keys) => setShow(Array.isArray(keys) && keys.length === 0)).catch(() => {});
  }, []);
  if (!show) return null;
  const dismiss = () => { try { localStorage.setItem(KEY, "1"); } catch {} setShow(false); };
  const enable = async () => {
    setBusy(true); setMsg("");
    try { await registerPasskey(deviceName()); setMsg("Done! Next time use 'Login with fingerprint / face' on the login page."); setTimeout(() => setShow(false), 3500); }
    catch (e) { setMsg(e.message || "Could not set up. Open My Health > Security to try again."); }
    finally { setBusy(false); }
  };
  return (
    <div className="mb-4 flex flex-wrap items-center justify-between gap-2 rounded-xl border border-blue-200 bg-blue-50 p-3 text-sm text-blue-900">
      <span>🔐 <b>Log in faster:</b> turn on fingerprint / face login for this device.{msg && <span className="ml-2 font-medium">{msg}</span>}</span>
      <span className="flex gap-2">
        <button className="btn-primary py-1" disabled={busy} onClick={enable}>{busy ? "Waiting..." : "Turn on"}</button>
        <button className="btn-ghost py-1" onClick={dismiss}>Not now</button>
      </span>
    </div>
  );
}
