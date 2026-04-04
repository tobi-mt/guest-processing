"""Lightweight web interface with a static frontend and JSON API."""

from __future__ import annotations

import json
import mimetypes
import os
import re
import tempfile
import webbrowser
from csv import DictWriter
from base64 import b64decode
from email.parser import BytesParser
from email.policy import default
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO, StringIO
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import urlsplit

from openpyxl import Workbook

from guest_database_manager.ask_mirror_talk_client import AskMirrorTalkClient, AskMirrorTalkClientError
from guest_database_manager.constants import DEFAULT_DB_PATH
from guest_database_manager.database import GuestDatabase
from guest_database_manager.email_manager import EmailManager
from guest_database_manager.episode_planner import (
    build_episode_copy_assist,
    build_promotion_readiness,
    build_release_recommendations,
    parse_episode_import_csv,
)
from guest_database_manager.guest_recommender import (
    build_guest_recommendation_stats,
    enrich_guests_with_recommendations,
)
from guest_database_manager.guest_research import research_guest_from_google_search, research_guest_from_public_web
from guest_database_manager.google_calendar_sync import GoogleCalendarSyncClient, GoogleCalendarSyncError
from guest_database_manager.openai_scheduling_copilot import OpenAISchedulingCopilot, build_month_context

STATIC_DIR = Path(__file__).parent / "static"
FORM_SOURCE_NAME = "Direct Web Entry"
INTAKE_SOURCE_NAME = "Website Intake Questionnaire"
ALLOWED_ORIGINS = {
    "https://www.mirrortalkpodcast.com",
    "https://mirrortalkpodcast.com",
    "http://localhost:8501",
    "http://127.0.0.1:8501",
}
API_TOKEN_ENV_VAR = "MIRROR_TALK_INTAKE_API_TOKEN"
DASHBOARD_USERNAME_ENV_VAR = "MIRROR_TALK_DASHBOARD_USERNAME"
DASHBOARD_PASSWORD_ENV_VAR = "MIRROR_TALK_DASHBOARD_PASSWORD"
EMAIL_SMTP_SERVER_ENV_VAR = "MIRROR_TALK_SMTP_SERVER"
EMAIL_SMTP_PORT_ENV_VAR = "MIRROR_TALK_SMTP_PORT"
EMAIL_USERNAME_ENV_VAR = "MIRROR_TALK_SMTP_USERNAME"
EMAIL_PASSWORD_ENV_VAR = "MIRROR_TALK_SMTP_PASSWORD"
EMAIL_RESEND_API_KEY_ENV_VAR = "MIRROR_TALK_RESEND_API_KEY"
EMAIL_FROM_ENV_VAR = "MIRROR_TALK_FROM_EMAIL"
EMAIL_FROM_NAME_ENV_VAR = "MIRROR_TALK_FROM_NAME"
EMAIL_CC_ENV_VAR = "MIRROR_TALK_CC_EMAIL"
GOOGLE_CLIENT_ID_ENV_VAR = "MIRROR_TALK_GOOGLE_CLIENT_ID"
GOOGLE_CLIENT_SECRET_ENV_VAR = "MIRROR_TALK_GOOGLE_CLIENT_SECRET"
GOOGLE_REFRESH_TOKEN_ENV_VAR = "MIRROR_TALK_GOOGLE_REFRESH_TOKEN"
GOOGLE_CALENDAR_ID_ENV_VAR = "MIRROR_TALK_GOOGLE_CALENDAR_ID"
GOOGLE_CALENDAR_QUERY_ENV_VAR = "MIRROR_TALK_GOOGLE_CALENDAR_QUERY"
GOOGLE_CALENDAR_TIMEZONE_ENV_VAR = "MIRROR_TALK_GOOGLE_CALENDAR_TIMEZONE"
GOOGLE_CALENDAR_DAYS_AHEAD_ENV_VAR = "MIRROR_TALK_GOOGLE_CALENDAR_DAYS_AHEAD"
ASK_MIRROR_TALK_BASE_URL_ENV_VAR = "MIRROR_TALK_ASK_BASE_URL"
ASK_MIRROR_TALK_USERNAME_ENV_VAR = "MIRROR_TALK_ASK_USERNAME"
ASK_MIRROR_TALK_PASSWORD_ENV_VAR = "MIRROR_TALK_ASK_PASSWORD"
OPENAI_API_KEY_ENV_VAR = "MIRROR_TALK_OPENAI_API_KEY"
OPENAI_MODEL_ENV_VAR = "MIRROR_TALK_OPENAI_MODEL"
OPENAI_TIMEOUT_ENV_VAR = "MIRROR_TALK_OPENAI_TIMEOUT_SECONDS"
DEFAULT_GOOGLE_CALENDAR_SYNC_DAYS_AHEAD = 365
AI_AUTORESEARCH_CANDIDATE_LIMIT = 12
BULK_GUEST_RESEARCH_BATCH_SIZE = 25
FORM_FIELDS = {
    "full_name",
    "email",
    "website",
    "profession",
    "background",
    "motivation",
    "life_experiences",
    "core_values",
    "favorite_quote",
    "faith",
    "alignment",
    "passionate_topics",
    "message",
    "experience",
    "additional_info",
    "social_handles",
    "has_social_media",
}
LONG_TEXT_FIELDS = [
    "background",
    "profession",
    "passionate_topics",
    "message",
    "experience",
    "additional_info",
]
MIN_WORDS_BY_FIELD = {
    "background": 8,
    "profession": 1,
    "passionate_topics": 1,
    "message": 1,
    "experience": 4,
    "additional_info": 4,
}
SPAM_KEYWORDS = {
    "seo",
    "casino",
    "crypto",
    "backlink",
    "guest post service",
    "viagra",
    "betting",
    "loan",
}
HOST_NAME_HINTS = (
    "tobi ojekunle",
    "mirror talk",
    "podcast.mirrortalk",
)
OUTREACH_STEP_DEFINITIONS = [
    {
        "key": "monday_preparation",
        "day": "Monday",
        "time_label": "Anytime",
        "title": "Preparation and positioning",
        "description": "Finalize titles, thumbnails, clips, blog, and email.",
    },
    {
        "key": "tuesday_launch",
        "day": "Tuesday",
        "time_label": "17:00",
        "title": "Podcast and YouTube launch",
        "description": "Launch the full episode where the weekly cycle begins.",
    },
    {
        "key": "tuesday_distribution",
        "day": "Tuesday",
        "time_label": "18:30-21:00",
        "title": "First clip, email, and social push",
        "description": "Use the first-night momentum window while attention is highest.",
    },
    {
        "key": "wednesday_momentum",
        "day": "Wednesday",
        "time_label": "12:00-15:00",
        "title": "Momentum and engagement",
        "description": "Publish the second clip, engage comments, and post a carousel.",
    },
    {
        "key": "thursday_blog",
        "day": "Thursday",
        "time_label": "11:00",
        "title": "Website blog post",
        "description": "Publish the SEO-focused long-form version on the website.",
    },
    {
        "key": "thursday_amplification",
        "day": "Thursday",
        "time_label": "14:00-17:00",
        "title": "Clip #3 and blog promotion",
        "description": "Use blog content to widen discovery and reinforce the episode.",
    },
    {
        "key": "friday_newsletter",
        "day": "Friday",
        "time_label": "15:00",
        "title": "Substack newsletter",
        "description": "Build the reflective and personal relationship layer for the episode.",
    },
    {
        "key": "friday_reflection",
        "day": "Friday",
        "time_label": "15:00-18:00",
        "title": "Reflection posts and engagement",
        "description": "Keep the conversation warm across social platforms before the weekend.",
    },
    {
        "key": "weekend_review",
        "day": "Weekend",
        "time_label": "Flexible",
        "title": "Analytics review and planning",
        "description": "Review performance, note what worked, and plan the next launch cycle.",
    },
]
OUTREACH_CORE_PRINCIPLES = [
    "One episode equals one coordinated launch cycle.",
    "Focus on the first 48 hours for maximum momentum.",
    "Repurpose every episode into multiple assets.",
    "Build audience relationship, not just content output.",
    "Monetize consistently, not occasionally.",
]
OUTREACH_METRICS = [
    "Downloads per episode (first 7 days)",
    "YouTube views (first 48 hours)",
    "Short-form performance",
    "Email subscriber growth",
    "Monthly revenue",
]

EXPORTABLE_FIELDS: Dict[str, list[str]] = {
    "guests": [
        "full_name",
        "email",
        "website",
        "profession",
        "social_media_handles",
        "background",
        "passionate_topics",
        "email_status",
        "original_file_name",
        "date_added",
    ],
    "interviews": [
        "guest_name",
        "guest_email",
        "title",
        "scheduled_for",
        "timezone",
        "join_url",
        "confirmation_status",
        "reminder_status",
        "calendar_event_id",
        "calendar_source",
    ],
    "episodes": [
        "guest_name",
        "guest_email",
        "website",
        "episode_title",
        "topic",
        "category",
        "interview_date",
        "release_date",
        "release_status",
        "production_status",
        "promotion_status",
        "priority_score",
        "legacy_episode_number",
        "riverside_status",
        "show_notes_url",
        "release_files_url",
        "transcript_text",
        "outreach_plan",
        "source_file_name",
        "recommendation_reason",
    ],
    "recommendations": [
        "guest_name",
        "guest_email",
        "episode_title",
        "topic",
        "category",
        "interview_date",
        "production_status",
        "promotion_status",
        "priority_score",
        "recommended_release_date",
        "recommendation_reason",
    ],
}


class WebInterfaceError(Exception):
    """Raised when a web request payload is invalid."""


def _word_count(text: str) -> int:
    """Count words in a text block."""
    return len(re.findall(r"\b\w+\b", text))


def _normalize_text(value: Any) -> str:
    """Convert form values to trimmed strings."""
    if value is None:
        return ""
    return str(value).strip()


def _normalize_website(value: Any) -> str:
    """Accept common website input patterns like www.example.com."""
    website = _normalize_text(value)
    if website and not re.match(r"^[a-z]+://", website, flags=re.IGNORECASE):
        website = f"https://{website}"
    return website


def _normalize_episode_release_status(release_date: str, release_status: str) -> str:
    """Treat dated future episodes as scheduled unless explicitly released."""
    normalized_status = _normalize_text(release_status).lower()
    normalized_date = _normalize_text(release_date)
    if normalized_status == "released":
        parsed_release = GuestWebService._parse_datetime_static(normalized_date)
        if parsed_release and parsed_release > datetime.now():
            return "scheduled"
        return "released"
    if normalized_date:
        return "scheduled"
    return normalized_status or "unplanned"


def validate_intake_payload(payload: Dict[str, str]) -> None:
    """Reject obviously spammy or low-effort intake submissions."""
    combined_text = " ".join(str(payload.get(field, "")) for field in payload).lower()

    if any(keyword in combined_text for keyword in SPAM_KEYWORDS):
        raise WebInterfaceError("Your submission was flagged as spam.")

    for field in LONG_TEXT_FIELDS:
        value = str(payload.get(field, "")).strip()
        if not value:
            continue
        if _word_count(value) < MIN_WORDS_BY_FIELD.get(field, 8):
            field_label = field.replace("_", " ")
            raise WebInterfaceError(f"Please provide a more complete answer for: {field_label}")


def build_guest_payload(payload: Dict[str, Any], source_name: str = FORM_SOURCE_NAME) -> Dict[str, Any]:
    """Convert a web form payload into the database shape."""
    guest_data = {field: _normalize_text(payload.get(field)) for field in FORM_FIELDS}
    guest_data["full_name"] = guest_data["full_name"] or _normalize_text(payload.get("name"))
    guest_data["website"] = _normalize_website(payload.get("website"))
    guest_data["is_processed"] = False
    guest_data["original_file_name"] = source_name
    guest_data["original_data"] = json.dumps(payload, ensure_ascii=False)

    if not guest_data["full_name"]:
        raise WebInterfaceError("Full name is required.")

    email = guest_data["email"]
    if email and "@" not in email:
        raise WebInterfaceError("Email address must contain '@'.")

    if source_name == INTAKE_SOURCE_NAME:
        validate_intake_payload(guest_data)

    return guest_data


def serialize_guest(guest: Dict[str, Any]) -> Dict[str, Any]:
    """Convert database rows into frontend-friendly JSON."""
    serialized = dict(guest)
    serialized["is_processed"] = bool(serialized.get("is_processed"))
    guest_research = serialized.get("guest_research")
    if isinstance(guest_research, str) and guest_research.strip():
        try:
            serialized["guest_research"] = json.loads(guest_research)
        except (TypeError, ValueError):
            serialized["guest_research"] = None
    elif not isinstance(guest_research, dict):
        serialized["guest_research"] = None
    serialized["guest_research"] = GuestWebService._decorate_research_payload(
        serialized.get("guest_research"),
        serialized.get("guest_research_updated_at"),
    )
    return serialized


def _empty_outreach_plan() -> Dict[str, bool]:
    """Return the default outreach checklist state."""
    return {step["key"]: False for step in OUTREACH_STEP_DEFINITIONS}


def _normalize_outreach_plan(value: Any) -> Dict[str, bool]:
    """Parse stored outreach JSON into a stable checklist payload."""
    normalized = _empty_outreach_plan()
    if isinstance(value, dict):
        source = value
    else:
        text = _normalize_text(value)
        if not text:
            return normalized
        try:
            source = json.loads(text)
        except (TypeError, ValueError):
            return normalized

    if not isinstance(source, dict):
        return normalized

    for step in OUTREACH_STEP_DEFINITIONS:
        normalized[step["key"]] = bool(source.get(step["key"]))
    return normalized


