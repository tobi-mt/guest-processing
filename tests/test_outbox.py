"""Transactional outbox reliability tests."""

from threading import Event
from datetime import datetime, timezone

import pytest

from guest_database_manager.database import GuestDatabase
from guest_database_manager.email_manager import EmailManager
from guest_database_manager.web_interface import GuestWebService


def _enqueue(db: GuestDatabase, key: str = "booking:1") -> int:
    return db.enqueue_email_outbox(
        interview_id=None,
        email_type="booking_confirmation",
        sent_to="guest@example.com",
        subject="Booked",
        body="Confirmation",
        next_attempt_at="2000-01-01 00:00:00",
        idempotency_key=key,
    )


def test_idempotency_key_prevents_duplicate_messages(temp_db):
    first = _enqueue(temp_db, "same-effect")
    second = _enqueue(temp_db, "same-effect")

    with temp_db._connect() as conn:
        count = conn.execute("SELECT COUNT(*) FROM email_outbox").fetchone()[0]
    assert first == second
    assert count == 1


def test_atomic_lease_allows_only_one_worker_to_claim(temp_db):
    outbox_id = _enqueue(temp_db)

    first_claim = temp_db.claim_due_email_outbox(worker_id="worker-1", lease_seconds=120)
    second_claim = temp_db.claim_due_email_outbox(worker_id="worker-2", lease_seconds=120)

    assert [row["id"] for row in first_claim] == [outbox_id]
    assert second_claim == []


def test_expired_sending_lease_is_recovered_after_worker_crash(temp_db):
    outbox_id = _enqueue(temp_db)
    temp_db.claim_due_email_outbox(worker_id="crashed-worker", lease_seconds=120)
    with temp_db._connect() as conn:
        conn.execute("UPDATE email_outbox SET lease_until = '2000-01-01 00:00:00' WHERE id = ?", (outbox_id,))

    recovered = temp_db.claim_due_email_outbox(worker_id="recovery-worker", lease_seconds=120)

    assert [row["id"] for row in recovered] == [outbox_id]
    assert recovered[0]["lease_owner"] == "recovery-worker"


def test_terminal_failure_creates_dead_letter_and_attempt_history(temp_db):
    outbox_id = _enqueue(temp_db)
    temp_db.claim_due_email_outbox(worker_id="worker-1")

    temp_db.mark_email_outbox_retry(
        outbox_id,
        attempts=5,
        next_attempt_at="2100-01-01 00:00:00",
        last_error="Provider rejected message",
        status="dead_letter",
        worker_id="worker-1",
    )

    with temp_db._connect() as conn:
        row = conn.execute("SELECT status, dead_letter_at FROM email_outbox WHERE id = ?", (outbox_id,)).fetchone()
        attempt = conn.execute(
            "SELECT attempt_number, worker_id, status, error FROM email_outbox_attempts WHERE outbox_id = ?",
            (outbox_id,),
        ).fetchone()
    assert row[0] == "dead_letter"
    assert row[1]
    assert attempt == (5, "worker-1", "dead_letter", "Provider rejected message")
    assert temp_db.get_email_outbox_health()["dead_letter"] == 1

    retried = temp_db.retry_dead_letter_email(outbox_id)
    assert retried["status"] == "retrying"
    assert retried["dead_letter_at"] is None
    assert temp_db.list_email_outbox_failures() == []
    assert temp_db.list_audit_events("communication", outbox_id)[0]["event_type"] == "dead_letter_retried"


def test_completed_idempotent_effect_is_not_sent_twice(monkeypatch, temp_db):
    service = GuestWebService(temp_db.db_path)
    _enqueue(temp_db, "one-external-effect")
    _enqueue(temp_db, "one-external-effect")
    calls = []

    class StubEmailManager:
        last_error = ""
        resend_api_key = "test"

        def configure_resend(self, **kwargs):
            return None

        def is_configured(self):
            return True

        def send_email(self, *args, **kwargs):
            calls.append((args, kwargs))
            return True

    monkeypatch.setattr("guest_database_manager.web_interface.EmailManager", StubEmailManager)

    assert service.process_pending_email_outbox()["sent"] == 1
    assert service.process_pending_email_outbox()["sent"] == 0
    assert len(calls) == 1
    assert calls[0][1]["idempotency_key"] == "one-external-effect"
    with temp_db._connect() as conn:
        runs = conn.execute(
            "SELECT status, checked_count, succeeded_count, failed_count FROM automation_runs ORDER BY id"
        ).fetchall()
    assert runs == [("completed", 1, 1, 0), ("completed", 0, 0, 0)]


