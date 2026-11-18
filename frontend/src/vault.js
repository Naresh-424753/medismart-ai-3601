// Private Vault: client-side encryption with the Web Crypto API.
// File format:  "MSV1" | iterations (uint32 BE) | salt (16) | iv (12) | AES-256-GCM ciphertext+tag
// The key is derived from the passphrase with PBKDF2-SHA256 and never leaves the browser. A wrong passphrase or a modified file fails to decrypt.
const MAGIC = [0x4d, 0x53, 0x56, 0x31];
const ITER = 600000;
const enc = new TextEncoder();

async function keyFrom(pass, salt, iters) {
  const base = await crypto.subtle.importKey("raw", enc.encode(pass), "PBKDF2", false, ["deriveKey"]);
  return crypto.subtle.deriveKey({ name: "PBKDF2", hash: "SHA-256", salt, iterations: iters }, base, { name: "AES-GCM", length: 256 }, false, ["encrypt", "decrypt"]);
}

export const vaultSupported = () => !!(globalThis.crypto && crypto.subtle);

export async function encryptFile(file, pass) {
  const salt = crypto.getRandomValues(new Uint8Array(16));
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const key = await keyFrom(pass, salt, ITER);
  const ct = new Uint8Array(await crypto.subtle.encrypt({ name: "AES-GCM", iv }, key, await file.arrayBuffer()));
  const head = new Uint8Array(4 + 4 + 16 + 12);
  head.set(MAGIC, 0);
  new DataView(head.buffer).setUint32(4, ITER);
  head.set(salt, 8);
  head.set(iv, 24);
  const out = new Uint8Array(head.length + ct.length);
  out.set(head, 0);
  out.set(ct, head.length);
  return new Blob([out], { type: "application/octet-stream" });
}

export async function decryptBlob(blob, pass, type = "application/octet-stream") {
  const buf = new Uint8Array(await blob.arrayBuffer());
  if (buf.length < 40 || MAGIC.some((b, i) => buf[i] !== b)) throw new Error("This is not a vault file");
  const iters = new DataView(buf.buffer, buf.byteOffset).getUint32(4);
  if (iters < 100000 || iters > 5000000) throw new Error("Unsupported vault file");
  const key = await keyFrom(pass, buf.slice(8, 24), iters);
  try {
    return new Blob([await crypto.subtle.decrypt({ name: "AES-GCM", iv: buf.slice(24, 36) }, key, buf.slice(36))], { type });
  } catch {
    throw new Error("Wrong passphrase, or the file was changed");
  }
}
