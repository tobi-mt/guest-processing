# SPDX-FileCopyrightText: 2024-present Guest Database Manager <admin@example.com>
#
# SPDX-License-Identifier: MIT
"""Tests for the database module."""

import sqlite3

import pytest

# from guest_database_manager.database import GuestDatabase


def test_database_initialization(temp_db):
    """Test database initialization."""
    assert temp_db.db_path.exists()

    # Check that the table was created
    stats = temp_db.get_guest_stats()
    assert stats['total'] == 0
    assert stats['processed'] == 0
    assert stats['unprocessed'] == 0


def test_add_guest_from_csv(temp_db, sample_csv_file):
    """Test adding guests from CSV file."""
    result = temp_db.add_guest_from_csv(sample_csv_file)

    assert result['imported'] == 3
    assert result['updated'] == 0
    assert result['errors'] == 0

    # Verify guests were added
    stats = temp_db.get_guest_stats()
    assert stats['total'] == 3


def test_get_all_guests(temp_db, sample_csv_file):
    """Test retrieving all guests."""
    temp_db.add_guest_from_csv(sample_csv_file)

    guests_list = temp_db.get_all_guests()
    assert len(guests_list) == 3
    names = [g['name'] for g in guests_list]
    full_names = [g['full_name'] for g in guests_list]
    assert 'John Doe' in names
    assert 'Jane Smith' in names
    assert 'Alice Johnson' in full_names


def test_mark_guest_processed(temp_db, sample_csv_file):
    """Test marking a guest as processed."""
    temp_db.add_guest_from_csv(sample_csv_file)

    guests_list = temp_db.get_all_guests()
    guest_id = guests_list[0]['id']

    # Mark as processed
    temp_db.mark_guest_processed(guest_id)

    # Verify status changed
    stats = temp_db.get_guest_stats()
    assert stats['processed'] == 1
    assert stats['unprocessed'] == 2


def test_mark_guest_unprocessed(temp_db, sample_csv_file):
    """Test marking a guest as unprocessed."""
    temp_db.add_guest_from_csv(sample_csv_file)

    guests_list = temp_db.get_all_guests()
    guest_id = guests_list[0]['id']

    # Mark as processed then unprocessed
    temp_db.mark_guest_processed(guest_id)
    temp_db.mark_guest_unprocessed(guest_id)

    # Verify status changed back
    stats = temp_db.get_guest_stats()
    assert stats['processed'] == 0
    assert stats['unprocessed'] == 3


def test_delete_guest(temp_db, sample_csv_file):
    """Test deleting a guest."""
    temp_db.add_guest_from_csv(sample_csv_file)

    guests_list = temp_db.get_all_guests()
    guest_id = guests_list[0]['id']

    # Delete guest
    temp_db.delete_guest(guest_id)

    # Verify guest was deleted
    stats = temp_db.get_guest_stats()
    assert stats['total'] == 2


def test_clean_database(temp_db):
    """Test database cleaning."""
    result = temp_db.clean_database()
    assert isinstance(result, dict)
    assert 'removed' in result
    assert 'fixed' in result


def test_import_stores_source_metadata(temp_db, sample_csv_file):
    """Imported guests should keep the source file name for analytics and traceability."""
    temp_db.add_guest_from_csv(sample_csv_file)

    guests_list = temp_db.get_all_guests()
    assert guests_list
    assert all(guest["original_file_name"] == sample_csv_file.name for guest in guests_list)
    assert all(guest["original_data"] for guest in guests_list)


def test_accept_and_reject_without_email_set_status(temp_db, sample_csv_file):
    """Manual decisions without email should still set a meaningful guest status."""
    temp_db.add_guest_from_csv(sample_csv_file)
    guests_list = temp_db.get_all_guests()

    first_guest_id = guests_list[0]["id"]
    second_guest_id = guests_list[1]["id"]

    temp_db.accept_guest_without_email(first_guest_id)
    temp_db.reject_guest_without_email(second_guest_id)

    accepted_guest = temp_db.get_guest_by_id(first_guest_id)
    rejected_guest = temp_db.get_guest_by_id(second_guest_id)

    assert accepted_guest["is_processed"] == 1
    assert accepted_guest["email_status"] == "accepted"
    assert accepted_guest["email_sent_at"] is None

    assert rejected_guest["is_processed"] == 1
    assert rejected_guest["email_status"] == "rejected"
    assert rejected_guest["email_sent_at"] is None


