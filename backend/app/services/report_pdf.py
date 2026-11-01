"""ReportLab PDF generation for scan reports and complaint drafts."""

from __future__ import annotations

import io
import re
from datetime import datetime, timezone
from typing import Any
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

INK = colors.HexColor("#0f172a")
MUTED = colors.HexColor("#475569")
ACCENT = colors.HexColor("#0e7490")
DANGER = colors.HexColor("#b91c1c")
WARNING = colors.HexColor("#b45309")
SAFE = colors.HexColor("#15803d")
UNKNOWN = colors.HexColor("#4b5563")

_CLASS_COLORS = {
    "malicious": DANGER,
    "suspicious": WARNING,
    "no_significant_indicators": SAFE,
    "unknown": UNKNOWN,
}


def _ts() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).strftime("%Y-%m-%d %H:%M UTC")


def _safe(value: Any, limit: int = 4000) -> str:
    text = "" if value is None else str(value)
    text = text.replace("\r", " ").replace("\n", "<br/>")
    # Helvetica + WinAnsi supports Latin-1 only. Replace the rest rather than
    # allowing ReportLab to fail on emoji or unsupported scripts.
    text = "".join(char if ord(char) <= 0xFF else "?" for char in text)
    text = text[:limit]
    return escape(text).replace("&lt;br/&gt;", "<br/>")


def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "TLTitle", parent=base["Title"], fontName="Helvetica-Bold", fontSize=20,
            leading=24, textColor=INK, alignment=TA_LEFT, spaceAfter=2,
        ),
        "h2": ParagraphStyle(
            "TLH2", parent=base["Heading2"], fontName="Helvetica-Bold", fontSize=12,
            leading=15, textColor=INK, spaceBefore=12, spaceAfter=5,
        ),
        "body": ParagraphStyle(
            "TLBody", parent=base["BodyText"], fontName="Helvetica", fontSize=9,
            leading=13, textColor=INK,
        ),
        "small": ParagraphStyle(
            "TLSmall", parent=base["BodyText"], fontName="Helvetica", fontSize=8,
            leading=11, textColor=MUTED,
        ),
        "cell": ParagraphStyle(
            "TLCell", parent=base["BodyText"], fontName="Helvetica", fontSize=8,
            leading=10.5, textColor=INK,
        ),
        "cellbold": ParagraphStyle(
            "TLCellBold", parent=base["BodyText"], fontName="Helvetica-Bold", fontSize=8,
            leading=10.5, textColor=INK,
        ),
        "banner": ParagraphStyle(
            "TLBanner", parent=base["Heading1"], fontName="Helvetica-Bold", fontSize=13,
            leading=17, textColor=colors.white, alignment=TA_LEFT,
        ),
    }


def _footer(canvas, doc) -> None:
    canvas.saveState()
    width, _height = A4
    canvas.setStrokeColor(colors.HexColor("#e2e8f0"))
    canvas.setLineWidth(0.5)
    canvas.line(19 * mm, 15 * mm, width - 19 * mm, 15 * mm)
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(MUTED)
    canvas.drawString(19 * mm, 10 * mm, "ThreatLens — local analysis report. Not a legal or security certification.")
    canvas.drawRightString(width - 19 * mm, 10 * mm, f"Page {doc.page}")
    canvas.restoreState()


def _build_doc(buffer: io.BytesIO) -> BaseDocTemplate:
    doc = BaseDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=19 * mm,
        rightMargin=19 * mm,
        topMargin=18 * mm,
        bottomMargin=22 * mm,
        title="ThreatLens report",
        author="ThreatLens",
    )
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="main")
    doc.addPageTemplates([PageTemplate(id="page", frames=[frame], onPage=_footer)])
    return doc


def _kv_table(rows: list[tuple[str, str]], styles: dict[str, ParagraphStyle]) -> Table:
    data = [
        [Paragraph(_safe(key), styles["cellbold"]), Paragraph(_safe(value), styles["cell"])]
        for key, value in rows
    ]
    table = Table(data, colWidths=[38 * mm, 128 * mm], hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("LINEBELOW", (0, 0), (-1, -1), 0.3, colors.HexColor("#e2e8f0")),
            ]
        )
    )
    return table


def _bullets(items: list[str], styles: dict[str, ParagraphStyle]) -> list[Paragraph]:
    return [Paragraph(f"• {_safe(item, 800)}", styles["body"]) for item in items if item]


def _classification_banner(
    label: str, score: int, classification: str, styles: dict[str, ParagraphStyle]
) -> Table:
    color = _CLASS_COLORS.get(classification, UNKNOWN)
    data = [
        [
            Paragraph(_safe(label), styles["banner"]),
            Paragraph(
                f'<font color="white"><b>Risk score: {score}/100</b> (heuristic)</font>',
                styles["cell"],
            ),
        ]
    ]
    table = Table(data, colWidths=[120 * mm, 46 * mm], hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), color),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )
    return table


