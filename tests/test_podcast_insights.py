import json

from guest_database_manager.db_connection import connect_database
from guest_database_manager.growth_intelligence import GrowthIntelligence
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


def test_global_rollup_counts_each_delivery_channel_once(temp_db):
    service = GuestWebService(temp_db.db_path)
    service.record_growth_observations({"observations": [
        {"provider": "spotify", "metric_name": "downloads", "metric_value": 100,
         "period_start": "2026-11-01", "period_end": "2026-11-28", "source_reference": "spotify.csv",
         "source_class": "host_rss_delivery", "overlap_group": "open_rss_downloads"},
        {"provider": "spotify", "metric_name": "plays", "metric_value": 50,
         "period_start": "2026-11-01", "period_end": "2026-11-28", "source_reference": "spotify.csv",
         "source_class": "provider_native", "overlap_group": "spotify_native_plays"},
        {"provider": "apple_podcasts", "metric_name": "plays", "metric_value": 80,
         "period_start": "2026-11-01", "period_end": "2026-11-28", "source_reference": "apple.csv",
         "source_class": "provider_native", "overlap_group": "apple_native_plays"},
        {"provider": "youtube:channel", "metric_name": "plays", "metric_value": 40,
         "period_start": "2026-11-01", "period_end": "2026-11-28", "source_reference": "youtube-api",
         "source_class": "video_platform_consumption", "overlap_group": "youtube_native_plays"},
    ]}, actor="automation")

    rollup = PodcastInsights(temp_db.db_path).dashboard()["summary"]["global_rollup"]

    assert rollup["measured_activity"] == 190
    assert rollup["audio_starts"] == 150
    assert rollup["video_views"] == 40
    assert rollup["coverage"] == "complete"
    assert all("Apple" not in item["label"] for item in rollup["components"])


def test_global_rollup_bounds_people_instead_of_adding_overlapping_audiences(temp_db):
    service = GuestWebService(temp_db.db_path)
    service.record_growth_observations({"observations": [
        {"provider": "spotify", "metric_name": "unique_listeners", "metric_value": 70,
         "period_start": "2026-11-01", "period_end": "2026-11-28", "source_reference": "spotify.csv",
         "source_class": "host_cross_platform_aggregate"},
        {"provider": "apple_podcasts", "metric_name": "unique_listeners", "metric_value": 20,
         "period_start": "2026-11-01", "period_end": "2026-11-28", "source_reference": "apple.csv",
         "source_class": "provider_native"},
        {"provider": "youtube:channel", "metric_name": "unique_viewers", "metric_value": 30,
         "period_start": "2026-11-01", "period_end": "2026-11-28", "source_reference": "youtube-export.csv"},
    ]}, actor="automation")

    reach = PodcastInsights(temp_db.db_path).dashboard()["summary"]["global_rollup"]["reach_range"]

    assert reach["minimum"] == 70
    assert reach["maximum"] == 100
    assert reach["source_count"] == 2


def test_global_rollup_does_not_claim_missing_zero_value_channels(temp_db):
    service = GuestWebService(temp_db.db_path)
    service.record_growth_observations({"observations": [
        {"provider": "spotify", "metric_name": "unique_listeners", "metric_value": 7,
         "period_start": "2026-11-21", "period_end": "2026-11-21", "source_reference": "spotify.csv",
         "source_class": "host_cross_platform_aggregate"},
        {"provider": "youtube:channel", "metric_name": "plays", "metric_value": 40,
         "period_start": "2026-10-25", "period_end": "2026-11-21", "source_reference": "youtube-api"},
    ]}, actor="automation")

    rollup = PodcastInsights(temp_db.db_path).dashboard()["summary"]["global_rollup"]

    assert rollup["measured_activity"] == 40
    assert rollup["audio_starts"] is None
    assert rollup["coverage"] == "partial"
    assert [item["key"] for item in rollup["components"]] == ["youtube_views"]


