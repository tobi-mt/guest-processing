from pathlib import Path

import pytest

from guest_database_manager.database import GuestDatabase
from guest_database_manager.partner_intelligence import PartnerIntelligence, PartnerIntelligenceError
from guest_database_manager.web_interface import GuestWebService
from guest_database_manager.partner_sources import ContactObservation, ProviderResult, SourceEvidence


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
    with pytest.raises(PartnerIntelligenceError, match="named contact"):
        intelligence.draft_pitch(prospect["id"], actor="tester")
    intelligence.add_contact_research(prospect["id"], {"contact_name": "Ava", "source_url": "https://hope.example/team", "source_title": "Team", "fact_text": "Ava leads Hope Press's current resilience and personal growth publishing programme."}, actor="tester")
    drafted = intelligence.draft_pitch(prospect["id"], actor="tester")

    with pytest.raises(PartnerIntelligenceError, match="human-approved"):
        intelligence.record_outcome(prospect["id"], {"outcome": "handed_off"}, actor="tester")

    draft_id = drafted["drafts"][0]["id"]
    intelligence.review_draft(draft_id, "approved", actor="editor", reason="Facts checked")
    result = intelligence.record_outcome(prospect["id"], {"outcome": "handed_off", "pitch_draft_id": draft_id}, actor="editor")
    assert result["status"] == "approved"
    assert "Ava leads Hope Press" in drafted["drafts"][0]["body"]


def test_contact_can_be_added_after_imported_research(intelligence: PartnerIntelligence):
    prospect = intelligence.create_prospect({"organisation_name": "New Partner", "website": "https://new.example", "partner_type": "wellbeing"}, actor="tester")
    updated = intelligence.set_contact(prospect["id"], {"contact_name": "Jordan", "contact_email": "jordan@new.example"}, actor="tester")
    assert updated["contact_name"] == "Jordan"
    assert updated["contact_email"] == "jordan@new.example"


def test_opt_out_creates_suppression_and_audit_event(intelligence: PartnerIntelligence):
    prospect = _prospect(intelligence)
    result = intelligence.record_outcome(prospect["id"], {"outcome": "opted_out", "notes": "Requested no future contact"}, actor="editor")

    assert result["status"] == "suppressed"
    events = intelligence.database.list_audit_events("partner_prospect", prospect["id"])
    assert any(event["event_type"] == "outcome_opted_out" for event in events)

    with pytest.raises(PartnerIntelligenceError, match="suppressed"):
        _prospect(intelligence)


def test_curated_suggestion_imports_source_backed_research(tmp_path: Path):
    service = GuestWebService(tmp_path / "partner-suggestions.db")
    suggestions = service.list_partner_suggestions()["suggestions"]

    assert suggestions
    imported = service.import_partner_suggestion(0, actor="tester")
    assert len(imported["evidence"]) == len(suggestions[0]["evidence"])

    with pytest.raises(PartnerIntelligenceError, match="already been imported"):
        service.import_partner_suggestion(0, actor="tester")


def test_semantic_strategy_creates_three_tailored_editable_drafts(tmp_path: Path):
    class FakeAI:
        def generate_partner_strategy(self, context):
            assert len(context["evidence"]) == 2
            return {
                "score": 91, "confidence": "high", "rationale": "Strong verified launch alignment.",
                "risks": [], "angles": [],
                "emails": [
                    {"angle_title": f"Angle {index}", "subject": f"Subject {index}",
                     "body": f"Hello Ava,\n\nA source-backed tailored partnership email number {index}.\n\nWarmly,\nTobi"}
                    for index in range(1, 4)
                ],
            }

    service = PartnerIntelligence(GuestDatabase(tmp_path / "semantic.db"), ai_factory=lambda: FakeAI())
    prospect = _prospect(service)
    _add_two_sources(service, prospect["id"])
    service.add_contact_research(prospect["id"], {"contact_name": "Ava", "source_url": "https://hope.example/team", "source_title": "Team", "fact_text": "Ava leads the publisher's resilience and purpose programme."}, actor="tester")

    analyzed = service.analyze_fit(prospect["id"], actor="tester", episode_context=[{"title": "Resilience"}])
    drafted = service.draft_pitch(prospect["id"], actor="tester")

    assert analyzed["fit_score"] == 91
    assert analyzed["confidence"] == "high"
    assert len(drafted["drafts"]) == 3
    edited = service.update_draft(drafted["drafts"][0]["id"], {"subject": "Edited", "body": "Hello Ava,\n\nThis is the complete, carefully edited partnership email.\n\nTobi"}, actor="editor")
    assert edited["drafts"][0]["subject"] == "Edited"


