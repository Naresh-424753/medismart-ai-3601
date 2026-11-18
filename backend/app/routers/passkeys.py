"""Fingerprint / face / device-PIN login (WebAuthn passkeys). See services/webauthn.py for the protocol checks.

* A passkey is added while logged in (after password). Login with it needs the device's biometric/PIN check (user verification is mandatory),
  so it counts as two factors and skips the email OTP step. Passwords keep working.
* Keys are bound to the website's domain (the frontend origin listed in CORS_ORIGINS). If you change the website domain, passkeys must be re-added.
* Challenges are random, single-use and expire after 5 minutes."""
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from ..common import audit, new_id, notify, now
from ..config import settings
from ..db import get_db
from ..deps import client_ip, current_user
from ..services import webauthn as wa
from .auth import _finish_login

router = APIRouter(prefix="/auth/passkey", tags=["passkeys"])
MAX_PASSKEYS = 5
TTL = timedelta(minutes=5)


def _origin(request: Request) -> tuple[str, str]:
    """(origin, rp_id) taken from the browser's Origin header, only if it is one of our configured website origins."""
    o = request.headers.get("origin", "")
    if not o or o not in settings.CORS_ORIGINS:
        raise HTTPException(400, "Fingerprint / face login is not available from this website address")
    host = urlparse(o).hostname
    if not host or (urlparse(o).scheme != "https" and host not in ("localhost", "127.0.0.1")):
        raise HTTPException(400, "Fingerprint / face login needs a secure (https) website")
    return o, host


async def _new_challenge(db, purpose: str, origin: str, user_id: str | None) -> tuple[str, str]:
    cid, ch = new_id(), wa.b64u(secrets.token_bytes(32))
    exp = (datetime.now(timezone.utc) + TTL).isoformat(timespec="seconds")
    await db.webauthn_challenges.insert_one({"id": cid, "challenge": ch, "purpose": purpose, "origin": origin, "user_id": user_id, "expires_at": exp})
    return cid, ch


async def _take_challenge(db, cid: str, purpose: str, origin: str) -> dict:
    """Single use: the record is deleted whether or not the verification then succeeds."""
    c = await db.webauthn_challenges.find_one({"id": cid, "purpose": purpose})
    if c:
        await db.webauthn_challenges.delete_one({"id": cid})
    if not c or c["origin"] != origin or datetime.fromisoformat(c["expires_at"]) < datetime.now(timezone.utc):
        raise HTTPException(400, "Request expired. Please try again.")
    return c


class RegVerifyIn(BaseModel):
    challenge_id: str = Field(max_length=64)
    credential: dict
    name: str = Field(default="This device", max_length=40)


class LoginOptIn(BaseModel):
    email: str | None = Field(default=None, max_length=120)


class LoginVerifyIn(BaseModel):
    challenge_id: str = Field(max_length=64)
    credential: dict


@router.post("/register/options")
async def register_options(request: Request, user: dict = Depends(current_user)):
    db = get_db()
    origin, rp_id = _origin(request)
    have = await db.passkeys.find({"user_id": user["id"]}, {"_id": 0, "credential_id": 1}).to_list(20)
    if len(have) >= MAX_PASSKEYS:
        raise HTTPException(400, f"You can register up to {MAX_PASSKEYS} devices. Remove one first.")
    cid, ch = await _new_challenge(db, "register", origin, user["id"])
    return {"challenge_id": cid, "publicKey": {
        "challenge": ch, "rp": {"id": rp_id, "name": settings.CLINIC_NAME},
        "user": {"id": wa.b64u(user["id"].encode()), "name": user["email"], "displayName": user["name"]},
        "pubKeyCredParams": [{"type": "public-key", "alg": -7}, {"type": "public-key", "alg": -257}],
        "authenticatorSelection": {"authenticatorAttachment": "platform", "userVerification": "required", "residentKey": "preferred"},
        "excludeCredentials": [{"type": "public-key", "id": h["credential_id"]} for h in have],
        "attestation": "none", "timeout": 120000}}


