"""Migration ledger and schema evolution tests."""

import sqlite3

import pytest

from guest_database_manager.schema_manager import SchemaManager


def _versions(path):
    with sqlite3.connect(path) as conn:
        return [row[0] for row in conn.execute("SELECT version FROM schema_migrations ORDER BY version")]


def test_migrations_apply_to_empty_database_and_are_idempotent(tmp_path):
    db_path = tmp_path / "empty.db"

    SchemaManager.create_tables(str(db_path))
    SchemaManager.create_tables(str(db_path))

    assert _versions(db_path) == [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24]
    with sqlite3.connect(db_path) as conn:
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        guest_columns = {row[1] for row in conn.execute("PRAGMA table_info(guests)")}
        episode_columns = {row[1] for row in conn.execute("PRAGMA table_info(episodes)")}
    assert {
        "guest_applications",
        "audit_events",
        "schema_migrations",
        "calendar_reconciliation_proposals",
        "recommendation_feedback",
        "guest_ai_analyses",
        "recommendation_policies",
        "recommendation_observations",
        "recommendation_outcomes",
        "recommendation_evaluations",
        "recommendation_deployments",
        "recommendation_learning_settings",
        "interview_reschedule_proposals",
        "growth_metric_observations",
        "growth_experiments",
    } <= tables
    assert {"normalized_name", "normalized_email", "row_version", "identity_status", "owner", "marketing_opt_in"} <= guest_columns
    assert {
        "working_title",
        "published_title",
        "transcript_source_id",
        "transcript_synced_at",
        "transcript_match_method",
        "transcript_match_score",
    } <= episode_columns


