import hashlib
import sqlite3
from datetime import date
from urllib.parse import parse_qs, urlsplit

import pytest

from guest_database_manager.podcast_analytics_connectors import (
    AnalyticsConnectorError,
    COLLECTOR_TOKEN_ENV,
    GA4_PROPERTY_ENV,
    GOOGLE_CLIENT_ID_ENV,
    GOOGLE_CLIENT_SECRET_ENV,
    OPENPODCAST_AUTO_SYNC_ENV,
    OPENPODCAST_PODCAST_ID_ENV,
    OPENPODCAST_TOKEN_ENV,
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


def test_analytics_job_lease_elects_one_replica_and_recovers_after_expiry(temp_db):
    from guest_database_manager.web_interface import GuestWebService

    first = GuestWebService(temp_db.db_path)
    second = GuestWebService(temp_db.db_path)

    assert first._try_acquire_analytics_job_lease(owner_id="replica-a", lease_seconds=300) is True
    assert second._try_acquire_analytics_job_lease(owner_id="replica-b", lease_seconds=300) is False
    with sqlite3.connect(temp_db.db_path) as conn:
        conn.execute(
            "UPDATE analytics_job_leases SET lease_until='2000-01-01T00:00:00Z' "
            "WHERE job_key='podcast-analytics-cycle'"
        )
    assert second._try_acquire_analytics_job_lease(owner_id="replica-b", lease_seconds=300) is True


def test_local_collector_keeps_browser_session_local_and_ingests_validated_export(temp_db, monkeypatch):
    token = "collector-token-with-at-least-thirty-two-characters"
    monkeypatch.setenv(COLLECTOR_TOKEN_ENV, token)
    connectors = PodcastAnalyticsConnectors(temp_db.db_path)

    enabled = connectors.set_local_collector("spotify", enabled=True, actor="admin")
    assert enabled == {"provider": "spotify", "enabled": True, "status": "waiting"}
    csv_text = (
        "Date,Plays & downloads,Plays (on Spotify),Downloads (everywhere else),Audience,"
        "Audience (on Spotify),Audience (everywhere else)\n"
        "9/24/2026,12,9,3,4,2,2"
    )
    result = connectors.ingest_local_export(
        provider="spotify", token=token, csv_text=csv_text,
        source_reference="spotify-overview.csv",
    )

    assert result["inserted"] == 3
    duplicate = connectors.ingest_local_export(
        provider="spotify", token=token, csv_text=csv_text,
        source_reference="spotify-overview.csv",
    )
    assert duplicate["status"] == "completed"
    assert duplicate["inserted"] == 0
    assert duplicate["duplicates"] == 3
    collector = connectors.status()["local_collectors"]
    assert collector["configured"] is True
    assert collector["session_storage"] == "local_only"
    assert collector["connections"]["spotify"]["status"] == "connected"
    assert token not in str(collector)


def test_local_collector_bootstrap_registration_requires_the_ingestion_credential(temp_db, monkeypatch):
    token = "collector-token-with-at-least-thirty-two-characters"
    monkeypatch.setenv(COLLECTOR_TOKEN_ENV, token)
    connectors = PodcastAnalyticsConnectors(temp_db.db_path)

    with pytest.raises(AnalyticsConnectorError, match="credential is invalid"):
        connectors.register_local_collector("spotify", token="wrong")

    registered = connectors.register_local_collector("spotify", token=token)

    assert registered == {"provider": "spotify", "enabled": True, "status": "waiting"}
    connection = connectors.status()["local_collectors"]["connections"]["spotify"]
    assert connection["enabled"] is True
    assert connection["status"] == "waiting"


def test_local_collector_fails_closed_for_bad_token_and_review_rows(temp_db, monkeypatch):
    token = "collector-token-with-at-least-thirty-two-characters"
    monkeypatch.setenv(COLLECTOR_TOKEN_ENV, token)
    connectors = PodcastAnalyticsConnectors(temp_db.db_path)
    connectors.set_local_collector("apple_podcasts", enabled=True, actor="admin")
    with pytest.raises(AnalyticsConnectorError, match="credential is invalid"):
        connectors.ingest_local_export(
            provider="apple_podcasts", token="wrong", csv_text="x", source_reference="x.csv"
        )
    episode_csv = (
        "Show ID,Episode ID,Episode Title,Date,Total Time Listened,Plays,Unique Listeners,"
        "Unique Engaged Listeners\n1518394292,1001,Unknown Episode,20260901,120,7,4,2"
    )
    with pytest.raises(AnalyticsConnectorError, match="require review"):
        connectors.ingest_local_export(
            provider="apple_podcasts", token=token, csv_text=episode_csv,
            source_reference="apple-episodes.csv",
        )
    assert connectors.status()["local_collectors"]["connections"]["apple_podcasts"]["status"] == "error"


def test_local_collector_reports_stale_when_heartbeat_stops(temp_db, monkeypatch):
    token = "collector-token-with-at-least-thirty-two-characters"
    monkeypatch.setenv(COLLECTOR_TOKEN_ENV, token)
    connectors = PodcastAnalyticsConnectors(temp_db.db_path)
    connectors.set_local_collector("spotify", enabled=True, actor="admin")
    with sqlite3.connect(temp_db.db_path) as conn:
        conn.execute(
            """UPDATE analytics_browser_collectors
               SET status = 'connected', last_seen_at = '2026-01-01T00:00:00Z'
               WHERE provider = 'spotify'"""
        )

    assert connectors.status()["local_collectors"]["connections"]["spotify"]["status"] == "stale"


def test_openpodcast_sync_normalizes_show_level_daily_evidence_and_is_idempotent(temp_db, monkeypatch):
    monkeypatch.setenv(OPENPODCAST_TOKEN_ENV, "server-only-openpodcast-token")
    monkeypatch.setenv(OPENPODCAST_PODCAST_ID_ENV, "4501")
    connectors = PodcastAnalyticsConnectors(temp_db.db_path)
    responses = {
        "episodesDailyMetrics": {"data": [
            {"date": "2026-10-01", "spotify_streams": 7, "spotify_listeners": 5,
             "apple_plays": 4, "apple_listeners": 3, "apple_engaged_listeners": 2},
            {"date": "2026-10-01", "spotify_streams": 11, "spotify_listeners": 8,
             "apple_plays": None, "apple_listeners": None, "apple_engaged_listeners": None},
        ]},
        "podcastFollowers": {"data": [{"date": "2026-10-01", "spotify_total_followers": 90,
                                          "apple_total_followers": 40}]},
        "spotifyImpressionsSources": {"data": [
            {"date_start": "2026-10-01", "date_end": "2026-10-07", "source_id": "HOME",
             "impression_count": 120},
        ]},
        "spotifyCountries": {"data": [
            {"spotify_country_shortcode": "DE", "spotify_listeners": "12"},
        ]},
    }

    monkeypatch.setattr(
        connectors, "_get_openpodcast_json",
        lambda url, _token: responses[next(key for key in responses if f"/{key}?" in url)],
    )
    first = connectors.sync_openpodcast(actor="admin", start=__import__("datetime").date(2026, 10, 1),
                                        end=__import__("datetime").date(2026, 10, 7))
    second = connectors.sync_openpodcast(actor="admin", start=__import__("datetime").date(2026, 10, 1),
                                         end=__import__("datetime").date(2026, 10, 7))

    assert first == {"submitted": 6, "inserted": 6, "duplicates": 0, "status": "completed",
                     "period_start": "2026-10-01", "period_end": "2026-10-07"}
    assert second["inserted"] == 0
    assert second["duplicates"] == 6
    with sqlite3.connect(temp_db.db_path) as conn:
        spotify_plays = conn.execute(
            """SELECT metric_value FROM growth_metric_observations
               WHERE provider='spotify' AND metric_name='plays' AND period_end='2026-10-01'"""
        ).fetchone()[0]
        listener_rows = conn.execute(
            """SELECT COUNT(*) FROM growth_metric_observations
               WHERE metric_name IN ('unique_listeners', 'engaged_listeners')"""
        ).fetchone()[0]
    assert spotify_plays == 18
    # Per-episode listener counts are not additive into show-level unique listeners.
    assert listener_rows == 0
    status = connectors.status()["openpodcast"]
    assert status["status"] == "connected"
    assert status["podcast_id"] == "4501"
    assert "server-only-openpodcast-token" not in str(status)


def test_openpodcast_sync_requires_server_configuration(temp_db, monkeypatch):
    monkeypatch.delenv(OPENPODCAST_TOKEN_ENV, raising=False)
    monkeypatch.delenv(OPENPODCAST_PODCAST_ID_ENV, raising=False)
    connectors = PodcastAnalyticsConnectors(temp_db.db_path)

    assert connectors.status()["openpodcast"]["status"] == "not_configured"
    with pytest.raises(AnalyticsConnectorError, match="not configured"):
        connectors.sync_openpodcast(actor="admin")


def test_openpodcast_credentials_do_not_enable_optional_startup_sync(temp_db, monkeypatch):
    monkeypatch.setenv(OPENPODCAST_TOKEN_ENV, "server-only-openpodcast-token")
    monkeypatch.setenv(OPENPODCAST_PODCAST_ID_ENV, "4501")
    monkeypatch.delenv(OPENPODCAST_AUTO_SYNC_ENV, raising=False)
    connectors = PodcastAnalyticsConnectors(temp_db.db_path)

    status = connectors.status()["openpodcast"]

    assert status["configured"] is True
    assert status["auto_sync_enabled"] is False
    assert status["status"] == "manual"
    assert connectors.openpodcast_auto_sync_due() is False


def test_openpodcast_automatic_failure_enters_backoff(temp_db, monkeypatch):
    monkeypatch.setenv(OPENPODCAST_TOKEN_ENV, "server-only-openpodcast-token")
    monkeypatch.setenv(OPENPODCAST_PODCAST_ID_ENV, "4501")
    monkeypatch.setenv(OPENPODCAST_AUTO_SYNC_ENV, "true")
    connectors = PodcastAnalyticsConnectors(temp_db.db_path)
    monkeypatch.setattr(
        connectors, "_get_openpodcast_json",
        lambda *_args: (_ for _ in ()).throw(AnalyticsConnectorError("provider unavailable")),
    )

    assert connectors.openpodcast_auto_sync_due() is True
    with pytest.raises(AnalyticsConnectorError):
        connectors.sync_openpodcast(actor="podcast-analytics-automation")

    assert connectors.status()["openpodcast"]["status"] == "error"
    assert connectors.openpodcast_auto_sync_due() is False


def test_openpodcast_sync_identifies_failing_endpoint_without_exposing_provider_details(temp_db, monkeypatch):
    monkeypatch.setenv(OPENPODCAST_TOKEN_ENV, "server-only-openpodcast-token")
    monkeypatch.setenv(OPENPODCAST_PODCAST_ID_ENV, "4501")
    connectors = PodcastAnalyticsConnectors(temp_db.db_path)

    def provider_response(url, _token):
        if "/podcastFollowers?" in url:
            raise AnalyticsConnectorError("upstream response details")
        return {"data": []}

    monkeypatch.setattr(connectors, "_get_openpodcast_json", provider_response)
    with pytest.raises(
        AnalyticsConnectorError,
        match="endpoint podcastFollowers could not be synchronized",
    ) as failure:
        connectors.sync_openpodcast(
            actor="admin", start=__import__("datetime").date(2026, 10, 1),
            end=__import__("datetime").date(2026, 10, 30),
        )
    assert "upstream response details" not in str(failure.value)
    status = connectors.status()["openpodcast"]
    assert status["status"] == "error"
    assert status["last_error_code"] == "endpoint_failed:podcastFollowers"
    assert status["last_error_at"]
    assert "upstream response details" not in str(status)


def test_openpodcast_rejected_credential_is_reported_without_exposing_it(temp_db, monkeypatch):
    token = "server-only-openpodcast-token"
    monkeypatch.setenv(OPENPODCAST_TOKEN_ENV, token)
    monkeypatch.setenv(OPENPODCAST_PODCAST_ID_ENV, "4501")
    connectors = PodcastAnalyticsConnectors(temp_db.db_path)
    monkeypatch.setattr(
        connectors, "_get_openpodcast_json",
        lambda *_args: (_ for _ in ()).throw(
            AnalyticsConnectorError("OpenPodcast rejected the configured analytics credential.")
        ),
    )

    with pytest.raises(AnalyticsConnectorError, match="episodesDailyMetrics"):
        connectors.sync_openpodcast(actor="admin")

    status = connectors.status()["openpodcast"]
    assert status["status"] == "error"
    assert status["last_error_code"] == "credential_rejected"
    assert token not in str(status)


def test_openpodcast_records_rate_limit_without_upstream_details(temp_db, monkeypatch):
    from urllib.error import HTTPError

    monkeypatch.setenv(OPENPODCAST_TOKEN_ENV, "test-only")
    monkeypatch.setenv(OPENPODCAST_PODCAST_ID_ENV, "4501")
    connectors = PodcastAnalyticsConnectors(temp_db.db_path)

    def rate_limited(*args, **kwargs):
        raise HTTPError("https://example.test", 429, "private response details", {}, None)

    monkeypatch.setattr("guest_database_manager.podcast_analytics_connectors.urlopen", rate_limited)
    with pytest.raises(AnalyticsConnectorError, match="episodesDailyMetrics"):
        connectors.sync_openpodcast(actor="test")
    status = connectors.status()["openpodcast"]
    assert status["last_error_code"] == "http_429:episodesDailyMetrics"
    assert "private response details" not in str(status)


class _OpenPodcastResponse:
    def __init__(self, body: bytes):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, _limit):
        return self.body


