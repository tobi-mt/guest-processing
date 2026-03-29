"""Episode import and recommendation helpers for podcast operations."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime, timedelta
from io import StringIO
from typing import Any, Dict, Iterable, List


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _parse_legacy_date(value: str) -> str:
    text = _clean_text(value)
    if not text:
        return ""

    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d.%m.%Y"):
        try:
            return datetime.strptime(text, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return text


def _normalize_row(row: Dict[str, Any]) -> Dict[str, str]:
    return {_clean_text(key): _clean_text(value) for key, value in row.items() if key is not None}


def _map_queue_status_to_production_status(status: str) -> str:
    normalized = _clean_text(status).lower()
    if normalized in {"processing", "restoring"}:
        return "editing"
    if normalized:
        return "recorded"
    return "ready"


def _detect_source_type(filename: str) -> str:
    lowered = filename.lower()
    if "not yet released" in lowered:
        return "release_queue"
    return "released_archive"


def parse_episode_import_csv(content: bytes, filename: str) -> List[Dict[str, Any]]:
    """Convert a legacy episode CSV into normalized episode records."""
    text = content.decode("utf-8-sig")
    reader = csv.DictReader(StringIO(text))
    source_type = _detect_source_type(filename)
    episodes: List[Dict[str, Any]] = []

    for raw_row in reader:
        row = _normalize_row(raw_row)
        guest_name = row.get("Name") or row.get("Names") or ""
        topic = row.get("Topic", "")
        category = row.get("Category", "")
        release_date = _parse_legacy_date(row.get("Release Date", ""))
        interview_date = _parse_legacy_date(row.get("Interview Date", ""))
        legacy_episode_number = row.get("Episode Number") or row.get("") or ""
        riverside_status = row.get("Riverside FM Status", "")

        if not guest_name and not topic:
            continue

        episodes.append(
            {
                "guest_name": guest_name,
                "guest_email": row.get("Email", ""),
                "website": row.get("Website", ""),
                "episode_title": topic or guest_name,
                "topic": topic,
                "category": category,
                "interview_date": interview_date,
                "recording_date": interview_date,
                "release_date": release_date,
                "release_status": "released" if release_date and source_type == "released_archive" else "unplanned",
                "production_status": (
                    "released"
                    if release_date and source_type == "released_archive"
                    else _map_queue_status_to_production_status(riverside_status)
                ),
                "priority_score": 0,
                "recommendation_reason": "",
                "legacy_episode_number": legacy_episode_number,
                "riverside_status": riverside_status,
                "source_file_name": filename,
                "source_type": source_type,
                "notes": "",
            }
        )

    return episodes


def next_release_slot(reference: datetime) -> datetime:
    """Return the next Tuesday 17:00 slot at or after the reference date."""
    candidate = reference.replace(hour=17, minute=0, second=0, microsecond=0)
    days_until_tuesday = (1 - candidate.weekday()) % 7
    candidate = candidate + timedelta(days=days_until_tuesday)
    if candidate < reference:
        candidate += timedelta(days=7)
    return candidate


@dataclass
class RecommendationContext:
    released_history: List[Dict[str, Any]]
    queue: List[Dict[str, Any]]
    reference: datetime


def _parse_episode_date(value: Any) -> datetime | None:
    text = _clean_text(value)
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


def build_release_recommendations(
    episodes: Iterable[Dict[str, Any]],
    *,
    reference: datetime,
    limit: int = 5,
) -> List[Dict[str, Any]]:
    """Recommend the next episodes to release based on Mirror Talk history."""
    episodes = list(episodes)
    released_history = [
        episode for episode in episodes
        if _clean_text(episode.get("release_status")).lower() == "released" or _parse_episode_date(episode.get("release_date"))
    ]
    queue = [
        episode for episode in episodes
        if _clean_text(episode.get("release_status")).lower() != "released"
    ]
    if not queue:
        return []

    released_history = sorted(
        released_history,
        key=lambda item: _parse_episode_date(item.get("release_date")) or datetime.min,
        reverse=True,
    )
    recent_categories = [
        _clean_text(item.get("category"))
        for item in released_history[:8]
        if _clean_text(item.get("category"))
    ]
    category_counts: Dict[str, int] = {}
    for item in released_history:
        category = _clean_text(item.get("category"))
        if category:
            category_counts[category] = category_counts.get(category, 0) + 1

    ranked: List[Dict[str, Any]] = []
    for episode in queue:
        category = _clean_text(episode.get("category"))
        interview_date = _parse_episode_date(episode.get("interview_date"))
        production_status = _clean_text(episode.get("production_status")).lower()
        riverside_status = _clean_text(episode.get("riverside_status")).lower()

        score = 0.0
        reasons: List[str] = []

        if production_status == "ready":
            score += 34
            reasons.append("ready to publish")
        elif production_status == "recorded":
            score += 26
            reasons.append("recorded and likely ready for scheduling")
        elif production_status == "editing":
            score += 12
            reasons.append("already in post-production")
        else:
            score += 4

        if interview_date:
            age_days = max((reference.date() - interview_date.date()).days, 0)
            age_score = min(age_days / 14, 24)
            score += age_score
            if age_days >= 90:
                reasons.append("has been waiting a long time")

        if category:
            if category not in recent_categories[:4]:
                score += 10
                reasons.append(f"adds variety beyond the most recent {len(recent_categories[:4])} releases")
            else:
                score -= 6

            category_frequency = category_counts.get(category, 0)
            if category_frequency <= 8:
                score += 6
                reasons.append(f"helps surface a less-frequent {category} conversation")
            elif category_frequency >= 40:
                score -= 3

        if riverside_status in {"processing", "restoring"}:
            score -= 8
            reasons.append(f"Riverside still marked as {riverside_status}")

        if _clean_text(episode.get("website")):
            score += 2
        if _clean_text(episode.get("legacy_episode_number")):
            score += 1

        enriched = dict(episode)
        enriched["priority_score"] = round(score, 1)
        enriched["recommendation_reason"] = "; ".join(dict.fromkeys(reasons)) or "good fit for the next available slot"
        ranked.append(enriched)

    ranked.sort(
        key=lambda item: (
            -float(item.get("priority_score") or 0),
            _parse_episode_date(item.get("interview_date")) or datetime.max,
            _clean_text(item.get("guest_name")),
        )
    )

    slot = next_release_slot(reference)
    for item in ranked[:limit]:
        item["recommended_release_date"] = slot.strftime("%Y-%m-%d %H:%M:%S")
        slot += timedelta(days=7)

    return ranked[:limit]
