#!/usr/bin/env python3
"""Mark all Excel guests as accepted with email status."""

import sys
import pandas as pd
sys.path.insert(0, 'src')

from guest_database_manager.database import GuestDatabase

def mark_excel_guests_as_accepted():
    """Mark all guests from Excel sheet as accepted."""
    print("Marking Excel sheet guests as ACCEPTED...")
    
    # Initialize database
    db = GuestDatabase('guest_database.db')
    
    # Get initial stats
    print("\n=== Initial Database Stats ===")
    initial_stats = db.get_stats()
    initial_email_stats = db.get_email_stats()
    
    print("Guest stats:")
    for key, value in initial_stats.items():
        print(f"  {key}: {value}")
    
    print("Email stats:")
    for key, value in initial_email_stats.items():
        print(f"  {key}: {value}")
    
    # Read Excel file
    excel_file = "Soulful Guest Questionnaire30072025.xlsx"
    print(f"\n=== Reading {excel_file} ===")
    
    try:
        df = pd.read_excel(excel_file)
        print(f"Read {len(df)} rows from Excel file")
        
        # Process each guest from Excel
        accepted_count = 0
        already_accepted_count = 0
        not_found_count = 0
        
        print("\n=== Marking guests as ACCEPTED ===")
        
        for index, row in df.iterrows():
            # Get name from "Full name" column and email from "Email2" column
            full_name = row.get('Full name', '').strip() if pd.notna(row.get('Full name')) else ''
            email = row.get('Email2', '').strip() if pd.notna(row.get('Email2')) else ''
            
            if not full_name or not email:
                print(f"Row {index + 1}: Skipping - missing name or email")
                continue
            
            # Check if guest exists in database
            if db.guest_exists(full_name, email):
                existing_guest = db.get_guest_by_name_email(full_name, email)
                
                if existing_guest:
                    current_status = existing_guest.get('email_status', 'None')
                    
                    if current_status != 'accepted':
                        # Mark as accepted with email
                        db.accept_guest_with_email(existing_guest['id'], "Welcome to our podcast! We're excited to have you as a guest.")
                        accepted_count += 1
                        print(f"✅ Accepted: {full_name}")
                    else:
                        already_accepted_count += 1
                        print(f"✓ Already accepted: {full_name}")
            else:
                not_found_count += 1
                print(f"✗ Not found in database: {full_name} ({email})")
        
        print(f"\n=== Processing Summary ===")
        print(f"Newly accepted: {accepted_count}")
        print(f"Already accepted: {already_accepted_count}")
        print(f"Not found in database: {not_found_count}")
        
    except Exception as e:
        print(f"Error reading Excel file: {e}")
        return
    
    # Get final stats
    print("\n=== Final Database Stats ===")
    final_stats = db.get_stats()
    final_email_stats = db.get_email_stats()
    
    print("Guest stats:")
    for key, value in final_stats.items():
        print(f"  {key}: {value}")
    
    print("Email stats:")
    for key, value in final_email_stats.items():
        print(f"  {key}: {value}")
    
    # Show changes
    print("\n=== Changes ===")
    print("Guest stats changes:")
    for key in final_stats:
        change = final_stats[key] - initial_stats[key]
        if change != 0:
            print(f"  {key}: +{change}")
    
    print("Email stats changes:")
    for key in final_email_stats:
        change = final_email_stats[key] - initial_email_stats[key]
        if change != 0:
            print(f"  {key}: +{change}")

if __name__ == "__main__":
    mark_excel_guests_as_accepted()
