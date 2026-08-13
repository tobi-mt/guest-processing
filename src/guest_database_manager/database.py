import logging
import sqlite3
from datetime import datetime, timezone
from json import dumps, loads
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from uuid import uuid4

try:
    from .constants import DEFAULT_DB_PATH
    from .data_mapper import DataMapper
    from .db_connection import connect_database
    from .file_reader import FileReader
    from .lifecycle import validate_state, validate_transition
    from .schema_manager import SchemaManager
except ImportError as exc:
    if "attempted relative import" not in str(exc):
        raise
    from constants import DEFAULT_DB_PATH
    from data_mapper import DataMapper
    from db_connection import connect_database
    from file_reader import FileReader
    from lifecycle import validate_state, validate_transition
    from schema_manager import SchemaManager

logger = logging.getLogger(__name__)
INTAKE_SOURCE_NAME = "Website Intake Questionnaire"


def _normalized_identity(value: Optional[str]) -> str:
    """Normalize names and emails for duplicate matching."""
    if not value:
        return ""
    return str(value).strip().casefold()


def _normalized_episode_identity(value: Optional[str]) -> str:
    """Normalize episode identity fields for duplicate matching."""
    return _normalized_identity(value)


def _episode_row_text(row: Dict[str, Any], key: str) -> str:
    """Return a trimmed text value for an episode row field."""
    return str(row.get(key) or "").strip()


def _episode_title_is_placeholder(row: Dict[str, Any]) -> bool:
    """Treat title-as-guest-name rows as placeholders when choosing a canonical episode."""
    guest_name = _normalized_episode_identity(row.get("guest_name"))
    episode_title = _normalized_episode_identity(row.get("episode_title"))
    return bool(guest_name and episode_title and guest_name == episode_title)


def _episode_status_rank(value: str, *, kind: str) -> int:
    """Rank episode status fields so the most advanced useful state wins."""
    normalized = _normalized_episode_identity(value)
    if kind == "release":
        order = {"released": 3, "scheduled": 2, "unplanned": 1}
    elif kind == "production":
        order = {"released": 5, "ready": 4, "editing": 3, "recorded": 2, "idea": 1}
    else:
        order = {"released": 4, "ready": 3, "needs_assets": 2, "unknown": 1}
    return order.get(normalized, 0)


def _prefer_existing_metadata(existing_value: Optional[str], new_value: Optional[str]) -> Optional[str]:
    """Keep the original source metadata when a guest is updated."""
    if existing_value and str(existing_value).strip():
        return existing_value
    return new_value


def _is_blank_import_value(value: Any) -> bool:
    """Treat None, NaN-like values, and empty strings as blank import cells."""
    if value is None:
        return True
    try:
        if value != value:
            return True
    except Exception:
        pass
    return str(value).strip() == ""


def _normalize_outreach_plan_storage(value: Any) -> str:
    """Store outreach plan payloads consistently as JSON strings."""
    if isinstance(value, dict):
        return dumps(value, ensure_ascii=False, sort_keys=True)
    if value is None:
        return ""
    text = str(value).strip()
    if not text:
        return ""
    try:
        parsed = loads(text)
    except Exception:
        return text
    if isinstance(parsed, dict):
        return dumps(parsed, ensure_ascii=False, sort_keys=True)
    return text


def _clean_import_row_dict(row: Any) -> Dict[str, Any]:
    """Remove blank-header columns and normalize empty cell values for import metadata."""
    cleaned: Dict[str, Any] = {}
    for key, value in row.items():
        header = str(key).strip() if key is not None else ""
        lowered_header = header.casefold()
        if not header or lowered_header.startswith("unnamed:"):
            continue
        cleaned[header] = "" if _is_blank_import_value(value) else value
    return cleaned


def _row_has_non_empty_values(row: Any) -> bool:
    """Return True when a row has at least one non-empty value under a real header."""
    for key, value in row.items():
        header = str(key).strip() if key is not None else ""
        lowered_header = header.casefold()
        if not header or lowered_header.startswith("unnamed:"):
            continue
        if not _is_blank_import_value(value):
            return True
    return False


