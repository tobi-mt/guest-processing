"""Regression coverage for AI guest-context preparation and structured analysis."""

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


def test_analysis_returns_empty_result_when_the_model_returns_no_content(monkeypatch):
    assistant = AIAssistant(api_key="test")
    monkeypatch.setattr(assistant, "_call_openai", lambda *args, **kwargs: None)

    result = assistant.research_guest_from_text(_guest())

    assert result == {}


def test_analysis_does_not_retry_after_a_network_failure(monkeypatch):
    assistant = AIAssistant(api_key="test")
    calls = []

    def fail(*args, **kwargs):
        calls.append((args, kwargs))
        raise requests.Timeout("timed out")

    monkeypatch.setattr("guest_database_manager.ai_assistant.requests.post", fail)

    assert assistant.research_guest_from_text(_guest()) == {}
    assert len(calls) == 1


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
        return Response()

    monkeypatch.setattr("guest_database_manager.ai_assistant.requests.post", fake_post)

    assert assistant._call_openai([{"role": "user", "content": "Hello"}]) == "OK"
    assert "temperature" not in captured["payload"]
