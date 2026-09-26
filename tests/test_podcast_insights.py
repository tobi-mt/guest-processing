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
    assert all(item["status"] == "provider_access_required" for item in coverage["private"])
    assert coverage["automated_connected"] == 0
    assert coverage["automated_expected"] == 2
    assert coverage["provider_limited_count"] == 3


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


def test_newer_subscriber_snapshot_does_not_hide_latest_play_window(temp_db):
    service = GuestWebService(temp_db.db_path)
    service.record_growth_observations({"observations": [
        {"provider": "youtube", "metric_name": "plays", "metric_value": 181,
         "period_start": "2026-08-26", "period_end": "2026-09-22", "source_reference": "youtube-api"},
        {"provider": "youtube", "metric_name": "watch_time_hours", "metric_value": 7.8,
         "period_start": "2026-08-26", "period_end": "2026-09-22", "source_reference": "youtube-api"},
        {"provider": "youtube", "metric_name": "subscribers", "metric_value": 65,
         "period_start": "2026-09-25", "period_end": "2026-09-25", "source_reference": "youtube-data-api"},
    ]}, actor="automation")

    result = PodcastInsights(temp_db.db_path).dashboard()

    assert result["summary"]["plays"] == 181
    assert result["summary"]["plays_period_end"] == "2026-09-22"
    assert result["trend"] == []
    assert result["provider_strength"][0]["metrics"]["plays"] == 181
    assert result["provider_strength"][0]["metrics"]["subscribers"] == 65


def test_dimension_shares_are_calculated_within_provider_not_across_incompatible_sources(temp_db):
    service = GuestWebService(temp_db.db_path)
    service.record_growth_observations({"observations": [
        {"provider": "youtube", "metric_name": "device_mobile", "metric_value": 80,
         "period_start": "2026-09-01", "period_end": "2026-09-22", "source_reference": "youtube-api"},
        {"provider": "youtube", "metric_name": "device_desktop", "metric_value": 20,
         "period_start": "2026-09-01", "period_end": "2026-09-22", "source_reference": "youtube-api"},
        {"provider": "website", "metric_name": "device_desktop", "metric_value": 10,
         "period_start": "2026-09-01", "period_end": "2026-09-22", "source_reference": "ga4-api"},
    ]}, actor="automation")

    devices = PodcastInsights(temp_db.db_path).dashboard()["devices"]
    shares = {(row["provider"], row["name"]): row["share_pct"] for row in devices}

    assert shares[("youtube", "Mobile")] == 80
    assert shares[("youtube", "Desktop")] == 20
    assert shares[("website", "Desktop")] == 100


def test_dimension_breakdown_keeps_each_providers_latest_available_period(temp_db):
    service = GuestWebService(temp_db.db_path)
    service.record_growth_observations({"observations": [
        {"provider": "youtube", "metric_name": "device_mobile", "metric_value": 80,
         "period_start": "2026-09-01", "period_end": "2026-09-22", "source_reference": "youtube-api"},
        {"provider": "website", "metric_name": "device_desktop", "metric_value": 10,
         "period_start": "2026-09-01", "period_end": "2026-09-20", "source_reference": "ga4-api"},
    ]}, actor="automation")

    devices = PodcastInsights(temp_db.db_path).dashboard()["devices"]

    assert {(row["provider"], row["period_end"]) for row in devices} == {
        ("youtube", "2026-09-22"), ("website", "2026-09-20"),
    }


