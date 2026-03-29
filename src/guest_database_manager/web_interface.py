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
from datetime import datetime, timedelta
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO, StringIO
from pathlib import Path
from typing import Any, Dict, Optional

from openpyxl import Workbook

from guest_database_manager.constants import DEFAULT_DB_PATH
from guest_database_manager.database import GuestDatabase
from guest_database_manager.email_manager import EmailManager
from guest_database_manager.episode_planner import build_release_recommendations, parse_episode_import_csv
from guest_database_manager.google_calendar_sync import GoogleCalendarSyncClient, GoogleCalendarSyncError

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


def _link_count(text: str) -> int:
    """Count link-like fragments in a text block."""
    return len(re.findall(r"https?://|www\.", text.lower()))


def _normalize_text(value: Any) -> str:
    """Convert form values to trimmed strings."""
    if value is None:
        return ""
    return str(value).strip()


def validate_intake_payload(payload: Dict[str, str]) -> None:
    """Reject obviously spammy or low-effort intake submissions."""
    combined_text = " ".join(str(payload.get(field, "")) for field in payload).lower()

    if any(keyword in combined_text for keyword in SPAM_KEYWORDS):
        raise WebInterfaceError("Your submission was flagged as spam.")

    if _link_count(combined_text) > 5:
        raise WebInterfaceError("Too many links in submission.")

    for field in LONG_TEXT_FIELDS:
        value = str(payload.get(field, "")).strip()
        if not value:
            continue
        if _word_count(value) < 8:
            field_label = field.replace("_", " ")
            raise WebInterfaceError(f"Please provide a more complete answer for: {field_label}")


def build_guest_payload(payload: Dict[str, Any], source_name: str = FORM_SOURCE_NAME) -> Dict[str, Any]:
    """Convert a web form payload into the database shape."""
    guest_data = {field: _normalize_text(payload.get(field)) for field in FORM_FIELDS}
    guest_data["full_name"] = guest_data["full_name"] or _normalize_text(payload.get("name"))
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
    return serialized


@dataclass
class GuestWebService:
    """Service layer for the direct web interface."""

    db_path: Path

    def __post_init__(self) -> None:
        self.database = GuestDatabase(self.db_path)

    def list_guests(self) -> Dict[str, Any]:
        """Return all guests for the frontend."""
        guests = [serialize_guest(guest) for guest in self.database.get_all_guests()]
        return {
            "guests": guests,
            "stats": self.database.get_stats(),
            "email_stats": self.database.get_email_stats(),
            "email_enabled": self._build_email_manager().is_configured(),
        }

    def list_operations(self) -> Dict[str, Any]:
        """Return the current interview and episode operations data."""
        interviews = self._sort_interviews_by_upcoming_priority(self.database.list_interviews())
        episodes = self.database.list_episodes()
        reminder_candidates = [self._serialize_interview_reminder(candidate) for candidate in self.get_due_weekly_reminders()]
        return {
            "stats": self.database.get_operations_stats(),
            "interviews": interviews,
            "episodes": episodes,
            "recommendations": build_release_recommendations(episodes, reference=datetime.now()),
            "available_categories": self.database.list_episode_categories(),
            "reminder_candidates": reminder_candidates,
            "calendar_sync_enabled": self._build_google_calendar_client() is not None,
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
        return self.create_guest(payload, source_name=INTAKE_SOURCE_NAME)

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

    def delete_guest(self, guest_id: int) -> Dict[str, Any]:
        """Delete a guest and return a small confirmation payload."""
        self.database.delete_guest(guest_id)
        return {"deleted": True, "id": guest_id}

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
        episode_data = {
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
            "release_date": _normalize_text(payload.get("release_date")),
            "release_status": _normalize_text(payload.get("release_status")) or "unplanned",
            "production_status": _normalize_text(payload.get("production_status")) or "idea",
            "promotion_status": _normalize_text(payload.get("promotion_status")) or "unknown",
            "priority_score": payload.get("priority_score") or 0,
            "recommendation_reason": _normalize_text(payload.get("recommendation_reason")),
            "legacy_episode_number": _normalize_text(payload.get("legacy_episode_number")),
            "riverside_status": _normalize_text(payload.get("riverside_status")),
            "source_file_name": _normalize_text(payload.get("source_file_name")),
            "source_type": _normalize_text(payload.get("source_type")),
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

    def import_episode_file(self, filename: str, content: bytes) -> Dict[str, int]:
        """Import released-history or not-yet-released episode CSV data."""
        suffix = Path(filename).suffix.lower()
        if suffix != ".csv":
            raise WebInterfaceError("Please upload a CSV file for episode planning import.")

        episodes = parse_episode_import_csv(content, filename)
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

    def update_episode(self, episode_id: int, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Update an episode record."""
        current = self.database.get_episode_by_id(episode_id)
        if not current:
            raise WebInterfaceError("Episode not found.")

        episode_data = dict(current)
        episode_data.update(payload)
        saved = self.create_episode(episode_data)
        return saved

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

    def sync_google_calendar_interviews(
        self,
        *,
        days_ahead: int = 30,
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
        if self.path in {"/", "/intake", "/intake.html"}:
            self._serve_static("intake.html")
            return

        if self.path in {"/dashboard", "/index.html"}:
            if not self._is_authorized_dashboard_request():
                self._send_basic_auth_challenge()
                return
            self._serve_static("index.html")
            return

        if self.path in {"/operations", "/operations.html"}:
            if not self._is_authorized_dashboard_request():
                self._send_basic_auth_challenge()
                return
            self._serve_static("operations.html")
            return

        if self.path.startswith("/static/"):
            relative_path = self.path.removeprefix("/static/")
            self._serve_static(relative_path)
            return

        if self.path == "/api/guests":
            if not self._is_authorized_dashboard_request():
                self._send_json(HTTPStatus.UNAUTHORIZED, {"error": "Unauthorized dashboard request"})
                return
            self._send_json(HTTPStatus.OK, self.service.list_guests())
            return

        if self.path == "/api/export":
            if not self._is_authorized_dashboard_request():
                self._send_json(HTTPStatus.UNAUTHORIZED, {"error": "Unauthorized dashboard request"})
                return
            self._send_csv(
                HTTPStatus.OK,
                self.service.export_guests_csv(),
                filename="mirror-talk-guests.csv",
            )
            return

        if self.path == "/api/exports":
            self._send_json(HTTPStatus.METHOD_NOT_ALLOWED, {"error": "Use POST for flexible exports"})
            return

        if self.path == "/api/operations":
            if not self._is_authorized_dashboard_request():
                self._send_json(HTTPStatus.UNAUTHORIZED, {"error": "Unauthorized dashboard request"})
                return
            self._send_json(HTTPStatus.OK, self.service.list_operations())
            return

        if self.path == "/api/google-calendar/sync":
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

        if self.path.startswith("/api/interviews/") and self.path.endswith("/reminder-template"):
            if not self._is_authorized_dashboard_request():
                self._send_json(HTTPStatus.UNAUTHORIZED, {"error": "Unauthorized dashboard request"})
                return

            interview_id = self._extract_record_id(self.path[: -len("/reminder-template")], "/api/interviews/")
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
            days_ahead = int(payload.get("days_ahead", 30) or 30)
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

            self._send_json(HTTPStatus.OK, self.service.delete_guest(guest_id))
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
        self.wfile.write(response)

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
        return bool(request_token) and request_token == configured_token

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