def test_provider_idempotency_prevents_duplicate_effect_after_post_send_crash(monkeypatch, temp_db):
    service = GuestWebService(temp_db.db_path)
    outbox_id = _enqueue(temp_db, "crash-after-provider-success")
    provider_keys = set()
    provider_calls = []

    class IdempotentProvider:
        last_error = ""
        resend_api_key = "test"

        def configure_resend(self, **kwargs):
            return None

        def is_configured(self):
            return True

        def send_email(self, *args, **kwargs):
            key = kwargs["idempotency_key"]
            provider_calls.append(key)
            provider_keys.add(key)
            return True

    real_mark_sent = service.database.mark_email_outbox_sent
    crashed = {"value": False}

    def crash_once(*args, **kwargs):
        if not crashed["value"]:
            crashed["value"] = True
            raise RuntimeError("worker crashed after provider accepted message")
        return real_mark_sent(*args, **kwargs)

    monkeypatch.setattr("guest_database_manager.web_interface.EmailManager", IdempotentProvider)
    monkeypatch.setattr(service.database, "mark_email_outbox_sent", crash_once)

    with pytest.raises(RuntimeError, match="worker crashed"):
        service.process_pending_email_outbox(worker_id="crashed-worker")
    with temp_db._connect() as conn:
        conn.execute(
            "UPDATE email_outbox SET lease_until = '2000-01-01 00:00:00' WHERE id = ?",
            (outbox_id,),
        )

    assert service.process_pending_email_outbox(worker_id="recovery-worker")["sent"] == 1
    assert provider_calls == ["crash-after-provider-success", "crash-after-provider-success"]
    assert provider_keys == {"crash-after-provider-success"}
    with temp_db._connect() as conn:
        assert conn.execute("SELECT status FROM email_outbox WHERE id = ?", (outbox_id,)).fetchone()[0] == "sent"


def test_resend_receives_provider_idempotency_header(monkeypatch):
    from guest_database_manager.email_manager import EmailManager

    captured = {}

    class Response:
        ok = True

    def fake_post(url, **kwargs):
        captured.update(kwargs)
        return Response()

    monkeypatch.setattr("guest_database_manager.email_manager.requests.post", fake_post)
    manager = EmailManager()
    manager.configure_resend(api_key="resend-key", from_email="host@example.com")

    assert manager.send_email(
        "guest@example.com",
        "Subject",
        "Body",
        idempotency_key="booking_confirmation:42:2026-08-02",
    )
    assert captured["headers"]["Idempotency-Key"] == "booking_confirmation:42:2026-08-02"


def test_smtp_email_includes_plain_text_and_html_alternatives(monkeypatch):
    captured = {}

    class SMTP:
        def __init__(self, server, port):
            captured["connection"] = (server, port)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def starttls(self, context):
            return None

        def login(self, username, password):
            return None

        def send_message(self, message, to_addrs):
            captured["message"] = message
            captured["to_addrs"] = to_addrs

    monkeypatch.setattr("guest_database_manager.email_manager.smtplib.SMTP", SMTP)
    manager = EmailManager()
    manager.configure_smtp("smtp.example.test", 587, "user", "password", "host@example.com")

    assert manager.send_email(
        "guest@example.com",
        "Connect with Mirror Talk",
        "Listen here:\nhttps://mirrortalkpodcast.com/listen-connect/",
    )

    alternatives = captured["message"].get_payload()[0]
    assert alternatives.get_content_subtype() == "alternative"
    assert [part.get_content_subtype() for part in alternatives.get_payload()] == ["plain", "html"]
    assert "https://mirrortalkpodcast.com/listen-connect/" in alternatives.get_payload()[0].get_payload(decode=True).decode()
    html_body = alternatives.get_payload()[1].get_payload(decode=True).decode()
    assert ">Listen and connect with Mirror Talk</a>" in html_body


