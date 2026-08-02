"""Shared SQLite connection policy tests."""

from guest_database_manager.db_connection import connect_database


def test_shared_connection_enforces_integrity_and_busy_timeout():
    with connect_database(":memory:") as conn:
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert conn.execute("PRAGMA busy_timeout").fetchone()[0] == 5000
