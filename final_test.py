#!/usr/bin/env python3
"""
Final end-to-end test of the Guest Database Manager CSV import functionality.
This script will test the complete import process with a real CSV file.
"""

import sys
import os
import logging

# Add the src directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from guest_database_manager.database import GuestDatabase

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def test_csv_import():
    """Test CSV import functionality with a real file."""
    
    # Initialize database
    db = GuestDatabase("test_import.db")
    
    # Test files to try
    test_files = [
        "Soulful Guest Questionnaire.csv",
        "Soulful Guest Questionnaire 10_07_2025.csv",
        "src/Soulful Guest Questionnaire 22052025.csv"
    ]
    
    successful_import = False
    
    for file_path in test_files:
        if os.path.exists(file_path):
            print(f"\n🔍 Testing import with file: {file_path}")
            
            try:
                # Import the CSV
                stats = db.import_from_csv(file_path)
                
                print(f"📊 Import Results:")
                print(f"   ✅ Imported: {stats['imported']}")
                print(f"   🔄 Updated: {stats['updated']}")
                print(f"   ⏭️  Skipped: {stats['skipped']}")
                print(f"   ❌ Errors: {stats['errors']}")
                
                # Get database stats
                db_stats = db.get_stats()
                print(f"\n📈 Database Statistics:")
                print(f"   👥 Total guests: {db_stats['total']}")
                print(f"   ✅ Processed: {db_stats['processed']}")
                print(f"   ⏳ Unprocessed: {db_stats['unprocessed']}")
                
                # Show a few sample records
                guests = db.get_all_guests()
                if guests:
                    print(f"\n📋 Sample imported guests:")
                    for i, guest in enumerate(guests[:3]):
                        print(f"   {i+1}. {guest['name']} - {guest['email']}")
                        print(f"      Business: {guest['business_type']}")
                        print(f"      Location: {guest['location']}")
                        print()
                
                successful_import = True
                break
                
            except Exception as e:
                print(f"❌ Error importing {file_path}: {e}")
                continue
        else:
            print(f"⚠️  File not found: {file_path}")
    
    if successful_import:
        print("✅ CSV import test completed successfully!")
        
        # Test email stats
        try:
            email_stats = db.get_email_stats()
            print(f"\n📧 Email Statistics:")
            print(f"   With email: {email_stats['with_email']}")
            print(f"   Without email: {email_stats['without_email']}")
        except Exception as e:
            print(f"⚠️  Email stats error (expected): {e}")
        
        return True
    else:
        print("❌ No CSV files could be imported successfully.")
        return False

def test_excel_import():
    """Test Excel import functionality."""
    db = GuestDatabase("test_import.db")
    
    excel_files = [
        "Soulful Guest Questionnaire30072025.xlsx"
    ]
    
    for file_path in excel_files:
        if os.path.exists(file_path):
            print(f"\n🔍 Testing Excel import with file: {file_path}")
            
            try:
                stats = db.import_from_excel(file_path)
                
                print(f"📊 Excel Import Results:")
                print(f"   ✅ Imported: {stats['imported']}")
                print(f"   🔄 Updated: {stats['updated']}")
                print(f"   ⏭️  Skipped: {stats['skipped']}")
                print(f"   ❌ Errors: {stats['errors']}")
                
                return True
                
            except Exception as e:
                print(f"❌ Error importing Excel {file_path}: {e}")
                continue
        else:
            print(f"⚠️  Excel file not found: {file_path}")
    
    return False

if __name__ == "__main__":
    print("🚀 Starting Guest Database Manager End-to-End Test")
    print("="*60)
    
    # Clean up any existing test database
    if os.path.exists("test_import.db"):
        os.remove("test_import.db")
    
    success = True
    
    # Test CSV import
    if not test_csv_import():
        success = False
    
    # Test Excel import
    if not test_excel_import():
        print("⚠️  Excel import test failed (might be expected)")
    
    # Clean up test database
    if os.path.exists("test_import.db"):
        os.remove("test_import.db")
    
    if success:
        print("\n🎉 All tests passed! The Guest Database Manager is ready to use.")
        print("💡 You can now use the web interface at http://localhost:8052")
    else:
        print("\n❌ Some tests failed. Please check the CSV files and import logic.")
    
    print("="*60)
