"""Episode import and recommendation helpers for podcast operations."""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from io import StringIO
from typing import Any, Dict, Iterable, List


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _slug_words(value: str) -> list[str]:
    """Return meaningful title-case words from a text field."""
    words = [part.strip(" ,.-") for part in _clean_text(value).split()]
    return [word for word in words if word]


def _transcript_sentences(episode: Dict[str, Any], limit: int = 3) -> list[str]:
    """Extract a few grounded transcript sentences for drafting help."""
    transcript = _clean_text(episode.get("transcript_text"))
    if not transcript:
        return []
    sentences = [part.strip() for part in transcript.replace("\n", " ").split(".") if part.strip()]
    return [sentence for sentence in sentences if len(sentence.split()) >= 6][:limit]


def _guest_research_payload(value: Any) -> Dict[str, Any]:
    """Parse guest research JSON or dicts into a stable payload."""
    if isinstance(value, dict):
        return value
    text = _clean_text(value)
    if not text:
        return {}
    try:
        parsed = json.loads(text)
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _topic_like_text(value: str, guest_name: str) -> str:
    """Return topic text only when it carries more meaning than the guest name itself."""
    text = _clean_text(value)
    guest = _clean_text(guest_name)
    if not text:
        return ""
    text_words = {word.casefold() for word in _slug_words(text)}
    guest_words = {word.casefold() for word in _slug_words(guest)}
    if not text_words:
        return ""
    if guest_words and len(text_words - guest_words) < 2:
        return ""
    return text


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


def _reserved_release_slots(episodes: Iterable[Dict[str, Any]], *, reference: datetime) -> set[datetime]:
    """Collect future scheduled release dates that should reserve recommendation slots."""
    reserved: set[datetime] = set()
    for episode in episodes:
        if _clean_text(episode.get("release_status")).lower() != "scheduled":
            continue
        scheduled_release = _parse_episode_date(episode.get("release_date"))
        if not scheduled_release or scheduled_release < reference:
            continue
        reserved.add(scheduled_release.replace(second=0, microsecond=0))
    return reserved


def _next_available_release_slot(reference: datetime, reserved_slots: set[datetime]) -> datetime:
    """Return the next recommendation slot that is not already reserved."""
    slot = next_release_slot(reference)
    while slot.replace(second=0, microsecond=0) in reserved_slots:
        slot = next_release_slot(slot + timedelta(seconds=1))
    return slot


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


def _month_theme_score(episode: Dict[str, Any], slot_date: datetime) -> tuple[float, str, List[str]]:
    """Score how well an episode fits the seasonal mood of the month."""
    topic = _clean_text(episode.get("topic")).lower()
    title = _clean_text(episode.get("episode_title")).lower()
    category = _clean_text(episode.get("category")).lower()
    haystack = " ".join([title, topic, category])
    keywords = SEASONAL_THEME_KEYWORDS.get(slot_date.month, ())
    matched = [keyword for keyword in keywords if keyword in haystack]
    if not matched:
        return 0.0, "", []
    return 8.0, f"fits the seasonal focus for {slot_date.strftime('%B')}", matched


def _promotion_readiness_score(episode: Dict[str, Any]) -> tuple[float, str]:
    """Reward episodes that already look promotion-ready."""
    promotion_status = _clean_text(episode.get("promotion_status")).lower()
    if promotion_status in {"ready", "released"}:
        return 14.0, "promotion assets look ready"
    if promotion_status == "needs_assets":
        return -10.0, "still needs promo assets before release"
    return -2.0, "promotion readiness is still unclear"


