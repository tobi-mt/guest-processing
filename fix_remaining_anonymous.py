#!/usr/bin/env python3
"""
Fix remaining anonymous email addresses by matching with Excel data.
"""

import pandas as pd
import sys
import os

# Add src to path
sys.path.append('src')
from guest_database_manager.database import GuestDatabase

def fix_anonymous_emails():
    """Fix anonymous email addresses using Excel data."""
    
    # Load Excel data
    try:
        df = pd.read_excel('Soulful Guest Questionnaire30072025.xlsx')
        print(f'Excel file loaded with {len(df)} rows')
        print('Available columns:', list(df.columns))
        
        # Check for anonymous guests in database
        db = GuestDatabase()
        guests = db.get_all_guests()
        anonymous_guests = [g for g in guests if g.get('email') == 'anonymous']
        
        print(f'\nFound {len(anonymous_guests)} guests with "anonymous" email')
        
        # Use correct column names
        name_col = 'Full name'  # Note: lowercase 'n'
        email_col = 'Email2'
        
        if name_col not in df.columns:
            print(f"Error: Column '{name_col}' not found in Excel")
            return
            
        if email_col not in df.columns:
            print(f"Error: Column '{email_col}' not found in Excel")
            return
        
        # Find recoverable emails
        recoverable = []
        truly_anonymous = []
        
        for guest in anonymous_guests:
            guest_name = guest.get('name', '').strip()
            guest_id = guest.get('id')
            
            if not guest_name:
                truly_anonymous.append(guest)
                continue
            
            # Try exact match first
            exact_matches = df[df[name_col].str.strip().str.lower() == guest_name.lower()]
            
            if exact_matches.empty:
                # Try partial match
                partial_matches = df[df[name_col].str.contains(guest_name.split()[0], case=False, na=False)]
                if not partial_matches.empty:
                    # Look for best match
                    best_match = None
                    for idx, row in partial_matches.iterrows():
                        excel_name = str(row[name_col]).strip()
                        if guest_name.lower() in excel_name.lower() or excel_name.lower() in guest_name.lower():
                            best_match = row
                            break
                    
                    if best_match is not None:
                        exact_matches = pd.DataFrame([best_match])
            
            if not exact_matches.empty:
                email = exact_matches.iloc[0][email_col]
                if pd.notna(email) and str(email).strip() != 'anonymous' and '@' in str(email):
                    recoverable.append((guest_id, guest_name, str(email).strip()))
                else:
                    truly_anonymous.append(guest)
            else:
                truly_anonymous.append(guest)
        
        print(f'\nRecoverable emails: {len(recoverable)}')
        print(f'Truly anonymous: {len(truly_anonymous)}')
        
        if recoverable:
            print('\nRecoverable emails:')
            for guest_id, name, email in recoverable:
                print(f'  ID {guest_id}: {name} -> {email}')
        
        # Ask for confirmation
        if recoverable:
            response = input(f'\nUpdate {len(recoverable)} email addresses? (y/n): ')
            if response.lower() == 'y':
                updated_count = 0
                for guest_id, name, email in recoverable:
                    try:
                        db.cursor.execute(
                            "UPDATE guests SET email = ? WHERE id = ?",
                            (email, guest_id)
                        )
                        updated_count += 1
                    except Exception as e:
                        print(f'Error updating guest {guest_id}: {e}')
                
                db.conn.commit()
                print(f'\nSuccessfully updated {updated_count} email addresses')
                
                # Update email statistics
                print('Updating email statistics...')
                db.update_email_statistics()
                
                # Show final stats
                final_stats = db.get_email_statistics()
                print(f'\nFinal email statistics:')
                print(f'Total guests: {final_stats.get("total_guests", 0)}')
                print(f'Real emails: {final_stats.get("real_emails", 0)}')
                print(f'Anonymous emails: {final_stats.get("anonymous_emails", 0)}')
                
        if truly_anonymous:
            print(f'\nRemaining truly anonymous guests ({len(truly_anonymous)}):')
            for guest in truly_anonymous[:10]:
                print(f'  ID {guest.get("id")}: {guest.get("name", "N/A")}')
            if len(truly_anonymous) > 10:
                print(f'  ... and {len(truly_anonymous) - 10} more')
                
    except Exception as e:
        print(f'Error: {e}')
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    fix_anonymous_emails()
