#!/usr/bin/env python3
"""
Fix CSV Import Issues - Robust Import Script
============================================

This script will:
1. Check the current database schema
2. Add missing columns if needed
3. Import the CSV file with proper error handling
"""

import pandas as pd
import sqlite3
import re
import json
from datetime import datetime
from pathlib import Path
import sys


def check_and_update_schema():
    """Check current database schema and add missing columns if needed."""
    print("🔍 Checking database schema...")
    
    conn = sqlite3.connect('guest_database.db')
    cursor = conn.cursor()
    
    # Get current columns
    cursor.execute("PRAGMA table_info(guests)")
    current_columns = {row[1] for row in cursor.fetchall()}
    print(f"📋 Current columns: {sorted(current_columns)}")
    
    # Define required columns for CSV import
    required_columns = {
        'id': 'INTEGER PRIMARY KEY AUTOINCREMENT',
        'full_name': 'TEXT',
        'name': 'TEXT',  # For backward compatibility
        'email': 'TEXT',
        'website': 'TEXT',
        'social_media_handles': 'TEXT',
        'personal_professional_background': 'TEXT',
        'current_path': 'TEXT',
        'motivation': 'TEXT',
        'life_experience': 'TEXT',
        'core_values': 'TEXT',
        'life_practice': 'TEXT',
        'life_practice_alignment': 'TEXT',
        'favourite_quote': 'TEXT',
        'passion_topic': 'TEXT',
        'listeners_takeaway': 'TEXT',
        'podcast_experience': 'TEXT',
        'anything_else': 'TEXT',
        'following_us': 'TEXT',
        'accuracy_confirmed': 'TEXT DEFAULT "No"',
        'is_processed': 'BOOLEAN DEFAULT 0',
        'date_added': 'TEXT',
        'original_data': 'TEXT'
    }
    
    # Add missing columns
    missing_columns = required_columns.keys() - current_columns
    
    if missing_columns:
        print(f"➕ Adding missing columns: {sorted(missing_columns)}")
        
        for column in missing_columns:
            column_def = required_columns[column]
            try:
                cursor.execute(f"ALTER TABLE guests ADD COLUMN {column} {column_def}")
                print(f"✅ Added column: {column}")
            except sqlite3.OperationalError as e:
                if "duplicate column name" not in str(e).lower():
                    print(f"❌ Error adding column {column}: {e}")
    else:
        print("✅ All required columns already exist")
    
    conn.commit()
    conn.close()


def clean_email(email_text):
    """Extract and clean email addresses from text."""
    if pd.isna(email_text) or not email_text:
        return None
    
    email_str = str(email_text).strip()
    
    # Skip anonymous or example emails
    if 'anonymous' in email_str.lower() or '@example.com' in email_str.lower():
        return None
    
    # Extract first valid email using regex
    email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
    emails = re.findall(email_pattern, email_str)
    
    return emails[0] if emails else None


def truncate_text(text, max_length=2000):
    """Truncate text to maximum length."""
    if pd.isna(text) or not text:
        return None
    
    text_str = str(text).strip()
    if len(text_str) > max_length:
        return text_str[:max_length-3] + "..."
    return text_str if text_str else None


def clean_text(text):
    """Clean and normalize text."""
    if pd.isna(text) or not text:
        return None
    
    text_str = str(text).strip()
    text_str = re.sub(r'\s+', ' ', text_str)
    text_str = ''.join(char for char in text_str if ord(char) >= 32 or char in '\n\r\t')
    
    return text_str if text_str else None


