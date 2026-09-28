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
    Spacer,
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


def build_pdf(data: ReportData, path: Path) -> None:
    regular, bold = _font_pair()
    brand = _brand()
    settings = get_settings()
    path.parent.mkdir(parents=True, exist_ok=True)

    def paint(canvas, doc):
        canvas.saveState()
        width, height = A4
        canvas.setFillColor(brand)
        canvas.rect(0, height - 42, width, 42, fill=1, stroke=0)
        canvas.setFillColor(white)
        canvas.setFont(bold, 11)
        canvas.drawString(48, height - 26, settings.company_name)
        canvas.setFont(regular, 9)
        canvas.drawRightString(width - 48, height - 26, settings.company_tagline)
        canvas.setFillColor(HexColor("#64748B"))
        canvas.setFont(regular, 8)
        canvas.drawString(48, 26, "Confidential")
        canvas.drawRightString(width - 48, 26, f"Page {doc.page}")
        canvas.restoreState()

    document = BaseDocTemplate(
        str(path),
        pagesize=A4,
        title=f"{settings.company_name} — {data.title}",
        author=settings.company_name,
    )
    frame = Frame(48, 46, A4[0] - 96, A4[1] - 100, showBoundary=0)
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
        fontSize=12,
        leading=16,
        textColor=brand,
        spaceBefore=12,
        spaceAfter=4,
    )
    meta = ParagraphStyle(
        "Meta",
        fontName=regular,
        fontSize=9,
        leading=12,
        textColor=HexColor("#475569"),
        spaceAfter=8,
    )

    story = [
        Paragraph(_xml(data.title, bold), title),
        Paragraph(
            _xml(
                f"{data.when_label}  ·  {data.platform}  ·  Sentiment: {data.sentiment or 'neutral'}",
                regular,
            ),
            meta,
        ),
        Paragraph(
            _xml("Participants: " + (", ".join(data.participants) if data.participants else "Not recorded"), regular),
            meta,
        ),
        Paragraph("Executive summary", section),
        Paragraph(_xml(data.executive_summary, regular), body),
        Paragraph("Manager summary", section),
    ]
    for line in (data.manager_summary or "None recorded").splitlines():
        story.append(Paragraph(_xml(line or " ", regular), small))

    story.append(Paragraph("Decisions", section))
    story.extend(_bullets(data.decisions, small, regular))
    story.append(Paragraph("Risks", section))
    story.extend(_bullets(data.risks, small, regular))
    story.append(Paragraph("Next steps", section))
    story.extend(_bullets(data.next_steps, small, regular))
    story.append(Paragraph("Action items", section))
    story.append(_action_table(data.action_items, regular, bold, brand))
    story.append(Paragraph("Transcript", section))
    story.append(_transcript_table(data.segments, regular, bold, brand))
    if data.chat:
        story.append(Paragraph("Chat", section))
        story.append(_chat_table(data.chat, regular, bold, brand))
    if data.detailed_summary and data.detailed_summary != data.executive_summary:
        story.append(Paragraph("Detailed notes", section))
        for line in data.detailed_summary.splitlines():
            story.append(Paragraph(_xml(line or " ", regular), small))

    document.build(story)


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
                ("BACKGROUND", (0, 0), (-1, 0), brand),
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
