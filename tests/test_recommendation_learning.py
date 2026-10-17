import sqlite3

import pytest

from guest_database_manager.recommendation_learning import LearningError, RecommendationLearning, apply_active_policy
from guest_database_manager.web_interface import GuestWebRequestHandler, GuestWebService
from guest_database_manager.rss_release_reconciliation import RSSReconciliationError, RSSReleaseReconciler


def _recommendation(episode_id, score, *, readiness=60, watchouts=0):
    return {
        "id": episode_id,
        "guest_name": f"Guest {episode_id}",
        "episode_title": f"Episode {episode_id}",
        "priority_score": score,
        "base_priority_score": score,
        "website": "https://example.com",
        "promotion_readiness": {"score": readiness},
        "watchouts": ["risk"] * watchouts,
    }


def test_learning_starts_safe_and_reads_do_not_write(temp_db):
    learning = RecommendationLearning(temp_db.db_path)
    before = learning.status()

    ranked = apply_active_policy(temp_db.db_path, [_recommendation(1, 50)])
    after = learning.status()

    assert ranked[0]["learning"]["mode"] == "rules_baseline"
    assert before["counts"] == after["counts"] == {"observations": 0, "outcomes": 0, "evaluations": 0}
    assert before["settings"]["kill_switch"] == 1
    assert before["settings"]["automation_enabled"] == 0


def test_observation_and_outcome_are_idempotent_and_audited(temp_db):
    episode_id, _ = temp_db.upsert_episode({"guest_name": "Learning Guest", "episode_title": "Learn"})
    learning = RecommendationLearning(temp_db.db_path)
    recommendation = _recommendation(episode_id, 72)

    first = learning.observe([recommendation], actor="editor", correlation_id="view-1")
    duplicate = learning.observe([recommendation], actor="editor", correlation_id="view-1")
    outcome = learning.record_outcome(
        episode_id, outcome_type="released", value=None, metadata={"downloads": 500}, actor="editor",
        source="manual", occurred_at="2099-01-01T12:00:00Z", idempotency_key="outcome-1",
    )
    repeated = learning.record_outcome(
        episode_id, outcome_type="released", value=None, metadata={}, actor="editor",
        source="manual", occurred_at="2099-01-01T12:00:00Z", idempotency_key="outcome-1",
    )

    assert first["recorded"] == 1
    assert duplicate["recorded"] == 0
    assert outcome["id"] == repeated["id"]
    status = learning.status()
    assert status["counts"]["outcomes"] == 1
    assert status["outcomes"] == {
        "by_type": {"released": 1},
        "linked": 1,
        "unlinked": 0,
        "latest_at": "2099-01-01T12:00:00Z",
    }
    assert any(event["event_type"] == "recommendation_outcome_recorded" for event in temp_db.list_audit_events("recommendation_policy", "system"))


def test_evaluation_requires_minimum_linked_samples(temp_db):
    learning = RecommendationLearning(temp_db.db_path)

    result = learning.evaluate(actor="analyst")

    assert result["status"] == "insufficient_data"
    assert result["sample_count"] == 0


def test_evaluate_promote_apply_and_rollback_policy(temp_db):
    learning = RecommendationLearning(temp_db.db_path)
    learning.update_settings(
        {"automation_enabled": False, "kill_switch": True, "min_samples": 20, "min_uplift": 0, "max_weight_change": 0.25},
        actor="admin",
    )
    for index in range(24):
        episode_id, _ = temp_db.upsert_episode({"guest_name": f"Guest {index}", "episode_title": f"Episode {index}"})
        recommendation = _recommendation(episode_id, 25 + index * 2, readiness=20 + index * 3, watchouts=0 if index > 11 else 3)
        learning.observe([recommendation], actor="operator", correlation_id=f"view-{index}")
        learning.record_outcome(
            episode_id, outcome_type="performance", value=1.0 if index > 11 else 0.0, metadata={}, actor="operator",
            source="test", occurred_at=f"2099-01-{index + 1:02d}T12:00:00Z", idempotency_key=f"outcome-{index}",
        )

    evaluation = learning.evaluate(actor="analyst")
    status = learning.status()
    candidate = next(policy for policy in status["policies"] if policy["version"] == evaluation["candidate_version"])
    assert evaluation["status"] == "passed"

    active = learning.promote(
        candidate["version"], actor="admin", reason="Validated holdout improvement", expected_row_version=candidate["row_version"]
    )
    adjusted = apply_active_policy(temp_db.db_path, [_recommendation(999, 50)])
    assert active["version"] == candidate["version"]
    assert adjusted[0]["learning"]["mode"] == "adaptive"
    assert abs(adjusted[0]["learning"]["adjustment"]) <= 10

    restored = learning.rollback(actor="admin", reason="Rollback drill")
    assert restored["version"] == "release-planner-v1"


