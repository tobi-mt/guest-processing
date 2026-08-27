import sqlite3

import pytest

from guest_database_manager.recommendation_learning import LearningError, RecommendationLearning, apply_active_policy
from guest_database_manager.web_interface import GuestWebRequestHandler, GuestWebService


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
        source="manual", occurred_at="2026-01-01T12:00:00Z", idempotency_key="outcome-1",
    )
    repeated = learning.record_outcome(
        episode_id, outcome_type="released", value=None, metadata={}, actor="editor",
        source="manual", occurred_at="2026-01-01T12:00:00Z", idempotency_key="outcome-1",
    )

    assert first["recorded"] == 1
    assert duplicate["recorded"] == 0
    assert outcome["id"] == repeated["id"]
    assert learning.status()["counts"]["outcomes"] == 1
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
            source="test", occurred_at=f"2026-01-{index + 1:02d}T12:00:00Z", idempotency_key=f"outcome-{index}",
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
    for path in ("settings", "promote", "rollback", "cycle"):
        assert GuestWebRequestHandler._required_role_for_request("POST", f"/api/recommendation-learning/{path}") == "admin"
