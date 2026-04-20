"""Helper script to test Google Service Account Calendar integration."""

import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Add src to path for local testing
sys.path.insert(0, str(Path(__file__).parent / "src"))

from guest_database_manager.google_service_account_calendar import (
    GoogleServiceAccountCalendarClient,
    GoogleCalendarServiceAccountError,
)


def print_section(title: str):
    """Print a formatted section header."""
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60 + "\n")


def test_service_account():
    """Test the Google Service Account calendar integration."""
    
    print_section("Google Service Account Calendar Test")
    
    # Check environment variables
    service_account_file = os.environ.get("MIRROR_TALK_GOOGLE_SERVICE_ACCOUNT_FILE", "").strip()
    calendar_id = os.environ.get("MIRROR_TALK_GOOGLE_CALENDAR_ID", "").strip()
    
    if not service_account_file:
        print("❌ MIRROR_TALK_GOOGLE_SERVICE_ACCOUNT_FILE not set")
        print("\nPlease set this environment variable to the path of your service account JSON key file.")
        print("Example:")
        print('  export MIRROR_TALK_GOOGLE_SERVICE_ACCOUNT_FILE="/path/to/service-account-key.json"')
        return False
    
    if not calendar_id:
        print("❌ MIRROR_TALK_GOOGLE_CALENDAR_ID not set")
        print("\nPlease set this environment variable to your Google Calendar ID.")
        print("Example:")
        print('  export MIRROR_TALK_GOOGLE_CALENDAR_ID="your-calendar@gmail.com"')
        return False
    
    print(f"✅ Service Account File: {service_account_file}")
    print(f"✅ Calendar ID: {calendar_id}")
    
    # Check if file exists
    if not Path(service_account_file).exists():
        print(f"\n❌ Service account file not found: {service_account_file}")
        return False
    
    print(f"✅ Service account file exists")
    
    # Try to create client
    print_section("Creating Calendar Client")
    
    try:
        client = GoogleServiceAccountCalendarClient(
            service_account_file=service_account_file,
            calendar_id=calendar_id,
        )
        print(f"✅ Calendar client created successfully")
        print(f"   Service Account Email: {client.credentials.get('client_email')}")
    except GoogleCalendarServiceAccountError as exc:
        print(f"❌ Failed to create calendar client: {exc}")
        return False
    except Exception as exc:
        print(f"❌ Unexpected error: {exc}")
        return False
    
    # Try to fetch events
    print_section("Fetching Calendar Events")
    
    try:
        events = client.list_upcoming_events(days_ahead=30)
        print(f"✅ Successfully fetched {len(events)} upcoming event(s)")
        
        if events:
            print("\nUpcoming events:")
            for i, event in enumerate(events[:5], 1):  # Show first 5
                summary = event.get('summary', 'No title')
                start = event.get('start', {}).get('dateTime', 'No start time')
                print(f"  {i}. {summary}")
                print(f"     Start: {start}")
        else:
            print("\nNo upcoming events found in the next 30 days.")
    except GoogleCalendarServiceAccountError as exc:
        print(f"❌ Failed to fetch events: {exc}")
        print("\nPossible issues:")
        print("1. Calendar not shared with service account")
        print(f"   → Share '{calendar_id}' with: {client.credentials.get('client_email')}")
        print("2. Calendar API not enabled in Google Cloud Console")
        print("   → Enable at: https://console.cloud.google.com/apis/library/calendar-json.googleapis.com")
        print("3. Incorrect calendar ID")
        print("   → Check calendar settings in Google Calendar")
        return False
    except Exception as exc:
        print(f"❌ Unexpected error: {exc}")
        return False
    
    # Success!
    print_section("Test Complete")
    print("✅ All tests passed!")
    print("\nYour service account calendar integration is working correctly.")
    print("You can now use this in your application without worrying about token expiration!")
    
    return True


def migration_instructions():
    """Print migration instructions."""
    print_section("Migration Instructions")
    
    print("""
To migrate from refresh tokens to service account:

1. Create Service Account (if not done):
   - Go to: https://console.cloud.google.com/iam-admin/serviceaccounts
   - Create new service account
   - Download JSON key file

2. Share Calendar with Service Account:
   - Open Google Calendar
   - Click settings (⚙️) → Settings
   - Select your calendar
   - Under "Share with specific people", add service account email
   - Grant "Make changes to events" permission

3. Update Environment Variables:
   
   # Old (remove these):
   unset MIRROR_TALK_GOOGLE_CLIENT_ID
   unset MIRROR_TALK_GOOGLE_CLIENT_SECRET
   unset MIRROR_TALK_GOOGLE_REFRESH_TOKEN
   
   # New (add these):
   export MIRROR_TALK_GOOGLE_SERVICE_ACCOUNT_FILE="/path/to/service-account-key.json"
   export MIRROR_TALK_GOOGLE_CALENDAR_ID="your-calendar@gmail.com"

4. Install Required Dependencies:
   pip install pyjwt

5. Run This Test Script:
   python test_service_account_calendar.py

6. Update Your Code:
   - Import: from guest_database_manager.google_service_account_calendar import create_client_from_env
   - Use: client = create_client_from_env()
   - Or: client = GoogleServiceAccountCalendarClient(service_account_file, calendar_id)

For detailed instructions, see: GOOGLE_OAUTH_TESTING_MODE_SOLUTIONS.md
""")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--help":
        migration_instructions()
    else:
        success = test_service_account()
        if not success:
            print("\n💡 Run with --help flag for migration instructions")
            print("   python test_service_account_calendar.py --help")
            sys.exit(1)