def test_channel_scoped_youtube_rows_replace_matching_legacy_aggregate_once_all_channels_are_present(temp_db):
    service = GuestWebService(temp_db.db_path)
    with connect_database(temp_db.db_path) as conn:
        for channel_id in ("UC-one", "UC-two"):
            conn.execute(
                """INSERT INTO analytics_oauth_connections
                   (provider, youtube_channel_id, youtube_channel_title, status, connected_at, updated_at)
                   VALUES ('google', ?, ?, 'connected', '2026-09-25T00:00:00Z', '2026-09-25T00:00:00Z')""",
                (channel_id, channel_id),
            )
        conn.commit()
    service.record_growth_observations({"observations": [
        {"provider": "youtube", "metric_name": "plays", "metric_value": 100,
         "period_start": "2026-09-01", "period_end": "2026-09-22", "source_reference": "legacy"},
        {"provider": "youtube:UC-one", "metric_name": "plays", "metric_value": 100,
         "period_start": "2026-09-01", "period_end": "2026-09-22", "source_reference": "one"},
        {"provider": "youtube:UC-two", "metric_name": "plays", "metric_value": 50,
         "period_start": "2026-09-01", "period_end": "2026-09-22", "source_reference": "two"},
    ]}, actor="automation")

    result = PodcastInsights(temp_db.db_path).dashboard()

    assert result["summary"]["plays"] == 150
    assert {card["provider"] for card in result["provider_strength"]} == {
        "youtube:uc-one", "youtube:uc-two",
    }


def test_summary_keeps_youtube_window_separate_from_newer_spotify_daily_rows(temp_db):
    service = GuestWebService(temp_db.db_path)
    observations = [
        {"provider": "youtube:channel", "metric_name": "plays", "metric_value": 150,
         "period_start": "2026-08-26", "period_end": "2026-09-22", "source_reference": "youtube"},
    ]
    for day, downloads, plays, audience in (
        ("2026-09-22", 10, 4, 8), ("2026-09-23", 11, 5, 9),
        ("2026-09-24", 12, 6, 10), ("2026-09-25", 13, 7, 11),
    ):
        observations.extend([
            {"provider": "spotify", "metric_name": "downloads", "metric_value": downloads,
             "period_start": day, "period_end": day, "source_reference": "spotify"},
            {"provider": "spotify", "metric_name": "plays", "metric_value": plays,
             "period_start": day, "period_end": day, "source_reference": "spotify"},
            {"provider": "spotify", "metric_name": "unique_listeners", "metric_value": audience,
             "period_start": day, "period_end": day, "source_reference": "spotify"},
        ])
    service.record_growth_observations({"observations": observations}, actor="automation")

    summary = PodcastInsights(temp_db.db_path).dashboard()["summary"]

    assert summary["plays"] == 150
    assert summary["plays_period_end"] == "2026-09-22"
    assert summary["spotify_28d"] == {
        "period_start": "2026-08-29", "period_end": "2026-09-25",
        "downloads": 46.0, "plays": 22.0, "latest_daily_audience": 11.0,
    }


def test_apple_country_plays_are_aggregated_across_months_with_clean_labels(temp_db):
    service = GuestWebService(temp_db.db_path)
    service.record_growth_observations({"observations": [
        {"provider": "apple_podcasts", "metric_name": "country_plays_germany_276", "metric_value": 7,
         "period_start": "2026-08-01", "period_end": "2026-08-31", "source_reference": "apple"},
        {"provider": "apple_podcasts", "metric_name": "country_plays_germany_276", "metric_value": 3,
         "period_start": "2026-09-01", "period_end": "2026-09-30", "source_reference": "apple"},
        {"provider": "apple_podcasts", "metric_name": "country_plays_canada_124", "metric_value": 5,
         "period_start": "2026-09-01", "period_end": "2026-09-30", "source_reference": "apple"},
    ]}, actor="analyst")

    countries = PodcastInsights(temp_db.db_path).dashboard()["countries"]

    assert countries == [
        {"name": "Germany", "value": 10.0, "provider": "apple_podcasts",
         "period_start": "2026-08-01", "period_end": "2026-09-30", "measure": "plays", "share_pct": 66.7},
        {"name": "Canada", "value": 5.0, "provider": "apple_podcasts",
         "period_start": "2026-09-01", "period_end": "2026-09-30", "measure": "plays", "share_pct": 33.3},
    ]
