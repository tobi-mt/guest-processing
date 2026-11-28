"""Automatic, read-only collection of public Apple Podcasts storefront ratings."""

from __future__ import annotations

import html
import json
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

import pycountry

from guest_database_manager.db_connection import connect_database
from guest_database_manager.growth_intelligence import GrowthIntelligence

APPLE_PODCAST_ID = "1518394292"
PROVIDER = "apple_podcasts_public"
RATING_METRICS = ("rating_average", "rating_count")
# Core listening markets are always checked; markets with measured audience or prior
# ratings are added automatically so new regions are tracked without configuration.
DEFAULT_STOREFRONTS = ("us", "gb", "ca", "au", "ng", "de", "ie", "za", "gh", "ke", "in", "nz")
REFRESH_AFTER = timedelta(hours=20)
FAILURE_BACKOFF = timedelta(hours=6)
# Bounds the shared background worker. Storefronts not reached are recorded as pending,
# checked first on the next run, and make that run due after FAILURE_BACKOFF.
RUN_BUDGET_SECONDS = 120.0
USER_AGENT = "MirrorTalkPodcastReach/1.0 (+https://mirrortalkpodcast.com)"
_JSON_LD = re.compile(
    r"<script[^>]*type=[\"']application/ld\+json[\"'][^>]*>(.*?)</script>", re.S | re.I,
)

Fetcher = Callable[[str], tuple[int, str, str]]


