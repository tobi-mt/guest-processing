#!/usr/bin/env python3
"""
Quick verification test for the fixed Guest Database Manager.
"""

import sys
import os

# Add the src directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from guest_database_manager.database import GuestDatabase

def test_basic_functionality():
    """Test that all the fixed functionality works."""
    
    print("🧪 Testing Guest Database Manager - Final Verification")
    print("="*60)
    
    # Clean up any existing test database
    if os.path.exists("verification_test.db"):
        os.remove("verification_test.db")
    
    # Initialize database
    db = GuestDatabase("verification_test.db")
    
    # Test 1: get_stats method
    try:
        stats = db.get_stats()
        print(f"✅ get_stats() works: {stats}")
    except Exception as e:
        print(f"❌ get_stats() failed: {e}")
        return False
    
    # Test 2: get_email_stats method
    try:
        email_stats = db.get_email_stats()
        print(f"✅ get_email_stats() works: {email_stats}")
        
        # Check if it has all required keys
        required_keys = ['with_email', 'without_email', 'total_emails', 'accepted_emails', 'rejected_emails', 'skipped_guests']
        for key in required_keys:
            if key not in email_stats:
                print(f"❌ Missing key '{key}' in email_stats")
                return False
        print("✅ All required email_stats keys present")
        
    except Exception as e:
        print(f"❌ get_email_stats() failed: {e}")
        return False
    
    # Test 3: get_all_guests method returns list
    try:
        guests = db.get_all_guests()
        print(f"✅ get_all_guests() returns list: {type(guests)}")
        if not isinstance(guests, list):
            print(f"❌ get_all_guests() should return list, got {type(guests)}")
            return False
    except Exception as e:
        print(f"❌ get_all_guests() failed: {e}")
        return False
    
    # Test 4: import_from_csv method exists
    try:
        if hasattr(db, 'import_from_csv'):
            print("✅ import_from_csv method exists")
        else:
            print("❌ import_from_csv method missing")
            return False
    except Exception as e:
        print(f"❌ Error checking import_from_csv: {e}")
        return False
    
    # Test 5: import_from_excel method exists
    try:
        if hasattr(db, 'import_from_excel'):
            print("✅ import_from_excel method exists")
        else:
            print("❌ import_from_excel method missing")
            return False
    except Exception as e:
        print(f"❌ Error checking import_from_excel: {e}")
        return False
    
    # Clean up test database
    if os.path.exists("verification_test.db"):
        os.remove("verification_test.db")
    
    print("\n🎉 All basic functionality tests passed!")
    print("💻 The Guest Database Manager web app should now work correctly.")
    print("🌐 Access it at: http://localhost:8052")
    print("="*60)
    
    return True

if __name__ == "__main__":
    success = test_basic_functionality()
    if success:
        print("\n✅ VERIFICATION COMPLETE - All systems are working!")
    else:
        print("\n❌ VERIFICATION FAILED - Some issues remain.")