def test_migrations_backfill_representative_legacy_guest(tmp_path):
    db_path = tmp_path / "legacy.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """CREATE TABLE guests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                full_name TEXT,
                email TEXT,
                is_processed BOOLEAN DEFAULT 0,
                date_added TIMESTAMP,
                date_processed TIMESTAMP,
                original_file_name TEXT,
                original_data TEXT
            )"""
        )
        conn.execute(
            "INSERT INTO guests (name, full_name, email, original_file_name, original_data) VALUES (?, ?, ?, ?, ?)",
            ("Legacy Person", "Legacy Person", " Legacy@Example.com ", "legacy.csv", '{"source":"legacy"}'),
        )

    SchemaManager.create_tables(str(db_path))

    with sqlite3.connect(db_path) as conn:
        application = conn.execute(
            "SELECT source, payload_json, status FROM guest_applications WHERE guest_id = 1"
        ).fetchone()
        identity = conn.execute("SELECT normalized_name, normalized_email FROM guests WHERE id = 1").fetchone()
    assert application == ("legacy.csv", '{"source":"legacy"}', "submitted")
    assert identity == ("legacy person", "legacy@example.com")


def test_title_provenance_migration_backfills_existing_episode_title(tmp_path):
    db_path = tmp_path / "version-eight.db"
    SchemaManager.create_tables(str(db_path))
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "INSERT INTO episodes (guest_name, episode_title) VALUES (?, ?)",
            ("Legacy Guest", "Legacy Editorial Title"),
        )
        conn.execute("UPDATE episodes SET working_title = NULL")
        conn.execute("DELETE FROM schema_migrations WHERE version = 9")

    SchemaManager.create_tables(str(db_path))

    with sqlite3.connect(db_path) as conn:
        title = conn.execute(
            "SELECT episode_title, working_title, published_title FROM episodes"
        ).fetchone()
    assert title == ("Legacy Editorial Title", "Legacy Editorial Title", None)
    assert 9 in _versions(db_path)


def test_failed_migration_rolls_back_its_schema_and_ledger(monkeypatch, tmp_path):
    db_path = tmp_path / "rollback.db"

    def fail_after_write(conn):
        conn.execute("CREATE TABLE should_rollback (id INTEGER PRIMARY KEY)")
        raise RuntimeError("migration failed")

    monkeypatch.setattr(SchemaManager, "_migration_002_domain_history", fail_after_write)

    with pytest.raises(RuntimeError, match="migration failed"):
        SchemaManager.create_tables(str(db_path))

    assert _versions(db_path) == [1]
    with sqlite3.connect(db_path) as conn:
        table = conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'should_rollback'"
        ).fetchone()
    assert table is None


def test_recommendation_learning_migration_rolls_back_all_ddl(monkeypatch, tmp_path):
    db_path = tmp_path / "migration-seventeen.db"
    SchemaManager.create_tables(str(db_path))
    learning_tables = (
        "recommendation_policies",
        "recommendation_observations",
        "recommendation_outcomes",
        "recommendation_evaluations",
        "recommendation_deployments",
        "recommendation_learning_settings",
    )
    with sqlite3.connect(db_path) as conn:
        conn.execute("DELETE FROM schema_migrations WHERE version = 17")
        for table in learning_tables:
            conn.execute(f"DROP TABLE {table}")

    original = SchemaManager._migration_017_recommendation_learning

    def fail_after_all_ddl(conn):
        original(conn)
        raise RuntimeError("migration 17 failed")

    monkeypatch.setattr(SchemaManager, "_migration_017_recommendation_learning", fail_after_all_ddl)
    with pytest.raises(RuntimeError, match="migration 17 failed"):
        SchemaManager.create_tables(str(db_path))

    with sqlite3.connect(db_path) as conn:
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert not set(learning_tables) & tables
    assert 17 not in _versions(db_path)


def test_growth_intelligence_migration_rolls_back_all_ddl(monkeypatch, tmp_path):
    db_path = tmp_path / "migration-twenty-three.db"
    SchemaManager.create_tables(str(db_path))
    growth_tables = ("growth_metric_observations", "growth_experiments")
    with sqlite3.connect(db_path) as conn:
        conn.execute("DELETE FROM schema_migrations WHERE version = 23")
        for table in growth_tables:
            conn.execute(f"DROP TABLE {table}")

    original = SchemaManager._migration_023_growth_intelligence

    def fail_after_all_ddl(conn):
        original(conn)
        raise RuntimeError("migration 23 failed")

    monkeypatch.setattr(SchemaManager, "_migration_023_growth_intelligence", fail_after_all_ddl)
    with pytest.raises(RuntimeError, match="migration 23 failed"):
        SchemaManager.create_tables(str(db_path))

    with sqlite3.connect(db_path) as conn:
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert not set(growth_tables) & tables
    assert 23 not in _versions(db_path)


def test_growth_evidence_integrity_migration_rolls_back_rebuild(monkeypatch, tmp_path):
    db_path = tmp_path / "migration-twenty-four.db"
    SchemaManager.create_tables(str(db_path))
    with sqlite3.connect(db_path) as conn:
        conn.execute("DELETE FROM schema_migrations WHERE version = 24")
        before_sql = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'growth_metric_observations'"
        ).fetchone()[0]

    original = SchemaManager._migration_024_growth_evidence_integrity

    def fail_after_rebuild(conn):
        original(conn)
        raise RuntimeError("migration 24 failed")

    monkeypatch.setattr(SchemaManager, "_migration_024_growth_evidence_integrity", fail_after_rebuild)
    with pytest.raises(RuntimeError, match="migration 24 failed"):
        SchemaManager.create_tables(str(db_path))

    with sqlite3.connect(db_path) as conn:
        after_sql = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'growth_metric_observations'"
        ).fetchone()[0]
        temporary_table = conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'growth_metric_observations_v24'"
        ).fetchone()
    assert after_sql == before_sql
    assert temporary_table is None
    assert 24 not in _versions(db_path)


def test_validation_triggers_reject_invalid_external_statuses(tmp_path):
    db_path = tmp_path / "validated.db"
    SchemaManager.create_tables(str(db_path))

    with sqlite3.connect(db_path) as conn, pytest.raises(sqlite3.IntegrityError, match="invalid interviews.status"):
        conn.execute(
            "INSERT INTO interviews (guest_name, scheduled_for, status) VALUES ('Invalid', '2026-08-10', 'maybe')"
        )


def test_identity_trigger_normalizes_writes_outside_repository(tmp_path):
    db_path = tmp_path / "identity.db"
    SchemaManager.create_tables(str(db_path))

    with sqlite3.connect(db_path) as conn:
        conn.execute("INSERT INTO guests (name, full_name, email) VALUES (' Name ', ' Full Name ', ' EMAIL@Example.com ')")
        identity = conn.execute("SELECT normalized_name, normalized_email FROM guests").fetchone()

    assert identity == ("full name", "email@example.com")
