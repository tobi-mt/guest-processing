#!/usr/bin/env python3
"""Fix anonymous email addresses by matching with Excel data."""

import sys
import pandas as pd
sys.path.insert(0, 'src')

from guest_database_manager.database import GuestDatabase

def fix_anonymous_emails():
    """Fix anonymous email addresses using Excel data."""
    print("Fixing anonymous email addresses...")
    
    # Initialize database
    db = GuestDatabase('guest_database.db')
    
    # Read Excel file to get correct email mappings
    excel_file = "Soulful Guest Questionnaire30072025.xlsx"
    
    try:
        df = pd.read_excel(excel_file)
        print(f"Read {len(df)} entries from Excel file")
        
        # Create name to email mapping from Excel  
        name_to_email = {}
        for _, row in df.iterrows():
            # Use 'Full name' column for name
            full_name = row.get('Full name', '').strip() if pd.notna(row.get('Full name')) else ''
            # Use 'Email2' column for email (not 'Email' which contains 'anonymous')
            email = row.get('Email2', '').strip() if pd.notna(row.get('Email2')) else ''
            
            if full_name and email and email != 'anonymous':
                name_to_email[full_name] = email
        
        print(f"Created email mapping for {len(name_to_email)} guests")
        
        # Get all guests with anonymous emails
        all_guests = db.get_all_guests()
        anonymous_guests = [g for g in all_guests if g['email'] == 'anonymous']
        
        print(f"\\nFound {len(anonymous_guests)} guests with anonymous emails")
        
        fixed_count = 0
        not_found_count = 0
        
        for guest in anonymous_guests:
            guest_name = guest['name']
            
            # Try to find the email for this guest (try exact match first, then case-insensitive)
            correct_email = None
            
            # Try exact match
            if guest_name in name_to_email:
                correct_email = name_to_email[guest_name]
            else:
                # Try case-insensitive match
                for excel_name, excel_email in name_to_email.items():
                    if guest_name.lower().strip() == excel_name.lower().strip():
                        correct_email = excel_email
                        break
            
            if correct_email:
                # Check if we already have a guest with this name and correct email
                existing_with_email = None
                for g in all_guests:
                    if (g['name'].lower().strip() == guest_name.lower().strip() and 
                        g['email'] == correct_email and g['id'] != guest['id']):
                        existing_with_email = g
                        break
                
                if existing_with_email:
                    # We have a duplicate! Delete the anonymous version
                    print(f"🗑️  Removing duplicate: {guest_name} (anonymous)")
                    
                    # Delete the anonymous guest
                    with db._get_connection() as conn:
                        conn.execute("DELETE FROM guests WHERE id = ?", (guest['id'],))
                        conn.commit()
                    fixed_count += 1
                else:
                    # Update the email address
                    print(f"📧 Updating email: {guest_name} -> {correct_email}")
                    
                    with db._get_connection() as conn:
                        conn.execute(
                            "UPDATE guests SET email = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                            (correct_email, guest['id'])
                        )
                        conn.commit()
                    fixed_count += 1
            else:
                print(f"❌ No email found for: {guest_name}")
                not_found_count += 1
        
        print(f"\\n=== Fix Summary ===")
        print(f"Fixed/removed: {fixed_count}")
        print(f"Not found in Excel: {not_found_count}")
        
    except Exception as e:
        print(f"Error: {e}")
        return
    
    # Show final stats
    print("\\n=== Final Database Stats ===")
    final_guests = db.get_all_guests()
    anonymous_final = [g for g in final_guests if g['email'] == 'anonymous']
    real_email_final = [g for g in final_guests if g['email'] != 'anonymous']
    
    print(f"Total guests: {len(final_guests)}")
    print(f"Guests with real emails: {len(real_email_final)}")
    print(f"Guests with anonymous emails: {len(anonymous_final)}")
    
    # Show updated statistics
    stats = db.get_stats()
    email_stats = db.get_email_stats()
    
    print("\\nGuest stats:")
    for key, value in stats.items():
        print(f"  {key}: {value}")
    
    print("\\nEmail stats:")
    for key, value in email_stats.items():
        print(f"  {key}: {value}")

# Add method to database class for connection access
def add_connection_method():
    """Add a method to access database connection."""
    import sqlite3
    from contextlib import contextmanager
    
    @contextmanager
    def get_connection(self):
        conn = sqlite3.connect(self.db_path)
        try:
            yield conn
        finally:
            conn.close()
    
    # Add method to GuestDatabase class
    GuestDatabase._get_connection = get_connection

if __name__ == "__main__":
    add_connection_method()
    fix_anonymous_emails()
