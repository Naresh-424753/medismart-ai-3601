"""Smart Health Passport: a patient-controlled QR code that lets a VERIFIED clinician (approved doctor / hospital / nurse account)
see blood group, allergies, history, medicines, recent prescriptions and latest vitals in one screen.

Security model:
* The QR holds a random 192-bit token (never the data). Only its SHA-256 hash is used for lookup; the token itself is stored
  encrypted (Fernet, key derived from JWT_SECRET) so the patient can show the QR again. Changing JWT_SECRET invalidates old QR codes.
* Opening a passport needs a login with an admin-approved clinical role, so a found/stolen QR is useless to the public
  (the separate public emergency card shows only blood group, allergies and contacts).
* The patient chooses the validity (1 day to 1 year), can revoke or regenerate at any time, sees every view, gets a notification,
  and each view is written to the audit log and the patient's tamper-evident ledger.
* A nurse sees only what ROLE_SCOPE_CAP allows (no lab reports)."""
import base64
import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from cryptography.fernet import Fernet, InvalidToken
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..access import ROLE_SCOPE_CAP
from ..common import audit, new_id, notify, now
from ..config import settings
from ..db import get_db
from ..deps import require_roles
from ..services import ledger
from .patients import age_from_dob

router = APIRouter(prefix="/passport", tags=["health passport"])
patient_only = require_roles("patient")
clinician = require_roles("doctor", "hospital", "nurse")  # super_admin passes automatically


def _fernet() -> Fernet:
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(("passport|" + settings.JWT_SECRET).encode()).digest()))


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class IssueIn(BaseModel):
    days: int = Field(default=30, ge=1, le=365)


@router.post("/token", status_code=201)
async def issue(body: IssueIn, user: dict = Depends(patient_only)):
    """Creates a new QR token. Any earlier token stops working immediately."""
    db = get_db()
    await db.passport_tokens.update_many({"user_id": user["id"], "revoked": False}, {"$set": {"revoked": True, "revoked_at": now()}})
    token = secrets.token_urlsafe(24)
    exp = _iso(datetime.now(timezone.utc) + timedelta(days=body.days))
    await db.passport_tokens.insert_one({"id": new_id(), "user_id": user["id"], "token_hash": _hash(token), "token_enc": _fernet().encrypt(token.encode()).decode(),
                                         "created_at": now(), "expires_at": exp, "revoked": False})
    await audit(db, user["id"], "passport_issue", f"{body.days} days", role="patient")
    return {"token": token, "expires_at": exp}


async def _active(db, uid: str):
    t = await db.passport_tokens.find({"user_id": uid, "revoked": False}, {"_id": 0}).sort("created_at", -1).limit(1).to_list(1)
    return t[0] if t and t[0]["expires_at"] > now() else None


@router.get("/me")
async def mine(user: dict = Depends(patient_only)):
    db = get_db()
    t = await _active(db, user["id"])
    token = None
    if t:
        try:
            token = _fernet().decrypt(t["token_enc"].encode()).decode()
        except InvalidToken:
            token = None  # JWT_SECRET changed: ask the patient to regenerate
    views = await db.passport_views.find({"patient_user_id": user["id"]}, {"_id": 0, "patient_user_id": 0}).sort("ts", -1).limit(30).to_list(30)
    p = await db.patients.find_one({"user_id": user["id"]}, {"_id": 0, "health_id": 1}) or {}
    return {"active": bool(token), "token": token, "expires_at": t["expires_at"] if t else None, "needs_regenerate": bool(t and not token), "health_id": p.get("health_id"), "views": views}


@router.delete("/token")
async def revoke(user: dict = Depends(patient_only)):
    db = get_db()
    await db.passport_tokens.update_many({"user_id": user["id"], "revoked": False}, {"$set": {"revoked": True, "revoked_at": now()}})
    await audit(db, user["id"], "passport_revoke", "", role="patient")
    return {"revoked": True}


