"""Supported, read-only OAuth collection for private podcast analytics."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import secrets
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from cryptography.fernet import Fernet, InvalidToken

from guest_database_manager.db_connection import connect_database
from guest_database_manager.growth_intelligence import GrowthIntelligence

GOOGLE_CLIENT_ID_ENV = "MIRROR_TALK_GOOGLE_ANALYTICS_CLIENT_ID"
GOOGLE_CLIENT_SECRET_ENV = "MIRROR_TALK_GOOGLE_ANALYTICS_CLIENT_SECRET"
TOKEN_KEY_ENV = "MIRROR_TALK_ANALYTICS_TOKEN_ENCRYPTION_KEY"
GA4_PROPERTY_ENV = "MIRROR_TALK_GA4_PROPERTY_ID"
PUBLIC_URL_ENV = "MIRROR_TALK_PUBLIC_URL"
COLLECTOR_TOKEN_ENV = "MIRROR_TALK_ANALYTICS_COLLECTOR_TOKEN"
LOCAL_COLLECTOR_PROVIDERS = {"spotify", "apple_podcasts"}

GOOGLE_SCOPES = (
    "openid",
    "email",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/analytics.readonly",
)


class AnalyticsConnectorError(ValueError):
    """A safe, user-facing connector failure."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


class PodcastAnalyticsConnectors:
    """Own OAuth credentials, collection, retry state, and disconnect behavior."""

    def __init__(self, db_path: str | Path):
        self.db_path = str(db_path)
        self.growth = GrowthIntelligence(db_path)

    @staticmethod
    def _config() -> dict[str, str]:
        return {
            "client_id": os.environ.get(GOOGLE_CLIENT_ID_ENV, "").strip(),
            "client_secret": os.environ.get(GOOGLE_CLIENT_SECRET_ENV, "").strip(),
            "token_key": os.environ.get(TOKEN_KEY_ENV, "").strip(),
            "ga4_property_id": os.environ.get(GA4_PROPERTY_ENV, "").strip().removeprefix("properties/"),
            "public_url": os.environ.get(PUBLIC_URL_ENV, "").strip().rstrip("/"),
            "collector_token": os.environ.get(COLLECTOR_TOKEN_ENV, "").strip(),
        }

    @classmethod
    def _cipher(cls) -> Fernet:
        secret = cls._config()["token_key"]
        if len(secret) < 32:
            raise AnalyticsConnectorError("Analytics token encryption is not configured.")
        key = base64.urlsafe_b64encode(hashlib.sha256(secret.encode("utf-8")).digest())
        return Fernet(key)

    @classmethod
    def _redirect_uri(cls, origin: str = "") -> str:
        base = cls._config()["public_url"] or origin.rstrip("/")
        if not base:
            raise AnalyticsConnectorError("The public application URL is not configured.")
        return f"{base}/api/analytics-connectors/google/callback"

    def status(self) -> dict[str, Any]:
        config = self._config()
        with connect_database(self.db_path) as conn:
            conn.row_factory = __import__("sqlite3").Row
            rows = conn.execute(
                """SELECT id, provider, account_email, youtube_channel_id, youtube_channel_title,
                          youtube_channel_thumbnail, sync_ga4, status, scopes_json, connected_at,
                          last_sync_at, last_success_at, last_error_code, last_error_at,
                          next_retry_at, consecutive_failures, revoked_at, updated_at
                   FROM analytics_oauth_connections WHERE provider = 'google'
                   ORDER BY connected_at, id"""
            ).fetchall()
            collector_rows = conn.execute(
                """SELECT provider, enabled, status, last_seen_at, last_sync_at, last_success_at,
                          last_error_code, last_error_at, consecutive_failures, updated_at
                   FROM analytics_browser_collectors ORDER BY provider"""
            ).fetchall()
        connections = [dict(row) for row in rows]
        for connection in connections:
            connection["scopes"] = json.loads(connection.pop("scopes_json") or "[]")
            connection["sync_ga4"] = bool(connection["sync_ga4"])
        oauth_ready = bool(config["client_id"] and config["client_secret"] and len(config["token_key"]) >= 32)
        collectors = {str(row["provider"]): dict(row) for row in collector_rows}
        for provider in LOCAL_COLLECTOR_PROVIDERS:
            collectors.setdefault(provider, {
                "provider": provider, "enabled": 0, "status": "disconnected",
                "last_seen_at": None, "last_sync_at": None, "last_success_at": None,
                "last_error_code": "", "last_error_at": None,
                "consecutive_failures": 0, "updated_at": None,
            })
        for item in collectors.values():
            item["enabled"] = bool(item["enabled"])
        return {
            "google": {
                "oauth_configured": oauth_ready,
                "ga4_configured": bool(config["ga4_property_id"]),
                "youtube_supported": True,
                "ga4_supported": True,
                "connections": connections,
                "connection": connections[0] if len(connections) == 1 else None,
                "required_environment": [
                    GOOGLE_CLIENT_ID_ENV,
                    GOOGLE_CLIENT_SECRET_ENV,
                    TOKEN_KEY_ENV,
                    GA4_PROPERTY_ENV,
                ],
            },
            "local_collectors": {
                "configured": len(config["collector_token"]) >= 32,
                "connections": collectors,
                "session_storage": "local_only",
                "required_environment": [COLLECTOR_TOKEN_ENV],
            },
            "unsupported": [
                {"provider": "spotify_creators", "reason": "No supported private creator-analytics API."},
                {"provider": "apple_connect", "reason": "Apple does not provide third-party podcast analytics access."},
            ],
        }

    @staticmethod
    def _local_provider(provider: str) -> str:
        normalized = str(provider or "").strip().casefold()
        if normalized not in LOCAL_COLLECTOR_PROVIDERS:
            raise AnalyticsConnectorError("The local collector supports only Spotify and Apple Podcasts.")
        return normalized

    def set_local_collector(self, provider: str, *, enabled: bool, actor: str) -> dict[str, Any]:
        provider = self._local_provider(provider)
        if enabled and len(self._config()["collector_token"]) < 32:
            raise AnalyticsConnectorError("The local analytics collector token is not configured in production.")
        now = _iso(_now())
        status = "waiting" if enabled else "disconnected"
        with connect_database(self.db_path) as conn:
            conn.execute(
                """INSERT INTO analytics_browser_collectors (provider, enabled, status, updated_at)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(provider) DO UPDATE SET enabled=excluded.enabled, status=excluded.status,
                     last_error_code='', last_error_at=NULL, consecutive_failures=0, updated_at=excluded.updated_at""",
                (provider, int(enabled), status, now),
            )
            self._audit(
                conn, "analytics_local_collector_changed", actor,
                "Local-only browser analytics collector changed",
                {"provider": provider, "enabled": bool(enabled), "session_storage": "local_only"},
            )
            conn.commit()
        return {"provider": provider, "enabled": bool(enabled), "status": status}

    def ingest_local_export(
        self, *, provider: str, token: str, csv_text: str, source_reference: str
    ) -> dict[str, Any]:
        provider = self._local_provider(provider)
        expected = self._config()["collector_token"]
        if len(expected) < 32 or not secrets.compare_digest(str(token or ""), expected):
            raise AnalyticsConnectorError("The local analytics collector credential is invalid.")
        now = _now()
        with connect_database(self.db_path) as conn:
            row = conn.execute(
                "SELECT enabled FROM analytics_browser_collectors WHERE provider=?", (provider,)
            ).fetchone()
        if not row or not bool(row[0]):
            raise AnalyticsConnectorError("This local analytics collector is disabled in Podcast Reach.")
        try:
            preview = self.growth.preview_csv(
                csv_text, provider=provider, source_reference=source_reference, mapping=None
            )
            if int(preview["summary"].get("invalid") or 0):
                raise AnalyticsConnectorError(
                    "The provider export contains rows that require review; nothing was imported automatically."
                )
            observations = preview.get("observations") or []
            if not observations:
                raise AnalyticsConnectorError("The provider export contains no new valid observations.")
            result = self.growth.record_observations(
                observations,
                actor="local-analytics-collector",
                correlation_id=f"local-{provider}-{hashlib.sha256(csv_text.encode()).hexdigest()[:20]}",
            )
        except Exception as exc:
            with connect_database(self.db_path) as conn:
                conn.execute(
                    """UPDATE analytics_browser_collectors SET status='error', last_seen_at=?, last_sync_at=?,
                       last_error_code='validation_failed', last_error_at=?,
                       consecutive_failures=consecutive_failures+1, updated_at=? WHERE provider=?""",
                    (_iso(now), _iso(now), _iso(now), _iso(now), provider),
                )
                conn.commit()
            if isinstance(exc, AnalyticsConnectorError):
                raise
            raise AnalyticsConnectorError("The provider export could not be validated safely.") from exc
        with connect_database(self.db_path) as conn:
            conn.execute(
                """UPDATE analytics_browser_collectors SET status='connected', last_seen_at=?, last_sync_at=?,
                   last_success_at=?, last_error_code='', last_error_at=NULL,
                   consecutive_failures=0, updated_at=? WHERE provider=?""",
                (_iso(now), _iso(now), _iso(now), _iso(now), provider),
            )
            self._audit(
                conn, "analytics_local_sync_completed", "local-analytics-collector",
                "Validated local browser analytics export synchronized",
                {"provider": provider, "source_reference": source_reference,
                 "submitted": int(result.get("submitted") or 0),
                 "inserted": int(result.get("inserted") or 0),
                 "duplicates": int(result.get("duplicates") or 0)},
            )
            conn.commit()
        return {"provider": provider, "status": "completed", **result}

    def report_local_collector_status(
        self, *, provider: str, token: str, status: str, error_code: str = ""
    ) -> dict[str, Any]:
        provider = self._local_provider(provider)
        expected = self._config()["collector_token"]
        if len(expected) < 32 or not secrets.compare_digest(str(token or ""), expected):
            raise AnalyticsConnectorError("The local analytics collector credential is invalid.")
        normalized_status = str(status or "").strip().casefold()
        if normalized_status not in {"waiting", "connected", "error", "reauth_required"}:
            raise AnalyticsConnectorError("The local collector reported an unsupported status.")
        safe_error = re.sub(r"[^a-z0-9_]+", "_", str(error_code or "").casefold()).strip("_")[:80]
        now = _iso(_now())
        with connect_database(self.db_path) as conn:
            row = conn.execute(
                "SELECT enabled FROM analytics_browser_collectors WHERE provider=?", (provider,)
            ).fetchone()
            if not row or not bool(row[0]):
                raise AnalyticsConnectorError("This local analytics collector is disabled in Podcast Reach.")
            failed = normalized_status in {"error", "reauth_required"}
            conn.execute(
                """UPDATE analytics_browser_collectors SET status=?, last_seen_at=?,
                   last_error_code=?, last_error_at=?,
                   consecutive_failures=CASE WHEN ? THEN consecutive_failures+1 ELSE 0 END,
                   updated_at=? WHERE provider=?""",
                (normalized_status, now, safe_error if failed else "", now if failed else None,
                 int(failed), now, provider),
            )
            conn.commit()
        return {"provider": provider, "status": normalized_status, "error_code": safe_error if failed else ""}

    def begin_google(self, *, actor: str, origin: str) -> dict[str, str]:
        config = self._config()
        if not (config["client_id"] and config["client_secret"] and len(config["token_key"]) >= 32):
            raise AnalyticsConnectorError("Google analytics OAuth is not configured in production.")
        state = secrets.token_urlsafe(32)
        code_verifier = secrets.token_urlsafe(64)
        code_challenge = base64.urlsafe_b64encode(hashlib.sha256(code_verifier.encode()).digest()).decode().rstrip("=")
        state_hash = hashlib.sha256(state.encode()).hexdigest()
        now = _now()
        with connect_database(self.db_path) as conn:
            conn.execute("DELETE FROM analytics_oauth_states WHERE expires_at < ? OR consumed_at IS NOT NULL", (_iso(now),))
            conn.execute(
                """INSERT INTO analytics_oauth_states
                   (state_hash, actor, code_verifier_ciphertext, expires_at, created_at) VALUES (?, ?, ?, ?, ?)""",
                (state_hash, actor, self._cipher().encrypt(code_verifier.encode()).decode(),
                 _iso(now + timedelta(minutes=10)), _iso(now)),
            )
            conn.commit()
        params = {
            "client_id": config["client_id"],
            "redirect_uri": self._redirect_uri(origin),
            "response_type": "code",
            "scope": " ".join(GOOGLE_SCOPES),
            "access_type": "offline",
            "prompt": "consent",
            "include_granted_scopes": "true",
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        }
        return {"authorization_url": "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(params)}

    def complete_google(self, *, state: str, code: str, origin: str) -> dict[str, Any]:
        if not state or not code:
            raise AnalyticsConnectorError("Google authorization was not completed.")
        state_hash = hashlib.sha256(state.encode()).hexdigest()
        now = _now()
        with connect_database(self.db_path) as conn:
            conn.row_factory = __import__("sqlite3").Row
            row = conn.execute(
                "SELECT actor, code_verifier_ciphertext, expires_at, consumed_at FROM analytics_oauth_states WHERE state_hash = ?",
                (state_hash,),
            ).fetchone()
            if not row or row["consumed_at"] or str(row["expires_at"]) < _iso(now):
                raise AnalyticsConnectorError("Google authorization state is invalid or expired.")
            changed = conn.execute(
                "UPDATE analytics_oauth_states SET consumed_at = ? WHERE state_hash = ? AND consumed_at IS NULL",
                (_iso(now), state_hash),
            ).rowcount
            conn.commit()
        if changed != 1:
            raise AnalyticsConnectorError("Google authorization state was already used.")
        try:
            code_verifier = self._cipher().decrypt(str(row["code_verifier_ciphertext"]).encode()).decode()
        except InvalidToken as exc:
            raise AnalyticsConnectorError("Google authorization state could not be verified.") from exc
        token = self._post_form(
            "https://oauth2.googleapis.com/token",
            {
                "code": code,
                "client_id": self._config()["client_id"],
                "client_secret": self._config()["client_secret"],
                "redirect_uri": self._redirect_uri(origin),
                "grant_type": "authorization_code",
                "code_verifier": code_verifier,
            },
        )
        refresh_token = str(token.get("refresh_token") or "")
        if not refresh_token:
            raise AnalyticsConnectorError("Google did not issue durable offline access. Reconnect and grant consent.")
        access_token = str(token.get("access_token") or "")
        profile = self._get_json("https://openidconnect.googleapis.com/v1/userinfo", access_token)
        channel_payload = self._get_json(
            "https://www.googleapis.com/youtube/v3/channels?" + urlencode({
                "part": "id,snippet,statistics", "mine": "true", "maxResults": 50,
            }),
            access_token,
        )
        channel_items = channel_payload.get("items") or []
        if not channel_items:
            raise AnalyticsConnectorError("This Google account does not expose an owned YouTube channel.")
        channel = channel_items[0]
        channel_id = str(channel.get("id") or "").strip()
        snippet = channel.get("snippet") or {}
        if not channel_id:
            raise AnalyticsConnectorError("Google did not return a stable YouTube channel id.")
        thumbnails = snippet.get("thumbnails") or {}
        thumbnail = str((thumbnails.get("default") or thumbnails.get("medium") or {}).get("url") or "")
        cipher = self._cipher().encrypt(refresh_token.encode()).decode()
        scopes = sorted(set(str(token.get("scope") or "").split()))
        with connect_database(self.db_path) as conn:
            existing = conn.execute(
                "SELECT id, sync_ga4 FROM analytics_oauth_connections WHERE provider='google' AND youtube_channel_id=?",
                (channel_id,),
            ).fetchone()
            has_primary = bool(conn.execute(
                "SELECT 1 FROM analytics_oauth_connections WHERE provider='google' AND sync_ga4=1 LIMIT 1"
            ).fetchone())
            sync_ga4 = int(existing[1]) if existing else (0 if has_primary else 1)
            conn.execute(
                """INSERT INTO analytics_oauth_connections
                   (provider, account_subject, account_email, youtube_channel_id, youtube_channel_title,
                    youtube_channel_thumbnail, sync_ga4, refresh_token_ciphertext, scopes_json,
                    status, connected_at, consecutive_failures, updated_at)
                   VALUES ('google', ?, ?, ?, ?, ?, ?, ?, ?, 'connected', ?, 0, ?)
                   ON CONFLICT(provider, youtube_channel_id) DO UPDATE SET
                     account_subject=excluded.account_subject, account_email=excluded.account_email,
                     youtube_channel_title=excluded.youtube_channel_title,
                     youtube_channel_thumbnail=excluded.youtube_channel_thumbnail,
                     refresh_token_ciphertext=excluded.refresh_token_ciphertext, scopes_json=excluded.scopes_json,
                     status='connected', connected_at=excluded.connected_at, last_error_code='',
                     last_error_at=NULL, next_retry_at=NULL, consecutive_failures=0, revoked_at=NULL,
                     updated_at=excluded.updated_at""",
                (str(profile.get("sub") or ""), str(profile.get("email") or ""), channel_id,
                 str(snippet.get("title") or channel_id), thumbnail, sync_ga4, cipher,
                 json.dumps(scopes), _iso(now), _iso(now)),
            )
            connection_id = int(conn.execute(
                "SELECT id FROM analytics_oauth_connections WHERE provider='google' AND youtube_channel_id=?",
                (channel_id,),
            ).fetchone()[0])
            self._audit(conn, "analytics_oauth_connected", str(row["actor"]), "Read-only Google analytics access granted",
                        {"provider": "google", "connection_id": connection_id, "account_email": str(profile.get("email") or ""),
                         "youtube_channel_id": channel_id, "youtube_channel_title": str(snippet.get("title") or channel_id),
                         "scopes": scopes})
            conn.commit()
        return {"status": "connected", "connection_id": connection_id,
                "account_email": str(profile.get("email") or ""), "youtube_channel_id": channel_id,
                "youtube_channel_title": str(snippet.get("title") or channel_id)}

    def sync_google(self, *, actor: str, force: bool = False, connection_id: int | None = None) -> dict[str, Any]:
        with connect_database(self.db_path) as conn:
            conn.row_factory = __import__("sqlite3").Row
            if connection_id is None:
                rows = conn.execute(
                    "SELECT * FROM analytics_oauth_connections WHERE provider='google' AND status != 'disconnected' ORDER BY id"
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM analytics_oauth_connections WHERE provider='google' AND id=?", (connection_id,)
                ).fetchall()
        if not rows:
            return {"status": "not_connected", "inserted": 0}
        results = [self._sync_google_connection(row, actor=actor, force=force) for row in rows]
        return {
            "status": "completed" if all(item["status"] in {"completed", "fresh", "retry_scheduled"} for item in results) else "partial",
            "connections": results,
            "inserted": sum(int(item.get("inserted") or 0) for item in results),
            "duplicates": sum(int(item.get("duplicates") or 0) for item in results),
            "observations": sum(int(item.get("observations") or 0) for item in results),
        }

    def _sync_google_connection(self, row: Any, *, actor: str, force: bool) -> dict[str, Any]:
        connection_id = int(row["id"])
        if row["status"] == "revoked":
            return {"status": "reconnect_required", "connection_id": connection_id, "inserted": 0}
        now = _now()
        if not force:
            if row["last_success_at"] and now - datetime.fromisoformat(str(row["last_success_at"]).replace("Z", "+00:00")) < timedelta(hours=20):
                return {"status": "fresh", "connection_id": connection_id, "inserted": 0}
            if row["next_retry_at"] and str(row["next_retry_at"]) > _iso(now):
                return {"status": "retry_scheduled", "connection_id": connection_id, "inserted": 0}
        try:
            refresh = self._cipher().decrypt(str(row["refresh_token_ciphertext"]).encode()).decode()
        except (InvalidToken, AnalyticsConnectorError) as exc:
            self._record_failure(connection_id, "credential_decryption_failed", revoked=True)
            raise AnalyticsConnectorError("Stored Google authorization cannot be decrypted; reconnect the account.") from exc
        try:
            access = self._refresh_access_token(refresh)
            channel_id = str(row["youtube_channel_id"] or "")
            channel_title = str(row["youtube_channel_title"] or "")
            if not channel_id:
                identity = self._youtube_channel_identity(access)
                channel_id, channel_title = identity["id"], identity["title"]
                with connect_database(self.db_path) as conn:
                    conflict = conn.execute(
                        "SELECT id FROM analytics_oauth_connections WHERE provider='google' AND youtube_channel_id=? AND id!=?",
                        (channel_id, connection_id),
                    ).fetchone()
                    if conflict:
                        raise AnalyticsConnectorError("This YouTube channel is already connected; disconnect the legacy duplicate.")
                    conn.execute(
                        """UPDATE analytics_oauth_connections
                           SET youtube_channel_id=?, youtube_channel_title=?, youtube_channel_thumbnail=?, updated_at=?
                           WHERE id=?""",
                        (channel_id, channel_title, identity["thumbnail"], _iso(now), connection_id),
                    )
                    conn.commit()
            observations = self._collect_google(
                access, channel_id=channel_id, channel_title=channel_title, sync_ga4=bool(row["sync_ga4"]),
            )
            result = self.growth.record_observations(
                observations, actor=actor, correlation_id=f"google-sync-{connection_id}-{now.date().isoformat()}"
            ) if observations else {"inserted": 0, "duplicates": 0}
        except AnalyticsConnectorError as exc:
            code = "authorization_revoked" if "authorization" in str(exc).lower() else "provider_sync_failed"
            self._record_failure(connection_id, code, revoked=code == "authorization_revoked")
            raise
        except Exception as exc:
            self._record_failure(connection_id, "provider_sync_failed", revoked=False)
            raise AnalyticsConnectorError("A configured Google analytics source could not be synchronized.") from exc
        with connect_database(self.db_path) as conn:
            conn.execute(
                """UPDATE analytics_oauth_connections SET status='connected', last_sync_at=?, last_success_at=?,
                   last_error_code='', last_error_at=NULL, next_retry_at=NULL, consecutive_failures=0, updated_at=?
                   WHERE provider='google' AND id=?""",
                (_iso(now), _iso(now), _iso(now), connection_id),
            )
            self._audit(conn, "analytics_sync_completed", actor, "Scheduled private analytics synchronization",
                        {"provider": "google", "connection_id": connection_id,
                         "youtube_channel_id": str(row["youtube_channel_id"] or ""), "observation_count": len(observations),
                         "inserted": int(result.get("inserted") or 0), "duplicates": int(result.get("duplicates") or 0)})
            conn.commit()
        return {"status": "completed", "connection_id": connection_id, **result, "observations": len(observations)}

    def _youtube_channel_identity(self, access_token: str) -> dict[str, str]:
        payload = self._get_json(
            "https://www.googleapis.com/youtube/v3/channels?" + urlencode({
                "part": "id,snippet", "mine": "true", "maxResults": 50,
            }),
            access_token,
        )
        items = payload.get("items") or []
        if not items or not str(items[0].get("id") or "").strip():
            raise AnalyticsConnectorError("This Google account does not expose an owned YouTube channel.")
        snippet = items[0].get("snippet") or {}
        thumbnails = snippet.get("thumbnails") or {}
        return {
            "id": str(items[0]["id"]),
            "title": str(snippet.get("title") or items[0]["id"]),
            "thumbnail": str((thumbnails.get("default") or thumbnails.get("medium") or {}).get("url") or ""),
        }

    def disconnect_google(self, *, actor: str = "admin", connection_id: int | None = None) -> dict[str, Any]:
        with connect_database(self.db_path) as conn:
            rows = conn.execute(
                "SELECT id, refresh_token_ciphertext FROM analytics_oauth_connections WHERE provider='google'"
                + (" AND id=?" if connection_id is not None else ""),
                (connection_id,) if connection_id is not None else (),
            ).fetchall()
        if connection_id is None and len(rows) > 1:
            raise AnalyticsConnectorError("Choose the specific Google channel to disconnect.")
        row = rows[0] if rows else None
        if row and row[1]:
            try:
                refresh = self._cipher().decrypt(str(row[1]).encode()).decode()
                self._post_form("https://oauth2.googleapis.com/revoke", {"token": refresh}, expect_json=False)
            except Exception:
                pass  # Local revocation must still remove retained authorization.
        now = _iso(_now())
        with connect_database(self.db_path) as conn:
            conn.execute(
                """UPDATE analytics_oauth_connections SET refresh_token_ciphertext='', status='disconnected',
                   revoked_at=?, next_retry_at=NULL, updated_at=? WHERE provider='google' AND id=?""",
                (now, now, int(row[0]) if row else -1),
            )
            self._audit(conn, "analytics_oauth_disconnected", actor, "Retained Google refresh token deleted",
                        {"provider": "google", "status": "disconnected"})
            conn.commit()
        return {"status": "disconnected", "connection_id": int(row[0]) if row else connection_id}

    def _collect_google(self, access_token: str, *, channel_id: str = "", channel_title: str = "",
                        sync_ga4: bool = True) -> list[dict[str, Any]]:
        end = date.today() - timedelta(days=3)
        start = end - timedelta(days=27)
        common = {"period_start": start.isoformat(), "period_end": end.isoformat(), "traffic_scope": "all"}
        rows: list[dict[str, Any]] = []
        channel_selector = f"channel=={channel_id}" if channel_id else "channel==MINE"
        youtube_provider = f"youtube:{channel_id}" if channel_id else "youtube"
        youtube_reference = f"youtube-analytics-api:{channel_id or 'mine'}"
        yt = self._get_json("https://youtubeanalytics.googleapis.com/v2/reports?" + urlencode({
            "ids": channel_selector, "startDate": start.isoformat(), "endDate": end.isoformat(),
            "metrics": "views,estimatedMinutesWatched,averageViewDuration",
        }), access_token)
        values = (yt.get("rows") or [[0, 0, 0]])[0]
        for metric, value in (("plays", values[0]), ("watch_time_hours", float(values[1]) / 60),
                              ("average_view_duration_seconds", values[2])):
            rows.append({**common, "provider": youtube_provider, "metric_name": metric, "metric_value": value,
                         "source_reference": youtube_reference})
        channel = self._get_json(
            "https://www.googleapis.com/youtube/v3/channels?" + urlencode(
                {"part": "statistics", "id": channel_id} if channel_id else {"part": "statistics", "mine": "true"}
            ),
            access_token,
        )
        channel_items = channel.get("items") or []
        if channel_items:
            subscriber_count = (channel_items[0].get("statistics") or {}).get("subscriberCount")
            if subscriber_count is not None:
                today = date.today().isoformat()
                rows.append({"provider": youtube_provider, "metric_name": "subscribers", "metric_value": subscriber_count,
                             "period_start": today, "period_end": today, "traffic_scope": "all",
                             "source_reference": f"youtube-data-api:{channel_id or 'mine'}"})
        rows.extend(self._youtube_dimension(access_token, start, end, "deviceType", "device",
                                            channel_selector, youtube_provider, youtube_reference))
        rows.extend(self._youtube_dimension(access_token, start, end, "country", "country",
                                            channel_selector, youtube_provider, youtube_reference))

        property_id = self._config()["ga4_property_id"]
        if property_id and sync_ga4:
            ga = self._ga4_report(access_token, property_id, start, end, [], ["activeUsers"])
            active = ((ga.get("rows") or [{}])[0].get("metricValues") or [{"value": 0}])[0]["value"]
            rows.append({**common, "provider": "website", "metric_name": "organic_reach", "metric_value": active,
                         "traffic_scope": "organic", "source_reference": "ga4-data-api"})
            rows.extend(self._ga4_dimensions(access_token, property_id, start, end, "deviceCategory", "device"))
            rows.extend(self._ga4_dimensions(access_token, property_id, start, end, "country", "country"))
        return rows

    def _youtube_dimension(self, token: str, start: date, end: date, dimension: str, prefix: str,
                           channel_selector: str = "channel==MINE", provider: str = "youtube",
                           source_reference: str = "youtube-analytics-api") -> list[dict[str, Any]]:
        data = self._get_json("https://youtubeanalytics.googleapis.com/v2/reports?" + urlencode({
            "ids": channel_selector, "startDate": start.isoformat(), "endDate": end.isoformat(),
            "metrics": "views", "dimensions": dimension, "sort": "-views", "maxResults": 50,
        }), token)
        return [{"provider": provider, "metric_name": f"{prefix}_{self._slug(item[0])}", "metric_value": item[1],
                 "period_start": start.isoformat(), "period_end": end.isoformat(), "traffic_scope": "all",
                 "source_reference": source_reference} for item in data.get("rows") or []]

    def _ga4_report(self, token: str, property_id: str, start: date, end: date,
                    dimensions: list[str], metrics: list[str]) -> dict[str, Any]:
        body = json.dumps({"dateRanges": [{"startDate": start.isoformat(), "endDate": end.isoformat()}],
                           "dimensions": [{"name": item} for item in dimensions],
                           "metrics": [{"name": item} for item in metrics], "limit": "100"}).encode()
        return self._request_json(f"https://analyticsdata.googleapis.com/v1beta/properties/{property_id}:runReport",
                                  token, data=body)

    def _ga4_dimensions(self, token: str, property_id: str, start: date, end: date,
                        dimension: str, prefix: str) -> list[dict[str, Any]]:
        data = self._ga4_report(token, property_id, start, end, [dimension], ["activeUsers"])
        rows = []
        for item in data.get("rows") or []:
            label = ((item.get("dimensionValues") or [{}])[0].get("value") or "other")
            value = ((item.get("metricValues") or [{}])[0].get("value") or 0)
            rows.append({"provider": "website", "metric_name": f"{prefix}_{self._slug(label)}", "metric_value": value,
                         "period_start": start.isoformat(), "period_end": end.isoformat(), "traffic_scope": "all",
                         "source_reference": "ga4-data-api"})
        return rows

    @staticmethod
    def _slug(value: Any) -> str:
        return re.sub(r"[^a-z0-9]+", "_", str(value).casefold()).strip("_")[:64] or "other"

    def _refresh_access_token(self, refresh_token: str) -> str:
        try:
            payload = self._post_form("https://oauth2.googleapis.com/token", {
                "client_id": self._config()["client_id"], "client_secret": self._config()["client_secret"],
                "refresh_token": refresh_token, "grant_type": "refresh_token",
            })
        except AnalyticsConnectorError as exc:
            raise AnalyticsConnectorError("Google authorization was revoked or expired; reconnect the account.") from exc
        token = str(payload.get("access_token") or "")
        if not token:
            raise AnalyticsConnectorError("Google authorization did not return an access token.")
        return token

    def _record_failure(self, connection_id: int, code: str, *, revoked: bool) -> None:
        now = _now()
        with connect_database(self.db_path) as conn:
            row = conn.execute(
                "SELECT consecutive_failures FROM analytics_oauth_connections WHERE provider='google' AND id=?",
                (connection_id,),
            ).fetchone()
            failures = int(row[0] if row else 0) + 1
            delay = min(24 * 60, 5 * (2 ** min(failures - 1, 8)))
            conn.execute(
                """UPDATE analytics_oauth_connections SET status=?, last_sync_at=?, last_error_code=?,
                   last_error_at=?, next_retry_at=?, consecutive_failures=?, updated_at=? WHERE provider='google' AND id=?""",
                ("revoked" if revoked else "error", _iso(now), code, _iso(now),
                 None if revoked else _iso(now + timedelta(minutes=delay)), failures, _iso(now), connection_id),
            )
            conn.commit()

    @staticmethod
    def _audit(conn: Any, event_type: str, actor: str, reason: str, after: dict[str, Any]) -> None:
        conn.execute(
            """INSERT INTO audit_events
               (entity_type, entity_id, event_type, actor, source, reason, correlation_id, after_json)
               VALUES ('analytics_connector', 'google', ?, ?, 'podcast_analytics_connectors', ?, ?, ?)""",
            (event_type, actor, reason, secrets.token_hex(16), json.dumps(after, sort_keys=True)),
        )

    @staticmethod
    def _post_form(url: str, values: dict[str, str], *, expect_json: bool = True) -> dict[str, Any]:
        request = Request(url, data=urlencode(values).encode(), headers={"Content-Type": "application/x-www-form-urlencoded"})
        try:
            with urlopen(request, timeout=20) as response:  # noqa: S310 - fixed Google endpoints
                body = response.read(256_000)
        except (HTTPError, URLError, TimeoutError) as exc:
            raise AnalyticsConnectorError("The Google authorization service rejected or could not complete the request.") from exc
        return json.loads(body) if expect_json and body else {}

    @staticmethod
    def _get_json(url: str, token: str) -> dict[str, Any]:
        return PodcastAnalyticsConnectors._request_json(url, token)

    @staticmethod
    def _request_json(url: str, token: str, *, data: bytes | None = None) -> dict[str, Any]:
        request = Request(url, data=data, headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
        try:
            with urlopen(request, timeout=25) as response:  # noqa: S310 - fixed Google API endpoints
                return json.loads(response.read(1_000_000))
        except HTTPError as exc:
            if exc.code == 401:
                raise AnalyticsConnectorError("Google authorization was revoked or expired; reconnect the account.") from exc
            raise AnalyticsConnectorError("A configured Google analytics source could not be synchronized.") from exc
        except (URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise AnalyticsConnectorError("A configured Google analytics source could not be synchronized.") from exc
