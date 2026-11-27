"""Preview-first reconciliation of podcast RSS releases to governed episodes."""

from __future__ import annotations

import hashlib
import html
import ipaddress
import json
import os
import re
import socket
from dataclasses import dataclass
from datetime import datetime, timezone
from difflib import SequenceMatcher
from email.utils import parsedate_to_datetime
from pathlib import Path
from time import perf_counter
from typing import Any
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener, urlopen
from xml.etree import ElementTree

from guest_database_manager.db_connection import connect_database
from guest_database_manager.database import GuestDatabase
from guest_database_manager.recommendation_learning import RecommendationLearning

DEFAULT_RSS_URL = "https://anchor.fm/s/261b1464/podcast/rss"
MAX_FEED_BYTES = 8 * 1024 * 1024
MAX_TRANSCRIPT_BYTES = 8 * 1024 * 1024
MAX_TRANSCRIPT_CHARACTERS = 5_000_000
MAX_TRANSCRIPT_ATTEMPTS = 5
DEFAULT_TRANSCRIPT_IMPORTS_PER_CYCLE = 20
AUTO_RELEASE_MAX_DATE_DISTANCE_DAYS = 3
PODCAST_NAMESPACE = "https://podcastindex.org/namespace/1.0"
SUPPORTED_TRANSCRIPT_TYPES = {
    "application/json",
    "application/srt",
    "application/x-subrip",
    "text/plain",
    "text/srt",
    "text/vtt",
}
GENERIC_DOWNLOAD_TYPES = {"application/octet-stream", "binary/octet-stream"}


