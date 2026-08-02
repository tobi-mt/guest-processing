from guest_database_manager.guest_recommender import evaluate_guest_recommendations


def test_recommendation_evaluation_reports_bands_disagreement_and_version():
    result = evaluate_guest_recommendations(
        [
            {"email_status": "accepted", "decision_support": {"score": 80, "suggested_decision": "approve"}},
            {"email_status": "rejected", "decision_support": {"score": 75, "suggested_decision": "approve"}},
            {"email_status": "accepted", "decision_support": {"score": 20, "suggested_decision": "decline"}},
        ]
    )

    assert result["model_version"] == "mirror-talk-intake-v1"
    assert result["evaluated_decisions"] == 3
    assert result["disagreement_count"] == 2
    assert result["override_rate"] == 0.667
    assert result["calibration_status"] == "insufficient_sample"
