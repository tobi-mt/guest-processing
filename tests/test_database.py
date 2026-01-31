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