def test_upsert_guest_avoids_duplicate_entries_by_email(temp_db):
    """Manual and web flows should update an existing guest instead of inserting duplicates."""
    first_id, first_action = temp_db.upsert_guest(
        {
            "full_name": "Jordan Rivers",
            "email": "jordan@example.com",
            "background": "Original background",
            "is_processed": False,
        }
    )
    second_id, second_action = temp_db.upsert_guest(
        {
            "full_name": "Jordan Rivers",
            "email": "jordan@example.com",
            "background": "Updated background",
            "profession": "Coach",
            "is_processed": False,
        }
    )

    assert first_action == "created"
    assert second_action == "updated"
    assert first_id == second_id
    assert temp_db.get_stats()["total"] == 1

    guest = temp_db.get_guest_by_id(first_id)
    assert guest["background"] == "Updated background"
    assert guest["profession"] == "Coach"


def test_upsert_guest_preserves_original_source_metadata(temp_db):
    """Updating an existing guest should not replace their original source label."""
    first_id, _ = temp_db.upsert_guest(
        {
            "full_name": "Jordan Rivers",
            "email": "jordan@example.com",
            "background": "Original background",
            "original_file_name": "legacy-import.xlsx",
            "original_data": '{"source":"legacy"}',
            "is_processed": False,
        }
    )
    temp_db.upsert_guest(
        {
            "full_name": "Jordan Rivers",
            "email": "jordan@example.com",
            "background": "Updated background",
            "original_file_name": "Soulful Guest Questionnaire(1-45).xlsx",
            "original_data": '{"source":"new"}',
            "is_processed": False,
        }
    )

    guest = temp_db.get_guest_by_id(first_id)
    assert guest["original_file_name"] == "legacy-import.xlsx"
    assert guest["original_data"] == '{"source":"legacy"}'


def test_upsert_interview_uses_calendar_event_id(temp_db):
    """Interviews should update in place when they come from the same calendar event."""
    first_id, first_action = temp_db.upsert_interview(
        {
            "guest_name": "Amina Hart",
            "guest_email": "amina@example.com",
            "calendar_event_id": "event_123",
            "title": "Mirror Talk Conversation",
            "scheduled_for": "2026-04-07 17:00:00",
            "timezone": "Europe/Berlin",
        }
    )
    second_id, second_action = temp_db.upsert_interview(
        {
            "guest_name": "Amina Hart",
            "guest_email": "amina@example.com",
            "calendar_event_id": "event_123",
            "title": "Updated Mirror Talk Conversation",
            "scheduled_for": "2026-04-07 17:30:00",
            "timezone": "Europe/Berlin",
            "join_url": "https://riverside.fm/example",
        }
    )

    assert first_action == "created"
    assert second_action == "updated"
    assert first_id == second_id

    interview = temp_db.get_interview_by_id(first_id)
    assert interview["title"] == "Updated Mirror Talk Conversation"
    assert interview["join_url"] == "https://riverside.fm/example"


def test_upsert_episode_and_log_reminder(temp_db):
    """Episode planning and reminder logging should live outside guest intake records."""
    interview_id, _ = temp_db.upsert_interview(
        {
            "guest_name": "Jordan Rivers",
            "guest_email": "jordan@example.com",
            "calendar_event_id": "event_episode",
            "title": "Jordan Rivers Interview",
            "scheduled_for": "2026-04-08 17:00:00",
        }
    )
    episode_id, action = temp_db.upsert_episode(
        {
            "interview_id": interview_id,
            "guest_name": "Jordan Rivers",
            "guest_email": "jordan@example.com",
            "episode_title": "Healing Through Hard Seasons",
            "topic": "Healing",
            "category": "Personal Growth",
            "interview_date": "2026-04-08",
            "release_date": "2026-04-14 17:00:00",
            "release_status": "scheduled",
            "production_status": "recorded",
            "priority_score": 8.5,
        }
    )

    assert action == "created"
    episode = temp_db.get_episode_by_id(episode_id)
    assert episode["episode_title"] == "Healing Through Hard Seasons"
    assert episode["working_title"] == "Healing Through Hard Seasons"
    assert episode["release_status"] == "scheduled"

    log_id = temp_db.log_reminder(
        interview_id=interview_id,
        reminder_type="weekly_confirmation",
        sent_to="jordan@example.com",
        status="sent",
        provider="resend",
    )

    assert log_id > 0
    reminder_log = temp_db.get_reminder_log(interview_id)
    assert len(reminder_log) == 1
    assert reminder_log[0]["provider"] == "resend"

    stats = temp_db.get_operations_stats()
    assert stats["interviews_total"] == 1
    assert stats["episodes_total"] == 1
    assert stats["episodes_scheduled"] == 1
    assert stats["reminders_sent"] == 1