def test_global_rollup_prefers_host_total_over_its_app_breakdown(temp_db):
    service = GuestWebService(temp_db.db_path)
    common = {
        "provider": "podcast_host", "metric_name": "downloads",
        "period_start": "2026-11-01", "period_end": "2026-11-28",
        "source_class": "host_rss_delivery", "overlap_group": "open_rss_downloads",
    }
    service.record_growth_observations({"observations": [
        {**common, "metric_value": 100, "source_reference": "host-total.csv"},
        {**common, "metric_value": 60, "source_reference": "host-apps.csv", "app_name": "Apple Podcasts"},
        {**common, "metric_value": 40, "source_reference": "host-apps.csv", "app_name": "Pocket Casts"},
    ]}, actor="automation")

    rollup = PodcastInsights(temp_db.db_path).dashboard()["summary"]["global_rollup"]

    assert rollup["audio_starts"] == 100
    assert rollup["measured_activity"] == 100


def test_performance_trend_reconciles_exact_windows_and_drives_headline_comparison(temp_db):
    service = GuestWebService(temp_db.db_path)
    observations = []
    for day, downloads, plays in (
        ("2026-10-01", 10, 5), ("2026-10-02", 12, 6),
        ("2026-10-03", 20, 8), ("2026-10-04", 22, 9),
    ):
        observations.extend([
            {"provider": "spotify", "metric_name": "downloads", "metric_value": downloads,
             "period_start": day, "period_end": day, "source_reference": "spotify.csv",
             "source_class": "host_rss_delivery", "overlap_group": "open_rss_downloads"},
            {"provider": "spotify", "metric_name": "plays", "metric_value": plays,
             "period_start": day, "period_end": day, "source_reference": "spotify.csv",
             "source_class": "provider_native", "overlap_group": "spotify_native_plays"},
        ])
    observations.extend([
        {"provider": "youtube:channel", "metric_name": "plays", "metric_value": 30,
         "period_start": "2026-10-01", "period_end": "2026-10-02", "source_reference": "youtube-api"},
        {"provider": "youtube:channel", "metric_name": "plays", "metric_value": 50,
         "period_start": "2026-10-03", "period_end": "2026-10-04", "source_reference": "youtube-api"},
        {"provider": "youtube:channel", "metric_name": "plays", "metric_value": 70,
         "period_start": "2026-10-05", "period_end": "2026-10-06", "source_reference": "youtube-api"},
        {"provider": "apple_podcasts", "metric_name": "plays", "metric_value": 999,
         "period_start": "2026-10-01", "period_end": "2026-10-31", "source_reference": "apple.csv"},
    ])
    service.record_growth_observations({"observations": observations}, actor="automation")

    result = PodcastInsights(temp_db.db_path).dashboard()

    assert result["performance_trend"] == [
        {"period": "2026-10-02", "period_start": "2026-10-01", "period_end": "2026-10-02",
         "total": 63.0, "audio": 33.0, "video": 30.0, "open_rss_downloads": 22.0,
         "spotify_native_plays": 11.0, "youtube_views": 30.0, "coverage": "complete",
         "missing_components": []},
        {"period": "2026-10-04", "period_start": "2026-10-03", "period_end": "2026-10-04",
         "total": 109.0, "audio": 59.0, "video": 50.0, "open_rss_downloads": 42.0,
         "spotify_native_plays": 17.0, "youtube_views": 50.0, "coverage": "complete",
         "missing_components": []},
        {"period": "2026-10-06", "period_start": "2026-10-05", "period_end": "2026-10-06",
         "total": 70.0, "audio": None, "video": 70.0, "open_rss_downloads": None,
         "spotify_native_plays": None, "youtube_views": 70.0, "coverage": "partial",
         "missing_components": ["open_rss_downloads", "spotify_native_plays"]},
    ]
    rollup = result["summary"]["global_rollup"]
    assert rollup["measured_activity"] == 109
    assert rollup["period_end"] == "2026-10-04"
    assert rollup["comparison"]["total"] == {
        "current": 109.0, "previous": 63.0, "delta": 46.0, "delta_pct": 73.0,
    }


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


