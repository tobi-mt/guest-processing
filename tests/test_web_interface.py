# SPDX-FileCopyrightText: 2024-present Guest Database Manager <admin@example.com>
#
# SPDX-License-Identifier: MIT
"""Tests for the direct web interface service layer."""

import json
from datetime import datetime, timedelta, timezone
from io import BytesIO
from zoneinfo import ZoneInfo

import pandas as pd
import pytest
from openpyxl import load_workbook

from guest_database_manager.web_interface import (
    AGENCY_REFERRAL_SOURCE_NAME,
    ASK_MIRROR_TALK_BASE_URL_ENV_VAR,
    ASK_MIRROR_TALK_PASSWORD_ENV_VAR,
    ASK_MIRROR_TALK_USERNAME_ENV_VAR,
    API_TOKEN_ENV_VAR,
    BOOKING_BASE_URL_ENV_VAR,
    BOOKING_MONTHS_AHEAD_ENV_VAR,
    EMAIL_FROM_ENV_VAR,
    EMAIL_FROM_NAME_ENV_VAR,
    EMAIL_PASSWORD_ENV_VAR,
    EMAIL_CC_ENV_VAR,
    EMAIL_RESEND_API_KEY_ENV_VAR,
    GOOGLE_CALENDAR_ID_ENV_VAR,
    GOOGLE_CALENDAR_DAYS_AHEAD_ENV_VAR,
    GOOGLE_CLIENT_ID_ENV_VAR,
    GOOGLE_CLIENT_SECRET_ENV_VAR,
    GOOGLE_REFRESH_TOKEN_ENV_VAR,
    EMAIL_SMTP_PORT_ENV_VAR,
    EMAIL_SMTP_SERVER_ENV_VAR,
    EMAIL_USERNAME_ENV_VAR,
    FORM_SOURCE_NAME,
    INTAKE_SOURCE_NAME,
    PUBLIC_INTAKE_URL_ENV_VAR,
    GuestWebRequestHandler,
    GuestWebService,
    WebInterfaceError,
    build_guest_payload,
    validate_intake_payload,
)
from guest_database_manager.guest_research import _candidate_urls
from guest_database_manager import guest_research
from guest_database_manager.email_manager import EmailManager
from guest_database_manager.google_calendar_sync import GoogleCalendarSyncClient
from guest_database_manager.openai_scheduling_copilot import OpenAISchedulingCopilot


def test_build_guest_payload_requires_name():
    """Direct entry should reject nameless guests."""
    with pytest.raises(WebInterfaceError):
        build_guest_payload({"email": "guest@example.com"})


def test_build_guest_payload_sets_source_metadata():
    """Direct entry records should be marked as coming from the web interface."""
    payload = build_guest_payload({"full_name": "Jane Doe", "email": "jane@example.com"})

    assert payload["original_file_name"] == FORM_SOURCE_NAME
    assert json.loads(payload["original_data"])["full_name"] == "Jane Doe"


def test_build_guest_payload_accepts_custom_source_name():
    """Public intake submissions should keep their own source label."""
    payload = build_guest_payload(
        {"full_name": "Jane Doe", "email": "jane@example.com"},
        source_name=INTAKE_SOURCE_NAME,
    )

    assert payload["original_file_name"] == INTAKE_SOURCE_NAME


def test_build_guest_payload_normalizes_website_without_scheme():
    """Website values starting with www should be normalized into valid URLs."""
    payload = build_guest_payload(
        {"full_name": "Jane Doe", "email": "jane@example.com", "website": "www.example.com"},
        source_name=INTAKE_SOURCE_NAME,
    )

    assert payload["website"] == "https://www.example.com"


def test_guest_research_candidate_urls_split_multiline_website_field():
    """Bulk guest research should tolerate multiple website URLs in one stored field."""
    urls = _candidate_urls(
        {
            "website": "Www.peakhealthandfitness.co.uk\nWww.thelifeorganic.com",
            "social_media_handles": "",
        }
    )

    assert "https://Www.peakhealthandfitness.co.uk" in urls
    assert "https://Www.thelifeorganic.com" in urls


def test_guest_research_candidate_urls_extract_urls_from_messy_website_text():
    """Website parsing should recover usable URLs from messy pasted text."""
    urls = _candidate_urls(
        {
            "website": "Website [https://vft23.com/] and www.example.org",
            "social_media_handles": "",
        }
    )

    assert "https://vft23.com/" in urls
    assert "https://www.example.org" in urls


def test_guest_research_rejects_generic_instagram_login_page(monkeypatch):
    """Generic social login pages should not be stored as useful guest research."""
    monkeypatch.setattr(
        guest_research,
        "_fetch_page",
        lambda url: {
            "url": url,
            "title": "Login • Instagram",
            "description": "Create an account or log in to Instagram - Share what you're into with the people who get you.",
            "heading": "",
            "text": "Create an account or log in to Instagram",
        },
    )

    with pytest.raises(ValueError):
        guest_research.research_guest_from_public_web(
            {
                "website": "",
                "social_media_handles": "Instagram: eva.hooft",
            }
        )


def test_web_service_can_create_and_update_guest(temp_db):
    """The service layer should write and update guests through the shared database."""
    service = GuestWebService(temp_db.db_path)

    created_guest = service.create_guest(
        {
            "full_name": "Jordan Rivers",
            "email": "jordan@example.com",
            "background": "Host and storyteller",
        }
    )
    assert created_guest["original_file_name"] == FORM_SOURCE_NAME

    updated_guest = service.update_guest_status(created_guest["id"], "accepted")
    assert updated_guest["email_status"] == "accepted"

    listed_guests = service.list_guests()["guests"]
    assert len(listed_guests) == 1
    assert listed_guests[0]["full_name"] == "Jordan Rivers"


def test_web_service_create_guest_updates_existing_match(temp_db):
    """Public and dashboard writes should not create duplicate guests."""
    service = GuestWebService(temp_db.db_path)

    first_guest = service.create_guest(
        {
            "full_name": "Jordan Rivers",
            "email": "jordan@example.com",
            "background": "First version",
        }
    )
    second_guest = service.create_guest(
        {
            "full_name": "Jordan Rivers",
            "email": "jordan@example.com",
            "background": "Refined version",
            "profession": "Coach",
        }
    )

    assert first_guest["id"] == second_guest["id"]
    guests = service.list_guests()["guests"]
    assert len(guests) == 1
    assert guests[0]["background"] == "Refined version"
    assert guests[0]["profession"] == "Coach"


def test_web_service_can_update_guest_details_without_resetting_status(temp_db):
    """Dashboard edits should update guest details while preserving decision metadata."""
    service = GuestWebService(temp_db.db_path)
    guest = service.create_guest(
        {
            "full_name": "Jordan Rivers",
            "email": "jordan@example.com",
            "background": "First version",
        }
    )
    service.update_guest_status(guest["id"], "accepted")

    updated_guest = service.update_guest(
        guest["id"],
        {
            "profession": "Coach",
            "website": "https://jordan.example.com",
            "background": "Updated version",
        },
    )

    assert updated_guest["profession"] == "Coach"
    assert updated_guest["website"] == "https://jordan.example.com"
    assert updated_guest["background"] == "Updated version"
    assert updated_guest["email_status"] == "accepted"


def test_delete_processed_guest_requires_exact_name_confirmation(temp_db):
    """Processed guests should need a typed full-name confirmation before deletion."""
    service = GuestWebService(temp_db.db_path)
    guest = service.create_guest(
        {
            "full_name": "Luke Aulin",
            "email": "luke@example.com",
            "background": "Guest profile",
        }
    )
    service.update_guest_status(guest["id"], "accepted")

    with pytest.raises(WebInterfaceError, match='Type "Luke Aulin" to delete this processed guest.'):
        service.delete_guest(guest["id"])

    result = service.delete_guest(guest["id"], confirm_name="Luke Aulin")
    assert result["deleted"] is True
    assert service.database.get_guest_by_id(guest["id"]) is None


def test_delete_unprocessed_guest_still_works_without_typed_confirmation(temp_db):
    """Unprocessed guests can still be deleted without the stronger name gate."""
    service = GuestWebService(temp_db.db_path)
    guest = service.create_guest(
        {
            "full_name": "Fresh Guest",
            "email": "fresh@example.com",
        }
    )

    result = service.delete_guest(guest["id"])
    assert result["deleted"] is True
    assert service.database.get_guest_by_id(guest["id"]) is None


def test_delete_interview_requires_exact_label_confirmation(temp_db):
    """Interview deletion should require a typed guest label."""
    service = GuestWebService(temp_db.db_path)
    interview = service.create_interview(
        {
            "guest_name": "Jordan Rivers",
            "guest_email": "jordan@example.com",
            "scheduled_for": "2026-04-10 18:00:00",
        }
    )

    with pytest.raises(WebInterfaceError, match='Type "Jordan Rivers" to delete this interview.'):
        service.delete_interview(interview["id"])

    result = service.delete_interview(interview["id"], confirm_label="Jordan Rivers")
    assert result["deleted"] is True
    assert service.database.get_interview_by_id(interview["id"]) is None


def test_delete_episode_requires_exact_label_confirmation(temp_db):
    """Episode deletion should require a typed episode label."""
    service = GuestWebService(temp_db.db_path)
    episode = service.create_episode(
        {
            "guest_name": "Jordan Rivers",
            "guest_email": "jordan@example.com",
            "episode_title": "Healing Through Honest Conversations",
        }
    )

    with pytest.raises(WebInterfaceError, match='Type "Healing Through Honest Conversations" to delete this episode.'):
        service.delete_episode(episode["id"])

    result = service.delete_episode(episode["id"], confirm_label="Healing Through Honest Conversations")
    assert result["deleted"] is True
    assert service.database.get_episode_by_id(episode["id"]) is None


def test_web_service_can_research_guest_and_store_public_profile_context(monkeypatch, temp_db):
    """Dashboard research should save structured public-profile evidence on the guest."""
    service = GuestWebService(temp_db.db_path)
    guest = service.create_guest(
        {
            "full_name": "Jordan Rivers",
            "email": "jordan@example.com",
            "website": "https://jordan.example.com",
        }
    )

    monkeypatch.setattr(
        "guest_database_manager.web_interface.research_guest_from_public_web",
        lambda current: {
            "summary": "Public profile research suggests strong conversation angles around healing and leadership.",
            "likely_topics": ["Healing", "Leadership"],
            "timely_signals": ["public profile emphasizes speaking experience"],
            "sources": [{"url": "https://jordan.example.com", "host": "jordan.example.com", "title": "Jordan Rivers"}],
            "updated_at": "2026-04-03T10:00:00Z",
        },
    )

    researched_guest = service.research_guest(guest["id"])

    assert researched_guest["guest_research"]["likely_topics"] == ["Healing", "Leadership"]
    assert researched_guest["guest_research_updated_at"] == "2026-04-03T10:00:00Z"
    assert researched_guest["guest_research"]["research_mode"] == "manual"
    assert researched_guest["guest_research"]["freshness"]["status"] in {"fresh", "aging", "stale", "unknown"}


def test_web_service_can_retry_failed_research_with_search(monkeypatch, temp_db):
    """Failed research should be recoverable via the search-assisted retry path."""
    service = GuestWebService(temp_db.db_path)
    guest = service.create_guest(
        {
            "full_name": "Jordan Rivers",
            "email": "jordan@example.com",
            "website": "https://broken.example.com",
        }
    )
    service._persist_guest_research_failure(guest, "403 Forbidden", mode="manual")

    monkeypatch.setattr(
        "guest_database_manager.web_interface.research_guest_from_google_search",
        lambda current: {
            "summary": "Search-assisted research suggests strong conversation angles around healing and leadership.",
            "likely_topics": ["Healing", "Leadership"],
            "timely_signals": ["public profile emphasizes speaking experience"],
            "sources": [{"url": "https://jordan.example.com", "host": "jordan.example.com", "title": "Jordan Rivers"}],
            "search_fallback": {
                "query_url": "https://www.google.com/search?q=Jordan+Rivers",
                "result_urls": ["https://jordan.example.com"],
            },
            "updated_at": "2026-04-04T10:00:00Z",
        },
    )

    researched_guest = service.retry_guest_research_with_search(guest["id"])

    assert researched_guest["guest_research"]["likely_topics"] == ["Healing", "Leadership"]
    assert researched_guest["guest_research"]["cache_status"] == "ready"
    assert researched_guest["guest_research"]["search_fallback"]["result_urls"] == ["https://jordan.example.com"]


def test_retry_failed_research_with_search_requires_failed_cache(temp_db):
    """Search-assisted retry should only run on guests whose research previously failed."""
    service = GuestWebService(temp_db.db_path)
    guest = service.create_guest(
        {
            "full_name": "Jordan Rivers",
            "email": "jordan@example.com",
            "website": "https://jordan.example.com",
        }
    )

    with pytest.raises(WebInterfaceError, match="only available for guests whose research has already failed"):
        service.retry_guest_research_with_search(guest["id"])


def test_planning_uses_guest_research_as_copilot_context(monkeypatch, temp_db):
    """Planning should attach stored guest research and reuse it in copy suggestions."""
    service = GuestWebService(temp_db.db_path)
    guest = service.create_guest(
        {
            "full_name": "Jordan Rivers",
            "email": "jordan@example.com",
            "website": "https://jordan.example.com",
        }
    )

    monkeypatch.setattr(
        "guest_database_manager.web_interface.research_guest_from_public_web",
        lambda current: {
            "summary": "Public profile research suggests strong conversation angles around healing and leadership.",
            "likely_topics": ["Healing", "Leadership"],
            "timely_signals": ["public profile emphasizes speaking experience"],
            "sources": [{"url": "https://jordan.example.com", "host": "jordan.example.com", "title": "Jordan Rivers"}],
            "updated_at": "2026-04-03T10:00:00Z",
        },
    )
    service.research_guest(guest["id"])
    service.create_episode(
        {
            "guest_name": "Jordan Rivers",
            "guest_email": "jordan@example.com",
            "episode_title": "Jordan Rivers",
            "category": "Leadership",
            "production_status": "ready",
            "promotion_status": "ready",
        }
    )

    planning = service.list_planning()
    episode = next(item for item in planning["episodes"] if item["guest_email"] == "jordan@example.com")

    assert episode["guest_research"]["likely_topics"] == ["Healing", "Leadership"]
    assert "public work in healing, leadership" in episode["copy_assist"]["summary"].lower()


def test_planning_can_attach_openai_scheduling_copilot(monkeypatch, temp_db):
    """Planning recommendations should expose optional OpenAI scheduling copilot evidence."""
    service = GuestWebService(temp_db.db_path)
    service.create_episode(
        {
            "guest_name": "Jordan Rivers",
            "guest_email": "jordan@example.com",
            "episode_title": "Healing Through Honest Conversations",
            "topic": "Healing and leadership",
            "category": "Mental Health",
            "production_status": "ready",
            "promotion_status": "ready",
        }
    )

    class StubCopilot:
        def enrich_recommendations(self, recommendations, *, reference, released_history):
            enriched = []
            for item in recommendations:
                enriched_item = dict(item)
                enriched_item["ai_copilot"] = {
                    "model": "gpt-5",
                    "alignment_score": 82,
                    "summary": "Research-backed fit for the current release window.",
                    "why_now": ["guest research supports a timely healing angle"],
                    "watchouts": ["keep the framing grounded and specific"],
                    "monthly_theme": "Renewal after hard seasons",
                    "source_evidence": [{"source": "Guest website", "detail": "Mentions healing and leadership work"}],
                }
                enriched.append(enriched_item)
            return {
                "status": "active",
                "message": "AI copilot enriched the recommendations.",
                "model": "gpt-5",
                "current_month_context": {"month_label": "April 2026", "theme": "Renewal, resurrection, and new life"},
                "recommendations": enriched,
            }

    monkeypatch.setattr(service, "_build_openai_scheduling_copilot", lambda: StubCopilot())

    planning = service.list_planning()
    ai_planning = service.list_planning_ai_copilot()
    recommendation = ai_planning["recommendations"][0]

    assert planning["ai_scheduling_enabled"] is True
    assert "ai_copilot" not in planning["recommendations"][0]
    assert planning["ai_copilot_status"]["status"] == "configured"
    assert ai_planning["ai_scheduling_enabled"] is True
    assert ai_planning["ai_copilot_status"]["status"] == "active"
    assert ai_planning["ai_copilot_status"]["current_month_context"]["theme"] == "Renewal, resurrection, and new life"
    assert recommendation["ai_copilot"]["model"] == "gpt-5"
    assert recommendation["ai_copilot"]["alignment_score"] == 82


def test_planning_ai_copilot_auto_researches_top_candidates(monkeypatch, temp_db):
    """AI planning should auto-research matched guests when stored research is still missing."""
    service = GuestWebService(temp_db.db_path)
    service.create_guest(
        {
            "full_name": "Jordan Rivers",
            "email": "jordan@example.com",
            "website": "https://jordan.example.com",
            "profession": "Speaker",
            "background": "Jordan helps people heal through honest conversations and resilient leadership.",
            "passionate_topics": "Healing",
        }
    )
    service.create_episode(
        {
            "guest_name": "Jordan Rivers",
            "guest_email": "jordan@example.com",
            "episode_title": "Jordan Rivers",
            "category": "Mental Health",
            "production_status": "ready",
            "promotion_status": "ready",
        }
    )

    monkeypatch.setattr(
        "guest_database_manager.web_interface.research_guest_from_public_web",
        lambda current: {
            "summary": "Public profile research suggests strong conversation angles around healing and leadership.",
            "likely_topics": ["Healing", "Leadership"],
            "timely_signals": ["public profile emphasizes speaking experience"],
            "sources": [{"url": "https://jordan.example.com", "host": "jordan.example.com", "title": "Jordan Rivers"}],
            "updated_at": "2026-04-03T10:00:00Z",
        },
    )

    class StubCopilot:
        def enrich_recommendations(self, recommendations, *, reference, released_history):
            assert recommendations[0]["guest_research"]["likely_topics"] == ["Healing", "Leadership"]
            return {
                "status": "active",
                "message": "AI copilot enriched the recommendations.",
                "model": "gpt-5",
                "current_month_context": {"month_label": "April 2026", "theme": "Renewal, resurrection, and new life"},
                "recommendations": recommendations,
            }

    monkeypatch.setattr(service, "_build_openai_scheduling_copilot", lambda: StubCopilot())

    ai_planning = service.list_planning_ai_copilot()
    researched_guest = next(
        guest for guest in service.database.get_all_guests()
        if guest.get("email") == "jordan@example.com"
    )

    assert ai_planning["ai_copilot_status"]["status"] == "active"
    assert "auto-researched 1 guest profile" in ai_planning["ai_copilot_status"]["message"].lower()
    assert researched_guest["guest_research"]
    assert json.loads(researched_guest["guest_research"])["research_mode"] == "auto"


