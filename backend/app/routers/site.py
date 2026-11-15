"""Public hospital website + patient bills.

Public (no login): /site/home, /site/doctors, /site/feedback (POST).
Admin: PUT /site/config, GET /site/feedback. Patient: /site/my-bills (list, UPI QR, report payment, PDF receipt).
Content (packages, insurers, blog, gallery, hours, parking) is edited by an admin and stored in db.site_config; nothing is hard-coded."""
import io
from datetime import datetime, timedelta
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..common import audit, new_id, notify, now
from ..config import settings
from ..db import get_db
from ..deps import require_roles

router = APIRouter(prefix="/site", tags=["hospital website"])
admin_only = require_roles("admin")  # super_admin passes automatically
patient_only = require_roles("patient")

DEPARTMENTS = [
    {"name": "Cardiology", "icon": "heart", "services": ["ECG & Echo", "Stress test", "Angiography", "Heart-failure clinic"]},
    {"name": "Neurology", "icon": "brain", "services": ["EEG", "Stroke care", "Epilepsy clinic", "Headache clinic"]},
    {"name": "Orthopedics", "icon": "bone", "services": ["Fracture care", "Joint replacement", "Sports injury", "Physiotherapy"]},
    {"name": "Pediatrics", "icon": "baby", "services": ["Vaccination", "Newborn care", "Growth monitoring", "Child emergency"]},
    {"name": "Gynecology", "icon": "female", "services": ["Antenatal care", "Delivery", "Ultrasound", "Family planning"]},
    {"name": "Dental", "icon": "tooth", "services": ["Check-up & cleaning", "Fillings", "Root canal", "Braces"]},
    {"name": "Other facilities", "icon": "plus", "services": ["24x7 pharmacy", "Pathology lab", "X-ray / CT / MRI", "Ambulance", "ICU", "Blood bank"]},
]


def _defaults() -> dict:
    return {
        "name": settings.CLINIC_NAME, "tagline": "", "address": settings.CLINIC_ADDRESS, "phone": settings.CLINIC_PHONE or settings.SUPPORT_PHONE,
        "email": settings.SUPPORT_EMAIL, "whatsapp": settings.SUPPORT_WHATSAPP, "emergency_phone": "112", "ambulance_phone": "108",
        "visiting_hours": "", "opd_hours": "", "parking": "", "map_query": settings.CLINIC_ADDRESS, "emergency_location": "",
        "departments": DEPARTMENTS, "packages": [], "insurers": [], "blog": [], "gallery": [],
    }


class PackageIn(BaseModel):
    name: str = Field(max_length=80)
    price: float = Field(ge=0)
    includes: list[str] = Field(default_factory=list, max_length=40)


class BlogIn(BaseModel):
    title: str = Field(max_length=120)
    body: str = Field(max_length=4000)
    date: str = ""


class GalleryIn(BaseModel):
    url: str = Field(pattern=r"^https://\S+$", max_length=500)
    caption: str = Field(default="", max_length=100)


class ConfigIn(BaseModel):
    name: str | None = Field(default=None, max_length=100)
    tagline: str | None = Field(default=None, max_length=160)
    address: str | None = Field(default=None, max_length=300)
    phone: str | None = Field(default=None, max_length=30)
    email: str | None = Field(default=None, max_length=100)
    whatsapp: str | None = Field(default=None, max_length=20)
    emergency_phone: str | None = Field(default=None, max_length=20)
    ambulance_phone: str | None = Field(default=None, max_length=20)
    visiting_hours: str | None = Field(default=None, max_length=200)
    opd_hours: str | None = Field(default=None, max_length=200)
    parking: str | None = Field(default=None, max_length=300)
    map_query: str | None = Field(default=None, max_length=200)
    emergency_location: str | None = Field(default=None, max_length=200)
    packages: list[PackageIn] | None = Field(default=None, max_length=30)
    insurers: list[str] | None = Field(default=None, max_length=80)
    blog: list[BlogIn] | None = Field(default=None, max_length=50)
    gallery: list[GalleryIn] | None = Field(default=None, max_length=40)


async def _config(db) -> dict:
    cfg = _defaults()
    saved = await db.site_config.find_one({"id": "main"}, {"_id": 0, "id": 0}) or {}
    cfg.update({k: v for k, v in saved.items() if v not in (None, "")})
    return cfg


