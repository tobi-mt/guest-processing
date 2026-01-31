#!/usr/bin/env python3
"""Test script to verify analytics function works without errors."""

import sys
from pathlib import Path

# Add the src directory to the Python path
sys.path.insert(0, str(Path(__file__).parent / "src" / "guest_database_manager"))

import pandas as pd
from database import GuestDatabase


def test_analytics():
    """Test the analytics functionality."""
    # Initialize database
    db = GuestDatabase("guest_database.db")
    
    # Get all guests
    guests_list = db.get_all_guests()
    
    if not guests_list:
        print("❌ No guests found in database")
        return False
    
    print(f"✅ Found {len(guests_list)} guests in database")
    
    # Convert to DataFrame
    guests_df = pd.DataFrame(guests_list)
    print(f"✅ Created DataFrame with {len(guests_df)} rows")
    
    # Test date parsing
    if "date_added" in guests_df.columns:
        try:
            guests_df["date_added"] = pd.to_datetime(guests_df["date_added"], format='mixed', errors='coerce')
            valid_dates = guests_df["date_added"].notna()
            print(f"✅ Date parsing successful: {valid_dates.sum()} valid dates out of {len(guests_df)}")
        except Exception as e:
            print(f"❌ Date parsing failed: {e}")
            return False
    else:
        print("⚠️ No date_added column found")
    
    # Test stats
    try:
        stats = db.get_stats()
        email_stats = db.get_email_stats()
        print(f"✅ Stats retrieved: Total={stats['total']}, Processed={stats['processed']}")
        print(f"✅ Email stats retrieved: Emails={email_stats.get('total_emails', 0)}")
    except Exception as e:
        print(f"❌ Stats retrieval failed: {e}")
        return False
    
    print("✅ All analytics tests passed!")
    return True


if __name__ == "__main__":
    test_analytics()
