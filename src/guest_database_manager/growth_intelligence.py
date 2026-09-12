"""Source-backed growth intelligence for Mirror Talk."""

from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from guest_database_manager.db_connection import connect_database
from guest_database_manager.episode_planner import EDITORIAL_PILLARS, build_editorial_fit


CANONICAL_METRICS = {
    "organic_reach": "count",
    "paid_reach": "count",
    "consumption_depth_pct": "percent",
    "conversion_rate_pct": "percent",
    "return_rate_pct": "percent",
    "downloads_7d": "count",
    "youtube_ctr_pct": "percent",
    "youtube_retention_30s_pct": "percent",
    "average_view_duration_seconds": "seconds",
    "spotify_home_impressions": "count",
    "spotify_search_impressions": "count",
    "guest_shares": "count",
    "guest_newsletter_inclusions": "count",
    "email_subscribers_gained": "count",
    "site_to_podcast_conversion_pct": "percent",
}
MFS_COMPONENTS = ("organic_reach", "consumption_depth_pct", "conversion_rate_pct", "return_rate_pct")


class GrowthIntelligenceError(ValueError):
    """Raised when growth evidence is unsafe or ambiguous."""


def _text(value: Any) -> str:
    return str(value or "").strip()


def _iso_date(value: Any, field: str) -> str:
    text = _text(value)
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date().isoformat()
    except ValueError as exc:
        raise GrowthIntelligenceError(f"{field} must be an ISO date or datetime.") from exc