def test_insights_selects_primary_source_when_aggregator_evidence_overlaps(temp_db):
    service = GuestWebService(temp_db.db_path)
    common = {
        "provider": "spotify", "metric_name": "plays", "period_start": "2026-09-01",
        "period_end": "2026-09-30", "overlap_group": "spotify_native_plays",
    }
    service.record_growth_observations({"observations": [
        {**common, "metric_value": 100, "source_reference": "spotify.csv", "source_class": "provider_native"},
        {**common, "metric_value": 98, "source_reference": "openpodcast-api:daily", "source_class": "aggregator_copy"},
    ]}, actor="automation")

    result = PodcastInsights(temp_db.db_path).dashboard()

    spotify = next(item for item in result["provider_strength"] if item["provider"] == "spotify")
    assert spotify["metrics"]["plays"] == 100


def test_insights_exposes_structured_youtube_demographics_traffic_and_content(temp_db):
    service = GuestWebService(temp_db.db_path)
    common = {
        "provider": "youtube:uc-one", "period_start": "2026-09-01",
        "period_end": "2026-09-30", "source_reference": "youtube-api",
    }
    service.record_growth_observations({"observations": [
        {**common, "metric_name": "viewer_percentage", "metric_value": 62.5,
         "age_group": "age25-34", "gender": "female"},
        {**common, "metric_name": "traffic_source_views", "metric_value": 44,
         "traffic_source": "YT_SEARCH"},
        {**common, "metric_name": "video_views", "metric_value": 80,
         "platform_content_id": "video-1", "platform_content_title": "Measured episode"},
    ]}, actor="automation")

    result = PodcastInsights(temp_db.db_path).dashboard()

    assert result["demographics"][0]["name"] == "25–34 · Female"
    assert result["demographics"][0]["share_pct"] == 62.5
    assert result["traffic_sources"][0]["name"] == "Yt Search"
    assert result["top_platform_content"][0]["title"] == "Measured episode"
    assert result["top_platform_content"][0]["metrics"]["video_views"] == 80


def test_insights_exposes_host_reported_listening_apps_without_treating_them_as_listings(temp_db):
    service = GuestWebService(temp_db.db_path)
    service.record_growth_observations({"observations": [
        {"provider": "podcast_host", "metric_name": "downloads", "metric_value": 30,
         "period_start": "2026-11-01", "period_end": "2026-11-23", "source_reference": "host-export",
         "source_class": "host_rss_delivery", "app_name": "Pocket Casts"},
        {"provider": "podcast_host", "metric_name": "downloads", "metric_value": 70,
         "period_start": "2026-11-01", "period_end": "2026-11-23", "source_reference": "host-export",
         "source_class": "host_rss_delivery", "app_name": "Apple Podcasts"},
        {"provider": "podcast_host", "metric_name": "downloads", "metric_value": 100,
         "period_start": "2026-11-01", "period_end": "2026-11-23", "source_reference": "host-total",
         "source_class": "host_rss_delivery"},
        {"provider": "another_host", "metric_name": "downloads", "metric_value": 100,
         "period_start": "2026-11-01", "period_end": "2026-11-23", "source_reference": "other-total",
         "source_class": "host_rss_delivery"},
    ]}, actor="automation")

    apps = PodcastInsights(temp_db.db_path).dashboard()["listening_apps"]

    assert [(item["name"], item["value"], item["share_pct"]) for item in apps] == [
        ("Apple Podcasts", 70.0, 70.0),
        ("Pocket Casts", 30.0, 30.0),
    ]


