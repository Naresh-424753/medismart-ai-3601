import asyncio
import hashlib
import math
import smtplib
import uuid
from datetime import datetime, timezone
from email.message import EmailMessage

from .config import settings


def new_id() -> str:
    return uuid.uuid4().hex


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def today() -> str:
    from zoneinfo import ZoneInfo
    return datetime.now(ZoneInfo(settings.APP_TZ)).strftime("%Y-%m-%d")


def haversine_km(lat1, lon1, lat2, lon2) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def clean(doc: dict | None, drop: tuple = ()) -> dict | None:
    if doc is None:
        return None
    doc = {k: v for k, v in doc.items() if k != "_id" and k not in drop}
    return doc


PRIVATE_USER_FIELDS = ("password_hash", "failed_logins", "locked_until")


def public_user(u: dict) -> dict:
    return clean(u, PRIVATE_USER_FIELDS)


async def log_event(db, user_id: str, kind: str, title: str, data: dict | None = None):
    """Adds an entry to the patient's health timeline."""
    await db.events.insert_one({"id": new_id(), "user_id": user_id, "kind": kind, "title": title, "data": data or {}, "ts": now()})


AUDIT_GENESIS = "0" * 64
_audit_lock = asyncio.Lock()


def audit_hash(e: dict, prev: str) -> str:
    """SHA-256 over the entry's fields and the previous entry's hash: changing or deleting any past entry breaks every later hash."""
    body = "|".join(str(e.get(k) or "") for k in ("seq", "id", "user_id", "role", "action", "detail", "ip", "ts"))
    return hashlib.sha256(f"{prev}|{body}".encode()).hexdigest()


async def audit(db, user_id: str | None, action: str, detail: str = "", ip: str = "", role: str = ""):
    """Append-only, tamper-evident audit trail (hash chain). Nothing in the API updates or deletes these rows."""
    async with _audit_lock:
        last = await db.audit_logs.find({"seq": {"$exists": True}}, {"_id": 0, "seq": 1, "hash": 1}).sort("seq", -1).limit(1).to_list(1)
        seq = (last[0]["seq"] + 1) if last else 1
        prev = last[0]["hash"] if last else AUDIT_GENESIS
        e = {"id": new_id(), "seq": seq, "user_id": user_id, "role": role, "action": action, "detail": detail, "ip": ip, "ts": now()}
        e["prev_hash"], e["hash"] = prev, audit_hash(e, prev)
        await db.audit_logs.insert_one(e)


def email_configured() -> bool:
    return bool(settings.BREVO_API_KEY or settings.SMTP_HOST)


def _send_email(to: str, subject: str, body: str):
    if settings.BREVO_API_KEY:  # HTTPS API: works where outbound SMTP ports are blocked
        import httpx
        r = httpx.post("https://api.brevo.com/v3/smtp/email", headers={"api-key": settings.BREVO_API_KEY, "accept": "application/json"},
                       json={"sender": {"name": "MediSmart AI 360", "email": settings.SMTP_FROM}, "to": [{"email": to}], "subject": subject, "textContent": body}, timeout=20)
        if r.status_code >= 400:
            raise RuntimeError(f"Brevo API {r.status_code}: {r.text[:200]}")
        return
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = settings.SMTP_FROM, to, subject
    msg.set_content(body)
    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=15) as s:
        s.starttls()
        if settings.SMTP_USER:
            s.login(settings.SMTP_USER, settings.SMTP_PASS)
        s.send_message(msg)


def to_e164(phone: str) -> str | None:
    """'98765 43210' -> '+919876543210' (default country code from DEFAULT_COUNTRY_CODE). Returns None if it does not look like a phone number."""
    import re
    raw = (phone or "").replace("whatsapp:", "").strip()
    digits = re.sub(r"\D", "", raw)
    if raw.startswith("+"):
        out = "+" + digits
    elif digits.startswith("00"):
        out = "+" + digits[2:]
    elif len(digits) == 10:
        out = "+" + settings.DEFAULT_COUNTRY_CODE + digits
    elif len(digits) == 11 and digits.startswith("0"):
        out = "+" + settings.DEFAULT_COUNTRY_CODE + digits[1:]
    else:
        out = "+" + digits
    return out if 8 <= len(out) - 1 <= 15 else None


def _send_twilio(to: str, body: str, whatsapp: bool):
    import httpx
    frm = settings.TWILIO_WA_FROM if whatsapp else settings.TWILIO_SMS_FROM
    num = to_e164(to)
    if not num:
        raise ValueError("invalid phone number")
    if whatsapp:
        num = f"whatsapp:{num}"
        frm = frm if frm.startswith("whatsapp:") else f"whatsapp:{frm}"
    httpx.post(f"https://api.twilio.com/2010-04-01/Accounts/{settings.TWILIO_SID}/Messages.json",
               auth=(settings.TWILIO_SID, settings.TWILIO_TOKEN), data={"From": frm, "To": num, "Body": body}, timeout=15).raise_for_status()


async def notify(db, user: dict | None, title: str, body: str, kind: str = "info", channels: tuple = ("app",), email: str | None = None, phone: str | None = None):
    """Always stores an in-app notification; also tries email / SMS / WhatsApp if configured. Never raises."""
    uid = user["id"] if user else None
    if uid:
        await db.notifications.insert_one({"id": new_id(), "user_id": uid, "title": title, "body": body, "kind": kind, "read": False, "ts": now()})
    to_email = email or (user or {}).get("email")
    to_phone = phone or (user or {}).get("phone")
    loop = asyncio.get_running_loop()
    jobs = []  # each channel is tried on its own: a failing SMS must not stop the WhatsApp message
    if "email" in channels and email_configured() and to_email:
        jobs.append(("email", _send_email, (to_email, title, body)))
    if "sms" in channels and settings.TWILIO_SID and settings.TWILIO_SMS_FROM and to_phone:
        jobs.append(("sms", _send_twilio, (to_phone, f"{title}: {body}", False)))
    if "whatsapp" in channels and settings.TWILIO_SID and settings.TWILIO_WA_FROM and to_phone:
        jobs.append(("whatsapp", _send_twilio, (to_phone, f"{title}: {body}", True)))
    for name, fn, args in jobs:
        try:
            await loop.run_in_executor(None, fn, *args)
        except Exception as e:  # delivery problems must never break the request
            await audit(db, uid, "notify_failed", f"{name}: {str(e)[:180]}")