class RSSReconciliationError(ValueError):
    """A safe, operator-facing RSS reconciliation error."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _normalize_title(value: Any) -> str:
    text = html.unescape(str(value or "")).casefold()
    return " ".join(re.findall(r"[a-z0-9]+", text))


def _guest_name_in_title(guest_name: Any, normalized_title: str) -> bool:
    """Return whether a sufficiently specific full guest name occurs in a feed title."""
    normalized_guest = _normalize_title(guest_name)
    guest_tokens = normalized_guest.split()
    if len(guest_tokens) < 2:
        return False
    return f" {normalized_guest} " in f" {normalized_title} "


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


def _publication_is_due(value: Any, *, reference: datetime | None = None) -> bool:
    published_at = _iso_datetime(value)
    if not published_at:
        return False
    due_at = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
    now = reference or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return due_at <= now.astimezone(timezone.utc)


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
    transcript_sources: tuple[dict[str, str], ...]
    content_hash: str


class _SafeTranscriptRedirectHandler(HTTPRedirectHandler):
    """Reject redirects before urllib can connect to a non-public destination."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        _validate_public_https_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _validate_public_https_url(value: Any) -> str:
    """Return a normalized public HTTPS URL or raise a safe reconciliation error."""
    url = str(value or "").strip()
    parsed = urlparse(url)
    if parsed.scheme.casefold() != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise RSSReconciliationError("Transcript URL must be a public HTTPS URL")
    try:
        addresses = socket.getaddrinfo(parsed.hostname, parsed.port or 443, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise RSSReconciliationError("Transcript host could not be resolved") from exc
    if not addresses:
        raise RSSReconciliationError("Transcript host could not be resolved")
    for address in addresses:
        try:
            ip = ipaddress.ip_address(address[4][0])
        except ValueError as exc:
            raise RSSReconciliationError("Transcript host returned an invalid address") from exc
        if not ip.is_global:
            raise RSSReconciliationError("Transcript URL must resolve to a public address")
    return url


def _timestamp_to_seconds(value: str) -> float | None:
    match = re.match(r"^(?:(\d+):)?(\d{1,2}):(\d{2})(?:[.,](\d{1,3}))?$", value.strip())
    if not match:
        return None
    hours, minutes, seconds, millis = match.groups()
    return int(hours or 0) * 3600 + int(minutes) * 60 + int(seconds) + int((millis or "0").ljust(3, "0")) / 1000


def _normalize_timed_transcript(text: str) -> str:
    """Convert SRT/VTT cues to readable paragraphs without timing markup."""
    lines: list[str] = []
    previous = ""
    for raw_line in text.replace("\ufeff", "").splitlines():
        line = raw_line.strip()
        if not line or line.upper() == "WEBVTT" or line.isdigit() or line.startswith(("NOTE", "STYLE", "REGION")):
            continue
        if "-->" in line:
            start = line.split("-->", 1)[0].strip().split(" ", 1)[0]
            if _timestamp_to_seconds(start) is not None:
                continue
        line = html.unescape(re.sub(r"<[^>]+>", "", line)).strip()
        if not line or line == previous:
            continue
        lines.append(line)
        previous = line
    return "\n".join(lines).strip()


def _json_transcript_text(payload: Any) -> str:
    """Extract ordered speech text from common Podcasting 2.0 JSON shapes."""
    if isinstance(payload, list):
        parts = [_json_transcript_text(item) for item in payload]
        return "\n".join(part for part in parts if part)
    if not isinstance(payload, dict):
        return ""
    for key in ("segments", "cues", "results", "items", "transcript"):
        if isinstance(payload.get(key), (list, dict)):
            nested = _json_transcript_text(payload[key])
            if nested:
                return nested
    for key in ("text", "content", "transcript"):
        if isinstance(payload.get(key), str):
            return payload[key].strip()
    return ""


def _decode_transcript(payload: bytes, media_type: str) -> str:
    """Validate and normalize one supported transcript representation."""
    if len(payload) > MAX_TRANSCRIPT_BYTES:
        raise RSSReconciliationError("Transcript exceeds the safe size limit")
    try:
        decoded = payload.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise RSSReconciliationError("Transcript is not valid UTF-8") from exc
    normalized_type = media_type.split(";", 1)[0].strip().casefold()
    if normalized_type == "application/json":
        try:
            text = _json_transcript_text(json.loads(decoded))
        except json.JSONDecodeError as exc:
            raise RSSReconciliationError("Transcript JSON is invalid") from exc
    elif normalized_type in {"application/srt", "application/x-subrip", "text/srt", "text/vtt"}:
        text = _normalize_timed_transcript(decoded)
    elif normalized_type == "text/plain":
        text = decoded.strip()
    else:
        raise RSSReconciliationError("Transcript media type is not supported")
    text = text.replace("\x00", "").strip()
    if not text:
        raise RSSReconciliationError("Transcript contains no readable text")
    if len(text) > MAX_TRANSCRIPT_CHARACTERS:
        raise RSSReconciliationError("Transcript exceeds the safe character limit")
    return text


class RSSReleaseReconciler:
    """Match feed items and optionally apply tightly governed release transitions."""

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
    def _preferred_transcript_source(item: FeedItem) -> dict[str, str] | None:
        """Choose one deterministic, losslessly convertible transcript source."""
        priority = {
            "application/json": 0,
            "text/vtt": 1,
            "application/x-subrip": 2,
            "application/srt": 2,
            "text/srt": 2,
            "text/plain": 3,
        }
        candidates = sorted(
            item.transcript_sources,
            key=lambda source: (
                priority.get(source.get("type", ""), 99),
                0 if source.get("rel", "").casefold() != "captions" else 1,
                source.get("url", ""),
            ),
        )
        return dict(candidates[0]) if candidates else None

    def fetch_transcript(self, source: dict[str, str], *, timeout_seconds: float = 20.0) -> tuple[str, str]:
        """Fetch a public transcript with SSRF, type, and size protections."""
        url = _validate_public_https_url(source.get("url"))
        expected_type = str(source.get("type") or "").split(";", 1)[0].strip().casefold()
        if expected_type not in SUPPORTED_TRANSCRIPT_TYPES:
            raise RSSReconciliationError("Transcript media type is not supported")
        request = Request(url, headers={"User-Agent": "MirrorTalkTranscriptImporter/1.0"})
        opener = build_opener(_SafeTranscriptRedirectHandler())
        try:
            with opener.open(request, timeout=max(2.0, timeout_seconds)) as response:  # noqa: S310 - validated URL
                _validate_public_https_url(response.geturl())
                response_type = str(response.headers.get("Content-Type") or "").split(";", 1)[0].strip().casefold()
                if response_type and response_type not in SUPPORTED_TRANSCRIPT_TYPES | GENERIC_DOWNLOAD_TYPES:
                    raise RSSReconciliationError("Transcript response type is not supported")
                payload = response.read(MAX_TRANSCRIPT_BYTES + 1)
        except RSSReconciliationError:
            raise
        except Exception as exc:
            raise RSSReconciliationError("Transcript could not be fetched") from exc
        if len(payload) > MAX_TRANSCRIPT_BYTES:
            raise RSSReconciliationError("Transcript exceeds the safe size limit")
        effective_type = expected_type if response_type in GENERIC_DOWNLOAD_TYPES else (response_type or expected_type)
        text = _decode_transcript(payload, effective_type)
        return text, hashlib.sha256(text.encode("utf-8")).hexdigest()

    @staticmethod
    def _transcript_error_code(exc: Exception) -> str:
        message = str(exc).casefold()
        for marker, code in (
            ("public https", "unsafe_url"),
            ("public address", "unsafe_url"),
            ("resolved", "dns_failed"),
            ("size", "too_large"),
            ("utf-8", "invalid_encoding"),
            ("json", "invalid_json"),
            ("media type", "unsupported_type"),
            ("response type", "unsupported_type"),
            ("readable text", "empty_transcript"),
        ):
            if marker in message:
                return code
        return "fetch_failed"

    def _sync_linked_transcript(
        self, *, rss_item_id: int, item: FeedItem, episode_id: int, actor: str
    ) -> str:
        """Import a transcript only through an already unique RSS-to-episode identity."""
        source = self._preferred_transcript_source(item)
        if source is None:
            return "unavailable"
        with connect_database(self.db_path) as conn:
            conn.row_factory = __import__("sqlite3").Row
            state = conn.execute(
                """SELECT transcript_status, transcript_attempts, transcript_next_attempt_at,
                          transcript_url, transcript_content_hash
                   FROM rss_feed_items WHERE id = ?""",
                (rss_item_id,),
            ).fetchone()
        if not state:
            return "unavailable"
        if state["transcript_status"] == "imported" and state["transcript_content_hash"]:
            return "already_imported"
        episode = self.database.get_episode_by_id(episode_id)
        if not episode or str(episode.get("release_status") or "").casefold() != "released":
            return "review_required"
        if str(episode.get("transcript_text") or "").strip():
            with connect_database(self.db_path) as conn:
                conn.execute(
                    "UPDATE rss_feed_items SET transcript_status = 'existing', "
                    "transcript_last_error_code = '' WHERE id = ?",
                    (rss_item_id,),
                )
                conn.commit()
            return "existing"
        attempts = int(state["transcript_attempts"] or 0)
        if attempts >= MAX_TRANSCRIPT_ATTEMPTS:
            return "failed"
        next_attempt = _iso_datetime(state["transcript_next_attempt_at"])
        if next_attempt and datetime.fromisoformat(next_attempt.replace("Z", "+00:00")) > datetime.now(timezone.utc):
            return "retry_wait"
        try:
            transcript_text, content_hash = self.fetch_transcript(source)
            self.database.synchronize_episode_transcript(
                episode_id,
                transcript_text=transcript_text,
                source_id=f"rss:{item.key}",
                source_version=content_hash,
                match_method="rss_unique_identity",
                match_score=1000,
                approve_source=True,
                overwrite_existing=False,
                source="podcast_rss",
                actor=actor,
                correlation_id=f"rss-transcript:{item.key}:{episode_id}",
            )
        except Exception as exc:
            next_attempts = attempts + 1
            retry_minutes = min(15 * (2 ** max(0, next_attempts - 1)), 24 * 60)
            error_code = self._transcript_error_code(exc)
            with connect_database(self.db_path) as conn:
                conn.execute(
                    """UPDATE rss_feed_items
                       SET transcript_status = 'failed', transcript_attempts = ?,
                           transcript_next_attempt_at = datetime('now', ?),
                           transcript_last_error_code = ?
                       WHERE id = ?""",
                    (next_attempts, f"+{retry_minutes} minutes", error_code, rss_item_id),
                )
                conn.commit()
            return "failed"
        with connect_database(self.db_path) as conn:
            conn.execute(
                """UPDATE rss_feed_items
                   SET transcript_status = 'imported', transcript_attempts = ?,
                       transcript_next_attempt_at = NULL, transcript_last_error_code = '',
                       transcript_imported_at = CURRENT_TIMESTAMP, transcript_content_hash = ?
                   WHERE id = ?""",
                (attempts + 1, content_hash, rss_item_id),
            )
            conn.commit()
        return "imported"

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
        podcast = f"{{{PODCAST_NAMESPACE}}}"
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
            transcript_sources: list[dict[str, str]] = []
            seen_transcripts: set[tuple[str, str]] = set()
            for transcript in node.findall(f"{podcast}transcript"):
                transcript_url = str(transcript.attrib.get("url") or "").strip()
                transcript_type = str(transcript.attrib.get("type") or "").split(";", 1)[0].strip().casefold()
                if not transcript_url or transcript_type not in SUPPORTED_TRANSCRIPT_TYPES:
                    continue
                identity_key = (transcript_url, transcript_type)
                if identity_key in seen_transcripts:
                    continue
                seen_transcripts.add(identity_key)
                transcript_sources.append({
                    "url": transcript_url,
                    "type": transcript_type,
                    "language": str(transcript.attrib.get("language") or "").strip(),
                    "rel": str(transcript.attrib.get("rel") or "").strip(),
                })
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
                f"{duration_seconds}\0{artwork_url}\0{season_number}\0{episode_number}\0{feed_position}\0"
                f"{json.dumps(transcript_sources, sort_keys=True)}".encode()
            ).hexdigest()
            items.append(FeedItem(
                key, guid, title, normalized, published_at, link, enclosure_url, description,
                duration_seconds, artwork_url, season_number, episode_number, feed_position,
                tuple(transcript_sources), content_hash,
            ))
        if not items:
            raise RSSReconciliationError("The podcast RSS feed contains no episodes")
        return items

    def _episodes(self) -> list[dict[str, Any]]:
        with connect_database(self.db_path) as conn:
            conn.row_factory = __import__("sqlite3").Row
            return [dict(row) for row in conn.execute(
                """SELECT id, guest_name, episode_title, working_title, published_title,
                          release_date, release_status
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

            # Published titles often replace the editorial title. A full guest name
            # plus close release-date agreement is strong enough to identify a
            # unique episode, while repeat guests and single-name guests stay out of
            # automation.
            if not candidates and item.normalized_title:
                guest_date_candidates = []
                for episode_id, episode in by_id.items():
                    if not _guest_name_in_title(episode.get("guest_name"), item.normalized_title):
                        continue
                    candidate_distance = _date_distance_days(
                        item.published_at, episode.get("release_date")
                    )
                    if (
                        candidate_distance is not None
                        and candidate_distance <= AUTO_RELEASE_MAX_DATE_DISTANCE_DAYS
                    ):
                        guest_date_candidates.append(episode_id)
                if len(guest_date_candidates) == 1:
                    candidates = guest_date_candidates
                    method = "guest_name_date"
                    confidence = 0.99
                elif len(guest_date_candidates) > 1:
                    candidates = sorted(guest_date_candidates)
                    method = "guest_name_date"
                    confidence = 0.0

            status = "unmatched"
            reason = "No unique title candidate"
            episode_id = candidates[0] if len(candidates) == 1 else None
            distance = _date_distance_days(item.published_at, by_id[episode_id].get("release_date")) if episode_id else None
            if len(candidates) > 1:
                status, reason = "review_required", "RSS evidence matches more than one episode"
            elif episode_id:
                episode = by_id[episode_id]
                if (
                    str(episode.get("release_status") or "").strip().casefold() != "released"
                    and not _publication_is_due(item.published_at)
                ):
                    status, reason = "review_required", "RSS publication time has not arrived"
                elif str(episode.get("release_status") or "").strip().casefold() != "released":
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
                "episode_release_status": (
                    str(by_id[episode_id].get("release_status") or "").strip().casefold()
                    if episode_id else ""
                ),
            })
        episode_match_counts: dict[int, int] = {}
        for match in matches:
            if match["episode_id"] is not None:
                episode_id = int(match["episode_id"])
                episode_match_counts[episode_id] = episode_match_counts.get(episode_id, 0) + 1
        for match in matches:
            episode_id = match["episode_id"]
            if episode_id is not None and episode_match_counts[int(episode_id)] > 1:
                match["status"] = "conflict"
                match["reason"] = "More than one feed item maps to the same episode"
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
                transcript_source = self._preferred_transcript_source(item)
                transcript_url = str((transcript_source or {}).get("url") or "")
                transcript_type = str((transcript_source or {}).get("type") or "")
                transcript_language = str((transcript_source or {}).get("language") or "")
                conn.execute(
                    """INSERT INTO rss_feed_items
                       (feed_url, item_key, guid, title, normalized_title, published_at, link, enclosure_url,
                        description, duration_seconds, artwork_url, season_number, episode_number, feed_position,
                        transcript_sources_json, transcript_url, transcript_type, transcript_language,
                        transcript_status, content_hash, first_seen_at, last_seen_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                       ON CONFLICT(feed_url, item_key) DO UPDATE SET title=excluded.title,
                         normalized_title=excluded.normalized_title, published_at=excluded.published_at,
                         link=excluded.link, enclosure_url=excluded.enclosure_url,
                         description=excluded.description, duration_seconds=excluded.duration_seconds,
                         artwork_url=excluded.artwork_url, season_number=excluded.season_number,
                         episode_number=excluded.episode_number, feed_position=excluded.feed_position,
                         transcript_sources_json=excluded.transcript_sources_json,
                         transcript_type=excluded.transcript_type,
                         transcript_language=excluded.transcript_language,
                         transcript_attempts=CASE WHEN rss_feed_items.transcript_url <> excluded.transcript_url
                           THEN 0 ELSE rss_feed_items.transcript_attempts END,
                         transcript_next_attempt_at=CASE WHEN rss_feed_items.transcript_url <> excluded.transcript_url
                           THEN NULL ELSE rss_feed_items.transcript_next_attempt_at END,
                         transcript_last_error_code=CASE WHEN rss_feed_items.transcript_url <> excluded.transcript_url
                           THEN '' ELSE rss_feed_items.transcript_last_error_code END,
                         transcript_status=CASE
                           WHEN excluded.transcript_url = '' THEN 'unavailable'
                           WHEN rss_feed_items.transcript_url <> excluded.transcript_url THEN 'pending'
                           ELSE rss_feed_items.transcript_status END,
                         transcript_url=excluded.transcript_url,
                         content_hash=excluded.content_hash, last_seen_at=excluded.last_seen_at""",
                    (self.feed_url, item.key, item.guid, item.title, item.normalized_title, item.published_at,
                     item.link, item.enclosure_url, item.description, item.duration_seconds, item.artwork_url,
                     item.season_number, item.episode_number, item.feed_position,
                     json.dumps(item.transcript_sources, sort_keys=True), transcript_url, transcript_type,
                     transcript_language, "pending" if transcript_url else "unavailable",
                     item.content_hash, fetched_at, fetched_at),
                )
                item_id = int(conn.execute(
                    "SELECT id FROM rss_feed_items WHERE feed_url = ? AND item_key = ?", (self.feed_url, item.key)
                ).fetchone()[0])
                if transcript_url and match["status"] != "auto_linked":
                    conn.execute(
                        """UPDATE rss_feed_items SET transcript_status = 'review_required'
                           WHERE id = ? AND transcript_status NOT IN ('imported', 'existing')""",
                        (item_id,),
                    )
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
        transcript_imports = 0
        transcript_failures = 0
        transcript_review_required = 0
        transcript_deferred = 0
        try:
            configured_limit = int(os.environ.get(
                "MIRROR_TALK_RSS_TRANSCRIPT_IMPORTS_PER_CYCLE",
                str(DEFAULT_TRANSCRIPT_IMPORTS_PER_CYCLE),
            ))
        except ValueError:
            configured_limit = DEFAULT_TRANSCRIPT_IMPORTS_PER_CYCLE
        transcript_import_limit = min(max(configured_limit, 1), 50)
        transcript_attempts_this_cycle = 0
        for item_id, match in persisted:
            item = match["item"]
            should_confirm_release = (
                apply_lifecycle
                and
                match.get("episode_id") is not None
                and match.get("status") == "review_required"
                and match.get("match_method") in {"exact_title", "guest_name_date"}
                and float(match.get("confidence") or 0) >= 0.99
                and match.get("episode_release_status") == "scheduled"
                and match.get("date_distance_days") is not None
                and int(match["date_distance_days"]) <= AUTO_RELEASE_MAX_DATE_DISTANCE_DAYS
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
            if apply_lifecycle and match["status"] == "auto_linked" and match.get("episode_id") is not None:
                if transcript_attempts_this_cycle >= transcript_import_limit:
                    transcript_deferred += int(bool(item.transcript_sources))
                else:
                    transcript_result = self._sync_linked_transcript(
                        rss_item_id=item_id,
                        item=item,
                        episode_id=int(match["episode_id"]),
                        actor=actor,
                    )
                    if transcript_result in {"imported", "failed"}:
                        transcript_attempts_this_cycle += 1
                    transcript_imports += int(transcript_result == "imported")
                    transcript_failures += int(transcript_result == "failed")
                    transcript_review_required += int(transcript_result == "review_required")
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
            "transcript_imports": transcript_imports,
            "transcript_failures": transcript_failures,
            "transcript_review_required": transcript_review_required,
            "transcript_deferred": transcript_deferred,
            "transcript_import_limit": transcript_import_limit,
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
            transcript_counts = {str(row[0]): int(row[1]) for row in conn.execute(
                "SELECT transcript_status, COUNT(*) FROM rss_feed_items GROUP BY transcript_status"
            ).fetchall()}
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
            "transcripts": transcript_counts,
            "publishing_cadence": cadence,
        }
