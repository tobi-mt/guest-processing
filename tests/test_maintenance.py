"""Tests for read-only integrity and recovery verification."""

import sqlite3

from guest_database_manager.maintenance import (
    build_integrity_report,
    build_sqlite_scale_report,
    is_database_ready,
    verify_backup_restore,
)


def test_integrity_report_is_read_only_and_detects_duplicates(temp_db):
    temp_db.insert_guest({"full_name": "Duplicate Person", "email": "one@example.com"})
    temp_db.insert_guest({"full_name": "duplicate person", "email": "two@example.com"})

    report = build_integrity_report(temp_db.db_path)

    assert report["status"] == "issues_found"
    assert report["findings"]["duplicate_guest_names"] == 1
    assert report["counts"]["guests"] == 2
    assert len(temp_db.get_all_guests()) == 2


def test_integrity_report_detects_orphan_when_foreign_keys_were_bypassed(temp_db):
    with sqlite3.connect(str(temp_db.db_path)) as conn:
        conn.execute(
            "INSERT INTO interviews (guest_id, guest_name, scheduled_for) VALUES (999999, 'Orphan', '2026-08-10')"
        )

    report = build_integrity_report(temp_db.db_path)

    assert report["findings"]["orphan_interviews"] == 1
    assert report["findings"]["foreign_key_violations"] == 1


def test_backup_restore_verification_preserves_counts(temp_db):
    temp_db.insert_guest({"full_name": "Backup Person", "email": "backup@example.com"})

    result = verify_backup_restore(temp_db.db_path)

    assert result["status"] == "ok"
    assert result["counts_match"] is True
    assert result["source_counts"] == result["restored_counts"]


def test_scale_report_measures_observable_exit_signals(temp_db):
    report = build_sqlite_scale_report(temp_db.db_path)

    assert report["database_bytes"] > 0
    assert report["backup_seconds"] >= 0
    assert report["breached_observable_signals"] == []
    assert report["postgres_rehearsal_authorized"] is False


def test_duplicate_review_findings_do_not_make_service_unready():
    report = {"sqlite_integrity": ["ok"], "findings": {"duplicate_guest_emails": 2}}
    assert is_database_ready(report)


def test_invalid_lifecycle_state_makes_service_unready():
    report = {"sqlite_integrity": ["ok"], "findings": {"invalid_release_status": 1}}
    assert not is_database_ready(report)
