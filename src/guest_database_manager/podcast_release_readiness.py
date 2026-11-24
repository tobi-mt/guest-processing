"""Deterministic release gate for the Podcast Reach subsystem."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from guest_database_manager.db_connection import connect_database
from guest_database_manager.podcast_analytics_connectors import (
    LOCAL_COLLECTOR_PROVIDERS,
    PodcastAnalyticsConnectors,
    _parse_datetime,
)
from guest_database_manager.podcast_source_monitor import PUBLIC_SOURCES


REQUIRED_SCHEMA_VERSION = 45
PUBLIC_SOURCE_MAX_AGE = timedelta(hours=48)
GOOGLE_SYNC_MAX_AGE = timedelta(hours=48)
ANALYTICS_PERIOD_MAX_AGE = {
    "youtube": timedelta(days=45),
    "spotify": timedelta(days=45),
    "apple_podcasts": timedelta(days=75),
    "open_rss_downloads": timedelta(days=45),
}


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _period_age(period_end: Any, now: datetime) -> timedelta | None:
    text = str(period_end or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return now - parsed.astimezone(timezone.utc)


class PodcastReachReleaseReadiness:
    """Report every condition required before Podcast Reach is called released."""

    def __init__(self, db_path: str | Path):
        self.db_path = str(db_path)
        self.connectors = PodcastAnalyticsConnectors(db_path)

    def report(self, *, now: datetime | None = None) -> dict[str, Any]:
        now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        blockers: list[dict[str, str]] = []
        warnings: list[dict[str, str]] = []
        checks: dict[str, dict[str, Any]] = {}

        def block(code: str, message: str) -> None:
            blockers.append({"code": code, "message": message})

        with connect_database(self.db_path) as conn:
            conn.row_factory = __import__("sqlite3").Row
            schema_version = int(conn.execute("SELECT COALESCE(MAX(version), 0) FROM schema_migrations").fetchone()[0])
            if schema_version < REQUIRED_SCHEMA_VERSION:
                block("schema_outdated", f"Database migration {REQUIRED_SCHEMA_VERSION} has not been applied.")
                return {
                    "status": "not_ready",
                    "generated_at": _iso(now),
                    "blocker_count": 1,
                    "warning_count": 0,
                    "blockers": blockers,
                    "warnings": warnings,
                    "checks": {"schema": {
                        "status": "fail",
                        "current_version": schema_version,
                        "required_version": REQUIRED_SCHEMA_VERSION,
                    }},
                }
            platforms = [dict(row) for row in conn.execute(
                """SELECT platform_key, display_name, status, distribution_mode, last_verified_at,
                          last_error_code FROM podcast_platform_registry ORDER BY platform_key"""
            ).fetchall()]
            source_checks = [dict(row) for row in conn.execute(
                """SELECT check_row.* FROM podcast_source_checks check_row
                   JOIN (SELECT source_key, MAX(id) AS id FROM podcast_source_checks GROUP BY source_key) latest
                     ON latest.id = check_row.id"""
            ).fetchall()]
            evidence_rows = [dict(row) for row in conn.execute(
                """SELECT provider, metric_name, source_class, period_end, imported_at
                   FROM current_growth_metric_observations
                   WHERE metric_name IN ('downloads', 'plays')"""
            ).fetchall()]

        schema_ok = schema_version >= REQUIRED_SCHEMA_VERSION
        checks["schema"] = {
            "status": "pass" if schema_ok else "fail",
            "current_version": schema_version,
            "required_version": REQUIRED_SCHEMA_VERSION,
        }

        expected = [row for row in platforms if row["distribution_mode"] != "expected_missing"]
        available = [row for row in expected if row["status"] == "available"]
        unresolved = [row["platform_key"] for row in expected if row["status"] != "available"]
        known_missing = [row["platform_key"] for row in platforms if row["distribution_mode"] == "expected_missing"]
        distribution_ok = bool(expected) and not unresolved
        checks["distribution"] = {
            "status": "pass" if distribution_ok else "fail",
            "available": len(available),
            "expected": len(expected),
            "coverage_pct": round(len(available) * 100 / len(expected), 1) if expected else 0.0,
            "unresolved": unresolved,
            "known_missing": known_missing,
        }
        if not distribution_ok:
            block("distribution_incomplete", "All expected distribution targets must be verified or catalog-confirmed.")
        if known_missing:
            warnings.append({
                "code": "known_missing_destinations",
                "message": f"Known unlisted destinations remain visible: {', '.join(known_missing)}.",
            })

        latest_checks = {str(row["source_key"]): row for row in source_checks}
        stale_or_missing = []
        for source_key, _name, _url in PUBLIC_SOURCES:
            row = latest_checks.get(source_key)
            checked_at = _parse_datetime(row.get("checked_at")) if row else None
            if not row or row.get("status") != "available" or not checked_at or now - checked_at > PUBLIC_SOURCE_MAX_AGE:
                stale_or_missing.append(source_key)
        public_ok = not stale_or_missing
        checks["public_sources"] = {
            "status": "pass" if public_ok else "fail",
            "fresh_available": len(PUBLIC_SOURCES) - len(stale_or_missing),
            "expected": len(PUBLIC_SOURCES),
            "max_age_hours": int(PUBLIC_SOURCE_MAX_AGE.total_seconds() // 3600),
            "stale_or_missing": stale_or_missing,
        }
        if not public_ok:
            block("public_sources_incomplete", "Run a successful public-source verification within 48 hours of release.")

        connector_status = self.connectors.status()
        google = connector_status["google"]
        google_connections = google["connections"]
        fresh_google = []
        for connection in google_connections:
            last_success = _parse_datetime(connection.get("last_success_at"))
            if (
                connection.get("status") == "connected"
                and last_success
                and now - last_success <= GOOGLE_SYNC_MAX_AGE
                and connection.get("youtube_channel_id")
            ):
                fresh_google.append(connection)
        google_ok = bool(google["oauth_configured"] and fresh_google)
        checks["youtube_analytics"] = {
            "status": "pass" if google_ok else "fail",
            "oauth_configured": bool(google["oauth_configured"]),
            "fresh_connected_channels": len(fresh_google),
            "configured_connections": len(google_connections),
            "max_sync_age_hours": int(GOOGLE_SYNC_MAX_AGE.total_seconds() // 3600),
        }
        if not google_ok:
            block("youtube_analytics_not_ready", "Configure Google OAuth and complete a successful YouTube sync within 48 hours.")

        collectors = connector_status["local_collectors"]
        collector_connections = collectors["connections"]
        collector_failures = []
        for provider in sorted(LOCAL_COLLECTOR_PROVIDERS):
            item = collector_connections.get(provider) or {}
            if not item.get("enabled") or item.get("status") != "connected" or not item.get("last_success_at"):
                collector_failures.append(provider)
        collectors_ok = bool(collectors["configured"] and not collector_failures)
        checks["provider_collectors"] = {
            "status": "pass" if collectors_ok else "fail",
            "credential_configured": bool(collectors["configured"]),
            "required": sorted(LOCAL_COLLECTOR_PROVIDERS),
            "not_connected": collector_failures,
        }
        if not collectors_ok:
            block("provider_collectors_not_ready", "Enable and successfully synchronize the Spotify and Apple local collectors.")

        evidence_specs = {
            "youtube": lambda row: str(row["provider"]).startswith("youtube") and row["metric_name"] == "plays",
            "spotify": lambda row: row["provider"] == "spotify" and row["metric_name"] == "plays",
            "apple_podcasts": lambda row: row["provider"] == "apple_podcasts" and row["metric_name"] == "plays",
            "open_rss_downloads": lambda row: row["metric_name"] == "downloads" and row["source_class"] == "host_rss_delivery",
        }
        evidence_detail = {}
        stale_evidence = []
        for key, predicate in evidence_specs.items():
            matches = [row for row in evidence_rows if predicate(row)]
            latest = max((str(row["period_end"]) for row in matches), default=None)
            age = _period_age(latest, now)
            fresh = bool(age is not None and age <= ANALYTICS_PERIOD_MAX_AGE[key])
            evidence_detail[key] = {
                "latest_period_end": latest,
                "max_age_days": ANALYTICS_PERIOD_MAX_AGE[key].days,
                "status": "pass" if fresh else "fail",
            }
            if not fresh:
                stale_evidence.append(key)
        evidence_ok = not stale_evidence
        checks["analytics_evidence"] = {
            "status": "pass" if evidence_ok else "fail",
            "sources": evidence_detail,
            "stale_or_missing": stale_evidence,
        }
        if not evidence_ok:
            block("analytics_evidence_incomplete", "Backfill fresh YouTube, Spotify, Apple, and open-RSS delivery evidence before release.")

        if not google["ga4_configured"]:
            warnings.append({"code": "ga4_not_configured", "message": "GA4 is optional for podcast reach but website conversion analytics will be absent."})
        openpodcast = connector_status["openpodcast"]
        if not openpodcast["configured"]:
            warnings.append({"code": "aggregator_not_configured", "message": "The optional OpenPodcast secondary evidence source is not configured."})

        return {
            "status": "ready" if not blockers else "not_ready",
            "generated_at": _iso(now),
            "blocker_count": len(blockers),
            "warning_count": len(warnings),
            "blockers": blockers,
            "warnings": warnings,
            "checks": checks,
        }