class GuestDatabase:
    """Manages the SQLite database for guest information with simplified interface."""
    
    def __init__(self, db_path: Union[str, Path] = DEFAULT_DB_PATH):
        """Initialize the database connection and create tables if needed."""
        self.db_path = Path(db_path) if isinstance(db_path, str) else db_path
        SchemaManager.create_tables(str(self.db_path))
        self.mapper = DataMapper()
        self.file_reader = FileReader()

    def _connect(self) -> sqlite3.Connection:
        """Open a configured connection with integrity enforcement enabled."""
        return connect_database(self.db_path)

    def get_booking_availability(self) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM booking_availability WHERE id = 1").fetchone()
            return dict(row) if row else None

    def save_booking_availability(self, values: Dict[str, Any], *, actor: str) -> Dict[str, Any]:
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            before_row = conn.execute("SELECT * FROM booking_availability WHERE id = 1").fetchone()
            before = dict(before_row) if before_row else None
            conn.execute("""INSERT INTO booking_availability (id, timezone, weekdays_json, slot_times_json, days_ahead, min_notice_hours, blackouts_json, updated_at, updated_by)
                VALUES (1, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?)
                ON CONFLICT(id) DO UPDATE SET timezone=excluded.timezone, weekdays_json=excluded.weekdays_json,
                slot_times_json=excluded.slot_times_json, days_ahead=excluded.days_ahead,
                min_notice_hours=excluded.min_notice_hours, blackouts_json=excluded.blackouts_json, updated_at=CURRENT_TIMESTAMP, updated_by=excluded.updated_by""",
                (values['timezone'], dumps(values['weekdays']), dumps(values['slot_times']), values['days_ahead'], values['min_notice_hours'], dumps(values.get('blackouts', [])), actor))
            after = dict(conn.execute("SELECT * FROM booking_availability WHERE id = 1").fetchone())
            self._append_audit_event_conn(conn, entity_type="booking_availability", entity_id=1,
                event_type="availability_updated", actor=actor, source="availability_page", before=before, after=after)
            conn.commit()
            return after

    @staticmethod
    def get_column_value(row: Any, possible_columns: List[str]) -> str:
        """Preserve the legacy import helper while delegating to ``DataMapper``."""
        return DataMapper.get_column_value(row, possible_columns)
    
    # ==================== CRUD Operations ====================
    
    def insert_guest(self, guest_data: Dict[str, Any]) -> int:
        """Insert a new guest into the database."""
        with self._connect() as conn:
            cursor = conn.execute("""
                INSERT INTO guests (
                    name, full_name, email, website, social_media_handles, 
                    background, profession, motivation, life_experiences, core_values, 
                    faith_practice, beliefs_align, favorite_quote, passionate_topics, message_takeaway,
                    podcast_experience, additional_info, following_us, marketing_opt_in, is_processed,
                    original_file_name, original_data, guest_research, guest_research_updated_at,
                    booking_token, booking_token_created_at, booking_override,
                    normalized_name, normalized_email, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """, (
                guest_data.get('full_name'), guest_data.get('full_name'), guest_data.get('email'), 
                guest_data.get('website'), guest_data.get('social_handles'),
                guest_data.get('background'), guest_data.get('profession'), guest_data.get('motivation'), 
                guest_data.get('life_experiences'), guest_data.get('core_values'), guest_data.get('faith'), 
                guest_data.get('alignment'), guest_data.get('favorite_quote'), guest_data.get('passionate_topics'), 
                guest_data.get('message'), guest_data.get('experience'), guest_data.get('additional_info'), 
                guest_data.get('has_social_media'), bool(guest_data.get('marketing_opt_in', False)), guest_data.get('is_processed', False),
                guest_data.get('original_file_name'), guest_data.get('original_data'),
                guest_data.get('guest_research'), guest_data.get('guest_research_updated_at'),
                guest_data.get('booking_token'), guest_data.get('booking_token_created_at'),
                guest_data.get('booking_override'),
                _normalized_identity(guest_data.get('full_name')),
                _normalized_identity(guest_data.get('email')),
            ))
            guest_id = int(cursor.lastrowid)
            self._insert_guest_application(conn, guest_id, guest_data)
            conn.commit()
            return guest_id

    @staticmethod
    def _insert_guest_application(conn: sqlite3.Connection, guest_id: int, guest_data: Dict[str, Any]) -> int:
        """Append one immutable intake/import submission for a guest identity."""
        payload = guest_data.get("original_data")
        if not payload:
            payload = dumps(guest_data, ensure_ascii=False, default=str, sort_keys=True)
        source = str(guest_data.get("original_file_name") or "direct_entry").strip() or "direct_entry"
        cursor = conn.execute(
            """
            INSERT INTO guest_applications (guest_id, source, payload_json, status)
            VALUES (?, ?, ?, 'submitted')
            """,
            (guest_id, source, str(payload)),
        )
        return int(cursor.lastrowid)

    def create_guest_application(self, guest_id: int, guest_data: Dict[str, Any]) -> int:
        """Append a submission without overwriting the guest's prior decision."""
        with self._connect() as conn:
            application_id = self._insert_guest_application(conn, guest_id, guest_data)
            conn.commit()
            return application_id

    def list_guest_applications(self, guest_id: int) -> List[Dict]:
        """Return every submission for a guest, newest first."""
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM guest_applications WHERE guest_id = ? ORDER BY submitted_at DESC, id DESC",
                (guest_id,),
            ).fetchall()
            return [dict(row) for row in rows]

    def list_latest_guest_applications(self) -> Dict[int, Dict[str, Any]]:
        """Return the latest immutable application projection for every guest."""
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """SELECT application.*
                   FROM guest_applications AS application
                   JOIN (
                       SELECT guest_id, MAX(id) AS latest_id
                       FROM guest_applications
                       GROUP BY guest_id
                   ) AS latest ON latest.latest_id = application.id"""
            ).fetchall()
            return {int(row["guest_id"]): dict(row) for row in rows}

    def transition_latest_guest_application(
        self,
        guest_id: int,
        status: str,
        *,
        reason: str = "",
        actor: str = "operator",
        source: str = "guest_dashboard",
    ) -> Dict[str, Any]:
        """Move the latest application projection while preserving prior submissions."""
        allowed = {"submitted", "triage", "needs_information", "accepted", "declined", "withdrawn"}
        if status not in allowed:
            raise ValueError(f"Unsupported application status: {status}")
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            current_row = conn.execute(
                "SELECT * FROM guest_applications WHERE guest_id = ? ORDER BY submitted_at DESC, id DESC LIMIT 1",
                (guest_id,),
            ).fetchone()
            if not current_row:
                raise ValueError("Guest application not found")
            current = dict(current_row)
            status = validate_transition("application", current["status"], status)
            cursor = conn.execute(
                """UPDATE guest_applications
                   SET status = ?, decision_reason = ?,
                       decided_at = CASE WHEN ? IN ('accepted', 'declined', 'withdrawn') THEN CURRENT_TIMESTAMP ELSE NULL END,
                       row_version = row_version + 1, updated_at = CURRENT_TIMESTAMP
                   WHERE id = ? AND row_version = ?""",
                (status, reason or None, status, current["id"], current["row_version"]),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("Application was changed by another request")
            updated = dict(
                conn.execute("SELECT * FROM guest_applications WHERE id = ?", (current["id"],)).fetchone()
            )
            conn.execute(
                """INSERT INTO audit_events
                   (entity_type, entity_id, event_type, actor, source, reason, before_json, after_json)
                   VALUES ('application', ?, 'status_changed', ?, ?, ?, ?, ?)""",
                (
                    str(current["id"]),
                    actor,
                    source,
                    reason or None,
                    dumps(current, ensure_ascii=False, default=str, sort_keys=True),
                    dumps(updated, ensure_ascii=False, default=str, sort_keys=True),
                ),
            )
            conn.commit()
            return updated

    def append_audit_event(
        self,
        *,
        entity_type: str,
        entity_id: Any,
        event_type: str,
        actor: str = "system",
        source: str = "application",
        reason: str = "",
        correlation_id: str = "",
        before: Any = None,
        after: Any = None,
    ) -> int:
        """Append an immutable, attributable domain event."""
        with self._connect() as conn:
            event_id = self._append_audit_event_conn(
                conn,
                entity_type=entity_type,
                entity_id=entity_id,
                event_type=event_type,
                actor=actor,
                source=source,
                reason=reason,
                correlation_id=correlation_id,
                before=before,
                after=after,
            )
            conn.commit()
            return event_id

    @staticmethod
    def _append_audit_event_conn(
        conn: sqlite3.Connection,
        *,
        entity_type: str,
        entity_id: Any,
        event_type: str,
        actor: str = "system",
        source: str = "application",
        reason: str = "",
        correlation_id: str = "",
        before: Any = None,
        after: Any = None,
    ) -> int:
        cursor = conn.execute(
            """INSERT INTO audit_events
               (entity_type, entity_id, event_type, actor, source, reason, correlation_id, before_json, after_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                entity_type,
                str(entity_id),
                event_type,
                actor or "system",
                source or "application",
                reason or None,
                correlation_id or None,
                dumps(before, ensure_ascii=False, default=str, sort_keys=True) if before is not None else None,
                dumps(after, ensure_ascii=False, default=str, sort_keys=True) if after is not None else None,
            ),
        )
        return int(cursor.lastrowid)

    def list_audit_events(self, entity_type: str, entity_id: Any) -> List[Dict]:
        """Return the immutable activity timeline for one entity."""
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """SELECT * FROM audit_events
                   WHERE entity_type = ? AND entity_id = ? ORDER BY created_at DESC, id DESC""",
                (entity_type, str(entity_id)),
            ).fetchall()
            return [dict(row) for row in rows]

    def record_recommendation_feedback(
        self,
        episode_id: int,
        *,
        action: str,
        reason: str = "",
        actor: str = "system",
        source: str = "scheduling_intelligence",
        recommendation_version: str = "",
        recommendation_snapshot: Any = None,
        correlation_id: str = "",
        idempotency_key: str = "",
    ) -> Dict[str, Any]:
        """Append a reversible scheduling-recommendation decision and its audit event."""
        normalized_action = str(action or "").strip().lower()
        normalized_reason = str(reason or "").strip()
        if normalized_action not in {"rejected", "restored"}:
            raise ValueError("Recommendation feedback action must be rejected or restored")
        if normalized_action == "rejected" and not normalized_reason:
            raise ValueError("A rejection reason is required")
        request_key = str(idempotency_key or "").strip() or str(uuid4())

        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            existing = conn.execute(
                "SELECT * FROM recommendation_feedback WHERE idempotency_key = ?",
                (request_key,),
            ).fetchone()
            if existing:
                return dict(existing)
            episode = conn.execute("SELECT * FROM episodes WHERE id = ?", (episode_id,)).fetchone()
            if not episode:
                raise ValueError("Episode not found")
            previous = conn.execute(
                "SELECT * FROM recommendation_feedback WHERE episode_id = ? ORDER BY id DESC LIMIT 1",
                (episode_id,),
            ).fetchone()
            snapshot_json = (
                dumps(recommendation_snapshot, ensure_ascii=False, default=str, sort_keys=True)
                if recommendation_snapshot is not None
                else None
            )
            cursor = conn.execute(
                """INSERT INTO recommendation_feedback
                   (episode_id, action, reason, actor, source, recommendation_version,
                    recommendation_snapshot, correlation_id, idempotency_key)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    episode_id,
                    normalized_action,
                    normalized_reason or None,
                    str(actor or "system").strip() or "system",
                    str(source or "scheduling_intelligence").strip() or "scheduling_intelligence",
                    str(recommendation_version or "").strip() or None,
                    snapshot_json,
                    str(correlation_id or "").strip() or None,
                    request_key,
                ),
            )
            saved = dict(conn.execute("SELECT * FROM recommendation_feedback WHERE id = ?", (cursor.lastrowid,)).fetchone())
            self._append_audit_event_conn(
                conn,
                entity_type="episode",
                entity_id=episode_id,
                event_type=f"recommendation_{normalized_action}",
                actor=saved["actor"],
                source=saved["source"],
                reason=normalized_reason,
                correlation_id=str(correlation_id or ""),
                before=dict(previous) if previous else None,
                after=saved,
            )
            conn.commit()
            return saved

    def get_latest_recommendation_feedback(self, episode_ids: Optional[List[int]] = None) -> Dict[int, Dict[str, Any]]:
        """Return the latest scheduling-recommendation decision for each episode."""
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            params: list[Any] = []
            where = ""
            if episode_ids is not None:
                normalized_ids = sorted({int(value) for value in episode_ids})
                if not normalized_ids:
                    return {}
                placeholders = ",".join("?" for _ in normalized_ids)
                where = f"WHERE feedback.episode_id IN ({placeholders})"
                params.extend(normalized_ids)
            rows = conn.execute(
                f"""SELECT feedback.*
                    FROM recommendation_feedback AS feedback
                    JOIN (
                        SELECT episode_id, MAX(id) AS latest_id
                        FROM recommendation_feedback
                        GROUP BY episode_id
                    ) AS latest ON latest.latest_id = feedback.id
                    {where}""",
                params,
            ).fetchall()
            return {int(row["episode_id"]): dict(row) for row in rows}

    def find_existing_guest(self, guest_data: Dict[str, Any]) -> Optional[Dict]:
        """Find an existing guest using the best available identity fields."""
        full_name = _normalized_identity(guest_data.get("full_name"))
        email = _normalized_identity(guest_data.get("email"))

        with self._connect() as conn:
            conn.row_factory = sqlite3.Row

            if email and email != "anonymous":
                cursor = conn.execute(
                    """
                    SELECT * FROM guests
                    WHERE LOWER(COALESCE(email, '')) = ? AND COALESCE(identity_status, 'active') = 'active'
                    ORDER BY id DESC
                    LIMIT 1
                    """,
                    (email,),
                )
                row = cursor.fetchone()
                if row:
                    return dict(row)

            if full_name:
                cursor = conn.execute(
                    """
                    SELECT * FROM guests
                    WHERE LOWER(COALESCE(full_name, name, '')) = ? AND COALESCE(identity_status, 'active') = 'active'
                    ORDER BY id DESC
                    LIMIT 1
                    """,
                    (full_name,),
                )
                row = cursor.fetchone()
                if row:
                    return dict(row)

        return None

    def upsert_guest(self, guest_data: Dict[str, Any]) -> tuple[int, str]:
        """Insert or update a guest to avoid duplicate entries."""
        existing_guest = self.find_existing_guest(guest_data)

        if existing_guest:
            incoming_source = str(guest_data.get("original_file_name") or "").strip()
            is_new_intake = incoming_source == INTAKE_SOURCE_NAME
            if is_new_intake:
                self.create_guest_application(existing_guest["id"], guest_data)

            merged_guest = dict(existing_guest)
            merged_guest.update(guest_data)
            if guest_data.get("marketing_opt_in") is None:
                merged_guest["marketing_opt_in"] = existing_guest.get("marketing_opt_in", False)
            merged_guest["full_name"] = guest_data.get("full_name") or existing_guest.get("full_name") or existing_guest.get("name")
            merged_guest["email"] = (
                guest_data.get("email")
                if self.mapper.should_update_email(existing_guest.get("email"), guest_data.get("email"))
                else existing_guest.get("email")
            )
            merged_guest["is_processed"] = existing_guest.get("is_processed")
            merged_guest["email_status"] = existing_guest.get("email_status")
            merged_guest["email_sent_at"] = existing_guest.get("email_sent_at")
            merged_guest["skip_reason"] = existing_guest.get("skip_reason")
            merged_guest["original_file_name"] = _prefer_existing_metadata(
                existing_guest.get("original_file_name"),
                guest_data.get("original_file_name"),
            )
            merged_guest["original_data"] = _prefer_existing_metadata(
                existing_guest.get("original_data"),
                guest_data.get("original_data"),
            )
            merged_guest["guest_research"] = _prefer_existing_metadata(
                existing_guest.get("guest_research"),
                guest_data.get("guest_research"),
            )
            merged_guest["guest_research_updated_at"] = (
                guest_data.get("guest_research_updated_at")
                or existing_guest.get("guest_research_updated_at")
            )
            merged_guest["booking_token"] = guest_data.get("booking_token") or existing_guest.get("booking_token")
            merged_guest["booking_token_created_at"] = (
                guest_data.get("booking_token_created_at")
                or existing_guest.get("booking_token_created_at")
            )
            merged_guest["booking_override"] = guest_data.get("booking_override") or existing_guest.get("booking_override")
            if is_new_intake:
                # Keep the guest table as a compatibility projection of the latest
                # application while prior decisions remain immutable in history.
                merged_guest["is_processed"] = False
                merged_guest["email_status"] = None
                merged_guest["email_sent_at"] = None
                merged_guest["skip_reason"] = None
                merged_guest["original_file_name"] = guest_data.get("original_file_name")
                merged_guest["original_data"] = guest_data.get("original_data")
            self.update_guest_by_id(existing_guest["id"], merged_guest)
            return existing_guest["id"], "updated"

        return self.insert_guest(guest_data), "created"
    
    def update_guest_by_id(self, guest_id: int, guest_data: Dict[str, Any]) -> None:
        """Update an existing guest in the database by ID."""
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            current_row = conn.execute("SELECT * FROM guests WHERE id = ?", (guest_id,)).fetchone()
            current = dict(current_row) if current_row else None
            if not current:
                raise ValueError("Guest not found")
            expected_version = int(guest_data.get("row_version") or current["row_version"])
            cursor = conn.execute("""
                UPDATE guests SET
                    name = ?, full_name = ?, email = ?, website = ?, social_media_handles = ?,
                    background = ?, profession = ?, motivation = ?, life_experiences = ?, 
                    core_values = ?, faith_practice = ?, beliefs_align = ?, favorite_quote = ?,
                    passionate_topics = ?, message_takeaway = ?, podcast_experience = ?, 
                    additional_info = ?, following_us = ?, marketing_opt_in = ?, is_processed = ?, email_status = ?,
                    email_sent_at = ?, skip_reason = ?, original_file_name = ?, original_data = ?,
                    guest_research = ?, guest_research_updated_at = ?, booking_token = ?, booking_token_created_at = ?,
                    booking_override = ?, owner = ?,
                    normalized_name = ?, normalized_email = ?, row_version = row_version + 1,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ? AND row_version = ?
            """, (
                guest_data.get('full_name'), guest_data.get('full_name'), guest_data.get('email'), 
                guest_data.get('website'), guest_data.get('social_handles'), guest_data.get('background'), 
                guest_data.get('profession'), guest_data.get('motivation'), guest_data.get('life_experiences'), 
                guest_data.get('core_values'), guest_data.get('faith'), guest_data.get('alignment'), 
                guest_data.get('favorite_quote'), guest_data.get('passionate_topics'), guest_data.get('message'), 
                guest_data.get('experience'), guest_data.get('additional_info'), guest_data.get('has_social_media'),
                bool(guest_data.get('marketing_opt_in', False)), guest_data.get('is_processed'), guest_data.get('email_status'),
                guest_data.get('email_sent_at'), guest_data.get('skip_reason'),
                guest_data.get('original_file_name'), guest_data.get('original_data'),
                guest_data.get('guest_research'), guest_data.get('guest_research_updated_at'),
                guest_data.get('booking_token'), guest_data.get('booking_token_created_at'),
                guest_data.get('booking_override'),
                guest_data.get('owner'),
                _normalized_identity(guest_data.get('full_name')),
                _normalized_identity(guest_data.get('email')),
                guest_id,
                expected_version,
            ))
            if cursor.rowcount != 1:
                raise RuntimeError("Guest was changed by another request")
            updated = dict(conn.execute("SELECT * FROM guests WHERE id = ?", (guest_id,)).fetchone())
            self._append_audit_event_conn(
                conn,
                entity_type="guest",
                entity_id=guest_id,
                event_type="updated",
                actor=str(guest_data.get("actor") or "operator"),
                source=str(guest_data.get("source") or "guest_dashboard"),
                reason=str(guest_data.get("reason") or ""),
                correlation_id=str(guest_data.get("correlation_id") or ""),
                before=current,
                after=updated,
            )
            conn.commit()
    
    def delete_guest(self, guest_id: int) -> None:
        """Delete a guest from the database."""
        with self._connect() as conn:
            conn.execute("DELETE FROM guests WHERE id = ?", (guest_id,))
            conn.commit()
    
    def get_guest_by_id(self, guest_id: int) -> Optional[Dict]:
        """Get a guest by ID."""
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("SELECT * FROM guests WHERE id = ?", (guest_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_guest_ai_analysis(self, guest_id: int, *, input_fingerprint: str, model: str) -> Optional[Dict[str, Any]]:
        """Return a saved analysis only when it matches the current guest data and model."""
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                """SELECT analysis_json, created_at FROM guest_ai_analyses
                   WHERE guest_id = ? AND input_fingerprint = ? AND model = ?""",
                (guest_id, input_fingerprint, model),
            ).fetchone()
            if not row:
                return None
            try:
                analysis = loads(str(row["analysis_json"]))
            except (TypeError, ValueError):
                logger.warning("Ignoring malformed saved AI analysis for guest_id=%s", guest_id)
                return None
            if not isinstance(analysis, dict):
                return None
            return {"analysis": analysis, "created_at": row["created_at"]}

    def save_guest_ai_analysis(self, guest_id: int, *, analysis: Dict[str, Any], input_fingerprint: str, model: str) -> None:
        """Upsert a completed analysis without altering guest application provenance."""
        serialized = dumps(analysis, ensure_ascii=False, sort_keys=True)
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO guest_ai_analyses (guest_id, analysis_json, input_fingerprint, model)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(guest_id) DO UPDATE SET
                     analysis_json = excluded.analysis_json,
                     input_fingerprint = excluded.input_fingerprint,
                     model = excluded.model,
                     created_at = CURRENT_TIMESTAMP""",
                (guest_id, serialized, input_fingerprint, model),
            )
            conn.commit()
    
    def get_guest_by_name(self, name: str) -> Optional[Dict]:
        """Get a guest by name (case-insensitive)."""
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT * FROM guests WHERE LOWER(full_name) = LOWER(?) LIMIT 1",
                (name,)
            )
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def get_all_guests(self) -> List[Dict]:
        """Get all guests."""
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT * FROM guests WHERE COALESCE(identity_status, 'active') = 'active' ORDER BY date_added DESC"
            )
            return [dict(row) for row in cursor.fetchall()]

    def list_identity_merge_candidates(self) -> List[Dict[str, Any]]:
        """Return exact-email and same-name identity groups for human review."""
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """SELECT * FROM guests
                   WHERE COALESCE(identity_status, 'active') IN ('active', 'review')
                     AND (normalized_email <> '' OR normalized_name <> '')
                   ORDER BY normalized_email, normalized_name, id"""
            ).fetchall()
        by_key: Dict[tuple[str, str], List[Dict[str, Any]]] = {}
        for row in rows:
            item = dict(row)
            if item.get("normalized_email"):
                key = ("exact_email", str(item["normalized_email"]))
                by_key.setdefault(key, []).append(item)
            elif item.get("normalized_name"):
                key = ("same_name", str(item["normalized_name"]))
                by_key.setdefault(key, []).append(item)
        return [
            {"match_type": key[0], "match_value": key[1], "guests": guests}
            for key, guests in by_key.items()
            if len(guests) > 1
        ]

    def merge_guest_identities(
        self,
        survivor_id: int,
        duplicate_id: int,
        *,
        actor: str = "operator",
        reason: str,
        correlation_id: str = "",
    ) -> Dict[str, Any]:
        """Merge related records into a survivor while retaining a tombstone."""
        if survivor_id == duplicate_id:
            raise ValueError("Survivor and duplicate must be different guests")
        if not reason.strip():
            raise ValueError("A merge reason is required")
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            survivor_row = conn.execute("SELECT * FROM guests WHERE id = ?", (survivor_id,)).fetchone()
            duplicate_row = conn.execute("SELECT * FROM guests WHERE id = ?", (duplicate_id,)).fetchone()
            if not survivor_row or not duplicate_row:
                raise ValueError("Guest identity not found")
            survivor, duplicate = dict(survivor_row), dict(duplicate_row)
            if survivor.get("identity_status") == "merged" or duplicate.get("identity_status") == "merged":
                raise ValueError("A merged tombstone cannot be merged again")
            exact_email = survivor.get("normalized_email") and survivor.get("normalized_email") == duplicate.get("normalized_email")
            exact_name = survivor.get("normalized_name") and survivor.get("normalized_name") == duplicate.get("normalized_name")
            if not (exact_email or exact_name):
                raise ValueError("Identities do not share a normalized email or name")

            for table in ("guest_applications", "interviews", "episodes"):
                conn.execute(f"UPDATE {table} SET guest_id = ? WHERE guest_id = ?", (survivor_id, duplicate_id))
            cursor = conn.execute(
                """UPDATE guests
                   SET identity_status = 'merged', merged_into_guest_id = ?, row_version = row_version + 1,
                       updated_at = CURRENT_TIMESTAMP
                   WHERE id = ? AND row_version = ?""",
                (survivor_id, duplicate_id, duplicate["row_version"]),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("Guest identity was changed by another request")
            after = dict(conn.execute("SELECT * FROM guests WHERE id = ?", (duplicate_id,)).fetchone())
            self._append_audit_event_conn(
                conn,
                entity_type="guest_identity",
                entity_id=duplicate_id,
                event_type="merged",
                actor=actor,
                source="deduplication_review",
                reason=reason,
                correlation_id=correlation_id,
                before=duplicate,
                after={"tombstone": after, "survivor_id": survivor_id},
            )
            conn.commit()
            return {"survivor_id": survivor_id, "merged_id": duplicate_id, "status": "merged"}

    def get_guest_by_booking_token(self, booking_token: str) -> Optional[Dict]:
        """Fetch a single guest by booking token."""
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT * FROM guests WHERE booking_token = ? LIMIT 1",
                (booking_token,),
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def create_calendar_reconciliation_proposals(
        self, proposals: List[Dict[str, Any]], *, correlation_id: str
    ) -> List[Dict[str, Any]]:
        """Persist a reviewable calendar diff without changing interviews."""
        created_ids: List[int] = []
        with self._connect() as conn:
            for proposal in proposals:
                event_id = str(proposal.get("calendar_event_id") or "").strip()
                if not event_id:
                    continue
                conn.execute(
                    """UPDATE calendar_reconciliation_proposals
                       SET status = 'superseded', reviewed_at = CURRENT_TIMESTAMP, row_version = row_version + 1
                       WHERE calendar_event_id = ? AND status = 'pending'""",
                    (event_id,),
                )
                cursor = conn.execute(
                    """INSERT INTO calendar_reconciliation_proposals
                       (calendar_event_id, interview_id, action, before_json, after_json, reason, correlation_id)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (
                        event_id,
                        proposal.get("interview_id"),
                        proposal["action"],
                        dumps(proposal.get("before"), ensure_ascii=False, default=str, sort_keys=True)
                        if proposal.get("before") is not None
                        else None,
                        dumps(proposal.get("after") or {}, ensure_ascii=False, default=str, sort_keys=True),
                        proposal.get("reason"),
                        correlation_id,
                    ),
                )
                created_ids.append(int(cursor.lastrowid))
            conn.commit()
            if not created_ids:
                return []
            conn.row_factory = sqlite3.Row
            placeholders = ",".join("?" for _ in created_ids)
            rows = conn.execute(
                f"SELECT * FROM calendar_reconciliation_proposals WHERE id IN ({placeholders}) ORDER BY id",
                created_ids,
            ).fetchall()
            return [dict(row) for row in rows]

    def get_calendar_reconciliation_proposal(self, proposal_id: int) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM calendar_reconciliation_proposals WHERE id = ?", (proposal_id,)
            ).fetchone()
            return dict(row) if row else None

    def mark_calendar_reconciliation_proposal(
        self, proposal_id: int, *, status: str, expected_version: int
    ) -> Dict[str, Any]:
        if status not in {"approved", "applied", "dismissed", "failed"}:
            raise ValueError("Unsupported calendar proposal status")
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                """UPDATE calendar_reconciliation_proposals
                   SET status = ?, reviewed_at = COALESCE(reviewed_at, CURRENT_TIMESTAMP),
                       applied_at = CASE WHEN ? = 'applied' THEN CURRENT_TIMESTAMP ELSE applied_at END,
                       row_version = row_version + 1
                   WHERE id = ? AND row_version = ?""",
                (status, status, proposal_id, expected_version),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("Calendar proposal was changed by another request")
            conn.commit()
            return dict(conn.execute("SELECT * FROM calendar_reconciliation_proposals WHERE id = ?", (proposal_id,)).fetchone())

    # ==================== Podcast Operations ====================

    def upsert_interview(self, interview_data: Dict[str, Any]) -> tuple[int, str]:
        """Insert or update an interview using the calendar event id when available."""
        interview_id = interview_data.get("id")
        raw_calendar_event_id = interview_data.get("calendar_event_id")
        calendar_event_id = str(raw_calendar_event_id).strip() if raw_calendar_event_id is not None else ""
        if not calendar_event_id:
            calendar_event_id = None
        raw_reschedule_token = interview_data.get("reschedule_token")
        reschedule_token = str(raw_reschedule_token).strip() if raw_reschedule_token is not None else ""
        if not reschedule_token:
            reschedule_token = None

        with self._connect() as conn:
            conn.row_factory = sqlite3.Row

            existing_row = None
            if interview_id:
                cursor = conn.execute(
                    "SELECT id FROM interviews WHERE id = ? LIMIT 1",
                    (interview_id,),
                )
                existing_row = cursor.fetchone()
            elif calendar_event_id:
                cursor = conn.execute(
                    "SELECT id FROM interviews WHERE calendar_event_id = ? LIMIT 1",
                    (calendar_event_id,),
                )
                existing_row = cursor.fetchone()

            interview_status = validate_state("interview", interview_data.get("status", "scheduled"))
            confirmation_status = validate_state(
                "confirmation", interview_data.get("confirmation_status", "pending")
            )
            if existing_row:
                existing_row = conn.execute(
                    "SELECT * FROM interviews WHERE id = ?", (existing_row["id"],)
                ).fetchone()
                interview_status = validate_transition("interview", existing_row["status"], interview_status)
                confirmation_status = validate_transition(
                    "confirmation", existing_row["confirmation_status"], confirmation_status
                )

            fields = (
                interview_data.get("guest_id"),
                interview_data.get("guest_name"),
                interview_data.get("guest_email"),
                calendar_event_id,
                interview_data.get("calendar_source"),
                interview_data.get("event_updated_at"),
                interview_data.get("last_synced_at"),
                reschedule_token,
                interview_data.get("reschedule_token_created_at"),
                interview_data.get("title"),
                interview_data.get("scheduled_for"),
                interview_data.get("timezone", "Europe/Berlin"),
                interview_data.get("join_url"),
                interview_status,
                confirmation_status,
                interview_data.get("reminder_status", "not_scheduled"),
                interview_data.get("reminder_sent_at"),
                interview_data.get("notes"),
                interview_data.get("owner"),
            )

            if existing_row:
                cursor = conn.execute(
                    """
                    UPDATE interviews SET
                        guest_id = ?, guest_name = ?, guest_email = ?, calendar_event_id = ?, calendar_source = ?,
                        event_updated_at = ?, last_synced_at = ?, reschedule_token = ?, reschedule_token_created_at = ?, title = ?, scheduled_for = ?, timezone = ?,
                        join_url = ?, status = ?, confirmation_status = ?, reminder_status = ?,
                        reminder_sent_at = ?, notes = ?, owner = ?, row_version = row_version + 1,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ? AND row_version = ?
                    """,
                    fields + (existing_row["id"], int(interview_data.get("row_version") or existing_row["row_version"])),
                )
                if cursor.rowcount != 1:
                    raise RuntimeError("Interview was changed by another request")
                updated_row = dict(conn.execute("SELECT * FROM interviews WHERE id = ?", (existing_row["id"],)).fetchone())
                event_type = (
                    "status_changed"
                    if (existing_row["status"], existing_row["confirmation_status"])
                    != (updated_row["status"], updated_row["confirmation_status"])
                    else "updated"
                )
                self._append_audit_event_conn(
                    conn,
                    entity_type="interview",
                    entity_id=existing_row["id"],
                    event_type=event_type,
                    actor=str(interview_data.get("actor") or "operator"),
                    source=str(interview_data.get("source") or "operations"),
                    reason=str(interview_data.get("reason") or ""),
                    correlation_id=str(interview_data.get("correlation_id") or ""),
                    before=dict(existing_row),
                    after=updated_row,
                )
                conn.commit()
                return existing_row["id"], "updated"

            cursor = conn.execute(
                """
                INSERT INTO interviews (
                    guest_id, guest_name, guest_email, calendar_event_id, calendar_source, event_updated_at,
                    last_synced_at, reschedule_token, reschedule_token_created_at, title, scheduled_for, timezone, join_url, status, confirmation_status,
                    reminder_status, reminder_sent_at, notes, updated_at
                    , owner
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?)
                """,
                fields,
            )
            interview_id = int(cursor.lastrowid)
            created_row = dict(conn.execute("SELECT * FROM interviews WHERE id = ?", (interview_id,)).fetchone())
            self._append_audit_event_conn(
                conn, entity_type="interview", entity_id=interview_id, event_type="created",
                actor=str(interview_data.get("actor") or "operator"),
                source=str(interview_data.get("source") or "operations"),
                reason=str(interview_data.get("reason") or ""),
                correlation_id=str(interview_data.get("correlation_id") or ""), after=created_row
            )
            conn.commit()
            return interview_id, "created"

    def list_interviews(self) -> List[Dict]:
        """Return all interviews, newest scheduled items first."""
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT * FROM interviews ORDER BY datetime(scheduled_for) DESC, id DESC"
            )
            return [dict(row) for row in cursor.fetchall()]

    def update_interview(self, interview_id: int, interview_data: Dict[str, Any]) -> None:
        """Update an interview record."""
        current = self.get_interview_by_id(interview_id)
        if not current:
            raise ValueError("Interview not found")

        merged = dict(current)
        merged.update(interview_data)
        self.upsert_interview(merged)

    def get_interview_by_id(self, interview_id: int) -> Optional[Dict]:
        """Fetch a single interview by id."""
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("SELECT * FROM interviews WHERE id = ?", (interview_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_interview_by_calendar_event_id(self, calendar_event_id: str) -> Optional[Dict]:
        """Fetch a single interview by Google Calendar event id."""
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT * FROM interviews WHERE calendar_event_id = ? LIMIT 1",
                (calendar_event_id,),
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_interview_by_reschedule_token(self, reschedule_token: str) -> Optional[Dict]:
        """Fetch a single interview by reschedule token."""
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT * FROM interviews WHERE reschedule_token = ? LIMIT 1",
                (reschedule_token,),
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def delete_interview(self, interview_id: int) -> None:
        """Delete an interview from the database."""
        with self._connect() as conn:
            conn.execute("DELETE FROM interviews WHERE id = ?", (interview_id,))
            conn.commit()

    def upsert_episode(self, episode_data: Dict[str, Any]) -> tuple[int, str]:
        """Insert or update an episode using interview id when available."""
        interview_id = episode_data.get("interview_id")
        episode_id = episode_data.get("id")

        with self._connect() as conn:
            conn.row_factory = sqlite3.Row

            existing_row = None
            if episode_id:
                cursor = conn.execute(
                    "SELECT id FROM episodes WHERE id = ? LIMIT 1",
                    (episode_id,),
                )
                existing_row = cursor.fetchone()
            elif interview_id:
                cursor = conn.execute(
                    "SELECT id FROM episodes WHERE interview_id = ? LIMIT 1",
                    (interview_id,),
                )
                existing_row = cursor.fetchone()
            elif episode_data.get("legacy_episode_number"):
                # Episode numbers are sequencing metadata, not identity. They can
                # collide temporarily while future releases are being renumbered,
                # so only reuse a numbered row when a guest identity signal also
                # agrees. A number-only match previously overwrote unrelated
                # scheduled episodes and silently lost their title and metadata.
                cursor = conn.execute(
                    """
                    SELECT id FROM episodes
                    WHERE legacy_episode_number = ?
                      AND (
                        (TRIM(COALESCE(?, '')) <> '' AND LOWER(TRIM(COALESCE(guest_email, ''))) = LOWER(TRIM(?)))
                        OR
                        (TRIM(COALESCE(?, '')) <> '' AND LOWER(TRIM(COALESCE(guest_name, ''))) = LOWER(TRIM(?)))
                      )
                    ORDER BY id DESC
                    LIMIT 1
                    """,
                    (
                        episode_data.get("legacy_episode_number"),
                        episode_data.get("guest_email"),
                        episode_data.get("guest_email"),
                        episode_data.get("guest_name"),
                        episode_data.get("guest_name"),
                    ),
                )
                existing_row = cursor.fetchone()
            elif episode_data.get("guest_name") and episode_data.get("topic") and episode_data.get("interview_date"):
                cursor = conn.execute(
                    """
                    SELECT id FROM episodes
                    WHERE guest_name = ? AND COALESCE(topic, '') = ? AND COALESCE(interview_date, '') = ?
                    LIMIT 1
                    """,
                    (
                        episode_data.get("guest_name"),
                        episode_data.get("topic"),
                        episode_data.get("interview_date"),
                    ),
                )
                existing_row = cursor.fetchone()

            if not existing_row:
                existing_row = self._find_existing_episode_row(conn, episode_data)

            release_status = validate_state("release", episode_data.get("release_status", "unplanned"))
            production_status = validate_state("production", episode_data.get("production_status", "idea"))
            promotion_status = validate_state("promotion", episode_data.get("promotion_status", "unknown"))
            if existing_row:
                existing_row = conn.execute(
                    "SELECT * FROM episodes WHERE id = ?", (existing_row["id"],)
                ).fetchone()
                release_status = validate_transition("release", existing_row["release_status"], release_status)
                production_status = validate_transition(
                    "production", existing_row["production_status"], production_status
                )
                promotion_status = validate_transition(
                    "promotion", existing_row["promotion_status"], promotion_status
                )

            original_planned_release_date = episode_data.get("original_planned_release_date")
            if not original_planned_release_date and existing_row:
                original_planned_release_date = existing_row["original_planned_release_date"]
            if not original_planned_release_date and release_status == "scheduled":
                original_planned_release_date = episode_data.get("release_date")

            fields = (
                episode_data.get("guest_id"),
                interview_id,
                episode_data.get("guest_name"),
                episode_data.get("guest_email"),
                episode_data.get("website"),
                episode_data.get("episode_title"),
                episode_data.get("working_title") or episode_data.get("episode_title"),
                episode_data.get("published_title"),
                episode_data.get("topic"),
                episode_data.get("category"),
                episode_data.get("interview_date"),
                episode_data.get("recording_date"),
                episode_data.get("release_date"),
                release_status,
                production_status,
                promotion_status,
                episode_data.get("priority_score", 0),
                episode_data.get("recommendation_reason"),
                episode_data.get("legacy_episode_number"),
                episode_data.get("riverside_status"),
                episode_data.get("source_file_name"),
                episode_data.get("source_type"),
                episode_data.get("show_notes_url"),
                episode_data.get("release_files_url"),
                episode_data.get("transcript_text"),
                episode_data.get("transcript_source_id"),
                episode_data.get("transcript_synced_at"),
                episode_data.get("transcript_match_method"),
                episode_data.get("transcript_match_score"),
                _normalize_outreach_plan_storage(episode_data.get("outreach_plan")),
                episode_data.get("ai_monthly_angle_state"),
                episode_data.get("ai_monthly_angle_theme"),
                episode_data.get("notes"),
                episode_data.get("owner"),
                episode_data.get("editorial_disposition", "active"),
                original_planned_release_date,
            )

            if existing_row:
                cursor = conn.execute(
                    """
                    UPDATE episodes SET
                        guest_id = ?, interview_id = ?, guest_name = ?, guest_email = ?, website = ?, episode_title = ?, working_title = ?, published_title = ?,
                        topic = ?, category = ?, interview_date = ?, recording_date = ?, release_date = ?,
                        release_status = ?, production_status = ?, promotion_status = ?, priority_score = ?, recommendation_reason = ?,
                        legacy_episode_number = ?, riverside_status = ?, source_file_name = ?, source_type = ?,
                        show_notes_url = ?, release_files_url = ?, transcript_text = ?, transcript_source_id = ?, transcript_synced_at = ?, transcript_match_method = ?, transcript_match_score = ?, outreach_plan = ?,
                        ai_monthly_angle_state = ?, ai_monthly_angle_theme = ?, notes = ?, owner = ?, editorial_disposition = ?, original_planned_release_date = ?,
                        row_version = row_version + 1, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ? AND row_version = ?
                    """,
                    fields + (existing_row["id"], int(episode_data.get("row_version") or existing_row["row_version"])),
                )
                if cursor.rowcount != 1:
                    raise RuntimeError("Episode was changed by another request")
                updated_row = dict(conn.execute("SELECT * FROM episodes WHERE id = ?", (existing_row["id"],)).fetchone())
                event_type = (
                    "status_changed"
                    if (
                        existing_row["release_status"],
                        existing_row["production_status"],
                        existing_row["promotion_status"],
                    )
                    != (
                        updated_row["release_status"],
                        updated_row["production_status"],
                        updated_row["promotion_status"],
                    )
                    else "updated"
                )
                self._append_audit_event_conn(
                    conn,
                    entity_type="episode",
                    entity_id=existing_row["id"],
                    event_type=event_type,
                    actor=str(episode_data.get("actor") or "operator"),
                    source=str(episode_data.get("source") or "planning"),
                    reason=str(episode_data.get("reason") or ""),
                    correlation_id=str(episode_data.get("correlation_id") or ""),
                    before=dict(existing_row),
                    after=updated_row,
                )
                conn.commit()
                return existing_row["id"], "updated"

            cursor = conn.execute(
                """
                INSERT INTO episodes (
                    guest_id, interview_id, guest_name, guest_email, website, episode_title, working_title, published_title, topic, category,
                    interview_date, recording_date, release_date, release_status, production_status,
                    promotion_status, priority_score, recommendation_reason, legacy_episode_number, riverside_status,
                    source_file_name, source_type, show_notes_url, release_files_url, transcript_text,
                    transcript_source_id, transcript_synced_at, transcript_match_method, transcript_match_score, outreach_plan,
                    ai_monthly_angle_state, ai_monthly_angle_theme, notes, updated_at, owner, editorial_disposition,
                    original_planned_release_date
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?, ?, ?)
                """,
                fields,
            )
            episode_id = int(cursor.lastrowid)
            created_row = dict(conn.execute("SELECT * FROM episodes WHERE id = ?", (episode_id,)).fetchone())
            self._append_audit_event_conn(
                conn, entity_type="episode", entity_id=episode_id, event_type="created",
                actor=str(episode_data.get("actor") or "operator"),
                source=str(episode_data.get("source") or "planning"),
                reason=str(episode_data.get("reason") or ""),
                correlation_id=str(episode_data.get("correlation_id") or ""), after=created_row
            )
            conn.commit()
            return episode_id, "created"

    def update_episode_sequence_numbers(
        self,
        updates: List[tuple[int, str, Optional[int]]],
    ) -> int:
        """Atomically renumber episodes without rewriting unrelated record fields."""
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            changed = 0
            for episode_id, legacy_episode_number, expected_row_version in updates:
                existing_row = conn.execute(
                    "SELECT * FROM episodes WHERE id = ? LIMIT 1",
                    (episode_id,),
                ).fetchone()
                if not existing_row:
                    raise ValueError("Episode not found")
                before = dict(existing_row)
                if str(before.get("legacy_episode_number") or "") == str(legacy_episode_number or ""):
                    continue

                row_version = int(expected_row_version or before.get("row_version") or 1)
                cursor = conn.execute(
                    """UPDATE episodes
                       SET legacy_episode_number = ?, row_version = row_version + 1,
                           updated_at = CURRENT_TIMESTAMP
                       WHERE id = ? AND row_version = ?""",
                    (legacy_episode_number, episode_id, row_version),
                )
                if cursor.rowcount != 1:
                    raise RuntimeError("Episode was changed by another request")
                after = dict(
                    conn.execute("SELECT * FROM episodes WHERE id = ?", (episode_id,)).fetchone()
                )
                self._append_audit_event_conn(
                    conn,
                    entity_type="episode",
                    entity_id=episode_id,
                    event_type="sequence_renumbered",
                    actor="system",
                    source="planning_sequence",
                    reason="Keep future scheduled episode numbers aligned to release order.",
                    before=before,
                    after=after,
                )
                changed += 1
            conn.commit()
            return changed

    def _find_existing_episode_row(self, conn: sqlite3.Connection, episode_data: Dict[str, Any]) -> Optional[sqlite3.Row]:
        """Find an existing episode using normalized archive/import identity fields."""
        guest_name = _normalized_episode_identity(episode_data.get("guest_name"))
        guest_email = _normalized_episode_identity(episode_data.get("guest_email"))
        topic = _normalized_episode_identity(episode_data.get("topic"))
        episode_title = _normalized_episode_identity(episode_data.get("episode_title"))
        release_date = _normalized_episode_identity(episode_data.get("release_date"))
        interview_date = _normalized_episode_identity(episode_data.get("interview_date"))
        source_file_name = _normalized_episode_identity(episode_data.get("source_file_name"))

        lookup_paths = [
            (
                guest_name and release_date,
                """
                SELECT id FROM episodes
                WHERE LOWER(COALESCE(guest_name, '')) = ?
                  AND LOWER(COALESCE(release_date, '')) = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (guest_name, release_date),
            ),
            (
                guest_email and release_date,
                """
                SELECT id FROM episodes
                WHERE LOWER(COALESCE(guest_email, '')) = ?
                  AND LOWER(COALESCE(release_date, '')) = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (guest_email, release_date),
            ),
            (
                guest_name and topic and interview_date,
                """
                SELECT id FROM episodes
                WHERE LOWER(COALESCE(guest_name, '')) = ?
                  AND LOWER(COALESCE(topic, '')) = ?
                  AND LOWER(COALESCE(interview_date, '')) = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (guest_name, topic, interview_date),
            ),
            (
                guest_name and episode_title and interview_date,
                """
                SELECT id FROM episodes
                WHERE LOWER(COALESCE(guest_name, '')) = ?
                  AND LOWER(COALESCE(episode_title, '')) = ?
                  AND LOWER(COALESCE(interview_date, '')) = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (guest_name, episode_title, interview_date),
            ),
            (
                source_file_name and guest_name and release_date,
                """
                SELECT id FROM episodes
                WHERE LOWER(COALESCE(source_file_name, '')) = ?
                  AND LOWER(COALESCE(guest_name, '')) = ?
                  AND LOWER(COALESCE(release_date, '')) = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (source_file_name, guest_name, release_date),
            ),
            (
                source_file_name and guest_name and topic and interview_date,
                """
                SELECT id FROM episodes
                WHERE LOWER(COALESCE(source_file_name, '')) = ?
                  AND LOWER(COALESCE(guest_name, '')) = ?
                  AND LOWER(COALESCE(topic, '')) = ?
                  AND LOWER(COALESCE(interview_date, '')) = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (source_file_name, guest_name, topic, interview_date),
            ),
        ]

        for should_run, query, params in lookup_paths:
            if not should_run:
                continue
            cursor = conn.execute(query, params)
            row = cursor.fetchone()
            if row:
                return row

        return None

    def _episode_duplicate_key_groups(self, episode_rows: List[Dict[str, Any]]) -> List[List[Dict[str, Any]]]:
        """Group likely duplicate episodes using strong import/archive identity keys."""
        active_rows = list(episode_rows)
        groups: List[List[Dict[str, Any]]] = []

        def normalized_key(parts: List[Optional[str]]) -> tuple[str, ...]:
            return tuple(_normalized_episode_identity(part) for part in parts)

        for key_builder in (
            lambda row: ("legacy",) + normalized_key([row.get("legacy_episode_number")]),
            lambda row: ("guest_release",) + normalized_key([row.get("guest_name"), row.get("release_date")]),
            lambda row: ("email_interview",) + normalized_key([row.get("guest_email"), row.get("interview_date")]),
            lambda row: ("guest_topic_interview",) + normalized_key([row.get("guest_name"), row.get("topic"), row.get("interview_date")]),
            lambda row: ("guest_title_interview",) + normalized_key([row.get("guest_name"), row.get("episode_title"), row.get("interview_date")]),
            lambda row: ("guest_interview",) + normalized_key([row.get("guest_name"), row.get("interview_date")]),
        ):
            grouped: Dict[tuple[str, ...], List[Dict[str, Any]]] = {}
            for row in active_rows:
                key = key_builder(row)
                if any(not part for part in key[1:]):
                    continue
                grouped.setdefault(key, []).append(row)

            duplicate_ids: set[int] = set()
            for key, rows in grouped.items():
                if len(rows) > 1:
                    if key[0] == "guest_interview" and not any(_episode_title_is_placeholder(row) for row in rows):
                        continue
                    groups.append(rows)
                    duplicate_ids.update(int(row["id"]) for row in rows)

            if duplicate_ids:
                active_rows = [row for row in active_rows if int(row["id"]) not in duplicate_ids]

        return groups

    def _episode_canonical_score(self, row: Dict[str, Any]) -> tuple[int, int]:
        """Score episode rows so cleanup keeps the strongest canonical record."""
        score = 0
        if _episode_row_text(row, "legacy_episode_number"):
            score += 100
        if _episode_row_text(row, "guest_email"):
            score += 12
        if _episode_row_text(row, "website"):
            score += 6
        if _episode_row_text(row, "topic"):
            score += 12
        if _episode_row_text(row, "category"):
            score += 8
        if _episode_row_text(row, "interview_date"):
            score += 6
        if _episode_row_text(row, "release_date"):
            score += 6
        if _episode_row_text(row, "show_notes_url"):
            score += 10
        if _episode_row_text(row, "release_files_url"):
            score += 10
        if _episode_row_text(row, "transcript_text"):
            score += 18
        if _episode_row_text(row, "source_file_name"):
            score += 4
        if _episode_row_text(row, "episode_title") and not _episode_title_is_placeholder(row):
            score += 5
        if _normalized_episode_identity(row.get("source_type")) in {"released_archive", "release_queue"}:
            score += 8
        score += _episode_status_rank(_episode_row_text(row, "release_status"), kind="release") * 3
        score += _episode_status_rank(_episode_row_text(row, "production_status"), kind="production") * 2
        score += _episode_status_rank(_episode_row_text(row, "promotion_status"), kind="promotion")
        return score, -int(row["id"])

    def _best_episode_text_value(self, rows: List[Dict[str, Any]], key: str) -> str:
        """Pick the most trustworthy non-empty text value for a merged episode field."""
        sorted_rows = sorted(rows, key=self._episode_canonical_score, reverse=True)
        for row in sorted_rows:
            value = _episode_row_text(row, key)
            if value:
                return value
        return ""

    def _best_episode_long_text_value(self, rows: List[Dict[str, Any]], key: str) -> str:
        """Pick the richest long-form value while keeping the strongest row as tiebreaker."""
        candidates = []
        for row in rows:
            value = _episode_row_text(row, key)
            if value:
                score, inverse_id = self._episode_canonical_score(row)
                candidates.append((len(value), score, inverse_id, value))
        if not candidates:
            return ""
        candidates.sort(reverse=True)
        return candidates[0][3]

    def _merge_duplicate_episode_rows(self, rows: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Merge duplicate episode rows into a single conservative canonical record."""
        canonical = dict(max(rows, key=self._episode_canonical_score))
        canonical["guest_id"] = canonical.get("guest_id")
        canonical["interview_id"] = canonical.get("interview_id")
        canonical["guest_name"] = self._best_episode_text_value(rows, "guest_name")
        canonical["guest_email"] = self._best_episode_text_value(rows, "guest_email")
        canonical["website"] = self._best_episode_text_value(rows, "website")
        canonical["episode_title"] = self._best_episode_text_value(rows, "episode_title")
        canonical["working_title"] = self._best_episode_text_value(rows, "working_title") or canonical["episode_title"]
        canonical["published_title"] = self._best_episode_text_value(rows, "published_title")
        canonical["topic"] = self._best_episode_text_value(rows, "topic")
        canonical["category"] = self._best_episode_text_value(rows, "category")
        canonical["interview_date"] = self._best_episode_text_value(rows, "interview_date")
        canonical["recording_date"] = self._best_episode_text_value(rows, "recording_date")
        canonical["release_date"] = self._best_episode_text_value(rows, "release_date")
        canonical["legacy_episode_number"] = self._best_episode_text_value(rows, "legacy_episode_number")
        canonical["riverside_status"] = self._best_episode_text_value(rows, "riverside_status")
        canonical["source_file_name"] = self._best_episode_text_value(rows, "source_file_name")
        canonical["source_type"] = self._best_episode_text_value(rows, "source_type")
        canonical["show_notes_url"] = self._best_episode_text_value(rows, "show_notes_url")
        canonical["release_files_url"] = self._best_episode_text_value(rows, "release_files_url")
        canonical["transcript_text"] = self._best_episode_long_text_value(rows, "transcript_text")
        canonical["transcript_source_id"] = self._best_episode_text_value(rows, "transcript_source_id")
        canonical["transcript_synced_at"] = self._best_episode_text_value(rows, "transcript_synced_at")
        canonical["transcript_match_method"] = self._best_episode_text_value(rows, "transcript_match_method")
        canonical["transcript_match_score"] = max(float(row.get("transcript_match_score") or 0) for row in rows)
        canonical["outreach_plan"] = self._best_episode_long_text_value(rows, "outreach_plan")
        canonical["notes"] = self._best_episode_long_text_value(rows, "notes")
        canonical["recommendation_reason"] = self._best_episode_long_text_value(rows, "recommendation_reason")
        canonical["priority_score"] = max(float(row.get("priority_score") or 0) for row in rows)

        canonical["release_status"] = max(
            (_episode_row_text(row, "release_status") for row in rows),
            key=lambda value: _episode_status_rank(value, kind="release"),
            default="unplanned",
        )
        canonical["production_status"] = max(
            (_episode_row_text(row, "production_status") for row in rows),
            key=lambda value: _episode_status_rank(value, kind="production"),
            default="idea",
        )
        canonical["promotion_status"] = max(
            (_episode_row_text(row, "promotion_status") for row in rows),
            key=lambda value: _episode_status_rank(value, kind="promotion"),
            default="unknown",
        )
        return canonical

    def list_episodes(self) -> List[Dict]:
        """Return all episodes ordered by planned release date."""
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                """
                SELECT * FROM episodes
                ORDER BY
                    CASE WHEN release_date IS NULL THEN 1 ELSE 0 END,
                    datetime(release_date) ASC,
                    id DESC
                """
            )
            return [dict(row) for row in cursor.fetchall()]

    def list_episode_categories(self) -> List[str]:
        """Return known episode categories ordered by how often they appear."""
        with self._connect() as conn:
            cursor = conn.execute(
                """
                SELECT category, COUNT(*) AS usage_count
                FROM episodes
                WHERE TRIM(COALESCE(category, '')) <> ''
                GROUP BY category
                ORDER BY usage_count DESC, LOWER(category) ASC
                """
            )
            return [row[0] for row in cursor.fetchall()]

    def get_episode_by_id(self, episode_id: int) -> Optional[Dict]:
        """Fetch a single episode by id."""
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("SELECT * FROM episodes WHERE id = ?", (episode_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_episode_by_interview_id(self, interview_id: int) -> Optional[Dict]:
        """Fetch the episode linked to an interview, if one exists."""
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("SELECT * FROM episodes WHERE interview_id = ? LIMIT 1", (interview_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def delete_episode(self, episode_id: int) -> None:
        """Delete an episode from the database."""
        with self._connect() as conn:
            conn.execute("DELETE FROM episodes WHERE id = ?", (episode_id,))
            conn.commit()

    def log_reminder(self, interview_id: int, reminder_type: str, sent_to: str, status: str, provider: str = "", notes: str = "") -> int:
        """Record a reminder attempt for an interview."""
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO reminder_log (interview_id, reminder_type, sent_to, provider, status, notes)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (interview_id, reminder_type, sent_to, provider, status, notes),
            )
            conn.execute(
                """
                UPDATE interviews
                SET reminder_status = ?, reminder_sent_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (status, interview_id),
            )
            conn.commit()
            return cursor.lastrowid

    def log_interview_email(self, interview_id: int, email_type: str, sent_to: str, status: str, provider: str = "", notes: str = "") -> int:
        """Record a non-reminder interview email without mutating reminder status."""
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO reminder_log (interview_id, reminder_type, sent_to, provider, status, notes)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (interview_id, email_type, sent_to, provider, status, notes),
            )
            conn.commit()
            return cursor.lastrowid

    def enqueue_email_outbox(
        self,
        *,
        interview_id: Optional[int],
        email_type: str,
        sent_to: str,
        subject: str,
        body: str,
        attachments_json: str = "",
        provider: str = "",
        max_attempts: int = 5,
        next_attempt_at: Optional[str] = None,
        status: str = "pending",
        last_error: str = "",
        idempotency_key: str = "",
        correlation_id: str = "",
    ) -> int:
        """Store an email for later retry when delivery is temporarily unavailable."""
        status = validate_state("communication", status)
        idempotency_key = str(idempotency_key or f"generated:{uuid4().hex}").strip()
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO email_outbox (
                    interview_id, email_type, sent_to, subject, body, attachments_json,
                    provider, status, attempts, max_attempts, next_attempt_at, last_error,
                    idempotency_key, correlation_id, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                ON CONFLICT(idempotency_key) DO NOTHING
                """,
                (
                    interview_id,
                    email_type,
                    sent_to,
                    subject,
                    body,
                    attachments_json or None,
                    provider,
                    status,
                    0,
                    max(1, int(max_attempts)),
                    next_attempt_at or None,
                    last_error or "",
                    idempotency_key,
                    correlation_id or None,
                ),
            )
            if cursor.rowcount == 0:
                existing = conn.execute(
                    "SELECT id FROM email_outbox WHERE idempotency_key = ?", (idempotency_key,)
                ).fetchone()
                if not existing:
                    raise RuntimeError("Idempotent outbox insert could not be resolved")
                conn.commit()
                return int(existing[0])
            conn.commit()
            return int(cursor.lastrowid)

    def claim_due_email_outbox(
        self,
        *,
        worker_id: str,
        limit: int = 20,
        lease_seconds: int = 120,
    ) -> List[Dict]:
        """Atomically lease due messages so only one worker can deliver them."""
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            conn.execute("BEGIN IMMEDIATE")
            rows = conn.execute(
                """SELECT * FROM email_outbox
                   WHERE (
                         status IN ('pending', 'retrying')
                         AND COALESCE(next_attempt_at, CURRENT_TIMESTAMP) <= CURRENT_TIMESTAMP
                         AND (lease_until IS NULL OR lease_until <= CURRENT_TIMESTAMP)
                       ) OR (
                         status = 'sending' AND lease_until <= CURRENT_TIMESTAMP
                       )
                   ORDER BY next_attempt_at ASC, id ASC LIMIT ?""",
                (max(1, int(limit)),),
            ).fetchall()
            claimed: List[Dict] = []
            for row in rows:
                validate_transition("communication", row["status"], "sending")
                cursor = conn.execute(
                    """UPDATE email_outbox
                       SET status = 'sending', lease_owner = ?,
                           lease_until = datetime('now', ?), row_version = row_version + 1,
                           updated_at = CURRENT_TIMESTAMP
                       WHERE id = ? AND row_version = ?
                         AND (
                           status IN ('pending', 'retrying')
                           OR (status = 'sending' AND lease_until <= CURRENT_TIMESTAMP)
                         )""",
                    (worker_id, f"+{max(1, int(lease_seconds))} seconds", row["id"], row["row_version"]),
                )
                if cursor.rowcount == 1:
                    claimed.append(
                        dict(conn.execute("SELECT * FROM email_outbox WHERE id = ?", (row["id"],)).fetchone())
                    )
            conn.commit()
            return claimed

    def get_due_email_outbox(self, limit: int = 20) -> List[Dict]:
        """Return queued emails that are ready for another delivery attempt."""
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                """
                SELECT *
                FROM email_outbox
                WHERE status IN ('pending', 'retrying')
                  AND COALESCE(next_attempt_at, CURRENT_TIMESTAMP) <= CURRENT_TIMESTAMP
                ORDER BY next_attempt_at ASC, id ASC
                LIMIT ?
                """,
                (max(1, int(limit)),),
            )
            return [dict(row) for row in cursor.fetchall()]

    def mark_email_outbox_sent(self, outbox_id: int, *, worker_id: str = "") -> None:
        """Mark a queued email as delivered."""
        with self._connect() as conn:
            current = conn.execute("SELECT status FROM email_outbox WHERE id = ?", (outbox_id,)).fetchone()
            if not current:
                raise ValueError("Outbox message not found")
            validate_transition("communication", current[0], "sent")
            conn.execute(
                """
                UPDATE email_outbox
                SET status = 'sent',
                    attempts = attempts + 1,
                    last_error = NULL,
                    sent_at = CURRENT_TIMESTAMP,
                    lease_owner = NULL,
                    lease_until = NULL,
                    row_version = row_version + 1,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ? AND (? = '' OR lease_owner = ?)
                """,
                (outbox_id, worker_id, worker_id),
            )
            attempt_number = int(conn.execute("SELECT attempts FROM email_outbox WHERE id = ?", (outbox_id,)).fetchone()[0])
            conn.execute(
                """INSERT INTO email_outbox_attempts
                   (outbox_id, attempt_number, worker_id, status) VALUES (?, ?, ?, 'sent')""",
                (outbox_id, attempt_number, worker_id or None),
            )
            conn.commit()

    def mark_email_outbox_retry(
        self,
        outbox_id: int,
        *,
        attempts: int,
        next_attempt_at: str,
        last_error: str,
        status: str = "retrying",
        worker_id: str = "",
    ) -> None:
        """Update a queued email after a failed attempt."""
        with self._connect() as conn:
            current = conn.execute("SELECT status FROM email_outbox WHERE id = ?", (outbox_id,)).fetchone()
            if not current:
                raise ValueError("Outbox message not found")
            status = validate_transition("communication", current[0], status)
            conn.execute(
                """
                UPDATE email_outbox
                SET status = ?,
                    attempts = ?,
                    next_attempt_at = ?,
                    last_error = ?,
                    dead_letter_at = CASE WHEN ? = 'dead_letter' THEN CURRENT_TIMESTAMP ELSE dead_letter_at END,
                    lease_owner = NULL,
                    lease_until = NULL,
                    row_version = row_version + 1,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ? AND (? = '' OR lease_owner = ?)
                """,
                (status, attempts, next_attempt_at, last_error, status, outbox_id, worker_id, worker_id),
            )
            conn.execute(
                """INSERT INTO email_outbox_attempts
                   (outbox_id, attempt_number, worker_id, status, error)
                   VALUES (?, ?, ?, ?, ?)""",
                (outbox_id, attempts, worker_id or None, status, last_error or None),
            )
            conn.commit()

    def get_email_outbox_health(self) -> Dict[str, int]:
        """Return operator-facing queue health counts."""
        with self._connect() as conn:
            rows = conn.execute("SELECT status, COUNT(*) FROM email_outbox GROUP BY status").fetchall()
            health = {str(status): int(count) for status, count in rows}
            health["overdue"] = int(
                conn.execute(
                    """SELECT COUNT(*) FROM email_outbox
                       WHERE status IN ('pending', 'retrying') AND next_attempt_at < datetime('now', '-5 minutes')"""
                ).fetchone()[0]
            )
            return health

    def list_email_outbox_failures(self, limit: int = 50) -> List[Dict]:
        """Return delivery metadata for operator review without message bodies."""
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """SELECT id, interview_id, email_type, sent_to, subject, provider,
                          status, attempts, max_attempts, last_error, created_at,
                          updated_at, dead_letter_at, correlation_id, row_version
                   FROM email_outbox
                   WHERE status IN ('failed', 'dead_letter')
                   ORDER BY COALESCE(dead_letter_at, updated_at) DESC, id DESC LIMIT ?""",
                (max(1, int(limit)),),
            ).fetchall()
            return [dict(row) for row in rows]

    def list_booking_confirmation_preflight_failures(self, limit: int = 50) -> List[Dict]:
        """Return booking emails that could not enter the delivery pipeline.

        An outbox item without a usable recipient must never be retried
        automatically. A later successful manual confirmation clears this alert.
        """
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """SELECT log.id, log.interview_id, log.reminder_type AS email_type,
                          log.sent_to, '' AS subject, log.provider, log.status,
                          0 AS attempts, 0 AS max_attempts, log.notes AS last_error,
                          log.sent_at AS created_at, log.sent_at AS updated_at,
                          NULL AS dead_letter_at, NULL AS correlation_id,
                          0 AS row_version, 'preflight' AS failure_source
                   FROM reminder_log AS log
                   WHERE log.reminder_type = 'booking_confirmation'
                     AND log.status = 'unavailable'
                     AND NOT EXISTS (
                         SELECT 1 FROM reminder_log AS later
                         WHERE later.interview_id = log.interview_id
                           AND later.reminder_type = 'booking_confirmation'
                           AND later.status = 'sent'
                           AND later.id > log.id
                     )
                   ORDER BY log.id DESC LIMIT ?""",
                (max(1, int(limit)),),
            ).fetchall()
            return [dict(row) for row in rows]

    def retry_dead_letter_email(self, outbox_id: int) -> Dict[str, Any]:
        """Return one terminal failure to the retry queue after operator review."""
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            current_row = conn.execute("SELECT * FROM email_outbox WHERE id = ?", (outbox_id,)).fetchone()
            if not current_row:
                raise ValueError("Outbox message not found")
            current = dict(current_row)
            validate_transition("communication", current["status"], "retrying")
            cursor = conn.execute(
                """UPDATE email_outbox
                   SET status = 'retrying', next_attempt_at = CURRENT_TIMESTAMP,
                       last_error = NULL, dead_letter_at = NULL,
                       lease_owner = NULL, lease_until = NULL,
                       row_version = row_version + 1, updated_at = CURRENT_TIMESTAMP
                   WHERE id = ? AND row_version = ?""",
                (outbox_id, current["row_version"]),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("Outbox message was changed by another request")
            updated = dict(conn.execute("SELECT * FROM email_outbox WHERE id = ?", (outbox_id,)).fetchone())
            self._append_audit_event_conn(
                conn,
                entity_type="communication",
                entity_id=outbox_id,
                event_type="dead_letter_retried",
                actor="operator",
                source="operations",
                before=current,
                after=updated,
            )
            conn.commit()
            return updated

    def start_automation_run(self, automation_type: str, *, worker_id: str = "", correlation_id: str = "") -> int:
        """Record the start of an observable automation execution."""
        with self._connect() as conn:
            cursor = conn.execute(
                """INSERT INTO automation_runs (automation_type, correlation_id, worker_id, status)
                   VALUES (?, ?, ?, 'running')""",
                (automation_type, correlation_id or None, worker_id or None),
            )
            conn.commit()
            return int(cursor.lastrowid)

    def finish_automation_run(
        self,
        run_id: int,
        *,
        status: str,
        checked: int = 0,
        succeeded: int = 0,
        failed: int = 0,
        details: Any = None,
    ) -> None:
        """Finalize automation metrics for operational review."""
        with self._connect() as conn:
            cursor = conn.execute(
                """UPDATE automation_runs
                   SET status = ?, checked_count = ?, succeeded_count = ?, failed_count = ?,
                       details_json = ?, finished_at = CURRENT_TIMESTAMP
                   WHERE id = ? AND finished_at IS NULL""",
                (
                    status,
                    int(checked),
                    int(succeeded),
                    int(failed),
                    dumps(details, ensure_ascii=False, default=str, sort_keys=True) if details is not None else None,
                    run_id,
                ),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("Automation run was already finalized or does not exist")
            conn.commit()

    def get_email_outbox_count(self) -> int:
        """Return the number of pending or retryable queued emails."""
        with self._connect() as conn:
            cursor = conn.execute(
                "SELECT COUNT(*) FROM email_outbox WHERE status IN ('pending', 'retrying')"
            )
            return int(cursor.fetchone()[0])

    def get_reminder_log(self, interview_id: Optional[int] = None) -> List[Dict]:
        """Return reminder log entries, optionally for a single interview."""
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            if interview_id is None:
                cursor = conn.execute("SELECT * FROM reminder_log ORDER BY sent_at DESC, id DESC")
            else:
                cursor = conn.execute(
                    "SELECT * FROM reminder_log WHERE interview_id = ? ORDER BY sent_at DESC, id DESC",
                    (interview_id,),
                )
            return [dict(row) for row in cursor.fetchall()]

    def get_operations_stats(self) -> Dict[str, int]:
        """Return a small summary of podcast operations records."""
        with self._connect() as conn:
            interviews_total = conn.execute("SELECT COUNT(*) FROM interviews").fetchone()[0]
            interviews_pending_confirmation = conn.execute(
                "SELECT COUNT(*) FROM interviews WHERE confirmation_status = 'pending'"
            ).fetchone()[0]
            episodes_total = conn.execute("SELECT COUNT(*) FROM episodes").fetchone()[0]
            episodes_scheduled = conn.execute(
                "SELECT COUNT(*) FROM episodes WHERE release_status = 'scheduled'"
            ).fetchone()[0]
            reminders_sent = conn.execute("SELECT COUNT(*) FROM reminder_log").fetchone()[0]

        return {
            "interviews_total": interviews_total,
            "interviews_pending_confirmation": interviews_pending_confirmation,
            "episodes_total": episodes_total,
            "episodes_scheduled": episodes_scheduled,
            "reminders_sent": reminders_sent,
        }
    
    # ==================== Status Management ====================
    
    def mark_guest_processed(self, guest_id: int) -> None:
        """Mark a guest as processed."""
        self._update_guest_lifecycle(guest_id, is_processed=True, event_type="marked_processed")
    
    def mark_guest_unprocessed(self, guest_id: int) -> None:
        """Mark a guest as unprocessed."""
        self._update_guest_lifecycle(guest_id, is_processed=False, event_type="marked_unprocessed")
    
    def accept_guest_with_email(self, guest_id: int, custom_message: str = "") -> None:
        """Mark guest as accepted and record email sent."""
        self._update_guest_lifecycle(
            guest_id,
            is_processed=True,
            email_status="accepted",
            email_sent_at=datetime.now(timezone.utc).isoformat(),
            event_type="accepted_email_sent",
            reason=custom_message,
        )
    
    def reject_guest_with_email(self, guest_id: int, custom_message: str = "") -> None:
        """Mark guest as rejected and record email sent."""
        self._update_guest_lifecycle(
            guest_id,
            is_processed=True,
            email_status="rejected",
            email_sent_at=datetime.now(timezone.utc).isoformat(),
            event_type="declined_email_sent",
            reason=custom_message,
        )

    def accept_guest_without_email(self, guest_id: int) -> None:
        """Mark guest as accepted without sending an email."""
        self._update_guest_lifecycle(
            guest_id, is_processed=True, email_status="accepted", email_sent_at=None, event_type="accepted"
        )

    def reject_guest_without_email(self, guest_id: int) -> None:
        """Mark guest as rejected without sending an email."""
        self._update_guest_lifecycle(
            guest_id, is_processed=True, email_status="rejected", email_sent_at=None, event_type="declined"
        )
    
    def skip_guest(self, guest_id: int, reason: str = "") -> None:
        """Mark guest as skipped without sending email."""
        self._update_guest_lifecycle(
            guest_id, is_processed=True, email_status="skipped", skip_reason=reason, event_type="skipped", reason=reason
        )

    def _update_guest_lifecycle(
        self,
        guest_id: int,
        *,
        is_processed: bool,
        event_type: str,
        email_status: Any = ...,
        email_sent_at: Any = ...,
        skip_reason: Any = ...,
        reason: str = "",
    ) -> None:
        """Apply an attributed, optimistic guest lifecycle projection update."""
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM guests WHERE id = ?", (guest_id,)).fetchone()
            if not row:
                raise ValueError("Guest not found")
            before = dict(row)
            updates = {"is_processed": bool(is_processed)}
            if email_status is not ...:
                updates["email_status"] = email_status
            if email_sent_at is not ...:
                updates["email_sent_at"] = email_sent_at
            if skip_reason is not ...:
                updates["skip_reason"] = skip_reason
            assignments = ", ".join(f"{column} = ?" for column in updates)
            cursor = conn.execute(
                f"""UPDATE guests SET {assignments}, row_version = row_version + 1,
                       updated_at = CURRENT_TIMESTAMP WHERE id = ? AND row_version = ?""",
                (*updates.values(), guest_id, before["row_version"]),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("Guest was changed by another request")
            after = dict(conn.execute("SELECT * FROM guests WHERE id = ?", (guest_id,)).fetchone())
            self._append_audit_event_conn(
                conn,
                entity_type="guest",
                entity_id=guest_id,
                event_type=event_type,
                actor="operator",
                source="guest_dashboard",
                reason=reason,
                before=before,
                after=after,
            )
            conn.commit()
    
    # ==================== Statistics ====================
    
    def get_stats(self) -> Dict[str, int]:
        """Get guest statistics."""
        with self._connect() as conn:
            cursor = conn.execute("""
                SELECT 
                    COUNT(*) as total,
                    SUM(CASE WHEN is_processed = 1 THEN 1 ELSE 0 END) as processed,
                    SUM(CASE WHEN is_processed = 0 THEN 1 ELSE 0 END) as unprocessed
                FROM guests
            """)
            row = cursor.fetchone()
            return {
                "total": row[0] or 0,
                "processed": row[1] or 0,
                "unprocessed": row[2] or 0
            }
    
    def get_email_stats(self) -> Dict[str, int]:
        """Get email-related statistics."""
        with self._connect() as conn:
            cursor = conn.execute("""
                SELECT 
                    COUNT(CASE WHEN email_status IS NOT NULL THEN 1 END) as total_emails,
                    COUNT(CASE WHEN email_status = 'accepted' THEN 1 END) as accepted_emails,
                    COUNT(CASE WHEN email_status = 'rejected' THEN 1 END) as rejected_emails,
                    COUNT(CASE WHEN email_status = 'skipped' THEN 1 END) as skipped_guests
                FROM guests
            """)
            row = cursor.fetchone()
            return {
                "total_emails": row[0] or 0,
                "accepted_emails": row[1] or 0,
                "rejected_emails": row[2] or 0,
                "skipped_guests": row[3] or 0
            }
    
    # ==================== Import Operations ====================
    
    def import_from_file(self, file_path: str, encoding: str = 'utf-8', source_name: Optional[str] = None) -> Dict[str, int]:
        """
        Import guest data from CSV or Excel file.
        
        Args:
            file_path: Path to the file
            encoding: Encoding for CSV files
            
        Returns:
            Dictionary with import statistics
        """
        stats = {'imported': 0, 'updated': 0, 'skipped': 0, 'errors': 0}
        
        # Read file
        df = self.file_reader.read_file(file_path, encoding)
        if df is None or df.empty:
            logger.error("Could not read file or file is empty")
            stats['errors'] += 1
            return stats
        
        logger.info("Read file with %d rows and columns: %s", len(df), list(df.columns))
        
        # Process each row
        for index, row in df.iterrows():
            try:
                if not _row_has_non_empty_values(row):
                    logger.info("Row %d: Skipped blank row", index + 1)
                    stats['skipped'] += 1
                    continue

                guest_data = self.mapper.clean_guest_data(row)
                guest_data['original_file_name'] = Path(source_name or file_path).name
                guest_data['original_data'] = dumps(
                    _clean_import_row_dict(row.fillna("").to_dict()),
                    ensure_ascii=False,
                    default=str,
                )
                
                # Validate data
                is_valid, error_msg = self.mapper.validate_guest_data(guest_data)
                if not is_valid:
                    logger.warning("Row %d: %s", index + 1, error_msg)
                    stats['skipped'] += 1
                    continue
                
                # Check if guest exists
                existing_guest = self.find_existing_guest(guest_data)
                
                if existing_guest:
                    # Update existing guest while preserving status
                    if guest_data.get("marketing_opt_in") is None:
                        guest_data["marketing_opt_in"] = existing_guest.get("marketing_opt_in", False)
                    guest_data['is_processed'] = existing_guest['is_processed']
                    guest_data['email_status'] = existing_guest.get('email_status')
                    guest_data['email_sent_at'] = existing_guest.get('email_sent_at')
                    guest_data['skip_reason'] = existing_guest.get('skip_reason')
                    guest_data['original_file_name'] = _prefer_existing_metadata(
                        existing_guest.get('original_file_name'),
                        guest_data.get('original_file_name'),
                    )
                    guest_data['original_data'] = _prefer_existing_metadata(
                        existing_guest.get('original_data'),
                        guest_data.get('original_data'),
                    )
                    
                    # Update email if new one is better
                    if self.mapper.should_update_email(existing_guest['email'], guest_data['email']):
                        logger.info("Row %d: Updating email for %s", index + 1, guest_data['full_name'])
                    
                    self.update_guest_by_id(existing_guest['id'], guest_data)
                    stats['updated'] += 1
                    logger.info("Row %d: Updated guest %s", index + 1, guest_data['full_name'])
                else:
                    guest_id, action = self.upsert_guest(guest_data)
                    if action == "updated":
                        stats['updated'] += 1
                        logger.info("Row %d: Matched and updated guest %s (id=%s)", index + 1, guest_data['full_name'], guest_id)
                    else:
                        stats['imported'] += 1
                        logger.info("Row %d: Imported new guest %s", index + 1, guest_data['full_name'])
                    
            except Exception as e:
                logger.error("Row %d: Error processing row - %s", index + 1, e)
                stats['errors'] += 1
                continue
        
        logger.info("Import completed. Stats: %s", stats)
        return stats
    
    # Legacy method names for compatibility
    def import_from_csv(self, file_path: str, encoding: str = 'utf-8') -> Dict[str, int]:
        """Import from CSV (legacy method, calls import_from_file)."""
        return self.import_from_file(file_path, encoding)
    
    def import_from_excel(self, file_path: str) -> Dict[str, int]:
        """Import from Excel (legacy method, calls import_from_file)."""
        return self.import_from_file(file_path)
    
    def add_guest_from_csv(self, file_path: str, encoding: str = 'utf-8') -> Dict[str, int]:
        """Add guests from CSV (legacy method, calls import_from_file)."""
        return self.import_from_file(file_path, encoding)
    
    def get_guest_stats(self) -> Dict[str, int]:
        """Get guest statistics (legacy method, calls get_stats)."""
        return self.get_stats()
    
    def clean_database(self) -> Dict[str, int]:
        """
        Clean database by removing duplicates and fixing data issues.
        
        Returns:
            Dictionary with cleanup statistics
        """
        stats = {'removed': 0, 'fixed': 0, 'episodes_removed': 0, 'episodes_merged': 0}
        
        with self._connect() as conn:
            # Find and remove duplicate guests (same name and email)
            cursor = conn.execute("""
                SELECT full_name, email, COUNT(*) as count, GROUP_CONCAT(id) as ids
                FROM guests
                WHERE full_name IS NOT NULL AND email IS NOT NULL
                GROUP BY LOWER(full_name), LOWER(email)
                HAVING count > 1
            """)
            
            for row in cursor.fetchall():
                ids = [int(id_str) for id_str in row[3].split(',')]
                # Keep the first one (oldest), delete the rest
                for guest_id in ids[1:]:
                    conn.execute("DELETE FROM guests WHERE id = ?", (guest_id,))
                    stats['removed'] += 1
            
            # Fix any NULL values in critical fields
            conn.execute("""
                UPDATE guests 
                SET is_processed = FALSE 
                WHERE is_processed IS NULL
            """)
            stats['fixed'] += conn.total_changes

            conn.row_factory = sqlite3.Row
            episode_rows = [dict(row) for row in conn.execute("SELECT * FROM episodes ORDER BY id ASC").fetchall()]
            for group in self._episode_duplicate_key_groups(episode_rows):
                merged = self._merge_duplicate_episode_rows(group)
                keep_id = int(merged["id"])
                fields = (
                    merged.get("guest_id"),
                    merged.get("interview_id"),
                    merged.get("guest_name"),
                    merged.get("guest_email"),
                    merged.get("website"),
                    merged.get("episode_title"),
                    merged.get("working_title") or merged.get("episode_title"),
                    merged.get("published_title"),
                    merged.get("topic"),
                    merged.get("category"),
                    merged.get("interview_date"),
                    merged.get("recording_date"),
                    merged.get("release_date"),
                    merged.get("release_status", "unplanned"),
                    merged.get("production_status", "idea"),
                    merged.get("promotion_status", "unknown"),
                    merged.get("priority_score", 0),
                    merged.get("recommendation_reason"),
                    merged.get("legacy_episode_number"),
                    merged.get("riverside_status"),
                    merged.get("source_file_name"),
                    merged.get("source_type"),
                    merged.get("show_notes_url"),
                    merged.get("release_files_url"),
                    merged.get("transcript_text"),
                    merged.get("transcript_source_id"),
                    merged.get("transcript_synced_at"),
                    merged.get("transcript_match_method"),
                    merged.get("transcript_match_score"),
                    merged.get("outreach_plan"),
                    merged.get("ai_monthly_angle_state"),
                    merged.get("ai_monthly_angle_theme"),
                    merged.get("notes"),
                    merged.get("owner"),
                    merged.get("editorial_disposition", "active"),
                    merged.get("original_planned_release_date"),
                    keep_id,
                )
                conn.execute(
                    """
                    UPDATE episodes SET
                        guest_id = ?, interview_id = ?, guest_name = ?, guest_email = ?, website = ?, episode_title = ?, working_title = ?, published_title = ?,
                        topic = ?, category = ?, interview_date = ?, recording_date = ?, release_date = ?,
                        release_status = ?, production_status = ?, promotion_status = ?, priority_score = ?, recommendation_reason = ?,
                        legacy_episode_number = ?, riverside_status = ?, source_file_name = ?, source_type = ?,
                        show_notes_url = ?, release_files_url = ?, transcript_text = ?, transcript_source_id = ?, transcript_synced_at = ?,
                        transcript_match_method = ?, transcript_match_score = ?, outreach_plan = ?, ai_monthly_angle_state = ?,
                        ai_monthly_angle_theme = ?, notes = ?, owner = ?, editorial_disposition = ?, original_planned_release_date = ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    fields,
                )
                duplicate_ids = [int(row["id"]) for row in group if int(row["id"]) != keep_id]
                for duplicate_id in duplicate_ids:
                    conn.execute("DELETE FROM episodes WHERE id = ?", (duplicate_id,))
                    stats["episodes_removed"] += 1
                if duplicate_ids:
                    stats["episodes_merged"] += 1

            conn.commit()

        logger.info("Database cleaned. Stats: %s", stats)
        return stats
