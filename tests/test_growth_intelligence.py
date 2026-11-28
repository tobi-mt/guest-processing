from __future__ import annotations

import sqlite3

import pytest

from guest_database_manager.growth_intelligence import GrowthIntelligence, GrowthIntelligenceError


def _observation(episode_id, metric_name, metric_value, **overrides):
    row = {
        "episode_id": episode_id,
        "provider": "youtube",
        "metric_name": metric_name,
        "metric_value": metric_value,
        "traffic_scope": "organic" if metric_name == "organic_reach" else "paid" if metric_name == "paid_reach" else "all",
        "period_start": "2026-09-01",
        "period_end": "2026-09-07",
        "source_reference": "youtube-export-2026-09-08.csv",
    }
    row.update(overrides)
    return row


def test_growth_observations_are_append_only_idempotent_and_source_backed(temp_db):
    episode_id, _ = temp_db.upsert_episode({"guest_name": "Growth Guest", "episode_title": "Healing Trauma"})
    intelligence = GrowthIntelligence(temp_db.db_path)
    row = _observation(episode_id, "organic_reach", 1200)

    first = intelligence.record_observations([row], actor="producer", correlation_id="import-1")
    duplicate = intelligence.record_observations([row], actor="producer", correlation_id="import-1")
    renamed_export = intelligence.record_observations([{**row, "source_reference": "renamed-export.csv"}], actor="producer")
    explicit_retry = intelligence.record_observations([{**row, "idempotency_key": "different-request"}], actor="producer")

    assert first == {"submitted": 1, "inserted": 1, "duplicates": 0}
    assert duplicate == {"submitted": 1, "inserted": 0, "duplicates": 1}
    assert renamed_export == {"submitted": 1, "inserted": 0, "duplicates": 1}
    assert explicit_retry == {"submitted": 1, "inserted": 0, "duplicates": 1}
    with sqlite3.connect(temp_db.db_path) as conn:
        saved = conn.execute("SELECT actor, correlation_id, source_reference, source_hash FROM growth_metric_observations").fetchone()
    assert saved[:3] == ("producer", "import-1", "youtube-export-2026-09-08.csv")
    assert len(saved[3]) == 64


def test_growth_observations_are_database_immutable_and_block_episode_deletion(temp_db):
    episode_id, _ = temp_db.upsert_episode({"guest_name": "Evidence Guest", "episode_title": "Evidence"})
    intelligence = GrowthIntelligence(temp_db.db_path)
    intelligence.record_observations([_observation(episode_id, "organic_reach", 10)], actor="producer")

    with sqlite3.connect(temp_db.db_path) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            conn.execute("UPDATE growth_metric_observations SET metric_value = 11")
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            conn.execute("DELETE FROM growth_metric_observations")
        with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
            conn.execute("DELETE FROM episodes WHERE id = ?", (episode_id,))


def test_growth_observation_corrections_append_a_revision_and_current_view_selects_it(temp_db):
    intelligence = GrowthIntelligence(temp_db.db_path)
    original = _observation(None, "downloads", 100)

    intelligence.record_observations([original], actor="collector", correlation_id="daily-1")
    revised = intelligence.record_observations(
        [{**original, "metric_value": 106}], actor="collector", correlation_id="daily-2"
    )

    assert revised == {"submitted": 1, "inserted": 1, "duplicates": 0, "revised": 1}
    with sqlite3.connect(temp_db.db_path) as conn:
        history = conn.execute(
            "SELECT metric_value, revision, supersedes_id FROM growth_metric_observations ORDER BY revision"
        ).fetchall()
        current = conn.execute(
            "SELECT metric_value, revision FROM current_growth_metric_observations"
        ).fetchone()
    assert history == [(100, 1, None), (106, 2, 1)]
    assert current == (106, 2)


