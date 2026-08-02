"""Documented, source-backed operational KPI computation."""

from __future__ import annotations

import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from guest_database_manager.db_connection import connect_database


METRIC_DEFINITIONS = {
    "guest_decision_lead_hours": {
        "owner": "Podcast producer",
        "source": "guest_applications.submitted_at → decided_at",
        "definition": "Elapsed hours from application receipt to terminal decision.",
    },
    "interview_to_release_days": {
        "owner": "Episode producer",
        "source": "episodes.interview_date/recording_date → release_date",
        "definition": "Elapsed days from recording/interview to explicit release.",
    },
    "application_queue_age_hours": {
        "owner": "Guest producer",
        "source": "open guest_applications.submitted_at",
        "definition": "Age of submitted, triage, or needs-information applications.",
    },
    "confirmation_coverage_pct": {
        "owner": "Booking producer",
        "source": "future active interviews.confirmation_status",
        "definition": "Share of future active interviews explicitly confirmed.",
    },
    "reminder_delivery_pct": {
        "owner": "Booking producer",
        "source": "reminder_log.status",
        "definition": "Share of recorded reminder attempts marked sent.",
    },
    "episode_readiness_pct": {
        "owner": "Episode producer",
        "source": "unreleased episodes.production_status",
        "definition": "Share of unreleased episodes in ready state.",
    },
    "scheduled_coverage_pct": {
        "owner": "Editorial lead",
        "source": "unreleased episodes.release_status",
        "definition": "Share of unreleased episodes with an explicit scheduled state.",
    },
    "on_time_release_pct": {
        "owner": "Editorial lead",
        "source": "episodes.original_planned_release_date → release_date",
        "definition": "Share of released episodes published no later than their immutable first scheduled date.",
    },
}


def _parse(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _distribution(values: Iterable[float]) -> dict[str, float | int | None]:
    ordered = sorted(float(value) for value in values if value >= 0)
    if not ordered:
        return {"count": 0, "median": None, "p90": None}
    midpoint = len(ordered) // 2
    median = ordered[midpoint] if len(ordered) % 2 else (ordered[midpoint - 1] + ordered[midpoint]) / 2
    p90_index = max(0, math.ceil(len(ordered) * 0.9) - 1)
    return {"count": len(ordered), "median": round(median, 2), "p90": round(ordered[p90_index], 2)}


def build_operational_metrics(db_path: str | Path, *, now: datetime | None = None) -> dict[str, Any]:
    """Compute aggregate KPIs without exposing record payloads."""
    reference = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    with connect_database(db_path) as conn:
        applications = conn.execute(
            "SELECT submitted_at, decided_at, status FROM guest_applications"
        ).fetchall()
        episodes = conn.execute(
            "SELECT interview_date, recording_date, release_date, release_status, production_status, "
            "original_planned_release_date FROM episodes"
        ).fetchall()
        interviews = conn.execute(
            "SELECT scheduled_for, status, confirmation_status FROM interviews"
        ).fetchall()
        reminders = conn.execute("SELECT status FROM reminder_log").fetchall()

    decision_hours = []
    queue_hours = []
    for submitted_at, decided_at, status in applications:
        submitted = _parse(submitted_at)
        decided = _parse(decided_at)
        if submitted and decided:
            decision_hours.append((decided - submitted).total_seconds() / 3600)
        elif submitted and status in {"submitted", "triage", "needs_information"}:
            queue_hours.append((reference - submitted).total_seconds() / 3600)

    release_days = []
    unreleased = 0
    ready = 0
    scheduled = 0
    baseline_releases = 0
    on_time_releases = 0
    for interview_date, recording_date, release_date, release_status, production_status, original_planned in episodes:
        start = _parse(recording_date) or _parse(interview_date)
        released = _parse(release_date) if release_status == "released" else None
        if start and released:
            release_days.append((released - start).total_seconds() / 86400)
        planned = _parse(original_planned)
        if released and planned:
            baseline_releases += 1
            on_time_releases += int(released <= planned)
        if release_status != "released":
            unreleased += 1
            ready += int(production_status == "ready")
            scheduled += int(release_status == "scheduled")

    future_active = [
        row for row in interviews
        if row[1] == "scheduled" and (_parse(row[0]) or datetime.min.replace(tzinfo=timezone.utc)) >= reference
    ]
    reminder_total = len(reminders)
    reminder_sent = sum(1 for row in reminders if row[0] == "sent")

    pct = lambda numerator, denominator: round((numerator / denominator) * 100, 1) if denominator else None
    return {
        "generated_at": reference.isoformat(),
        "freshness": "live",
        "definitions": METRIC_DEFINITIONS,
        "values": {
            "guest_decision_lead_hours": _distribution(decision_hours),
            "interview_to_release_days": _distribution(release_days),
            "application_queue_age_hours": _distribution(queue_hours),
            "confirmation_coverage_pct": pct(
                sum(1 for row in future_active if row[2] == "confirmed"), len(future_active)
            ),
            "reminder_delivery_pct": pct(reminder_sent, reminder_total),
            "episode_readiness_pct": pct(ready, unreleased),
            "scheduled_coverage_pct": pct(scheduled, unreleased),
            "on_time_release_pct": pct(on_time_releases, baseline_releases),
        },
        "quality": {
            "missing_decision_timestamps": sum(
                1 for submitted, decided, status in applications
                if status in {"accepted", "declined", "withdrawn"} and not decided
            ),
            "on_time_release_baseline_count": baseline_releases,
            "on_time_release_caveat": None if baseline_releases else "unavailable until a scheduled episode is released",
        },
    }