def test_insights_exposes_spotify_host_app_geography_and_demographic_shares(temp_db):
    service = GuestWebService(temp_db.db_path)
    common = {
        "provider": "spotify", "period_start": "2026-10-27", "period_end": "2026-11-25",
        "source_reference": "spotify-audience", "source_class": "provider_native",
    }
    service.record_growth_observations({"observations": [
        {**common, "metric_name": "country_audience_share_pct_united_states", "metric_value": 57.9},
        {**common, "metric_name": "viewer_percentage", "metric_value": 68.8,
         "age_group": "28-34"},
        {**common, "metric_name": "viewer_percentage", "metric_value": 86.6,
         "gender": "male"},
        {**common, "metric_name": "app_share_pct", "metric_value": 8.7,
         "app_name": "Apple Podcasts", "source_class": "host_rss_delivery"},
        {**common, "metric_name": "app_share_pct", "metric_value": 3.5,
         "app_name": "Audible", "source_class": "host_rss_delivery"},
    ]}, actor="automation")

    result = PodcastInsights(temp_db.db_path).dashboard()

    assert result["countries"][0]["name"] == "United States"
    assert result["countries"][0]["is_percentage"] is True
    assert {item["dimension_group"] for item in result["demographics"]} == {"Age Group", "Gender"}
    assert {item["name"] for item in result["demographics"]} == {"28–34", "Male"}
    assert [(item["name"], item["value"]) for item in result["listening_apps"]] == [
        ("Apple Podcasts", 8.7), ("Audible", 3.5),
    ]
    assert all(item["is_percentage"] for item in result["listening_apps"])


def test_source_coverage_never_treats_public_listing_as_private_analytics(temp_db):
    coverage = PodcastSourceMonitor(temp_db.db_path).status()

    assert coverage["public_available"] == 0
    assert coverage["public_expected"] == 9
    assert coverage["private_connected"] == 0
    assert coverage["private_expected"] == 5
    assert all(item["status"] == "provider_access_required" for item in coverage["private"])
    assert coverage["automated_connected"] == 0
    assert coverage["automated_expected"] == 2
    assert coverage["provider_limited_count"] == 3


def test_host_rss_delivery_counts_as_connected_hosting_analytics(temp_db):
    GrowthIntelligence(temp_db.db_path).record_observations([{
        "provider": "spotify", "metric_name": "downloads", "metric_value": 42,
        "period_start": "2026-11-01", "period_end": "2026-11-25",
        "source_reference": "spotify-performance.csv", "source_class": "host_rss_delivery",
    }], actor="test")

    coverage = PodcastSourceMonitor(temp_db.db_path).status()
    hosting = next(item for item in coverage["private"] if item["key"] == "podcast_host")

    assert hosting["status"] == "data_present"
    assert hosting["metrics_present"] == ["downloads"]


def test_directory_discovery_maps_first_party_and_catalog_links_to_platforms():
    payload = b'''<a href="https://goodpods.com/podcasts/show">Goodpods</a>
        <a href="https://music.amazon.de/podcasts/show">Amazon</a>
        <a href="https://pca.st/itunes/1518394292">Pocket Casts</a>
        <a href="https://music.youtube.com/library/podcasts?addrssfeed=x">YouTube Music</a>
        <a href="https://unrelated.example/show">Ignore</a>'''

    assert PodcastSourceMonitor._discover_platform_keys(payload) == {
        "goodpods", "amazon_music", "pocket_casts", "youtube_music_rss",
    }


def test_transient_public_check_failure_preserves_verified_platform(temp_db, monkeypatch):
    verified_at = "2026-11-24T12:00:00Z"
    with connect_database(temp_db.db_path) as conn:
        conn.execute(
            """UPDATE podcast_platform_registry
               SET status='available', evidence_level='verified', last_verified_at=?
               WHERE platform_key='listen_notes'""",
            (verified_at,),
        )
        conn.commit()

    monkeypatch.setattr(
        "guest_database_manager.podcast_source_monitor.urlopen",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(TimeoutError("temporary")),
    )
    PodcastSourceMonitor(temp_db.db_path).run(actor="test", force=True)

    with connect_database(temp_db.db_path) as conn:
        row = conn.execute(
            "SELECT status, evidence_level, last_verified_at, last_error_code "
            "FROM podcast_platform_registry WHERE platform_key='listen_notes'"
        ).fetchone()
    assert tuple(row[:3]) == ("available", "verified", verified_at)
    assert row[3] == "TimeoutError"


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
        {"provider": "apple_podcasts", "metric_name": "country_germany_276", "metric_value": 99,
         "period_start": "2026-09-01", "period_end": "2026-09-30", "source_reference": "legacy"},
    ]}, actor="analyst")

    countries = PodcastInsights(temp_db.db_path).dashboard()["countries"]

    assert countries == [
        {"name": "Germany", "value": 10.0, "provider": "apple_podcasts",
         "period_start": "2026-08-01", "period_end": "2026-09-30", "measure": "plays", "share_pct": 66.7},
        {"name": "Canada", "value": 5.0, "provider": "apple_podcasts",
         "period_start": "2026-09-01", "period_end": "2026-09-30", "measure": "plays", "share_pct": 33.3},
    ]


