"""Guest-facing PDF receipts for completed Mirror Talk intake applications."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from io import BytesIO
from typing import Any, Mapping
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import HRFlowable, KeepTogether, Paragraph, SimpleDocTemplate, Spacer


_QUESTIONS = (
    ("About you", "full_name", "Full name"),
    ("About you", "email", "Email address"),
    ("About you", "website", "Primary website or public profile (optional)"),
    ("About you", "social_handles", "Additional public links (optional)"),
    ("About you", "background", "Introduce yourself in a few sentences"),
    ("About you", "profession", "What work do you do, and what perspective have you earned through it?"),
    ("Your story", "life_experiences", "What turning point or lived experience most shaped who you are today?"),
    ("Your story", "motivation", "Why does sharing this story matter to you now?"),
    ("Your story", "core_values", "What values or principles guided you through that experience?"),
    ("Your story", "faith_choice", "Does a faith, spiritual practice, or philosophy meaningfully shape this story? (optional)"),
    ("Your story", "faith_detail", "Relevant faith, spiritual, or philosophical context"),
    ("The episode", "passionate_topics", "What topics could you discuss with unusual depth or first-hand authority?"),
    ("The episode", "message", "What should a listener understand, feel, or do differently after hearing your story?"),
    ("The episode", "alignment_detail", "Why would this story belong on Mirror Talk specifically?"),
    ("The episode", "experience_choice", "Have you been interviewed or spoken publicly before? (optional)"),
    ("The episode", "experience_detail", "Previous interview or speaking context"),
    ("The episode", "additional_info", "Conversation boundaries or anything else we should know (optional)"),
    ("The episode", "favorite_quote_detail", "A favourite quote or philosophy (optional)"),
)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _answers_for(guest: Mapping[str, Any]) -> dict[str, str]:
    """Return submitted answers, preferring the unaltered form payload."""
    original = guest.get("original_data")
    if isinstance(original, str):
        try:
            original = json.loads(original)
        except (TypeError, ValueError):
            original = {}
    raw = original if isinstance(original, Mapping) else {}
    answers = {key: _text(raw.get(key) or guest.get(key)) for _, key, _ in _QUESTIONS}

    # Older stored applications use these field names; preserve their answers too.
    answers["faith_choice"] = answers["faith_choice"] or _text(guest.get("faith"))
    answers["alignment_detail"] = answers["alignment_detail"] or _text(guest.get("alignment"))
    answers["favorite_quote_detail"] = answers["favorite_quote_detail"] or _text(guest.get("favorite_quote"))
    answers["experience_detail"] = answers["experience_detail"] or _text(guest.get("experience"))
    return answers


def build_intake_receipt_pdf(guest: Mapping[str, Any]) -> bytes:
    """Build a polished, static PDF copy of an applicant's submitted answers."""
    answers = _answers_for(guest)
    submitted_at = datetime.now(timezone.utc).strftime("%d %B %Y")
    output = BytesIO()
    document = SimpleDocTemplate(
        output,
        pagesize=A4,
        leftMargin=22 * mm,
        rightMargin=22 * mm,
        topMargin=19 * mm,
        bottomMargin=18 * mm,
        title="Mirror Talk application receipt",
        author="Mirror Talk Podcast",
    )
    styles = getSampleStyleSheet()
    title = ParagraphStyle("ReceiptTitle", parent=styles["Title"], fontName="Helvetica-Bold", fontSize=24, leading=28, textColor=colors.HexColor("#1E3D3A"), alignment=TA_LEFT, spaceAfter=5)
    eyebrow = ParagraphStyle("ReceiptEyebrow", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=8, leading=11, textColor=colors.HexColor("#B66B47"), spaceAfter=8)
    subtitle = ParagraphStyle("ReceiptSubtitle", parent=styles["Normal"], fontSize=10, leading=15, textColor=colors.HexColor("#4A5B59"), spaceAfter=16)
    section = ParagraphStyle("ReceiptSection", parent=styles["Heading2"], fontName="Helvetica-Bold", fontSize=13, leading=17, textColor=colors.HexColor("#1E3D3A"), spaceBefore=12, spaceAfter=7)
    question = ParagraphStyle("ReceiptQuestion", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=9, leading=13, textColor=colors.HexColor("#35514D"), spaceAfter=3)
    answer = ParagraphStyle("ReceiptAnswer", parent=styles["Normal"], fontSize=10, leading=15, textColor=colors.HexColor("#1E2423"), spaceAfter=10)
    footer = ParagraphStyle("ReceiptFooter", parent=styles["Normal"], fontSize=8, leading=11, textColor=colors.HexColor("#647673"), spaceBefore=12)

    story = [
        Paragraph("MIRROR TALK PODCAST", eyebrow),
        Paragraph("Your application", title),
        Paragraph(f"A copy of the answers you shared with us on {submitted_at}.", subtitle),
        HRFlowable(width="100%", thickness=1, color=colors.HexColor("#D8E2DF"), spaceAfter=4),
    ]
    active_section = ""
    for section_name, key, prompt in _QUESTIONS:
        value = answers[key]
        if not value:
            continue
        if section_name != active_section:
            story.append(Paragraph(section_name, section))
            active_section = section_name
        safe_prompt = escape(prompt)
        safe_answer = escape(value).replace("\n", "<br/>")
        story.append(KeepTogether([Paragraph(safe_prompt, question), Paragraph(safe_answer, answer)]))

    story.extend(
        [
            HRFlowable(width="100%", thickness=1, color=colors.HexColor("#D8E2DF"), spaceBefore=6),
            Spacer(1, 5),
            Paragraph("Thank you for sharing your story with Mirror Talk. We will review your application with care.", footer),
        ]
    )
    document.build(story)
    return output.getvalue()