def test_planning_ai_copilot_does_not_rerun_existing_auto_research(monkeypatch, temp_db):
    """Stored guest research should be reused until the operator manually refreshes it."""
    service = GuestWebService(temp_db.db_path)
    guest = service.create_guest(
        {
            "full_name": "Jordan Rivers",
            "email": "jordan@example.com",
            "website": "https://jordan.example.com",
        }
    )
    stored_research = {
        "summary": "Stored profile evidence around healing and leadership.",
        "likely_topics": ["Healing", "Leadership"],
        "timely_signals": ["public profile emphasizes speaking experience"],
        "sources": [{"url": "https://jordan.example.com", "host": "jordan.example.com", "title": "Jordan Rivers"}],
        "updated_at": "2025-01-01T10:00:00Z",
        "research_mode": "auto",
    }
    service.database.update_guest_by_id(
        guest["id"],
        {
            **service.database.get_guest_by_id(guest["id"]),
            "guest_research": json.dumps(stored_research, ensure_ascii=False),
            "guest_research_updated_at": "2025-01-01T10:00:00Z",
        },
    )
    service.create_episode(
        {
            "guest_name": "Jordan Rivers",
            "guest_email": "jordan@example.com",
            "episode_title": "Jordan Rivers",
            "category": "Mental Health",
            "production_status": "ready",
            "promotion_status": "ready",
        }
    )

    def should_not_run(_current):
        raise AssertionError("Planning should not rerun guest research when cached research already exists.")

    monkeypatch.setattr(
        "guest_database_manager.web_interface.research_guest_from_public_web",
        should_not_run,
    )

    class StubCopilot:
        def enrich_recommendations(self, recommendations, *, reference, released_history):
            assert recommendations[0]["guest_research"]["research_mode"] == "auto"
            return {
                "status": "active",
                "message": "AI copilot enriched the recommendations.",
                "model": "gpt-5",
                "current_month_context": {"month_label": "April 2026", "theme": "Renewal, resurrection, and new life"},
                "recommendations": recommendations,
            }

    monkeypatch.setattr(service, "_build_openai_scheduling_copilot", lambda: StubCopilot())

    ai_planning = service.list_planning_ai_copilot()

    assert "auto-researched" not in ai_planning["ai_copilot_status"]["message"].lower()


def test_planning_ai_copilot_thin_context_message_explains_candidate_coverage(monkeypatch, temp_db):
    """Thin-context status should explain how much grounded data the AI candidate window had."""
    service = GuestWebService(temp_db.db_path)
    service.create_episode(
        {
            "guest_name": "Jordan Rivers",
            "guest_email": "jordan@example.com",
            "episode_title": "Jordan Rivers",
            "category": "Mental Health",
            "production_status": "ready",
            "promotion_status": "ready",
        }
    )

    class ThinContextCopilot:
        def enrich_recommendations(self, recommendations, *, reference, released_history):
            return {
                "status": "thin_context",
                "message": "AI copilot was configured, but the current candidates had too little grounded context to add trustworthy guidance.",
                "model": "gpt-5",
                "current_month_context": {"month_label": "April 2026", "theme": "Renewal, resurrection, and new life"},
                "recommendations": recommendations,
            }

    monkeypatch.setattr(service, "_build_openai_scheduling_copilot", lambda: ThinContextCopilot())

    ai_planning = service.list_planning_ai_copilot()

    assert ai_planning["ai_copilot_status"]["status"] == "thin_context"
    assert "0 of 1 ai candidates had matched guest profile data" in ai_planning["ai_copilot_status"]["message"].lower()
    assert ai_planning["ai_copilot_status"]["diagnostics"]["with_guest_research"] == 0


def test_planning_ai_copilot_can_research_episode_directly_without_guest_match(monkeypatch, temp_db):
    """AI planning should use the episode website directly when no dashboard guest match exists."""
    service = GuestWebService(temp_db.db_path)
    service.create_episode(
        {
            "guest_name": "Jordan Rivers",
            "guest_email": "jordan@example.com",
            "episode_title": "Jordan Rivers",
            "website": "https://jordan.example.com",
            "category": "Mental Health",
            "production_status": "ready",
            "promotion_status": "ready",
        }
    )

    monkeypatch.setattr(
        "guest_database_manager.web_interface.research_guest_from_public_web",
        lambda current: {
            "summary": "Direct episode research found a healing and leadership profile.",
            "likely_topics": ["Healing", "Leadership"],
            "timely_signals": ["public profile emphasizes speaking experience"],
            "sources": [{"url": "https://jordan.example.com", "host": "jordan.example.com", "title": "Jordan Rivers"}],
            "updated_at": "2026-04-04T10:00:00Z",
        },
    )

    class StubCopilot:
        def enrich_recommendations(self, recommendations, *, reference, released_history):
            assert recommendations[0]["guest_research"]["research_mode"] == "auto_episode"
            return {
                "status": "active",
                "message": "AI copilot enriched the recommendations.",
                "model": "gpt-5",
                "current_month_context": {"month_label": "April 2026", "theme": "Renewal, resurrection, and new life"},
                "recommendations": recommendations,
            }

    monkeypatch.setattr(service, "_build_openai_scheduling_copilot", lambda: StubCopilot())

    ai_planning = service.list_planning_ai_copilot()

    assert ai_planning["ai_copilot_status"]["status"] == "active"
    assert ai_planning["recommendations"][0]["guest_research"]["likely_topics"] == ["Healing", "Leadership"]


def test_openai_scheduling_copilot_builds_grounded_fallback_when_model_returns_no_analyses():
    """Researched candidates should still get cautious copilot guidance when the model returns an empty analysis list."""
    copilot = OpenAISchedulingCopilot(api_key="test", model="gpt-5")

    recommendations = [
        {
            "id": 1,
            "guest_name": "Jordan Rivers",
            "website": "https://jordan.example.com",
            "episode_title": "Jordan Rivers",
            "topic": "",
            "category": "Mental Health",
            "recommended_release_date": "2026-04-08 17:00:00",
            "production_status": "ready",
            "promotion_status": "ready",
            "priority_score": 100,
            "promotion_readiness": {"score": 76, "label": "Nearly ready"},
            "archive_overlap": {"status": "clear", "message": ""},
            "topic_cluster_warning": {"status": "clear", "message": ""},
            "guest_profile_context": None,
            "guest_research": {
                "summary": "Public profile research suggests strong conversation angles around healing and leadership.",
                "likely_topics": ["Healing", "Leadership"],
                "timely_signals": ["public profile emphasizes speaking experience"],
                "sources": [{"title": "Jordan Rivers", "description": "Jordan helps people heal through honest conversations."}],
                "research_mode": "auto_episode",
            },
            "why_now": [],
            "watchouts": [],
        }
    ]

    copilot._call_openai = lambda payload: {"status": "active", "analyses": []}  # type: ignore[method-assign]
    result = copilot.enrich_recommendations(recommendations, reference=pd.Timestamp("2026-04-04").to_pydatetime(), released_history=[])

    assert result["status"] == "active"
    assert "fallback guidance" in result["message"].lower()
    assert result["recommendations"][0]["ai_copilot"]["alignment_score"] >= 58


def test_planning_matches_guest_on_safe_name_variant(temp_db):
    """Planning should attach guest context when the episode name is a safe subset of the stored guest name."""
    service = GuestWebService(temp_db.db_path)
    guest = service.create_guest(
        {
            "full_name": "Jordan A Rivers",
            "email": "jordan@example.com",
            "website": "https://jordan.example.com",
            "profession": "Coach",
            "background": "Leadership and healing mentor",
        }
    )
    service.database.update_guest_by_id(
        guest["id"],
        {
            **service.database.get_guest_by_id(guest["id"]),
            "guest_research": json.dumps(
                {
                    "summary": "Stored profile context",
                    "likely_topics": ["Healing"],
                    "updated_at": "2026-04-01T10:00:00Z",
                    "research_mode": "manual",
                    "cache_status": "ready",
                },
                ensure_ascii=False,
            ),
            "guest_research_updated_at": "2026-04-01T10:00:00Z",
        },
    )
    service.create_episode(
        {
            "guest_name": "Jordan Rivers",
            "episode_title": "Jordan Rivers",
            "category": "Mental Health",
            "production_status": "ready",
            "promotion_status": "ready",
        }
    )

    planning = service.list_planning()
    episode = next(item for item in planning["recommendations"] if item["guest_name"] == "Jordan Rivers")

    assert episode["guest_profile_context"]["profession"] == "Coach"
    assert episode["guest_research"]["likely_topics"] == ["Healing"]


def test_episode_monthly_angle_review_state_is_persisted(temp_db):
    """Pinned or rejected monthly-angle decisions should persist on the episode record."""
    service = GuestWebService(temp_db.db_path)
    episode = service.create_episode(
        {
            "guest_name": "Jordan Rivers",
            "episode_title": "Jordan Rivers",
            "category": "Mental Health",
            "production_status": "ready",
            "promotion_status": "ready",
        }
    )

    updated = service.update_episode(
        episode["id"],
        {
            "ai_monthly_angle_state": "pinned",
            "ai_monthly_angle_theme": "Renewal after hard seasons",
        },
    )

    assert updated["ai_monthly_angle_state"] == "pinned"
    assert updated["ai_monthly_angle_theme"] == "Renewal after hard seasons"


def test_planning_keeps_ambiguous_name_matches_unlinked(temp_db):
    """Planning should skip guest research when multiple guests would match the same short name equally well."""
    service = GuestWebService(temp_db.db_path)
    service.create_guest(
        {
            "full_name": "Jordan A Rivers",
            "email": "jordan1@example.com",
            "website": "https://jordan-one.example.com",
        }
    )
    service.create_guest(
        {
            "full_name": "Jordan B Rivers",
            "email": "jordan2@example.com",
            "website": "https://jordan-two.example.com",
        }
    )
    service.create_episode(
        {
            "guest_name": "Jordan Rivers",
            "episode_title": "Jordan Rivers",
            "category": "Mental Health",
            "production_status": "ready",
            "promotion_status": "ready",
        }
    )

    planning = service.list_planning()
    episode = next(item for item in planning["recommendations"] if item["guest_name"] == "Jordan Rivers")

    assert episode["guest_profile_context"] is None
    assert episode["guest_research"] is None


def test_bulk_research_guests_skips_cached_and_missing_profiles(monkeypatch, temp_db):
    """Bulk guest research should only process guests who still need it and have usable profile hints."""
    service = GuestWebService(temp_db.db_path)
    cached_guest = service.create_guest(
        {
            "full_name": "Cached Guest",
            "email": "cached@example.com",
            "website": "https://cached.example.com",
        }
    )
    missing_profile_guest = service.create_guest(
        {
            "full_name": "Missing Profile Guest",
            "email": "missing@example.com",
        }
    )
    needs_research_guest = service.create_guest(
        {
            "full_name": "Needs Research Guest",
            "email": "needs@example.com",
            "website": "https://needs.example.com",
        }
    )
    service.database.update_guest_by_id(
        cached_guest["id"],
        {
            **service.database.get_guest_by_id(cached_guest["id"]),
            "guest_research": json.dumps({"summary": "Stored", "updated_at": "2026-04-01T10:00:00Z", "research_mode": "manual"}, ensure_ascii=False),
            "guest_research_updated_at": "2026-04-01T10:00:00Z",
        },
    )

    monkeypatch.setattr(
        "guest_database_manager.web_interface.research_guest_from_public_web",
        lambda current: {
            "summary": f"Research for {str(current.get('full_name') or '').strip()}",
            "likely_topics": ["Healing"],
            "timely_signals": [],
            "sources": [{"url": str(current.get("website") or "").strip(), "host": "example.com", "title": str(current.get("full_name") or "").strip()}],
            "updated_at": "2026-04-03T10:00:00Z",
        },
    )

    result = service.bulk_research_guests(limit=10)
    refreshed_needs_research = service.database.get_guest_by_id(needs_research_guest["id"])

    assert result["researched"] == 1
    assert result["skipped_cached"] >= 1
    assert result["skipped_missing_profile"] >= 1
    assert result["remaining_eligible"] == 0
    assert json.loads(refreshed_needs_research["guest_research"])["research_mode"] == "manual"


def test_bulk_research_guests_caches_failures_and_skips_them_later(monkeypatch, temp_db):
    """Bulk research should cache repeated failures so later runs do not retry the same guest."""
    service = GuestWebService(temp_db.db_path)
    guest = service.create_guest(
        {
            "full_name": "Broken Profile Guest",
            "email": "broken@example.com",
            "website": "https://broken.example.com",
        }
    )

    monkeypatch.setattr(
        "guest_database_manager.web_interface.research_guest_from_public_web",
        lambda current: (_ for _ in ()).throw(ValueError("403 Forbidden")),
    )

    first_result = service.bulk_research_guests(limit=10)
    stored_guest = service.database.get_guest_by_id(guest["id"])
    second_result = service.bulk_research_guests(limit=10)

    assert first_result["researched"] == 0
    assert "403 forbidden" in first_result["errors"][0].lower()
    assert json.loads(stored_guest["guest_research"])["cache_status"] == "failed"
    assert second_result["skipped_failed"] >= 1
    assert second_result["remaining_eligible"] == 0


def test_web_service_create_guest_preserves_existing_source_label(temp_db):
    """Dashboard writes should not replace an existing guest's original source label."""
    service = GuestWebService(temp_db.db_path)

    first_guest_id, _ = temp_db.upsert_guest(
        {
            "full_name": "Jordan Rivers",
            "email": "jordan@example.com",
            "background": "First version",
            "original_file_name": "legacy-import.xlsx",
            "original_data": '{"source":"legacy"}',
            "is_processed": False,
        }
    )
    second_guest = service.create_guest(
        {
            "full_name": "Jordan Rivers",
            "email": "jordan@example.com",
            "background": "Refined version",
        }
    )

    assert first_guest_id == second_guest["id"]
    guest = service.list_guests()["guests"][0]
    assert guest["original_file_name"] == "legacy-import.xlsx"


def test_web_service_can_create_public_intake_submission(temp_db):
    """The public intake flow should write a guest with website-specific source metadata."""
    service = GuestWebService(temp_db.db_path)

    created_guest = service.create_intake_submission(
        {
            "full_name": "Amara Stone",
            "email": "amara@example.com",
            "background": "I am a speaker and advocate whose work focuses on healing, resilience, and community storytelling.",
            "profession": "I work as a coach and facilitator after years of leading programs centered on recovery and growth.",
            "passionate_topics": "I love discussing healing, resilience, faith, emotional honesty, and what it takes to rebuild after hard seasons.",
            "message": "I want listeners to remember that healing is possible, honesty is powerful, and small consistent steps can change a life.",
            "experience": "I have spoken on podcasts, live panels, and community events where I share my story and practical lessons from it.",
            "additional_info": "I care deeply about meaningful conversations that leave people encouraged, grounded, and more hopeful than before.",
        }
    )

    assert created_guest["original_file_name"] == INTAKE_SOURCE_NAME
    assert created_guest["email_status"] is None


def test_public_intake_submission_does_not_inherit_previous_acceptance(temp_db):
    """A fresh website intake should not silently inherit accepted status from an older reviewed guest."""
    service = GuestWebService(temp_db.db_path)
    original = service.create_guest(
        {
            "full_name": "Amar Dhall",
            "email": "amar@example.com",
            "website": "https://example.com",
        }
    )
    service.update_guest_status(original["id"], "accepted")

    created_guest = service.create_intake_submission(
        {
            "full_name": "Amar Dhall",
            "email": "amar@example.com",
            "website": "https://example.com",
            "profession": "Author",
            "background": "I help people rebuild their confidence after hard seasons and major life transitions.",
            "passionate_topics": "Healing",
            "message": "Hope",
            "experience": "Yes - I have joined a few meaningful podcast conversations before.",
            "additional_info": "I would love to share practical hope and emotional resilience with your audience.",
            "social_handles": "Instagram: @amardhall",
            "has_social_media": "yes",
        }
    )

    assert created_guest["id"] == original["id"]
    assert created_guest["email_status"] is None
    assert created_guest["is_processed"] is False

    original_after = service.database.get_guest_by_id(original["id"])
    assert original_after["email_status"] is None
    assert original_after["is_processed"] == 0


def test_public_intake_requires_self_attestation(temp_db):
    """Guests should explicitly confirm they are applying for themselves."""
    service = GuestWebService(temp_db.db_path)

    with pytest.raises(WebInterfaceError, match="confirm that you are the guest applying for yourself"):
        service.create_intake_submission(
            {
                "application_role": "self",
                "full_name": "Amara Stone",
                "email": "amara@example.com",
                "profession": "Author",
                "background": "I help people find hope and clarity after major life transitions and hard seasons.",
                "passionate_topics": "Healing",
                "message": "Hope",
                "experience": "Yes - I have joined a few meaningful podcast conversations before.",
                "additional_info": "I would love to encourage your audience with honest, grounded hope.",
                "social_handles": "Instagram: @amarastone",
            }
        )


def test_public_intake_rejects_shared_email_used_for_other_guest(temp_db):
    """A guest should not be able to submit using an email already tied to another name."""
    service = GuestWebService(temp_db.db_path)
    service.create_guest({"full_name": "Agency Client One", "email": "shared@example.com"})

    with pytest.raises(WebInterfaceError, match="own personal or professional email address"):
        service.create_intake_submission(
            {
                "application_role": "self",
                "self_attestation": "yes",
                "full_name": "Agency Client Two",
                "email": "shared@example.com",
                "profession": "Coach",
                "background": "I work with people rebuilding their confidence after grief, burnout, and identity loss.",
                "passionate_topics": "Resilience",
                "message": "Healing",
                "experience": "Yes - I have spoken on a few podcasts and community events before.",
                "additional_info": "I would love to share a grounded message of resilience and hope.",
                "social_handles": "Instagram: @clienttwo",
            }
        )


def test_agency_referral_sends_personal_application_link(monkeypatch, temp_db):
    """Agency submissions should trigger a guest-owned intake invitation instead of a full intake approval flow."""

    sent = {}

    class StubEmailManager:
        def __init__(self):
            self.configured = False

        def configure_resend(self, **kwargs):
            self.configured = True

        def is_configured(self):
            return self.configured

        def send_personal_application_request_email(self, guest_name, to_email, intake_url, agency_name=""):
            sent["guest_name"] = guest_name
            sent["to_email"] = to_email
            sent["intake_url"] = intake_url
            sent["agency_name"] = agency_name
            return True

    monkeypatch.setattr("guest_database_manager.web_interface.EmailManager", StubEmailManager)
    monkeypatch.setenv(EMAIL_RESEND_API_KEY_ENV_VAR, "re_test_123")
    monkeypatch.setenv(EMAIL_FROM_ENV_VAR, "onboarding@updates.mirrortalkpodcast.com")
    monkeypatch.setenv(EMAIL_FROM_NAME_ENV_VAR, "Mirror Talk Podcast")

    service = GuestWebService(temp_db.db_path)
    created_guest = service.create_intake_submission(
        {
            "application_role": "on_behalf",
            "agency_name": "Bright Talent Agency",
            "agency_email": "hello@brighttalent.example",
            "represented_guest_name": "Amar Dhall",
            "represented_guest_email": "amar@example.com",
        }
    )

    assert created_guest["original_file_name"] == AGENCY_REFERRAL_SOURCE_NAME
    assert created_guest["submission_mode"] == "agency_referral"
    assert sent["guest_name"] == "Amar Dhall"
    assert sent["to_email"] == "amar@example.com"
    assert sent["agency_name"] == "Bright Talent Agency"
    assert "full_name=Amar+Dhall" in sent["intake_url"]
    assert "email=amar%40example.com" in sent["intake_url"]
    assert sent["intake_url"].startswith("https://guest-processing-production.up.railway.app/intake?")


