# SPDX-FileCopyrightText: 2024-present Guest Database Manager <admin@example.com>
#
# SPDX-License-Identifier: MIT
"""Tests for the database module."""

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
    import sqlite3

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
    import sqlite3

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
