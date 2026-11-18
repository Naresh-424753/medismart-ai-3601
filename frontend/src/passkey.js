// Fingerprint / face / device-PIN login (WebAuthn passkeys). The phone or computer checks the biometric; the server only stores a public key.
import { api } from "./api.js";

const b2u = (s) => { const t = s.replace(/-/g, "+").replace(/_/g, "/"); const bin = atob(t + "=".repeat((4 - (t.length % 4)) % 4)); return Uint8Array.from(bin, (c) => c.charCodeAt(0)).buffer; };
const u2b = (buf) => { let s = ""; new Uint8Array(buf).forEach((b) => { s += String.fromCharCode(b); }); return btoa(s).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, ""); };

export const passkeySupported = () => typeof window !== "undefined" && !!window.PublicKeyCredential && !!navigator.credentials && window.isSecureContext;

function friendly(e) {
  if (e && (e.name === "NotAllowedError" || e.name === "AbortError")) return new Error("Cancelled, or the fingerprint / face check did not complete. Please try again.");
  if (e && e.name === "InvalidStateError") return new Error("This device is already added.");
  if (e && e.name === "NotSupportedError") return new Error("This device does not support fingerprint / face login.");
  return e;
}

export function deviceName() {
  const ua = navigator.userAgent;
  return /iPhone/.test(ua) ? "iPhone" : /iPad/.test(ua) ? "iPad" : /Android/.test(ua) ? "Android phone" : /Windows/.test(ua) ? "Windows PC" : /Mac/.test(ua) ? "Mac" : "This device";
}

export async function registerPasskey(name) {
  const o = await api("/auth/passkey/register/options", { method: "POST" });
  const pk = o.publicKey;
  let cred;
  try {
    cred = await navigator.credentials.create({ publicKey: { ...pk, challenge: b2u(pk.challenge), user: { ...pk.user, id: b2u(pk.user.id) }, excludeCredentials: pk.excludeCredentials.map((c) => ({ ...c, id: b2u(c.id) })) } });
  } catch (e) { throw friendly(e); }
  const r = cred.response;
  return api("/auth/passkey/register/verify", { method: "POST", body: { challenge_id: o.challenge_id, name: name || deviceName(), credential: { id: cred.id, rawId: u2b(cred.rawId), type: cred.type, response: { clientDataJSON: u2b(r.clientDataJSON), attestationObject: u2b(r.attestationObject) } } } });
}

/** Asks the device for a fingerprint / face check and returns what /auth/passkey/login/verify needs. */
export async function passkeyAssertion(email) {
  const o = await api("/auth/passkey/login/options", { method: "POST", body: { email: email || null } });
  const pk = o.publicKey;
  let cred;
  try {
    cred = await navigator.credentials.get({ publicKey: { ...pk, challenge: b2u(pk.challenge), allowCredentials: (pk.allowCredentials || []).map((c) => ({ ...c, id: b2u(c.id) })) } });
  } catch (e) { throw friendly(e); }
  const r = cred.response;
  return { challenge_id: o.challenge_id, credential: { id: cred.id, rawId: u2b(cred.rawId), type: cred.type, response: { clientDataJSON: u2b(r.clientDataJSON), authenticatorData: u2b(r.authenticatorData), signature: u2b(r.signature), userHandle: r.userHandle ? u2b(r.userHandle) : null } } };
}
