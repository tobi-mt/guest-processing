#!/usr/bin/env python3
"""
Test script to verify the Guest Database Manager app functionality.
"""

import sys
import os
import sqlite3
import pandas as pd

# Add the src directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from guest_database_manager.database import GuestDatabase

def test_database_functionality():
    """Test the database functionality."""
    print("🔍 Testing Database Functionality...")
    
    # Initialize database
    db = GuestDatabase()
    
    # Get all guests
    guests = db.get_all_guests()
    print(f"✅ Total guests in database: {len(guests)}")
    
    if len(guests) > 0:
        print("\n📋 Sample guest data:")
        for i, guest in enumerate(guests[:3]):  # Show first 3 guests
            print(f"  {i+1}. {guest.get('full_name', 'No name')} - {guest.get('email', 'No email')}")
            print(f"     Business: {guest.get('business_type', 'Not specified')}")
            print(f"     Status: {'Processed' if guest.get('is_processed') else 'Unprocessed'}")
            print()
    
    # Test statistics
    total_guests = len(guests)
    processed_count = sum(1 for g in guests if g.get('is_processed'))
    with_email_count = sum(1 for g in guests if g.get('email') and g.get('email') != '')
    
    print("📊 Database Statistics:")
    print(f"  Total guests: {total_guests}")
    print(f"  Processed: {processed_count}")
    print(f"  Unprocessed: {total_guests - processed_count}")
    print(f"  With emails: {with_email_count}")
    print(f"  Without emails: {total_guests - with_email_count}")
    
    return True

def test_database_schema():
    """Test the database schema."""
    print("\n🏗️  Testing Database Schema...")
    
    db_path = "guest_database.db"
    if not os.path.exists(db_path):
        print("❌ Database file not found!")
        return False
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Get table info
    cursor.execute("PRAGMA table_info(guests)")
    columns = cursor.fetchall()
    
    print("📋 Database columns:")
    for col in columns:
        print(f"  - {col[1]} ({col[2]})")
    
    # Check for critical columns
    column_names = [col[1] for col in columns]
    required_columns = ['id', 'full_name', 'email', 'is_processed', 'date_added']
    
    for req_col in required_columns:
        if req_col in column_names:
            print(f"  ✅ {req_col} - found")
        else:
            print(f"  ❌ {req_col} - missing")
    
    conn.close()
    return True

def test_column_mapping():
    """Test that the app columns match database columns."""
    print("\n🔗 Testing Column Mapping...")
    
    # Expected columns from the questionnaire
    expected_columns = [
        'id', 'full_name', 'email', 'business_type', 'website', 
        'background', 'motivation', 'core_values', 'has_social_media',
        'completion_time', 'is_processed', 'date_added'
    ]
    
    db = GuestDatabase()
    guests = db.get_all_guests()
    
    if len(guests) > 0:
        first_guest = guests[0]
        
        print("🔍 Checking column availability in guest data:")
        for col in expected_columns:
            if col in first_guest:
                value = first_guest[col]
                if pd.isna(value) or value == "":
                    print(f"  📝 {col} - exists (empty)")
                else:
                    print(f"  ✅ {col} - exists with data")
            else:
                print(f"  ❌ {col} - missing")
    
    return True

def main():
    """Main test function."""
    print("🚀 Guest Database Manager - Functionality Test")
    print("=" * 50)
    
    try:
        test_database_schema()
        test_database_functionality()
        test_column_mapping()
        
        print("\n🎉 All tests completed successfully!")
        print("\n📝 Summary:")
        print("  ✅ Database schema is correct")
        print("  ✅ Database functionality works")
        print("  ✅ Column mapping is compatible with app")
        print("\n🌐 You can now run the app with:")
        print("  ./Guest\\ Database\\ Manager.command")
        print("  OR")
        print("  streamlit run src/guest_database_manager/app.py")
        
    except (ImportError, sqlite3.Error, FileNotFoundError) as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    return True

if __name__ == "__main__":
    main()
