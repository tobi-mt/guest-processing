import logging
import sqlite3
from json import dumps, loads
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

try:
    from .constants import DEFAULT_DB_PATH
    from .data_mapper import DataMapper
    from .file_reader import FileReader
    from .schema_manager import SchemaManager
except ImportError as exc:
    if "attempted relative import" not in str(exc):
        raise
    from constants import DEFAULT_DB_PATH
    from data_mapper import DataMapper
    from file_reader import FileReader
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
    
    # ==================== CRUD Operations ====================
    
    def insert_guest(self, guest_data: Dict[str, Any]) -> int:
        """Insert a new guest into the database."""
        with sqlite3.connect(str(self.db_path)) as conn:
            cursor = conn.execute("""
                INSERT INTO guests (
                    name, full_name, email, website, social_media_handles, 
                    background, profession, motivation, life_experiences, core_values, 
                    faith_practice, beliefs_align, favorite_quote, passionate_topics, message_takeaway,
                    podcast_experience, additional_info, following_us, is_processed,
                    original_file_name, original_data, guest_research, guest_research_updated_at,
                    booking_token, booking_token_created_at, booking_override, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """, (
                guest_data.get('full_name'), guest_data.get('full_name'), guest_data.get('email'), 
                guest_data.get('website'), guest_data.get('social_handles'),
                guest_data.get('background'), guest_data.get('profession'), guest_data.get('motivation'), 
                guest_data.get('life_experiences'), guest_data.get('core_values'), guest_data.get('faith'), 
                guest_data.get('alignment'), guest_data.get('favorite_quote'), guest_data.get('passionate_topics'), 
                guest_data.get('message'), guest_data.get('experience'), guest_data.get('additional_info'), 
                guest_data.get('has_social_media'), guest_data.get('is_processed', False),
                guest_data.get('original_file_name'), guest_data.get('original_data'),
                guest_data.get('guest_research'), guest_data.get('guest_research_updated_at'),
                guest_data.get('booking_token'), guest_data.get('booking_token_created_at'),
                guest_data.get('booking_override'),
            ))
            conn.commit()
            return cursor.lastrowid

    def find_existing_guest(self, guest_data: Dict[str, Any]) -> Optional[Dict]:
        """Find an existing guest using the best available identity fields."""
        full_name = _normalized_identity(guest_data.get("full_name"))
        email = _normalized_identity(guest_data.get("email"))

        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row

            if email and email != "anonymous":
                cursor = conn.execute(
                    """
                    SELECT * FROM guests
                    WHERE LOWER(COALESCE(email, '')) = ?
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
                    WHERE LOWER(COALESCE(full_name, name, '')) = ?
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
            existing_was_reviewed = bool(existing_guest.get("is_processed")) or bool(existing_guest.get("email_status"))
            if incoming_source == INTAKE_SOURCE_NAME and existing_was_reviewed:
                reopened_guest = dict(existing_guest)
                reopened_guest.update(guest_data)
                reopened_guest["full_name"] = guest_data.get("full_name") or existing_guest.get("full_name") or existing_guest.get("name")
                reopened_guest["email"] = (
                    guest_data.get("email")
                    if self.mapper.should_update_email(existing_guest.get("email"), guest_data.get("email"))
                    else existing_guest.get("email")
                )
                reopened_guest["is_processed"] = False
                reopened_guest["email_status"] = None
                reopened_guest["email_sent_at"] = None
                reopened_guest["skip_reason"] = None
                reopened_guest["original_file_name"] = guest_data.get("original_file_name")
                reopened_guest["original_data"] = guest_data.get("original_data")
                self.update_guest_by_id(existing_guest["id"], reopened_guest)
                return existing_guest["id"], "updated"

            merged_guest = dict(existing_guest)
            merged_guest.update(guest_data)
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
            self.update_guest_by_id(existing_guest["id"], merged_guest)
            return existing_guest["id"], "updated"

        return self.insert_guest(guest_data), "created"
    
    def update_guest_by_id(self, guest_id: int, guest_data: Dict[str, Any]) -> None:
        """Update an existing guest in the database by ID."""
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute("""
                UPDATE guests SET
                    name = ?, full_name = ?, email = ?, website = ?, social_media_handles = ?,
                    background = ?, profession = ?, motivation = ?, life_experiences = ?, 
                    core_values = ?, faith_practice = ?, beliefs_align = ?, favorite_quote = ?,
                    passionate_topics = ?, message_takeaway = ?, podcast_experience = ?, 
                    additional_info = ?, following_us = ?, is_processed = ?, email_status = ?,
                    email_sent_at = ?, skip_reason = ?, original_file_name = ?, original_data = ?,
                    guest_research = ?, guest_research_updated_at = ?, booking_token = ?, booking_token_created_at = ?,
                    booking_override = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (
                guest_data.get('full_name'), guest_data.get('full_name'), guest_data.get('email'), 
                guest_data.get('website'), guest_data.get('social_handles'), guest_data.get('background'), 
                guest_data.get('profession'), guest_data.get('motivation'), guest_data.get('life_experiences'), 
                guest_data.get('core_values'), guest_data.get('faith'), guest_data.get('alignment'), 
                guest_data.get('favorite_quote'), guest_data.get('passionate_topics'), guest_data.get('message'), 
                guest_data.get('experience'), guest_data.get('additional_info'), guest_data.get('has_social_media'), 
                guest_data.get('is_processed'), guest_data.get('email_status'),
                guest_data.get('email_sent_at'), guest_data.get('skip_reason'),
                guest_data.get('original_file_name'), guest_data.get('original_data'),
                guest_data.get('guest_research'), guest_data.get('guest_research_updated_at'),
                guest_data.get('booking_token'), guest_data.get('booking_token_created_at'),
                guest_data.get('booking_override'),
                guest_id
            ))
            conn.commit()
    
    def delete_guest(self, guest_id: int) -> None:
        """Delete a guest from the database."""
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute("DELETE FROM guests WHERE id = ?", (guest_id,))
            conn.commit()
    
    def get_guest_by_id(self, guest_id: int) -> Optional[Dict]:
        """Get a guest by ID."""
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("SELECT * FROM guests WHERE id = ?", (guest_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def get_guest_by_name(self, name: str) -> Optional[Dict]:
        """Get a guest by name (case-insensitive)."""
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT * FROM guests WHERE LOWER(full_name) = LOWER(?) LIMIT 1",
                (name,)
            )
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def get_all_guests(self) -> List[Dict]:
        """Get all guests."""
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("SELECT * FROM guests ORDER BY date_added DESC")
            return [dict(row) for row in cursor.fetchall()]

    def get_guest_by_booking_token(self, booking_token: str) -> Optional[Dict]:
        """Fetch a single guest by booking token."""
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT * FROM guests WHERE booking_token = ? LIMIT 1",
                (booking_token,),
            )
            row = cursor.fetchone()
            return dict(row) if row else None

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

        with sqlite3.connect(str(self.db_path)) as conn:
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
                interview_data.get("status", "scheduled"),
                interview_data.get("confirmation_status", "pending"),
                interview_data.get("reminder_status", "not_scheduled"),
                interview_data.get("reminder_sent_at"),
                interview_data.get("notes"),
            )

            if existing_row:
                conn.execute(
                    """
                    UPDATE interviews SET
                        guest_id = ?, guest_name = ?, guest_email = ?, calendar_event_id = ?, calendar_source = ?,
                        event_updated_at = ?, last_synced_at = ?, reschedule_token = ?, reschedule_token_created_at = ?, title = ?, scheduled_for = ?, timezone = ?,
                        join_url = ?, status = ?, confirmation_status = ?, reminder_status = ?,
                        reminder_sent_at = ?, notes = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    fields + (existing_row["id"],),
                )
                conn.commit()
                return existing_row["id"], "updated"

            cursor = conn.execute(
                """
                INSERT INTO interviews (
                    guest_id, guest_name, guest_email, calendar_event_id, calendar_source, event_updated_at,
                    last_synced_at, reschedule_token, reschedule_token_created_at, title, scheduled_for, timezone, join_url, status, confirmation_status,
                    reminder_status, reminder_sent_at, notes, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                """,
                fields,
            )
            conn.commit()
            return cursor.lastrowid, "created"

    def list_interviews(self) -> List[Dict]:
        """Return all interviews, newest scheduled items first."""
        with sqlite3.connect(str(self.db_path)) as conn:
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
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("SELECT * FROM interviews WHERE id = ?", (interview_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_interview_by_reschedule_token(self, reschedule_token: str) -> Optional[Dict]:
        """Fetch a single interview by reschedule token."""
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT * FROM interviews WHERE reschedule_token = ? LIMIT 1",
                (reschedule_token,),
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def delete_interview(self, interview_id: int) -> None:
        """Delete an interview from the database."""
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute("DELETE FROM interviews WHERE id = ?", (interview_id,))
            conn.commit()

    def upsert_episode(self, episode_data: Dict[str, Any]) -> tuple[int, str]:
        """Insert or update an episode using interview id when available."""
        interview_id = episode_data.get("interview_id")
        episode_id = episode_data.get("id")

        with sqlite3.connect(str(self.db_path)) as conn:
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
                cursor = conn.execute(
                    "SELECT id FROM episodes WHERE legacy_episode_number = ? LIMIT 1",
                    (episode_data.get("legacy_episode_number"),),
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

            fields = (
                episode_data.get("guest_id"),
                interview_id,
                episode_data.get("guest_name"),
                episode_data.get("guest_email"),
                episode_data.get("website"),
                episode_data.get("episode_title"),
                episode_data.get("topic"),
                episode_data.get("category"),
                episode_data.get("interview_date"),
                episode_data.get("recording_date"),
                episode_data.get("release_date"),
                episode_data.get("release_status", "unplanned"),
                episode_data.get("production_status", "idea"),
                episode_data.get("promotion_status", "unknown"),
                episode_data.get("priority_score", 0),
                episode_data.get("recommendation_reason"),
                episode_data.get("legacy_episode_number"),
                episode_data.get("riverside_status"),
                episode_data.get("source_file_name"),
                episode_data.get("source_type"),
                episode_data.get("show_notes_url"),
                episode_data.get("release_files_url"),
                episode_data.get("transcript_text"),
                _normalize_outreach_plan_storage(episode_data.get("outreach_plan")),
                episode_data.get("ai_monthly_angle_state"),
                episode_data.get("ai_monthly_angle_theme"),
                episode_data.get("notes"),
            )

            if existing_row:
                conn.execute(
                    """
                    UPDATE episodes SET
                        guest_id = ?, interview_id = ?, guest_name = ?, guest_email = ?, website = ?, episode_title = ?,
                        topic = ?, category = ?, interview_date = ?, recording_date = ?, release_date = ?,
                        release_status = ?, production_status = ?, promotion_status = ?, priority_score = ?, recommendation_reason = ?,
                        legacy_episode_number = ?, riverside_status = ?, source_file_name = ?, source_type = ?,
                        show_notes_url = ?, release_files_url = ?, transcript_text = ?, outreach_plan = ?,
                        ai_monthly_angle_state = ?, ai_monthly_angle_theme = ?, notes = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    fields + (existing_row["id"],),
                )
                conn.commit()
                return existing_row["id"], "updated"

            cursor = conn.execute(
                """
                INSERT INTO episodes (
                    guest_id, interview_id, guest_name, guest_email, website, episode_title, topic, category,
                    interview_date, recording_date, release_date, release_status, production_status,
                    promotion_status, priority_score, recommendation_reason, legacy_episode_number, riverside_status,
                    source_file_name, source_type, show_notes_url, release_files_url, transcript_text, outreach_plan,
                    ai_monthly_angle_state, ai_monthly_angle_theme, notes, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                """,
                fields,
            )
            conn.commit()
            return cursor.lastrowid, "created"

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
        with sqlite3.connect(str(self.db_path)) as conn:
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
        with sqlite3.connect(str(self.db_path)) as conn:
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
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("SELECT * FROM episodes WHERE id = ?", (episode_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_episode_by_interview_id(self, interview_id: int) -> Optional[Dict]:
        """Fetch the episode linked to an interview, if one exists."""
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("SELECT * FROM episodes WHERE interview_id = ? LIMIT 1", (interview_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def delete_episode(self, episode_id: int) -> None:
        """Delete an episode from the database."""
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute("DELETE FROM episodes WHERE id = ?", (episode_id,))
            conn.commit()

    def log_reminder(self, interview_id: int, reminder_type: str, sent_to: str, status: str, provider: str = "", notes: str = "") -> int:
        """Record a reminder attempt for an interview."""
        with sqlite3.connect(str(self.db_path)) as conn:
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
        with sqlite3.connect(str(self.db_path)) as conn:
            cursor = conn.execute(
                """
                INSERT INTO reminder_log (interview_id, reminder_type, sent_to, provider, status, notes)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (interview_id, email_type, sent_to, provider, status, notes),
            )
            conn.commit()
            return cursor.lastrowid

    def get_reminder_log(self, interview_id: Optional[int] = None) -> List[Dict]:
        """Return reminder log entries, optionally for a single interview."""
        with sqlite3.connect(str(self.db_path)) as conn:
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
        with sqlite3.connect(str(self.db_path)) as conn:
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
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute(
                "UPDATE guests SET is_processed = TRUE, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (guest_id,)
            )
            conn.commit()
    
    def mark_guest_unprocessed(self, guest_id: int) -> None:
        """Mark a guest as unprocessed."""
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute(
                "UPDATE guests SET is_processed = FALSE, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (guest_id,)
            )
            conn.commit()
    
    def accept_guest_with_email(self, guest_id: int, custom_message: str = "") -> None:
        """Mark guest as accepted and record email sent."""
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute("""
                UPDATE guests SET 
                   is_processed = TRUE, 
                   email_status = 'accepted',
                   email_sent_at = CURRENT_TIMESTAMP,
                   updated_at = CURRENT_TIMESTAMP 
                WHERE id = ?
            """, (guest_id,))
            conn.commit()
    
    def reject_guest_with_email(self, guest_id: int, custom_message: str = "") -> None:
        """Mark guest as rejected and record email sent."""
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute("""
                UPDATE guests SET 
                   is_processed = TRUE, 
                   email_status = 'rejected',
                   email_sent_at = CURRENT_TIMESTAMP,
                   updated_at = CURRENT_TIMESTAMP 
                WHERE id = ?
            """, (guest_id,))
            conn.commit()

    def accept_guest_without_email(self, guest_id: int) -> None:
        """Mark guest as accepted without sending an email."""
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute("""
                UPDATE guests SET
                   is_processed = TRUE,
                   email_status = 'accepted',
                   email_sent_at = NULL,
                   updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (guest_id,))
            conn.commit()

    def reject_guest_without_email(self, guest_id: int) -> None:
        """Mark guest as rejected without sending an email."""
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute("""
                UPDATE guests SET
                   is_processed = TRUE,
                   email_status = 'rejected',
                   email_sent_at = NULL,
                   updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (guest_id,))
            conn.commit()
    
    def skip_guest(self, guest_id: int, reason: str = "") -> None:
        """Mark guest as skipped without sending email."""
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute("""
                UPDATE guests SET 
                   is_processed = TRUE, 
                   email_status = 'skipped',
                   skip_reason = ?,
                   updated_at = CURRENT_TIMESTAMP 
                WHERE id = ?
            """, (reason, guest_id))
            conn.commit()
    
    # ==================== Statistics ====================
    
    def get_stats(self) -> Dict[str, int]:
        """Get guest statistics."""
        with sqlite3.connect(str(self.db_path)) as conn:
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
        with sqlite3.connect(str(self.db_path)) as conn:
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
        
        with sqlite3.connect(str(self.db_path)) as conn:
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
                    merged.get("notes"),
                    keep_id,
                )
                conn.execute(
                    """
                    UPDATE episodes SET
                        guest_id = ?, interview_id = ?, guest_name = ?, guest_email = ?, website = ?, episode_title = ?,
                        topic = ?, category = ?, interview_date = ?, recording_date = ?, release_date = ?,
                        release_status = ?, production_status = ?, promotion_status = ?, priority_score = ?, recommendation_reason = ?,
                        legacy_episode_number = ?, riverside_status = ?, source_file_name = ?, source_type = ?,
                        show_notes_url = ?, release_files_url = ?, transcript_text = ?, notes = ?, updated_at = CURRENT_TIMESTAMP
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