def test_growth_validation_rejects_ambiguous_or_unsafe_evidence(temp_db):
    intelligence = GrowthIntelligence(temp_db.db_path)

    with pytest.raises(GrowthIntelligenceError, match="existing episode"):
        intelligence.record_observations([_observation(999, "organic_reach", 1)], actor="producer")
    with pytest.raises(GrowthIntelligenceError, match="organic traffic_scope"):
        intelligence.record_observations([_observation(None, "organic_reach", 1, traffic_scope="all")], actor="producer")
    with pytest.raises(GrowthIntelligenceError, match="cannot exceed 100"):
        intelligence.record_observations([_observation(None, "conversion_rate_pct", 101)], actor="producer")
    with pytest.raises(GrowthIntelligenceError, match="Unsupported"):
        intelligence.record_observations([_observation(None, "views", 10)], actor="producer")


def test_canonical_csv_preserves_host_app_device_and_geography_dimensions(temp_db):
    intelligence = GrowthIntelligence(temp_db.db_path)
    preview = intelligence.preview_csv(
        "provider,metric_name,metric_value,period_start,period_end,source_reference,app_name,device_type,country_code,source_class\n"
        "podcast_host,downloads,42,2026-11-01,2026-11-23,host-export.csv,Pocket Casts,mobile,DE,host_rss_delivery\n",
        provider="podcast_host",
        source_reference="host-export.csv",
    )

    assert preview["summary"]["ready"] == 1
    observation = preview["observations"][0]
    assert observation["app_name"] == "Pocket Casts"
    assert observation["device_type"] == "mobile"
    assert observation["country_code"] == "DE"
    assert observation["source_class"] == "host_rss_delivery"

    intelligence.record_observations(preview["observations"], actor="test")
    with sqlite3.connect(temp_db.db_path) as conn:
        saved = conn.execute(
            "SELECT app_name, device_type, country_code, source_class FROM growth_metric_observations"
        ).fetchone()
    assert saved == ("Pocket Casts", "mobile", "DE", "host_rss_delivery")


def test_mirror_fan_score_requires_all_dimensions_and_separates_paid_reach(temp_db):
    episode_id, _ = temp_db.upsert_episode({"guest_name": "MFS Guest", "episode_title": "Purpose and Identity"})
    intelligence = GrowthIntelligence(temp_db.db_path)
    intelligence.record_observations([
        _observation(episode_id, "organic_reach", 5000),
        _observation(episode_id, "paid_reach", 20000),
        _observation(episode_id, "consumption_depth_pct", 50),
    ], actor="producer")

    incomplete = intelligence.dashboard()
    assert incomplete["reach"] == {"organic": 5000.0, "paid": 20000.0, "paid_share_pct": 80.0}
    assert incomplete["distribution"]["guest_shares"] == 0
    assert incomplete["episode_scores"][0]["mfs"]["status"] == "incomplete"

    intelligence.record_observations([
        _observation(episode_id, "conversion_rate_pct", 25),
        _observation(episode_id, "return_rate_pct", 40),
    ], actor="producer")
    ready = intelligence.dashboard()["episode_scores"][0]["mfs"]
    assert ready["status"] == "ready"
    assert ready["score"] == 47.3
    assert "Geometric mean" in ready["method"]


def test_dashboard_does_not_sum_historical_snapshots_or_mix_mfs_periods(temp_db):
    episode_id, _ = temp_db.upsert_episode({"guest_name": "Window Guest", "episode_title": "Identity"})
    intelligence = GrowthIntelligence(temp_db.db_path)
    intelligence.record_observations([
        _observation(episode_id, "organic_reach", 900, period_start="2026-08-01", period_end="2026-08-07", source_reference="old.csv"),
        _observation(episode_id, "organic_reach", 1200),
        _observation(episode_id, "consumption_depth_pct", 50),
        _observation(episode_id, "conversion_rate_pct", 10, period_start="2026-08-01", period_end="2026-08-07", source_reference="old.csv"),
        _observation(episode_id, "return_rate_pct", 20, period_start="2026-08-01", period_end="2026-08-07", source_reference="old.csv"),
    ], actor="producer")

    dashboard = intelligence.dashboard()

    assert dashboard["reach"]["organic"] == 1200
    assert dashboard["episode_scores"][0]["mfs"]["status"] == "incomplete"
    assert set(dashboard["episode_scores"][0]["mfs"]["missing_metrics"]) == {"conversion_rate_pct", "return_rate_pct"}


