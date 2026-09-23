"""Read-only, cross-workspace exception intelligence."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from guest_database_manager.db_connection import connect_database
from guest_database_manager.maintenance import build_integrity_report


FINDING_LABELS = {
    "foreign_key_violations": ("critical", "Broken database relationships", "/dashboard"),
    "duplicate_guest_emails": ("high", "Guest emails needing identity review", "/dashboard"),
    "duplicate_guest_names": ("normal", "Guest names needing identity review", "/dashboard"),
    "missing_guest_identity": ("critical", "Guests missing an identity", "/dashboard"),
    "invalid_guest_email_status": ("high", "Guests with invalid decision states", "/dashboard"),
    "orphan_interviews": ("critical", "Interviews missing their guest", "/operations"),
    "invalid_interview_status": ("critical", "Interviews with invalid states", "/operations"),
    "invalid_confirmation_status": ("high", "Interviews with invalid confirmations", "/operations"),
    "orphan_episode_guests": ("critical", "Episodes missing their guest", "/planning"),
    "orphan_episode_interviews": ("high", "Episodes missing their interview", "/planning"),
    "invalid_release_status": ("critical", "Episodes with invalid release states", "/planning"),
    "invalid_production_status": ("critical", "Episodes with invalid production states", "/planning"),
    "invalid_promotion_status": ("critical", "Episodes with invalid promotion states", "/planning"),
    "conflicting_episode_dates": ("critical", "Released or scheduled episodes missing dates", "/planning"),
}


def _item(
    key: str,
    *,
    severity: str,
    category: str,
    title: str,
    reason: str,
    href: str,
    action_label: str,
    count: int = 1,
) -> dict[str, Any]:
    return {
        "key": key,
        "severity": severity,
        "category": category,
        "title": title,
        "reason": reason,
        "href": href,
        "action_label": action_label,
        "count": int(count),
    }


def build_exception_center(
    db_path: str | Path,
    *,
    action_queue: dict[str, Any],
    growth: dict[str, Any],
    operations_alerts: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Combine integrity, delivery, evidence, and urgent workflow exceptions."""
    report = build_integrity_report(db_path)
    items: list[dict[str, Any]] = []
    for finding, count in report.get("findings", {}).items():
        count = int(count or 0)
        if not count:
            continue
        severity, title, href = FINDING_LABELS.get(
            finding, ("normal", finding.replace("_", " ").title(), "/dashboard")
        )
        items.append(_item(
            f"integrity:{finding}",
            severity=severity,
            category="data_integrity",
            title=title,
            reason=f"{count} record{'s' if count != 1 else ''} require review. The system has not changed them automatically.",
            href=href,
            action_label="Review records",
            count=count,
        ))

    with connect_database(db_path) as conn:
        tables = {str(row[0]) for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        if "email_outbox" in tables:
            failed = int(conn.execute(
                "SELECT COUNT(*) FROM email_outbox WHERE status IN ('failed', 'dead_letter')"
            ).fetchone()[0])
            if failed:
                items.append(_item(
                    "delivery:failed",
                    severity="high",
                    category="delivery",
                    title="Communications requiring operator review",
                    reason=f"{failed} failed or dead-letter communication{'s' if failed != 1 else ''} remain unsent.",
                    href="/operations",
                    action_label="Review delivery",
                    count=failed,
                ))
        if "episodes" in tables:
            columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(episodes)")}
            if "transcript_text" in columns:
                missing_transcripts = int(conn.execute(
                    """SELECT COUNT(*) FROM episodes
                       WHERE LOWER(TRIM(COALESCE(release_status, ''))) IN ('scheduled', 'released')
                       AND TRIM(COALESCE(transcript_text, '')) = ''"""
                ).fetchone()[0])
                if missing_transcripts:
                    items.append(_item(
                        "content:missing_transcript",
                        severity="normal",
                        category="content",
                        title="Published workflow missing transcripts",
                        reason=f"{missing_transcripts} scheduled or released episode{'s' if missing_transcripts != 1 else ''} have no transcript.",
                        href="/planning?tab=release_planning",
                        action_label="Review episodes",
                        count=missing_transcripts,
                    ))
            if "promotion_status" in columns:
                missing_assets = int(conn.execute(
                    """SELECT COUNT(*) FROM episodes
                       WHERE LOWER(TRIM(COALESCE(release_status, ''))) IN ('scheduled', 'released')
                       AND LOWER(TRIM(COALESCE(promotion_status, ''))) IN ('unknown', 'needs_assets')"""
                ).fetchone()[0])
                if missing_assets:
                    items.append(_item(
                        "content:missing_assets", severity="high", category="content",
                        title="Release workflow missing promotional assets",
                        reason=f"{missing_assets} scheduled or released episode{'s' if missing_assets != 1 else ''} still need promotional assets.",
                        href="/planning?tab=release_planning", action_label="Review assets", count=missing_assets,
                    ))
        if "guests" in tables:
            guest_columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(guests)")}
            if "guest_research_updated_at" in guest_columns:
                stale_research = int(conn.execute(
                    """SELECT COUNT(*) FROM guests
                       WHERE TRIM(COALESCE(guest_research, '')) != ''
                       AND (guest_research_updated_at IS NULL
                            OR datetime(guest_research_updated_at) < datetime('now', '-90 days'))"""
                ).fetchone()[0])
                if stale_research:
                    items.append(_item(
                        "evidence:stale_research", severity="normal", category="evidence",
                        title="Guest research needs refreshing",
                        reason=f"{stale_research} guest research record{'s' if stale_research != 1 else ''} are older than 90 days or have no freshness date.",
                        href="/dashboard", action_label="Refresh research", count=stale_research,
                    ))

    alerts = operations_alerts or {}
    double_bookings = alerts.get("double_bookings") or []
    if double_bookings:
        booking_count = sum(int(item.get("count") or 0) for item in double_bookings)
        items.append(_item(
            "calendar:double_bookings", severity="critical", category="calendar",
            title="Guests have overlapping future bookings",
            reason=f"{len(double_bookings)} guest{'s' if len(double_bookings) != 1 else ''} appear across {booking_count} active interview slots.",
            href="/operations", action_label="Resolve bookings", count=len(double_bookings),
        ))
    cleanup = alerts.get("calendar_cleanup") or []
    if cleanup:
        items.append(_item(
            "calendar:cleanup", severity="high", category="calendar",
            title="Calendar events conflict with interview status",
            reason=f"{len(cleanup)} declined, rescheduled, or cancelled interview{'s' if len(cleanup) != 1 else ''} still have calendar events.",
            href="/operations", action_label="Review calendar", count=len(cleanup),
        ))

    quality = growth.get("quality") or {}
    observation_count = int(quality.get("observation_count") or 0)
    if observation_count == 0:
        items.append(_item(
            "evidence:no_growth_data",
            severity="high",
            category="evidence",
            title="Growth intelligence has no evidence",
            reason="Recommendations cannot learn from release outcomes until verified analytics are imported.",
            href="/planning?tab=scheduling_intelligence#analytics-import",
            action_label="Import analytics",
        ))
    elif growth.get("freshness") == "stale":
        items.append(_item(
            "evidence:stale_growth_data",
            severity="normal",
            category="evidence",
            title="Growth evidence is stale",
            reason=f"The latest imported period ended {growth.get('latest_period_end') or 'on an unknown date'}.",
            href="/planning?tab=scheduling_intelligence#analytics-import",
            action_label="Refresh evidence",
        ))
    incomplete_scores = sum(
        1 for score in growth.get("episode_scores", [])
        if (score.get("mfs") or {}).get("status") != "ready"
    )
    if incomplete_scores:
        items.append(_item(
            "evidence:incomplete_mfs",
            severity="normal",
            category="evidence",
            title="Episodes missing complete Mirror Fan Score evidence",
            reason=f"{incomplete_scores} episode{'s' if incomplete_scores != 1 else ''} lack one or more required outcome dimensions.",
            href="/planning?tab=scheduling_intelligence#analytics-import",
            action_label="Review evidence",
            count=incomplete_scores,
        ))

    for action in action_queue.get("items", []):
        if action.get("priority") != "urgent":
            continue
        items.append(_item(
            f"workflow:{action.get('key')}",
            severity="high",
            category="workflow",
            title=str(action.get("next_action") or "Workflow exception"),
            reason=f"{action.get('title')}: {action.get('reason')}",
            href=str(action.get("href") or "/dashboard"),
            action_label=str(action.get("action_label") or "Review"),
        ))

    severity_order = {"critical": 0, "high": 1, "normal": 2}
    items.sort(key=lambda item: (severity_order.get(item["severity"], 3), item["category"], item["title"].casefold()))
    counts = {
        severity: sum(item["count"] for item in items if item["severity"] == severity)
        for severity in ("critical", "high", "normal")
    }
    counts["total"] = sum(item["count"] for item in items)
    return {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "status": "clear" if not items else "attention",
        "counts": counts,
        "items": items,
        "integrity": {
            "status": report.get("status"),
            "sqlite_integrity": report.get("sqlite_integrity"),
        },
    }