def test_continuous_worker_starts_processes_and_stops(monkeypatch, temp_db):
    service = GuestWebService(temp_db.db_path)
    processed = Event()
    monkeypatch.setattr(service, "process_pending_email_outbox", lambda **kwargs: processed.set())

    service.start_outbox_worker(interval_seconds=1)
    assert processed.wait(timeout=1)
    service.stop_outbox_worker(timeout_seconds=1)

    assert service._outbox_thread is not None
    assert not service._outbox_thread.is_alive()


def test_reviewed_email_template_variants_are_explicit_and_preserve_required_links():
    manager = EmailManager()

    acceptance = manager.get_acceptance_template("Amina", booking_url="https://example.test/book", variant="concise")
    reminder = manager.get_interview_reminder_template(
        "Amina", datetime(2026, 8, 20, 10, tzinfo=timezone.utc), "UTC", "https://example.test/join", variant="concise"
    )

    assert acceptance["subject"] == "You’re invited to join Mirror Talk Podcast"
    assert "https://example.test/book" in acceptance["body"]
    assert "https://example.test/join" in reminder["body"]
    assert {item["id"] for item in manager.template_variants("accepted")} == {"warm", "concise"}


def test_every_guest_email_template_has_a_human_greeting_and_mirror_talk_signature():
    manager = EmailManager()
    scheduled = datetime(2026, 8, 20, 10, tzinfo=timezone.utc)
    templates = [
        manager.get_acceptance_template("Amina", booking_url="https://example.test/book"),
        manager.get_rejection_template("Amina"),
        manager.get_interview_reminder_template("Amina", scheduled, "UTC", "https://example.test/join"),
        manager.get_interview_cancellation_template("Amina", scheduled, "UTC"),
        manager.get_booking_confirmation_template("Amina", scheduled, "UTC", "https://example.test/join"),
        manager.get_reschedule_link_template("Amina", scheduled, "UTC", "https://example.test/reschedule"),
        manager.get_post_interview_appreciation_template("Amina"),
        manager.get_intake_confirmation_template("Amina"),
        manager.get_personal_application_request_template("Amina", "https://example.test/apply"),
        manager.get_booking_link_template("Amina", "https://example.test/book"),
        manager.get_released_episode_template(
            "Amina", "https://example.test/episode", "https://example.test/files"
        ),
        manager.get_release_heads_up_template("Amina", "Friday, 04 December 2026"),
    ]

    assert len(templates) == len(manager.EMAIL_TEMPLATE_VARIANTS)
    for template in templates:
        assert template["subject"].strip()
        assert template["body"].startswith("Hi Amina,\n\n")
        assert "Mirror Talk" in template["body"]
        assert "Dear Sir/Madam" not in template["body"]
        assert "valued guest" not in template["body"].lower()


def test_guest_email_templates_use_the_current_listen_and_connect_link():
    manager = EmailManager()
    templates = [
        manager.get_intake_confirmation_template("Amina"),
        manager.get_released_episode_template(
            "Amina", "https://example.test/episode", "https://example.test/files"
        ),
    ]

    for template in templates:
        assert "https://mirrortalkpodcast.com/listen-connect/" in template["body"]
        assert "https://lnkfi.re/mirrortalk" not in template["body"]


def test_email_personalization_uses_bounded_research_topics_without_raw_notes():
    manager = EmailManager()
    context = manager.build_personalization_context(
        {
            "guest_research": {
                "likely_topics": ["caregiver resilience", "x" * 200],
                "summary": "Internal research summary must never be copied into an email.",
            },
            "background": "Private intake background must also stay private.",
        }
    )

    template = manager.get_acceptance_template(
        "Amina", booking_url="https://example.test/book", personalization=context
    )

    assert context == {"topic": "caregiver resilience"}
    assert "Your perspective on caregiver resilience" in template["body"]
    assert "Internal research summary" not in template["body"]
    assert "Private intake background" not in template["body"]


