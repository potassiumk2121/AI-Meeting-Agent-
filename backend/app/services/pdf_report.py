import os
from dataclasses import dataclass, field
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib.colors import HexColor, white
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    PageTemplate,
    Paragraph,
    Table,
    TableStyle,
)
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

from app.config import get_settings

_FONTS: dict[str, str] = {}


def _font_pair() -> tuple[str, str]:
    if _FONTS:
        return _FONTS["regular"], _FONTS["bold"]
    candidates = [
        (
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        ),
        (r"C:\Windows\Fonts\arial.ttf", r"C:\Windows\Fonts\arialbd.ttf"),
        (r"C:\Windows\Fonts\segoeui.ttf", r"C:\Windows\Fonts\segoeuib.ttf"),
    ]
    regular_name, bold_name = "Helvetica", "Helvetica-Bold"
    for regular, bold in candidates:
        if os.path.exists(regular):
            pdfmetrics.registerFont(TTFont("AppSans", regular))
            bold_path = bold if os.path.exists(bold) else regular
            pdfmetrics.registerFont(TTFont("AppSans-Bold", bold_path))
            regular_name, bold_name = "AppSans", "AppSans-Bold"
            break
    _FONTS["regular"] = regular_name
    _FONTS["bold"] = bold_name
    return regular_name, bold_name


def _brand():
    try:
        return HexColor(get_settings().brand_color)
    except Exception:
        return HexColor("#102033")


def _xml(text: str, font: str) -> str:
    value = text or ""
    if font == "Helvetica":
        value = value.encode("latin-1", "replace").decode("latin-1")
    return escape(value).replace("\n", "<br/>")


@dataclass
class ReportData:
    title: str
    when_label: str
    platform: str
    participants: list[str]
    sentiment: str
    executive_summary: str
    detailed_summary: str
    manager_summary: str
    decisions: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    next_steps: list[str] = field(default_factory=list)
    action_items: list[tuple[str, str, str]] = field(default_factory=list)
    segments: list[tuple[str, str, str, str]] = field(default_factory=list)
    chat: list[tuple[str, str, str]] = field(default_factory=list)


_LOGO = Path(__file__).resolve().parent.parent / "assets" / "development-monitors.jpg"
_COPPER = HexColor("#C46A3A")
_INK = HexColor("#243038")
_RULE = HexColor("#D9D4CC")


def build_pdf(data: ReportData, path: Path) -> None:
    regular, bold = _font_pair()
    brand = _brand()
    settings = get_settings()
    path.parent.mkdir(parents=True, exist_ok=True)

    def paint(canvas, doc):
        canvas.saveState()
        width, height = A4
        canvas.setFillColor(white)
        canvas.rect(0, 0, width, height, fill=1, stroke=0)
        if _LOGO.exists():
            canvas.drawImage(
                str(_LOGO),
                36,
                height - 78,
                width=228,
                height=66,
                preserveAspectRatio=True,
                anchor="sw",
                mask="auto",
            )
        canvas.setFillColor(_INK)
        canvas.setFont(bold, 8)
        canvas.drawRightString(width - 40, height - 38, "AI MEETING INTELLIGENCE")
        canvas.setFillColor(HexColor("#8A8178"))
        canvas.setFont(regular, 7)
        canvas.drawRightString(width - 40, height - 50, "PLAN. DEVELOP. MONITOR.")
        canvas.setStrokeColor(_COPPER)
        canvas.setLineWidth(2)
        canvas.line(36, height - 86, width - 36, height - 86)
        canvas.setStrokeColor(_INK)
        canvas.setLineWidth(0.4)
        canvas.line(36, 40, width - 36, 40)
        canvas.setFillColor(_INK)
        canvas.setFont(regular, 8)
        canvas.drawString(36, 24, f"{settings.company_name} LLC")
        canvas.setFillColor(HexColor("#8A8178"))
        canvas.drawCentredString(width / 2, 24, "Confidential")
        canvas.setFillColor(_INK)
        canvas.drawRightString(width - 36, 24, f"Page {doc.page}")
        canvas.restoreState()

    document = BaseDocTemplate(
        str(path),
        pagesize=A4,
        title=f"{settings.company_name} — {data.title}",
        author=settings.company_name,
    )
    frame = Frame(40, 56, A4[0] - 80, A4[1] - 156, showBoundary=0)
    document.addPageTemplates([PageTemplate(id="main", frames=[frame], onPage=paint)])

    body = ParagraphStyle(
        "Body",
        fontName=regular,
        fontSize=10,
        leading=14,
        textColor=HexColor("#1F2937"),
        alignment=TA_LEFT,
        spaceAfter=6,
    )
    small = ParagraphStyle(
        "Small",
        parent=body,
        fontSize=9,
        leading=12,
        textColor=HexColor("#334155"),
    )
    title = ParagraphStyle(
        "Title",
        fontName=bold,
        fontSize=18,
        leading=22,
        textColor=HexColor("#0F172A"),
        spaceAfter=4,
    )
    section = ParagraphStyle(
        "Section",
        fontName=bold,
        fontSize=11,
        leading=14,
        textColor=_INK,
        spaceBefore=14,
        spaceAfter=6,
    )
    kicker = ParagraphStyle(
        "Kicker",
        fontName=bold,
        fontSize=8,
        leading=10,
        textColor=_COPPER,
        spaceAfter=4,
    )
    story = [
        Paragraph("MEETING REPORT", kicker),
        Paragraph(_xml(data.title, bold), title),
        _facts_table(data, regular, bold),
        Paragraph("01  Executive summary", section),
        Paragraph(_xml(data.executive_summary, regular), body),
        Paragraph("02  Manager summary", section),
    ]
    for line in (data.manager_summary or "None recorded").splitlines():
        story.append(Paragraph(_xml(line or " ", regular), small))

    story.append(Paragraph("03  Decisions", section))
    story.extend(_bullets(data.decisions, small, regular))
    story.append(Paragraph("04  Risks", section))
    story.extend(_bullets(data.risks, small, regular))
    story.append(Paragraph("05  Next steps", section))
    story.extend(_bullets(data.next_steps, small, regular))
    story.append(Paragraph("06  Action items", section))
    story.append(_action_table(data.action_items, regular, bold, brand))
    story.append(Paragraph("07  Transcript", section))
    story.append(_transcript_table(data.segments, regular, bold, brand))
    if data.chat:
        story.append(Paragraph("08  Chat", section))
        story.append(_chat_table(data.chat, regular, bold, brand))
    if data.detailed_summary and data.detailed_summary != data.executive_summary:
        story.append(Paragraph("09  Detailed notes", section))
        for line in data.detailed_summary.splitlines():
            story.append(Paragraph(_xml(line or " ", regular), small))

    document.build(story)