@router.post("/register/verify", status_code=201)
async def register_verify(body: RegVerifyIn, request: Request, user: dict = Depends(current_user)):
    db = get_db()
    origin, rp_id = _origin(request)
    ch = await _take_challenge(db, body.challenge_id, "register", origin)
    if ch["user_id"] != user["id"]:
        raise HTTPException(400, "Request expired. Please try again.")
    try:
        r = wa.verify_registration(body.credential, ch["challenge"], origin, rp_id)
    except wa.WebAuthnError as e:
        raise HTTPException(400, str(e))
    if await db.passkeys.find_one({"credential_id": r["credential_id"]}):
        raise HTTPException(409, "This passkey is already registered")
    if await db.passkeys.count_documents({"user_id": user["id"]}) >= MAX_PASSKEYS:
        raise HTTPException(400, f"You can register up to {MAX_PASSKEYS} devices.")
    pid = new_id()
    await db.passkeys.insert_one({"id": pid, "user_id": user["id"], "name": body.name.strip() or "This device", "rp_id": rp_id, "created_at": now(), "last_used": None, **r})
    await audit(db, user["id"], "passkey_add", pid, client_ip(request), role=user["role"])
    await notify(db, user, "Fingerprint / face login added", f"A new device ({body.name}) can now log in to your account. If this was not you, remove it in Security and change your password.", "security", ("app", "email"))
    return {"id": pid, "name": body.name}


@router.post("/login/options")
async def login_options(body: LoginOptIn, request: Request):
    db = get_db()
    origin, rp_id = _origin(request)
    allow, uid = [], None
    if body.email:
        u = await db.users.find_one({"email": body.email.lower().strip()}, {"id": 1})
        if u:
            uid = u["id"]
            allow = [{"type": "public-key", "id": k["credential_id"]} for k in await db.passkeys.find({"user_id": uid, "rp_id": rp_id}, {"_id": 0, "credential_id": 1}).to_list(10)]
    cid, ch = await _new_challenge(db, "login", origin, None)  # same shape for known and unknown emails: nothing about accounts is revealed
    return {"challenge_id": cid, "publicKey": {"challenge": ch, "rpId": rp_id, "allowCredentials": allow, "userVerification": "required", "timeout": 120000}}


@router.post("/login/verify")
async def login_verify(body: LoginVerifyIn, request: Request):
    db = get_db()
    origin, rp_id = _origin(request)
    ch = await _take_challenge(db, body.challenge_id, "login", origin)
    fail = HTTPException(401, "Fingerprint / face login failed. Use your password instead.")
    cid = body.credential.get("rawId") if isinstance(body.credential, dict) else None
    stored = await db.passkeys.find_one({"credential_id": cid, "rp_id": rp_id}) if isinstance(cid, str) else None
    if not stored:
        raise fail
    user = await db.users.find_one({"id": stored["user_id"]})
    if not user:
        raise fail
    try:
        new_count = wa.verify_assertion(body.credential, ch["challenge"], origin, rp_id, stored)
    except wa.WebAuthnError as e:
        await audit(db, user["id"], "passkey_login_failed", str(e)[:80], client_ip(request), role=user["role"])
        raise fail
    if user.get("status") == "suspended":
        raise HTTPException(403, "Account suspended")
    if not user.get("email_verified"):
        raise HTTPException(403, "Please verify your email OTP first (log in with your password once)")
    await db.passkeys.update_one({"id": stored["id"]}, {"$set": {"sign_count": new_count, "last_used": now()}})
    return await _finish_login(db, user, request, "passkey")


@router.get("")
async def list_passkeys(user: dict = Depends(current_user)):
    return await get_db().passkeys.find({"user_id": user["id"]}, {"_id": 0, "public_key_pem": 0, "credential_id": 0, "alg": 0, "sign_count": 0, "user_id": 0}).sort("created_at", 1).to_list(20)


@router.delete("/{pid}")
async def remove_passkey(pid: str, request: Request, user: dict = Depends(current_user)):
    db = get_db()
    if not await db.passkeys.find_one({"id": pid, "user_id": user["id"]}):
        raise HTTPException(404, "Not found")
    await db.passkeys.delete_one({"id": pid, "user_id": user["id"]})
    await audit(db, user["id"], "passkey_remove", pid, client_ip(request), role=user["role"])
    return {"removed": True}
