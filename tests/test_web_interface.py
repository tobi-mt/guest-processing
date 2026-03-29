# SPDX-FileCopyrightText: 2024-present Guest Database Manager <admin@example.com>
#
# SPDX-License-Identifier: MIT
"""Tests for the direct web interface service layer."""

import json

import pandas as pd
import pytest

from guest_database_manager.web_interface import (
    EMAIL_FROM_ENV_VAR,
    EMAIL_FROM_NAME_ENV_VAR,
    EMAIL_PASSWORD_ENV_VAR,
    EMAIL_CC_ENV_VAR,
    EMAIL_RESEND_API_KEY_ENV_VAR,
    EMAIL_SMTP_PORT_ENV_VAR,
    EMAIL_SMTP_SERVER_ENV_VAR,
    EMAIL_USERNAME_ENV_VAR,
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


def test_web_service_can_send_acceptance_email(monkeypatch, temp_db):
    """Hosted dashboard should be able to send an approval email and persist acceptance."""

    class StubEmailManager:
        def __init__(self):
            self.configured = False

        def configure_smtp(self, **kwargs):
            self.configured = True

        def is_configured(self):
            return self.configured

        def send_acceptance_email(self, guest_name, to_email, custom_message=""):
            assert guest_name == "Amina Hart"
            assert to_email == "amina@example.com"
            assert custom_message == "Welcome aboard"
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

        def get_acceptance_template(self, guest_name, custom_message=""):
            assert guest_name == "Amina Hart"
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

    assert interview["calendar_event_id"] == "event_ops_1"
    assert episode["episode_title"] == "Healing Through Hard Seasons"
    assert len(operations["interviews"]) == 1
    assert len(operations["episodes"]) == 1


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