def _metric_value(metric: str, value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise GrowthIntelligenceError("metric_value must be numeric.") from exc
    if not math.isfinite(number) or number < 0:
        raise GrowthIntelligenceError("metric_value must be a finite non-negative number.")
    if CANONICAL_METRICS[metric] == "percent" and number > 100:
        raise GrowthIntelligenceError("Percentage metrics cannot exceed 100.")
    return number


class GrowthIntelligence:
    """Persist immutable observations and derive recalculable summaries."""

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)

    def record_observations(self, rows: Iterable[dict[str, Any]], *, actor: str, correlation_id: str = "") -> dict[str, Any]:
        rows = list(rows)
        if not rows or len(rows) > 500:
            raise GrowthIntelligenceError("Provide between 1 and 500 observations.")
        prepared = []
        with connect_database(self.db_path) as conn:
            valid_episode_ids = {int(row[0]) for row in conn.execute("SELECT id FROM episodes").fetchall()}
            for row in rows:
                metric = _text(row.get("metric_name"))
                if metric not in CANONICAL_METRICS:
                    raise GrowthIntelligenceError(f"Unsupported metric_name: {metric or 'missing'}.")
                episode_id = row.get("episode_id")
                episode_id = int(episode_id) if episode_id not in (None, "") else None
                if episode_id is not None and episode_id not in valid_episode_ids:
                    raise GrowthIntelligenceError("episode_id does not identify an existing episode.")
                provider = _text(row.get("provider")).lower()
                source_reference = _text(row.get("source_reference"))
                if not provider or not source_reference:
                    raise GrowthIntelligenceError("provider and source_reference are required.")
                scope = _text(row.get("traffic_scope") or "all").lower()
                if scope not in {"organic", "paid", "all", "unknown"}:
                    raise GrowthIntelligenceError("traffic_scope must be organic, paid, all, or unknown.")
                if metric == "organic_reach" and scope != "organic":
                    raise GrowthIntelligenceError("organic_reach must use organic traffic_scope.")
                if metric == "paid_reach" and scope != "paid":
                    raise GrowthIntelligenceError("paid_reach must use paid traffic_scope.")
                start = _iso_date(row.get("period_start"), "period_start")
                end = _iso_date(row.get("period_end"), "period_end")
                if end < start:
                    raise GrowthIntelligenceError("period_end cannot be before period_start.")
                value = _metric_value(metric, row.get("metric_value"))
                fingerprint = json.dumps([episode_id, provider, metric, scope, start, end], separators=(",", ":"))
                observation_key = hashlib.sha256(fingerprint.encode()).hexdigest()
                key = _text(row.get("idempotency_key")) or observation_key
                source_hash = hashlib.sha256(source_reference.encode()).hexdigest()
                prepared.append((episode_id, provider, metric, value, CANONICAL_METRICS[metric], scope, start, end, source_reference, source_hash, observation_key, key, actor, correlation_id))
            before = conn.total_changes
            conn.executemany(
                """INSERT OR IGNORE INTO growth_metric_observations
                   (episode_id, provider, metric_name, metric_value, unit, traffic_scope,
                    period_start, period_end, source_reference, source_hash, observation_key,
                    idempotency_key, actor, correlation_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                prepared,
            )
            inserted = conn.total_changes - before
            conn.commit()
        return {"submitted": len(rows), "inserted": inserted, "duplicates": len(rows) - inserted}

    @staticmethod
    def _episode_mfs(rows: list[dict[str, Any]]) -> dict[str, Any]:
        latest_period_end = max((row["period_end"] for row in rows), default=None)
        latest_period_start = max(
            (row["period_start"] for row in rows if row["period_end"] == latest_period_end),
            default=None,
        )
        period_rows = [
            row for row in rows
            if row["period_end"] == latest_period_end and row["period_start"] == latest_period_start
        ]
        latest: dict[str, dict[str, Any]] = {}
        for row in period_rows:
            metric = row["metric_name"]
            if metric in MFS_COMPONENTS and metric not in latest:
                latest[metric] = row
        missing = [metric for metric in MFS_COMPONENTS if metric not in latest]
        if missing:
            return {"status": "incomplete", "score": None, "period_start": latest_period_start, "period_end": latest_period_end, "missing_metrics": missing, "components": {key: latest[key]["metric_value"] for key in latest}}
        # Reach is normalized to the current 5k organic-breakout operating target.
        normalized = [min(100.0, latest["organic_reach"]["metric_value"] / 50.0)]
        normalized.extend(float(latest[key]["metric_value"]) for key in MFS_COMPONENTS[1:])
        score = math.prod(max(value, 0.01) for value in normalized) ** (1 / 4)
        return {"status": "ready", "score": round(score, 1), "period_start": latest_period_start, "period_end": latest_period_end, "missing_metrics": [], "components": {key: latest[key]["metric_value"] for key in MFS_COMPONENTS}, "method": "Geometric mean; organic reach normalized to the 5,000-view breakout target."}

    def dashboard(self) -> dict[str, Any]:
        with connect_database(self.db_path) as conn:
            conn.row_factory = __import__("sqlite3").Row
            rows = [dict(row) for row in conn.execute("SELECT * FROM growth_metric_observations ORDER BY period_end DESC, id DESC").fetchall()]
            episodes = [dict(row) for row in conn.execute("SELECT * FROM episodes ORDER BY release_date DESC, id DESC").fetchall()]
            experiments = [dict(row) for row in conn.execute("SELECT * FROM growth_experiments ORDER BY updated_at DESC, id DESC").fetchall()]
        by_episode: dict[int, list[dict[str, Any]]] = {}
        for row in rows:
            if row["episode_id"] is not None:
                by_episode.setdefault(int(row["episode_id"]), []).append(row)
        episode_scores = []
        episode_map = {int(item["id"]): item for item in episodes}
        for episode_id, metrics in by_episode.items():
            episode = episode_map.get(episode_id, {})
            episode_scores.append({"episode_id": episode_id, "episode_title": episode.get("published_title") or episode.get("episode_title") or "Untitled episode", "mfs": self._episode_mfs(metrics)})
        released = [episode for episode in episodes if _text(episode.get("release_status")).lower() == "released"][:12]
        pillar_counts = {name: 0 for name in EDITORIAL_PILLARS}
        unclassified = 0
        for episode in released:
            pillar = build_editorial_fit(episode)["pillar"]
            if pillar in pillar_counts:
                pillar_counts[pillar] += 1
            else:
                unclassified += 1
        denominator = len(released) or 1
        guardrails = {
            "Heal": "Heal + Become: 5–7 of 12",
            "Become": "Heal + Become: 5–7 of 12",
            "Love": "Love + Purpose: 3–5 of 12",
            "Purpose": "Love + Purpose: 3–5 of 12",
            "Lead": "1–2 of 12; human story required",
        }
        editorial_mix = [
            {
                "pillar": name,
                "count": pillar_counts[name],
                "actual_share_pct": round(pillar_counts[name] * 100 / denominator, 1),
                "twelve_release_guardrail": guardrails[name],
            }
            for name in EDITORIAL_PILLARS
        ]
        latest_period = max((row["period_end"] for row in rows), default=None)
        current_rows = [row for row in rows if row["period_end"] == latest_period]
        current_total = lambda metric: sum(row["metric_value"] for row in current_rows if row["metric_name"] == metric)
        paid = sum(row["metric_value"] for row in current_rows if row["metric_name"] == "paid_reach")
        organic = sum(row["metric_value"] for row in current_rows if row["metric_name"] == "organic_reach")
        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "freshness": "no_data" if not latest_period else "current" if (datetime.now(timezone.utc).date() - datetime.fromisoformat(latest_period).date()).days <= 14 else "stale",
            "latest_period_end": latest_period,
            "quality": {"observation_count": len(rows), "episodes_with_evidence": len(by_episode), "mfs_ready": sum(item["mfs"]["status"] == "ready" for item in episode_scores), "unclassified_released_episodes": unclassified, "editorial_window_count": len(released)},
            "reach": {"organic": organic, "paid": paid, "paid_share_pct": round(paid * 100 / (paid + organic), 1) if paid + organic else None},
            "discovery": {"downloads_7d": current_total("downloads_7d"), "spotify_home_impressions": current_total("spotify_home_impressions"), "spotify_search_impressions": current_total("spotify_search_impressions")},
            "distribution": {"guest_shares": current_total("guest_shares"), "guest_newsletter_inclusions": current_total("guest_newsletter_inclusions")},
            "owned_audience": {"email_subscribers_gained": current_total("email_subscribers_gained"), "site_to_podcast_conversion_pct": max((row["metric_value"] for row in current_rows if row["metric_name"] == "site_to_podcast_conversion_pct"), default=None)},
            "episode_scores": sorted(episode_scores, key=lambda item: (item["mfs"]["score"] is None, -(item["mfs"]["score"] or 0))),
            "editorial_mix": editorial_mix,
            "experiments": experiments,
            "metric_definitions": CANONICAL_METRICS,
        }

    def create_experiment(self, payload: dict[str, Any], *, actor: str, correlation_id: str = "") -> dict[str, Any]:
        required = {key: _text(payload.get(key)) for key in ("name", "hypothesis", "primary_metric", "control_label", "treatment_label")}
        if not all(required.values()):
            raise GrowthIntelligenceError("Experiment name, hypothesis, primary metric, control, and treatment are required.")
        if required["primary_metric"] not in CANONICAL_METRICS:
            raise GrowthIntelligenceError("Experiment primary_metric must be canonical.")
        starts_on = _iso_date(payload["starts_on"], "starts_on") if payload.get("starts_on") else None
        ends_on = _iso_date(payload["ends_on"], "ends_on") if payload.get("ends_on") else None
        if starts_on and ends_on and ends_on < starts_on:
            raise GrowthIntelligenceError("Experiment ends_on cannot be before starts_on.")
        with connect_database(self.db_path) as conn:
            cursor = conn.execute("""INSERT INTO growth_experiments
                (name, hypothesis, primary_metric, control_label, treatment_label, status, starts_on, ends_on, actor, correlation_id)
                VALUES (?, ?, ?, ?, ?, 'draft', ?, ?, ?, ?)""", (*required.values(), starts_on, ends_on, actor, correlation_id))
            experiment_id = int(cursor.lastrowid)
            conn.commit()
        return {"id": experiment_id, "status": "draft", **required, "starts_on": starts_on, "ends_on": ends_on}
