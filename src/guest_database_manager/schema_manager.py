"""Database schema management utilities."""

import hashlib
import json
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
            marketing_opt_in BOOLEAN NOT NULL DEFAULT 0,
            
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

    CREATE_RESCHEDULE_PROPOSALS_TABLE_SQL = """
        CREATE TABLE IF NOT EXISTS interview_reschedule_proposals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            interview_id INTEGER NOT NULL,
            mode TEXT NOT NULL CHECK (mode IN ('open_calendar', 'specific', 'alternatives')),
            timezone TEXT NOT NULL,
            options_json TEXT NOT NULL DEFAULT '[]',
            subject TEXT NOT NULL,
            body TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'sent' CHECK (status IN ('sent', 'accepted', 'superseded', 'expired')),
            created_by TEXT NOT NULL DEFAULT 'operator',
            sent_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
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
    def _migration_014_partner_intelligence(conn: sqlite3.Connection) -> None:
        """Create the isolated, review-first partner intelligence data boundary."""
        conn.execute(
            """CREATE TABLE IF NOT EXISTS partner_prospects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                organisation_name TEXT NOT NULL,
                website TEXT,
                contact_name TEXT,
                contact_email TEXT,
                partner_type TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'research'
                    CHECK (status IN ('research', 'draft', 'approved', 'rejected', 'contacted', 'responded', 'booked', 'suppressed')),
                research_summary TEXT NOT NULL DEFAULT '',
                fit_score INTEGER NOT NULL DEFAULT 0 CHECK (fit_score BETWEEN 0 AND 100),
                score_json TEXT NOT NULL DEFAULT '{}',
                row_version INTEGER NOT NULL DEFAULT 1,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )"""
        )
        conn.execute(
            """CREATE TABLE IF NOT EXISTS partner_evidence (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                prospect_id INTEGER NOT NULL,
                source_url TEXT NOT NULL,
                source_title TEXT NOT NULL,
                published_at TEXT,
                collected_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                fact_text TEXT NOT NULL,
                source_hash TEXT NOT NULL,
                UNIQUE(prospect_id, source_url, source_hash),
                FOREIGN KEY (prospect_id) REFERENCES partner_prospects(id) ON DELETE CASCADE
            )"""
        )
        conn.execute(
            """CREATE TABLE IF NOT EXISTS partner_pitch_drafts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                prospect_id INTEGER NOT NULL,
                version INTEGER NOT NULL,
                subject TEXT NOT NULL,
                body TEXT NOT NULL,
                evidence_ids_json TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'approved', 'rejected', 'retired')),
                generated_by TEXT NOT NULL DEFAULT 'system',
                review_reason TEXT,
                approved_by TEXT,
                approved_at TIMESTAMP,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(prospect_id, version),
                FOREIGN KEY (prospect_id) REFERENCES partner_prospects(id) ON DELETE CASCADE
            )"""
        )
        conn.execute(
            """CREATE TABLE IF NOT EXISTS partner_outreach_outcomes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                prospect_id INTEGER NOT NULL,
                pitch_draft_id INTEGER,
                outcome TEXT NOT NULL CHECK (outcome IN ('handed_off', 'contacted', 'replied', 'meeting', 'booked', 'declined', 'opted_out')),
                notes TEXT,
                actor TEXT NOT NULL,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (prospect_id) REFERENCES partner_prospects(id) ON DELETE CASCADE,
                FOREIGN KEY (pitch_draft_id) REFERENCES partner_pitch_drafts(id) ON DELETE SET NULL
            )"""
        )
        conn.execute(
            """CREATE TABLE IF NOT EXISTS partner_suppressions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                normalized_contact TEXT NOT NULL UNIQUE,
                reason TEXT NOT NULL,
                actor TEXT NOT NULL,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )"""
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_partner_prospects_status ON partner_prospects(status, fit_score DESC)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_partner_evidence_prospect ON partner_evidence(prospect_id, collected_at DESC)")

    @staticmethod
    def _migration_016_partner_contact_research(conn: sqlite3.Connection) -> None:
        """Store source-backed contact context separately from organisation evidence."""
        conn.execute(
            """CREATE TABLE IF NOT EXISTS partner_contact_research (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                prospect_id INTEGER NOT NULL,
                contact_name TEXT NOT NULL,
                source_url TEXT NOT NULL,
                source_title TEXT NOT NULL,
                fact_text TEXT NOT NULL,
                collected_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                source_hash TEXT NOT NULL,
                UNIQUE(prospect_id, contact_name, source_url, source_hash),
                FOREIGN KEY (prospect_id) REFERENCES partner_prospects(id) ON DELETE CASCADE
            )"""
        )

    @staticmethod
    def _migration_018_partner_automation(conn: sqlite3.Connection) -> None:
        """Add explainable strategy, editable drafts, and outbox handoff metadata."""
        SchemaManager._add_column_if_missing(conn, "partner_prospects", "confidence", "TEXT NOT NULL DEFAULT 'low'")
        SchemaManager._add_column_if_missing(conn, "partner_prospects", "strategy_json", "TEXT NOT NULL DEFAULT '{}'")
        SchemaManager._add_column_if_missing(conn, "partner_pitch_drafts", "angle_title", "TEXT NOT NULL DEFAULT ''")
        SchemaManager._add_column_if_missing(conn, "partner_pitch_drafts", "updated_at", "TIMESTAMP")
        SchemaManager._add_column_if_missing(conn, "partner_pitch_drafts", "outbox_id", "INTEGER")
        conn.execute(
            """CREATE TABLE IF NOT EXISTS partner_contact_candidates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                prospect_id INTEGER NOT NULL,
                contact_name TEXT NOT NULL DEFAULT '',
                contact_email TEXT NOT NULL DEFAULT '',
                role_title TEXT NOT NULL DEFAULT '',
                confidence TEXT NOT NULL CHECK (confidence IN ('low', 'medium', 'high')),
                source_url TEXT NOT NULL,
                evidence_text TEXT NOT NULL,
                selected_at TIMESTAMP,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(prospect_id, contact_email, source_url),
                FOREIGN KEY (prospect_id) REFERENCES partner_prospects(id) ON DELETE CASCADE
            )"""
        )

    @staticmethod
    def _migration_019_apollo_partner_enrichment(conn: sqlite3.Connection) -> None:
        """Retain provider provenance without exposing provider credentials."""
        SchemaManager._add_column_if_missing(conn, "partner_contact_candidates", "provider", "TEXT NOT NULL DEFAULT 'public_web'")
        SchemaManager._add_column_if_missing(conn, "partner_contact_candidates", "provider_record_id", "TEXT NOT NULL DEFAULT ''")
        SchemaManager._add_column_if_missing(conn, "partner_contact_candidates", "verification_status", "TEXT NOT NULL DEFAULT ''")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_partner_contact_research_prospect ON partner_contact_research(prospect_id, collected_at DESC)")

    @staticmethod
    def _migration_020_partner_pitch_studio(conn: sqlite3.Connection) -> None:
        """Track pitch intent, selection, and variant performance."""
        SchemaManager._add_column_if_missing(conn, "partner_pitch_drafts", "template_id", "TEXT NOT NULL DEFAULT 'editorial_conversation'")
        SchemaManager._add_column_if_missing(conn, "partner_pitch_drafts", "tone", "TEXT NOT NULL DEFAULT 'warm'")
        SchemaManager._add_column_if_missing(conn, "partner_pitch_drafts", "objective", "TEXT NOT NULL DEFAULT ''")
        SchemaManager._add_column_if_missing(conn, "partner_pitch_drafts", "angle_rationale", "TEXT NOT NULL DEFAULT ''")
        SchemaManager._add_column_if_missing(conn, "partner_pitch_drafts", "selected_at", "TIMESTAMP")
        SchemaManager._add_column_if_missing(conn, "partner_pitch_drafts", "selected_by", "TEXT")

    @staticmethod
    def _migration_021_partner_source_intelligence(conn: sqlite3.Connection) -> None:
        """Track normalized free-source evidence and provider coverage."""
        SchemaManager._add_column_if_missing(conn, "partner_evidence", "provider", "TEXT NOT NULL DEFAULT 'manual'")
        SchemaManager._add_column_if_missing(conn, "partner_evidence", "evidence_type", "TEXT NOT NULL DEFAULT 'organisation_fact'")
        SchemaManager._add_column_if_missing(conn, "partner_evidence", "confidence", "TEXT NOT NULL DEFAULT 'medium'")
        conn.execute(
            """CREATE TABLE IF NOT EXISTS partner_enrichment_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                prospect_id INTEGER NOT NULL,
                provider TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('completed', 'empty', 'failed', 'skipped')),
                result_count INTEGER NOT NULL DEFAULT 0,
                error_code TEXT NOT NULL DEFAULT '',
                started_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(prospect_id, provider, started_at),
                FOREIGN KEY (prospect_id) REFERENCES partner_prospects(id) ON DELETE CASCADE
            )"""
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_partner_enrichment_runs_prospect ON partner_enrichment_runs(prospect_id, started_at DESC)")

    @staticmethod
    def _migration_017_recommendation_learning(conn: sqlite3.Connection) -> None:
        """Create the governed, append-only recommendation learning subsystem."""
        schema_sql = """
            CREATE TABLE IF NOT EXISTS recommendation_policies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                version TEXT NOT NULL UNIQUE,
                parent_version TEXT,
                status TEXT NOT NULL CHECK(status IN ('draft', 'approved', 'active', 'retired', 'rejected')),
                weights_json TEXT NOT NULL,
                training_summary_json TEXT NOT NULL DEFAULT '{}',
                created_by TEXT NOT NULL,
                approved_by TEXT,
                approval_reason TEXT,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                approved_at TIMESTAMP,
                row_version INTEGER NOT NULL DEFAULT 1
            );
            CREATE UNIQUE INDEX IF NOT EXISTS idx_recommendation_policy_active
                ON recommendation_policies(status) WHERE status = 'active';
            CREATE TABLE IF NOT EXISTS recommendation_observations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                episode_id INTEGER NOT NULL,
                policy_version TEXT NOT NULL,
                feature_schema_version TEXT NOT NULL,
                features_json TEXT NOT NULL,
                score REAL NOT NULL,
                rank INTEGER,
                recommendation_snapshot TEXT NOT NULL,
                correlation_id TEXT NOT NULL,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(episode_id, policy_version, correlation_id),
                FOREIGN KEY (episode_id) REFERENCES episodes(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS recommendation_outcomes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                episode_id INTEGER NOT NULL,
                observation_id INTEGER,
                outcome_type TEXT NOT NULL CHECK(outcome_type IN ('accepted', 'rejected', 'booked', 'released', 'delayed', 'cancelled', 'performance')),
                value REAL NOT NULL,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                actor TEXT NOT NULL,
                source TEXT NOT NULL,
                idempotency_key TEXT NOT NULL UNIQUE,
                occurred_at TIMESTAMP NOT NULL,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (episode_id) REFERENCES episodes(id) ON DELETE CASCADE,
                FOREIGN KEY (observation_id) REFERENCES recommendation_observations(id) ON DELETE SET NULL
            );
            CREATE TABLE IF NOT EXISTS recommendation_evaluations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                candidate_version TEXT NOT NULL,
                champion_version TEXT NOT NULL,
                sample_count INTEGER NOT NULL,
                baseline_metric REAL NOT NULL,
                candidate_metric REAL NOT NULL,
                uplift REAL NOT NULL,
                guardrails_json TEXT NOT NULL,
                report_json TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('passed', 'failed', 'insufficient_data')),
                created_by TEXT NOT NULL,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS recommendation_deployments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                policy_version TEXT NOT NULL,
                previous_version TEXT,
                action TEXT NOT NULL CHECK(action IN ('activated', 'rolled_back', 'auto_activated')),
                actor TEXT NOT NULL,
                reason TEXT NOT NULL,
                evaluation_id INTEGER,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS recommendation_learning_settings (
                id INTEGER PRIMARY KEY CHECK(id = 1),
                automation_enabled INTEGER NOT NULL DEFAULT 0 CHECK(automation_enabled IN (0, 1)),
                kill_switch INTEGER NOT NULL DEFAULT 1 CHECK(kill_switch IN (0, 1)),
                min_samples INTEGER NOT NULL DEFAULT 30,
                min_uplift REAL NOT NULL DEFAULT 0.03,
                max_weight_change REAL NOT NULL DEFAULT 0.25,
                updated_by TEXT NOT NULL DEFAULT 'system',
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_recommendation_observations_episode
                ON recommendation_observations(episode_id, created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_recommendation_outcomes_episode
                ON recommendation_outcomes(episode_id, occurred_at DESC);
            """
        # sqlite3.Connection.executescript() implicitly commits any pending
        # transaction. Execute each DDL statement separately so the migration
        # runner's BEGIN IMMEDIATE/rollback boundary remains authoritative.
        for statement in schema_sql.split(";"):
            if statement.strip():
                conn.execute(statement)
        conn.execute(
            """INSERT OR IGNORE INTO recommendation_policies
               (version, status, weights_json, training_summary_json, created_by, approved_by, approval_reason, approved_at)
               VALUES ('release-planner-v1', 'active', '{}', '{"mode":"rules_baseline"}',
                       'system', 'system', 'Initial governed baseline', CURRENT_TIMESTAMP)"""
        )
        conn.execute("INSERT OR IGNORE INTO recommendation_learning_settings (id) VALUES (1)")

    @staticmethod
    def _migration_015_marketing_opt_in(conn: sqlite3.Connection) -> None:
        """Add an explicit, safe-by-default newsletter consent flag."""
        SchemaManager._add_column_if_missing(conn, "guests", "marketing_opt_in", "BOOLEAN NOT NULL DEFAULT 0")

    @staticmethod
    def _migration_022_reschedule_proposals(conn: sqlite3.Connection) -> None:
        """Persist the exact structured alternatives included in reschedule emails."""
        conn.execute(SchemaManager.CREATE_RESCHEDULE_PROPOSALS_TABLE_SQL)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_reschedule_proposals_interview "
            "ON interview_reschedule_proposals(interview_id, sent_at DESC)"
        )

    @staticmethod
    def _migration_023_growth_intelligence(conn: sqlite3.Connection) -> None:
        """Create append-only, source-backed growth evidence and experiments."""
        statements = (
            """CREATE TABLE IF NOT EXISTS growth_metric_observations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                episode_id INTEGER,
                provider TEXT NOT NULL,
                metric_name TEXT NOT NULL,
                metric_value REAL NOT NULL CHECK(metric_value >= 0),
                unit TEXT NOT NULL,
                traffic_scope TEXT NOT NULL DEFAULT 'all'
                    CHECK(traffic_scope IN ('organic', 'paid', 'all', 'unknown')),
                period_start TEXT NOT NULL,
                period_end TEXT NOT NULL,
                source_reference TEXT NOT NULL,
                source_hash TEXT NOT NULL,
                observation_key TEXT NOT NULL UNIQUE,
                idempotency_key TEXT NOT NULL UNIQUE,
                actor TEXT NOT NULL,
                correlation_id TEXT NOT NULL DEFAULT '',
                imported_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (episode_id) REFERENCES episodes(id) ON DELETE RESTRICT,
                CHECK(period_end >= period_start)
            )""",
            """CREATE INDEX IF NOT EXISTS idx_growth_metrics_episode_period
                ON growth_metric_observations(episode_id, period_end DESC)""",
            """CREATE INDEX IF NOT EXISTS idx_growth_metrics_provider_metric
                ON growth_metric_observations(provider, metric_name, period_end DESC)""",
            """CREATE TRIGGER IF NOT EXISTS trg_growth_observations_immutable_update
            BEFORE UPDATE ON growth_metric_observations
            BEGIN
                SELECT RAISE(ABORT, 'growth observations are immutable');
            END""",
            """CREATE TRIGGER IF NOT EXISTS trg_growth_observations_immutable_delete
            BEFORE DELETE ON growth_metric_observations
            BEGIN
                SELECT RAISE(ABORT, 'growth observations are immutable');
            END""",
            """CREATE TABLE IF NOT EXISTS growth_experiments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                hypothesis TEXT NOT NULL,
                primary_metric TEXT NOT NULL,
                control_label TEXT NOT NULL,
                treatment_label TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'draft'
                    CHECK(status IN ('draft', 'running', 'completed', 'cancelled')),
                starts_on TEXT,
                ends_on TEXT,
                decision TEXT NOT NULL DEFAULT '',
                actor TEXT NOT NULL,
                correlation_id TEXT NOT NULL DEFAULT '',
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                CHECK(ends_on IS NULL OR starts_on IS NULL OR ends_on >= starts_on)
            )""",
        )
        for statement in statements:
            conn.execute(statement)

    @staticmethod
    def _migration_024_growth_evidence_integrity(conn: sqlite3.Connection) -> None:
        """Upgrade early growth tables without losing already imported evidence."""
        conn.execute(
            """CREATE TABLE growth_metric_observations_v24 (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                episode_id INTEGER,
                provider TEXT NOT NULL,
                metric_name TEXT NOT NULL,
                metric_value REAL NOT NULL CHECK(metric_value >= 0),
                unit TEXT NOT NULL,
                traffic_scope TEXT NOT NULL DEFAULT 'all'
                    CHECK(traffic_scope IN ('organic', 'paid', 'all', 'unknown')),
                period_start TEXT NOT NULL,
                period_end TEXT NOT NULL,
                source_reference TEXT NOT NULL,
                source_hash TEXT NOT NULL,
                observation_key TEXT NOT NULL UNIQUE,
                idempotency_key TEXT NOT NULL UNIQUE,
                actor TEXT NOT NULL,
                correlation_id TEXT NOT NULL DEFAULT '',
                imported_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (episode_id) REFERENCES episodes(id) ON DELETE RESTRICT,
                CHECK(period_end >= period_start)
            )"""
        )
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM growth_metric_observations ORDER BY id"
        ).fetchall()
        logical_keys: dict[str, int] = {}
        for row in rows:
            fingerprint = json.dumps(
                [
                    row["episode_id"],
                    row["provider"],
                    row["metric_name"],
                    row["traffic_scope"],
                    row["period_start"],
                    row["period_end"],
                ],
                separators=(",", ":"),
            )
            observation_key = hashlib.sha256(fingerprint.encode()).hexdigest()
            if observation_key in logical_keys:
                raise sqlite3.IntegrityError(
                    "duplicate logical growth observations require review before migration "
                    f"(rows {logical_keys[observation_key]} and {row['id']})"
                )
            logical_keys[observation_key] = int(row["id"])
            conn.execute(
                """INSERT INTO growth_metric_observations_v24
                    (id, episode_id, provider, metric_name, metric_value, unit, traffic_scope,
                     period_start, period_end, source_reference, source_hash, observation_key,
                     idempotency_key, actor, correlation_id, imported_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    row["id"], row["episode_id"], row["provider"], row["metric_name"],
                    row["metric_value"], row["unit"], row["traffic_scope"],
                    row["period_start"], row["period_end"], row["source_reference"],
                    row["source_hash"], observation_key, row["idempotency_key"],
                    row["actor"], row["correlation_id"], row["imported_at"],
                ),
            )
        conn.execute("DROP TABLE growth_metric_observations")
        conn.execute("ALTER TABLE growth_metric_observations_v24 RENAME TO growth_metric_observations")
        conn.execute("CREATE INDEX idx_growth_metrics_episode_period ON growth_metric_observations(episode_id, period_end DESC)")
        conn.execute("CREATE INDEX idx_growth_metrics_provider_metric ON growth_metric_observations(provider, metric_name, period_end DESC)")
        conn.execute("""CREATE TRIGGER trg_growth_observations_immutable_update BEFORE UPDATE ON growth_metric_observations BEGIN SELECT RAISE(ABORT, 'growth observations are immutable'); END""")
        conn.execute("""CREATE TRIGGER trg_growth_observations_immutable_delete BEFORE DELETE ON growth_metric_observations BEGIN SELECT RAISE(ABORT, 'growth observations are immutable'); END""")

    @staticmethod
    def _migration_025_repair_legacy_orphan_references(conn: sqlite3.Connection) -> None:
        """Repair legacy foreign keys without deleting operational evidence."""
        orphan_interview_ids = [
            int(row[0])
            for row in conn.execute(
                """SELECT i.id FROM interviews i
                   LEFT JOIN guests g ON g.id = i.guest_id
                   WHERE i.guest_id IS NOT NULL AND g.id IS NULL
                   ORDER BY i.id"""
            )
        ]
        empty_episode_link_ids = [
            int(row[0])
            for row in conn.execute(
                """SELECT id FROM episodes
                   WHERE typeof(interview_id) = 'text' AND TRIM(interview_id) = ''
                   ORDER BY id"""
            )
        ]
        orphan_reminder_ids = [
            int(row[0])
            for row in conn.execute(
                """SELECT r.id FROM reminder_log r
                   LEFT JOIN interviews i ON i.id = r.interview_id
                   WHERE r.interview_id IS NOT NULL AND i.id IS NULL
                   ORDER BY r.id"""
            )
        ]

        conn.execute(
            """UPDATE interviews SET guest_id = NULL, row_version = row_version + 1,
                                      updated_at = CURRENT_TIMESTAMP
               WHERE guest_id IS NOT NULL
                 AND NOT EXISTS (SELECT 1 FROM guests WHERE guests.id = interviews.guest_id)"""
        )
        conn.execute(
            """UPDATE episodes SET interview_id = NULL, row_version = row_version + 1,
                                    updated_at = CURRENT_TIMESTAMP
               WHERE typeof(interview_id) = 'text' AND TRIM(interview_id) = ''"""
        )

        conn.execute(
            """CREATE TABLE reminder_log_v25 (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                interview_id INTEGER,
                orphaned_interview_id INTEGER,
                reminder_type TEXT NOT NULL,
                sent_to TEXT NOT NULL,
                provider TEXT,
                status TEXT NOT NULL,
                sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                notes TEXT,
                FOREIGN KEY (interview_id) REFERENCES interviews(id) ON DELETE SET NULL
            )"""
        )
        conn.execute(
            """INSERT INTO reminder_log_v25
               (id, interview_id, orphaned_interview_id, reminder_type, sent_to,
                provider, status, sent_at, notes)
               SELECT r.id,
                      CASE WHEN i.id IS NOT NULL THEN r.interview_id ELSE NULL END,
                      CASE WHEN i.id IS NULL THEN r.interview_id ELSE NULL END,
                      r.reminder_type, r.sent_to, r.provider, r.status, r.sent_at, r.notes
               FROM reminder_log r
               LEFT JOIN interviews i ON i.id = r.interview_id"""
        )
        conn.execute("DROP TABLE reminder_log")
        conn.execute("ALTER TABLE reminder_log_v25 RENAME TO reminder_log")

        before = {
            "orphan_interview_ids": orphan_interview_ids,
            "empty_episode_interview_link_ids": empty_episode_link_ids,
            "orphan_reminder_ids": orphan_reminder_ids,
        }
        conn.execute(
            """INSERT INTO audit_events
               (entity_type, entity_id, event_type, actor, source, reason,
                correlation_id, before_json, after_json)
               VALUES ('database_integrity', 'migration-25', 'legacy_orphan_references_repaired',
                       'system', 'schema_migration',
                       'Preserved records while normalizing invalid legacy foreign-key values.',
                       'migration-25', ?, ?)""",
            (
                json.dumps(before, sort_keys=True),
                json.dumps(
                    {
                        "interview_guest_links_cleared": len(orphan_interview_ids),
                        "episode_interview_links_cleared": len(empty_episode_link_ids),
                        "reminder_links_preserved_as_provenance": len(orphan_reminder_ids),
                    },
                    sort_keys=True,
                ),
            ),
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
            (14, "partner_intelligence", SchemaManager._migration_014_partner_intelligence),
            (15, "marketing_opt_in", SchemaManager._migration_015_marketing_opt_in),
            (16, "partner_contact_research", SchemaManager._migration_016_partner_contact_research),
            (17, "recommendation_learning", SchemaManager._migration_017_recommendation_learning),
            (18, "partner_automation", SchemaManager._migration_018_partner_automation),
            (19, "apollo_partner_enrichment", SchemaManager._migration_019_apollo_partner_enrichment),
            (20, "partner_pitch_studio", SchemaManager._migration_020_partner_pitch_studio),
            (21, "partner_source_intelligence", SchemaManager._migration_021_partner_source_intelligence),
            (22, "reschedule_proposals", SchemaManager._migration_022_reschedule_proposals),
            (23, "growth_intelligence", SchemaManager._migration_023_growth_intelligence),
            (24, "growth_evidence_integrity", SchemaManager._migration_024_growth_evidence_integrity),
            (25, "repair_legacy_orphan_references", SchemaManager._migration_025_repair_legacy_orphan_references),
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
