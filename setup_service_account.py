#!/usr/bin/env python3
"""
Quick setup wizard for Google Service Account calendar integration.

This interactive script helps you configure your service account credentials.
"""

import json
import os
import sys
from pathlib import Path


def print_header(text: str):
    """Print a formatted header."""
    print("\n" + "=" * 70)
    print(f"  {text}")
    print("=" * 70 + "\n")


def print_step(number: int, text: str):
    """Print a step number."""
    print(f"\n🔹 Step {number}: {text}")
    print("-" * 70)


def validate_service_account_file(file_path: str) -> tuple[bool, str]:
    """
    Validate that a service account file exists and is valid JSON.
    
    Returns:
        (is_valid, message)
    """
    path = Path(file_path).expanduser()
    
    if not path.exists():
        return False, f"File not found: {path}"
    
    try:
        with open(path, 'r') as f:
            data = json.load(f)
        
        required_fields = ["type", "client_email", "private_key"]
        missing = [f for f in required_fields if f not in data]
        
        if missing:
            return False, f"Missing required fields: {', '.join(missing)}"
        
        if data.get("type") != "service_account":
            return False, f"Invalid type: {data.get('type')} (expected: service_account)"
        
        return True, data["client_email"]
    
    except json.JSONDecodeError as e:
        return False, f"Invalid JSON: {e}"
    except Exception as e:
        return False, f"Error reading file: {e}"


