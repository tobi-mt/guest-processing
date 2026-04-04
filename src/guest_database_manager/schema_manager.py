"""Database schema management utilities."""

import sqlite3
import logging
from typing import List, Tuple

logger = logging.getLogger(__name__)


class SchemaManager:
    """Manages database schema creation and migrations."""
    
    # Core table schema
    CREATE_TABLE_SQL = """
        CREATE TABLE IF NOT EXISTS guests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            
            -- Basic Info
            name TEXT NOT NULL,
            full_name TEXT,
            email TEXT,
            website TEXT,
            social_media_handles TEXT,
            
            -- Professional Background
            background TEXT,
            profession TEXT,
            motivation TEXT,
            life_experiences TEXT,
            
            -- Values & Philosophy
            core_values TEXT,
            faith_practice TEXT,
            beliefs_align TEXT,
            favorite_quote TEXT,
            
            -- Discussion Topics
            passionate_topics TEXT,
            message_takeaway TEXT,
            podcast_experience TEXT,
            additional_info TEXT,
            
            -- Engagement
            following_us TEXT,
            following_status TEXT,
            
            -- System fields
            is_processed BOOLEAN DEFAULT 0,
            email_status TEXT,
            email_sent_at TIMESTAMP,
            skip_reason TEXT,
            date_added TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            date_processed TIMESTAMP,
            updated_at TIMESTAMP,
            
            -- Metadata
            original_file_name TEXT,
            original_data TEXT,
            guest_research TEXT,
            guest_research_updated_at TIMESTAMP,
            
            UNIQUE(name, email, full_name)
        )
    """

    CREATE_INTERVIEWS_TABLE_SQL = """
        CREATE TABLE IF NOT EXISTS interviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guest_id INTEGER,
            guest_name TEXT NOT NULL,
            guest_email TEXT,
            calendar_event_id TEXT UNIQUE,
            calendar_source TEXT,
            event_updated_at TIMESTAMP,
            last_synced_at TIMESTAMP,
            title TEXT,
            scheduled_for TIMESTAMP NOT NULL,
            timezone TEXT DEFAULT 'Europe/Berlin',
            join_url TEXT,
            status TEXT DEFAULT 'scheduled',
            confirmation_status TEXT DEFAULT 'pending',
            reminder_status TEXT DEFAULT 'not_scheduled',
            reminder_sent_at TIMESTAMP,
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (guest_id) REFERENCES guests(id) ON DELETE SET NULL
        )
    """

    CREATE_EPISODES_TABLE_SQL = """
        CREATE TABLE IF NOT EXISTS episodes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guest_id INTEGER,
            interview_id INTEGER,
            guest_name TEXT NOT NULL,
            guest_email TEXT,
            website TEXT,
            episode_title TEXT,
            topic TEXT,
            category TEXT,
            interview_date TIMESTAMP,
            recording_date TIMESTAMP,
            release_date TIMESTAMP,
            release_status TEXT DEFAULT 'unplanned',
            production_status TEXT DEFAULT 'idea',
            promotion_status TEXT DEFAULT 'unknown',
            priority_score REAL DEFAULT 0,
            recommendation_reason TEXT,
            legacy_episode_number TEXT,
            riverside_status TEXT,
            source_file_name TEXT,
            source_type TEXT,
            show_notes_url TEXT,
            release_files_url TEXT,
            transcript_text TEXT,
            outreach_plan TEXT,
            ai_monthly_angle_state TEXT,
            ai_monthly_angle_theme TEXT,
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (guest_id) REFERENCES guests(id) ON DELETE SET NULL,
            FOREIGN KEY (interview_id) REFERENCES interviews(id) ON DELETE SET NULL
        )
    """

    CREATE_REMINDER_LOG_TABLE_SQL = """
        CREATE TABLE IF NOT EXISTS reminder_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            interview_id INTEGER NOT NULL,
            reminder_type TEXT NOT NULL,
            sent_to TEXT NOT NULL,
            provider TEXT,
            status TEXT NOT NULL,
            sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            notes TEXT,
            FOREIGN KEY (interview_id) REFERENCES interviews(id) ON DELETE CASCADE
        )
    """
    
    # Columns that might need to be added to existing databases
    OPTIONAL_COLUMNS: List[Tuple[str, str]] = [
        ("email_status", "TEXT"),
        ("email_sent_at", "TIMESTAMP"),
        ("skip_reason", "TEXT"),
        ("updated_at", "TIMESTAMP"),
        ("following_us", "TEXT"),
        ("social_media_handles", "TEXT"),
        ("passionate_topics", "TEXT"),
        ("message_takeaway", "TEXT"),
        ("podcast_experience", "TEXT"),
        ("additional_info", "TEXT"),
        ("original_file_name", "TEXT"),
        ("original_data", "TEXT"),
        ("guest_research", "TEXT"),
        ("guest_research_updated_at", "TIMESTAMP"),
    ]

    INTERVIEW_OPTIONAL_COLUMNS: List[Tuple[str, str]] = [
        ("calendar_source", "TEXT"),
        ("event_updated_at", "TIMESTAMP"),
        ("last_synced_at", "TIMESTAMP"),
    ]

    EPISODE_OPTIONAL_COLUMNS: List[Tuple[str, str]] = [
        ("website", "TEXT"),
        ("promotion_status", "TEXT"),
        ("legacy_episode_number", "TEXT"),
        ("riverside_status", "TEXT"),
        ("source_file_name", "TEXT"),
        ("source_type", "TEXT"),
        ("show_notes_url", "TEXT"),
        ("release_files_url", "TEXT"),
        ("transcript_text", "TEXT"),
        ("outreach_plan", "TEXT"),
        ("ai_monthly_angle_state", "TEXT"),
        ("ai_monthly_angle_theme", "TEXT"),
    ]
    
    @staticmethod
    def create_tables(db_path: str) -> None:
        """
        Create tables if they don't exist.
        
        Args:
            db_path: Path to the database file
        """
        with sqlite3.connect(db_path) as conn:
            conn.execute(SchemaManager.CREATE_TABLE_SQL)
            conn.execute(SchemaManager.CREATE_INTERVIEWS_TABLE_SQL)
            conn.execute(SchemaManager.CREATE_EPISODES_TABLE_SQL)
            conn.execute(SchemaManager.CREATE_REMINDER_LOG_TABLE_SQL)
            SchemaManager._add_optional_columns(conn)
            conn.commit()
    
    @staticmethod
    def _add_optional_columns(conn: sqlite3.Connection) -> None:
        """
        Add optional columns that might be missing from older database versions.
        
        Args:
            conn: Active database connection
        """
        for column_name, column_type in SchemaManager.OPTIONAL_COLUMNS:
            try:
                conn.execute(f"ALTER TABLE guests ADD COLUMN {column_name} {column_type}")
                logger.info(f"Added column: {column_name}")
            except sqlite3.OperationalError:
                # Column already exists
                pass

        for column_name, column_type in SchemaManager.INTERVIEW_OPTIONAL_COLUMNS:
            try:
                conn.execute(f"ALTER TABLE interviews ADD COLUMN {column_name} {column_type}")
                logger.info(f"Added interview column: {column_name}")
            except sqlite3.OperationalError:
                pass

        for column_name, column_type in SchemaManager.EPISODE_OPTIONAL_COLUMNS:
            try:
                conn.execute(f"ALTER TABLE episodes ADD COLUMN {column_name} {column_type}")
                logger.info(f"Added episode column: {column_name}")
            except sqlite3.OperationalError:
                pass
    
    @staticmethod
    def get_column_names(db_path: str) -> List[str]:
        """
        Get list of column names in the guests table.
        
        Args:
            db_path: Path to the database file
            
        Returns:
            List of column names
        """
        with sqlite3.connect(db_path) as conn:
            cursor = conn.execute("PRAGMA table_info(guests)")
            return [row[1] for row in cursor.fetchall()]
    
    @staticmethod
    def verify_schema(db_path: str) -> bool:
        """
        Verify that the database schema is valid.
        
        Args:
            db_path: Path to the database file
            
        Returns:
            True if schema is valid
        """
        try:
            columns = SchemaManager.get_column_names(db_path)
            required_columns = ['id', 'name', 'full_name', 'email', 'is_processed']
            return all(col in columns for col in required_columns)
        except Exception as e:
            logger.error(f"Schema verification failed: {e}")
            return False