def test_openpodcast_fetches_episode_daily_metrics_in_bounded_windows(temp_db, monkeypatch):
    import json
    from urllib.parse import parse_qs, urlsplit

    monkeypatch.setenv(OPENPODCAST_TOKEN_ENV, "server-only-openpodcast-token")
    monkeypatch.setenv(OPENPODCAST_PODCAST_ID_ENV, "4501")
    connectors = PodcastAnalyticsConnectors(temp_db.db_path)
    daily_windows = []

    def respond(request, timeout):
        parts = urlsplit(request.full_url)
        if parts.path.endswith("/episodesDailyMetrics"):
            query = parse_qs(parts.query)
            daily_windows.append((query["start"][0], query["end"][0]))
            # A whole-month response for a large catalog exceeds the 10 MB response cap.
            if (date.fromisoformat(query["end"][0]) - date.fromisoformat(query["start"][0])).days > 6:
                return _OpenPodcastResponse(b"x" * 10_000_001)
            data = [{"date": query["start"][0], "spotify_streams": 1, "spotify_listeners": 1}]
        else:
            data = []
        return _OpenPodcastResponse(json.dumps({"meta": {"result": "success"}, "data": data}).encode())

    monkeypatch.setattr("guest_database_manager.podcast_analytics_connectors.urlopen", respond)
    result = connectors.sync_openpodcast(actor="admin", start=date(2026, 10, 1), end=date(2026, 10, 30))

    assert result["status"] == "completed"
    assert daily_windows == [
        ("2026-10-01", "2026-10-07"), ("2026-10-08", "2026-10-14"), ("2026-10-15", "2026-10-21"),
        ("2026-10-22", "2026-10-28"), ("2026-10-29", "2026-10-30"),
    ]
    assert result["inserted"] == 5