def build_promotion_readiness(episode: Dict[str, Any]) -> Dict[str, Any]:
    """Return a deterministic promotion-readiness summary from stored episode fields."""
    score = 0
    strengths: list[str] = []
    blockers: list[str] = []

    episode_title = _clean_text(episode.get("episode_title"))
    topic = _clean_text(episode.get("topic"))
    category = _clean_text(episode.get("category"))
    guest_name = _clean_text(episode.get("guest_name"))
    guest_email = _clean_text(episode.get("guest_email"))
    website = _clean_text(episode.get("website"))
    show_notes_url = _clean_text(episode.get("show_notes_url"))
    release_files_url = _clean_text(episode.get("release_files_url"))
    recommendation_reason = _clean_text(episode.get("recommendation_reason"))
    production_status = _clean_text(episode.get("production_status")).lower()
    promotion_status = _clean_text(episode.get("promotion_status")).lower()
    release_status = _clean_text(episode.get("release_status")).lower()

    if release_status == "released":
        if episode_title:
            strengths.append("episode is already published")
        if show_notes_url:
            strengths.append("show notes link is live")
        if release_files_url:
            strengths.append("guest files link is ready")
        if guest_name and guest_email:
            strengths.append("guest follow-up details are complete")
        return {
            "score": 100,
            "label": "Released",
            "strengths": strengths[:4] or ["episode is already published"],
            "blockers": [],
        }

    if episode_title:
        score += 14
        strengths.append("episode title is set")
    else:
        blockers.append("episode title is still missing")

    if topic:
        score += 12
        strengths.append("topic is clearly defined")
    else:
        blockers.append("topic is still missing")

    if category:
        score += 10
        strengths.append("category is assigned")
    else:
        blockers.append("category is still missing")

    if guest_name and guest_email:
        score += 12
        strengths.append("guest details are complete")
    elif guest_name:
        score += 5
        blockers.append("guest email is still missing")
    else:
        blockers.append("guest details are incomplete")

    if website:
        score += 4
    if recommendation_reason:
        score += 4

    if production_status == "ready":
        score += 18
        strengths.append("production is marked ready")
    elif production_status == "editing":
        score += 8
        blockers.append("episode is still in editing")
    elif production_status == "recorded":
        score += 5
        blockers.append("episode is recorded but not marked ready")
    else:
        blockers.append("production stage is still too early")

    if promotion_status in {"ready", "released"}:
        score += 18
        strengths.append("promotion assets are marked ready")
    elif promotion_status == "needs_assets":
        blockers.append("promotion assets are still missing")
    else:
        blockers.append("promotion readiness has not been confirmed")

    if show_notes_url:
        score += 6
        strengths.append("show notes link is ready")
    if release_files_url:
        score += 6
        strengths.append("guest files link is ready")

    score = max(0, min(100, score))
    if score >= 80:
        label = "Ready to publish"
    elif score >= 60:
        label = "Nearly ready"
    elif score >= 40:
        label = "Needs prep"
    else:
        label = "Blocked"

    return {
        "score": score,
        "label": label,
        "strengths": strengths[:4],
        "blockers": blockers[:4],
    }


def build_episode_title_suggestions(episode: Dict[str, Any]) -> list[str]:
    """Generate grounded title variants from the stored episode fields."""
    guest_name = _clean_text(episode.get("guest_name"))
    topic = _clean_text(episode.get("topic")) or _clean_text(episode.get("episode_title"))
    category = _clean_text(episode.get("category"))
    transcript_sentences = _transcript_sentences(episode, limit=1)

    if not topic:
        return []

    core_topic = " ".join(_slug_words(topic)[:8]).strip()
    transcript_phrase = ""
    if transcript_sentences:
        transcript_phrase = " ".join(_slug_words(transcript_sentences[0])[:6]).strip()
    if not core_topic:
        return []

    suggestions = [
        core_topic,
        f"{core_topic} with {guest_name}" if guest_name else "",
        f"Mirror Talk: {core_topic}",
        f"{core_topic} | Mirror Talk",
        f"{category}: {core_topic}" if category else "",
        transcript_phrase if transcript_phrase and transcript_phrase.casefold() != core_topic.casefold() else "",
    ]

    unique: list[str] = []
    seen = set()
    for suggestion in suggestions:
        cleaned = suggestion.strip()
        key = cleaned.casefold()
        if cleaned and key not in seen:
            seen.add(key)
            unique.append(cleaned)
    return unique[:4]


def build_episode_copy_assist(episode: Dict[str, Any]) -> Dict[str, str]:
    """Build simple, grounded promo copy from the episode record."""
    guest_name = _clean_text(episode.get("guest_name")) or "our guest"
    topic = _topic_like_text(episode.get("topic"), guest_name)
    if not topic:
        topic = _topic_like_text(episode.get("episode_title"), guest_name)
    category = _clean_text(episode.get("category"))
    episode_title = _clean_text(episode.get("episode_title")) or topic or guest_name
    transcript_sentences = _transcript_sentences(episode, limit=2)
    guest_research = _guest_research_payload(episode.get("guest_research"))
    research_topics = [str(item).strip() for item in guest_research.get("likely_topics", []) if str(item).strip()]
    research_summary = _clean_text(guest_research.get("summary"))

    if topic:
        summary = f"{guest_name} joins Mirror Talk for a conversation about {topic.lower()}."
        social_caption = f"New on Mirror Talk: {episode_title}. {guest_name} joins us to explore {topic.lower()}."
        newsletter_blurb = f"This week on Mirror Talk, {guest_name} joins us for {topic.lower()}."
    elif research_topics:
        topic_list = ", ".join(research_topics[:3]).lower()
        summary = f"{guest_name} joins Mirror Talk for a conversation shaped by their public work in {topic_list}."
        social_caption = f"New on Mirror Talk: {episode_title}. {guest_name} brings perspective on {topic_list}."
        newsletter_blurb = f"This week on Mirror Talk, {guest_name} joins us with grounded perspective on {topic_list}."
    else:
        summary = f"{guest_name} joins Mirror Talk for a thoughtful conversation."
        social_caption = f"New on Mirror Talk: {episode_title}. {guest_name} joins us for a thoughtful conversation."
        newsletter_blurb = f"This week on Mirror Talk, we are joined by {guest_name} for a thoughtful conversation."
    if category:
        summary += f" The episode sits within our {category} conversations."
    if transcript_sentences:
        summary += f" In the conversation, {transcript_sentences[0][0].lower() + transcript_sentences[0][1:] if len(transcript_sentences[0]) > 1 else transcript_sentences[0].lower()}."
    elif research_summary and research_summary.casefold() not in summary.casefold():
        summary += f" Public profile research suggests: {research_summary}"

    show_notes_intro = transcript_sentences[0] if transcript_sentences else summary
    quote_pull = transcript_sentences[1] if len(transcript_sentences) > 1 else ""

    return {
        "summary": summary,
        "social_caption": social_caption,
        "newsletter_blurb": newsletter_blurb,
        "show_notes_intro": show_notes_intro,
        "quote_pull": quote_pull,
    }


