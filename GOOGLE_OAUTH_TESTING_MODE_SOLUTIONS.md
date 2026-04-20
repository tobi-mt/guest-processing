# Solutions for Google OAuth in Testing Mode

## The Problem

When your Google Cloud project is stuck in **Testing mode**:
- ✅ Refresh tokens expire after **7 days**
- ✅ Limited to **100 test users**
- ✅ Need to constantly regenerate tokens manually
- ✅ Google won't approve production status for internal/personal apps

## Solution Options (Ranked by Best Practice)

---

## 🏆 **Solution 1: Use Google Service Account (RECOMMENDED)**

### What is it?
Service Accounts are special Google accounts for server-to-server authentication that **don't require user interaction** and **never expire**.

### ✅ Advantages
- No token expiration issues
- No user consent required
- Perfect for server/backend applications
- No "Testing vs Production" mode concerns

### ⚠️ Requirements
- You must own/control the Google Calendar
- Need domain-wide delegation if using Google Workspace

### Implementation Steps

#### Step 1: Create a Service Account

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Select your project
3. Navigate to **IAM & Admin** → **Service Accounts**
4. Click **Create Service Account**
   - Name: `guest-processing-calendar`
   - Description: `Service account for calendar sync`
5. Click **Create and Continue**
6. Skip role assignment (not needed for Calendar API)
7. Click **Done**

#### Step 2: Create Service Account Key

1. Click on your new service account
2. Go to **Keys** tab
3. Click **Add Key** → **Create new key**
4. Select **JSON** format
5. Download the JSON file (keep it secure!)

#### Step 3: Share Calendar with Service Account

1. Open Google Calendar
2. Find your calendar in the left sidebar
3. Click the three dots → **Settings and sharing**
4. Scroll to **Share with specific people**
5. Click **Add people**
6. Enter the service account email (looks like `guest-processing-calendar@your-project.iam.gserviceaccount.com`)
7. Set permission to **Make changes to events**
8. Click **Send**

#### Step 4: Update Your Code

Create a new file `google_service_account_sync.py`:

```python
"""Google Calendar sync using Service Account authentication."""

from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
import jwt


class ServiceAccountCalendarClient:
    """Google Calendar client using Service Account authentication."""

    TOKEN_URL = "https://oauth2.googleapis.com/token"
    EVENTS_URL_TEMPLATE = "https://www.googleapis.com/calendar/v3/calendars/{calendar_id}/events"
    SCOPES = ["https://www.googleapis.com/auth/calendar"]
    
    def __init__(self, service_account_file: str | Path, calendar_id: str):
        """
        Initialize with service account credentials.
        
        Args:
            service_account_file: Path to the JSON key file downloaded from Google Cloud
            calendar_id: The Google Calendar ID (usually an email address)
        """
        self.calendar_id = calendar_id
        
        # Load service account credentials
        with open(service_account_file, 'r') as f:
            self.credentials = json.load(f)
        
        self._access_token: Optional[str] = None
        self._token_expiry: Optional[datetime] = None
    
    def _create_jwt(self) -> str:
        """Create a signed JWT for service account authentication."""
        now = int(time.time())
        
        payload = {
            "iss": self.credentials["client_email"],
            "sub": self.credentials["client_email"],
            "aud": self.TOKEN_URL,
            "iat": now,
            "exp": now + 3600,  # 1 hour
            "scope": " ".join(self.SCOPES),
        }
        
        # Sign with private key
        private_key = serialization.load_pem_private_key(
            self.credentials["private_key"].encode(),
            password=None
        )
        
        token = jwt.encode(
            payload,
            private_key,
            algorithm="RS256",
            headers={"kid": self.credentials.get("private_key_id")}
        )
        
        return token
    
    def _get_access_token(self) -> str:
        """Get a valid access token, refreshing if necessary."""
        # Return cached token if still valid
        if self._access_token and self._token_expiry:
            if datetime.now(timezone.utc) < self._token_expiry - timedelta(minutes=5):
                return self._access_token
        
        # Create signed JWT
        signed_jwt = self._create_jwt()
        
        # Exchange JWT for access token
        response = requests.post(
            self.TOKEN_URL,
            data={
                "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                "assertion": signed_jwt,
            },
            timeout=20,
        )
        
        if not response.ok:
            raise Exception(f"Failed to get access token: {response.text}")
        
        data = response.json()
        self._access_token = data["access_token"]
        self._token_expiry = datetime.now(timezone.utc) + timedelta(seconds=data["expires_in"])
        
        return self._access_token
    
    def list_upcoming_events(
        self,
        days_ahead: int = 30,
        reference: Optional[datetime] = None,
        query: str = "",
    ) -> List[Dict[str, Any]]:
        """Fetch upcoming events from the calendar."""
        access_token = self._get_access_token()
        
        reference = reference or datetime.now(timezone.utc)
        time_min = reference.isoformat()
        time_max = (reference + timedelta(days=days_ahead)).isoformat()
        
        params = {
            "singleEvents": "true",
            "orderBy": "startTime",
            "timeMin": time_min,
            "timeMax": time_max,
            "maxResults": 250,
        }
        
        if query.strip():
            params["q"] = query.strip()
        
        url = self.EVENTS_URL_TEMPLATE.format(
            calendar_id=requests.utils.quote(self.calendar_id, safe="")
        )
        
        response = requests.get(
            url,
            headers={"Authorization": f"Bearer {access_token}"},
            params=params,
            timeout=20,
        )
        
        if not response.ok:
            raise Exception(f"Failed to fetch events: {response.text}")
        
        return response.json().get("items", [])
```

