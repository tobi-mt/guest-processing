"""End-to-end HTTP regression coverage for the public intake workflow."""

from __future__ import annotations

from contextlib import contextmanager
from threading import Thread
from unittest.mock import patch

import requests

from guest_database_manager.web_interface import API_TOKEN_ENV_VAR, create_web_server


VALID_SELF_APPLICATION = {
    "application_role": "self",
    "self_attestation": "yes",
    "full_name": "HTTP Intake Guest",
    "email": "http-intake-guest@example.test",
    "website": "www.http-intake.example",
    "background": "I am a speaker and advocate whose work centers on healing, resilience, and community storytelling.",
    "profession": "Coach",
    "motivation": "Helping people find hope and language for difficult seasons motivates my work and life.",
    "life_experiences": "Grief, recovery, and rebuilding community after loss shaped my commitment to honest healing.",
    "core_values": "Compassion, courage, curiosity, and integrity guide my decisions and relationships.",
    "alignment": "Yes — I believe honest, reflective conversations help people feel seen and less alone.",
    "passionate_topics": "Healing",
    "message": "Hope",
    "experience": "Yes — I have spoken on podcasts, panels, and community events about resilience and healing.",
    "additional_info": "I would be grateful to contribute a grounded, encouraging conversation for your listeners.",
    "social_handles": "Instagram: @httpintakeguest",
}


@contextmanager
def running_public_intake_server(db_path):
    """Run a real ephemeral server without DNS lookups during the test."""
    with patch("socket.getfqdn", return_value="localhost"):
        server = create_web_server(host="127.0.0.1", port=0, db_path=db_path)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_public_intake_http_workflow_serves_page_submits_and_persists(temp_db, monkeypatch):
    """A browser-equivalent request must complete the full public self-intake flow."""
    monkeypatch.delenv(API_TOKEN_ENV_VAR, raising=False)
    with running_public_intake_server(temp_db.db_path) as base_url:
        page = requests.get(f"{base_url}/intake", timeout=5)
        submission = requests.post(f"{base_url}/api/intake", json=VALID_SELF_APPLICATION, timeout=5)

    assert page.status_code == 200
    assert 'src="/static/intake.js?v=20260925.2"' in page.text
    assert submission.status_code == 201
    body = submission.json()
    assert body["message"] == "Thank you for applying. Your submission has been received."
    assert body["guest"]["full_name"] == VALID_SELF_APPLICATION["full_name"]
    assert body["guest"]["website"] == "https://www.http-intake.example"
    assert temp_db.get_guest_by_id(body["guest"]["id"])["email"] == VALID_SELF_APPLICATION["email"]


def test_public_intake_http_workflow_rejects_incomplete_payload_without_persisting(temp_db, monkeypatch):
    """Server-side validation remains authoritative if client-side JavaScript is bypassed."""
    monkeypatch.delenv(API_TOKEN_ENV_VAR, raising=False)
    incomplete = dict(VALID_SELF_APPLICATION)
    incomplete.pop("motivation")
    with running_public_intake_server(temp_db.db_path) as base_url:
        response = requests.post(f"{base_url}/api/intake", json=incomplete, timeout=5)

    assert response.status_code == 400
    assert response.json()["error"] == "Please complete the required field: motivation"
    assert temp_db.get_all_guests() == []


def test_public_intake_accepts_application_without_public_profiles(temp_db, monkeypatch):
    """Editorially useful applicants must not be excluded for lacking a website or social profile."""
    monkeypatch.delenv(API_TOKEN_ENV_VAR, raising=False)
    application = dict(VALID_SELF_APPLICATION)
    application.pop("website")
    application.pop("social_handles")
    application["email"] = "private-intake-guest@example.test"

    with running_public_intake_server(temp_db.db_path) as base_url:
        response = requests.post(f"{base_url}/api/intake", json=application, timeout=5)

    assert response.status_code == 201
    assert response.json()["guest"]["website"] == ""


def test_public_intake_accepts_concise_optional_boundaries_and_experience(temp_db, monkeypatch):
    """Optional context must not be subject to hidden essay-length requirements."""
    monkeypatch.delenv(API_TOKEN_ENV_VAR, raising=False)
    application = dict(VALID_SELF_APPLICATION)
    application.update(
        email="concise-optional@example.test",
        experience="First timer",
        additional_info="No politics",
    )

    with running_public_intake_server(temp_db.db_path) as base_url:
        response = requests.post(f"{base_url}/api/intake", json=application, timeout=5)

    assert response.status_code == 201
    assert response.json()["guest"]["additional_info"] == "No politics"


def test_public_intake_rejects_malformed_and_non_object_json_cleanly(temp_db, monkeypatch):
    """Broken clients should receive stable 400 responses instead of dropped connections."""
    monkeypatch.delenv(API_TOKEN_ENV_VAR, raising=False)
    with running_public_intake_server(temp_db.db_path) as base_url:
        malformed = requests.post(
            f"{base_url}/api/intake",
            data=b'{"application_role":',
            headers={"Content-Type": "application/json"},
            timeout=5,
        )
        non_object = requests.post(f"{base_url}/api/intake", json=["not", "an", "application"], timeout=5)

    assert malformed.status_code == 400
    assert malformed.json() == {"error": "Please submit a valid application request."}
    assert non_object.status_code == 400
    assert non_object.json() == {"error": "Please submit the application as a JSON object."}


def test_public_intake_rejects_oversized_request_before_processing(temp_db, monkeypatch):
    """The public endpoint must cap memory use from unexpectedly large requests."""
    monkeypatch.delenv(API_TOKEN_ENV_VAR, raising=False)
    oversized = {"application_role": "self", "background": "x" * (129 * 1024)}

    with running_public_intake_server(temp_db.db_path) as base_url:
        response = requests.post(f"{base_url}/api/intake", json=oversized, timeout=5)

    assert response.status_code == 400
    assert "too large" in response.json()["error"].lower()
    assert temp_db.get_all_guests() == []


def test_public_intake_http_workflow_requires_token_when_configured(temp_db, monkeypatch):
    """Public intake cannot be posted cross-site when token protection is enabled."""
    monkeypatch.setenv(API_TOKEN_ENV_VAR, "intake-test-token")
    with running_public_intake_server(temp_db.db_path) as base_url:
        rejected = requests.post(f"{base_url}/api/intake", json=VALID_SELF_APPLICATION, timeout=5)
        accepted = requests.post(
            f"{base_url}/api/intake",
            json=VALID_SELF_APPLICATION,
            headers={"X-Api-Token": "intake-test-token"},
            timeout=5,
        )

    assert rejected.status_code == 401
    assert rejected.json() == {"error": "Unauthorized intake request"}
    assert accepted.status_code == 201
