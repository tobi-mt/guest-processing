#!/usr/bin/env python3
"""
Simple Excel Questionnaire Importer
"""

import pandas as pd
import sqlite3
import sys
import os

sys.path.append('src')

def import_excel_data(excel_file):
    """Import data from Excel questionnaire."""
    
    print(f"Loading Excel file: {excel_file}")
    df = pd.read_excel(excel_file)
    print(f"Loaded {len(df)} rows with {len(df.columns)} columns")
    
    # Show columns
    print("\nAvailable columns:")
    for i, col in enumerate(df.columns, 1):
        print(f"  {i:2d}. {col}")
    
    # Import data
    imported = 0
    updated = 0
    
    with sqlite3.connect('guest_database.db') as conn:
        for _, row in df.iterrows():
            full_name = str(row.get('Full name', '')).strip()
            if not full_name or full_name == 'nan':
                continue
            
            # Get email with fallback
            email = None
            for email_col in ['Email2', 'Email1', "Guest's Email"]:
                if email_col in df.columns:
                    email_val = row.get(email_col, '')
                    if pd.notna(email_val) and '@' in str(email_val):
                        email = str(email_val).strip()
                        break
            
            if not email:
                email = 'anonymous@example.com'
            
            # Check if exists
            cursor = conn.execute("SELECT id FROM guests WHERE full_name = ?", (full_name,))
            existing = cursor.fetchone()
            
            if existing:
                # Update
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
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (
                    email,
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
                    existing[0]
                ))
                updated += 1
            else:
                # Insert
                conn.execute("""
                    INSERT INTO guests (
                        full_name, email, website, social_media_handles,
                        personal_professional_background, current_path, motivation, life_experience,
                        core_values, life_practice, life_practice_alignment, favourite_quote,
                        passion_topic, listeners_takeaway, podcast_experience, anything_else,
                        following_us, accuracy_confirmed, is_processed
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    False
                ))
                imported += 1
    
    print(f"\nImport complete:")
    print(f"  New guests: {imported}")
    print(f"  Updated guests: {updated}")

if __name__ == '__main__':
    if os.path.exists('sample_questionnaire.xlsx'):
        import_excel_data('sample_questionnaire.xlsx')
    else:
        print("No Excel file found. Please provide the questionnaire Excel file.")
