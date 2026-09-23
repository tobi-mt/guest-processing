from __future__ import annotations

from guest_database_manager.exception_center import build_exception_center
from guest_database_manager.growth_intelligence import GrowthIntelligence


def test_exception_center_combines_evidence_content_and_urgent_workflow(temp_db):
    temp_db.upsert_episode({
        "guest_name": "Released Guest",
        "episode_title": "Released Without Transcript",
        "release_status": "released",
        "production_status": "released",
        "promotion_status": "released",
        "release_date": "2026-09-01",
    })
    action_queue = {
        "items": [{
            "key": "episode:1:readiness",
            "priority": "urgent",
            "next_action": "Resolve release blockers",
            "title": "Urgent Episode",
            "reason": "Artwork is missing.",
            "href": "/planning?episode_id=1",
            "action_label": "Fix episode",
        }]
    }

    payload = build_exception_center(
        temp_db.db_path,
        action_queue=action_queue,
        growth=GrowthIntelligence(temp_db.db_path).dashboard(),
    )

    keys = {item["key"] for item in payload["items"]}
    assert payload["status"] == "attention"
    assert "evidence:no_growth_data" in keys
    assert "content:missing_transcript" in keys
    assert "workflow:episode:1:readiness" in keys
    assert payload["counts"]["high"] >= 2


def test_exception_center_is_clear_when_sources_have_no_findings(temp_db):
    growth = GrowthIntelligence(temp_db.db_path).dashboard()
    growth["quality"]["observation_count"] = 1
    growth["freshness"] = "current"

    payload = build_exception_center(temp_db.db_path, action_queue={"items": []}, growth=growth)

    assert payload["status"] == "clear"
    assert payload["items"] == []
    assert payload["integrity"]["sqlite_integrity"] == ["ok"]


def test_exception_center_includes_calendar_discrepancies(temp_db):
    growth = GrowthIntelligence(temp_db.db_path).dashboard()
    growth["quality"]["observation_count"] = 1
    growth["freshness"] = "current"
    payload = build_exception_center(
        temp_db.db_path,
        action_queue={"items": []},
        growth=growth,
        operations_alerts={
            "double_bookings": [{"guest_name": "Ada", "count": 2}],
            "calendar_cleanup": [{"id": 7}],
        },
    )
    keys = {item["key"] for item in payload["items"]}
    assert "calendar:double_bookings" in keys
    assert "calendar:cleanup" in keys
