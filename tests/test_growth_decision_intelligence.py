from datetime import datetime, timedelta, timezone

from guest_database_manager.db_connection import connect_database
from guest_database_manager.growth_decision_intelligence import GrowthDecisionIntelligence


def test_growth_intelligence_builds_explainable_advisory_signals_without_writes(temp_db):
    start = datetime(2025, 1, 7, 6, tzinfo=timezone.utc)
    with connect_database(temp_db.db_path) as conn:
        for index in range(12):
            published = (start + timedelta(days=7 * index)).isoformat().replace("+00:00", "Z")
            conn.execute(
                """INSERT INTO rss_feed_items
                   (feed_url, item_key, guid, title, normalized_title, published_at, link,
                    enclosure_url, content_hash, first_seen_at, last_seen_at)
                   VALUES ('feed', ?, ?, ?, ?, ?, '', '', ?, ?, ?)""",
                (f"key-{index}", f"guid-{index}", f"Episode {index}", f"episode {index}",
                 published, f"hash-{index}", published, published),
            )
        conn.commit()
        before = conn.execute("SELECT COUNT(*) FROM audit_events").fetchone()[0]

    monthly = {
        "spotify": [
            {"period": f"2025-{month:02d}", "downloads": 80 if month <= 3 else 96,
             "plays": 20 if month <= 3 else 24}
            for month in range(1, 7)
        ],
        "apple_podcasts": [
            {"period": f"2025-{month:02d}", "plays": 50 if month <= 3 else 40}
            for month in range(1, 7)
        ],
    }
    result = GrowthDecisionIntelligence(temp_db.db_path).dashboard(
        monthly, {"evidence_progress": {"linked": 4, "minimum": 30}}
    )

    assert result["mode"] == "advisory_shadow"
    assert result["signals"]["spotify_momentum"]["change_pct"] == 20.0
    assert result["signals"]["apple_momentum"]["change_pct"] == -20.0
    assert result["signals"]["release_cadence"]["median_days_between_releases"] == 7
    assert result["guardrails"]["ranking_changed"] is False
    assert result["guardrails"]["publishing_changed"] is False
    assert {item["id"] for item in result["recommendations"]} == {
        "spotify-momentum", "apple-podcasts-momentum", "release-cadence", "learning-evidence",
    }
    with connect_database(temp_db.db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM audit_events").fetchone()[0] == before
