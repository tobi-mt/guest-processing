#!/usr/bin/env python3
"""
Test script to verify that the enhanced import logic correctly handles 
different email column names and prevents duplicates.
"""

import pandas as pd
import tempfile
import os
from src.guest_database_manager.database import GuestDatabase

def test_import_with_different_email_columns():
    """Test importing data with different email column names."""
    
    # Create test data with different email column names
    test_data_email2 = {
        'Name': ['Test User 1', 'Test User 2'],
        'Email2': ['test1@example.com', 'test2@example.com'],
        'Phone': ['123-456-7890', '098-765-4321']
    }
    
    test_data_guest_email = {
        'Name': ['Test User 1', 'Test User 3'],  # Test User 1 is duplicate
        "Guest's Email": ['test1@example.com', 'test3@example.com'],
        'Phone': ['123-456-7890', '555-555-5555']
    }
    
    # Create temporary CSV files
    with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f1:
        df1 = pd.DataFrame(test_data_email2)
        df1.to_csv(f1.name, index=False)
        csv_file1 = f1.name
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f2:
        df2 = pd.DataFrame(test_data_guest_email)
        df2.to_csv(f2.name, index=False)
        csv_file2 = f2.name
    
    try:
        # Create a test database
        test_db = GuestDatabase("test_import.db")
        
        print("Testing import with 'Email2' column...")
        stats1 = test_db.import_from_csv(csv_file1)
        print(f"First import stats: {stats1}")
        
        print("\nTesting import with 'Guest's Email' column...")
        stats2 = test_db.import_from_csv(csv_file2)
        print(f"Second import stats: {stats2}")
        
        # Check final results
        all_guests = test_db.get_all_guests()
        print(f"\nFinal guest count: {len(all_guests)}")
        
        print("\nGuests in database:")
        for guest in all_guests:
            print(f"  {guest['name']} - {guest['email']}")
        
        # Verify no duplicates by name
        names = [guest['name'].lower().strip() for guest in all_guests]
        unique_names = set(names)
        print(f"\nUnique names: {len(unique_names)}, Total guests: {len(all_guests)}")
        
        if len(unique_names) == len(all_guests):
            print("✅ SUCCESS: No duplicate names found!")
        else:
            print("❌ ERROR: Duplicate names found!")
        
        # Test email column detection
        print("\n" + "="*50)
        print("Testing email column detection:")
        
        # Test with Email2
        test_row_email2 = pd.Series({'Name': 'Test', 'Email2': 'test@example.com'})
        email = test_db.get_column_value(test_row_email2, ["Email", "email", "Email2", "email2", "Guest's Email", "guest's email"])
        print(f"Email2 detection: {email}")
        
        # Test with Guest's Email
        test_row_guest = pd.Series({'Name': 'Test', "Guest's Email": 'guest@example.com'})
        email = test_db.get_column_value(test_row_guest, ["Email", "email", "Email2", "email2", "Guest's Email", "guest's email"])
        print(f"Guest's Email detection: {email}")
        
    finally:
        # Clean up
        os.unlink(csv_file1)
        os.unlink(csv_file2)
        if os.path.exists("test_import.db"):
            os.unlink("test_import.db")

if __name__ == "__main__":
    test_import_with_different_email_columns()