def test_openpodcast_keeps_working_endpoints_when_one_upstream_query_fails(temp_db, monkeypatch):
    import json

    monkeypatch.setenv(OPENPODCAST_TOKEN_ENV, "server-only-openpodcast-token")
    monkeypatch.setenv(OPENPODCAST_PODCAST_ID_ENV, "4501")
    monkeypatch.setenv(OPENPODCAST_AUTO_SYNC_ENV, "true")
    connectors = PodcastAnalyticsConnectors(temp_db.db_path)
    bodies = {
        # OpenPodcast reports server-side query failures as HTTP 200 with null data.
        "episodesDailyMetrics": {"meta": {"result": "error", "query": "episodesDailyMetrics"}, "data": None},
        "podcastFollowers": {"meta": {"result": "success"}, "data": [
            {"date": "2026-10-07", "spotify_total_followers": 90, "apple_total_followers": 40},
        ]},
        "spotifyImpressionsSources": {"meta": {"result": "success"}, "data": []},
        "spotifyCountries": {"meta": {"result": "success"}, "data": []},
    }

    def respond(request, timeout):
        endpoint = next(key for key in bodies if f"/{key}?" in request.full_url)
        return _OpenPodcastResponse(json.dumps(bodies[endpoint]).encode())

    monkeypatch.setattr("guest_database_manager.podcast_analytics_connectors.urlopen", respond)
    result = connectors.sync_openpodcast(actor="podcast-analytics-automation",
                                         start=date(2026, 10, 1), end=date(2026, 10, 7))

    assert result["status"] == "partial"
    assert result["inserted"] == 2
    assert result["failed_endpoints"] == ["episodesDailyMetrics"]
    status = connectors.status()["openpodcast"]
    assert status["status"] == "degraded"
    assert status["last_error_code"] == "upstream_query_failed:episodesDailyMetrics"
    assert status["failed_endpoints"] == ["episodesDailyMetrics"]
    assert status["last_success_at"]
    assert connectors.openpodcast_auto_sync_due() is False