#### Step 5: Update Environment Variables

Instead of using refresh tokens, use the service account:

```bash
# Old approach (remove these)
# MIRROR_TALK_GOOGLE_CLIENT_ID=...
# MIRROR_TALK_GOOGLE_CLIENT_SECRET=...
# MIRROR_TALK_GOOGLE_REFRESH_TOKEN=...

# New approach
export MIRROR_TALK_GOOGLE_SERVICE_ACCOUNT_FILE="/path/to/service-account-key.json"
export MIRROR_TALK_GOOGLE_CALENDAR_ID="your-calendar-id@group.calendar.google.com"
```

#### Step 6: Install Dependencies

```bash
pip install pyjwt cryptography
```

---

## 🔧 **Solution 2: Desktop Application OAuth Flow**

If you must use user OAuth (not service account), use the **Desktop App** flow which gives longer-lived refresh tokens even in Testing mode.

### Implementation

Create `google_oauth_helper.py`:

```python
"""Helper to generate Google OAuth refresh token using local server."""

from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
import pickle
import os

SCOPES = ['https://www.googleapis.com/auth/calendar']

def get_refresh_token():
    """
    Run this once to get a refresh token that lasts longer.
    
    Save your OAuth client credentials as 'credentials.json' in the same directory.
    Download from: Google Cloud Console → APIs & Services → Credentials
    """
    creds = None
    
    # Check if we have saved credentials
    if os.path.exists('token.pickle'):
        with open('token.pickle', 'rb') as token:
            creds = pickle.load(token)
    
    # If no valid credentials, get new ones
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                'credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        
        # Save credentials for future use
        with open('token.pickle', 'wb') as token:
            pickle.dump(creds, token)
    
    print(f"✅ Refresh Token: {creds.refresh_token}")
    print(f"✅ Valid until: {creds.expiry}")
    return creds.refresh_token

if __name__ == '__main__':
    get_refresh_token()
```

### Usage

```bash
# Install dependencies
pip install google-auth-oauthlib google-auth

# Download OAuth client credentials from Google Cloud Console
# Save as credentials.json

# Run to get refresh token
python google_oauth_helper.py

# Copy the refresh token to your environment variables
```

### ⚠️ Limitations
- Still expires after 7 days in Testing mode
- Just makes the process easier to regenerate

---

## 🔄 **Solution 3: Automated Token Refresh Script**

If stuck with Testing mode, automate the token refresh process.

Create `auto_refresh_token.py`:

```python
"""Automatically refresh Google OAuth token when it expires."""

import os
import time
from datetime import datetime, timedelta
from pathlib import Path
import subprocess

def check_and_refresh_token():
    """Check if token needs refresh and regenerate if needed."""
    
    # Store last refresh date in a file
    refresh_file = Path.home() / ".google_token_refresh_date"
    
    if refresh_file.exists():
        last_refresh = datetime.fromisoformat(refresh_file.read_text().strip())
        days_since_refresh = (datetime.now() - last_refresh).days
        
        if days_since_refresh < 6:  # Refresh before 7-day expiry
            print(f"✅ Token still valid ({days_since_refresh} days old)")
            return
    
    print("⚠️  Token expiring soon or expired. Please refresh:")
    print("1. Visit: https://developers.google.com/oauthplayground/")
    print("2. Configure to use your OAuth credentials")
    print("3. Authorize Calendar API v3")
    print("4. Exchange authorization code for tokens")
    print("5. Copy the refresh_token")
    print()
    
    new_token = input("Paste new refresh token: ").strip()
    
    if new_token:
        # Update environment variable (you'll need to make this persistent)
        os.environ['MIRROR_TALK_GOOGLE_REFRESH_TOKEN'] = new_token
        
        # Save refresh date
        refresh_file.write_text(datetime.now().isoformat())
        
        print("✅ Token updated!")
    else:
        print("❌ No token provided")

if __name__ == '__main__':
    check_and_refresh_token()
```

