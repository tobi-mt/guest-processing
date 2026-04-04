"""Optional OpenAI-backed scheduling copilot for richer planning intelligence."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Dict, Iterable, List

import requests

logger = logging.getLogger(__name__)

MAX_RECOMMENDATIONS = 4
MAX_RECENT_RELEASES = 5
MAX_TEXT_CHARS = 180
MAX_SOURCE_DETAIL_CHARS = 120

MONTHLY_EDITORIAL_PROFILES: Dict[int, Dict[str, Any]] = {
    1: {
        "theme": "Fresh beginnings and intentional reset",
        "timely_signals": ["new year reflection", "goal setting", "renewed discipline"],
        "observances": ["New Year season", "fresh-start momentum"],
    },
    2: {
        "theme": "Love, belonging, and relational depth",
        "timely_signals": ["friendship", "marriage", "emotional intimacy"],
        "observances": ["Valentine season", "heart-centered reflection"],
    },
    3: {
        "theme": "Purpose, courage, and emerging identity",
        "timely_signals": ["women's voices", "spring transition", "inner growth"],
        "observances": ["Women's History Month", "seasonal transition into spring"],
    },
    4: {
        "theme": "Renewal, resurrection, and new life",
        "timely_signals": ["hope after hard seasons", "healing", "fresh beginnings"],
        "observances": ["Stress Awareness Month", "Autism Acceptance Month", "Earth Day"],
    },
    5: {
        "theme": "Mental health, motherhood, and sustaining growth",
        "timely_signals": ["emotional wellbeing", "caregiving", "graduation season"],
        "observances": ["Mental Health Awareness Month", "Mother's Day"],
    },
    6: {
        "theme": "Identity, fatherhood, resilience, and community",
        "timely_signals": ["fatherhood", "community leadership", "summer reflection"],
        "observances": ["Men's Health Month", "Father's Day"],
    },
    7: {
        "theme": "Freedom, calling, and brave leadership",
        "timely_signals": ["independence", "vocation", "service"],
        "observances": ["mid-year reset", "summer leadership season"],
    },
    8: {
        "theme": "Preparation, discipline, and back-to-rhythm momentum",
        "timely_signals": ["school routines", "family structure", "recommitment"],
        "observances": ["back-to-school season", "late-summer planning"],
    },
    9: {
        "theme": "Resilience, mental health, and renewed focus",
        "timely_signals": ["recovery", "purpose", "mental wellbeing"],
        "observances": ["Suicide Prevention Month", "new academic rhythm"],
    },
    10: {
        "theme": "Healing stories, awareness, and courageous honesty",
        "timely_signals": ["healing journeys", "awareness campaigns", "testimony"],
        "observances": ["Breast Cancer Awareness Month", "Domestic Violence Awareness Month"],
    },
    11: {
        "theme": "Gratitude, reflection, and community care",
        "timely_signals": ["thankfulness", "service", "family conversations"],
        "observances": ["Thanksgiving season", "gratitude reflection"],
    },
    12: {
        "theme": "Advent hope, peace, and meaningful endings",
        "timely_signals": ["hope", "rest", "year-end reflection"],
        "observances": ["Advent season", "Christmas"],
    },
}


def _compute_easter_sunday(year: int) -> date:
    """Return Gregorian Easter Sunday for the given year."""
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return date(year, month, day)


def build_month_context(reference: datetime) -> Dict[str, Any]:
    """Build a month-aware editorial context with real calendar timing."""
    profile = MONTHLY_EDITORIAL_PROFILES.get(reference.month, MONTHLY_EDITORIAL_PROFILES[1])
    christian_moments: list[str] = []
    easter = _compute_easter_sunday(reference.year)
    movable_events = {
        "Ash Wednesday": easter - timedelta(days=46),
        "Palm Sunday": easter - timedelta(days=7),
        "Good Friday": easter - timedelta(days=2),
        "Easter Sunday": easter,
        "Pentecost": easter + timedelta(days=49),
    }
    fixed_events = {
        "Christmas Day": date(reference.year, 12, 25),
        "New Year's Day": date(reference.year, 1, 1),
    }
    for label, event_date in {**movable_events, **fixed_events}.items():
        if event_date.month == reference.month:
            christian_moments.append(f"{label} ({event_date.strftime('%b')} {event_date.day})")

    return {
        "month_label": reference.strftime("%B %Y"),
        "theme": profile["theme"],
        "timely_signals": list(profile["timely_signals"]),
        "observances": list(profile["observances"]),
        "christian_moments": christian_moments,
        "season": _season_label(reference.month),
    }


def _season_label(month: int) -> str:
    if month in (12, 1, 2):
        return "Winter"
    if month in (3, 4, 5):
        return "Spring"
    if month in (6, 7, 8):
        return "Summer"
    return "Autumn"


@dataclass
class OpenAISchedulingCopilot:
    """Small wrapper around the OpenAI Responses API for scheduling copilot hints."""

    api_key: str
    model: str
    base_url: str = "https://api.openai.com/v1/responses"
    timeout_seconds: int = 12

    def enrich_recommendations(
        self,
        recommendations: Iterable[Dict[str, Any]],
        *,
        reference: datetime,
        released_history: Iterable[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Return recommendations with optional AI copilot hints and explicit runtime status."""
        recommendations = [dict(item) for item in recommendations]
        if not recommendations:
            return {
                "status": "no_candidates",
                "message": "No recommendation candidates were available for AI review.",
                "model": self.model,
                "current_month_context": build_month_context(reference),
                "recommendations": [],
            }
        recommendations = recommendations[:MAX_RECOMMENDATIONS]

        prompt_payload = {
            "reference_date": reference.strftime("%Y-%m-%d"),
            "current_month_context": build_month_context(reference),
            "recommendations": [self._serialize_candidate(item) for item in recommendations],
            "recent_releases": [self._serialize_release(item) for item in list(released_history)[:MAX_RECENT_RELEASES]],
        }
        result = self._call_openai(prompt_payload)
        analyses = result.get("analyses", [])
        analysis_by_id = {int(item["id"]): item for item in analyses if str(item.get("id", "")).isdigit()}
        fallback_analyses = self._build_grounded_fallback_analyses(recommendations, reference)

        enriched: list[Dict[str, Any]] = []
        for recommendation in recommendations:
            analysis = analysis_by_id.get(int(recommendation.get("id") or 0))
            if not analysis:
                analysis = fallback_analyses.get(int(recommendation.get("id") or 0))
            enriched_item = dict(recommendation)
            if analysis:
                ai_score = int(analysis.get("alignment_score") or 0)
                score_adjustment = max(-6, min(6, round((ai_score - 50) / 10)))
                enriched_item["priority_score"] = round(float(enriched_item.get("priority_score") or 0) + score_adjustment, 1)
                enriched_item["ai_copilot"] = {
                    "model": self.model,
                    "guidance_mode": str(analysis.get("guidance_mode") or "model").strip(),
                    "alignment_score": ai_score,
                    "summary": str(analysis.get("summary") or "").strip(),
                    "why_now": [str(item).strip() for item in analysis.get("why_now", []) if str(item).strip()][:3],
                    "watchouts": [str(item).strip() for item in analysis.get("watchouts", []) if str(item).strip()][:3],
                    "monthly_theme": str(analysis.get("monthly_theme") or "").strip(),
                    "source_evidence": [
                        {
                            "source": str(item.get("source") or "").strip(),
                            "detail": str(item.get("detail") or "").strip(),
                        }
                        for item in analysis.get("source_evidence", [])
                        if str(item.get("source") or "").strip() and str(item.get("detail") or "").strip()
                    ][:4],
                }
                enriched_item["why_now"] = list(dict.fromkeys(enriched_item.get("why_now", []) + enriched_item["ai_copilot"]["why_now"]))[:5]
                enriched_item["watchouts"] = list(dict.fromkeys(enriched_item.get("watchouts", []) + enriched_item["ai_copilot"]["watchouts"]))[:5]
            enriched.append(enriched_item)

        enriched.sort(
            key=lambda item: (
                -float(item.get("priority_score") or 0),
                str(item.get("recommended_release_date") or ""),
                str(item.get("guest_name") or ""),
            )
        )
        enriched_count = sum(1 for item in enriched if item.get("ai_copilot"))
        model_analysis_count = sum(1 for item in recommendations if analysis_by_id.get(int(item.get("id") or 0)))
        fallback_analysis_count = max(0, enriched_count - model_analysis_count)
        if enriched_count:
            status = "active"
            if fallback_analysis_count > 0 and model_analysis_count > 0:
                message = (
                    f"AI copilot enriched {enriched_count} recommendation{'s' if enriched_count != 1 else ''}; "
                    f"{model_analysis_count} came directly from the model and {fallback_analysis_count} used grounded copilot fallback notes."
                )
            elif fallback_analysis_count > 0:
                message = (
                    f"AI copilot produced grounded fallback guidance for {fallback_analysis_count} researched recommendation"
                    f"{'s' if fallback_analysis_count != 1 else ''} using current-month context and saved evidence."
                )
            else:
                message = f"AI copilot enriched {enriched_count} recommendation{'s' if enriched_count != 1 else ''} using guest profiles, web research, and current-month context."
        elif result.get("status") == "fallback":
            status = "fallback"
            message = str(result.get("message") or "AI copilot fell back to deterministic planning.")
        else:
            status = "thin_context"
            message = "AI copilot was configured, but the current candidates had too little grounded context to add trustworthy guidance."

        return {
            "status": status,
            "message": message,
            "model": self.model,
            "current_month_context": build_month_context(reference),
            "recommendations": enriched,
        }

    @staticmethod
    def _build_grounded_fallback_analyses(recommendations: list[Dict[str, Any]], reference: datetime) -> Dict[int, Dict[str, Any]]:
        """Build cautious copilot notes when researched candidates exist but the model returns nothing useful."""
        month_context = build_month_context(reference)
        fallback: Dict[int, Dict[str, Any]] = {}
        for item in recommendations:
            recommendation_id = int(item.get("id") or 0)
            if not recommendation_id:
                continue
            research = item.get("guest_research") if isinstance(item.get("guest_research"), dict) else {}
            profile = item.get("guest_profile_context") if isinstance(item.get("guest_profile_context"), dict) else {}
            likely_topics = [str(topic).strip() for topic in research.get("likely_topics", []) if str(topic).strip()]
            timely_signals = [str(signal).strip() for signal in research.get("timely_signals", []) if str(signal).strip()]
            summary = str(research.get("summary") or "").strip()
            evidence = []
            for source in research.get("sources", [])[:3]:
                label = str(source.get("title") or source.get("host") or source.get("url") or "").strip()
                detail = str(source.get("description") or "").strip()
                if label and detail:
                    evidence.append({"source": label, "detail": OpenAISchedulingCopilot._trim_text(detail, MAX_SOURCE_DETAIL_CHARS)})
            if not (likely_topics or timely_signals or summary or profile):
                continue

            why_now: list[str] = []
            if likely_topics:
                why_now.append(f"public profile research points toward {', '.join(likely_topics[:2]).lower()}")
            if timely_signals:
                why_now.append(timely_signals[0])
            if month_context["theme"] and likely_topics:
                why_now.append(f"can be framed carefully within {month_context['theme'].lower()}")

            watchouts = ["keep the framing grounded in the guest's actual public work rather than a broad seasonal label"]
            if not profile:
                watchouts.append("dashboard guest profile match is still missing, so rely on website evidence carefully")

            fallback[recommendation_id] = {
                "id": recommendation_id,
                "alignment_score": 64 if profile else 58,
                "summary": summary or "Saved public-profile evidence gives this episode enough context for cautious scheduling guidance.",
                "monthly_theme": month_context["theme"],
                "guidance_mode": "grounded_fallback",
                "why_now": why_now[:3],
                "watchouts": watchouts[:3],
                "source_evidence": evidence[:4],
            }
        return fallback

    def _call_openai(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        schema = {
            "name": "scheduling_copilot_result",
            "schema": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "analyses": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "id": {"type": "integer"},
                                "alignment_score": {"type": "integer"},
                                "summary": {"type": "string"},
                                "monthly_theme": {"type": "string"},
                                "guidance_mode": {"type": "string"},
                                "why_now": {"type": "array", "items": {"type": "string"}},
                                "watchouts": {"type": "array", "items": {"type": "string"}},
                                "source_evidence": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "additionalProperties": False,
                                        "properties": {
                                            "source": {"type": "string"},
                                            "detail": {"type": "string"},
                                        },
                                        "required": ["source", "detail"],
                                    },
                                },
                            },
                            "required": ["id", "alignment_score", "summary", "monthly_theme", "guidance_mode", "why_now", "watchouts", "source_evidence"],
                        },
                    }
                },
                "required": ["analyses"],
            },
        }

        instructions = (
            "You are an editorial scheduling copilot for Mirror Talk Podcast. "
            "Use only the supplied episode metadata, guest database profile context, guest web research, current month context, and recent release history. "
            "Do not invent outside facts. If evidence is thin, say so plainly. "
            "Match the recommended release month to relevant observances, Christian moments, and timely themes only when the guest information genuinely supports that angle. "
            "Return grounded suggestions that help with scheduling, not autopilot decisions. "
            "You must return one analysis object for every candidate id you receive. "
            "If the evidence is moderate rather than strong, still return an analysis with a lower alignment score, cautious summary, and explicit watchouts instead of skipping the candidate. "
            "Treat reusable guest research, auto-researched episode websites, and multiple public sources as valid grounded context. "
            "Only use a very low score and strong caution when the supplied evidence is genuinely too generic or contradictory. "
            "Be concise and evidence-led."
        )
        try:
            response = requests.post(
                self.base_url,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model,
                    "input": [
                        {"role": "system", "content": [{"type": "input_text", "text": instructions}]},
                        {"role": "user", "content": [{"type": "input_text", "text": json.dumps(payload, ensure_ascii=False)}]},
                    ],
                    "text": {
                        "format": {
                            "type": "json_schema",
                            "name": schema["name"],
                            "schema": schema["schema"],
                            "strict": True,
                        }
                    },
                    "max_output_tokens": 700,
                },
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            data = response.json()
            text_output = self._extract_output_text(data)
            return {"status": "active", "analyses": json.loads(text_output).get("analyses", []) if text_output else []}
        except (requests.RequestException, ValueError, json.JSONDecodeError) as exc:
            if isinstance(exc, requests.HTTPError) and exc.response is not None:
                logger.warning(
                    "OpenAI scheduling copilot unavailable, falling back to deterministic planning: %s | body=%s",
                    exc,
                    exc.response.text[:400],
                )
            else:
                logger.warning("OpenAI scheduling copilot unavailable, falling back to deterministic planning: %s", exc)
            return {
                "status": "fallback",
                "message": f"OpenAI scheduling copilot fell back to deterministic planning: {exc}",
                "analyses": [],
            }

    @staticmethod
    def _extract_output_text(data: Dict[str, Any]) -> str:
        """Extract the first text block from a Responses API payload."""
        for item in data.get("output", []):
            for content in item.get("content", []):
                text = content.get("text")
                if text:
                    return text
        return ""

    @staticmethod
    def _serialize_candidate(item: Dict[str, Any]) -> Dict[str, Any]:
        research = item.get("guest_research") if isinstance(item.get("guest_research"), dict) else {}
        profile = item.get("guest_profile_context") if isinstance(item.get("guest_profile_context"), dict) else {}
        release_date = item.get("recommended_release_date")
        release_month_context = None
        if release_date:
            try:
                release_month_context = build_month_context(datetime.fromisoformat(str(release_date).replace("Z", "+00:00")))
            except ValueError:
                release_month_context = None
        return {
            "id": item.get("id"),
            "guest_name": OpenAISchedulingCopilot._trim_text(item.get("guest_name"), 80),
            "website": OpenAISchedulingCopilot._trim_text(item.get("website"), 100),
            "episode_title": OpenAISchedulingCopilot._trim_text(item.get("episode_title"), 100),
            "topic": OpenAISchedulingCopilot._trim_text(item.get("topic"), 120),
            "category": OpenAISchedulingCopilot._trim_text(item.get("category"), 50),
            "recommended_release_date": item.get("recommended_release_date"),
            "release_month_context": release_month_context,
            "production_status": item.get("production_status"),
            "promotion_status": item.get("promotion_status"),
            "promotion_readiness": {
                "score": (item.get("promotion_readiness") or {}).get("score"),
                "label": OpenAISchedulingCopilot._trim_text((item.get("promotion_readiness") or {}).get("label"), 40),
            },
            "archive_overlap": {
                "status": (item.get("archive_overlap") or {}).get("status"),
                "message": OpenAISchedulingCopilot._trim_text((item.get("archive_overlap") or {}).get("message"), MAX_TEXT_CHARS),
            },
            "topic_cluster_warning": {
                "status": (item.get("topic_cluster_warning") or {}).get("status"),
                "message": OpenAISchedulingCopilot._trim_text((item.get("topic_cluster_warning") or {}).get("message"), MAX_TEXT_CHARS),
            },
            "guest_profile_context": {
                "profession": OpenAISchedulingCopilot._trim_text(profile.get("profession"), 80),
                "background": OpenAISchedulingCopilot._trim_text(profile.get("background"), MAX_TEXT_CHARS),
                "faith_practice": OpenAISchedulingCopilot._trim_text(profile.get("faith_practice"), 90),
                "core_values": OpenAISchedulingCopilot._trim_text(profile.get("core_values"), 100),
                "passionate_topics": OpenAISchedulingCopilot._trim_text(profile.get("passionate_topics"), 100),
            },
            "context_strength": {
                "has_profile_context": bool(profile),
                "has_guest_research": bool(research),
                "research_mode": OpenAISchedulingCopilot._trim_text(research.get("research_mode"), 30),
                "research_source_count": len(research.get("sources", [])),
                "likely_topic_count": len(research.get("likely_topics", [])),
                "timely_signal_count": len(research.get("timely_signals", [])),
                "summary_present": bool(OpenAISchedulingCopilot._trim_text(research.get("summary"), MAX_TEXT_CHARS)),
            },
            "guest_research": {
                "summary": OpenAISchedulingCopilot._trim_text(research.get("summary"), MAX_TEXT_CHARS),
                "likely_topics": [OpenAISchedulingCopilot._trim_text(topic, 40) for topic in research.get("likely_topics", [])[:3]],
                "timely_signals": [OpenAISchedulingCopilot._trim_text(signal, 80) for signal in research.get("timely_signals", [])[:2]],
                "sources": [
                    {
                        "source": OpenAISchedulingCopilot._trim_text(source.get("title") or source.get("host") or source.get("url"), 60),
                        "detail": OpenAISchedulingCopilot._trim_text(source.get("description") or "", MAX_SOURCE_DETAIL_CHARS),
                    }
                    for source in research.get("sources", [])
                ][:2],
            },
        }

    @staticmethod
    def _serialize_release(item: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "guest_name": OpenAISchedulingCopilot._trim_text(item.get("guest_name"), 80),
            "episode_title": OpenAISchedulingCopilot._trim_text(item.get("episode_title"), 100),
            "topic": OpenAISchedulingCopilot._trim_text(item.get("topic"), 100),
            "category": OpenAISchedulingCopilot._trim_text(item.get("category"), 50),
            "release_date": item.get("release_date"),
        }

    @staticmethod
    def _trim_text(value: Any, limit: int) -> str:
        """Trim long prompt fields to keep the OpenAI payload lean."""
        text = str(value or "").strip()
        if len(text) <= limit:
            return text
        return text[: max(0, limit - 1)].rstrip() + "…"