def test_public_intake_link_reuses_booking_domain_when_public_url_missing(monkeypatch):
    """Agency referral links should fall back to the hosted intake route, not the marketing page."""
    monkeypatch.delenv(PUBLIC_INTAKE_URL_ENV_VAR, raising=False)
    monkeypatch.setenv(BOOKING_BASE_URL_ENV_VAR, "https://mirror.example.com/book")

    url = GuestWebService._public_intake_link("Dhruva Gulur", "dhruva@dhruvamd.com")

    assert url.startswith("https://mirror.example.com/intake?")
    assert "full_name=Dhruva+Gulur" in url
    assert "email=dhruva%40dhruvamd.com" in url


def test_list_guests_exposes_agency_submission_meta(monkeypatch, temp_db):
    """Dashboard payload should surface structured agency referral context."""

    class StubEmailManager:
        def __init__(self):
            self.configured = False

        def configure_resend(self, **kwargs):
            self.configured = True

        def is_configured(self):
            return self.configured

        def send_personal_application_request_email(self, guest_name, to_email, intake_url, agency_name=""):
            return True

    monkeypatch.setattr("guest_database_manager.web_interface.EmailManager", StubEmailManager)
    monkeypatch.setenv(EMAIL_RESEND_API_KEY_ENV_VAR, "re_test_123")
    monkeypatch.setenv(EMAIL_FROM_ENV_VAR, "onboarding@updates.mirrortalkpodcast.com")
    monkeypatch.setenv(EMAIL_FROM_NAME_ENV_VAR, "Mirror Talk Podcast")

    service = GuestWebService(temp_db.db_path)
    service.create_intake_submission(
        {
            "application_role": "on_behalf",
            "agency_name": "Bright Talent Agency",
            "agency_email": "hello@brighttalent.example",
            "represented_guest_name": "Amar Dhall",
            "represented_guest_email": "amar@example.com",
        }
    )

    payload = service.list_guests()
    guest = next(item for item in payload["guests"] if item["full_name"] == "Amar Dhall")

    assert guest["submission_meta"] == {
        "mode": "agency_referral",
        "label": "Agency referral",
        "guest_name": "Amar Dhall",
        "guest_email": "amar@example.com",
        "agency_name": "Bright Talent Agency",
        "agency_email": "hello@brighttalent.example",
        "personal_application_required": True,
        "personal_application_status": "Awaiting the guest's own application.",
    }


def test_resend_guest_personal_application_email(monkeypatch, temp_db):
    """Agency referrals should support resending the guest-owned application link from the dashboard."""
    sent = {}

    class StubEmailManager:
        def __init__(self):
            self.configured = False
            self.last_error = ""

        def configure_resend(self, **kwargs):
            self.configured = True

        def is_configured(self):
            return self.configured

        def send_personal_application_request_email(self, guest_name, to_email, intake_url, agency_name=""):
            sent["guest_name"] = guest_name
            sent["to_email"] = to_email
            sent["intake_url"] = intake_url
            sent["agency_name"] = agency_name
            return True

    monkeypatch.setattr("guest_database_manager.web_interface.EmailManager", StubEmailManager)
    monkeypatch.setenv(EMAIL_RESEND_API_KEY_ENV_VAR, "re_test_123")
    monkeypatch.setenv(EMAIL_FROM_ENV_VAR, "onboarding@updates.mirrortalkpodcast.com")
    monkeypatch.setenv(EMAIL_FROM_NAME_ENV_VAR, "Mirror Talk Podcast")
    monkeypatch.setenv(PUBLIC_INTAKE_URL_ENV_VAR, "https://guest-processing-production.up.railway.app/intake")

    service = GuestWebService(temp_db.db_path)
    created_guest = service.create_intake_submission(
        {
            "application_role": "on_behalf",
            "agency_name": "Kay Villanueva",
            "agency_email": "kay@example.com",
            "represented_guest_name": "Dhruva Gulur",
            "represented_guest_email": "dhruva@dhruvamd.com",
        }
    )
    sent.clear()

    resent_guest = service.resend_guest_personal_application_email(created_guest["id"])

    assert resent_guest["id"] == created_guest["id"]
    assert sent["guest_name"] == "Dhruva Gulur"
    assert sent["to_email"] == "dhruva@dhruvamd.com"
    assert sent["agency_name"] == "Kay Villanueva"
    assert sent["intake_url"].startswith("https://guest-processing-production.up.railway.app/intake?")


def test_resend_guest_personal_application_email_requires_agency_referral(monkeypatch, temp_db):
    """The resend action should not appear as a generic email sender for normal guests."""
    class StubEmailManager:
        def __init__(self):
            self.configured = False

        def configure_resend(self, **kwargs):
            self.configured = True

        def is_configured(self):
            return self.configured

    monkeypatch.setattr("guest_database_manager.web_interface.EmailManager", StubEmailManager)
    monkeypatch.setenv(EMAIL_RESEND_API_KEY_ENV_VAR, "re_test_123")
    monkeypatch.setenv(EMAIL_FROM_ENV_VAR, "onboarding@updates.mirrortalkpodcast.com")
    monkeypatch.setenv(EMAIL_FROM_NAME_ENV_VAR, "Mirror Talk Podcast")

    service = GuestWebService(temp_db.db_path)
    guest = service.create_guest({"full_name": "Amara Stone", "email": "amara@example.com"})

    with pytest.raises(WebInterfaceError, match="not created through an agency referral"):
        service.resend_guest_personal_application_email(guest["id"])


def test_list_guests_exposes_self_submission_meta(temp_db):
    """Dashboard payload should show direct self-application context."""
    service = GuestWebService(temp_db.db_path)
    service.create_intake_submission(
        {
            "application_role": "self",
            "self_attestation": "yes",
            "full_name": "Amara Stone",
            "email": "amara@example.com",
            "profession": "Author",
            "background": "I help people find hope and clarity after major life transitions and hard seasons.",
            "passionate_topics": "Healing",
            "message": "Hope",
            "experience": "Yes - I have joined a few meaningful podcast conversations before.",
            "additional_info": "I would love to encourage your audience with honest, grounded hope.",
            "social_handles": "Instagram: @amarastone",
        }
    )

    payload = service.list_guests()
    guest = next(item for item in payload["guests"] if item["full_name"] == "Amara Stone")

    assert guest["submission_meta"] == {
        "mode": "self_application",
        "label": "Self application",
        "guest_name": "Amara Stone",
        "guest_email": "amara@example.com",
        "agency_name": "",
        "agency_email": "",
        "personal_application_required": True,
        "personal_application_status": "Confirmed by the guest.",
    }


def test_list_guests_flags_shared_identity_patterns(temp_db):
    """Dashboard review assist should flag reused email and shared website domains across different names."""
    service = GuestWebService(temp_db.db_path)
    temp_db.insert_guest(
        {
            "full_name": "Agency Client One",
            "email": "shared@example.com",
            "website": "https://shared-domain.example.com",
            "background": "A grounded and thoughtful story about healing after burnout.",
            "profession": "Coach",
            "passionate_topics": "Healing",
            "message": "Hope",
        }
    )
    temp_db.insert_guest(
        {
            "full_name": "Agency Client Two",
            "email": "shared@example.com",
            "website": "https://shared-domain.example.com/about",
            "background": "A grounded and thoughtful story about resilience after loss.",
            "profession": "Speaker",
            "passionate_topics": "Resilience",
            "message": "Faith",
        }
    )

    payload = service.list_guests()
    guest = next(item for item in payload["guests"] if item["full_name"] == "Agency Client Two")

    assert "Agency Client One" in guest["decision_support"]["identity_flags"]["email_conflicts"]
    assert "Agency Client One" in guest["decision_support"]["identity_flags"]["host_conflicts"]
    cautions = " ".join(guest["decision_support"]["cautions"]).lower()
    assert "same email appears" in cautions


def test_public_intake_submission_sends_confirmation_email_when_configured(monkeypatch, temp_db):
    """Public intake should send a best-effort confirmation email when hosted email is configured."""

    class StubEmailManager:
        def __init__(self):
            self.configured = False

        def configure_resend(self, **kwargs):
            self.configured = True

        def is_configured(self):
            return self.configured

        def send_intake_confirmation_email(self, guest_name, to_email):
            assert guest_name == "Amara Stone"
            assert to_email == "amara@example.com"
            return True

    monkeypatch.setattr("guest_database_manager.web_interface.EmailManager", StubEmailManager)
    monkeypatch.setenv(EMAIL_RESEND_API_KEY_ENV_VAR, "re_test_123")
    monkeypatch.setenv(EMAIL_FROM_ENV_VAR, "onboarding@updates.mirrortalkpodcast.com")
    monkeypatch.setenv(EMAIL_FROM_NAME_ENV_VAR, "Mirror Talk Podcast")

    service = GuestWebService(temp_db.db_path)
    created_guest = service.create_intake_submission(
        {
            "full_name": "Amara Stone",
            "email": "amara@example.com",
            "background": "I am a speaker and advocate whose work focuses on healing, resilience, and community storytelling.",
            "profession": "Coach",
            "passionate_topics": "Healing",
            "message": "Hope",
            "additional_info": "I care deeply about meaningful conversations that leave people encouraged and grounded.",
        }
    )

    assert created_guest["original_file_name"] == INTAKE_SOURCE_NAME


def test_public_intake_submission_ignores_confirmation_email_failures(monkeypatch, temp_db):
    """Confirmation email failures should not block the intake submission itself."""

    class StubEmailManager:
        def __init__(self):
            self.configured = False

        def configure_resend(self, **kwargs):
            self.configured = True

        def is_configured(self):
            return self.configured

        def send_intake_confirmation_email(self, guest_name, to_email):
            raise RuntimeError("delivery failed")

    monkeypatch.setattr("guest_database_manager.web_interface.EmailManager", StubEmailManager)
    monkeypatch.setenv(EMAIL_RESEND_API_KEY_ENV_VAR, "re_test_123")
    monkeypatch.setenv(EMAIL_FROM_ENV_VAR, "onboarding@updates.mirrortalkpodcast.com")
    monkeypatch.setenv(EMAIL_FROM_NAME_ENV_VAR, "Mirror Talk Podcast")

    service = GuestWebService(temp_db.db_path)
    created_guest = service.create_intake_submission(
        {
            "full_name": "Amara Stone",
            "email": "amara@example.com",
            "background": "I am a speaker and advocate whose work focuses on healing, resilience, and community storytelling.",
            "profession": "Coach",
            "passionate_topics": "Healing",
            "message": "Hope",
            "additional_info": "I care deeply about meaningful conversations that leave people encouraged and grounded.",
        }
    )

    assert created_guest["full_name"] == "Amara Stone"


def test_public_intake_validation_allows_concise_profession_answer(temp_db):
    """Profession answers should not require an essay to pass the intake checks."""
    service = GuestWebService(temp_db.db_path)

    created_guest = service.create_intake_submission(
        {
            "full_name": "Amara Stone",
            "email": "amara@example.com",
            "website": "www.amarastone.com",
            "background": "I am a speaker and advocate whose work focuses on healing, resilience, and community storytelling.",
            "profession": "Trauma-informed coach and speaker.",
            "passionate_topics": "I love discussing healing, resilience, faith, emotional honesty, and what it takes to rebuild after hard seasons.",
            "message": "I want listeners to remember that healing is possible, honesty is powerful, and small consistent steps can change a life.",
            "experience": "I have spoken on podcasts and community panels about resilience, leadership, and emotional healing.",
            "additional_info": "I care deeply about meaningful conversations that leave people encouraged and grounded.",
        }
    )

    assert created_guest["website"] == "https://www.amarastone.com"


def test_public_intake_validation_allows_one_word_profession_answer(temp_db):
    """Very normal one-word profession answers should not be rejected."""
    service = GuestWebService(temp_db.db_path)

    created_guest = service.create_intake_submission(
        {
            "full_name": "Jordan Hale",
            "email": "jordan@example.com",
            "background": "I am a storyteller and coach who helps people rebuild confidence after difficult seasons of life.",
            "profession": "Author",
            "passionate_topics": "I care about healing, courage, resilience, emotional honesty, and the power of meaningful conversations.",
            "message": "I want listeners to leave with more hope, more honesty, and more trust in their ability to begin again.",
            "additional_info": "I would love to contribute a grounded and thoughtful conversation to Mirror Talk.",
        }
    )

    assert created_guest["profession"] == "Author"


def test_public_intake_validation_allows_one_word_passionate_topics_answer(temp_db):
    """One-word passionate topics answers can still be perfectly valid."""
    service = GuestWebService(temp_db.db_path)

    created_guest = service.create_intake_submission(
        {
            "full_name": "Amina Lane",
            "email": "amina@example.com",
            "background": "I am a coach and storyteller who helps people rebuild confidence after painful seasons of life.",
            "profession": "Coach",
            "passionate_topics": "God",
            "message": "I want listeners to leave with more hope, honesty, and courage for their own journey.",
            "additional_info": "I would love to contribute a grounded and meaningful conversation to Mirror Talk.",
        }
    )

    assert created_guest["passionate_topics"] == "God"


def test_public_intake_validation_allows_one_word_message_answer(temp_db):
    """One-word takeaways can still be meaningful and should not be rejected."""
    service = GuestWebService(temp_db.db_path)

    created_guest = service.create_intake_submission(
        {
            "full_name": "Amina Lane",
            "email": "amina@example.com",
            "background": "I am a coach and storyteller who helps people rebuild confidence after painful seasons of life.",
            "profession": "Coach",
            "passionate_topics": "Healing",
            "message": "Hope",
            "additional_info": "I would love to contribute a grounded and meaningful conversation to Mirror Talk.",
        }
    )

    assert created_guest["message_takeaway"] == "Hope"


def test_public_intake_request_accepts_configured_token():
    """Public intake should still accept explicit API-token requests."""
    handler = GuestWebRequestHandler.__new__(GuestWebRequestHandler)
    handler.headers = {"X-Api-Token": "secret-token"}

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setenv(API_TOKEN_ENV_VAR, "secret-token")
        assert handler._is_authorized_request() is True


def test_public_intake_request_accepts_known_origin_without_token():
    """Public intake should trust the approved website origin even when a token is configured."""
    handler = GuestWebRequestHandler.__new__(GuestWebRequestHandler)
    handler.headers = {"Origin": "https://mirrortalkpodcast.com"}
    handler.server = type("Server", (), {"server_port": 8000})()

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setenv(API_TOKEN_ENV_VAR, "secret-token")
        assert handler._is_authorized_request() is True


def test_public_intake_request_accepts_live_service_origin_without_token():
    """Public intake should trust submissions that originate from the live intake service itself."""
    handler = GuestWebRequestHandler.__new__(GuestWebRequestHandler)
    handler.headers = {
        "Origin": "https://guest-processing-production.up.railway.app",
        "X-Forwarded-Proto": "https",
        "Host": "guest-processing-production.up.railway.app",
    }
    handler.server = type("Server", (), {"server_port": 8000})()

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setenv(API_TOKEN_ENV_VAR, "secret-token")
        assert handler._is_authorized_request() is True


def test_public_intake_request_rejects_unknown_origin_without_token():
    """Public intake should still reject untrusted cross-site submissions when a token is configured."""
    handler = GuestWebRequestHandler.__new__(GuestWebRequestHandler)
    handler.headers = {"Origin": "https://example.com"}
    handler.server = type("Server", (), {"server_port": 8000})()

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setenv(API_TOKEN_ENV_VAR, "secret-token")
        assert handler._is_authorized_request() is False


def test_web_service_can_import_uploaded_csv(temp_db):
    """Uploaded CSV imports should reuse the shared import pipeline and keep the source filename."""
    service = GuestWebService(temp_db.db_path)
    csv_bytes = (
        "Full name,Email,Website\n"
        "Jordan Rivers,jordan@example.com,https://jord.example.com\n"
    ).encode("utf-8")

    result = service.import_guest_file("guest-intake.csv", csv_bytes)

    assert result["imported"] == 1
    imported_guest = service.list_guests()["guests"][0]
    assert imported_guest["original_file_name"] == "guest-intake.csv"
    assert imported_guest["email"] == "jordan@example.com"


def test_web_service_skips_blank_uploaded_guest_rows(temp_db):
    """Uploaded guest files should ignore rows that are completely empty."""
    service = GuestWebService(temp_db.db_path)
    csv_bytes = (
        "Full name,Email,Website\n"
        "Jordan Rivers,jordan@example.com,https://jord.example.com\n"
        ",,\n"
    ).encode("utf-8")

    result = service.import_guest_file("guest-intake.csv", csv_bytes)

    assert result["imported"] == 1
    assert result["skipped"] == 1
    assert len(service.list_guests()["guests"]) == 1


def test_web_service_can_import_uploaded_excel_with_timestamp_columns(temp_db, tmp_path):
    """Excel imports should tolerate timestamp metadata columns from form exports."""
    service = GuestWebService(temp_db.db_path)
    excel_path = tmp_path / "guest-intake.xlsx"
    dataframe = pd.DataFrame(
        [
            {
                "Start time": pd.Timestamp("2026-01-20 21:51:28"),
                "Completion time": pd.Timestamp("2026-01-20 21:54:39"),
                "Full name": "David Fullmer",
                "Guest's Email": "becomeseven808@gmail.com",
                "Website": "https://www.becomingseven.com",
            }
        ]
    )
    dataframe.to_excel(excel_path, index=False)

    result = service.import_guest_file(excel_path.name, excel_path.read_bytes())

    assert result["imported"] == 1
    imported_guest = service.list_guests()["guests"][0]
    assert imported_guest["full_name"] == "David Fullmer"
    assert imported_guest["email"] == "becomeseven808@gmail.com"


def test_web_service_can_import_episode_history_and_queue_csvs(temp_db):
    """Episode planning imports should normalize both released history and the unreleased queue."""
    service = GuestWebService(temp_db.db_path)
    released_csv = (
        "Name,Email,Website,Topic,Category,Interview Date,Release Date,Episode Number\n"
        "Amina Hart,amina@example.com,https://amina.example.com,Healing With Honesty,Personal Development,14/10/2024,07/01/2025,423\n"
    ).encode("utf-8")
    queue_csv = (
        " Names,Email,Website,Topic,Category,Interview Date,Riverside FM Status\n"
        "Jordan Rivers,jordan@example.com,https://jordan.example.com,Building Calm Under Pressure,Finance,11/03/2026,Processing\n"
    ).encode("utf-8")

    released_result = service.import_episode_file("MT Guest List - 2026.csv", released_csv)
    queue_result = service.import_episode_file("MT Guest List - Not Yet Released.csv", queue_csv)

    episodes = service.list_planning()["episodes"]

    assert released_result["imported"] == 1
    assert queue_result["imported"] == 1
    assert len(episodes) == 2
    released_episode = next(item for item in episodes if item["guest_name"] == "Amina Hart")
    queue_episode = next(item for item in episodes if item["guest_name"] == "Jordan Rivers")
    assert released_episode["release_status"] == "released"
    assert released_episode["legacy_episode_number"] == "423"
    assert released_episode["promotion_status"] == "released"
    assert queue_episode["source_type"] == "release_queue"
    assert queue_episode["production_status"] == "editing"
    assert queue_episode["promotion_status"] == "needs_assets"
    assert queue_episode["website"] == "https://jordan.example.com"


