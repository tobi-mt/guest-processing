"""Optional OpenAI-backed scheduling copilot for richer planning intelligence."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Iterable, List

import requests

logger = logging.getLogger(__name__)

MAX_RECOMMENDATIONS = 4
MAX_RECENT_RELEASES = 5
MAX_TEXT_CHARS = 180
MAX_SOURCE_DETAIL_CHARS = 120


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
    ) -> List[Dict[str, Any]]:
        """Return recommendations with optional AI copilot hints and a controlled score adjustment."""
        recommendations = [dict(item) for item in recommendations]
        if not recommendations:
            return []
        recommendations = recommendations[:MAX_RECOMMENDATIONS]

        prompt_payload = {
            "reference_date": reference.strftime("%Y-%m-%d"),
            "recommendations": [self._serialize_candidate(item) for item in recommendations],
            "recent_releases": [self._serialize_release(item) for item in list(released_history)[:MAX_RECENT_RELEASES]],
        }
        result = self._call_openai(prompt_payload)
        analyses = result.get("analyses", [])
        analysis_by_id = {int(item["id"]): item for item in analyses if str(item.get("id", "")).isdigit()}

        enriched: list[Dict[str, Any]] = []
        for recommendation in recommendations:
            analysis = analysis_by_id.get(int(recommendation.get("id") or 0))
            enriched_item = dict(recommendation)
            if analysis:
                ai_score = int(analysis.get("alignment_score") or 0)
                score_adjustment = max(-6, min(6, round((ai_score - 50) / 10)))
                enriched_item["priority_score"] = round(float(enriched_item.get("priority_score") or 0) + score_adjustment, 1)
                enriched_item["ai_copilot"] = {
                    "model": self.model,
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
        return enriched

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
                            "required": ["id", "alignment_score", "summary", "monthly_theme", "why_now", "watchouts", "source_evidence"],
                        },
                    }
                },
                "required": ["analyses"],
            },
        }

        instructions = (
            "You are an editorial scheduling copilot for Mirror Talk Podcast. "
            "Use only the supplied episode metadata, guest research, and recent release history. "
            "Do not invent outside facts. If evidence is thin, say so plainly. "
            "Return grounded suggestions that help with scheduling, not autopilot decisions. "
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
            return json.loads(text_output) if text_output else {"analyses": []}
        except (requests.RequestException, ValueError, json.JSONDecodeError) as exc:
            logger.warning("OpenAI scheduling copilot unavailable, falling back to deterministic planning: %s", exc)
            return {"analyses": []}

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
        return {
            "id": item.get("id"),
            "guest_name": OpenAISchedulingCopilot._trim_text(item.get("guest_name"), 80),
            "episode_title": OpenAISchedulingCopilot._trim_text(item.get("episode_title"), 100),
            "topic": OpenAISchedulingCopilot._trim_text(item.get("topic"), 120),
            "category": OpenAISchedulingCopilot._trim_text(item.get("category"), 50),
            "recommended_release_date": item.get("recommended_release_date"),
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
