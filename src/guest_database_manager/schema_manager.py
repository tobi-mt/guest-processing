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
            
            UNIQUE(name, email, full_name)
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