@dataclass
class GuestWebService:
    """Service layer for the direct web interface."""

    db_path: Path

    def __post_init__(self) -> None:
        self.database = GuestDatabase(self.db_path)

    def list_guests(self) -> Dict[str, Any]:
        """Return all guests for the frontend."""
        guests = [serialize_guest(guest) for guest in enrich_guests_with_recommendations(self.database.get_all_guests())]
        for guest in guests:
            guest["promotion_profile"] = self._build_guest_promotion_profile(guest)
        return {
            "guests": guests,
            "stats": self.database.get_stats(),
            "email_stats": self.database.get_email_stats(),
            "recommendation_stats": build_guest_recommendation_stats(guests),
            "email_enabled": self._build_email_manager().is_configured(),
        }

    def list_operations(self) -> Dict[str, Any]:
        """Return the current interview and episode operations data."""
        episodes = [self._normalize_episode_record(episode) for episode in self.database.list_episodes()]
        raw_interviews = self.database.list_interviews()
        interviews = [
            self._serialize_interview_reminder(interview)
            for interview in self._sort_interviews_by_upcoming_priority(raw_interviews)
        ]
        reminder_candidates = [self._serialize_interview_reminder(candidate) for candidate in self.get_due_weekly_reminders()]
        return {
            "stats": self.database.get_operations_stats(),
            "interviews": interviews,
            "reminder_candidates": reminder_candidates,
            "calendar_sync_enabled": self._build_google_calendar_client() is not None,
            "weekly_outreach": self._build_weekly_outreach_focus(episodes),
            "weekly_system": self._build_weekly_system_payload(),
            "booking_alerts": self._build_operations_alerts(raw_interviews),
        }

    def list_planning(self) -> Dict[str, Any]:
        """Return episode planning data separate from interview operations."""
        episodes = [self._normalize_episode_record(episode) for episode in self.database.list_episodes()]
        guests = [serialize_guest(guest) for guest in self.database.get_all_guests()]
        ai_copilot = self._build_openai_scheduling_copilot()
        enriched_episodes = []
        for episode in episodes:
            enriched = dict(episode)
            enriched["guest_profile_context"] = self._match_guest_profile_context(enriched, guests)
            enriched["guest_research"] = self._match_guest_research(enriched, guests)
            enriched["promotion_readiness"] = build_promotion_readiness(enriched)
            enriched["copy_assist"] = build_episode_copy_assist(enriched)
            enriched_episodes.append(enriched)
        recommendations = build_release_recommendations(enriched_episodes, reference=datetime.now())
        return {
            "stats": self._build_episode_stats(enriched_episodes),
            "episodes": enriched_episodes,
            "recommendations": recommendations,
            "available_categories": self.database.list_episode_categories(),
            "ask_sync_enabled": self._build_ask_mirror_talk_client() is not None,
            "ai_scheduling_enabled": ai_copilot is not None,
            "ai_copilot_status": {
                "status": "configured" if ai_copilot is not None else "not_configured",
                "message": (
                    "AI copilot is configured and will hydrate recommendation cards after the base planning view loads."
                    if ai_copilot is not None
                    else "AI copilot is not configured on this deployment."
                ),
                "current_month_context": build_month_context(datetime.now()),
            },
            "weekly_system": self._build_weekly_system_payload(),
        }

    def list_planning_ai_copilot(self) -> Dict[str, Any]:
        """Return AI-enriched recommendations without blocking the base planning page load."""
        ai_scheduling_client = self._build_openai_scheduling_copilot()
        if ai_scheduling_client is None:
            return {"ai_scheduling_enabled": False, "recommendations": []}

        episodes = [self._normalize_episode_record(episode) for episode in self.database.list_episodes()]
        guests = [serialize_guest(guest) for guest in self.database.get_all_guests()]
        enriched_episodes = []
        for episode in episodes:
            enriched = dict(episode)
            enriched["guest_profile_context"] = self._match_guest_profile_context(enriched, guests)
            enriched["guest_research"] = self._match_guest_research(enriched, guests)
            enriched["promotion_readiness"] = build_promotion_readiness(enriched)
            enriched["copy_assist"] = build_episode_copy_assist(enriched)
            enriched_episodes.append(enriched)

        recommendations = build_release_recommendations(enriched_episodes, reference=datetime.now())
        auto_researched_count = 0
        candidate_ids = {
            item.get("id")
            for item in recommendations[:AI_AUTORESEARCH_CANDIDATE_LIMIT]
            if item.get("id") is not None
        }
        if candidate_ids:
            for episode in enriched_episodes:
                if episode.get("id") not in candidate_ids:
                    continue
                if _normalize_text(episode.get("release_status")).lower() == "released":
                    continue
                auto_research = self._auto_research_guest_for_episode(episode, guests)
                if auto_research:
                    previous_updated_at = _normalize_text((episode.get("guest_research") or {}).get("updated_at"))
                    previous_mode = _normalize_text((episode.get("guest_research") or {}).get("research_mode"))
                    episode["guest_research"] = auto_research
                    if previous_updated_at != _normalize_text(auto_research.get("updated_at")) or previous_mode != _normalize_text(auto_research.get("research_mode")):
                        auto_researched_count += 1
            if auto_researched_count:
                recommendations = build_release_recommendations(enriched_episodes, reference=datetime.now())
        ai_diagnostics = self._build_ai_candidate_diagnostics(recommendations)
        ai_result = ai_scheduling_client.enrich_recommendations(
            recommendations,
            reference=datetime.now(),
            released_history=[
                item for item in enriched_episodes
                if _normalize_text(item.get("release_status")).lower() == "released"
            ],
        )
        return {
            "ai_scheduling_enabled": True,
            "ai_copilot_status": {
                "status": ai_result.get("status", "fallback"),
                "message": self._compose_ai_copilot_status_message(ai_result, auto_researched_count, ai_diagnostics),
                "model": ai_result.get("model"),
                "current_month_context": ai_result.get("current_month_context"),
                "diagnostics": ai_diagnostics,
            },
            "recommendations": ai_result.get("recommendations", recommendations),
        }

    @staticmethod
    def _compose_ai_copilot_status_message(
        ai_result: Dict[str, Any],
        auto_researched_count: int,
        diagnostics: Dict[str, int],
    ) -> str:
        """Blend AI runtime status with any automatic guest-research work."""
        base_message = _normalize_text(ai_result.get("message"))
        if _normalize_text(ai_result.get("status")) == "thin_context":
            base_message = (
                f"{base_message} "
                f"{diagnostics.get('with_profile_context', 0)} of {diagnostics.get('candidate_count', 0)} AI candidates had matched guest profile data, "
                f"and {diagnostics.get('with_guest_research', 0)} had reusable guest research."
            ).strip()
        if auto_researched_count <= 0:
            return base_message
        prefix = (
            f"Planning auto-researched {auto_researched_count} guest profile"
            f"{'s' if auto_researched_count != 1 else ''} from saved website or social data. "
        )
        return f"{prefix}{base_message}".strip()

    @staticmethod
    def _build_ai_candidate_diagnostics(recommendations: list[Dict[str, Any]]) -> Dict[str, int]:
        """Summarize how much grounded context the AI candidate window actually has."""
        candidate_window = recommendations[:4]
        return {
            "candidate_count": len(candidate_window),
            "with_profile_context": sum(1 for item in candidate_window if item.get("guest_profile_context")),
            "with_guest_research": sum(1 for item in candidate_window if item.get("guest_research")),
            "with_non_placeholder_topic": sum(
                1
                for item in candidate_window
                if _normalize_text(item.get("topic"))
                and _normalize_text(item.get("topic")).casefold() != _normalize_text(item.get("guest_name")).casefold()
            ),
        }

    def export_guests_csv(self) -> str:
        """Export all guests as a CSV string for occasional admin downloads."""
        guests = self.database.get_all_guests()
        fieldnames = [
            "id",
            "full_name",
            "email",
            "website",
            "social_media_handles",
            "background",
            "profession",
            "motivation",
            "life_experiences",
            "core_values",
            "faith_practice",
            "beliefs_align",
            "favorite_quote",
            "passionate_topics",
            "message_takeaway",
            "podcast_experience",
            "additional_info",
            "following_us",
            "is_processed",
            "email_status",
            "email_sent_at",
            "skip_reason",
            "original_file_name",
            "date_added",
            "updated_at",
        ]

        buffer = StringIO()
        writer = DictWriter(buffer, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for guest in guests:
            writer.writerow({name: guest.get(name, "") for name in fieldnames})
        return buffer.getvalue()

    def export_records(self, list_name: str, fields: list[str], export_format: str) -> tuple[bytes, str, str]:
        """Export a chosen list with selected fields as CSV or Excel."""
        normalized_list = list_name.strip().lower()
        if normalized_list not in EXPORTABLE_FIELDS:
            raise WebInterfaceError("That list cannot be exported.")

        allowed_fields = EXPORTABLE_FIELDS[normalized_list]
        selected_fields = [field for field in fields if field in allowed_fields]
        if not selected_fields:
            raise WebInterfaceError("Please choose at least one valid field to export.")

        normalized_format = export_format.strip().lower()
        if normalized_format not in {"csv", "xlsx"}:
            raise WebInterfaceError("Export format must be CSV or Excel.")

        records = self._records_for_export(normalized_list)
        if normalized_format == "csv":
            csv_text = self._records_to_csv(records, selected_fields)
            return (
                csv_text.encode("utf-8"),
                f"mirror-talk-{normalized_list}.csv",
                "text/csv; charset=utf-8",
            )

        workbook_bytes = self._records_to_xlsx(records, selected_fields)
        return (
            workbook_bytes,
            f"mirror-talk-{normalized_list}.xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    def _records_for_export(self, list_name: str) -> list[Dict[str, Any]]:
        """Collect the requested record set for export."""
        if list_name == "guests":
            return [serialize_guest(guest) for guest in self.database.get_all_guests()]
        if list_name == "interviews":
            return self._sort_interviews_by_upcoming_priority(self.database.list_interviews())
        if list_name == "episodes":
            return self.database.list_episodes()
        if list_name == "recommendations":
            episodes = self.database.list_episodes()
            return build_release_recommendations(episodes, reference=datetime.now())
        raise WebInterfaceError("That list cannot be exported.")

    @staticmethod
    def _build_episode_stats(episodes: list[Dict[str, Any]]) -> Dict[str, int]:
        """Build lightweight planning stats from episode records."""
        released = 0
        scheduled = 0
        unreleased = 0
        promo_ready_queue = 0
        needs_assets_queue = 0

        for episode in episodes:
            release_status = _normalize_text(episode.get("release_status")).lower()
            promo_status = _normalize_text(episode.get("promotion_status")).lower()
            if release_status == "released":
                released += 1
            else:
                unreleased += 1
                if promo_status == "ready":
                    promo_ready_queue += 1
                elif promo_status == "needs_assets":
                    needs_assets_queue += 1
            if release_status == "scheduled":
                scheduled += 1

        return {
            "episodes_total": len(episodes),
            "episodes_released": released,
            "episodes_scheduled": scheduled,
            "episodes_unreleased": unreleased,
            "episodes_promo_ready": promo_ready_queue,
            "episodes_need_assets": needs_assets_queue,
        }

    @staticmethod
    def _build_weekly_system_payload() -> Dict[str, Any]:
        """Return the reusable Mirror Talk weekly outreach system."""
        return {
            "steps": OUTREACH_STEP_DEFINITIONS,
            "principles": OUTREACH_CORE_PRINCIPLES,
            "metrics": OUTREACH_METRICS,
        }

    @staticmethod
    def _build_guest_promotion_profile(guest: Dict[str, Any]) -> Dict[str, Any]:
        """Estimate how promotion-ready a guest profile is for outreach."""
        strengths: list[str] = []
        gaps: list[str] = []
        score = 0

        if _normalize_text(guest.get("website")):
            score += 30
            strengths.append("Website available for blog, show notes, and guest links.")
        else:
            gaps.append("Website missing, so blog and profile linking will take more manual work.")

        if _normalize_text(guest.get("social_media_handles")):
            score += 30
            strengths.append("Social profile details are available for outreach tagging and promotion.")
        else:
            gaps.append("Social profile details are missing, which limits fast post-release promotion.")

        if _normalize_text(guest.get("background")):
            score += 20
            strengths.append("Background is filled in, which helps with show notes and release copy.")
        else:
            gaps.append("Background is thin, so promo copy may need more manual shaping.")

        if _normalize_text(guest.get("podcast_experience")) or _normalize_text(guest.get("additional_info")):
            score += 10
            strengths.append("There is enough supporting context to brief the guest and shape promotion.")

        if _normalize_text(guest.get("email")):
            score += 10
            strengths.append("Email is available for thank-you and release follow-up.")
        else:
            gaps.append("Email is missing, which blocks the key follow-up emails.")

        if score >= 80:
            label = "Promotion-ready guest profile"
        elif score >= 55:
            label = "Good foundation"
        else:
            label = "Needs profile enrichment"

        return {
            "score": score,
            "label": label,
            "strengths": strengths[:3],
            "gaps": gaps[:3],
        }

    @staticmethod
    def _research_payload(value: Any) -> Optional[Dict[str, Any]]:
        """Parse stored guest research JSON into a stable object."""
        if isinstance(value, dict):
            return value
        text = _normalize_text(value)
        if not text:
            return None
        try:
            parsed = json.loads(text)
        except (TypeError, ValueError):
            return None
        return parsed if isinstance(parsed, dict) else None

    @staticmethod
    def _research_freshness(updated_at: Any) -> Dict[str, Any]:
        """Summarize how fresh stored guest research is."""
        updated_text = _normalize_text(updated_at)
        if not updated_text:
            return {"status": "missing", "label": "Not researched yet", "age_days": None}
        normalized = updated_text.replace("Z", "+00:00")
        try:
            updated_dt = datetime.fromisoformat(normalized)
        except ValueError:
            return {"status": "unknown", "label": "Research date unavailable", "age_days": None}
        if updated_dt.tzinfo is None:
            updated_dt = updated_dt.replace(tzinfo=timezone.utc)
        age_days = max(0, int((datetime.now(timezone.utc) - updated_dt.astimezone(timezone.utc)).total_seconds() // 86400))
        if age_days <= 30:
            return {"status": "fresh", "label": f"Fresh · {age_days}d ago", "age_days": age_days}
        if age_days <= 90:
            return {"status": "aging", "label": f"Aging · {age_days}d ago", "age_days": age_days}
        return {"status": "stale", "label": f"Stale · {age_days}d ago", "age_days": age_days}

    @staticmethod
    def _decorate_research_payload(research: Any, updated_at: Any = None) -> Optional[Dict[str, Any]]:
        """Attach stable metadata to stored guest research payloads."""
        if not isinstance(research, dict):
            return None
        decorated = dict(research)
        research_updated_at = _normalize_text(decorated.get("updated_at")) or _normalize_text(updated_at)
        mode = _normalize_text(decorated.get("research_mode")) or "manual"
        cache_status = _normalize_text(decorated.get("cache_status")) or "ready"
        decorated["updated_at"] = research_updated_at
        decorated["research_mode"] = mode
        decorated["cache_status"] = cache_status
        decorated["freshness"] = GuestWebService._research_freshness(research_updated_at)
        return decorated

    @staticmethod
    def _guest_has_public_profile_hint(guest: Dict[str, Any]) -> bool:
        """Check whether a guest has enough public profile data for web research."""
        return bool(
            _normalize_text(guest.get("website"))
            or _normalize_text(guest.get("social_media_handles"))
            or _normalize_text(guest.get("social_handles"))
        )

    def _find_matching_guest(self, episode: Dict[str, Any], guests: list[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Find the best matching guest for an episode by email first, then exact name."""
        email_key = _normalize_text(episode.get("guest_email")).casefold()
        name_key = _normalize_text(episode.get("guest_name")).casefold()

        for guest in guests:
            if email_key and _normalize_text(guest.get("email")).casefold() == email_key:
                return guest

        for guest in guests:
            guest_name = _normalize_text(guest.get("full_name") or guest.get("name")).casefold()
            if name_key and guest_name == name_key:
                return guest

        return None

    def _persist_guest_research(self, guest: Dict[str, Any], research: Dict[str, Any]) -> Dict[str, Any]:
        """Save refreshed public-profile research back onto the guest record."""
        guest_id = guest.get("id")
        if not str(guest_id or "").isdigit():
            return guest
        current = self.database.get_guest_by_id(int(guest_id))
        if not current:
            return guest
        updated_guest = dict(current)
        updated_guest["guest_research"] = json.dumps(research, ensure_ascii=False)
        updated_guest["guest_research_updated_at"] = research.get("updated_at")
        self.database.update_guest_by_id(int(guest_id), updated_guest)
        refreshed = self.database.get_guest_by_id(int(guest_id))
        return serialize_guest(refreshed) if refreshed else guest

    def _persist_guest_research_failure(self, guest: Dict[str, Any], error_message: str, mode: str = "auto") -> Dict[str, Any]:
        """Cache a failed research attempt so repeated runs do not retry the same bad source forever."""
        guest_id = guest.get("id")
        if not str(guest_id or "").isdigit():
            return guest
        current = self.database.get_guest_by_id(int(guest_id))
        if not current:
            return guest
        now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        failure_payload = {
            "summary": "",
            "likely_topics": [],
            "timely_signals": [],
            "sources": [],
            "updated_at": now,
            "research_mode": mode,
            "cache_status": "failed",
            "last_error": _normalize_text(error_message),
        }
        updated_guest = dict(current)
        updated_guest["guest_research"] = json.dumps(failure_payload, ensure_ascii=False)
        updated_guest["guest_research_updated_at"] = now
        self.database.update_guest_by_id(int(guest_id), updated_guest)
        refreshed = self.database.get_guest_by_id(int(guest_id))
        return serialize_guest(refreshed) if refreshed else guest

    def _auto_research_guest_for_episode(self, episode: Dict[str, Any], guests: list[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Auto-research a matched guest so planning can rely on real profile evidence."""
        matched_guest = self._find_matching_guest(episode, guests)
        if not matched_guest:
            return None
        existing_research = self._decorate_research_payload(
            self._research_payload(matched_guest.get("guest_research")),
            matched_guest.get("guest_research_updated_at"),
        )
        if existing_research:
            if existing_research.get("cache_status") == "failed":
                return None
            return existing_research
        if not self._guest_has_public_profile_hint(matched_guest):
            return existing_research
        try:
            research = research_guest_from_public_web(matched_guest)
        except ValueError as exc:
            self._persist_guest_research_failure(matched_guest, str(exc), mode="auto")
            return existing_research
        research["research_mode"] = "auto"
        research["cache_status"] = "ready"
        refreshed_guest = self._persist_guest_research(matched_guest, research)
        matched_guest.update(refreshed_guest)
        return self._decorate_research_payload(
            self._research_payload(refreshed_guest.get("guest_research")) or research,
            refreshed_guest.get("guest_research_updated_at") or research.get("updated_at"),
        )

    def _match_guest_research(self, episode: Dict[str, Any], guests: list[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Attach guest research to planning records by guest email first, then by name."""
        matched_guest = self._find_matching_guest(episode, guests)
        if not matched_guest:
            return None
        research = self._decorate_research_payload(
            self._research_payload(matched_guest.get("guest_research")),
            matched_guest.get("guest_research_updated_at"),
        )
        if research and research.get("cache_status") == "failed":
            return None
        return research

    def _match_guest_profile_context(self, episode: Dict[str, Any], guests: list[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Attach compact guest profile context from the Mirror Talk database."""
        matched_guest = self._find_matching_guest(episode, guests)
        if matched_guest is None:
            return None

        return {
            "profession": _normalize_text(matched_guest.get("profession")),
            "background": _normalize_text(matched_guest.get("background")),
            "faith_practice": _normalize_text(matched_guest.get("faith_practice")),
            "core_values": _normalize_text(matched_guest.get("core_values")),
            "passionate_topics": _normalize_text(matched_guest.get("passionate_topics")),
        }

    def _build_episode_outreach_summary(self, episode: Dict[str, Any]) -> Dict[str, Any]:
        """Summarize the outreach checklist and next activation step for an episode."""
        plan = _normalize_outreach_plan(episode.get("outreach_plan"))
        completed_steps = [step for step in OUTREACH_STEP_DEFINITIONS if plan.get(step["key"])]
        pending_steps = [step for step in OUTREACH_STEP_DEFINITIONS if not plan.get(step["key"])]
        completed_count = len(completed_steps)
        total_count = len(OUTREACH_STEP_DEFINITIONS)
        release_status = _normalize_text(episode.get("release_status")).lower()

        if release_status == "released" and not pending_steps:
            next_step = "Launch cycle complete. Use the weekend review to fold insights into the next episode."
        elif pending_steps:
            first_pending = pending_steps[0]
            next_step = f"Next outreach step: {first_pending['day']} {first_pending['title'].lower()}."
        else:
            next_step = "No outreach tasks have been started yet."

        return {
            "plan": plan,
            "completed_count": completed_count,
            "total_count": total_count,
            "progress_label": f"{completed_count}/{total_count} outreach steps complete",
            "next_step": next_step,
            "completed_labels": [step["title"] for step in completed_steps[:3]],
            "pending_labels": [step["title"] for step in pending_steps[:3]],
        }

    def _build_weekly_outreach_focus(self, episodes: list[Dict[str, Any]]) -> Dict[str, Any]:
        """Build a weekly outreach spotlight for operations."""
        reference = datetime.now()

        def episode_rank(item: Dict[str, Any]) -> tuple[int, float]:
            release_date = self._parse_datetime_static(item.get("release_date"))
            if release_date:
                delta_days = abs((release_date - reference).total_seconds())
                return (0, delta_days)
            interview_date = self._parse_datetime_static(item.get("interview_date"))
            if interview_date:
                delta_days = abs((interview_date - reference).total_seconds())
                return (1, delta_days)
            return (2, float(item.get("id") or 0) * -1)

        eligible = [
            item
            for item in episodes
            if _normalize_text(item.get("release_status")).lower() in {"scheduled", "released"}
        ]
        spotlight = min(eligible, key=episode_rank) if eligible else None

        return {
            "social_focus": [
                {"day": "Tuesday", "theme": "Launch and attention spike"},
                {"day": "Wednesday", "theme": "Momentum and engagement"},
                {"day": "Thursday", "theme": "Discovery and SEO amplification"},
                {"day": "Friday", "theme": "Connection and relationship building"},
            ],
            "spotlight_episode": spotlight,
            "spotlight_summary": self._build_episode_outreach_summary(spotlight) if spotlight else None,
        }

    def _build_operations_alerts(self, interviews: list[Dict[str, Any]]) -> Dict[str, Any]:
        """Highlight duplicate future bookings and stale calendar holds."""
        reference = datetime.now()
        duplicate_groups: Dict[str, list[Dict[str, Any]]] = {}
        cleanup_candidates: list[Dict[str, Any]] = []

        for interview in interviews:
            scheduled_for = self._parse_datetime(interview.get("scheduled_for"))
            if not scheduled_for:
                continue
            comparison_reference = self._align_reference_datetime(reference, scheduled_for)
            future_or_current = scheduled_for >= comparison_reference
            status = _normalize_text(interview.get("status")).lower()
            confirmation = _normalize_text(interview.get("confirmation_status")).lower()
            guest_key = _normalize_text(interview.get("guest_email")) or _normalize_text(interview.get("guest_name"))

            if future_or_current and status != "cancelled" and confirmation != "declined" and guest_key:
                duplicate_groups.setdefault(guest_key, []).append(interview)

            if _normalize_text(interview.get("calendar_event_id")) and (
                status == "cancelled" or confirmation in {"declined", "reschedule_requested"}
            ):
                reason = "Cancelled interview still linked to Google Calendar." if status == "cancelled" else "Guest declined or asked to reschedule, but the calendar slot still exists."
                cleanup_candidates.append(
                    {
                        "id": interview.get("id"),
                        "guest_name": _normalize_text(interview.get("guest_name")),
                        "title": _normalize_text(interview.get("title")),
                        "scheduled_for": interview.get("scheduled_for"),
                        "reason": reason,
                    }
                )

        duplicate_alerts = []
        for items in duplicate_groups.values():
            if len(items) < 2:
                continue
            sorted_items = self._sort_interviews_by_upcoming_priority(items, reference=reference)
            duplicate_alerts.append(
                {
                    "guest_name": _normalize_text(sorted_items[0].get("guest_name")) or "Guest",
                    "count": len(sorted_items),
                    "interviews": [
                        {
                            "id": item.get("id"),
                            "title": _normalize_text(item.get("title")),
                            "scheduled_for": item.get("scheduled_for"),
                        }
                        for item in sorted_items
                    ],
                }
            )

        duplicate_alerts.sort(key=lambda item: item["guest_name"].lower())
        cleanup_candidates.sort(key=lambda item: _normalize_text(item.get("scheduled_for")))
        return {
            "double_bookings": duplicate_alerts,
            "calendar_cleanup": cleanup_candidates,
        }

    @staticmethod
    def _parse_datetime_static(value: Any) -> Optional[datetime]:
        """Parse simple date/datetime strings used in planning records."""
        text = _normalize_text(value)
        if not text:
            return None
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%d"):
            try:
                return datetime.strptime(text, fmt)
            except ValueError:
                continue
        try:
            return datetime.fromisoformat(text.replace("Z", "+00:00")).replace(tzinfo=None)
        except ValueError:
            return None

    def _normalize_episode_record(self, episode: Dict[str, Any]) -> Dict[str, Any]:
        """Fix stale imported planning states based on current release dates."""
        normalized = dict(episode)
        normalized_status = _normalize_episode_release_status(
            _normalize_text(episode.get("release_date")),
            _normalize_text(episode.get("release_status")),
        )
        normalized["release_status"] = normalized_status
        if normalized_status == "released":
            normalized["production_status"] = "released"
        if normalized_status == "scheduled" and _normalize_text(normalized.get("production_status")).lower() == "released":
            normalized["production_status"] = "ready"
        normalized["outreach_plan"] = _normalize_outreach_plan(normalized.get("outreach_plan"))
        normalized["outreach_summary"] = self._build_episode_outreach_summary(normalized)
        return normalized

    @staticmethod
    def _episode_match_key(value: Any) -> str:
        """Create a conservative normalized title key for transcript sync."""
        normalized = _normalize_text(value).lower()
        normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
        return " ".join(part for part in normalized.split() if part)

    @staticmethod
    def _word_tokens(value: Any) -> list[str]:
        """Split a text into normalized comparison tokens."""
        normalized = _normalize_text(value).lower()
        normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
        return [part for part in normalized.split() if len(part) > 1]

    @classmethod
    def _person_tokens(cls, value: Any) -> list[str]:
        """Split a guest name into meaningful person tokens."""
        stop_words = {"and", "with", "the", "podcast", "mirror", "talk"}
        return [part for part in cls._word_tokens(value) if part not in stop_words]

    @staticmethod
    def _extract_guest_name_from_interview_title(title: Any, fallback_name: Any) -> str:
        """Prefer the real guest participant list when an interview title includes the host too."""

        def strip_host_participants(value: str) -> str:
            if not value:
                return ""
            parts = [
                part.strip(" -,:")
                for part in re.split(r"\s*(?:,|&|\band\b)\s*", value, flags=re.IGNORECASE)
                if part.strip(" -,:")
            ]
            if len(parts) < 2:
                return value

            guest_parts = [part for part in parts if not any(hint in part.lower() for hint in HOST_NAME_HINTS)]
            if not guest_parts or len(guest_parts) == len(parts):
                return value
            if len(guest_parts) == 1:
                return guest_parts[0]
            return " & ".join(guest_parts)

        fallback = strip_host_participants(_normalize_text(fallback_name))
        text = strip_host_participants(_normalize_text(title))
        return text or fallback

    @classmethod
    def _episode_title_overlap_score(cls, episode: Dict[str, Any], remote_episode: Dict[str, Any]) -> int:
        """Score title/topic overlap to break ties for guest-based matches."""
        local_tokens = set(cls._word_tokens(episode.get("episode_title"))) | set(cls._word_tokens(episode.get("topic")))
        remote_tokens = set(cls._word_tokens(remote_episode.get("title")))
        if not local_tokens or not remote_tokens:
            return 0
        overlap = len(local_tokens & remote_tokens)
        return min(overlap * 10, 60)

    @classmethod
    def _episode_date_proximity_score(cls, episode: Dict[str, Any], remote_episode: Dict[str, Any]) -> int:
        """Use publish/release proximity as a supporting match signal."""
        local_date = (
            cls._parse_datetime_static(episode.get("release_date"))
            or cls._parse_datetime_static(episode.get("interview_date"))
        )
        remote_date = cls._parse_datetime_static(remote_episode.get("published_at"))
        if not local_date or not remote_date:
            return 0
        day_gap = abs((local_date.date() - remote_date.date()).days)
        if day_gap <= 3:
            return 80
        if day_gap <= 14:
            return 50
        if day_gap <= 45:
            return 20
        return 0

    @classmethod
    def _score_ask_episode_match(cls, episode: Dict[str, Any], remote_episode: Dict[str, Any]) -> tuple[int, str]:
        """Return a conservative score and method for Ask Mirror Talk matching."""
        local_title_key = cls._episode_match_key(episode.get("episode_title"))
        remote_title_key = cls._episode_match_key(remote_episode.get("title"))
        if local_title_key and remote_title_key and local_title_key == remote_title_key:
            return 1000, "title"

        guest_tokens = cls._person_tokens(episode.get("guest_name"))
        if not guest_tokens:
            return 0, ""

        remote_title_tokens = set(cls._word_tokens(remote_episode.get("title")))
        remote_description_tokens = set(cls._word_tokens(remote_episode.get("description")))
        overlap_bonus = cls._episode_title_overlap_score(episode, remote_episode)
        date_bonus = cls._episode_date_proximity_score(episode, remote_episode)
        surname_token = guest_tokens[-1] if len(guest_tokens) > 1 else guest_tokens[0]

        if all(token in remote_title_tokens for token in guest_tokens):
            return 800 + overlap_bonus + date_bonus, "guest_title"
        if all(token in remote_description_tokens for token in guest_tokens):
            return 700 + overlap_bonus + date_bonus, "guest_description"

        title_hits = sum(token in remote_title_tokens for token in guest_tokens)
        if len(guest_tokens) >= 2 and title_hits >= len(guest_tokens) - 1 and surname_token in remote_title_tokens:
            return 500 + overlap_bonus + date_bonus, "guest_partial"

        primary_tokens = [surname_token] if len(guest_tokens) > 1 else [guest_tokens[0]]

        partial_title_hits = sum(token in remote_title_tokens for token in primary_tokens)
        partial_description_hits = sum(token in remote_description_tokens for token in primary_tokens)
        if partial_title_hits and (date_bonus >= 50 or overlap_bonus >= 20):
            return 360 + overlap_bonus + date_bonus, "guest_name_fragment"
        if partial_description_hits and date_bonus >= 50:
            return 320 + overlap_bonus + date_bonus, "guest_name_fragment"

        return 0, ""

    @classmethod
    def _summarize_ask_match_candidate(
        cls,
        episode: Dict[str, Any],
        remote_episode: Dict[str, Any],
        score: int,
        method: str,
    ) -> Dict[str, Any]:
        """Return a compact candidate summary for ambiguous Ask matches."""
        local_date = episode.get("release_date") or episode.get("interview_date")
        remote_date = remote_episode.get("published_at")
        return {
            "id": remote_episode.get("id"),
            "title": _normalize_text(remote_episode.get("title")),
            "published_at": _normalize_text(remote_date),
            "score": score,
            "method": method,
            "has_transcript": bool(_normalize_text(remote_episode.get("transcript_text"))),
            "date_gap_days": cls._ask_candidate_date_gap_days(local_date, remote_date),
        }

    @classmethod
    def _ask_candidate_date_gap_days(cls, local_value: Any, remote_value: Any) -> Optional[int]:
        """Return the absolute day gap between local and remote dates when both are available."""
        local_date = cls._parse_datetime_static(local_value)
        remote_date = cls._parse_datetime_static(remote_value)
        if not local_date or not remote_date:
            return None
        return abs((local_date.date() - remote_date.date()).days)

    @staticmethod
    def _records_to_csv(records: list[Dict[str, Any]], fields: list[str]) -> str:
        """Serialize records to CSV using the selected fields."""
        buffer = StringIO()
        writer = DictWriter(buffer, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for record in records:
            writer.writerow({field: record.get(field, "") for field in fields})
        return buffer.getvalue()

    @staticmethod
    def _records_to_xlsx(records: list[Dict[str, Any]], fields: list[str]) -> bytes:
        """Serialize records to an Excel workbook using the selected fields."""
        workbook = Workbook()
        worksheet = workbook.active
        worksheet.title = "Export"
        worksheet.append(fields)
        for record in records:
            worksheet.append([record.get(field, "") for field in fields])

        output = BytesIO()
        workbook.save(output)
        return output.getvalue()

    def create_guest(self, payload: Dict[str, Any], source_name: str = FORM_SOURCE_NAME) -> Dict[str, Any]:
        """Create a guest directly from the web form."""
        guest_data = build_guest_payload(payload, source_name=source_name)
        guest_id, _ = self.database.upsert_guest(guest_data)
        guest = self.database.get_guest_by_id(guest_id)
        return serialize_guest(guest) if guest else {"id": guest_id}

    def create_intake_submission(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Create a guest submission from the public intake questionnaire."""
        guest = self.create_guest(payload, source_name=INTAKE_SOURCE_NAME)
        self._send_intake_confirmation_email(guest)
        return guest

    def import_guest_file(self, filename: str, content: bytes, encoding: str = "utf-8") -> Dict[str, int]:
        """Import guests from an uploaded CSV or Excel file."""
        suffix = Path(filename).suffix.lower()
        if suffix not in {".csv", ".xlsx", ".xls"}:
            raise WebInterfaceError("Please upload a CSV or Excel file.")

        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp_file:
            tmp_file.write(content)
            temp_path = Path(tmp_file.name)

        try:
            return self.database.import_from_file(str(temp_path), encoding=encoding, source_name=filename)
        finally:
            temp_path.unlink(missing_ok=True)

    def update_guest_status(self, guest_id: int, status: str, skip_reason: str = "") -> Dict[str, Any]:
        """Update a guest processing status."""
        normalized_status = status.strip().lower()

        if normalized_status == "accepted":
            self.database.accept_guest_without_email(guest_id)
        elif normalized_status == "rejected":
            self.database.reject_guest_without_email(guest_id)
        elif normalized_status == "skipped":
            self.database.skip_guest(guest_id, skip_reason)
        elif normalized_status == "unprocessed":
            self.database.mark_guest_unprocessed(guest_id)
        elif normalized_status == "processed":
            self.database.mark_guest_processed(guest_id)
        else:
            raise WebInterfaceError(f"Unsupported status: {status}")

        guest = self.database.get_guest_by_id(guest_id)
        if not guest:
            raise WebInterfaceError("Guest not found.")
        return serialize_guest(guest)

    def send_guest_decision_email(self, guest_id: int, status: str, custom_message: str = "") -> Dict[str, Any]:
        """Send an approval/decline email and persist the resulting decision."""
        return self.send_guest_decision_email_message(guest_id, status, subject="", body="", custom_message=custom_message)

    def get_guest_decision_email_template(self, guest_id: int, status: str) -> Dict[str, str]:
        """Return the default approval/decline email template for dashboard editing."""
        normalized_status = status.strip().lower()
        if normalized_status not in {"accepted", "rejected"}:
            raise WebInterfaceError("Only accepted or rejected emails can be sent.")

        guest = self.database.get_guest_by_id(guest_id)
        if not guest:
            raise WebInterfaceError("Guest not found.")

        guest_name = (guest.get("full_name") or guest.get("name") or "Guest").strip()
        email_manager = self._build_email_manager()

        if normalized_status == "accepted":
            return email_manager.get_acceptance_template(guest_name)

        return email_manager.get_rejection_template(guest_name)

    def send_guest_decision_email_message(
        self,
        guest_id: int,
        status: str,
        subject: str = "",
        body: str = "",
        custom_message: str = "",
    ) -> Dict[str, Any]:
        """Send an approval/decline email and persist the resulting decision."""
        normalized_status = status.strip().lower()
        if normalized_status not in {"accepted", "rejected"}:
            raise WebInterfaceError("Only accepted or rejected emails can be sent.")

        guest = self.database.get_guest_by_id(guest_id)
        if not guest:
            raise WebInterfaceError("Guest not found.")

        guest_email = (guest.get("email") or "").strip()
        if not guest_email:
            raise WebInterfaceError("This guest does not have an email address.")

        email_manager = self._build_email_manager()
        if not email_manager.is_configured():
            raise WebInterfaceError("Dashboard email is not configured on the server.")

        guest_name = (guest.get("full_name") or guest.get("name") or "Guest").strip()

        subject = subject.strip()
        body = body.strip()

        if subject and body:
            sent = email_manager.send_email(guest_email, subject, body)
        else:
            if normalized_status == "accepted":
                sent = email_manager.send_acceptance_email(guest_name, guest_email, custom_message)
            else:
                sent = email_manager.send_rejection_email(guest_name, guest_email, custom_message)

        if not sent:
            error_detail = (email_manager.last_error or "").strip()
            if error_detail:
                raise WebInterfaceError(f"The email could not be sent: {error_detail}")
            raise WebInterfaceError("The email could not be sent. Please check the server email configuration.")

        if normalized_status == "accepted":
            self.database.accept_guest_with_email(guest_id, custom_message)
        else:
            self.database.reject_guest_with_email(guest_id, custom_message)

        updated_guest = self.database.get_guest_by_id(guest_id)
        if not updated_guest:
            raise WebInterfaceError("Guest not found after email send.")
        return serialize_guest(updated_guest)

    def delete_guest(self, guest_id: int, confirm_name: str = "") -> Dict[str, Any]:
        """Delete a guest and return a small confirmation payload."""
        guest = self.database.get_guest_by_id(guest_id)
        if not guest:
            raise WebInterfaceError("Guest not found.")

        guest_name = _normalize_text(guest.get("full_name") or guest.get("name"))
        normalized_confirm_name = _normalize_text(confirm_name)
        needs_strong_confirmation = bool(guest.get("is_processed")) or bool(_normalize_text(guest.get("email_status")))
        if needs_strong_confirmation and guest_name and normalized_confirm_name != guest_name:
            raise WebInterfaceError(
                f'Type "{guest.get("full_name") or guest.get("name")}" to delete this processed guest.'
            )

        self.database.delete_guest(guest_id)
        return {"deleted": True, "id": guest_id}

    def update_guest(self, guest_id: int, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Update core guest details without overwriting source/status metadata."""
        current = self.database.get_guest_by_id(guest_id)
        if not current:
            raise WebInterfaceError("Guest not found.")

        updated_guest = {
            "full_name": _normalize_text(payload.get("full_name")) or _normalize_text(current.get("full_name") or current.get("name")),
            "email": _normalize_text(payload.get("email")) or _normalize_text(current.get("email")),
            "website": _normalize_text(payload.get("website")) or _normalize_text(current.get("website")),
            "profession": _normalize_text(payload.get("profession")) or _normalize_text(current.get("profession")),
            "social_handles": _normalize_text(payload.get("social_handles")) or _normalize_text(current.get("social_media_handles")),
            "background": _normalize_text(payload.get("background")) or _normalize_text(current.get("background")),
            "motivation": _normalize_text(payload.get("motivation")) or _normalize_text(current.get("motivation")),
            "life_experiences": _normalize_text(payload.get("life_experiences")) or _normalize_text(current.get("life_experiences")),
            "core_values": _normalize_text(payload.get("core_values")) or _normalize_text(current.get("core_values")),
            "favorite_quote": _normalize_text(payload.get("favorite_quote")) or _normalize_text(current.get("favorite_quote")),
            "passionate_topics": _normalize_text(payload.get("passionate_topics")) or _normalize_text(current.get("passionate_topics")),
            "additional_info": _normalize_text(payload.get("additional_info")) or _normalize_text(current.get("additional_info")),
            "has_social_media": _normalize_text(payload.get("has_social_media")) or _normalize_text(current.get("following_us")),
            "is_processed": current.get("is_processed"),
            "email_status": current.get("email_status"),
            "email_sent_at": current.get("email_sent_at"),
            "skip_reason": current.get("skip_reason"),
            "original_file_name": current.get("original_file_name"),
            "original_data": current.get("original_data"),
            "guest_research": current.get("guest_research"),
            "guest_research_updated_at": current.get("guest_research_updated_at"),
        }

        if not updated_guest["full_name"]:
            raise WebInterfaceError("Full name is required.")

        if updated_guest["email"] and "@" not in updated_guest["email"]:
            raise WebInterfaceError("Email address must contain '@'.")

        self.database.update_guest_by_id(guest_id, updated_guest)
        guest = self.database.get_guest_by_id(guest_id)
        if not guest:
            raise WebInterfaceError("Guest could not be saved.")
        return serialize_guest(guest)

    def research_guest(self, guest_id: int) -> Dict[str, Any]:
        """Fetch public profile context for a guest and store it for copilot use."""
        current = self.database.get_guest_by_id(guest_id)
        if not current:
            raise WebInterfaceError("Guest not found.")

        try:
            research = research_guest_from_public_web(current)
        except ValueError as exc:
            raise WebInterfaceError(str(exc))
        research["research_mode"] = "manual"

        updated_guest = dict(current)
        updated_guest["guest_research"] = json.dumps(research, ensure_ascii=False)
        updated_guest["guest_research_updated_at"] = research.get("updated_at")

        self.database.update_guest_by_id(guest_id, updated_guest)
        guest = self.database.get_guest_by_id(guest_id)
        if not guest:
            raise WebInterfaceError("Guest could not be saved after research.")
        return serialize_guest(guest)

    def retry_guest_research_with_search(self, guest_id: int) -> Dict[str, Any]:
        """Retry failed guest research by using Google search results as a rescue source."""
        current = self.database.get_guest_by_id(guest_id)
        if not current:
            raise WebInterfaceError("Guest not found.")

        existing_research = self._decorate_research_payload(
            self._research_payload(current.get("guest_research")),
            current.get("guest_research_updated_at"),
        )
        if not existing_research or existing_research.get("cache_status") != "failed":
            raise WebInterfaceError("Search-assisted retry is only available for guests whose research has already failed.")

        try:
            research = research_guest_from_google_search(current)
        except ValueError as exc:
            raise WebInterfaceError(str(exc))
        research["research_mode"] = "manual"
        research["cache_status"] = "ready"

        updated_guest = dict(current)
        updated_guest["guest_research"] = json.dumps(research, ensure_ascii=False)
        updated_guest["guest_research_updated_at"] = research.get("updated_at")

        self.database.update_guest_by_id(guest_id, updated_guest)
        guest = self.database.get_guest_by_id(guest_id)
        if not guest:
            raise WebInterfaceError("Guest could not be saved after search-assisted research.")
        return serialize_guest(guest)

    def bulk_research_guests(self, limit: int = BULK_GUEST_RESEARCH_BATCH_SIZE) -> Dict[str, Any]:
        """Research missing guest profiles in bounded batches for faster planning copilot prep."""
        limit = max(1, min(100, int(limit or BULK_GUEST_RESEARCH_BATCH_SIZE)))
        guests = [serialize_guest(guest) for guest in self.database.get_all_guests()]
        actionable: list[Dict[str, Any]] = []
        skipped_cached = 0
        skipped_failed = 0
        skipped_missing_profile = 0

        for guest in guests:
            existing_research = self._decorate_research_payload(
                self._research_payload(guest.get("guest_research")),
                guest.get("guest_research_updated_at"),
            )
            if existing_research:
                if existing_research.get("cache_status") == "failed":
                    skipped_failed += 1
                else:
                    skipped_cached += 1
                continue
            if not self._guest_has_public_profile_hint(guest):
                skipped_missing_profile += 1
                continue
            actionable.append(guest)

        researched = 0
        errors: list[str] = []
        for guest in actionable[:limit]:
            try:
                research = research_guest_from_public_web(guest)
            except ValueError as exc:
                errors.append(f"{_normalize_text(guest.get('full_name')) or 'Guest'}: {exc}")
                self._persist_guest_research_failure(guest, str(exc), mode="manual")
                continue
            research["research_mode"] = "manual"
            research["cache_status"] = "ready"
            self._persist_guest_research(guest, research)
            researched += 1

        return {
            "researched": researched,
            "errors": errors[:5],
            "skipped_cached": skipped_cached,
            "skipped_failed": skipped_failed,
            "skipped_missing_profile": skipped_missing_profile,
            "remaining_eligible": max(0, len(actionable) - limit),
            "processed_batch_size": min(limit, len(actionable)),
            "eligible_total": len(actionable),
        }

    def delete_interview(self, interview_id: int, confirm_label: str = "") -> Dict[str, Any]:
        """Delete an interview and return a small confirmation payload."""
        interview = self.database.get_interview_by_id(interview_id)
        if not interview:
            raise WebInterfaceError("Interview not found.")
        expected_label = _normalize_text(interview.get("guest_name")) or _normalize_text(interview.get("title"))
        if expected_label and _normalize_text(confirm_label) != expected_label:
            raise WebInterfaceError(
                f'Type "{interview.get("guest_name") or interview.get("title")}" to delete this interview.'
            )
        self.database.delete_interview(interview_id)
        return {"deleted": True, "id": interview_id}

    def create_interview(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Create or update an interview record."""
        interview_data = {
            "guest_id": payload.get("guest_id"),
            "guest_name": _normalize_text(payload.get("guest_name")),
            "guest_email": _normalize_text(payload.get("guest_email")),
            "calendar_event_id": _normalize_text(payload.get("calendar_event_id")),
            "title": _normalize_text(payload.get("title")),
            "scheduled_for": _normalize_text(payload.get("scheduled_for")),
            "timezone": _normalize_text(payload.get("timezone")) or "Europe/Berlin",
            "join_url": _normalize_text(payload.get("join_url")),
            "status": _normalize_text(payload.get("status")) or "scheduled",
            "confirmation_status": _normalize_text(payload.get("confirmation_status")) or "pending",
            "reminder_status": _normalize_text(payload.get("reminder_status")) or "not_scheduled",
            "reminder_sent_at": _normalize_text(payload.get("reminder_sent_at")),
            "notes": _normalize_text(payload.get("notes")),
        }

        if not interview_data["guest_name"]:
            raise WebInterfaceError("Interview guest name is required.")
        if not interview_data["scheduled_for"]:
            raise WebInterfaceError("Interview date and time are required.")

        interview_id, _ = self.database.upsert_interview(interview_data)
        interview = self.database.get_interview_by_id(interview_id)
        if not interview:
            raise WebInterfaceError("Interview could not be saved.")
        return interview

    def update_interview(self, interview_id: int, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Update an interview record."""
        current = self.database.get_interview_by_id(interview_id)
        if not current:
            raise WebInterfaceError("Interview not found.")

        interview_data = dict(current)
        interview_data.update(payload)
        saved = self.create_interview(interview_data)
        return saved

    def create_episode(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Create or update an episode record."""
        normalized_release_date = _normalize_text(payload.get("release_date"))
        normalized_release_status = _normalize_episode_release_status(
            normalized_release_date,
            _normalize_text(payload.get("release_status")),
        )
        episode_data = {
            "id": payload.get("id"),
            "guest_id": payload.get("guest_id"),
            "interview_id": payload.get("interview_id"),
            "guest_name": _normalize_text(payload.get("guest_name")),
            "guest_email": _normalize_text(payload.get("guest_email")),
            "website": _normalize_text(payload.get("website")),
            "episode_title": _normalize_text(payload.get("episode_title")),
            "topic": _normalize_text(payload.get("topic")),
            "category": _normalize_text(payload.get("category")),
            "interview_date": _normalize_text(payload.get("interview_date")),
            "recording_date": _normalize_text(payload.get("recording_date")),
            "release_date": normalized_release_date,
            "release_status": normalized_release_status,
            "production_status": _normalize_text(payload.get("production_status")) or "idea",
            "promotion_status": _normalize_text(payload.get("promotion_status")) or "unknown",
            "priority_score": payload.get("priority_score") or 0,
            "recommendation_reason": _normalize_text(payload.get("recommendation_reason")),
            "legacy_episode_number": _normalize_text(payload.get("legacy_episode_number")),
            "riverside_status": _normalize_text(payload.get("riverside_status")),
            "source_file_name": _normalize_text(payload.get("source_file_name")),
            "source_type": _normalize_text(payload.get("source_type")),
            "show_notes_url": _normalize_text(payload.get("show_notes_url")),
            "release_files_url": _normalize_text(payload.get("release_files_url")),
            "transcript_text": _normalize_text(payload.get("transcript_text")),
            "outreach_plan": _normalize_outreach_plan(payload.get("outreach_plan")),
            "notes": _normalize_text(payload.get("notes")),
        }

        if not episode_data["guest_name"]:
            raise WebInterfaceError("Episode guest name is required.")
        if not episode_data["episode_title"]:
            raise WebInterfaceError("Episode title is required.")

        episode_id, _ = self.database.upsert_episode(episode_data)
        episode = self.database.get_episode_by_id(episode_id)
        if not episode:
            raise WebInterfaceError("Episode could not be saved.")
        return episode

    def create_episode_from_interview(self, interview_id: int) -> Dict[str, Any]:
        """Create or refresh a planning episode from a completed interview."""
        interview = self.database.get_interview_by_id(interview_id)
        if not interview:
            raise WebInterfaceError("Interview not found.")

        guest_name = self._extract_guest_name_from_interview_title(
            interview.get("title"),
            interview.get("guest_name"),
        )
        if not guest_name:
            raise WebInterfaceError("This interview does not have a guest name yet.")

        linked_episode = self.database.get_episode_by_interview_id(interview_id)
        linked_guest = None
        guest_id = interview.get("guest_id")
        if guest_id:
            linked_guest = self.database.get_guest_by_id(int(guest_id))
        if not linked_guest:
            linked_guest = self.database.get_guest_by_name(guest_name)

        scheduled_for = self._parse_datetime(interview.get("scheduled_for"))
        scheduled_date = scheduled_for.date().isoformat() if scheduled_for else ""
        preserved_title = _normalize_text(linked_episode.get("episode_title")) if linked_episode else ""
        interview_title = _normalize_text(interview.get("title"))

        episode_payload = {
            "id": linked_episode.get("id") if linked_episode else None,
            "guest_id": (linked_guest or {}).get("id") or interview.get("guest_id"),
            "interview_id": interview_id,
            "guest_name": guest_name,
            "guest_email": _normalize_text(interview.get("guest_email"))
            or _normalize_text((linked_episode or {}).get("guest_email"))
            or _normalize_text((linked_guest or {}).get("email")),
            "website": _normalize_text((linked_episode or {}).get("website"))
            or _normalize_text((linked_guest or {}).get("website")),
            "episode_title": preserved_title or interview_title or guest_name,
            "topic": _normalize_text((linked_episode or {}).get("topic")),
            "category": _normalize_text((linked_episode or {}).get("category")),
            "interview_date": _normalize_text((linked_episode or {}).get("interview_date")) or scheduled_date,
            "recording_date": _normalize_text((linked_episode or {}).get("recording_date")) or scheduled_date,
            "release_date": _normalize_text((linked_episode or {}).get("release_date")),
            "release_status": _normalize_text((linked_episode or {}).get("release_status")) or "unplanned",
            "production_status": _normalize_text((linked_episode or {}).get("production_status")) or "recorded",
            "promotion_status": _normalize_text((linked_episode or {}).get("promotion_status")) or "needs_assets",
            "priority_score": (linked_episode or {}).get("priority_score") or 0,
            "recommendation_reason": _normalize_text((linked_episode or {}).get("recommendation_reason")),
            "legacy_episode_number": _normalize_text((linked_episode or {}).get("legacy_episode_number")),
            "riverside_status": _normalize_text((linked_episode or {}).get("riverside_status")),
            "source_file_name": _normalize_text((linked_episode or {}).get("source_file_name")),
            "source_type": _normalize_text((linked_episode or {}).get("source_type")) or "operations_handoff",
            "show_notes_url": _normalize_text((linked_episode or {}).get("show_notes_url")),
            "release_files_url": _normalize_text((linked_episode or {}).get("release_files_url")),
            "transcript_text": _normalize_text((linked_episode or {}).get("transcript_text")),
            "outreach_plan": _normalize_outreach_plan((linked_episode or {}).get("outreach_plan")),
            "notes": _normalize_text((linked_episode or {}).get("notes")) or _normalize_text(interview.get("notes")),
        }

        episode = self.create_episode(episode_payload)
        if not episode:
            raise WebInterfaceError("Planning episode could not be created.")
        normalized_episode = self._normalize_episode_record(episode)
        normalized_episode["handoff_ready_for_planning"] = True
        return normalized_episode

    def import_episode_file(self, filename: str, content: bytes) -> Dict[str, int]:
        """Import released-history or not-yet-released episode CSV data."""
        suffix = Path(filename).suffix.lower()
        if suffix != ".csv":
            raise WebInterfaceError("Please upload a CSV file for episode planning import.")

        episodes = parse_episode_import_csv(content, filename, reference=datetime.now())
        if not episodes:
            raise WebInterfaceError("No episode rows were found in that CSV file.")

        imported = 0
        updated = 0
        for episode_data in episodes:
            _, action = self.database.upsert_episode(episode_data)
            if action == "created":
                imported += 1
            else:
                updated += 1

        return {
            "imported": imported,
            "updated": updated,
            "total": imported + updated,
        }

    def sync_ask_mirror_talk_transcripts(
        self,
        *,
        overwrite_existing: bool = False,
        limit: int = 1000,
        search: str = "",
    ) -> Dict[str, Any]:
        """Enrich local planning records with transcripts from Ask Mirror Talk."""
        client = self._build_ask_mirror_talk_client()
        if client is None:
            raise WebInterfaceError("Ask Mirror Talk sync is not configured.")

        try:
            remote_episodes = client.export_episodes(limit=limit, search=search, include_transcript=True)
        except AskMirrorTalkClientError as exc:
            raise WebInterfaceError(str(exc)) from exc

        local_episodes = self.database.list_episodes()
        updated = 0
        matched = 0
        matched_by_title = 0
        matched_by_guest = 0
        skipped_ambiguous = 0
        skipped_existing = 0
        skipped_without_remote_transcript = 0
        skipped_without_title = 0
        updated_transcript = 0
        updated_title_only = 0
        updated_titles: list[str] = []
        ambiguous_matches: list[Dict[str, Any]] = []
        used_remote_ids: set[Any] = set()

        for episode in local_episodes:
            if not self._episode_match_key(episode.get("episode_title")) and not self._person_tokens(episode.get("guest_name")):
                skipped_without_title += 1
                continue

            candidates: list[tuple[int, str, Dict[str, Any]]] = []
            for remote_episode in remote_episodes:
                remote_id = remote_episode.get("id")
                if remote_id in used_remote_ids:
                    continue
                score, method = self._score_ask_episode_match(episode, remote_episode)
                if score > 0:
                    candidates.append((score, method, remote_episode))

            if not candidates:
                continue

            candidates.sort(key=lambda item: item[0], reverse=True)
            best_score, best_method, remote_episode = candidates[0]
            if len(candidates) > 1 and best_score < 1000 and (best_score - candidates[1][0]) < 100:
                skipped_ambiguous += 1
                ambiguous_matches.append(
                    {
                        "local_episode": {
                            "id": episode.get("id"),
                            "title": _normalize_text(episode.get("episode_title")),
                            "guest_name": _normalize_text(episode.get("guest_name")),
                            "release_date": _normalize_text(episode.get("release_date")),
                            "interview_date": _normalize_text(episode.get("interview_date")),
                        },
                        "candidates": [
                            self._summarize_ask_match_candidate(episode, candidate_remote, score, method)
                            for score, method, candidate_remote in candidates[:2]
                        ],
                    }
                )
                continue

            matched += 1
            if best_method == "title":
                matched_by_title += 1
            else:
                matched_by_guest += 1
            used_remote_ids.add(remote_episode.get("id"))

            transcript_text = _normalize_text(remote_episode.get("transcript_text"))
            remote_title = _normalize_text(remote_episode.get("title"))
            transcript_exists = bool(_normalize_text(episode.get("transcript_text")))
            should_update_transcript = bool(transcript_text) and (overwrite_existing or not transcript_exists)
            should_update_title = bool(remote_title) and remote_title != _normalize_text(episode.get("episode_title"))

            if not should_update_transcript and not should_update_title:
                if transcript_exists and transcript_text:
                    skipped_existing += 1
                elif not transcript_text and not should_update_title:
                    skipped_without_remote_transcript += 1
                continue

            payload: Dict[str, Any] = {
                "source_type": _normalize_text(episode.get("source_type")) or "ask_mirror_talk_sync",
                "source_file_name": _normalize_text(episode.get("source_file_name")) or "Ask Mirror Talk",
            }
            if should_update_transcript:
                payload["transcript_text"] = transcript_text
                updated_transcript += 1
            elif not transcript_text:
                skipped_without_remote_transcript += 1
            if should_update_title:
                payload["episode_title"] = remote_title
                if not should_update_transcript:
                    updated_title_only += 1

            self.update_episode(
                episode["id"],
                payload,
            )
            updated += 1
            updated_titles.append(remote_title or _normalize_text(episode.get("episode_title")))

        unmatched_local = max(len(local_episodes) - matched - skipped_without_title, 0)
        return {
            "remote_episodes": len(remote_episodes),
            "matched": matched,
            "matched_by_title": matched_by_title,
            "matched_by_guest": matched_by_guest,
            "updated": updated,
            "updated_transcript": updated_transcript,
            "updated_title_only": updated_title_only,
            "skipped_ambiguous": skipped_ambiguous,
            "skipped_existing": skipped_existing,
            "skipped_without_remote_transcript": skipped_without_remote_transcript,
            "skipped_without_title": skipped_without_title,
            "unmatched_local": unmatched_local,
            "updated_titles": updated_titles[:10],
            "ambiguous_matches": ambiguous_matches[:12],
        }

    def update_episode(self, episode_id: int, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Update an episode record."""
        current = self.database.get_episode_by_id(episode_id)
        if not current:
            raise WebInterfaceError("Episode not found.")

        episode_data = dict(current)
        episode_data.update(payload)
        saved = self.create_episode(episode_data)
        return saved

    def delete_episode(self, episode_id: int, confirm_label: str = "") -> Dict[str, Any]:
        """Delete an episode and return a small confirmation payload."""
        episode = self.database.get_episode_by_id(episode_id)
        if not episode:
            raise WebInterfaceError("Episode not found.")
        expected_label = _normalize_text(episode.get("episode_title")) or _normalize_text(episode.get("guest_name"))
        if expected_label and _normalize_text(confirm_label) != expected_label:
            raise WebInterfaceError(
                f'Type "{episode.get("episode_title") or episode.get("guest_name")}" to delete this episode.'
            )
        self.database.delete_episode(episode_id)
        return {"deleted": True, "id": episode_id}

    def get_due_weekly_reminders(self, *, reference: Optional[datetime] = None) -> list[Dict[str, Any]]:
        """Return interviews due for a weekly confirmation reminder."""
        reference = reference or datetime.now()

        candidates: list[Dict[str, Any]] = []
        interviews = self._sort_interviews_by_upcoming_priority(
            self.database.list_interviews(),
            reference=reference,
        )

        for interview in interviews:
            scheduled_for = self._parse_datetime(interview.get("scheduled_for"))
            if not scheduled_for:
                continue
            comparison_reference = reference
            if scheduled_for.tzinfo is not None and comparison_reference.tzinfo is None:
                comparison_reference = comparison_reference.replace(tzinfo=scheduled_for.tzinfo)
            elif scheduled_for.tzinfo is None and comparison_reference.tzinfo is not None:
                comparison_reference = comparison_reference.astimezone(timezone.utc).replace(tzinfo=None)

            week_start = comparison_reference - timedelta(days=comparison_reference.weekday())
            week_start = week_start.replace(hour=0, minute=0, second=0, microsecond=0)
            week_end = week_start + timedelta(days=7)
            if not (week_start <= scheduled_for < week_end):
                continue
            if _normalize_text(interview.get("status")).lower() == "cancelled":
                continue
            if _normalize_text(interview.get("confirmation_status")).lower() in {"declined", "reschedule_requested"}:
                continue
            if (interview.get("reminder_status") or "").strip().lower() == "sent":
                continue
            if not (interview.get("guest_email") or "").strip():
                continue
            candidates.append(interview)

        return candidates

    def _sort_interviews_by_upcoming_priority(
        self,
        interviews: list[Dict[str, Any]],
        *,
        reference: Optional[datetime] = None,
    ) -> list[Dict[str, Any]]:
        """Show the nearest upcoming interview first, then keep past interviews below."""
        reference = reference or datetime.now()

        def sort_key(interview: Dict[str, Any]) -> tuple[Any, ...]:
            scheduled_for = self._parse_datetime(interview.get("scheduled_for"))
            if not scheduled_for:
                return (2, datetime.max, -int(interview.get("id") or 0))

            comparison_reference = self._align_reference_datetime(reference, scheduled_for)
            if scheduled_for >= comparison_reference:
                return (0, scheduled_for, int(interview.get("id") or 0))

            return (1, -scheduled_for.timestamp(), -int(interview.get("id") or 0))

        return sorted(interviews, key=sort_key)

    def preview_interview_reminder(self, interview_id: int) -> Dict[str, Any]:
        """Return the reminder email template for an interview."""
        interview = self.database.get_interview_by_id(interview_id)
        if not interview:
            raise WebInterfaceError("Interview not found.")

        scheduled_for = self._parse_datetime(interview.get("scheduled_for"))
        if not scheduled_for:
            raise WebInterfaceError("Interview date is invalid or missing.")

        guest_name = _normalize_text(interview.get("guest_name")) or "Guest"
        timezone_label = _normalize_text(interview.get("timezone")) or "CET"
        join_url = _normalize_text(interview.get("join_url"))

        email_manager = self._build_email_manager()
        template = email_manager.get_interview_reminder_template(
            guest_name=guest_name,
            scheduled_for=scheduled_for,
            timezone_label=timezone_label,
            join_url=join_url,
        )
        return {
            "interview": self._serialize_interview_reminder(interview),
            "subject": template["subject"],
            "body": template["body"],
        }

    def preview_interview_appreciation(self, interview_id: int) -> Dict[str, Any]:
        """Return the post-interview appreciation email template."""
        interview = self.database.get_interview_by_id(interview_id)
        if not interview:
            raise WebInterfaceError("Interview not found.")

        guest_name = _normalize_text(interview.get("guest_name")) or "Guest"
        email_manager = self._build_email_manager()
        template = email_manager.get_post_interview_appreciation_template(guest_name=guest_name)
        return {
            "interview": self._serialize_interview_reminder(interview),
            "subject": template["subject"],
            "body": template["body"],
        }

    def send_interview_reminder(self, interview_id: int, subject: str = "", body: str = "") -> Dict[str, Any]:
        """Send a weekly confirmation reminder for an interview and log it."""
        interview = self.database.get_interview_by_id(interview_id)
        if not interview:
            raise WebInterfaceError("Interview not found.")

        guest_email = _normalize_text(interview.get("guest_email"))
        if not guest_email:
            raise WebInterfaceError("This interview does not have a guest email.")

        email_manager = self._build_email_manager()
        if not email_manager.is_configured():
            raise WebInterfaceError("Dashboard email is not configured on the server.")

        preview = self.preview_interview_reminder(interview_id)
        resolved_subject = subject.strip() or preview["subject"]
        resolved_body = body.strip() or preview["body"]

        sent = email_manager.send_email(guest_email, resolved_subject, resolved_body)
        if not sent:
            error_detail = (email_manager.last_error or "").strip()
            if error_detail:
                raise WebInterfaceError(f"The reminder email could not be sent: {error_detail}")
            raise WebInterfaceError("The reminder email could not be sent.")

        provider = "resend" if email_manager.resend_api_key else "smtp"
        self.database.log_reminder(
            interview_id=interview_id,
            reminder_type="weekly_confirmation",
            sent_to=guest_email,
            status="sent",
            provider=provider,
            notes=resolved_subject,
        )
        updated = self.database.get_interview_by_id(interview_id)
        if not updated:
            raise WebInterfaceError("Interview not found after reminder send.")
        return self._serialize_interview_reminder(updated)

    def send_due_weekly_reminders(self, *, reference: Optional[datetime] = None, dry_run: bool = False) -> Dict[str, Any]:
        """Send reminders for all due interviews in the current week."""
        due_interviews = self.get_due_weekly_reminders(reference=reference)
        if dry_run:
            return {
                "dry_run": True,
                "count": len(due_interviews),
                "interviews": [self._serialize_interview_reminder(interview) for interview in due_interviews],
            }

        sent = []
        errors = []

        for interview in due_interviews:
            try:
                sent_interview = self.send_interview_reminder(interview["id"])
                sent.append(sent_interview)
            except WebInterfaceError as exc:
                errors.append({"interview_id": interview["id"], "guest_name": interview.get("guest_name"), "error": str(exc)})

        return {
            "dry_run": False,
            "sent": sent,
            "errors": errors,
            "count": len(sent),
        }

    def send_interview_appreciation(self, interview_id: int, subject: str = "", body: str = "") -> Dict[str, Any]:
        """Send a thank-you email after an interview."""
        interview = self.database.get_interview_by_id(interview_id)
        if not interview:
            raise WebInterfaceError("Interview not found.")

        guest_email = _normalize_text(interview.get("guest_email"))
        if not guest_email:
            raise WebInterfaceError("This interview does not have a guest email.")

        email_manager = self._build_email_manager()
        if not email_manager.is_configured():
            raise WebInterfaceError("Dashboard email is not configured on the server.")

        preview = self.preview_interview_appreciation(interview_id)
        resolved_subject = subject.strip() or preview["subject"]
        resolved_body = body.strip() or preview["body"]

        sent = email_manager.send_email(guest_email, resolved_subject, resolved_body)
        if not sent:
            error_detail = (email_manager.last_error or "").strip()
            if error_detail:
                raise WebInterfaceError(f"The appreciation email could not be sent: {error_detail}")
            raise WebInterfaceError("The appreciation email could not be sent.")

        provider = "resend" if email_manager.resend_api_key else "smtp"
        self.database.log_interview_email(
            interview_id=interview_id,
            email_type="post_interview_appreciation",
            sent_to=guest_email,
            status="sent",
            provider=provider,
            notes=resolved_subject,
        )
        refreshed = self.database.get_interview_by_id(interview_id)
        if not refreshed:
            raise WebInterfaceError("Interview not found after appreciation email send.")
        return self._serialize_interview_reminder(refreshed)

    def preview_episode_appreciation(self, episode_id: int) -> Dict[str, Any]:
        """Return the post-recording appreciation email template from an episode record."""
        episode = self.database.get_episode_by_id(episode_id)
        if not episode:
            raise WebInterfaceError("Episode not found.")

        guest_name = _normalize_text(episode.get("guest_name")) or "Guest"
        email_manager = self._build_email_manager()
        template = email_manager.get_post_interview_appreciation_template(guest_name=guest_name)
        return {
            "episode": self._normalize_episode_record(episode),
            "subject": template["subject"],
            "body": template["body"],
        }

    def send_episode_appreciation(self, episode_id: int, subject: str = "", body: str = "") -> Dict[str, Any]:
        """Send a thank-you email from an episode record after recording."""
        episode = self.database.get_episode_by_id(episode_id)
        if not episode:
            raise WebInterfaceError("Episode not found.")

        guest_email = _normalize_text(episode.get("guest_email"))
        if not guest_email:
            raise WebInterfaceError("This episode does not have a guest email.")

        email_manager = self._build_email_manager()
        if not email_manager.is_configured():
            raise WebInterfaceError("Dashboard email is not configured on the server.")

        preview = self.preview_episode_appreciation(episode_id)
        resolved_subject = subject.strip() or preview["subject"]
        resolved_body = body.strip() or preview["body"]

        sent = email_manager.send_email(guest_email, resolved_subject, resolved_body)
        if not sent:
            error_detail = (email_manager.last_error or "").strip()
            if error_detail:
                raise WebInterfaceError(f"The appreciation email could not be sent: {error_detail}")
            raise WebInterfaceError("The appreciation email could not be sent.")

        provider = "resend" if email_manager.resend_api_key else "smtp"
        linked_interview_id = episode.get("interview_id")
        if linked_interview_id:
            self.database.log_interview_email(
                interview_id=int(linked_interview_id),
                email_type="post_interview_appreciation",
                sent_to=guest_email,
                status="sent",
                provider=provider,
                notes=resolved_subject,
            )
        refreshed = self.database.get_episode_by_id(episode_id)
        if not refreshed:
            raise WebInterfaceError("Episode not found after appreciation email send.")
        return self._normalize_episode_record(refreshed)

    def preview_episode_release_email(self, episode_id: int) -> Dict[str, Any]:
        """Return the released-episode follow-up email template from an episode record."""
        episode = self.database.get_episode_by_id(episode_id)
        if not episode:
            raise WebInterfaceError("Episode not found.")

        guest_name = _normalize_text(episode.get("guest_name")) or "Guest"
        show_notes_url = _normalize_text(episode.get("show_notes_url")) or "[Add show notes link]"
        files_url = _normalize_text(episode.get("release_files_url")) or "[Add files link]"
        email_manager = self._build_email_manager()
        template = email_manager.get_released_episode_template(
            guest_name=guest_name,
            show_notes_url=show_notes_url,
            files_url=files_url,
        )
        return {
            "episode": self._normalize_episode_record(episode),
            "subject": template["subject"],
            "body": template["body"],
        }

    def send_episode_release_email(self, episode_id: int, subject: str = "", body: str = "") -> Dict[str, Any]:
        """Send the released-episode follow-up email from an episode record."""
        episode = self.database.get_episode_by_id(episode_id)
        if not episode:
            raise WebInterfaceError("Episode not found.")

        guest_email = _normalize_text(episode.get("guest_email"))
        if not guest_email:
            raise WebInterfaceError("This episode does not have a guest email.")
        if not _normalize_text(episode.get("show_notes_url")):
            raise WebInterfaceError("Add the show notes link before sending the release email.")
        if not _normalize_text(episode.get("release_files_url")):
            raise WebInterfaceError("Add the files link before sending the release email.")

        email_manager = self._build_email_manager()
        if not email_manager.is_configured():
            raise WebInterfaceError("Dashboard email is not configured on the server.")

        preview = self.preview_episode_release_email(episode_id)
        resolved_subject = subject.strip() or preview["subject"]
        resolved_body = body.strip() or preview["body"]

        sent = email_manager.send_email(guest_email, resolved_subject, resolved_body)
        if not sent:
            error_detail = (email_manager.last_error or "").strip()
            if error_detail:
                raise WebInterfaceError(f"The release email could not be sent: {error_detail}")
            raise WebInterfaceError("The release email could not be sent.")

        provider = "resend" if email_manager.resend_api_key else "smtp"
        linked_interview_id = episode.get("interview_id")
        if linked_interview_id:
            self.database.log_interview_email(
                interview_id=int(linked_interview_id),
                email_type="released_episode_follow_up",
                sent_to=guest_email,
                status="sent",
                provider=provider,
                notes=resolved_subject,
            )
        refreshed = self.database.get_episode_by_id(episode_id)
        if not refreshed:
            raise WebInterfaceError("Episode not found after release email send.")
        return self._normalize_episode_record(refreshed)

    def sync_google_calendar_interviews(
        self,
        *,
        days_ahead: int = DEFAULT_GOOGLE_CALENDAR_SYNC_DAYS_AHEAD,
        reference: Optional[datetime] = None,
        query: str = "",
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        """Sync upcoming Google Calendar interview events into the interview tracker."""
        client = self._build_google_calendar_client()
        if client is None:
            raise WebInterfaceError("Google Calendar sync is not configured on the server.")

        effective_query = query.strip() or os.environ.get(GOOGLE_CALENDAR_QUERY_ENV_VAR, "").strip()

        try:
            events = client.list_upcoming_events(days_ahead=days_ahead, reference=reference, query=effective_query)
        except GoogleCalendarSyncError as exc:
            raise WebInterfaceError(str(exc)) from exc

        normalized = [client.normalize_event(event) for event in events]
        if dry_run:
            return {
                "dry_run": True,
                "count": len(normalized),
                "interviews": [self._serialize_interview_reminder(item) for item in normalized],
            }

        synced = []
        for event_data in normalized:
            interview_id, action = self.database.upsert_interview(event_data)
            interview = self.database.get_interview_by_id(interview_id)
            if interview:
                serialized = self._serialize_interview_reminder(interview)
                serialized["sync_action"] = action
                synced.append(serialized)

        return {
            "dry_run": False,
            "count": len(synced),
            "interviews": synced,
        }

    def push_interview_to_google_calendar(self, interview_id: int) -> Dict[str, Any]:
        """Push a linked interview record back to its Google Calendar event."""
        interview = self.database.get_interview_by_id(interview_id)
        if not interview:
            raise WebInterfaceError("Interview not found.")
        if not _normalize_text(interview.get("calendar_event_id")):
            raise WebInterfaceError("This interview is not linked to a Google Calendar event.")

        client = self._build_google_calendar_client()
        if client is None:
            raise WebInterfaceError("Google Calendar sync is not configured on the server.")

        try:
            updated_event = client.update_event_from_interview(interview)
        except GoogleCalendarSyncError as exc:
            raise WebInterfaceError(str(exc)) from exc

        updates = {
            "event_updated_at": updated_event.get("updated", interview.get("event_updated_at")),
            "last_synced_at": datetime.now().astimezone().isoformat(),
            "calendar_source": interview.get("calendar_source") or "google_calendar",
        }
        self.database.update_interview(interview_id, updates)
        refreshed = self.database.get_interview_by_id(interview_id)
        if not refreshed:
            raise WebInterfaceError("Interview not found after Google Calendar update.")
        return self._serialize_interview_reminder(refreshed)

    def remove_interview_from_google_calendar(self, interview_id: int) -> Dict[str, Any]:
        """Delete a linked Google Calendar event and mark the local interview as cancelled."""
        interview = self.database.get_interview_by_id(interview_id)
        if not interview:
            raise WebInterfaceError("Interview not found.")
        event_id = _normalize_text(interview.get("calendar_event_id"))
        if not event_id:
            raise WebInterfaceError("This interview is not linked to a Google Calendar event.")

        client = self._build_google_calendar_client()
        if client is None:
            raise WebInterfaceError("Google Calendar sync is not configured on the server.")

        try:
            client.delete_event(event_id)
        except GoogleCalendarSyncError as exc:
            raise WebInterfaceError(str(exc)) from exc

        updates = {
            "status": "cancelled",
            "confirmation_status": "declined" if _normalize_text(interview.get("confirmation_status")).lower() == "pending" else interview.get("confirmation_status"),
            "last_synced_at": datetime.now().astimezone().isoformat(),
            "notes": "\n".join(
                part
                for part in [
                    _normalize_text(interview.get("notes")),
                    "Removed from Google Calendar.",
                ]
                if part
            ),
        }
        self.database.update_interview(interview_id, updates)
        refreshed = self.database.get_interview_by_id(interview_id)
        if not refreshed:
            raise WebInterfaceError("Interview not found after Google Calendar removal.")
        return self._serialize_interview_reminder(refreshed)

    @staticmethod
    def _parse_datetime(value: Any) -> Optional[datetime]:
        """Parse a stored interview datetime."""
        normalized = _normalize_text(value)
        if not normalized:
            return None

        try:
            return datetime.fromisoformat(normalized.replace("Z", "+00:00"))
        except ValueError:
            try:
                return datetime.strptime(normalized, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                return None

    def _serialize_interview_reminder(self, interview: Dict[str, Any]) -> Dict[str, Any]:
        """Return reminder-friendly interview data with formatted schedule info."""
        serialized = dict(interview)
        scheduled_for = self._parse_datetime(interview.get("scheduled_for"))
        serialized["scheduled_for_display"] = (
            scheduled_for.strftime("%A %d %B %Y at %H:%M") if scheduled_for else _normalize_text(interview.get("scheduled_for"))
        )
        linked_episode = None
        interview_id = interview.get("id")
        if interview_id:
            linked_episode = self.database.get_episode_by_interview_id(int(interview_id))
        serialized["planning_episode_id"] = linked_episode.get("id") if linked_episode else None
        serialized["planning_episode_title"] = linked_episode.get("episode_title") if linked_episode else ""
        return serialized

    @staticmethod
    def _align_reference_datetime(reference: datetime, scheduled_for: datetime) -> datetime:
        """Align the comparison reference to the interview datetime awareness."""
        if scheduled_for.tzinfo is not None and reference.tzinfo is None:
            return reference.replace(tzinfo=scheduled_for.tzinfo)
        if scheduled_for.tzinfo is None and reference.tzinfo is not None:
            return reference.astimezone().replace(tzinfo=None)
        return reference

    def _build_google_calendar_client(self) -> Optional[GoogleCalendarSyncClient]:
        """Build the Google Calendar client from environment configuration."""
        client_id = os.environ.get(GOOGLE_CLIENT_ID_ENV_VAR, "").strip()
        client_secret = os.environ.get(GOOGLE_CLIENT_SECRET_ENV_VAR, "").strip()
        refresh_token = os.environ.get(GOOGLE_REFRESH_TOKEN_ENV_VAR, "").strip()
        calendar_id = os.environ.get(GOOGLE_CALENDAR_ID_ENV_VAR, "").strip()
        timezone_name = os.environ.get(GOOGLE_CALENDAR_TIMEZONE_ENV_VAR, "Europe/Berlin").strip() or "Europe/Berlin"

        if not all([client_id, client_secret, refresh_token, calendar_id]):
            return None

        return GoogleCalendarSyncClient(
            client_id=client_id,
            client_secret=client_secret,
            refresh_token=refresh_token,
            calendar_id=calendar_id,
            default_timezone=timezone_name,
        )

    @staticmethod
    def _build_ask_mirror_talk_client() -> Optional[AskMirrorTalkClient]:
        """Build the Ask Mirror Talk client from environment configuration."""
        base_url = os.environ.get(ASK_MIRROR_TALK_BASE_URL_ENV_VAR, "").strip()
        username = os.environ.get(ASK_MIRROR_TALK_USERNAME_ENV_VAR, "").strip()
        password = os.environ.get(ASK_MIRROR_TALK_PASSWORD_ENV_VAR, "").strip()
        if not all([base_url, username, password]):
            return None
        return AskMirrorTalkClient(base_url=base_url, username=username, password=password)

    @staticmethod
    def _build_openai_scheduling_copilot() -> Optional[OpenAISchedulingCopilot]:
        """Build the optional OpenAI scheduling copilot from environment configuration."""
        api_key = os.environ.get(OPENAI_API_KEY_ENV_VAR, "").strip()
        model = os.environ.get(OPENAI_MODEL_ENV_VAR, "").strip() or "gpt-5"
        if not api_key:
            return None
        timeout_raw = os.environ.get(OPENAI_TIMEOUT_ENV_VAR, "12").strip() or "12"
        try:
            timeout_seconds = max(3, min(30, int(timeout_raw)))
        except ValueError:
            timeout_seconds = 12
        return OpenAISchedulingCopilot(api_key=api_key, model=model, timeout_seconds=timeout_seconds)

    def _build_email_manager(self) -> EmailManager:
        """Build an email manager from environment configuration for the hosted dashboard."""
        email_manager = EmailManager()
        email_manager.smtp_server = None
        email_manager.smtp_port = None
        email_manager.username = None
        email_manager.password = None
        email_manager.from_email = None
        email_manager.from_name = None
        email_manager.resend_api_key = None
        resend_api_key = os.environ.get(EMAIL_RESEND_API_KEY_ENV_VAR, "").strip()
        smtp_server = os.environ.get(EMAIL_SMTP_SERVER_ENV_VAR, "").strip()
        smtp_username = os.environ.get(EMAIL_USERNAME_ENV_VAR, "").strip()
        smtp_password = os.environ.get(EMAIL_PASSWORD_ENV_VAR, "").strip()
        from_email = os.environ.get(EMAIL_FROM_ENV_VAR, "").strip()
        from_name = os.environ.get(EMAIL_FROM_NAME_ENV_VAR, "Mirror Talk Podcast").strip()
        cc_email = os.environ.get(EMAIL_CC_ENV_VAR, "podcast.mirrortalk@gmail.com").strip()

        if resend_api_key and from_email:
            email_manager.configure_resend(
                api_key=resend_api_key,
                from_email=from_email,
                from_name=from_name,
                cc_email=cc_email,
            )
            return email_manager

        if smtp_server and smtp_username and smtp_password and from_email:
            smtp_port_raw = os.environ.get(EMAIL_SMTP_PORT_ENV_VAR, "587").strip() or "587"
            try:
                smtp_port = int(smtp_port_raw)
            except ValueError as exc:
                raise WebInterfaceError("Server email port is invalid.") from exc

            email_manager.configure_smtp(
                smtp_server=smtp_server,
                smtp_port=smtp_port,
                username=smtp_username,
                password=smtp_password,
                from_email=from_email,
                from_name=from_name,
                cc_email=cc_email,
            )

        return email_manager

    def _send_intake_confirmation_email(self, guest: Dict[str, Any]) -> None:
        """Best-effort confirmation email for public intake submissions."""
        guest_email = _normalize_text(guest.get("email"))
        if not guest_email:
            return

        email_manager = self._build_email_manager()
        if not email_manager.is_configured():
            return

        guest_name = _normalize_text(guest.get("full_name")) or "there"
        try:
            email_manager.send_intake_confirmation_email(guest_name, guest_email)
        except Exception:
            return


class GuestWebRequestHandler(BaseHTTPRequestHandler):
    """HTTP request handler for the direct web interface."""

    service: GuestWebService

    def do_OPTIONS(self) -> None:  # noqa: N802
        origin = self.headers.get("Origin")
        self.send_response(HTTPStatus.NO_CONTENT)
        self._send_cors_headers(origin)
        self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type, X-Api-Token")
        self.send_header("Access-Control-Max-Age", "86400")
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        request_path = urlsplit(self.path).path

        if request_path in {"/", "/intake", "/intake.html"}:
            self._serve_static("intake.html")
            return

        if request_path in {"/dashboard", "/index.html"}:
            if not self._is_authorized_dashboard_request():
                self._send_basic_auth_challenge()
                return
            self._serve_static("index.html")
            return

        if request_path in {"/operations", "/operations.html"}:
            if not self._is_authorized_dashboard_request():
                self._send_basic_auth_challenge()
                return
            self._serve_static("operations.html")
            return

        if request_path in {"/planning", "/planning.html"}:
            if not self._is_authorized_dashboard_request():
                self._send_basic_auth_challenge()
                return
            self._serve_static("planning.html")
            return

        if request_path.startswith("/static/"):
            relative_path = request_path.removeprefix("/static/")
            self._serve_static(relative_path)
            return

        if request_path == "/api/guests":
            if not self._is_authorized_dashboard_request():
                self._send_json(HTTPStatus.UNAUTHORIZED, {"error": "Unauthorized dashboard request"})
                return
            self._send_json(HTTPStatus.OK, self.service.list_guests())
            return

        if request_path == "/api/export":
            if not self._is_authorized_dashboard_request():
                self._send_json(HTTPStatus.UNAUTHORIZED, {"error": "Unauthorized dashboard request"})
                return
            self._send_csv(
                HTTPStatus.OK,
                self.service.export_guests_csv(),
                filename="mirror-talk-guests.csv",
            )
            return

        if request_path == "/api/exports":
            self._send_json(HTTPStatus.METHOD_NOT_ALLOWED, {"error": "Use POST for flexible exports"})
            return

        if request_path == "/api/operations":
            if not self._is_authorized_dashboard_request():
                self._send_json(HTTPStatus.UNAUTHORIZED, {"error": "Unauthorized dashboard request"})
                return
            self._send_json(HTTPStatus.OK, self.service.list_operations())
            return

        if request_path == "/api/planning":
            if not self._is_authorized_dashboard_request():
                self._send_json(HTTPStatus.UNAUTHORIZED, {"error": "Unauthorized dashboard request"})
                return
            self._send_json(HTTPStatus.OK, self.service.list_planning())
            return

        if request_path == "/api/planning/ai-copilot":
            if not self._is_authorized_dashboard_request():
                self._send_json(HTTPStatus.UNAUTHORIZED, {"error": "Unauthorized dashboard request"})
                return
            self._send_json(HTTPStatus.OK, self.service.list_planning_ai_copilot())
            return

        if request_path == "/api/google-calendar/sync":
            if not self._is_authorized_dashboard_request():
                self._send_json(HTTPStatus.UNAUTHORIZED, {"error": "Unauthorized dashboard request"})
                return

            try:
                result = self.service.sync_google_calendar_interviews(dry_run=True)
            except WebInterfaceError as exc:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                return

            self._send_json(HTTPStatus.OK, result)
            return

        if request_path.startswith("/api/interviews/") and request_path.endswith("/reminder-template"):
            if not self._is_authorized_dashboard_request():
                self._send_json(HTTPStatus.UNAUTHORIZED, {"error": "Unauthorized dashboard request"})
                return

            interview_id = self._extract_record_id(request_path[: -len("/reminder-template")], "/api/interviews/")
            if interview_id is None:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": "Invalid interview id"})
                return

            try:
                payload = self.service.preview_interview_reminder(interview_id)
            except WebInterfaceError as exc:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                return

            self._send_json(HTTPStatus.OK, payload)
            return

        if request_path.startswith("/api/interviews/") and request_path.endswith("/appreciation-template"):
            if not self._is_authorized_dashboard_request():
                self._send_json(HTTPStatus.UNAUTHORIZED, {"error": "Unauthorized dashboard request"})
                return

            interview_id = self._extract_record_id(request_path[: -len("/appreciation-template")], "/api/interviews/")
            if interview_id is None:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": "Invalid interview id"})
                return

            try:
                payload = self.service.preview_interview_appreciation(interview_id)
            except WebInterfaceError as exc:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                return

            self._send_json(HTTPStatus.OK, payload)
            return

        if request_path.startswith("/api/episodes/") and request_path.endswith("/appreciation-template"):
            if not self._is_authorized_dashboard_request():
                self._send_json(HTTPStatus.UNAUTHORIZED, {"error": "Unauthorized dashboard request"})
                return

            episode_id = self._extract_record_id(request_path[: -len("/appreciation-template")], "/api/episodes/")
            if episode_id is None:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": "Invalid episode id"})
                return

            try:
                payload = self.service.preview_episode_appreciation(episode_id)
            except WebInterfaceError as exc:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                return

            self._send_json(HTTPStatus.OK, payload)
            return

        if request_path.startswith("/api/episodes/") and request_path.endswith("/release-email-template"):
            if not self._is_authorized_dashboard_request():
                self._send_json(HTTPStatus.UNAUTHORIZED, {"error": "Unauthorized dashboard request"})
                return

            episode_id = self._extract_record_id(request_path[: -len("/release-email-template")], "/api/episodes/")
            if episode_id is None:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": "Invalid episode id"})
                return

            try:
                payload = self.service.preview_episode_release_email(episode_id)
            except WebInterfaceError as exc:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                return

            self._send_json(HTTPStatus.OK, payload)
            return

        self._send_json(HTTPStatus.NOT_FOUND, {"error": "Not found"})

    def do_POST(self) -> None:  # noqa: N802
        if self.path == "/api/guests":
            if not self._is_authorized_dashboard_request():
                self._send_json(HTTPStatus.UNAUTHORIZED, {"error": "Unauthorized dashboard request"})
                return
            payload = self._read_json_payload()
            try:
                guest = self.service.create_guest(payload)
            except WebInterfaceError as exc:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                return

            self._send_json(HTTPStatus.CREATED, guest)
            return

        if self.path == "/api/intake":
            if not self._is_authorized_request():
                self._send_json(HTTPStatus.UNAUTHORIZED, {"error": "Unauthorized intake request"})
                return

            payload = self._read_json_payload()
            try:
                guest = self.service.create_intake_submission(payload)
            except WebInterfaceError as exc:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                return

            self._send_json(
                HTTPStatus.CREATED,
                {
                    "message": "Thank you for applying. Your submission has been received.",
                    "guest": guest,
                },
            )
            return

        if self.path == "/api/import":
            if not self._is_authorized_dashboard_request():
                self._send_json(HTTPStatus.UNAUTHORIZED, {"error": "Unauthorized dashboard request"})
                return

            try:
                fields, files = self._read_multipart_form_data()
                uploaded_file = files.get("file")
                if not uploaded_file:
                    raise WebInterfaceError("Please choose a CSV or Excel file to import.")

                result = self.service.import_guest_file(
                    uploaded_file["filename"],
                    uploaded_file["content"],
                    encoding=fields.get("encoding", "utf-8"),
                )
            except WebInterfaceError as exc:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                return

            self._send_json(HTTPStatus.OK, result)
            return

        if self.path == "/api/interviews":
            if not self._is_authorized_dashboard_request():
                self._send_json(HTTPStatus.UNAUTHORIZED, {"error": "Unauthorized dashboard request"})
                return

            payload = self._read_json_payload()
            try:
                interview = self.service.create_interview(payload)
            except WebInterfaceError as exc:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                return

            self._send_json(HTTPStatus.CREATED, interview)
            return

        if self.path == "/api/exports":
            if not self._is_authorized_dashboard_request():
                self._send_json(HTTPStatus.UNAUTHORIZED, {"error": "Unauthorized dashboard request"})
                return

            payload = self._read_json_payload()
            try:
                content, filename, content_type = self.service.export_records(
                    payload.get("list_name", ""),
                    payload.get("fields", []),
                    payload.get("format", "csv"),
                )
            except WebInterfaceError as exc:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                return

            self._send_file(HTTPStatus.OK, content, filename=filename, content_type=content_type)
            return

        if self.path == "/api/episodes":
            if not self._is_authorized_dashboard_request():
                self._send_json(HTTPStatus.UNAUTHORIZED, {"error": "Unauthorized dashboard request"})
                return

            payload = self._read_json_payload()
            try:
                episode = self.service.create_episode(payload)
            except WebInterfaceError as exc:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                return

            self._send_json(HTTPStatus.CREATED, episode)
            return

        if self.path == "/api/episodes/import":
            if not self._is_authorized_dashboard_request():
                self._send_json(HTTPStatus.UNAUTHORIZED, {"error": "Unauthorized dashboard request"})
                return

            try:
                _, files = self._read_multipart_form_data()
                uploaded_file = files.get("file")
                if not uploaded_file:
                    raise WebInterfaceError("Please choose an episode CSV file to import.")

                result = self.service.import_episode_file(
                    uploaded_file["filename"],
                    uploaded_file["content"],
                )
            except WebInterfaceError as exc:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                return

            self._send_json(HTTPStatus.OK, result)
            return

        if self.path == "/api/guests/research-bulk":
            if not self._is_authorized_dashboard_request():
                self._send_json(HTTPStatus.UNAUTHORIZED, {"error": "Unauthorized dashboard request"})
                return

            payload = self._read_json_payload()
            try:
                result = self.service.bulk_research_guests(int(payload.get("limit", BULK_GUEST_RESEARCH_BATCH_SIZE) or BULK_GUEST_RESEARCH_BATCH_SIZE))
            except WebInterfaceError as exc:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                return

            self._send_json(HTTPStatus.OK, result)
            return

        if self.path == "/api/ask-mirror-talk/sync":
            if not self._is_authorized_dashboard_request():
                self._send_json(HTTPStatus.UNAUTHORIZED, {"error": "Unauthorized dashboard request"})
                return

            payload = self._read_json_payload()
            try:
                result = self.service.sync_ask_mirror_talk_transcripts(
                    overwrite_existing=bool(payload.get("overwrite_existing")),
                    limit=int(payload.get("limit", 1000) or 1000),
                    search=_normalize_text(payload.get("search")),
                )
            except WebInterfaceError as exc:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                return

            self._send_json(HTTPStatus.OK, result)
            return

        if self.path == "/api/reminders/send-weekly":
            if not self._is_authorized_dashboard_request():
                self._send_json(HTTPStatus.UNAUTHORIZED, {"error": "Unauthorized dashboard request"})
                return

            payload = self._read_json_payload()
            reference_value = _normalize_text(payload.get("reference"))
            dry_run = bool(payload.get("dry_run"))
            reference = self.service._parse_datetime(reference_value) if reference_value else None

            try:
                result = self.service.send_due_weekly_reminders(reference=reference, dry_run=dry_run)
            except WebInterfaceError as exc:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                return

            self._send_json(HTTPStatus.OK, result)
            return

        if self.path == "/api/google-calendar/sync":
            if not self._is_authorized_dashboard_request():
                self._send_json(HTTPStatus.UNAUTHORIZED, {"error": "Unauthorized dashboard request"})
                return

            payload = self._read_json_payload()
            reference_value = _normalize_text(payload.get("reference"))
            reference = self.service._parse_datetime(reference_value) if reference_value else None
            configured_days_ahead = os.environ.get(
                GOOGLE_CALENDAR_DAYS_AHEAD_ENV_VAR,
                str(DEFAULT_GOOGLE_CALENDAR_SYNC_DAYS_AHEAD),
            ).strip() or str(DEFAULT_GOOGLE_CALENDAR_SYNC_DAYS_AHEAD)
            days_ahead = int(payload.get("days_ahead", configured_days_ahead) or configured_days_ahead)
            query = _normalize_text(payload.get("query"))
            dry_run = bool(payload.get("dry_run"))

            try:
                result = self.service.sync_google_calendar_interviews(
                    days_ahead=days_ahead,
                    reference=reference,
                    query=query,
                    dry_run=dry_run,
                )
            except WebInterfaceError as exc:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                return

            self._send_json(HTTPStatus.OK, result)
            return

        if self.path.startswith("/api/guests/") and self.path.endswith("/status"):
            if not self._is_authorized_dashboard_request():
                self._send_json(HTTPStatus.UNAUTHORIZED, {"error": "Unauthorized dashboard request"})
                return
            guest_id = self._extract_guest_id(self.path, suffix="/status")
            if guest_id is None:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": "Invalid guest id"})
                return

            payload = self._read_json_payload()
            try:
                guest = self.service.update_guest_status(
                    guest_id,
                    payload.get("status", ""),
                    payload.get("skip_reason", ""),
                )
            except WebInterfaceError as exc:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                return

            self._send_json(HTTPStatus.OK, guest)
            return

        if self.path.startswith("/api/guests/") and self.path.endswith("/research"):
            if not self._is_authorized_dashboard_request():
                self._send_json(HTTPStatus.UNAUTHORIZED, {"error": "Unauthorized dashboard request"})
                return
            guest_id = self._extract_guest_id(self.path, suffix="/research")
            if guest_id is None:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": "Invalid guest id"})
                return

            try:
                guest = self.service.research_guest(guest_id)
            except WebInterfaceError as exc:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                return

            self._send_json(HTTPStatus.OK, guest)
            return

        if self.path.startswith("/api/guests/") and self.path.endswith("/research-with-search"):
            if not self._is_authorized_dashboard_request():
                self._send_json(HTTPStatus.UNAUTHORIZED, {"error": "Unauthorized dashboard request"})
                return
            guest_id = self._extract_guest_id(self.path, suffix="/research-with-search")
            if guest_id is None:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": "Invalid guest id"})
                return

            try:
                guest = self.service.retry_guest_research_with_search(guest_id)
            except WebInterfaceError as exc:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                return

            self._send_json(HTTPStatus.OK, guest)
            return

        if self.path.startswith("/api/guests/") and not self.path.endswith("/email-decision") and not self.path.endswith("/email-template"):
            if not self._is_authorized_dashboard_request():
                self._send_json(HTTPStatus.UNAUTHORIZED, {"error": "Unauthorized dashboard request"})
                return
            guest_id = self._extract_guest_id(self.path)
            if guest_id is None:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": "Invalid guest id"})
                return

            payload = self._read_json_payload()
            try:
                guest = self.service.update_guest(guest_id, payload)
            except WebInterfaceError as exc:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                return

            self._send_json(HTTPStatus.OK, guest)
            return

        if self.path.startswith("/api/guests/") and self.path.endswith("/email-decision"):
            if not self._is_authorized_dashboard_request():
                self._send_json(HTTPStatus.UNAUTHORIZED, {"error": "Unauthorized dashboard request"})
                return

            guest_id = self._extract_guest_id(self.path, suffix="/email-decision")
            if guest_id is None:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": "Invalid guest id"})
                return

            payload = self._read_json_payload()
            try:
                guest = self.service.send_guest_decision_email_message(
                    guest_id,
                    payload.get("status", ""),
                    payload.get("subject", ""),
                    payload.get("body", ""),
                    payload.get("custom_message", ""),
                )
            except WebInterfaceError as exc:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                return

            self._send_json(HTTPStatus.OK, guest)
            return

        if self.path.startswith("/api/guests/") and self.path.endswith("/email-template"):
            if not self._is_authorized_dashboard_request():
                self._send_json(HTTPStatus.UNAUTHORIZED, {"error": "Unauthorized dashboard request"})
                return

            guest_id = self._extract_guest_id(self.path, suffix="/email-template")
            if guest_id is None:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": "Invalid guest id"})
                return

            payload = self._read_json_payload()
            try:
                template = self.service.get_guest_decision_email_template(guest_id, payload.get("status", ""))
            except WebInterfaceError as exc:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                return

            self._send_json(HTTPStatus.OK, template)
            return

        if self.path.startswith("/api/interviews/"):
            if not self._is_authorized_dashboard_request():
                self._send_json(HTTPStatus.UNAUTHORIZED, {"error": "Unauthorized dashboard request"})
                return

            if self.path.endswith("/move-to-planning"):
                interview_id = self._extract_record_id(self.path[: -len("/move-to-planning")], "/api/interviews/")
                if interview_id is None:
                    self._send_json(HTTPStatus.BAD_REQUEST, {"error": "Invalid interview id"})
                    return

                try:
                    episode = self.service.create_episode_from_interview(interview_id)
                except WebInterfaceError as exc:
                    self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                    return

                self._send_json(HTTPStatus.OK, episode)
                return

            if self.path.endswith("/push-to-calendar"):
                interview_id = self._extract_record_id(self.path[: -len("/push-to-calendar")], "/api/interviews/")
                if interview_id is None:
                    self._send_json(HTTPStatus.BAD_REQUEST, {"error": "Invalid interview id"})
                    return

                try:
                    interview = self.service.push_interview_to_google_calendar(interview_id)
                except WebInterfaceError as exc:
                    self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                    return

                self._send_json(HTTPStatus.OK, interview)
                return

            if self.path.endswith("/remove-from-calendar"):
                interview_id = self._extract_record_id(self.path[: -len("/remove-from-calendar")], "/api/interviews/")
                if interview_id is None:
                    self._send_json(HTTPStatus.BAD_REQUEST, {"error": "Invalid interview id"})
                    return

                try:
                    interview = self.service.remove_interview_from_google_calendar(interview_id)
                except WebInterfaceError as exc:
                    self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                    return

                self._send_json(HTTPStatus.OK, interview)
                return

            if self.path.endswith("/send-reminder"):
                interview_id = self._extract_record_id(self.path[: -len("/send-reminder")], "/api/interviews/")
                if interview_id is None:
                    self._send_json(HTTPStatus.BAD_REQUEST, {"error": "Invalid interview id"})
                    return

                payload = self._read_json_payload()
                try:
                    interview = self.service.send_interview_reminder(
                        interview_id,
                        payload.get("subject", ""),
                        payload.get("body", ""),
                    )
                except WebInterfaceError as exc:
                    self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                    return

                self._send_json(HTTPStatus.OK, interview)
                return

            if self.path.endswith("/send-appreciation"):
                interview_id = self._extract_record_id(self.path[: -len("/send-appreciation")], "/api/interviews/")
                if interview_id is None:
                    self._send_json(HTTPStatus.BAD_REQUEST, {"error": "Invalid interview id"})
                    return

                payload = self._read_json_payload()
                try:
                    interview = self.service.send_interview_appreciation(
                        interview_id,
                        payload.get("subject", ""),
                        payload.get("body", ""),
                    )
                except WebInterfaceError as exc:
                    self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                    return

                self._send_json(HTTPStatus.OK, interview)
                return

            interview_id = self._extract_record_id(self.path, "/api/interviews/")
            if interview_id is None:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": "Invalid interview id"})
                return

            payload = self._read_json_payload()
            try:
                interview = self.service.update_interview(interview_id, payload)
            except WebInterfaceError as exc:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                return

            self._send_json(HTTPStatus.OK, interview)
            return

        if self.path.startswith("/api/episodes/"):
            if not self._is_authorized_dashboard_request():
                self._send_json(HTTPStatus.UNAUTHORIZED, {"error": "Unauthorized dashboard request"})
                return

            if self.path.endswith("/send-release-email"):
                episode_id = self._extract_record_id(self.path[: -len("/send-release-email")], "/api/episodes/")
                if episode_id is None:
                    self._send_json(HTTPStatus.BAD_REQUEST, {"error": "Invalid episode id"})
                    return

                payload = self._read_json_payload()
                try:
                    episode = self.service.send_episode_release_email(
                        episode_id,
                        payload.get("subject", ""),
                        payload.get("body", ""),
                    )
                except WebInterfaceError as exc:
                    self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                    return

                self._send_json(HTTPStatus.OK, episode)
                return

            if self.path.endswith("/send-appreciation"):
                episode_id = self._extract_record_id(self.path[: -len("/send-appreciation")], "/api/episodes/")
                if episode_id is None:
                    self._send_json(HTTPStatus.BAD_REQUEST, {"error": "Invalid episode id"})
                    return

                payload = self._read_json_payload()
                try:
                    episode = self.service.send_episode_appreciation(
                        episode_id,
                        payload.get("subject", ""),
                        payload.get("body", ""),
                    )
                except WebInterfaceError as exc:
                    self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                    return

                self._send_json(HTTPStatus.OK, episode)
                return

            episode_id = self._extract_record_id(self.path, "/api/episodes/")
            if episode_id is None:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": "Invalid episode id"})
                return

            payload = self._read_json_payload()
            try:
                episode = self.service.update_episode(episode_id, payload)
            except WebInterfaceError as exc:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                return

            self._send_json(HTTPStatus.OK, episode)
            return

        self._send_json(HTTPStatus.NOT_FOUND, {"error": "Not found"})

    def do_DELETE(self) -> None:  # noqa: N802
        if self.path.startswith("/api/guests/"):
            if not self._is_authorized_dashboard_request():
                self._send_json(HTTPStatus.UNAUTHORIZED, {"error": "Unauthorized dashboard request"})
                return
            guest_id = self._extract_guest_id(self.path)
            if guest_id is None:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": "Invalid guest id"})
                return

            payload = self._read_json_payload()
            try:
                result = self.service.delete_guest(guest_id, payload.get("confirm_name", ""))
            except WebInterfaceError as exc:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                return

            self._send_json(HTTPStatus.OK, result)
            return

        if self.path.startswith("/api/interviews/"):
            if not self._is_authorized_dashboard_request():
                self._send_json(HTTPStatus.UNAUTHORIZED, {"error": "Unauthorized dashboard request"})
                return
            interview_id = self._extract_record_id(self.path, "/api/interviews/")
            if interview_id is None:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": "Invalid interview id"})
                return
            payload = self._read_json_payload()
            try:
                self._send_json(HTTPStatus.OK, self.service.delete_interview(interview_id, payload.get("confirm_label", "")))
            except WebInterfaceError as exc:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            return

        if self.path.startswith("/api/episodes/"):
            if not self._is_authorized_dashboard_request():
                self._send_json(HTTPStatus.UNAUTHORIZED, {"error": "Unauthorized dashboard request"})
                return
            episode_id = self._extract_record_id(self.path, "/api/episodes/")
            if episode_id is None:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": "Invalid episode id"})
                return
            payload = self._read_json_payload()
            try:
                self._send_json(HTTPStatus.OK, self.service.delete_episode(episode_id, payload.get("confirm_label", "")))
            except WebInterfaceError as exc:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            return

        self._send_json(HTTPStatus.NOT_FOUND, {"error": "Not found"})

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
        """Silence default request logging."""

    def _read_json_payload(self) -> Dict[str, Any]:
        content_length = int(self.headers.get("Content-Length", "0"))
        if content_length == 0:
            return {}

        raw_data = self.rfile.read(content_length)
        return json.loads(raw_data.decode("utf-8"))

    def _read_multipart_form_data(self) -> tuple[Dict[str, str], Dict[str, Dict[str, Any]]]:
        content_length = int(self.headers.get("Content-Length", "0"))
        if content_length == 0:
            raise WebInterfaceError("Upload request was empty.")

        content_type = self.headers.get("Content-Type", "")
        if "multipart/form-data" not in content_type:
            raise WebInterfaceError("Upload request must use multipart form data.")

        raw_data = self.rfile.read(content_length)
        message = BytesParser(policy=default).parsebytes(
            f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n".encode("utf-8") + raw_data
        )

        fields: Dict[str, str] = {}
        files: Dict[str, Dict[str, Any]] = {}

        for part in message.iter_parts():
            name = part.get_param("name", header="content-disposition")
            if not name:
                continue

            filename = part.get_filename()
            payload = part.get_payload(decode=True) or b""

            if filename:
                files[name] = {
                    "filename": filename,
                    "content": payload,
                    "content_type": part.get_content_type(),
                }
                continue

            charset = part.get_content_charset() or "utf-8"
            fields[name] = payload.decode(charset, errors="replace").strip()

        return fields, files

    def _serve_static(self, relative_path: str) -> None:
        safe_path = (STATIC_DIR / relative_path).resolve()
        if not safe_path.is_file() or STATIC_DIR.resolve() not in safe_path.parents and safe_path != STATIC_DIR.resolve():
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "Static file not found"})
            return

        content_type, _ = mimetypes.guess_type(safe_path.name)
        self.send_response(HTTPStatus.OK)
        self._send_cors_headers(self.headers.get("Origin"))
        self.send_header("Content-Type", content_type or "application/octet-stream")
        self.end_headers()
        self.wfile.write(safe_path.read_bytes())

    def _send_json(self, status: HTTPStatus, payload: Dict[str, Any]) -> None:
        response = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self._send_cors_headers(self.headers.get("Origin"))
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(response)))
        self.end_headers()
        try:
            self.wfile.write(response)
        except (BrokenPipeError, ConnectionResetError):
            return

    def _send_csv(self, status: HTTPStatus, payload: str, filename: str) -> None:
        response = payload.encode("utf-8")
        self.send_response(status)
        self._send_cors_headers(self.headers.get("Origin"))
        self.send_header("Content-Type", "text/csv; charset=utf-8")
        self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.send_header("Content-Length", str(len(response)))
        self.end_headers()
        self.wfile.write(response)

    def _send_file(self, status: HTTPStatus, payload: bytes, filename: str, content_type: str) -> None:
        self.send_response(status)
        self._send_cors_headers(self.headers.get("Origin"))
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _send_cors_headers(self, origin: Optional[str]) -> None:
        if origin in ALLOWED_ORIGINS:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")

    def _is_authorized_request(self) -> bool:
        configured_token = os.environ.get(API_TOKEN_ENV_VAR, "").strip()
        if not configured_token:
            return True

        request_token = self.headers.get("X-Api-Token", "").strip()
        if request_token and request_token == configured_token:
            return True

        return self._is_trusted_public_intake_request()

    def _is_trusted_public_intake_request(self) -> bool:
        """Allow public intake submissions from the known website and this live service origin."""
        origin = (self.headers.get("Origin") or "").strip()
        referer = (self.headers.get("Referer") or "").strip()

        trusted_origins = set(ALLOWED_ORIGINS)
        current_origin = self._current_service_origin()
        if current_origin:
            trusted_origins.add(current_origin)

        if origin and origin in trusted_origins:
            return True

        if referer:
            referer_origin = self._extract_origin(referer)
            if referer_origin and referer_origin in trusted_origins:
                return True

        return False

    def _current_service_origin(self) -> str:
        """Infer the current public service origin from forwarded or host headers."""
        forwarded_proto = (self.headers.get("X-Forwarded-Proto") or "").strip()
        proto = forwarded_proto or ("https" if self.server.server_port == 443 else "http")

        forwarded_host = (self.headers.get("X-Forwarded-Host") or "").strip()
        host = forwarded_host or (self.headers.get("Host") or "").strip()
        if not host:
            return ""

        return f"{proto}://{host}"

    @staticmethod
    def _extract_origin(url: str) -> str:
        """Return a normalized origin string from a full URL."""
        try:
            parts = urlsplit(url)
        except Exception:
            return ""

        if not parts.scheme or not parts.netloc:
            return ""

        return f"{parts.scheme}://{parts.netloc}"

    def _is_authorized_dashboard_request(self) -> bool:
        configured_username = os.environ.get(DASHBOARD_USERNAME_ENV_VAR, "").strip()
        configured_password = os.environ.get(DASHBOARD_PASSWORD_ENV_VAR, "").strip()

        if not configured_username and not configured_password:
            return True

        auth_header = self.headers.get("Authorization", "")
        if not auth_header.startswith("Basic "):
            return False

        try:
            encoded_credentials = auth_header.split(" ", 1)[1]
            decoded_credentials = b64decode(encoded_credentials).decode("utf-8")
            username, password = decoded_credentials.split(":", 1)
        except Exception:
            return False

        return username == configured_username and password == configured_password

    def _send_basic_auth_challenge(self) -> None:
        self.send_response(HTTPStatus.UNAUTHORIZED)
        self.send_header("WWW-Authenticate", 'Basic realm="Mirror Talk Dashboard"')
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"Authentication required")

    @staticmethod
    def _extract_guest_id(path: str, suffix: str = "") -> Optional[int]:
        prefix = "/api/guests/"
        trimmed = path.removeprefix(prefix)
        if suffix and trimmed.endswith(suffix):
            trimmed = trimmed[: -len(suffix)]
        trimmed = trimmed.strip("/")

        try:
            return int(trimmed)
        except ValueError:
            return None

    @staticmethod
    def _extract_record_id(path: str, prefix: str) -> Optional[int]:
        trimmed = path.removeprefix(prefix).strip("/")
        try:
            return int(trimmed)
        except ValueError:
            return None


def create_web_server(
    host: str = "127.0.0.1",
    port: int = 8601,
    db_path: Path | str = DEFAULT_DB_PATH,
) -> ThreadingHTTPServer:
    """Create the HTTP server for the direct web interface."""
    server = ThreadingHTTPServer((host, port), GuestWebRequestHandler)
    GuestWebRequestHandler.service = GuestWebService(Path(db_path))
    return server


def run_web_interface(
    host: str = "127.0.0.1",
    port: int = 8601,
    db_path: Path | str = DEFAULT_DB_PATH,
    open_browser: bool = True,
) -> None:
    """Run the direct web interface server."""
    server = create_web_server(host=host, port=port, db_path=db_path)
    url = f"http://{host}:{port}"
    print(f"🌐 Starting direct web interface at {url}")
    print(f"🗄️ Using database: {Path(db_path)}")

    if open_browser:
        webbrowser.open(url)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n🛑 Shutting down web interface...")
    finally:
        server.server_close()
