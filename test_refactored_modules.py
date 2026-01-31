#!/usr/bin/env python3
"""Test script to verify refactored modules work correctly."""

import sys
from pathlib import Path

# Add src directory to path
sys.path.insert(0, str(Path(__file__).parent / "src" / "guest_database_manager"))

def test_constants():
    """Test constants module."""
    print("Testing constants module...")
    from constants import COLUMN_MAPPINGS, DB_COLUMN_MAP, DEFAULT_DB_PATH
    
    assert len(COLUMN_MAPPINGS) > 0, "Column mappings should not be empty"
    assert "full_name" in COLUMN_MAPPINGS, "Should have full_name mapping"
    assert "email" in COLUMN_MAPPINGS, "Should have email mapping"
    print("✅ Constants module OK")

def test_data_mapper():
    """Test data mapper module."""
    print("\nTesting data mapper module...")
    import pandas as pd
    from data_mapper import DataMapper
    
    # Create test data
    test_row = pd.Series({
        "Full name": "Test User",
        "Email": "test@example.com",
        "Website": "https://example.com"
    })
    
    mapper = DataMapper()
    guest_data = mapper.clean_guest_data(test_row)
    
    assert guest_data['full_name'] == "Test User", "Should extract full name"
    assert guest_data['email'] == "test@example.com", "Should extract email"
    assert guest_data['website'] == "https://example.com", "Should extract website"
    
    # Test validation
    is_valid, error = mapper.validate_guest_data(guest_data)
    assert is_valid, f"Valid data should pass validation: {error}"
    
    # Test invalid data
    invalid_data = {"full_name": "", "email": ""}
    is_valid, error = mapper.validate_guest_data(invalid_data)
    assert not is_valid, "Invalid data should fail validation"
    
    print("✅ Data mapper module OK")

def test_file_reader():
    """Test file reader module."""
    print("\nTesting file reader module...")
    from file_reader import FileReader
    
    # Test with non-existent file
    df = FileReader.read_file("nonexistent.csv")
    assert df is None, "Should return None for non-existent file"
    
    print("✅ File reader module OK")

def test_schema_manager():
    """Test schema manager module."""
    print("\nTesting schema manager module...")
    import tempfile
    import os
    from schema_manager import SchemaManager
    
    # Create temporary database
    temp_db = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
    temp_db.close()
    
    try:
        # Test schema creation
        SchemaManager.create_tables(temp_db.name)
        
        # Test schema verification
        is_valid = SchemaManager.verify_schema(temp_db.name)
        assert is_valid, "Schema should be valid after creation"
        
        # Test column retrieval
        columns = SchemaManager.get_column_names(temp_db.name)
        assert len(columns) > 0, "Should have columns"
        assert 'id' in columns, "Should have id column"
        assert 'name' in columns, "Should have name column"
        assert 'full_name' in columns, "Should have full_name column"
        
        print("✅ Schema manager module OK")
    finally:
        # Clean up
        os.unlink(temp_db.name)

def test_database_refactored():
    """Test refactored database module."""
    print("\nTesting refactored database module...")
    import tempfile
    import os
    from database_refactored import GuestDatabase
    
    # Create temporary database
    temp_db = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
    temp_db.close()
    
    try:
        # Initialize database
        db = GuestDatabase(temp_db.name)
        
        # Test insert
        guest_data = {
            'full_name': 'Test Guest',
            'email': 'test@example.com',
            'website': 'https://example.com',
            'profession': 'Software Engineer',
            'is_processed': False
        }
        guest_id = db.insert_guest(guest_data)
        assert guest_id > 0, "Should return valid guest ID"
        
        # Test get by ID
        guest = db.get_guest_by_id(guest_id)
        assert guest is not None, "Should retrieve guest by ID"
        assert guest['email'] == 'test@example.com', "Should have correct email"
        
        # Test get by name
        guest = db.get_guest_by_name('Test Guest')
        assert guest is not None, "Should retrieve guest by name"
        
        # Test get all
        all_guests = db.get_all_guests()
        assert len(all_guests) == 1, "Should have one guest"
        
        # Test update
        guest_data['profession'] = 'Senior Engineer'
        db.update_guest_by_id(guest_id, guest_data)
        updated_guest = db.get_guest_by_id(guest_id)
        assert updated_guest['profession'] == 'Senior Engineer', "Should update profession"
        
        # Test stats
        stats = db.get_stats()
        assert stats['total'] == 1, "Should have 1 total guest"
        assert stats['unprocessed'] == 1, "Should have 1 unprocessed guest"
        
        # Test mark processed
        db.mark_guest_processed(guest_id)
        stats = db.get_stats()
        assert stats['processed'] == 1, "Should have 1 processed guest"
        
        # Test email stats
        email_stats = db.get_email_stats()
        assert isinstance(email_stats, dict), "Should return email stats dict"
        
        # Test delete
        db.delete_guest(guest_id)
        deleted_guest = db.get_guest_by_id(guest_id)
        assert deleted_guest is None, "Guest should be deleted"
        
        print("✅ Refactored database module OK")
    finally:
        # Clean up
        os.unlink(temp_db.name)

def main():
    """Run all tests."""
    print("=" * 60)
    print("Running Refactored Module Tests")
    print("=" * 60)
    
    try:
        test_constants()
        test_data_mapper()
        test_file_reader()
        test_schema_manager()
        test_database_refactored()
        
        print("\n" + "=" * 60)
        print("✅ ALL TESTS PASSED!")
        print("=" * 60)
        print("\nThe refactored modules are working correctly.")
        print("You can now safely replace the old database.py with database_refactored.py")
        return 0
    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        return 1
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())
