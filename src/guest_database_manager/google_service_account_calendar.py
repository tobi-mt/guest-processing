"""Google Calendar sync using Service Account authentication (no token expiration)."""

from __future__ import annotations

import json
import time
from base64 import b64decode
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import jwt
import requests


class GoogleCalendarServiceAccountError(Exception):
    """Raised when Google Calendar service account operations fail."""


class GoogleServiceAccountCalendarClient:
    """
    Google Calendar client using Service Account authentication.
    
    This solves the refresh token expiration problem by using service accounts
    which don't require user interaction and never expire.
    
    Setup:
        1. Create service account in Google Cloud Console
        2. Download JSON key file
        3. Share your calendar with the service account email
        4. Use this client instead of the refresh token approach
    
    Example:
        client = GoogleServiceAccountCalendarClient(
            service_account_file="path/to/service-account-key.json",
            calendar_id="your-calendar@gmail.com"
        )
        events = client.list_upcoming_events(days_ahead=30)
    """

    TOKEN_URL = "https://oauth2.googleapis.com/token"
    EVENTS_URL_TEMPLATE = "https://www.googleapis.com/calendar/v3/calendars/{calendar_id}/events"
    SCOPES = ["https://www.googleapis.com/auth/calendar"]

    @staticmethod
    def _validate_credentials(credentials: Dict[str, Any], *, source_label: str) -> Dict[str, Any]:
        """Validate the basic shape of a service-account credential payload."""
        required_fields = ["client_email", "private_key", "token_uri"]
        missing = [field for field in required_fields if field not in credentials]
        if missing:
            raise GoogleCalendarServiceAccountError(
                f"{source_label} missing required fields: {', '.join(missing)}"
            )
        return credentials
    
    def __init__(
        self,
        service_account_file: str | Path,
        calendar_id: str,
        default_timezone: str = "Europe/Berlin"
    ):
        """
        Initialize with service account credentials.
        
        Args:
            service_account_file: Path to JSON key file from Google Cloud Console
            calendar_id: Google Calendar ID (usually an email address)
            default_timezone: Default timezone for events
        """
        self.calendar_id = calendar_id
        self.default_timezone = default_timezone
        
        # Load service account credentials
        service_account_path = Path(service_account_file)
        if not service_account_path.exists():
            raise GoogleCalendarServiceAccountError(
                f"Service account file not found: {service_account_file}"
            )
        
        try:
            with open(service_account_path, 'r') as f:
                credentials = json.load(f)
        except json.JSONDecodeError as exc:
            raise GoogleCalendarServiceAccountError(
                f"Invalid JSON in service account file: {exc}"
            ) from exc
        self.credentials = self._validate_credentials(credentials, source_label="Service account file")
        
        self._access_token: Optional[str] = None
        self._token_expiry: Optional[datetime] = None

    @classmethod
    def from_base64(
        cls,
        service_account_base64: str,
        calendar_id: str,
        default_timezone: str = "Europe/Berlin",
    ) -> "GoogleServiceAccountCalendarClient":
        """Initialize directly from a base64-encoded service-account JSON payload."""
        try:
            decoded = b64decode(service_account_base64)
        except Exception as exc:
            raise GoogleCalendarServiceAccountError(
                f"Service account base64 could not be decoded: {exc}"
            ) from exc

        try:
            credentials = json.loads(decoded.decode("utf-8"))
        except UnicodeDecodeError as exc:
            raise GoogleCalendarServiceAccountError(
                f"Service account base64 did not decode to UTF-8 JSON: {exc}"
            ) from exc
        except json.JSONDecodeError as exc:
            raise GoogleCalendarServiceAccountError(
                f"Invalid JSON in service account base64 payload: {exc}"
            ) from exc

        instance = cls.__new__(cls)
        instance.calendar_id = calendar_id
        instance.default_timezone = default_timezone
        instance.credentials = cls._validate_credentials(credentials, source_label="Service account base64 payload")
        instance._access_token = None
        instance._token_expiry = None
        return instance
    
    def _create_signed_jwt(self) -> str:
        """Create a signed JWT for service account authentication."""
        now = int(time.time())
        
        payload = {
            "iss": self.credentials["client_email"],
            "sub": self.credentials["client_email"],
            "aud": self.credentials.get("token_uri", self.TOKEN_URL),
            "iat": now,
            "exp": now + 3600,  # 1 hour expiration
            "scope": " ".join(self.SCOPES),
        }
        
        # Sign JWT with private key
        try:
            token = jwt.encode(
                payload,
                self.credentials["private_key"],
                algorithm="RS256",
            )
        except Exception as exc:
            raise GoogleCalendarServiceAccountError(
                f"Failed to create signed JWT: {exc}"
            ) from exc
        
        return token
    
    def _get_access_token(self) -> str:
        """Get a valid access token, refreshing if necessary."""
        # Return cached token if still valid (with 5-minute buffer)
        if self._access_token and self._token_expiry:
            if datetime.now(timezone.utc) < self._token_expiry - timedelta(minutes=5):
                return self._access_token
        
        # Create signed JWT
        signed_jwt = self._create_signed_jwt()
        
        # Exchange JWT for access token
        try:
            response = requests.post(
                self.TOKEN_URL,
                data={
                    "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                    "assertion": signed_jwt,
                },
                timeout=20,
            )
        except requests.RequestException as exc:
            raise GoogleCalendarServiceAccountError(
                f"Could not reach Google OAuth: {exc}"
            ) from exc
        
        if not response.ok:
            raise GoogleCalendarServiceAccountError(
                f"Failed to get access token: {response.text or response.status_code}"
            )
        
        try:
            data = response.json()
        except json.JSONDecodeError as exc:
            raise GoogleCalendarServiceAccountError(
                f"Invalid JSON response from token endpoint: {exc}"
            ) from exc
        
        self._access_token = data.get("access_token")
        if not self._access_token:
            raise GoogleCalendarServiceAccountError(
                "Token response did not include access_token"
            )
        
        # Cache token with expiry time
        expires_in = data.get("expires_in", 3600)
        self._token_expiry = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
        
        return self._access_token
    
    def list_upcoming_events(
        self,
        *,
        days_ahead: int = 30,
        reference: Optional[datetime] = None,
        query: str = "",
    ) -> List[Dict[str, Any]]:
        """
        Fetch upcoming timed events from the configured Google Calendar.
        
        Args:
            days_ahead: Number of days ahead to fetch events
            reference: Reference datetime (defaults to now)
            query: Optional search query to filter events
            
        Returns:
            List of calendar event dictionaries
        """
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
        
        url = self.EVENTS_URL_TEMPLATE.format(
            calendar_id=requests.utils.quote(self.calendar_id, safe="")
        )
        
        try:
            response = requests.get(
                url,
                headers={"Authorization": f"Bearer {access_token}"},
                params=params,
                timeout=20,
            )
        except requests.RequestException as exc:
            raise GoogleCalendarServiceAccountError(
                f"Could not reach Google Calendar: {exc}"
            ) from exc
        
        if not response.ok:
            raise GoogleCalendarServiceAccountError(
                f"Failed to fetch events: {response.text or response.status_code}"
            )
        
        try:
            payload = response.json()
        except json.JSONDecodeError as exc:
            raise GoogleCalendarServiceAccountError(
                f"Invalid JSON response from Calendar API: {exc}"
            ) from exc
        
        return payload.get("items", [])
    
    def get_event(self, event_id: str) -> Dict[str, Any]:
        """
        Fetch a single Google Calendar event.
        
        Args:
            event_id: The calendar event ID
            
        Returns:
            Calendar event dictionary
        """
        access_token = self._get_access_token()
        
        url = f"{self.EVENTS_URL_TEMPLATE.format(calendar_id=requests.utils.quote(self.calendar_id, safe=''))}/{event_id}"
        
        try:
            response = requests.get(
                url,
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=20,
            )
        except requests.RequestException as exc:
            raise GoogleCalendarServiceAccountError(
                f"Could not reach Google Calendar: {exc}"
            ) from exc
        
        if not response.ok:
            raise GoogleCalendarServiceAccountError(
                f"Failed to fetch event {event_id}: {response.text or response.status_code}"
            )
        
        return response.json()
    
    def create_event(
        self,
        summary: str,
        start_time: datetime,
        end_time: datetime,
        description: str = "",
        location: str = "",
        attendees: Optional[List[Dict[str, str]]] = None,
        timezone: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Create a new calendar event.
        
        Args:
            summary: Event title
            start_time: Event start datetime
            end_time: Event end datetime
            description: Event description
            location: Event location
            attendees: List of attendee dicts with 'email' and optional 'displayName'
            timezone: Timezone name (defaults to default_timezone)
            
        Returns:
            Created event dictionary
        """
        access_token = self._get_access_token()
        timezone_name = timezone or self.default_timezone
        
        payload: Dict[str, Any] = {
            "summary": summary,
            "start": {
                "dateTime": start_time.isoformat(),
                "timeZone": timezone_name,
            },
            "end": {
                "dateTime": end_time.isoformat(),
                "timeZone": timezone_name,
            },
        }
        
        if description:
            payload["description"] = description
        
        if location:
            payload["location"] = location
        
        if attendees:
            payload["attendees"] = attendees
        
        url = self.EVENTS_URL_TEMPLATE.format(
            calendar_id=requests.utils.quote(self.calendar_id, safe="")
        )
        
        try:
            response = requests.post(
                url,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                },
                params={"sendUpdates": "all"},
                json=payload,
                timeout=20,
            )
        except requests.RequestException as exc:
            raise GoogleCalendarServiceAccountError(
                f"Could not reach Google Calendar: {exc}"
            ) from exc
        
        if not response.ok:
            raise GoogleCalendarServiceAccountError(
                f"Failed to create event: {response.text or response.status_code}"
            )
        
        return response.json()
    
    def update_event(
        self,
        event_id: str,
        summary: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        description: Optional[str] = None,
        location: Optional[str] = None,
        timezone: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Update an existing calendar event.
        
        Args:
            event_id: The calendar event ID to update
            summary: New event title (optional)
            start_time: New start datetime (optional)
            end_time: New end datetime (optional)
            description: New description (optional)
            location: New location (optional)
            timezone: Timezone name (optional)
            
        Returns:
            Updated event dictionary
        """
        access_token = self._get_access_token()
        
        # Fetch existing event first
        existing = self.get_event(event_id)
        
        # Build update payload
        payload: Dict[str, Any] = {}
        
        if summary is not None:
            payload["summary"] = summary
        
        if start_time is not None:
            tz = timezone or existing.get("start", {}).get("timeZone") or self.default_timezone
            payload["start"] = {
                "dateTime": start_time.isoformat(),
                "timeZone": tz,
            }
        
        if end_time is not None:
            tz = timezone or existing.get("end", {}).get("timeZone") or self.default_timezone
            payload["end"] = {
                "dateTime": end_time.isoformat(),
                "timeZone": tz,
            }
        
        if description is not None:
            payload["description"] = description
        
        if location is not None:
            payload["location"] = location
        
        url = f"{self.EVENTS_URL_TEMPLATE.format(calendar_id=requests.utils.quote(self.calendar_id, safe=''))}/{event_id}"
        
        try:
            response = requests.patch(
                url,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=20,
            )
        except requests.RequestException as exc:
            raise GoogleCalendarServiceAccountError(
                f"Could not reach Google Calendar: {exc}"
            ) from exc
        
        if not response.ok:
            raise GoogleCalendarServiceAccountError(
                f"Failed to update event {event_id}: {response.text or response.status_code}"
            )
        
        return response.json()
    
    def delete_event(self, event_id: str) -> None:
        """
        Delete a calendar event.
        
        Args:
            event_id: The calendar event ID to delete
        """
        access_token = self._get_access_token()
        
        url = f"{self.EVENTS_URL_TEMPLATE.format(calendar_id=requests.utils.quote(self.calendar_id, safe=''))}/{event_id}"
        
        try:
            response = requests.delete(
                url,
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=20,
            )
        except requests.RequestException as exc:
            raise GoogleCalendarServiceAccountError(
                f"Could not reach Google Calendar: {exc}"
            ) from exc
        
        if not response.ok and response.status_code != 404:
            raise GoogleCalendarServiceAccountError(
                f"Failed to delete event {event_id}: {response.text or response.status_code}"
            )


def create_client_from_env() -> Optional[GoogleServiceAccountCalendarClient]:
    """
    Create a service account calendar client from environment variables.
    
    Required environment variables:
        - MIRROR_TALK_GOOGLE_SERVICE_ACCOUNT_FILE: Path to service account JSON key
        - MIRROR_TALK_GOOGLE_CALENDAR_ID: Calendar ID
    
    Returns:
        GoogleServiceAccountCalendarClient instance or None if not configured
    """
    import os
    
    service_account_file = os.environ.get("MIRROR_TALK_GOOGLE_SERVICE_ACCOUNT_FILE", "").strip()
    calendar_id = os.environ.get("MIRROR_TALK_GOOGLE_CALENDAR_ID", "").strip()
    
    if not service_account_file or not calendar_id:
        return None
    
    return GoogleServiceAccountCalendarClient(
        service_account_file=service_account_file,
        calendar_id=calendar_id,
    )
