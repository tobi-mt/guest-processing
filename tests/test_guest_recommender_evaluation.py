from guest_database_manager.guest_recommender import build_strategic_guest_scorecard, evaluate_guest_recommendations


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


def test_strategic_guest_scorecard_uses_six_weighted_dimensions_without_inventing_reach():
    result = build_strategic_guest_scorecard({
        "background": "After addiction and grief, I rebuilt my life and now help families heal through honest conversations.",
        "life_experiences": "My recovery changed my identity, relationships, and understanding of purpose.",
        "profession": "Licensed therapist and author with twenty years of clinical practice.",
        "passionate_topics": "trauma healing, shame, attachment, and forgiveness",
        "message_takeaway": "Listeners can understand that recovery is possible and learn a grounded first step.",
        "core_values": "honesty compassion responsibility faith service and emotional courage",
        "additional_info": "I can discuss failures and difficult turning points without making the conversation promotional.",
        "website": "https://example.com",
        "social_media_handles": "@example",
    })

    assert set(result["dimensions"]) == {"transformation_story", "audience_relevance", "expertise_credibility", "emotional_depth", "distribution_potential", "originality"}
    assert sum(item["weight_pct"] for item in result["dimensions"].values()) == 100
    assert result["dimensions"]["distribution_potential"]["score"] == 60
    assert result["advisory_only"] is True
