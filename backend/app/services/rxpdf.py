"""Prescription PDF (ReportLab): clinic header, patient block, medicines table, interaction warnings, signature block with QR.

The "digital signature" is an HMAC code issued by this server (verifiable at /prescriptions/verify/<code> and through the
QR). It proves the prescription was issued by this system and not altered; it is NOT a legal Digital Signature Certificate
(DSC / eSign). Add one if your jurisdiction requires it."""
from __future__ import annotations

import io

from reportlab.graphics import renderPDF
from reportlab.graphics.barcode.qr import QrCodeWidget
from reportlab.graphics.shapes import Drawing
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Flowable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from ..config import settings

BRAND = colors.HexColor("#047857")
_ss = getSampleStyleSheet()
H = ParagraphStyle("h", parent=_ss["Title"], textColor=BRAND, fontSize=20, leading=24, alignment=0, spaceAfter=0)
SMALL = ParagraphStyle("s", parent=_ss["Normal"], fontSize=8.5, leading=11, textColor=colors.HexColor("#475569"))
N = ParagraphStyle("n", parent=_ss["Normal"], fontSize=10, leading=13)
B = ParagraphStyle("b", parent=N, fontName="Helvetica-Bold")


def _esc(t) -> str:
    return str(t or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


class _QR(Flowable):
    def __init__(self, value: str, size: float = 26 * mm):
        super().__init__()
        self.value, self.size = value, size
        self.width = self.height = size

    def draw(self):
        w = QrCodeWidget(self.value)
        x1, y1, x2, y2 = w.getBounds()
        d = Drawing(self.size, self.size, transform=[self.size / (x2 - x1), 0, 0, self.size / (y2 - y1), 0, 0])
        d.add(w)
        renderPDF.draw(d, self.canv, 0, 0)


def build(rx: dict, patient: dict, doctor: dict, signature: str) -> bytes:
    """rx: prescription doc; patient: {name, age, sex, phone, allergies}; doctor: {name, specialization, license_no, hospital}."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm, topMargin=14 * mm, bottomMargin=16 * mm,
                            title=f"Prescription {rx['code']}", author=doctor.get("name", ""))
    el = []
    head_l = [Paragraph(_esc(settings.CLINIC_NAME), H)]
    for line in (settings.CLINIC_ADDRESS, ("Ph: " + settings.CLINIC_PHONE) if settings.CLINIC_PHONE else "", ("Reg. No: " + settings.CLINIC_REG_NO) if settings.CLINIC_REG_NO else ""):
        if line:
            head_l.append(Paragraph(_esc(line), SMALL))
    head_r = [Paragraph(f"<b>Dr. {_esc(doctor.get('name'))}</b>", N), Paragraph(_esc(doctor.get("specialization")), SMALL)]
    if doctor.get("license_no"):
        head_r.append(Paragraph("Reg. No: " + _esc(doctor["license_no"]), SMALL))
    if doctor.get("hospital"):
        head_r.append(Paragraph(_esc(doctor["hospital"]), SMALL))
    t = Table([[head_l, head_r]], colWidths=[100 * mm, 78 * mm])
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LINEBELOW", (0, 0), (-1, 0), 1.5, BRAND), ("BOTTOMPADDING", (0, 0), (-1, -1), 6), ("ALIGN", (1, 0), (1, 0), "RIGHT")]))
    el += [t, Spacer(1, 4 * mm)]

    age = f"{patient.get('age')} yrs" if patient.get("age") is not None else ""
    info = [[Paragraph(f"<b>Patient:</b> {_esc(patient.get('name'))}", N), Paragraph(f"<b>Age/Sex:</b> {_esc(age)} {_esc(patient.get('sex'))}", N), Paragraph(f"<b>Date:</b> {_esc(rx['created_at'][:10])}", N)],
            [Paragraph(f"<b>Rx No:</b> {_esc(rx['code'])}", N), Paragraph(f"<b>Phone:</b> {_esc(patient.get('phone'))}", N), Paragraph(f"<b>Allergies:</b> {_esc(', '.join(patient.get('allergies') or []) or 'none recorded')}", N)]]
    it = Table(info, colWidths=[62 * mm, 50 * mm, 66 * mm])
    it.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")), ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8fafc")), ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
    el += [it, Spacer(1, 3 * mm)]
    if rx.get("diagnosis"):
        el += [Paragraph(f"<b>Diagnosis / complaint:</b> {_esc(rx['diagnosis'])}", N), Spacer(1, 3 * mm)]

    el.append(Paragraph("<font size=18 color='#047857'><b>Rx</b></font>", ParagraphStyle("rx", parent=N, leading=24, spaceAfter=3)))
    rows = [[Paragraph("<b>#</b>", N), Paragraph("<b>Medicine</b>", N), Paragraph("<b>Dose</b>", N), Paragraph("<b>When</b>", N), Paragraph("<b>Days</b>", N), Paragraph("<b>Instructions</b>", N)]]
    for i, m in enumerate(rx.get("items", []), 1):
        rows.append([str(i), Paragraph(_esc(m.get("name")), B), Paragraph(_esc(m.get("dose")), N), Paragraph(_esc(", ".join(m.get("times", []))), N), str(m.get("duration_days", "")), Paragraph(_esc(m.get("instructions")), N)])
    mt = Table(rows, colWidths=[8 * mm, 46 * mm, 24 * mm, 30 * mm, 15 * mm, 55 * mm], repeatRows=1)
    mt.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#d1fae5")), ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e1")), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    el += [mt, Spacer(1, 3 * mm)]
    if rx.get("warnings"):
        el.append(Paragraph("<b>Safety alerts:</b> " + "; ".join(_esc(w) for w in rx["warnings"]), ParagraphStyle("w", parent=N, textColor=colors.HexColor("#b45309"))))
        el.append(Spacer(1, 2 * mm))
    if rx.get("notes"):
        el += [Paragraph(f"<b>Advice:</b> {_esc(rx['notes'])}", N), Spacer(1, 3 * mm)]

    base = (settings.PUBLIC_API_URL or "").rstrip("/")
    verify_url = f"{base}/prescriptions/verify/{rx['code']}" if base else f"MEDISMART-RX:{rx['code']}:{signature}"
    sig = [Paragraph("<b>Digitally signed</b>", N), Paragraph(f"Dr. {_esc(doctor.get('name'))}", N), Paragraph(f"Issued: {_esc(rx['created_at'][:19].replace('T', ' '))} UTC", SMALL),
           Paragraph(f"Signature code: <font face='Courier'>{_esc(signature)}</font>", SMALL), Paragraph("Scan the QR or open the link to verify this prescription.", SMALL)]
    st = Table([[sig, _QR(verify_url)]], colWidths=[140 * mm, 38 * mm])
    st.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LINEABOVE", (0, 0), (-1, 0), 0.5, colors.HexColor("#94a3b8")), ("TOPPADDING", (0, 0), (-1, -1), 6)]))
    el += [Spacer(1, 6 * mm), st, Spacer(1, 3 * mm),
           Paragraph("This prescription was generated electronically. Take medicines only as directed; do not share them. In an emergency call 112 / 108.", SMALL)]
    doc.build(el)
    return buf.getvalue()
