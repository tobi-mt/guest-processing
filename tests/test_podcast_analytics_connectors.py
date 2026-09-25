import hashlib
import sqlite3
from urllib.parse import parse_qs, urlsplit

import pytest

from guest_database_manager.podcast_analytics_connectors import (
    AnalyticsConnectorError,
    GA4_PROPERTY_ENV,
    GOOGLE_CLIENT_ID_ENV,
    GOOGLE_CLIENT_SECRET_ENV,
    TOKEN_KEY_ENV,
    PodcastAnalyticsConnectors,
)


def _configure(monkeypatch):
    monkeypatch.setenv(GOOGLE_CLIENT_ID_ENV, "client-id")
    monkeypatch.setenv(GOOGLE_CLIENT_SECRET_ENV, "client-secret")
    monkeypatch.setenv(TOKEN_KEY_ENV, "a-dedicated-test-encryption-secret-with-entropy")
    monkeypatch.setenv(GA4_PROPERTY_ENV, "123456")


def test_google_connection_requires_production_configuration(temp_db):
    connectors = PodcastAnalyticsConnectors(temp_db.db_path)

    assert connectors.status()["google"]["oauth_configured"] is False
    with pytest.raises(AnalyticsConnectorError, match="not configured"):
        connectors.begin_google(actor="admin", origin="https://example.test")


def test_google_oauth_state_is_hashed_short_lived_and_one_time(temp_db, monkeypatch):
    _configure(monkeypatch)
    connectors = PodcastAnalyticsConnectors(temp_db.db_path)
    authorization = connectors.begin_google(actor="admin", origin="https://example.test")
    query = parse_qs(urlsplit(authorization["authorization_url"]).query)
    state = query["state"][0]

    with sqlite3.connect(temp_db.db_path) as conn:
        saved = conn.execute("SELECT state_hash, actor, code_verifier_ciphertext, consumed_at FROM analytics_oauth_states").fetchone()
    assert saved[0] == hashlib.sha256(state.encode()).hexdigest()
    assert saved[1] == "admin"
    assert saved[2]
    assert saved[3] is None
    assert state not in saved[0]

    monkeypatch.setattr(connectors, "_post_form", lambda *args, **kwargs: {
        "refresh_token": "durable-refresh-token", "access_token": "access", "scope": "openid email"
    })
    monkeypatch.setattr(connectors, "_get_json", lambda *args: {"sub": "account-1", "email": "owner@example.test"})
    result = connectors.complete_google(state=state, code="code", origin="https://example.test")
    assert result["status"] == "connected"

    with sqlite3.connect(temp_db.db_path) as conn:
        ciphertext, email = conn.execute(
            "SELECT refresh_token_ciphertext, account_email FROM analytics_oauth_connections"
        ).fetchone()
    assert ciphertext != "durable-refresh-token"
    assert "durable-refresh-token" not in ciphertext
    assert email == "owner@example.test"
    with pytest.raises(AnalyticsConnectorError, match="already used|invalid or expired"):
        connectors.complete_google(state=state, code="code", origin="https://example.test")


def test_google_sync_is_idempotent_and_updates_health(temp_db, monkeypatch):
    _configure(monkeypatch)
    connectors = PodcastAnalyticsConnectors(temp_db.db_path)
    encrypted = connectors._cipher().encrypt(b"refresh").decode()
    with sqlite3.connect(temp_db.db_path) as conn:
        conn.execute(
            """INSERT INTO analytics_oauth_connections
               (provider, refresh_token_ciphertext, status, connected_at, updated_at)
               VALUES ('google', ?, 'connected', '2026-09-25T00:00:00Z', '2026-09-25T00:00:00Z')""",
            (encrypted,),
        )
        conn.commit()
    monkeypatch.setattr(connectors, "_refresh_access_token", lambda token: "access")
    monkeypatch.setattr(connectors, "_collect_google", lambda token: [{
        "provider": "youtube", "metric_name": "plays", "metric_value": 42,
        "period_start": "2026-08-01", "period_end": "2026-08-28",
        "traffic_scope": "all", "source_reference": "youtube-analytics-api",
    }])

    first = connectors.sync_google(actor="automation", force=True)
    second = connectors.sync_google(actor="automation", force=True)

    assert first["inserted"] == 1
    assert second["inserted"] == 0
    assert second["duplicates"] == 1
    status = connectors.status()["google"]["connection"]
    assert status["status"] == "connected"
    assert status["last_success_at"]
    assert "refresh_token_ciphertext" not in status


def test_disconnect_deletes_retained_token_even_if_remote_revoke_fails(temp_db, monkeypatch):
    _configure(monkeypatch)
    connectors = PodcastAnalyticsConnectors(temp_db.db_path)
    encrypted = connectors._cipher().encrypt(b"refresh").decode()
    with sqlite3.connect(temp_db.db_path) as conn:
        conn.execute(
            """INSERT INTO analytics_oauth_connections
               (provider, refresh_token_ciphertext, status, connected_at, updated_at)
               VALUES ('google', ?, 'connected', '2026-09-25T00:00:00Z', '2026-09-25T00:00:00Z')""",
            (encrypted,),
        )
        conn.commit()
    monkeypatch.setattr(connectors, "_post_form", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("offline")))

    assert connectors.disconnect_google()["status"] == "disconnected"
    with sqlite3.connect(temp_db.db_path) as conn:
        token, status = conn.execute(
            "SELECT refresh_token_ciphertext, status FROM analytics_oauth_connections"
        ).fetchone()
    assert token == ""
    assert status == "disconnected"


def test_google_collector_keeps_platform_metrics_source_backed(temp_db, monkeypatch):
    _configure(monkeypatch)
    connectors = PodcastAnalyticsConnectors(temp_db.db_path)

    def google_response(url, _token):
        if "youtubeanalytics" in url and "dimensions=deviceType" in url:
            return {"rows": [["MOBILE", 70], ["DESKTOP", 30]]}
        if "youtubeanalytics" in url and "dimensions=country" in url:
            return {"rows": [["DE", 60]]}
        if "youtubeanalytics" in url:
            return {"rows": [[100, 120, 72]]}
        if "youtube/v3/channels" in url:
            return {"items": [{"statistics": {"subscriberCount": "2500"}}]}
        raise AssertionError(url)

    monkeypatch.setattr(connectors, "_get_json", google_response)
    monkeypatch.setattr(connectors, "_ga4_report", lambda token, property_id, start, end, dimensions, metrics: (
        {"rows": [{"dimensionValues": [{"value": "mobile"}], "metricValues": [{"value": "25"}]}]}
        if dimensions else {"rows": [{"metricValues": [{"value": "40"}]}]}
    ))

    observations = connectors._collect_google("access")
    values = {(row["provider"], row["metric_name"]): float(row["metric_value"]) for row in observations}

    assert values[("youtube", "plays")] == 100
    assert values[("youtube", "watch_time_hours")] == 2
    assert values[("youtube", "subscribers")] == 2500
    assert values[("youtube", "device_mobile")] == 70
    assert values[("website", "organic_reach")] == 40
    assert values[("website", "device_mobile")] == 25