def test_openpodcast_reports_upstream_query_failure_when_every_endpoint_fails(temp_db, monkeypatch):
    monkeypatch.setenv(OPENPODCAST_TOKEN_ENV, "server-only-openpodcast-token")
    monkeypatch.setenv(OPENPODCAST_PODCAST_ID_ENV, "4501")
    connectors = PodcastAnalyticsConnectors(temp_db.db_path)
    monkeypatch.setattr(
        "guest_database_manager.podcast_analytics_connectors.urlopen",
        lambda *_args, **_kwargs: _OpenPodcastResponse(b'{"meta": {"result": "error"}, "data": null}'),
    )

    with pytest.raises(AnalyticsConnectorError, match="episodesDailyMetrics"):
        connectors.sync_openpodcast(actor="admin")

    status = connectors.status()["openpodcast"]
    assert status["status"] == "error"
    assert status["last_error_code"] == "upstream_query_failed:episodesDailyMetrics"
    assert status["failed_endpoints"] == [
        "episodesDailyMetrics", "podcastFollowers", "spotifyCountries", "spotifyImpressionsSources",
    ]


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
    def google_identity(url, _token):
        if "userinfo" in url:
            return {"sub": "account-1", "email": "owner@example.test"}
        return {"items": [{"id": "UC-one", "snippet": {"title": "Mirror Talk"}}]}
    monkeypatch.setattr(connectors, "_get_json", google_identity)
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
               (provider, youtube_channel_id, refresh_token_ciphertext, status, connected_at, updated_at)
               VALUES ('google', 'UC-test', ?, 'connected', '2026-09-25T00:00:00Z', '2026-09-25T00:00:00Z')""",
            (encrypted,),
        )
        conn.commit()
    monkeypatch.setattr(connectors, "_refresh_access_token", lambda token: "access")
    monkeypatch.setattr(connectors, "_collect_google", lambda token, **kwargs: [{
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


def test_google_oauth_keeps_two_distinct_channel_connections(temp_db, monkeypatch):
    _configure(monkeypatch)
    connectors = PodcastAnalyticsConnectors(temp_db.db_path)
    identities = iter([
        ("account-1", "one@example.test", "UC-one", "Mirror Talk Main"),
        ("account-2", "two@example.test", "UC-two", "Mirror Talk Clips"),
    ])
    active = {}

    def google_response(url, _token):
        if "userinfo" in url:
            account, email, channel_id, title = next(identities)
            active.update(account=account, email=email, channel_id=channel_id, title=title)
            return {"sub": account, "email": email}
        return {"items": [{"id": active["channel_id"], "snippet": {"title": active["title"]}}]}

    monkeypatch.setattr(connectors, "_post_form", lambda *args, **kwargs: {
        "refresh_token": "refresh", "access_token": "access", "scope": "openid email",
    })
    monkeypatch.setattr(connectors, "_get_json", google_response)
    for _ in range(2):
        authorization = connectors.begin_google(actor="admin", origin="https://example.test")
        state = parse_qs(urlsplit(authorization["authorization_url"]).query)["state"][0]
        connectors.complete_google(state=state, code="code", origin="https://example.test")

    connections = connectors.status()["google"]["connections"]
    assert [(item["youtube_channel_id"], item["youtube_channel_title"]) for item in connections] == [
        ("UC-one", "Mirror Talk Main"), ("UC-two", "Mirror Talk Clips"),
    ]
    assert [item["sync_ga4"] for item in connections] == [True, False]


def test_google_sync_keeps_channel_observations_independent(temp_db, monkeypatch):
    _configure(monkeypatch)
    connectors = PodcastAnalyticsConnectors(temp_db.db_path)
    encrypted = connectors._cipher().encrypt(b"refresh").decode()
    with sqlite3.connect(temp_db.db_path) as conn:
        for channel_id, title in (("UC-one", "Main"), ("UC-two", "Clips")):
            conn.execute(
                """INSERT INTO analytics_oauth_connections
                   (provider, youtube_channel_id, youtube_channel_title, refresh_token_ciphertext,
                    status, connected_at, updated_at)
                   VALUES ('google', ?, ?, ?, 'connected', '2026-09-25T00:00:00Z', '2026-09-25T00:00:00Z')""",
                (channel_id, title, encrypted),
            )
        conn.commit()
    monkeypatch.setattr(connectors, "_refresh_access_token", lambda token: "access")
    monkeypatch.setattr(connectors, "_collect_google", lambda token, **kwargs: [{
        "provider": f"youtube:{kwargs['channel_id']}", "metric_name": "plays", "metric_value": 10,
        "period_start": "2026-08-01", "period_end": "2026-08-28", "traffic_scope": "all",
        "source_reference": f"youtube-analytics-api:{kwargs['channel_id']}",
    }])

    result = connectors.sync_google(actor="automation", force=True)

    assert result["inserted"] == 2
    with sqlite3.connect(temp_db.db_path) as conn:
        assert conn.execute(
            "SELECT provider FROM growth_metric_observations ORDER BY provider"
        ).fetchall() == [("youtube:uc-one",), ("youtube:uc-two",)]


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
        if "youtubeanalytics" in url and "dimensions=ageGroup%2Cgender" in url:
            return {"rows": [["age25-34", "female", 62.5], ["age25-34", "male", 37.5]]}
        if "youtubeanalytics" in url and "dimensions=insightTrafficSourceType" in url:
            return {"rows": [["YT_SEARCH", 44]]}
        if "youtubeanalytics" in url and "dimensions=video" in url:
            return {"rows": [["video-1", 80, 90, 68]]}
        if "youtubeanalytics" in url:
            return {"rows": [[100, 120, 72, 55.5]]}
        if "youtube/v3/channels" in url:
            return {"items": [{"statistics": {"subscriberCount": "2500"}}]}
        if "youtube/v3/videos" in url:
            return {"items": [{"id": "video-1", "snippet": {"title": "A measured episode"}}]}
        raise AssertionError(url)

    monkeypatch.setattr(connectors, "_get_json", google_response)
    monkeypatch.setattr(connectors, "_ga4_report", lambda token, property_id, start, end, dimensions, metrics, **_kwargs: (
        {"rows": [{"dimensionValues": [{"value": "mobile"}], "metricValues": [{"value": "25"}]}]}
        if dimensions else {"rows": [{"metricValues": [{"value": "40"}]}]}
    ))

    observations = connectors._collect_google("access")
    values = {(row["provider"], row["metric_name"]): float(row["metric_value"]) for row in observations}

    assert values[("youtube", "plays")] == 100
    assert values[("youtube", "watch_time_hours")] == 2
    assert values[("youtube", "lifetime_plays")] == 100
    assert values[("youtube", "lifetime_watch_time_hours")] == 2
    assert values[("youtube", "subscribers")] == 2500
    assert values[("youtube", "device_mobile")] == 70
    assert values[("youtube", "average_view_percentage")] == 55.5
    assert values[("youtube", "traffic_source_views")] == 44
    assert values[("youtube", "video_views")] == 80
    assert values[("youtube", "video_lifetime_views")] == 80
    assert values[("website", "organic_reach")] == 40
    assert values[("website", "device_mobile")] == 25


def test_ga4_web_player_events_are_normalized_without_becoming_downloads(temp_db, monkeypatch):
    connectors = PodcastAnalyticsConnectors(temp_db.db_path)
    captured = []

    def report(_token, _property_id, _start, _end, dimensions, metrics, **kwargs):
        captured.append((dimensions, metrics, kwargs.get("dimension_filter")))
        return {"rows": [
            {"dimensionValues": [{"value": "audio_play"}],
             "metricValues": [{"value": "42"}, {"value": "31"}]},
            {"dimensionValues": [{"value": "audio_progress_50"}],
             "metricValues": [{"value": "24"}, {"value": "20"}]},
            {"dimensionValues": [{"value": "audio_complete"}],
             "metricValues": [{"value": "18"}, {"value": "16"}]},
        ]}

    monkeypatch.setattr(connectors, "_ga4_report", report)
    observations = connectors._ga4_web_player_events(
        "token", "123", date(2026, 11, 1), date(2026, 11, 28)
    )

    assert {(row["metric_name"], row["metric_value"]) for row in observations} == {
        ("web_player_play_starts", 42.0),
        ("web_player_unique_users", 31.0),
        ("web_player_progress_50", 24.0),
        ("web_player_completions", 18.0),
    }
    assert all(row["provider"] == "website" and row["source_class"] == "website" for row in observations)
    assert not {row["metric_name"] for row in observations} & {"downloads", "plays"}
    assert captured[0][2]["filter"]["fieldName"] == "eventName"


def test_partial_collector_run_is_degraded_not_failed(temp_db, monkeypatch):
    token = "collector-token-with-at-least-thirty-two-characters"
    monkeypatch.setenv(COLLECTOR_TOKEN_ENV, token)
    connectors = PodcastAnalyticsConnectors(temp_db.db_path)
    connectors.set_local_collector("spotify", enabled=True, actor="admin")

    with pytest.raises(AnalyticsConnectorError, match="missing reports"):
        connectors.report_local_collector_status(
            provider="spotify", token=token, status="degraded", error_code="timeout",
        )
    connectors.report_local_collector_status(
        provider="spotify", token=token, status="degraded", error_code="missing_reports_age_gender",
    )

    connection = connectors.status()["local_collectors"]["connections"]["spotify"]
    assert connection["status"] == "degraded"
    assert connection["missing_reports"] == ["age", "gender"]
    assert connection["consecutive_failures"] == 0
