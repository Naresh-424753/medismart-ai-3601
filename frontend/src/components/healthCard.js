/** Designed emergency medical card (front + back) drawn on a canvas and saved as one PNG. Works offline once downloaded; print it, keep it in your wallet or use it as a lock screen. */
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { QRCodeSVG } from "qrcode.react";

const W = 1012, H = 638, GAP = 40; // credit-card ratio (85.6 x 54 mm at ~300 dpi)
const RED = "#b91c1c", GREEN = "#047857", INK = "#0f172a", MUTED = "#64748b";

function rr(c, x, y, w, h, r) { c.beginPath(); c.moveTo(x + r, y); c.arcTo(x + w, y, x + w, y + h, r); c.arcTo(x + w, y + h, x, y + h, r); c.arcTo(x, y + h, x, y, r); c.arcTo(x, y, x + w, y, r); c.closePath(); }
function fit(c, text, maxW, font, min = 18) { let s = parseInt(font, 10); const fam = font.replace(/^\d+px/, ""); while (s > min) { c.font = `${s}px${fam}`; if (c.measureText(text).width <= maxW) break; s -= 2; } c.font = `${s}px${fam}`; }
function clip(c, text, maxW) { if (c.measureText(text).width <= maxW) return text; let t = text; while (t.length > 1 && c.measureText(t + "…").width > maxW) t = t.slice(0, -1); return t + "…"; }
function lines(c, text, x, y, maxW, lh, maxLines) { const words = String(text).split(/\s+/); let line = "", n = 0; for (const w of words) { const t = line ? line + " " + w : w; if (c.measureText(t).width > maxW && line) { c.fillText(line, x, y); y += lh; line = w; if (++n >= maxLines) return y; } else line = t; } if (line) { c.fillText(line, x, y); y += lh; } return y; }

async function loadPhoto(url) {
  if (!url) return null;
  try { const r = await fetch(url, { mode: "cors" }); if (!r.ok) return null; return await createImageBitmap(await r.blob()); } catch { return null; }
}
async function loadQr(value, size) {
  const svg = renderToStaticMarkup(createElement(QRCodeSVG, { value, size, level: "M", includeMargin: false })).replace("<svg ", '<svg xmlns="http://www.w3.org/2000/svg" ');
  const img = new Image();
  await new Promise((ok, no) => { img.onload = ok; img.onerror = no; img.src = "data:image/svg+xml;charset=utf-8," + encodeURIComponent(svg); });
  return img;
}

