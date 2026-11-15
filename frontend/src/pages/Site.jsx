// Public hospital website (no login): departments, doctors + slots, packages, insurance, emergency, blog, gallery, feedback, contact & map.
import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api.js";
import { useAuth } from "../auth.jsx";
import { Alert, Badge, useAsync } from "../components/ui.jsx";

const T = {
  en: { home: "Home", doctors: "Find a Doctor", departments: "Departments", packages: "Health Packages", insurance: "Insurance / TPA", emergency: "Emergency", blog: "Health Blog", gallery: "Gallery", feedback: "Feedback", contact: "Contact", login: "Login / Register", portal: "My portal",
    book: "Book appointment", search: "Search doctor, specialization…", slots: "Next available slots", noslots: "No free slots this week", fee: "Fee", yrs: "yrs", call: "Call now", ambulance: "Ambulance", helpline: "Emergency helpline",
    visiting: "Visiting hours", opd: "OPD hours", parking: "Parking", address: "Address", whatsapp: "WhatsApp enquiry", map: "Open in Google Maps", send: "Send", name: "Your name", email: "Email (optional)", msg: "Your message",
    insq: "Check if your insurer is accepted", accepted: "Accepted", notlisted: "Not in our list. Please call the billing desk to confirm.", chat: "Live chat with reception", pharm: "Pharmacy & medicines", blood: "Blood bank", includes: "Includes",
    feedbackKind: "Type", fb: "Feedback", cp: "Complaint", rating: "Rating", reviews: "Patient reviews", lang: "हिंदी" },
  hi: { home: "होम", doctors: "डॉक्टर खोजें", departments: "विभाग", packages: "हेल्थ पैकेज", insurance: "बीमा / TPA", emergency: "आपातकाल", blog: "हेल्थ ब्लॉग", gallery: "गैलरी", feedback: "फीडबैक", contact: "संपर्क", login: "लॉगिन / रजिस्टर", portal: "मेरा पोर्टल",
    book: "अपॉइंटमेंट बुक करें", search: "डॉक्टर या विशेषज्ञता खोजें…", slots: "अगले उपलब्ध समय", noslots: "इस हफ्ते कोई स्लॉट खाली नहीं", fee: "फीस", yrs: "साल", call: "अभी कॉल करें", ambulance: "एम्बुलेंस", helpline: "इमरजेंसी हेल्पलाइन",
    visiting: "मिलने का समय", opd: "OPD समय", parking: "पार्किंग", address: "पता", whatsapp: "WhatsApp पर पूछें", map: "Google Maps में खोलें", send: "भेजें", name: "आपका नाम", email: "ईमेल (वैकल्पिक)", msg: "आपका संदेश",
    insq: "देखें आपकी बीमा कंपनी स्वीकार है या नहीं", accepted: "स्वीकार्य", notlisted: "सूची में नहीं है। कृपया बिलिंग डेस्क पर कॉल करके पूछें।", chat: "रिसेप्शन से चैट करें", pharm: "फार्मेसी और दवाइयाँ", blood: "ब्लड बैंक", includes: "शामिल",
    feedbackKind: "प्रकार", fb: "फीडबैक", cp: "शिकायत", rating: "रेटिंग", reviews: "मरीजों की राय", lang: "English" },
};
const ICON = { heart: "❤️", brain: "🧠", bone: "🦴", baby: "👶", female: "🤰", tooth: "🦷", plus: "➕" };
const telHref = (n) => `tel:${String(n || "").replace(/[^\d+]/g, "")}`;