@router.get("/home")
async def home():
    db = get_db()
    cfg = await _config(db)
    fb = await db.site_feedback.find({"public": True}, {"_id": 0, "email": 0}).sort("created_at", -1).limit(6).to_list(6)
    allfb = await db.site_feedback.find({}, {"rating": 1}).to_list(2000)
    cfg["feedback"] = fb
    cfg["rating_avg"] = round(sum(f["rating"] for f in allfb) / len(allfb), 1) if allfb else None
    cfg["rating_count"] = len(allfb)
    cfg["map_url"] = f"https://www.google.com/maps/search/?api=1&query={quote(cfg['map_query'])}" if cfg.get("map_query") else ""
    cfg["map_embed"] = f"https://www.google.com/maps?q={quote(cfg['map_query'])}&output=embed" if cfg.get("map_query") else ""
    return cfg


@router.put("/config")
async def save_config(body: ConfigIn, user: dict = Depends(admin_only)):
    db = get_db()
    d = body.model_dump(exclude_none=True)
    await db.site_config.update_one({"id": "main"}, {"$set": d, "$setOnInsert": {"id": "main"}}, upsert=True)
    await audit(db, user["id"], "site_config", ",".join(sorted(d)), role=user["role"])
    return await _config(db)


@router.get("/doctors")
async def doctors(q: str | None = None, specialization: str | None = None):
    """Public doctor directory with the next free slots (no login). Booking itself needs a patient login."""
    db = get_db()
    ok = {u["id"] async for u in db.users.find({"role": "doctor", "approved": True, "status": {"$ne": "suspended"}}, {"id": 1})}
    today = datetime.utcnow().date()
    out = []
    for d in await db.doctors.find({}, {"_id": 0}).to_list(300):
        if d["user_id"] not in ok:
            continue
        if specialization and specialization.lower() not in d["specialization"].lower():
            continue
        if q and q.lower() not in (d["name"] + d["specialization"] + (d.get("qualification") or "")).lower():
            continue
        av = d.get("availability") or {}
        slots = []
        for i in range(7):
            day = today + timedelta(days=i)
            if day.weekday() not in av.get("days", []):
                continue
            taken = {a["time"] async for a in db.appointments.find({"doctor_id": d["id"], "date": day.isoformat(), "status": {"$in": ["booked", "confirmed"]}})}
            for s in av.get("slots", []):
                if s not in taken and not (i == 0 and s <= datetime.utcnow().strftime("%H:%M")):
                    slots.append({"date": day.isoformat(), "time": s})
        out.append({**{k: d.get(k) for k in ("id", "name", "specialization", "qualification", "experience_years", "opd_timing", "photo_url", "fee", "hospital", "city", "rating", "rating_count", "bio")},
                    "next_slots": slots[:6]})
    return sorted(out, key=lambda x: -(x.get("rating") or 0))