def test_promotion_requires_passed_evaluation_and_concurrency(temp_db):
    learning = RecommendationLearning(temp_db.db_path)
    with sqlite3.connect(temp_db.db_path) as conn:
        conn.execute(
            "INSERT INTO recommendation_policies (version, parent_version, status, weights_json, created_by) VALUES ('draft-v1', 'release-planner-v1', 'draft', '{}', 'test')"
        )

    with pytest.raises(LearningError, match="pass offline evaluation"):
        learning.promote("draft-v1", actor="admin", reason="No eval", expected_row_version=1)


def test_automatic_promotion_is_blocked_by_default(temp_db):
    learning = RecommendationLearning(temp_db.db_path)
    with pytest.raises(LearningError, match="disabled"):
        learning.promote("missing", actor="system", reason="automatic", expected_row_version=1, automatic=True)


def test_automation_stays_on_baseline_until_evidence_gate(temp_db):
    learning = RecommendationLearning(temp_db.db_path)
    learning.update_settings(
        {"automation_enabled": True, "kill_switch": False, "min_samples": 30,
         "min_uplift": 0.03, "max_weight_change": 0.25}, actor="admin",
    )

    result = learning.run_cycle(actor="automation")

    assert result["status"] == "not_promoted"
    assert result["reason"] == "insufficient_data"
    assert learning.status()["active_policy"]["version"] == "release-planner-v1"


