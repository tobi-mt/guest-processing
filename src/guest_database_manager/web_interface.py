"""Lightweight web interface with a static frontend and JSON API."""

from __future__ import annotations

import json
import mimetypes
import os
import re
import webbrowser
from base64 import b64decode
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Optional

from guest_database_manager.constants import DEFAULT_DB_PATH
from guest_database_manager.database import GuestDatabase

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
        }

    def create_guest(self, payload: Dict[str, Any], source_name: str = FORM_SOURCE_NAME) -> Dict[str, Any]:
        """Create a guest directly from the web form."""
        guest_data = build_guest_payload(payload, source_name=source_name)
        guest_id = self.database.insert_guest(guest_data)
        guest = self.database.get_guest_by_id(guest_id)
        return serialize_guest(guest) if guest else {"id": guest_id}

    def create_intake_submission(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Create a guest submission from the public intake questionnaire."""
        return self.create_guest(payload, source_name=INTAKE_SOURCE_NAME)

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

    def delete_guest(self, guest_id: int) -> Dict[str, Any]:
        """Delete a guest and return a small confirmation payload."""
        self.database.delete_guest(guest_id)
        return {"deleted": True, "id": guest_id}


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