class FeedbackIn(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    email: str = Field(default="", max_length=120)
    rating: int = Field(ge=1, le=5)
    kind: str = Field(default="feedback", pattern=r"^(feedback|complaint)$")
    message: str = Field(min_length=5, max_length=1500)


@router.post("/feedback", status_code=201)
async def feedback(body: FeedbackIn):
    db = get_db()
    # complaints are never shown publicly; feedback shows on the site only after admin sets public=true
    await db.site_feedback.insert_one({"id": new_id(), **body.model_dump(), "public": False, "created_at": now()})
    return {"message": "Thank you. Your " + ("complaint was sent to the administration." if body.kind == "complaint" else "feedback was received.")}


@router.get("/feedback")
async def list_feedback(user: dict = Depends(admin_only)):
    return await get_db().site_feedback.find({}, {"_id": 0}).sort("created_at", -1).limit(300).to_list(300)


@router.patch("/feedback/{fid}")
async def publish_feedback(fid: str, public: bool, user: dict = Depends(admin_only)):
    db = get_db()
    if not await db.site_feedback.find_one({"id": fid, "kind": "feedback"}):
        raise HTTPException(404, "Feedback not found")
    await db.site_feedback.update_one({"id": fid}, {"$set": {"public": public}})
    return {"ok": True}


# ---------------- patient bills ----------------
async def _my_bill(db, user, bid):
    b = await db.bills.find_one({"id": bid, "patient_user_id": user["id"]}, {"_id": 0})
    if not b:
        raise HTTPException(404, "Bill not found")
    h = await db.hospitals.find_one({"id": b["hospital_id"]}, {"_id": 0}) or {}
    return b, h


@router.get("/my-bills")
async def my_bills(user: dict = Depends(patient_only)):
    db = get_db()
    bills = await db.bills.find({"patient_user_id": user["id"]}, {"_id": 0}).sort("created_at", -1).limit(100).to_list(100)
    names = {h["id"]: h["name"] async for h in db.hospitals.find({}, {"id": 1, "name": 1})}
    p = await db.patients.find_one({"user_id": user["id"]}, {"_id": 0}) or {}
    for b in bills:
        b["hospital_name"] = names.get(b["hospital_id"], "")
    return {"bills": bills, "pending_total": round(sum(b["total"] for b in bills if b["status"] != "paid"), 2),
            "insurance": p.get("insurance") or {}}


class InsuranceIn(BaseModel):
    provider: str = Field(default="", max_length=80)
    policy_no: str = Field(default="", max_length=40)
    tpa: str = Field(default="", max_length=80)
    valid_till: str = Field(default="", max_length=10)


@router.put("/my-insurance")
async def my_insurance(body: InsuranceIn, user: dict = Depends(patient_only)):
    await get_db().patients.update_one({"user_id": user["id"]}, {"$set": {"insurance": body.model_dump()}})
    return body.model_dump()


@router.get("/my-bills/{bid}/pay")
async def pay_info(bid: str, user: dict = Depends(patient_only)):
    b, h = await _my_bill(get_db(), user, bid)
    if b["status"] == "paid":
        raise HTTPException(400, "Already paid")
    vpa = h.get("upi_id")
    demo = not vpa
    if demo and not settings.DEV_MODE:
        raise HTTPException(409, "This hospital has not set up UPI payments yet. Please pay at the billing counter.")
    vpa = vpa or "demo@medismart"
    uri = f"upi://pay?pa={quote(vpa)}&pn={quote(h.get('name', 'Hospital')[:40])}&am={b['total']:.2f}&cu=INR&tn={quote('Bill ' + bid[:8])}&tr={bid[:20]}"
    return {"upi_uri": uri, "amount": b["total"], "payee": h.get("name", ""), "vpa": vpa, "demo": demo}


class UtrIn(BaseModel):
    utr: str = Field(pattern=r"^\d{12}$")


@router.post("/my-bills/{bid}/pay")
async def report_payment(bid: str, body: UtrIn, user: dict = Depends(patient_only)):
    """Patient says they paid. The bill stays 'unpaid' until the hospital checks its UPI app and confirms; then it becomes 'paid'."""
    db = get_db()
    b, h = await _my_bill(db, user, bid)
    if b["status"] == "paid":
        raise HTTPException(400, "Already paid")
    await db.bills.update_one({"id": bid}, {"$set": {"utr": body.utr, "payment_reported_at": now()}})
    hu = await db.users.find_one({"id": h.get("user_id")}) if h.get("user_id") else None
    if hu:
        await notify(db, hu, "Bill payment to verify", f"{b['patient_name']} reports paying Rs {b['total']:.0f} (UPI ref {body.utr}). Check your UPI app and confirm.", "bill")
    return {"status": "waiting_for_hospital_confirmation"}


@router.get("/my-bills/{bid}/receipt")
async def receipt(bid: str, user: dict = Depends(patient_only)):
    from fastapi.responses import Response
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    b, h = await _my_bill(get_db(), user, bid)
    if b["status"] != "paid":
        raise HTTPException(400, "Receipt is available after the hospital confirms payment")
    ss = getSampleStyleSheet()
    esc = lambda t: str(t or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm, bottomMargin=16 * mm, title="Payment receipt")
    rows = [["Item", "Amount (Rs)"]] + [[esc(i["name"]), f"{i['amount']:.2f}"] for i in b["items"]] + [["Total", f"{b['total']:.2f}"]]
    t = Table(rows, colWidths=[120 * mm, 40 * mm])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#047857")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white), ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                           ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"), ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#cbd5e1"))]))
    how = "Cash" if b.get("payment_method") == "cash" else f"UPI (ref {esc(b.get('utr'))})"
    doc.build([Paragraph(esc(h.get("name", "Hospital")), ss["Title"]), Paragraph(esc(h.get("address", "")), ss["Normal"]), Spacer(1, 8 * mm),
               Paragraph("<b>PAYMENT RECEIPT</b>", ss["Heading2"]),
               Paragraph(f"Receipt no: {esc(bid[:8].upper())} &nbsp;&nbsp; Patient: {esc(b['patient_name'])}", ss["Normal"]),
               Paragraph(f"Billed: {esc(b['created_at'][:10])} &nbsp;&nbsp; Paid: {esc((b.get('paid_at') or '')[:10])} &nbsp;&nbsp; Mode: {how}", ss["Normal"]),
               Spacer(1, 6 * mm), t, Spacer(1, 8 * mm), Paragraph("Computer-generated receipt. Payment status was confirmed by the hospital.", ss["Italic"])])
    return Response(buf.getvalue(), media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="receipt-{bid[:8]}.pdf"'})
