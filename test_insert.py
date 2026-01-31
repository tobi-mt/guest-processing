#!/usr/bin/env python3
"""Test script to check column mapping issues."""

import sqlite3
import sys
from pathlib import Path

# Add the src directory to the Python path
sys.path.insert(0, str(Path(__file__).parent / "src" / "guest_database_manager"))

def test_insert():
    """Test inserting a simple record to identify column issues."""
    
    # Connect to database
    db_path = "guest_database.db"
    
    # Get all columns from database
    with sqlite3.connect(db_path) as conn:
        cursor = conn.execute("PRAGMA table_info(guests)")
        columns = cursor.fetchall()
        print("Database columns:")
        for col in columns:
            print(f"  {col[1]} ({col[2]})")
    
    # Try to insert with minimal data
    test_data = {
        'full_name': 'Test Guest',
        'email': 'test@example.com',
        'is_processed': False
    }
    
    print("\nTrying to insert test data...")
    
    try:
        with sqlite3.connect(db_path) as conn:
            cursor = conn.execute("""
                INSERT INTO guests (full_name, email, is_processed, updated_at) 
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            """, (test_data['full_name'], test_data['email'], test_data['is_processed']))
            conn.commit()
            print(f"✅ Successfully inserted test guest with ID: {cursor.lastrowid}")
            
            # Clean up
            conn.execute("DELETE FROM guests WHERE id = ?", (cursor.lastrowid,))
            conn.commit()
            print("✅ Test record cleaned up")
            
    except Exception as e:
        print(f"❌ Insert failed: {e}")
        return False
    
    return True

if __name__ == "__main__":
    test_insert()
