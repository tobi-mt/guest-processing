"""Source-backed podcast reach and distribution intelligence."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import re
from typing import Any

from guest_database_manager.db_connection import connect_database


ADDITIVE_METRICS = {"downloads", "plays", "streams", "downloads_7d", "watch_time_hours"}
AUDIENCE_METRICS = {"unique_listeners", "listeners", "followers", "subscribers"}
DEVICE_PREFIX = "device_"
COUNTRY_PREFIX = "country_"
DISPLAY_METRICS = {
    "downloads", "plays", "streams", "unique_listeners", "listeners", "followers",
    "subscribers", "watch_time_hours", "average_view_duration_seconds", "organic_reach",
    "consumption_depth_pct", "engaged_listeners",
}


class PodcastInsights:
    def __init__(self, db_path: str | Path):
        self.db_path = str(db_path)

    def dashboard(self) -> dict[str, Any]:
        with connect_database(self.db_path) as conn:
            conn.row_factory = __import__("sqlite3").Row
            rows = [dict(row) for row in conn.execute(
                """SELECT episode_id, provider, metric_name, metric_value, unit, period_start, period_end,
                          source_reference, source_class, overlap_group, country_code, city,
                          device_type, app_name, age_group, gender, traffic_source, imported_at
                          , platform_content_id, platform_content_title
                   FROM current_growth_metric_observations ORDER BY period_end, id"""
            ).fetchall()]
            platform_rows = [dict(row) for row in conn.execute(
                """SELECT platform_key, display_name, kind, listing_url, discovery_method,
                          evidence_level, status, last_verified_at, last_error_code,
                          distribution_mode, analytics_mode, directory_source
                   FROM podcast_platform_registry ORDER BY display_name"""
            ).fetchall()]
            identified_channels = int(conn.execute(
                """SELECT COUNT(*) FROM analytics_oauth_connections
                   WHERE provider='google' AND youtube_channel_id != '' AND status != 'disconnected'"""
            ).fetchone()[0])

        scoped_youtube = {str(row["provider"]) for row in rows if str(row["provider"]).startswith("youtube:")}
        if identified_channels and len(scoped_youtube) >= identified_channels:
            scoped_keys = {
                (str(row["metric_name"]), str(row["period_start"]), str(row["period_end"]))
                for row in rows if str(row["provider"]).startswith("youtube:")
            }
            rows = [
                row for row in rows
                if str(row["provider"]) != "youtube"
                or (str(row["metric_name"]), str(row["period_start"]), str(row["period_end"])) not in scoped_keys
            ]

        provider_groups: dict[str, list[dict[str, Any]]] = {}
        period_groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
        grain_groups: dict[tuple[str, str, str, str], int] = {}
        for row in rows:
            provider = str(row["provider"]).strip().casefold()
            provider_groups.setdefault(provider, []).append(row)
            period = (row["period_start"], row["period_end"])
            period_groups.setdefault(period, []).append(row)
            grain_key = (provider, row["metric_name"], *period)
            grain_groups[grain_key] = grain_groups.get(grain_key, 0) | (1 if row.get("episode_id") is None else 2)

        providers = sorted(provider_groups)
        provider_cards = []
        for provider in providers:
            provider_rows = provider_groups[provider]
            latest_end = max(row["period_end"] for row in provider_rows)
            latest = []
            metric_groups: dict[str, list[dict[str, Any]]] = {}
            for row in provider_rows:
                metric_groups.setdefault(row["metric_name"], []).append(row)
            for metric_rows in metric_groups.values():
                metric_end = max(row["period_end"] for row in metric_rows)
                latest.extend(row for row in metric_rows if row["period_end"] == metric_end)
            metrics: dict[str, float] = {}
            for metric in {row["metric_name"] for row in latest}:
                if metric in DISPLAY_METRICS:
                    metrics[metric] = self._metric_total(latest, metric)
            visible_latest = [row for row in latest if row["metric_name"] in metrics]
            provider_cards.append({
                "provider": provider,
                "period_end": max((row["period_end"] for row in visible_latest), default=latest_end),
                "period_start": min((row["period_start"] for row in visible_latest), default=latest_end),
                "metrics": metrics,
                "sources": sorted({row["source_reference"] for row in visible_latest}),
                "freshness": self._freshness(latest_end),
            })

        periods = sorted(period_groups)
        latest_common_period = max(periods, default=None, key=lambda value: value[1])
        downloads_total, downloads_period = self._latest_family_total(rows, {"downloads", "downloads_7d"})
        youtube_rows = [row for row in rows if str(row["provider"]).casefold().startswith("youtube")]
        plays_total, plays_period = self._latest_family_total(youtube_rows, {"plays", "streams"})
        spotify_rows = [row for row in rows if str(row["provider"]).casefold() == "spotify"]
        spotify_window = self._rolling_daily_metrics(
            spotify_rows, {"downloads", "plays", "unique_listeners"}, days=28
        )
        spotify_lifetime = self._spotify_lifetime(spotify_rows)
        spotify_monthly = self._spotify_monthly(spotify_rows)
        apple_rows = [row for row in rows if str(row["provider"]).casefold() == "apple_podcasts"]
        apple_summary = self._apple_summary(apple_rows)
        apple_monthly = self._apple_monthly(apple_rows)
        audience_by_platform = []
        for card in provider_cards:
            for metric in AUDIENCE_METRICS:
                if metric in card["metrics"]:
                    audience_by_platform.append({
                        "provider": card["provider"], "metric": metric,
                        "value": card["metrics"][metric], "period_end": card["period_end"],
                    })

        devices = self._dimension_breakdown(rows, DEVICE_PREFIX)
        countries = self._dimension_breakdown(
            [
                row for row in rows
                if not str(row["metric_name"]).startswith("country_plays_")
                and not (
                    str(row["provider"]).casefold() == "apple_podcasts"
                    and str(row["metric_name"]).startswith(COUNTRY_PREFIX)
                )
            ],
            COUNTRY_PREFIX,
        )
        countries.extend(self._additive_dimension_breakdown(
            rows, "country_plays_", provider="apple_podcasts"
        ))
        cities = self._additive_dimension_breakdown(
            rows, "city_plays_", provider="apple_podcasts"
        )
        demographics = self._structured_dimension_breakdown(
            rows, metric="viewer_percentage", label_fields=("age_group", "gender"), percentage_values=True
        )
        traffic_sources = self._structured_dimension_breakdown(
            rows, metric="traffic_source_views", label_fields=("traffic_source",)
        )
        listening_apps = self._structured_dimension_breakdown(
            [row for row in rows if row.get("source_class") == "host_rss_delivery"],
            metric="downloads", label_fields=("app_name",)
        )
        top_videos = self._top_platform_content(rows)
        trend = []
        trend_groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for row in spotify_rows:
            if row["period_start"] == row["period_end"]:
                trend_groups.setdefault((row["period_start"], row["period_end"]), []).append(row)
        for start, end in sorted(trend_groups):
            period_rows = trend_groups[(start, end)]
            if not any(row["metric_name"] in {"downloads", "downloads_7d", "plays", "streams"} for row in period_rows):
                continue
            trend.append({
                "period_start": start, "period_end": end,
                "downloads": self._metric_total(period_rows, "downloads") + self._metric_total(period_rows, "downloads_7d")
                if any(row["metric_name"] in {"downloads", "downloads_7d"} for row in period_rows) else None,
                "plays": self._metric_total(period_rows, "plays") + self._metric_total(period_rows, "streams")
                if any(row["metric_name"] in {"plays", "streams"} for row in period_rows) else None,
            })

        metric_names = {row["metric_name"] for row in rows}
        has_downloads = bool(metric_names & {"downloads", "downloads_7d"})
        has_youtube_plays = any(row["metric_name"] in {"plays", "streams"} for row in youtube_rows)
        latest_end = max((row["period_end"] for row in rows), default=None)
        stale = sum(self._freshness(card["period_end"]) == "stale" for card in provider_cards)
        mixed_grain = sorted(
            f"{provider}:{metric}:{start}:{end}"
            for (provider, metric, start, end), grain_mask in grain_groups.items()
            if grain_mask == 3
        )
        verified_platforms = sum(row["status"] == "available" for row in platform_rows)
        expected_platforms = [row for row in platform_rows if row["distribution_mode"] != "expected_missing"]
        available_expected = sum(row["status"] == "available" for row in expected_platforms)
        platforms = [{
            "key": row["platform_key"], "name": row["display_name"], "kind": row["kind"],
            "url": row["listing_url"], "source": row["discovery_method"],
            "availability": row["status"], "evidence_level": row["evidence_level"],
            "verified_on": row["last_verified_at"], "error_code": row["last_error_code"],
            "distribution_mode": row["distribution_mode"], "analytics_mode": row["analytics_mode"],
            "directory_source": row["directory_source"],
        } for row in platform_rows]
        return {
            "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "summary": {
                "verified_platforms": verified_platforms,
                "known_platforms": len(platforms),
                "expected_distribution_targets": len(expected_platforms),
                "direct_listings": sum(row["distribution_mode"] in {"direct_listing", "direct_video"} for row in platform_rows),
                "catalog_listings": sum(row["distribution_mode"] == "catalog_listing" for row in platform_rows),
                "rss_subscription_targets": sum(row["distribution_mode"] == "rss_subscription" for row in platform_rows),
                "known_missing_platforms": sum(row["distribution_mode"] == "expected_missing" for row in platform_rows),
                "distribution_coverage_pct": round(available_expected * 100 / len(expected_platforms), 1) if expected_platforms else 0.0,
                "platforms_with_private_analytics": len(provider_cards),
                "latest_period_start": latest_common_period[0] if latest_common_period else None,
                "latest_period_end": latest_common_period[1] if latest_common_period else None,
                "downloads": downloads_total if has_downloads else None,
                "downloads_period_end": downloads_period[1] if downloads_period else None,
                "plays": plays_total if has_youtube_plays else None,
                "plays_period_end": plays_period[1] if plays_period else None,
                "spotify_28d": spotify_window,
                "spotify_lifetime": spotify_lifetime,
                "apple": apple_summary,
                "unique_listeners": None,
                "unique_listener_explanation": "Cross-platform listeners are not additive; a deduplicated total requires compatible identity-level reporting from every provider.",
            },
            "platforms": platforms,
            "provider_strength": provider_cards,
            "audience_by_platform": audience_by_platform,
            "devices": devices,
            "countries": countries,
            "cities": cities,
            "demographics": demographics,
            "traffic_sources": traffic_sources,
            "listening_apps": listening_apps,
            "top_platform_content": top_videos,
            "trend": trend[-14:],
            "monthly_trends": {"spotify": spotify_monthly, "apple_podcasts": apple_monthly},
            "quality": {
                "status": "no_data" if not rows else "partial" if len(provider_cards) < max(len(platforms), 1) else "covered",
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
        selected = PodcastInsights._prefer_authoritative_overlap_sources(selected)
        total = 0.0
        for provider in {str(row["provider"]) for row in selected}:
            provider_rows = [row for row in selected if str(row["provider"]) == provider]
            show_rows = [row for row in provider_rows if row.get("episode_id") is None]
            total += sum(float(row["metric_value"]) for row in (show_rows or provider_rows))
        return total

    @staticmethod
    def _prefer_authoritative_overlap_sources(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Keep one authoritative source family for explicitly overlapping evidence."""
        ungrouped = [row for row in rows if not str(row.get("overlap_group") or "")]
        grouped: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            overlap_group = str(row.get("overlap_group") or "")
            if overlap_group:
                grouped.setdefault(overlap_group, []).append(row)
        priority = {
            "host_rss_delivery": 50,
            "provider_native": 40,
            "video_platform_consumption": 40,
            "host_cross_platform_aggregate": 30,
            "website": 20,
            "aggregator_copy": 10,
        }
        selected = list(ungrouped)
        for candidates in grouped.values():
            families: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
            for row in candidates:
                family = (
                    str(row.get("source_class") or ""),
                    str(row.get("provider") or ""),
                    str(row.get("source_reference") or ""),
                )
                families.setdefault(family, []).append(row)
            chosen_family = max(
                families,
                key=lambda family: (
                    priority.get(family[0], 0),
                    max(str(item.get("imported_at") or "") for item in families[family]),
                    family,
                ),
            )
            selected.extend(families[chosen_family])
        return selected

    @classmethod
    def _latest_family_total(cls, rows: list[dict[str, Any]], metrics: set[str]) -> tuple[float, tuple[str, str] | None]:
        candidates = [row for row in rows if row["metric_name"] in metrics]
        period = max(
            {(row["period_start"], row["period_end"]) for row in candidates},
            default=None,
            key=lambda value: (value[1], value[0]),
        )
        selected = [row for row in candidates if period and (row["period_start"], row["period_end"]) == period]
        return sum(cls._metric_total(selected, metric) for metric in metrics), period

    @classmethod
    def _rolling_daily_metrics(
        cls, rows: list[dict[str, Any]], metrics: set[str], *, days: int
    ) -> dict[str, Any] | None:
        daily = [row for row in rows if row["metric_name"] in metrics and row["period_start"] == row["period_end"]]
        latest = max((datetime.fromisoformat(row["period_end"]).date() for row in daily), default=None)
        if latest is None:
            return None
        start = latest - timedelta(days=days - 1)
        selected = [
            row for row in daily
            if start <= datetime.fromisoformat(row["period_end"]).date() <= latest
        ]
        latest_rows = [row for row in selected if row["period_end"] == latest.isoformat()]
        return {
            "period_start": start.isoformat(),
            "period_end": latest.isoformat(),
            "downloads": cls._metric_total(selected, "downloads"),
            "plays": cls._metric_total(selected, "plays") + cls._metric_total(selected, "streams"),
            "latest_daily_audience": cls._metric_total(latest_rows, "unique_listeners"),
        }

    @classmethod
    def _spotify_lifetime(cls, rows: list[dict[str, Any]]) -> dict[str, Any] | None:
        daily = [row for row in rows if row["period_start"] == row["period_end"]]
        if not daily:
            return None
        return {
            "period_start": min(row["period_start"] for row in daily),
            "period_end": max(row["period_end"] for row in daily),
            "downloads": cls._metric_total(daily, "downloads"),
            "plays": cls._metric_total(daily, "plays") + cls._metric_total(daily, "streams"),
        }

    @classmethod
    def _spotify_monthly(cls, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        months: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            if row["period_start"] == row["period_end"] and row["metric_name"] in {"downloads", "plays", "streams"}:
                months.setdefault(row["period_end"][:7], []).append(row)
        return [{
            "period": month,
            "downloads": cls._metric_total(month_rows, "downloads"),
            "plays": cls._metric_total(month_rows, "plays") + cls._metric_total(month_rows, "streams"),
        } for month, month_rows in sorted(months.items())]

    @staticmethod
    def _apple_summary(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
        country_rows = [row for row in rows if str(row["metric_name"]).startswith("country_")]
        if not country_rows:
            return None
        plays = [row for row in country_rows if str(row["metric_name"]).startswith("country_plays_")]
        listening = [row for row in country_rows if str(row["metric_name"]).startswith("country_listening_seconds_")]
        followers = [row for row in rows if row["metric_name"] == "followers"]
        latest_month = max((row["period_end"] for row in country_rows), default=None)
        latest = [row for row in country_rows if row["period_end"] == latest_month]
        listeners = [row for row in latest if str(row["metric_name"]).startswith("country_listeners_")]
        engaged = [row for row in latest if str(row["metric_name"]).startswith("country_engaged_listeners_")]
        latest_followers = max(followers, key=lambda row: row["period_end"], default=None)
        return {
            "period_start": min(row["period_start"] for row in country_rows),
            "period_end": max(row["period_end"] for row in country_rows),
            "plays": sum(float(row["metric_value"]) for row in plays),
            "listening_time_hours": sum(float(row["metric_value"]) for row in listening) / 3600,
            "latest_month_listeners": sum(float(row["metric_value"]) for row in listeners),
            "latest_month_engaged_listeners": sum(float(row["metric_value"]) for row in engaged),
            "followers": float(latest_followers["metric_value"]) if latest_followers else None,
        }

    @staticmethod
    def _apple_monthly(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        months: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            metric = str(row["metric_name"])
            if metric.startswith(("country_plays_", "country_listening_seconds_", "country_listeners_", "country_engaged_listeners_")):
                months.setdefault(row["period_start"][:7], []).append(row)
        result = []
        for month, month_rows in sorted(months.items()):
            result.append({
                "period": month,
                "plays": sum(float(row["metric_value"]) for row in month_rows if str(row["metric_name"]).startswith("country_plays_")),
                "listening_time_hours": sum(float(row["metric_value"]) for row in month_rows if str(row["metric_name"]).startswith("country_listening_seconds_")) / 3600,
                "listeners": sum(float(row["metric_value"]) for row in month_rows if str(row["metric_name"]).startswith("country_listeners_")),
                "engaged_listeners": sum(float(row["metric_value"]) for row in month_rows if str(row["metric_name"]).startswith("country_engaged_listeners_")),
            })
        return result

    @staticmethod
    def _has_mixed_grain(rows: list[dict[str, Any]], provider: str, metric: str,
                         start: str, end: str) -> bool:
        selected = [row for row in rows if str(row["provider"]).casefold() == provider and
                    row["metric_name"] == metric and row["period_start"] == start and row["period_end"] == end]
        return any(row.get("episode_id") is None for row in selected) and any(row.get("episode_id") is not None for row in selected)

    @staticmethod
    def _dimension_breakdown(rows: list[dict[str, Any]], prefix: str) -> list[dict[str, Any]]:
        candidates = [row for row in rows if str(row["metric_name"]).startswith(prefix)]
        values = []
        for provider, metric in sorted({(str(row["provider"]), str(row["metric_name"])) for row in candidates}):
            provider_metric_rows = [
                row for row in candidates
                if str(row["provider"]) == provider and row["metric_name"] == metric
            ]
            latest = max((row["period_end"] for row in provider_metric_rows), default=None)
            relevant = [row for row in provider_metric_rows if row["period_end"] == latest]
            show_rows = [row for row in relevant if row.get("episode_id") is None]
            values.append({"name": metric[len(prefix):].replace("_", " ").title(),
                           "value": sum(float(row["metric_value"]) for row in (show_rows or relevant)),
                           "provider": provider, "period_end": latest})
        provider_totals = {
            provider: sum(item["value"] for item in values if item["provider"] == provider)
            for provider in {item["provider"] for item in values}
        }
        for item in values:
            total = provider_totals[item["provider"]]
            item["share_pct"] = round(item["value"] * 100 / total, 1) if total else None
        return sorted(values, key=lambda item: (item["provider"], -item["value"]))

    @staticmethod
    def _additive_dimension_breakdown(
        rows: list[dict[str, Any]], prefix: str, *, provider: str
    ) -> list[dict[str, Any]]:
        candidates = [
            row for row in rows
            if str(row["provider"]).casefold() == provider and str(row["metric_name"]).startswith(prefix)
        ]
        values = []
        for metric in sorted({str(row["metric_name"]) for row in candidates}):
            metric_rows = [row for row in candidates if row["metric_name"] == metric]
            show_rows = [row for row in metric_rows if row.get("episode_id") is None]
            name = re.sub(r"_\d+$", "", metric[len(prefix):]).replace("_", " ").title()
            values.append({
                "name": name,
                "value": sum(float(row["metric_value"]) for row in (show_rows or metric_rows)),
                "provider": provider,
                "period_start": min(row["period_start"] for row in metric_rows),
                "period_end": max(row["period_end"] for row in metric_rows),
                "measure": "plays",
            })
        total = sum(item["value"] for item in values)
        for item in values:
            item["share_pct"] = round(item["value"] * 100 / total, 1) if total else None
        return sorted(values, key=lambda item: -item["value"])

    @staticmethod
    def _structured_dimension_breakdown(
        rows: list[dict[str, Any]], *, metric: str, label_fields: tuple[str, ...],
        percentage_values: bool = False,
    ) -> list[dict[str, Any]]:
        candidates = [row for row in rows if row["metric_name"] == metric]
        values = []
        for provider in sorted({str(row["provider"]) for row in candidates}):
            provider_rows = [row for row in candidates if str(row["provider"]) == provider]
            latest = max((row["period_end"] for row in provider_rows), default=None)
            latest_rows = [row for row in provider_rows if row["period_end"] == latest]
            total = sum(float(row["metric_value"]) for row in latest_rows)
            for row in latest_rows:
                value = float(row["metric_value"])
                labels = []
                for field in label_fields:
                    raw_label = str(row.get(field) or "unknown")
                    age_match = re.fullmatch(r"age(\d+)[_-](\d+|plus)", raw_label, re.I) if field == "age_group" else None
                    labels.append(
                        f"{age_match.group(1)}–{age_match.group(2)}" if age_match
                        else raw_label.replace("_", " ").title()
                    )
                values.append({
                    "name": " · ".join(labels), "value": value, "provider": provider,
                    "period_end": latest,
                    "share_pct": round(value, 1) if percentage_values else round(value * 100 / total, 1) if total else None,
                    "measure": "audience share" if percentage_values else "views",
                })
        return sorted(values, key=lambda item: (item["provider"], -item["value"]))

    @staticmethod
    def _top_platform_content(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        candidates = [
            row for row in rows
            if row["metric_name"].startswith("video_") and str(row.get("platform_content_id") or "")
        ]
        grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
        for row in candidates:
            grouped.setdefault((str(row["provider"]), str(row["platform_content_id"]), row["period_end"]), []).append(row)
        latest_by_content: dict[tuple[str, str], tuple[str, list[dict[str, Any]]]] = {}
        for (provider, content_id, period_end), content_rows in grouped.items():
            key = (provider, content_id)
            if key not in latest_by_content or period_end > latest_by_content[key][0]:
                latest_by_content[key] = (period_end, content_rows)
        result = []
        for (provider, content_id), (period_end, content_rows) in latest_by_content.items():
            metrics = {row["metric_name"]: float(row["metric_value"]) for row in content_rows}
            result.append({
                "provider": provider, "platform_content_id": content_id,
                "title": next((str(row.get("platform_content_title") or "") for row in content_rows if row.get("platform_content_title")), content_id),
                "period_end": period_end, "metrics": metrics,
            })
        return sorted(result, key=lambda item: -item["metrics"].get("video_views", 0))[:20]