@router.get("/open/{token}")
async def open_passport(token: str, user: dict = Depends(clinician)):
    db = get_db()
    if not user.get("approved") and user["role"] != "super_admin":
        raise HTTPException(403, "Your account is pending admin verification")
    t = await db.passport_tokens.find_one({"token_hash": _hash(token[:100])}, {"_id": 0})
    if not t or t["revoked"]:
        raise HTTPException(404, "This Health Passport QR is invalid or was revoked")
    if t["expires_at"] <= now():
        raise HTTPException(410, "This Health Passport QR has expired. Ask the patient to generate a new one.")
    uid = t["user_id"]
    p = await db.patients.find_one({"user_id": uid}, {"_id": 0})
    u = await db.users.find_one({"id": uid}, {"_id": 0, "name": 1, "phone": 1})
    if not p or not u:
        raise HTTPException(404, "Patient not found")
    cap = ROLE_SCOPE_CAP.get(user["role"])
    can = lambda scope: cap is None or scope in cap
    meds = await db.medicines.find({"user_id": uid, "active": True}, {"_id": 0, "name": 1, "dose": 1, "times": 1, "end_date": 1, "instructions": 1}).to_list(50) if can("medicines") else []
    rx = []
    if can("medicines"):
        for r in await db.prescriptions.find({"patient_user_id": uid}, {"_id": 0}).sort("created_at", -1).limit(5).to_list(5):
            rx.append({"code": r["code"], "date": r["created_at"][:10], "doctor": r.get("doctor_name"), "diagnosis": r.get("diagnosis"), "notes": r.get("notes"),
                       "items": [{"name": i.get("name"), "dose": i.get("dose"), "times": i.get("times"), "days": i.get("duration_days"), "instructions": i.get("instructions")} for i in r.get("items", [])]})
    vit = []
    if can("vitals"):
        vit = await db.vitals.find({"patient_id": p["id"]}, {"_id": 0, "ecg": 0}).sort("ts", -1).limit(1).to_list(1)
    reports = []
    if can("reports"):
        for r in await db.reports.find({"user_id": uid}, {"_id": 0}).sort("ts", -1).limit(3).to_list(3):
            reports.append({"title": r["title"], "date": r["report_date"], "summary": r["summary"],
                            "abnormal": [{"test": f["test"], "value": f["value"], "unit": f["unit"], "status": f["status"]} for f in r.get("findings", []) if f["status"] != "normal"]})
    # record the view: audit log, tamper-evident ledger, passport history shown to the patient, and a (de-duplicated) notification
    last = await db.passport_views.find({"patient_user_id": uid, "viewer_id": user["id"]}, {"_id": 0}).sort("ts", -1).limit(1).to_list(1)
    await db.passport_views.insert_one({"id": new_id(), "patient_user_id": uid, "viewer_id": user["id"], "viewer_name": user["name"], "viewer_role": user["role"], "ts": now()})
    await audit(db, user["id"], "passport_view", uid, role=user["role"])
    await ledger.append(db, uid, "access_event", {"viewer_role": user["role"], "scope": "passport"}, actor=user["id"])
    pu = await db.users.find_one({"id": uid})
    if pu and not (last and (datetime.fromisoformat(now().replace("Z", "+00:00")) - datetime.fromisoformat(last[0]["ts"].replace("Z", "+00:00"))).total_seconds() < 600):
        await notify(db, pu, "Health Passport opened", f"{user['name']} ({user['role']}) opened your Health Passport.", "passport")
    return {
        "patient": {"name": u["name"], "photo_url": p.get("photo_url") or None, "age": age_from_dob(p.get("dob")), "sex": p.get("sex"), "dob": p.get("dob"), "blood_group": p.get("blood_group"), "health_id": p.get("health_id"),
                    "height_cm": p.get("height_cm"), "weight_kg": p.get("weight_kg"), "phone": u.get("phone")},
        "allergies": p.get("allergies", []), "conditions": p.get("diseases", []), "surgeries": p.get("surgeries", []), "vaccinations": p.get("vaccinations", []),
        "emergency_contacts": p.get("emergency_contacts", []), "insurance": p.get("insurance") or {},
        "medicines": meds, "prescriptions": rx, "latest_vitals": vit[0] if vit else None, "recent_reports": reports,
        "viewer_role": user["role"], "token_expires_at": t["expires_at"], "viewed_at": now(),
        "note": "Patient-provided and system data. Verify critical details with the patient or family. Your access has been recorded and the patient was notified.",
    }
