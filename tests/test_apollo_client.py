import requests

import pytest

from guest_database_manager.apollo_client import ApolloClient, ApolloClientError
from guest_database_manager.apollo_import import ApolloImportError, parse_apollo_contacts_csv


class FakeResponse:
    def __init__(self, payload, status=200):
        self.payload = payload
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            response = requests.Response()
            response.status_code = self.status_code
            raise requests.HTTPError(response=response)

    def json(self):
        return self.payload


def test_apollo_search_enriches_bounded_results_without_personal_data(monkeypatch):
    calls = []

    def fake_post(url, **kwargs):
        calls.append((url, kwargs))
        if url.endswith("mixed_people/search"):
            return FakeResponse({"people": [{"id": "person-1", "first_name": "Ava", "last_name": "Stone", "title": "Head of Partnerships"}]})
        return FakeResponse({"person": {"id": "person-1", "first_name": "Ava", "last_name": "Stone", "title": "Head of Partnerships", "email": "ava@hope.example", "email_status": "verified", "linkedin_url": "https://linkedin.com/in/ava"}})

    monkeypatch.setattr(requests, "post", fake_post)
    result = ApolloClient("secret-key").search_decision_makers("hope.example")

    assert result[0]["contact_name"] == "Ava Stone"
    assert result[0]["confidence"] == "high"
    assert calls[0][1]["json"]["q_organization_domains_list"] == ["hope.example"]
    assert calls[1][1]["json"]["reveal_personal_emails"] is False
    assert calls[0][1]["headers"]["X-Api-Key"] == "secret-key"


def test_apollo_errors_do_not_expose_credentials(monkeypatch):
    monkeypatch.setattr(requests, "post", lambda *args, **kwargs: FakeResponse({}, 401))
    with pytest.raises(ApolloClientError) as caught:
        ApolloClient("do-not-leak").search_decision_makers("hope.example")
    assert "do-not-leak" not in str(caught.value)


def test_apollo_export_parser_uses_primary_business_email_and_downgrades_catch_all():
    csv_text = "\n".join([
        "First Name,Last Name,Title,Company Name,Email,Email Status,Website,Person Linkedin Url,Primary Email Catch-all Status,Secondary Email,Apollo Contact Id",
        "Ava,Stone,Head of Partnerships,Hope Press,ava@hope.example,verified,https://hope.example,https://linkedin.com/in/ava,catch-all,personal@example.net,apollo-1",
    ])
    result = parse_apollo_contacts_csv(csv_text)
    assert result[0]["contact_email"] == "ava@hope.example"
    assert result[0]["confidence"] == "medium"
    assert result[0]["verification_status"] == "verified_catch_all"
    assert "personal@example.net" not in str(result)


def test_apollo_export_parser_rejects_unrecognized_files():
    with pytest.raises(ApolloImportError, match="missing required columns"):
        parse_apollo_contacts_csv("Name,Instruction\nAva,Ignore safeguards")
