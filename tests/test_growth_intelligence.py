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