def test_web_service_imports_future_release_dates_as_scheduled(temp_db):
    """Imported archive rows with future release dates should stay scheduled, not released."""
    service = GuestWebService(temp_db.db_path)
    future_csv = (
        "Name,Email,Website,Topic,Category,Interview Date,Release Date,Episode Number\n"
        "Future Guest,future@example.com,https://future.example.com,The Next Chapter,Personal Development,14/10/2098,07/01/2099,999\n"
    ).encode("utf-8")

    result = service.import_episode_file("MT Guest List - 2099.csv", future_csv)
    episode = service.list_planning()["episodes"][0]

    assert result["imported"] == 1
    assert episode["release_status"] == "scheduled"
    assert episode["production_status"] == "ready"


def test_list_planning_normalizes_stale_future_release_states(temp_db):
    """Episodes already stored with future release dates should not remain marked as released."""
    service = GuestWebService(temp_db.db_path)
    temp_db.upsert_episode(
        {
            "guest_name": "Future Guest",
            "guest_email": "future@example.com",
            "episode_title": "The Next Chapter",
            "release_date": "2099-04-01",
            "release_status": "released",
            "production_status": "released",
        }
    )

    episode = service.list_planning()["episodes"][0]

    assert episode["release_status"] == "scheduled"
    assert episode["production_status"] == "ready"


def test_web_service_episode_import_ignores_blank_rows_and_headers(temp_db):
    """Episode planning imports should ignore empty rows and unnamed columns."""
    service = GuestWebService(temp_db.db_path)
    queue_csv = (
        "Names,Email,,Topic,Category,Interview Date,Riverside FM Status\n"
        "Jordan Rivers,jordan@example.com,,Building Calm Under Pressure,Finance,11/03/2026,Processing\n"
        ",,,,,,\n"
    ).encode("utf-8")

    result = service.import_episode_file("MT Guest List - Not Yet Released.csv", queue_csv)
    planning = service.list_planning()

    assert result["imported"] == 1
    assert result["updated"] == 0
    assert len(planning["episodes"]) == 1
    assert planning["episodes"][0]["guest_name"] == "Jordan Rivers"


def test_web_service_episode_import_reimport_updates_instead_of_creating_duplicates(temp_db):
    """Re-importing the same episode CSV should update existing rows, not flood the database."""
    service = GuestWebService(temp_db.db_path)
    released_csv = (
        "Name,Email,Website,Topic,Category,Interview Date,Release Date\n"
        "Amina Hart,amina@example.com,https://amina.example.com,Healing With Honesty,Personal Development,14/10/2024,07/01/2025\n"
    ).encode("utf-8")
    queue_csv = (
        "Names,Email,Website,Topic,Category,Interview Date,Riverside FM Status\n"
        "Jordan Rivers,jordan@example.com,https://jordan.example.com,Building Calm Under Pressure,Finance,11/03/2026,Processing\n"
    ).encode("utf-8")

    first_released = service.import_episode_file("MT Guest List - 2026.csv", released_csv)
    second_released = service.import_episode_file("MT Guest List - 2026.csv", released_csv)
    first_queue = service.import_episode_file("MT Guest List - Not Yet Released.csv", queue_csv)
    second_queue = service.import_episode_file("MT Guest List - Not Yet Released.csv", queue_csv)
    planning = service.list_planning()

    assert first_released["imported"] == 1
    assert second_released["imported"] == 0
    assert second_released["updated"] == 1
    assert first_queue["imported"] == 1
    assert second_queue["imported"] == 0
    assert second_queue["updated"] == 1
    assert len(planning["episodes"]) == 2


def test_web_service_can_export_guests_to_csv(temp_db):
    """Dashboard exports should return a CSV with the imported guest data."""
    service = GuestWebService(temp_db.db_path)
    service.create_guest(
        {
            "full_name": "Amina Hart",
            "email": "amina@example.com",
            "website": "https://amina.example.com",
            "background": "Author and speaker",
        }
    )

    exported_csv = service.export_guests_csv()

    assert "full_name,email,website" in exported_csv
    assert "Amina Hart,amina@example.com,https://amina.example.com" in exported_csv


def test_create_episode_with_release_date_defaults_to_scheduled(temp_db):
    """Saving a dated episode should automatically classify it as scheduled unless released explicitly."""
    service = GuestWebService(temp_db.db_path)

    episode = service.create_episode(
        {
            "guest_name": "Jordan Rivers",
            "guest_email": "jordan@example.com",
            "episode_title": "Building Calm Under Pressure",
            "release_date": "2026-04-14T17:00",
        }
    )

    assert episode["release_status"] == "scheduled"


def test_web_service_can_delete_interview_and_episode(temp_db):
    """Operations records should be removable through the web service."""
    service = GuestWebService(temp_db.db_path)
    interview = service.create_interview(
        {
            "guest_name": "Jordan Rivers",
            "guest_email": "jordan@example.com",
            "title": "Jordan Rivers and Tobi Ojekunle",
            "scheduled_for": "2026-04-08T17:00",
        }
    )
    episode = service.create_episode(
        {
            "guest_name": "Jordan Rivers",
            "guest_email": "jordan@example.com",
            "episode_title": "Healing Through Hard Seasons",
            "topic": "Healing",
            "interview_id": interview["id"],
        }
    )

    assert service.delete_episode(
        episode["id"], confirm_label="Healing Through Hard Seasons"
    ) == {"deleted": True, "id": episode["id"]}
    assert service.delete_interview(
        interview["id"], confirm_label="Jordan Rivers"
    ) == {"deleted": True, "id": interview["id"]}
    assert service.list_planning()["episodes"] == []
    assert service.list_operations()["interviews"] == []


def test_web_service_can_move_completed_interview_into_planning(temp_db):
    """A completed interview should hand off into planning without creating duplicates."""
    service = GuestWebService(temp_db.db_path)
    service.create_guest(
        {
            "full_name": "Jordan Rivers",
            "email": "jordan@example.com",
            "website": "https://jordan.example.com",
        }
    )
    interview = service.create_interview(
        {
            "guest_name": "Jordan Rivers",
            "guest_email": "jordan@example.com",
            "title": "Jordan Rivers and Tobi Ojekunle",
            "scheduled_for": "2026-04-08T17:00",
        }
    )

    created_episode = service.create_episode_from_interview(interview["id"])

    assert created_episode["interview_id"] == interview["id"]
    assert created_episode["guest_name"] == "Jordan Rivers"
    assert created_episode["guest_email"] == "jordan@example.com"
    assert created_episode["website"] == "https://jordan.example.com"
    assert created_episode["production_status"] == "recorded"
    assert created_episode["promotion_status"] == "needs_assets"
    assert created_episode["interview_date"] == "2026-04-08"
    assert created_episode["recording_date"] == "2026-04-08"

    refreshed_episode = service.create_episode_from_interview(interview["id"])

    planning = service.list_planning()
    operations = service.list_operations()

    assert refreshed_episode["id"] == created_episode["id"]
    assert len(planning["episodes"]) == 1
    assert operations["interviews"][0]["planning_episode_id"] == created_episode["id"]


def test_interview_to_planning_handoff_strips_host_name_from_guest(temp_db):
    """Interview handoff should keep only the guest name when the title includes the host."""
    service = GuestWebService(temp_db.db_path)
    interview = service.create_interview(
        {
            "guest_name": "Patrick Kamba and Tobi Ojekunle",
            "guest_email": "patrick@example.com",
            "title": "Patrick Kamba and Tobi Ojekunle",
            "scheduled_for": "2026-04-08T17:00",
        }
    )

    episode = service.create_episode_from_interview(interview["id"])

    assert episode["guest_name"] == "Patrick Kamba"


def test_interview_to_planning_handoff_keeps_multiple_guests_without_host(temp_db):
    """Interview handoff should preserve multiple guests while dropping the host."""
    service = GuestWebService(temp_db.db_path)
    interview = service.create_interview(
        {
            "guest_name": "Alice Smith, Bob Jones and Tobi Ojekunle",
            "guest_email": "alice@example.com",
            "title": "Alice Smith, Bob Jones and Tobi Ojekunle",
            "scheduled_for": "2026-04-08T17:00",
        }
    )

    episode = service.create_episode_from_interview(interview["id"])

    assert episode["guest_name"] == "Alice Smith & Bob Jones"


def test_release_recommendations_skip_already_scheduled_episodes(temp_db):
    """Scheduled episodes should not be re-recommended for the next open slot."""
    service = GuestWebService(temp_db.db_path)
    service.create_episode(
        {
            "guest_name": "Ready and Scheduled",
            "guest_email": "scheduled@example.com",
            "episode_title": "Already On The Calendar",
            "topic": "Already On The Calendar",
            "release_date": "2026-04-14T17:00",
            "release_status": "scheduled",
            "production_status": "ready",
            "promotion_status": "ready",
        }
    )
    service.create_episode(
        {
            "guest_name": "Needs A Slot",
            "guest_email": "queue@example.com",
            "episode_title": "Still Waiting",
            "topic": "Still Waiting",
            "production_status": "ready",
            "promotion_status": "ready",
        }
    )

    recommendations = service.list_planning()["recommendations"]

    assert len(recommendations) == 1
    assert recommendations[0]["guest_name"] == "Needs A Slot"


def test_planning_payload_includes_grounded_editorial_assist(temp_db):
    """Planning payload should expose deterministic readiness and copy/title suggestions."""
    service = GuestWebService(temp_db.db_path)
    service.create_episode(
        {
            "guest_name": "Jordan Rivers",
            "guest_email": "jordan@example.com",
            "website": "https://jordan.example.com",
            "episode_title": "Building Calm Under Pressure",
            "topic": "Building Calm Under Pressure",
            "category": "Finance",
            "production_status": "ready",
            "promotion_status": "ready",
            "show_notes_url": "https://mirrortalkpodcast.com/episodes/building-calm",
            "release_files_url": "https://downloads.mirrortalkpodcast.com/building-calm",
            "transcript_text": "We explored how calm under pressure begins with honest self-awareness. Jordan reflected on building better financial boundaries through practice.",
        }
    )

    planning = service.list_planning()
    episode = planning["episodes"][0]
    recommendation = planning["recommendations"][0]

    assert episode["promotion_readiness"]["score"] >= 70
    assert "summary" in episode["copy_assist"]
    assert episode["copy_assist"]["show_notes_intro"]
    assert recommendation["promotion_readiness"]["score"] >= 70


def test_planning_payload_includes_outreach_system_and_episode_summary(temp_db):
    """Planning should expose the weekly outreach system and episode-level checklist summary."""
    service = GuestWebService(temp_db.db_path)
    service.create_episode(
        {
            "guest_name": "Jordan Rivers",
            "guest_email": "jordan@example.com",
            "episode_title": "Building Calm Under Pressure",
            "release_date": "2026-04-07T17:00",
            "release_status": "scheduled",
            "outreach_plan": {
                "monday_preparation": True,
                "tuesday_launch": True,
            },
        }
    )

    planning = service.list_planning()
    episode = planning["episodes"][0]

    assert planning["weekly_system"]["steps"][0]["key"] == "monday_preparation"
    assert planning["weekly_system"]["principles"]
    assert episode["outreach_plan"]["monday_preparation"] is True
    assert episode["outreach_summary"]["completed_count"] == 2
    assert "Next outreach step" in episode["outreach_summary"]["next_step"]


def test_create_episode_prefills_priority_and_legacy_episode_number(temp_db):
    """Planning should auto-fill a sensible next legacy number and priority when omitted."""
    service = GuestWebService(temp_db.db_path)
    service.create_episode(
        {
            "guest_name": "Jordan Rivers",
            "episode_title": "Episode Forty One",
            "legacy_episode_number": "41",
            "priority_score": 8,
            "release_status": "scheduled",
            "production_status": "ready",
            "promotion_status": "ready",
        }
    )

    created = service.create_episode(
        {
            "guest_name": "Amara Stone",
            "episode_title": "A New Beginning",
            "release_status": "unplanned",
            "production_status": "recorded",
            "promotion_status": "needs_assets",
        }
    )

    assert created["legacy_episode_number"] == "42"
    assert float(created["priority_score"]) == 5.0


def test_create_episode_clamps_priority_score_to_editable_range(temp_db):
    """Editable episode priority should stay inside the planning form's 0-10 range."""
    service = GuestWebService(temp_db.db_path)

    created = service.create_episode(
        {
            "guest_name": "Spencer Vann",
            "episode_title": "Spencer Vann",
            "priority_score": 104,
            "release_status": "unplanned",
            "production_status": "ready",
            "promotion_status": "ready",
        }
    )

    assert float(created["priority_score"]) == 10.0


def test_recommendations_skip_release_dates_already_reserved_by_scheduled_episodes(temp_db):
    """Scheduled release dates should push later recommendations onto the next free slot."""
    service = GuestWebService(temp_db.db_path)
    service.create_episode(
        {
            "guest_name": "Already Scheduled",
            "guest_email": "scheduled@example.com",
            "episode_title": "Already Scheduled",
            "topic": "Already Scheduled",
            "category": "Faith",
            "release_date": "2026-04-14 17:00:00",
            "release_status": "scheduled",
            "production_status": "ready",
            "promotion_status": "ready",
        }
    )
    service.create_episode(
        {
            "guest_name": "Jordan Rivers",
            "guest_email": "jordan@example.com",
            "episode_title": "Healing Through Honest Conversations",
            "topic": "Healing Through Honest Conversations",
            "category": "Mental Health",
            "interview_date": "2026-03-01",
            "release_status": "unplanned",
            "production_status": "ready",
            "promotion_status": "ready",
        }
    )
    service.create_episode(
        {
            "guest_name": "Amara Stone",
            "guest_email": "amara@example.com",
            "episode_title": "Renewal After Hard Seasons",
            "topic": "Renewal After Hard Seasons",
            "category": "Faith",
            "interview_date": "2026-03-05",
            "release_status": "unplanned",
            "production_status": "ready",
            "promotion_status": "ready",
        }
    )

    planning = service.list_planning()

    recommended_dates = [item["recommended_release_date"] for item in planning["recommendations"][:2]]
    assert "2026-04-14 17:00:00" not in recommended_dates
    assert recommended_dates[0] == "2026-04-21 17:00:00"


def test_released_episode_readiness_does_not_show_early_stage_blockers(temp_db):
    """Released episodes should not be described as too early in production."""
    service = GuestWebService(temp_db.db_path)
    service.create_episode(
        {
            "guest_name": "Jordan Rivers",
            "guest_email": "jordan@example.com",
            "episode_title": "Already Published",
            "topic": "Already Published",
            "release_status": "released",
            "production_status": "released",
            "promotion_status": "released",
            "show_notes_url": "https://mirrortalkpodcast.com/episodes/already-published",
        }
    )

    episode = service.list_planning()["episodes"][0]

    assert episode["promotion_readiness"]["label"] == "Released"
    assert "production stage is still too early" not in episode["promotion_readiness"]["blockers"]


def test_list_planning_normalizes_released_episode_production_state(temp_db):
    """Released episodes should display as released, not ready, in planning."""
    service = GuestWebService(temp_db.db_path)
    service.create_episode(
        {
            "guest_name": "Jordan Rivers",
            "guest_email": "jordan@example.com",
            "episode_title": "A Meaningful Conversation",
            "release_date": "2026-03-31T17:00",
            "release_status": "released",
            "production_status": "ready",
        }
    )

    episode = service.list_planning()["episodes"][0]

    assert episode["release_status"] == "released"
    assert episode["production_status"] == "released"


def test_copy_assist_does_not_treat_guest_name_as_topic(temp_db):
    """Copy assist should not invent a fake topic by echoing the guest name."""
    service = GuestWebService(temp_db.db_path)
    service.create_episode(
        {
            "guest_name": "Magic Barclay",
            "guest_email": "magic@example.com",
            "episode_title": "Magic Barclay",
            "topic": "",
            "category": "General Health",
            "production_status": "ready",
            "promotion_status": "ready",
        }
    )

    episode = service.list_planning()["episodes"][0]
    copy_assist = episode["copy_assist"]

    assert "about magic barclay" not in copy_assist["summary"].lower()
    assert "explore magic barclay" not in copy_assist["social_caption"].lower()
    assert "for magic barclay" not in copy_assist["newsletter_blurb"].lower()


def test_list_planning_reports_ask_sync_configuration(monkeypatch, temp_db):
    """Planning payload should signal when Ask Mirror Talk sync is configured."""
    monkeypatch.setenv(ASK_MIRROR_TALK_BASE_URL_ENV_VAR, "https://ask-mirror-talk.example.com")
    monkeypatch.setenv(ASK_MIRROR_TALK_USERNAME_ENV_VAR, "admin")
    monkeypatch.setenv(ASK_MIRROR_TALK_PASSWORD_ENV_VAR, "secret")

    service = GuestWebService(temp_db.db_path)

    assert service.list_planning()["ask_sync_enabled"] is True


def test_web_service_can_sync_matching_transcripts_from_ask_mirror_talk(monkeypatch, temp_db):
    """Planning should be able to enrich matching episodes from Ask Mirror Talk."""

    class StubAskMirrorTalkClient:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def export_episodes(self, **kwargs):
            assert kwargs["include_transcript"] is True
            return [
                {
                    "title": "Building Calm Under Pressure",
                    "transcript_text": "We explored how calm grows through honest practice.",
                },
                {
                    "title": "Another Episode",
                    "transcript_text": "Unused transcript.",
                },
            ]

    monkeypatch.setattr("guest_database_manager.web_interface.AskMirrorTalkClient", StubAskMirrorTalkClient)
    monkeypatch.setenv(ASK_MIRROR_TALK_BASE_URL_ENV_VAR, "https://ask-mirror-talk.example.com")
    monkeypatch.setenv(ASK_MIRROR_TALK_USERNAME_ENV_VAR, "admin")
    monkeypatch.setenv(ASK_MIRROR_TALK_PASSWORD_ENV_VAR, "secret")

    service = GuestWebService(temp_db.db_path)
    episode = service.create_episode(
        {
            "guest_name": "Jordan Rivers",
            "guest_email": "jordan@example.com",
            "episode_title": "Building Calm Under Pressure",
            "topic": "Building Calm Under Pressure",
        }
    )

    result = service.sync_ask_mirror_talk_transcripts()
    updated_episode = service.list_planning()["episodes"][0]

    assert result["updated"] == 1
    assert result["matched"] == 1
    assert result["matched_by_title"] == 1
    assert updated_episode["id"] == episode["id"]
    assert updated_episode["transcript_text"] == "We explored how calm grows through honest practice."


