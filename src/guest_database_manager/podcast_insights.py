"""Source-backed podcast reach and distribution intelligence."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import re
from typing import Any

import pycountry

from guest_database_manager.db_connection import connect_database


ADDITIVE_METRICS = {"downloads", "plays", "streams", "downloads_7d", "watch_time_hours"}
AUDIENCE_METRICS = {
    "unique_listeners", "new_listeners", "returning_listeners", "unique_viewers",
    "listeners", "followers", "subscribers",
}
RATING_METRICS = {"rating_average", "rating_count"}
CONTENT_NON_ADDITIVE_METRICS = {"unique_listeners", "engaged_listeners", "unique_viewers"}
# Apple's episode-export "Average Consumption" was imported as a percentage, but its values
# (1-4) contradict Apple's own listening time; previously stored rows are not displayed.
UNVERIFIED_UNIT_OVERLAP_GROUPS = {"apple_native_consumption_depth_pct"}
DEVICE_PREFIX = "device_"
COUNTRY_PREFIX = "country_"


def _canonical_country_key(value: Any) -> str:
    """Converge country names and ISO-2/ISO-3 codes on one stable key."""
    label = re.sub(r"\s+", " ", str(value or "").strip())
    if not label or label.casefold() == "unknown":
        return ""
    candidate = label.upper() if len(label) in {2, 3} else label
    try:
        return str(pycountry.countries.lookup(candidate).alpha_2).casefold()
    except LookupError:
        return label.casefold()
DISPLAY_METRICS = {
    "downloads", "plays", "streams", "unique_listeners", "listeners", "followers",
    "subscribers", "watch_time_hours", "average_view_duration_seconds", "organic_reach",
    "consumption_depth_pct", "engaged_listeners", "unique_viewers",
    "new_listeners", "returning_listeners",
    "lifetime_plays", "lifetime_watch_time_hours",
    "video_lifetime_views", "video_lifetime_watch_time_hours",
    "video_lifetime_average_view_duration_seconds",
    "plays_downloads",
    "web_player_play_starts", "web_player_unique_users", "web_player_pauses",
    "web_player_progress_25", "web_player_progress_50", "web_player_progress_75",
    "web_player_completions", "web_player_referral_users",
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
            episode_titles = {
                int(row["id"]): next((
                    str(row[key]).strip() for key in ("published_title", "working_title", "episode_title")
                    if row[key] and str(row[key]).strip()
                ), f"Episode {row['id']}")
                for row in conn.execute(
                    "SELECT id, published_title, working_title, episode_title FROM episodes"
                ).fetchall()
            }

        # Public ratings measure sentiment, not reach; keeping them out of the reach rows
        # prevents a daily public snapshot from masking a stale private provider export.
        rating_rows = [row for row in rows if row["metric_name"] in RATING_METRICS]
        rows = [
            row for row in rows
            if row["metric_name"] not in RATING_METRICS
            and row.get("overlap_group") not in UNVERIFIED_UNIT_OVERLAP_GROUPS
        ]
        rows = self._prefer_primary_evidence(rows)
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
                end_rows = [row for row in metric_rows if row["period_end"] == metric_end]
                show_rows = [
                    row for row in end_rows
                    if row.get("episode_id") is None and not row.get("platform_content_id")
                ]
                if show_rows:
                    # A daily row and a multi-day window can end on the same date; adding them
                    # would double count, so show-level cards use the shortest latest window.
                    show_period = max(
                        {(row["period_start"], row["period_end"]) for row in show_rows},
                        key=lambda value: (value[1], value[0]),
                    )
                    end_rows = [
                        row for row in show_rows
                        if (row["period_start"], row["period_end"]) == show_period
                    ]
                latest.extend(end_rows)
            metrics: dict[str, float] = {}
            for metric in {row["metric_name"] for row in latest}:
                # Per-video averages describe individual videos; their sum is not a channel average.
                if metric not in DISPLAY_METRICS or metric == "video_lifetime_average_view_duration_seconds":
                    continue
                metric_latest = [row for row in latest if row["metric_name"] == metric]
                content_only = all(
                    row.get("episode_id") is not None or row.get("platform_content_id")
                    for row in metric_latest
                )
                if content_only and metric in CONTENT_NON_ADDITIVE_METRICS:
                    # One person who hears several episodes appears in each episode's count.
                    continue
                if content_only and metric == "consumption_depth_pct":
                    weighted = self._play_weighted_depth(metric_latest, latest)
                    if weighted is not None:
                        metrics[metric] = weighted
                    continue
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
        spotify_daily = self._spotify_daily(spotify_rows)
        spotify_monthly = self._spotify_monthly(spotify_rows)
        apple_rows = [row for row in rows if str(row["provider"]).casefold() == "apple_podcasts"]
        apple_summary = self._apple_summary(apple_rows)
        apple_monthly = self._apple_monthly(apple_rows)
        provider_monthly = self._provider_monthly_trends(rows)
        if spotify_monthly:
            provider_monthly["spotify"] = spotify_monthly
        if apple_monthly:
            provider_monthly["apple_podcasts"] = apple_monthly
        performance_trend = self._performance_trend(
            rows, youtube_rows, expected_youtube_channels=identified_channels
        )
        global_rollup = self._global_rollup(rows, spotify_window, youtube_rows)
        self._apply_comparable_performance(global_rollup, performance_trend)
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
        traffic_sources.extend(self._structured_dimension_breakdown(
            rows, metric="web_player_referral_users", label_fields=("traffic_source",)
        ))
        listening_apps = self._structured_dimension_breakdown(
            [row for row in rows if row.get("source_class") == "host_rss_delivery"],
            metric="downloads", label_fields=("app_name",)
        )
        if not any(item["name"] != "Unknown" for item in listening_apps):
            listening_apps = self._structured_dimension_breakdown(
                [row for row in rows if row.get("source_class") == "host_rss_delivery"],
                metric="app_share_pct", label_fields=("app_name",), percentage_values=True,
            )
        if any(item["name"] != "Unknown" for item in listening_apps):
            listening_apps = [item for item in listening_apps if item["name"] != "Unknown"]
        listening_app_total = sum(float(item["value"]) for item in listening_apps)
        for item in listening_apps:
            item["share_pct"] = (
                round(float(item["value"]) * 100 / listening_app_total, 1)
                if listening_app_total else None
            )
        listening_apps.sort(key=lambda item: -float(item["value"]))
        top_videos = self._top_platform_content(rows)
        episode_performance = self._episode_performance(rows, episode_titles)
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
        topline = self._topline_summary(
            rows=rows, platforms=platforms, countries=countries,
            audience_by_platform=audience_by_platform, spotify_daily=spotify_daily,
            spotify_lifetime=spotify_lifetime, apple_summary=apple_summary,
        )
        measurement_coverage = self._measurement_coverage(rows, provider_cards)
        platform_measurement = self._platform_measurement_coverage(
            platforms, rows, provider_cards
        )
        attention_items = self._attention_items(
            spotify_daily=spotify_daily, stale_provider_count=stale,
            missing_core_metrics=sorted({"downloads", "unique_listeners", "consumption_depth_pct"} - metric_names),
            distribution_coverage_pct=round(available_expected * 100 / len(expected_platforms), 1) if expected_platforms else 0.0,
            unconfirmed_destinations=[
                str(row["display_name"]) for row in expected_platforms if row["status"] != "available"
            ],
        )
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
                "unconfirmed_destinations": [
                    str(row["display_name"]) for row in expected_platforms if row["status"] != "available"
                ],
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
                "global_rollup": global_rollup,
                "topline": topline,
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
            "public_ratings": self._public_ratings(rating_rows, countries),
            "top_platform_content": top_videos,
            "episode_performance": episode_performance,
            "measurement_coverage": measurement_coverage,
            "platform_measurement": platform_measurement,
            "attention_items": attention_items,
            "trend": trend[-14:],
            "monthly_trends": provider_monthly,
            "daily_trends": {"spotify": spotify_daily},
            "performance_trend": performance_trend,
            "quality": {
                "status": (
                    "no_data" if not rows else "covered"
                    if platform_measurement["available_count"] > 0
                    and platform_measurement["uncovered_available_count"] == 0 else "partial"
                ),
                "observation_count": len(rows),
                "latest_period_end": latest_end,
                "stale_provider_count": stale,
                "mixed_grain_conflicts": mixed_grain,
                "missing_core_metrics": sorted({"downloads", "unique_listeners", "consumption_depth_pct"} - metric_names),
                "limitations": [
                    "Public listings prove availability, not audience size.",
                    "Listener totals are reported per platform and are never summed across providers.",
                    "Downloads, plays, streams, and views remain distinct metrics unless a source defines them identically.",
                    "Device and country breakdowns appear only when connected sources provide those dimensions.",
                    "Where show-level and episode-level rows overlap, the show-level total controls to prevent double-counting.",
                ],
            },
            "definitions": {
                "downloads": "Provider-reported file downloads for the selected period.",
                "plays": "Provider-reported starts or plays; not assumed equivalent to downloads.",
                "global_measured_activity": "Open-RSS downloads plus Spotify-native plays plus YouTube views for their latest comparable windows. Apple-native plays are excluded because Apple delivery is already represented in host-reported RSS downloads.",
                "unique_listeners": "Distinct listeners within one provider and period; not deduplicated across platforms.",
                "followers": "People who chose an ongoing follow relationship on a provider. This is a current relationship counter, not a listening total.",
                "subscribers": "People who chose an ongoing subscription relationship on a provider. This is a current relationship counter, not a listening total.",
                "audience_relationships": "Current followers and subscribers summed across connected providers. Recent listeners are excluded because they measure consumption during a provider-specific period.",
                "platform_strength": "The latest source-backed metrics for each provider, without a fabricated composite score.",
                "platform_coverage": "Every confirmed open-RSS destination is covered by the hosting total. A destination is shown separately only when its source supplies a trustworthy per-app or native-platform breakdown.",
            },
        }

    @staticmethod
    def _platform_measurement_coverage(
        platforms: list[dict[str, Any]], rows: list[dict[str, Any]],
        provider_cards: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Explain how every known destination participates without inventing app totals."""
        providers = {str(item.get("provider") or "").casefold() for item in provider_cards}
        host_rows = [
            row for row in rows
            if row.get("source_class") == "host_rss_delivery"
            and row.get("metric_name") in {"downloads", "downloads_7d"}
        ]
        host_available = bool(host_rows)

        def normalized(value: Any) -> str:
            return re.sub(r"[^a-z0-9]+", "", str(value or "").casefold())

        measured_apps = {
            normalized(row.get("app_name")) for row in host_rows if normalized(row.get("app_name"))
        }
        entries = []
        for platform in platforms:
            key = str(platform.get("key") or "").casefold()
            name = str(platform.get("name") or "")
            mode = str(platform.get("analytics_mode") or "host_rss_only")
            available = platform.get("availability") == "available"
            direct = (
                key in providers
                or (key == "youtube" and any(provider.startswith("youtube") for provider in providers))
                or (key == "apple_podcasts" and "apple" in providers)
                or (key == "mirror_talk_web" and bool(providers & {"website", "ga4", "google_analytics"}))
            )
            app_detail = normalized(name) in measured_apps
            rss_covered = available and mode in {"host_rss_only", "website_and_host_rss", "host_and_provider_export"} and host_available
            if not available:
                status = "not_available"
            elif direct:
                status = "direct_measured"
            elif app_detail:
                status = "app_measured"
            elif rss_covered:
                status = "aggregate_measured"
            else:
                status = "availability_only"
            entries.append({
                "key": key, "name": name, "status": status,
                "analytics_mode": mode,
                "included_in_total": status in {"direct_measured", "app_measured", "aggregate_measured"},
                "detail": {
                    "direct_measured": "Direct provider analytics",
                    "app_measured": "Hosting analytics with an app breakdown",
                    "aggregate_measured": "Included in the open-RSS hosting total",
                    "availability_only": "Listing confirmed; the destination does not expose separate analytics",
                    "not_available": "Not currently listed",
                }[status],
            })
        available_entries = [item for item in entries if item["status"] != "not_available"]
        covered = [item for item in available_entries if item["included_in_total"]]
        direct = [item for item in available_entries if item["status"] in {"direct_measured", "app_measured"}]
        return {
            "platforms": entries,
            "available_count": len(available_entries),
            "covered_count": len(covered),
            "direct_detail_count": len(direct),
            "aggregate_covered_count": sum(item["status"] == "aggregate_measured" for item in available_entries),
            "uncovered_available_count": len(available_entries) - len(covered),
            "host_aggregate_available": host_available,
            "note": (
                "All confirmed RSS destinations are included once in hosting delivery. "
                "Separate platform figures appear only where a source provides them."
            ),
        }

    @classmethod
    def _episode_performance(
        cls, rows: list[dict[str, Any]], episode_titles: dict[int, str]
    ) -> list[dict[str, Any]]:
        """Return compact, source-backed episode comparisons without inventing missing metrics."""
        grouped: dict[int, list[dict[str, Any]]] = {}
        for row in rows:
            if row.get("episode_id") is not None and row["metric_name"] in DISPLAY_METRICS:
                grouped.setdefault(int(row["episode_id"]), []).append(row)
        result = []
        for episode_id, episode_rows in grouped.items():
            latest_by_provider_metric: dict[tuple[str, str], dict[str, Any]] = {}
            for row in episode_rows:
                key = (str(row["provider"]), str(row["metric_name"]))
                current = latest_by_provider_metric.get(key)
                if current is None or (row["period_end"], row["imported_at"]) > (
                    current["period_end"], current["imported_at"]
                ):
                    latest_by_provider_metric[key] = row
            selected = list(latest_by_provider_metric.values())
            metrics: dict[str, float] = {}
            for metric in sorted({row["metric_name"] for row in selected}):
                metrics[metric] = sum(
                    float(row["metric_value"]) for row in selected if row["metric_name"] == metric
                )
            audio_activity = metrics.get("plays_downloads")
            if audio_activity is None:
                audio_activity = sum(metrics.get(metric, 0) for metric in ("downloads", "plays", "streams"))
            video_activity = metrics.get("video_lifetime_views", metrics.get("video_views", 0))
            activity = audio_activity + video_activity + metrics.get("web_player_play_starts", 0)
            result.append({
                "episode_id": episode_id,
                "title": episode_titles.get(episode_id, f"Episode {episode_id}"),
                "activity": activity,
                "metrics": metrics,
                "providers": sorted({str(row["provider"]) for row in selected}),
                "period_start": min(row["period_start"] for row in selected),
                "period_end": max(row["period_end"] for row in selected),
                "freshness": cls._freshness(max(row["period_end"] for row in selected)),
            })
        return sorted(result, key=lambda item: (-item["activity"], item["title"]))[:20]

    @staticmethod
    def _measurement_coverage(
        rows: list[dict[str, Any]], provider_cards: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        present = {str(row["metric_name"]) for row in rows}
        definitions = (
            ("Downloads and plays", {"downloads", "downloads_7d", "plays", "streams"}),
            ("Listening and watch time", {"listening_time_hours", "watch_time_hours", "lifetime_watch_time_hours"}),
            ("Listeners", {"unique_listeners", "listeners", "unique_viewers"}),
            ("Followers and subscribers", {"followers", "subscribers"}),
            ("Geography", set(), COUNTRY_PREFIX),
            ("Devices", set(), DEVICE_PREFIX),
            ("Completion and retention", {"consumption_depth_pct", "average_view_percentage"}),
            ("Episode performance", set()),
            ("Web-player engagement", {
                "web_player_play_starts", "web_player_progress_25", "web_player_progress_50",
                "web_player_progress_75", "web_player_completions",
            }),
        )
        result = []
        episode_metrics = {
            "downloads", "plays", "streams", "plays_downloads", "consumption_depth_pct",
            "video_views", "video_lifetime_views", "web_player_play_starts", "web_player_completions",
        }
        for definition in definitions:
            label, metrics, *prefix = definition
            if label == "Episode performance":
                available = any(
                    (row.get("episode_id") is not None or row.get("platform_content_id"))
                    and row.get("metric_name") in episode_metrics
                    for row in rows
                )
            else:
                available = bool(present & metrics) or bool(prefix and any(name.startswith(prefix[0]) for name in present))
            providers = sorted({
                str(row["provider"]) for row in rows
                if row["metric_name"] in metrics or (prefix and str(row["metric_name"]).startswith(prefix[0]))
                or (
                    label == "Episode performance"
                    and (row.get("episode_id") is not None or row.get("platform_content_id"))
                    and row.get("metric_name") in episode_metrics
                )
            })
            result.append({"label": label, "available": available, "providers": providers})
        return result

    @staticmethod
    def _attention_items(
        *, spotify_daily: list[dict[str, Any]], stale_provider_count: int,
        missing_core_metrics: list[str], distribution_coverage_pct: float,
        unconfirmed_destinations: list[str] | None = None,
    ) -> list[dict[str, str]]:
        items: list[dict[str, str]] = []
        totals = [float(row.get("downloads") or 0) + float(row.get("plays") or 0) for row in spotify_daily]
        if len(totals) >= 35:
            recent = sum(totals[-7:]) / 7
            baseline = sum(totals[-35:-7]) / 28
            if baseline:
                change = (recent - baseline) * 100 / baseline
                if abs(change) >= 25:
                    direction = "above" if change > 0 else "below"
                    items.append({
                        "severity": "positive" if change > 0 else "warning",
                        "title": f"Recent podcast activity is {abs(change):.0f}% {direction} its four-week baseline",
                        "detail": "Latest 7-day daily average compared with the preceding 28 days.",
                    })
        if stale_provider_count:
            items.append({"severity": "warning", "title": f"{stale_provider_count} source refresh is overdue", "detail": "Existing values remain visible with their source dates."})
        if distribution_coverage_pct < 100:
            names = sorted(set(unconfirmed_destinations or []))
            named_gap = ", ".join(names[:3])
            items.append({
                "severity": "neutral",
                "title": f"Distribution confirmation is {distribution_coverage_pct:.1f}% complete",
                "detail": (
                    f"Still being confirmed automatically: {named_gap}."
                    if named_gap else "Unconfirmed destinations continue to be checked automatically."
                ),
            })
        if missing_core_metrics:
            readable = ", ".join(metric.replace("_", " ") for metric in missing_core_metrics)
            items.append({"severity": "neutral", "title": "Some providers do not expose every insight", "detail": f"Currently unavailable or incomplete: {readable}. Missing values are never shown as zero."})
        return items[:3]

    @classmethod
    def _topline_summary(
        cls, *, rows: list[dict[str, Any]], platforms: list[dict[str, Any]],
        countries: list[dict[str, Any]], audience_by_platform: list[dict[str, Any]],
        spotify_daily: list[dict[str, Any]], spotify_lifetime: dict[str, Any] | None,
        apple_summary: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """Build the six defensible, all-source executive metrics."""
        video_lifetime = [
            row for row in rows
            if row.get("source_class") == "video_platform_consumption"
            and row["metric_name"] in {"lifetime_plays", "lifetime_watch_time_hours"}
        ]
        if not video_lifetime:
            video_lifetime = [
                row for row in rows
                if str(row["provider"]).startswith("youtube")
                and row["metric_name"] in {"lifetime_plays", "lifetime_watch_time_hours"}
            ]
        video_views = cls._latest_cumulative_total(video_lifetime, "lifetime_plays")
        video_hours = cls._latest_cumulative_total(video_lifetime, "lifetime_watch_time_hours")
        podcast_activity = (
            float((spotify_lifetime or {}).get("downloads") or 0)
            + float((spotify_lifetime or {}).get("plays") or 0)
        )
        open_rss_downloads = float((spotify_lifetime or {}).get("downloads") or 0)
        spotify_native_plays = float((spotify_lifetime or {}).get("plays") or 0)
        apple_hours = float((apple_summary or {}).get("listening_time_hours") or 0)
        country_names = {
            _canonical_country_key(item.get("name"))
            for item in countries
            if _canonical_country_key(item.get("name"))
            and float(item.get("value") or 0) > 0
        }
        relationship_breakdown: dict[str, float] = {}
        relationship_by_platform: list[dict[str, Any]] = []
        for item in audience_by_platform:
            metric = str(item.get("metric") or "")
            if metric in {"unique_listeners", "unique_viewers", "listeners", "followers", "subscribers"}:
                value = float(item.get("value") or 0)
                relationship_breakdown[metric] = relationship_breakdown.get(metric, 0) + value
                relationship_by_platform.append({
                    "provider": item.get("provider"), "metric": metric, "value": value,
                    "period_end": item.get("period_end"),
                })
        durable_relationships = sum(
            value for metric, value in relationship_breakdown.items()
            if metric in {"followers", "subscribers"}
        )

        recent = spotify_daily[-30:]
        previous = spotify_daily[-60:-30]
        recent_total = sum(float(item.get("downloads") or 0) + float(item.get("plays") or 0) for item in recent)
        previous_total = sum(float(item.get("downloads") or 0) + float(item.get("plays") or 0) for item in previous)
        growth_pct = (
            round((recent_total - previous_total) * 1000 / previous_total) / 10
            if previous_total and len(recent) == 30 and len(previous) == 30 else None
        )
        return {
            "downloads_plays": (
                podcast_activity + video_views
                if spotify_lifetime is not None or video_lifetime else None
            ),
            "podcast_downloads_plays": podcast_activity,
            "open_rss_downloads": open_rss_downloads,
            "spotify_native_plays": spotify_native_plays,
            "video_views": video_views,
            "activity_coverage_note": (
                "Open podcast apps (hosting/RSS) are counted once, then separate Spotify-native "
                "plays and YouTube views are added. App breakdowns decompose the hosting total and "
                "are never added again. Web-player starts remain separate unless verified outside "
                "hosting delivery."
            ),
            "listening_watch_hours": (
                apple_hours + video_hours
                if apple_summary is not None or video_lifetime else None
            ),
            "apple_listening_hours": apple_hours,
            "video_watch_hours": video_hours,
            "youtube_watch_hours": video_hours,
            "hours_coverage_note": "Listening and watch time from every connected source that exposes a lifetime duration; unavailable provider durations remain blank.",
            "countries_reached": len(country_names),
            "platforms_available": sum(item.get("availability") == "available" for item in platforms),
            "audience_relationships": durable_relationships,
            "audience_relationship_breakdown": relationship_breakdown,
            "audience_relationship_by_platform": relationship_by_platform,
            "audience_relationship_note": "Known followers and subscriptions. Listener counts are shown separately by platform and period because they are not additive.",
            "growth_pct": growth_pct,
            "growth_current": recent_total if recent else None,
            "growth_previous": previous_total if previous else None,
            "growth_basis": "Latest 30 podcast days versus the preceding 30 days.",
        }

    @classmethod
    def _performance_trend(
        cls, rows: list[dict[str, Any]], youtube_rows: list[dict[str, Any]],
        *, expected_youtube_channels: int = 0,
    ) -> list[dict[str, Any]]:
        """Reconcile audio and video into exact, comparable reporting windows."""
        youtube_periods = sorted({
            (row["period_start"], row["period_end"])
            for row in youtube_rows if row["metric_name"] in {"plays", "streams"}
        })
        points = []
        for period_start, period_end in youtube_periods:
            start = datetime.fromisoformat(period_start).date()
            end = datetime.fromisoformat(period_end).date()
            youtube_period_rows = [
                row for row in youtube_rows
                if (row["period_start"], row["period_end"]) == (period_start, period_end)
            ]
            youtube_providers = {
                str(row["provider"]) for row in youtube_period_rows
                if str(row["provider"]).startswith("youtube:")
            }
            youtube_complete = bool(youtube_period_rows) and (
                not expected_youtube_channels
                or len(youtube_providers) >= expected_youtube_channels
            )
            video = sum(
                cls._metric_total(youtube_period_rows, metric)
                for metric in {"plays", "streams"}
            )

            daily_host = [
                row for row in rows
                if row["period_start"] == row["period_end"]
                and start <= datetime.fromisoformat(row["period_end"]).date() <= end
                and row["metric_name"] in {"downloads", "downloads_7d"}
                and row.get("source_class") == "host_rss_delivery"
            ]
            exact_host = [
                row for row in rows
                if (row["period_start"], row["period_end"]) == (period_start, period_end)
                and row["metric_name"] in {"downloads", "downloads_7d"}
                and row.get("source_class") == "host_rss_delivery"
            ]
            window_days = (end - start).days + 1

            def covers_window(daily: list[dict[str, Any]]) -> bool:
                return len({row["period_end"] for row in daily}) >= window_days

            host_rows = cls._prefer_aggregate_rows(
                daily_host if covers_window(daily_host) else exact_host
            )
            downloads = sum(
                cls._metric_total(host_rows, metric) for metric in {"downloads", "downloads_7d"}
            )

            daily_spotify = [
                row for row in rows
                if str(row["provider"]).casefold() == "spotify"
                and row["period_start"] == row["period_end"]
                and start <= datetime.fromisoformat(row["period_end"]).date() <= end
                and row["metric_name"] in {"plays", "streams"}
                and row.get("source_class") == "provider_native"
            ]
            exact_spotify = [
                row for row in rows
                if str(row["provider"]).casefold() == "spotify"
                and (row["period_start"], row["period_end"]) == (period_start, period_end)
                and row["metric_name"] in {"plays", "streams"}
                and row.get("source_class") == "provider_native"
            ]
            spotify_rows = cls._prefer_aggregate_rows(
                daily_spotify if covers_window(daily_spotify) else exact_spotify
            )
            spotify_plays = sum(
                cls._metric_total(spotify_rows, metric) for metric in {"plays", "streams"}
            )
            present = {
                key for key, available in (
                    ("open_rss_downloads", bool(host_rows)),
                    ("spotify_native_plays", bool(spotify_rows)),
                    ("youtube_views", youtube_complete),
                ) if available
            }
            audio = downloads + spotify_plays if host_rows or spotify_rows else None
            total = (audio or 0.0) + video
            points.append({
                "period": period_end,
                "period_start": period_start,
                "period_end": period_end,
                "total": total,
                "audio": audio,
                "video": video,
                "open_rss_downloads": downloads if host_rows else None,
                "spotify_native_plays": spotify_plays if spotify_rows else None,
                "youtube_views": video,
                "coverage": "complete" if len(present) == 3 else "partial",
                "missing_components": sorted(
                    {"open_rss_downloads", "spotify_native_plays", "youtube_views"} - present
                ),
            })
        return points

    @classmethod
    def _apply_comparable_performance(
        cls, rollup: dict[str, Any], trend: list[dict[str, Any]]
    ) -> None:
        comparable = [point for point in trend if point["coverage"] == "complete"]
        if comparable:
            current = comparable[-1]
            rollup.update({
                "measured_activity": current["total"],
                "audio_starts": current["audio"],
                "video_views": current["video"],
                "period_start": current["period_start"],
                "period_end": current["period_end"],
                "coverage": "complete",
                "period_alignment": "aligned",
                "components": [
                    {"key": "open_rss_downloads", "label": "Podcast-app downloads",
                     "value": current["open_rss_downloads"], "period_start": current["period_start"],
                     "period_end": current["period_end"], "source": "Podcast hosting delivery"},
                    {"key": "spotify_native_plays", "label": "Spotify plays",
                     "value": current["spotify_native_plays"], "period_start": current["period_start"],
                     "period_end": current["period_end"], "source": "Spotify for Creators"},
                    {"key": "youtube_views", "label": "YouTube views",
                     "value": current["youtube_views"], "period_start": current["period_start"],
                     "period_end": current["period_end"], "source": "YouTube Analytics"},
                ],
            })
        rollup["comparison"] = cls._performance_comparison(comparable)

    @staticmethod
    def _performance_comparison(points: list[dict[str, Any]]) -> dict[str, Any]:
        if len(points) < 2:
            return {"available": False}
        current = points[-1]
        # Rolling windows overlap; "prior period" must be the latest window that ends before
        # the current one starts, not the same window shifted by one day.
        previous = next((
            point for point in reversed(points[:-1])
            if str(point["period_end"]) < str(current["period_start"])
        ), None)
        if previous is None:
            return {"available": False}

        def compare(key: str) -> dict[str, float | None]:
            current_value = float(current[key] or 0)
            previous_value = float(previous[key] or 0)
            delta = current_value - previous_value
            return {
                "current": current_value,
                "previous": previous_value,
                "delta": delta,
                "delta_pct": round(delta * 100 / previous_value, 1) if previous_value else None,
            }

        return {
            "available": True,
            "current_period_start": current["period_start"],
            "current_period_end": current["period_end"],
            "previous_period_start": previous["period_start"],
            "previous_period_end": previous["period_end"],
            "total": compare("total"),
            "audio": compare("audio"),
            "video": compare("video"),
            "components": {
                key: compare(key) for key in (
                    "open_rss_downloads", "spotify_native_plays", "youtube_views"
                )
            },
        }

    @staticmethod
    def _prefer_aggregate_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not rows:
            return []
        undimensional = [
            row for row in rows
            if not any(row.get(field) for field in (
                "country_code", "city", "device_type", "app_name", "age_group",
                "gender", "traffic_source", "platform_content_id",
            ))
        ]
        return undimensional or rows

    @classmethod
    def _global_rollup(
        cls,
        rows: list[dict[str, Any]],
        spotify_window: dict[str, Any] | None,
        youtube_rows: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Build one non-overlapping cross-channel activity total.

        The hosting export is authoritative for open-RSS delivery, including Apple
        Podcasts and the long tail of RSS clients. Provider-native Apple plays are
        therefore intentionally not added again.
        """
        components: list[dict[str, Any]] = []
        if spotify_window:
            window_start = datetime.fromisoformat(spotify_window["period_start"]).date()
            window_end = datetime.fromisoformat(spotify_window["period_end"]).date()
            spotify_daily = [
                row for row in rows
                if str(row["provider"]).casefold() == "spotify"
                and row["period_start"] == row["period_end"]
                and window_start <= datetime.fromisoformat(row["period_end"]).date() <= window_end
            ]
            if any(row["metric_name"] in {"downloads", "downloads_7d"} for row in spotify_daily):
                components.append({
                    "key": "open_rss_downloads", "label": "Podcast-app downloads",
                    "value": float(spotify_window["downloads"]),
                    "period_start": spotify_window["period_start"],
                    "period_end": spotify_window["period_end"],
                    "source": "Spotify for Creators hosting delivery",
                })
            if any(row["metric_name"] in {"plays", "streams"} for row in spotify_daily):
                components.append({
                    "key": "spotify_native_plays", "label": "Spotify plays",
                    "value": float(spotify_window["plays"]),
                    "period_start": spotify_window["period_start"],
                    "period_end": spotify_window["period_end"],
                    "source": "Spotify for Creators",
                })
            audio_starts = sum(float(item["value"]) for item in components) if components else None
        else:
            host_rows = [
                row for row in rows
                if row["metric_name"] in {"downloads", "downloads_7d"}
                and row.get("source_class") == "host_rss_delivery"
            ]
            host_period = max(
                {(row["period_start"], row["period_end"]) for row in host_rows},
                default=None, key=lambda value: (value[1], value[0]),
            )
            current_host_rows = [
                row for row in host_rows
                if host_period and (row["period_start"], row["period_end"]) == host_period
            ]
            undimensional_host_rows = [
                row for row in current_host_rows
                if not any(row.get(field) for field in (
                    "country_code", "city", "device_type", "app_name", "age_group",
                    "gender", "traffic_source", "platform_content_id",
                ))
            ]
            controlling_host_rows = undimensional_host_rows or current_host_rows
            host_downloads = sum(
                cls._metric_total(controlling_host_rows, metric)
                for metric in {"downloads", "downloads_7d"}
            )
            native_spotify_rows = [
                row for row in rows
                if str(row["provider"]).casefold() == "spotify"
                and row["metric_name"] in {"plays", "streams"}
                and row.get("source_class") == "provider_native"
            ]
            spotify_plays, spotify_period = cls._latest_family_total(
                native_spotify_rows, {"plays", "streams"}
            )
            audio_starts = None
            if host_period:
                components.append({
                    "key": "open_rss_downloads", "label": "Podcast-app downloads",
                    "value": host_downloads, "period_start": host_period[0],
                    "period_end": host_period[1], "source": "Podcast hosting delivery",
                })
            if spotify_period:
                components.append({
                    "key": "spotify_native_plays", "label": "Spotify plays",
                    "value": spotify_plays, "period_start": spotify_period[0],
                    "period_end": spotify_period[1], "source": "Spotify for Creators",
                })
            audio_components = [item for item in components if item["key"] != "youtube_views"]
            if audio_components:
                audio_starts = sum(float(item["value"]) for item in audio_components)

        video_views, video_period = cls._latest_family_total(youtube_rows, {"plays", "streams"})
        if video_period:
            components.append({
                "key": "youtube_views", "label": "YouTube views", "value": video_views,
                "period_start": video_period[0], "period_end": video_period[1],
                "source": "YouTube Analytics",
            })

        total = sum(float(item["value"]) for item in components) if components else None
        starts = [datetime.fromisoformat(item["period_start"]).date() for item in components]
        ends = [datetime.fromisoformat(item["period_end"]).date() for item in components]
        aligned = len(ends) < 2 or (
            (max(starts) - min(starts)).days <= 7 and (max(ends) - min(ends)).days <= 7
        )
        expected = {"open_rss_downloads", "spotify_native_plays", "youtube_views"}
        present = {item["key"] for item in components}

        audience_rows = [
            row for row in rows
            if row["metric_name"] in {"unique_listeners", "unique_viewers"}
            and row.get("episode_id") is None
        ]
        audience_period = max(
            {(row["period_start"], row["period_end"]) for row in audience_rows},
            default=None, key=lambda value: (value[1], value[0]),
        )
        audience_sources: list[dict[str, Any]] = []
        if audience_period:
            current = [
                row for row in audience_rows
                if (row["period_start"], row["period_end"]) == audience_period
            ]
            if any(
                row["metric_name"] == "unique_listeners"
                and row.get("source_class") == "host_cross_platform_aggregate"
                for row in current
            ):
                current = [
                    row for row in current
                    if row["metric_name"] == "unique_viewers"
                    or row.get("source_class") == "host_cross_platform_aggregate"
                ]
            for provider in sorted({str(row["provider"]) for row in current}):
                provider_rows = [row for row in current if str(row["provider"]) == provider]
                preferred_metric = (
                    "unique_viewers"
                    if any(row["metric_name"] == "unique_viewers" for row in provider_rows)
                    else "unique_listeners"
                )
                value = cls._metric_total(provider_rows, preferred_metric)
                audience_sources.append({"provider": provider, "value": value})
        reach_range = None
        if audience_sources:
            values = [float(item["value"]) for item in audience_sources]
            reach_range = {
                "minimum": max(values),
                "maximum": sum(values) if len(values) > 1 else None,
                "period_start": audience_period[0],
                "period_end": audience_period[1],
                "source_count": len(values),
                "explanation": (
                    "The lower bound is the largest provider audience; the upper bound assumes no person used more than one provider."
                    if len(values) > 1 else
                    "Only one distinct-audience source is available, so a cross-platform upper bound cannot be calculated."
                ),
            }

        return {
            "measured_activity": total,
            "audio_starts": audio_starts,
            "video_views": video_views if video_period else None,
            "components": components,
            "coverage": "complete" if expected <= present else "partial" if components else "no_data",
            "period_alignment": "aligned" if aligned else "directional",
            "period_start": min((item["period_start"] for item in components), default=None),
            "period_end": max((item["period_end"] for item in components), default=None),
            "reach_range": reach_range,
            "excluded_from_total": [
                "Apple-native plays and engagement, because Apple downloads are already included in hosting delivery.",
                "Public listing checks, because availability is not consumption.",
            ],
        }

    @classmethod
    def _public_ratings(
        cls, rows: list[dict[str, Any]], countries: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        """Summarize the latest public rating snapshot for each storefront."""
        if not rows:
            return None
        snapshots: dict[str, dict[str, dict[str, Any]]] = {}
        for row in rows:
            code = str(row.get("country_code") or "").casefold()
            if code:
                snapshots.setdefault(code, {}).setdefault(str(row["period_end"]), {})[row["metric_name"]] = row
        storefronts = []
        for code, by_period in snapshots.items():
            complete = {period: values for period, values in by_period.items() if RATING_METRICS <= set(values)}
            if not complete:
                continue
            latest_period = max(complete)
            latest = complete[latest_period]
            baseline_cutoff = (datetime.fromisoformat(latest_period).date() - timedelta(days=30)).isoformat()
            baseline_period = max((period for period in complete if period <= baseline_cutoff), default=None)
            count = float(latest["rating_count"]["metric_value"])
            try:
                name = str(pycountry.countries.get(alpha_2=code.upper()).name)
            except (AttributeError, LookupError):
                name = code.upper()
            storefronts.append({
                "storefront": code, "name": name,
                "average": float(latest["rating_average"]["metric_value"]),
                "count": count,
                "change_30d": (
                    count - float(complete[baseline_period]["rating_count"]["metric_value"])
                    if baseline_period else None
                ),
                "period_end": latest_period,
                "freshness": cls._freshness(latest_period),
                "source": latest["rating_count"]["source_reference"],
            })
        if not storefronts:
            return None
        storefronts.sort(key=lambda item: (-item["count"], item["name"]))
        total = sum(item["count"] for item in storefronts)
        changes = [item["change_30d"] for item in storefronts if item["change_30d"] is not None]
        rated = {item["storefront"] for item in storefronts if item["count"] > 0}
        audience_markets = []
        for item in countries:
            code = _canonical_country_key(item.get("name"))
            if len(code) == 2 and code not in rated and float(item.get("value") or 0) > 0:
                audience_markets.append(str(item.get("name")))
        return {
            "provider": "apple_podcasts",
            "total_ratings": total,
            "weighted_average": (
                round(sum(item["average"] * item["count"] for item in storefronts) / total, 2)
                if total else None
            ),
            "new_ratings_30d": sum(changes) if changes else None,
            "period_end": max(item["period_end"] for item in storefronts),
            "freshness": cls._freshness(max(item["period_end"] for item in storefronts)),
            "storefronts": storefronts,
            "unrated_audience_markets": list(dict.fromkeys(audience_markets))[:8],
            "definition": (
                "Public Apple Podcasts star ratings by storefront. Storefront averages are rounded by "
                "Apple, so the combined average is a rating-count-weighted approximation."
            ),
        }

    @staticmethod
    def _freshness(period_end: str) -> str:
        age = (datetime.now(timezone.utc).date() - datetime.fromisoformat(period_end).date()).days
        return "current" if age <= 14 else "aging" if age <= 45 else "stale"

    @staticmethod
    def _metric_total(rows: list[dict[str, Any]], metric: str) -> float:
        selected = [row for row in rows if row["metric_name"] == metric]
        selected = PodcastInsights._latest_rows_by_natural_grain(selected)
        selected = PodcastInsights._prefer_authoritative_overlap_sources(selected)
        total = 0.0
        for provider in {str(row["provider"]) for row in selected}:
            provider_rows = [row for row in selected if str(row["provider"]) == provider]
            show_rows = [row for row in provider_rows if row.get("episode_id") is None]
            controlling_rows = PodcastInsights._prefer_aggregate_rows(show_rows or provider_rows)
            total += sum(float(row["metric_value"]) for row in controlling_rows)
        return total

    @staticmethod
    def _latest_rows_by_natural_grain(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Collapse repeated full-history imports without trusting changing source metadata.

        Provider exports are immutable snapshots, but collector upgrades can change source
        references, source classes, or overlap groups. Those fields must not make the same
        provider/date/content observation additive.
        """
        dimensions = (
            "episode_id", "provider", "metric_name", "traffic_scope", "period_start", "period_end",
            "country_code", "city", "device_type", "app_name", "age_group", "gender",
            "traffic_source", "platform_content_id",
        )
        latest: dict[tuple[str, ...], dict[str, Any]] = {}
        for row in rows:
            key = tuple(str(row.get(field) or "") for field in dimensions)
            current = latest.get(key)
            if current is None or str(row.get("imported_at") or "") > str(current.get("imported_at") or ""):
                latest[key] = row
        return list(latest.values())

    @classmethod
    def _latest_cumulative_total(cls, rows: list[dict[str, Any]], metric: str) -> float:
        """Sum one latest lifetime snapshot per provider without accumulating sync history."""
        total = 0.0
        candidates = [row for row in rows if row.get("metric_name") == metric]
        for provider in {str(row.get("provider") or "") for row in candidates}:
            provider_rows = [row for row in candidates if str(row.get("provider") or "") == provider]
            latest_period = max(
                ((str(row.get("period_start") or ""), str(row.get("period_end") or "")) for row in provider_rows),
                default=None, key=lambda value: (value[1], value[0]),
            )
            period_rows = [
                row for row in provider_rows
                if latest_period and (str(row.get("period_start") or ""), str(row.get("period_end") or "")) == latest_period
            ]
            latest_import = max((str(row.get("imported_at") or "") for row in period_rows), default="")
            snapshot_rows = [
                row for row in period_rows if str(row.get("imported_at") or "") == latest_import
            ]
            total += cls._metric_total(snapshot_rows, metric)
        return total

    @staticmethod
    def _play_weighted_depth(
        depth_rows: list[dict[str, Any]], rows: list[dict[str, Any]],
    ) -> float | None:
        """Average per-episode consumption, weighting each episode by its plays."""
        def identity(row: dict[str, Any]) -> tuple[str, str, str, str]:
            return (
                str(row.get("episode_id") or ""), str(row.get("platform_content_id") or ""),
                str(row.get("period_start") or ""), str(row.get("period_end") or ""),
            )

        plays = {identity(row): float(row["metric_value"]) for row in rows if row["metric_name"] == "plays"}
        weighted = total = 0.0
        for row in depth_rows:
            weight = plays.get(identity(row), 0.0)
            weighted += float(row["metric_value"]) * weight
            total += weight
        if total:
            return weighted / total
        return None

    @staticmethod
    def _prefer_primary_evidence(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Use aggregator copies only for provider measures that no primary source reports.

        Aggregators such as OpenPodcast re-publish provider data with a different grain or
        shape (daily show plays, country listener counts). Mixing those with the provider's
        own export would replace lifetime totals with single days or blend counts with shares.
        """
        def family(row: dict[str, Any]) -> tuple[str, str]:
            metric = str(row["metric_name"])
            dimension = metric.split("_", 1)[0]
            return (
                str(row["provider"]).casefold(),
                dimension if dimension in {"country", "city", "device"} else metric,
            )

        primary = {family(row) for row in rows if row.get("source_class") != "aggregator_copy"}
        return [
            row for row in rows
            if row.get("source_class") != "aggregator_copy" or family(row) not in primary
        ]

    @staticmethod
    def _prefer_authoritative_overlap_sources(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Keep one authoritative source family for explicitly overlapping evidence.

        Overlap is resolved per reporting period: daily rows for different dates often
        arrive in different collector uploads and are complementary, not duplicates.
        """
        ungrouped = [row for row in rows if not str(row.get("overlap_group") or "")]
        grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
        for row in rows:
            overlap_group = str(row.get("overlap_group") or "")
            if overlap_group:
                key = (
                    overlap_group,
                    str(row.get("period_start") or ""),
                    str(row.get("period_end") or ""),
                )
                grouped.setdefault(key, []).append(row)
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
        daily = cls._spotify_daily(rows)
        if not daily:
            return None
        return {
            "period_start": min(row["period"] for row in daily),
            "period_end": max(row["period"] for row in daily),
            "downloads": sum(float(row.get("downloads") or 0) for row in daily),
            "plays": sum(float(row.get("plays") or 0) for row in daily),
        }

    @classmethod
    def _spotify_daily(cls, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        days: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            if (
                row["period_start"] == row["period_end"]
                and row["metric_name"] in {"downloads", "plays", "streams", "unique_listeners"}
            ):
                days.setdefault(row["period_end"], []).append(row)
        return [{
            "period": period,
            "downloads": cls._metric_total(day_rows, "downloads"),
            "plays": cls._metric_total(day_rows, "plays") + cls._metric_total(day_rows, "streams"),
            "audience": cls._metric_total(day_rows, "unique_listeners"),
        } for period, day_rows in sorted(days.items())]

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

    @classmethod
    def _provider_monthly_trends(
        cls, rows: list[dict[str, Any]]
    ) -> dict[str, list[dict[str, Any]]]:
        """Return history for every provider that supplies comparable activity evidence."""
        result: dict[str, list[dict[str, Any]]] = {}
        for provider in sorted({str(row["provider"]) for row in rows}):
            provider_rows = [row for row in rows if str(row["provider"]) == provider]
            months: dict[str, list[dict[str, Any]]] = {}
            for row in provider_rows:
                if row["metric_name"] in {
                    "downloads", "downloads_7d", "plays", "streams", "watch_time_hours",
                    "unique_listeners", "listeners", "unique_viewers",
                }:
                    months.setdefault(str(row["period_end"])[:7], []).append(row)
            points = []
            for month, month_rows in sorted(months.items()):
                daily = [row for row in month_rows if row["period_start"] == row["period_end"]]
                activity_rows = daily or month_rows
                activity = sum(
                    cls._metric_total(activity_rows, metric)
                    for metric in {"downloads", "downloads_7d", "plays", "streams"}
                )
                listeners = sum(
                    cls._metric_total(month_rows, metric)
                    for metric in {"unique_listeners", "listeners", "unique_viewers"}
                )
                if activity or listeners:
                    points.append({"period": month, "activity": activity, "listeners": listeners})
            if points:
                result[provider] = points
        return result

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
            selected_rows = show_rows or relevant
            latest_by_identity: dict[str, dict[str, Any]] = {}
            for row in selected_rows:
                identity = str(row.get("episode_id") or "show")
                current = latest_by_identity.get(identity)
                if current is None or str(row.get("imported_at") or "") > str(current.get("imported_at") or ""):
                    latest_by_identity[identity] = row
            percentage_prefix = f"{prefix}audience_share_pct_"
            is_percentage = metric.startswith(percentage_prefix)
            name = metric[len(percentage_prefix):] if is_percentage else metric[len(prefix):]
            values.append({"name": name.replace("_", " ").title(),
                           "value": sum(float(row["metric_value"]) for row in latest_by_identity.values()),
                           "provider": provider, "period_end": latest,
                           "is_percentage": is_percentage,
                           "measure": "audience share" if is_percentage else "audience"})
        provider_totals = {
            provider: sum(item["value"] for item in values if item["provider"] == provider)
            for provider in {item["provider"] for item in values}
        }
        for item in values:
            total = provider_totals[item["provider"]]
            item["share_pct"] = (
                round(item["value"], 1) if item["is_percentage"]
                else round(item["value"] * 100 / total, 1) if total else None
            )
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
        candidate_groups = {
            (str(row["provider"]), tuple(field for field in label_fields if str(row.get(field) or "").strip()))
            for row in candidates
        }
        for provider, dimension_fields in sorted(candidate_groups):
            provider_rows = [
                row for row in candidates
                if str(row["provider"]) == provider
                and tuple(field for field in label_fields if str(row.get(field) or "").strip()) == dimension_fields
            ]
            latest = max((row["period_end"] for row in provider_rows), default=None)
            latest_rows = [row for row in provider_rows if row["period_end"] == latest]
            labelled_rows = [
                row for row in latest_rows
                if any(str(row.get(field) or "").strip() for field in label_fields)
            ]
            if labelled_rows:
                latest_rows = labelled_rows
            latest_by_label: dict[tuple[str, ...], dict[str, Any]] = {}
            for row in latest_rows:
                label_key = tuple(str(row.get(field) or "unknown").strip().casefold() for field in dimension_fields)
                current = latest_by_label.get(label_key)
                if current is None or str(row.get("imported_at") or "") > str(current.get("imported_at") or ""):
                    latest_by_label[label_key] = row
            latest_rows = list(latest_by_label.values())
            total = sum(float(row["metric_value"]) for row in latest_rows)
            for row in latest_rows:
                value = float(row["metric_value"])
                labels = []
                for field in dimension_fields:
                    raw_label = str(row.get(field) or "unknown")
                    age_match = re.fullmatch(r"(?:age)?(\d+)[_-](\d+|plus)", raw_label, re.I) if field == "age_group" else None
                    labels.append(
                        f"{age_match.group(1)}–{age_match.group(2)}" if age_match
                        else raw_label if field == "app_name"
                        else raw_label.replace("_", " ").title()
                    )
                values.append({
                    "name": " · ".join(labels) or "Unknown", "value": value, "provider": provider,
                    "period_end": latest,
                    "share_pct": round(value, 1) if percentage_values else round(value * 100 / total, 1) if total else None,
                    "measure": "audience share" if percentage_values else "views",
                    "dimension_group": " & ".join(
                        field.replace("_", " ").title() for field in dimension_fields
                    ),
                    "is_percentage": percentage_values,
                })
        return sorted(values, key=lambda item: (item["provider"], -item["value"]))

    @staticmethod
    def _top_platform_content(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        candidates = [
            row for row in rows
            if (
                row["metric_name"].startswith("video_")
                or row["metric_name"].startswith("web_player_")
                or row["metric_name"] == "plays_downloads"
            )
            and str(row.get("platform_content_id") or "")
            and row.get("episode_id") is None
        ]
        grouped: dict[tuple[str, str, str, str], list[dict[str, Any]]] = {}
        for row in candidates:
            provider = str(row["provider"])
            content_id = str(row["platform_content_id"])
            # Spotify's export has no episode ID; its title surrogate needs the publish date.
            publish_date = (
                str(row.get("period_start") or "")
                if provider == "spotify" and content_id.startswith("title:")
                else ""
            )
            grouped.setdefault(
                (provider, content_id, publish_date, str(row["period_end"])), []
            ).append(row)
        latest_by_content: dict[tuple[str, str, str], tuple[str, list[dict[str, Any]]]] = {}
        for (provider, content_id, publish_date, period_end), content_rows in grouped.items():
            key = (provider, content_id, publish_date)
            if key not in latest_by_content or period_end > latest_by_content[key][0]:
                latest_by_content[key] = (period_end, content_rows)
        result = []
        for (provider, content_id, publish_date), (period_end, content_rows) in latest_by_content.items():
            metrics = {row["metric_name"]: float(row["metric_value"]) for row in content_rows}
            result.append({
                "provider": provider, "platform_content_id": content_id,
                "title": next((str(row.get("platform_content_title") or "") for row in content_rows if row.get("platform_content_title")), content_id),
                "period_start": publish_date or min(
                    (str(row.get("period_start") or "") for row in content_rows), default=""
                ),
                "period_end": period_end, "freshness": PodcastInsights._freshness(period_end),
                "metrics": metrics,
            })
        def activity(item: dict[str, Any]) -> float:
            metrics = item["metrics"]
            return next((
                float(metrics[metric]) for metric in (
                    "plays_downloads", "video_lifetime_views", "video_views",
                    "web_player_play_starts", "web_player_completions",
                ) if metrics.get(metric) is not None
            ), 0.0)

        return sorted(
            result,
            key=lambda item: (
                -activity(item), item["title"].casefold(), item["provider"],
                item["platform_content_id"], item["period_start"],
            ),
        )[:20]