def test_dashboard_reports_editorial_mix_freshness_and_experiments(temp_db):
    temp_db.upsert_episode({"guest_name": "Archive Guest", "episode_title": "Healing Grief", "topic": "healing grief", "release_status": "released", "production_status": "released", "promotion_status": "released"})
    intelligence = GrowthIntelligence(temp_db.db_path)
    experiment = intelligence.create_experiment({
        "name": "Monday flagship",
        "hypothesis": "Monday improves organic reach",
        "primary_metric": "organic_reach",
        "control_label": "Tuesday 17:00",
        "treatment_label": "Monday 16:00",
        "starts_on": "2026-09-01",
        "ends_on": "2026-12-01",
    }, actor="producer")

    dashboard = intelligence.dashboard()
    assert dashboard["freshness"] == "no_data"
    assert dashboard["editorial_mix"][0]["pillar"] == "Heal"
    assert dashboard["editorial_mix"][0]["actual_share_pct"] == 100.0
    assert experiment["status"] == "draft"
    assert dashboard["experiments"][0]["name"] == "Monday flagship"


def test_csv_preview_maps_columns_links_unique_episode_and_does_not_write(temp_db):
    episode_id, _ = temp_db.upsert_episode({
        "guest_name": "Amina Hart",
        "episode_title": "Healing With Courage",
    })
    intelligence = GrowthIntelligence(temp_db.db_path)
    csv_text = "\n".join([
        "Episode Title,Guest,Metric,Value,Start Date,End Date",
        "Healing With Courage,Amina Hart,organic_reach,1200,2026-09-01,2026-09-07",
        "Healing With Courage,Amina Hart,conversion_rate_pct,17.5,2026-09-01,2026-09-07",
    ])

    preview = intelligence.preview_csv(
        csv_text,
        provider="youtube",
        source_reference="youtube-week-36.csv",
    )

    assert preview["summary"] == {
        "submitted": 2,
        "ready": 2,
        "invalid": 0,
        "duplicates": 0,
        "linked_to_episode": 2,
        "unlinked": 0,
    }
    assert preview["observations"][0]["episode_id"] == episode_id
    assert preview["observations"][0]["traffic_scope"] == "organic"
    assert preview["quality"]["missing_mfs_metrics"] == ["consumption_depth_pct", "return_rate_pct"]
    with sqlite3.connect(temp_db.db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM growth_metric_observations").fetchone()[0] == 0


def test_csv_preview_flags_invalid_ambiguous_and_duplicate_rows(temp_db):
    for guest in ("First Guest", "Second Guest"):
        temp_db.upsert_episode({"guest_name": guest, "episode_title": "Shared Title"})
    intelligence = GrowthIntelligence(temp_db.db_path)
    existing = _observation(None, "organic_reach", 100)
    intelligence.record_observations([existing], actor="producer")
    csv_text = "\n".join([
        "title,metric_name,metric_value,period_start,period_end,traffic_scope",
        "Shared Title,organic_reach,100,2026-09-01,2026-09-07,organic",
        "Shared Title,conversion_rate_pct,101,2026-09-01,2026-09-07,all",
    ])

    preview = intelligence.preview_csv(
        csv_text,
        provider="youtube",
        source_reference="retry.csv",
    )

    assert preview["summary"]["duplicates"] == 1
    assert preview["summary"]["invalid"] == 1
    assert preview["summary"]["ready"] == 0
    assert "ambiguous" in preview["rows"][0]["warnings"][0].lower()
    assert "cannot exceed 100" in preview["rows"][1]["errors"][0]


def test_csv_preview_requires_mappable_required_columns(temp_db):
    intelligence = GrowthIntelligence(temp_db.db_path)

    with pytest.raises(GrowthIntelligenceError, match="Map the required CSV columns"):
        intelligence.preview_csv(
            "Something,Else\na,b",
            provider="youtube",
            source_reference="unknown.csv",
        )


def test_csv_preview_unfolds_wide_canonical_metric_columns(temp_db):
    episode_id, _ = temp_db.upsert_episode({
        "guest_name": "Wide Guest",
        "episode_title": "Wide Analytics",
    })
    intelligence = GrowthIntelligence(temp_db.db_path)
    preview = intelligence.preview_csv(
        "episode_id,start,end,organic_reach,consumption_depth_pct\n"
        f"{episode_id},2026-09-01,2026-09-07,1200,48",
        provider="youtube",
        source_reference="wide-export.csv",
    )

    assert preview["format"] == "wide"
    assert preview["summary"]["ready"] == 2
    assert {item["metric_name"] for item in preview["observations"]} == {
        "organic_reach",
        "consumption_depth_pct",
    }


def test_csv_preview_recognizes_provider_export_aliases_and_single_date_column(temp_db):
    intelligence = GrowthIntelligence(temp_db.db_path)

    preview = intelligence.preview_csv(
        'Date,Plays,Audience,Downloads,Average Consumption\n"Sep 22, 2026",181,72,240,54.5',
        provider="spotify",
        source_reference="spotify-overview.csv",
    )

    assert preview["format"] == "wide"
    assert preview["summary"]["ready"] == 4
    assert {item["metric_name"] for item in preview["observations"]} == {
        "plays", "unique_listeners", "downloads", "consumption_depth_pct",
    }
    assert {item["period_start"] for item in preview["observations"]} == {"2026-09-22"}
    assert {item["period_end"] for item in preview["observations"]} == {"2026-09-22"}


def test_spotify_all_time_export_is_detected_without_double_counting_combined_columns(temp_db):
    intelligence = GrowthIntelligence(temp_db.db_path)
    preview = intelligence.preview_csv(
        "Date,Plays & downloads,Plays (on Spotify),Downloads (everywhere else),Audience,"
        "Audience (on Spotify),Audience (everywhere else)\n"
        "6/12/2020,12,9,3,4,2,2",
        provider="spotify",
        source_reference="spotify-all-time.csv",
    )

    assert preview["format"] == "provider"
    assert preview["summary"]["ready"] == 3
    assert {(row["metric_name"], row["metric_value"]) for row in preview["observations"]} == {
        ("plays", 9.0), ("downloads", 3.0), ("unique_listeners", 4.0),
    }


def test_spotify_lifetime_episode_export_is_rankable_without_inflating_show_totals(temp_db):
    intelligence = GrowthIntelligence(temp_db.db_path)
    preview = intelligence.preview_csv(
        "Episode name,Publish date,Performance,Plays & downloads,Analytics Period Start,Analytics Period End\n"
        "A Source-backed Episode,06/12/2020,1,4321,2020-06-12,2026-11-27\n",
        provider="spotify",
        source_reference="spotify-episodes.csv",
    )

    assert preview["format"] == "provider"
    assert preview["summary"]["ready"] == 1
    row = preview["observations"][0]
    assert (row["metric_name"], row["metric_value"]) == ("plays_downloads", 4321.0)
    assert row["platform_content_title"] == "A Source-backed Episode"
    assert row["platform_content_id"] == "title:a source backed episode"
    assert row["episode_id"] is None


@pytest.mark.parametrize("provider", ["spotify", "apple_podcasts"])
def test_provider_audience_snapshot_keeps_followers_and_listeners_distinct(temp_db, provider):
    preview = GrowthIntelligence(temp_db.db_path).preview_csv(
        "Snapshot Date,Followers,Listeners\n2026-11-25,4321,1234\n",
        provider=provider,
        source_reference="audience-snapshot.csv",
    )

    assert preview["format"] == "provider"
    assert {(row["metric_name"], row["metric_value"]) for row in preview["observations"]} == {
        ("followers", 4321.0), ("listeners", 1234.0),
    }


@pytest.mark.parametrize(
    ("csv_text", "expected"),
    [
        (
            "Gender,Percentage,Analytics Period Start,Analytics Period End\n"
            "Female,12.9,2026-10-27,2026-11-25\n",
            ("viewer_percentage", "gender", "female", 12.9),
        ),
        (
            "Age,Total percentage,Analytics Period Start,Analytics Period End\n"
            "28-34,68.8,2026-10-27,2026-11-25\n",
            ("viewer_percentage", "age_group", "28_34", 68.8),
        ),
        (
            "Geo,Percentage,Analytics Period Start,Analytics Period End\n"
            "United States,57.9,2026-10-27,2026-11-25\n",
            ("country_audience_share_pct_united_states", None, "", 57.9),
        ),
        (
            "App,Percentage,Analytics Period Start,Analytics Period End\n"
            "Apple Podcasts,8.7,2026-10-27,2026-11-25\n",
            ("app_share_pct", "app_name", "Apple Podcasts", 8.7),
        ),
    ],
)
def test_spotify_audience_dimension_exports_are_normalized(temp_db, csv_text, expected):
    preview = GrowthIntelligence(temp_db.db_path).preview_csv(
        csv_text, provider="spotify", source_reference="spotify-audience.csv",
    )

    assert preview["format"] == "provider"
    assert preview["summary"]["ready"] == 1
    row = preview["observations"][0]
    metric, dimension, dimension_value, value = expected
    assert row["metric_name"] == metric
    assert row["metric_value"] == value
    if dimension:
        assert row[dimension] == dimension_value


def test_spotify_audience_composition_export_is_normalized(temp_db):
    preview = GrowthIntelligence(temp_db.db_path).preview_csv(
        "Date,Total,Returning,New,Analytics Period Start,Analytics Period End\n"
        "11/25/2026,120,45,75,2026-10-27,2026-11-25\n",
        provider="spotify", source_reference="spotify-audience-composition.csv",
    )

    assert preview["format"] == "provider"
    assert preview["summary"]["ready"] == 3
    assert {row["metric_name"]: row["metric_value"] for row in preview["observations"]} == {
        "unique_listeners": 120,
        "returning_listeners": 45,
        "new_listeners": 75,
    }


def test_provider_export_accepts_more_than_legacy_500_row_limit(temp_db):
    intelligence = GrowthIntelligence(temp_db.db_path)
    rows = [
        f"2025-01-{(index % 28) + 1:02d},{index + 10},{index + 7},3,4,2,2"
        for index in range(501)
    ]
    preview = intelligence.preview_csv(
        "Date,Plays & downloads,Plays (on Spotify),Downloads (everywhere else),Audience,"
        "Audience (on Spotify),Audience (everywhere else)\n" + "\n".join(rows),
        provider="spotify",
        source_reference="spotify-large.csv",
    )

    assert preview["summary"]["submitted"] == 1503


def test_apple_country_export_preserves_month_and_location_grain(temp_db):
    intelligence = GrowthIntelligence(temp_db.db_path)
    preview = intelligence.preview_csv(
        "Show ID,Country/Region Code,Country/Region,Date,Total Time Listened,Plays,"
        "Unique Listeners,Unique Engaged Listeners\n"
        "1518394292,276,Germany,20260901,120,7,4,2",
        provider="apple_podcasts",
        source_reference="apple-country.csv",
    )

    assert preview["format"] == "provider"
    assert preview["summary"]["ready"] == 4
    metrics = {row["metric_name"]: row["metric_value"] for row in preview["observations"]}
    assert metrics == {
        "country_plays_germany_276": 7,
        "country_listening_seconds_germany_276": 120,
        "country_listeners_germany_276": 4,
        "country_engaged_listeners_germany_276": 2,
    }
    assert preview["observations"][0]["period_start"] == "2026-09-01"
    assert preview["observations"][0]["period_end"] == "2026-09-30"


def test_current_apple_episode_export_preserves_window_and_provider_identity(temp_db):
    intelligence = GrowthIntelligence(temp_db.db_path)
    preview = intelligence.preview_csv(
        "Show Name,Episode ID,Episode GUID,Episode Number,Episode Title,Release Date,Duration,"
        "Unique Listeners,Unique Engaged Listeners,Plays,Average Consumption,"
        "Analytics Period Start,Analytics Period End\n"
        "Mirror Talk,1001,guid-1,468,Provider-only Episode,2026-11-24,3600,2,1,3,75%,"
        "2026-09-27,2026-11-25\n",
        provider="apple_podcasts",
        source_reference="apple-episodes.csv",
    )

    assert preview["format"] == "provider"
    assert preview["summary"] == {
        "submitted": 3, "ready": 3, "invalid": 0, "duplicates": 0,
        "linked_to_episode": 0, "unlinked": 3,
    }
    assert {row["metric_name"] for row in preview["observations"]} == {
        "plays", "unique_listeners", "engaged_listeners",
    }
    assert {row["period_start"] for row in preview["observations"]} == {"2026-09-27"}
    assert {row["period_end"] for row in preview["observations"]} == {"2026-11-25"}
    assert {row["platform_content_id"] for row in preview["observations"]} == {"1001"}


def test_apple_episode_export_requires_unique_internal_title_match(temp_db):
    intelligence = GrowthIntelligence(temp_db.db_path)
    csv_text = (
        "Show ID,Episode ID,Episode Title,Date,Total Time Listened,Plays,Unique Listeners,"
        "Unique Engaged Listeners\n"
        "1518394292,1001,Known Episode,20260901,120,7,4,2"
    )
    unmatched = intelligence.preview_csv(
        csv_text, provider="apple_podcasts", source_reference="apple-episodes.csv"
    )
    assert unmatched["summary"]["invalid"] == 3
    assert unmatched["summary"]["ready"] == 0

    episode_id, _ = temp_db.upsert_episode({"guest_name": "Guest", "episode_title": "Known Episode"})
    matched = intelligence.preview_csv(
        csv_text, provider="apple_podcasts", source_reference="apple-episodes.csv"
    )
    assert matched["summary"]["ready"] == 3
    assert {row["episode_id"] for row in matched["observations"]} == {episode_id}


def test_apple_follower_export_imports_current_net_follower_stock(temp_db):
    intelligence = GrowthIntelligence(temp_db.db_path)
    preview = intelligence.preview_csv(
        "Date,Net Followers,Gross Followers,Gross Unfollowers\n20260901,8,10,2",
        provider="apple_podcasts",
        source_reference="apple-followers.csv",
    )

    assert preview["summary"]["ready"] == 1
    assert preview["observations"][0]["metric_name"] == "followers"
    assert preview["observations"][0]["metric_value"] == 8


def test_dashboard_groups_import_history_by_correlation_id(temp_db):
    intelligence = GrowthIntelligence(temp_db.db_path)
    intelligence.record_observations(
        [_observation(None, "organic_reach", 100), _observation(None, "conversion_rate_pct", 10)],
        actor="producer",
        correlation_id="batch-42",
    )

    history = intelligence.dashboard()["import_history"]

    assert history[0]["batch_key"] == "batch-42"
    assert history[0]["observation_count"] == 2
    assert history[0]["actor"] == "producer"
