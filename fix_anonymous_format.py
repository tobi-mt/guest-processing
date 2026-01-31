#!/usr/bin/env python3
"""
Fix anonymous email format for consistency and update statistics.
"""

import sys
import sqlite3

# Add src to path
sys.path.append('src')
from guest_database_manager.database import GuestDatabase

def fix_anonymous_format():
    """Fix anonymous email format for consistency."""
    
    db = GuestDatabase()
    guests = db.get_all_guests()
    anonymous_guests = [g for g in guests if g.get('email') == 'anonymous']
    
    print(f'Found {len(anonymous_guests)} guests with "anonymous" email')
    
    if not anonymous_guests:
        print('No anonymous emails to fix')
        return
    
    print('\nOptions:')
    print('1. Convert "anonymous" to "anonymous@example.com" (consistent format)')
    print('2. Generate numbered anonymous emails (anonymous1@example.com, etc.)')
    print('3. Cancel')
    
    choice = input('\nChoose option (1/2/3): ').strip()
    
    if choice == '1':
        # Convert all to anonymous@example.com
        new_email = 'anonymous@example.com'
        print(f'\nConverting {len(anonymous_guests)} emails to "{new_email}"')
        
        updated_count = 0
        for guest in anonymous_guests:
            try:
                with sqlite3.connect(db.db_path) as conn:
                    conn.execute(
                        "UPDATE guests SET email = ? WHERE id = ?",
                        (new_email, guest.get('id'))
                    )
                updated_count += 1
            except sqlite3.Error as e:
                print(f'Error updating guest {guest.get("id")}: {e}')
        
        print(f'Successfully updated {updated_count} email addresses')
        
    elif choice == '2':
        # Generate numbered anonymous emails
        print(f'\nGenerating numbered anonymous emails for {len(anonymous_guests)} guests')
        
        updated_count = 0
        for i, guest in enumerate(anonymous_guests, 1):
            new_email = f'anonymous{i}@example.com'
            try:
                with sqlite3.connect(db.db_path) as conn:
                    conn.execute(
                        "UPDATE guests SET email = ? WHERE id = ?",
                        (new_email, guest.get('id'))
                    )
                updated_count += 1
                if i <= 5:  # Show first 5
                    print(f'  {guest.get("name")} -> {new_email}')
            except sqlite3.Error as e:
                print(f'Error updating guest {guest.get("id")}: {e}')
        
        if len(anonymous_guests) > 5:
            print(f'  ... and {len(anonymous_guests) - 5} more')
        
        print(f'Successfully updated {updated_count} email addresses')
        
    else:
        print('Cancelled')
        return
    
    # Show final stats
    final_stats = db.get_email_stats()
    print('\nFinal email statistics:')
    total_guests = db.get_stats()['total']
    print(f'Total guests: {total_guests}')
    print(f'With email: {final_stats.get("with_email", 0)}')
    print(f'Without email: {final_stats.get("without_email", 0)}')
    
    print('\nAnonymous email update complete!')

if __name__ == '__main__':
    fix_anonymous_format()
