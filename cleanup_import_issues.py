#!/usr/bin/env python3
"""
Cleanup script to fix data quality issues after CSV import
"""

import sqlite3

def fix_malformed_names():
    """Fix names that are actually long bio text instead of names"""
    
    conn = sqlite3.connect('guest_database.db')
    cursor = conn.cursor()
    
    # Find entries where the name is abnormally long (likely bio text)
    cursor.execute('SELECT id, name, full_name, email FROM guests WHERE LENGTH(full_name) > 100')
    malformed = cursor.fetchall()
    
    deleted_count = 0
    
    for guest_id, _, full_name, email in malformed:
        print(f"\nFound malformed name (ID {guest_id}):")
        print(f"Current name: {full_name[:100]}...")
        
        # Check if there's another entry with the same email and proper name
        if email:
            cursor.execute(
                'SELECT id, full_name FROM guests WHERE email = ? AND LENGTH(full_name) < 100 AND id != ?',
                (email, guest_id)
            )
            proper_entry = cursor.fetchone()
            
            if proper_entry:
                print(f"Found proper entry for same email: {proper_entry[1]}")
                print(f"Deleting malformed entry ID {guest_id}")
                cursor.execute('DELETE FROM guests WHERE id = ?', (guest_id,))
                deleted_count += 1
                print(f"✓ Deleted malformed entry ID {guest_id}")
            else:
                print(f"No proper entry found for email {email}, keeping malformed entry")
        else:
            print(f"No email for malformed entry, deleting ID {guest_id}")
            cursor.execute('DELETE FROM guests WHERE id = ?', (guest_id,))
            deleted_count += 1
            print(f"✓ Deleted malformed entry ID {guest_id}")
    
    conn.commit()
    conn.close()
    
    print(f"\nDeleted {deleted_count} malformed entries")
    return deleted_count

def fix_duplicate_dr_len_lopez():
    """Fix duplicate Dr. Len Lopez entries"""
    
    conn = sqlite3.connect('guest_database.db')
    cursor = conn.cursor()
    
    # Find Dr. Len Lopez entries
    cursor.execute('SELECT id, name, full_name, email FROM guests WHERE email = ?', ('doc@drlenlopez.com',))
    len_lopez_entries = cursor.fetchall()
    
    if len(len_lopez_entries) > 1:
        print(f"\nFound {len(len_lopez_entries)} Dr. Len Lopez entries:")
        
        # Keep the one with the shortest, cleanest name
        best_entry = None
        entries_to_delete = []
        
        for entry in len_lopez_entries:
            guest_id, _, full_name, _ = entry
            print(f"ID {guest_id}: {full_name[:50]}...")
            
            # Check if this is the best entry (shortest name)
            if best_entry is None:
                best_entry = entry
            elif len(full_name) < len(best_entry[2]):
                # This entry has a shorter name, so it's better
                entries_to_delete.append(best_entry[0])
                best_entry = entry
            else:
                # Current best entry is still better
                entries_to_delete.append(guest_id)
        
        # Delete duplicate entries
        for guest_id in entries_to_delete:
            cursor.execute('DELETE FROM guests WHERE id = ?', (guest_id,))
            print(f"✓ Deleted duplicate entry ID {guest_id}")
        
        # Update the remaining entry to have a clean name
        if best_entry:
            cursor.execute(
                'UPDATE guests SET name = ?, full_name = ? WHERE id = ?',
                ('Dr. Len Lopez', 'Dr. Len Lopez', best_entry[0])
            )
            print("✓ Updated remaining entry to 'Dr. Len Lopez'")
        
        conn.commit()
        print(f"Removed {len(entries_to_delete)} duplicate Dr. Len Lopez entries")
    
    conn.close()

def verify_cleanup():
    """Verify the cleanup worked correctly"""
    
    conn = sqlite3.connect('guest_database.db')
    cursor = conn.cursor()
    
    # Check total count
    cursor.execute('SELECT COUNT(*) FROM guests')
    total = cursor.fetchone()[0]
    
    # Check for remaining long names
    cursor.execute('SELECT COUNT(*) FROM guests WHERE LENGTH(full_name) > 100')
    long_names = cursor.fetchone()[0]
    
    # Check for fake emails
    cursor.execute('SELECT COUNT(*) FROM guests WHERE email LIKE "%anonymous%"')
    fake_emails = cursor.fetchone()[0]
    
    # Check email distribution
    cursor.execute('SELECT COUNT(*) FROM guests WHERE email IS NOT NULL')
    with_email = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM guests WHERE email IS NULL')
    without_email = cursor.fetchone()[0]
    
    print("\n=== CLEANUP VERIFICATION ===")
    print(f"Total guests: {total}")
    print(f"Long names (>100 chars): {long_names}")
    print(f"Fake emails: {fake_emails}")
    print(f"Guests with email: {with_email}")
    print(f"Guests without email: {without_email}")
    
    if long_names == 0 and fake_emails == 0:
        print("✅ Database is clean!")
    else:
        print("⚠️  Still has data quality issues")
    
    conn.close()

if __name__ == "__main__":
    print("Starting database cleanup...")
    
    # Fix malformed names
    fix_malformed_names()
    
    # Fix duplicates
    fix_duplicate_dr_len_lopez()
    
    # Verify cleanup
    verify_cleanup()
    
    print("\nCleanup completed!")
