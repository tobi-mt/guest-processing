#!/usr/bin/env python3
"""
Comprehensive test to verify the Guest Database Manager is working correctly.
"""

import sys
import os

# Add the src directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from guest_database_manager.database import GuestDatabase

def test_all_functionality():
    """Test all database functionality that the app uses."""
    
    print("🧪 COMPREHENSIVE GUEST DATABASE MANAGER TEST")
    print("="*60)
    
    # Initialize database
    db = GuestDatabase('guest_database.db')
    
    all_tests_passed = True
    
    # Test 1: get_stats
    try:
        stats = db.get_stats()
        print(f"✅ get_stats(): {stats}")
        assert 'total' in stats
        assert 'processed' in stats  
        assert 'unprocessed' in stats
        print("   ✅ All required keys present")
    except Exception as e:
        print(f"❌ get_stats() failed: {e}")
        all_tests_passed = False
    
    # Test 2: get_email_stats
    try:
        email_stats = db.get_email_stats()
        print(f"✅ get_email_stats(): {email_stats}")
        
        required_keys = ['with_email', 'without_email', 'total_emails', 'accepted_emails', 'rejected_emails', 'skipped_guests']
        for key in required_keys:
            assert key in email_stats, f"Missing key: {key}"
            print(f"   ✅ {key}: {email_stats[key]}")
        
        print("   ✅ All required email stats keys present")
    except Exception as e:
        print(f"❌ get_email_stats() failed: {e}")
        all_tests_passed = False
    
    # Test 3: get_all_guests
    try:
        guests = db.get_all_guests()
        print(f"✅ get_all_guests(): Found {len(guests)} guests")
        assert isinstance(guests, list)
        print("   ✅ Returns list as expected")
    except Exception as e:
        print(f"❌ get_all_guests() failed: {e}")
        all_tests_passed = False
    
    # Test 4: Safe dictionary access (simulating what the app does)
    try:
        email_stats = db.get_email_stats()
        
        # Test .get() method access (this is what the app now uses)
        total_emails = email_stats.get("total_emails", 0)
        accepted_emails = email_stats.get("accepted_emails", 0)
        rejected_emails = email_stats.get("rejected_emails", 0)
        skipped_guests = email_stats.get("skipped_guests", 0)
        
        print(f"✅ Safe dictionary access works:")
        print(f"   📧 Total Emails: {total_emails}")
        print(f"   ✅ Accepted: {accepted_emails}")
        print(f"   ❌ Rejected: {rejected_emails}")
        print(f"   ⏭️ Skipped: {skipped_guests}")
        
    except Exception as e:
        print(f"❌ Safe dictionary access failed: {e}")
        all_tests_passed = False
    
    print("="*60)
    
    if all_tests_passed:
        print("🎉 ALL TESTS PASSED!")
        print("✅ The Guest Database Manager should work correctly")
        print("🌐 Web interface available at: http://localhost:8052")
    else:
        print("❌ SOME TESTS FAILED!")
        print("⚠️  There may still be issues with the application")
    
    return all_tests_passed

if __name__ == "__main__":
    test_all_functionality()
