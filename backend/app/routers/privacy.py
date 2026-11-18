"""User privacy & session control: login history, active devices, remote logout, data export, account deletion."""
import time

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from ..common import audit, now, notify
from ..db import get_db
from ..deps import client_ip, current_user
from ..security import verify_password
from ..services import audit_logger
from .admin import erase_account

router = APIRouter(prefix="/privacy", tags=["privacy"])


def mask_phone(p: str) -> str:
    d = "".join(c for c in (p or "") if c.isdigit())
    return ("*" * (len(d) - 2) + d[-2:]) if len(d) > 4 else ("*" * len(d))


def mask_email(e: str) -> str:
    if not e or "@" not in e:
        return e or ""
    n, dom = e.split("@", 1)
    return (n[:1] + "*" * max(len(n) - 1, 2)) + "@" + dom


@router.get("/login-history")
async def my_login_history(user: dict = Depends(current_user)):
    rows = await get_db().login_history.find({"user_id": user["id"]}, {"_id": 0}).sort("ts", -1).limit(50).to_list(50)
    return rows


@router.get("/access-log")
async def who_accessed_my_data(user: dict = Depends(current_user)):
    """Everyone (doctor, family, admin...) who read or downloaded your records, including refused attempts. Part of the tamper-proof audit chain."""
    db = get_db()
    rows = await audit_logger.trail_for(db, user["id"])
    names: dict = {}
    out = []
    for r in rows:
        uid = r.get("user_id")
        if uid not in names:
            u = await db.users.find_one({"id": uid}, {"name": 1, "role": 1}) if uid else None
            names[uid] = (u or {}).get("name", "deleted user")
        out.append({"when": r["ts"], "who": names[uid], "role": r.get("role"), "action": r["action"], "what": r["detail"].split("|", 1)[-1], "ip": r.get("ip")})
    return out


@router.get("/sessions")
async def my_sessions(user: dict = Depends(current_user)):
    """Active devices. A session disappears when you log out, are logged out remotely, or its token expires."""
    db = get_db()
    out = []
    async for s in db.sessions.find({"user_id": user["id"]}, {"_id": 0}).sort("created", -1).limit(30):
        if await db.revoked_tokens.find_one({"jti": s["id"]}):
            continue
        out.append({**s, "current": s["id"] == user["_jti"]})
    return out


@router.delete("/sessions/{sid}")
async def end_session(sid: str, user: dict = Depends(current_user)):
    db = get_db()
    s = await db.sessions.find_one({"id": sid, "user_id": user["id"]})
    if not s:
        raise HTTPException(404, "Session not found")
    await db.revoked_tokens.insert_one({"jti": sid, "ts": now()})
    await db.sessions.delete_one({"id": sid})
    await audit(db, user["id"], "session_revoked", sid[:8], role=user["role"])
    return {"ended": sid}


@router.post("/logout-all")
async def logout_all(request: Request, user: dict = Depends(current_user)):
    """Kills every token issued before now, on every device, including this one."""
    db = get_db()
    await db.users.update_one({"id": user["id"]}, {"$set": {"sessions_valid_after": int(time.time())}})
    async for s in db.sessions.find({"user_id": user["id"]}, {"_id": 0, "id": 1}):  # also covers tokens issued in the same second
        await db.revoked_tokens.insert_one({"jti": s["id"], "ts": now()})
    await db.revoked_tokens.insert_one({"jti": user["_jti"], "ts": now()})
    await db.sessions.delete_many({"user_id": user["id"]})
    await audit(db, user["id"], "logout_all", "", client_ip(request), user["role"])
    return {"message": "Logged out from all devices. Please log in again."}


@router.get("/export")
async def export_my_data(user: dict = Depends(current_user)):
    """Everything personal we hold about you, as JSON (right of access / portability)."""
    from .admin import _OWNED
    db = get_db()
    out = {"exported_at": now(), "account": {k: user.get(k) for k in ("id", "name", "email", "phone", "role", "created_at", "two_factor")}}
    skip = {"login_history", "notifications"}
    for col, field in _OWNED:
        if col in skip or col in ("sessions", "passkeys", "passport_tokens", "media"):
            continue
        rows = await db[col].find({field: user["id"]}, {"_id": 0}).limit(2000).to_list(2000)
        if rows:
            out[col] = rows
    out["login_history"] = await db.login_history.find({"user_id": user["id"]}, {"_id": 0}).sort("ts", -1).limit(200).to_list(200)
    await audit(db, user["id"], "data_export", "", role=user["role"])
    return out


class DeleteIn(BaseModel):
    password: str = Field(min_length=1, max_length=128)
    confirm: str = Field(default="", max_length=20)


@router.post("/delete-account")
async def delete_my_account(body: DeleteIn, request: Request, user: dict = Depends(current_user)):
    """Self-service erasure. Needs your password and the word DELETE. Super admin / admin accounts are removed by a super admin instead."""
    db = get_db()
    if user["role"] in ("admin", "super_admin"):
        raise HTTPException(403, "Admin accounts cannot self-delete; ask a super admin")
    if body.confirm != "DELETE":
        raise HTTPException(400, 'Type DELETE to confirm')
    full = await db.users.find_one({"id": user["id"]})
    if not verify_password(body.password, full["password_hash"]):
        raise HTTPException(400, "Password is incorrect")
    ip = client_ip(request)
    await erase_account(db, user["id"])
    await db.otps.delete_many({"email": full["email"]})
    await db.revoked_tokens.insert_one({"jti": user["_jti"], "ts": now()})
    await db.users.delete_one({"id": user["id"]})
    await audit(db, None, "account_self_deleted", f"{full['email']} ({full['role']})", ip)  # the tamper-evident audit trail is kept by design
    return {"message": "Your account and personal data were deleted."}
