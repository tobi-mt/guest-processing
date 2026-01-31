#!/usr/bin/env python3
"""
Smart Email Extraction from Original Data
=========================================

This script extracts real emails from the original_data field while:
1. Preserving CSV guest emails (don't overwrite them)
2. Using Email2 prioritization logic
3. Properly handling JSON data
"""

import sys
import sqlite3
import json
sys.path.append('src')

def main():
    print("🔧 SMART EMAIL EXTRACTION FROM ORIGINAL DATA")
    print("=" * 50)
    
    # CSV guests that should NOT be overwritten
    csv_guests = [
        'Kute Blackson', 'marni battista', 'Betsy Pepine', 
        'Eli Libby & Kyle Nelson', 'Roy Biancalana', 'Freddy Jackson',
        'Alex Dumas', 'Linda Brand', 'Tamika Quinn', 'Steve Huff'
    ]
    
    with sqlite3.connect('guest_database.db') as conn:
        # Get guests with original_data but exclude CSV guests and those with real emails
        cursor = conn.execute("""
            SELECT id, full_name, email, original_data 
            FROM guests 
            WHERE original_data IS NOT NULL 
            AND email = 'anonymous@example.com'
            AND full_name NOT IN ({})
        """.format(','.join(['?' for _ in csv_guests])), csv_guests)
        
        guests = cursor.fetchall()
        print(f"📊 Found {len(guests)} guests to process (excluding CSV guests)")
        
        updated_count = 0
        
        for guest_id, full_name, current_email, original_data in guests:
            try:
                # Try to parse as JSON first
                try:
                    data = json.loads(original_data)
                except json.JSONDecodeError:
                    # If JSON fails, try eval (for older format)
                    data = eval(original_data)
                
                # Email prioritization: email > Email2 > Guest's Email > Contact Email > Email
                email = None
                email_columns = ['email', 'Email2', "Guest's Email", 'Contact Email', 'Email']
                
                for email_col in email_columns:
                    if email_col in data and data[email_col]:
                        email_val = str(data[email_col]).strip()
                        if '@' in email_val and email_val.lower() != 'anonymous':
                            email = email_val
                            print(f"   📧 Found {email_col}: {email} for {full_name}")
                            break
                
                if email and email != current_email:
                    conn.execute("""
                        UPDATE guests 
                        SET email = ?, updated_at = CURRENT_TIMESTAMP 
                        WHERE id = ?
                    """, (email, guest_id))
                    print(f"✅ Updated {full_name}: {current_email} → {email}")
                    updated_count += 1
                    
            except Exception as e:
                print(f"❌ Error processing {full_name}: {e}")
                continue
        
        print(f"\n📈 Summary:")
        print(f"   📧 Emails extracted: {updated_count}")
        
        # Final status check
        cursor = conn.execute("SELECT COUNT(*) FROM guests")
        total_guests = cursor.fetchone()[0]
        
        cursor = conn.execute("SELECT COUNT(*) FROM guests WHERE email LIKE '%@%' AND email != 'anonymous@example.com'")
        real_emails = cursor.fetchone()[0]
        
        cursor = conn.execute("SELECT COUNT(*) FROM guests WHERE email = 'anonymous@example.com'")
        placeholder_emails = cursor.fetchone()[0]
        
        success_rate = (real_emails / total_guests) * 100 if total_guests else 0
        
        print(f"\n📊 Final Database Status:")
        print(f"   Total guests: {total_guests}")
        print(f"   Real emails: {real_emails}")
        print(f"   Placeholder emails: {placeholder_emails}")
        print(f"   Email success rate: {success_rate:.1f}%")
        
        if real_emails > 100:
            print(f"\n🎉 SUCCESS: High email extraction rate achieved!")
        elif real_emails > 50:
            print(f"\n✅ GOOD: Reasonable email extraction rate")
        else:
            print(f"\n⚠️  LOW: Email extraction rate needs improvement")

if __name__ == "__main__":
    main()
