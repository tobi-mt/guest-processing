"""Google Calendar interview sync helpers."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import requests


class GoogleCalendarSyncError(Exception):
    """Raised when Google Calendar sync cannot proceed."""


RIVERSIDE_URL_RE = re.compile(r"https://riverside\.fm/\S+", re.IGNORECASE)
PODCAST_EVENT_MARKERS = (
    "mirror talk",
    "soulful podcast conversation",
    "soulful-conversations",
    "riverside.fm/studio/soulful-conversations",
    "mirrortalkpodcast.com/join-our-family",
    "forms.office.com/r/tcvdr6kkzu",
)


@dataclass
class GoogleCalendarSyncClient:
    """Small Google Calendar API client using OAuth refresh tokens."""

    client_id: str
    client_secret: str
    refresh_token: str
    calendar_id: str
    default_timezone: str = "Europe/Berlin"

    TOKEN_URL = "https://oauth2.googleapis.com/token"
    EVENTS_URL_TEMPLATE = "https://www.googleapis.com/calendar/v3/calendars/{calendar_id}/events"

    def _get_access_token(self) -> str:
        """Exchange the refresh token for an access token."""
        try:
            response = requests.post(
                self.TOKEN_URL,
                data={
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "refresh_token": self.refresh_token,
                    "grant_type": "refresh_token",
                },
                timeout=20,
            )
        except requests.RequestException as exc:
            raise GoogleCalendarSyncError(f"Could not reach Google OAuth: {exc}") from exc

        if not response.ok:
            raise GoogleCalendarSyncError(
                f"Google OAuth token exchange failed: {response.text.strip() or response.status_code}"
            )

        payload = response.json()
        access_token = payload.get("access_token", "").strip()
        if not access_token:
            raise GoogleCalendarSyncError("Google OAuth token response did not include an access token.")
        return access_token

    def list_upcoming_events(
        self,
        *,
        days_ahead: int = 30,
        reference: Optional[datetime] = None,
        query: str = "",
    ) -> List[Dict[str, Any]]:
        """Fetch upcoming timed events from the configured Google Calendar."""
        access_token = self._get_access_token()
        reference = reference or datetime.now(timezone.utc)
        time_min = reference.astimezone(timezone.utc).isoformat()
        time_max = (reference + timedelta(days=days_ahead)).astimezone(timezone.utc).isoformat()

        params = {
            "singleEvents": "true",
            "orderBy": "startTime",
            "timeMin": time_min,
            "timeMax": time_max,
            "maxResults": 250,
        }
        if query.strip():
            params["q"] = query.strip()

        url = self.EVENTS_URL_TEMPLATE.format(calendar_id=requests.utils.quote(self.calendar_id, safe=""))
        try:
            response = requests.get(
                url,
                headers={"Authorization": f"Bearer {access_token}"},
                params=params,
                timeout=20,
            )
        except requests.RequestException as exc:
            raise GoogleCalendarSyncError(f"Could not reach Google Calendar: {exc}") from exc

        if not response.ok:
            raise GoogleCalendarSyncError(
                f"Google Calendar event fetch failed: {response.text.strip() or response.status_code}"
            )

        payload = response.json()
        items = payload.get("items", [])
        return [
            item
            for item in items
            if item.get("start", {}).get("dateTime") and self._looks_like_podcast_event(item, query=query)
        ]

    def normalize_event(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """Convert a Google Calendar event payload into an interview record shape."""
        attendees = event.get("attendees") or []
        guest_attendee = self._pick_guest_attendee(attendees)
        guest_name = (
            (guest_attendee or {}).get("displayName")
            or self._extract_name_from_summary(event.get("summary", ""))
            or "Guest"
        )
        guest_email = (guest_attendee or {}).get("email", "")

        start = event.get("start", {})
        scheduled_for = start.get("dateTime", "")
        timezone_label = start.get("timeZone") or self.default_timezone
        confirmation_status = self._map_confirmation_status((guest_attendee or {}).get("responseStatus", "needsAction"))

        return {
            "guest_name": guest_name,
            "guest_email": guest_email,
            "calendar_event_id": event.get("id", ""),
            "calendar_source": "google_calendar",
            "event_updated_at": event.get("updated", ""),
            "last_synced_at": datetime.now(timezone.utc).isoformat(),
            "title": event.get("summary", "") or f"Mirror Talk conversation with {guest_name}",
            "scheduled_for": scheduled_for,
            "timezone": timezone_label,
            "join_url": self._extract_join_url(event),
            "status": "cancelled" if event.get("status") == "cancelled" else "scheduled",
            "confirmation_status": confirmation_status,
            "reminder_status": "not_scheduled",
            "notes": self._build_notes(event),
        }

    def _pick_guest_attendee(self, attendees: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Choose the attendee that most likely represents the guest."""
        for attendee in attendees:
            email = (attendee.get("email") or "").strip().lower()
            if attendee.get("self"):
                continue
            if "mirrortalk" in email:
                continue
            return attendee
        return attendees[0] if attendees else None

    @staticmethod
    def _map_confirmation_status(response_status: str) -> str:
        """Map Google attendee status into our interview confirmation status."""
        normalized = (response_status or "").strip().lower()
        if normalized == "accepted":
            return "confirmed"
        if normalized == "tentative":
            return "tentative"
        if normalized == "declined":
            return "declined"
        return "pending"

    @staticmethod
    def _extract_name_from_summary(summary: str) -> str:
        """Best-effort guest name extraction from an event title."""
        text = (summary or "").strip()
        if not text:
            return ""

        patterns = [
            r"with\s+(.+)$",
            r"conversation\s*[:-]\s*(.+)$",
            r"interview\s*[:-]\s*(.+)$",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        return text

    @staticmethod
    def _extract_join_url(event: Dict[str, Any]) -> str:
        """Pull the best available join URL from the event."""
        hangout_link = (event.get("hangoutLink") or "").strip()
        if hangout_link:
            return hangout_link

        location = (event.get("location") or "").strip()
        if location.startswith("http"):
            return location

        description = (event.get("description") or "").strip()
        match = RIVERSIDE_URL_RE.search(description)
        if match:
            return match.group(0)

        return ""

    @staticmethod
    def _looks_like_podcast_event(event: Dict[str, Any], *, query: str = "") -> bool:
        """Decide whether a calendar event looks like a Mirror Talk interview."""
        summary = (event.get("summary") or "").strip().lower()
        description = (event.get("description") or "").strip().lower()
        location = (event.get("location") or "").strip().lower()
        haystack = "\n".join([summary, description, location])

        if query.strip() and query.strip().lower() in haystack:
            return True

        return any(marker in haystack for marker in PODCAST_EVENT_MARKERS)

    @staticmethod
    def _build_notes(event: Dict[str, Any]) -> str:
        """Store a small amount of event context in notes for operators."""
        notes = []
        location = (event.get("location") or "").strip()
        description = (event.get("description") or "").strip()
        if location:
            notes.append(f"Location: {location}")
        if description:
            notes.append(description[:1200])
        return "\n\n".join(notes)
