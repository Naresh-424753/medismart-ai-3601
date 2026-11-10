import json
import os

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field

from ..common import audit, new_id, notify, now, public_user
from ..db import get_db
from ..deps import current_user, require_roles
from ..services import blobstore

router = APIRouter(prefix="/admin", tags=["admin"])
admin_only = require_roles("admin")  # super_admin passes automatically
super_only = require_roles("super_admin")


@router.get("/stats")
async def stats(user: dict = Depends(admin_only)):
    db = get_db()
    users = await db.users.find({}, {"_id": 0, "role": 1, "approved": 1, "status": 1}).to_list(100000)
    by_role: dict = {}
    for u in users:
        by_role[u["role"]] = by_role.get(u["role"], 0) + 1
    return {"users": len(users), "by_role": by_role, "pending_approvals": sum(1 for u in users if not u.get("approved")),
            "appointments": await db.appointments.count_documents({}), "open_emergencies": await db.emergency_alerts.count_documents({"status": "open"}),
            "reports": await db.reports.count_documents({}), "vitals_readings": await db.vitals.count_documents({}),
            "suspicious_logins": await db.audit_logs.count_documents({"action": "suspicious_login"})}


@router.get("/users")
async def users(role: str | None = None, pending: bool = False, q: str | None = None, user: dict = Depends(admin_only)):
    f: dict = {}
    if role:
        f["role"] = role
    if pending:
        f["approved"] = False
    rows = await get_db().users.find(f).sort("created_at", -1).limit(500).to_list(500)
    out = [public_user(u) for u in rows if not q or q.lower() in (u["name"] + u["email"]).lower()]
    return out


@router.patch("/users/{uid}")
async def update_user(uid: str, approved: bool | None = None, suspended: bool | None = None, user: dict = Depends(admin_only)):
    db = get_db()
    target = await db.users.find_one({"id": uid})
    if not target:
        raise HTTPException(404, "User not found")
    if target["role"] == "super_admin" or (target["role"] == "admin" and user["role"] != "super_admin"):
        raise HTTPException(403, "Only a super admin can change admin accounts")
    upd = {}
    if approved is not None:
        upd["approved"] = approved
    if suspended is not None:
        upd["status"] = "suspended" if suspended else "active"
    if upd:
        await db.users.update_one({"id": uid}, {"$set": upd})
        if upd.get("approved"):
            await db.hospitals.update_one({"user_id": uid}, {"$set": {"verified": True}})
            await notify(db, target, "Account approved", "Your account has been verified by the admin team.", "account")
        if "approved" in upd and not upd["approved"]:
            await db.hospitals.update_one({"user_id": uid}, {"$set": {"verified": False}})
        await audit(db, user["id"], "admin_update_user", f"{uid} {upd}")
    return {"id": uid, **upd}


# Personal data removed together with an account: (collection, field holding the user id)
_OWNED = [("assistant_sessions", "user_id"), ("medicines", "user_id"), ("med_logs", "user_id"), ("med_reminders", "user_id"), ("med_orders", "user_id"), ("notifications", "user_id"),
          ("events", "user_id"), ("reports", "user_id"), ("risk_assessments", "user_id"), ("rx_images", "user_id"), ("rx_scans", "user_id"),
          ("imaging_results", "user_id"), ("chat_history", "user_id"), ("login_history", "user_id"), ("wearable_samples", "user_id"),
          ("ews_state", "user_id"), ("ews_settings", "user_id"), ("ews_events", "user_id"), ("consents", "patient_user_id"),
          ("appointments", "patient_user_id"), ("pharmacy_stock", "user_id"), ("pharmacies", "user_id"), ("hospitals", "user_id"),
          ("doctors", "user_id"), ("patients", "user_id")]


@router.delete("/users/{uid}")
async def delete_user(uid: str, user: dict = Depends(admin_only)):
    """Permanently deletes an account and its personal data. The tamper-evident ledger and the audit log are kept on purpose."""
    db = get_db()
    target = await db.users.find_one({"id": uid})
    if not target:
        raise HTTPException(404, "User not found")
    if uid == user["id"]:
        raise HTTPException(400, "You cannot delete your own account")
    if target["role"] == "super_admin":
        raise HTTPException(403, "The super admin account cannot be deleted")
    if target["role"] == "admin" and user["role"] != "super_admin":
        raise HTTPException(403, "Only a super admin can delete admin accounts")
    pat = await db.patients.find_one({"user_id": uid}, {"_id": 0, "id": 1})
    if pat:
        for col in ("vitals", "vital_alerts", "board_cases"):
            await db[col].delete_many({"patient_id": pat["id"]})
    async for d in db.documents.find({"user_id": uid}, {"_id": 0, "id": 1}):
        blobstore.delete(uid, d["id"])
    await db.documents.delete_many({"user_id": uid})
    # a doctor's future appointments are cancelled, not erased from the patients' history
    await db.appointments.update_many({"doctor_user_id": uid, "status": {"$in": ["booked", "confirmed"]}}, {"$set": {"status": "cancelled"}})
    counts = {}
    for col, field in _OWNED:
        r = await db[col].delete_many({field: uid})
        n = getattr(r, "deleted_count", 0)
        if n:
            counts[col] = n
    await db.otps.delete_many({"email": target["email"]})
    await db.users.delete_one({"id": uid})
    await audit(db, user["id"], "admin_delete_user", f"{target['email']} ({target['role']})")
    return {"deleted": uid, "email": target["email"], "removed": counts}