@pytest.mark.parametrize("invalid", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_values_cannot_poison_learning(temp_db, invalid):
    episode_id, _ = temp_db.upsert_episode({"guest_name": "Finite Guest", "episode_title": "Finite"})
    learning = RecommendationLearning(temp_db.db_path)

    with pytest.raises(LearningError, match="finite number"):
        learning.observe([_recommendation(episode_id, invalid)], actor="operator")
    with pytest.raises(LearningError, match="finite number"):
        learning.record_outcome(
            episode_id, outcome_type="performance", value=invalid, metadata={}, actor="operator",
            source="test", occurred_at="2026-01-01T12:00:00Z", idempotency_key=f"invalid-{invalid}",
        )
    with pytest.raises(LearningError, match="finite number"):
        learning.update_settings({"min_uplift": invalid}, actor="admin")

    assert learning.status()["counts"] == {"observations": 0, "outcomes": 0, "evaluations": 0}


def test_outcome_timestamp_requires_valid_timezone(temp_db):
    episode_id, _ = temp_db.upsert_episode({"guest_name": "Time Guest", "episode_title": "Time"})
    learning = RecommendationLearning(temp_db.db_path)

    for timestamp in ("not-a-date", "2026-01-01T12:00:00"):
        with pytest.raises(LearningError, match="timestamp"):
            learning.record_outcome(
                episode_id, outcome_type="released", value=None, metadata={}, actor="operator",
                source="test", occurred_at=timestamp, idempotency_key=f"invalid-{timestamp}",
            )

    assert learning.status()["counts"]["outcomes"] == 0


def test_historical_outcome_does_not_link_to_later_observation(temp_db):
    episode_id, _ = temp_db.upsert_episode({"guest_name": "History", "episode_title": "History"})
    learning = RecommendationLearning(temp_db.db_path)
    learning.observe([_recommendation(episode_id, 60)], actor="operator", correlation_id="today")

    outcome = learning.record_outcome(
        episode_id, outcome_type="released", value=None, metadata={}, actor="rss",
        source="podcast_rss", occurred_at="2020-01-01T12:00:00Z", idempotency_key="historical-release",
    )

    assert outcome["observation_id"] is None


def test_rss_reconciliation_marks_exact_unique_episode_released(temp_db):
    released_id, _ = temp_db.upsert_episode({
        "guest_name": "Released Guest", "episode_title": "A Verified Release",
        "published_title": "A Verified Release", "release_status": "released", "release_date": "2026-09-20",
    })
    pending_id, _ = temp_db.upsert_episode({
        "guest_name": "Pending Guest", "episode_title": "Published But Pending",
        "working_title": "Editorial working title", "notes": "Private editorial note",
        "release_status": "scheduled", "release_date": "2026-09-21",
    })
    learning = RecommendationLearning(temp_db.db_path)
    learning.observe([_recommendation(released_id, 70)], actor="operator", correlation_id="before-release")
    with sqlite3.connect(temp_db.db_path) as conn:
        conn.execute(
            "UPDATE recommendation_observations SET created_at = '2026-09-19 12:00:00' WHERE episode_id = ?",
            (released_id,),
        )
    feed = """<?xml version="1.0"?><rss xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd"><channel>
      <itunes:image href="https://example.com/show.jpg"/>
      <item><guid>released-1</guid><title>A Verified Release</title><pubDate>Sun, 20 Sep 2026 12:00:00 GMT</pubDate></item>
      <item><guid>pending-1</guid><title>Published But Pending</title><pubDate>Mon, 21 Sep 2026 12:00:00 GMT</pubDate>
        <description>Public show notes</description><link>https://example.com/pending</link>
        <enclosure url="https://cdn.example.com/pending.mp3" type="audio/mpeg"/>
        <itunes:duration>01:02:03</itunes:duration><itunes:image href="https://example.com/pending.jpg"/>
        <itunes:season>4</itunes:season><itunes:episode>27</itunes:episode>
      </item>
      <item><guid>unknown-1</guid><title>No System Match</title><pubDate>Tue, 22 Sep 2026 12:00:00 GMT</pubDate></item>
    </channel></rss>"""

    reconciler = RSSReleaseReconciler(temp_db.db_path, feed_url="https://example.com/feed.xml")
    result = reconciler.reconcile(actor="operator", payload=feed, apply_lifecycle=True)
    repeated = reconciler.reconcile(actor="operator", payload=feed, apply_lifecycle=True)
    status = reconciler.status()

    assert result["counts"] == {"auto_linked": 2, "unmatched": 1}
    assert result["lifecycle_changed"] is True
    assert result["lifecycle_updates"] == 1
    assert result["outcomes_verified"] == result["new_outcomes"] == 2
    assert result["linked_outcomes"] == 1
    assert repeated["outcomes_verified"] == 2
    assert repeated["linked_outcomes"] == 1
    assert repeated["new_outcomes"] == 0
    assert status["items"] == 3
    assert status["counts"] == result["counts"]
    assert status["latest_run"]["status"] == "completed"
    assert status["failures_24h"] == 0
    assert status["publishing_cadence"]["episodes_analyzed"] == 3
    assert status["publishing_cadence"]["median_days_between_releases"] == 1.0
    with sqlite3.connect(temp_db.db_path) as conn:
        conn.row_factory = sqlite3.Row
        assert conn.execute("SELECT COUNT(*) FROM recommendation_outcomes").fetchone()[0] == 2
        pending = dict(conn.execute("SELECT * FROM episodes WHERE id = ?", (pending_id,)).fetchone())
        assert pending["release_status"] == "released"
        assert pending["production_status"] == "released"
        assert pending["promotion_status"] == "released"
        assert pending["published_title"] == "Published But Pending"
        assert pending["working_title"] == "Editorial working title"
        assert pending["notes"] == "Private editorial note"
        assert pending["published_description"] == "Public show notes"
        assert pending["public_episode_url"] == "https://example.com/pending"
        assert pending["audio_enclosure_url"] == "https://cdn.example.com/pending.mp3"
        assert pending["rss_duration_seconds"] == 3723
        assert pending["rss_artwork_url"] == "https://example.com/pending.jpg"
        assert pending["rss_season_number"] == 4
        assert pending["rss_episode_number"] == 27
        assert pending["rss_feed_position"] == 2
        assert pending["rss_metadata_synced_at"]
        assert str(pending["release_date"]).startswith("2026-09-21")
        audit = conn.execute(
            """SELECT actor, source, reason, correlation_id FROM audit_events
               WHERE entity_type = 'episode' AND entity_id = ? AND event_type = 'status_changed'
               ORDER BY id DESC LIMIT 1""",
            (pending_id,),
        ).fetchone()
        assert tuple(audit)[:3] == (
            "operator",
            "podcast_rss",
            "Canonical RSS feed confirmed publication.",
        )
        assert audit["correlation_id"].startswith("rss:")


def test_rss_reconciliation_records_safe_failure_metrics(temp_db):
    reconciler = RSSReleaseReconciler(temp_db.db_path, feed_url="https://example.com/feed.xml")

    with pytest.raises(RSSReconciliationError, match="unsupported XML"):
        reconciler.reconcile(actor="automation", payload="<!DOCTYPE rss><rss><channel/></rss>")

    status = reconciler.status()
    assert status["latest_run"]["status"] == "failed"
    assert status["latest_run"]["error_code"] == "RSSReconciliationError"
    assert status["failures_24h"] == 1


def test_rss_background_reconciliation_keeps_release_transition_human_approved(temp_db):
    episode_id, _ = temp_db.upsert_episode({
        "guest_name": "Approval Guest", "episode_title": "Approval Required Release",
        "release_status": "scheduled", "release_date": "2026-09-21",
    })
    feed = """<?xml version="1.0"?><rss><channel><item>
      <guid>approval-required</guid><title>Approval Required Release</title>
      <pubDate>Mon, 21 Sep 2026 12:00:00 GMT</pubDate>
    </item></channel></rss>"""

    result = RSSReleaseReconciler(temp_db.db_path, feed_url="https://example.com/feed.xml").reconcile(
        actor="rss-release-automation", payload=feed
    )

    assert result["lifecycle_changed"] is False
    assert result["counts"] == {"review_required": 1}
    unchanged = temp_db.get_episode_by_id(episode_id)
    assert unchanged["release_status"] == "scheduled"
    assert unchanged["published_description"] is None


def test_invalid_persisted_policy_weights_fail_safe(temp_db):
    with sqlite3.connect(temp_db.db_path) as conn:
        conn.execute(
            "UPDATE recommendation_policies SET weights_json = ? WHERE status = 'active'",
            ('{"bias": NaN}',),
        )

    ranked = apply_active_policy(temp_db.db_path, [_recommendation(1, 50)])

    assert ranked[0]["priority_score"] == 50
    assert ranked[0]["learning"]["mode"] == "invalid_policy_fallback"


def test_shadow_cycle_is_idempotent_links_release_and_never_promotes(temp_db):
    episode_id, _ = temp_db.upsert_episode({"guest_name": "Shadow Guest", "episode_title": "Shadow"})
    learning = RecommendationLearning(temp_db.db_path)
    recommendation = _recommendation(episode_id, 75)

    first = learning.run_shadow_cycle([recommendation], actor="automation", cycle_key="shadow:day-1")
    replay = learning.run_shadow_cycle([recommendation], actor="automation", cycle_key="shadow:day-1")
    with sqlite3.connect(temp_db.db_path) as conn:
        conn.execute(
            "UPDATE episodes SET release_status = 'released', release_date = '2099-09-25' WHERE id = ?",
            (episode_id,),
        )
    second = learning.run_shadow_cycle([], actor="automation", cycle_key="shadow:day-2")
    status = learning.status()

    assert first["observations_recorded"] == 1
    assert replay["idempotent_replay"] is True
    assert second["outcomes_linked"] == 1
    assert status["active_policy"]["version"] == "release-planner-v1"
    assert status["settings"]["automation_enabled"] == 0
    assert status["settings"]["kill_switch"] == 1
    assert status["evidence_progress"] == {"linked": 1, "minimum": 30, "credible_target": 100}
    assert status["kpis"]["latest_cycle_latency_ms"] >= 0
    assert status["kpis"]["fallback_rate"] == 0.0


def test_release_completion_rate_only_compares_accepted_episode_cohort(temp_db):
    learning = RecommendationLearning(temp_db.db_path)
    accepted_released, _ = temp_db.upsert_episode({"guest_name": "Released", "episode_title": "Released"})
    accepted_pending, _ = temp_db.upsert_episode({"guest_name": "Pending", "episode_title": "Pending"})
    unrelated_released, _ = temp_db.upsert_episode({"guest_name": "Archive", "episode_title": "Archive"})

    for episode_id, outcome_type, key in (
        (accepted_released, "accepted", "accepted-released"),
        (accepted_released, "released", "released-after-acceptance"),
        (accepted_pending, "accepted", "accepted-pending"),
        (unrelated_released, "released", "historical-release"),
    ):
        learning.record_outcome(
            episode_id, outcome_type=outcome_type, value=None, metadata={}, actor="operator",
            source="test", occurred_at="2026-10-17T12:00:00Z", idempotency_key=key,
        )

    assert learning.status()["kpis"]["release_completion_rate"] == 0.5


def test_feedback_learning_writes_are_atomic_and_restore_is_not_acceptance(temp_db):
    episode_id, _ = temp_db.upsert_episode({"guest_name": "Atomic Guest", "episode_title": "Atomic"})
    service = GuestWebService(temp_db.db_path)
    payload = {
        "action": "rejected", "reason": "Not this cycle", "idempotency_key": "feedback-atomic",
        "recommendation": {"priority_score": 72, "promotion_readiness": {"score": 80}},
    }
    with sqlite3.connect(temp_db.db_path) as conn:
        conn.execute("DROP TABLE recommendation_outcomes")

    with pytest.raises(sqlite3.OperationalError):
        service.update_scheduling_recommendation_feedback(episode_id, payload, actor="editor")
    with sqlite3.connect(temp_db.db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM recommendation_feedback").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM recommendation_observations").fetchone()[0] == 0


def test_restoring_recommendation_does_not_create_positive_training_label(temp_db):
    episode_id, _ = temp_db.upsert_episode({"guest_name": "Restore Guest", "episode_title": "Restore"})
    service = GuestWebService(temp_db.db_path)
    service.update_scheduling_recommendation_feedback(
        episode_id,
        {"action": "rejected", "reason": "Timing", "idempotency_key": "reject-1", "recommendation": {"priority_score": 60}},
        actor="editor",
    )
    service.update_scheduling_recommendation_feedback(
        episode_id, {"action": "restored", "idempotency_key": "restore-1"}, actor="editor"
    )
    with sqlite3.connect(temp_db.db_path) as conn:
        outcomes = conn.execute("SELECT outcome_type, value FROM recommendation_outcomes ORDER BY id").fetchall()
    assert outcomes == [("rejected", 0.0)]


def test_learning_control_routes_require_admin_except_evaluation_and_outcomes():
    assert GuestWebRequestHandler._required_role_for_request("POST", "/api/recommendation-learning/evaluate") == "operator"
    assert GuestWebRequestHandler._required_role_for_request("POST", "/api/recommendation-learning/outcomes") == "operator"
    assert GuestWebRequestHandler._required_role_for_request("POST", "/api/recommendation-learning/shadow-cycle") == "operator"
    assert GuestWebRequestHandler._required_role_for_request("POST", "/api/recommendation-learning/rss-reconcile") == "operator"
    for path in ("settings", "promote", "rollback", "cycle"):
        assert GuestWebRequestHandler._required_role_for_request("POST", f"/api/recommendation-learning/{path}") == "admin"
