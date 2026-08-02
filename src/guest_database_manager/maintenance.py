"""Read-only database integrity and backup verification utilities."""

from __future__ import annotations

import sqlite3
import tempfile
from time import monotonic
from pathlib import Path
from typing import Any

from guest_database_manager.db_connection import connect_database


ALLOWED_GUEST_EMAIL_STATUSES = {"", "accepted", "declined", "rejected", "skipped", "pending"}
ALLOWED_INTERVIEW_STATUSES = {"scheduled", "completed", "cancelled", "no_show"}
ALLOWED_CONFIRMATION_STATUSES = {"pending", "confirmed", "declined", "reschedule_requested"}
ALLOWED_RELEASE_STATUSES = {"unplanned", "scheduled", "released", "archived"}
ALLOWED_PRODUCTION_STATUSES = {"idea", "recorded", "editing", "ready", "released", "archived"}
ALLOWED_PROMOTION_STATUSES = {"unknown", "needs_assets", "ready", "released", "archived"}


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)).fetchone()
    return row is not None


def _count(conn: sqlite3.Connection, sql: str, params: tuple[Any, ...] = ()) -> int:
    return int(conn.execute(sql, params).fetchone()[0])


def build_integrity_report(db_path: str | Path) -> dict[str, Any]:
    """Profile integrity risks without changing the database."""
    path = Path(db_path)
    if not path.exists():
        raise FileNotFoundError(path)

    with connect_database(path) as conn:
        sqlite_integrity = [row[0] for row in conn.execute("PRAGMA integrity_check").fetchall()]
        foreign_key_violations = len(conn.execute("PRAGMA foreign_key_check").fetchall())

        findings: dict[str, int] = {
            "foreign_key_violations": foreign_key_violations,
            "duplicate_guest_emails": 0,
            "duplicate_guest_names": 0,
            "missing_guest_identity": 0,
            "invalid_guest_email_status": 0,
            "orphan_interviews": 0,
            "invalid_interview_status": 0,
            "invalid_confirmation_status": 0,
            "orphan_episode_guests": 0,
            "orphan_episode_interviews": 0,
            "invalid_release_status": 0,
            "invalid_production_status": 0,
            "invalid_promotion_status": 0,
            "conflicting_episode_dates": 0,
        }
        counts: dict[str, int] = {}

        if _table_exists(conn, "guests"):
            counts["guests"] = _count(conn, "SELECT COUNT(*) FROM guests")
            findings["duplicate_guest_emails"] = _count(
                conn,
                "SELECT COUNT(*) FROM (SELECT LOWER(TRIM(email)) FROM guests "
                "WHERE TRIM(COALESCE(email, '')) <> '' GROUP BY LOWER(TRIM(email)) HAVING COUNT(*) > 1)",
            )
            findings["duplicate_guest_names"] = _count(
                conn,
                "SELECT COUNT(*) FROM (SELECT LOWER(TRIM(COALESCE(full_name, name))) FROM guests "
                "WHERE TRIM(COALESCE(full_name, name, '')) <> '' "
                "GROUP BY LOWER(TRIM(COALESCE(full_name, name))) HAVING COUNT(*) > 1)",
            )
            findings["missing_guest_identity"] = _count(
                conn, "SELECT COUNT(*) FROM guests WHERE TRIM(COALESCE(full_name, name, '')) = ''"
            )
            placeholders = ",".join("?" for _ in ALLOWED_GUEST_EMAIL_STATUSES)
            findings["invalid_guest_email_status"] = _count(
                conn,
                f"SELECT COUNT(*) FROM guests WHERE LOWER(TRIM(COALESCE(email_status, ''))) NOT IN ({placeholders})",
                tuple(sorted(ALLOWED_GUEST_EMAIL_STATUSES)),
            )

        if _table_exists(conn, "interviews"):
            counts["interviews"] = _count(conn, "SELECT COUNT(*) FROM interviews")
            if _table_exists(conn, "guests"):
                findings["orphan_interviews"] = _count(
                    conn,
                    "SELECT COUNT(*) FROM interviews i LEFT JOIN guests g ON g.id = i.guest_id "
                    "WHERE i.guest_id IS NOT NULL AND g.id IS NULL",
                )
            placeholders = ",".join("?" for _ in ALLOWED_INTERVIEW_STATUSES)
            findings["invalid_interview_status"] = _count(
                conn,
                f"SELECT COUNT(*) FROM interviews WHERE LOWER(TRIM(COALESCE(status, ''))) NOT IN ({placeholders})",
                tuple(sorted(ALLOWED_INTERVIEW_STATUSES)),
            )
            placeholders = ",".join("?" for _ in ALLOWED_CONFIRMATION_STATUSES)
            findings["invalid_confirmation_status"] = _count(
                conn,
                f"SELECT COUNT(*) FROM interviews WHERE LOWER(TRIM(COALESCE(confirmation_status, ''))) NOT IN ({placeholders})",
                tuple(sorted(ALLOWED_CONFIRMATION_STATUSES)),
            )

        if _table_exists(conn, "episodes"):
            counts["episodes"] = _count(conn, "SELECT COUNT(*) FROM episodes")
            if _table_exists(conn, "guests"):
                findings["orphan_episode_guests"] = _count(
                    conn,
                    "SELECT COUNT(*) FROM episodes e LEFT JOIN guests g ON g.id = e.guest_id "
                    "WHERE e.guest_id IS NOT NULL AND g.id IS NULL",
                )
            if _table_exists(conn, "interviews"):
                findings["orphan_episode_interviews"] = _count(
                    conn,
                    "SELECT COUNT(*) FROM episodes e LEFT JOIN interviews i ON i.id = e.interview_id "
                    "WHERE e.interview_id IS NOT NULL AND i.id IS NULL",
                )
            for key, column, allowed in (
                ("invalid_release_status", "release_status", ALLOWED_RELEASE_STATUSES),
                ("invalid_production_status", "production_status", ALLOWED_PRODUCTION_STATUSES),
                ("invalid_promotion_status", "promotion_status", ALLOWED_PROMOTION_STATUSES),
            ):
                placeholders = ",".join("?" for _ in allowed)
                findings[key] = _count(
                    conn,
                    f"SELECT COUNT(*) FROM episodes WHERE LOWER(TRIM(COALESCE({column}, ''))) NOT IN ({placeholders})",
                    tuple(sorted(allowed)),
                )
            findings["conflicting_episode_dates"] = _count(
                conn,
                "SELECT COUNT(*) FROM episodes WHERE "
                "(LOWER(TRIM(COALESCE(release_status, ''))) = 'scheduled' AND TRIM(COALESCE(release_date, '')) = '') "
                "OR (LOWER(TRIM(COALESCE(release_status, ''))) = 'released' AND TRIM(COALESCE(release_date, '')) = '')",
            )

    issue_count = sum(findings.values()) + (0 if sqlite_integrity == ["ok"] else len(sqlite_integrity))
    return {
        "database": str(path),
        "status": "ok" if issue_count == 0 else "issues_found",
        "sqlite_integrity": sqlite_integrity,
        "counts": counts,
        "findings": findings,
        "issue_count": issue_count,
    }


