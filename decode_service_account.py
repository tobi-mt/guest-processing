#!/usr/bin/env python3
"""
Decode Google Service Account from base64 environment variable.

This script is used in Railway/cloud deployments where you can't upload files directly.
The service account JSON is base64-encoded and stored in an environment variable,
then decoded to a file at startup.

Usage:
    python decode_service_account.py

Environment Variables:
    MIRROR_TALK_GOOGLE_SERVICE_ACCOUNT_BASE64: Base64-encoded service account JSON
    MIRROR_TALK_GOOGLE_SERVICE_ACCOUNT_FILE: (Optional) Custom path for decoded file
"""

import base64
import json
import os
import sys
from pathlib import Path


def decode_service_account():
    """
    Decode service account from base64 environment variable and save to file.
    
    Returns:
        bool: True if successful, False if skipped or failed
    """
    # Check for base64-encoded service account
    base64_content = os.environ.get("MIRROR_TALK_GOOGLE_SERVICE_ACCOUNT_BASE64", "").strip()
    
    if not base64_content:
        # Not an error - service account is optional
        print("ℹ️  MIRROR_TALK_GOOGLE_SERVICE_ACCOUNT_BASE64 not set")
        print("   Skipping service account setup (will use OAuth if configured)")
        return False
    
    try:
        # Decode base64
        json_content = base64.b64decode(base64_content).decode('utf-8')
        
        # Validate it's valid JSON and has required fields
        service_account_data = json.loads(json_content)
        required_fields = ["type", "client_email", "private_key"]
        missing_fields = [f for f in required_fields if f not in service_account_data]
        
        if missing_fields:
            print(f"❌ Invalid service account JSON: missing fields {', '.join(missing_fields)}")
            return False
        
        if service_account_data.get("type") != "service_account":
            print(f"❌ Invalid service account type: {service_account_data.get('type')}")
            return False
        
        # Determine output path
        output_path = os.environ.get("MIRROR_TALK_GOOGLE_SERVICE_ACCOUNT_FILE", "").strip()
        if not output_path:
            # Default to /tmp for cloud environments (Railway, Heroku, etc.)
            output_path = "/tmp/google-service-account.json"
        
        service_account_path = Path(output_path)
        
        # Create parent directory if it doesn't exist
        service_account_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Save to file
        service_account_path.write_text(json_content)
        
        # Set restrictive permissions (owner read/write only)
        try:
            service_account_path.chmod(0o600)
        except Exception:
            # chmod might fail on some platforms (Windows), that's okay
            pass
        
        # Update environment variable to point to the decoded file
        os.environ["MIRROR_TALK_GOOGLE_SERVICE_ACCOUNT_FILE"] = str(service_account_path)
        
        # Success!
        print(f"✅ Service account decoded and saved to: {service_account_path}")
        print(f"   Service Account Email: {service_account_data.get('client_email')}")
        print(f"   Project: {service_account_data.get('project_id')}")
        
        return True
        
    except base64.binascii.Error as e:
        print(f"❌ Failed to decode base64: {e}")
        print("   Make sure MIRROR_TALK_GOOGLE_SERVICE_ACCOUNT_BASE64 is valid base64")
        return False
    
    except json.JSONDecodeError as e:
        print(f"❌ Failed to parse JSON: {e}")
        print("   The decoded base64 content is not valid JSON")
        return False
    
    except Exception as e:
        print(f"❌ Unexpected error decoding service account: {e}")
        return False


def main():
    """Main entry point."""
    print("=" * 70)
    print("  Google Service Account Setup")
    print("=" * 70)
    
    success = decode_service_account()
    
    if success:
        print("\n✅ Service account ready to use!")
        print("   Your app will use the service account for Google Calendar API")
        print("   (No token expiration issues!)")
    else:
        print("\n⚠️  Service account not configured")
        print("   App will fall back to OAuth refresh token if configured")
        print("   (Note: OAuth tokens expire every 7 days in Testing mode)")
    
    print("=" * 70)
    
    # Don't exit with error - service account is optional
    return 0


if __name__ == "__main__":
    sys.exit(main())