export default function Site() {
  const { user } = useAuth();
  const [lang, setLang] = useState(() => { try { return localStorage.getItem("site_lang") || "en"; } catch { return "en"; } });
  const t = T[lang];
  const [c, setC] = useState(null);
  const [docs, setDocs] = useState([]);
  const [dq, setDq] = useState("");
  const [ins, setIns] = useState("");
  const [fb, setFb] = useState({ name: "", email: "", rating: 5, kind: "feedback", message: "" });
  const [fbOk, setFbOk] = useState("");
  const { error, run, busy } = useAsync();
  useEffect(() => { api("/site/home").then(setC).catch(() => setC({ name: "Hospital", departments: [], packages: [], insurers: [], blog: [], gallery: [], feedback: [] })); }, []);
  useEffect(() => { const h = setTimeout(() => api(`/site/doctors?${new URLSearchParams(dq ? { q: dq } : {})}`).then(setDocs).catch(() => {}), 250); return () => clearTimeout(h); }, [dq]);
  const setL = (l) => { setLang(l); try { localStorage.setItem("site_lang", l); } catch { /* ignore */ } };
  const insMatch = useMemo(() => (ins.trim() && c ? c.insurers.filter((x) => x.toLowerCase().includes(ins.trim().toLowerCase())) : null), [ins, c]);
  if (!c) return <p className="p-8 text-center text-slate-500">Loading…</p>;
  const sendFb = (e) => { e.preventDefault(); run(async () => { const r = await api("/site/feedback", { method: "POST", body: { ...fb, rating: +fb.rating } }); setFbOk(r.message); setFb({ ...fb, message: "" }); }); };
  const wa = c.whatsapp ? `https://wa.me/${c.whatsapp}?text=${encodeURIComponent("Hello, I have an enquiry.")}` : "";
  const bookTo = user ? "/appointments" : "/login";
  const Sec = ({ id, title, children }) => <section id={id} className="mx-auto max-w-6xl scroll-mt-20 px-4 py-8"><h2 className="mb-4 text-xl font-bold text-brand-700">{title}</h2>{children}</section>;
  return (
    <div className="min-h-screen bg-white text-slate-800">
      <header className="sticky top-0 z-30 border-b bg-white/95 backdrop-blur">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-2 px-4 py-2">
          <a href="#top" className="text-lg font-bold text-brand-700">{c.name}</a>
          <nav className="flex flex-wrap items-center gap-3 text-sm">
            {[["doctors", t.doctors], ["departments", t.departments], ["packages", t.packages], ["emergency", t.emergency], ["contact", t.contact]].map(([id, l]) => <a key={id} href={`#${id}`} className="hover:text-brand-700">{l}</a>)}
            <button className="rounded border px-2 py-0.5 text-xs" onClick={() => setL(lang === "en" ? "hi" : "en")}>{t.lang}</button>
            <Link className="btn-primary py-1" to={user ? "/" : "/login"}>{user ? t.portal : t.login}</Link>
          </nav>
        </div>
      </header>
      <div id="top" className="bg-gradient-to-br from-brand-50 to-white">
        <div className="mx-auto max-w-6xl px-4 py-12">
          <h1 className="text-3xl font-bold text-brand-800 md:text-4xl">{c.name}</h1>
          {c.tagline && <p className="mt-2 max-w-xl text-slate-600">{c.tagline}</p>}
          <div className="mt-5 flex flex-wrap gap-3">
            <Link className="btn-primary" to={bookTo}>{t.book}</Link>
            <a className="rounded-lg bg-red-600 px-4 py-2 font-semibold text-white" href={telHref(c.emergency_phone)}>🚑 {t.helpline}: {c.emergency_phone}</a>
            {wa && <a className="rounded-lg bg-[#25D366] px-4 py-2 font-semibold text-white" href={wa} target="_blank" rel="noreferrer">{t.whatsapp}</a>}
          </div>
          {c.rating_avg && <p className="mt-3 text-sm text-slate-600">★ {c.rating_avg} ({c.rating_count})</p>}
        </div>
      </div>

      <Sec id="doctors" title={t.doctors}>
        <input className="input mb-4 max-w-md" placeholder={t.search} value={dq} onChange={(e) => setDq(e.target.value)} />
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {docs.map((d) => (
            <div key={d.id} className="card space-y-2">
              <div className="flex gap-3">
                {d.photo_url ? <img src={d.photo_url} alt={`Dr. ${d.name}`} className="h-16 w-16 rounded-full object-cover" loading="lazy" referrerPolicy="no-referrer" /> : <div className="flex h-16 w-16 items-center justify-center rounded-full bg-brand-100 text-xl font-bold text-brand-700">{d.name[0]}</div>}
                <div><b>Dr. {d.name}</b><p className="text-sm text-slate-600">{d.specialization}</p>{d.qualification && <p className="text-xs text-slate-500">{d.qualification}</p>}</div>
              </div>
              <p className="text-xs text-slate-600">{d.experience_years ?? "?"} {t.yrs} · {t.fee} ₹{d.fee}{d.opd_timing ? ` · OPD ${d.opd_timing}` : ""}</p>
              <div><p className="text-xs font-semibold">{t.slots}</p>
                {d.next_slots.length ? <div className="mt-1 flex flex-wrap gap-1">{d.next_slots.map((s) => <Badge key={s.date + s.time} tone="info">{s.date.slice(5)} {s.time}</Badge>)}</div> : <p className="text-xs text-slate-500">{t.noslots}</p>}</div>
              <Link className="btn-primary block py-1 text-center" to={bookTo}>{t.book}</Link>
            </div>))}
        </div>
      </Sec>

      <Sec id="departments" title={t.departments}>
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
          {c.departments.map((d) => <div key={d.name} className="card"><p className="text-2xl">{ICON[d.icon] || "➕"}</p><b>{d.name}</b><ul className="mt-1 list-disc pl-4 text-sm text-slate-600">{d.services.map((s) => <li key={s}>{s}</li>)}</ul></div>)}
        </div>
        <div className="mt-4 flex flex-wrap gap-3 text-sm"><Link className="btn-ghost" to={user ? "/medicines" : "/login"}>💊 {t.pharm}</Link><Link className="btn-ghost" to={user ? "/blood" : "/login"}>🩸 {t.blood}</Link></div>
      </Sec>

      {c.packages.length > 0 && <Sec id="packages" title={t.packages}>
        <div className="grid gap-4 md:grid-cols-3">{c.packages.map((p) => <div key={p.name} className="card"><b>{p.name}</b><p className="text-2xl font-bold text-brand-700">₹{p.price}</p><p className="text-xs font-semibold">{t.includes}</p><ul className="list-disc pl-4 text-sm text-slate-600">{p.includes.map((i) => <li key={i}>{i}</li>)}</ul></div>)}</div>
      </Sec>}

      {c.insurers.length > 0 && <Sec id="insurance" title={t.insurance}>
        <input className="input mb-3 max-w-md" placeholder={t.insq} value={ins} onChange={(e) => setIns(e.target.value)} />
        {insMatch && (insMatch.length ? <p className="mb-3 text-sm text-emerald-700">✔ {t.accepted}: {insMatch.join(", ")}</p> : <p className="mb-3 text-sm text-amber-700">{t.notlisted}</p>)}
        <div className="flex flex-wrap gap-2">{c.insurers.map((i) => <Badge key={i}>{i}</Badge>)}</div>
      </Sec>}

      <Sec id="emergency" title={`24×7 ${t.emergency}`}>
        <div className="grid gap-3 md:grid-cols-3">
          <a className="card block bg-red-50 text-center" href={telHref(c.emergency_phone)}><p className="text-3xl">📞</p><b>{t.helpline}</b><p className="text-xl font-bold text-red-700">{c.emergency_phone}</p><p className="text-xs">{t.call}</p></a>
          <a className="card block text-center" href={telHref(c.ambulance_phone)}><p className="text-3xl">🚑</p><b>{t.ambulance}</b><p className="text-xl font-bold">{c.ambulance_phone}</p><p className="text-xs">{t.call}</p></a>
          <div className="card text-center"><p className="text-3xl">🏥</p><b>Emergency department</b><p className="text-sm text-slate-600">{c.emergency_location || c.address || "—"}</p></div>
        </div>
      </Sec>

      {c.blog.length > 0 && <Sec id="blog" title={t.blog}><div className="grid gap-4 md:grid-cols-2">{c.blog.map((b, i) => <article key={i} className="card"><b>{b.title}</b>{b.date && <p className="text-xs text-slate-500">{b.date}</p>}<p className="mt-1 whitespace-pre-line text-sm text-slate-700">{b.body}</p></article>)}</div></Sec>}

      {c.gallery.length > 0 && <Sec id="gallery" title={t.gallery}><div className="grid grid-cols-2 gap-3 md:grid-cols-4">{c.gallery.map((g) => <figure key={g.url}><img src={g.url} alt={g.caption || "Hospital"} className="h-36 w-full rounded-lg object-cover" loading="lazy" referrerPolicy="no-referrer" />{g.caption && <figcaption className="text-xs text-slate-500">{g.caption}</figcaption>}</figure>)}</div></Sec>}

      <Sec id="feedback" title={`${t.feedback} / ${t.cp}`}>
        <div className="grid gap-6 md:grid-cols-2">
          <form onSubmit={sendFb} className="card space-y-2">
            <div className="grid grid-cols-2 gap-2"><input className="input" required minLength={2} placeholder={t.name} value={fb.name} onChange={(e) => setFb({ ...fb, name: e.target.value })} /><input className="input" type="email" placeholder={t.email} value={fb.email} onChange={(e) => setFb({ ...fb, email: e.target.value })} /></div>
            <div className="grid grid-cols-2 gap-2"><select className="input" value={fb.kind} onChange={(e) => setFb({ ...fb, kind: e.target.value })}><option value="feedback">{t.fb}</option><option value="complaint">{t.cp}</option></select>
              <select className="input" value={fb.rating} onChange={(e) => setFb({ ...fb, rating: e.target.value })}>{[5, 4, 3, 2, 1].map((n) => <option key={n} value={n}>{"★".repeat(n)}</option>)}</select></div>
            <textarea className="input min-h-[90px]" required minLength={5} maxLength={1500} placeholder={t.msg} value={fb.message} onChange={(e) => setFb({ ...fb, message: e.target.value })} />
            <Alert tone="error">{error}</Alert><Alert tone="ok">{fbOk}</Alert>
            <button className="btn-primary" disabled={busy}>{t.send}</button>
          </form>
          <div className="space-y-2"><p className="text-sm font-semibold">{t.reviews}</p>{c.feedback.length ? c.feedback.map((f) => <div key={f.id} className="card py-2 text-sm"><b>{f.name}</b> <span className="text-amber-500">{"★".repeat(f.rating)}</span><p className="text-slate-600">{f.message}</p></div>) : <p className="text-sm text-slate-500">—</p>}</div>
        </div>
      </Sec>

      <Sec id="contact" title={t.contact}>
        <div className="grid gap-6 md:grid-cols-2">
          <ul className="space-y-2 text-sm">
            {c.address && <li>📍 <b>{t.address}:</b> {c.address}</li>}
            {c.phone && <li>📞 <a className="underline" href={telHref(c.phone)}>{c.phone}</a></li>}
            {c.email && <li>✉️ <a className="underline" href={`mailto:${c.email}`}>{c.email}</a></li>}
            {c.opd_hours && <li>🕘 <b>{t.opd}:</b> {c.opd_hours}</li>}
            {c.visiting_hours && <li>👪 <b>{t.visiting}:</b> {c.visiting_hours}</li>}
            {c.parking && <li>🅿️ <b>{t.parking}:</b> {c.parking}</li>}
            <li className="flex flex-wrap gap-2 pt-2">{wa && <a className="rounded-lg bg-[#25D366] px-3 py-1.5 font-semibold text-white" href={wa} target="_blank" rel="noreferrer">{t.whatsapp}</a>}
              <Link className="btn-ghost" to="/contact">💬 {t.chat}</Link>{c.map_url && <a className="btn-ghost" href={c.map_url} target="_blank" rel="noreferrer">{t.map}</a>}</li>
          </ul>
          {c.map_embed && <iframe title="Map" src={c.map_embed} className="h-64 w-full rounded-xl border" loading="lazy" referrerPolicy="no-referrer-when-downgrade" />}
        </div>
      </Sec>
      <footer className="border-t py-4 text-center text-xs text-slate-500">{c.name} · In a medical emergency call {c.emergency_phone}</footer>
    </div>
  );
}
