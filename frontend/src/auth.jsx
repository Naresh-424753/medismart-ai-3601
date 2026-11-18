import { createContext, useContext, useEffect, useState } from "react";
import { api, tokenStore } from "./api.js";
import { passkeyAssertion } from "./passkey.js";

const Ctx = createContext(null);
export const useAuth = () => useContext(Ctx);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(!!tokenStore.get());

  useEffect(() => {
    if (!tokenStore.get()) return;
    api("/auth/me")
      .then(setUser)
      .catch(() => tokenStore.clear())
      .finally(() => setLoading(false));
  }, []);

  // Idle timeout: a forgotten, unlocked phone or shared PC logs itself out (default 15 min, VITE_IDLE_MIN to change, 0 = off)
  useEffect(() => {
    const mins = Number(import.meta.env.VITE_IDLE_MIN ?? 15);
    if (!user || !mins) return;
    let t;
    const arm = () => { clearTimeout(t); t = setTimeout(async () => { try { await api("/auth/logout", { method: "POST" }); } catch {} tokenStore.clear(); setUser(null); }, mins * 60000); };
    const ev = ["mousemove", "keydown", "touchstart", "click", "scroll"];
    ev.forEach((e) => window.addEventListener(e, arm, { passive: true }));
    arm();
    return () => { clearTimeout(t); ev.forEach((e) => window.removeEventListener(e, arm)); };
  }, [user]);

  const finish = (r) => { tokenStore.set(r.token); setUser(r.user); return r; };
  // Returns {requires_otp:true} when 2FA is on; then call verifyLoginOtp.
  const login = async (email, password) => {
    const r = await api("/auth/login", { method: "POST", body: { email, password } });
    return r.requires_otp ? r : finish(r);
  };
  const verifyLoginOtp = async (email, otp) =>
    finish(await api("/auth/verify-otp", { method: "POST", body: { email, otp, purpose: "login" } }));
  const loginPasskey = async (email) => finish(await api("/auth/passkey/login/verify", { method: "POST", body: await passkeyAssertion(email) }));
  const logout = async () => {
    try {
      await api("/auth/logout", { method: "POST" });
    } catch {}
    tokenStore.clear();
    setUser(null);
  };
  return <Ctx.Provider value={{ user, loading, login, verifyLoginOtp, loginPasskey, logout, setUser }}>{children}</Ctx.Provider>;
}
