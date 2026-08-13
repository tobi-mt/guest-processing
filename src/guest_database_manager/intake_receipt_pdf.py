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
    ("About you", "website", "Website"),
    ("About you", "social_handles", "Social and public profiles"),
    ("Your journey", "background", "A brief overview of your personal and professional background"),
    ("Your journey", "profession", "What is your current profession, and what led you to this career path?"),
    ("Your journey", "motivation", "What motivates or inspires you in your work and life?"),
    ("Your journey", "life_experiences", "What life experiences or pivotal moments have shaped who you are today?"),
    ("Your perspective", "core_values", "What are your core values or guiding principles?"),
    ("Your perspective", "faith_choice", "Do you follow a specific faith, spiritual practice, or philosophical tradition?"),
    ("Your perspective", "faith_detail", "Tell us a little more about that practice or tradition"),
    ("Your perspective", "alignment_choice", "Do you believe your beliefs and values align with the themes of soulful conversations?"),
    ("Your perspective", "alignment_detail", "If yes, how do you think your perspective could contribute meaningfully?"),
    ("Your perspective", "favorite_quote_choice", "Do you have a favourite quote or philosophy that guides your life?"),
    ("Your perspective", "favorite_quote_detail", "Share the quote or philosophy and why it resonates with you"),
    ("The conversation", "passionate_topics", "What topics or themes are you most passionate about discussing?"),
    ("The conversation", "message", "What message or takeaway would you like to leave with our listeners?"),
    ("The conversation", "experience_choice", "Have you been a guest on podcasts or spoken at events before?"),
    ("The conversation", "experience_detail", "If yes, please share links or a little context"),
    ("The conversation", "additional_info", "Is there anything else you'd like us to know about you?"),
    ("The conversation", "has_social_media", "Are you following us on podcast platforms and social media?"),
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
    answers["alignment_choice"] = answers["alignment_choice"] or _text(guest.get("alignment"))
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