def test_approved_partner_handoff_is_idempotently_queued(intelligence: PartnerIntelligence):
    prospect = _prospect(intelligence)
    _add_two_sources(intelligence, prospect["id"])
    intelligence.add_contact_research(prospect["id"], {"contact_name": "Ava", "source_url": "https://hope.example/team", "source_title": "Team", "fact_text": "Ava leads Hope Press's resilience publishing programme."}, actor="tester")
    drafted = intelligence.draft_pitch(prospect["id"], actor="tester")
    draft_id = drafted["drafts"][0]["id"]
    intelligence.review_draft(draft_id, "approved", actor="editor")

    first = intelligence.queue_approved_draft(draft_id, actor="editor")
    second = intelligence.queue_approved_draft(draft_id, actor="editor")

    assert first["drafts"][0]["outbox_id"] == second["drafts"][0]["outbox_id"]
    assert intelligence.database.get_email_outbox_count() == 1


def test_apollo_candidates_are_normalized_with_provenance(tmp_path: Path):
    class FakeApollo:
        def search_decision_makers(self, domain):
            assert domain == "hope.example"
            return [{"provider_record_id": "apollo-1", "contact_name": "Ava Stone",
                     "contact_email": "ava@hope.example", "role_title": "Head of Partnerships",
                     "confidence": "high", "verification_status": "verified",
                     "source_url": "https://linkedin.com/in/ava"}]

    service = PartnerIntelligence(GuestDatabase(tmp_path / "apollo.db"), apollo_factory=lambda: FakeApollo())
    prospect = _prospect(service)
    enriched = service.discover_contacts_with_apollo(prospect["id"], actor="tester")

    candidate = enriched["contact_candidates"][0]
    assert candidate["provider"] == "apollo"
    assert candidate["verification_status"] == "verified"
    selected = service.select_contact_candidate(prospect["id"], candidate["id"], actor="tester")
    assert selected["contact_name"] == "Ava Stone"


def test_apollo_export_import_creates_unselected_review_candidate(tmp_path: Path):
    service = PartnerIntelligence(GuestDatabase(tmp_path / "apollo-export.db"))
    csv_text = "\n".join([
        "First Name,Last Name,Title,Company Name,Email,Email Status,Website,Person Linkedin Url,Primary Email Catch-all Status,Industry,Apollo Contact Id,Primary Email Last Verified At",
        "Ava,Stone,Head of Partnerships,Hope Press,ava@hope.example,verified,https://hope.example,https://linkedin.com/in/ava,not catch-all,Publishing,apollo-1,2026-08-20",
    ])

    preview = service.preview_apollo_csv(csv_text)
    result = service.import_apollo_csv(csv_text, actor="tester")
    prospect = result["prospects"][0]

    assert preview["high_confidence"] == 1
    assert result["created_prospects"] == 1
    assert prospect["contact_name"] == ""
    assert prospect["contact_candidates"][0]["provider"] == "apollo_export"
    assert prospect["evidence"] == []


