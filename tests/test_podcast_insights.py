import json

from guest_database_manager.db_connection import connect_database
from guest_database_manager.podcast_insights import PodcastInsights
from guest_database_manager.podcast_source_monitor import PodcastSourceMonitor
from guest_database_manager.web_interface import GuestWebService


def test_insights_distinguishes_missing_evidence_from_measured_zero(temp_db):
    result = PodcastInsights(temp_db.db_path).dashboard()

    assert result["summary"]["downloads"] is None
    assert result["summary"]["plays"] is None
    assert result["summary"]["unique_listeners"] is None
    assert result["quality"]["status"] == "no_data"


def test_insights_never_invents_cross_platform_listener_total(temp_db):
    service = GuestWebService(temp_db.db_path)
    service.record_growth_observations({"observations": [
        {"provider": "spotify", "metric_name": "unique_listeners", "metric_value": 120,
         "period_start": "2026-09-01", "period_end": "2026-09-30", "source_reference": "spotify.csv"},
        {"provider": "apple", "metric_name": "unique_listeners", "metric_value": 80,
         "period_start": "2026-09-01", "period_end": "2026-09-30", "source_reference": "apple.csv"},
        {"provider": "spotify", "metric_name": "downloads", "metric_value": 300,
         "period_start": "2026-09-01", "period_end": "2026-09-30", "source_reference": "spotify.csv"},
        {"provider": "apple", "metric_name": "downloads", "metric_value": 200,
         "period_start": "2026-09-01", "period_end": "2026-09-30", "source_reference": "apple.csv"},
    ]}, actor="analyst")

    result = PodcastInsights(temp_db.db_path).dashboard()

    assert result["summary"]["unique_listeners"] is None
    assert result["summary"]["downloads"] == 500
    assert {item["value"] for item in result["audience_by_platform"]} == {80, 120}
    assert result["quality"]["status"] == "partial"


def test_insights_support_source_backed_device_and_country_dimensions(temp_db):
    service = GuestWebService(temp_db.db_path)
    service.record_growth_observations({"observations": [
        {"provider": "podcast_host", "metric_name": "device_mobile", "metric_value": 75,
         "period_start": "2026-09-01", "period_end": "2026-09-30", "source_reference": "host.csv"},
        {"provider": "podcast_host", "metric_name": "device_desktop", "metric_value": 25,
         "period_start": "2026-09-01", "period_end": "2026-09-30", "source_reference": "host.csv"},
        {"provider": "podcast_host", "metric_name": "country_germany", "metric_value": 60,
         "period_start": "2026-09-01", "period_end": "2026-09-30", "source_reference": "host.csv"},
    ]}, actor="analyst")

    result = service.get_podcast_insights()

    assert result["devices"][0]["name"] == "Mobile"
    assert result["devices"][0]["share_pct"] == 75
    assert result["countries"][0]["name"] == "Germany"
    assert result["countries"][0]["share_pct"] == 100


def test_insights_prefers_show_total_over_overlapping_episode_rows(temp_db):
    episode_id, _ = temp_db.upsert_episode({"guest_name": "Reach Guest", "episode_title": "Reach"})
    service = GuestWebService(temp_db.db_path)
    common = {"provider": "spotify", "metric_name": "downloads", "period_start": "2026-09-01",
              "period_end": "2026-09-30", "source_reference": "spotify.csv"}
    service.record_growth_observations({"observations": [
        {**common, "metric_value": 1000},
        {**common, "episode_id": episode_id, "metric_value": 400},
    ]}, actor="analyst")

    result = service.get_podcast_insights()

    assert result["summary"]["downloads"] == 1000
    assert result["quality"]["mixed_grain_conflicts"] == ["spotify:downloads:2026-09-01:2026-09-30"]


def test_source_coverage_never_treats_public_listing_as_private_analytics(temp_db):
    coverage = PodcastSourceMonitor(temp_db.db_path).status()

    assert coverage["public_available"] == 0
    assert coverage["public_expected"] == 6
    assert coverage["private_connected"] == 0
    assert coverage["private_expected"] == 5
    assert all(item["status"] == "not_connected" for item in coverage["private"])


def test_web_insights_keeps_private_metrics_missing_without_public_checks(temp_db):
    result = GuestWebService(temp_db.db_path).get_podcast_insights()

    assert result["public_catalog"]["published_episodes"] is None
    assert result["quality"]["status"] == "no_data"
    assert result["summary"]["downloads"] is None


def test_web_insights_surfaces_verified_public_catalog_without_inventing_private_metrics(temp_db):
    evidence = {
        "episode_count": 520,
        "latest_release": "2026-09-24T03:00:00Z",
        "feed_url": "https://anchor.fm/s/261b1464/podcast/rss",
    }
    with connect_database(temp_db.db_path) as conn:
        conn.execute(
            """INSERT INTO podcast_source_checks
               (source_key, source_name, source_url, status, evidence_json, latency_ms,
                error_code, actor, checked_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                "apple_public",
                "Apple Podcasts",
                "https://itunes.apple.com/lookup?id=1518394292&entity=podcast",
                "available",
                json.dumps(evidence),
                100,
                "",
                "test",
                "2026-09-25T10:00:00Z",
            ),
        )
        conn.commit()

    result = GuestWebService(temp_db.db_path).get_podcast_insights()

    assert result["public_catalog"]["published_episodes"] == 520
    assert result["public_catalog"]["latest_release"] == "2026-09-24T03:00:00Z"
    assert result["quality"]["status"] == "public_only"
    assert result["summary"]["downloads"] is None
    assert result["summary"]["unique_listeners"] is None