def build_scan_report_pdf(scan: Any) -> bytes:
    styles = _styles()
    analysis = scan.analysis or {}
    assessment = analysis.get("assessment") or {}
    findings = assessment.get("supporting_findings") or []
    limitations = assessment.get("limitations") or []
    actions = assessment.get("recommended_actions") or []
    classification = assessment.get("classification", scan.classification)
    score = assessment.get("risk_score", scan.risk_score)
    label = assessment.get("classification_label", scan.classification)

    story: list[Any] = [
        Paragraph("ThreatLens", styles["title"]),
        Paragraph("See the Threat. Understand the Risk. Take Action.", styles["small"]),
        Spacer(1, 8),
        Paragraph("Scan report", styles["h2"]),
        _classification_banner(label, int(score or 0), classification, styles),
        Spacer(1, 6),
        Paragraph(_safe(assessment.get("summary", scan.summary)), styles["body"]),
        Spacer(1, 6),
        _kv_table(
            [
                ("Scan ID", scan.id),
                ("Input type", scan.input_type),
                ("Submitted", scan.input_label),
                ("Created", scan.created_at.isoformat(sep=" ") if scan.created_at else ""),
                ("Score type", assessment.get("score_kind", "heuristic_uncalibrated")),
                (
                    "Evidence coverage",
                    f"{assessment.get('evidence_quality', {}).get('completed', 0)} of "
                    f"{assessment.get('evidence_quality', {}).get('attempted', 0)} stage(s) completed",
                ),
            ],
            styles,
        ),
        Paragraph("Supporting indicators", styles["h2"]),
    ]

    if findings:
        rows = [[
            Paragraph("Severity", styles["cellbold"]),
            Paragraph("Indicator", styles["cellbold"]),
            Paragraph("Source", styles["cellbold"]),
        ]]
        for item in findings[:40]:
            rows.append(
                [
                    Paragraph(_safe(item.get("severity", ""), 20), styles["cell"]),
                    Paragraph(
                        f"<b>{_safe(item.get('title', ''), 160)}</b><br/>{_safe(item.get('description', ''), 500)}",
                        styles["cell"],
                    ),
                    Paragraph(_safe(item.get("source_label") or item.get("source", ""), 60), styles["cell"]),
                ]
            )
        table = Table(rows, colWidths=[20 * mm, 116 * mm, 30 * mm], repeatRows=1, hAlign="LEFT")
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f5f9")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#e2e8f0")),
                    ("LEFTPADDING", (0, 0), (-1, -1), 4),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )
        story.append(table)
        if len(findings) > 40:
            story.append(Paragraph(f"{len(findings) - 40} additional indicator(s) are available in the app.", styles["small"]))
    else:
        story.append(Paragraph("No indicators were recorded.", styles["body"]))

    story.append(Paragraph("Technical details", styles["h2"]))
    technical: list[tuple[str, str]] = []
    if scan.input_type == "url":
        http = analysis.get("http") or {}
        html = analysis.get("html") or {}
        browser = analysis.get("browser") or {}
        technical = [
            ("Hostname", analysis.get("hostname", "")),
            ("Normalised URL", analysis.get("normalized_url", "")),
            ("HTTP status", str(http.get("status_code", "not available"))),
            ("Final URL", http.get("final_url", "not collected")),
            ("Content type", http.get("content_type", "not collected")),
            ("Redirects", str(max(0, len(http.get("redirect_chain") or []) - 1)) if http.get("available") else "not available"),
            ("Page title", html.get("title", "not collected")),
            ("Forms / password fields", f"{html.get('form_count', 0)} / {html.get('password_field_count', 0)}"),
            ("External links", str(html.get("external_link_count", 0))),
            ("Browser analysis", "completed" if browser.get("available") else f"unavailable — {browser.get('reason', '')}"),
        ]
    elif scan.input_type == "email":
        input_data = analysis.get("input") or {}
        technical = [
            ("Subject", input_data.get("subject", "not supplied")),
            ("Sender", input_data.get("sender", "not supplied")),
            ("Extracted links", str(len(analysis.get("extracted_urls") or []))),
            ("ML classifier", (analysis.get("ml") or {}).get("reason") or "available"),
        ]
    else:
        file_info = analysis.get("file") or {}
        technical = [
            ("Filename", file_info.get("filename", "not available")),
            ("Actual format", file_info.get("actual_format", "not available")),
            ("Dimensions", f"{file_info.get('width', '?')} × {file_info.get('height', '?')} px"),
            ("SHA-256", file_info.get("sha256", "")),
            ("QR values", str(len(analysis.get("qr_values") or []))),
            ("OCR characters", str(len(analysis.get("ocr_text") or ""))),
            ("Extracted links", str(len(analysis.get("extracted_urls") or []))),
        ]
    story.append(_kv_table(technical, styles))

    url_results = analysis.get("url_results") or []
    if url_results:
        story.append(Paragraph("Extracted link assessments", styles["h2"]))
        rows = [[
            Paragraph("URL", styles["cellbold"]),
            Paragraph("Result", styles["cellbold"]),
            Paragraph("Score", styles["cellbold"]),
        ]]
        for item in url_results:
            rows.append(
                [
                    Paragraph(_safe(item.get("url", ""), 300), styles["cell"]),
                    Paragraph(_safe(item.get("classification_label", item.get("error", {}).get("message", "")), 80), styles["cell"]),
                    Paragraph(str(item.get("risk_score", "—")), styles["cell"]),
                ]
            )
        table = Table(rows, colWidths=[110 * mm, 36 * mm, 20 * mm], repeatRows=1, hAlign="LEFT")
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f5f9")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#e2e8f0")),
                    ("LEFTPADDING", (0, 0), (-1, -1), 4),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )
        story.append(table)

    story.append(Paragraph("Limitations", styles["h2"]))
    story.extend(_bullets(limitations, styles))
    story.append(Paragraph("Recommended actions", styles["h2"]))
    story.extend(_bullets(actions, styles))
    story.append(Spacer(1, 10))
    story.append(
        Paragraph(
            "This report is generated from automated analysis. It is evidence-based but not proof of "
            "maliciousness, and the absence of indicators is not a guarantee of safety. Generated "
            f"{_ts()}.",
            styles["small"],
        )
    )

    buffer = io.BytesIO()
    doc = _build_doc(buffer)
    doc.build(story)
    return buffer.getvalue()


