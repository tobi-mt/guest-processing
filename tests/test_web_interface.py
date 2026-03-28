# SPDX-FileCopyrightText: 2024-present Guest Database Manager <admin@example.com>
#
# SPDX-License-Identifier: MIT
"""Tests for the direct web interface service layer."""

import json

import pytest

from guest_database_manager.web_interface import (
    FORM_SOURCE_NAME,
    INTAKE_SOURCE_NAME,
    GuestWebService,
    WebInterfaceError,
    build_guest_payload,
    validate_intake_payload,
)


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