def test_web_service_can_match_ask_episode_by_guest_name_and_update_title(monkeypatch, temp_db):
    """Planning sync should update the local episode title when Ask Mirror Talk has the published version."""

    class StubAskMirrorTalkClient:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def export_episodes(self, **kwargs):
            return [
                {
                    "id": 77,
                    "title": "Jordan Rivers on Building Calm Under Pressure",
                    "description": "Jordan Rivers joins Mirror Talk for a conversation about calm under pressure and financial resilience.",
                    "transcript_text": "Jordan explains how honest practice helps people stay calm under pressure.",
                }
            ]

    monkeypatch.setattr("guest_database_manager.web_interface.AskMirrorTalkClient", StubAskMirrorTalkClient)
    monkeypatch.setenv(ASK_MIRROR_TALK_BASE_URL_ENV_VAR, "https://ask-mirror-talk.example.com")
    monkeypatch.setenv(ASK_MIRROR_TALK_USERNAME_ENV_VAR, "admin")
    monkeypatch.setenv(ASK_MIRROR_TALK_PASSWORD_ENV_VAR, "secret")

    service = GuestWebService(temp_db.db_path)
    service.create_episode(
        {
            "guest_name": "Jordan Rivers",
            "guest_email": "jordan@example.com",
            "episode_title": "Calm Under Pressure",
            "topic": "Building Calm Under Pressure",
        }
    )

    result = service.sync_ask_mirror_talk_transcripts()
    updated_episode = service.list_planning()["episodes"][0]

    assert result["updated"] == 1
    assert result["matched"] == 1
    assert result["matched_by_guest"] == 1
    assert result["updated_transcript"] == 1
    assert result["updated_title_only"] == 0
    assert updated_episode["episode_title"] == "Jordan Rivers on Building Calm Under Pressure"
    assert updated_episode["transcript_text"] == "Jordan explains how honest practice helps people stay calm under pressure."


def test_web_service_can_use_date_proximity_for_guest_match(monkeypatch, temp_db):
    """Release-date proximity should strengthen an otherwise weak guest match."""

    class StubAskMirrorTalkClient:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def export_episodes(self, **kwargs):
            return [
                {
                    "id": 51,
                    "title": "A Different Published Title",
                    "description": "A thoughtful Mirror Talk conversation with Jordan Rivers.",
                    "published_at": "2026-04-01T03:00:00",
                    "transcript_text": "Jordan reflects on healing and resilience with practical honesty.",
                }
            ]

    monkeypatch.setattr("guest_database_manager.web_interface.AskMirrorTalkClient", StubAskMirrorTalkClient)
    monkeypatch.setenv(ASK_MIRROR_TALK_BASE_URL_ENV_VAR, "https://ask-mirror-talk.example.com")
    monkeypatch.setenv(ASK_MIRROR_TALK_USERNAME_ENV_VAR, "admin")
    monkeypatch.setenv(ASK_MIRROR_TALK_PASSWORD_ENV_VAR, "secret")

    service = GuestWebService(temp_db.db_path)
    service.create_episode(
        {
            "guest_name": "Jordan Rivers",
            "guest_email": "jordan@example.com",
            "episode_title": "Internal Working Title",
            "topic": "Healing and Resilience",
            "release_date": "2026-04-01T17:00",
        }
    )

    result = service.sync_ask_mirror_talk_transcripts()
    updated_episode = service.list_planning()["episodes"][0]

    assert result["matched"] == 1
    assert result["matched_by_guest"] == 1
    assert updated_episode["episode_title"] == "A Different Published Title"


def test_web_service_can_match_by_first_or_last_name_with_date_anchor(monkeypatch, temp_db):
    """Partial guest-name matches should only work when another signal makes them safe."""

    class StubAskMirrorTalkClient:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def export_episodes(self, **kwargs):
            return [
                {
                    "id": 61,
                    "title": "Volk on Grief, Healing and Spiritual Solace",
                    "description": "A moving Mirror Talk conversation about grief and healing.",
                    "published_at": "2026-04-02T03:00:00",
                    "transcript_text": "Catia reflects on healing through grief and finding spiritual solace.",
                }
            ]

    monkeypatch.setattr("guest_database_manager.web_interface.AskMirrorTalkClient", StubAskMirrorTalkClient)
    monkeypatch.setenv(ASK_MIRROR_TALK_BASE_URL_ENV_VAR, "https://ask-mirror-talk.example.com")
    monkeypatch.setenv(ASK_MIRROR_TALK_USERNAME_ENV_VAR, "admin")
    monkeypatch.setenv(ASK_MIRROR_TALK_PASSWORD_ENV_VAR, "secret")

    service = GuestWebService(temp_db.db_path)
    service.create_episode(
        {
            "guest_name": "Victoria Volk",
            "guest_email": "victoria@example.com",
            "episode_title": "Grief and Healing",
            "topic": "Grief and Healing",
            "release_date": "2026-04-01T17:00",
        }
    )

    result = service.sync_ask_mirror_talk_transcripts()
    updated_episode = service.list_planning()["episodes"][0]

    assert result["matched"] == 1
    assert result["matched_by_guest"] == 1
    assert updated_episode["episode_title"] == "Volk on Grief, Healing and Spiritual Solace"


def test_web_service_reports_ambiguous_ask_matches(monkeypatch, temp_db):
    """Ambiguous Ask transcript matches should be surfaced with the top candidate details."""

    class StubAskMirrorTalkClient:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def export_episodes(self, **kwargs):
            return [
                {
                    "id": 81,
                    "title": "Jordan Rivers on Building Calm",
                    "description": "Jordan Rivers joins Mirror Talk for a calm conversation about resilience.",
                    "published_at": "2026-04-01T03:00:00",
                    "transcript_text": "Jordan discusses calm and resilience.",
                },
                {
                    "id": 82,
                    "title": "Jordan Rivers on Building Calm and Courage",
                    "description": "Jordan Rivers joins Mirror Talk for a conversation about courage and calm.",
                    "published_at": "2026-04-03T03:00:00",
                    "transcript_text": "Jordan discusses courage and calm.",
                },
            ]

    monkeypatch.setattr("guest_database_manager.web_interface.AskMirrorTalkClient", StubAskMirrorTalkClient)
    monkeypatch.setenv(ASK_MIRROR_TALK_BASE_URL_ENV_VAR, "https://ask-mirror-talk.example.com")
    monkeypatch.setenv(ASK_MIRROR_TALK_USERNAME_ENV_VAR, "admin")
    monkeypatch.setenv(ASK_MIRROR_TALK_PASSWORD_ENV_VAR, "secret")

    service = GuestWebService(temp_db.db_path)
    service.create_episode(
        {
            "guest_name": "Jordan Rivers",
            "guest_email": "jordan@example.com",
            "episode_title": "Internal Calm Working Title",
            "topic": "Calm and Courage",
            "release_date": "2026-04-02T17:00",
        }
    )

    result = service.sync_ask_mirror_talk_transcripts()

    assert result["matched"] == 0
    assert result["skipped_ambiguous"] == 1
    assert len(result["ambiguous_matches"]) == 1
    ambiguous = result["ambiguous_matches"][0]
    assert ambiguous["local_episode"]["guest_name"] == "Jordan Rivers"
    assert len(ambiguous["candidates"]) == 2
    assert {candidate["id"] for candidate in ambiguous["candidates"]} == {81, 82}
    assert all(candidate["method"] == "guest_title" for candidate in ambiguous["candidates"])


def test_web_service_does_not_match_different_guest_on_shared_first_name(monkeypatch, temp_db):
    """Shared first names alone should not let Ask sync overwrite the wrong episode."""

    class StubAskMirrorTalkClient:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def export_episodes(self, **kwargs):
            return [
                {
                    "id": 91,
                    "title": "John Patrick Morgan: Becoming The Champion of Your Life - Overcoming The Fear of Taking Risks, Anxiety And The Lack of Drive",
                    "description": "A published Mirror Talk episode with John Patrick Morgan.",
                    "published_at": "2026-03-20T17:00:00",
                    "transcript_text": "John Patrick Morgan shares his story.",
                }
            ]

    monkeypatch.setattr("guest_database_manager.web_interface.AskMirrorTalkClient", StubAskMirrorTalkClient)
    monkeypatch.setenv(ASK_MIRROR_TALK_BASE_URL_ENV_VAR, "https://ask-mirror-talk.example.com")
    monkeypatch.setenv(ASK_MIRROR_TALK_USERNAME_ENV_VAR, "admin")
    monkeypatch.setenv(ASK_MIRROR_TALK_PASSWORD_ENV_VAR, "secret")

    service = GuestWebService(temp_db.db_path)
    service.create_episode(
        {
            "guest_name": "Patrick Kamba",
            "guest_email": "patrick@example.com",
            "episode_title": "A Different Unreleased Episode",
            "topic": "Purpose and Drive",
            "release_status": "unplanned",
        }
    )

    result = service.sync_ask_mirror_talk_transcripts()
    episode = service.list_planning()["episodes"][0]

    assert result["matched"] == 0
    assert result["updated"] == 0
    assert episode["episode_title"] == "A Different Unreleased Episode"
    assert not episode["transcript_text"]


def test_web_service_can_export_selected_episode_fields_as_csv(temp_db):
    """Flexible export should allow narrow CSV extracts for episode planning."""
    service = GuestWebService(temp_db.db_path)
    service.create_episode(
        {
            "guest_name": "Amina Hart",
            "guest_email": "amina@example.com",
            "episode_title": "Healing With Honesty",
            "topic": "Healing With Honesty",
            "category": "Personal Development",
            "promotion_status": "ready",
        }
    )

    payload, filename, content_type = service.export_records(
        "episodes",
        ["guest_name", "guest_email"],
        "csv",
    )

    assert filename == "mirror-talk-episodes.csv"
    assert content_type.startswith("text/csv")
    exported_csv = payload.decode("utf-8")
    assert "guest_name,guest_email" in exported_csv
    assert "Amina Hart,amina@example.com" in exported_csv
    assert "category" not in exported_csv


def test_web_service_can_export_selected_episode_fields_as_excel(temp_db):
    """Flexible export should support Excel downloads with selected fields only."""
    service = GuestWebService(temp_db.db_path)
    service.create_episode(
        {
            "guest_name": "Jordan Rivers",
            "guest_email": "jordan@example.com",
            "episode_title": "Building Calm Under Pressure",
            "topic": "Building Calm Under Pressure",
            "category": "Finance",
            "promotion_status": "ready",
        }
    )

    payload, filename, content_type = service.export_records(
        "episodes",
        ["guest_name", "promotion_status"],
        "xlsx",
    )

    workbook = load_workbook(filename=BytesIO(payload))
    worksheet = workbook.active

    assert filename == "mirror-talk-episodes.xlsx"
    assert content_type == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    assert worksheet["A1"].value == "guest_name"
    assert worksheet["B1"].value == "promotion_status"
    assert worksheet["A2"].value == "Jordan Rivers"
    assert worksheet["B2"].value == "ready"


def test_web_service_can_send_acceptance_email(monkeypatch, temp_db):
    """Hosted dashboard should be able to send an approval email and persist acceptance."""

    class StubEmailManager:
        def __init__(self):
            self.configured = False

        def configure_smtp(self, **kwargs):
            self.configured = True

        def is_configured(self):
            return self.configured

        def send_acceptance_email(self, guest_name, to_email, custom_message="", booking_url=""):
            assert guest_name == "Amina Hart"
            assert to_email == "amina@example.com"
            assert custom_message == "Welcome aboard"
            assert booking_url
            return True

        def send_rejection_email(self, guest_name, to_email, custom_message=""):
            raise AssertionError("Rejection email should not be called")

    monkeypatch.setattr("guest_database_manager.web_interface.EmailManager", StubEmailManager)
    monkeypatch.setenv(EMAIL_SMTP_SERVER_ENV_VAR, "smtp.example.com")
    monkeypatch.setenv(EMAIL_SMTP_PORT_ENV_VAR, "587")
    monkeypatch.setenv(EMAIL_USERNAME_ENV_VAR, "mirror@example.com")
    monkeypatch.setenv(EMAIL_PASSWORD_ENV_VAR, "top-secret")
    monkeypatch.setenv(EMAIL_FROM_ENV_VAR, "mirror@example.com")
    monkeypatch.setenv(EMAIL_FROM_NAME_ENV_VAR, "Mirror Talk Podcast")

    service = GuestWebService(temp_db.db_path)
    guest = service.create_guest({"full_name": "Amina Hart", "email": "amina@example.com"})

    updated_guest = service.send_guest_decision_email(guest["id"], "accepted", "Welcome aboard")

    assert updated_guest["email_status"] == "accepted"


def test_list_guests_includes_decision_support_and_stats(temp_db):
    """The dashboard payload should include explainable guest recommendations."""
    service = GuestWebService(temp_db.db_path)
    service.create_guest(
        {
            "full_name": "Amina Hart",
            "email": "amina@example.com",
            "website": "https://amina.example.com",
            "background": "I help people heal, grow, and rebuild meaning after difficult seasons through honest storytelling and practical reflection.",
            "profession": "I work as a coach and speaker focused on healing, resilience, and emotional honesty.",
            "passionate_topics": "Healing, faith, identity, purpose, relationships, and resilient growth.",
            "message": "I want listeners to leave feeling hopeful and more courageous about their own next steps.",
            "additional_info": "I love meaningful conversations that are honest, reflective, and grounded in lived experience.",
            "has_social_media": "Yes",
        }
    )
    service.create_guest(
        {
            "full_name": "Promo Person",
            "background": "SEO backlink opportunity.",
            "profession": "Growth hacker",
            "passionate_topics": "Lead generation and sales funnel wins.",
        }
    )

    payload = service.list_guests()

    assert "recommendation_stats" in payload
    assert payload["recommendation_stats"]["strong_fits"] >= 1
    assert payload["recommendation_stats"]["high_risk"] >= 1
    first_guest = next(guest for guest in payload["guests"] if guest["full_name"] == "Amina Hart")
    assert first_guest["decision_support"]["score"] >= 58
    assert first_guest["decision_support"]["suggested_decision"] == "approve"
    assert first_guest["decision_support"]["signals"]


def test_list_guests_includes_promotion_profile(temp_db):
    """Dashboard guests should include a promotion-profile summary for outreach readiness."""
    service = GuestWebService(temp_db.db_path)
    service.create_guest(
        {
            "full_name": "Jordan Rivers",
            "email": "jordan@example.com",
            "website": "https://jordan.example.com",
            "social_handles": "Instagram: jordanrivers",
            "background": "Jordan helps people handle pressure with calm leadership and grounded habits.",
            "profession": "Coach",
        }
    )

    guest = service.list_guests()["guests"][0]

    assert guest["promotion_profile"]["score"] >= 80
    assert guest["promotion_profile"]["label"] == "Promotion-ready guest profile"
    assert guest["promotion_profile"]["strengths"]


def test_guest_decision_support_can_reference_previously_accepted_guests(temp_db):
    """Guest review assist should use Mirror Talk's own accepted history as context."""
    service = GuestWebService(temp_db.db_path)
    accepted = service.create_guest(
        {
            "full_name": "Accepted Reference",
            "email": "accepted@example.com",
            "background": "I speak about healing, purpose, resilience, and identity after hard life transitions.",
            "profession": "Coach and speaker focused on healing and resilience.",
            "passionate_topics": "Healing, identity, purpose, resilience.",
            "message": "I want listeners to leave with more hope and courage.",
        }
    )
    service.update_guest_status(accepted["id"], "accepted")
    service.create_guest(
        {
            "full_name": "New Similar Guest",
            "email": "new@example.com",
            "background": "My work focuses on healing, resilience, and identity after difficult seasons.",
            "profession": "Speaker focused on healing and personal growth.",
            "passionate_topics": "Healing, resilience, identity, and purpose.",
            "message": "I want listeners to leave feeling hopeful.",
        }
    )

    payload = service.list_guests()
    new_guest = next(guest for guest in payload["guests"] if guest["full_name"] == "New Similar Guest")

    assert "Accepted Reference" in new_guest["decision_support"]["accepted_guest_matches"]


def test_guest_decision_support_flags_worldview_fit_cautions(temp_db):
    """AI review assist should flag possible worldview mismatch without auto-deciding for the user."""
    service = GuestWebService(temp_db.db_path)
    service.create_guest(
        {
            "full_name": "Worldview Tension Guest",
            "email": "worldview@example.com",
            "background": "I help people find success through manifestation, spiritual energy, and intuitive guidance.",
            "profession": "Coach and guide",
            "passionate_topics": "Manifestation, tarot, psychic intuition, and energetic abundance.",
            "message": "I want listeners to trust manifestation fully.",
            "alignment": "No",
            "faith": "Yes — I teach a new age spiritual path.",
        }
    )

    payload = service.list_guests()
    guest = next(item for item in payload["guests"] if item["full_name"] == "Worldview Tension Guest")

    cautions = " ".join(guest["decision_support"]["cautions"]).lower()
    signals = [signal["label"] for signal in guest["decision_support"]["signals"]]

    assert "worldview" in cautions or "faith" in cautions
    assert "Worldview Caution" in signals


def test_guest_decision_support_does_not_penalize_grounded_faith_language(temp_db):
    """Christian or faith-sensitive language should not be treated as a caution by itself."""
    service = GuestWebService(temp_db.db_path)
    service.create_guest(
        {
            "full_name": "Faith Aligned Guest",
            "email": "faith@example.com",
            "background": "I speak about healing, Christian hope, honesty, and rebuilding life after difficult seasons.",
            "profession": "Speaker and mentor",
            "passionate_topics": "Faith, healing, resilience, purpose, and emotional honesty.",
            "message": "I want listeners to leave with more hope.",
            "alignment": "Yes — my perspective fits soulful conversations well.",
            "faith": "Yes — I am a Christian and my faith shapes how I serve people.",
        }
    )

    payload = service.list_guests()
    guest = next(item for item in payload["guests"] if item["full_name"] == "Faith Aligned Guest")

    cautions = " ".join(guest["decision_support"]["cautions"]).lower()

    assert "worldview" not in cautions


def test_web_service_prefers_resend_for_hosted_email(monkeypatch, temp_db):
    """Hosted dashboard should configure Resend when its API key is present."""

    class StubEmailManager:
        def __init__(self):
            self.configured = False
            self.last_error = ""
            self.resend_used = False

        def configure_resend(self, **kwargs):
            self.configured = True
            self.resend_used = True
            self.from_email = kwargs["from_email"]
            self.cc_email = kwargs["cc_email"]

        def configure_smtp(self, **kwargs):
            raise AssertionError("SMTP should not be configured when Resend is available")

        def is_configured(self):
            return self.configured

    monkeypatch.setattr("guest_database_manager.web_interface.EmailManager", StubEmailManager)
    monkeypatch.setenv(EMAIL_RESEND_API_KEY_ENV_VAR, "re_test_123")
    monkeypatch.setenv(EMAIL_FROM_ENV_VAR, "onboarding@updates.mirrortalkpodcast.com")
    monkeypatch.setenv(EMAIL_FROM_NAME_ENV_VAR, "Mirror Talk Podcast")
    monkeypatch.setenv(EMAIL_CC_ENV_VAR, "podcast.mirrortalk@gmail.com")

    service = GuestWebService(temp_db.db_path)

    assert service.list_guests()["email_enabled"] is True


def test_web_service_passes_cc_email_to_smtp(monkeypatch, temp_db):
    """Hosted dashboard should pass the CC address into SMTP config."""

    class StubEmailManager:
        def __init__(self):
            self.configured = False
            self.last_error = ""
            self.cc_email = None

        def configure_smtp(self, **kwargs):
            self.configured = True
            self.cc_email = kwargs["cc_email"]

        def is_configured(self):
            return self.configured

    monkeypatch.setattr("guest_database_manager.web_interface.EmailManager", StubEmailManager)
    monkeypatch.setenv(EMAIL_SMTP_SERVER_ENV_VAR, "smtp.example.com")
    monkeypatch.setenv(EMAIL_SMTP_PORT_ENV_VAR, "587")
    monkeypatch.setenv(EMAIL_USERNAME_ENV_VAR, "mirror@example.com")
    monkeypatch.setenv(EMAIL_PASSWORD_ENV_VAR, "top-secret")
    monkeypatch.setenv(EMAIL_FROM_ENV_VAR, "mirror@example.com")
    monkeypatch.setenv(EMAIL_FROM_NAME_ENV_VAR, "Mirror Talk Podcast")
    monkeypatch.setenv(EMAIL_CC_ENV_VAR, "podcast.mirrortalk@gmail.com")

    service = GuestWebService(temp_db.db_path)

    assert service._build_email_manager().cc_email == "podcast.mirrortalk@gmail.com"


