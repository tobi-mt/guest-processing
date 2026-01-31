#!/usr/bin/env python3
"""
Import CSV Export from Questionnaire
"""

import pandas as pd
import sqlite3
import sys
import os
import json
from datetime import datetime

sys.path.append('src')

def import_csv_data(csv_file):
    """Import data from CSV questionnaire export."""
    
    print(f"Loading CSV file: {csv_file}")
    df = pd.read_csv(csv_file)
    print(f"Loaded {len(df)} rows with {len(df.columns)} columns")
    
    # Show columns
    print("\nAvailable columns:")
    for i, col in enumerate(df.columns, 1):
        print(f"  {i:2d}. {col}")
    
    # Import data
    imported = 0
    updated = 0
    skipped = 0
    
    with sqlite3.connect('guest_database.db') as conn:
        for _, row in df.iterrows():
            full_name = str(row.get('Full name', '')).strip()
            if not full_name or full_name == 'nan' or not full_name:
                skipped += 1
                continue
            
            # Prioritize Email2 over Email column (ignore "anonymous" in Email column)
            email = None
            email_col_priority = ['Email2', "Guest's Email", 'Email']
            
            for email_col in email_col_priority:
                if email_col in df.columns:
                    email_val = row.get(email_col, '')
                    if (pd.notna(email_val) and 
                        str(email_val).strip() and 
                        '@' in str(email_val) and 
                        str(email_val).strip().lower() != 'anonymous'):
                        email = str(email_val).strip()
                        print(f"  Using {email_col}: {email} for {full_name}")
                        break
            
            if not email:
                email = 'anonymous@example.com'
                print(f"  No valid email found for {full_name}, using placeholder")
            
            # Check if guest exists (by name)
            cursor = conn.execute("SELECT id, email FROM guests WHERE full_name = ?", (full_name,))
            existing = cursor.fetchone()
            
            # Store original data as JSON for future reference
            original_data = row.to_dict()
            
            if existing:
                # Update existing guest
                guest_id, current_email = existing
                print(f"  Updating existing guest: {full_name}")
                
                # Only update email if we have a better one
                update_email = email
                if (current_email and 
                    current_email != 'anonymous@example.com' and 
                    email == 'anonymous@example.com'):
                    update_email = current_email  # Keep the better email
                    print(f"    Keeping existing email: {current_email}")
                
                conn.execute("""
                    UPDATE guests SET 
                        email = ?, 
                        website = ?,
                        social_media_handles = ?,
                        personal_professional_background = ?,
                        current_path = ?,
                        motivation = ?,
                        life_experience = ?,
                        core_values = ?,
                        life_practice = ?,
                        life_practice_alignment = ?,
                        favourite_quote = ?,
                        passion_topic = ?,
                        listeners_takeaway = ?,
                        podcast_experience = ?,
                        anything_else = ?,
                        following_us = ?,
                        accuracy_confirmed = ?,
                        original_data = ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (
                    update_email,
                    row.get('Website', None),
                    row.get('Kindly list your active social media handles?', None),
                    row.get('A brief overview of your personal and professional background', None),
                    row.get('What is your current profession, and what led you to this career path?', None),
                    row.get('What motivates or inspires you in your work and life?\n', None),
                    row.get('What life experiences or pivotal moments have shaped who you are today?\n', None),
                    row.get('What are your core values or guiding principles?\n', None),
                    row.get('Do you follow a specific faith, spiritual practice, or philosophical tradition?\n', None),
                    row.get('Do you believe your beliefs and values align with the themes of soulful conversations?\n', None),
                    row.get('Do you have a favourite quote or philosophy that guides your life?', None),
                    row.get('What topics or themes are you most passionate about discussing?\n', None),
                    row.get('What message or takeaway would you like to leave with our listeners?\n', None),
                    row.get('Have you been a guest on podcasts or spoken at events before?\n', None),
                    row.get("Is there anything else you'd like us to know about you?\n", None),
                    row.get('Are you following us on podcast platforms and social media?', None),
                    row.get('Do you confirm that all questions and fields have been answered fully and accurately?', None),
                    json.dumps(original_data),
                    guest_id
                ))
                updated += 1
            else:
                # Insert new guest
                print(f"  Adding new guest: {full_name}")
                conn.execute("""
                    INSERT INTO guests (
                        full_name, email, website, social_media_handles,
                        personal_professional_background, current_path, motivation, life_experience,
                        core_values, life_practice, life_practice_alignment, favourite_quote,
                        passion_topic, listeners_takeaway, podcast_experience, anything_else,
                        following_us, accuracy_confirmed, is_processed, original_data
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    full_name, email, 
                    row.get('Website', None),
                    row.get('Kindly list your active social media handles?', None),
                    row.get('A brief overview of your personal and professional background', None),
                    row.get('What is your current profession, and what led you to this career path?', None),
                    row.get('What motivates or inspires you in your work and life?\n', None),
                    row.get('What life experiences or pivotal moments have shaped who you are today?\n', None),
                    row.get('What are your core values or guiding principles?\n', None),
                    row.get('Do you follow a specific faith, spiritual practice, or philosophical tradition?\n', None),
                    row.get('Do you believe your beliefs and values align with the themes of soulful conversations?\n', None),
                    row.get('Do you have a favourite quote or philosophy that guides your life?', None),
                    row.get('What topics or themes are you most passionate about discussing?\n', None),
                    row.get('What message or takeaway would you like to leave with our listeners?\n', None),
                    row.get('Have you been a guest on podcasts or spoken at events before?\n', None),
                    row.get("Is there anything else you'd like us to know about you?\n", None),
                    row.get('Are you following us on podcast platforms and social media?', None),
                    row.get('Do you confirm that all questions and fields have been answered fully and accurately?', None),
                    False,
                    json.dumps(original_data)
                ))
                imported += 1
    
    print(f"\n📊 Import Summary:")
    print(f"  ✅ New guests imported: {imported}")
    print(f"  🔄 Existing guests updated: {updated}")
    print(f"  ⏭️  Rows skipped: {skipped}")
    print(f"  📈 Total processed: {imported + updated}")

if __name__ == '__main__':
    csv_file = 'new_guest_export.csv'
    if os.path.exists(csv_file):
        import_csv_data(csv_file)
    else:
        print(f"CSV file '{csv_file}' not found. Please ensure the file exists in the current directory.")