@router.post("/admins")
async def create_admin(email: str, user: dict = Depends(super_only)):
    db = get_db()
    t = await db.users.find_one({"email": email.lower()})
    if not t:
        raise HTTPException(404, "User not found")
    await db.users.update_one({"id": t["id"]}, {"$set": {"role": "admin", "approved": True}})
    await audit(db, user["id"], "make_admin", email)
    return {"ok": True}


class NewAdminIn(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    email: EmailStr
    phone: str = Field(default="", max_length=20)
    password: str


@router.post("/admins/create", status_code=201)
async def create_admin_account(body: NewAdminIn, user: dict = Depends(super_only)):
    """Super admin creates a brand-new admin account (already verified and approved). Share the password with that person privately."""
    from ..security import hash_password, password_problem
    db = get_db()
    if (p := password_problem(body.password)):
        raise HTTPException(400, p)
    email = body.email.lower()
    if await db.users.find_one({"email": email}):
        raise HTTPException(409, "An account with this email already exists - use 'Make admin' on that account instead")
    uid = new_id()
    await db.users.insert_one({"id": uid, "name": body.name.strip(), "email": email, "phone": body.phone, "role": "admin", "password_hash": hash_password(body.password),
                               "email_verified": True, "approved": True, "status": "active", "two_factor": False, "created_by": user["id"], "created_at": now()})
    await audit(db, user["id"], "create_admin", email, role=user["role"])
    return {"id": uid, "email": email, "role": "admin"}


@router.post("/admins/{uid}/demote")
async def demote_admin(uid: str, user: dict = Depends(super_only)):
    db = get_db()
    t = await db.users.find_one({"id": uid})
    if not t or t["role"] != "admin":
        raise HTTPException(404, "Admin not found")
    await db.users.update_one({"id": uid}, {"$set": {"role": "patient"}})
    await audit(db, user["id"], "demote_admin", t["email"], role=user["role"])
    return {"ok": True}


@router.get("/users/{uid}/detail")
async def user_detail(uid: str, user: dict = Depends(super_only)):
    """Everything about one ACCOUNT: identity, status, role profile, how much data it holds (counts only), logins and recent audit entries.
    Password hashes, OTP codes and the contents of medical records are never returned. Each view is written to the audit trail."""
    db = get_db()
    t = await db.users.find_one({"id": uid})
    if not t:
        raise HTTPException(404, "User not found")
    profiles = {}
    for col in ("patients", "doctors", "hospitals", "pharmacies"):
        d = await db[col].find_one({"user_id": uid}, {"_id": 0})
        if d:
            profiles[col] = {k: v for k, v in d.items() if k not in ("allergies", "conditions", "chronic_conditions", "medical_history")}
    counts = {}
    for col, field in _OWNED:
        if col in ("login_history", "patients", "doctors", "hospitals", "pharmacies", "pharmacy_stock", "consents", "appointments"):
            continue
        n = await db[col].count_documents({field: uid})
        if n:
            counts[col] = n
    appts = await db.appointments.count_documents({"$or": [{"patient_user_id": uid}, {"doctor_user_id": uid}]})
    if appts:
        counts["appointments"] = appts
    logins = await db.login_history.find({"user_id": uid}, {"_id": 0}).sort("ts", -1).limit(10).to_list(10)
    acts = await db.audit_logs.find({"user_id": uid}, {"_id": 0, "seq": 1, "action": 1, "detail": 1, "ts": 1}).sort("ts", -1).limit(15).to_list(15)
    await audit(db, user["id"], "view_account_detail", t["email"], role=user["role"])
    safe = {k: v for k, v in public_user(t).items() if not any(x in k.lower() for x in ("otp", "hash", "secret", "token", "totp"))}
    return {"user": safe, "profiles": profiles, "data_counts": counts, "recent_logins": logins, "recent_activity": acts,
            "two_factor": bool(t.get("two_factor")), "email_verified": bool(t.get("email_verified")), "created_by": t.get("created_by")}


ROLE_MATRIX = {
    "super_admin": "Everything, incl. promoting admins and deleting accounts",
    "admin": "Approve users, suspend/delete accounts, read audit logs, contact inbox",
    "doctor": "Own appointments, prescriptions, patients with an appointment or consent",
    "nurse": "Read-only summary, vitals and medicines of patients who shared them (never documents or lab reports)",
    "lab": "Lab bookings, enter and verify results",
    "pharmacist": "Pharmacy stock, orders, prescription verification",
    "patient": "Own record, consents, bookings, reports",
    "family": "Whatever the patient shares by consent",
}


@router.get("/system-check")
async def system_check(user: dict = Depends(admin_only)):
    """Which integrations are configured (booleans only - never the values) and whether Gemini is healthy."""
    from ..services import gemini
    from ..common import email_configured
    from ..config import settings as st
    return {"gemini": gemini.status(), "email": email_configured(), "twilio_sms": bool(st.TWILIO_SID and st.TWILIO_SMS_FROM), "twilio_whatsapp": bool(st.TWILIO_SID and st.TWILIO_WA_FROM),
            "mongo_mock": getattr(__import__("app.db", fromlist=["is_mock"]), "is_mock", lambda: False)(), "gcs": bool(st.GCS_BUCKET), "env_problems": env_problems()}


def env_problems() -> list[str]:
    from ..config import settings as st
    out = []
    if len(st.JWT_SECRET) < 32 or st.JWT_SECRET.startswith(("change", "dev", "secret")):
        out.append("JWT_SECRET is short or a placeholder")
    if not st.DATA_KEY:
        out.append("DATA_KEY is not set (documents are encrypted with a key derived from JWT_SECRET)")
    if getattr(st, "DEV_MODE", False):
        out.append("DEV_MODE is on: OTPs are printed to the log")
    return out


@router.get("/roles")
async def roles(user: dict = Depends(admin_only)):
    return ROLE_MATRIX


@router.get("/audit-logs/verify")
async def verify_audit(user: dict = Depends(admin_only)):
    """Recomputes the audit hash chain. `ok: false` with `broken_at` means a row was edited, removed or inserted after the fact."""
    from ..common import AUDIT_GENESIS, audit_hash
    db = get_db()
    prev, n, broken = AUDIT_GENESIS, 0, None
    async for e in db.audit_logs.find({"seq": {"$exists": True}}, {"_id": 0}).sort("seq", 1):
        n += 1
        if e["seq"] != n or e.get("prev_hash") != prev or audit_hash(e, prev) != e.get("hash"):
            broken = e["seq"]
            break
        prev = e["hash"]
    return {"ok": broken is None, "entries": n, "broken_at": broken, "head_hash": prev,
            "note": "Publish or e-mail head_hash regularly: someone who rewrites the whole chain can only be caught by comparing it with an earlier copy."}


@router.get("/audit-logs")
async def audit_logs(action: str | None = None, limit: int = 200, user: dict = Depends(admin_only)):
    q = {"action": action} if action else {}
    return await get_db().audit_logs.find(q, {"_id": 0}).sort("ts", -1).limit(min(limit, 1000)).to_list(1000)


@router.get("/login-history")
async def login_history(user_id: str | None = None, user: dict = Depends(admin_only)):
    q = {"user_id": user_id} if user_id else {}
    return await get_db().login_history.find(q, {"_id": 0}).sort("ts", -1).limit(300).to_list(300)


@router.post("/backup")
async def backup(user: dict = Depends(super_only)):
    """Dumps non-sensitive collections to JSON files on the server (use mongodump for full production backups)."""
    db = get_db()
    folder = os.path.join("data", "backups", now().replace(":", "-"))
    os.makedirs(folder, exist_ok=True)
    counts = {}
    for c in ["users", "patients", "doctors", "appointments", "reports", "medicines", "hospitals", "audit_logs"]:
        rows = await db[c].find({}, {"_id": 0, "password_hash": 0}).to_list(1000000)
        with open(os.path.join(folder, c + ".json"), "w") as f:
            json.dump(rows, f, default=str)
        counts[c] = len(rows)
    await audit(db, user["id"], "backup", folder)
    return {"folder": folder, "counts": counts}


# ---- family dashboard ----
family = APIRouter(prefix="/family", tags=["family"])


@family.get("/patients")
async def family_patients(user: dict = Depends(require_roles("family", "nurse"))):
    """Patients who granted this account access (via consent). Nurses only ever get the scopes in ROLE_SCOPE_CAP."""
    from ..access import ROLE_SCOPE_CAP
    cap = ROLE_SCOPE_CAP.get(user["role"])
    db = get_db()
    out = []
    async for c in db.consents.find({"grantee_email": user["email"], "active": True}, {"_id": 0}):
        if c.get("expires") and c["expires"] < now()[:10]:
            continue
        u = await db.users.find_one({"id": c["patient_user_id"]}, {"_id": 0, "name": 1})
        out.append({"patient_user_id": c["patient_user_id"], "name": u["name"] if u else "?", "scopes": [x for x in c["scopes"] if cap is None or x in cap], "expires": c.get("expires")})
    return out
