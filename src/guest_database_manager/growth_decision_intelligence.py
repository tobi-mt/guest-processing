"""Explainable growth signals derived from podcast analytics and RSS history."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any

from guest_database_manager.db_connection import connect_database


def _pct_change(current: float, previous: float) -> float | None:
    if previous <= 0:
        return None
    return round((current - previous) * 100 / previous, 1)


def _window_signal(rows: list[dict[str, Any]], keys: tuple[str, ...]) -> dict[str, Any]:
    current_month = datetime.now(timezone.utc).strftime("%Y-%m")
    complete = [row for row in rows if str(row.get("period")) < current_month]
    recent = complete[-3:]
    previous = complete[-6:-3]
    recent_total = sum(sum(float(row.get(key) or 0) for key in keys) for row in recent)
    previous_total = sum(sum(float(row.get(key) or 0) for key in keys) for row in previous)
    change = _pct_change(recent_total, previous_total) if len(recent) == 3 and len(previous) == 3 else None
    values = [sum(float(row.get(key) or 0) for key in keys) for row in complete[-12:]]
    anomaly = None
    if len(values) >= 6:
        center = median(values[:-1])
        deviation = median(abs(value - center) for value in values[:-1])
        robust_z = 0.6745 * (values[-1] - center) / deviation if deviation else 0.0
        if abs(robust_z) >= 3.5:
            anomaly = {"direction": "spike" if robust_z > 0 else "drop", "robust_z": round(robust_z, 2)}
    return {
        "recent_periods": [row["period"] for row in recent],
        "comparison_periods": [row["period"] for row in previous],
        "recent_total": recent_total,
        "comparison_total": previous_total,
        "change_pct": change,
        "anomaly": anomaly,
        "complete_months": len(complete),
    }


class GrowthDecisionIntelligence:
    """Read-only advisory intelligence; it never changes rankings or publication state."""

    def __init__(self, db_path: str | Path):
        self.db_path = str(db_path)

    def _cadence(self) -> dict[str, Any]:
        with connect_database(self.db_path) as conn:
            dates = [
                datetime.fromisoformat(str(row[0]).replace("Z", "+00:00")).date()
                for row in conn.execute(
                    "SELECT published_at FROM rss_feed_items WHERE published_at != '' ORDER BY published_at"
                ).fetchall()
            ]
        intervals = [
            (right - left).days for left, right in zip(dates, dates[1:])
            if 0 < (right - left).days <= 60
        ]
        recent = intervals[-52:]
        typical = median(recent) if recent else None
        consistency = (
            sum(abs(value - typical) <= 2 for value in recent) / len(recent)
            if recent and typical is not None else None
        )
        return {
            "rss_episodes": len(dates),
            "intervals_analyzed": len(recent),
            "median_days_between_releases": typical,
            "within_two_days_of_cadence_pct": round(consistency * 100, 1) if consistency is not None else None,
        }

    def dashboard(self, monthly_trends: dict[str, list[dict[str, Any]]], learning: dict[str, Any]) -> dict[str, Any]:
        spotify = _window_signal(monthly_trends.get("spotify") or [], ("downloads", "plays"))
        apple = _window_signal(monthly_trends.get("apple_podcasts") or [], ("plays",))
        cadence = self._cadence()
        evidence = learning.get("evidence_progress") or {}
        linked = int(evidence.get("linked") or 0)
        minimum = int(evidence.get("minimum") or 30)
        confidence_score = min(1.0, spotify["complete_months"] / 12) * 0.3
        confidence_score += min(1.0, apple["complete_months"] / 12) * 0.3
        confidence_score += min(1.0, cadence["rss_episodes"] / 30) * 0.2
        confidence_score += min(1.0, linked / max(minimum, 1)) * 0.2
        recommendations = []

        for provider, signal in (("Spotify", spotify), ("Apple Podcasts", apple)):
            change = signal["change_pct"]
            if change is None:
                continue
            if change <= -15:
                action = f"Investigate the {provider} decline before changing the release plan."
                priority = "high"
            elif change >= 15:
                action = f"Preserve the current {provider} distribution and promotion pattern while testing one change at a time."
                priority = "medium"
            else:
                action = f"Treat {provider} as stable; optimize experiments for learning rather than short-term volume."
                priority = "normal"
            recommendations.append({
                "id": f"{provider.casefold().replace(' ', '-')}-momentum",
                "priority": priority,
                "action": action,
                "rationale": f"The latest three complete months changed {change:+.1f}% versus the preceding three months.",
                "confidence": "high" if signal["complete_months"] >= 12 else "medium",
                "ranking_changed": False,
            })

        cadence_pct = cadence["within_two_days_of_cadence_pct"]
        if cadence_pct is not None:
            recommendations.append({
                "id": "release-cadence",
                "priority": "medium" if cadence_pct < 70 else "normal",
                "action": "Stabilize the release cadence before attributing performance changes to episode choices."
                if cadence_pct < 70 else "Keep the established release cadence as the control for future content experiments.",
                "rationale": f"{cadence_pct:.1f}% of the last {cadence['intervals_analyzed']} release intervals were within two days of the {cadence['median_days_between_releases']}-day median.",
                "confidence": "high" if cadence["intervals_analyzed"] >= 20 else "medium",
                "ranking_changed": False,
            })

        if linked < minimum:
            recommendations.append({
                "id": "learning-evidence",
                "priority": "high",
                "action": "Keep adaptive ranking in shadow mode and continue linking recommendation outcomes.",
                "rationale": f"Only {linked} independently linked outcomes are available; the activation gate requires {minimum}.",
                "confidence": "high",
                "ranking_changed": False,
            })

        return {
            "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "mode": "advisory_shadow",
            "confidence_score": round(confidence_score, 2),
            "signals": {"spotify_momentum": spotify, "apple_momentum": apple, "release_cadence": cadence},
            "recommendations": recommendations,
            "guardrails": {
                "ranking_changed": False,
                "publishing_changed": False,
                "current_month_excluded_from_momentum": True,
                "non_additive_listener_totals_excluded": True,
                "minimum_linked_outcomes": minimum,
            },
        }
