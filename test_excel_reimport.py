#!/usr/bin/env python3
"""
Test re-importing Excel data to verify no duplicates are created
"""

import pandas as pd
import tempfile
import os
from src.guest_database_manager.database import GuestDatabase

def test_excel_reimport():
    """Test re-importing Excel data with Guest's Email column."""
    
    # Create test data similar to what would be in an Excel file
    test_data = {
        'Name': ['Alex Dumas', 'Kute Blackson', 'New Person'],
        "Guest's Email": ['alex@bipoccc.org', 'media@kuteblackson.com', 'new@example.com'],
        'Phone': ['555-0001', '555-0002', '555-0003']
    }
    
    # Create temporary Excel file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.xlsx', delete=False) as f:
        df = pd.DataFrame(test_data)
        df.to_excel(f.name, index=False)
        excel_file = f.name
    
    try:
        # Use the real database
        db = GuestDatabase()
        
        # Get initial count
        initial_guests = len(db.get_all_guests())
        print(f"Initial guest count: {initial_guests}")
        
        # Check specific guests before import
        alex_before = db.get_guest_by_name('Alex Dumas')
        kute_before = db.get_guest_by_name('Kute Blackson')
        
        print(f"Alex Dumas before: ID {alex_before['id'] if alex_before else 'None'}")
        print(f"Kute Blackson before: ID {kute_before['id'] if kute_before else 'None'}")
        
        print("\nImporting Excel with 'Guest's Email' column...")
        stats = db.import_from_excel(excel_file)
        print(f"Import stats: {stats}")
        
        # Get final count
        final_guests = len(db.get_all_guests())
        print(f"Final guest count: {final_guests}")
        
        # Check specific guests after import
        alex_after = db.get_guest_by_name('Alex Dumas')
        kute_after = db.get_guest_by_name('Kute Blackson')
        
        print(f"Alex Dumas after: ID {alex_after['id'] if alex_after else 'None'}")
        print(f"Kute Blackson after: ID {kute_after['id'] if kute_after else 'None'}")
        
        # Verify no duplicates
        import sqlite3
        conn = sqlite3.connect('guest_database.db')
        cursor = conn.cursor()
        cursor.execute('SELECT LOWER(TRIM(name)) as name_lower, COUNT(*) as count FROM guests GROUP BY LOWER(TRIM(name)) HAVING COUNT(*) > 1')
        duplicates = cursor.fetchall()
        
        if len(duplicates) == 0:
            print("\n✅ SUCCESS: No duplicates created!")
        else:
            print(f"\n❌ ERROR: {len(duplicates)} duplicate groups found!")
            for name, count in duplicates:
                print(f"  {name}: {count} entries")
        
        conn.close()
        
        # Expected results
        expected_imported = 1  # Only "New Person" should be imported
        expected_updated = 2   # Alex and Kute should be updated
        
        if (stats['imported'] == expected_imported and 
            stats['updated'] == expected_updated and
            final_guests == initial_guests + expected_imported):
            print("✅ Import behavior is correct!")
        else:
            print("❌ Import behavior unexpected:")
            print(f"  Expected: {expected_imported} imported, {expected_updated} updated")
            print(f"  Actual: {stats['imported']} imported, {stats['updated']} updated")
            
    finally:
        # Clean up
        os.unlink(excel_file)

if __name__ == "__main__":
    test_excel_reimport()
