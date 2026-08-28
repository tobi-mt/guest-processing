import socket

import pytest

from guest_database_manager.partner_sources import PartnerSourceError, PublicSourceClient, _safe_public_url


class FakeResponse:
    def __init__(self, *, payload=None, text="", content_type="application/json"):
        self._payload = payload or {}
        self.text = text
        self.content = text.encode()
        self.headers = {"Content-Type": content_type}

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class FakeSession:
    def get(self, url, **kwargs):
        if "orcid.org" in url:
            return FakeResponse(payload={"expanded-result": [{"orcid-id":"0000-0002-1825-0097","given-names":"Ava","family-names":"Stone"}]})
        if "wikidata" in url:
            return FakeResponse(payload={"search": [{"label": "Hope Press", "description": "independent publisher", "concepturi": "https://www.wikidata.org/wiki/Q1"}]})
        if "openalex" in url:
            return FakeResponse(payload={"results": [{"display_name": "Hope Institute", "id": "https://openalex.org/I1", "type": "education", "works_count": 42}]})
        if "crossref" in url:
            return FakeResponse(payload={"message": {"items": [{"title": ["Resilience"], "URL": "https://doi.org/10.1/test", "publisher": "Hope Press"}]}})
        if "gdelt" in url:
            return FakeResponse(payload={"articles": [{"title": "Hope launches programme", "url": "https://news.example/hope", "seendate": "20260827"}]})
        return FakeResponse(text="""<html><head><title>Hope Press</title><script type="application/ld+json">{"@type":"Person","name":"Ava Stone","jobTitle":"Head of Partnerships","sameAs":"https://orcid.org/0000-0002-1825-0097"}</script></head><body>Hope Press creates evidence-led books about resilience, purpose, relationships, and personal growth. Contact partnerships@hope.example for collaborations.</body></html>""", content_type="text/html")


def test_first_party_extracts_published_contact_jsonld_and_orcid(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *args, **kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))])
    result = PublicSourceClient(session=FakeSession()).first_party("Hope Press", "https://hope.example")
    assert any(item.contact_email == "partnerships@hope.example" for item in result.contacts)
    assert any(item.contact_name == "Ava Stone" for item in result.contacts)
    assert result.discovered_orcid_ids == ["0000-0002-1825-0097"]
    assert result.evidence[0].confidence == "high"


def test_structured_public_providers_normalize_evidence():
    client = PublicSourceClient(session=FakeSession())
    assert client.wikidata("Hope Press").evidence[0].evidence_type == "structured_identity"
    assert client.openalex("Hope Press").evidence[0].evidence_type == "research_authority"
    assert client.crossref("Hope Press").evidence[0].evidence_type == "publication_signal"
    assert client.gdelt("Hope Press").evidence[0].confidence == "low"
    assert client.orcid([], "Hope Press").evidence[0].evidence_type == "person_identity"


def test_first_party_url_guard_blocks_private_network(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *args, **kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 80))])
    with pytest.raises(PartnerSourceError, match="Private or local"):
        _safe_public_url("http://example.test/contact", allowed_host="example.test")
