"""Release contract tests for Podcast Reach."""

from datetime import datetime, timezone

from guest_database_manager.db_connection import connect_database
from guest_database_manager.growth_intelligence import GrowthIntelligence
from guest_database_manager.podcast_release_readiness import PodcastReachReleaseReadiness
from guest_database_manager.podcast_source_monitor import PUBLIC_SOURCES


def test_release_readiness_fails_closed_when_collection_is_not_configured(temp_db):
    report = PodcastReachReleaseReadiness(temp_db.db_path).report()

    assert report["status"] == "not_ready"
    assert report["checks"]["schema"]["status"] == "pass"
    assert report["checks"]["distribution"]["status"] == "fail"
    assert report["checks"]["public_sources"]["status"] == "fail"
    assert report["checks"]["youtube_analytics"]["status"] == "fail"
    assert report["checks"]["provider_collectors"]["status"] == "fail"
    assert report["checks"]["analytics_evidence"]["status"] == "fail"


def test_release_readiness_reports_outdated_schema_without_querying_new_contract(temp_db):
    with connect_database(temp_db.db_path) as conn:
        conn.execute("DELETE FROM schema_migrations WHERE version=46")
        conn.commit()

    report = PodcastReachReleaseReadiness(temp_db.db_path).report()

    assert report["status"] == "not_ready"
    assert report["blockers"] == [{
        "code": "schema_outdated",
        "message": "Database migration 46 has not been applied.",
    }]
    assert report["checks"]["schema"]["current_version"] == 45


def test_release_readiness_passes_only_with_fresh_distribution_and_private_evidence(temp_db, monkeypatch):
    now = datetime(2026, 11, 24, 12, 0, tzinfo=timezone.utc)
    now_text = now.isoformat().replace("+00:00", "Z")
    monkeypatch.setenv("MIRROR_TALK_GOOGLE_ANALYTICS_CLIENT_ID", "client")
    monkeypatch.setenv("MIRROR_TALK_GOOGLE_ANALYTICS_CLIENT_SECRET", "secret")
    monkeypatch.setenv("MIRROR_TALK_ANALYTICS_TOKEN_ENCRYPTION_KEY", "x" * 32)
    monkeypatch.setenv("MIRROR_TALK_ANALYTICS_COLLECTOR_TOKEN", "y" * 32)
    monkeypatch.delenv("MIRROR_TALK_GA4_PROPERTY_ID", raising=False)
    monkeypatch.delenv("MIRROR_TALK_OPENPODCAST_TOKEN", raising=False)
    monkeypatch.delenv("MIRROR_TALK_OPENPODCAST_PODCAST_ID", raising=False)

    with connect_database(temp_db.db_path) as conn:
        conn.execute(
            """UPDATE podcast_platform_registry SET status='available',
                      last_verified_at=?, last_error_code=''
               WHERE distribution_mode!='expected_missing'""",
            (now_text,),
        )
        conn.executemany(
            """INSERT INTO podcast_source_checks
               (source_key, source_name, source_url, status, evidence_json, latency_ms,
                error_code, actor, checked_at) VALUES (?, ?, ?, 'available', '{}', 10, '', 'test', ?)""",
            [(key, name, url, now_text) for key, name, url in PUBLIC_SOURCES],
        )
        conn.execute(
            """INSERT INTO analytics_oauth_connections
               (provider, account_subject, account_email, youtube_channel_id,
                youtube_channel_title, refresh_token_ciphertext, scopes_json, status,
                connected_at, last_sync_at, last_success_at, updated_at)
               VALUES ('google', 'subject', 'owner@example.test', 'UC-release', 'Mirror Talk',
                       'encrypted', '[]', 'connected', ?, ?, ?, ?)""",
            (now_text, now_text, now_text, now_text),
        )
        conn.executemany(
            """INSERT INTO analytics_browser_collectors
               (provider, enabled, status, last_seen_at, last_sync_at, last_success_at, updated_at)
               VALUES (?, 1, 'connected', ?, ?, ?, ?)""",
            [(provider, now_text, now_text, now_text, now_text) for provider in ("spotify", "apple_podcasts")],
        )
        conn.commit()

    observations = [
        {"provider": "youtube:uc-release", "metric_name": "plays", "metric_value": 10,
         "period_start": "2026-11-01", "period_end": "2026-11-23", "source_reference": "youtube-api"},
        {"provider": "spotify", "metric_name": "plays", "metric_value": 11,
         "period_start": "2026-11-01", "period_end": "2026-11-23", "source_reference": "spotify-export"},
        {"provider": "spotify", "metric_name": "downloads", "metric_value": 12,
         "period_start": "2026-11-01", "period_end": "2026-11-23", "source_reference": "spotify-export",
         "source_class": "host_rss_delivery"},
        {"provider": "apple_podcasts", "metric_name": "plays", "metric_value": 13,
         "period_start": "2026-11-01", "period_end": "2026-11-23", "source_reference": "apple-export"},
    ]
    GrowthIntelligence(temp_db.db_path).record_observations(observations, actor="test")

    report = PodcastReachReleaseReadiness(temp_db.db_path).report(now=now)

    assert report["status"] == "ready"
    assert report["blocker_count"] == 0
    assert report["checks"]["distribution"]["coverage_pct"] == 100.0
    assert report["checks"]["public_sources"]["fresh_available"] == len(PUBLIC_SOURCES)
    assert {item["code"] for item in report["warnings"]} == {
        "known_missing_destinations", "ga4_not_configured", "aggregator_not_configured",
    }


def test_release_readiness_rejects_stale_source_and_analytics_periods(temp_db, monkeypatch):
    monkeypatch.setenv("MIRROR_TALK_GOOGLE_ANALYTICS_CLIENT_ID", "client")
    monkeypatch.setenv("MIRROR_TALK_GOOGLE_ANALYTICS_CLIENT_SECRET", "secret")
    monkeypatch.setenv("MIRROR_TALK_ANALYTICS_TOKEN_ENCRYPTION_KEY", "x" * 32)
    monkeypatch.setenv("MIRROR_TALK_ANALYTICS_COLLECTOR_TOKEN", "y" * 32)
    old = "2026-01-01T00:00:00Z"
    with connect_database(temp_db.db_path) as conn:
        conn.execute(
            "UPDATE podcast_platform_registry SET status='available' WHERE distribution_mode!='expected_missing'"
        )
        conn.executemany(
            """INSERT INTO podcast_source_checks
               (source_key, source_name, source_url, status, evidence_json, latency_ms,
                error_code, actor, checked_at) VALUES (?, ?, ?, 'available', '{}', 10, '', 'test', ?)""",
            [(key, name, url, old) for key, name, url in PUBLIC_SOURCES],
        )
        conn.commit()

    report = PodcastReachReleaseReadiness(temp_db.db_path).report(
        now=datetime(2026, 11, 24, tzinfo=timezone.utc)
    )

    assert report["status"] == "not_ready"
    assert "public_sources_incomplete" in {item["code"] for item in report["blockers"]}
    assert "analytics_evidence_incomplete" in {item["code"] for item in report["blockers"]}
