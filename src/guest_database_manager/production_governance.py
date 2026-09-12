"""Canonical, deterministic production-governance vocabulary and classification."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

POLICY_VERSION = "1.0.1"
POLICY_EFFECTIVE_DATE = "2026-09-12"
FLAGSHIP_WEEKDAY = 1  # Tuesday; datetime.weekday() uses Monday=0.
FLAGSHIP_HOUR = 5
FLAGSHIP_MINUTE = 0

CONTENT_CLASSES = frozenset({
    "unclassified", "flagship", "spotify_clip", "youtube_short_or_reel",
    "wordpress_article", "substack_companion", "archive_resurface",
})
FLAGSHIP_FORMATS = frozenset({"guest_conversation", "host_reflection"})

PILLARS: Mapping[str, tuple[str, ...]] = {
    "HEAL": ("trauma", "heal", "healing", "health", "grief", "recovery", "anxiety", "self-compassion"),
    "BECOME": ("identity", "courage", "growth", "transformation", "discipline", "reinvention", "confidence"),
    "LOVE": ("relationship", "intimacy", "family", "belonging", "forgiveness", "connection", "loneliness"),
    "PURPOSE": ("purpose", "meaning", "faith", "calling", "creativity", "contribution", "spiritual"),
    "LEAD": ("leadership", "leader", "work", "influence", "service", "responsibility", "founder", "ceo"),
}


def classify_focus(source: Mapping[str, Any]) -> dict[str, Any]:
    """Return explicit classifications when present, otherwise advisory inference."""
    explicit_primary = str(source.get("primary_pillar") or "").strip().upper()
    explicit_secondary = str(source.get("secondary_pillar") or "").strip().upper()
    if explicit_primary in PILLARS:
        return {
            "primary_pillar": explicit_primary,
            "secondary_pillar": explicit_secondary if explicit_secondary in PILLARS and explicit_secondary != explicit_primary else "",
            "source": "human",
            "confidence": "confirmed",
            "matched_keywords": [],
            "policy_version": POLICY_VERSION,
        }

    text = " ".join(
        str(source.get(field) or "")
        for field in (
            "episode_title", "topic", "category", "background", "life_experiences",
            "passionate_topics", "message_takeaway", "core_values", "motivation",
        )
    ).casefold()
    ranked: list[tuple[int, str, list[str]]] = []
    for pillar, keywords in PILLARS.items():
        matches = [keyword for keyword in keywords if re.search(rf"(?<!\w){re.escape(keyword)}(?!\w)", text)]
        ranked.append((len(matches), pillar, matches))
    ranked.sort(key=lambda item: (-item[0], list(PILLARS).index(item[1])))
    if not ranked[0][0]:
        return {
            "primary_pillar": "",
            "secondary_pillar": "",
            "source": "inferred",
            "confidence": "unclassified",
            "matched_keywords": [],
            "policy_version": POLICY_VERSION,
        }
    secondary = ranked[1][1] if ranked[1][0] else ""
    return {
        "primary_pillar": ranked[0][1],
        "secondary_pillar": secondary,
        "source": "inferred",
        "confidence": "strong" if ranked[0][0] >= 2 else "directional",
        "matched_keywords": ranked[0][2][:5],
        "policy_version": POLICY_VERSION,
    }


def flagship_eligibility(episode: Mapping[str, Any]) -> dict[str, Any]:
    """Determine whether a record may compete for a flagship release slot."""
    content_class = str(episode.get("content_class") or "unclassified").strip().lower()
    format_type = str(episode.get("format_type") or "").strip().lower()
    if content_class not in {"unclassified", "flagship"}:
        return {"eligible": False, "reason": f"{content_class} is not a flagship release class"}
    if content_class == "flagship" and format_type not in FLAGSHIP_FORMATS:
        return {"eligible": False, "reason": "flagship format is missing or invalid"}
    if content_class == "unclassified":
        return {"eligible": True, "reason": "legacy record requires human classification", "needs_review": True}
    return {"eligible": True, "reason": "approved flagship class and format", "needs_review": False}
