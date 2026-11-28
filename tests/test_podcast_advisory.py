import sqlite3

from guest_database_manager.growth_intelligence import GrowthIntelligence
from guest_database_manager.podcast_advisory import PodcastAdvisory
from guest_database_manager.web_interface import GuestWebService


def _episode(temp_db, title, category, guest, release_date):
    episode_id, _ = temp_db.upsert_episode({
        "episode_title": title, "working_title": title, "category": category,
        "guest_name": guest, "release_date": release_date, "release_status": "released",
    })
    return episode_id


def test_advisory_uses_episode_evidence_without_changing_workflow_state(temp_db):
    first = _episode(temp_db, "Healing one", "Healing", "Guest A", "2026-10-01")
    second = _episode(temp_db, "Healing two", "Healing", "Guest B", "2026-10-08")
    observations = []
    for episode_id, value in ((first, 30), (second, 50)):
        for day in ("2026-10-01", "2026-10-02", "2026-10-03"):
            observations.append({
                "episode_id": episode_id, "provider": "podcast_host", "metric_name": "downloads",
                "metric_value": value, "period_start": day, "period_end": day,
                "source_reference": "host-daily", "source_class": "host_rss_delivery",
                "overlap_group": "open_rss_downloads",
            })
    GrowthIntelligence(temp_db.db_path).record_observations(observations, actor="test")
    insights = GuestWebService(temp_db.db_path).podcast_insights.dashboard()

    result = PodcastAdvisory(temp_db.db_path).dashboard(insights)

    assert result["mode"] == "advisory"
    assert result["guardrails"]["changes_workflow_state"] is False
    assert result["release_planning"]["category_benchmarks"][0]["name"] == "Healing"
    assert result["recommendation_learning"]["eligible_episode_outcomes"] == 2


def test_sponsor_export_has_definitions_and_excludes_private_connection_details(temp_db):
    episode_id = _episode(temp_db, "Measured episode", "Purpose", "Guest", "2026-11-01")
    GrowthIntelligence(temp_db.db_path).record_observations([{
        "episode_id": episode_id, "provider": "spotify", "metric_name": "plays",
        "metric_value": 42, "period_start": "2026-11-01", "period_end": "2026-11-07",
        "source_reference": "spotify-performance.csv", "source_class": "provider_native",
    }], actor="test")

    exported = GuestWebService(temp_db.db_path).export_podcast_reach_csv()

    assert "section,metric,value,period_or_as_of,definition_or_note" in exported
    assert "Platform performance,spotify — plays,42.0" in exported
    assert "Episode performance,Measured episode,42.0" in exported
    assert "collector_token" not in exported
    assert "last_error_code" not in exported


def test_episode_analytics_automatically_link_to_the_prior_recommendation(temp_db):
    service = GuestWebService(temp_db.db_path)
    episode = service.create_episode({
        "guest_name": "Learning Guest", "episode_title": "Learning Episode",
        "release_status": "released", "release_date": "2026-11-01",
    })
    service.recommendation_learning.observe(
        [{**episode, "priority_score": 75, "promotion_readiness": {"score": 80}}],
        actor="producer", correlation_id="learning-episode-recommendation",
    )
    with sqlite3.connect(temp_db.db_path) as conn:
        conn.execute(
            "UPDATE recommendation_observations SET created_at='2026-10-31 12:00:00' WHERE episode_id=?",
            (episode["id"],),
        )

    result = service.record_growth_observations({"observations": [{
        "episode_id": episode["id"], "provider": "spotify", "metric_name": "plays",
        "metric_value": 120, "period_start": "2026-11-01", "period_end": "2026-11-07",
        "source_reference": "spotify-performance.csv", "source_class": "provider_native",
    }]}, actor="analytics-automation")

    assert result["learning_outcomes"] == 1
    with sqlite3.connect(temp_db.db_path) as conn:
        outcome = conn.execute(
            "SELECT source, observation_id, metadata_json FROM recommendation_outcomes WHERE episode_id=?",
            (episode["id"],),
        ).fetchone()
    assert outcome[0] == "podcast_analytics_automation"
    assert outcome[1] is not None
    assert "midrank percentile" in outcome[2]


def test_promotion_advice_names_connected_youtube_channel(temp_db):
    insights = {
        "provider_strength": [{"provider": "youtube:ucabc", "metrics": {"plays": 50}}],
        "analytics_connectors": {"google": {"connections": [
            {"youtube_channel_id": "UCabc", "youtube_channel_title": "Mirror Talk"},
        ]}},
    }

    result = PodcastAdvisory(temp_db.db_path).dashboard(insights)

    actions = [item["action"] for item in result["promotion_planning"]["recommendations"]]
    assert "Prioritize the next measured promotion check on YouTube (Mirror Talk)." in actions
