"""Persisted dashboard accounts, password verification, and account recovery."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import secrets
import sqlite3
import struct
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from cryptography.fernet import Fernet, InvalidToken

from guest_database_manager.db_connection import connect_database


ROLES = {"viewer", "operator", "admin", "super_admin"}
PBKDF2_ITERATIONS = 600_000
COMMON_PASSWORDS = {
    "password123", "password1234", "qwerty123456", "letmein123456", "welcome123456",
    "admin123456", "changeme1234", "mirror talk 1",
}


class AccountError(ValueError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def validate_password(password: str) -> None:
    if len(password) < 12 or len(password) > 256:
        raise AccountError("Password must be between 12 and 256 characters.")
    if not re.search(r"[A-Za-z]", password) or not re.search(r"\d", password):
        raise AccountError("Password must contain at least one letter and one number.")
    if password.casefold() in COMMON_PASSWORDS:
        raise AccountError("Choose a less common password.")


def validate_password_for_account(password: str, *, username: str, email: str | None = None) -> None:
    validate_password(password)
    lowered = password.casefold()
    identifiers = {username.casefold(), (email or "").split("@", 1)[0].casefold()}
    if any(len(value) >= 3 and value in lowered for value in identifiers):
        raise AccountError("Password must not contain your username or email name.")


def hash_password(password: str, *, enforce_policy: bool = True) -> str:
    if enforce_policy:
        validate_password(password)
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return "pbkdf2_sha256${}${}${}".format(
        PBKDF2_ITERATIONS,
        base64.urlsafe_b64encode(salt).decode("ascii").rstrip("="),
        base64.urlsafe_b64encode(digest).decode("ascii").rstrip("="),
    )


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, iterations, salt_text, digest_text = encoded.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        salt = base64.urlsafe_b64decode(salt_text + "=" * (-len(salt_text) % 4))
        expected = base64.urlsafe_b64decode(digest_text + "=" * (-len(digest_text) % 4))
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, int(iterations))
        return hmac.compare_digest(actual, expected)
    except (TypeError, ValueError):
        return False


class AccountStore:
    def __init__(self, db_path: Path | str, *, encryption_secret: str = ""):
        self.db_path = Path(db_path)
        material = (encryption_secret or f"development-only:{self.db_path.resolve()}").encode("utf-8")
        self._cipher = Fernet(base64.urlsafe_b64encode(hashlib.sha256(b"dashboard-mfa:" + material).digest()))

    def _connect(self):
        conn = connect_database(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    @staticmethod
    def _public(row: Any) -> dict[str, Any]:
        return {key: row[key] for key in (
            "id", "username", "email", "display_name", "role", "is_active",
            "must_set_password", "auth_version", "created_at", "created_by", "updated_at", "updated_by",
            "last_login_at", "password_changed_at", "mfa_enabled",
        )}

    @staticmethod
    def _record_event(conn: Any, account_id: int, event_type: str, actor: str, detail: dict[str, Any] | None = None) -> None:
        conn.execute(
            """INSERT INTO dashboard_account_events
               (account_id, event_type, actor, correlation_id, detail_json, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (account_id, event_type, actor, str(uuid4()), json.dumps(detail or {}, sort_keys=True), _now()),
        )

    def bootstrap(self, username: str, password: str, *, role: str) -> None:
        if not username or not password:
            return
        with self._connect() as conn:
            existing = conn.execute(
                "SELECT id, role FROM dashboard_accounts WHERE username = ? COLLATE NOCASE", (username,)
            ).fetchone()
            if existing:
                if username.casefold() == "mt_admin" and existing["role"] != "super_admin":
                    conn.execute(
                        "UPDATE dashboard_accounts SET role='super_admin', auth_version=auth_version+1, updated_at=?, updated_by='system-bootstrap' WHERE id=?",
                        (_now(), existing["id"]),
                    )
                    self._record_event(conn, int(existing["id"]), "role_promoted", "system-bootstrap", {"role": "super_admin"})
                return
            now = _now()
            effective_role = "super_admin" if username.casefold() == "mt_admin" else role
            conn.execute(
                """INSERT INTO dashboard_accounts
                   (username, role, password_hash, created_at, created_by, updated_at, updated_by)
                   VALUES (?, ?, ?, ?, 'system-bootstrap', ?, 'system-bootstrap')""",
                (username, effective_role, hash_password(password, enforce_policy=False), now, now),
            )
            account_id = conn.execute("SELECT id FROM dashboard_accounts WHERE username=? COLLATE NOCASE", (username,)).fetchone()[0]
            self._record_event(conn, account_id, "account_bootstrapped", "system-bootstrap", {"role": effective_role})

    @staticmethod
    def _totp(secret: str, counter: int) -> str:
        key = base64.b32decode(secret + "=" * (-len(secret) % 8), casefold=True)
        digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
        offset = digest[-1] & 0x0F
        value = (struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF) % 1_000_000
        return f"{value:06d}"

    def _encrypt(self, value: str) -> str:
        return self._cipher.encrypt(value.encode("ascii")).decode("ascii")

    def _decrypt(self, value: str) -> str:
        try:
            return self._cipher.decrypt(value.encode("ascii")).decode("ascii")
        except (InvalidToken, ValueError) as exc:
            raise AccountError("MFA configuration cannot be decrypted. Check the session secret configuration.") from exc

    def _matching_totp_counter(self, secret: str, code: str, *, now: int | None = None) -> int | None:
        if not re.fullmatch(r"\d{6}", code):
            return None
        current = int(time.time() if now is None else now) // 30
        for counter in (current - 1, current, current + 1):
            if secrets.compare_digest(self._totp(secret, counter), code):
                return counter
        return None

    def authenticate(self, username: str, password: str, *, otp: str = "") -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM dashboard_accounts WHERE username = ? COLLATE NOCASE AND is_active = 1 AND must_set_password = 0", (username,)
            ).fetchone()
            if not row or not verify_password(password, row["password_hash"]):
                return None
            if row["mfa_enabled"]:
                if not otp:
                    result = self._public(row)
                    result["mfa_required"] = True
                    return result
                counter = self._matching_totp_counter(self._decrypt(row["mfa_secret_ciphertext"]), otp)
                if counter is None or (row["mfa_last_counter"] is not None and counter <= int(row["mfa_last_counter"])):
                    return None
                conn.execute("UPDATE dashboard_accounts SET mfa_last_counter=? WHERE id=?", (counter, row["id"]))
            conn.execute("UPDATE dashboard_accounts SET last_login_at=? WHERE id=?", (_now(), row["id"]))
            return self._public(row)

    def has_accounts(self) -> bool:
        with self._connect() as conn:
            return bool(conn.execute("SELECT 1 FROM dashboard_accounts LIMIT 1").fetchone())

    def session_account(self, account_id: int) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM dashboard_accounts WHERE id=? AND is_active=1", (account_id,)).fetchone()
            return self._public(row) if row else None

    def list_accounts(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM dashboard_accounts ORDER BY username COLLATE NOCASE").fetchall()
            return [self._public(row) for row in rows]

    def create(self, payload: dict[str, Any], *, actor: str) -> dict[str, Any]:
        username = str(payload.get("username") or "").strip()
        email = str(payload.get("email") or "").strip() or None
        display_name = str(payload.get("display_name") or "").strip()
        role = str(payload.get("role") or "viewer").strip().lower()
        if not re.fullmatch(r"[A-Za-z0-9._@+-]{3,120}", username):
            raise AccountError("Username must be 3–120 characters and use only letters, numbers, or . _ @ + -.")
        if role not in ROLES:
            raise AccountError("Invalid account role.")
        if email and (email.count("@") != 1 or len(email) > 320):
            raise AccountError("Enter a valid email address.")
        encoded = hash_password(secrets.token_urlsafe(48), enforce_policy=False)
        now = _now()
        try:
            with self._connect() as conn:
                cursor = conn.execute(
                    """INSERT INTO dashboard_accounts
                       (username, email, display_name, role, password_hash, must_set_password,
                        created_at, created_by, updated_at, updated_by)
                       VALUES (?, ?, ?, ?, ?, 1, ?, ?, ?, ?)""",
                    (username, email, display_name, role, encoded, now, actor, now, actor),
                )
                row = conn.execute("SELECT * FROM dashboard_accounts WHERE id=?", (cursor.lastrowid,)).fetchone()
                self._record_event(conn, int(cursor.lastrowid), "account_created", actor, {"role": role})
                return self._public(row)
        except Exception as exc:
            if "UNIQUE constraint" in str(exc):
                raise AccountError("That username or email is already in use.") from exc
            raise

    def update(self, account_id: int, payload: dict[str, Any], *, actor: str, actor_id: int) -> dict[str, Any]:
        with self._connect() as conn:
            current = conn.execute("SELECT * FROM dashboard_accounts WHERE id=?", (account_id,)).fetchone()
            if not current:
                raise AccountError("Account not found.")
            role = str(payload.get("role", current["role"])).strip().lower()
            active = 1 if bool(payload.get("is_active", current["is_active"])) else 0
            display_name = str(payload.get("display_name", current["display_name"]) or "").strip()
            email = str(payload.get("email", current["email"]) or "").strip() or None
            if role not in ROLES:
                raise AccountError("Invalid account role.")
            if account_id == actor_id and (not active or role != "super_admin"):
                raise AccountError("You cannot deactivate or remove super-admin access from your own account.")
            if current["role"] == "super_admin" and (not active or role != "super_admin"):
                remaining = conn.execute(
                    "SELECT COUNT(*) FROM dashboard_accounts WHERE role='super_admin' AND is_active=1 AND id<>?", (account_id,)
                ).fetchone()[0]
                if not remaining:
                    raise AccountError("At least one active super administrator is required.")
            changed_security = role != current["role"] or active != current["is_active"]
            conn.execute(
                """UPDATE dashboard_accounts SET email=?, display_name=?, role=?, is_active=?,
                   auth_version=auth_version+?, updated_at=?, updated_by=? WHERE id=?""",
                (email, display_name, role, active, int(changed_security), _now(), actor, account_id),
            )
            self._record_event(conn, account_id, "account_updated", actor, {"role": role, "is_active": bool(active)})
            row = conn.execute("SELECT * FROM dashboard_accounts WHERE id=?", (account_id,)).fetchone()
            return self._public(row)

    def create_access_token(
        self, account_id: int, *, actor: str, purpose: str = "recovery", minutes: int = 30
    ) -> str:
        if purpose not in {"invitation", "recovery"}:
            raise AccountError("Invalid account token purpose.")
        token = secrets.token_urlsafe(32)
        digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
        now = datetime.now(timezone.utc)
        with self._connect() as conn:
            account = conn.execute("SELECT id FROM dashboard_accounts WHERE id=? AND is_active=1", (account_id,)).fetchone()
            if not account:
                raise AccountError("Active account not found.")
            conn.execute("UPDATE dashboard_account_recovery_tokens SET used_at=? WHERE account_id=? AND used_at IS NULL", (_now(), account_id))
            conn.execute(
                """INSERT INTO dashboard_account_recovery_tokens
                   (account_id, token_hash, purpose, expires_at, created_at, created_by)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (account_id, digest, purpose, (now + timedelta(minutes=max(5, min(minutes, 60)))).isoformat().replace("+00:00", "Z"), _now(), actor),
            )
            self._record_event(conn, account_id, f"{purpose}_issued", actor, {"expires_in_minutes": max(5, min(minutes, 60))})
        return token

    def create_recovery_token(self, account_id: int, *, actor: str, minutes: int = 30) -> str:
        return self.create_access_token(account_id, actor=actor, purpose="recovery", minutes=minutes)

    def recover(self, token: str, password: str) -> None:
        digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
        now = _now()
        with self._connect() as conn:
            candidate = conn.execute(
                """SELECT t.account_id, a.username, a.email FROM dashboard_account_recovery_tokens t
                   JOIN dashboard_accounts a ON a.id=t.account_id
                   WHERE t.token_hash=? AND t.used_at IS NULL AND t.expires_at>? AND a.is_active=1""",
                (digest, now),
            ).fetchone()
        if not candidate:
            raise AccountError("This account link is invalid or has expired.")
        validate_password_for_account(password, username=candidate["username"], email=candidate["email"])
        encoded = hash_password(password)
        with self._connect() as conn:
            row = conn.execute(
                """SELECT t.id token_id, t.account_id, t.purpose FROM dashboard_account_recovery_tokens t
                   JOIN dashboard_accounts a ON a.id=t.account_id
                   WHERE t.token_hash=? AND t.used_at IS NULL AND t.expires_at>? AND a.is_active=1""",
                (digest, now),
            ).fetchone()
            if not row:
                raise AccountError("This account link is invalid or has expired.")
            conn.execute("UPDATE dashboard_account_recovery_tokens SET used_at=? WHERE id=?", (now, row["token_id"]))
            conn.execute(
                """UPDATE dashboard_accounts SET password_hash=?, must_set_password=0,
                   auth_version=auth_version+1, password_changed_at=?, updated_at=?, updated_by='account-recovery'
                   WHERE id=?""",
                (encoded, now, now, row["account_id"]),
            )
            if row["purpose"] == "recovery":
                conn.execute(
                    """UPDATE dashboard_accounts SET mfa_enabled=0, mfa_secret_ciphertext=NULL,
                       mfa_pending_secret_ciphertext=NULL, mfa_last_counter=NULL WHERE id=?""",
                    (row["account_id"],),
                )
            self._record_event(conn, int(row["account_id"]), f"{row['purpose']}_completed", "account-recovery")

    def change_password(self, account_id: int, current_password: str, new_password: str, *, actor: str) -> None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT password_hash, username, email FROM dashboard_accounts WHERE id=? AND is_active=1", (account_id,)
            ).fetchone()
        if not row or not verify_password(current_password, row["password_hash"]):
            raise AccountError("Current password is incorrect.")
        validate_password_for_account(new_password, username=row["username"], email=row["email"])
        if verify_password(new_password, row["password_hash"]):
            raise AccountError("New password must be different from the current password.")
        encoded = hash_password(new_password)
        now = _now()
        with self._connect() as conn:
            conn.execute(
                """UPDATE dashboard_accounts SET password_hash=?, auth_version=auth_version+1,
                   password_changed_at=?, updated_at=?, updated_by=? WHERE id=?""",
                (encoded, now, now, actor, account_id),
            )
            self._record_event(conn, account_id, "password_changed", actor)

    def invalidate_sessions(self, account_id: int, *, actor: str) -> None:
        with self._connect() as conn:
            if not conn.execute("SELECT 1 FROM dashboard_accounts WHERE id=?", (account_id,)).fetchone():
                raise AccountError("Account not found.")
            conn.execute(
                "UPDATE dashboard_accounts SET auth_version=auth_version+1, updated_at=?, updated_by=? WHERE id=?",
                (_now(), actor, account_id),
            )
            self._record_event(conn, account_id, "sessions_invalidated", actor)

    def begin_mfa(self, account_id: int, *, actor: str) -> dict[str, str]:
        secret = base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")
        with self._connect() as conn:
            row = conn.execute("SELECT username FROM dashboard_accounts WHERE id=? AND is_active=1", (account_id,)).fetchone()
            if not row:
                raise AccountError("Account not found.")
            conn.execute(
                "UPDATE dashboard_accounts SET mfa_pending_secret_ciphertext=?, updated_at=?, updated_by=? WHERE id=?",
                (self._encrypt(secret), _now(), actor, account_id),
            )
            self._record_event(conn, account_id, "mfa_enrollment_started", actor)
        label = row["username"].replace(" ", "%20")
        return {"secret": secret, "otpauth_uri": f"otpauth://totp/Mirror%20Talk:{label}?secret={secret}&issuer=Mirror%20Talk"}

    def confirm_mfa(self, account_id: int, code: str, *, actor: str) -> None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT mfa_pending_secret_ciphertext FROM dashboard_accounts WHERE id=? AND is_active=1", (account_id,)
            ).fetchone()
            if not row or not row["mfa_pending_secret_ciphertext"]:
                raise AccountError("Start MFA enrollment before confirming a code.")
            secret = self._decrypt(row["mfa_pending_secret_ciphertext"])
            counter = self._matching_totp_counter(secret, code)
            if counter is None:
                raise AccountError("The authentication code is invalid.")
            conn.execute(
                """UPDATE dashboard_accounts SET mfa_enabled=1, mfa_secret_ciphertext=mfa_pending_secret_ciphertext,
                   mfa_pending_secret_ciphertext=NULL, mfa_last_counter=NULL, auth_version=auth_version+1,
                   updated_at=?, updated_by=? WHERE id=?""",
                (_now(), actor, account_id),
            )
            self._record_event(conn, account_id, "mfa_enabled", actor)

    def disable_mfa(self, account_id: int, password: str, code: str, *, actor: str) -> None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM dashboard_accounts WHERE id=? AND is_active=1", (account_id,)).fetchone()
            if not row or not row["mfa_enabled"] or not verify_password(password, row["password_hash"]):
                raise AccountError("Password or authentication code is incorrect.")
            counter = self._matching_totp_counter(self._decrypt(row["mfa_secret_ciphertext"]), code)
            if counter is None or (row["mfa_last_counter"] is not None and counter <= int(row["mfa_last_counter"])):
                raise AccountError("Password or authentication code is incorrect.")
            conn.execute(
                """UPDATE dashboard_accounts SET mfa_enabled=0, mfa_secret_ciphertext=NULL,
                   mfa_pending_secret_ciphertext=NULL, mfa_last_counter=NULL, auth_version=auth_version+1,
                   updated_at=?, updated_by=? WHERE id=?""",
                (_now(), actor, account_id),
            )
            self._record_event(conn, account_id, "mfa_disabled", actor)