def test_delete_interview_and_episode(temp_db):
    """Interview and episode records should be removable from the operations store."""
    interview_id, _ = temp_db.upsert_interview(
        {
            "guest_name": "Jordan Rivers",
            "guest_email": "jordan@example.com",
            "title": "Jordan Rivers and Tobi Ojekunle",
            "scheduled_for": "2026-04-08 17:00:00",
        }
    )
    episode_id, _ = temp_db.upsert_episode(
        {
            "interview_id": interview_id,
            "guest_name": "Jordan Rivers",
            "guest_email": "jordan@example.com",
            "episode_title": "Healing Through Hard Seasons",
            "topic": "Healing",
        }
    )

    temp_db.delete_episode(episode_id)
    temp_db.delete_interview(interview_id)

    assert temp_db.get_episode_by_id(episode_id) is None
    assert temp_db.get_interview_by_id(interview_id) is None


def test_import_skips_blank_rows_and_blank_header_columns(temp_db, tmp_path):
    """Guest imports should ignore empty rows and unnamed empty columns."""
    csv_path = tmp_path / "guests-with-blank-rows.csv"
    csv_path.write_text(
        "Full name,Email,,Website\n"
        "Jordan Rivers,jordan@example.com,,https://jordan.example.com\n"
        ",,,\n",
        encoding="utf-8",
    )

    result = temp_db.import_from_file(str(csv_path))

    guests = temp_db.get_all_guests()
    assert result["imported"] == 1
    assert result["skipped"] == 1
    assert len(guests) == 1
    assert guests[0]["full_name"] == "Jordan Rivers"
    assert guests[0]["original_data"] == '{"Full name": "Jordan Rivers", "Email": "jordan@example.com", "Website": "https://jordan.example.com"}'


