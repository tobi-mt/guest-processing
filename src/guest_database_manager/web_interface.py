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
from dataclasses import dataclass
from email.parser import BytesParser
from email.policy import default
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import StringIO
from pathlib import Path
from typing import Any, Dict, Optional

from guest_database_manager.constants import DEFAULT_DB_PATH
from guest_database_manager.database import GuestDatabase
from guest_database_manager.email_manager import EmailManager

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
EMAIL_FROM_ENV_VAR = "MIRROR_TALK_FROM_EMAIL"
EMAIL_FROM_NAME_ENV_VAR = "MIRROR_TALK_FROM_NAME"
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
            "email_enabled": self._build_email_manager().is_configured(),
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

    def create_guest(self, payload: Dict[str, Any], source_name: str = FORM_SOURCE_NAME) -> Dict[str, Any]:
        """Create a guest directly from the web form."""
        guest_data = build_guest_payload(payload, source_name=source_name)
        guest_id = self.database.insert_guest(guest_data)
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

        if normalized_status == "accepted":
            sent = email_manager.send_acceptance_email(guest_name, guest_email, custom_message)
            if sent:
                self.database.accept_guest_with_email(guest_id, custom_message)
        else:
            sent = email_manager.send_rejection_email(guest_name, guest_email, custom_message)
            if sent:
                self.database.reject_guest_with_email(guest_id, custom_message)

        if not sent:
            raise WebInterfaceError("The email could not be sent. Please check the server email configuration.")

        updated_guest = self.database.get_guest_by_id(guest_id)
        if not updated_guest:
            raise WebInterfaceError("Guest not found after email send.")
        return serialize_guest(updated_guest)

    def delete_guest(self, guest_id: int) -> Dict[str, Any]:
        """Delete a guest and return a small confirmation payload."""
        self.database.delete_guest(guest_id)
        return {"deleted": True, "id": guest_id}

    def _build_email_manager(self) -> EmailManager:
        """Build an email manager from environment configuration for the hosted dashboard."""
        email_manager = EmailManager()
        email_manager.smtp_server = None
        email_manager.smtp_port = None
        email_manager.username = None
        email_manager.password = None
        email_manager.from_email = None
        email_manager.from_name = None
        smtp_server = os.environ.get(EMAIL_SMTP_SERVER_ENV_VAR, "").strip()
        smtp_username = os.environ.get(EMAIL_USERNAME_ENV_VAR, "").strip()
        smtp_password = os.environ.get(EMAIL_PASSWORD_ENV_VAR, "").strip()
        from_email = os.environ.get(EMAIL_FROM_ENV_VAR, "").strip()

        if smtp_server and smtp_username and smtp_password and from_email:
            smtp_port_raw = os.environ.get(EMAIL_SMTP_PORT_ENV_VAR, "587").strip() or "587"
            from_name = os.environ.get(EMAIL_FROM_NAME_ENV_VAR, "Mirror Talk Podcast").strip()
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
                guest = self.service.send_guest_decision_email(
                    guest_id,
                    payload.get("status", ""),
                    payload.get("custom_message", ""),
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
