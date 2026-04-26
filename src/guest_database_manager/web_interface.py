"""Lightweight web interface with a static frontend and JSON API."""

from __future__ import annotations

import json
import mimetypes
import os
import re
import secrets
import sqlite3
import tempfile
import webbrowser
from csv import DictWriter
from base64 import b64decode
from time import monotonic
from email.parser import BytesParser
from email.policy import default
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass, field
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO, StringIO
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import parse_qsl, urlencode, urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

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
AGENCY_REFERRAL_SOURCE_NAME = "Agency Referral"
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
BOOKING_BASE_URL_ENV_VAR = "MIRROR_TALK_BOOKING_BASE_URL"
PUBLIC_INTAKE_URL_ENV_VAR = "MIRROR_TALK_PUBLIC_INTAKE_URL"
BOOKING_TIMEZONE_ENV_VAR = "MIRROR_TALK_BOOKING_TIMEZONE"
BOOKING_SLOT_WEEKDAYS_ENV_VAR = "MIRROR_TALK_BOOKING_SLOT_WEEKDAYS"
BOOKING_SLOT_TIMES_ENV_VAR = "MIRROR_TALK_BOOKING_SLOT_TIMES"
BOOKING_DAYS_AHEAD_ENV_VAR = "MIRROR_TALK_BOOKING_DAYS_AHEAD"
BOOKING_MONTHS_AHEAD_ENV_VAR = "MIRROR_TALK_BOOKING_MONTHS_AHEAD"
BOOKING_BUFFER_MINUTES_ENV_VAR = "MIRROR_TALK_BOOKING_BUFFER_MINUTES"
BOOKING_MIN_NOTICE_HOURS_ENV_VAR = "MIRROR_TALK_BOOKING_MIN_NOTICE_HOURS"
BOOKING_DURATION_MINUTES_ENV_VAR = "MIRROR_TALK_BOOKING_DURATION_MINUTES"
BOOKING_JOIN_URL_ENV_VAR = "MIRROR_TALK_BOOKING_JOIN_URL"
DEFAULT_GOOGLE_CALENDAR_SYNC_DAYS_AHEAD = 365
AI_AUTORESEARCH_CANDIDATE_LIMIT = 12
BULK_GUEST_RESEARCH_BATCH_SIZE = 25
BOOKING_DEFAULT_WEEKDAYS = ("TU", "WE", "TH")
BOOKING_DEFAULT_TIMES = ("17:00", "19:00")
BOOKING_DEFAULT_DAYS_AHEAD = 45
BOOKING_DEFAULT_MONTHS_AHEAD = 3
BOOKING_DEFAULT_BUFFER_MINUTES = 15
BOOKING_DEFAULT_MIN_NOTICE_HOURS = 24
BOOKING_DEFAULT_DURATION_MINUTES = 60
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


def _website_host_for_identity(value: Any) -> str:
    """Return a normalized website host for duplicate-intent checks."""
    text = _normalize_text(value)
    if not text:
        return ""
    normalized = text if "://" in text else f"https://{text}"
    try:
        host = urlsplit(normalized).netloc.casefold()
    except ValueError:
        return ""
    return re.sub(r"^www\.", "", host)