def test_clean_database_merges_duplicate_episode_rows(temp_db):
    """Episode cleanup should merge duplicate archive rows conservatively."""
    with sqlite3.connect(str(temp_db.db_path)) as conn:
        cursor = conn.execute(
            """
            INSERT INTO episodes (
                guest_name, guest_email, episode_title, topic, release_date, release_status,
                legacy_episode_number, source_file_name, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (
                "Confessions Series",
                "",
                "Hello Fear, My Old Friend",
                "Hello Fear, My Old Friend",
                "2025-06-07",
                "released",
                "363",
                "MT Guest List - 2025.csv",
            ),
        )
        first_id = cursor.lastrowid
        cursor = conn.execute(
            """
            INSERT INTO episodes (
                guest_name, guest_email, episode_title, topic, release_date, release_status,
                transcript_text, source_file_name, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (
                "Confessions Series",
                "",
                "Different Wrong Title",
                "Hello Fear, My Old Friend",
                "2025-06-07",
                "released",
                "A richer transcript that should be preserved.",
                "MT Guest List - 2025.csv",
            ),
        )
        second_id = cursor.lastrowid
        conn.commit()

    assert first_id != second_id

    result = temp_db.clean_database()
    episodes = temp_db.list_episodes()

    assert result["episodes_merged"] == 1
    assert result["episodes_removed"] == 1
    assert len(episodes) == 1
    assert episodes[0]["legacy_episode_number"] == "363"
    assert episodes[0]["episode_title"] == "Hello Fear, My Old Friend"
    assert episodes[0]["transcript_text"] == "A richer transcript that should be preserved."


def test_clean_database_merges_placeholder_title_episode_with_richer_duplicate(temp_db):
    """Cleanup should merge same-guest interview duplicates when one title is only a guest-name placeholder."""
    with sqlite3.connect(str(temp_db.db_path)) as conn:
        cursor = conn.execute(
            """
            INSERT INTO episodes (
                guest_name, guest_email, episode_title, topic, interview_date, release_status, source_file_name, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (
                "Brent Freeman",
                "brent@example.com",
                "Brent Freeman",
                "",
                "2026-04-10",
                "unplanned",
                "queue.csv",
            ),
        )
        first_id = cursor.lastrowid
        cursor = conn.execute(
            """
            INSERT INTO episodes (
                guest_name, guest_email, episode_title, topic, interview_date, release_status, source_file_name, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (
                "Brent Freeman",
                "brent@example.com",
                "Brent Kesler: Financial Intelligence - Mapping Out The Millionaire Mystery",
                "",
                "2026-04-10",
                "unplanned",
                "queue.csv",
            ),
        )
        second_id = cursor.lastrowid
        conn.commit()

    assert first_id != second_id

    result = temp_db.clean_database()
    episodes = temp_db.list_episodes()

    assert result["episodes_merged"] == 1
    assert result["episodes_removed"] == 1
    assert len(episodes) == 1
    assert episodes[0]["episode_title"] == "Brent Kesler: Financial Intelligence - Mapping Out The Millionaire Mystery"


def test_database_connections_enforce_foreign_keys(temp_db):
    """Core database writes must reject orphaned relationship rows."""
    with pytest.raises(sqlite3.IntegrityError), temp_db._connect() as conn:
        conn.execute(
            "INSERT INTO interviews (guest_id, guest_name, scheduled_for) VALUES (?, ?, ?)",
            (999999, "Orphan Guest", "2026-08-10 10:00:00"),
        )


def test_reapplication_preserves_prior_application_decision(temp_db):
    guest_id = temp_db.insert_guest(
        {"full_name": "Repeat Applicant", "email": "repeat@example.com", "original_file_name": "first.csv"}
    )
    accepted = temp_db.transition_latest_guest_application(guest_id, "accepted", reason="Strong fit")

    repeated_id, action = temp_db.upsert_guest(
        {
            "full_name": "Repeat Applicant",
            "email": "repeat@example.com",
            "original_file_name": "Website Intake Questionnaire",
            "original_data": '{"submission":2}',
        }
    )

    applications = list(reversed(temp_db.list_guest_applications(guest_id)))
    assert repeated_id == guest_id
    assert action == "updated"
    assert [item["status"] for item in applications] == ["accepted", "submitted"]
    assert applications[0]["decision_reason"] == "Strong fit"
    assert accepted["row_version"] == 2


def test_application_transition_appends_attributable_audit_event(temp_db):
    guest_id = temp_db.insert_guest({"full_name": "Audited Applicant", "email": "audit@example.com"})
    application = temp_db.list_guest_applications(guest_id)[0]

    updated = temp_db.transition_latest_guest_application(
        guest_id,
        "declined",
        reason="Topic overlap",
        actor="producer@example.com",
        source="test",
    )

    events = temp_db.list_audit_events("application", application["id"])
    assert updated["status"] == "declined"
    assert events[0]["event_type"] == "status_changed"
    assert events[0]["actor"] == "producer@example.com"
    assert events[0]["source"] == "test"
    assert events[0]["reason"] == "Topic overlap"


def test_guest_update_rejects_stale_row_version(temp_db):
    guest_id = temp_db.insert_guest({"full_name": "Concurrent Guest", "email": "first@example.com"})
    stale = temp_db.get_guest_by_id(guest_id)
    current = dict(stale)
    current["email"] = "current@example.com"
    temp_db.update_guest_by_id(guest_id, current)

    stale["email"] = "stale@example.com"
    with pytest.raises(RuntimeError, match="changed by another request"):
        temp_db.update_guest_by_id(guest_id, stale)

    assert temp_db.get_guest_by_id(guest_id)["email"] == "current@example.com"


def test_episode_update_rejects_stale_row_version(temp_db):
    episode_id, _ = temp_db.upsert_episode(
        {"guest_name": "Concurrent Episode", "episode_title": "Version One"}
    )
    stale = temp_db.get_episode_by_id(episode_id)
    current = dict(stale)
    current["episode_title"] = "Version Two"
    temp_db.upsert_episode(current)

    stale["episode_title"] = "Stale Version"
    with pytest.raises(RuntimeError, match="changed by another request"):
        temp_db.upsert_episode(stale)

    assert temp_db.get_episode_by_id(episode_id)["episode_title"] == "Version Two"


def test_episode_sequence_renumbering_is_atomic_on_concurrent_change(temp_db):
    first_id, _ = temp_db.upsert_episode(
        {"guest_name": "First Sequence Guest", "episode_title": "First Sequence Episode"}
    )
    second_id, _ = temp_db.upsert_episode(
        {"guest_name": "Second Sequence Guest", "episode_title": "Second Sequence Episode"}
    )
    first = temp_db.get_episode_by_id(first_id)
    second = temp_db.get_episode_by_id(second_id)

    with pytest.raises(RuntimeError, match="changed by another request"):
        temp_db.update_episode_sequence_numbers(
            [
                (first_id, "501", first["row_version"]),
                (second_id, "502", second["row_version"] + 1),
            ]
        )

    assert temp_db.get_episode_by_id(first_id)["legacy_episode_number"] is None
    assert temp_db.get_episode_by_id(second_id)["legacy_episode_number"] is None
    assert all(
        event["event_type"] != "sequence_renumbered"
        for event in temp_db.list_audit_events("episode", first_id)
    )


def test_episode_lifecycle_changes_create_before_after_audit_events(temp_db):
    episode_id, _ = temp_db.upsert_episode(
        {
            "guest_name": "Lifecycle Guest",
            "episode_title": "Lifecycle Episode",
            "production_status": "editing",
            "release_status": "unplanned",
        }
    )
    episode = temp_db.get_episode_by_id(episode_id)
    episode["production_status"] = "ready"

    temp_db.upsert_episode(episode)

    events = list(reversed(temp_db.list_audit_events("episode", episode_id)))
    assert [event["event_type"] for event in events] == ["created", "status_changed"]
    assert '"production_status": "editing"' in events[1]["before_json"]
    assert '"production_status": "ready"' in events[1]["after_json"]


def test_recommendation_feedback_is_reversible_audited_and_idempotent(temp_db):
    episode_id, _ = temp_db.upsert_episode(
        {"guest_name": "Editorial Guest", "episode_title": "Editorial Episode"}
    )

    rejected = temp_db.record_recommendation_feedback(
        episode_id,
        action="rejected",
        reason="Too similar to a recent episode",
        actor="editor@example.com",
        idempotency_key="reject-request-1",
        recommendation_version="release-planner-v1",
        recommendation_snapshot={"priority_score": 84},
    )
    duplicate = temp_db.record_recommendation_feedback(
        episode_id,
        action="rejected",
        reason="Too similar to a recent episode",
        actor="editor@example.com",
        idempotency_key="reject-request-1",
    )

    assert duplicate["id"] == rejected["id"]
    assert temp_db.get_latest_recommendation_feedback()[episode_id]["action"] == "rejected"
    temp_db.record_recommendation_feedback(
        episode_id,
        action="restored",
        reason="Editorial timing changed",
        actor="editor@example.com",
        idempotency_key="restore-request-1",
    )
    assert temp_db.get_latest_recommendation_feedback([episode_id])[episode_id]["action"] == "restored"
    events = temp_db.list_audit_events("episode", episode_id)
    assert [events[0]["event_type"], events[1]["event_type"]] == [
        "recommendation_restored",
        "recommendation_rejected",
    ]


def test_recommendation_rejection_requires_reason(temp_db):
    episode_id, _ = temp_db.upsert_episode(
        {"guest_name": "Reason Guest", "episode_title": "Reason Episode"}
    )
    with pytest.raises(ValueError, match="reason is required"):
        temp_db.record_recommendation_feedback(episode_id, action="rejected")


@pytest.mark.parametrize(
    ("method_name", "status", "event_type"),
    [
        ("accept_guest_with_email", "accepted", "accepted_email_sent"),
        ("reject_guest_with_email", "rejected", "declined_email_sent"),
    ],
)
def test_emailed_guest_decisions_use_attributed_lifecycle_boundary(
    temp_db, method_name, status, event_type
):
    guest_id = temp_db.insert_guest({"full_name": "Email Decision", "email": "decision@example.com"})

    getattr(temp_db, method_name)(guest_id, "Reviewed wording")

    guest = temp_db.get_guest_by_id(guest_id)
    event = temp_db.list_audit_events("guest", guest_id)[0]
    assert guest["email_status"] == status
    assert guest["row_version"] == 2
    assert guest["email_sent_at"]
    assert event["event_type"] == event_type
    assert event["reason"] == "Reviewed wording"


def test_identity_merge_preserves_history_and_tombstone(temp_db):
    survivor = temp_db.insert_guest({"full_name": "Same Person", "email": "same@example.com"})
    duplicate = temp_db.insert_guest({"full_name": "Same Person Duplicate", "email": "same@example.com"})

    candidates = temp_db.list_identity_merge_candidates()
    assert any(group["match_type"] == "exact_email" for group in candidates)

    result = temp_db.merge_guest_identities(survivor, duplicate, reason="Verified duplicate applications")

    assert result == {"survivor_id": survivor, "merged_id": duplicate, "status": "merged"}
    assert temp_db.get_guest_by_id(duplicate)["merged_into_guest_id"] == survivor
    assert temp_db.get_guest_by_id(duplicate)["identity_status"] == "merged"
    assert len(temp_db.list_guest_applications(survivor)) == 2
    assert duplicate not in {guest["id"] for guest in temp_db.get_all_guests()}
    assert temp_db.list_audit_events("guest_identity", duplicate)[0]["event_type"] == "merged"


def test_identity_merge_rejects_unrelated_guests(temp_db):
    first = temp_db.insert_guest({"full_name": "First Person", "email": "first@example.com"})
    second = temp_db.insert_guest({"full_name": "Second Person", "email": "second@example.com"})

    with pytest.raises(ValueError, match="do not share"):
        temp_db.merge_guest_identities(first, second, reason="No match")
