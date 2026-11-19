import json

import pytest

from guest_database_manager.ask_mirror_talk_client import (
    MAX_EXPORT_BYTES,
    AskMirrorTalkClient,
    AskMirrorTalkClientError,
)


class FakeResponse:
    def __init__(self, payload, *, status_code=200, headers=None):
        self.body = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
        self.status_code = status_code
        self.headers = headers or {}
        self.closed = False

    @property
    def ok(self):
        return 200 <= self.status_code < 300

    def iter_content(self, chunk_size):
        for offset in range(0, len(self.body), chunk_size):
            yield self.body[offset:offset + chunk_size]

    def close(self):
        self.closed = True


def test_export_fetches_transcripts_with_bounded_stream(monkeypatch):
    response = FakeResponse({"episodes": [{"id": 1, "transcript_text": "Verified text"}]})

    def fake_get(url, **kwargs):
        assert kwargs["stream"] is True
        assert kwargs["params"]["limit"] == 1000
        assert kwargs["params"]["include_transcript"] == "true"
        return response

    monkeypatch.setattr("guest_database_manager.ask_mirror_talk_client.requests.get", fake_get)

    episodes = AskMirrorTalkClient("https://ask.example", "user", "secret").export_episodes()

    assert episodes == [{"id": 1, "transcript_text": "Verified text"}]
    assert response.closed is True


def test_export_rejects_oversized_response_before_reading(monkeypatch):
    response = FakeResponse(
        b"{}", headers={"Content-Length": str(MAX_EXPORT_BYTES + 1)}
    )
    monkeypatch.setattr(
        "guest_database_manager.ask_mirror_talk_client.requests.get",
        lambda *args, **kwargs: response,
    )

    with pytest.raises(AskMirrorTalkClientError, match="oversized"):
        AskMirrorTalkClient("https://ask.example", "user", "secret").export_episodes()

    assert response.closed is True


def test_export_rejects_non_object_episode_entries(monkeypatch):
    response = FakeResponse({"episodes": ["not-an-episode"]})
    monkeypatch.setattr(
        "guest_database_manager.ask_mirror_talk_client.requests.get",
        lambda *args, **kwargs: response,
    )

    with pytest.raises(AskMirrorTalkClientError, match="invalid episode payload"):
        AskMirrorTalkClient("https://ask.example", "user", "secret").export_episodes()


@pytest.mark.parametrize("payload", [[], ["not-an-export"]])
def test_export_rejects_non_object_root_payload(monkeypatch, payload):
    response = FakeResponse(payload)
    monkeypatch.setattr(
        "guest_database_manager.ask_mirror_talk_client.requests.get",
        lambda *args, **kwargs: response,
    )

    with pytest.raises(AskMirrorTalkClientError, match="invalid episode payload"):
        AskMirrorTalkClient("https://ask.example", "user", "secret").export_episodes()