def _facts_table(data: ReportData, regular: str, bold: str):
    label = ParagraphStyle("FactLabel", fontName=bold, fontSize=8, leading=11, textColor=HexColor("#8A8178"))
    value = ParagraphStyle("FactValue", fontName=regular, fontSize=9, leading=12, textColor=_INK)
    people = ", ".join(data.participants) if data.participants else "Not recorded"
    pairs = [
        ("When", data.when_label or "Not recorded"),
        ("Platform", data.platform or "Not recorded"),
        ("Sentiment", (data.sentiment or "neutral").capitalize()),
        ("Participants", people),
    ]
    rows = [
        [Paragraph(name.upper(), label), Paragraph(_xml(text, regular), value)]
        for name, text in pairs
    ]
    table = Table(rows, colWidths=[90, 420])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), HexColor("#F7F5F2")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("LINEBELOW", (0, 0), (-1, -2), 0.3, _RULE),
                ("BOX", (0, 0), (-1, -1), 0.4, _RULE),
            ]
        )
    )
    return table


def _bullets(items: list[str], style: ParagraphStyle, font: str) -> list:
    if not items:
        return [Paragraph("None recorded.", style)]
    return [Paragraph(_xml(f"• {item}", font), style) for item in items]


def _table(header: list[str], rows: list[list], regular: str, bold: str, brand, widths: list[int]):
    header_cells = [
        Paragraph(escape(cell), ParagraphStyle("H", fontName=bold, fontSize=8, textColor=white, leading=10))
        for cell in header
    ]
    body_rows = []
    cell_style = ParagraphStyle("C", fontName=regular, fontSize=8, leading=11, textColor=HexColor("#1F2937"))
    for row in rows:
        body_rows.append([Paragraph(_xml(str(value), regular), cell_style) for value in row])
    table = Table([header_cells, *body_rows] if body_rows else [header_cells, ["—"] * len(header)], colWidths=widths, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), _INK),
                ("TEXTCOLOR", (0, 0), (-1, 0), white),
                ("FONTNAME", (0, 0), (-1, 0), bold),
                ("BACKGROUND", (0, 1), (-1, -1), HexColor("#F8FAFC")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [white, HexColor("#F8FAFC")]),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("GRID", (0, 0), (-1, -1), 0.25, HexColor("#E2E8F0")),
            ]
        )
    )
    return table


def _action_table(items: list[tuple[str, str, str]], regular: str, bold: str, brand):
    rows = [list(item) for item in items] or [["—", "None recorded", "—"]]
    return _table(["Assignee", "Task", "Status"], rows, regular, bold, brand, [110, 310, 70])


def _transcript_table(items: list[tuple[str, str, str, str]], regular: str, bold: str, brand):
    rows = []
    for stamp, speaker, original, english in items:
        spoken = english if original.strip() == english.strip() else f"{english}\nOriginal: {original}"
        rows.append([stamp, speaker, spoken])
    if not rows:
        rows = [["—", "—", "No transcript"]]
    return _table(["Time", "Speaker", "English"], rows, regular, bold, brand, [70, 90, 330])


def _chat_table(items: list[tuple[str, str, str]], regular: str, bold: str, brand):
    rows = [[stamp, sender, text] for stamp, sender, text in items]
    return _table(["Time", "Sender", "Message"], rows, regular, bold, brand, [70, 90, 330])
