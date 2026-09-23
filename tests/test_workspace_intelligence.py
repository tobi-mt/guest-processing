from __future__ import annotations

from guest_database_manager.workspace_intelligence import build_personal_briefing, search_workspace


def test_workspace_search_finds_guests_episodes_transcripts_actions_and_exceptions(temp_db):
    guest_id, _ = temp_db.upsert_guest({"full_name": "Ada Example", "email": "ada@example.com"})
    episode_id, _ = temp_db.upsert_episode({
        "guest_id": guest_id,
        "guest_name": "Ada Example",
        "episode_title": "Resilient Systems",
        "transcript_text": "A discussion about graceful recovery and observability.",
        "release_status": "unplanned",
    })
    actions = {"items": [{"key": f"episode:{episode_id}", "title": "Resilient Systems", "next_action": "Schedule release", "reason": "Ready", "href": "/planning"}]}
    exceptions = {"items": [{"key": "content:test", "title": "Resilient assets", "reason": "Artwork needed", "category": "content", "href": "/planning"}]}

    payload = search_workspace(temp_db.db_path, "resilient", action_queue=actions, exceptions=exceptions)

    kinds = {item["kind"] for item in payload["results"]}
    assert {"episode", "action", "exception"} <= kinds
    episode = next(item for item in payload["results"] if item["kind"] == "episode")
    assert episode["secondary_command"] == "Schedule"
    assert "action=schedule" in episode["secondary_href"]

    transcript = search_workspace(temp_db.db_path, "observability", action_queue={"items": []}, exceptions={"items": []})
    assert transcript["results"][0]["match_source"] == "transcript"


def test_personal_briefing_is_role_scoped_and_quiet_when_nothing_is_actionable():
    actions = {"items": [
        {"key": "guest:1", "owner": "sam", "title": "Owned", "due_at": "2000-01-01T00:00:00Z"},
        {"key": "guest:2", "owner": "other", "title": "Not owned", "due_at": "2000-01-01T00:00:00Z"},
    ]}
    payload = build_personal_briefing(username="sam", action_queue=actions, exceptions={"items": []}, window="daily")
    assert payload["counts"]["assigned"] == 1
    assert payload["counts"]["overdue"] == 1
    assert payload["notification_policy"] == "quiet_unless_actionable"
