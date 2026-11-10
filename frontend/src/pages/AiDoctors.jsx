import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api.js";
import { Alert, Badge, Card, Disclaimer, Empty, useAsync } from "../components/ui.jsx";
import Icon from "../components/Icon.jsx";
import SosButton from "../components/SosButton.jsx";
import { SR, hasVoiceFor, saveLang, savedLang, speak as speakText, useVoiceLangs } from "../components/voice.js";

const SEV = { mild: "good", moderate: "warn", severe: "bad" };
const when = (s) => (s || "").slice(0, 16).replace("T", " ");

const speakThen = (text, tag, done) => {
  if (!("speechSynthesis" in window) || !text) return done();
  window.speechSynthesis.cancel();
  const u = new SpeechSynthesisUtterance(text);
  u.lang = tag;
  const base = tag.split("-")[0];
  const v = window.speechSynthesis.getVoices().find((x) => x.lang === tag) || window.speechSynthesis.getVoices().find((x) => x.lang.startsWith(base));
  if (v) u.voice = v;
  u.onend = done; u.onerror = done;
  window.speechSynthesis.speak(u);
};
const mmss = (n) => `${String(Math.floor(n / 60)).padStart(2, "0")}:${String(n % 60).padStart(2, "0")}`;

/** Hands-free voice call: the AI speaks, then the mic listens, and so on. Uses the browser's own speech engines (Chrome / Edge). */
function VoiceCall({ session, L, send, onEnd, ending }) {
  const [on, setOn] = useState(false);
  const [state, setState] = useState("idle"); // idle | listening | thinking | speaking
  const [secs, setSecs] = useState(0);
  const [live, setLive] = useState("");
  const [err, setErr] = useState("");
  const onRef = useRef(false);
  const recRef = useRef(null);
  const timer = useRef(null);
  const sendRef = useRef(send);
  sendRef.current = send;

  const stop = () => {
    onRef.current = false; setOn(false); setState("idle"); setLive("");
    clearInterval(timer.current);
    try { recRef.current?.stop(); } catch { /* already stopped */ }
    window.speechSynthesis?.cancel();
  };
  useEffect(() => stop, []); // stop everything when the page is left

  const listen = () => {
    if (!onRef.current) return;
    const rec = new SR();
    rec.lang = L.speech; rec.interimResults = true; rec.continuous = false;
    let finalText = "";
    rec.onresult = (ev) => {
      let interim = "";
      for (let i = ev.resultIndex; i < ev.results.length; i++) { const r = ev.results[i]; if (r.isFinal) finalText += r[0].transcript; else interim += r[0].transcript; }
      setLive((finalText + " " + interim).trim());
    };
    rec.onerror = (e) => {
      if (e.error === "not-allowed" || e.error === "service-not-allowed") { setErr("Microphone permission was denied. Allow the microphone in your browser and start the call again."); stop(); }
    };
    rec.onend = async () => {
      if (!onRef.current) return;
      const t = finalText.trim();
      setLive("");
      if (!t) return setTimeout(listen, 300); // silence: keep listening
      setState("thinking");
      const reply = await sendRef.current(null, t, true);
      if (!onRef.current) return;
      if (reply) { setState("speaking"); speakThen(reply, (L.code === "en" || !/[^\x00-\x7F]/.test(reply)) ? "en-IN" : L.speech, () => { if (onRef.current) listen(); }); }
      else listen();
    };
    recRef.current = rec; setState("listening");
    try { rec.start(); } catch { setTimeout(listen, 500); }
  };

  const start = () => {
    setErr("");
    if (!SR) return setErr("Voice calls need speech recognition, which this browser does not have. Use Chrome or Edge, or type below.");
    onRef.current = true; setOn(true); setSecs(0);
    timer.current = setInterval(() => setSecs((n) => n + 1), 1000);
    const last = session.messages[session.messages.length - 1];
    if (last?.role === "assistant") { setState("speaking"); speakThen(last.content, "en-IN", () => onRef.current && listen()); } else listen();
  };
  const end = () => { stop(); onEnd(); };
  const label = { idle: "Not connected", listening: "Listening… speak now", thinking: "The AI doctor is thinking…", speaking: "The AI doctor is speaking…" }[state];

  return (
    <div className="card flex flex-col items-center gap-3 py-5 text-center">
      <div className="flex w-full items-center justify-between text-sm">
        <span className="flex items-center gap-2 rounded-md border px-2 py-1"><span className={`h-3 w-3 rounded-full ${on ? "bg-emerald-500" : "bg-red-500"}`} />{on ? "Connected" : "Not connected"}</span>
        <span className="font-mono text-lg text-slate-500">{mmss(secs)}</span>
      </div>
      <div className={`flex h-24 w-24 items-center justify-center rounded-full bg-brand-50 text-brand-700 ${state === "speaking" ? "animate-pulse ring-4 ring-brand-300" : state === "listening" ? "ring-4 ring-emerald-300" : ""}`}>
        <Icon name={session.icon || "heart"} className="h-10 w-10" />
      </div>
      <div><p className="font-semibold">{session.agent} AI</p><p className="text-sm text-slate-500">{label}</p></div>
      {live && <p className="max-w-md rounded-lg bg-slate-100 px-3 py-2 text-sm italic text-slate-600">“{live}”</p>}
      <Alert tone="error">{err}</Alert>
      {!on
        ? <button className="btn-primary" onClick={start} disabled={ending}>📞 Start voice call</button>
        : <button className="rounded-lg bg-red-600 px-4 py-2 font-semibold text-white hover:bg-red-700" onClick={end} disabled={ending}>{ending ? "Preparing report…" : "📵 End call and get report"}</button>}
    </div>
  );
}

