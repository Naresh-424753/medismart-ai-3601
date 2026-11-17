// Small photo uploader: choose a photo from the phone/computer, it is uploaded and onDone(url) receives the public link.
import { useRef, useState } from "react";
import { api } from "../api.js";

export default function PhotoUpload({ value, onDone, label = "Upload photo" }) {
  const ref = useRef(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const pick = async (e) => {
    const f = e.target.files?.[0];
    e.target.value = "";
    if (!f) return;
    if (!f.type.startsWith("image/")) { setErr("Choose an image file (JPG, PNG or WebP)."); return; }
    if (f.size > 6 * 1024 * 1024) { setErr("Photo is larger than 6 MB."); return; }
    setBusy(true); setErr("");
    try {
      const form = new FormData();
      form.append("file", f);
      const r = await api("/media/upload", { method: "POST", form });
      onDone(r.url);
    } catch (x) { setErr(x.message || "Upload failed"); }
    setBusy(false);
  };
  return (
    <div className="flex items-center gap-3">
      {value ? <img src={value} alt="" className="h-14 w-14 rounded-full object-cover" referrerPolicy="no-referrer" /> : <div className="flex h-14 w-14 items-center justify-center rounded-full bg-slate-100 text-xl text-slate-400">📷</div>}
      <div>
        <input ref={ref} type="file" accept="image/jpeg,image/png,image/webp" className="hidden" onChange={pick} />
        <button type="button" className="btn-ghost py-1" disabled={busy} onClick={() => ref.current?.click()}>{busy ? "Uploading…" : label}</button>
        {value && <button type="button" className="ml-2 text-xs text-slate-500 underline" onClick={() => onDone("")}>Remove</button>}
        {err && <p className="text-xs text-red-600">{err}</p>}
      </div>
    </div>
  );
}
