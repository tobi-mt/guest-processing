#!/usr/bin/env python3
"""Mark processed guests from Excel sheet as processed in database."""

import sys
import pandas as pd
sys.path.insert(0, 'src')

from guest_database_manager.database import GuestDatabase

def mark_excel_guests_as_processed():
    """Mark all guests from Excel sheet as processed."""
    print("Marking Excel sheet guests as processed...")
    
    # Initialize database
    db = GuestDatabase('guest_database.db')
    
    # Get initial stats
    print("\n=== Initial Database Stats ===")
    initial_stats = db.get_stats()
    for key, value in initial_stats.items():
        print(f"{key}: {value}")
    
    # Read Excel file
    excel_file = "Soulful Guest Questionnaire30072025.xlsx"
    print(f"\n=== Reading {excel_file} ===")
    
    try:
        df = pd.read_excel(excel_file)
        print(f"Read {len(df)} rows from Excel file")
        
        # Process each guest from Excel
        processed_count = 0
        not_found_count = 0
        already_processed_count = 0
        
        print("\n=== Processing guests from Excel ===")
        
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
                
                if existing_guest and not existing_guest['is_processed']:
                    # Mark as processed (you can change this to accept_guest_with_email, reject_guest_with_email, or skip_guest)
                    db.mark_guest_processed(existing_guest['id'])
                    processed_count += 1
                    print(f"✓ Processed: {full_name}")
                elif existing_guest and existing_guest['is_processed']:
                    already_processed_count += 1
                    print(f"- Already processed: {full_name}")
            else:
                not_found_count += 1
                print(f"✗ Not found in database: {full_name} ({email})")
        
        print(f"\n=== Processing Summary ===")
        print(f"Newly processed: {processed_count}")
        print(f"Already processed: {already_processed_count}")
        print(f"Not found in database: {not_found_count}")
        
    except Exception as e:
        print(f"Error reading Excel file: {e}")
        return
    
    # Get final stats
    print("\n=== Final Database Stats ===")
    final_stats = db.get_stats()
    final_email_stats = db.get_email_stats()
    
    for key, value in final_stats.items():
        print(f"{key}: {value}")
    
    # Show changes
    print("\n=== Changes ===")
    for key in final_stats:
        change = final_stats[key] - initial_stats[key]
        if change != 0:
            print(f"{key}: +{change}")
    
    print("\n=== Email Stats ===")
    for key, value in final_email_stats.items():
        print(f"{key}: {value}")

def mark_excel_guests_with_status():
    """Mark guests with specific status (accept/reject/skip)."""
    print("\n" + "="*60)
    print("ALTERNATIVE: Mark guests with specific status")
    print("="*60)
    
    # You can also mark guests with specific email status
    # Uncomment the desired action below:
    
    excel_file = "Soulful Guest Questionnaire30072025.xlsx"
    db = GuestDatabase('guest_database.db')
    
    try:
        df = pd.read_excel(excel_file)
        
        accepted_count = 0
        
        for index, row in df.iterrows():
            full_name = row.get('Full name', '').strip() if pd.notna(row.get('Full name')) else ''
            email = row.get('Email2', '').strip() if pd.notna(row.get('Email2')) else ''
            
            if not full_name or not email:
                continue
            
            if db.guest_exists(full_name, email):
                existing_guest = db.get_guest_by_name_email(full_name, email)
                
                if existing_guest and not existing_guest['is_processed']:
                    # Choose one of these actions:
                    
                    # Option 1: Accept all guests
                    db.accept_guest_with_email(existing_guest['id'], "Welcome to our podcast!")
                    accepted_count += 1
                    
                    # Option 2: Reject all guests
                    # db.reject_guest_with_email(existing_guest['id'], "Thank you for your interest")
                    
                    # Option 3: Skip all guests
                    # db.skip_guest(existing_guest['id'], "Processed in bulk")
        
        print(f"Accepted {accepted_count} guests from Excel sheet")
        
        # Show final stats
        final_stats = db.get_stats()
        final_email_stats = db.get_email_stats()
        
        print("\n=== Final Stats After Status Update ===")
        for key, value in final_stats.items():
            print(f"{key}: {value}")
        
        print("\n=== Final Email Stats ===")
        for key, value in final_email_stats.items():
            print(f"{key}: {value}")
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    # Option 1: Just mark as processed (no email status)
    mark_excel_guests_as_processed()
    
    # Option 2: Mark with specific status (accept/reject/skip)
    # Uncomment the line below if you want to mark them with a specific email status
    # mark_excel_guests_with_status()
