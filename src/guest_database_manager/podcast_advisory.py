"""Read-only, source-backed advisory intelligence for podcast workflows."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any

from guest_database_manager.db_connection import connect_database


ADDITIVE_ACTIVITY = {"downloads", "downloads_7d", "plays", "streams"}


class PodcastAdvisory:
    """Turn verified analytics into explanations without changing workflow state."""

    def __init__(self, db_path: str | Path):
        self.db_path = str(db_path)

    def dashboard(self, insights: dict[str, Any]) -> dict[str, Any]:
        with connect_database(self.db_path) as conn:
            conn.row_factory = __import__("sqlite3").Row
            episodes = {
                int(row["id"]): dict(row)
                for row in conn.execute(
                    """SELECT id, guest_name, category, release_date, rss_duration_seconds,
                              published_title, working_title, episode_title
                       FROM episodes"""
                ).fetchall()
            }
            daily = [dict(row) for row in conn.execute(
                """SELECT episode_id, provider, metric_name, metric_value, period_start,
                          period_end, source_class, overlap_group
                   FROM current_growth_metric_observations
                   WHERE episode_id IS NOT NULL AND period_start = period_end
                     AND metric_name IN ('downloads', 'downloads_7d', 'plays', 'streams')
                   ORDER BY period_end"""
            ).fetchall()]

        episode_performance = insights.get("episode_performance") or []
        enriched = []
        for item in episode_performance:
            episode = episodes.get(int(item.get("episode_id") or 0), {})
            enriched.append({
                **item,
                "category": str(episode.get("category") or "").strip(),
                "guest_name": str(episode.get("guest_name") or "").strip(),
                "duration_seconds": episode.get("rss_duration_seconds"),
                "release_date": episode.get("release_date"),
            })

        category_groups: dict[str, list[float]] = defaultdict(list)
        guest_groups: dict[str, list[float]] = defaultdict(list)
        duration_groups: dict[str, list[float]] = defaultdict(list)
        for item in enriched:
            activity = float(item.get("activity") or 0)
            if item["category"]:
                category_groups[item["category"]].append(activity)
            if item["guest_name"]:
                guest_groups[item["guest_name"]].append(activity)
            duration = item.get("duration_seconds")
            if isinstance(duration, (int, float)) and duration > 0:
                minutes = float(duration) / 60
                duration_groups["Under 30 min" if minutes < 30 else "30–60 min" if minutes <= 60 else "Over 60 min"].append(activity)

        def benchmarks(groups: dict[str, list[float]], minimum: int = 2) -> list[dict[str, Any]]:
            return sorted(({
                "name": name, "episodes": len(values), "median_activity": round(median(values), 1),
                "evidence": "directional" if len(values) < 5 else "established",
            } for name, values in groups.items() if len(values) >= minimum), key=lambda row: -row["median_activity"])

        forecasts = self._forecasts(daily, episodes)
        countries = [row for row in insights.get("countries") or [] if row.get("name") != "Unknown"]
        providers = [row for row in insights.get("provider_strength") or [] if row.get("metrics")]
        promotion = []
        activity_providers = [
            (row, sum(float(value or 0) for metric, value in row.get("metrics", {}).items()
                      if metric in ADDITIVE_ACTIVITY or metric in {"lifetime_plays"}))
            for row in providers
        ]
        activity_providers = [(row, value) for row, value in activity_providers if value > 0]
        if activity_providers:
            strongest, _ = max(activity_providers, key=lambda item: item[1])
            promotion.append({
                "action": (
                    "Prioritize the next measured promotion check on "
                    f"{self._provider_label(strongest.get('provider'), insights)}."
                ),
                "reason": "It has the strongest latest source-backed activity among currently measured providers.",
                "confidence": "directional",
            })
        if countries:
            top = countries[0]
            promotion.append({
                "action": f"Adapt promotion timing and copy for {top.get('name')} before expanding to smaller measured markets.",
                "reason": f"It is the largest currently measured geography ({float(top.get('value') or 0):,.0f} reported audience units).",
                "confidence": "directional",
            })

        categories = benchmarks(category_groups)
        guests = benchmarks(guest_groups)
        durations = benchmarks(duration_groups)
        exceptions = [
            {"severity": item.get("severity", "neutral"), "title": item.get("title"), "detail": item.get("detail")}
            for item in (insights.get("attention_items") or [])
        ]
        return {
            "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "mode": "advisory",
            "guardrails": {
                "changes_workflow_state": False,
                "schedules_or_publishes": False,
                "contacts_people": False,
                "missing_values_are_zero": False,
                "cross_platform_people_are_summed": False,
            },
            "release_planning": {
                "category_benchmarks": categories[:8], "duration_benchmarks": durations,
                "guidance": self._guidance(categories, "category"),
            },
            "guest_selection": {
                "guest_benchmarks": guests[:8],
                "guidance": self._guidance(guests, "guest history"),
            },
            "promotion_planning": {"recommendations": promotion},
            "editorial_strategy": {
                "successful_categories": categories[:5],
                "underserved_topics": [],
                "note": "Topic opportunity needs episode-level topic tags; category evidence is available now.",
            },
            "operations": {
                "priority_episodes": [row for row in enriched if row.get("freshness") == "stale"][:8],
                "recommendation": "Refresh stale evidence before changing promotion or editorial decisions."
                if any(row.get("freshness") == "stale" for row in enriched) else "No episode-level evidence refresh is currently overdue.",
            },
            "recommendation_learning": {
                "eligible_episode_outcomes": len(enriched),
                "status": "available" if enriched else "waiting_for_episode_metrics",
                "note": "Only episode-linked, source-backed observations are eligible for governed learning.",
            },
            "forecasting": forecasts,
            "exception_management": {"items": exceptions},
        }

    @staticmethod
    def _guidance(rows: list[dict[str, Any]], subject: str) -> str:
        if not rows:
            return f"More episode-linked evidence is needed before comparing {subject}."
        leader = rows[0]
        return f"Use {leader['name']} as a comparison set, not an automatic editorial rule; its median measured activity is {leader['median_activity']:,.0f} across {leader['episodes']} episodes."

    @staticmethod
    def _label(value: Any) -> str:
        return str(value or "provider").replace("_", " ").title()

    @classmethod
    def _provider_label(cls, provider: Any, insights: dict[str, Any]) -> str:
        """Name a provider as owners know it, including connected YouTube channel titles."""
        key = str(provider or "").casefold()
        if key.startswith("youtube:"):
            connections = ((insights.get("analytics_connectors") or {}).get("google") or {}).get("connections") or []
            title = next((
                str(item.get("youtube_channel_title") or "").strip()
                for item in connections
                if f"youtube:{str(item.get('youtube_channel_id') or '').casefold()}" == key
            ), "")
            return f"YouTube ({title})" if title else "YouTube"
        return {"youtube": "YouTube", "apple_podcasts": "Apple Podcasts", "ga4": "Website"}.get(key) or cls._label(provider)

    @staticmethod
    def _forecasts(daily: list[dict[str, Any]], episodes: dict[int, dict[str, Any]]) -> dict[str, Any]:
        totals: dict[tuple[int, int], float] = defaultdict(float)
        seen: set[tuple[Any, ...]] = set()
        for row in daily:
            episode_id = int(row["episode_id"])
            released = str(episodes.get(episode_id, {}).get("release_date") or "")[:10]
            try:
                age = (date.fromisoformat(str(row["period_end"])[:10]) - date.fromisoformat(released)).days
            except ValueError:
                continue
            if age < 0:
                continue
            overlap = str(row.get("overlap_group") or row.get("source_class") or row["provider"])
            identity = (episode_id, row["period_end"], row["metric_name"], overlap)
            if identity in seen:
                continue
            seen.add(identity)
            for window in (7, 28):
                if age < window:
                    totals[(episode_id, window)] += float(row["metric_value"] or 0)
        result: dict[str, Any] = {}
        for window in (7, 28):
            values = [value for (episode_id, days), value in totals.items() if days == window and value > 0]
            result[f"first_{window}_days"] = {
                "expected_activity": round(median(values), 1) if len(values) >= 3 else None,
                "comparable_episodes": len(values),
                "status": "ready" if len(values) >= 3 else "insufficient_evidence",
                "method": "Median source-backed daily activity from comparable released episodes.",
            }
        return result