export async function drawHealthCard(p, cardUrl) {
  const cv = document.createElement("canvas");
  cv.width = W; cv.height = H * 2 + GAP;
  const c = cv.getContext("2d");
  c.fillStyle = "#e2e8f0"; c.fillRect(0, 0, cv.width, cv.height);
  const [photo, qr] = await Promise.all([loadPhoto(p.photo_url), loadQr(cardUrl, 300)]);
  const allergies = (p.allergies || []).map((a) => a.name + (a.severity ? ` (${a.severity})` : ""));
  const conditions = (p.diseases || []).map((d) => d.name);
  const contacts = (p.emergency_contacts || []).slice(0, 3);
  const F = ' system-ui, "Segoe UI", Roboto, Arial, sans-serif';

  // ---------------- FRONT
  c.save(); rr(c, 0, 0, W, H, 34); c.clip();
  c.fillStyle = "#fff"; c.fillRect(0, 0, W, H);
  c.fillStyle = RED; c.fillRect(0, 0, W, 112);
  c.fillStyle = "#fff"; c.font = `800 38px${F}`; c.textBaseline = "alphabetic"; c.fillText("EMERGENCY MEDICAL CARD", 40, 56);
  c.font = `500 22px${F}`; c.fillText("MediSmart AI 360 · Digital Health Pass", 40, 92);
  c.fillStyle = "#fff"; rr(c, W - 150, 24, 110, 64, 14); c.fill(); c.fillStyle = RED; c.font = `800 34px${F}`; c.textAlign = "center"; c.fillText("+", W - 95, 68); c.textAlign = "left";
  // photo
  const px = 40, py = 150, ps = 210;
  c.save(); rr(c, px, py, ps, ps, 26); c.clip();
  if (photo) { const s = Math.max(ps / photo.width, ps / photo.height); c.drawImage(photo, px + (ps - photo.width * s) / 2, py + (ps - photo.height * s) / 2, photo.width * s, photo.height * s); }
  else { c.fillStyle = "#e0f2fe"; c.fillRect(px, py, ps, ps); c.fillStyle = "#0369a1"; c.font = `800 110px${F}`; c.textAlign = "center"; c.fillText((p.name || "?").trim()[0].toUpperCase(), px + ps / 2, py + ps / 2 + 38); c.textAlign = "left"; }
  c.restore(); c.strokeStyle = "#cbd5e1"; c.lineWidth = 3; rr(c, px, py, ps, ps, 26); c.stroke();
  // identity
  const tx = 290; c.fillStyle = INK; fit(c, p.name || "", W - tx - 40, `800 52px${F}`, 28); c.fillText(clip(c, p.name || "", W - tx - 40), tx, 195);
  c.fillStyle = MUTED; c.font = `500 26px${F}`;
  c.fillText([p.age != null && `${p.age} yrs`, p.sex && p.sex[0].toUpperCase() + p.sex.slice(1), p.dob && `DOB ${p.dob}`].filter(Boolean).join("  ·  "), tx, 238);
  c.fillStyle = GREEN; c.font = `700 30px ui-monospace, Consolas, monospace`; c.fillText(`ID  ${p.health_id}`, tx, 285);
  // blood group
  c.fillStyle = "#fef2f2"; rr(c, tx, 312, 230, 120, 22); c.fill(); c.strokeStyle = RED; c.lineWidth = 3; rr(c, tx, 312, 230, 120, 22); c.stroke();
  c.fillStyle = RED; c.font = `600 20px${F}`; c.fillText("BLOOD GROUP", tx + 22, 344);
  c.font = `900 70px${F}`; c.fillText(p.blood_group || "?", tx + 22, 414);
  // allergies box
  const ax = tx + 255; c.fillStyle = "#fffbeb"; rr(c, ax, 312, W - ax - 40, 120, 22); c.fill(); c.strokeStyle = "#f59e0b"; c.lineWidth = 3; rr(c, ax, 312, W - ax - 40, 120, 22); c.stroke();
  c.fillStyle = "#b45309"; c.font = `600 20px${F}`; c.fillText("ALLERGIES", ax + 22, 344);
  c.fillStyle = INK; c.font = `600 26px${F}`; lines(c, allergies.join(", ") || "None recorded", ax + 22, 380, W - ax - 84, 32, 2);
  // footer
  c.fillStyle = "#f1f5f9"; c.fillRect(0, H - 118, W, 118);
  c.fillStyle = MUTED; c.font = `600 20px${F}`; c.fillText("EMERGENCY CONTACT", 40, H - 76);
  c.fillStyle = INK; c.font = `700 30px${F}`; const k = contacts[0]; c.fillText(k ? clip(c, `${k.name}${k.relation ? ` (${k.relation})` : ""}  ·  ${k.phone || ""}`, W - 80) : "Not set. Add one in My Health", 40, H - 32);
  c.restore();

  // ---------------- BACK
  const oy = H + GAP;
  c.save(); rr(c, 0, oy, W, H, 34); c.clip();
  c.fillStyle = "#fff"; c.fillRect(0, oy, W, H);
  c.fillStyle = RED; c.fillRect(0, oy, W, 20);
  c.fillStyle = INK; c.font = `800 30px${F}`; c.fillText("Medical conditions", 40, oy + 76);
  c.fillStyle = "#334155"; c.font = `500 25px${F}`; let y = lines(c, conditions.join(", ") || "None recorded", 40, oy + 114, 560, 32, 3);
  c.fillStyle = INK; c.font = `800 30px${F}`; c.fillText("Emergency contacts", 40, Math.max(y + 24, oy + 250));
  c.font = `500 25px${F}`; c.fillStyle = "#334155"; y = Math.max(y + 24, oy + 250) + 40;
  if (!contacts.length) { c.fillText("None recorded", 40, y); y += 34; }
  contacts.forEach((k2) => { c.fillText(clip(c, `${k2.name}${k2.relation ? ` (${k2.relation})` : ""}: ${k2.phone || ""}`, 560), 40, y); y += 36; });
  c.fillStyle = RED; c.font = `800 30px${F}`; c.fillText("Emergency 112  ·  Ambulance 108", 40, oy + H - 100);
  c.fillStyle = MUTED; c.font = `500 20px${F}`; c.fillText("Scan the QR to open this card on any phone, no login needed.", 40, oy + H - 64);
  c.fillText("Patient-provided information. Keep it updated.", 40, oy + H - 36);
  c.fillStyle = "#fff"; rr(c, 650, oy + 70, 320, 360, 24); c.fill(); c.strokeStyle = "#cbd5e1"; c.lineWidth = 3; rr(c, 650, oy + 70, 320, 360, 24); c.stroke();
  c.drawImage(qr, 665, oy + 85, 290, 290);
  c.fillStyle = INK; c.font = `700 24px${F}`; c.textAlign = "center"; c.fillText("SCAN IN EMERGENCY", 810, oy + 412); c.textAlign = "left";
  c.restore();
  return cv;
}

export async function downloadHealthCard(p, cardUrl) {
  const cv = await drawHealthCard(p, cardUrl);
  const a = document.createElement("a");
  a.href = cv.toDataURL("image/png");
  a.download = `emergency-card-${p.health_id}.png`;
  a.click();
}

export async function printHealthCard(p, cardUrl) {
  const cv = await drawHealthCard(p, cardUrl);
  const w = window.open("", "_blank");
  if (!w) return;
  w.document.write(`<!doctype html><title>Emergency card</title><style>body{margin:0;text-align:center}img{width:85.6mm;margin:6mm auto;display:block}@page{margin:8mm}</style><img src="${cv.toDataURL("image/png")}"><script>onload=()=>setTimeout(()=>print(),300)<\/script>`);
  w.document.close();
}
