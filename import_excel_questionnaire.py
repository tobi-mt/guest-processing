#!/usr/bin/env python3
"""
Excel Questionnaire Importer
This script imports the complete questionnaire data from Excel with proper column mapping.
"""

import pandas as pd
import sqlite3
import sys
import os
from datetime import datetime

# Add src to path
sys.path.append('src')

def import_excel_questionnaire(excel_file_path):
    """Import questionnaire data from Excel file."""
    
    if not os.path.exists(excel_file_path):
        print(f"❌ Excel file not found: {excel_file_path}")
        return False
    
    try:
        # Load Excel file
        df = pd.read_excel(excel_file_path)
        print(f"📊 Loaded Excel file with {len(df)} rows and {len(df.columns)} columns")
        
        # Show available columns
        print(f"\n📋 Available columns in Excel:")
        for i, col in enumerate(df.columns, 1):
            print(f"  {i:2d}. {col}")
        
        # Define column mapping from Excel to database
        column_mapping = {
            # Basic Info
            'Full name': 'full_name',
            'Email2': 'email',  # Primary email column
            'Email1': 'email_fallback',  # Fallback if Email2 is empty
            'Email': 'email_fallback2',  # Second fallback
            "Guest's Email": 'email_fallback3',  # Third fallback
            'Website': 'website',
            'Do you have a website?': 'website_question',
            'Kindly list your active social media handles?': 'social_media_handles',
            
            # Professional Background
            'A brief overview of your personal and professional background': 'personal_professional_background',
            'What is your current profession, and what led you to this career path?': 'current_path',
            'What motivates or inspires you in your work and life?\n': 'motivation',
            'What life experiences or pivotal moments have shaped who you are today?\n': 'life_experience',
            
            # Values and Philosophy
            'What are your core values or guiding principles?\n': 'core_values',
            'Do you follow a specific faith, spiritual practice, or philosophical tradition?\n': 'life_practice',
            'Do you believe your beliefs and values align with the themes of soulful conversations?\n': 'life_practice_alignment',
            'Do you have a favourite quote or philosophy that guides your life?': 'favourite_quote',
            
            # Discussion Topics
            'What topics or themes are you most passionate about discussing?\n': 'passion_topic',
            'What message or takeaway would you like to leave with our listeners?\n': 'listeners_takeaway',
            'Have you been a guest on podcasts or spoken at events before?\n': 'podcast_experience',
            "Is there anything else you'd like us to know about you?\n": 'anything_else',
            
            # Engagement
            'Are you following us on podcast platforms and social media?': 'following_us',
            'Do you confirm that all questions and fields have been answered fully and accurately?': 'accuracy_confirmed',
        }
        
        # Check which columns exist in the Excel file
        available_mappings = {}
        missing_columns = []
        
        for excel_col, db_col in column_mapping.items():
            if excel_col in df.columns:
                available_mappings[excel_col] = db_col
            else:
                missing_columns.append(excel_col)
        
        print(f"\n✅ Found {len(available_mappings)} matching columns")
        print(f"❌ Missing {len(missing_columns)} expected columns")
        
        if missing_columns:
            print("\n⚠️  Missing columns:")
            for col in missing_columns[:5]:  # Show first 5
                print(f"   - {col}")
            if len(missing_columns) > 5:
                print(f"   ... and {len(missing_columns) - 5} more")
        
        # Process each row
        imported_count = 0
        updated_count = 0
        error_count = 0
        
        with sqlite3.connect('guest_database.db') as conn:
            for index, row in df.iterrows():
                try:
                    # Extract basic info
                    full_name = str(row.get('Full name', '')).strip()
                    if not full_name or full_name.lower() in ['nan', 'none', '']:
                        print(f"⚠️  Row {index + 1}: Skipping row with empty name")
                        continue
                    
                    # Determine email with fallback logic
                    email = None
                    for email_col in ['Email2', 'Email1', 'Email', "Guest's Email"]:
                        if email_col in df.columns:
                            email_val = row.get(email_col, '')
                            if pd.notna(email_val) and str(email_val).strip() and '@' in str(email_val):
                                email = str(email_val).strip()
                                break
                    
                    if not email:
                        email = 'anonymous@example.com'
                    
                    # Extract all other fields
                    data = {}
                    for excel_col, db_col in available_mappings.items():
                        value = row.get(excel_col, '')
                        if pd.notna(value) and str(value).strip() and str(value).lower() not in ['nan', 'none']:
                            data[db_col] = str(value).strip()
                        else:
                            data[db_col] = None
                    
                    # Check if guest already exists
                    cursor = conn.execute(
                        "SELECT id FROM guests WHERE full_name = ? OR (email = ? AND email != 'anonymous@example.com')",
                        (full_name, email)
                    )
                    existing = cursor.fetchone()
                    
                    if existing:
                        # Update existing guest
                        guest_id = existing[0]
                        update_fields = []
                        update_values = []
                        
                        for db_col, value in data.items():
                            if db_col not in ['email_fallback', 'email_fallback2', 'email_fallback3', 'website_question']:
                                update_fields.append(f"{db_col} = ?")
                                update_values.append(value)
                        
                        if update_fields:
                            update_values.append(guest_id)
                            conn.execute(
                                f"UPDATE guests SET {', '.join(update_fields)}, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                                update_values
                            )
                            updated_count += 1
                    else:
                        # Insert new guest
                        conn.execute("""
                            INSERT INTO guests (
                                full_name, email, website, social_media_handles,
                                personal_professional_background, current_path, motivation, life_experience,
                                core_values, life_practice, life_practice_alignment, favourite_quote,
                                passion_topic, listeners_takeaway, podcast_experience, anything_else,
                                following_us, accuracy_confirmed, is_processed
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                            full_name, email, data.get('website', None), data.get('social_media_handles', None),
                            data.get('personal_professional_background', None), data.get('current_path', None),
                            data.get('motivation', None), data.get('life_experience', None),
                            data.get('core_values', None), data.get('life_practice', None),
                            data.get('life_practice_alignment', None), data.get('favourite_quote', None),
                            data.get('passion_topic', None), data.get('listeners_takeaway', None),
                            data.get('podcast_experience', None), data.get('anything_else', None),
                            data.get('following_us', None), data.get('accuracy_confirmed', None),
                            False  # is_processed
                        ))
                        imported_count += 1
                
                except Exception as e:
                    error_count += 1
                    print(f"❌ Error processing row {index + 1} ({full_name}): {e}")
        
        print(f"\n📊 Import Summary:")
        print(f"   ✅ New guests imported: {imported_count}")
        print(f"   🔄 Existing guests updated: {updated_count}")
        print(f"   ❌ Errors: {error_count}")
        print(f"   📋 Total processed: {imported_count + updated_count}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error importing Excel file: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Main function."""
    print("=" * 70)
    print("📊 EXCEL QUESTIONNAIRE IMPORTER")
    print("=" * 70)
    
    # Check for Excel files in current directory
    excel_files = []
    for file in os.listdir('.'):
        if file.endswith('.xlsx') or file.endswith('.xls'):
            excel_files.append(file)
    
    if excel_files:
        print(f"\n📁 Found Excel files:")
        for i, file in enumerate(excel_files, 1):
            print(f"   {i}. {file}")
        
        if len(excel_files) == 1:
            excel_file = excel_files[0]
            response = input(f"\nImport from '{excel_file}'? (y/n): ")
            if response.lower() == 'y':
                import_excel_questionnaire(excel_file)
        else:
            choice = input(f"\nSelect file number (1-{len(excel_files)}): ")
            try:
                file_index = int(choice) - 1
                if 0 <= file_index < len(excel_files):
                    import_excel_questionnaire(excel_files[file_index])
                else:
                    print("Invalid selection")
            except ValueError:
                print("Invalid input")
    else:
        print("\n📁 No Excel files found in current directory")
        excel_file = input("\nEnter path to Excel file (or drag & drop): ").strip()
        if excel_file:
            # Remove quotes if present (from drag & drop)
            excel_file = excel_file.strip('\'\"')
            import_excel_questionnaire(excel_file)

if __name__ == '__main__':
    main()
