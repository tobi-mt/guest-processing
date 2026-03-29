import logging
import sqlite3
from json import dumps
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


def _normalized_identity(value: Optional[str]) -> str:
    """Normalize names and emails for duplicate matching."""
    if not value:
        return ""
    return str(value).strip().casefold()


def _prefer_existing_metadata(existing_value: Optional[str], new_value: Optional[str]) -> Optional[str]:
    """Keep the original source metadata when a guest is updated."""
    if existing_value and str(existing_value).strip():
        return existing_value
    return new_value


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
                    original_file_name, original_data, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """, (
                guest_data.get('full_name'), guest_data.get('full_name'), guest_data.get('email'), 
                guest_data.get('website'), guest_data.get('social_handles'),
                guest_data.get('background'), guest_data.get('profession'), guest_data.get('motivation'), 
                guest_data.get('life_experiences'), guest_data.get('core_values'), guest_data.get('faith'), 
                guest_data.get('alignment'), guest_data.get('favorite_quote'), guest_data.get('passionate_topics'), 
                guest_data.get('message'), guest_data.get('experience'), guest_data.get('additional_info'), 
                guest_data.get('has_social_media'), guest_data.get('is_processed', False),
                guest_data.get('original_file_name'), guest_data.get('original_data')
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
                guest_data.get('original_file_name'), guest_data.get('original_data'), guest_id
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

    # ==================== Podcast Operations ====================

    def upsert_interview(self, interview_data: Dict[str, Any]) -> tuple[int, str]:
        """Insert or update an interview using the calendar event id when available."""
        calendar_event_id = interview_data.get("calendar_event_id")

        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row

            existing_row = None
            if calendar_event_id:
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
                        event_updated_at = ?, last_synced_at = ?, title = ?, scheduled_for = ?, timezone = ?,
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
                    last_synced_at, title, scheduled_for, timezone, join_url, status, confirmation_status,
                    reminder_status, reminder_sent_at, notes, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
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

    def upsert_episode(self, episode_data: Dict[str, Any]) -> tuple[int, str]:
        """Insert or update an episode using interview id when available."""
        interview_id = episode_data.get("interview_id")

        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row

            existing_row = None
            if interview_id:
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
                episode_data.get("priority_score", 0),
                episode_data.get("recommendation_reason"),
                episode_data.get("legacy_episode_number"),
                episode_data.get("riverside_status"),
                episode_data.get("source_file_name"),
                episode_data.get("source_type"),
                episode_data.get("notes"),
            )

            if existing_row:
                conn.execute(
                    """
                    UPDATE episodes SET
                        guest_id = ?, interview_id = ?, guest_name = ?, guest_email = ?, website = ?, episode_title = ?,
                        topic = ?, category = ?, interview_date = ?, recording_date = ?, release_date = ?,
                        release_status = ?, production_status = ?, priority_score = ?, recommendation_reason = ?,
                        legacy_episode_number = ?, riverside_status = ?, source_file_name = ?, source_type = ?,
                        notes = ?, updated_at = CURRENT_TIMESTAMP
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
                    priority_score, recommendation_reason, legacy_episode_number, riverside_status,
                    source_file_name, source_type, notes, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                """,
                fields,
            )
            conn.commit()
            return cursor.lastrowid, "created"

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

    def get_episode_by_id(self, episode_id: int) -> Optional[Dict]:
        """Fetch a single episode by id."""
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("SELECT * FROM episodes WHERE id = ?", (episode_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

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
                guest_data = self.mapper.clean_guest_data(row)
                guest_data['original_file_name'] = Path(source_name or file_path).name
                guest_data['original_data'] = dumps(row.fillna("").to_dict(), ensure_ascii=False, default=str)
                
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
        stats = {'removed': 0, 'fixed': 0}
        
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
            
            conn.commit()
        
        logger.info("Database cleaned. Stats: %s", stats)
        return stats