def build_complaint_pdf(complaint: Any, user: Any) -> bytes:
    styles = _styles()
    story: list[Any] = [
        Paragraph("ThreatLens", styles["title"]),
        Paragraph("Cybercrime complaint preparation — DRAFT", styles["h2"]),
        Spacer(1, 4),
    ]
    banner = Table(
        [[Paragraph("DRAFT FOR YOUR REVIEW — NOT SUBMITTED TO ANY AUTHORITY", styles["banner"])]],
        colWidths=[166 * mm],
    )
    banner.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), WARNING),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )
    story.extend(
        [
            banner,
            Spacer(1, 8),
            Paragraph(
                "This document was prepared locally by ThreatLens from information you supplied. "
                "Review every field for accuracy. ThreatLens did not submit this complaint and does "
                "not provide legal advice.",
                styles["body"],
            ),
            Paragraph("Complainant", styles["h2"]),
            _kv_table(
                [
                    ("Name", getattr(user, "display_name", "")),
                    ("Email", getattr(user, "email", "")),
                    ("Draft ID", complaint.id),
                    ("Generated", _ts()),
                ],
                styles,
            ),
            Paragraph("Incident details", styles["h2"]),
            _kv_table(
                [
                    ("Incident date", complaint.incident_date or "not supplied"),
                    ("Category", complaint.incident_category),
                    ("Suspected URL", complaint.suspect_url or "not supplied"),
                    ("Financial loss", complaint.financial_loss or "not supplied"),
                ],
                styles,
            ),
            Paragraph("Description", styles["h2"]),
            Paragraph(_safe(complaint.description, 6000), styles["body"]),
            Paragraph("Evidence and supporting information", styles["h2"]),
            Paragraph(_safe(complaint.evidence or "No evidence details were supplied.", 6000), styles["body"]),
            Paragraph("Suggested next steps", styles["h2"]),
        ]
    )
    story.extend(
        _bullets(
            [
                "Verify all details and attach your own evidence (screenshots, transaction records, messages).",
                "In India, submit or verify reporting options at the National Cyber Crime Reporting Portal: https://cybercrime.gov.in/",
                "For financial fraud, contact your bank immediately and follow their dispute process.",
                "Do not send passwords, one-time codes or full card numbers in a complaint.",
            ],
            styles,
        )
    )
    story.append(Spacer(1, 10))
    story.append(
        Paragraph(
            "ThreatLens generated this draft locally. It has not been submitted, filed, acknowledged "
            "or verified by any authority.",
            styles["small"],
        )
    )
    buffer = io.BytesIO()
    doc = _build_doc(buffer)
    doc.build(story)
    return buffer.getvalue()
