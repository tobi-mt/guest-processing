"""Guest database management module."""

import sqlite3
import pandas as pd
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class GuestDatabase:
    """Manages the SQLite database for guest information."""
    
    def __init__(self, db_path: str = "guest_database.db"):
        """Initialize the database connection and create tables if needed."""
        self.db_path = db_path
        self.create_tables()
    
    def create_tables(self):
        """Create the guests table if it doesn't exist."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS guests (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    
                    -- Basic Info (matching Excel questionnaire)
                    full_name TEXT NOT NULL,                    -- Column 1: Full name
                    email TEXT,                                 -- Column 2: Email2 or Email1 or Guest's Email
                    website TEXT,                              -- Column 3: Website
                    social_media_handles TEXT,                 -- Column 4: "Kindly list your active social media handles?"
                    
                    -- Professional Background
                    personal_professional_background TEXT,      -- Column 5: "A brief overview of your personal and professional background"
                    current_path TEXT,                         -- Column 6: "What is your current profession, and what led you to this career path?"
                    motivation TEXT,                           -- Column 7: "What motivates or inspires you in your work and life?"
                    life_experience TEXT,                      -- Column 8: "What life experiences or pivotal moments have shaped who you are today?"
                    
                    -- Values and Philosophy
                    core_values TEXT,                          -- Column 9: "What are your core values or guiding principles?"
                    life_practice TEXT,                        -- Column 10: "Do you follow a specific faith, spiritual practice, or philosophical tradition?"
                    life_practice_alignment TEXT,              -- Column 11: "Do you believe your beliefs and values align with the themes of soulful conversations?"
                    favourite_quote TEXT,                      -- Column 12: "Do you have a favourite quote or philosophy that guides your life?"
                    
                    -- Discussion Topics
                    passion_topic TEXT,                        -- Column 13: "What topics or themes are you most passionate about discussing?"
                    listeners_takeaway TEXT,                   -- Column 14: "What message or takeaway would you like to leave with our listeners?"
                    podcast_experience TEXT,                   -- Column 15: "Have you been a guest on podcasts or spoken at events before?"
                    anything_else TEXT,                        -- Column 16: "Is there anything else you'd like us to know about you?"
                    
                    -- Engagement
                    following_us TEXT,                         -- Column 17: "Are you following us on podcast platforms and social media?"
                    accuracy_confirmed TEXT,                   -- Column 18: "Do you confirm that all questions and fields have been answered fully and accurately?"
                    
                    -- System fields
                    is_processed BOOLEAN DEFAULT FALSE,
                    email_status TEXT,
                    email_sent_at TIMESTAMP,
                    skip_reason TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    
                    -- Keep original data for reference
                    original_data TEXT,                        -- JSON dump of original record
                    
                    UNIQUE(full_name, email)
                )
            """)
            
            # Add new columns if they don't exist (for existing databases)
            try:
                conn.execute("ALTER TABLE guests ADD COLUMN email_status TEXT")
            except sqlite3.OperationalError:
                pass  # Column already exists
            
            try:
                conn.execute("ALTER TABLE guests ADD COLUMN email_sent_at TIMESTAMP")
            except sqlite3.OperationalError:
                pass  # Column already exists
            
            try:
                conn.execute("ALTER TABLE guests ADD COLUMN skip_reason TEXT")
            except sqlite3.OperationalError:
                pass  # Column already exists
            
            try:
                conn.execute("ALTER TABLE guests ADD COLUMN updated_at TIMESTAMP")
            except sqlite3.OperationalError:
                pass  # Column already exists
                
            conn.commit()
    
    def get_column_value(self, row: pd.Series, possible_columns: List[str]) -> str:
        """Get value from row using possible column names, handling case and whitespace."""
        for col in possible_columns:
            # Try exact match first
            if col in row.index and pd.notna(row[col]):
                return str(row[col]).strip()
            
            # Try case-insensitive match
            for actual_col in row.index:
                if actual_col.lower().strip() == col.lower().strip():
                    if pd.notna(row[actual_col]):
                        return str(row[actual_col]).strip()
            
            # Try partial match (contains)
            for actual_col in row.index:
                if col.lower() in actual_col.lower() or actual_col.lower() in col.lower():
                    if pd.notna(row[actual_col]):
                        return str(row[actual_col]).strip()
        
        return ""
    
    def _clean_guest_data(self, row: pd.Series) -> Dict[str, Any]:
        """Clean and normalize guest data from a pandas Series."""
        
        # Define possible column names for each field
        name_columns = ["Full name", "full_name", "Name", "name", "Full Name", "Guest Name", "guest_name"]
        email_columns = [
            "Email2", "email2", "Guest's Email", "guest's email", "Guest Email", "guest_email",
            "Email", "email", "Email Address", "email_address", "E-mail", "e-mail",
            "Contact Email", "contact_email", "Primary Email", "primary_email"
        ]
        phone_columns = ["Phone", "phone", "Phone Number", "phone_number", "Mobile", "mobile", "Contact Number", "contact_number"]
        instagram_columns = ["Instagram", "instagram", "Instagram Handle", "instagram_handle", "IG", "ig", "@instagram", "Social Media - Instagram"]
        facebook_columns = ["Facebook", "facebook", "Facebook Profile", "facebook_profile", "FB", "fb", "Social Media - Facebook"]
        website_columns = ["Website", "website", "Website URL", "website_url", "Web", "web", "Site", "site", "Do you have a website?"]
        location_columns = ["Location", "location", "City", "city", "State", "state", "Country", "country", "Where are you based?", "Based in"]
        business_type_columns = ["Business Type", "business_type", "Industry", "industry", "Business", "business", "What type of business", "Type of business"]
        business_stage_columns = ["Business Stage", "business_stage", "Stage", "stage", "Business Phase", "business_phase", "What stage is your business", "Stage of business"]
        topics_columns = ["Topics", "topics", "Interview Topics", "interview_topics", "Discussion Topics", "discussion_topics", "What would you like to discuss", "Topics of interest"]
        challenges_columns = ["Challenges", "challenges", "Business Challenges", "business_challenges", "Current Challenges", "current_challenges", "What challenges are you facing", "Main challenges"]
        goals_columns = ["Goals", "goals", "Business Goals", "business_goals", "Objectives", "objectives", "What are your goals", "Main goals"]
        previous_guest_columns = ["Previous Guest", "previous_guest", "Been on podcast before", "Previous Appearance", "previous_appearance"]
        referral_columns = ["Referral Source", "referral_source", "How did you hear about us", "Referral", "referral", "Source", "source"]
        additional_info_columns = ["Additional Information", "additional_information", "Additional Info", "additional_info", "Comments", "comments", "Notes", "notes", "Other", "other", "Anything else", "Additional notes"]
        
        # Additional columns from the real questionnaire
        background_columns = ["A brief overview of your personal and professional background", "background", "Background"]
        profession_columns = ["What is your current profession, and what led you to this career path?", "profession", "Profession", "Current profession"]
        motivation_columns = ["What motivates or inspires you in your work and life?\n", "motivation", "Motivation", "What motivates you"]
        life_experiences_columns = ["What life experiences or pivotal moments have shaped who you are today?\n", "life_experiences", "Life experiences", "Pivotal moments"]
        core_values_columns = ["What are your core values or guiding principles?\n", "core_values", "Core values", "Values"]
        faith_columns = ["Do you follow a specific faith, spiritual practice, or philosophical tradition?\n", "faith", "Faith", "Spiritual practice"]
        alignment_columns = ["Do you believe your beliefs and values align with the themes of soulful conversations?\n", "alignment", "Alignment", "Values alignment"]
        favorite_quote_columns = ["Do you have a favourite quote or philosophy that guides your life?", "favorite_quote", "Favorite quote", "Quote"]
        passionate_topics_columns = ["What topics or themes are you most passionate about discussing?\n", "passionate_topics", "Passionate topics", "Discussion themes"]
        message_columns = ["What message or takeaway would you like to leave with our listeners?\n", "message", "Message", "Takeaway"]
        experience_columns = ["Have you been a guest on podcasts or spoken at events before?\n", "experience", "Experience", "Previous experience"]
        social_media_columns = ["Do you have social media handles?", "has_social_media", "Social media", "Social media handles"]
        social_handles_columns = ["Kindly list your active social media handles?", "social_handles", "Social handles", "Active social media"]
        
        return {
            'full_name': self.get_column_value(row, name_columns),
            'email': self.get_column_value(row, email_columns),
            'phone': self.get_column_value(row, phone_columns),
            'instagram': self.get_column_value(row, instagram_columns),
            'facebook': self.get_column_value(row, facebook_columns),
            'website': self.get_column_value(row, website_columns),
            'location': self.get_column_value(row, location_columns),
            'business_type': self.get_column_value(row, business_type_columns),
            'business_stage': self.get_column_value(row, business_stage_columns),
            'topics': self.get_column_value(row, topics_columns),
            'challenges': self.get_column_value(row, challenges_columns),
            'goals': self.get_column_value(row, goals_columns),
            'previous_guest': self.get_column_value(row, previous_guest_columns),
            'referral_source': self.get_column_value(row, referral_columns),
            'additional_info': self.get_column_value(row, additional_info_columns),
            'background': self.get_column_value(row, background_columns),
            'profession': self.get_column_value(row, profession_columns),
            'motivation': self.get_column_value(row, motivation_columns),
            'life_experiences': self.get_column_value(row, life_experiences_columns),
            'core_values': self.get_column_value(row, core_values_columns),
            'faith': self.get_column_value(row, faith_columns),
            'alignment': self.get_column_value(row, alignment_columns),
            'favorite_quote': self.get_column_value(row, favorite_quote_columns),
            'passionate_topics': self.get_column_value(row, passionate_topics_columns),
            'message': self.get_column_value(row, message_columns),
            'experience': self.get_column_value(row, experience_columns),
            'has_social_media': self.get_column_value(row, social_media_columns),
            'social_handles': self.get_column_value(row, social_handles_columns),
            'is_processed': False
        }
    
    def import_from_csv(self, file_path: str, encoding: str = 'utf-8') -> Dict[str, int]:
        """Import guest data from a CSV file with robust error handling."""
        stats = {'imported': 0, 'updated': 0, 'skipped': 0, 'errors': 0}
        
        try:
            # Try multiple encodings and reading strategies
            encodings_to_try = [encoding, 'utf-8', 'latin-1', 'cp1252', 'iso-8859-1']
            df = None
            
            for enc in encodings_to_try:
                try:
                    logger.info(f"Trying to read CSV with encoding: {enc}")
                    # Try with error handling for bad lines
                    df = pd.read_csv(
                        file_path, 
                        encoding=enc,
                        on_bad_lines='skip',  # Skip problematic lines
                        engine='c'  # Use C engine for better performance
                    )
                    logger.info(f"Successfully read CSV with encoding: {enc}")
                    break
                except (UnicodeDecodeError, pd.errors.ParserError) as e:
                    logger.warning(f"Failed to read with encoding {enc}: {e}")
                    continue
            
            if df is None:
                # Fallback to python engine if C engine fails
                try:
                    logger.info("Trying fallback with python engine")
                    df = pd.read_csv(
                        file_path,
                        encoding='utf-8',
                        on_bad_lines='skip',
                        engine='python'
                    )
                except Exception as e:
                    raise Exception(f"Could not read CSV file with any encoding: {e}")
            
            if df.empty:
                logger.warning("CSV file is empty or contains no valid data")
                return stats
            
            logger.info(f"Read CSV with {len(df)} rows and columns: {list(df.columns)}")
            
            # Process each row
            for index, row in df.iterrows():
                try:
                    guest_data = self._clean_guest_data(row)
                    
                    # Skip if no name
                    if not guest_data['full_name']:
                        logger.warning(f"Row {index + 1}: Skipping - no name found")
                        stats['skipped'] += 1
                        continue
                    
                    # Check if guest already exists (by name, case-insensitive)
                    existing_guest = self.get_guest_by_name(guest_data['full_name'])
                    
                    if existing_guest:
                        # Preserve important fields when updating
                        guest_data['is_processed'] = existing_guest['is_processed']
                        guest_data['email_status'] = existing_guest.get('email_status')
                        guest_data['email_sent_at'] = existing_guest.get('email_sent_at')
                        guest_data['skip_reason'] = existing_guest.get('skip_reason')
                        
                        # If new email is better than existing (not anonymous), update it
                        if (guest_data['email'] and guest_data['email'] != 'anonymous' and 
                            (not existing_guest['email'] or existing_guest['email'] == 'anonymous')):
                            logger.info(f"Row {index + 1}: Updating email for {guest_data['full_name']} from '{existing_guest['email']}' to '{guest_data['email']}'")
                        
                        self.update_guest_by_id(existing_guest['id'], guest_data)
                        stats['updated'] += 1
                        logger.info(f"Row {index + 1}: Updated guest {guest_data['full_name']}")
                    else:
                        # Insert new guest
                        self.insert_guest(guest_data)
                        stats['imported'] += 1
                        logger.info(f"Row {index + 1}: Imported new guest {guest_data['full_name']}")
                        
                except Exception as e:
                    logger.error(f"Row {index + 1}: Error processing row - {e}")
                    stats['errors'] += 1
                    continue
            
            logger.info(f"Import completed. Stats: {stats}")
            return stats
            
        except Exception as e:
            logger.error(f"Error importing CSV: {e}")
            stats['errors'] += 1
            return stats
    
    def import_from_excel(self, file_path: str) -> Dict[str, int]:
        """Import guest data from an Excel file."""
        stats = {'imported': 0, 'updated': 0, 'skipped': 0, 'errors': 0}
        
        try:
            # Read Excel file
            df = pd.read_excel(file_path)
            logger.info(f"Read Excel with {len(df)} rows and columns: {list(df.columns)}")
            
            # Process each row
            for index, row in df.iterrows():
                try:
                    guest_data = self._clean_guest_data(row)
                    
                    # Skip if no name
                    if not guest_data['full_name']:
                        logger.warning(f"Row {index + 1}: Skipping - no name found")
                        stats['skipped'] += 1
                        continue
                    
                    # Check if guest already exists (by name, case-insensitive)
                    existing_guest = self.get_guest_by_name(guest_data['full_name'])
                    
                    if existing_guest:
                        # Preserve important fields when updating
                        guest_data['is_processed'] = existing_guest['is_processed']
                        guest_data['email_status'] = existing_guest.get('email_status')
                        guest_data['email_sent_at'] = existing_guest.get('email_sent_at')
                        guest_data['skip_reason'] = existing_guest.get('skip_reason')
                        
                        # If new email is better than existing (not anonymous), update it
                        if (guest_data['email'] and guest_data['email'] != 'anonymous' and 
                            (not existing_guest['email'] or existing_guest['email'] == 'anonymous')):
                            logger.info(f"Row {index + 1}: Updating email for {guest_data['full_name']} from '{existing_guest['email']}' to '{guest_data['email']}'")
                        
                        self.update_guest_by_id(existing_guest['id'], guest_data)
                        stats['updated'] += 1
                        logger.info(f"Row {index + 1}: Updated guest {guest_data['full_name']}")
                    else:
                        # Insert new guest
                        self.insert_guest(guest_data)
                        stats['imported'] += 1
                        logger.info(f"Row {index + 1}: Imported new guest {guest_data['full_name']}")
                        
                except Exception as e:
                    logger.error(f"Row {index + 1}: Error processing row - {e}")
                    stats['errors'] += 1
                    continue
            
            logger.info(f"Import completed. Stats: {stats}")
            return stats
            
        except Exception as e:
            logger.error(f"Error importing Excel: {e}")
            stats['errors'] += 1
            return stats
    
    def guest_exists_by_name(self, name: str) -> bool:
        """Check if a guest already exists based on name (case-insensitive) only."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT COUNT(*) FROM guests WHERE LOWER(TRIM(name)) = LOWER(TRIM(?))",
                (name,)
            )
            return cursor.fetchone()[0] > 0
    
    def get_guest_by_name(self, name: str) -> Optional[Dict]:
        """Get a guest by name (case-insensitive), preferring one with real email."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            
            # Get by name, preferring real email over anonymous
            cursor = conn.execute("""
                SELECT * FROM guests 
                WHERE LOWER(TRIM(full_name)) = LOWER(TRIM(?)) 
                ORDER BY 
                    CASE WHEN email != 'anonymous' AND email IS NOT NULL AND email != '' THEN 0 ELSE 1 END,
                    id 
                LIMIT 1
            """, (name,))
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def get_guest_by_name_email(self, name: str, email: str) -> Optional[Dict]:
        """Get a guest by name (case-insensitive) and email, or just by name if no exact email match."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            
            # First try exact name and email match
            cursor = conn.execute(
                "SELECT * FROM guests WHERE LOWER(TRIM(full_name)) = LOWER(TRIM(?)) AND email = ?",
                (name, email)
            )
            row = cursor.fetchone()
            if row:
                return dict(row)
            
            # If no exact email match, try to find by name only (to update existing guest)
            cursor = conn.execute(
                "SELECT * FROM guests WHERE LOWER(TRIM(full_name)) = LOWER(TRIM(?)) ORDER BY id LIMIT 1",
                (name,)
            )
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def insert_guest(self, guest_data: Dict[str, Any]) -> int:
        """Insert a new guest into the database."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                INSERT INTO guests (
                    name, full_name, email, website, social_media_handles, 
                    background, profession, motivation, life_experiences, core_values, 
                    faith_practice, beliefs_align, favorite_quote, passionate_topics, message_takeaway,
                    podcast_experience, additional_info, following_us, is_processed,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """, (
                guest_data.get('full_name'), guest_data.get('full_name'), guest_data.get('email'), 
                guest_data.get('website'), guest_data.get('social_handles'),
                guest_data.get('background'), guest_data.get('profession'), guest_data.get('motivation'), 
                guest_data.get('life_experiences'), guest_data.get('core_values'), guest_data.get('faith'), 
                guest_data.get('alignment'), guest_data.get('favorite_quote'), guest_data.get('passionate_topics'), 
                guest_data.get('message'), guest_data.get('experience'), guest_data.get('additional_info'), 
                guest_data.get('has_social_media'), guest_data.get('is_processed', False)
            ))
            conn.commit()
            return cursor.lastrowid
    
    def update_guest(self, guest_data: Dict[str, Any]) -> None:
        """Update an existing guest in the database."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                UPDATE guests SET
                    website = ?, social_media_handles = ?, personal_professional_background = ?,
                    current_path = ?, motivation = ?, life_experience = ?, core_values = ?,
                    life_practice = ?, life_practice_alignment = ?, favourite_quote = ?,
                    passion_topic = ?, listeners_takeaway = ?, podcast_experience = ?,
                    anything_else = ?, following_us = ?, accuracy_confirmed = ?,
                    is_processed = ?, updated_at = CURRENT_TIMESTAMP
                WHERE full_name = ? AND email = ?
            """, (
                guest_data.get('website'), guest_data.get('social_handles'), guest_data.get('background'),
                guest_data.get('profession'), guest_data.get('motivation'), guest_data.get('life_experiences'),
                guest_data.get('core_values'), guest_data.get('faith'), guest_data.get('alignment'),
                guest_data.get('favorite_quote'), guest_data.get('passionate_topics'), guest_data.get('message'),
                guest_data.get('experience'), guest_data.get('additional_info'), guest_data.get('has_social_media'),
                guest_data.get('accuracy_confirmed'), guest_data.get('is_processed'),
                guest_data.get('full_name'), guest_data.get('email')
            ))
            conn.commit()
    
    def update_guest_by_id(self, guest_id: int, guest_data: Dict[str, Any]) -> None:
        """Update an existing guest in the database by ID."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                UPDATE guests SET
                    name = ?, full_name = ?, email = ?, website = ?, social_media_handles = ?,
                    background = ?, profession = ?, motivation = ?, life_experiences = ?, 
                    core_values = ?, faith_practice = ?, beliefs_align = ?, favorite_quote = ?,
                    passionate_topics = ?, message_takeaway = ?, podcast_experience = ?, 
                    additional_info = ?, following_us = ?, is_processed = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (
                guest_data.get('full_name'), guest_data.get('full_name'), guest_data.get('email'), 
                guest_data.get('website'), guest_data.get('social_handles'), guest_data.get('background'), 
                guest_data.get('profession'), guest_data.get('motivation'), guest_data.get('life_experiences'), 
                guest_data.get('core_values'), guest_data.get('faith'), guest_data.get('alignment'), 
                guest_data.get('favorite_quote'), guest_data.get('passionate_topics'), guest_data.get('message'), 
                guest_data.get('experience'), guest_data.get('additional_info'), guest_data.get('has_social_media'), 
                guest_data.get('is_processed'), guest_id
            ))
            conn.commit()
    
    def delete_guest(self, guest_id: int) -> None:
        """Delete a guest from the database."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM guests WHERE id = ?", (guest_id,))
            conn.commit()
    
    def get_all_guests(self) -> List[Dict]:
        """Get all guests from the database."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("SELECT * FROM guests ORDER BY date_added DESC")
            return [dict(row) for row in cursor.fetchall()]
    
    def get_guests_by_status(self, is_processed: bool) -> List[Dict]:
        """Get guests filtered by processing status."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT * FROM guests WHERE is_processed = ? ORDER BY date_added DESC",
                (is_processed,)
            )
            return [dict(row) for row in cursor.fetchall()]
    
    def mark_guest_processed(self, guest_id: int) -> None:
        """Mark a guest as processed."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE guests SET is_processed = TRUE, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (guest_id,)
            )
            conn.commit()
    
    def mark_guest_unprocessed(self, guest_id: int) -> None:
        """Mark a guest as unprocessed and clear email status."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """UPDATE guests SET 
                   is_processed = FALSE, 
                   email_status = NULL, 
                   email_sent_at = NULL, 
                   skip_reason = NULL,
                   updated_at = CURRENT_TIMESTAMP 
                   WHERE id = ?""",
                (guest_id,)
            )
            conn.commit()

    def accept_guest_with_email(self, guest_id: int, custom_message: str = "") -> None:
        """Mark a guest as accepted and record that an acceptance email was sent."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """UPDATE guests SET 
                   is_processed = TRUE, 
                   email_status = 'accepted', 
                   email_sent_at = CURRENT_TIMESTAMP,
                   updated_at = CURRENT_TIMESTAMP 
                   WHERE id = ?""",
                (guest_id,)
            )
            conn.commit()

    def reject_guest_with_email(self, guest_id: int, custom_message: str = "") -> None:
        """Mark a guest as rejected and record that a rejection email was sent."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """UPDATE guests SET 
                   is_processed = TRUE, 
                   email_status = 'rejected', 
                   email_sent_at = CURRENT_TIMESTAMP,
                   updated_at = CURRENT_TIMESTAMP 
                   WHERE id = ?""",
                (guest_id,)
            )
            conn.commit()

    def skip_guest(self, guest_id: int, skip_reason: str = "") -> None:
        """Mark a guest as skipped with an optional reason."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """UPDATE guests SET 
                   is_processed = TRUE, 
                   email_status = 'skipped', 
                   skip_reason = ?,
                   updated_at = CURRENT_TIMESTAMP 
                   WHERE id = ?""",
                (skip_reason, guest_id)
            )
            conn.commit()

    def get_stats(self) -> Dict[str, int]:
        """Get database statistics."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("SELECT COUNT(*) FROM guests")
            total = cursor.fetchone()[0]
            
            cursor = conn.execute("SELECT COUNT(*) FROM guests WHERE is_processed = TRUE")
            processed = cursor.fetchone()[0]
            
            cursor = conn.execute("SELECT COUNT(*) FROM guests WHERE is_processed = FALSE")
            unprocessed = cursor.fetchone()[0]
            
            return {
                'total': total,
                'processed': processed,
                'unprocessed': unprocessed
            }
    
    def get_email_stats(self) -> Dict[str, int]:
        """Get email-related statistics."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("SELECT COUNT(*) FROM guests WHERE email IS NOT NULL AND email != ''")
            with_email = cursor.fetchone()[0]
            
            cursor = conn.execute("SELECT COUNT(*) FROM guests WHERE email IS NULL OR email = ''")
            without_email = cursor.fetchone()[0]
            
            # Count emails sent (guests with email_status set)
            cursor = conn.execute("SELECT COUNT(*) FROM guests WHERE email_status IS NOT NULL")
            total_emails = cursor.fetchone()[0]
            
            # Count accepted emails
            cursor = conn.execute("SELECT COUNT(*) FROM guests WHERE email_status = 'accepted'")
            accepted_emails = cursor.fetchone()[0]
            
            # Count rejected emails
            cursor = conn.execute("SELECT COUNT(*) FROM guests WHERE email_status = 'rejected'")
            rejected_emails = cursor.fetchone()[0]
            
            # Count skipped guests
            cursor = conn.execute("SELECT COUNT(*) FROM guests WHERE email_status = 'skipped'")
            skipped_guests = cursor.fetchone()[0]
            
            return {
                'with_email': with_email,
                'without_email': without_email,
                'total_emails': total_emails,
                'accepted_emails': accepted_emails,
                'rejected_emails': rejected_emails,
                'skipped_guests': skipped_guests
            }