def test_web_service_can_return_email_template(monkeypatch, temp_db):
    """Dashboard should be able to fetch editable approval/decline templates."""

    class StubEmailManager:
        def __init__(self):
            self.configured = False

        def configure_smtp(self, **kwargs):
            self.configured = True

        def is_configured(self):
            return self.configured

        def get_acceptance_template(self, guest_name, custom_message="", booking_url=""):
            assert guest_name == "Amina Hart"
            assert booking_url
            return {"subject": "Accepted", "body": "Welcome to Mirror Talk"}

        def get_rejection_template(self, guest_name, custom_message=""):
            assert guest_name == "Amina Hart"
            return {"subject": "Declined", "body": "Thank you for applying"}

    monkeypatch.setattr("guest_database_manager.web_interface.EmailManager", StubEmailManager)
    service = GuestWebService(temp_db.db_path)
    guest = service.create_guest({"full_name": "Amina Hart", "email": "amina@example.com"})

    acceptance_template = service.get_guest_decision_email_template(guest["id"], "accepted")
    rejection_template = service.get_guest_decision_email_template(guest["id"], "rejected")

    assert acceptance_template["subject"] == "Accepted"
    assert rejection_template["subject"] == "Declined"


def test_acceptance_template_uses_guest_booking_link(monkeypatch, temp_db):
    """Accepted-guest email previews should include the guest-specific booking link."""

    class StubEmailManager:
        def __init__(self):
            self.configured = False

        def configure_smtp(self, **kwargs):
            self.configured = True

        def is_configured(self):
            return self.configured

        def get_acceptance_template(self, guest_name, custom_message="", booking_url=""):
            return {
                "subject": "Accepted",
                "body": f"{guest_name} -> {booking_url}",
            }

        def get_rejection_template(self, guest_name, custom_message=""):
            return {"subject": "Declined", "body": "No"}

    monkeypatch.setattr("guest_database_manager.web_interface.EmailManager", StubEmailManager)
    service = GuestWebService(temp_db.db_path)
    guest = service.create_guest({"full_name": "Amina Hart", "email": "amina@example.com"})

    template = service.get_guest_decision_email_template(guest["id"], "accepted")

    assert "token=" in template["body"]
    saved_guest = service.database.get_guest_by_id(guest["id"])
    assert saved_guest["booking_token"]


def test_public_booking_context_and_slots_for_accepted_guest(monkeypatch, temp_db):
    """Accepted guests should receive a tokenized booking page with available slots."""
    service = GuestWebService(temp_db.db_path)
    guest = service.create_guest({"full_name": "Jordan Rivers", "email": "jordan@example.com"})
    service.update_guest_status(guest["id"], "accepted")
    token = service._ensure_guest_booking_token(guest["id"])

    monkeypatch.setattr(GuestWebService, "_build_google_calendar_client", lambda self: None)
    monkeypatch.setattr(GuestWebService, "_booking_days_ahead", staticmethod(lambda: 2))
    monkeypatch.setattr(GuestWebService, "_booking_min_notice_hours", staticmethod(lambda: 0))
    monkeypatch.setattr(GuestWebService, "_booking_slot_weekdays", staticmethod(lambda: tuple(range(7))))

    tz_name = service._booking_timezone_name()
    tz_obj = ZoneInfo(tz_name)
    next_slot = (datetime.now(tz_obj) + timedelta(hours=2)).replace(minute=0, second=0, microsecond=0)
    monkeypatch.setattr(GuestWebService, "_booking_slot_times", staticmethod(lambda: (next_slot.strftime("%H:%M"),)))

    context = service.get_public_booking_context(token)
    availability = service.list_public_booking_slots(token, limit=5)

    assert context["guest_name"] == "Jordan Rivers"
    assert context["existing_booking"] is None
    assert availability["slots"]
    assert availability["slots"][0]["timezone"] == tz_name


def test_public_booking_slots_include_month_window_metadata(monkeypatch, temp_db):
    """Booking availability should expose the configured month window for the guest-facing calendar."""
    service = GuestWebService(temp_db.db_path)
    guest = service.create_guest({"full_name": "Jordan Rivers", "email": "jordan@example.com"})
    service.update_guest_status(guest["id"], "accepted")
    token = service._ensure_guest_booking_token(guest["id"])

    monkeypatch.setenv(BOOKING_MONTHS_AHEAD_ENV_VAR, "4")
    monkeypatch.setattr(GuestWebService, "_build_google_calendar_client", lambda self: None)
    monkeypatch.setattr(GuestWebService, "_booking_min_notice_hours", staticmethod(lambda: 0))
    monkeypatch.setattr(GuestWebService, "_booking_slot_weekdays", staticmethod(lambda: tuple(range(7))))

    tz_obj = ZoneInfo(service._booking_timezone_name())
    next_slot = (datetime.now(tz_obj) + timedelta(hours=2)).replace(minute=0, second=0, microsecond=0)
    monkeypatch.setattr(GuestWebService, "_booking_slot_times", staticmethod(lambda: (next_slot.strftime("%H:%M"),)))

    availability = service.list_public_booking_slots(token, limit=5)

    assert availability["booking_window"]["months_ahead"] == 4
    assert availability["booking_window"]["days_ahead"] >= 120


def test_booking_slot_buffer_only_blocks_nearby_conflicts(monkeypatch, temp_db):
    """Availability should only be blocked when an event overlaps the configured slot plus buffer."""
    service = GuestWebService(temp_db.db_path)
    guest = service.create_guest({"full_name": "Jordan Rivers", "email": "jordan@example.com"})
    service.update_guest_status(guest["id"], "accepted")
    token = service._ensure_guest_booking_token(guest["id"])

    monkeypatch.setattr(GuestWebService, "_build_google_calendar_client", lambda self: None)
    monkeypatch.setattr(GuestWebService, "_booking_days_ahead", staticmethod(lambda: 1))
    monkeypatch.setattr(GuestWebService, "_booking_min_notice_hours", staticmethod(lambda: 0))
    monkeypatch.setattr(GuestWebService, "_booking_slot_weekdays", staticmethod(lambda: tuple(range(7))))
    monkeypatch.setattr(GuestWebService, "_booking_slot_times", staticmethod(lambda: ("10:00", "17:00")))
    monkeypatch.setattr(GuestWebService, "_booking_buffer_minutes", staticmethod(lambda: 15))

    tz_name = service._booking_timezone_name()
    tz_obj = ZoneInfo(tz_name)
    candidate_day = (datetime.now(tz_obj) + timedelta(days=1)).date()
    blocked_start = datetime(candidate_day.year, candidate_day.month, candidate_day.day, 9, 50, tzinfo=tz_obj)
    safe_start = datetime(candidate_day.year, candidate_day.month, candidate_day.day, 13, 0, tzinfo=tz_obj)

    service.create_interview(
        {
            "guest_name": "Already Busy",
            "guest_email": "busy@example.com",
            "title": "Busy slot",
            "scheduled_for": blocked_start.astimezone(timezone.utc).isoformat(),
            "timezone": tz_name,
        }
    )
    service.create_interview(
        {
            "guest_name": "Later Meeting",
            "guest_email": "later@example.com",
            "title": "Unrelated event",
            "scheduled_for": safe_start.astimezone(timezone.utc).isoformat(),
            "timezone": tz_name,
        }
    )

    availability = service.list_public_booking_slots(token)
    slot_times = {
        slot_start.strftime("%H:%M")
        for item in availability["slots"]
        for slot_start in [datetime.fromisoformat(item["start"].replace("Z", "+00:00")).astimezone(tz_obj)]
        if slot_start.date() == candidate_day
    }

    assert "10:00" not in slot_times
    assert "17:00" in slot_times


def test_public_booking_creates_interview_calendar_event_and_confirmation(monkeypatch, temp_db):
    """Booking a public slot should create the interview, attach the calendar event, and send confirmation."""
    service = GuestWebService(temp_db.db_path)
    guest = service.create_guest(
        {
            "full_name": "Jordan Rivers",
            "email": "jordan@example.com",
            "website": "https://jordan.example.com",
        }
    )
    service.update_guest_status(guest["id"], "accepted")
    token = service._ensure_guest_booking_token(guest["id"])

    scheduled_for = (datetime.now(timezone.utc) + timedelta(days=2)).replace(minute=0, second=0, microsecond=0).isoformat()

    monkeypatch.setattr(
        GuestWebService,
        "list_public_booking_slots",
        lambda self, booking_token, limit=12: {
            "guest_name": "Jordan Rivers",
            "booking_timezone": "Europe/Berlin",
            "existing_booking": None,
            "slots": [{"start": scheduled_for, "end": scheduled_for, "timezone": "Europe/Berlin"}],
        },
    )

    class StubCalendarClient:
        def create_event_from_interview(self, interview):
            assert interview["guest_name"] == "Jordan Rivers"
            return {"id": "google-event-1", "updated": "2026-04-07T12:00:00Z"}

    sent = {}

    monkeypatch.setattr(GuestWebService, "_build_google_calendar_client", lambda self: StubCalendarClient())
    monkeypatch.setattr(
        GuestWebService,
        "_send_booking_confirmation_email",
        lambda self, guest_payload, interview: sent.update({"guest": guest_payload["full_name"], "interview_id": interview["id"]}),
    )

    interview = service.create_public_booking(
        token,
        {
            "scheduled_for": scheduled_for,
            "timezone": "Europe/Berlin",
            "note": "Looking forward to it",
        },
    )

    saved = service.database.get_interview_by_id(interview["id"])
    assert saved is not None
    assert saved["guest_name"] == "Jordan Rivers"
    assert saved["calendar_event_id"] == "google-event-1"
    assert saved["confirmation_status"] == "confirmed"
    assert "Booked through the Mirror Talk guest booking flow." in (saved["notes"] or "")
    assert sent == {"guest": "Jordan Rivers", "interview_id": interview["id"]}


def test_booking_confirmation_email_includes_calendar_invite(monkeypatch):
    """Booking confirmations should include an ICS invite attachment."""
    manager = EmailManager()
    captured = {}

    def fake_send_email(to_email, subject, body, attachments=None):
        captured["to_email"] = to_email
        captured["subject"] = subject
        captured["body"] = body
        captured["attachments"] = attachments or []
        return True

    monkeypatch.setattr(manager, "send_email", fake_send_email)

    scheduled_for = datetime(2026, 4, 9, 17, 0, tzinfo=timezone.utc)
    sent = manager.send_booking_confirmation_email(
        "Jordan Rivers",
        "jordan@example.com",
        scheduled_for,
        "Europe/Berlin",
        "https://riverside.fm/studio/example",
    )

    assert sent is True
    assert captured["to_email"] == "jordan@example.com"
    assert len(captured["attachments"]) == 1
    attachment = captured["attachments"][0]
    assert attachment["filename"] == "mirror-talk-booking.ics"
    attachment_text = bytes(attachment["content"]).decode("utf-8")
    assert "BEGIN:VCALENDAR" in attachment_text
    assert "METHOD:REQUEST" in attachment_text
    assert "SUMMARY:Soulful Conversation with Jordan Rivers" in attachment_text
    assert "https://riverside.fm/studio/example" in attachment_text


def test_booking_confirmation_email_formats_time_in_booking_timezone():
    """Booking emails should display the interview time in the guest-facing booking timezone."""
    manager = EmailManager()

    template = manager.get_booking_confirmation_template(
        "Jordan Rivers",
        datetime(2026, 6, 11, 18, 0, tzinfo=timezone.utc),
        "Europe/Berlin",
        "https://riverside.fm/studio/example",
    )

    assert "Thursday 11 June, 2026 at 20:00 Europe/Berlin." in template["body"]


def test_google_calendar_event_creation_requests_attendee_updates(monkeypatch):
    """New booking events should ask Google Calendar to send attendee invites."""
    captured = {}

    class StubResponse:
        ok = True
        status_code = 200
        text = ""

        @staticmethod
        def json():
            return {"id": "event-123", "updated": "2026-04-07T20:00:00Z"}

    def fake_post(url, headers=None, params=None, json=None, timeout=None):
        captured["url"] = url
        captured["headers"] = headers
        captured["params"] = params
        captured["json"] = json
        captured["timeout"] = timeout
        return StubResponse()

    monkeypatch.setattr("guest_database_manager.google_calendar_sync.requests.post", fake_post)
    monkeypatch.setattr(
        GoogleCalendarSyncClient,
        "_get_access_token",
        lambda self: "test-access-token",
    )

    client = GoogleCalendarSyncClient(
        client_id="client-id",
        client_secret="client-secret",
        refresh_token="refresh-token",
        calendar_id="mirror-talk@example.com",
    )
    result = client.create_event_from_interview(
        {
            "guest_name": "Jordan Rivers",
            "guest_email": "jordan@example.com",
            "title": "Soulful Conversation with Jordan Rivers",
            "scheduled_for": "2026-04-09T17:00:00+00:00",
            "timezone": "Europe/Berlin",
            "join_url": "https://riverside.fm/studio/example",
        }
    )

    assert result["id"] == "event-123"
    assert captured["params"] == {"sendUpdates": "all"}
    assert captured["json"]["attendees"] == [{"email": "jordan@example.com", "displayName": "Jordan Rivers"}]


def test_web_service_can_send_custom_email_body(monkeypatch, temp_db):
    """Dashboard should be able to send an edited email subject/body from the composer."""

    class StubEmailManager:
        def __init__(self):
            self.configured = False

        def configure_smtp(self, **kwargs):
            self.configured = True

        def is_configured(self):
            return self.configured

        def send_email(self, to_email, subject, body):
            assert to_email == "amina@example.com"
            assert subject == "Custom Subject"
            assert body == "Custom Body"
            return True

    monkeypatch.setattr("guest_database_manager.web_interface.EmailManager", StubEmailManager)
    monkeypatch.setenv(EMAIL_SMTP_SERVER_ENV_VAR, "smtp.example.com")
    monkeypatch.setenv(EMAIL_SMTP_PORT_ENV_VAR, "587")
    monkeypatch.setenv(EMAIL_USERNAME_ENV_VAR, "mirror@example.com")
    monkeypatch.setenv(EMAIL_PASSWORD_ENV_VAR, "top-secret")
    monkeypatch.setenv(EMAIL_FROM_ENV_VAR, "mirror@example.com")
    monkeypatch.setenv(EMAIL_FROM_NAME_ENV_VAR, "Mirror Talk Podcast")

    service = GuestWebService(temp_db.db_path)
    guest = service.create_guest({"full_name": "Amina Hart", "email": "amina@example.com"})

    updated_guest = service.send_guest_decision_email_message(
        guest["id"],
        "accepted",
        subject="Custom Subject",
        body="Custom Body",
    )

    assert updated_guest["email_status"] == "accepted"


def test_web_service_rejects_email_send_without_server_config(temp_db):
    """Hosted dashboard should not pretend email works when SMTP env vars are missing."""
    service = GuestWebService(temp_db.db_path)
    guest = service.create_guest({"full_name": "Amina Hart", "email": "amina@example.com"})

    with pytest.raises(WebInterfaceError):
        service.send_guest_decision_email(guest["id"], "accepted", "")


def test_web_service_can_create_interview_and_episode_records(temp_db):
    """Operations records should be created through the service layer without touching guest intake flows."""
    service = GuestWebService(temp_db.db_path)

    interview = service.create_interview(
        {
            "guest_name": "Jordan Rivers",
            "guest_email": "jordan@example.com",
            "title": "Mirror Talk conversation",
            "scheduled_for": "2026-04-08 17:00:00",
            "timezone": "Europe/Berlin",
            "calendar_event_id": "event_ops_1",
        }
    )
    episode = service.create_episode(
        {
            "guest_name": "Jordan Rivers",
            "guest_email": "jordan@example.com",
            "episode_title": "Healing Through Hard Seasons",
            "topic": "Healing",
            "category": "Personal Growth",
            "release_status": "scheduled",
            "production_status": "recorded",
        }
    )

    operations = service.list_operations()
    planning = service.list_planning()

    assert interview["calendar_event_id"] == "event_ops_1"
    assert episode["episode_title"] == "Healing Through Hard Seasons"
    assert len(operations["interviews"]) == 1
    assert len(planning["episodes"]) == 1


def test_operations_expose_known_episode_categories_for_guided_input(temp_db):
    """Episode entry should expose common categories from existing episode records."""
    service = GuestWebService(temp_db.db_path)

    service.create_episode(
        {
            "guest_name": "Guest One",
            "guest_email": "one@example.com",
            "episode_title": "Personal Growth Story",
            "topic": "Personal Growth Story",
            "category": "Personal Development",
        }
    )
    service.create_episode(
        {
            "guest_name": "Guest Two",
            "guest_email": "two@example.com",
            "episode_title": "Finance Story",
            "topic": "Finance Story",
            "category": "Finance",
        }
    )
    service.create_episode(
        {
            "guest_name": "Guest Three",
            "guest_email": "three@example.com",
            "episode_title": "Another Personal Growth Story",
            "topic": "Another Personal Growth Story",
            "category": "Personal Development",
        }
    )

    operations = service.list_operations()

    planning = service.list_planning()

    assert planning["available_categories"][:2] == ["Personal Development", "Finance"]


def test_operations_include_weekly_outreach_spotlight(temp_db):
    """Operations should surface the current release-cycle spotlight and daily focus."""
    service = GuestWebService(temp_db.db_path)
    service.create_episode(
        {
            "guest_name": "Jordan Rivers",
            "guest_email": "jordan@example.com",
            "episode_title": "Healing Through Hard Seasons",
            "topic": "Healing",
            "category": "Personal Development",
            "release_date": "2026-04-07T17:00",
            "release_status": "scheduled",
            "outreach_plan": {"monday_preparation": True},
        }
    )

    operations = service.list_operations()

    assert operations["weekly_system"]["metrics"]
    assert operations["weekly_outreach"]["spotlight_episode"]["episode_title"] == "Healing Through Hard Seasons"
    assert operations["weekly_outreach"]["spotlight_summary"]["completed_count"] == 1
    assert operations["weekly_outreach"]["social_focus"][0]["day"] == "Tuesday"


