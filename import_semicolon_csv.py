#!/usr/bin/env python3
"""
Import script for semicolon-delimited CSV questionnaire files.
Handles the specific format from Soulful Guest Questionnaire(1-138).csv
"""

import sqlite3
import pandas as pd
import json
from datetime import datetime

def clean_text(text):
    """Clean and strip text, handle newlines"""
    if pd.isna(text) or text is None:
        return None
    
    text = str(text).strip()
    if text == '' or text.lower() in ['nan', 'none', 'null']:
        return None
    
    # Clean up newlines and extra spaces
    text = text.replace('\n', ' ').replace('\r', ' ')
    text = ' '.join(text.split())  # Remove extra whitespace
    
    return text

def is_real_email(email):
    """Check if email is real (not a placeholder)"""
    if not email:
        return False
    
    email = email.lower().strip()
    
    # Check for placeholder patterns
    fake_patterns = [
        'anonymous', 'example.com', 'test.com', 'fake.com', 
        'sample.com', 'placeholder', 'noemail', 'unknown',
        'temp.com', 'dummy.com'
    ]
    
    for pattern in fake_patterns:
        if pattern in email:
            return False
    
    # Basic email format check
    if '@' not in email or '.' not in email:
        return False
        
    return True

def import_semicolon_csv(csv_path, db_path='guest_database.db'):
    """Import guests from semicolon-delimited CSV file"""
    
    # Read CSV with semicolon delimiter
    print(f"Reading CSV file: {csv_path}")
    df = pd.read_csv(csv_path, delimiter=';')
    print(f"Found {len(df)} rows in CSV")
    
    # Connect to database
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    imported_count = 0
    skipped_count = 0
    updated_count = 0
    
    for index, row in df.iterrows():
        # Extract name from "Full name" column
        full_name = clean_text(row.get('Full name'))
        if not full_name:
            print(f"Row {index + 1}: No name found, skipping")
            skipped_count += 1
            continue
            
        # Extract email - prioritize Email2, fallback to Email
        email = None
        email2 = clean_text(row.get('Email2'))
        email1 = clean_text(row.get('Email'))
        
        if is_real_email(email2):
            email = email2
        elif is_real_email(email1):
            email = email1
        # If neither is real, leave email as None
        
        # Check if guest already exists
        cursor.execute(
            'SELECT id, is_processed FROM guests WHERE full_name = ? AND (email = ? OR (email IS NULL AND ? IS NULL))',
            (full_name, email, email)
        )
        existing = cursor.fetchone()
        
        if existing:
            existing_id, is_processed = existing
            # Update existing guest but preserve is_processed status
            print(f"Updating existing guest: {full_name}")
            
            # Prepare data for update
            guest_data = {
                'website': clean_text(row.get('Website')),
                'social_media': clean_text(row.get('Kindly list your active social media handles?')),
                'background': clean_text(row.get('A brief overview of your personal and professional background')),
                'profession': clean_text(row.get('What is your current profession, and what led you to this career path?')),
                'motivation': clean_text(row.get('What motivates or inspires you in your work and life?\n')),
                'life_experiences': clean_text(row.get('What life experiences or pivotal moments have shaped who you are today?\n')),
                'core_values': clean_text(row.get('What are your core values or guiding principles?\n')),
                'faith_practice': clean_text(row.get('Do you follow a specific faith, spiritual practice, or philosophical tradition?\n')),
                'beliefs_align': clean_text(row.get('Do you believe your beliefs and values align with the themes of soulful conversations?\n')),
                'favorite_quote': clean_text(row.get('Do you have a favourite quote or philosophy that guides your life?')),
                'passionate_topics': clean_text(row.get('What topics or themes are you most passionate about discussing?\n')),
                'message_takeaway': clean_text(row.get('What message or takeaway would you like to leave with our listeners?\n')),
                'podcast_experience': clean_text(row.get('Have you been a guest on podcasts or spoken at events before?\n')),
                'additional_info': clean_text(row.get('Is there anything else you\'d like us to know about you?\n')),
                'following_status': clean_text(row.get('Are you following us on podcast platforms and social media?'))
            }
            
            # Update query - preserve is_processed
            update_query = '''
                UPDATE guests SET
                    email = ?, website = ?, social_media = ?, 
                    background = ?, profession = ?, motivation = ?,
                    life_experiences = ?, core_values = ?, faith_practice = ?,
                    beliefs_align = ?, favorite_quote = ?, passionate_topics = ?,
                    message_takeaway = ?, podcast_experience = ?, additional_info = ?,
                    following_status = ?
                WHERE id = ?
            '''
            
            cursor.execute(update_query, (
                email, guest_data['website'], guest_data['social_media'],
                guest_data['background'], guest_data['profession'], 
                guest_data['motivation'], guest_data['life_experiences'], guest_data['core_values'],
                guest_data['faith_practice'], guest_data['beliefs_align'],
                guest_data['favorite_quote'], guest_data['passionate_topics'],
                guest_data['message_takeaway'], guest_data['podcast_experience'],
                guest_data['additional_info'], guest_data['following_status'],
                existing_id
            ))
            updated_count += 1
            
        else:
            # Insert new guest
            print(f"Adding new guest: {full_name}")
            
            # Prepare data for insert
            guest_data = {
                'name': full_name,  # Set both name and full_name for compatibility
                'full_name': full_name,
                'email': email,
                'website': clean_text(row.get('Website')),
                'social_media': clean_text(row.get('Kindly list your active social media handles?')),
                'background': clean_text(row.get('A brief overview of your personal and professional background')),
                'profession': clean_text(row.get('What is your current profession, and what led you to this career path?')),
                'motivation': clean_text(row.get('What motivates or inspires you in your work and life?\n')),
                'life_experiences': clean_text(row.get('What life experiences or pivotal moments have shaped who you are today?\n')),
                'core_values': clean_text(row.get('What are your core values or guiding principles?\n')),
                'faith_practice': clean_text(row.get('Do you follow a specific faith, spiritual practice, or philosophical tradition?\n')),
                'beliefs_align': clean_text(row.get('Do you believe your beliefs and values align with the themes of soulful conversations?\n')),
                'favorite_quote': clean_text(row.get('Do you have a favourite quote or philosophy that guides your life?')),
                'passionate_topics': clean_text(row.get('What topics or themes are you most passionate about discussing?\n')),
                'message_takeaway': clean_text(row.get('What message or takeaway would you like to leave with our listeners?\n')),
                'podcast_experience': clean_text(row.get('Have you been a guest on podcasts or spoken at events before?\n')),
                'additional_info': clean_text(row.get('Is there anything else you\'d like us to know about you?\n')),
                'following_status': clean_text(row.get('Are you following us on podcast platforms and social media?')),
                'is_processed': False
            }
            
            # Insert query
            insert_query = '''
                INSERT INTO guests (
                    name, full_name, email, website, social_media,
                    background, profession, motivation,
                    life_experiences, core_values, faith_practice,
                    beliefs_align, favorite_quote, passionate_topics,
                    message_takeaway, podcast_experience, additional_info,
                    following_status, is_processed, date_added
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            '''
            
            cursor.execute(insert_query, (
                guest_data['name'], guest_data['full_name'], guest_data['email'], guest_data['website'],
                guest_data['social_media'], guest_data['background'],
                guest_data['profession'], guest_data['motivation'], guest_data['life_experiences'],
                guest_data['core_values'], guest_data['faith_practice'],
                guest_data['beliefs_align'], guest_data['favorite_quote'],
                guest_data['passionate_topics'], guest_data['message_takeaway'],
                guest_data['podcast_experience'], guest_data['additional_info'],
                guest_data['following_status'], guest_data['is_processed']
            ))
            imported_count += 1
    
    # Commit changes
    conn.commit()
    conn.close()
    
    print(f"\nImport completed:")
    print(f"- New guests added: {imported_count}")
    print(f"- Existing guests updated: {updated_count}")
    print(f"- Rows skipped: {skipped_count}")
    
    return {
        'imported': imported_count,
        'updated': updated_count,
        'skipped': skipped_count
    }

if __name__ == "__main__":
    # Import the CSV file
    result = import_semicolon_csv('/Users/tobi/Documents/PODCAST/Soulful Guest Questionnaire(1-138).csv')
    
    # Verify the result
    conn = sqlite3.connect('guest_database.db')
    cursor = conn.cursor()
    
    cursor.execute('SELECT COUNT(*) FROM guests')
    total_guests = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM guests WHERE email IS NOT NULL')
    guests_with_email = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM guests WHERE email IS NULL')
    guests_without_email = cursor.fetchone()[0]
    
    print(f"\nFinal database state:")
    print(f"- Total guests: {total_guests}")
    print(f"- Guests with email: {guests_with_email}")
    print(f"- Guests without email: {guests_without_email}")
    
    conn.close()
