"""Preview-first reconciliation of podcast RSS releases to governed episodes."""

from __future__ import annotations

import hashlib
import html
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from difflib import SequenceMatcher
from email.utils import parsedate_to_datetime
from pathlib import Path
from time import perf_counter
from typing import Any
from urllib.request import Request, urlopen
from xml.etree import ElementTree

from guest_database_manager.db_connection import connect_database
from guest_database_manager.database import GuestDatabase
from guest_database_manager.recommendation_learning import RecommendationLearning

DEFAULT_RSS_URL = "https://anchor.fm/s/261b1464/podcast/rss"
MAX_FEED_BYTES = 8 * 1024 * 1024


class RSSReconciliationError(ValueError):
    """A safe, operator-facing RSS reconciliation error."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _normalize_title(value: Any) -> str:
    text = html.unescape(str(value or "")).casefold()
    return " ".join(re.findall(r"[a-z0-9]+", text))


def _iso_datetime(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        parsed = parsedate_to_datetime(text)
    except (TypeError, ValueError, OverflowError):
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return ""
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _date_distance_days(first: Any, second: Any) -> int | None:
    left = _iso_datetime(first)
    right = _iso_datetime(second)
    if not left or not right:
        return None
    return abs((datetime.fromisoformat(left.replace("Z", "+00:00")).date() -
                datetime.fromisoformat(right.replace("Z", "+00:00")).date()).days)


def _duration_seconds(value: Any) -> int | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parts = [int(part) for part in text.split(":")]
    except ValueError:
        return None
    if len(parts) == 1:
        return parts[0] if parts[0] >= 0 else None
    if len(parts) not in (2, 3) or any(part < 0 for part in parts):
        return None
    total = 0
    for part in parts:
        total = total * 60 + part
    return total


def _positive_integer(value: Any) -> int | None:
    try:
        number = int(str(value or "").strip())
    except ValueError:
        return None
    return number if number > 0 else None


@dataclass(frozen=True)
class FeedItem:
    key: str
    guid: str
    title: str
    normalized_title: str
    published_at: str
    link: str
    enclosure_url: str
    description: str
    duration_seconds: int | None
    artwork_url: str
    season_number: int | None
    episode_number: int | None
    feed_position: int
    content_hash: str


class RSSReleaseReconciler:
    """Match authoritative feed items without mutating episode lifecycle fields."""

    def __init__(self, db_path: str | Path, *, feed_url: str = ""):
        self.db_path = str(db_path)
        self.feed_url = feed_url.strip() or os.environ.get("MIRROR_TALK_PODCAST_RSS_URL", "").strip() or DEFAULT_RSS_URL
        self.learning = RecommendationLearning(db_path)
        self.database = GuestDatabase(db_path)

    def fetch(self, *, timeout_seconds: float = 15.0) -> bytes:
        request = Request(self.feed_url, headers={"User-Agent": "MirrorTalkReleaseReconciler/1.0"})
        try:
            with urlopen(request, timeout=max(2.0, timeout_seconds)) as response:  # noqa: S310 - configured HTTPS feed
                content_type = str(response.headers.get("Content-Type") or "").casefold()
                if content_type and not any(kind in content_type for kind in ("xml", "rss", "text")):
                    raise RSSReconciliationError("The configured feed did not return RSS/XML content")
                payload = response.read(MAX_FEED_BYTES + 1)
        except RSSReconciliationError:
            raise
        except Exception as exc:
            raise RSSReconciliationError("The podcast RSS feed could not be fetched") from exc
        if len(payload) > MAX_FEED_BYTES:
            raise RSSReconciliationError("The podcast RSS feed exceeds the safe size limit")
        return payload

    @staticmethod
    def parse(payload: bytes | str) -> list[FeedItem]:
        raw = payload.encode("utf-8") if isinstance(payload, str) else payload
        if len(raw) > MAX_FEED_BYTES:
            raise RSSReconciliationError("The podcast RSS feed exceeds the safe size limit")
        upper = raw.upper()
        if b"<!DOCTYPE" in upper or b"<!ENTITY" in upper:
            raise RSSReconciliationError("The podcast RSS feed contains unsupported XML declarations")
        try:
            root = ElementTree.fromstring(raw)
        except ElementTree.ParseError as exc:
            raise RSSReconciliationError("The podcast RSS feed is not valid XML") from exc
        items: list[FeedItem] = []
        seen: set[str] = set()
        itunes = "{http://www.itunes.com/dtds/podcast-1.0.dtd}"
        content = "{http://purl.org/rss/1.0/modules/content/}"
        channel_image = root.find(f"./channel/{itunes}image")
        channel_artwork = str(channel_image.attrib.get("href") or "").strip() if channel_image is not None else ""
        for feed_position, node in enumerate(root.findall("./channel/item"), start=1):
            def text(name: str) -> str:
                child = node.find(name)
                return str(child.text or "").strip() if child is not None else ""

            title = text("title")
            guid = text("guid")
            link = text("link")
            enclosure = node.find("enclosure")
            enclosure_url = str(enclosure.attrib.get("url") or "").strip() if enclosure is not None else ""
            description = text(f"{content}encoded") or text("description")
            duration_seconds = _duration_seconds(text(f"{itunes}duration"))
            item_image = node.find(f"{itunes}image")
            artwork_url = (
                str(item_image.attrib.get("href") or "").strip() if item_image is not None else channel_artwork
            )
            season_number = _positive_integer(text(f"{itunes}season"))
            episode_number = _positive_integer(text(f"{itunes}episode"))
            published_at = _iso_datetime(text("pubDate"))
            identity = guid or enclosure_url or link
            if not identity:
                identity = hashlib.sha256(f"{title}\0{published_at}".encode()).hexdigest()
            key = hashlib.sha256(identity.encode()).hexdigest()
            if key in seen:
                continue
            seen.add(key)
            normalized = _normalize_title(title)
            content_hash = hashlib.sha256(
                f"{identity}\0{normalized}\0{published_at}\0{link}\0{enclosure_url}\0{description}\0"
                f"{duration_seconds}\0{artwork_url}\0{season_number}\0{episode_number}\0{feed_position}".encode()
            ).hexdigest()
            items.append(FeedItem(
                key, guid, title, normalized, published_at, link, enclosure_url, description,
                duration_seconds, artwork_url, season_number, episode_number, feed_position, content_hash,
            ))
        if not items:
            raise RSSReconciliationError("The podcast RSS feed contains no episodes")
        return items

    def _episodes(self) -> list[dict[str, Any]]:
        with connect_database(self.db_path) as conn:
            conn.row_factory = __import__("sqlite3").Row
            return [dict(row) for row in conn.execute(
                """SELECT id, episode_title, working_title, published_title, release_date, release_status
                   FROM episodes ORDER BY id"""
            ).fetchall()]

    def preview(self, payload: bytes | str | None = None) -> dict[str, Any]:
        items = self.parse(payload if payload is not None else self.fetch())
        episodes = self._episodes()
        title_index: dict[str, set[int]] = {}
        normalized_by_episode: dict[int, set[str]] = {}
        by_id = {int(row["id"]): row for row in episodes}
        for episode in episodes:
            episode_id = int(episode["id"])
            titles = {_normalize_title(episode.get(field)) for field in ("published_title", "episode_title", "working_title")}
            titles.discard("")
            normalized_by_episode[episode_id] = titles
            for title in titles:
                title_index.setdefault(title, set()).add(episode_id)

        matches: list[dict[str, Any]] = []
        claimed: dict[int, str] = {}
        for item in items:
            candidates = sorted(title_index.get(item.normalized_title, set()))
            method = "exact_title"
            confidence = 1.0 if candidates else 0.0
            if not candidates and item.normalized_title:
                scored = sorted(
                    ((max((SequenceMatcher(None, item.normalized_title, title).ratio() for title in titles), default=0.0), episode_id)
                     for episode_id, titles in normalized_by_episode.items()),
                    reverse=True,
                )
                if scored and scored[0][0] >= 0.9:
                    confidence, best_id = scored[0]
                    runner_up = scored[1][0] if len(scored) > 1 else 0.0
                    if confidence - runner_up >= 0.05:
                        candidates = [best_id]
                        method = "strong_title"

            status = "unmatched"
            reason = "No unique title candidate"
            episode_id = candidates[0] if len(candidates) == 1 else None
            distance = _date_distance_days(item.published_at, by_id[episode_id].get("release_date")) if episode_id else None
            if len(candidates) > 1:
                status, reason = "review_required", "Title matches more than one episode"
            elif episode_id:
                episode = by_id[episode_id]
                if str(episode.get("release_status") or "").strip().casefold() != "released":
                    status, reason = "review_required", "RSS confirms publication but the episode is not marked released"
                elif episode_id in claimed and claimed[episode_id] != item.key:
                    status, reason = "conflict", "More than one feed item maps to the same episode"
                elif distance is not None and distance > 14:
                    status, reason = "review_required", "Feed and system release dates differ by more than 14 days"
                elif method == "strong_title" and (confidence < 0.94 or distance is None or distance > 3):
                    status, reason = "review_required", "Fuzzy title match lacks strong date agreement"
                else:
                    status, reason = "auto_linked", "Unique released episode match"
                    claimed[episode_id] = item.key
            matches.append({
                "item": item, "episode_id": episode_id, "status": status, "match_method": method,
                "confidence": round(confidence, 4), "date_distance_days": distance, "reason": reason,
            })
        counts: dict[str, int] = {}
        for match in matches:
            counts[match["status"]] = counts.get(match["status"], 0) + 1
        return {"feed_url": self.feed_url, "item_count": len(items), "counts": counts, "matches": matches}

    def reconcile(
        self,
        *,
        actor: str,
        payload: bytes | str | None = None,
        apply_lifecycle: bool = False,
    ) -> dict[str, Any]:
        started = perf_counter()
        try:
            result = self._reconcile(actor=actor, payload=payload, apply_lifecycle=apply_lifecycle)
        except Exception as exc:
            self._record_run(
                actor=actor, status="failed", latency_ms=round((perf_counter() - started) * 1000),
                error_code=type(exc).__name__, result={},
            )
            raise
        self._record_run(
            actor=actor, status="completed", latency_ms=round((perf_counter() - started) * 1000),
            error_code="", result=result,
        )
        return result

    def _record_run(self, *, actor: str, status: str, latency_ms: int, error_code: str,
                    result: dict[str, Any]) -> None:
        counts = result.get("counts") or {}
        with connect_database(self.db_path) as conn:
            conn.execute(
                """INSERT INTO rss_reconciliation_runs
                   (feed_url, status, item_count, auto_linked_count, review_count,
                    unmatched_count, latency_ms, error_code, actor)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (self.feed_url, status, int(result.get("item_count") or 0),
                 int(counts.get("auto_linked") or 0),
                 int(counts.get("review_required") or 0) + int(counts.get("conflict") or 0),
                 int(counts.get("unmatched") or 0), max(0, latency_ms), error_code, actor),
            )
            conn.commit()

    def _reconcile(
        self,
        *,
        actor: str,
        payload: bytes | str | None = None,
        apply_lifecycle: bool = False,
    ) -> dict[str, Any]:
        preview = self.preview(payload)
        persisted: list[tuple[int, dict[str, Any]]] = []
        fetched_at = _now()
        with connect_database(self.db_path) as conn:
            conn.row_factory = __import__("sqlite3").Row
            for match in preview["matches"]:
                item: FeedItem = match["item"]
                conn.execute(
                    """INSERT INTO rss_feed_items
                       (feed_url, item_key, guid, title, normalized_title, published_at, link, enclosure_url,
                        description, duration_seconds, artwork_url, season_number, episode_number, feed_position,
                        content_hash, first_seen_at, last_seen_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                       ON CONFLICT(feed_url, item_key) DO UPDATE SET title=excluded.title,
                         normalized_title=excluded.normalized_title, published_at=excluded.published_at,
                         link=excluded.link, enclosure_url=excluded.enclosure_url,
                         description=excluded.description, duration_seconds=excluded.duration_seconds,
                         artwork_url=excluded.artwork_url, season_number=excluded.season_number,
                         episode_number=excluded.episode_number, feed_position=excluded.feed_position,
                         content_hash=excluded.content_hash, last_seen_at=excluded.last_seen_at""",
                    (self.feed_url, item.key, item.guid, item.title, item.normalized_title, item.published_at,
                     item.link, item.enclosure_url, item.description, item.duration_seconds, item.artwork_url,
                     item.season_number, item.episode_number, item.feed_position, item.content_hash, fetched_at, fetched_at),
                )
                item_id = int(conn.execute(
                    "SELECT id FROM rss_feed_items WHERE feed_url = ? AND item_key = ?", (self.feed_url, item.key)
                ).fetchone()[0])
                evidence = json.dumps({"date_distance_days": match["date_distance_days"]}, sort_keys=True)
                conn.execute(
                    """INSERT INTO rss_release_reconciliations
                       (rss_item_id, episode_id, status, match_method, confidence, reason, evidence_json, actor)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                       ON CONFLICT(rss_item_id) DO UPDATE SET episode_id=excluded.episode_id,
                         status=excluded.status, match_method=excluded.match_method,
                         confidence=excluded.confidence, reason=excluded.reason,
                         evidence_json=excluded.evidence_json, actor=excluded.actor,
                         updated_at=CURRENT_TIMESTAMP""",
                    (item_id, match["episode_id"], match["status"], match["match_method"],
                     match["confidence"], match["reason"], evidence, actor),
                )
                persisted.append((item_id, match))
            conn.commit()

        outcomes = 0
        linked_outcomes = 0
        new_outcomes = 0
        lifecycle_updates = 0
        for item_id, match in persisted:
            item = match["item"]
            should_confirm_release = (
                apply_lifecycle
                and
                match.get("episode_id") is not None
                and match.get("status") == "review_required"
                and match.get("match_method") == "exact_title"
                and float(match.get("confidence") or 0) >= 0.99
                and match.get("reason") == "RSS confirms publication but the episode is not marked released"
            )
            should_sync_metadata = apply_lifecycle and match.get("episode_id") is not None and (
                match.get("status") == "auto_linked" or should_confirm_release
            )
            if should_sync_metadata:
                self.database.confirm_episode_release_from_rss(
                    int(match["episode_id"]),
                    published_title=item.title,
                    published_at=item.published_at,
                    published_description=item.description,
                    public_episode_url=item.link,
                    audio_enclosure_url=item.enclosure_url,
                    duration_seconds=item.duration_seconds,
                    artwork_url=item.artwork_url,
                    season_number=item.season_number,
                    episode_number=item.episode_number,
                    feed_position=item.feed_position,
                    actor=actor,
                    correlation_id=f"rss:{item.key}",
                )
            if should_confirm_release:
                match["status"] = "auto_linked"
                match["reason"] = "Canonical RSS feed confirmed and applied the release"
                lifecycle_updates += 1
                with connect_database(self.db_path) as conn:
                    conn.execute(
                        """UPDATE rss_release_reconciliations
                           SET status = 'auto_linked', reason = ?, actor = ?, updated_at = CURRENT_TIMESTAMP
                           WHERE rss_item_id = ?""",
                        (match["reason"], actor, item_id),
                    )
                    conn.commit()
            if match["status"] != "auto_linked":
                continue
            with connect_database(self.db_path) as conn:
                conn.row_factory = __import__("sqlite3").Row
                existing = conn.execute(
                    """SELECT * FROM recommendation_outcomes
                       WHERE episode_id = ? AND outcome_type = 'released'
                       ORDER BY occurred_at, id LIMIT 1""", (int(match["episode_id"]),)
                ).fetchone()
            if existing:
                outcome = dict(existing)
            else:
                outcome = self.learning.record_outcome(
                    int(match["episode_id"]), outcome_type="released", value=None,
                    metadata={"feed_url": self.feed_url, "rss_item_key": item.key, "published_at": item.published_at},
                    actor=actor, source="podcast_rss", occurred_at=item.published_at,
                    idempotency_key=f"rss-release:{item.key}",
                )
                new_outcomes += 1
            outcomes += 1
            linked_outcomes += int(outcome.get("observation_id") is not None)
            with connect_database(self.db_path) as conn:
                conn.execute("UPDATE rss_release_reconciliations SET outcome_id = ? WHERE rss_item_id = ?", (outcome["id"], item_id))
                conn.commit()
        final_counts: dict[str, int] = {}
        for _, match in persisted:
            status = str(match["status"])
            final_counts[status] = final_counts.get(status, 0) + 1
        return {
            "feed_url": self.feed_url, "item_count": preview["item_count"], "counts": final_counts,
            "outcomes_verified": outcomes, "new_outcomes": new_outcomes, "linked_outcomes": linked_outcomes,
            "lifecycle_updates": lifecycle_updates,
            "ranking_changed": False, "lifecycle_changed": lifecycle_updates > 0,
        }

    def status(self) -> dict[str, Any]:
        with connect_database(self.db_path) as conn:
            conn.row_factory = __import__("sqlite3").Row
            counts = {str(row[0]): int(row[1]) for row in conn.execute(
                "SELECT status, COUNT(*) FROM rss_release_reconciliations GROUP BY status"
            ).fetchall()}
            total = int(conn.execute("SELECT COUNT(*) FROM rss_feed_items").fetchone()[0])
            latest = conn.execute("SELECT MAX(last_seen_at) FROM rss_feed_items").fetchone()[0]
            reviews = [dict(row) for row in conn.execute(
                """SELECT r.id, f.title, f.published_at, r.episode_id, r.status,
                          r.match_method, r.confidence, r.reason
                   FROM rss_release_reconciliations r JOIN rss_feed_items f ON f.id = r.rss_item_id
                   WHERE r.status IN ('review_required', 'conflict')
                   ORDER BY f.published_at DESC, r.id DESC LIMIT 20"""
            ).fetchall()]
            latest_run = conn.execute("SELECT * FROM rss_reconciliation_runs ORDER BY id DESC LIMIT 1").fetchone()
            failures = int(conn.execute(
                "SELECT COUNT(*) FROM rss_reconciliation_runs WHERE status = 'failed' AND created_at >= datetime('now', '-24 hours')"
            ).fetchone()[0])
            published = [str(row[0]) for row in conn.execute(
                "SELECT published_at FROM rss_feed_items WHERE published_at != '' ORDER BY published_at DESC LIMIT 50"
            ).fetchall()]
        dates = [datetime.fromisoformat(value.replace("Z", "+00:00")) for value in published]
        intervals = [(dates[index] - dates[index + 1]).total_seconds() / 86400 for index in range(len(dates) - 1)]
        ordered = sorted(intervals)
        median_days = None
        if ordered:
            middle = len(ordered) // 2
            median_days = ordered[middle] if len(ordered) % 2 else (ordered[middle - 1] + ordered[middle]) / 2
        cadence = {
            "episodes_analyzed": len(dates),
            "intervals_analyzed": len(intervals),
            "median_days_between_releases": round(median_days, 1) if median_days is not None else None,
            "average_days_between_releases": round(sum(intervals) / len(intervals), 1) if intervals else None,
            "latest_published_at": published[0] if published else None,
        }
        return {
            "feed_url": self.feed_url, "items": total, "counts": counts, "latest_fetch_at": latest,
            "review_queue": reviews, "latest_run": dict(latest_run) if latest_run else None,
            "failures_24h": failures,
            "publishing_cadence": cadence,
        }