def test_apple_city_plays_are_available_as_a_separate_drilldown(temp_db):
    service = GuestWebService(temp_db.db_path)
    service.record_growth_observations({"observations": [
        {"provider": "apple_podcasts", "metric_name": "city_plays_berlin_2950159", "metric_value": 12,
         "period_start": "2026-09-01", "period_end": "2026-09-30", "source_reference": "apple-city"},
    ]}, actor="analyst")

    assert PodcastInsights(temp_db.db_path).dashboard()["cities"] == [{
        "name": "Berlin", "value": 12.0, "provider": "apple_podcasts",
        "period_start": "2026-09-01", "period_end": "2026-09-30", "measure": "plays", "share_pct": 100.0,
    }]


def test_platform_totals_and_monthly_trends_preserve_additive_grain(temp_db):
    service = GuestWebService(temp_db.db_path)
    service.record_growth_observations({"observations": [
        {"provider": "spotify", "metric_name": "downloads", "metric_value": 10,
         "period_start": "2026-08-31", "period_end": "2026-08-31", "source_reference": "spotify"},
        {"provider": "spotify", "metric_name": "plays", "metric_value": 5,
         "period_start": "2026-08-31", "period_end": "2026-08-31", "source_reference": "spotify"},
        {"provider": "spotify", "metric_name": "downloads", "metric_value": 20,
         "period_start": "2026-09-01", "period_end": "2026-09-01", "source_reference": "spotify"},
        {"provider": "apple_podcasts", "metric_name": "country_plays_germany_276", "metric_value": 7,
         "period_start": "2026-09-01", "period_end": "2026-09-30", "source_reference": "apple"},
        {"provider": "apple_podcasts", "metric_name": "country_listening_seconds_germany_276", "metric_value": 3600,
         "period_start": "2026-09-01", "period_end": "2026-09-30", "source_reference": "apple"},
        {"provider": "apple_podcasts", "metric_name": "country_listeners_germany_276", "metric_value": 4,
         "period_start": "2026-09-01", "period_end": "2026-09-30", "source_reference": "apple"},
        {"provider": "apple_podcasts", "metric_name": "country_engaged_listeners_germany_276", "metric_value": 2,
         "period_start": "2026-09-01", "period_end": "2026-09-30", "source_reference": "apple"},
        {"provider": "apple_podcasts", "metric_name": "followers", "metric_value": 103,
         "period_start": "2026-09-01", "period_end": "2026-09-30", "source_reference": "followers"},
    ]}, actor="analyst")

    result = PodcastInsights(temp_db.db_path).dashboard()

    assert result["summary"]["spotify_lifetime"] == {
        "period_start": "2026-08-31", "period_end": "2026-09-01", "downloads": 30.0, "plays": 5.0,
    }
    assert result["summary"]["apple"] == {
        "period_start": "2026-09-01", "period_end": "2026-09-30", "plays": 7.0,
        "listening_time_hours": 1.0, "latest_month_listeners": 4.0,
        "latest_month_engaged_listeners": 2.0, "followers": 103.0,
    }
    assert result["monthly_trends"] == {
        "spotify": [
            {"period": "2026-08", "downloads": 10.0, "plays": 5.0},
            {"period": "2026-09", "downloads": 20.0, "plays": 0.0},
        ],
        "apple_podcasts": [{"period": "2026-09", "plays": 7.0, "listening_time_hours": 1.0,
                            "listeners": 4.0, "engaged_listeners": 2.0}],
    }
    assert result["daily_trends"]["spotify"] == [
        {"period": "2026-08-31", "downloads": 10.0, "plays": 5.0, "audience": 0.0},
        {"period": "2026-09-01", "downloads": 20.0, "plays": 0.0, "audience": 0.0},
    ]