def _theme_keyword_set(episode: Dict[str, Any]) -> set[str]:
    """Extract lightweight topical keywords from episode metadata."""
    source = " ".join(
        [
            _clean_text(episode.get("episode_title")),
            _clean_text(episode.get("topic")),
            _clean_text(episode.get("category")),
        ]
    ).casefold()
    tokens: set[str] = set()
    for raw in source.replace(",", " ").replace(".", " ").replace("/", " ").split():
        token = raw.strip(" -_")
        if len(token) >= 5:
            tokens.add(token)
    return tokens


def _archive_overlap_warning(episode: Dict[str, Any], released_history: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Compare an episode with the released archive and classify the overlap."""
    current_title = _clean_text(episode.get("episode_title"))
    current_category = _clean_text(episode.get("category"))
    current_keywords = _theme_keyword_set(episode)
    if not current_keywords:
        return {"status": "clear", "message": "", "matched_episode": ""}

    best_match: Dict[str, Any] | None = None
    best_overlap = 0

    for released in released_history[:40]:
        released_keywords = _theme_keyword_set(released)
        overlap = len(current_keywords.intersection(released_keywords))
        if overlap > best_overlap:
            best_overlap = overlap
            best_match = released

    if not best_match or best_overlap < 2:
        return {"status": "clear", "message": "", "matched_episode": ""}

    matched_title = _clean_text(best_match.get("episode_title")) or _clean_text(best_match.get("topic")) or "a past episode"
    matched_category = _clean_text(best_match.get("category"))
    same_category = bool(current_category and matched_category and current_category == matched_category)

    if best_overlap >= 4 and same_category:
        return {
            "status": "risky",
            "message": f"very close to the released archive, especially {matched_title}",
            "matched_episode": matched_title,
        }
    return {
        "status": "revisit",
        "message": f"touches a familiar theme from {matched_title}, but may still work as a fresh revisit",
        "matched_episode": matched_title,
    }


def _recent_topic_cluster_warning(episode: Dict[str, Any], released_history: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Warn when a topic cluster is already overrepresented in the last 10 releases."""
    recent_releases = released_history[:10]
    current_keywords = _theme_keyword_set(episode)
    if not current_keywords:
        return {"status": "clear", "message": ""}

    cluster_hits = 0
    for released in recent_releases:
        overlap = current_keywords.intersection(_theme_keyword_set(released))
        if len(overlap) >= 2:
            cluster_hits += 1

    if cluster_hits >= 3:
        return {
            "status": "warm",
            "message": "this topic cluster is already warm across the last 10 released episodes",
        }
    if cluster_hits >= 1:
        return {
            "status": "active",
            "message": "this theme has appeared recently in the last 10 released episodes",
        }
    return {"status": "clear", "message": ""}


def apply_sequence_warnings(recommendations: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Flag multi-week sequencing risks across the selected recommendation run."""
    category_counts: Dict[str, int] = {}
    guest_counts: Dict[str, int] = {}

    for episode in recommendations:
        category = _clean_text(episode.get("category"))
        guest = _clean_text(episode.get("guest_name")).casefold()
        if category:
            category_counts[category] = category_counts.get(category, 0) + 1
        if guest:
            guest_counts[guest] = guest_counts.get(guest, 0) + 1

    enriched: List[Dict[str, Any]] = []
    for index, episode in enumerate(recommendations):
        warnings = list(episode.get("watchouts") or [])
        category = _clean_text(episode.get("category"))
        guest = _clean_text(episode.get("guest_name")).casefold()
        current_keywords = _theme_keyword_set(episode)

        if category and category_counts.get(category, 0) >= 2:
            warnings.append("this category appears more than once in the current recommended run")
        if guest and guest_counts.get(guest, 0) >= 2:
            warnings.append("this guest appears more than once in the current recommended run")

        if index > 0:
            previous = recommendations[index - 1]
            previous_keywords = _theme_keyword_set(previous)
            overlap = current_keywords.intersection(previous_keywords)
            if len(overlap) >= 2:
                warnings.append("this topic overlaps heavily with the previous recommended release")

        if index < len(recommendations) - 1:
            next_episode = recommendations[index + 1]
            next_keywords = _theme_keyword_set(next_episode)
            overlap = current_keywords.intersection(next_keywords)
            if len(overlap) >= 2:
                warnings.append("the following week may feel too similar in topic or framing")

        enriched_episode = dict(episode)
        enriched_episode["sequence_warnings"] = list(dict.fromkeys(warnings))[:4]
        enriched.append(enriched_episode)

    return enriched


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
    reserved_slots = _reserved_release_slots(episodes, reference=reference)

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

    slot = _next_available_release_slot(reference, reserved_slots)
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
            why_now = list(reasons)
            watchouts: List[str] = []

            season_score, season_reason, season_keywords = _month_theme_score(episode, slot)
            score += season_score
            if season_reason:
                reasons.append(season_reason)
                why_now.append(season_reason)

            category = _clean_text(episode.get("category"))
            guest_name = _clean_text(episode.get("guest_name")).casefold()

            if category and category not in simulated_recent_categories[:4]:
                score += 7
                reasons.append("keeps the next release run varied")
                why_now.append("keeps the next release run varied")
            elif category:
                score -= 5
                watchouts.append("category is already close to the current release mix")

            if guest_name and guest_name not in simulated_recent_guests[:6]:
                score += 3
            elif guest_name:
                score -= 6
                reasons.append("another recent appearance from the same guest voice")
                watchouts.append("guest voice is still fresh in the recent archive")

            readiness = build_promotion_readiness(episode)
            if readiness["score"] >= 60:
                why_now.extend(readiness["strengths"][:2])
            else:
                watchouts.extend(readiness["blockers"][:2])

            guest_research = _guest_research_payload(episode.get("guest_research"))
            research_topics = [str(item).strip() for item in guest_research.get("likely_topics", []) if str(item).strip()]
            research_signals = [str(item).strip() for item in guest_research.get("timely_signals", []) if str(item).strip()]
            if research_topics:
                score += min(5.0, float(len(research_topics)))
                why_now.append(f"public profile suggests useful audience hooks around {', '.join(research_topics[:3]).lower()}")
            if research_signals:
                score += min(4.0, float(len(research_signals)))
                why_now.append(research_signals[0])

            archive_overlap = _archive_overlap_warning(episode, released_history)
            if archive_overlap["status"] == "risky":
                score -= 10
                watchouts.append(archive_overlap["message"])
            elif archive_overlap["status"] == "revisit":
                why_now.append(archive_overlap["message"])

            topic_cluster = _recent_topic_cluster_warning(episode, released_history)
            if topic_cluster["status"] == "warm":
                score -= 8
                watchouts.append(topic_cluster["message"])
            elif topic_cluster["status"] == "active":
                watchouts.append(topic_cluster["message"])

            candidate = dict(episode)
            candidate["priority_score"] = round(score, 1)
            candidate["recommendation_reason"] = "; ".join(dict.fromkeys(reasons)) or "good fit for the next available slot"
            candidate["recommended_release_date"] = slot.strftime("%Y-%m-%d %H:%M:%S")
            candidate["why_now"] = list(dict.fromkeys(why_now))[:4]
            candidate["watchouts"] = list(dict.fromkeys(watchouts))[:4]
            candidate["promotion_readiness"] = readiness
            candidate["title_suggestions"] = build_episode_title_suggestions(episode)
            candidate["copy_assist"] = build_episode_copy_assist(episode)
            candidate["archive_overlap"] = archive_overlap
            candidate["topic_cluster_warning"] = topic_cluster
            candidate["seasonal_fit"] = (
                {
                    "month": slot.strftime("%B"),
                    "reason": season_reason,
                    "matched_keywords": season_keywords,
                }
                if season_reason
                else None
            )
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
        reserved_slots.add(slot.replace(second=0, microsecond=0))

        chosen_category = _clean_text(chosen.get("category"))
        if chosen_category:
            simulated_recent_categories.insert(0, chosen_category)
        chosen_guest = _clean_text(chosen.get("guest_name")).casefold()
        if chosen_guest:
            simulated_recent_guests.insert(0, chosen_guest)
        slot = _next_available_release_slot(slot + timedelta(seconds=1), reserved_slots)

    return apply_sequence_warnings(selected)
