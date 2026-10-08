"""Regression coverage for AI guest-context preparation and structured analysis."""

import json
import logging

import requests

from guest_database_manager.ai_assistant import AIAssistant


def _guest():
    return {
        "full_name": "Avery Stone",
        "profession": "Community therapist",
        "background": "Recovered from burnout while building a peer-support practice.",
        "motivation": "Help caregivers name their limits without shame.",
        "life_experiences": "Cared for a parent during a prolonged illness.",
        "core_values": "Compassion and honesty",
        "faith_practice": "Contemplative prayer",
        "beliefs_align": "Mirror Talk's focus on resilient, honest stories resonates.",
        "favorite_quote": "Rest is not a reward.",
        "passionate_topics": "Caregiver wellbeing",
        "message_takeaway": "Boundaries can be an act of love.",
        "podcast_experience": "Guest on two wellbeing podcasts",
        "additional_info": "Launching a caregiver support group in October.",
        "website": "https://example.test",
        "social_media_handles": "@avery",
    }


def _story_analysis():
    return {
        "strongest_stories": [{"evidence": "Caregiving", "tension": "Limits", "internal_change": "Recovery", "universal_meaning": "Care", "sensitivity": "Careful"}] * 3,
        "central_tension": "Care without self-erasure",
        "transformation_arc": "Burnout to boundaries",
        "human_questions": ["What changed?"],
        "listener_applications": ["Name limits"],
        "boundaries": ["Private medical details"],
        "theme": "Sustainable care",
    }


def _conversation_design():
    candidates = []
    for index in range(20):
        candidates.append({
            "question": f"Candidate {index + 1}?",
            "guest_specificity": 2,
            "story_potential": 2,
            "depth": 2,
            "listener_relevance": 2,
            "spoken_quality": 2,
            "penalties": [],
            "final_score": 10,
            "arc_stage": "experience",
            "evidence": "intake",
        })
    return {
        "candidates": candidates,
        "selected_questions": [f"Candidate {index + 1}?" for index in range(10)],
        "rejected_questions": [],
        "arc_rationale": "Human progression",
        "average_selected_score": 10,
    }


def test_ai_context_uses_persisted_application_fields():
    context = AIAssistant._guest_context(_guest())

    assert "Contemplative prayer" in context
    assert "Boundaries can be an act of love." in context
    assert "Help caregivers name their limits" in context
    assert "Launching a caregiver support group" in context


def test_analysis_requests_structured_output_and_accepts_fenced_json(monkeypatch):
    assistant = AIAssistant(api_key="test")
    captured = {}

    def fake_call(messages, temperature=0.7, response_format=None):
        captured["prompt"] = messages[-1]["content"]
        captured["response_format"] = response_format
        return '''```json
{"summary":"A grounded story about caregiving.","themes":["caregiving"],"fit_score":8,"fit_rationale":"Connects resilience to a lived experience.","conversation_angles":["How did caring change your boundaries?"],"concerns":[],"best_timing":"No evidence for a timing hook","evidence_used":["caregiver support group"]}
```'''

    monkeypatch.setattr(assistant, "_call_openai", fake_call)
    result = assistant.research_guest_from_text(_guest())

    assert captured["response_format"] == {"type": "json_object"}
    assert "Boundaries can be an act of love." in captured["prompt"]
    assert result["fit_score"] == 8
    assert result["summary"] == "A grounded story about caregiving."


def test_questions_receive_full_application_context(monkeypatch):
    assistant = AIAssistant(api_key="test")
    captured = {}

    def fake_call(messages, temperature=0.7, response_format=None):
        captured["prompt"] = messages[-1]["content"]
        return "1. How did caring for your parent reshape what compassion means to you?"

    monkeypatch.setattr(assistant, "_call_openai", fake_call)

    assert assistant.generate_interview_questions(_guest(), 1)
    assert "Why they want to appear" in captured["prompt"]
    assert "Faith or spiritual practice" in captured["prompt"]
    assert "Message they want listeners to take away" in captured["prompt"]


def test_manuscript_uses_intake_and_research_and_enforces_structure(monkeypatch):
    guest = _guest()
    guest["guest_research"] = {"summary": "A verified public profile about caregiver advocacy."}
    assistant = AIAssistant(api_key="test")
    captured = {}

    manuscript_payload = {
        "core_theme": "Care without self-erasure",
        "introduction": "Today we explore care and boundaries with Avery Stone. Avery, welcome to Mirror Talk.",
        "main_questions": [f"Specific main question {index}?" for index in range(1, 11)],
        "closing_questions": [f"Specific closing question {index}?" for index in range(1, 4)],
        "listener_takeaways": ["A grounded lesson", "A practical distinction", "A reflective insight"],
        "producer_note": "Handle the family illness with care.",
    }
    responses = iter([manuscript_payload, manuscript_payload])

    def fake_call(messages, temperature=0.7, response_format=None):
        captured.setdefault("prompts", []).append(messages[-1]["content"])
        captured["response_format"] = response_format
        return json.dumps(next(responses))

    monkeypatch.setattr(assistant, "_call_openai", fake_call)
    manuscript = assistant.generate_interview_manuscript(guest)

    assert captured["response_format"] == {"type": "json_object"}
    assert len(captured["prompts"]) == 2
    assert all("Boundaries can be an act of love." in prompt for prompt in captured["prompts"])
    assert "caregiver advocacy" in captured["prompts"][0]
    assert "evaluate at least 20 possible" in captured["prompts"][0]
    assert "critical Senior Editorial Producer" in captured["prompts"][1]
    assert len(manuscript["main_questions"]) == 10
    assert len(manuscript["closing_questions"]) == 3


