#!/usr/bin/env python3
"""
Quick script to remove duplicates that were created again.
"""

import sqlite3

def remove_duplicates_again():
    """Remove duplicate guests, keeping the version with real email."""
    conn = sqlite3.connect('guest_database.db')
    cursor = conn.cursor()
    
    # Find all duplicate groups (same name, case-insensitive)
    cursor.execute("""
        SELECT LOWER(TRIM(name)) as name_lower, 
               GROUP_CONCAT(id) as ids,
               COUNT(*) as count
        FROM guests 
        GROUP BY LOWER(TRIM(name)) 
        HAVING COUNT(*) > 1
        ORDER BY count DESC
    """)
    
    duplicate_groups = cursor.fetchall()
    print(f"Found {len(duplicate_groups)} duplicate groups")
    
    total_removed = 0
    
    for name_lower, ids_str, count in duplicate_groups:
        ids = [int(id) for id in ids_str.split(',')]
        
        print(f"\nProcessing {count} duplicates for: {name_lower}")
        
        # Get full records for this group
        cursor.execute(f"""
            SELECT id, name, email, is_processed, email_status 
            FROM guests 
            WHERE id IN ({','.join('?' * len(ids))})
            ORDER BY 
                CASE WHEN email != 'anonymous' AND email IS NOT NULL AND email != '' THEN 0 ELSE 1 END,
                CASE WHEN is_processed = 1 THEN 0 ELSE 1 END,
                CASE WHEN email_status = 'accepted' THEN 0 ELSE 1 END,
                id
        """, ids)
        
        records = cursor.fetchall()
        
        # Keep the first record (best one based on sorting)
        keep_record = records[0]
        remove_records = records[1:]
        
        print(f"  Keeping: ID {keep_record[0]} - {keep_record[1]} - {keep_record[2]}")
        
        # Remove the duplicate records
        for record in remove_records:
            print(f"  Removing: ID {record[0]} - {record[1]} - {record[2]}")
            cursor.execute("DELETE FROM guests WHERE id = ?", (record[0],))
            total_removed += 1
    
    conn.commit()
    
    # Final count
    cursor.execute("SELECT COUNT(*) FROM guests")
    final_count = cursor.fetchone()[0]
    
    print(f"\nDeduplication complete!")
    print(f"Removed {total_removed} duplicate records")
    print(f"Final guest count: {final_count}")
    
    conn.close()

if __name__ == "__main__":
    remove_duplicates_again()