def test_percentage_dimensions_use_latest_duplicate_observation_once():
    rows = [
        {"provider": "spotify", "metric_name": "app_share_pct", "metric_value": 53.1,
         "period_end": "2026-11-25", "app_name": "Web Browser", "imported_at": "2026-11-25T10:00:00"},
        {"provider": "spotify", "metric_name": "app_share_pct", "metric_value": 53.1,
         "period_end": "2026-11-25", "app_name": "Web Browser", "imported_at": "2026-11-25T11:00:00"},
        {"provider": "spotify", "metric_name": "app_share_pct", "metric_value": 24.2,
         "period_end": "2026-11-25", "app_name": "Spotify", "imported_at": "2026-11-25T11:00:00"},
    ]

    result = PodcastInsights._structured_dimension_breakdown(
        rows, metric="app_share_pct", label_fields=("app_name",), percentage_values=True,
    )

    assert [(item["name"], item["value"]) for item in result] == [
        ("Web Browser", 53.1), ("Spotify", 24.2),
    ]


def test_prefixed_percentage_dimensions_do_not_sum_repeated_imports():
    rows = [
        {"provider": "spotify", "metric_name": "country_audience_share_pct_united_states",
         "metric_value": 57.85, "period_end": "2026-11-25", "episode_id": None,
         "imported_at": "2026-11-25T10:00:00"},
        {"provider": "spotify", "metric_name": "country_audience_share_pct_united_states",
         "metric_value": 57.85, "period_end": "2026-11-25", "episode_id": None,
         "imported_at": "2026-11-25T11:00:00"},
    ]

    assert PodcastInsights._dimension_breakdown(rows, "country_")[0]["value"] == 57.85


def test_topline_summary_reconciles_six_metrics_without_claiming_unique_people():
    daily = [
        {"period": f"2026-10-{day:02d}", "downloads": 10, "plays": 0}
        for day in range(1, 31)
    ] + [
        {"period": f"2026-11-{day:02d}", "downloads": 12, "plays": 0}
        for day in range(1, 31)
    ]
    rows = [
        {"provider": "youtube:one", "metric_name": "lifetime_plays", "metric_value": 50,
         "episode_id": None, "source_class": "", "overlap_group": "", "source_reference": "youtube",
         "imported_at": "2026-11-25T12:00:00"},
        {"provider": "youtube:one", "metric_name": "lifetime_watch_time_hours", "metric_value": 20,
         "episode_id": None, "source_class": "", "overlap_group": "", "source_reference": "youtube",
         "imported_at": "2026-11-25T12:00:00"},
    ]

    result = PodcastInsights._topline_summary(
        rows=rows,
        platforms=[{"availability": "available"}, {"availability": "unavailable"}],
        countries=[
            {"name": "Germany", "value": 4}, {"name": " germany ", "value": 3},
            {"name": "Canada", "value": 2}, {"name": "Unknown", "value": 5},
        ],
        audience_by_platform=[
            {"provider": "youtube:one", "metric": "subscribers", "value": 100, "period_end": "2026-11-25"},
            {"provider": "apple_podcasts", "metric": "followers", "value": 20, "period_end": "2026-11-25"},
            {"provider": "spotify", "metric": "unique_listeners", "value": 5, "period_end": "2026-11-25"},
        ],
        spotify_daily=daily,
        spotify_lifetime={"downloads": 1_000, "plays": 500},
        apple_summary={"listening_time_hours": 10},
    )

    assert result["downloads_plays"] == 1_550
    assert result["listening_watch_hours"] == 30
    assert result["countries_reached"] == 2
    assert result["platforms_available"] == 1
    assert result["audience_relationships"] == 120
    assert result["audience_relationship_by_platform"][-1]["value"] == 5
    assert result["growth_pct"] == 20
    assert "not additive" in result["audience_relationship_note"]
