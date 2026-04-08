"""Explainable guest decision-support scoring for the Mirror Talk dashboard."""

from __future__ import annotations

import re
from urllib.parse import urlsplit
from typing import Any, Dict, Iterable, List


MIRROR_TALK_KEYWORDS = (
    "healing",
    "hope",
    "purpose",
    "faith",
    "reflection",
    "resilience",
    "growth",
    "transformation",
    "mental",
    "wellbeing",
    "well-being",
    "story",
    "honesty",
    "community",
    "meaning",
    "soul",
    "relationship",
    "family",
    "legacy",
    "identity",
)

LOW_EFFORT_PHRASES = (
    "n/a",
    "none",
    "not sure",
    "anything",
    "whatever",
    "test",
)

PROMOTIONAL_PHRASES = (
    "book a call",
    "buy now",
    "sales funnel",
    "lead generation",
    "seo",
    "guest post",
    "backlink",
    "crypto",
    "casino",
)

WORLDVIEW_CAUTION_PHRASES = (
    "witchcraft",
    "occult",
    "tarot",
    "manifestation",
    "law of attraction",
    "new age",
    "crystal healing",
    "channeling",
    "mediumship",
    "psychic",
    "spell work",
)

VALUES_FRICTION_PHRASES = (
    "anything goes",
    "my truth only",
    "no right or wrong",
    "do whatever feels good",
    "fame at all costs",
    "success at any cost",
    "controversy sells",
)


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _normalize_text(value: Any) -> str:
    return _clean_text(value).casefold()


def _word_count(value: Any) -> int:
    return len([word for word in _clean_text(value).split() if word])


def _contains_any(text: str, phrases: Iterable[str]) -> bool:
    normalized = _normalize_text(text)
    return any(phrase in normalized for phrase in phrases)


def _keyword_matches(text: str, keywords: Iterable[str]) -> list[str]:
    normalized = _normalize_text(text)
    return [keyword for keyword in keywords if keyword in normalized]


def _theme_tokens(guest: Dict[str, Any]) -> set[str]:
    """Extract lightweight thematic tokens from a guest profile."""
    fields = [
        guest.get("background"),
        guest.get("profession"),
        guest.get("passionate_topics"),
        guest.get("message_takeaway"),
        guest.get("core_values"),
        guest.get("additional_info"),
    ]
    tokens: set[str] = set()
    for field in fields:
        for raw_token in _clean_text(field).replace(",", " ").replace(".", " ").split():
            token = raw_token.strip(" -_/").casefold()
            if len(token) >= 5:
                tokens.add(token)
    return tokens


def _website_host(value: Any) -> str:
    text = _clean_text(value)
    if not text:
        return ""
    normalized = text if "://" in text else f"https://{text}"
    try:
        host = urlsplit(normalized).netloc.casefold()
    except ValueError:
        return ""
    return re.sub(r"^www\.", "", host)


