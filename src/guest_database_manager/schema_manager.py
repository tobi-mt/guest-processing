"""Database schema management utilities."""

import sqlite3
import logging
from typing import Callable, List, Tuple

from guest_database_manager.db_connection import connect_database

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
            booking_token TEXT,
            booking_token_created_at TIMESTAMP,
            booking_override TEXT,
            
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
            reschedule_token TEXT,
            reschedule_token_created_at TIMESTAMP,
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
            working_title TEXT,
            published_title TEXT,
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
            transcript_source_id TEXT,
            transcript_synced_at TIMESTAMP,
            transcript_match_method TEXT,
            transcript_match_score INTEGER,
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

    CREATE_EMAIL_OUTBOX_TABLE_SQL = """
        CREATE TABLE IF NOT EXISTS email_outbox (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            interview_id INTEGER,
            email_type TEXT NOT NULL,
            sent_to TEXT NOT NULL,
            subject TEXT NOT NULL,
            body TEXT NOT NULL,
            attachments_json TEXT,
            provider TEXT,
            status TEXT NOT NULL DEFAULT 'pending',
            attempts INTEGER NOT NULL DEFAULT 0,
            max_attempts INTEGER NOT NULL DEFAULT 5,
            next_attempt_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_error TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            sent_at TIMESTAMP,
            FOREIGN KEY (interview_id) REFERENCES interviews(id) ON DELETE CASCADE
        )
    """

    CREATE_MIGRATIONS_TABLE_SQL = """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            applied_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """

    CREATE_APPLICATIONS_TABLE_SQL = """
        CREATE TABLE IF NOT EXISTS guest_applications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guest_id INTEGER NOT NULL,
            source TEXT NOT NULL DEFAULT 'unknown',
            submitted_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            payload_json TEXT NOT NULL DEFAULT '{}',
            status TEXT NOT NULL DEFAULT 'submitted'
                CHECK (status IN ('submitted', 'triage', 'needs_information', 'accepted', 'declined', 'withdrawn')),
            decision_reason TEXT,
            decided_at TIMESTAMP,
            row_version INTEGER NOT NULL DEFAULT 1,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (guest_id) REFERENCES guests(id) ON DELETE CASCADE
        )
    """

    CREATE_AUDIT_EVENTS_TABLE_SQL = """
        CREATE TABLE IF NOT EXISTS audit_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entity_type TEXT NOT NULL,
            entity_id TEXT NOT NULL,
            event_type TEXT NOT NULL,
            actor TEXT NOT NULL DEFAULT 'system',
            source TEXT NOT NULL DEFAULT 'application',
            reason TEXT,
            correlation_id TEXT,
            before_json TEXT,
            after_json TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
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
        ("booking_token", "TEXT"),
        ("booking_token_created_at", "TIMESTAMP"),
        ("booking_override", "TEXT"),
    ]

    INTERVIEW_OPTIONAL_COLUMNS: List[Tuple[str, str]] = [
        ("calendar_source", "TEXT"),
        ("event_updated_at", "TIMESTAMP"),
        ("last_synced_at", "TIMESTAMP"),
        ("reschedule_token", "TEXT"),
        ("reschedule_token_created_at", "TIMESTAMP"),
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
        ("working_title", "TEXT"),
        ("published_title", "TEXT"),
        ("transcript_source_id", "TEXT"),
        ("transcript_synced_at", "TIMESTAMP"),
        ("transcript_match_method", "TEXT"),
        ("transcript_match_score", "INTEGER"),
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
        with connect_database(db_path) as conn:
            conn.execute(SchemaManager.CREATE_TABLE_SQL)
            conn.execute(SchemaManager.CREATE_INTERVIEWS_TABLE_SQL)
            conn.execute(SchemaManager.CREATE_EPISODES_TABLE_SQL)
            conn.execute(SchemaManager.CREATE_REMINDER_LOG_TABLE_SQL)
            conn.execute(SchemaManager.CREATE_EMAIL_OUTBOX_TABLE_SQL)
            conn.commit()
            SchemaManager._run_migrations(conn)

    @staticmethod
    def _column_names(conn: sqlite3.Connection, table: str) -> set[str]:
        return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}

    @staticmethod
    def _add_column_if_missing(conn: sqlite3.Connection, table: str, name: str, declaration: str) -> None:
        if name in SchemaManager._column_names(conn, table):
            return
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {declaration}")
        logger.info("Added %s.%s", table, name)

    @staticmethod
    def _migration_001_optional_columns(conn: sqlite3.Connection) -> None:
        SchemaManager._add_optional_columns(conn)

    @staticmethod
    def _migration_002_domain_history(conn: sqlite3.Connection) -> None:
        conn.execute(SchemaManager.CREATE_APPLICATIONS_TABLE_SQL)
        conn.execute(SchemaManager.CREATE_AUDIT_EVENTS_TABLE_SQL)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_applications_guest_submitted ON guest_applications(guest_id, submitted_at DESC)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_entity_created ON audit_events(entity_type, entity_id, created_at DESC)")
        conn.execute(
            """
            INSERT INTO guest_applications (guest_id, source, submitted_at, payload_json, status, decision_reason, decided_at)
            SELECT g.id,
                   COALESCE(NULLIF(TRIM(g.original_file_name), ''), 'legacy_guest_record'),
                   COALESCE(g.date_added, CURRENT_TIMESTAMP),
                   COALESCE(NULLIF(TRIM(g.original_data), ''), '{}'),
                   CASE LOWER(TRIM(COALESCE(g.email_status, '')))
                     WHEN 'accepted' THEN 'accepted'
                     WHEN 'declined' THEN 'declined'
                     WHEN 'rejected' THEN 'declined'
                     ELSE 'submitted'
                   END,
                   g.skip_reason,
                   g.date_processed
            FROM guests g
            WHERE NOT EXISTS (SELECT 1 FROM guest_applications a WHERE a.guest_id = g.id)
            """
        )

    @staticmethod
    def _migration_003_identity_and_concurrency(conn: sqlite3.Connection) -> None:
        for table in ("guests", "interviews", "episodes", "email_outbox"):
            SchemaManager._add_column_if_missing(conn, table, "row_version", "INTEGER NOT NULL DEFAULT 1")
        SchemaManager._add_column_if_missing(conn, "guests", "normalized_name", "TEXT NOT NULL DEFAULT ''")
        SchemaManager._add_column_if_missing(conn, "guests", "normalized_email", "TEXT NOT NULL DEFAULT ''")
        conn.execute(
            "UPDATE guests SET normalized_name = LOWER(TRIM(COALESCE(full_name, name, ''))), "
            "normalized_email = LOWER(TRIM(COALESCE(email, '')))"
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_guests_normalized_name ON guests(normalized_name)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_guests_normalized_email ON guests(normalized_email) WHERE normalized_email <> ''")

    @staticmethod
    def _migration_004_validation_triggers(conn: sqlite3.Connection) -> None:
        validations = (
            ("interviews", "status", ("scheduled", "completed", "cancelled", "no_show")),
            ("interviews", "confirmation_status", ("pending", "confirmed", "declined", "reschedule_requested")),
            ("episodes", "release_status", ("unplanned", "scheduled", "released", "archived")),
            ("episodes", "production_status", ("idea", "recorded", "editing", "ready", "released", "archived")),
            ("episodes", "promotion_status", ("unknown", "needs_assets", "ready", "released", "archived")),
            ("email_outbox", "status", ("pending", "sending", "retrying", "sent", "failed", "dead_letter", "cancelled")),
        )
        for table, column, values in validations:
            allowed = ", ".join(f"'{value}'" for value in values)
            for operation in ("INSERT", "UPDATE"):
                trigger = f"validate_{table}_{column}_{operation.lower()}"
                conn.execute(
                    f"""CREATE TRIGGER IF NOT EXISTS {trigger}
                        BEFORE {operation} ON {table}
                        WHEN LOWER(TRIM(COALESCE(NEW.{column}, ''))) NOT IN ({allowed})
                        BEGIN SELECT RAISE(ABORT, 'invalid {table}.{column}'); END"""
                )
        conn.execute(
            """CREATE TRIGGER IF NOT EXISTS normalize_guest_identity_insert
               AFTER INSERT ON guests
               BEGIN
                 UPDATE guests SET
                   normalized_name = LOWER(TRIM(COALESCE(NEW.full_name, NEW.name, ''))),
                   normalized_email = LOWER(TRIM(COALESCE(NEW.email, '')))
                 WHERE id = NEW.id;
               END"""
        )

    @staticmethod
    def _migration_005_reliable_outbox(conn: sqlite3.Connection) -> None:
        for name, declaration in (
            ("idempotency_key", "TEXT"),
            ("correlation_id", "TEXT"),
            ("lease_owner", "TEXT"),
            ("lease_until", "TIMESTAMP"),
            ("dead_letter_at", "TIMESTAMP"),
        ):
            SchemaManager._add_column_if_missing(conn, "email_outbox", name, declaration)
        conn.execute("UPDATE email_outbox SET idempotency_key = 'legacy:' || id WHERE idempotency_key IS NULL")
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_email_outbox_idempotency ON email_outbox(idempotency_key)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_email_outbox_due ON email_outbox(status, next_attempt_at, lease_until)"
        )
        conn.execute(
            """CREATE TABLE IF NOT EXISTS email_outbox_attempts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                outbox_id INTEGER NOT NULL,
                attempt_number INTEGER NOT NULL,
                worker_id TEXT,
                status TEXT NOT NULL,
                provider TEXT,
                error TEXT,
                started_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                finished_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (outbox_id) REFERENCES email_outbox(id) ON DELETE CASCADE
            )"""
        )
        conn.execute(
            """CREATE TABLE IF NOT EXISTS automation_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                automation_type TEXT NOT NULL,
                correlation_id TEXT,
                worker_id TEXT,
                status TEXT NOT NULL,
                checked_count INTEGER NOT NULL DEFAULT 0,
                succeeded_count INTEGER NOT NULL DEFAULT 0,
                failed_count INTEGER NOT NULL DEFAULT 0,
                details_json TEXT,
                started_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                finished_at TIMESTAMP
            )"""
        )
        conn.execute(
            """CREATE TRIGGER IF NOT EXISTS normalize_guest_identity_update
               AFTER UPDATE OF name, full_name, email ON guests
               BEGIN
                 UPDATE guests SET
                   normalized_name = LOWER(TRIM(COALESCE(NEW.full_name, NEW.name, ''))),
                   normalized_email = LOWER(TRIM(COALESCE(NEW.email, '')))
                 WHERE id = NEW.id;
               END"""
        )

    @staticmethod
    def _migration_006_identity_and_calendar_governance(conn: sqlite3.Connection) -> None:
        SchemaManager._add_column_if_missing(conn, "guests", "identity_status", "TEXT NOT NULL DEFAULT 'active'")
        SchemaManager._add_column_if_missing(conn, "guests", "merged_into_guest_id", "INTEGER")
        for table in ("guests", "guest_applications", "interviews", "episodes"):
            SchemaManager._add_column_if_missing(conn, table, "owner", "TEXT")
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_guests_identity_status ON guests(identity_status, normalized_email, normalized_name)"
        )
        conn.execute(
            """CREATE TABLE IF NOT EXISTS calendar_reconciliation_proposals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                calendar_event_id TEXT NOT NULL,
                interview_id INTEGER,
                action TEXT NOT NULL CHECK (action IN ('create', 'update', 'cancel', 'unlink', 'no_change')),
                status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'applied', 'dismissed', 'superseded', 'failed')),
                before_json TEXT,
                after_json TEXT NOT NULL,
                reason TEXT,
                correlation_id TEXT NOT NULL,
                row_version INTEGER NOT NULL DEFAULT 1,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                reviewed_at TIMESTAMP,
                applied_at TIMESTAMP,
                FOREIGN KEY (interview_id) REFERENCES interviews(id) ON DELETE SET NULL
            )"""
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_calendar_proposals_status ON calendar_reconciliation_proposals(status, created_at DESC)"
        )
        for operation in ("INSERT", "UPDATE"):
            conn.execute(
                f"""CREATE TRIGGER IF NOT EXISTS validate_guests_identity_status_{operation.lower()}
                    BEFORE {operation} ON guests
                    WHEN LOWER(TRIM(COALESCE(NEW.identity_status, ''))) NOT IN ('active', 'merged', 'review')
                 BEGIN SELECT RAISE(ABORT, 'invalid guests.identity_status'); END"""
            )

    @staticmethod
    def _migration_007_editorial_dispositions(conn: sqlite3.Connection) -> None:
        SchemaManager._add_column_if_missing(
            conn, "episodes", "editorial_disposition", "TEXT NOT NULL DEFAULT 'active'"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_episodes_disposition ON episodes(editorial_disposition, release_status)"
        )
        for operation in ("INSERT", "UPDATE"):
            conn.execute(
                f"""CREATE TRIGGER IF NOT EXISTS validate_episodes_disposition_{operation.lower()}
                    BEFORE {operation} ON episodes
                    WHEN LOWER(TRIM(COALESCE(NEW.editorial_disposition, ''))) NOT IN ('active', 'hold', 'archive', 'retire')
                    BEGIN SELECT RAISE(ABORT, 'invalid episodes.editorial_disposition'); END"""
            )

    @staticmethod
    def _migration_008_release_baseline(conn: sqlite3.Connection) -> None:
        SchemaManager._add_column_if_missing(conn, "episodes", "original_planned_release_date", "TIMESTAMP")

    @staticmethod
    def _migration_009_episode_title_provenance(conn: sqlite3.Connection) -> None:
        """Preserve editorial and published titles plus transcript match provenance."""
        for name, declaration in (
            ("working_title", "TEXT"),
            ("published_title", "TEXT"),
            ("transcript_source_id", "TEXT"),
            ("transcript_synced_at", "TIMESTAMP"),
            ("transcript_match_method", "TEXT"),
            ("transcript_match_score", "INTEGER"),
        ):
            SchemaManager._add_column_if_missing(conn, "episodes", name, declaration)
        conn.execute(
            "UPDATE episodes SET working_title = episode_title "
            "WHERE TRIM(COALESCE(working_title, '')) = '' AND TRIM(COALESCE(episode_title, '')) <> ''"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_episodes_release_calendar "
            "ON episodes(release_status, release_date, id)"
        )

    @staticmethod
    def _migration_010_recommendation_feedback(conn: sqlite3.Connection) -> None:
        """Persist reversible human decisions about scheduling recommendations."""
        conn.execute(
            """CREATE TABLE IF NOT EXISTS recommendation_feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                episode_id INTEGER NOT NULL,
                action TEXT NOT NULL CHECK(action IN ('rejected', 'restored')),
                reason TEXT,
                actor TEXT NOT NULL,
                source TEXT NOT NULL DEFAULT 'scheduling_intelligence',
                recommendation_version TEXT,
                recommendation_snapshot TEXT,
                correlation_id TEXT,
                idempotency_key TEXT NOT NULL UNIQUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (episode_id) REFERENCES episodes(id) ON DELETE CASCADE
            )"""
        )

    @staticmethod
    def _migration_011_booking_availability(conn: sqlite3.Connection) -> None:
        """Persist operator-controlled default booking availability."""
        conn.execute(
            """CREATE TABLE IF NOT EXISTS booking_availability (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                timezone TEXT NOT NULL,
                weekdays_json TEXT NOT NULL,
                slot_times_json TEXT NOT NULL,
                days_ahead INTEGER NOT NULL,
                min_notice_hours INTEGER NOT NULL,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_by TEXT NOT NULL DEFAULT 'system'
            )"""
        )

    @staticmethod
    def _migration_012_booking_blackouts(conn: sqlite3.Connection) -> None:
        SchemaManager._add_column_if_missing(conn, "booking_availability", "blackouts_json", "TEXT NOT NULL DEFAULT '[]'")
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_recommendation_feedback_episode_latest "
            "ON recommendation_feedback(episode_id, id DESC)"
        )

    @staticmethod
    def _migration_013_ai_analysis_cache(conn: sqlite3.Connection) -> None:
        """Persist completed AI analyses separately from source research data."""
        conn.execute(
            """CREATE TABLE IF NOT EXISTS guest_ai_analyses (
                guest_id INTEGER PRIMARY KEY,
                analysis_json TEXT NOT NULL,
                input_fingerprint TEXT NOT NULL,
                model TEXT NOT NULL,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (guest_id) REFERENCES guests(id) ON DELETE CASCADE
            )"""
        )

    @staticmethod
    def _run_migrations(conn: sqlite3.Connection) -> None:
        """Apply each schema migration once, transactionally and in order."""
        conn.execute(SchemaManager.CREATE_MIGRATIONS_TABLE_SQL)
        conn.commit()
        migrations: tuple[tuple[int, str, Callable[[sqlite3.Connection], None]], ...] = (
            (1, "optional_columns", SchemaManager._migration_001_optional_columns),
            (2, "domain_history", SchemaManager._migration_002_domain_history),
            (3, "identity_and_concurrency", SchemaManager._migration_003_identity_and_concurrency),
            (4, "validation_triggers", SchemaManager._migration_004_validation_triggers),
            (5, "reliable_outbox", SchemaManager._migration_005_reliable_outbox),
            (6, "identity_and_calendar_governance", SchemaManager._migration_006_identity_and_calendar_governance),
            (7, "editorial_dispositions", SchemaManager._migration_007_editorial_dispositions),
            (8, "release_baseline", SchemaManager._migration_008_release_baseline),
            (9, "episode_title_provenance", SchemaManager._migration_009_episode_title_provenance),
            (10, "recommendation_feedback", SchemaManager._migration_010_recommendation_feedback),
            (11, "booking_availability", SchemaManager._migration_011_booking_availability),
            (12, "booking_blackouts", SchemaManager._migration_012_booking_blackouts),
            (13, "ai_analysis_cache", SchemaManager._migration_013_ai_analysis_cache),
        )
        applied = {int(row[0]) for row in conn.execute("SELECT version FROM schema_migrations").fetchall()}
        for version, name, migration in migrations:
            if version in applied:
                continue
            try:
                conn.execute("BEGIN IMMEDIATE")
                migration(conn)
                conn.execute("INSERT INTO schema_migrations (version, name) VALUES (?, ?)", (version, name))
                conn.commit()
            except Exception:
                conn.rollback()
                raise
    
    @staticmethod
    def _add_optional_columns(conn: sqlite3.Connection) -> None:
        """
        Add optional columns that might be missing from older database versions.
        
        Args:
            conn: Active database connection
        """
        for column_name, column_type in SchemaManager.OPTIONAL_COLUMNS:
            SchemaManager._add_column_if_missing(conn, "guests", column_name, column_type)

        for column_name, column_type in SchemaManager.INTERVIEW_OPTIONAL_COLUMNS:
            SchemaManager._add_column_if_missing(conn, "interviews", column_name, column_type)

        for column_name, column_type in SchemaManager.EPISODE_OPTIONAL_COLUMNS:
            SchemaManager._add_column_if_missing(conn, "episodes", column_name, column_type)
    
    @staticmethod
    def get_column_names(db_path: str) -> List[str]:
        """
        Get list of column names in the guests table.
        
        Args:
            db_path: Path to the database file
            
        Returns:
            List of column names
        """
        with connect_database(db_path) as conn:
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
