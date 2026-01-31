#!/usr/bin/env python3
"""
Test the get_email_stats method directly to verify it works.
"""

import sys
import os

# Add the src directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from guest_database_manager.database import GuestDatabase

def test_email_stats():
    """Test the get_email_stats method directly."""
    
    print("🧪 Testing get_email_stats method directly...")
    
    # Create a test database
    db = GuestDatabase("test_email_stats.db")
    
    try:
        # Call the method
        email_stats = db.get_email_stats()
        print(f"✅ Method call successful!")
        print(f"📊 Returned data: {email_stats}")
        
        # Check for the specific key that's causing the error
        if 'total_emails' in email_stats:
            print(f"✅ 'total_emails' key found: {email_stats['total_emails']}")
        else:
            print(f"❌ 'total_emails' key missing!")
            print(f"🔍 Available keys: {list(email_stats.keys())}")
            return False
        
        # Check all expected keys
        expected_keys = ['with_email', 'without_email', 'total_emails', 'accepted_emails', 'rejected_emails', 'skipped_guests']
        missing_keys = []
        for key in expected_keys:
            if key not in email_stats:
                missing_keys.append(key)
        
        if missing_keys:
            print(f"❌ Missing keys: {missing_keys}")
            return False
        else:
            print(f"✅ All expected keys present!")
        
        return True
        
    except Exception as e:
        print(f"❌ Error calling get_email_stats: {e}")
        return False
    
    finally:
        # Clean up
        if os.path.exists("test_email_stats.db"):
            os.remove("test_email_stats.db")

if __name__ == "__main__":
    success = test_email_stats()
    if success:
        print("\n✅ get_email_stats method is working correctly!")
        print("💡 The issue might be with Streamlit caching or import issues.")
    else:
        print("\n❌ get_email_stats method has issues that need to be fixed.")