def setup_wizard():
    """Interactive setup wizard."""
    
    print_header("Google Service Account Setup Wizard")
    
    print("This wizard will help you configure Google Calendar with a Service Account.")
    print("Service accounts solve the token expiration problem - they never expire!")
    
    # Check if already configured
    existing_file = os.environ.get("MIRROR_TALK_GOOGLE_SERVICE_ACCOUNT_FILE", "").strip()
    existing_calendar = os.environ.get("MIRROR_TALK_GOOGLE_CALENDAR_ID", "").strip()
    
    if existing_file and existing_calendar:
        print("\n⚠️  You already have service account credentials configured:")
        print(f"   File: {existing_file}")
        print(f"   Calendar: {existing_calendar}")
        
        response = input("\nDo you want to reconfigure? (y/N): ").strip().lower()
        if response != 'y':
            print("\nSetup cancelled.")
            return
    
    # Step 1: Service Account File
    print_step(1, "Locate Your Service Account JSON Key File")
    
    print("""
If you haven't created a service account yet:
  1. Go to: https://console.cloud.google.com/iam-admin/serviceaccounts
  2. Create a new service account (or use existing)
  3. Create and download a JSON key
  
See SERVICE_ACCOUNT_SETUP.md for detailed instructions.
""")
    
    while True:
        file_path = input("Enter the path to your service account JSON file: ").strip()
        
        if not file_path:
            print("❌ Please provide a file path")
            continue
        
        # Expand ~ to home directory
        file_path = str(Path(file_path).expanduser())
        
        is_valid, message = validate_service_account_file(file_path)
        
        if is_valid:
            print(f"✅ Valid service account file")
            print(f"   Service Account Email: {message}")
            service_account_email = message
            break
        else:
            print(f"❌ {message}")
            retry = input("Try again? (Y/n): ").strip().lower()
            if retry == 'n':
                print("\nSetup cancelled.")
                return
    
    # Step 2: Calendar ID
    print_step(2, "Enter Your Google Calendar ID")
    
    print("""
To find your Calendar ID:
  1. Open Google Calendar (https://calendar.google.com)
  2. Click Settings (⚙️) → Settings
  3. Select your calendar from the left sidebar
  4. Scroll to "Integrate calendar" section
  5. Copy the Calendar ID (usually your email address)

⚠️  IMPORTANT: You must share this calendar with the service account!
    Share with: {service_account_email}
    Permission: "Make changes to events"
""".format(service_account_email=service_account_email))
    
    while True:
        calendar_id = input("Enter your Calendar ID: ").strip()
        
        if not calendar_id:
            print("❌ Please provide a calendar ID")
            continue
        
        if "@" not in calendar_id:
            print("⚠️  Warning: Calendar ID usually contains '@'")
            confirm = input("Is this correct? (y/N): ").strip().lower()
            if confirm != 'y':
                continue
        
        break
    
    # Step 3: Verify Calendar Sharing
    print_step(3, "Verify Calendar Sharing")
    
    print(f"""
Before continuing, make sure you've shared the calendar with the service account:

  1. Open Google Calendar
  2. Find calendar: {calendar_id}
  3. Click ⋮ (three dots) → Settings and sharing
  4. Under "Share with specific people", add:
     
     {service_account_email}
     
  5. Set permission: "Make changes to events"
  6. Click Send (uncheck email notification)
""")
    
    response = input("Have you shared the calendar? (y/N): ").strip().lower()
    if response != 'y':
        print("\n⚠️  Please share the calendar before continuing.")
        print("   Re-run this script after sharing.")
        return
    
    # Step 4: Generate Configuration
    print_step(4, "Generate Configuration")
    
    print("\nHow would you like to store these credentials?\n")
    print("1. Environment variables (shell profile)")
    print("2. .env file (for local development)")
    print("3. Just show me the values (manual setup)")
    
    choice = input("\nEnter choice (1-3): ").strip()
    
    env_vars = f"""
# Google Service Account Configuration
export MIRROR_TALK_GOOGLE_SERVICE_ACCOUNT_FILE="{file_path}"
export MIRROR_TALK_GOOGLE_CALENDAR_ID="{calendar_id}"
""".strip()
    
    dotenv_vars = f"""
# Google Service Account Configuration
MIRROR_TALK_GOOGLE_SERVICE_ACCOUNT_FILE={file_path}
MIRROR_TALK_GOOGLE_CALENDAR_ID={calendar_id}
""".strip()
    
    if choice == "1":
        # Shell profile
        shell = os.environ.get("SHELL", "").lower()
        
        if "zsh" in shell:
            profile = Path.home() / ".zshrc"
        elif "bash" in shell:
            profile = Path.home() / ".bashrc"
        else:
            profile = Path.home() / ".profile"
        
        print(f"\nAdd these lines to your {profile}:\n")
        print(env_vars)
        
        response = input(f"\nAppend to {profile} now? (y/N): ").strip().lower()
        if response == 'y':
            with open(profile, 'a') as f:
                f.write("\n\n" + env_vars + "\n")
            print(f"✅ Added to {profile}")
            print(f"\nRun: source {profile}")
    
    elif choice == "2":
        # .env file
        env_file = Path.cwd() / ".env"
        
        print(f"\nAdd these lines to {env_file}:\n")
        print(dotenv_vars)
        
        response = input(f"\nAppend to {env_file} now? (y/N): ").strip().lower()
        if response == 'y':
            with open(env_file, 'a') as f:
                f.write("\n\n" + dotenv_vars + "\n")
            print(f"✅ Added to {env_file}")
            print("\nRun: source .env")
    
    else:
        # Manual
        print("\nCopy these environment variables:\n")
        print(env_vars)
    
    # Step 5: Test
    print_step(5, "Test the Configuration")
    
    print("""
To test your configuration:

  1. Load the environment variables (see above)
  2. Run the test script:
     
     python test_service_account_calendar.py
     
  3. If successful, you're all set! 🎉

If the test fails:
  - Verify the calendar is shared with the service account
  - Check that Calendar API is enabled in Cloud Console
  - Wait 1-2 minutes for permissions to propagate
""")
    
    response = input("\nRun test now? (y/N): ").strip().lower()
    if response == 'y':
        # Set environment variables for this process
        os.environ["MIRROR_TALK_GOOGLE_SERVICE_ACCOUNT_FILE"] = file_path
        os.environ["MIRROR_TALK_GOOGLE_CALENDAR_ID"] = calendar_id
        
        # Import and run test
        try:
            test_script = Path(__file__).parent / "test_service_account_calendar.py"
            if test_script.exists():
                print("\nRunning test...\n")
                os.system(f"python {test_script}")
            else:
                print("❌ Test script not found")
        except Exception as e:
            print(f"❌ Error running test: {e}")
    
    # Done!
    print_header("Setup Complete!")
    
    print("""
✅ Configuration saved!

Next steps:
  1. Make sure environment variables are loaded
  2. Run: python test_service_account_calendar.py
  3. Start using the service account in your application

For more help, see:
  - SERVICE_ACCOUNT_SETUP.md (step-by-step guide)
  - GOOGLE_OAUTH_TESTING_MODE_SOLUTIONS.md (all solutions)

🎉 You'll never have to manually refresh tokens again!
""")


if __name__ == "__main__":
    try:
        setup_wizard()
    except KeyboardInterrupt:
        print("\n\nSetup cancelled.")
        sys.exit(1)