def test_planning_stats_separate_release_overview_from_interview_ops(temp_db):
    """Planning payload should expose episode-specific overview stats on its own page."""
    service = GuestWebService(temp_db.db_path)

    service.create_episode(
        {
            "guest_name": "Released Guest",
            "guest_email": "released@example.com",
            "episode_title": "Released Episode",
            "topic": "Released Episode",
            "category": "Personal Development",
            "release_status": "released",
            "production_status": "released",
            "promotion_status": "released",
        }
    )
    service.create_episode(
        {
            "guest_name": "Scheduled Guest",
            "guest_email": "scheduled@example.com",
            "episode_title": "Scheduled Episode",
            "topic": "Scheduled Episode",
            "category": "Finance",
            "release_status": "scheduled",
            "production_status": "ready",
            "promotion_status": "ready",
        }
    )
    service.create_episode(
        {
            "guest_name": "Needs Assets Guest",
            "guest_email": "assets@example.com",
            "episode_title": "Needs Assets Episode",
            "topic": "Needs Assets Episode",
            "category": "Health",
            "release_status": "unplanned",
            "production_status": "recorded",
            "promotion_status": "needs_assets",
        }
    )

    planning = service.list_planning()

    assert planning["stats"]["episodes_total"] == 3
    assert planning["stats"]["episodes_released"] == 1
    assert planning["stats"]["episodes_scheduled"] == 1
    assert planning["stats"]["episodes_unreleased"] == 2
    assert planning["stats"]["episodes_promo_ready"] == 1
    assert planning["stats"]["episodes_need_assets"] == 1


def test_episode_recommendations_prefer_variety_and_ready_queue(temp_db):
    """Release recommendations should surface strong ready candidates for the next Tuesday slot."""
    service = GuestWebService(temp_db.db_path)

    service.create_episode(
        {
            "guest_name": "Released One",
            "guest_email": "one@example.com",
            "episode_title": "Personal Growth Story",
            "topic": "Personal Growth Story",
            "category": "Personal Development",
            "interview_date": "2026-01-01",
            "release_date": "2026-03-24",
            "release_status": "released",
            "production_status": "released",
        }
    )
    service.create_episode(
        {
            "guest_name": "Released Two",
            "guest_email": "two@example.com",
            "episode_title": "Confidence Reset",
            "topic": "Confidence Reset",
            "category": "Personal Development",
            "interview_date": "2026-01-07",
            "release_date": "2026-03-17",
            "release_status": "released",
            "production_status": "released",
        }
    )
    service.create_episode(
        {
            "guest_name": "Finance Guest",
            "guest_email": "finance@example.com",
            "episode_title": "Building Calm Under Pressure",
            "topic": "Building Calm Under Pressure",
            "category": "Finance",
            "interview_date": "2025-12-01",
            "production_status": "ready",
            "release_status": "unplanned",
        }
    )
    service.create_episode(
        {
            "guest_name": "Another Personal Development Guest",
            "guest_email": "pd@example.com",
            "episode_title": "Finding Balance",
            "topic": "Finding Balance",
            "category": "Personal Development",
            "interview_date": "2025-12-15",
            "production_status": "ready",
            "release_status": "unplanned",
        }
    )

    planning = service.list_planning()

    assert planning["recommendations"][0]["guest_name"] == "Finance Guest"
    assert planning["recommendations"][0]["recommended_release_date"].endswith("17:00:00")


def test_episode_recommendations_factor_seasonality_promo_readiness_and_guest_diversity(temp_db):
    """The smarter planner should consider seasonal fit, promo readiness, and recent guest/category fatigue."""
    service = GuestWebService(temp_db.db_path)

    for offset in range(4):
        service.create_episode(
            {
                "guest_name": f"Recent Personal Development {offset}",
                "guest_email": f"recent{offset}@example.com",
                "episode_title": f"Personal Development Story {offset}",
                "topic": f"Personal Development Story {offset}",
                "category": "Personal Development",
                "interview_date": "2025-12-01",
                "release_date": f"2026-03-{24 - offset:02d}",
                "release_status": "released",
                "production_status": "released",
                "promotion_status": "released",
            }
        )

    service.create_episode(
        {
            "guest_name": "Jordan Rivers",
            "guest_email": "jordan@example.com",
            "episode_title": "Anxiety and Renewal",
            "topic": "Healing anxiety and renewal in spring",
            "category": "Mental Health",
            "interview_date": "2025-11-15",
            "production_status": "ready",
            "promotion_status": "ready",
        }
    )
    service.create_episode(
        {
            "guest_name": "Recent Personal Development 1",
            "guest_email": "repeat@example.com",
            "episode_title": "Career Momentum Reset",
            "topic": "Career Momentum Reset",
            "category": "Personal Development",
            "interview_date": "2025-10-10",
            "production_status": "ready",
            "promotion_status": "ready",
        }
    )
    service.create_episode(
        {
            "guest_name": "Asset Missing Guest",
            "guest_email": "assets@example.com",
            "episode_title": "Spring Reset",
            "topic": "Spring Reset",
            "category": "Mental Health",
            "interview_date": "2025-11-01",
            "production_status": "ready",
            "promotion_status": "needs_assets",
        }
    )
    service.create_episode(
        {
            "guest_name": "Faith Leader",
            "guest_email": "faith@example.com",
            "episode_title": "Faith and Purpose in Leadership",
            "topic": "Faith, leadership, and purpose at work",
            "category": "Faith",
            "interview_date": "2025-11-20",
            "production_status": "ready",
            "promotion_status": "ready",
        }
    )

    planning = service.list_planning()
    top_recommendation = planning["recommendations"][0]
    jordan_recommendation = next(
        item for item in planning["recommendations"] if item["guest_name"] == "Jordan Rivers"
    )
    seasonal_recommendation = next(
        item for item in planning["recommendations"] if item["guest_name"] == "Faith Leader"
    )

    assert top_recommendation["guest_name"] in {"Jordan Rivers", "Faith Leader"}
    assert jordan_recommendation["promotion_status"] == "ready"
    assert jordan_recommendation["recommendation_reason"]
    assert top_recommendation["recommendation_reason"]
    assert seasonal_recommendation["seasonal_fit"]["month"] == "April"
    assert "seasonal focus for April" in seasonal_recommendation["seasonal_fit"]["reason"]
    assert "faith" in seasonal_recommendation["seasonal_fit"]["matched_keywords"]


def test_episode_recommendations_include_multi_week_sequence_warnings(temp_db):
    """Recommendations should flag repetitive multi-week runs across the selected lineup."""
    service = GuestWebService(temp_db.db_path)

    service.create_episode(
        {
            "guest_name": "Finance Guest One",
            "guest_email": "finance1@example.com",
            "episode_title": "Building Calm Under Pressure",
            "topic": "Building Calm Under Pressure",
            "category": "Finance",
            "interview_date": "2025-12-01",
            "production_status": "ready",
            "promotion_status": "ready",
        }
    )
    service.create_episode(
        {
            "guest_name": "Finance Guest Two",
            "guest_email": "finance2@example.com",
            "episode_title": "Building Better Financial Calm",
            "topic": "Building Better Financial Calm",
            "category": "Finance",
            "interview_date": "2025-12-08",
            "production_status": "ready",
            "promotion_status": "ready",
        }
    )
    service.create_episode(
        {
            "guest_name": "Healing Guest",
            "guest_email": "healing@example.com",
            "episode_title": "Healing Through Honest Reflection",
            "topic": "Healing Through Honest Reflection",
            "category": "Mental Health",
            "interview_date": "2025-11-15",
            "production_status": "ready",
            "promotion_status": "ready",
        }
    )

    planning = service.list_planning()
    finance_recommendations = [item for item in planning["recommendations"] if item["category"] == "Finance"]

    assert finance_recommendations
    assert any(item["sequence_warnings"] for item in finance_recommendations)


def test_episode_recommendations_flag_archive_overlap_without_hard_blocking(temp_db):
    """Recommendations should warn when a queued episode is too close to a released archive topic."""
    service = GuestWebService(temp_db.db_path)

    service.create_episode(
        {
            "guest_name": "Released Finance Guest",
            "guest_email": "released-finance@example.com",
            "episode_title": "Building Calm Under Pressure",
            "topic": "Building Calm Under Pressure",
            "category": "Finance",
            "interview_date": "2025-10-01",
            "release_date": "2026-03-10",
            "release_status": "released",
            "production_status": "released",
            "promotion_status": "released",
        }
    )
    service.create_episode(
        {
            "guest_name": "Queued Finance Guest",
            "guest_email": "queued-finance@example.com",
            "episode_title": "Building Better Calm Under Pressure",
            "topic": "Building Better Calm Under Pressure",
            "category": "Finance",
            "interview_date": "2025-12-01",
            "production_status": "ready",
            "promotion_status": "ready",
        }
    )

    planning = service.list_planning()
    recommendation = planning["recommendations"][0]

    assert recommendation["archive_overlap"]["status"] in {"risky", "revisit"}
    assert recommendation["archive_overlap"]["message"]


def test_episode_recommendations_flag_recent_topic_clusters(temp_db):
    """Recommendations should warn when a theme is already warm across the last 10 releases."""
    service = GuestWebService(temp_db.db_path)

    for offset in range(3):
        service.create_episode(
            {
                "guest_name": f"Recent Healing Guest {offset}",
                "guest_email": f"recent-healing-{offset}@example.com",
                "episode_title": f"Healing Through Honest Reflection {offset}",
                "topic": f"Healing Through Honest Reflection {offset}",
                "category": "Mental Health",
                "interview_date": "2025-10-01",
                "release_date": f"2026-03-{10 + offset:02d}",
                "release_status": "released",
                "production_status": "released",
                "promotion_status": "released",
            }
        )

    service.create_episode(
        {
            "guest_name": "Queued Healing Guest",
            "guest_email": "queued-healing@example.com",
            "episode_title": "Healing Through Honest Awareness",
            "topic": "Healing Through Honest Awareness",
            "category": "Mental Health",
            "interview_date": "2025-12-01",
            "production_status": "ready",
            "promotion_status": "ready",
        }
    )

    planning = service.list_planning()
    recommendation = next(item for item in planning["recommendations"] if item["guest_name"] == "Queued Healing Guest")

    assert recommendation["topic_cluster_warning"]["status"] in {"warm", "active"}
    assert recommendation["topic_cluster_warning"]["message"]


def test_operations_are_sorted_by_nearest_upcoming_interview_first(temp_db):
    """Operations should prioritize the closest upcoming interview and keep history below."""
    service = GuestWebService(temp_db.db_path)

    service.create_interview(
        {
            "guest_name": "Past Guest",
            "guest_email": "past@example.com",
            "title": "Past recording",
            "scheduled_for": "2026-03-20 12:00:00",
            "timezone": "Europe/Berlin",
            "calendar_event_id": "past-interview",
        }
    )
    service.create_interview(
        {
            "guest_name": "Soon Guest",
            "guest_email": "soon@example.com",
            "title": "Soon recording",
            "scheduled_for": "2026-03-31 09:00:00",
            "timezone": "Europe/Berlin",
            "calendar_event_id": "soon-interview",
        }
    )
    service.create_interview(
        {
            "guest_name": "Later Guest",
            "guest_email": "later@example.com",
            "title": "Later recording",
            "scheduled_for": "2026-04-05 15:00:00",
            "timezone": "Europe/Berlin",
            "calendar_event_id": "later-interview",
        }
    )

    ordered = service._sort_interviews_by_upcoming_priority(
        service.database.list_interviews(),
        reference=__import__("datetime").datetime(2026, 3, 30, 8, 0, 0),
    )

    assert [item["guest_name"] for item in ordered] == [
        "Soon Guest",
        "Later Guest",
        "Past Guest",
    ]


def test_due_weekly_reminders_follow_nearest_upcoming_order(temp_db):
    """Reminder review should show the nearest interview due this week first."""
    service = GuestWebService(temp_db.db_path)

    service.create_interview(
        {
            "guest_name": "Wednesday Guest",
            "guest_email": "wednesday@example.com",
            "title": "Midweek recording",
            "scheduled_for": "2026-03-31 14:00:00",
            "timezone": "Europe/Berlin",
            "calendar_event_id": "wednesday-interview",
        }
    )
    service.create_interview(
        {
            "guest_name": "Friday Guest",
            "guest_email": "friday@example.com",
            "title": "Friday recording",
            "scheduled_for": "2026-04-03 10:00:00",
            "timezone": "Europe/Berlin",
            "calendar_event_id": "friday-interview",
        }
    )

    due = service.get_due_weekly_reminders(reference=__import__("datetime").datetime(2026, 3, 30, 9, 0, 0))

    assert [item["guest_name"] for item in due] == [
        "Wednesday Guest",
        "Friday Guest",
    ]


def test_web_service_requires_interview_and_episode_basics(temp_db):
    """Operations records should validate their essential fields."""
    service = GuestWebService(temp_db.db_path)

    with pytest.raises(WebInterfaceError):
        service.create_interview({"guest_name": "", "scheduled_for": ""})

    with pytest.raises(WebInterfaceError):
        service.create_episode({"guest_name": "Jordan Rivers", "episode_title": ""})


def test_web_service_can_preview_and_send_weekly_interview_reminders(monkeypatch, temp_db):
    """Weekly interview reminders should use the hosted email path and update reminder tracking."""

    class StubEmailManager:
        def __init__(self):
            self.configured = False
            self.last_error = ""
            self.resend_api_key = "re_test"

        def configure_resend(self, **kwargs):
            self.configured = True

        def is_configured(self):
            return self.configured

        def get_interview_reminder_template(self, guest_name, scheduled_for, timezone_label, join_url):
            assert guest_name == "Jordan Rivers"
            assert timezone_label == "CET"
            return {"subject": "Reminder Subject", "body": f"Join here: {join_url}"}

        def send_email(self, to_email, subject, body):
            assert to_email == "jordan@example.com"
            assert subject == "Reminder Subject"
            assert "riverside.fm" in body
            return True

    monkeypatch.setattr("guest_database_manager.web_interface.EmailManager", StubEmailManager)
    monkeypatch.setenv(EMAIL_RESEND_API_KEY_ENV_VAR, "re_test_123")
    monkeypatch.setenv(EMAIL_FROM_ENV_VAR, "onboarding@updates.mirrortalkpodcast.com")
    monkeypatch.setenv(EMAIL_FROM_NAME_ENV_VAR, "Mirror Talk Podcast")

    service = GuestWebService(temp_db.db_path)
    interview = service.create_interview(
        {
            "guest_name": "Jordan Rivers",
            "guest_email": "jordan@example.com",
            "title": "Mirror Talk conversation",
            "scheduled_for": "2026-03-30 17:00:00",
            "timezone": "CET",
            "join_url": "https://riverside.fm/example",
            "calendar_event_id": "calendar-event-1",
        }
    )

    preview = service.preview_interview_reminder(interview["id"])
    assert preview["subject"] == "Reminder Subject"

    sent_interview = service.send_interview_reminder(interview["id"])
    assert sent_interview["reminder_status"] == "sent"

    weekly_result = service.send_due_weekly_reminders(reference=__import__("datetime").datetime(2026, 3, 30), dry_run=True)
    assert weekly_result["count"] == 0


def test_web_service_can_preview_and_send_post_interview_appreciation(monkeypatch, temp_db):
    """Post-interview appreciation emails should use the hosted email path without mutating reminder status."""

    class StubEmailManager:
        def __init__(self):
            self.configured = False
            self.last_error = ""
            self.resend_api_key = "re_test"

        def configure_resend(self, **kwargs):
            self.configured = True

        def is_configured(self):
            return self.configured

        def get_post_interview_appreciation_template(self, guest_name):
            assert guest_name == "Jordan Rivers"
            return {"subject": "Thank You", "body": "We appreciate you."}

        def send_email(self, to_email, subject, body):
            assert to_email == "jordan@example.com"
            assert subject == "Thank You"
            assert "appreciate" in body.lower()
            return True

    monkeypatch.setattr("guest_database_manager.web_interface.EmailManager", StubEmailManager)
    monkeypatch.setenv(EMAIL_RESEND_API_KEY_ENV_VAR, "re_test_123")
    monkeypatch.setenv(EMAIL_FROM_ENV_VAR, "onboarding@updates.mirrortalkpodcast.com")
    monkeypatch.setenv(EMAIL_FROM_NAME_ENV_VAR, "Mirror Talk Podcast")

    service = GuestWebService(temp_db.db_path)
    interview = service.create_interview(
        {
            "guest_name": "Jordan Rivers",
            "guest_email": "jordan@example.com",
            "title": "Mirror Talk conversation",
            "scheduled_for": "2026-03-30 17:00:00",
            "timezone": "CET",
            "join_url": "https://riverside.fm/example",
            "calendar_event_id": "calendar-event-1",
        }
    )

    preview = service.preview_interview_appreciation(interview["id"])
    assert preview["subject"] == "Thank You"

    sent_interview = service.send_interview_appreciation(interview["id"])
    assert sent_interview["reminder_status"] == "not_scheduled"


def test_web_service_can_preview_and_send_interview_cancellation(monkeypatch, temp_db):
    """Cancellation emails should send through the hosted path and mark the interview cancelled."""

    class StubEmailManager:
        def __init__(self):
            self.configured = False
            self.last_error = ""
            self.resend_api_key = "re_test"

        def configure_resend(self, **kwargs):
            self.configured = True

        def is_configured(self):
            return self.configured

        def get_interview_cancellation_template(self, guest_name, scheduled_for, timezone_label):
            assert guest_name == "Jordan Rivers"
            assert timezone_label == "CET"
            return {"subject": "Schedule Update", "body": "We need to cancel this booking."}

        def send_email(self, to_email, subject, body):
            assert to_email == "jordan@example.com"
            assert subject == "Schedule Update"
            assert "cancel" in body.lower()
            return True

    monkeypatch.setattr("guest_database_manager.web_interface.EmailManager", StubEmailManager)
    monkeypatch.setenv(EMAIL_RESEND_API_KEY_ENV_VAR, "re_test_123")
    monkeypatch.setenv(EMAIL_FROM_ENV_VAR, "onboarding@updates.mirrortalkpodcast.com")
    monkeypatch.setenv(EMAIL_FROM_NAME_ENV_VAR, "Mirror Talk Podcast")

    service = GuestWebService(temp_db.db_path)
    interview = service.create_interview(
        {
            "guest_name": "Jordan Rivers",
            "guest_email": "jordan@example.com",
            "title": "Soulful Conversation with Jordan Rivers",
            "scheduled_for": "2026-03-30 17:00:00",
            "timezone": "CET",
            "join_url": "https://riverside.fm/example",
            "calendar_event_id": "calendar-event-1",
            "confirmation_status": "confirmed",
        }
    )

    preview = service.preview_interview_cancellation(interview["id"])
    assert preview["subject"] == "Schedule Update"

    sent_interview = service.send_interview_cancellation(interview["id"])
    assert sent_interview["status"] == "cancelled"
    assert sent_interview["confirmation_status"] == "confirmed"
    assert sent_interview["reminder_status"] == "not_scheduled"

    log_entries = temp_db.get_reminder_log(interview["id"])
    assert any(entry["reminder_type"] == "interview_cancellation" for entry in log_entries)


