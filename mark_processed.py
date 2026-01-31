#!/usr/bin/env python3
"""Mark guests from Excel file as processed."""

import sys
import pandas as pd
sys.path.insert(0, 'src')

from guest_database_manager.database import GuestDatabase

def mark_excel_guests_as_processed():
    """Mark all guests from the Excel file as processed."""
    print("Marking Excel file guests as processed...")
    
    # Initialize database
    db = GuestDatabase('guest_database.db')
    
    # Get initial stats
    print("\n=== Initial Stats ===")
    initial_stats = db.get_stats()
    initial_email_stats = db.get_email_stats()
    
    for key, value in initial_stats.items():
        print(f"{key}: {value}")
    
    # Read Excel file to get the guest list
    excel_file = "Soulful Guest Questionnaire30072025.xlsx"
    print(f"\n=== Reading {excel_file} ===")
    
    try:
        df = pd.read_excel(excel_file)
        print(f"Found {len(df)} guests in Excel file")
        
        # Use Email2 as the actual email (as we discovered earlier)
        if 'Email2' in df.columns:
            df['Email'] = df['Email2']
        
        processed_count = 0
        
        print("\n=== Processing Status Options ===")
        print("1. Mark all as ACCEPTED (will send acceptance emails)")
        print("2. Mark all as REJECTED (will send rejection emails)")  
        print("3. Mark all as SKIPPED (will skip without sending emails)")
        print("4. Mark all as PROCESSED (general processed status)")
        print("5. Show me the guests first so I can decide")
        
        choice = input("\\nWhat should I do with these guests? Enter number (1-5): ").strip()
        
        if choice == "5":
            print("\\n=== Guests from Excel File ===")
            for index, row in df.iterrows():
                name = row.get('Name', row.get('Full name', 'Unknown'))
                email = row.get('Email', 'No email')
                print(f"{index + 1:3d}. {name} ({email})")
            return
        
        # Process based on choice
        for index, row in df.iterrows():
            try:
                name = row.get('Name', row.get('Full name', ''))
                email = row.get('Email', '')
                
                if not name or not email:
                    print(f"Skipping row {index + 1}: missing name or email")
                    continue
                
                # Find the guest in database
                guest = db.get_guest_by_name_email(name, email)
                if not guest:
                    print(f"Guest not found in database: {name} ({email})")
                    continue
                
                guest_id = guest['id']
                
                if choice == "1":
                    db.accept_guest_with_email(guest_id, "Welcome to our podcast!")
                    print(f"✅ Accepted: {name}")
                elif choice == "2":
                    db.reject_guest_with_email(guest_id, "Thank you for your interest")
                    print(f"❌ Rejected: {name}")
                elif choice == "3":
                    db.skip_guest(guest_id, "Processed in bulk import")
                    print(f"⏭️ Skipped: {name}")
                elif choice == "4":
                    db.mark_guest_processed(guest_id)
                    print(f"✔️ Processed: {name}")
                else:
                    print("Invalid choice, stopping.")
                    return
                
                processed_count += 1
                
            except Exception as e:
                print(f"Error processing {name}: {e}")
                continue
        
        print(f"\\n=== Successfully processed {processed_count} guests ===")
        
    except Exception as e:
        print(f"Error reading Excel file: {e}")
        return
    
    # Get final stats
    print("\\n=== Final Stats ===")
    final_stats = db.get_stats()
    final_email_stats = db.get_email_stats()
    
    for key, value in final_stats.items():
        print(f"{key}: {value}")
    
    # Show changes
    print("\\n=== Changes ===")
    for key in final_stats:
        change = final_stats[key] - initial_stats[key]
        if change != 0:
            print(f"{key}: +{change}")
    
    print("\\n=== Email Stats ===")
    for key, value in final_email_stats.items():
        print(f"{key}: {value}")

if __name__ == "__main__":
    mark_excel_guests_as_processed()
