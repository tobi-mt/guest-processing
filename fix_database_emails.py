#!/usr/bin/env python3
"""
Clean Up Database and Fix Emails
=================================

This script will:
1. Remove fake test users (john.smith@example.com, etc.)
2. Restore real emails from the CSV import for the 10 featured guests
3. Keep the extracted emails from original_data for other guests
"""

import sys
import sqlite3
import json
sys.path.append('src')

def main():
    print("🧹 CLEANING UP DATABASE AND FIXING EMAILS")
    print("=" * 50)
    
    # Step 1: Remove fake test users
    fake_users = ['John Smith', 'Jane Doe', 'Bob Johnson']
    
    with sqlite3.connect('guest_database.db') as conn:
        print("🗑️  Removing fake test users...")
        for fake_name in fake_users:
            cursor = conn.execute("SELECT id FROM guests WHERE full_name = ?", (fake_name,))
            result = cursor.fetchone()
            if result:
                conn.execute("DELETE FROM guests WHERE full_name = ?", (fake_name,))
                print(f"   ❌ Removed: {fake_name}")
            else:
                print(f"   ℹ️  {fake_name} not found (already removed)")
    
    # Step 2: Restore CSV guest emails
    csv_email_mapping = {
        'Kute Blackson': 'media@kuteblackson.com',
        'marni battista': 'marni@datingwithdignity.com', 
        'Betsy Pepine': 'betsy@betsypepine.com',
        'Eli Libby & Kyle Nelson': 'eli@peakfulfillmentcoaching.com',
        'Roy Biancalana': 'jenny.ortega@podcastguestingpro.com',
        'Freddy Jackson': 'Freddy@lovenoego.org',
        'Alex Dumas': 'alex@bipoccc.org',
        'Linda Brand': 'lindabrandcoaching@gmail.com',
        'Tamika Quinn': 'teamdreamgivers@yahoo.com',
        'Steve Huff': 'steve@winningchaos.com'
    }
    
    print("\n📧 Restoring CSV guest emails...")
    with sqlite3.connect('guest_database.db') as conn:
        for name, email in csv_email_mapping.items():
            conn.execute("""
                UPDATE guests 
                SET email = ?, updated_at = CURRENT_TIMESTAMP 
                WHERE full_name = ?
            """, (email, name))
            print(f"   ✅ {name} → {email}")
    
    # Step 3: Re-extract emails from original_data for other guests
    print("\n🔄 Re-extracting emails from original_data...")
    
    with sqlite3.connect('guest_database.db') as conn:
        cursor = conn.execute("""
            SELECT id, full_name, email, original_data 
            FROM guests 
            WHERE original_data IS NOT NULL 
            AND email = 'anonymous'
        """)
        
        updated_count = 0
        for row in cursor.fetchall():
            guest_id, full_name, current_email, original_data = row
            
            try:
                data = json.loads(original_data)
                
                # Find best email from original data
                email = None
                email_columns = ['Email2', "Guest's Email", 'Contact Email', 'Email']
                
                for email_col in email_columns:
                    if email_col in data and data[email_col]:
                        email_val = str(data[email_col]).strip()
                        if '@' in email_val and email_val.lower() != 'anonymous':
                            email = email_val
                            break
                
                if email and email != current_email:
                    conn.execute("""
                        UPDATE guests 
                        SET email = ?, updated_at = CURRENT_TIMESTAMP 
                        WHERE id = ?
                    """, (email, guest_id))
                    print(f"   ✅ {full_name} → {email}")
                    updated_count += 1
                else:
                    # Set placeholder for guests without real emails
                    conn.execute("""
                        UPDATE guests 
                        SET email = 'anonymous@example.com', updated_at = CURRENT_TIMESTAMP 
                        WHERE id = ?
                    """, (guest_id,))
                    
            except (json.JSONDecodeError, KeyError):
                # Set placeholder for guests with invalid original_data
                conn.execute("""
                    UPDATE guests 
                    SET email = 'anonymous@example.com', updated_at = CURRENT_TIMESTAMP 
                    WHERE id = ?
                """, (guest_id,))
        
        print(f"   📊 Updated {updated_count} additional guests with real emails")
    
    # Step 4: Final verification
    print("\n📊 FINAL STATUS CHECK:")
    
    with sqlite3.connect('guest_database.db') as conn:
        cursor = conn.execute("SELECT COUNT(*) FROM guests")
        total_guests = cursor.fetchone()[0]
        
        cursor = conn.execute("SELECT COUNT(*) FROM guests WHERE email LIKE '%@%' AND email != 'anonymous@example.com'")
        real_emails = cursor.fetchone()[0]
        
        cursor = conn.execute("SELECT COUNT(*) FROM guests WHERE email = 'anonymous@example.com'")
        placeholder_emails = cursor.fetchone()[0]
        
        cursor = conn.execute("SELECT COUNT(*) FROM guests WHERE email = 'anonymous' OR email IS NULL OR email = ''")
        anonymous_emails = cursor.fetchone()[0]
        
        print(f"   Total guests: {total_guests}")
        print(f"   Real emails: {real_emails}")
        print(f"   Placeholder emails: {placeholder_emails}")
        print(f"   Anonymous/missing: {anonymous_emails}")
        
        success_rate = (real_emails / total_guests) * 100 if total_guests else 0
        print(f"   Email success rate: {success_rate:.1f}%")
        
        # Show sample of real emails
        print(f"\n🌟 Sample of guests with real emails:")
        cursor = conn.execute("""
            SELECT full_name, email 
            FROM guests 
            WHERE email LIKE '%@%' AND email != 'anonymous@example.com'
            LIMIT 10
        """)
        
        for i, (name, email) in enumerate(cursor.fetchall(), 1):
            print(f"   {i:2d}. {name} - {email}")
    
    print(f"\n✅ CLEANUP COMPLETE!")
    print(f"🚀 Dashboard ready at: http://localhost:8052")

if __name__ == "__main__":
    main()