def is_database_ready(report: dict[str, Any]) -> bool:
    """Treat review queues as warnings while blocking corrupt or invalid state."""
    blocking_findings = {
        "foreign_key_violations",
        "missing_guest_identity",
        "invalid_guest_email_status",
        "orphan_interviews",
        "invalid_interview_status",
        "invalid_confirmation_status",
        "orphan_episode_guests",
        "orphan_episode_interviews",
        "invalid_release_status",
        "invalid_production_status",
        "invalid_promotion_status",
        "conflicting_episode_dates",
    }
    return report.get("sqlite_integrity") == ["ok"] and not any(
        int(report.get("findings", {}).get(key, 0)) for key in blocking_findings
    )


def verify_backup_restore(db_path: str | Path) -> dict[str, Any]:
    """Create a temporary SQLite backup, restore it, and compare table counts."""
    source_path = Path(db_path)
    if not source_path.exists():
        raise FileNotFoundError(source_path)

    with tempfile.TemporaryDirectory(prefix="guest-db-restore-check-") as temp_dir:
        backup_path = Path(temp_dir) / "backup.db"
        restored_path = Path(temp_dir) / "restored.db"
        with connect_database(source_path) as source, connect_database(backup_path) as backup:
            source.backup(backup)
        with connect_database(backup_path) as backup, connect_database(restored_path) as restored:
            backup.backup(restored)

        source_report = build_integrity_report(source_path)
        restored_report = build_integrity_report(restored_path)
        counts_match = source_report["counts"] == restored_report["counts"]
        restored_ok = restored_report["sqlite_integrity"] == ["ok"]
        return {
            "status": "ok" if counts_match and restored_ok else "failed",
            "counts_match": counts_match,
            "source_counts": source_report["counts"],
            "restored_counts": restored_report["counts"],
            "restored_integrity": restored_report["sqlite_integrity"],
        }


def build_sqlite_scale_report(db_path: str | Path) -> dict[str, Any]:
    """Measure observable SQLite exit signals without changing the source."""
    source_path = Path(db_path)
    if not source_path.exists():
        raise FileNotFoundError(source_path)
    started = monotonic()
    with tempfile.TemporaryDirectory(prefix="guest-db-scale-") as temp_dir:
        backup_path = Path(temp_dir) / "scale-check.db"
        with connect_database(source_path) as source, connect_database(backup_path) as backup:
            source.backup(backup)
    backup_seconds = monotonic() - started
    database_bytes = source_path.stat().st_size
    thresholds = {"database_bytes": 5 * 1024**3, "backup_seconds": 5 * 60}
    breached = [
        name
        for name, value in {"database_bytes": database_bytes, "backup_seconds": backup_seconds}.items()
        if value > thresholds[name]
    ]
    return {
        "database": str(source_path),
        "database_bytes": database_bytes,
        "backup_seconds": round(backup_seconds, 4),
        "thresholds": thresholds,
        "breached_observable_signals": breached,
        "postgres_rehearsal_authorized": False,
        "note": "Authorize a PostgreSQL rehearsal only after the full operational gate in SCALE_AND_POSTGRES.md is met.",
    }
