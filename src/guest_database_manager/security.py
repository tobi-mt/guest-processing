"""Authentication session, CSRF, role, and login-throttling primitives."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from dataclasses import dataclass, field
from threading import Lock
from typing import Any


ROLE_RANK = {"viewer": 10, "operator": 20, "admin": 30}


class SessionError(ValueError):
    pass


def role_allows(actual: str, required: str) -> bool:
    return ROLE_RANK.get(str(actual).lower(), 0) >= ROLE_RANK.get(str(required).lower(), 999)


class SessionSigner:
    """Issue and verify expiring HMAC-signed dashboard sessions."""

    def __init__(self, secret: str, *, ttl_seconds: int = 8 * 60 * 60):
        if not secret:
            raise ValueError("Session signing secret is required")
        self._secret = secret.encode("utf-8")
        self.ttl_seconds = max(60, int(ttl_seconds))

    def issue(
        self, *, role: str = "admin", subject: str = "dashboard", now: int | None = None
    ) -> tuple[str, dict[str, Any]]:
        normalized_role = str(role).strip().lower()
        if normalized_role not in ROLE_RANK:
            raise ValueError(f"Unsupported role: {role}")
        issued_at = int(time.time() if now is None else now)
        claims = {
            "iat": issued_at,
            "exp": issued_at + self.ttl_seconds,
            "role": normalized_role,
            "sub": str(subject or "dashboard"),
            "csrf": secrets.token_urlsafe(24),
            "sid": secrets.token_urlsafe(18),
        }
        payload = json.dumps(claims, separators=(",", ":"), sort_keys=True).encode("utf-8")
        encoded = base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")
        signature = hmac.new(self._secret, encoded.encode("ascii"), hashlib.sha256).hexdigest()
        return f"{encoded}.{signature}", claims

    def verify(self, token: str, *, now: int | None = None) -> dict[str, Any]:
        try:
            encoded, provided_signature = str(token).split(".", 1)
        except ValueError as exc:
            raise SessionError("Malformed session") from exc
        expected_signature = hmac.new(self._secret, encoded.encode("ascii"), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(provided_signature, expected_signature):
            raise SessionError("Invalid session signature")
        try:
            padding = "=" * (-len(encoded) % 4)
            claims = json.loads(base64.urlsafe_b64decode(encoded + padding))
        except Exception as exc:
            raise SessionError("Invalid session payload") from exc
        current_time = int(time.time() if now is None else now)
        if int(claims.get("exp") or 0) <= current_time:
            raise SessionError("Session expired")
        if claims.get("role") not in ROLE_RANK or not claims.get("csrf") or not claims.get("sid"):
            raise SessionError("Incomplete session")
        return claims


@dataclass
class LoginRateLimiter:
    """In-memory per-client failed-login limiter for the single-process service."""

    max_failures: int = 5
    window_seconds: int = 5 * 60
    lock_seconds: int = 15 * 60
    _failures: dict[str, list[float]] = field(default_factory=dict, init=False, repr=False)
    _locked_until: dict[str, float] = field(default_factory=dict, init=False, repr=False)
    _lock: Lock = field(default_factory=Lock, init=False, repr=False)

    def is_allowed(self, client: str, *, now: float | None = None) -> bool:
        timestamp = time.time() if now is None else float(now)
        with self._lock:
            return self._locked_until.get(client, 0) <= timestamp

    def record_failure(self, client: str, *, now: float | None = None) -> None:
        timestamp = time.time() if now is None else float(now)
        with self._lock:
            recent = [item for item in self._failures.get(client, []) if item > timestamp - self.window_seconds]
            recent.append(timestamp)
            self._failures[client] = recent
            if len(recent) >= self.max_failures:
                self._locked_until[client] = timestamp + self.lock_seconds

    def record_success(self, client: str) -> None:
        with self._lock:
            self._failures.pop(client, None)
            self._locked_until.pop(client, None)