export default function AiDoctors() {
  const langList = useVoiceLangs();
  const [lang, setLang] = useState(savedLang());
  const L = langList.find((l) => l.code === lang) || langList[0];
  const [agents, setAgents] = useState([]);
  const [notes, setNotes] = useState("");
  const [sugg, setSugg] = useState(null);
  const [session, setSession] = useState(null); // {id, agent, messages, ended, report}
  const [text, setText] = useState("");
  const [listening, setListening] = useState(false);
  const [speak, setSpeak] = useState(true);
  const [history, setHistory] = useState([]);
  const [sendBusy, setSendBusy] = useState(false);
  const [mode, setMode] = useState("chat"); // chat | call
  const { busy, error, setError, run } = useAsync();
  const endRef = useRef(null);
  const recRef = useRef(null);
  const target = useRef("chat"); // which box the mic fills

  const loadHistory = () => api("/assistant/sessions").then(setHistory).catch(() => {});
  useEffect(() => { api("/assistant/agents").then(setAgents).catch(() => {}); loadHistory(); }, []);
  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth" }); }, [session?.messages?.length]);
  useEffect(() => () => { window.speechSynthesis?.cancel(); recRef.current?.stop?.(); }, []);

  const say = (t) => { if (speak && t) speakText(t, (lang === "en" || !/[^\x00-\x7F]/.test(t)) ? "en-IN" : L.speech); };

  const suggest = (e) => {
    e.preventDefault();
    run(async () => setSugg(await api("/assistant/suggest", { method: "POST", body: { notes } })));
  };
  const start = (agent_id) => run(async () => {
    const s = await api("/assistant/sessions", { method: "POST", body: { agent_id, notes, lang } });
    setSession(s); setSugg(null); loadHistory();
    say(s.messages[0].content);
  });
  const open = (id) => run(async () => { const s = await api(`/assistant/sessions/${id}`); setSession(s); });

  const send = async (e, override, silent = false) => {
    e?.preventDefault();
    const message = (override ?? text).trim();
    if (!message || sendBusy || !session || session.ended) return null;
    setText(""); setError("");
    setSession((s) => ({ ...s, messages: [...s.messages, { role: "user", content: message }] }));
    setSendBusy(true);
    try {
      const r = await api(`/assistant/sessions/${session.id}/message`, { method: "POST", body: { message } });
      setSession((s) => ({ ...s, emergency: s.emergency || r.emergency, messages: [...s.messages, { role: "assistant", content: r.reply, source: r.source }] }));
      if (!silent) say(r.reply);
      return r.reply;
    } catch (err) { setError(err.message); return null; } finally { setSendBusy(false); }
  };

  const mic = (dest) => {
    if (!SR) return alert("Voice input is not supported in this browser. Try Chrome or Edge.");
    if (listening) return recRef.current?.stop();
    window.speechSynthesis?.cancel();
    const rec = new SR();
    rec.lang = L.speech; rec.interimResults = false;
    target.current = dest;
    rec.onresult = (ev) => { const t = ev.results[0][0].transcript; dest === "notes" ? setNotes((n) => (n ? n + " " : "") + t) : send(null, t); };
    rec.onend = () => setListening(false); rec.onerror = () => setListening(false);
    recRef.current = rec; setListening(true); rec.start();
  };

  const finish = () => run(async () => {
    window.speechSynthesis?.cancel();
    const report = await api(`/assistant/sessions/${session.id}/report`, { method: "POST" });
    setSession((s) => ({ ...s, ended: true, report })); loadHistory();
  });
  const del = (id) => confirm("Delete this consultation and its report?") && run(async () => {
    await api(`/assistant/sessions/${id}`, { method: "DELETE" });
    if (session?.id === id) setSession(null);
    loadHistory();
  });
  const reset = () => { window.speechSynthesis?.cancel(); setSession(null); setNotes(""); setSugg(null); setError(""); };

  const langBar = (
    <div className="flex flex-wrap items-center gap-3 text-sm">
      <select className="input w-auto py-1" value={lang} onChange={(e) => { setLang(e.target.value); saveLang(e.target.value); }} aria-label="Language">
        {langList.map((l) => <option key={l.code} value={l.code}>{l.native}</option>)}
      </select>
      <label className="flex items-center gap-1"><input type="checkbox" checked={speak} onChange={(e) => { setSpeak(e.target.checked); if (!e.target.checked) window.speechSynthesis?.cancel(); }} /> Read replies aloud</label>
      {speak && !hasVoiceFor(L.speech) && <span className="text-xs text-amber-700">No {L.name} voice on this device.</span>}
    </div>
  );

  /* ---------------- consultation / report ---------------- */
  if (session) {
    const rep = session.report;
    return (
      <>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h1 className="text-xl font-bold">AI {session.agent} <span className="text-sm font-normal text-slate-500">· {when(session.created)}</span></h1>
          <div className="flex items-center gap-3">{!session.ended && langBar}<button className="btn-ghost" onClick={reset}>← All AI doctors</button></div>
        </div>
        {session.emergency && (
          <div className="rounded-xl border-2 border-red-400 bg-red-50 p-3 text-sm text-red-900">
            <b>This may be an emergency.</b> Call <a className="font-bold underline" href="tel:112">112</a> or <a className="font-bold underline" href="tel:108">108</a> now or go to the nearest hospital.
            <div className="mt-2"><SosButton compact /></div>
          </div>
        )}
        {!session.ended && (
          <div className="flex gap-2 text-sm print:hidden">
            <button className={mode === "chat" ? "btn-primary" : "btn-ghost"} onClick={() => setMode("chat")}>💬 Chat</button>
            <button className={mode === "call" ? "btn-primary" : "btn-ghost"} onClick={() => setMode("call")}>📞 Voice call</button>
          </div>
        )}
        {!session.ended && mode === "call" && <VoiceCall session={session} L={L} send={send} onEnd={finish} ending={busy} />}
        <div className={`card flex flex-col ${mode === "call" && !session.ended ? "h-[30vh]" : "h-[55vh]"}`}>
          <div className="flex-1 space-y-3 overflow-y-auto pr-1" aria-live="polite">
            {session.messages.map((m, i) => (
              <div key={i} className={m.role === "user" ? "text-right" : ""}>
                <div className={`inline-block max-w-[85%] whitespace-pre-line rounded-2xl px-4 py-2 text-left text-sm ${m.role === "user" ? "bg-brand-600 text-white" : m.source === "safety" ? "border-2 border-red-400 bg-red-50 text-red-900" : "bg-slate-100 text-slate-800"}`}>{m.content}</div>
              </div>
            ))}
            {sendBusy && <p className="text-sm text-slate-400">The AI doctor is typing…</p>}
            <div ref={endRef} />
          </div>
          {!session.ended && mode === "chat" && (
            <form onSubmit={send} className="mt-3 flex gap-2">
              <button type="button" onClick={() => mic("chat")} className={`btn-ghost ${listening ? "ring-2 ring-red-400" : ""}`} aria-label="Speak">{listening ? "● Listening" : "🎤"}</button>
              <input className="input" value={text} onChange={(e) => setText(e.target.value)} placeholder="Type or tap the mic and speak…" maxLength={1000} />
              <button className="btn-primary" disabled={sendBusy}>Send</button>
            </form>
          )}
        </div>
        <Alert tone="error">{error}</Alert>
        {!session.ended && mode === "chat" && (
          <div className="flex flex-wrap items-center gap-3">
            <button className="btn-primary" onClick={finish} disabled={busy || session.messages.filter((m) => m.role === "user").length < 1}>{busy ? "Preparing…" : "End and get report"}</button>
            <span className="text-xs text-slate-500">Answer 3 to 4 questions first for a useful report.</span>
          </div>
        )}
        {rep && (
          <Card title="Consultation report" action={<Badge tone={SEV[rep.severity] || "muted"}>{rep.severity}</Badge>}>
            <div className="space-y-2 text-sm">
              <div className="grid gap-1 rounded-lg bg-slate-50 p-3 sm:grid-cols-2">
                <p><b>Doctor:</b> {rep.agent || session.agent}</p>
                <p><b>Patient:</b> {rep.patient || "Patient"}</p>
                <p><b>Consulted on:</b> {when(rep.consulted_on || session.created)}</p>
                <p><b>Messages:</b> {session.messages.length}</p>
              </div>
              <p><b>Main concern:</b> {rep.chief_complaint}</p>
              <p><b>Summary:</b> {rep.summary}</p>
              <p><b>Symptoms:</b> {(rep.symptoms || []).join(", ") || "none noted"}</p>
              <p><b>Duration:</b> {rep.duration}</p>
              <p><b>Medicines mentioned:</b> {(rep.medicines_mentioned || []).join(", ") || "none"}</p>
              <div><b>What to do next:</b><ul className="ml-5 list-disc">{(rep.recommendations || []).map((r, i) => <li key={i}>{r}</li>)}</ul></div>
              <p><b>Suggested specialist:</b> {rep.suggested_specialist}</p>
              <details className="rounded-lg border border-slate-200 p-2 print:open"><summary className="cursor-pointer font-medium">Conversation transcript</summary>
                <div className="mt-2 space-y-1">{session.messages.map((m, i) => <p key={i}><b>{m.role === "user" ? "You" : "AI doctor"}:</b> {m.content}</p>)}</div></details>
              <p className="text-xs text-slate-500">{rep.disclaimer} Source: {rep.source === "llm" ? "AI language model" : "rule-based summary"}.</p>
            </div>
            <div className="mt-3 flex flex-wrap gap-2 print:hidden">
              <Link className="btn-primary" to="/appointments">Book a doctor</Link>
              <Link className="btn-ghost" to="/risk">Run a risk check</Link>
              <button className="btn-ghost" onClick={() => window.print()}>Print / save PDF</button>
              <button className="btn-ghost" onClick={reset}>New consultation</button>
            </div>
          </Card>
        )}
        <Disclaimer />
      </>
    );
  }

  /* ---------------- start screen ---------------- */
  return (
    <>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div><h1 className="text-xl font-bold">AI Doctors</h1><p className="text-sm text-slate-500">Talk or type to a specialist AI, then get a summary report to show your doctor.</p></div>
        {langBar}
      </div>
      <Card title="1. Tell us what is wrong">
        <form onSubmit={suggest} className="space-y-3">
          <textarea className="input min-h-[90px]" required minLength={3} maxLength={1000} value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Example: knee pain for 2 weeks, worse while climbing stairs" />
          <div className="flex flex-wrap gap-2">
            <button type="button" className={`btn-ghost ${listening ? "ring-2 ring-red-400" : ""}`} onClick={() => mic("notes")}>{listening ? "● Listening" : "🎤 Speak"}</button>
            <button className="btn-primary" disabled={busy}>{busy ? "Finding…" : "Suggest the right AI doctor"}</button>
          </div>
        </form>
        <div className="mt-2"><Alert tone="error">{error}</Alert></div>
        {sugg?.emergency && <div className="mt-3 rounded-xl border-2 border-red-400 bg-red-50 p-3 text-sm text-red-900"><b>{sugg.emergency}</b></div>}
        {sugg && (
          <div className="mt-4 grid gap-3 md:grid-cols-2">
            {sugg.suggestions.map((a) => (
              <div key={a.id} className="rounded-xl border border-brand-200 bg-brand-50/50 p-3">
                <div className="flex items-center gap-2 font-semibold"><Icon name={a.icon} className="h-5 w-5 text-brand-700" />{a.specialist}</div>
                <p className="text-xs text-slate-600">{a.reason}</p>
                <button className="btn-primary mt-2" onClick={() => start(a.id)} disabled={busy}>Start consultation</button>
              </div>
            ))}
          </div>
        )}
      </Card>
      <Card title="Or choose a specialist">
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {agents.map((a) => (
            <button key={a.id} onClick={() => start(a.id)} disabled={busy} className="rounded-xl border border-slate-200 p-3 text-left transition hover:border-brand-400 hover:bg-brand-50/40">
              <div className="flex items-center gap-2 font-semibold"><Icon name={a.icon} className="h-5 w-5 text-brand-700" />{a.specialist}</div>
              <p className="mt-1 text-xs text-slate-600">{a.description}</p>
            </button>
          ))}
        </div>
      </Card>
      <Card title="Your past consultations">
        {history.length === 0 && <Empty>No consultations yet.</Empty>}
        <ul className="divide-y divide-slate-100 text-sm">
          {history.map((h) => (
            <li key={h.id} className="flex flex-wrap items-center justify-between gap-2 py-2">
              <span><b>{h.agent}</b> <span className="text-slate-500">· {when(h.updated)} · {h.messages_count} messages</span> {h.has_report ? <Badge tone="good">report</Badge> : <Badge>open</Badge>} {h.emergency && <Badge tone="bad">emergency</Badge>}</span>
              <span className="flex gap-2"><button className="btn-ghost py-1" onClick={() => open(h.id)}>{h.has_report ? "View report" : "Continue"}</button><button className="btn-ghost py-1 text-red-700" onClick={() => del(h.id)}>Delete</button></span>
            </li>
          ))}
        </ul>
      </Card>
      <Disclaimer />
    </>
  );
}
