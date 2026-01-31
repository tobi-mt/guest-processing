#!/usr/bin/env python3
"""
REMOVE ALL FAKE EMAILS - FINAL CLEANUP
======================================

This script will:
1. Remove ALL fake emails (@example.com, anonymous, etc.)
2. Set email to NULL for guests without real emails
3. Keep only legitimate email addresses
"""

import sqlite3

def main():
    print("🧹 REMOVING ALL FAKE EMAILS - FINAL CLEANUP")
    print("=" * 50)
    
    with sqlite3.connect('guest_database.db') as conn:
        # First, find all guests with fake emails
        cursor = conn.execute("""
            SELECT full_name, email 
            FROM guests 
            WHERE email LIKE '%@example.com'
            OR email = 'anonymous'
            OR email LIKE '%anonymous%'
        """)
        
        fake_emails = cursor.fetchall()
        print(f"❌ Found {len(fake_emails)} guests with fake emails")
        
        # Remove all fake emails - set to NULL
        conn.execute("""
            UPDATE guests 
            SET email = NULL, updated_at = CURRENT_TIMESTAMP
            WHERE email LIKE '%@example.com'
            OR email = 'anonymous'
            OR email LIKE '%anonymous%'
        """)
        
        print(f"✅ Removed all fake emails from {len(fake_emails)} guests")
        
        # Also remove the problematic "New Person" entry if it exists
        cursor = conn.execute("SELECT id FROM guests WHERE full_name = 'New Person'")
        new_person = cursor.fetchone()
        if new_person:
            conn.execute("DELETE FROM guests WHERE full_name = 'New Person'")
            print("🗑️  Removed 'New Person' test entry")
        
        # Final verification
        print(f"\n📊 FINAL DATABASE STATUS:")
        
        cursor = conn.execute("SELECT COUNT(*) FROM guests")
        total_guests = cursor.fetchone()[0]
        
        cursor = conn.execute("SELECT COUNT(*) FROM guests WHERE email IS NOT NULL AND email != ''")
        guests_with_emails = cursor.fetchone()[0]
        
        cursor = conn.execute("SELECT COUNT(*) FROM guests WHERE email IS NULL OR email = ''")
        guests_without_emails = cursor.fetchone()[0]
        
        # Verify no fake emails remain
        cursor = conn.execute("""
            SELECT COUNT(*) FROM guests 
            WHERE email LIKE '%@example.com'
            OR email = 'anonymous'
            OR email LIKE '%anonymous%'
        """)
        remaining_fake = cursor.fetchone()[0]
        
        print(f"   Total guests: {total_guests}")
        print(f"   Guests with real emails: {guests_with_emails}")
        print(f"   Guests without emails: {guests_without_emails}")
        print(f"   Remaining fake emails: {remaining_fake}")
        
        if remaining_fake == 0:
            print(f"\n🎉 SUCCESS: All fake emails removed!")
            print(f"✅ Only real email addresses remain in the database")
            print(f"✅ Guests without emails have NULL values (no fake placeholders)")
        else:
            print(f"\n⚠️  WARNING: {remaining_fake} fake emails still found!")
        
        # Show sample of real emails
        print(f"\n🌟 Sample of guests with real emails:")
        cursor = conn.execute("""
            SELECT full_name, email 
            FROM guests 
            WHERE email IS NOT NULL AND email != ''
            ORDER BY full_name
            LIMIT 10
        """)
        
        for i, (name, email) in enumerate(cursor.fetchall(), 1):
            print(f"   {i:2d}. {name} - {email}")
        
        print(f"\n✅ CLEANUP COMPLETE!")
        print(f"🚀 Dashboard ready with clean data at: http://localhost:8052")

if __name__ == "__main__":
    main()