class PublicRatingsError(RuntimeError):
    """Raised when public rating evidence cannot be collected safely."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_time(value: Any) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value or "").replace("Z", "+00:00").replace(" ", "T"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _storefront_code(value: Any) -> str:
    text = re.sub(r"[_\s]+", " ", str(value or "")).strip()
    if not text or text.casefold() == "unknown":
        return ""
    try:
        country = pycountry.countries.lookup(text.upper() if len(text) in {2, 3} else text)
    except LookupError:
        return ""
    return str(country.alpha_2).casefold()


def _json_ld_items(payload: Any) -> Iterable[dict[str, Any]]:
    if isinstance(payload, list):
        for item in payload:
            yield from _json_ld_items(item)
    elif isinstance(payload, dict):
        yield payload
        yield from _json_ld_items(payload.get("@graph") or [])


def parse_apple_rating(page: str, *, storefront: str, podcast_id: str = APPLE_PODCAST_ID) -> dict[str, Any] | None:
    """Return the show's storefront rating, or None when that storefront has no ratings.

    Apple redirects unknown storefronts to another one, so the structured URL must name
    the requested storefront and show before a value is accepted.
    """
    for match in _JSON_LD.finditer(page):
        try:
            payload = json.loads(html.unescape(match.group(1)))
        except json.JSONDecodeError:
            continue
        for item in _json_ld_items(payload):
            rating = item.get("aggregateRating")
            if not isinstance(rating, dict):
                continue
            reviewed = rating.get("itemReviewed") if isinstance(rating.get("itemReviewed"), dict) else {}
            url = str(item.get("url") or reviewed.get("url") or "")
            path = urlsplit(url).path
            if not path.startswith(f"/{storefront}/") or not path.endswith(f"/id{podcast_id}"):
                continue
            try:
                average = float(rating.get("ratingValue"))
                count = int(rating.get("ratingCount", rating.get("reviewCount")))
            except (TypeError, ValueError) as exc:
                raise PublicRatingsError("Apple changed its public rating format.") from exc
            if not 0 <= average <= 5 or count < 0:
                raise PublicRatingsError("Apple returned an out-of-range public rating.")
            return {"rating_average": average, "rating_count": count, "url": url}
    return None


def _default_fetch(url: str) -> tuple[int, str, str]:
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html"})
    try:
        with urlopen(request, timeout=15) as response:  # noqa: S310 - fixed Apple Podcasts host
            body = response.read(2_000_000).decode("utf-8", errors="replace")
            return int(response.status), str(response.geturl()), body
    except HTTPError as exc:
        return int(exc.code), url, ""


class PublicRatingsCollector:
    """Collect public storefront ratings as immutable, revision-aware observations."""

    def __init__(self, db_path: str | Path, *, fetch: Fetcher | None = None, podcast_id: str = APPLE_PODCAST_ID):
        self.db_path = str(db_path)
        self.fetch = fetch or _default_fetch
        self.podcast_id = podcast_id
        self.growth = GrowthIntelligence(db_path)

    def storefronts(self) -> list[str]:
        with connect_database(self.db_path) as conn:
            rated = [str(row[0]) for row in conn.execute(
                """SELECT DISTINCT country_code FROM current_growth_metric_observations
                   WHERE provider=? AND metric_name='rating_count' AND metric_value > 0""",
                (PROVIDER,),
            ).fetchall()]
            audience = conn.execute(
                """SELECT country_code, metric_name, SUM(metric_value) AS weight
                   FROM current_growth_metric_observations
                   WHERE provider != ? AND metric_value > 0
                     AND (country_code != '' OR metric_name LIKE 'country\\_%' ESCAPE '\\')
                   GROUP BY country_code, metric_name ORDER BY weight DESC""",
                (PROVIDER,),
            ).fetchall()
        ordered: list[str] = [_storefront_code(code) for code in self._pending_storefronts()]
        ordered.extend(_storefront_code(code) for code in rated)
        ordered.extend(DEFAULT_STOREFRONTS)
        for country_code, metric_name, _weight in audience:
            code = _storefront_code(country_code)
            if not code:
                # Country metrics end in a slugged country name, e.g. ..._united_kingdom.
                words = str(metric_name).split("_")
                code = next((
                    candidate for size in range(min(5, len(words) - 1), 0, -1)
                    if (candidate := _storefront_code(" ".join(words[-size:])))
                ), "")
            ordered.append(code)
        return list(dict.fromkeys(code for code in ordered if code))

    def _last_run_details(self) -> tuple[str, str, dict[str, Any]] | None:
        with connect_database(self.db_path) as conn:
            event = conn.execute(
                """SELECT event_type, after_json, created_at FROM audit_events
                   WHERE entity_type='analytics_connector' AND entity_id=?
                     AND event_type IN ('analytics_sync_completed', 'analytics_sync_failed')
                   ORDER BY id DESC LIMIT 1""",
                (PROVIDER,),
            ).fetchone()
        if not event:
            return None
        try:
            details = json.loads(event[1] or "{}")
        except json.JSONDecodeError:
            details = {}
        return str(event[0]), str(event[2]), details if isinstance(details, dict) else {}

    def _pending_storefronts(self) -> list[str]:
        last = self._last_run_details()
        pending = last[2].get("storefronts_pending") if last else None
        return [str(code) for code in pending] if isinstance(pending, list) else []

    def status(self) -> dict[str, Any]:
        with connect_database(self.db_path) as conn:
            latest = conn.execute(
                "SELECT MAX(imported_at) FROM current_growth_metric_observations WHERE provider=?",
                (PROVIDER,),
            ).fetchone()[0]
        event = self._last_run_details()
        failed = bool(event) and event[0] == "analytics_sync_failed"
        details = event[2] if event else {}
        pending = details.get("storefronts_pending")
        return {
            "last_success_at": latest,
            "last_run_at": event[1] if event else None,
            "status": "error" if failed else ("connected" if latest else "waiting"),
            "last_error_code": details.get("error_code", "") if failed else "",
            "storefronts_checked": details.get("storefronts_checked"),
            "storefronts_rated": details.get("storefronts_rated"),
            "storefronts_pending": len(pending) if isinstance(pending, list) else 0,
        }

    def due(self, *, now: datetime | None = None) -> bool:
        current = now or _now()
        status = self.status()
        last_run = _parse_time(status.get("last_run_at"))
        if (status["status"] == "error" or status["storefronts_pending"]) and last_run:
            return current - last_run >= FAILURE_BACKOFF
        last_success = _parse_time(status.get("last_success_at"))
        reference = max((value for value in (last_run, last_success) if value), default=None)
        return reference is None or current - reference >= REFRESH_AFTER

    def run(self, *, actor: str, force: bool = False) -> dict[str, Any]:
        if not force and not self.due():
            return {**self.status(), "status": "fresh"}
        today = _now().date().isoformat()
        observations: list[dict[str, Any]] = []
        checked = 0
        unavailable = 0
        pending: list[str] = []
        error_code = ""
        storefronts = self.storefronts()
        deadline = time.monotonic() + RUN_BUDGET_SECONDS
        for storefront in storefronts:
            if time.monotonic() >= deadline:
                unavailable += 1
                pending.append(storefront)
                continue
            url = f"https://podcasts.apple.com/{storefront}/podcast/id{self.podcast_id}"
            try:
                status_code, _final_url, page = self.fetch(url)
            except (URLError, TimeoutError, OSError):
                unavailable += 1
                pending.append(storefront)
                continue
            if status_code == 404:
                continue
            if status_code != 200:
                unavailable += 1
                pending.append(storefront)
                continue
            checked += 1
            try:
                rating = parse_apple_rating(page, storefront=storefront, podcast_id=self.podcast_id)
            except PublicRatingsError:
                error_code = "format_changed"
                continue
            if storefront == "us" and rating is None:
                # The primary storefront has had ratings since launch; a missing block
                # there is treated as a format change rather than "no ratings".
                error_code = error_code or "format_changed"
            if rating is None:
                continue
            for metric in RATING_METRICS:
                observations.append({
                    "provider": PROVIDER,
                    "metric_name": metric,
                    "metric_value": rating[metric],
                    "period_start": today,
                    "period_end": today,
                    "country_code": storefront.upper(),
                    "source_reference": f"https://podcasts.apple.com/{storefront}/podcast/id{self.podcast_id}",
                    "source_class": "public_listing",
                    "overlap_group": "apple_public_rating",
                })
        if not checked and not error_code:
            error_code = "unreachable"
        result: dict[str, Any] = {"submitted": 0, "inserted": 0, "duplicates": 0}
        if observations:
            result = self.growth.record_observations(
                observations, actor=actor, correlation_id=f"apple-public-ratings-{today}",
            )
        rated = len(observations) // len(RATING_METRICS)
        failed = bool(error_code) and not observations
        with connect_database(self.db_path) as conn:
            conn.execute(
                """INSERT INTO audit_events
                   (entity_type, entity_id, event_type, actor, source, reason, correlation_id, after_json)
                   VALUES ('analytics_connector', ?, ?, ?, 'public_ratings', ?, ?, ?)""",
                (
                    PROVIDER,
                    "analytics_sync_failed" if failed else "analytics_sync_completed",
                    actor,
                    "Public Apple Podcasts ratings collection",
                    f"apple-public-ratings-{today}",
                    json.dumps({
                        "error_code": error_code,
                        "storefronts_checked": checked,
                        "storefronts_rated": rated,
                        "storefronts_unavailable": unavailable,
                        "storefronts_pending": pending,
                        **result,
                    }, sort_keys=True),
                ),
            )
            conn.commit()
        return {
            "status": "error" if failed else "partial" if error_code or unavailable else "completed",
            "error_code": error_code,
            "storefronts_checked": checked,
            "storefronts_rated": rated,
            "storefronts_pending": len(pending),
            **result,
        }
