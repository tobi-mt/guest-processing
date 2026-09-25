"""Source-backed podcast reach and distribution intelligence."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from guest_database_manager.db_connection import connect_database


PLATFORMS = (
    {"name": "Spotify", "kind": "listening", "url": "https://open.spotify.com/show/0trwqguYCic32smqh3Ny60", "source": "Public show listing"},
    {"name": "Apple Podcasts", "kind": "listening", "url": "https://podcasts.apple.com/podcast/mirror-talk/id1518394292", "source": "Public show listing"},
    {"name": "YouTube", "kind": "video", "url": "https://www.youtube.com/@mirrortalkpodcast", "source": "Official channel"},
    {"name": "Amazon Music", "kind": "listening", "url": "https://music.amazon.com/podcasts/8996f709-4711-4d9f-8563-93b770bf42ae/mirror-talk-soulful-conversations", "source": "Public show listing"},
    {"name": "iHeartRadio", "kind": "listening", "url": "https://www.iheart.com/podcast/269-mirror-talk-soulful-conver-69159083/", "source": "Public show listing"},
    {"name": "Open podcast apps", "kind": "rss", "url": "https://anchor.fm/s/261b1464/podcast/rss", "source": "Canonical RSS feed"},
)

ADDITIVE_METRICS = {"downloads", "plays", "streams", "downloads_7d", "watch_time_hours"}
AUDIENCE_METRICS = {"unique_listeners", "listeners", "followers", "subscribers"}
DEVICE_PREFIX = "device_"
COUNTRY_PREFIX = "country_"


class PodcastInsights:
    def __init__(self, db_path: str | Path):
        self.db_path = str(db_path)

    def dashboard(self) -> dict[str, Any]:
        with connect_database(self.db_path) as conn:
            conn.row_factory = __import__("sqlite3").Row
            rows = [dict(row) for row in conn.execute(
                """SELECT episode_id, provider, metric_name, metric_value, unit, period_start, period_end,
                          source_reference, imported_at
                   FROM growth_metric_observations ORDER BY period_end, id"""
            ).fetchall()]

        providers = sorted({str(row["provider"]).strip().casefold() for row in rows})
        provider_cards = []
        for provider in providers:
            provider_rows = [row for row in rows if str(row["provider"]).strip().casefold() == provider]
            latest_end = max(row["period_end"] for row in provider_rows)
            latest = [row for row in provider_rows if row["period_end"] == latest_end]
            metrics: dict[str, float] = {}
            for metric in {row["metric_name"] for row in latest}:
                metrics[metric] = self._metric_total(latest, metric)
            provider_cards.append({
                "provider": provider,
                "period_end": latest_end,
                "period_start": min(row["period_start"] for row in latest),
                "metrics": metrics,
                "sources": sorted({row["source_reference"] for row in latest}),
                "freshness": self._freshness(latest_end),
            })

        periods = sorted({(row["period_start"], row["period_end"]) for row in rows})
        latest_common_period = max(periods, default=None, key=lambda value: value[1])
        common_rows = [row for row in rows if latest_common_period and (row["period_start"], row["period_end"]) == latest_common_period]
        totals = {
            metric: self._metric_total(common_rows, metric)
            for metric in sorted(ADDITIVE_METRICS)
        }
        audience_by_platform = []
        for card in provider_cards:
            for metric in AUDIENCE_METRICS:
                if metric in card["metrics"]:
                    audience_by_platform.append({
                        "provider": card["provider"], "metric": metric,
                        "value": card["metrics"][metric], "period_end": card["period_end"],
                    })

        devices = self._dimension_breakdown(rows, DEVICE_PREFIX)
        countries = self._dimension_breakdown(rows, COUNTRY_PREFIX)
        trend = []
        for start, end in periods:
            period_rows = [row for row in rows if row["period_start"] == start and row["period_end"] == end]
            trend.append({
                "period_start": start, "period_end": end,
                "downloads": self._metric_total(period_rows, "downloads") + self._metric_total(period_rows, "downloads_7d"),
                "plays": self._metric_total(period_rows, "plays") + self._metric_total(period_rows, "streams"),
            })

        metric_names = {row["metric_name"] for row in rows}
        has_downloads = bool(metric_names & {"downloads", "downloads_7d"})
        has_plays = bool(metric_names & {"plays", "streams"})
        latest_end = max((row["period_end"] for row in rows), default=None)
        stale = sum(self._freshness(card["period_end"]) == "stale" for card in provider_cards)
        mixed_grain = sorted({
            f"{provider}:{metric}:{start}:{end}"
            for provider in providers for metric in metric_names for start, end in periods
            if self._has_mixed_grain(rows, provider, metric, start, end)
        })
        return {
            "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "summary": {
                "verified_platforms": len(PLATFORMS),
                "platforms_with_private_analytics": len(provider_cards),
                "latest_period_start": latest_common_period[0] if latest_common_period else None,
                "latest_period_end": latest_common_period[1] if latest_common_period else None,
                "downloads": totals.get("downloads", 0) + totals.get("downloads_7d", 0) if has_downloads else None,
                "plays": totals.get("plays", 0) + totals.get("streams", 0) if has_plays else None,
                "unique_listeners": None,
                "unique_listener_explanation": "Cross-platform listeners are not additive; a deduplicated total requires compatible identity-level reporting from every provider.",
            },
            "platforms": [{**item, "availability": "verified", "verified_on": "2026-09-25"} for item in PLATFORMS],
            "provider_strength": provider_cards,
            "audience_by_platform": audience_by_platform,
            "devices": devices,
            "countries": countries,
            "trend": trend[-24:],
            "quality": {
                "status": "no_data" if not rows else "partial" if len(provider_cards) < len(PLATFORMS) else "covered",
                "observation_count": len(rows),
                "latest_period_end": latest_end,
                "stale_provider_count": stale,
                "mixed_grain_conflicts": mixed_grain,
                "missing_core_metrics": sorted({"downloads", "unique_listeners", "consumption_depth_pct"} - metric_names),
                "limitations": [
                    "Public listings prove availability, not audience size.",
                    "Listener totals are reported per platform and are never summed across providers.",
                    "Downloads, plays, streams, and views remain distinct metrics unless a source defines them identically.",
                    "Device and country breakdowns appear only when source-backed dimensional metrics are imported.",
                    "Where show-level and episode-level rows overlap, the show-level total controls to prevent double-counting.",
                ],
            },
            "definitions": {
                "downloads": "Provider-reported file downloads for the selected period.",
                "plays": "Provider-reported starts or plays; not assumed equivalent to downloads.",
                "unique_listeners": "Distinct listeners within one provider and period; not deduplicated across platforms.",
                "platform_strength": "The latest source-backed metrics for each provider, without a fabricated composite score.",
            },
        }

    @staticmethod
    def _freshness(period_end: str) -> str:
        age = (datetime.now(timezone.utc).date() - datetime.fromisoformat(period_end).date()).days
        return "current" if age <= 14 else "aging" if age <= 45 else "stale"

    @staticmethod
    def _metric_total(rows: list[dict[str, Any]], metric: str) -> float:
        selected = [row for row in rows if row["metric_name"] == metric]
        total = 0.0
        for provider in {str(row["provider"]) for row in selected}:
            provider_rows = [row for row in selected if str(row["provider"]) == provider]
            show_rows = [row for row in provider_rows if row.get("episode_id") is None]
            total += sum(float(row["metric_value"]) for row in (show_rows or provider_rows))
        return total

    @staticmethod
    def _has_mixed_grain(rows: list[dict[str, Any]], provider: str, metric: str,
                         start: str, end: str) -> bool:
        selected = [row for row in rows if str(row["provider"]).casefold() == provider and
                    row["metric_name"] == metric and row["period_start"] == start and row["period_end"] == end]
        return any(row.get("episode_id") is None for row in selected) and any(row.get("episode_id") is not None for row in selected)

    @staticmethod
    def _dimension_breakdown(rows: list[dict[str, Any]], prefix: str) -> list[dict[str, Any]]:
        candidates = [row for row in rows if str(row["metric_name"]).startswith(prefix)]
        latest = max((row["period_end"] for row in candidates), default=None)
        selected = [row for row in candidates if row["period_end"] == latest]
        values = []
        for provider, metric in sorted({(str(row["provider"]), str(row["metric_name"])) for row in selected}):
            relevant = [row for row in selected if str(row["provider"]) == provider and row["metric_name"] == metric]
            show_rows = [row for row in relevant if row.get("episode_id") is None]
            values.append({"name": metric[len(prefix):].replace("_", " ").title(),
                           "value": sum(float(row["metric_value"]) for row in (show_rows or relevant)),
                           "provider": provider, "period_end": latest})
        total = sum(item["value"] for item in values)
        for item in values:
            item["share_pct"] = round(item["value"] * 100 / total, 1) if total else None
        return sorted(values, key=lambda item: -item["value"])
