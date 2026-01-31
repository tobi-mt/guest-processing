#!/usr/bin/env python3
"""
Fix emails by extracting from original_data stored in database
"""

import sys
import os
import sqlite3
import json

# Add the src directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

def fix_emails_from_original_data():
    """Extract and update emails from the original_data field."""
    print("🔧 Fixing Emails from Original Data")
    print("=" * 40)
    
    with sqlite3.connect('guest_database.db') as conn:
        conn.row_factory = sqlite3.Row
        
        # Get all guests with original_data
        cursor = conn.execute('SELECT id, full_name, email, original_data FROM guests WHERE original_data IS NOT NULL')
        guests = cursor.fetchall()
        
        print(f"📊 Found {len(guests)} guests with original data")
        
        updated_count = 0
        real_emails_found = 0
        
        for guest in guests:
            try:
                # Parse the original_data JSON
                original_data = eval(guest['original_data'])  # It's stored as a string repr of dict
                
                # Extract email from original data
                original_email = original_data.get('email', '')
                
                if original_email and '@' in original_email and original_email != 'anonymous':
                    # Update the email in the database
                    conn.execute(
                        'UPDATE guests SET email = ? WHERE id = ?',
                        (original_email, guest['id'])
                    )
                    updated_count += 1
                    real_emails_found += 1
                    
                    print(f"✅ Updated {guest['full_name']}: {guest['email']} → {original_email}")
                    
            except Exception as e:
                print(f"❌ Error processing {guest['full_name']}: {e}")
                continue
        
        # Commit the changes
        conn.commit()
        
        print(f"\\n📈 Summary:")
        print(f"   Updated: {updated_count} guests")
        print(f"   Real emails found: {real_emails_found}")
        
        # Verify the results
        cursor = conn.execute('SELECT COUNT(*) as count FROM guests WHERE email IS NOT NULL AND email != \"anonymous\" AND email != \"\"')
        result = cursor.fetchone()
        total_real_emails = result['count']
        
        print(f"   Total guests with real emails now: {total_real_emails}")

if __name__ == "__main__":
    fix_emails_from_original_data()