def import_csv_robust():
    """Import CSV file with robust error handling."""
    print("🔍 Starting robust CSV import...")
    
    # First, update the database schema
    check_and_update_schema()
    
    try:
        # Try to find the CSV file
        csv_files = [
            "/Users/tobi/Downloads/Soulful Guest Questionnaire 1(Sheet1).csv",
            "/Users/tobi/PycharmProjects/pythonProject/MT Guest Processing/Soulful Guest Questionnaire 1(Sheet1).csv"
        ]
        
        df = None
        csv_file = None
        
        for file_path in csv_files:
            if Path(file_path).exists():
                print(f"📂 Found CSV file: {file_path}")
                
                # Try different encodings and separators
                for encoding in ['utf-8', 'latin-1', 'cp1252', 'iso-8859-1']:
                    for separator in [',', ';', '\t']:
                        try:
                            df = pd.read_csv(file_path, encoding=encoding, sep=separator)
                            if len(df.columns) > 5:  # Ensure we have enough columns
                                csv_file = file_path
                                print(f"✅ Successfully read CSV with {encoding} encoding and '{separator}' separator")
                                break
                        except Exception:
                            continue
                    if df is not None:
                        break
                if df is not None:
                    break
        
        if df is None:
            print("❌ Could not read any CSV file")
            return
        
        print(f"📊 CSV contains {len(df)} rows and {len(df.columns)} columns")
        print(f"📋 Columns: {list(df.columns)}")
        
        # Connect to database
        conn = sqlite3.connect('guest_database.db')
        cursor = conn.cursor()
        
        # Get existing emails and names to prevent duplicates
        cursor.execute("SELECT email FROM guests WHERE email IS NOT NULL AND email != ''")
        existing_emails = {row[0] for row in cursor.fetchall()}
        
        cursor.execute("SELECT full_name FROM guests WHERE full_name IS NOT NULL")
        existing_names = {row[0].lower() for row in cursor.fetchall()}
        
        imported = 0
        updated = 0
        skipped = 0
        errors = 0
        
        for index, row in df.iterrows():
            try:
                print(f"\n🔄 Processing row {index + 1}/{len(df)}")
                
                # Extract and clean basic fields
                full_name = clean_text(row.get('Full name', ''))
                if not full_name:
                    full_name = clean_text(row.get('Name', ''))
                
                if not full_name or len(full_name.strip()) < 2:
                    print(f"⚠️ Skipping row {index + 1}: No valid name found")
                    skipped += 1
                    continue
                
                # Check for duplicate names
                if full_name.lower() in existing_names:
                    print(f"⚠️ Skipping {full_name}: Name already exists")
                    skipped += 1
                    continue
                
                # Clean email with priority: Email2 > Email > others
                email = None
                for email_col in ['Email2', 'Email', 'email']:
                    if email_col in row:
                        email = clean_email(row[email_col])
                        if email:
                            break
                
                # Skip if email already exists
                if email and email in existing_emails:
                    print(f"⚠️ Skipping {full_name}: Email {email} already exists")
                    skipped += 1
                    continue
                
                # Prepare guest data with proper column mapping
                guest_data = {
                    'name': truncate_text(full_name, 100),  # For backward compatibility
                    'full_name': truncate_text(full_name, 200),
                    'email': email,
                    'website': truncate_text(clean_text(row.get('Website', '') or row.get('Do you have a website?', '')), 300),
                    'social_media_handles': truncate_text(clean_text(row.get('Kindly list your active social media handles?', '')), 1000),
                    'personal_professional_background': truncate_text(clean_text(row.get('A brief overview of your personal and professional background', '')), 3000),
                    'current_path': truncate_text(clean_text(row.get('What is your current profession, and what led you to this career path?', '')), 3000),
                    'motivation': truncate_text(clean_text(
                        row.get('What motivates or inspires you in your work and life?\n', '') or 
                        row.get('What motivates or inspires you in your work and life?', '')
                    ), 3000),
                    'life_experience': truncate_text(clean_text(
                        row.get('What life experiences or pivotal moments have shaped who you are today?\n', '') or
                        row.get('What life experiences or pivotal moments have shaped who you are today?', '')
                    ), 3000),
                    'core_values': truncate_text(clean_text(
                        row.get('What are your core values or guiding principles?\n', '') or
                        row.get('What are your core values or guiding principles?', '')
                    ), 3000),
                    'life_practice': truncate_text(clean_text(
                        row.get('Do you follow a specific faith, spiritual practice, or philosophical tradition?\n', '') or
                        row.get('Do you follow a specific faith, spiritual practice, or philosophical tradition?', '')
                    ), 3000),
                    'life_practice_alignment': truncate_text(clean_text(row.get('Do you believe your beliefs and values align with the themes of soulful conversations?', '')), 2000),
                    'favourite_quote': truncate_text(clean_text(row.get('Do you have a favourite quote or philosophy that guides your life?', '')), 2000),
                    'passion_topic': truncate_text(clean_text(
                        row.get('What topics or themes are you most passionate about discussing?\n', '') or
                        row.get('What topics or themes are you most passionate about discussing?', '')
                    ), 3000),
                    'listeners_takeaway': truncate_text(clean_text(
                        row.get('What message or takeaway would you like to leave with our listeners?\n', '') or
                        row.get('What message or takeaway would you like to leave with our listeners?', '')
                    ), 3000),
                    'podcast_experience': truncate_text(clean_text(
                        row.get('Have you been a guest on podcasts or spoken at events before?\n', '') or
                        row.get('Have you been a guest on podcasts or spoken at events before?', '')
                    ), 3000),
                    'anything_else': truncate_text(clean_text(
                        row.get('Is there anything else you\'d like us to know about you?\n', '') or
                        row.get('Is there anything else you\'d like us to know about you?', '')
                    ), 3000),
                    'following_us': truncate_text(clean_text(row.get('Are you following us on podcast platforms and social media?', '')), 1000),
                    'accuracy_confirmed': 'No',
                    'is_processed': False,
                    'date_added': datetime.now().isoformat(),
                    'original_data': json.dumps(dict(row), default=str)[:4000]  # Store original data
                }
                
                # Remove None values to avoid database issues
                guest_data = {k: v for k, v in guest_data.items() if v is not None}
                
                # Insert into database
                placeholders = ', '.join(['?' for _ in guest_data.keys()])
                columns = ', '.join(guest_data.keys())
                
                cursor.execute(f"""
                    INSERT INTO guests ({columns})
                    VALUES ({placeholders})
                """, list(guest_data.values()))
                
                # Track duplicates
                if email:
                    existing_emails.add(email)
                existing_names.add(full_name.lower())
                
                imported += 1
                print(f"✅ Imported: {full_name} ({email or 'no email'})")
                
            except Exception as e:
                errors += 1
                print(f"❌ Error processing row {index + 1}: {e}")
                continue
        
        # Commit all changes
        conn.commit()
        conn.close()
        
        print(f"\n🎉 Import completed successfully!")
        print(f"✅ Imported: {imported}")
        print(f"🔄 Updated: {updated}")
        print(f"⚠️ Skipped: {skipped}")
        print(f"❌ Errors: {errors}")
        
        if errors == 0:
            print("\n🌟 Perfect! No errors occurred during import!")
        else:
            print(f"\n💡 {errors} rows had errors but import continued")
        
    except Exception as e:
        print(f"❌ Fatal error during import: {e}")
        raise


if __name__ == "__main__":
    import_csv_robust()
