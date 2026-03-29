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
    normalized: Dict[str, str] = {}
    for key, value in row.items():
        header = _clean_text(key)
        if not header:
            continue
        normalized[header] = _clean_text(value)
    return normalized


def _map_queue_status_to_production_status(status: str) -> str:
    normalized = _clean_text(status).lower()
    if normalized in {"processing", "restoring"}:
        return "editing"
    if normalized:
        return "recorded"
    return "ready"


def _infer_promotion_status(
    *,
    source_type: str,
    production_status: str,
    website: str,
    guest_email: str,
    topic: str,
    category: str,
) -> str:
    """Infer whether an episode is likely promotion-ready."""
    if source_type == "released_archive":
        return "released"

    if production_status in {"editing", "idea"}:
        return "needs_assets"

    metadata_ready = all([guest_email, topic or category])
    if production_status == "ready" and metadata_ready:
        return "ready"

    if website and metadata_ready:
        return "ready"

    return "needs_assets"


def _detect_source_type(filename: str) -> str:
    lowered = filename.lower()
    if "not yet released" in lowered:
        return "release_queue"
    return "released_archive"


def _infer_release_status(*, release_date: str, source_type: str, reference: datetime) -> str:
    """Decide whether an imported episode is already released or still scheduled."""
    parsed_release = _parse_episode_date(release_date)
    if not parsed_release:
        return "unplanned"
    if parsed_release.date() > reference.date():
        return "scheduled"
    if source_type == "released_archive":
        return "released"
    return "scheduled"


def parse_episode_import_csv(content: bytes, filename: str, *, reference: datetime | None = None) -> List[Dict[str, Any]]:
    """Convert a legacy episode CSV into normalized episode records."""
    text = content.decode("utf-8-sig")
    reader = csv.DictReader(StringIO(text))
    source_type = _detect_source_type(filename)
    reference = reference or datetime.now()
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
        release_status = _infer_release_status(
            release_date=release_date,
            source_type=source_type,
            reference=reference,
        )
        production_status = (
            "released"
            if release_status == "released"
            else "ready"
            if release_status == "scheduled"
            else _map_queue_status_to_production_status(riverside_status)
        )
        promotion_status = _infer_promotion_status(
            source_type=source_type,
            production_status=production_status,
            website=row.get("Website", ""),
            guest_email=row.get("Email", ""),
            topic=topic,
            category=category,
        )

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
                "release_status": release_status,
                "production_status": production_status,
                "promotion_status": promotion_status,
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


SEASONAL_THEME_KEYWORDS: Dict[int, tuple[str, ...]] = {
    1: ("purpose", "new", "begin", "habit", "goal", "vision", "intentional"),
    2: ("relationship", "love", "marriage", "friendship", "connection", "family"),
    3: ("mental", "healing", "anxiety", "renewal", "spring", "mindset"),
    4: ("growth", "leadership", "career", "business", "purpose", "faith"),
    5: ("family", "mother", "parent", "home", "community", "care"),
    6: ("men", "father", "summer", "freedom", "health", "wellness"),
    7: ("rest", "travel", "adventure", "joy", "wellness", "lifestyle"),
    8: ("school", "discipline", "focus", "productivity", "career", "learning"),
    9: ("identity", "change", "courage", "resilience", "purpose", "business"),
    10: ("story", "transformation", "healing", "mindset", "mental", "faith"),
    11: ("gratitude", "giving", "service", "finance", "legacy", "impact"),
    12: ("reflection", "family", "hope", "faith", "joy", "year"),
}


def _month_theme_score(episode: Dict[str, Any], slot_date: datetime) -> tuple[float, str]:
    """Score how well an episode fits the seasonal mood of the month."""
    topic = _clean_text(episode.get("topic")).lower()
    title = _clean_text(episode.get("episode_title")).lower()
    category = _clean_text(episode.get("category")).lower()
    haystack = " ".join([title, topic, category])
    keywords = SEASONAL_THEME_KEYWORDS.get(slot_date.month, ())
    matched = [keyword for keyword in keywords if keyword in haystack]
    if not matched:
        return 0.0, ""
    return 8.0, f"fits the seasonal focus for {slot_date.strftime('%B')}"


def _promotion_readiness_score(episode: Dict[str, Any]) -> tuple[float, str]:
    """Reward episodes that already look promotion-ready."""
    promotion_status = _clean_text(episode.get("promotion_status")).lower()
    if promotion_status in {"ready", "released"}:
        return 14.0, "promotion assets look ready"
    if promotion_status == "needs_assets":
        return -10.0, "still needs promo assets before release"
    return -2.0, "promotion readiness is still unclear"


def _guest_recency_penalty(episode: Dict[str, Any], recent_releases: List[Dict[str, Any]]) -> tuple[float, str]:
    """Avoid back-to-back appearances from the same guest."""
    guest_name = _clean_text(episode.get("guest_name")).casefold()
    if not guest_name:
        return 0.0, ""

    for offset, released in enumerate(recent_releases[:12], start=1):
        released_guest = _clean_text(released.get("guest_name")).casefold()
        if released_guest and released_guest == guest_name:
            if offset <= 4:
                return -18.0, "same guest appeared very recently"
            return -8.0, "same guest has already been featured not long ago"
    return 4.0, "keeps guest voices varied"