def test_pitch_studio_selection_retires_alternatives_and_attributes_outcome(intelligence: PartnerIntelligence):
    prospect = _prospect(intelligence)
    _add_two_sources(intelligence, prospect["id"])
    intelligence.add_contact_research(prospect["id"], {"contact_name": "Ava", "source_url": "https://hope.example/team", "source_title": "Team", "fact_text": "Ava leads Hope Press's resilience publishing programme."}, actor="tester")
    drafted = intelligence.draft_pitch(prospect["id"], actor="tester", preferences={"template_id": "co_marketing", "tone": "concise"})
    assert len([item for item in drafted["drafts"] if item["status"] == "draft"]) == 3

    chosen_id = drafted["drafts"][0]["id"]
    selected = intelligence.select_draft(chosen_id, actor="editor")
    chosen = next(item for item in selected["drafts"] if item["id"] == chosen_id)
    assert chosen["selected_at"]
    assert chosen["template_id"] == "co_marketing"
    assert chosen["tone"] == "concise"
    assert len([item for item in selected["drafts"] if item["status"] == "retired"]) == 2

    intelligence.review_draft(chosen_id, "approved", actor="editor")
    intelligence.queue_approved_draft(chosen_id, actor="editor")
    intelligence.record_outcome(prospect["id"], {"outcome": "replied", "pitch_draft_id": chosen_id}, actor="editor")
    performance = intelligence.pitch_performance()
    assert performance[0]["replies"] == 1


def test_multi_source_enrichment_isolated_and_source_grounded(tmp_path: Path):
    class FakeSources:
        def first_party(self, organisation, website):
            return ProviderResult("first_party", [SourceEvidence("first_party", "https://hope.example/about", "About", "Hope Press publishes evidence-led resilience and purpose resources.", confidence="high")], [ContactObservation("first_party", "https://hope.example/contact", contact_email="partners@hope.example", role_title="Partnerships", confidence="high")], ["0000-0002-1825-0097"])
        def media_feeds(self, organisation, website):
            return ProviderResult("media_feeds", [SourceEvidence("media_feeds", "https://hope.example/feed/item", "Launch", "Hope Press published a current programme launch announcement.", "timely_signal", "high")])
        def wikidata(self, organisation): return ProviderResult("wikidata", [SourceEvidence("wikidata", "https://wikidata.org/wiki/Q1", "Hope Press", "Wikidata describes Hope Press as an independent publisher.", "structured_identity")])
        def openalex(self, organisation): return ProviderResult("openalex")
        def crossref(self, organisation): return ProviderResult("crossref")
        def gdelt(self, organisation): return ProviderResult("gdelt")
        def orcid(self, ids, organisation=""): return ProviderResult("orcid", [SourceEvidence("orcid", "https://orcid.org/0000-0002-1825-0097", "ORCID", "ORCID identifies Ava Stone's public researcher profile.", "person_identity", "high")])

    service = PartnerIntelligence(GuestDatabase(tmp_path / "sources.db"), public_source_factory=FakeSources)
    prospect = service.create_prospect({"organisation_name":"Hope Press","website":"https://hope.example","partner_type":"author_publisher"}, actor="tester")
    enriched = service.enrich_from_free_sources(prospect["id"], actor="tester")

    assert {item["provider"] for item in enriched["evidence"]} >= {"first_party", "media_feeds", "wikidata", "orcid"}
    assert any(item["contact_email"] == "partners@hope.example" for item in enriched["contact_candidates"])
    latest = {item["provider"]: item for item in enriched["source_coverage"]}
    assert latest["first_party"]["status"] == "completed"
    assert latest["openalex"]["status"] == "completed"
    assert latest["openalex"]["error_code"] == "no_results"


def test_existing_asset_like_contact_candidates_are_hidden(intelligence: PartnerIntelligence):
    prospect = _prospect(intelligence)
    with intelligence.database._connect() as conn:
        conn.execute("""INSERT INTO partner_contact_candidates
            (prospect_id, contact_email, source_url, provider, confidence, verification_status, evidence_text)
            VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (prospect["id"], "ecom-swiper@11.0.5.js", "https://hope.example", "first_party", "medium", "published", "Asset reference"))
        conn.commit()
    assert intelligence.get_prospect(prospect["id"])["contact_candidates"] == []