Add to crontab to run weekly:

```bash
# Run every Sunday at 9 AM
0 9 * * 0 /usr/bin/python3 /path/to/auto_refresh_token.py
```

---

## 🎯 **Solution 4: OAuth Playground Method (Current Improvement)**

Improve your current manual process with better documentation.

### Quick Refresh Guide

1. **Go to OAuth Playground**: https://developers.google.com/oauthplayground/

2. **Configure Your Credentials**:
   - Click the gear icon (⚙️) in top right
   - Check "Use your own OAuth credentials"
   - Enter your Client ID and Client Secret
   - Close settings

3. **Select Scopes**:
   - Scroll to "Calendar API v3"
   - Select: `https://www.googleapis.com/auth/calendar`
   - Click "Authorize APIs"

4. **Authorize**:
   - Sign in with your Google account
   - Click "Allow"

5. **Get Tokens**:
   - Click "Exchange authorization code for tokens"
   - Copy the **refresh_token** value

6. **Update Environment**:
   ```bash
   export MIRROR_TALK_GOOGLE_REFRESH_TOKEN="your_new_refresh_token"
   ```

7. **Set Reminder**:
   - Add to calendar: "Refresh Google Calendar Token" (repeat every 6 days)

---

## 📊 **Comparison Table**

| Solution | Expires? | Complexity | Best For |
|----------|----------|------------|----------|
| **Service Account** | ❌ Never | Medium | Production apps, server-to-server |
| **Desktop OAuth** | ✅ 7 days | Low | Personal use, easier setup |
| **Auto-Refresh Script** | ✅ 7 days | Low | Temporary workaround |
| **Manual (OAuth Playground)** | ✅ 7 days | Very Low | Current method (improved) |

---

## 🎯 **Recommended Action Plan**

### For Production/Long-term Use:
1. ✅ **Switch to Service Account** (Solution 1)
   - No expiration issues
   - Most reliable for production
   - Requires calendar sharing

### For Personal/Short-term Use:
1. ✅ **Use Desktop OAuth Flow** (Solution 2)
   - Easier setup than service account
   - Still requires weekly refresh

### If You Can't Switch:
1. ✅ **Automate the refresh process** (Solution 3)
   - Set up weekly reminder
   - Script the token update
   - Document the process

---

## 🔐 **Security Best Practices**

1. **Never commit credentials to git**:
   ```bash
   # Add to .gitignore
   credentials.json
   service-account-key.json
   token.pickle
   .env
   ```

2. **Use environment variables**:
   ```bash
   # Store in .env file (not committed)
   MIRROR_TALK_GOOGLE_SERVICE_ACCOUNT_FILE=/secure/path/key.json
   ```

3. **Restrict service account permissions**:
   - Only grant "Make changes to events" on specific calendar
   - Don't give broader Google Workspace access

4. **Rotate keys periodically**:
   - Generate new service account keys every 90 days
   - Delete old keys after migration

---

## 📚 **Additional Resources**

- [Google Service Accounts](https://cloud.google.com/iam/docs/service-accounts)
- [Calendar API Python Quickstart](https://developers.google.com/calendar/api/quickstart/python)
- [OAuth 2.0 for Testing](https://developers.google.com/identity/protocols/oauth2#testing)
- [Service Account Authorization](https://developers.google.com/identity/protocols/oauth2/service-account)

---

## 🆘 **Need Help?**

If you encounter issues:

1. **Check API is enabled**: 
   - Google Cloud Console → APIs & Services → Library
   - Search "Google Calendar API"
   - Ensure it's enabled

2. **Verify permissions**:
   - Service account has calendar access
   - Scopes match what you're requesting

3. **Check quotas**:
   - Cloud Console → APIs & Services → Dashboard
   - Check Calendar API quota usage

4. **Test with OAuth Playground**:
   - Verify credentials work manually first
   - Then implement in code