def _parse_original_data(value: Any) -> Dict[str, Any]:
    """Parse stored original_data JSON into a dictionary."""
    if isinstance(value, dict):
        return value
    text = _normalize_text(value)
    if not text:
        return {}
    try:
        parsed = json.loads(text)
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _build_submission_meta(guest: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Build a structured submission summary for dashboard review."""
    source_name = _normalize_text(guest.get("original_file_name"))
    original_data = _parse_original_data(guest.get("original_data"))

    if source_name == AGENCY_REFERRAL_SOURCE_NAME:
        agency_name = _normalize_text(original_data.get("agency_name"))
        agency_email = _normalize_text(original_data.get("agency_email"))
        guest_name = _normalize_text(
            original_data.get("represented_guest_name") or guest.get("full_name")
        )
        guest_email = _normalize_text(
            original_data.get("represented_guest_email") or guest.get("email")
        )
        return {
            "mode": "agency_referral",
            "label": "Agency referral",
            "guest_name": guest_name,
            "guest_email": guest_email,
            "agency_name": agency_name,
            "agency_email": agency_email,
            "personal_application_required": True,
            "personal_application_status": (
                "Awaiting the guest's own application."
                if source_name == AGENCY_REFERRAL_SOURCE_NAME
                else ""
            ),
        }

    application_role = _normalize_text(original_data.get("application_role")).lower()
    self_attestation = _normalize_text(original_data.get("self_attestation")).lower()
    if source_name == INTAKE_SOURCE_NAME or application_role == "self":
        return {
            "mode": "self_application",
            "label": "Self application",
            "guest_name": _normalize_text(guest.get("full_name")),
            "guest_email": _normalize_text(guest.get("email")),
            "agency_name": "",
            "agency_email": "",
            "personal_application_required": True,
            "personal_application_status": (
                "Confirmed by the guest."
                if self_attestation == "yes"
                else "Submitted directly by the guest."
            ),
        }

    return None


def serialize_guest(guest: Dict[str, Any]) -> Dict[str, Any]:
    """Convert database rows into frontend-friendly JSON."""
    serialized = dict(guest)
    serialized["is_processed"] = bool(serialized.get("is_processed"))
    serialized["submission_meta"] = _build_submission_meta(serialized)
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


def _parse_priority_score(value: Any) -> float:
    """Parse a priority score into a stable float."""
    if value in ("", None):
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _clamp_priority_score(value: float) -> float:
    """Keep editable priority scores inside the 0-10 form range."""
    return max(0.0, min(10.0, float(value)))


@dataclass
class GuestWebService:
    """Service layer for the direct web interface."""

    db_path: Path
    _payload_cache: Dict[str, tuple[float, Dict[str, Any]]] = field(default_factory=dict, init=False, repr=False)

    def __post_init__(self) -> None:
        self.database = GuestDatabase(self.db_path)

    @staticmethod
    def _payload_cache_ttl(cache_key: str) -> float:
        """Return a short cache TTL for expensive dashboard payloads."""
        if cache_key == "planning_ai_copilot":
            return 0.0
        return 3.0

    def _get_cached_payload(self, cache_key: str) -> Optional[Dict[str, Any]]:
        """Return a recent cached payload when it is still fresh enough to reuse."""
        ttl_seconds = self._payload_cache_ttl(cache_key)
        if ttl_seconds <= 0:
            return None
        cached = self._payload_cache.get(cache_key)
        if not cached:
            return None
        cached_at, payload = cached
        if (monotonic() - cached_at) > ttl_seconds:
            self._payload_cache.pop(cache_key, None)
            return None
        return dict(payload)

    def _store_cached_payload(self, cache_key: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Remember a payload briefly so repeated first-load refreshes are lighter."""
        ttl_seconds = self._payload_cache_ttl(cache_key)
        if ttl_seconds > 0:
            self._payload_cache[cache_key] = (monotonic(), dict(payload))
        return payload

    def _invalidate_payload_cache(self, *cache_keys: str) -> None:
        """Drop stale cached page payloads after writes mutate dashboard state."""
        if not cache_keys:
            self._payload_cache.clear()
            return
        for cache_key in cache_keys:
            self._payload_cache.pop(cache_key, None)

    def _next_legacy_episode_number(self, current_episode_id: Any = None) -> str:
        """Return the next numeric legacy episode number when one can be inferred."""
        current_id = str(current_episode_id or "").strip()
        episodes = [
            episode
            for episode in self.database.list_episodes()
            if not current_id or str(episode.get("id") or "").strip() != current_id
        ]

        all_numbers = {
            int(text)
            for text in (_normalize_text(item.get("legacy_episode_number")) for item in episodes)
            if text.isdigit()
        }

        def extract_max(rows: list[Dict[str, Any]]) -> int | None:
            scoped_numbers = [
                int(text)
                for text in (_normalize_text(item.get("legacy_episode_number")) for item in rows)
                if text.isdigit()
            ]
            if not scoped_numbers:
                return None
            return max(scoped_numbers)

        anchored_rows = [
            episode
            for episode in episodes
            if _normalize_text(episode.get("release_status")).lower() in {"released", "scheduled"}
            and _normalize_text(episode.get("release_date"))
        ]
        max_number = extract_max(anchored_rows)
        if max_number is None:
            max_number = extract_max(episodes)
        candidate = (max_number or 0) + 1
        while candidate in all_numbers:
            candidate += 1
        return str(candidate)

    def _suggest_episode_priority_score(self, payload: Dict[str, Any]) -> float:
        """Return a lightweight default priority score for planning records."""
        release_status = _normalize_text(payload.get("release_status")).lower()
        production_status = _normalize_text(payload.get("production_status")).lower()
        promotion_status = _normalize_text(payload.get("promotion_status")).lower()

        if release_status == "released" or production_status == "released":
            return 10.0
        if release_status == "scheduled":
            return 8.0
        if production_status == "ready" and promotion_status == "ready":
            return 8.0
        if production_status == "ready":
            return 7.0
        if production_status == "editing":
            return 6.0
        if production_status == "recorded":
            return 5.0
        return 3.0

    def list_guests(self) -> Dict[str, Any]:
        """Return all guests for the frontend."""
        cached = self._get_cached_payload("guests")
        if cached is not None:
            return cached
        episodes = [self._normalize_episode_record(episode) for episode in self.database.list_episodes()]
        interviews = self.database.list_interviews()
        guests = [serialize_guest(guest) for guest in enrich_guests_with_recommendations(self.database.get_all_guests())]
        for guest in guests:
            guest["promotion_profile"] = self._build_guest_promotion_profile(guest)
            guest["planning_summary"] = self._build_guest_planning_summary(guest, episodes)
            guest["workflow_context"] = self._build_guest_workflow_context(guest, interviews, episodes)
            guest["dashboard_processed"] = bool(guest["workflow_context"].get("dashboard_processed"))
            guest["dashboard_status"] = guest["workflow_context"].get("dashboard_status") or (
                "processed" if guest.get("is_processed") else "unprocessed"
            )
            guest["dashboard_status_label"] = guest["workflow_context"].get("dashboard_status_label") or (
                guest.get("email_status") or ("processed" if guest.get("is_processed") else "unprocessed")
            )
        processed_count = sum(1 for guest in guests if guest.get("dashboard_processed"))
        return self._store_cached_payload("guests", {
            "guests": guests,
            "stats": {
                "total": len(guests),
                "processed": processed_count,
                "unprocessed": len(guests) - processed_count,
            },
            "email_stats": self.database.get_email_stats(),
            "recommendation_stats": build_guest_recommendation_stats(guests),
            "email_enabled": self._build_email_manager().is_configured(),
        })

    def list_operations(self) -> Dict[str, Any]:
        """Return the current interview and episode operations data."""
        cached = self._get_cached_payload("operations")
        if cached is not None:
            return cached
        episodes = [self._normalize_episode_record(episode) for episode in self.database.list_episodes()]
        raw_interviews = self.database.list_interviews()
        interviews = [
            self._serialize_interview_reminder(interview)
            for interview in self._sort_interviews_by_upcoming_priority(raw_interviews)
        ]
        reminder_candidates = [self._serialize_interview_reminder(candidate) for candidate in self.get_due_weekly_reminders()]
        return self._store_cached_payload("operations", {
            "stats": self.database.get_operations_stats(),
            "interviews": interviews,
            "reminder_candidates": reminder_candidates,
            "calendar_sync_enabled": self._build_google_calendar_client() is not None,
            "weekly_outreach": self._build_weekly_outreach_focus(episodes),
            "weekly_system": self._build_weekly_system_payload(),
            "booking_alerts": self._build_operations_alerts(raw_interviews),
        })

    def list_planning(self) -> Dict[str, Any]:
        """Return episode planning data separate from interview operations."""
        cached = self._get_cached_payload("planning")
        if cached is not None:
            return cached
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
        return self._store_cached_payload("planning", {
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
        })

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
                if not auto_research and not episode.get("guest_research"):
                    auto_research = self._auto_research_episode_profile(episode)
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

    def _episode_belongs_to_guest(self, episode: Dict[str, Any], guest: Dict[str, Any]) -> bool:
        """Return whether a planning episode likely belongs to a given guest."""
        guest_id = str(guest.get("id") or "").strip()
        episode_guest_id = str(episode.get("guest_id") or "").strip()
        if guest_id and episode_guest_id and guest_id == episode_guest_id:
            return True

        guest_email = _normalize_text(guest.get("email")).casefold()
        episode_email = _normalize_text(episode.get("guest_email")).casefold()
        if guest_email and episode_email and guest_email == episode_email:
            return True

        guest_host = self._website_host(guest.get("website"))
        episode_host = self._website_host(episode.get("website"))
        if guest_host and episode_host and guest_host == episode_host:
            return True

        return self._name_match_score(
            episode.get("guest_name"),
            guest.get("full_name") or guest.get("name"),
        ) >= 85

    def _interview_belongs_to_guest(self, interview: Dict[str, Any], guest: Dict[str, Any]) -> bool:
        """Return whether an interview record likely belongs to a given guest."""
        guest_id = str(guest.get("id") or "").strip()
        interview_guest_id = str(interview.get("guest_id") or "").strip()
        if guest_id and interview_guest_id and guest_id == interview_guest_id:
            return True

        guest_email = _normalize_text(guest.get("email")).casefold()
        interview_email = _normalize_text(interview.get("guest_email")).casefold()
        if guest_email and interview_email and guest_email == interview_email:
            return True

        return self._name_match_score(
            interview.get("guest_name") or interview.get("title"),
            guest.get("full_name") or guest.get("name"),
        ) >= 85

    def _build_guest_planning_summary(
        self,
        guest: Dict[str, Any],
        episodes: list[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        """Attach compact planning context to a dashboard guest card."""
        linked = [episode for episode in episodes if self._episode_belongs_to_guest(episode, guest)]
        if not linked:
            return None

        def sort_key(item: Dict[str, Any]) -> tuple[datetime, int]:
            release_date = self._parse_datetime_static(item.get("release_date"))
            interview_date = self._parse_datetime_static(item.get("interview_date"))
            recording_date = self._parse_datetime_static(item.get("recording_date"))
            best_date = release_date or interview_date or recording_date or datetime.min
            return best_date, int(item.get("id") or 0)

        linked_sorted = sorted(linked, key=sort_key, reverse=True)
        featured = linked_sorted[0]
        open_items = [
            item for item in linked
            if _normalize_text(item.get("release_status")).lower() not in {"released"}
        ]
        scheduled_items = [
            item for item in linked
            if _normalize_text(item.get("release_status")).lower() == "scheduled"
        ]
        next_scheduled = sorted(
            scheduled_items,
            key=lambda item: self._parse_datetime_static(item.get("release_date")) or datetime.max,
        )

        featured_title = _normalize_text(featured.get("episode_title")) or _normalize_text(featured.get("topic")) or "Untitled episode"
        featured_release_status = _normalize_text(featured.get("release_status")) or "unplanned"
        featured_production_status = _normalize_text(featured.get("production_status")) or "idea"
        featured_release_date = _normalize_text(featured.get("release_date"))

        summary_lines = [f"{len(linked)} linked episode{'s' if len(linked) != 1 else ''}"]
        if scheduled_items:
            summary_lines.append(
                f"{len(scheduled_items)} scheduled"
            )
        if open_items:
            summary_lines.append(
                f"{len(open_items)} still active in planning"
            )

        return {
            "episode_count": len(linked),
            "open_count": len(open_items),
            "scheduled_count": len(scheduled_items),
            "featured_episode_id": featured.get("id"),
            "featured_title": featured_title,
            "featured_release_status": featured_release_status,
            "featured_production_status": featured_production_status,
            "featured_release_date": featured_release_date,
            "next_scheduled_release_date": _normalize_text((next_scheduled[0] if next_scheduled else {}).get("release_date")),
            "summary_label": " · ".join(summary_lines),
        }

    def _build_guest_workflow_context(
        self,
        guest: Dict[str, Any],
        interviews: list[Dict[str, Any]],
        episodes: list[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Summarize whether a dashboard guest is already active beyond intake review."""
        linked_interviews = [item for item in interviews if self._interview_belongs_to_guest(item, guest)]
        linked_episodes = [item for item in episodes if self._episode_belongs_to_guest(item, guest)]
        reference = datetime.now(timezone.utc)

        def as_reference(value: Any) -> Optional[datetime]:
            parsed = self._parse_datetime_static(value)
            if not parsed:
                return None
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)

        future_interviews = 0
        past_interviews = 0
        for interview in linked_interviews:
            if _normalize_text(interview.get("status")).lower() == "cancelled":
                continue
            scheduled_for = as_reference(interview.get("scheduled_for"))
            if not scheduled_for:
                continue
            if scheduled_for >= reference:
                future_interviews += 1
            else:
                past_interviews += 1

        released_episodes = sum(
            1
            for episode in linked_episodes
            if _normalize_text(episode.get("release_status")).lower() == "released"
        )
        scheduled_episodes = sum(
            1
            for episode in linked_episodes
            if _normalize_text(episode.get("release_status")).lower() == "scheduled"
        )

        if _normalize_text(guest.get("email_status")):
            dashboard_status = _normalize_text(guest.get("email_status")).lower()
            dashboard_status_label = _normalize_text(guest.get("email_status"))
        elif released_episodes:
            dashboard_status = "released_episode"
            dashboard_status_label = "released episode"
        elif scheduled_episodes:
            dashboard_status = "scheduled_episode"
            dashboard_status_label = "scheduled episode"
        elif linked_episodes:
            dashboard_status = "in_planning"
            dashboard_status_label = "in planning"
        elif future_interviews:
            dashboard_status = "scheduled_interview"
            dashboard_status_label = "scheduled interview"
        elif past_interviews:
            dashboard_status = "interviewed"
            dashboard_status_label = "interviewed"
        elif guest.get("is_processed"):
            dashboard_status = "processed"
            dashboard_status_label = "processed"
        else:
            dashboard_status = "unprocessed"
            dashboard_status_label = "unprocessed"

        return {
            "interview_count": len(linked_interviews),
            "future_interview_count": future_interviews,
            "past_interview_count": past_interviews,
            "planning_episode_count": len(linked_episodes),
            "released_episode_count": released_episodes,
            "scheduled_episode_count": scheduled_episodes,
            "dashboard_processed": dashboard_status != "unprocessed",
            "dashboard_status": dashboard_status,
            "dashboard_status_label": dashboard_status_label,
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

    @staticmethod
    def _website_host(value: Any) -> str:
        text = _normalize_text(value)
        if not text:
            return ""
        first_chunk = re.split(r"[\s\r\n,;]+", text, maxsplit=1)[0].strip()
        if not first_chunk:
            return ""
        normalized = first_chunk if "://" in first_chunk else f"https://{first_chunk}"
        try:
            host = urlsplit(normalized).netloc.casefold()
        except ValueError:
            return ""
        return re.sub(r"^www\.", "", host)

    @staticmethod
    def _name_tokens(value: Any) -> list[str]:
        text = _normalize_text(value)
        if not text:
            return []
        tokens = re.findall(r"[a-z0-9]+", text)
        honorifics = {"mr", "mrs", "ms", "dr", "prof", "rev", "sir", "jr", "sr", "ii", "iii", "iv"}
        filtered = [token for token in tokens if token not in honorifics]
        return filtered

    def _name_match_score(self, episode_name: Any, guest_name: Any) -> int:
        episode_tokens = self._name_tokens(episode_name)
        guest_tokens = self._name_tokens(guest_name)
        if not episode_tokens or not guest_tokens:
            return 0
        if episode_tokens == guest_tokens:
            return 100

        episode_set = set(episode_tokens)
        guest_set = set(guest_tokens)
        overlap = episode_set & guest_set
        if not overlap:
            return 0

        first_episode = episode_tokens[0]
        first_guest = guest_tokens[0]
        last_episode = episode_tokens[-1]
        last_guest = guest_tokens[-1]

        if first_episode == first_guest and last_episode == last_guest:
            return 95
        if last_episode == last_guest and len(overlap) >= min(2, len(episode_set), len(guest_set)):
            return 90
        if episode_set <= guest_set and len(episode_set) >= 2:
            return 85
        if guest_set <= episode_set and len(guest_set) >= 2:
            return 85
        if last_episode == last_guest and len(overlap) >= 1 and len(episode_set) >= 2 and len(guest_set) >= 2:
            return 70
        return 0

    def _find_matching_guest(self, episode: Dict[str, Any], guests: list[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Find the best matching guest for an episode by stable identifiers, then safe name variants."""
        email_key = _normalize_text(episode.get("guest_email")).casefold()
        website_host = self._website_host(episode.get("website"))
        episode_name = episode.get("guest_name")

        for guest in guests:
            if email_key and _normalize_text(guest.get("email")).casefold() == email_key:
                return guest

        host_matches: list[Dict[str, Any]] = []
        for guest in guests:
            guest_host = self._website_host(guest.get("website"))
            if website_host and guest_host and guest_host == website_host:
                host_matches.append(guest)

        if len(host_matches) == 1:
            return host_matches[0]

        scored_matches: list[tuple[int, Dict[str, Any]]] = []
        for guest in guests:
            guest_name = guest.get("full_name") or guest.get("name")
            score = self._name_match_score(episode_name, guest_name)
            if score > 0:
                scored_matches.append((score, guest))

        if not scored_matches:
            return None

        scored_matches.sort(key=lambda item: (item[0], int(item[1].get("id") or 0)), reverse=True)
        best_score = scored_matches[0][0]
        best_matches = [guest for score, guest in scored_matches if score == best_score]
        if best_score >= 85 and len(best_matches) == 1:
            return best_matches[0]

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

    def _auto_research_episode_profile(self, episode: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Use the episode's own guest name and website as a direct research fallback."""
        if not _normalize_text(episode.get("guest_name")) or not _normalize_text(episode.get("website")):
            return None
        try:
            research = research_guest_from_public_web(
                {
                    "full_name": episode.get("guest_name"),
                    "email": episode.get("guest_email"),
                    "website": episode.get("website"),
                    "social_media_handles": "",
                    "social_handles": "",
                }
            )
        except ValueError:
            return None
        research["research_mode"] = "auto_episode"
        research["cache_status"] = "ready"
        return self._decorate_research_payload(research, research.get("updated_at"))

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
            guest_id = _normalize_text(interview.get("guest_id"))
            guest_name = _normalize_text(interview.get("guest_name"))
            guest_email = _normalize_text(interview.get("guest_email"))
            guest_key = (
                f"id:{guest_id}" if guest_id else f"name:{guest_name}" if guest_name else f"email:{guest_email}" if guest_email else ""
            )

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
            value = re.sub(
                r"^(?:soulful conversation|mirror talk|conversation|interview)\s+with\s+",
                "",
                value,
                flags=re.IGNORECASE,
            ).strip(" -,:")
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
        self._invalidate_payload_cache("guests", "planning", "planning_ai_copilot")
        guest = self.database.get_guest_by_id(guest_id)
        return serialize_guest(guest) if guest else {"id": guest_id}

    def _email_used_by_other_guest(self, email: str, guest_name: str) -> bool:
        """Return whether an email is already associated with another guest name."""
        normalized_email = _normalize_text(email).casefold()
        normalized_name = _normalize_text(guest_name).casefold()
        if not normalized_email or not normalized_name:
            return False
        for guest in self.database.get_all_guests():
            if _normalize_text(guest.get("email")).casefold() != normalized_email:
                continue
            existing_name = _normalize_text(guest.get("full_name") or guest.get("name")).casefold()
            if existing_name and existing_name != normalized_name:
                return True
        return False

    @staticmethod
    def _public_intake_link(full_name: str = "", email: str = "") -> str:
        """Return the guest-facing intake URL, optionally prefilled."""
        configured = os.environ.get(PUBLIC_INTAKE_URL_ENV_VAR, "").strip()
        if configured:
            base_url = configured
        else:
            booking_base = os.environ.get(BOOKING_BASE_URL_ENV_VAR, "").strip()
            if booking_base:
                normalized_booking_base = booking_base.rstrip("/")
                if normalized_booking_base.endswith("/book"):
                    base_url = f"{normalized_booking_base[:-len('/book')]}/intake"
                else:
                    base_url = f"{normalized_booking_base}/intake"
            else:
                base_url = "https://guest-processing-production.up.railway.app/intake"
        params = urlencode(
            {
                key: value
                for key, value in {
                    "full_name": full_name.strip(),
                    "email": email.strip(),
                }.items()
                if value
            }
        )
        if not params:
            return base_url
        separator = "&" if "?" in base_url else "?"
        return f"{base_url}{separator}{params}"

    def _create_agency_referral(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Create a soft agency referral and send the real intake link to the guest."""
        agency_name = _normalize_text(payload.get("agency_name"))
        agency_email = _normalize_text(payload.get("agency_email"))
        guest_name = _normalize_text(payload.get("represented_guest_name"))
        guest_email = _normalize_text(payload.get("represented_guest_email"))
        if not agency_name:
            raise WebInterfaceError("Please share the agency or representative name.")
        if not guest_name:
            raise WebInterfaceError("Please share the guest's full name.")
        if not guest_email or "@" not in guest_email:
            raise WebInterfaceError("Please share the guest's real email address so we can contact them directly.")

        referral_note = (
            f"Agency referral from {agency_name}"
            + (f" ({agency_email})" if agency_email else "")
            + ". Awaiting a personal intake submission from the guest."
        )
        guest = self.create_guest(
            {
                "application_role": "on_behalf",
                "agency_name": agency_name,
                "agency_email": agency_email,
                "represented_guest_name": guest_name,
                "represented_guest_email": guest_email,
                "full_name": guest_name,
                "email": guest_email,
                "additional_info": referral_note,
                "background": "Agency-introduced referral awaiting the guest's own application.",
                "profession": "",
                "passionate_topics": "",
                "message": "",
                "has_social_media": "",
            },
            source_name=AGENCY_REFERRAL_SOURCE_NAME,
        )
        self._send_guest_self_application_request_email(
            guest_name,
            guest_email,
            self._public_intake_link(guest_name, guest_email),
            agency_name,
        )
        response = dict(guest)
        response["submission_mode"] = "agency_referral"
        response["message"] = (
            f"Thank you. We’ve emailed {guest_name} their personal Mirror Talk application link so they can apply in their own voice."
        )
        return response

    def create_intake_submission(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Create a guest submission from the public intake questionnaire."""
        application_role = _normalize_text(payload.get("application_role")).lower()
        if application_role == "on_behalf":
            return self._create_agency_referral(payload)

        if application_role not in {"", "self"}:
            raise WebInterfaceError("Please choose whether you are applying for yourself or on behalf of someone else.")

        full_name = _normalize_text(payload.get("full_name"))
        email = _normalize_text(payload.get("email"))
        if application_role == "self" and _normalize_text(payload.get("self_attestation")).lower() != "yes":
            raise WebInterfaceError("Please confirm that you are the guest applying for yourself before submitting.")
        if self._email_used_by_other_guest(email, full_name):
            raise WebInterfaceError(
                "Please use the guest's own personal or professional email address. We noticed this email is already associated with a different guest."
            )
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
        self._invalidate_payload_cache("guests", "planning", "planning_ai_copilot")
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
            return email_manager.get_acceptance_template(
                guest_name,
                booking_url=self._booking_link_for_guest(guest_id),
            )

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
                sent = email_manager.send_acceptance_email(
                    guest_name,
                    guest_email,
                    custom_message,
                    booking_url=self._booking_link_for_guest(guest_id),
                )
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

        self._invalidate_payload_cache("guests", "planning", "planning_ai_copilot")
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
        self._invalidate_payload_cache("guests", "planning", "planning_ai_copilot")
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
        self._invalidate_payload_cache("guests", "planning", "planning_ai_copilot")
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
        self._invalidate_payload_cache("guests", "planning", "planning_ai_copilot")
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
        self._invalidate_payload_cache("guests", "planning", "planning_ai_copilot")
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

        if researched or errors:
            self._invalidate_payload_cache("guests", "planning", "planning_ai_copilot")
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
        self._invalidate_payload_cache("operations", "planning", "planning_ai_copilot")
        return {"deleted": True, "id": interview_id}

    def create_interview(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Create or update an interview record."""
        interview_data = {
            "id": payload.get("id"),
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

        try:
            interview_id, _ = self.database.upsert_interview(interview_data)
        except sqlite3.IntegrityError as exc:
            message = str(exc)
            if "interviews.calendar_event_id" in message:
                raise WebInterfaceError(
                    "This interview could not be saved because its Google Calendar event id is already linked to another interview record."
                ) from exc
            raise WebInterfaceError(f"This interview could not be saved: {message}") from exc
        except ValueError as exc:
            raise WebInterfaceError(str(exc)) from exc
        interview = self.database.get_interview_by_id(interview_id)
        if not interview:
            raise WebInterfaceError("Interview could not be saved.")
        self._invalidate_payload_cache("operations", "planning", "planning_ai_copilot")
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

    def _guest_from_booking_token(self, booking_token: str) -> Dict[str, Any]:
        """Fetch a guest by booking token and ensure the guest can still book."""
        normalized_token = _normalize_text(booking_token)
        if not normalized_token:
            raise WebInterfaceError("Booking link is missing or invalid.")
        guest = self.database.get_guest_by_booking_token(normalized_token)
        if not guest:
            raise WebInterfaceError("This booking link is not valid anymore.")
        email_status = _normalize_text(guest.get("email_status")).lower()
        if email_status != "accepted":
            raise WebInterfaceError("This guest is not currently eligible to book an interview.")
        return guest

    def _serialize_public_booking_interview(self, interview: Dict[str, Any]) -> Dict[str, Any]:
        """Return a small safe booking summary for the guest-facing page."""
        return {
            "id": interview.get("id"),
            "scheduled_for": interview.get("scheduled_for"),
            "timezone": interview.get("timezone"),
            "join_url": interview.get("join_url"),
            "status": interview.get("status"),
            "confirmation_status": interview.get("confirmation_status"),
            "title": interview.get("title"),
        }

    def _normalize_booking_datetime(self, value: Any) -> Optional[datetime]:
        """Normalize a booking-related datetime into UTC for safe comparisons."""
        parsed = self._parse_datetime(value)
        if not parsed:
            return None
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    def _find_future_interview_for_guest(self, guest: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Return the next still-active interview for a guest, if one exists."""
        guest_id = str(guest.get("id") or "").strip()
        guest_email = _normalize_text(guest.get("email")).casefold()
        reference = datetime.now(timezone.utc)
        for interview in self.database.list_interviews():
            scheduled_for = self._normalize_booking_datetime(interview.get("scheduled_for"))
            if not scheduled_for or scheduled_for < reference:
                continue
            status = _normalize_text(interview.get("status")).lower()
            confirmation_status = _normalize_text(interview.get("confirmation_status")).lower()
            if status == "cancelled" or confirmation_status == "declined":
                continue
            if guest_id and str(interview.get("guest_id") or "").strip() == guest_id:
                return interview
            if guest_email and _normalize_text(interview.get("guest_email")).casefold() == guest_email:
                return interview
        return None

    def _repair_existing_public_booking(
        self,
        guest: Dict[str, Any],
        interview: Dict[str, Any],
        *,
        scheduled_for: str,
        timezone_label: str,
        guest_note: str,
    ) -> Optional[Dict[str, Any]]:
        """Repair a stale local booking by attaching the missing calendar event when possible."""
        if _normalize_text(interview.get("calendar_event_id")):
            return None
        existing_start = self._normalize_booking_datetime(interview.get("scheduled_for"))
        requested_start = self._normalize_booking_datetime(scheduled_for)
        if not existing_start or not requested_start or existing_start != requested_start:
            return None

        updated_interview = self.update_interview(
            int(interview["id"]),
            {
                "guest_email": _normalize_text(guest.get("email")) or _normalize_text(interview.get("guest_email")),
                "join_url": _normalize_text(interview.get("join_url")) or self._booking_join_url(),
                "status": "scheduled",
                "confirmation_status": "confirmed",
                "reminder_status": _normalize_text(interview.get("reminder_status")) or "not_scheduled",
                "notes": "\n".join(
                    part
                    for part in [
                        _normalize_text(interview.get("notes")),
                        "Calendar invite repaired through the Mirror Talk guest booking flow.",
                        f"Guest browser timezone: {timezone_label}" if timezone_label else "",
                        guest_note,
                    ]
                    if part
                ),
            },
        )

        client = self._build_google_calendar_client()
        if client is not None:
            try:
                created_event = client.create_event_from_interview(updated_interview)
            except GoogleCalendarSyncError as exc:
                raise WebInterfaceError(str(exc)) from exc
            self.database.update_interview(
                updated_interview["id"],
                {
                    "calendar_event_id": created_event.get("id"),
                    "calendar_source": "google_calendar",
                    "event_updated_at": created_event.get("updated"),
                    "last_synced_at": datetime.now().astimezone().isoformat(),
                },
            )
            updated_interview = self.database.get_interview_by_id(updated_interview["id"]) or updated_interview

        self._send_booking_confirmation_email(guest, updated_interview)
        return updated_interview

    def _booking_timezone(self) -> ZoneInfo:
        """Return the configured booking timezone object."""
        try:
            return ZoneInfo(self._booking_timezone_name())
        except ZoneInfoNotFoundError as exc:
            raise WebInterfaceError("Booking timezone is invalid on the server.") from exc

    def _booking_busy_windows(self, *, reference: datetime) -> list[tuple[datetime, datetime]]:
        """Return busy windows from Google Calendar and existing interviews."""
        busy: list[tuple[datetime, datetime]] = []
        client = self._build_google_calendar_client()
        duration = timedelta(minutes=self._booking_duration_minutes())
        if client is not None:
            try:
                events = client.list_busy_events(days_ahead=self._booking_days_ahead(), reference=reference)
            except GoogleCalendarSyncError as exc:
                raise WebInterfaceError(str(exc)) from exc
            for event in events:
                start = self._parse_datetime((event.get("start") or {}).get("dateTime"))
                end = self._parse_datetime((event.get("end") or {}).get("dateTime"))
                if start and end and end > start:
                    busy.append((start, end))

        for interview in self.database.list_interviews():
            status = _normalize_text(interview.get("status")).lower()
            if status == "cancelled":
                continue
            start = self._parse_datetime(interview.get("scheduled_for"))
            if not start:
                continue
            if start.tzinfo is None:
                start = start.replace(tzinfo=timezone.utc)
            else:
                start = start.astimezone(timezone.utc)
            end = start + duration
            busy.append((start, end))
        return busy

    @staticmethod
    def _slot_overlaps_busy(
        slot_start: datetime,
        slot_end: datetime,
        busy_windows: list[tuple[datetime, datetime]],
        *,
        buffer_minutes: int = BOOKING_DEFAULT_BUFFER_MINUTES,
    ) -> bool:
        """Return True when a slot overlaps any busy window."""
        slot_start = slot_start - timedelta(minutes=max(0, buffer_minutes))
        slot_end = slot_end + timedelta(minutes=max(0, buffer_minutes))
        for busy_start, busy_end in busy_windows:
            if slot_start < busy_end and slot_end > busy_start:
                return True
        return False

    def get_public_booking_context(self, booking_token: str) -> Dict[str, Any]:
        """Return guest-facing booking context from a secure token."""
        guest = self._guest_from_booking_token(booking_token)
        existing_interview = self._find_future_interview_for_guest(guest)
        return {
            "guest_name": _normalize_text(guest.get("full_name") or guest.get("name")) or "Guest",
            "guest_email": _normalize_text(guest.get("email")),
            "booking_timezone": self._booking_timezone_name(),
            "existing_booking": self._serialize_public_booking_interview(existing_interview) if existing_interview else None,
        }

    def list_public_booking_slots(self, booking_token: str, *, limit: Optional[int] = None) -> Dict[str, Any]:
        """Return available booking slots for a guest-facing booking link."""
        guest = self._guest_from_booking_token(booking_token)
        existing_interview = self._find_future_interview_for_guest(guest)
        timezone_obj = self._booking_timezone()
        reference = datetime.now(timezone.utc)
        min_notice = reference + timedelta(hours=self._booking_min_notice_hours())
        duration = timedelta(minutes=self._booking_duration_minutes())
        busy_windows = self._booking_busy_windows(reference=reference)
        weekdays = set(self._booking_slot_weekdays())
        slot_times = self._booking_slot_times()

        slots: list[Dict[str, Any]] = []
        current_local = min_notice.astimezone(timezone_obj)
        for day_offset in range(self._booking_days_ahead() + 1):
            candidate_day = (current_local + timedelta(days=day_offset)).date()
            weekday = datetime(candidate_day.year, candidate_day.month, candidate_day.day).weekday()
            if weekday not in weekdays:
                continue
            for slot_time in slot_times:
                try:
                    hour_text, minute_text = slot_time.split(":", 1)
                    slot_start = datetime(
                        candidate_day.year,
                        candidate_day.month,
                        candidate_day.day,
                        int(hour_text),
                        int(minute_text),
                        tzinfo=timezone_obj,
                    )
                except ValueError:
                    continue
                if slot_start.astimezone(timezone.utc) < min_notice:
                    continue
                slot_end = slot_start + duration
                if self._slot_overlaps_busy(
                    slot_start.astimezone(timezone.utc),
                    slot_end.astimezone(timezone.utc),
                    busy_windows,
                    buffer_minutes=self._booking_buffer_minutes(),
                ):
                    continue
                slots.append(
                    {
                        "start": slot_start.astimezone(timezone.utc).isoformat(),
                        "end": slot_end.astimezone(timezone.utc).isoformat(),
                        "timezone": self._booking_timezone_name(),
                    }
                )
                if limit is not None and len(slots) >= limit:
                    break
            if limit is not None and len(slots) >= limit:
                break

        return {
            "guest_name": _normalize_text(guest.get("full_name") or guest.get("name")) or "Guest",
            "booking_timezone": self._booking_timezone_name(),
            "existing_booking": self._serialize_public_booking_interview(existing_interview) if existing_interview else None,
            "booking_window": {
                "months_ahead": self._booking_months_ahead(),
                "days_ahead": self._booking_days_ahead(),
            },
            "slots": slots,
        }

    def create_public_booking(self, booking_token: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Create an interview from a public booking token and selected slot."""
        guest = self._guest_from_booking_token(booking_token)
        scheduled_for = _normalize_text(payload.get("scheduled_for"))
        timezone_label = _normalize_text(payload.get("timezone")) or self._booking_timezone_name()
        guest_note = _normalize_text(payload.get("note"))
        if not scheduled_for:
            raise WebInterfaceError("Please choose one of the available interview slots.")

        existing_interview = self._find_future_interview_for_guest(guest)
        if existing_interview:
            repaired = self._repair_existing_public_booking(
                guest,
                existing_interview,
                scheduled_for=scheduled_for,
                timezone_label=timezone_label,
                guest_note=guest_note,
            )
            if repaired:
                return self._serialize_public_booking_interview(repaired)
            raise WebInterfaceError("A future interview is already booked for this guest.")

        available = self.list_public_booking_slots(booking_token)
        available_starts = {item["start"] for item in available.get("slots", [])}
        normalized_scheduled_for = scheduled_for.replace("Z", "+00:00")
        if normalized_scheduled_for not in available_starts:
            raise WebInterfaceError("That slot is no longer available. Please choose another time.")

        interview = self.create_interview(
            {
                "guest_id": guest.get("id"),
                "guest_name": _normalize_text(guest.get("full_name") or guest.get("name")),
                "guest_email": _normalize_text(guest.get("email")),
                "title": f"Soulful Conversation with {_normalize_text(guest.get('full_name') or guest.get('name') or 'Guest')}",
                "scheduled_for": normalized_scheduled_for,
                "timezone": timezone_label,
                "join_url": self._booking_join_url(),
                "status": "scheduled",
                "confirmation_status": "confirmed",
                "reminder_status": "not_scheduled",
                "notes": "\n".join(
                    part for part in [
                        "Booked through the Mirror Talk guest booking flow.",
                        f"Guest browser timezone: {timezone_label}" if timezone_label else "",
                        guest_note,
                    ] if part
                ),
            }
        )

        client = self._build_google_calendar_client()
        if client is not None:
            try:
                created_event = client.create_event_from_interview(interview)
            except GoogleCalendarSyncError as exc:
                raise WebInterfaceError(str(exc)) from exc
            self.database.update_interview(
                interview["id"],
                {
                    "calendar_event_id": created_event.get("id"),
                    "calendar_source": "google_calendar",
                    "event_updated_at": created_event.get("updated"),
                    "last_synced_at": datetime.now().astimezone().isoformat(),
                },
            )
            interview = self.database.get_interview_by_id(interview["id"]) or interview

        self._send_booking_confirmation_email(guest, interview)
        return self._serialize_public_booking_interview(interview)

    def create_episode(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Create or update an episode record."""
        normalized_release_date = _normalize_text(payload.get("release_date"))
        normalized_release_status = _normalize_episode_release_status(
            normalized_release_date,
            _normalize_text(payload.get("release_status")),
        )
        normalized_production_status = _normalize_text(payload.get("production_status")) or "idea"
        normalized_promotion_status = _normalize_text(payload.get("promotion_status")) or "unknown"
        parsed_priority_score = _parse_priority_score(payload.get("priority_score"))
        if parsed_priority_score <= 0:
            parsed_priority_score = self._suggest_episode_priority_score(
                {
                    "release_status": normalized_release_status,
                    "production_status": normalized_production_status,
                    "promotion_status": normalized_promotion_status,
                }
            )
        parsed_priority_score = _clamp_priority_score(parsed_priority_score)
        legacy_episode_number = _normalize_text(payload.get("legacy_episode_number")) or self._next_legacy_episode_number(payload.get("id"))
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
            "production_status": normalized_production_status,
            "promotion_status": normalized_promotion_status,
            "priority_score": parsed_priority_score,
            "recommendation_reason": _normalize_text(payload.get("recommendation_reason")),
            "legacy_episode_number": legacy_episode_number,
            "riverside_status": _normalize_text(payload.get("riverside_status")),
            "source_file_name": _normalize_text(payload.get("source_file_name")),
            "source_type": _normalize_text(payload.get("source_type")),
            "show_notes_url": _normalize_text(payload.get("show_notes_url")),
            "release_files_url": _normalize_text(payload.get("release_files_url")),
            "transcript_text": _normalize_text(payload.get("transcript_text")),
            "outreach_plan": _normalize_outreach_plan(payload.get("outreach_plan")),
            "ai_monthly_angle_state": _normalize_text(payload.get("ai_monthly_angle_state")),
            "ai_monthly_angle_theme": _normalize_text(payload.get("ai_monthly_angle_theme")),
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
        self._invalidate_payload_cache("operations", "planning", "planning_ai_copilot")
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
            "ai_monthly_angle_state": _normalize_text((linked_episode or {}).get("ai_monthly_angle_state")),
            "ai_monthly_angle_theme": _normalize_text((linked_episode or {}).get("ai_monthly_angle_theme")),
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

        self._invalidate_payload_cache("planning", "planning_ai_copilot", "operations")
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
        if updated:
            self._invalidate_payload_cache("planning", "planning_ai_copilot", "operations")
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
        self._invalidate_payload_cache("planning", "planning_ai_copilot", "operations")
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
                return (2, float("inf"), -int(interview.get("id") or 0))

            comparison_reference = self._align_reference_datetime(reference, scheduled_for)
            sort_value = scheduled_for.timestamp()
            if scheduled_for >= comparison_reference:
                return (0, sort_value, int(interview.get("id") or 0))

            return (1, -sort_value, -int(interview.get("id") or 0))

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

    def preview_interview_cancellation(self, interview_id: int) -> Dict[str, Any]:
        """Return the cancellation email template for an interview."""
        interview = self.database.get_interview_by_id(interview_id)
        if not interview:
            raise WebInterfaceError("Interview not found.")

        scheduled_for = self._parse_datetime(interview.get("scheduled_for"))
        if not scheduled_for:
            raise WebInterfaceError("Interview date is invalid or missing.")

        guest_name = _normalize_text(interview.get("guest_name")) or "Guest"
        timezone_label = _normalize_text(interview.get("timezone")) or "CET"

        email_manager = self._build_email_manager()
        template = email_manager.get_interview_cancellation_template(
            guest_name=guest_name,
            scheduled_for=scheduled_for,
            timezone_label=timezone_label,
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

        guest_name = self._extract_guest_name_from_interview_title(
            interview.get("guest_name"),
            interview.get("title"),
        ) or "Guest"
        email_manager = self._build_email_manager()
        template = email_manager.get_post_interview_appreciation_template(guest_name=guest_name)
        return {
            "interview": self._serialize_interview_reminder(interview),
            "subject": template["subject"],
            "body": template["body"],
        }

    def preview_interview_booking_confirmation(self, interview_id: int) -> Dict[str, Any]:
        """Return the booking confirmation email template for an interview."""
        interview = self.database.get_interview_by_id(interview_id)
        if not interview:
            raise WebInterfaceError("Interview not found.")

        scheduled_for = self._parse_datetime(interview.get("scheduled_for"))
        if not scheduled_for:
            raise WebInterfaceError("Interview date is invalid or missing.")

        guest_name = self._extract_guest_name_from_interview_title(
            interview.get("guest_name"),
            interview.get("title"),
        ) or "Guest"
        timezone_label = _normalize_text(interview.get("timezone")) or self._booking_timezone_name()
        join_url = _normalize_text(interview.get("join_url")) or self._booking_join_url()

        email_manager = self._build_email_manager()
        template = email_manager.get_booking_confirmation_template(
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

    def send_interview_booking_confirmation(self, interview_id: int, subject: str = "", body: str = "") -> Dict[str, Any]:
        """Send the booking confirmation email and calendar invite for an interview."""
        interview = self.database.get_interview_by_id(interview_id)
        if not interview:
            raise WebInterfaceError("Interview not found.")

        guest_email = _normalize_text(interview.get("guest_email"))
        if not guest_email:
            raise WebInterfaceError("This interview does not have a guest email.")

        scheduled_for = self._parse_datetime(interview.get("scheduled_for"))
        if not scheduled_for:
            raise WebInterfaceError("Interview date is invalid or missing.")

        guest_name = self._extract_guest_name_from_interview_title(
            interview.get("guest_name"),
            interview.get("title"),
        ) or "Guest"
        timezone_label = _normalize_text(interview.get("timezone")) or self._booking_timezone_name()
        join_url = _normalize_text(interview.get("join_url")) or self._booking_join_url()

        email_manager = self._build_email_manager()
        if not email_manager.is_configured():
            raise WebInterfaceError("Dashboard email is not configured on the server.")

        preview = self.preview_interview_booking_confirmation(interview_id)
        resolved_subject = subject.strip() or preview["subject"]
        resolved_body = body.strip() or preview["body"]

        if subject.strip() or body.strip():
            invite_attachment = {
                "filename": "mirror-talk-booking.ics",
                "content": email_manager.build_calendar_invite(
                    guest_name=guest_name,
                    scheduled_for=scheduled_for,
                    timezone_label=timezone_label,
                    join_url=join_url,
                ),
            }
            sent = email_manager.send_email(
                guest_email,
                resolved_subject,
                resolved_body,
                attachments=[invite_attachment],
            )
        else:
            sent = email_manager.send_booking_confirmation_email(
                guest_name,
                guest_email,
                scheduled_for,
                timezone_label,
                join_url,
            )

        if not sent:
            error_detail = (email_manager.last_error or "").strip()
            if error_detail:
                raise WebInterfaceError(f"The booking confirmation email could not be sent: {error_detail}")
            raise WebInterfaceError("The booking confirmation email could not be sent.")

        provider = "resend" if email_manager.resend_api_key else "smtp"
        self.database.log_interview_email(
            interview_id=interview_id,
            email_type="booking_confirmation",
            sent_to=guest_email,
            status="sent",
            provider=provider,
            notes=resolved_subject,
        )
        refreshed = self.database.get_interview_by_id(interview_id)
        if not refreshed:
            raise WebInterfaceError("Interview not found after booking confirmation send.")
        return self._serialize_interview_reminder(refreshed)

    def send_interview_cancellation(self, interview_id: int, subject: str = "", body: str = "") -> Dict[str, Any]:
        """Send a cancellation email for an interview and mark it cancelled."""
        interview = self.database.get_interview_by_id(interview_id)
        if not interview:
            raise WebInterfaceError("Interview not found.")

        guest_email = _normalize_text(interview.get("guest_email"))
        if not guest_email:
            raise WebInterfaceError("This interview does not have a guest email.")

        email_manager = self._build_email_manager()
        if not email_manager.is_configured():
            raise WebInterfaceError("Dashboard email is not configured on the server.")

        preview = self.preview_interview_cancellation(interview_id)
        resolved_subject = subject.strip() or preview["subject"]
        resolved_body = body.strip() or preview["body"]

        sent = email_manager.send_email(guest_email, resolved_subject, resolved_body)
        if not sent:
            error_detail = (email_manager.last_error or "").strip()
            if error_detail:
                raise WebInterfaceError(f"The cancellation email could not be sent: {error_detail}")
            raise WebInterfaceError("The cancellation email could not be sent.")

        provider = "resend" if email_manager.resend_api_key else "smtp"
        self.database.log_interview_email(
            interview_id=interview_id,
            email_type="interview_cancellation",
            sent_to=guest_email,
            status="sent",
            provider=provider,
            notes=resolved_subject,
        )
        updated = self.update_interview(
            interview_id,
            {
                "status": "cancelled",
                "confirmation_status": (
                    interview.get("confirmation_status")
                    if _normalize_text(interview.get("confirmation_status")).lower() == "confirmed"
                    else "declined"
                ),
            },
        )
        return self._serialize_interview_reminder(updated)

    def preview_episode_appreciation(self, episode_id: int) -> Dict[str, Any]:
        """Return the post-recording appreciation email template from an episode record."""
        episode = self.database.get_episode_by_id(episode_id)
        if not episode:
            raise WebInterfaceError("Episode not found.")

        guest_name = self._extract_guest_name_from_interview_title(
            episode.get("guest_name"),
            episode.get("episode_title"),
        ) or "Guest"
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

        guest_name = self._extract_guest_name_from_interview_title(
            episode.get("guest_name"),
            episode.get("episode_title"),
        ) or "Guest"
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

        removal_result = {"deleted": True, "already_deleted": False}
        try:
            client_result = client.delete_event(event_id)
            if isinstance(client_result, dict):
                removal_result = client_result
        except GoogleCalendarSyncError as exc:
            raise WebInterfaceError(str(exc)) from exc

        removal_note = (
            "Google Calendar event was already gone, so the local interview was unlinked."
            if removal_result.get("already_deleted")
            else "Removed from Google Calendar."
        )
        updates = {
            "status": "cancelled",
            "confirmation_status": "declined" if _normalize_text(interview.get("confirmation_status")).lower() == "pending" else interview.get("confirmation_status"),
            "last_synced_at": datetime.now().astimezone().isoformat(),
            "calendar_event_id": None,
            "calendar_source": "",
            "event_updated_at": "",
            "notes": "\n".join(
                part
                for part in [
                    _normalize_text(interview.get("notes")),
                    removal_note,
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
        """Build the Google Calendar client from environment configuration.
        
        Tries service account first (preferred), then falls back to OAuth refresh token.
        """
        # Try service account first (no token expiration issues)
        service_account_file = os.environ.get("MIRROR_TALK_GOOGLE_SERVICE_ACCOUNT_FILE", "").strip()
        calendar_id = os.environ.get(GOOGLE_CALENDAR_ID_ENV_VAR, "").strip()
        
        if service_account_file and calendar_id:
            try:
                from guest_database_manager.google_service_account_calendar import GoogleServiceAccountCalendarClient
                # Wrap service account client to match the existing interface
                return GoogleServiceAccountCalendarClient(
                    service_account_file=service_account_file,
                    calendar_id=calendar_id,
                    default_timezone=os.environ.get(GOOGLE_CALENDAR_TIMEZONE_ENV_VAR, "Europe/Berlin").strip() or "Europe/Berlin",
                )
            except Exception:
                # Fall through to OAuth refresh token if service account fails
                pass
        
        # Fallback to OAuth refresh token (original method)
        client_id = os.environ.get(GOOGLE_CLIENT_ID_ENV_VAR, "").strip()
        client_secret = os.environ.get(GOOGLE_CLIENT_SECRET_ENV_VAR, "").strip()
        refresh_token = os.environ.get(GOOGLE_REFRESH_TOKEN_ENV_VAR, "").strip()

        if not all([client_id, client_secret, refresh_token, calendar_id]):
            return None

        return GoogleCalendarSyncClient(
            client_id=client_id,
            client_secret=client_secret,
            refresh_token=refresh_token,
            calendar_id=calendar_id,
            default_timezone=os.environ.get(GOOGLE_CALENDAR_TIMEZONE_ENV_VAR, "Europe/Berlin").strip() or "Europe/Berlin",
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

    @staticmethod
    def _booking_base_url() -> str:
        """Return the configured public booking base URL."""
        configured = os.environ.get(BOOKING_BASE_URL_ENV_VAR, "").strip()
        return configured or "https://guest-processing-production.up.railway.app/book"

    @staticmethod
    def _booking_timezone_name() -> str:
        """Return the configured booking timezone."""
        return os.environ.get(BOOKING_TIMEZONE_ENV_VAR, "Europe/Berlin").strip() or "Europe/Berlin"

    @staticmethod
    def _booking_slot_weekdays() -> tuple[int, ...]:
        """Return weekday numbers for guest booking availability."""
        raw = os.environ.get(BOOKING_SLOT_WEEKDAYS_ENV_VAR, ",".join(BOOKING_DEFAULT_WEEKDAYS)).strip()
        mapping = {"MO": 0, "TU": 1, "WE": 2, "TH": 3, "FR": 4, "SA": 5, "SU": 6}
        values = []
        for item in raw.split(","):
            normalized = item.strip().upper()
            if normalized in mapping:
                values.append(mapping[normalized])
        return tuple(values or [mapping[item] for item in BOOKING_DEFAULT_WEEKDAYS])

    @staticmethod
    def _booking_slot_times() -> tuple[str, ...]:
        """Return local times for guest booking availability."""
        raw = os.environ.get(BOOKING_SLOT_TIMES_ENV_VAR, ",".join(BOOKING_DEFAULT_TIMES)).strip()
        values = tuple(item.strip() for item in raw.split(",") if item.strip())
        return values or BOOKING_DEFAULT_TIMES

    @staticmethod
    def _booking_days_ahead() -> int:
        months_raw = os.environ.get(BOOKING_MONTHS_AHEAD_ENV_VAR, "").strip()
        if months_raw:
            try:
                months = max(1, min(12, int(months_raw)))
                return max(14, min(366, months * 31))
            except ValueError:
                return BOOKING_DEFAULT_MONTHS_AHEAD * 31

        raw = os.environ.get(BOOKING_DAYS_AHEAD_ENV_VAR, str(BOOKING_DEFAULT_DAYS_AHEAD)).strip() or str(BOOKING_DEFAULT_DAYS_AHEAD)
        try:
            return max(7, min(120, int(raw)))
        except ValueError:
            return BOOKING_DEFAULT_DAYS_AHEAD

    @staticmethod
    def _booking_months_ahead() -> int:
        raw = os.environ.get(BOOKING_MONTHS_AHEAD_ENV_VAR, "").strip()
        if raw:
            try:
                return max(1, min(12, int(raw)))
            except ValueError:
                return BOOKING_DEFAULT_MONTHS_AHEAD
        days = GuestWebService._booking_days_ahead()
        return max(1, min(12, (days + 30) // 31))

    @staticmethod
    def _booking_min_notice_hours() -> int:
        raw = os.environ.get(BOOKING_MIN_NOTICE_HOURS_ENV_VAR, str(BOOKING_DEFAULT_MIN_NOTICE_HOURS)).strip() or str(BOOKING_DEFAULT_MIN_NOTICE_HOURS)
        try:
            return max(2, min(168, int(raw)))
        except ValueError:
            return BOOKING_DEFAULT_MIN_NOTICE_HOURS

    @staticmethod
    def _booking_buffer_minutes() -> int:
        raw = os.environ.get(BOOKING_BUFFER_MINUTES_ENV_VAR, str(BOOKING_DEFAULT_BUFFER_MINUTES)).strip() or str(BOOKING_DEFAULT_BUFFER_MINUTES)
        try:
            return max(0, min(120, int(raw)))
        except ValueError:
            return BOOKING_DEFAULT_BUFFER_MINUTES

    @staticmethod
    def _booking_duration_minutes() -> int:
        raw = os.environ.get(BOOKING_DURATION_MINUTES_ENV_VAR, str(BOOKING_DEFAULT_DURATION_MINUTES)).strip() or str(BOOKING_DEFAULT_DURATION_MINUTES)
        try:
            return max(30, min(180, int(raw)))
        except ValueError:
            return BOOKING_DEFAULT_DURATION_MINUTES

    @staticmethod
    def _booking_join_url() -> str:
        return os.environ.get(
            BOOKING_JOIN_URL_ENV_VAR,
            "https://riverside.fm/studio/soulful-conversations?t=db1988c6212f0c5f39db",
        ).strip()

    def _ensure_guest_booking_token(self, guest_id: int) -> str:
        """Ensure a guest has a stable booking token."""
        guest = self.database.get_guest_by_id(guest_id)
        if not guest:
            raise WebInterfaceError("Guest not found.")
        existing_token = _normalize_text(guest.get("booking_token"))
        if existing_token:
            return existing_token

        booking_token = secrets.token_urlsafe(24)
        updated_guest = dict(guest)
        updated_guest["booking_token"] = booking_token
        updated_guest["booking_token_created_at"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        self.database.update_guest_by_id(guest_id, updated_guest)
        return booking_token

    def _booking_link_for_guest(self, guest_id: int) -> str:
        """Build the public booking link for a guest."""
        booking_token = self._ensure_guest_booking_token(guest_id)
        separator = "&" if "?" in self._booking_base_url() else "?"
        return f"{self._booking_base_url()}{separator}token={booking_token}"

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

    def _send_guest_self_application_request_email(
        self,
        guest_name: str,
        guest_email: str,
        intake_url: str,
        agency_name: str = "",
    ) -> None:
        """Best-effort email asking a referred guest to complete their own intake."""
        if not guest_email:
            return
        email_manager = self._build_email_manager()
        if not email_manager.is_configured():
            return
        try:
            email_manager.send_personal_application_request_email(
                guest_name,
                guest_email,
                intake_url,
                agency_name,
            )
        except Exception:
            return

    def resend_guest_personal_application_email(self, guest_id: int) -> Dict[str, Any]:
        """Resend the guest-owned intake invitation for an agency referral."""
        guest = self.database.get_guest_by_id(guest_id)
        if not guest:
            raise WebInterfaceError("Guest not found.")
        if _normalize_text(guest.get("original_file_name")) != AGENCY_REFERRAL_SOURCE_NAME:
            raise WebInterfaceError("This guest was not created through an agency referral.")

        original_data = _parse_original_data(guest.get("original_data"))
        guest_name = _normalize_text(original_data.get("represented_guest_name")) or _normalize_text(guest.get("full_name"))
        guest_email = _normalize_text(original_data.get("represented_guest_email")) or _normalize_text(guest.get("email"))
        agency_name = _normalize_text(original_data.get("agency_name"))

        if not guest_email:
            raise WebInterfaceError("This referral does not have a guest email yet.")

        email_manager = self._build_email_manager()
        if not email_manager.is_configured():
            raise WebInterfaceError("Dashboard email is not configured on the server.")

        intake_url = self._public_intake_link(guest_name, guest_email)
        try:
            sent = email_manager.send_personal_application_request_email(
                guest_name,
                guest_email,
                intake_url,
                agency_name,
            )
        except Exception as exc:
            error_detail = str(exc).strip()
            raise WebInterfaceError(error_detail or "The personal application email could not be sent.") from exc

        if not sent:
            error_detail = (email_manager.last_error or "").strip()
            if error_detail:
                raise WebInterfaceError(f"The personal application email could not be sent: {error_detail}")
            raise WebInterfaceError("The personal application email could not be sent.")

        refreshed = self.database.get_guest_by_id(guest_id)
        if not refreshed:
            raise WebInterfaceError("Guest not found after sending the email.")
        return serialize_guest(refreshed)

    def _send_booking_confirmation_email(self, guest: Dict[str, Any], interview: Dict[str, Any]) -> None:
        """Best-effort confirmation email after a guest books a slot."""
        guest_email = _normalize_text(guest.get("email"))
        if not guest_email:
            return
        scheduled_for = self._parse_datetime(interview.get("scheduled_for"))
        if not scheduled_for:
            return

        email_manager = self._build_email_manager()
        if not email_manager.is_configured():
            return

        guest_name = _normalize_text(guest.get("full_name") or guest.get("name")) or "there"
        try:
            email_manager.send_booking_confirmation_email(
                guest_name,
                guest_email,
                scheduled_for,
                _normalize_text(interview.get("timezone")) or self._booking_timezone_name(),
                _normalize_text(interview.get("join_url")) or self._booking_join_url(),
            )
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

        if request_path in {"/", "/intake", "/intake/", "/intake.html"}:
            self._serve_static("intake.html")
            return

        if request_path in {"/book", "/book/", "/booking", "/book.html"}:
            self._serve_static("booking.html")
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

        if request_path == "/api/booking/context":
            query = self._query_params(self.path)
            try:
                payload = self.service.get_public_booking_context(query.get("token", ""))
            except WebInterfaceError as exc:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                return
            self._send_json(HTTPStatus.OK, payload)
            return

        if request_path == "/api/booking/availability":
            query = self._query_params(self.path)
            try:
                payload = self.service.list_public_booking_slots(query.get("token", ""))
            except WebInterfaceError as exc:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                return
            self._send_json(HTTPStatus.OK, payload)
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

        if request_path.startswith("/api/interviews/") and request_path.endswith("/booking-confirmation-template"):
            if not self._is_authorized_dashboard_request():
                self._send_json(HTTPStatus.UNAUTHORIZED, {"error": "Unauthorized dashboard request"})
                return

            interview_id = self._extract_record_id(request_path[: -len("/booking-confirmation-template")], "/api/interviews/")
            if interview_id is None:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": "Invalid interview id"})
                return

            try:
                payload = self.service.preview_interview_booking_confirmation(interview_id)
            except WebInterfaceError as exc:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                return

            self._send_json(HTTPStatus.OK, payload)
            return

        if request_path.startswith("/api/interviews/") and request_path.endswith("/cancellation-template"):
            if not self._is_authorized_dashboard_request():
                self._send_json(HTTPStatus.UNAUTHORIZED, {"error": "Unauthorized dashboard request"})
                return

            interview_id = self._extract_record_id(request_path[: -len("/cancellation-template")], "/api/interviews/")
            if interview_id is None:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": "Invalid interview id"})
                return

            try:
                payload = self.service.preview_interview_cancellation(interview_id)
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

        if self.path == "/api/booking/confirm":
            payload = self._read_json_payload()
            try:
                interview = self.service.create_public_booking(
                    _normalize_text(payload.get("token")),
                    payload,
                )
            except WebInterfaceError as exc:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                return

            self._send_json(
                HTTPStatus.CREATED,
                {
                    "message": "Your Soulful Conversation has been booked.",
                    "interview": interview,
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

        if self.path.startswith("/api/guests/") and self.path.endswith("/resend-personal-application"):
            if not self._is_authorized_dashboard_request():
                self._send_json(HTTPStatus.UNAUTHORIZED, {"error": "Unauthorized dashboard request"})
                return
            guest_id = self._extract_guest_id(self.path, suffix="/resend-personal-application")
            if guest_id is None:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": "Invalid guest id"})
                return

            try:
                guest = self.service.resend_guest_personal_application_email(guest_id)
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
                except Exception as exc:  # pragma: no cover - defensive API guard
                    self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": f"Google Calendar removal failed: {exc}"})
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

            if self.path.endswith("/send-booking-confirmation"):
                interview_id = self._extract_record_id(self.path[: -len("/send-booking-confirmation")], "/api/interviews/")
                if interview_id is None:
                    self._send_json(HTTPStatus.BAD_REQUEST, {"error": "Invalid interview id"})
                    return

                payload = self._read_json_payload()
                try:
                    interview = self.service.send_interview_booking_confirmation(
                        interview_id,
                        payload.get("subject", ""),
                        payload.get("body", ""),
                    )
                except WebInterfaceError as exc:
                    self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                    return

                self._send_json(HTTPStatus.OK, interview)
                return

            if self.path.endswith("/send-cancellation"):
                interview_id = self._extract_record_id(self.path[: -len("/send-cancellation")], "/api/interviews/")
                if interview_id is None:
                    self._send_json(HTTPStatus.BAD_REQUEST, {"error": "Invalid interview id"})
                    return

                payload = self._read_json_payload()
                try:
                    interview = self.service.send_interview_cancellation(
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

    @staticmethod
    def _query_params(path: str) -> Dict[str, str]:
        """Parse simple query parameters from a request path."""
        query = urlsplit(path).query
        return {key: value for key, value in parse_qsl(query, keep_blank_values=True)}

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
