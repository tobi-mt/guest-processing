"""Transactional outbox reliability tests."""

from threading import Event

import pytest

from guest_database_manager.database import GuestDatabase
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


def test_continuous_worker_starts_processes_and_stops(monkeypatch, temp_db):
    service = GuestWebService(temp_db.db_path)
    processed = Event()
    monkeypatch.setattr(service, "process_pending_email_outbox", lambda **kwargs: processed.set())

    service.start_outbox_worker(interval_seconds=1)
    assert processed.wait(timeout=1)
    service.stop_outbox_worker(timeout_seconds=1)

    assert service._outbox_thread is not None
    assert not service._outbox_thread.is_alive()