def test_web_service_can_preview_and_send_episode_appreciation(monkeypatch, temp_db):
    """Episode records should support the post-recording appreciation workflow."""

    class StubEmailManager:
        def __init__(self):
            self.configured = False
            self.last_error = ""
            self.resend_api_key = "re_test"

        def configure_resend(self, **kwargs):
            self.configured = True

        def is_configured(self):
            return self.configured

        def get_post_interview_appreciation_template(self, guest_name):
            assert guest_name == "Jordan Rivers"
            return {"subject": "Thank You", "body": "We appreciate you."}

        def send_email(self, to_email, subject, body):
            assert to_email == "jordan@example.com"
            assert subject == "Thank You"
            assert "appreciate" in body.lower()
            return True

    monkeypatch.setattr("guest_database_manager.web_interface.EmailManager", StubEmailManager)
    monkeypatch.setenv(EMAIL_RESEND_API_KEY_ENV_VAR, "re_test_123")
    monkeypatch.setenv(EMAIL_FROM_ENV_VAR, "onboarding@updates.mirrortalkpodcast.com")
    monkeypatch.setenv(EMAIL_FROM_NAME_ENV_VAR, "Mirror Talk Podcast")

    service = GuestWebService(temp_db.db_path)
    episode = service.create_episode(
        {
            "guest_name": "Jordan Rivers",
            "guest_email": "jordan@example.com",
            "episode_title": "A Meaningful Conversation",
            "topic": "Purpose",
            "production_status": "recorded",
        }
    )

    preview = service.preview_episode_appreciation(episode["id"])
    assert preview["subject"] == "Thank You"

    sent_episode = service.send_episode_appreciation(episode["id"])
    assert sent_episode["guest_email"] == "jordan@example.com"


def test_web_service_can_preview_and_send_released_episode_email(monkeypatch, temp_db):
    """Released episodes should support a polished live-episode follow-up with links."""

    class StubEmailManager:
        def __init__(self):
            self.configured = False
            self.last_error = ""
            self.resend_api_key = "re_test"

        def configure_resend(self, **kwargs):
            self.configured = True

        def is_configured(self):
            return self.configured

        def get_released_episode_template(self, guest_name, show_notes_url, files_url):
            assert guest_name == "Jordan Rivers"
            assert show_notes_url == "https://mirrortalkpodcast.com/episode/jordan-rivers"
            assert files_url == "https://downloads.mirrortalkpodcast.com/jordan-rivers"
            return {"subject": "Your Mirror Talk episode is now live", "body": "Show notes and files are ready."}

        def send_email(self, to_email, subject, body):
            assert to_email == "jordan@example.com"
            assert subject == "Your Mirror Talk episode is now live"
            assert "files" in body.lower()
            return True

    monkeypatch.setattr("guest_database_manager.web_interface.EmailManager", StubEmailManager)
    monkeypatch.setenv(EMAIL_RESEND_API_KEY_ENV_VAR, "re_test_123")
    monkeypatch.setenv(EMAIL_FROM_ENV_VAR, "onboarding@updates.mirrortalkpodcast.com")
    monkeypatch.setenv(EMAIL_FROM_NAME_ENV_VAR, "Mirror Talk Podcast")

    service = GuestWebService(temp_db.db_path)
    episode = service.create_episode(
        {
            "guest_name": "Jordan Rivers",
            "guest_email": "jordan@example.com",
            "episode_title": "A Meaningful Conversation",
            "topic": "Purpose",
            "release_status": "released",
            "show_notes_url": "https://mirrortalkpodcast.com/episode/jordan-rivers",
            "release_files_url": "https://downloads.mirrortalkpodcast.com/jordan-rivers",
        }
    )

    assert episode["show_notes_url"] == "https://mirrortalkpodcast.com/episode/jordan-rivers"
    assert episode["release_files_url"] == "https://downloads.mirrortalkpodcast.com/jordan-rivers"

    preview = service.preview_episode_release_email(episode["id"])
    assert preview["subject"] == "Your Mirror Talk episode is now live"

    sent_episode = service.send_episode_release_email(episode["id"])
    assert sent_episode["guest_email"] == "jordan@example.com"


def test_web_service_can_sync_google_calendar_interviews(monkeypatch, temp_db):
    """Google Calendar events should sync into interview records through the service layer."""

    class StubCalendarClient:
        def list_upcoming_events(self, **kwargs):
            return [
                {
                    "id": "google_event_1",
                    "summary": "MIRROR TALK Podcast Conversation with Jordan Rivers",
                    "updated": "2026-03-30T10:00:00Z",
                    "status": "confirmed",
                    "start": {
                        "dateTime": "2026-03-31T17:00:00+01:00",
                        "timeZone": "Europe/Berlin",
                    },
                    "attendees": [
                        {
                            "displayName": "Jordan Rivers",
                            "email": "jordan@example.com",
                            "responseStatus": "accepted",
                        }
                    ],
                    "description": "Join here https://riverside.fm/studio/soulful-conversations?t=db1988c6212f0c5f39db",
                }
            ]

        def normalize_event(self, event):
            return {
                "guest_name": "Jordan Rivers",
                "guest_email": "jordan@example.com",
                "calendar_event_id": event["id"],
                "calendar_source": "google_calendar",
                "event_updated_at": event["updated"],
                "last_synced_at": "2026-03-30T11:00:00Z",
                "title": event["summary"],
                "scheduled_for": event["start"]["dateTime"],
                "timezone": "Europe/Berlin",
                "join_url": "https://riverside.fm/studio/soulful-conversations?t=db1988c6212f0c5f39db",
                "status": "scheduled",
                "confirmation_status": "confirmed",
                "reminder_status": "not_scheduled",
                "notes": "Imported from Google Calendar",
            }

    monkeypatch.setenv(GOOGLE_CLIENT_ID_ENV_VAR, "client-id")
    monkeypatch.setenv(GOOGLE_CLIENT_SECRET_ENV_VAR, "client-secret")
    monkeypatch.setenv(GOOGLE_REFRESH_TOKEN_ENV_VAR, "refresh-token")
    monkeypatch.setenv(GOOGLE_CALENDAR_ID_ENV_VAR, "calendar@example.com")
    service = GuestWebService(temp_db.db_path)
    monkeypatch.setattr(service, "_build_google_calendar_client", lambda: StubCalendarClient())

    result = service.sync_google_calendar_interviews()

    assert result["count"] == 1
    assert result["interviews"][0]["guest_name"] == "Jordan Rivers"
    assert service.list_operations()["interviews"][0]["calendar_source"] == "google_calendar"


def test_web_service_syncs_google_calendar_with_long_horizon_by_default(monkeypatch, temp_db):
    """Calendar sync should look far enough ahead by default for booking-safety checks."""

    class StubCalendarClient:
        def __init__(self):
            self.days_ahead_seen = None

        def list_upcoming_events(self, **kwargs):
            self.days_ahead_seen = kwargs.get("days_ahead")
            return []

        def normalize_event(self, event):
            return event

    monkeypatch.setenv(GOOGLE_CLIENT_ID_ENV_VAR, "client-id")
    monkeypatch.setenv(GOOGLE_CLIENT_SECRET_ENV_VAR, "client-secret")
    monkeypatch.setenv(GOOGLE_REFRESH_TOKEN_ENV_VAR, "refresh-token")
    monkeypatch.setenv(GOOGLE_CALENDAR_ID_ENV_VAR, "calendar@example.com")
    service = GuestWebService(temp_db.db_path)
    stub_client = StubCalendarClient()
    monkeypatch.setattr(service, "_build_google_calendar_client", lambda: stub_client)

    service.sync_google_calendar_interviews()

    assert stub_client.days_ahead_seen == 365


def test_web_service_can_push_interview_updates_to_google_calendar(monkeypatch, temp_db):
    """Operators should be able to explicitly push an interview back to its linked Google event."""

    class StubCalendarClient:
        def update_event_from_interview(self, interview):
            assert interview["calendar_event_id"] == "google_event_1"
            assert interview["title"] == "Updated Mirror Talk conversation"
            assert interview["scheduled_for"] == "2026-03-31 18:30:00"
            return {
                "updated": "2026-03-30T12:00:00Z",
            }

    monkeypatch.setenv(GOOGLE_CLIENT_ID_ENV_VAR, "client-id")
    monkeypatch.setenv(GOOGLE_CLIENT_SECRET_ENV_VAR, "client-secret")
    monkeypatch.setenv(GOOGLE_REFRESH_TOKEN_ENV_VAR, "refresh-token")
    monkeypatch.setenv(GOOGLE_CALENDAR_ID_ENV_VAR, "calendar@example.com")

    service = GuestWebService(temp_db.db_path)
    interview = service.create_interview(
        {
            "guest_name": "Jordan Rivers",
            "guest_email": "jordan@example.com",
            "title": "Updated Mirror Talk conversation",
            "scheduled_for": "2026-03-31 18:30:00",
            "timezone": "Europe/Berlin",
            "calendar_event_id": "google_event_1",
        }
    )
    monkeypatch.setattr(service, "_build_google_calendar_client", lambda: StubCalendarClient())

    pushed = service.push_interview_to_google_calendar(interview["id"])

    assert pushed["calendar_event_id"] == "google_event_1"
    assert pushed["event_updated_at"] == "2026-03-30T12:00:00Z"
    assert pushed["calendar_source"] == "google_calendar"


def test_operations_flag_duplicate_future_guest_bookings(temp_db):
    """Operations should warn when the same guest is holding multiple future dates."""
    service = GuestWebService(temp_db.db_path)
    service.create_interview(
        {
            "guest_name": "Jordan Rivers",
            "guest_email": "jordan@example.com",
            "title": "Mirror Talk with Jordan Rivers",
            "scheduled_for": "2099-03-31 17:00:00",
            "calendar_event_id": "google_event_1",
        }
    )
    service.create_interview(
        {
            "guest_name": "Jordan Rivers",
            "guest_email": "jordan@example.com",
            "title": "Mirror Talk with Jordan Rivers follow-up",
            "scheduled_for": "2099-04-03 17:00:00",
            "calendar_event_id": "google_event_2",
        }
    )

    operations = service.list_operations()

    assert len(operations["booking_alerts"]["double_bookings"]) == 1
    assert operations["booking_alerts"]["double_bookings"][0]["guest_name"] == "Jordan Rivers"
    assert operations["booking_alerts"]["double_bookings"][0]["count"] == 2


def test_operations_flag_calendar_cleanup_candidates(temp_db):
    """Declined or cancelled linked interviews should appear in calendar cleanup alerts."""
    service = GuestWebService(temp_db.db_path)
    service.create_interview(
        {
            "guest_name": "Jordan Rivers",
            "guest_email": "jordan@example.com",
            "title": "Mirror Talk with Jordan Rivers",
            "scheduled_for": "2099-03-31 17:00:00",
            "calendar_event_id": "google_event_1",
            "confirmation_status": "declined",
        }
    )

    operations = service.list_operations()

    assert len(operations["booking_alerts"]["calendar_cleanup"]) == 1
    assert "calendar slot still exists" in operations["booking_alerts"]["calendar_cleanup"][0]["reason"].lower()


def test_web_service_can_remove_interview_from_google_calendar(monkeypatch, temp_db):
    """Operators should be able to remove stale cancelled bookings from Google Calendar."""

    class StubCalendarClient:
        def delete_event(self, event_id):
            assert event_id == "google_event_1"

    monkeypatch.setenv(GOOGLE_CLIENT_ID_ENV_VAR, "client-id")
    monkeypatch.setenv(GOOGLE_CLIENT_SECRET_ENV_VAR, "client-secret")
    monkeypatch.setenv(GOOGLE_REFRESH_TOKEN_ENV_VAR, "refresh-token")
    monkeypatch.setenv(GOOGLE_CALENDAR_ID_ENV_VAR, "calendar@example.com")

    service = GuestWebService(temp_db.db_path)
    interview = service.create_interview(
        {
            "guest_name": "Jordan Rivers",
            "guest_email": "jordan@example.com",
            "title": "Updated Mirror Talk conversation",
            "scheduled_for": "2099-03-31 18:30:00",
            "timezone": "Europe/Berlin",
            "calendar_event_id": "google_event_1",
            "confirmation_status": "pending",
        }
    )
    monkeypatch.setattr(service, "_build_google_calendar_client", lambda: StubCalendarClient())

    removed = service.remove_interview_from_google_calendar(interview["id"])

    assert removed["status"] == "cancelled"
    assert removed["confirmation_status"] == "declined"
    assert "Removed from Google Calendar." in removed["notes"]
    assert removed["calendar_event_id"] is None


def test_web_service_treats_already_deleted_google_calendar_event_as_cleaned_up(monkeypatch, temp_db):
    """A stale Google Calendar event id should be treated as already removed, not as a fatal error."""

    class StubCalendarClient:
        def delete_event(self, event_id):
            assert event_id == "google_event_1"
            return {"deleted": False, "already_deleted": True}

    monkeypatch.setenv(GOOGLE_CLIENT_ID_ENV_VAR, "client-id")
    monkeypatch.setenv(GOOGLE_CLIENT_SECRET_ENV_VAR, "client-secret")
    monkeypatch.setenv(GOOGLE_REFRESH_TOKEN_ENV_VAR, "refresh-token")
    monkeypatch.setenv(GOOGLE_CALENDAR_ID_ENV_VAR, "calendar@example.com")

    service = GuestWebService(temp_db.db_path)
    interview = service.create_interview(
        {
            "guest_name": "Jordan Rivers",
            "guest_email": "jordan@example.com",
            "title": "Updated Mirror Talk conversation",
            "scheduled_for": "2099-03-31 18:30:00",
            "timezone": "Europe/Berlin",
            "calendar_event_id": "google_event_1",
            "calendar_source": "google_calendar",
            "confirmation_status": "pending",
        }
    )
    monkeypatch.setattr(service, "_build_google_calendar_client", lambda: StubCalendarClient())

    removed = service.remove_interview_from_google_calendar(interview["id"])

    assert removed["status"] == "cancelled"
    assert removed["calendar_event_id"] is None
    assert removed["calendar_source"] == ""
    assert "already gone" in removed["notes"].lower()


def test_google_calendar_sync_recognizes_soulful_podcast_event_markers():
    """Calendar sync should recognize Mirror Talk interview invites from the event body, not only the title."""
    from guest_database_manager.google_calendar_sync import GoogleCalendarSyncClient

    event = {
        "summary": "Soulful Podcast Conversation",
        "location": "https://riverside.fm/studio/soulful-conversations?t=db1988c6212f0c5f39db",
        "description": (
            "Thank you so much for accepting the invitation to be a guest on our beloved podcast. "
            "Please support us by following us on Spotify and Apple Podcasts. "
            "For more information, visit https://mirrortalkpodcast.com/join-our-family/"
        ),
    }

    assert GoogleCalendarSyncClient._looks_like_podcast_event(event, query="Mirror Talk") is True


def test_google_calendar_sync_extracts_guest_name_from_host_and_guest_title():
    """Calendar titles like 'Guest and Tobi Ojekunle' should resolve to the guest only."""
    from guest_database_manager.google_calendar_sync import GoogleCalendarSyncClient

    event = {
        "summary": "Tim Rexius and Tobi Ojekunle",
        "organizer": {"displayName": "Tobi Ojekunle", "email": "podcast.mirrortalk@gmail.com"},
        "attendees": [
            {"displayName": "Tobi Ojekunle", "email": "podcast.mirrortalk@gmail.com", "self": True},
            {"email": "tim@example.com", "responseStatus": "accepted"},
        ],
        "start": {"dateTime": "2026-04-02T20:00:00+02:00", "timeZone": "Europe/Berlin"},
        "description": "Location: https://riverside.fm/studio/soulful-conversations?t=db1988c6212f0c5f39db",
    }

    client = GoogleCalendarSyncClient(
        client_id="client-id",
        client_secret="client-secret",
        refresh_token="refresh-token",
        calendar_id="podcast.mirrortalk@gmail.com",
    )

    normalized = client.normalize_event(event)

    assert normalized["guest_name"] == "Tim Rexius"
    assert normalized["guest_email"] == "tim@example.com"


def test_operations_list_reports_calendar_sync_enabled(monkeypatch, temp_db):
    """Operations payload should surface whether Google Calendar sync is configured."""
    monkeypatch.setenv(GOOGLE_CLIENT_ID_ENV_VAR, "client-id")
    monkeypatch.setenv(GOOGLE_CLIENT_SECRET_ENV_VAR, "client-secret")
    monkeypatch.setenv(GOOGLE_REFRESH_TOKEN_ENV_VAR, "refresh-token")
    monkeypatch.setenv(GOOGLE_CALENDAR_ID_ENV_VAR, "calendar@example.com")

    service = GuestWebService(temp_db.db_path)
    payload = service.list_operations()

    assert payload["calendar_sync_enabled"] is True


def test_validate_intake_payload_rejects_spam_keywords():
    """Spammy submissions should be rejected before insertion."""
    with pytest.raises(WebInterfaceError):
        validate_intake_payload(
            {
                "background": "I offer premium SEO backlink services for your website.",
                "profession": "SEO seller with many services available right now.",
                "passionate_topics": "Marketing marketing marketing marketing marketing marketing marketing marketing",
                "message": "Buy now buy now buy now buy now buy now buy now buy now buy now",
                "experience": "Lots of guest posts across many websites with backlinks included always.",
                "additional_info": "Visit http://spam.example and http://spam2.example today.",
            }
        )


def test_validate_intake_payload_allows_legitimate_profile_links():
    """Real guest submissions should be able to include a website, socials, and past appearance links."""
    validate_intake_payload(
        {
            "website": "https://example.com",
            "social_handles": "https://instagram.com/example https://linkedin.com/in/example https://youtube.com/@example",
            "background": "I am a speaker and writer focused on healing, resilience, and the long work of emotional honesty.",
            "profession": "I work as a trauma-informed coach and public speaker.",
            "passionate_topics": "I care about healing, faith, leadership, reflection, emotional courage, and meaningful conversations.",
            "message": "I want listeners to leave with more hope, more honesty, and more compassion for their own journey.",
            "experience": "https://podcast-one.example https://podcast-two.example",
            "additional_info": "I would love to contribute a grounded and encouraging conversation to Mirror Talk.",
        }
    )


def test_validate_intake_payload_allows_profile_links_plus_podcast_link_in_additional_info():
    """A genuine applicant should be able to share socials and one podcast link in the final answer."""
    validate_intake_payload(
        {
            "website": "https://example.com",
            "social_handles": "\n".join(
                [
                    "Instagram: https://instagram.com/example",
                    "LinkedIn: https://linkedin.com/in/example",
                    "YouTube: https://youtube.com/@example",
                    "X/Twitter: https://x.com/example",
                    "Facebook: https://facebook.com/example",
                    "TikTok: https://tiktok.com/@example",
                ]
            ),
            "background": "I am a speaker and writer focused on healing, resilience, and the long work of emotional honesty.",
            "profession": "Author",
            "passionate_topics": "Healing",
            "message": "Hope",
            "experience": "https://podcast-one.example https://podcast-two.example",
            "additional_info": "You can also hear my podcast here: https://podcast.example/show",
        }
    )


def test_validate_intake_payload_allows_many_relevant_links():
    """Link-heavy creator submissions should still go through when the content is genuine."""
    validate_intake_payload(
        {
            "background": "Read more at https://a.example https://b.example https://c.example https://d.example https://e.example while I continue sharing honest work around healing, faith, and leadership.",
            "profession": "Speaker",
            "passionate_topics": "Faith",
            "message": "Hope",
            "experience": "I have spoken on https://f.example and hosted conversations at https://g.example.",
        }
    )


def test_validate_intake_payload_rejects_low_effort_answers():
    """Very short long-form answers should be rejected."""
    with pytest.raises(WebInterfaceError):
        validate_intake_payload(
            {
                "background": "Short answer only",
                "profession": "Another short answer",
                "passionate_topics": "Too short here",
                "message": "Still too short",
                "experience": "Barely enough",
                "additional_info": "Not detailed",
            }
        )
