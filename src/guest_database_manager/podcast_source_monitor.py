"""Daily, auditable monitoring of public and private podcast evidence sources."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from time import perf_counter
from typing import Any
from urllib.request import Request, urlopen

from guest_database_manager.db_connection import connect_database

PUBLIC_SOURCES = (
    ("rss", "Canonical RSS", "https://anchor.fm/s/261b1464/podcast/rss"),
    ("apple_public", "Apple Podcasts", "https://itunes.apple.com/lookup?id=1518394292&entity=podcast"),
    ("spotify_public", "Spotify", "https://open.spotify.com/show/0trwqguYCic32smqh3Ny60"),
    ("youtube_public", "YouTube", "https://www.youtube.com/@mirrortalkpodcast"),
    ("amazon_public", "Amazon Music", "https://music.amazon.com/podcasts/8996f709-4711-4d9f-8563-93b770bf42ae/mirror-talk-soulful-conversations"),
    ("iheart_public", "iHeartRadio", "https://www.iheart.com/podcast/269-mirror-talk-soulful-conver-69159083/"),
)

PRIVATE_SOURCES = (
    {"key": "spotify_creators", "name": "Spotify for Creators", "metrics": ["listeners", "followers", "streams", "devices", "geography"], "access": "Provider export required; no supported private analytics API.", "connection_mode": "provider_limited"},
    {"key": "apple_connect", "name": "Apple Podcasts Connect", "metrics": ["listeners", "engaged listeners", "plays", "consumption", "devices", "geography"], "access": "Provider export required; Apple does not offer third-party analytics access.", "connection_mode": "provider_limited"},
    {"key": "youtube_analytics", "name": "YouTube Analytics", "metrics": ["plays", "watch time", "subscribers", "devices", "geography", "retention"], "access": "Automated read-only Google OAuth sync.", "connection_mode": "automated"},
    {"key": "podcast_host", "name": "Podcast hosting analytics", "metrics": ["IAB downloads", "unique listeners", "apps", "devices", "geography"], "access": "Use the Spotify for Creators export when it contains hosting-wide downloads; otherwise use the verified host export.", "connection_mode": "provider_limited"},
    {"key": "website_analytics", "name": "Mirror Talk website analytics", "metrics": ["active users", "countries", "devices", "referrals", "conversions"], "access": "Automated read-only GA4 API sync.", "connection_mode": "automated"},
)


class PodcastSourceMonitor:
    def __init__(self, db_path: str | Path):
        self.db_path = str(db_path)

    def run(self, *, actor: str, force: bool = False) -> dict[str, Any]:
        if not force:
            with connect_database(self.db_path) as conn:
                latest = conn.execute(
                    "SELECT MAX(checked_at) FROM podcast_source_checks WHERE status = 'available'"
                ).fetchone()[0]
            if latest:
                parsed = datetime.fromisoformat(str(latest).replace("Z", "+00:00"))
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=timezone.utc)
                if datetime.now(timezone.utc) - parsed < timedelta(hours=24):
                    return {"status": "fresh", "checked": 0, "sources": self.status()}

        results = []
        for key, name, url in PUBLIC_SOURCES:
            started = perf_counter()
            status = "available"
            evidence: dict[str, Any] = {}
            error_code = ""
            try:
                request = Request(url, headers={"User-Agent": "MirrorTalkSourceMonitor/1.0"})
                with urlopen(request, timeout=15) as response:  # noqa: S310 - fixed allow-listed URLs
                    payload = response.read(512_000)
                    evidence = {"http_status": int(response.status), "content_type": str(response.headers.get("Content-Type") or "")}
                    if key == "apple_public":
                        parsed = json.loads(payload)
                        record = (parsed.get("results") or [{}])[0]
                        evidence.update({"result_count": parsed.get("resultCount", 0), "episode_count": record.get("trackCount"),
                                         "latest_release": record.get("releaseDate"), "feed_url": record.get("feedUrl")})
            except Exception as exc:
                status, error_code = "unavailable", type(exc).__name__
            checked_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            with connect_database(self.db_path) as conn:
                conn.execute(
                    """INSERT INTO podcast_source_checks
                       (source_key, source_name, source_url, status, evidence_json, latency_ms,
                        error_code, actor, checked_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (key, name, url, status, json.dumps(evidence, sort_keys=True),
                     round((perf_counter() - started) * 1000), error_code, actor, checked_at),
                )
                conn.commit()
            results.append({"source_key": key, "status": status})
        return {"status": "completed", "checked": len(results), "results": results, "sources": self.status()}

    def status(self) -> dict[str, Any]:
        with connect_database(self.db_path) as conn:
            conn.row_factory = __import__("sqlite3").Row
            public = [dict(row) for row in conn.execute(
                """SELECT c.* FROM podcast_source_checks c
                   JOIN (SELECT source_key, MAX(id) id FROM podcast_source_checks GROUP BY source_key) latest
                     ON latest.id = c.id ORDER BY c.source_name"""
            ).fetchall()]
            observations = [dict(row) for row in conn.execute(
                """SELECT provider, metric_name, period_end FROM growth_metric_observations
                   ORDER BY period_end, id"""
            ).fetchall()]
        for row in public:
            try:
                row["evidence"] = json.loads(row.pop("evidence_json") or "{}")
            except json.JSONDecodeError:
                row["evidence"] = {}
        private = []
        for source in PRIVATE_SOURCES:
            tokens = self._provider_tokens(source["key"])
            source_rows = [row for row in observations if str(row["provider"]).casefold() in tokens]
            private.append({
                **source,
                "status": "data_present" if source_rows else "provider_access_required",
                "observation_count": len(source_rows),
                "metrics_present": sorted({str(row["metric_name"]) for row in source_rows}),
                "latest_period_end": max((str(row["period_end"]) for row in source_rows), default=None),
            })
        automated = [row for row in private if row["connection_mode"] == "automated"]
        limited = [row for row in private if row["connection_mode"] == "provider_limited"]
        return {"public": public, "private": private, "public_available": sum(row["status"] == "available" for row in public),
                "public_expected": len(PUBLIC_SOURCES), "private_connected": sum(row["status"] == "data_present" for row in private),
                "private_expected": len(PRIVATE_SOURCES),
                "automated_connected": sum(row["status"] == "data_present" for row in automated),
                "automated_expected": len(automated), "provider_limited_count": len(limited)}

    @staticmethod
    def _provider_tokens(key: str) -> set[str]:
        return {
            "spotify_creators": {"spotify"}, "apple_connect": {"apple", "apple_podcasts"},
            "youtube_analytics": {"youtube"}, "podcast_host": {"podcast_host", "spotify_for_creators", "anchor"},
            "website_analytics": {"website", "google_analytics", "ga4"},
        }.get(key, {key})
