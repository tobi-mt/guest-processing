"""Canonical, deterministic production-governance vocabulary and classification."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from typing import Any

POLICY_VERSION = "1.1.0"
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

PILLAR_ANGLES: Mapping[str, tuple[str, ...]] = {
    "HEAL": ("the turning point that began their healing", "practical hope for someone facing a similar struggle"),
    "BECOME": ("the identity they had to leave behind", "the habits and courage that made reinvention possible"),
    "LOVE": ("how hardship changed the way they connect", "a grounded path toward forgiveness or belonging"),
    "PURPOSE": ("how they recognized a deeper calling", "turning faith, creativity, or meaning into service"),
    "LEAD": ("the responsibility behind their influence", "leading with humanity when results and values collide"),
}


def _research_payload(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except (TypeError, ValueError):
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _focus_sources(source: Mapping[str, Any]) -> list[dict[str, str | int]]:
    fields = (
        ("Episode title", "episode_title", 3),
        ("Episode topic", "topic", 4),
        ("Episode category", "category", 2),
        ("Background", "background", 3),
        ("Life experiences", "life_experiences", 3),
        ("Passionate topics", "passionate_topics", 4),
        ("Listener takeaway", "message_takeaway", 4),
        ("Core values", "core_values", 3),
        ("Motivation", "motivation", 2),
        ("Profession", "profession", 1),
    )
    sources: list[dict[str, str | int]] = []
    for label, key, weight in fields:
        text = str(source.get(key) or "").strip()
        if text:
            sources.append({"label": label, "text": text, "weight": weight, "url": ""})

    research = _research_payload(source.get("guest_research"))
    research_parts = [research.get("summary")]
    research_parts.extend(research.get("likely_topics") or [])
    research_text = " ".join(str(part or "") for part in research_parts).strip()
    if research_text:
        sources.append({"label": "Public-profile research", "text": research_text, "weight": 2, "url": ""})
    for item in (research.get("sources") or [])[:3]:
        if not isinstance(item, dict):
            continue
        text = " ".join(str(item.get(key) or "") for key in ("title", "description", "heading")).strip()
        if text:
            sources.append({"label": "Public source", "text": text, "weight": 1, "url": str(item.get("url") or "")})
    return sources


def _evidence_excerpt(text: str, *, limit: int = 150) -> str:
    compact = " ".join(text.split())
    return compact if len(compact) <= limit else f"{compact[: limit - 1].rstrip()}…"


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
            "confidence_pct": 100,
            "matched_keywords": [],
            "pillar_scores": [
                {"pillar": pillar, "confidence_pct": 100 if pillar == explicit_primary else 0}
                for pillar in PILLARS
            ],
            "evidence": [],
            "conversation_angles": list(PILLAR_ANGLES[explicit_primary]),
            "insufficient_evidence": False,
            "policy_version": POLICY_VERSION,
        }

    focus_sources = _focus_sources(source)
    ranked: list[tuple[int, str, list[str], list[dict[str, Any]]]] = []
    for pillar, keywords in PILLARS.items():
        score = 0
        matches: set[str] = set()
        evidence: list[dict[str, Any]] = []
        for item in focus_sources:
            text = str(item["text"])
            found = [keyword for keyword in keywords if re.search(rf"(?<!\w){re.escape(keyword)}(?!\w)", text.casefold())]
            if not found:
                continue
            score += int(item["weight"]) * len(set(found))
            matches.update(found)
            evidence.append({
                "pillar": pillar,
                "source": item["label"],
                "excerpt": _evidence_excerpt(text),
                "matched_keywords": sorted(set(found)),
                "url": item["url"],
            })
        ranked.append((score, pillar, sorted(matches), evidence))
    ranked.sort(key=lambda item: (-item[0], list(PILLARS).index(item[1])))
    total_score = sum(item[0] for item in ranked)
    pillar_scores = [
        {
            "pillar": pillar,
            "confidence_pct": round(score / total_score * 100) if total_score else 0,
            "matched_keywords": matches[:5],
        }
        for score, pillar, matches, _evidence in ranked
    ]
    if total_score and pillar_scores:
        pillar_scores[0]["confidence_pct"] += 100 - sum(item["confidence_pct"] for item in pillar_scores)
    if not ranked[0][0]:
        return {
            "primary_pillar": "",
            "secondary_pillar": "",
            "source": "inferred",
            "confidence": "unclassified",
            "confidence_pct": 0,
            "matched_keywords": [],
            "pillar_scores": pillar_scores,
            "evidence": [],
            "conversation_angles": [],
            "insufficient_evidence": True,
            "policy_version": POLICY_VERSION,
        }
    top_score, primary, top_matches, top_evidence = ranked[0]
    secondary = ranked[1][1] if ranked[1][0] and ranked[1][0] >= max(2, top_score * 0.4) else ""
    confidence_pct = pillar_scores[0]["confidence_pct"]
    is_episode_context = any(str(source.get(field) or "").strip() for field in ("episode_title", "topic", "category"))
    insufficient_evidence = (top_score < 4 or len(top_evidence) < 2) and not is_episode_context
    return {
        "primary_pillar": "" if insufficient_evidence else primary,
        "secondary_pillar": "" if insufficient_evidence else secondary,
        "suggested_pillar": primary,
        "source": "inferred",
        "confidence": "insufficient" if insufficient_evidence else "strong" if top_score >= 10 and confidence_pct >= 55 else "directional",
        "confidence_pct": confidence_pct,
        "matched_keywords": top_matches[:5],
        "pillar_scores": pillar_scores,
        "evidence": top_evidence[:4],
        "conversation_angles": list(PILLAR_ANGLES[primary]) if not insufficient_evidence else [],
        "insufficient_evidence": insufficient_evidence,
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