def test_acceptance_personalization_uses_professional_context_without_overclaiming():
    manager = EmailManager()
    context = manager.build_personalization_context(
        {
            "profession": "Trauma-informed therapist",
            "company": "The Listening Room",
            "guest_research": {"likely_topics": []},
        }
    )

    template = manager.get_acceptance_template(
        "Amina", booking_url="https://example.test/book", personalization=context
    )

    assert context == {
        "role": "Trauma-informed therapist",
        "organisation": "The Listening Room",
    }
    assert "Your perspective as Trauma-informed therapist at The Listening Room" in template["body"]
    assert "We were moved" not in template["body"]
    assert template["subject"] == "We’d love to welcome you to Mirror Talk"


def test_email_personalization_does_not_copy_links_from_profile_fields():
    manager = EmailManager()

    context = manager.build_personalization_context(
        {"profession": "https://example.test/profile", "company": "Purpose Studio"}
    )
    template = manager.get_acceptance_template("Amina", personalization=context)

    assert context == {"organisation": "Purpose Studio"}
    assert "Your work with Purpose Studio" in template["body"]
    assert "example.test/profile" not in template["body"]


def test_personalized_templates_fall_back_cleanly_and_expose_reviewed_variants():
    manager = EmailManager()
    context = manager.build_personalization_context(
        {"topic": "identity and confidence", "guest_research": "not-json"}
    )
    confirmation = manager.get_booking_confirmation_template(
        "Amina",
        datetime(2026, 8, 20, 10, tzinfo=timezone.utc),
        "UTC",
        "https://example.test/join",
        personalization=context,
    )
    concise_release = manager.get_released_episode_template(
        "Amina",
        "https://example.test/episode",
        "https://example.test/files",
        variant="concise",
        personalization=context,
    )

    assert "exploring identity and confidence" in confirmation["body"]
    assert "identity and confidence" in concise_release["body"]
    assert {item["id"] for item in manager.template_variants("released_episode")} == {
        "celebratory", "concise",
    }


def test_release_heads_up_template_sets_expectations_without_claiming_publication():
    manager = EmailManager()

    template = manager.get_release_heads_up_template(
        "Jordan", "Friday, 04 December 2026", personalization={"topic": "purpose"}
    )

    assert template["subject"] == "Your Mirror Talk episode is scheduled for Friday, 04 December 2026"
    assert "scheduled for release" in template["body"]
    assert "live episode link" in template["body"]
    assert "now live" not in template["body"]
    assert {item["id"] for item in manager.template_variants("release_heads_up")} == {"warm", "concise"}
    assert manager.build_personalization_context({"guest_research": {"cache_status": "failed"}}) == {}


def test_html_email_renderer_is_branded_responsive_and_escapes_guest_content():
    manager = EmailManager()
    rendered = manager._build_html_body(
        "Hi Amina,\n\nVisit https://example.test/episode\n\n<script>alert('no')</script>"
    )

    assert "Mirror Talk" in rendered
    assert "max-width:640px" in rendered
    assert 'href="https://example.test/episode"' in rendered
    assert "<script>" not in rendered
    assert "&lt;script&gt;" in rendered


def test_html_email_renderer_uses_descriptive_text_for_reviewed_and_contextual_links():
    manager = EmailManager()
    rendered = manager._build_html_body(
        "You can also stay connected here:\n"
        "https://mirrortalkpodcast.com/listen-connect/\n\n"
        "- Show notes: https://example.test/episode\n"
        "- Files (download link expires in 2 days): https://example.test/files"
    )

    assert ">Listen and connect with Mirror Talk</a>" in rendered
    assert ">View the episode show notes</a>" in rendered
    assert ">Download your episode files</a>" in rendered
    assert "&gt;" not in rendered


def test_html_email_renderer_keeps_unknown_link_text_visible():
    manager = EmailManager()

    rendered = manager._build_html_body("Reference: https://example.test/reference")

    assert ">https://example.test/reference</a>" in rendered
