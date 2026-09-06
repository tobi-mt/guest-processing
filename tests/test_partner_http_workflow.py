"""Browser-equivalent HTTP coverage for the complete Partner Intelligence workflow."""

from __future__ import annotations

from contextlib import contextmanager
from threading import Thread
from unittest.mock import patch

import requests

from guest_database_manager.web_interface import (
    DASHBOARD_PASSWORD_ENV_VAR,
    DASHBOARD_ROLE_ENV_VAR,
    DASHBOARD_SESSION_SECRET_ENV_VAR,
    DASHBOARD_USERNAME_ENV_VAR,
    OPENAI_API_KEY_ENV_VAR,
    create_web_server,
)


@contextmanager
def running_server(db_path):
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


def authenticated_session(monkeypatch, base_url):
    monkeypatch.setenv(DASHBOARD_USERNAME_ENV_VAR, "partner-tester")
    monkeypatch.setenv(DASHBOARD_PASSWORD_ENV_VAR, "local-password")
    monkeypatch.setenv(DASHBOARD_SESSION_SECRET_ENV_VAR, "partner-test-secret")
    monkeypatch.setenv(DASHBOARD_ROLE_ENV_VAR, "admin")
    session = requests.Session()
    response = session.post(
        f"{base_url}/api/dashboard/login",
        json={"username": "partner-tester", "password": "local-password"},
        timeout=5,
    )
    assert response.status_code == 200
    return session, {"X-CSRF-Token": session.cookies["dashboard_csrf"]}


def post(session, base_url, path, payload, headers):
    return session.post(f"{base_url}{path}", json=payload, headers=headers, timeout=5)


def test_partner_http_workflow_reaches_idempotent_outbox_only_after_approval(monkeypatch, temp_db):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv(OPENAI_API_KEY_ENV_VAR, raising=False)
    monkeypatch.setenv(DASHBOARD_USERNAME_ENV_VAR, "partner-tester")
    monkeypatch.setenv(DASHBOARD_PASSWORD_ENV_VAR, "local-password")
    monkeypatch.setenv(DASHBOARD_SESSION_SECRET_ENV_VAR, "partner-test-secret")
    monkeypatch.setenv(DASHBOARD_ROLE_ENV_VAR, "admin")
    with running_server(temp_db.db_path) as base_url:
        session, headers = authenticated_session(monkeypatch, base_url)
        page = session.get(f"{base_url}/partners", timeout=5)
        assert page.status_code == 200
        assert 'id="partner-stage-filters"' in page.text
        assert 'id="clear-partner-filters"' in page.text

        created = post(session, base_url, "/api/partners", {
            "organisation_name": "HTTP Hope Press",
            "website": "https://hope.example",
            "partner_type": "author_publisher",
            "research_summary": "A current resilience publishing programme.",
        }, headers)
        assert created.status_code == 201
        prospect_id = created.json()["id"]

        missing_csrf = session.post(
            f"{base_url}/api/partners/{prospect_id}/contact",
            json={"contact_name": "Ava Stone", "contact_email": "ava@hope.example"},
            timeout=5,
        )
        assert missing_csrf.status_code == 403

        contact = post(session, base_url, f"/api/partners/{prospect_id}/contact", {
            "contact_name": "Ava Stone", "contact_email": "ava@hope.example",
        }, headers)
        assert contact.status_code == 200
        assert contact.json()["readiness"]["needs_contact_research"] is True

        contact_research = post(session, base_url, f"/api/partners/{prospect_id}/contact-research", {
            "contact_name": "Ava Stone",
            "source_url": "https://hope.example/team",
            "source_title": "Team",
            "fact_text": "Ava leads the publisher's current partnership programme.",
        }, headers)
        assert contact_research.status_code == 200

        for source_url, title, fact in (
            ("https://hope.example/news", "Launch", "Hope Press launched a current resilience programme."),
            ("https://coverage.example/hope", "Independent coverage", "Independent coverage confirms the publishing programme."),
        ):
            evidence = post(session, base_url, f"/api/partners/{prospect_id}/evidence", {
                "source_url": source_url, "source_title": title, "fact_text": fact,
            }, headers)
            assert evidence.status_code == 200

        drafted = post(session, base_url, f"/api/partners/{prospect_id}/draft", {
            "template_id": "co_marketing", "tone": "warm",
        }, headers)
        assert drafted.status_code == 200
        drafts = [item for item in drafted.json()["drafts"] if item["status"] == "draft"]
        assert len(drafts) == 3
        draft_id = drafts[0]["id"]

        premature = post(session, base_url, f"/api/partner-pitches/{draft_id}/handoff", {}, headers)
        assert premature.status_code == 400
        assert "Approve this draft" in premature.json()["error"]
        assert temp_db.get_email_outbox_count() == 0

        selected = post(session, base_url, f"/api/partner-pitches/{draft_id}/select", {}, headers)
        assert selected.status_code == 200
        assert len([item for item in selected.json()["drafts"] if item["status"] == "retired"]) == 2

        queued = post(session, base_url, f"/api/partner-pitches/{draft_id}/approve-handoff", {}, headers)
        assert queued.status_code == 200
        assert temp_db.get_email_outbox_count() == 1
        assert next(item for item in queued.json()["drafts"] if item["id"] == draft_id)["outbox_id"]

        repeated = post(session, base_url, f"/api/partner-pitches/{draft_id}/handoff", {}, headers)
        assert repeated.status_code == 200
        assert temp_db.get_email_outbox_count() == 1


def test_partner_http_api_rejects_invalid_inputs_without_partial_records(monkeypatch, temp_db):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv(OPENAI_API_KEY_ENV_VAR, raising=False)
    monkeypatch.setenv(DASHBOARD_USERNAME_ENV_VAR, "partner-tester")
    monkeypatch.setenv(DASHBOARD_PASSWORD_ENV_VAR, "local-password")
    monkeypatch.setenv(DASHBOARD_SESSION_SECRET_ENV_VAR, "partner-test-secret")
    monkeypatch.setenv(DASHBOARD_ROLE_ENV_VAR, "admin")
    with running_server(temp_db.db_path) as base_url:
        session, headers = authenticated_session(monkeypatch, base_url)
        invalid = post(session, base_url, "/api/partners", {
            "organisation_name": "Broken Partner",
            "website": "javascript:alert(1)",
            "partner_type": "not-a-real-type",
        }, headers)
        assert invalid.status_code == 400
        partners = session.get(f"{base_url}/api/partners", timeout=5)
        assert partners.status_code == 200
        assert partners.json()["prospects"] == []