def _category_fatigue_score(episode: Dict[str, Any], recent_categories: List[str]) -> tuple[float, str]:
    """Penalize categories that have dominated the recent release window."""
    category = _clean_text(episode.get("category"))
    if not category:
        return 0.0, ""

    recent_window = recent_categories[:10]
    category_hits = sum(1 for item in recent_window if item == category)
    if category_hits >= 4:
        return -14.0, f"{category} has shown up heavily in the recent release window"
    if category_hits >= 2:
        return -6.0, f"{category} is already warm in the recent release mix"
    return 8.0, f"helps balance the current release mix beyond {category}"


def _base_episode_score(
    episode: Dict[str, Any],
    *,
    reference: datetime,
    released_history: List[Dict[str, Any]],
    category_counts: Dict[str, int],
    recent_categories: List[str],
) -> tuple[float, List[str]]:
    """Build a strong baseline score before slot-specific adjustments."""
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
        score += 24
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

    category_score, category_reason = _category_fatigue_score(episode, recent_categories)
    score += category_score
    if category_reason:
        reasons.append(category_reason)

    if category:
        category_frequency = category_counts.get(category, 0)
        if category_frequency <= 8:
            score += 6
            reasons.append(f"helps surface a less-frequent {category} conversation")
        elif category_frequency >= 40:
            score -= 4
            reasons.append(f"{category} already dominates the long-term archive")

    if riverside_status in {"processing", "restoring"}:
        score -= 8
        reasons.append(f"Riverside still marked as {riverside_status}")

    promotion_score, promotion_reason = _promotion_readiness_score(episode)
    score += promotion_score
    if promotion_reason:
        reasons.append(promotion_reason)

    guest_score, guest_reason = _guest_recency_penalty(episode, released_history)
    score += guest_score
    if guest_reason:
        reasons.append(guest_reason)

    if _clean_text(episode.get("website")):
        score += 2
    if _clean_text(episode.get("legacy_episode_number")):
        score += 1

    return score, reasons


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
        if _clean_text(episode.get("release_status")).lower() == "released"
    ]
    queue = [
        episode for episode in episodes
        if _clean_text(episode.get("release_status")).lower() not in {"released", "scheduled"}
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

    base_ranked: List[Dict[str, Any]] = []
    for episode in queue:
        base_score, reasons = _base_episode_score(
            episode,
            reference=reference,
            released_history=released_history,
            category_counts=category_counts,
            recent_categories=recent_categories,
        )
        enriched = dict(episode)
        enriched["base_priority_score"] = round(base_score, 1)
        enriched["base_recommendation_reasons"] = list(dict.fromkeys(reasons))
        base_ranked.append(enriched)

    slot = next_release_slot(reference)
    selected: List[Dict[str, Any]] = []
    remaining = list(base_ranked)
    simulated_recent_categories = list(recent_categories)
    simulated_recent_guests = [
        _clean_text(item.get("guest_name")).casefold()
        for item in released_history[:8]
        if _clean_text(item.get("guest_name"))
    ]

    while remaining and len(selected) < limit:
        scored_candidates: List[Dict[str, Any]] = []
        for episode in remaining:
            score = float(episode.get("base_priority_score") or 0)
            reasons = list(episode.get("base_recommendation_reasons") or [])

            season_score, season_reason = _month_theme_score(episode, slot)
            score += season_score
            if season_reason:
                reasons.append(season_reason)

            category = _clean_text(episode.get("category"))
            guest_name = _clean_text(episode.get("guest_name")).casefold()

            if category and category not in simulated_recent_categories[:4]:
                score += 7
                reasons.append("keeps the next release run varied")
            elif category:
                score -= 5

            if guest_name and guest_name not in simulated_recent_guests[:6]:
                score += 3
            elif guest_name:
                score -= 6
                reasons.append("another recent appearance from the same guest voice")

            candidate = dict(episode)
            candidate["priority_score"] = round(score, 1)
            candidate["recommendation_reason"] = "; ".join(dict.fromkeys(reasons)) or "good fit for the next available slot"
            candidate["recommended_release_date"] = slot.strftime("%Y-%m-%d %H:%M:%S")
            scored_candidates.append(candidate)

        scored_candidates.sort(
            key=lambda item: (
                -float(item.get("priority_score") or 0),
                _parse_episode_date(item.get("interview_date")) or datetime.max,
                _clean_text(item.get("guest_name")),
            )
        )

        chosen = scored_candidates[0]
        selected.append(chosen)
        remaining = [item for item in remaining if item is not chosen and item.get("id") != chosen.get("id")]

        chosen_category = _clean_text(chosen.get("category"))
        if chosen_category:
            simulated_recent_categories.insert(0, chosen_category)
        chosen_guest = _clean_text(chosen.get("guest_name")).casefold()
        if chosen_guest:
            simulated_recent_guests.insert(0, chosen_guest)
        slot += timedelta(days=7)

    return selected
