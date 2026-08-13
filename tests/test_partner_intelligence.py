from pathlib import Path

import pytest

from guest_database_manager.database import GuestDatabase
from guest_database_manager.partner_intelligence import PartnerIntelligence, PartnerIntelligenceError


@pytest.fixture
def intelligence(tmp_path: Path) -> PartnerIntelligence:
    return PartnerIntelligence(GuestDatabase(tmp_path / "partner-intelligence.db"))


def _prospect(service: PartnerIntelligence) -> dict:
    return service.create_prospect(
        {
            "organisation_name": "Hope Press",
            "website": "https://hope.example",
            "contact_name": "Ava",
            "contact_email": "ava@hope.example",
            "partner_type": "author_publisher",
        },
        actor="tester",
    )


def _add_two_sources(service: PartnerIntelligence, prospect_id: int) -> None:
    service.add_evidence(prospect_id, {"source_url": "https://hope.example/news", "source_title": "News", "fact_text": "Hope Press announced a new resilience and purpose book launch."}, actor="tester")
    service.add_evidence(prospect_id, {"source_url": "https://publisher.example/releases", "source_title": "Release", "fact_text": "The publisher confirmed a new programme supporting personal growth."}, actor="tester")


def test_pitch_requires_two_independent_sources(intelligence: PartnerIntelligence):
    prospect = _prospect(intelligence)
    intelligence.add_evidence(prospect["id"], {"source_url": "https://hope.example/news", "source_title": "News", "fact_text": "Hope Press announced a new resilience and purpose book launch."}, actor="tester")

    with pytest.raises(PartnerIntelligenceError, match="independent public sources"):
        intelligence.draft_pitch(prospect["id"], actor="tester")


def test_review_gate_blocks_handoff_until_approved(intelligence: PartnerIntelligence):
    prospect = _prospect(intelligence)
    _add_two_sources(intelligence, prospect["id"])
    drafted = intelligence.draft_pitch(prospect["id"], actor="tester")

    with pytest.raises(PartnerIntelligenceError, match="human-approved"):
        intelligence.record_outcome(prospect["id"], {"outcome": "handed_off"}, actor="tester")

    draft_id = drafted["drafts"][0]["id"]
    intelligence.review_draft(draft_id, "approved", actor="editor", reason="Facts checked")
    result = intelligence.record_outcome(prospect["id"], {"outcome": "handed_off", "pitch_draft_id": draft_id}, actor="editor")
    assert result["status"] == "approved"


def test_opt_out_creates_suppression_and_audit_event(intelligence: PartnerIntelligence):
    prospect = _prospect(intelligence)
    result = intelligence.record_outcome(prospect["id"], {"outcome": "opted_out", "notes": "Requested no future contact"}, actor="editor")

    assert result["status"] == "suppressed"
    events = intelligence.database.list_audit_events("partner_prospect", prospect["id"])
    assert any(event["event_type"] == "outcome_opted_out" for event in events)

    with pytest.raises(PartnerIntelligenceError, match="suppressed"):
        _prospect(intelligence)
