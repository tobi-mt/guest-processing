#!/usr/bin/env python3
"""Import from Excel file with all processed guests."""

import sys
import os
sys.path.insert(0, 'src')

from guest_database_manager.database import GuestDatabase

def import_from_excel_file(excel_file_path=None):
    """Import from Excel file with comprehensive reporting."""
    print("Importing from Excel file with processed guests...")
    
    # Initialize database
    db = GuestDatabase('guest_database.db')
    
    # Get initial stats
    print("\n=== Initial Database Stats ===")
    initial_stats = db.get_stats()
    initial_email_stats = db.get_email_stats()
    
    for key, value in initial_stats.items():
        print(f"{key}: {value}")
    
    print("\nInitial email stats:")
    for key, value in initial_email_stats.items():
        print(f"{key}: {value}")
    
    # Find Excel files if not specified
    if excel_file_path is None:
        excel_files = []
        for file in os.listdir('.'):
            if file.endswith('.xlsx'):
                excel_files.append(file)
        
        if not excel_files:
            print("No Excel files found in current directory")
            return
        
        print(f"\nFound Excel files: {excel_files}")
        excel_file_path = excel_files[0]  # Use the first one found
    
    if not os.path.exists(excel_file_path):
        print(f"Excel file not found: {excel_file_path}")
        return
    
    print(f"\n=== Importing from {excel_file_path} ===")
    
    # Import from Excel
    import_stats = db.import_from_excel(excel_file_path)
    print("Import results:")
    for key, value in import_stats.items():
        print(f"  {key}: {value}")
    
    # Get final stats
    print("\n=== Final Database Stats ===")
    final_stats = db.get_stats()
    final_email_stats = db.get_email_stats()
    
    for key, value in final_stats.items():
        print(f"{key}: {value}")
    
    # Show the changes
    print("\n=== Changes in Guest Count ===")
    for key in final_stats:
        change = final_stats[key] - initial_stats[key]
        if change != 0:
            print(f"{key}: +{change}")
        else:
            print(f"{key}: no change")
    
    # Show email stats
    print("\n=== Final Email Stats ===")
    for key, value in final_email_stats.items():
        print(f"{key}: {value}")
    
    # Show some sample guests
    print("\n=== Sample Guests (last 10 added) ===")
    all_guests = db.get_all_guests()
    for guest in all_guests[-10:]:
        status = "Processed" if guest['is_processed'] else "Unprocessed"
        email_status = guest.get('email_status', 'No email sent')
        print(f"- {guest['name']} ({guest['email']}) - {status} - {email_status}")
    
    print(f"\n=== Summary ===")
    print(f"Total guests in database: {len(all_guests)}")
    print(f"Import completed successfully!")

def list_available_files():
    """List all available Excel and CSV files."""
    print("=== Available Data Files ===")
    
    files = []
    for ext in ['.xlsx', '.csv']:
        for file in os.listdir('.'):
            if file.endswith(ext):
                files.append(file)
        
        # Check src directory too
        if os.path.exists('src'):
            for file in os.listdir('src'):
                if file.endswith(ext):
                    files.append(f"src/{file}")
    
    if files:
        print("Found data files:")
        for i, file in enumerate(files, 1):
            size = os.path.getsize(file) if os.path.exists(file) else 0
            print(f"  {i}. {file} ({size:,} bytes)")
    else:
        print("No Excel or CSV files found")
    
    return files

if __name__ == "__main__":
    # First list available files
    available_files = list_available_files()
    
    # Try to import from the Excel file
    import_from_excel_file("Soulful Guest Questionnaire30072025.xlsx")
