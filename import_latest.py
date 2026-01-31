#!/usr/bin/env python3
"""Import from the most recent CSV file."""

import sys
sys.path.insert(0, 'src')

from guest_database_manager.database import GuestDatabase

def import_latest_data():
    """Import from the most recent CSV file."""
    print("Importing from the most recent CSV file...")
    
    # Initialize database
    db = GuestDatabase('guest_database.db')
    
    # Get initial stats
    print("\n=== Initial Stats ===")
    initial_stats = db.get_stats()
    for key, value in initial_stats.items():
        print(f"{key}: {value}")
    
    # Import from the most recent file
    file_path = "src/Soulful Guest Questionnaire 22052025.csv"
    print(f"\n=== Importing from {file_path} ===")
    
    import_stats = db.import_from_csv(file_path)
    print("Import results:")
    for key, value in import_stats.items():
        print(f"{key}: {value}")
    
    # Get final stats
    print("\n=== Final Stats ===")
    final_stats = db.get_stats()
    for key, value in final_stats.items():
        print(f"{key}: {value}")
    
    # Show the difference
    print("\n=== Changes ===")
    for key in final_stats:
        change = final_stats[key] - initial_stats[key]
        if change != 0:
            print(f"{key}: +{change}")
    
    # Get email stats
    print("\n=== Email Stats ===")
    email_stats = db.get_email_stats()
    for key, value in email_stats.items():
        print(f"{key}: {value}")

if __name__ == "__main__":
    import_latest_data()
