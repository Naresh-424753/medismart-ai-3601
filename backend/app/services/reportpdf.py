"""PDF of an AI report analysis (ReportLab): patient block, summary, results table with status colours, notes, comparison, disclaimer.
Automated screening only: not a diagnosis and not a laboratory-issued report."""
from __future__ import annotations

import io

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from ..config import settings

BRAND = colors.HexColor("#047857")
_ss = getSampleStyleSheet()
H = ParagraphStyle("h", parent=_ss["Title"], textColor=BRAND, fontSize=19, leading=23, alignment=0, spaceAfter=0)
N = ParagraphStyle("n", parent=_ss["Normal"], fontSize=9.5, leading=12.5)
S = ParagraphStyle("s", parent=N, fontSize=8, leading=10.5, textColor=colors.HexColor("#475569"))
H2 = ParagraphStyle("h2", parent=_ss["Heading2"], fontSize=12, textColor=BRAND, spaceBefore=8, spaceAfter=3)
TONE = {"normal": colors.HexColor("#047857"), "low": colors.HexColor("#b45309"), "high": colors.HexColor("#b45309")}


def _e(t) -> str:
    return str(t if t is not None else "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _n(v) -> str:
    try:
        f = float(v)
        return str(int(f)) if f == int(f) else f"{f:.2f}".rstrip("0").rstrip(".")
    except (TypeError, ValueError):
        return _e(v)


def build_pdf(doc: dict, patient: dict) -> bytes:
    buf = io.BytesIO()
    pdf = SimpleDocTemplate(buf, pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm, topMargin=14 * mm, bottomMargin=16 * mm,
                            title=f"AI report analysis - {doc.get('title', '')}", author=settings.CLINIC_NAME)
    el = [Paragraph(_e(settings.CLINIC_NAME), H)]
    sub = " · ".join(x for x in (settings.CLINIC_ADDRESS, settings.CLINIC_PHONE, f"Reg. {settings.CLINIC_REG_NO}" if settings.CLINIC_REG_NO else "") if x)
    if sub:
        el.append(Paragraph(_e(sub), S))
    el += [Spacer(1, 3 * mm), Paragraph("<b>AI REPORT ANALYSIS</b>", ParagraphStyle("t", parent=N, fontSize=12))]
    info = [[Paragraph(f"<b>Patient:</b> {_e(patient.get('name'))}", N), Paragraph(f"<b>Age / Sex:</b> {_e(patient.get('age') or '-')} / {_e(patient.get('sex') or '-')}", N)],
            [Paragraph(f"<b>Report:</b> {_e(doc.get('title'))}", N), Paragraph(f"<b>Report date:</b> {_e(doc.get('report_date'))}", N)],
            [Paragraph(f"<b>Analysed:</b> {_e((doc.get('ts') or '')[:16].replace('T', ' '))}", N), Paragraph(f"<b>Ref:</b> {_e(doc.get('id', '')[:8].upper())}", N)]]
    t = Table(info, colWidths=[95 * mm, 85 * mm])
    t.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e1")), ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8fafc")), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    el += [Spacer(1, 2 * mm), t, Paragraph("Summary", H2), Paragraph(_e(doc.get("summary")), N), Paragraph("Results", H2)]

    rows = [["Test", "Result", "Reference range", "Status"]]
    style = [("BACKGROUND", (0, 0), (-1, 0), BRAND), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white), ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"), ("FONTSIZE", (0, 0), (-1, -1), 9),
             ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#cbd5e1")), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]
    findings = doc.get("findings", [])
    for i, f in enumerate(findings, start=1):
        st = f.get("status", "normal")
        label = st.upper() if st == "normal" else f"{st.upper()} ({f.get('severity', '')})"
        rows.append([Paragraph(_e(f.get("test")), N), f"{_n(f.get('value'))} {f.get('unit', '')}".strip(), f"{_n(f.get('low'))} - {_n(f.get('high'))}", label])
        style += [("TEXTCOLOR", (3, i), (3, i), colors.HexColor("#b91c1c") if f.get("severity") == "critical" else TONE.get(st, colors.black)), ("FONTNAME", (3, i), (3, i), "Helvetica-Bold")]
        if st != "normal":
            style.append(("BACKGROUND", (0, i), (-1, i), colors.HexColor("#fffbeb")))
    tb = Table(rows, colWidths=[62 * mm, 34 * mm, 42 * mm, 42 * mm], repeatRows=1)
    tb.setStyle(TableStyle(style))
    el.append(tb)

    ab = [f for f in findings if f.get("status") != "normal"]
    if ab:
        el.append(Paragraph("What the abnormal values may mean", H2))
        el += [Paragraph(f"<b>{_e(f['test'])}</b> ({_e(f['status'])}): {_e(f.get('note'))}", N) for f in ab]
    cmp_ = doc.get("comparison") or []
    if cmp_:
        el.append(Paragraph("Compared with your previous values", H2))
        el += [Paragraph(f"{_e(c['test'])}: {_n(c['previous'])} → {_n(c['current'])} ({_e(c['trend'])}{' ' + _n(c['percent']) + '%' if c.get('percent') is not None else ''})", N) for c in cmp_]
    el += [Spacer(1, 6 * mm), Paragraph("<b>Important:</b> This is an automated screening interpretation using general adult reference ranges. Laboratories use different ranges. "
                                         "It is not a diagnosis and not a laboratory-issued report. Please discuss the results with your doctor.", S)]

    def footer(c, d):
        c.saveState(); c.setFont("Helvetica", 7.5); c.setFillColor(colors.HexColor("#64748b"))
        c.drawString(15 * mm, 9 * mm, f"{settings.CLINIC_NAME} - AI analysis, not a diagnosis"); c.drawRightString(195 * mm, 9 * mm, f"Page {d.page}"); c.restoreState()
    pdf.build(el, onFirstPage=footer, onLaterPages=footer)
    return buf.getvalue()
