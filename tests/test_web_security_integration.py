"""HTTP-level authentication, authorization, CSRF, and header regression tests."""

from __future__ import annotations

from contextlib import contextmanager
import json
from threading import Thread
from unittest.mock import patch

import requests

from guest_database_manager.web_interface import (
    DASHBOARD_PASSWORD_ENV_VAR,
    DASHBOARD_ROLE_ENV_VAR,
    DASHBOARD_SESSION_SECRET_ENV_VAR,
    DASHBOARD_USERNAME_ENV_VAR,
    DASHBOARD_USERS_ENV_VAR,
    create_web_server,
)


@contextmanager
def running_server(db_path):
    # Avoid environment DNS delays from HTTPServer's cosmetic server-name lookup.
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


def configure_auth(monkeypatch, *, role="admin"):
    monkeypatch.setenv(DASHBOARD_USERNAME_ENV_VAR, "producer")
    monkeypatch.setenv(DASHBOARD_PASSWORD_ENV_VAR, "correct horse")
    monkeypatch.setenv(DASHBOARD_SESSION_SECRET_ENV_VAR, "integration-signing-secret")
    monkeypatch.setenv(DASHBOARD_ROLE_ENV_VAR, role)


def login(session, base_url):
    return session.post(
        f"{base_url}/api/dashboard/login",
        json={"username": "producer", "password": "correct horse"},
        timeout=5,
    )


def test_login_issues_signed_session_and_security_headers(monkeypatch, temp_db):
    configure_auth(monkeypatch)
    with running_server(temp_db.db_path) as base_url:
        session = requests.Session()
        response = login(session, base_url)

        assert response.status_code == 200
        assert session.cookies.get("dashboard_session")
        assert session.cookies.get("dashboard_csrf")
        assert response.headers["X-Frame-Options"] == "DENY"
        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert "frame-ancestors 'none'" in response.headers["Content-Security-Policy"]


def test_health_and_readiness_are_public_and_truthful(monkeypatch, temp_db):
    configure_auth(monkeypatch)
    with running_server(temp_db.db_path) as base_url:
        health = requests.get(f"{base_url}/healthz", timeout=5)
        readiness = requests.get(f"{base_url}/readyz", timeout=5)

        assert health.status_code == 200
        assert health.json()["status"] == "ok"
        assert readiness.status_code == 200
        assert readiness.json()["status"] == "ready"


def test_cookie_authenticated_write_requires_matching_csrf(monkeypatch, temp_db):
    configure_auth(monkeypatch)
    with running_server(temp_db.db_path) as base_url:
        session = requests.Session()
        assert login(session, base_url).status_code == 200

        rejected = session.post(
            f"{base_url}/api/guests",
            json={"full_name": "Protected Guest", "email": "protected@example.com"},
            timeout=5,
        )
        assert rejected.status_code == 403

        accepted = session.post(
            f"{base_url}/api/guests",
            json={"full_name": "Protected Guest", "email": "protected@example.com"},
            headers={"X-CSRF-Token": session.cookies["dashboard_csrf"]},
            timeout=5,
        )
        assert accepted.status_code == 201


def test_operator_can_reject_scheduling_recommendation_with_audited_reason(monkeypatch, temp_db):
    configure_auth(monkeypatch, role="operator")
    episode_id, _ = temp_db.upsert_episode(
        {
            "guest_name": "HTTP Feedback Guest",
            "episode_title": "HTTP Feedback Episode",
            "production_status": "ready",
            "promotion_status": "ready",
        }
    )
    with running_server(temp_db.db_path) as base_url:
        session = requests.Session()
        assert login(session, base_url).status_code == 200
        response = session.post(
            f"{base_url}/api/episodes/{episode_id}/recommendation-feedback",
            json={
                "action": "rejected",
                "reason": "Too similar to a recent episode",
                "idempotency_key": "http-reject-1",
            },
            headers={"X-CSRF-Token": session.cookies["dashboard_csrf"]},
            timeout=5,
        )

        assert response.status_code == 200
        assert response.json()["state"] == "rejected"
        planning = session.get(f"{base_url}/api/planning", timeout=5).json()
        assert episode_id not in {item["id"] for item in planning["recommendations"]}
        assert episode_id in {item["id"] for item in planning["rejected_recommendations"]}
        event = temp_db.list_audit_events("episode", episode_id)[0]
        assert event["event_type"] == "recommendation_rejected"
        assert event["actor"] == "producer"


def test_versioned_assets_cache_but_private_api_does_not(monkeypatch, temp_db):
    configure_auth(monkeypatch)
    with running_server(temp_db.db_path) as base_url:
        session = requests.Session()
        assert login(session, base_url).status_code == 200

        asset = session.get(f"{base_url}/static/app.js?v=contract-test", timeout=5)
        private_api = session.get(f"{base_url}/api/guests?skip_enrichment=true", timeout=5)

        assert asset.status_code == 200
        assert "immutable" in asset.headers["Cache-Control"]
        assert private_api.status_code == 200
        assert "no-store" in private_api.headers["Cache-Control"]


def test_viewer_session_cannot_write(monkeypatch, temp_db):
    configure_auth(monkeypatch, role="viewer")
    with running_server(temp_db.db_path) as base_url:
        session = requests.Session()
        assert login(session, base_url).status_code == 200

        response = session.post(
            f"{base_url}/api/guests",
            json={"full_name": "Blocked Guest"},
            headers={"X-CSRF-Token": session.cookies["dashboard_csrf"]},
            timeout=5,
        )
        assert response.status_code == 403
        assert "permissions" in response.json()["error"].lower()


def test_multi_user_roles_are_resolved_per_identity(monkeypatch, temp_db):
    monkeypatch.delenv(DASHBOARD_USERNAME_ENV_VAR, raising=False)
    monkeypatch.delenv(DASHBOARD_PASSWORD_ENV_VAR, raising=False)
    monkeypatch.setenv(DASHBOARD_SESSION_SECRET_ENV_VAR, "integration-signing-secret")
    monkeypatch.setenv(
        DASHBOARD_USERS_ENV_VAR,
        json.dumps(
            {
                "assistant": {"password": "read only", "role": "viewer"},
                "producer": {"password": "can operate", "role": "operator"},
            }
        ),
    )
    with running_server(temp_db.db_path) as base_url:
        viewer = requests.Session()
        operator = requests.Session()
        assert viewer.post(
            f"{base_url}/api/dashboard/login",
            json={"username": "assistant", "password": "read only"},
            timeout=5,
        ).status_code == 200
        assert operator.post(
            f"{base_url}/api/dashboard/login",
            json={"username": "producer", "password": "can operate"},
            timeout=5,
        ).status_code == 200

        viewer_write = viewer.post(
            f"{base_url}/api/guests",
            json={"full_name": "Viewer Blocked"},
            headers={"X-CSRF-Token": viewer.cookies["dashboard_csrf"]},
            timeout=5,
        )
        operator_write = operator.post(
            f"{base_url}/api/guests",
            json={"full_name": "Assigned Guest", "owner": "producer"},
            headers={"X-CSRF-Token": operator.cookies["dashboard_csrf"]},
            timeout=5,
        )

        assert viewer_write.status_code == 403
        assert operator_write.status_code == 201