def _identity_conflict_signals(guest: Dict[str, Any], all_guests: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    """Detect suspicious shared-email and shared-domain patterns across guest records."""
    current_name = _normalize_text(guest.get("full_name") or guest.get("name"))
    current_email = _normalize_text(guest.get("email"))
    current_host = _website_host(guest.get("website"))
    email_conflicts: list[str] = []
    host_conflicts: list[str] = []

    for other in all_guests:
        other_name = _normalize_text(other.get("full_name") or other.get("name"))
        if not other_name or other_name == current_name:
            continue
        if current_email and _normalize_text(other.get("email")) == current_email:
            email_conflicts.append(_clean_text(other.get("full_name") or other.get("name")))
        if current_host and _website_host(other.get("website")) == current_host:
            host_conflicts.append(_clean_text(other.get("full_name") or other.get("name")))

    return {
        "email_conflicts": email_conflicts[:3],
        "host_conflicts": host_conflicts[:3],
    }


def _accepted_history_signal(guest: Dict[str, Any], accepted_history: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    """Compare a guest with previously accepted guests using only stored profile themes."""
    current_name = _normalize_text(guest.get("full_name") or guest.get("name"))
    current_tokens = _theme_tokens(guest)
    if not current_tokens:
        return {"bonus": 0.0, "reason": "", "matches": []}

    ranked_matches: list[tuple[int, str]] = []
    for accepted_guest in accepted_history:
        accepted_name = _clean_text(accepted_guest.get("full_name") or accepted_guest.get("name"))
        if not accepted_name or _normalize_text(accepted_name) == current_name:
            continue
        overlap = current_tokens.intersection(_theme_tokens(accepted_guest))
        if len(overlap) >= 2:
            ranked_matches.append((len(overlap), accepted_name))

    ranked_matches.sort(key=lambda item: (-item[0], item[1].casefold()))
    top_matches = [name for _, name in ranked_matches[:3]]
    if not top_matches:
        return {"bonus": 0.0, "reason": "", "matches": []}

    strongest_overlap = ranked_matches[0][0]
    bonus = min(10.0, 2.5 * strongest_overlap)
    if len(top_matches) == 1:
        reason = f"shares themes with a guest you previously accepted ({top_matches[0]})"
    else:
        reason = f"shares themes with guests you previously accepted ({', '.join(top_matches[:2])})"
    return {"bonus": bonus, "reason": reason, "matches": top_matches}


def _build_signals(score: float, strengths: list[str], cautions: list[str], matched_keywords: list[str]) -> list[Dict[str, str]]:
    """Build compact UI signals from the score and explanation."""
    signals: list[Dict[str, str]] = []
    if score >= 75:
        signals.append({"label": "Strong Fit", "tone": "good"})
    elif score >= 55:
        signals.append({"label": "Promising", "tone": "good"})
    elif score < 35:
        signals.append({"label": "High Risk", "tone": "warning"})

    if matched_keywords:
        signals.append({"label": "Mirror Talk Fit", "tone": "good"})
    if any("complete" in reason or "thoughtful" in reason for reason in strengths):
        signals.append({"label": "Thoughtful Intake", "tone": "good"})
    if any("missing email" in reason for reason in cautions):
        signals.append({"label": "Missing Email", "tone": "warning"})
    if any("too brief" in reason or "low-effort" in reason for reason in cautions):
        signals.append({"label": "Thin Answers", "tone": "warning"})
    if any("promotional" in reason or "spam" in reason for reason in cautions):
        signals.append({"label": "Promotional Risk", "tone": "warning"})
    if any("worldview" in reason or "faith" in reason or "values" in reason for reason in cautions):
        signals.append({"label": "Worldview Caution", "tone": "warning"})
    if any("agency" in reason or "shared inbox" in reason or "website domain is shared" in reason for reason in cautions):
        signals.append({"label": "Identity Check", "tone": "warning"})
    return signals[:4]


def score_guest(
    guest: Dict[str, Any],
    accepted_history: Iterable[Dict[str, Any]] | None = None,
    all_guests: Iterable[Dict[str, Any]] | None = None,
) -> Dict[str, Any]:
    """Return an explainable recommendation payload for a single guest."""
    background = _clean_text(guest.get("background"))
    profession = _clean_text(guest.get("profession"))
    passionate_topics = _clean_text(guest.get("passionate_topics"))
    message_takeaway = _clean_text(guest.get("message_takeaway"))
    podcast_experience = _clean_text(guest.get("podcast_experience"))
    additional_info = _clean_text(guest.get("additional_info"))
    core_values = _clean_text(guest.get("core_values"))
    favorite_quote = _clean_text(guest.get("favorite_quote"))
    faith = _clean_text(guest.get("faith") or guest.get("faith_practice"))
    alignment = _clean_text(guest.get("alignment"))
    website = _clean_text(guest.get("website"))
    social_handles = _clean_text(guest.get("social_media_handles"))
    following_us = _normalize_text(guest.get("following_us"))
    email = _clean_text(guest.get("email"))

    long_form_blocks = [
        background,
        profession,
        passionate_topics,
        message_takeaway,
        additional_info,
        core_values,
    ]
    combined_long_form = "\n".join(block for block in long_form_blocks if block)
    combined_profile = "\n".join(
        block
        for block in [
            background,
            profession,
            passionate_topics,
            message_takeaway,
            additional_info,
            core_values,
            favorite_quote,
            faith,
            alignment,
            podcast_experience,
        ]
        if block
    )

    score = 0.0
    strengths: list[str] = []
    cautions: list[str] = []

    total_long_words = sum(_word_count(block) for block in long_form_blocks)
    answered_long_fields = sum(1 for block in long_form_blocks if _word_count(block) >= 8)

    score += min(total_long_words / 3.5, 30)
    if answered_long_fields >= 4 and total_long_words >= 70:
        score += 16
        strengths.append("shared a complete, thoughtful intake")
    elif answered_long_fields >= 2:
        score += 8
        strengths.append("gave enough context to review meaningfully")
    else:
        score -= 14
        cautions.append("answers are too brief to assess with confidence")

    matched_keywords = _keyword_matches(combined_profile, MIRROR_TALK_KEYWORDS)
    if matched_keywords:
        score += min(18, 4 + len(set(matched_keywords)) * 2)
        strengths.append("themes align well with Mirror Talk conversations")
    else:
        cautions.append("clear Mirror Talk thematic fit is not obvious yet")

    if website:
        score += 5
        strengths.append("has a website or public home base")
    if social_handles:
        score += 4
        strengths.append("has public social presence for promotion")
    if podcast_experience:
        score += 5
        strengths.append("appears comfortable with interviews or speaking")
    if following_us == "yes":
        score += 5
        strengths.append("already follows Mirror Talk")
    elif following_us == "not yet":
        score -= 1

    if email:
        score += 4
    else:
        score -= 16
        cautions.append("missing email will slow outreach and booking")

    if _contains_any(combined_long_form, LOW_EFFORT_PHRASES):
        score -= 10
        cautions.append("some answers feel low-effort or placeholder-like")

    if _contains_any(combined_profile, PROMOTIONAL_PHRASES):
        score -= 16
        cautions.append("language reads more promotional than conversational")

    worldview_text = "\n".join(block for block in [passionate_topics, core_values, faith, alignment, additional_info, favorite_quote] if block)
    worldview_cues = _keyword_matches(worldview_text, WORLDVIEW_CAUTION_PHRASES)
    values_friction_cues = _keyword_matches(worldview_text, VALUES_FRICTION_PHRASES)
    if worldview_cues:
        score -= min(18, 8 + len(set(worldview_cues)) * 2)
        cautions.append("worldview or spiritual framing may sit outside Mirror Talk's faith-sensitive tone")
    if values_friction_cues:
        score -= min(14, 6 + len(set(values_friction_cues)) * 2)
        cautions.append("stated values may be out of step with the reflective, grounded tone you usually want")
    normalized_alignment = _normalize_text(alignment)
    if normalized_alignment.startswith("no"):
        score -= 8
        cautions.append("the guest does not currently see a clear fit with Mirror Talk's soulful conversation style")
    normalized_faith = _normalize_text(faith)
    if normalized_faith.startswith("yes"):
        score += 3
        strengths.append("has a clearly stated spiritual or faith practice")

    if _word_count(background) < 10 and _word_count(profession) < 10:
        score -= 8
        cautions.append("personal and professional background is still too thin")

    if not passionate_topics:
        score -= 8
        cautions.append("discussion themes are not clearly defined")
    if not message_takeaway:
        score -= 6
        cautions.append("listener takeaway is not clearly stated")

    accepted_history_signal = _accepted_history_signal(guest, accepted_history or [])
    if accepted_history_signal["bonus"] > 0:
        score += accepted_history_signal["bonus"]
        strengths.append(accepted_history_signal["reason"])

    identity_conflicts = _identity_conflict_signals(guest, all_guests or [])
    if identity_conflicts["email_conflicts"]:
        score -= 8
        cautions.append("same email appears on other guest records, which may indicate an agency or shared inbox submission")
    if identity_conflicts["host_conflicts"]:
        score -= 4
        cautions.append("the website domain is shared across multiple guest names, so identity should be confirmed carefully")

    score = max(0.0, min(100.0, round(score, 1)))

    if score >= 58:
        suggested_decision = "approve"
        recommendation_label = "Strong Approve"
        confidence = "high"
    elif score >= 50:
        suggested_decision = "review"
        recommendation_label = "Promising Review"
        confidence = "medium"
    elif score >= 35:
        suggested_decision = "review"
        recommendation_label = "Needs Human Review"
        confidence = "medium"
    else:
        suggested_decision = "decline"
        recommendation_label = "Likely Decline"
        confidence = "high" if len(cautions) >= 2 else "medium"

    summary: str
    if suggested_decision == "approve":
        summary = "Strong fit for a meaningful Mirror Talk conversation."
    elif suggested_decision == "decline":
        summary = "Current intake does not yet make a strong enough case."
    else:
        summary = "Worth a human look, but not yet a clear yes."

    return {
        "score": score,
        "suggested_decision": suggested_decision,
        "recommendation_label": recommendation_label,
        "confidence": confidence,
        "summary": summary,
        "strengths": strengths[:3],
        "cautions": cautions[:3],
        "signals": _build_signals(score, strengths, cautions, matched_keywords),
        "accepted_guest_matches": accepted_history_signal["matches"],
        "identity_flags": identity_conflicts,
        "model_version": "mirror-talk-intake-v1",
    }


def enrich_guests_with_recommendations(guests: Iterable[Dict[str, Any]]) -> list[Dict[str, Any]]:
    """Attach decision-support payloads to guest records."""
    guest_list = list(guests)
    accepted_history = [
        guest for guest in guest_list
        if _normalize_text(guest.get("email_status")) == "accepted"
    ]
    enriched: list[Dict[str, Any]] = []
    for guest in guest_list:
        recommendation = score_guest(guest, accepted_history=accepted_history, all_guests=guest_list)
        enriched_guest = dict(guest)
        enriched_guest["decision_support"] = recommendation
        enriched.append(enriched_guest)
    return enriched


def build_guest_recommendation_stats(guests: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    """Summarize dashboard decision-support metrics."""
    guest_list = list(guests)
    if not guest_list:
        return {
            "strong_fits": 0,
            "review_queue": 0,
            "high_risk": 0,
            "average_score": 0,
        }

    strong_fits = 0
    review_queue = 0
    high_risk = 0
    total_score = 0.0

    for guest in guest_list:
        support = guest.get("decision_support") or score_guest(guest)
        total_score += float(support.get("score") or 0)
        decision = support.get("suggested_decision")
        score = float(support.get("score") or 0)
        if decision == "approve":
            strong_fits += 1
        elif decision == "decline" or score < 35:
            high_risk += 1
        else:
            review_queue += 1

    return {
        "strong_fits": strong_fits,
        "review_queue": review_queue,
        "high_risk": high_risk,
        "average_score": round(total_score / len(guest_list)),
    }