def test_manuscript_rejects_wrong_question_count(monkeypatch):
    assistant = AIAssistant(api_key="test")
    responses = iter(
        [
            {
                "core_theme": "Theme",
                "introduction": "Introduction",
                "main_questions": ["Only one?"],
                "closing_questions": ["One?", "Two?", "Three?"],
                "listener_takeaways": ["One", "Two", "Three"],
                "producer_note": "",
            },
        ]
    )
    monkeypatch.setattr(
        assistant,
        "_call_openai",
        lambda *args, **kwargs: json.dumps(next(responses)),
    )

    assert assistant.generate_interview_manuscript(_guest()) is None
    assert assistant.last_error == "OpenAI returned an invalid main questions section"


def test_manuscript_fails_closed_when_refined_manuscript_is_invalid(monkeypatch):
    assistant = AIAssistant(api_key="test")
    valid_manuscript = {
        "core_theme": "Theme",
        "introduction": "Introduction",
        "main_questions": [f"Question {index}?" for index in range(10)],
        "closing_questions": ["One?", "Two?", "Three?"],
        "listener_takeaways": ["One", "Two", "Three"],
        "producer_note": "",
    }
    responses = iter([valid_manuscript, {"problems": []}])
    monkeypatch.setattr(assistant, "_call_openai", lambda *args, **kwargs: json.dumps(next(responses)))

    assert assistant.generate_interview_manuscript(_guest()) is None
    assert assistant.last_error == "OpenAI returned an incomplete manuscript"


def test_manuscript_rejects_candidate_sets_below_quality_threshold(monkeypatch):
    assistant = AIAssistant(api_key="test")
    weak_design = _conversation_design()
    weak_design["average_selected_score"] = 7.9
    assert assistant._validate_conversation_design(weak_design) is False
    assert assistant.last_error == "OpenAI returned a question set below the editorial quality threshold"


def test_manuscript_application_only_mode_excludes_saved_research(monkeypatch):
    guest = _guest()
    guest["guest_research"] = {"summary": "SAVED RESEARCH MUST NOT APPEAR"}
    assistant = AIAssistant(api_key="test")
    captured = {}

    def fake_call(messages, **kwargs):
        captured["prompt"] = messages[-1]["content"]
        return json.dumps({"fit_score": 8})

    monkeypatch.setattr(assistant, "_call_openai", fake_call)
    assistant.generate_interview_manuscript(guest, settings={"research_mode": "application_only"})

    assert "SAVED RESEARCH MUST NOT APPEAR" not in captured["prompt"]
    assert '"research_mode": "application_only"' in captured["prompt"]


def test_analysis_returns_empty_result_when_the_model_returns_no_content(monkeypatch):
    assistant = AIAssistant(api_key="test")
    monkeypatch.setattr(assistant, "_call_openai", lambda *args, **kwargs: None)

    result = assistant.research_guest_from_text(_guest())

    assert result == {}


def test_analysis_does_not_retry_after_a_network_failure(monkeypatch):
    assistant = AIAssistant(api_key="test", request_timeout_seconds=45)
    calls = []

    def fail(*args, **kwargs):
        calls.append((args, kwargs))
        raise requests.Timeout("timed out")

    monkeypatch.setattr("guest_database_manager.ai_assistant.requests.post", fail)

    assert assistant.research_guest_from_text(_guest()) == {}
    assert len(calls) == 1
    assert assistant.last_error == "OpenAI response timed out after 45 seconds"


def test_openai_http_error_logs_safe_provider_metadata(monkeypatch, caplog):
    assistant = AIAssistant(api_key="test")
    response = requests.Response()
    response.status_code = 400
    response._content = b'{"error":{"message":"Unsupported parameter","type":"invalid_request_error","code":"unsupported_parameter"}}'
    error = requests.HTTPError(response=response)

    monkeypatch.setattr("guest_database_manager.ai_assistant.requests.post", lambda *args, **kwargs: (_ for _ in ()).throw(error))

    with caplog.at_level(logging.ERROR):
        assert assistant._call_openai([]) is None

    assert "status=400" in caplog.text
    assert "code=unsupported_parameter" in caplog.text
    assert assistant.last_error == "OpenAI rejected the request (invalid_request_error: unsupported_parameter)"


def test_reasoning_models_omit_temperature_for_chat_completions(monkeypatch):
    assistant = AIAssistant(api_key="test", model="gpt-5")
    captured = {}

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [{"message": {"content": "OK"}}]}

    def fake_post(*args, **kwargs):
        captured["payload"] = kwargs["json"]
        captured["timeout"] = kwargs["timeout"]
        return Response()

    monkeypatch.setattr("guest_database_manager.ai_assistant.requests.post", fake_post)

    assert assistant._call_openai([{"role": "user", "content": "Hello"}]) == "OK"
    assert "temperature" not in captured["payload"]
    assert captured["timeout"] == (10, 120.0)
