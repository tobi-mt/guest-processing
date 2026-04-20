# Google Service Account Setup Guide

## Quick Setup (Step-by-Step)

This guide will help you switch from the problematic refresh token approach to a reliable service account that **never expires**.

---

## 🎯 What You'll Achieve

- ✅ **No more token expiration** - Service accounts don't expire every 7 days
- ✅ **No manual token refresh** - Fully automated authentication
- ✅ **Production-ready** - Works regardless of Testing/Production mode
- ✅ **Same functionality** - All calendar features work the same way

---

## 📋 Prerequisites

- [ ] Access to Google Cloud Console (same project you're currently using)
- [ ] Owner/Admin access to your Google Calendar
- [ ] 10 minutes of setup time

---

## 🚀 Setup Steps

### Step 1: Create Service Account (5 minutes)

1. **Go to Google Cloud Console**
   - Navigate to: https://console.cloud.google.com/
   - Select your project (the one with your OAuth credentials)

2. **Navigate to Service Accounts**
   - Click: **IAM & Admin** → **Service Accounts**
   - Or direct link: https://console.cloud.google.com/iam-admin/serviceaccounts

3. **Create New Service Account**
   - Click **"+ CREATE SERVICE ACCOUNT"** button at top
   - Fill in details:
     - **Service account name**: `mirror-talk-calendar`
     - **Service account ID**: `mirror-talk-calendar` (auto-filled)
     - **Description**: `Service account for guest processing calendar sync`
   - Click **"CREATE AND CONTINUE"**

4. **Skip Role Assignment**
   - On "Grant this service account access to project" screen
   - Click **"CONTINUE"** (don't select any roles)

5. **Skip User Access**
   - On "Grant users access to this service account" screen
   - Click **"DONE"**

6. **Note the Service Account Email**
   - You should see your new service account listed
   - Email format: `mirror-talk-calendar@YOUR-PROJECT-ID.iam.gserviceaccount.com`
   - **Copy this email** - you'll need it in Step 2

### Step 2: Create and Download Key (2 minutes)

1. **Find Your Service Account**
   - In the Service Accounts list, find `mirror-talk-calendar`
   - Click on the email address to open details

2. **Create Key**
   - Click the **"KEYS"** tab
   - Click **"ADD KEY"** → **"Create new key"**
   - Select **"JSON"** format
   - Click **"CREATE"**

3. **Save the Key File**
   - A JSON file will download automatically
   - **Rename it**: `mirror-talk-service-account.json`
   - **Move to secure location**: 
     - Recommended: `~/.google/` (create this folder if needed)
     - Full path example: `/Users/yourusername/.google/mirror-talk-service-account.json`
   - ⚠️ **KEEP THIS FILE SECRET** - It's like a password!

4. **Set Permissions** (macOS/Linux)
   ```bash
   mkdir -p ~/.google
   mv ~/Downloads/mirror-talk-service-account.json ~/.google/
   chmod 600 ~/.google/mirror-talk-service-account.json
   ```

### Step 3: Share Calendar with Service Account (2 minutes)

1. **Open Google Calendar**
   - Go to: https://calendar.google.com/

2. **Find Your Calendar**
   - In the left sidebar, find the calendar you use for podcast interviews
   - Hover over it and click the three dots (⋮)
   - Click **"Settings and sharing"**

3. **Share with Service Account**
   - Scroll to section: **"Share with specific people"**
   - Click **"+ Add people"**
   - **Paste the service account email** from Step 1
     - Example: `mirror-talk-calendar@your-project-123456.iam.gserviceaccount.com`
   - Set permission: **"Make changes to events"**
   - **Uncheck** "Send email notification" (service accounts don't read email)
   - Click **"Send"**

4. **Verify**
   - You should see the service account listed under "Share with specific people"
   - Permission should show: "Make changes to events"

### Step 4: Enable Calendar API (1 minute)

1. **Go to API Library**
   - Navigate to: https://console.cloud.google.com/apis/library

2. **Search for Calendar API**
   - In search box, type: `Google Calendar API`
   - Click on **"Google Calendar API"**

3. **Enable the API**
   - If you see **"ENABLE"** button, click it
   - If you see **"MANAGE"** or **"API enabled"**, you're all set!

### Step 5: Configure Your Application (3 minutes)

1. **Set Environment Variables**

   Create or edit your `.env` file or shell profile:

   ```bash
   # Remove old OAuth credentials (optional - keep for now during testing)
   # MIRROR_TALK_GOOGLE_CLIENT_ID=...
   # MIRROR_TALK_GOOGLE_CLIENT_SECRET=...
   # MIRROR_TALK_GOOGLE_REFRESH_TOKEN=...

   # Add new service account credentials
   export MIRROR_TALK_GOOGLE_SERVICE_ACCOUNT_FILE="$HOME/.google/mirror-talk-service-account.json"
   export MIRROR_TALK_GOOGLE_CALENDAR_ID="your-calendar@gmail.com"  # Replace with your calendar ID
   ```

   **Finding Your Calendar ID:**
   - Open Google Calendar
   - Click settings (⚙️) → Settings
   - Select your calendar from the left sidebar
   - Scroll to **"Integrate calendar"**
   - Copy the **"Calendar ID"** (usually your email address)

2. **Apply Environment Variables**

   ```bash
   # If you edited .env
   source .env

   # Or if you edited .bashrc/.zshrc
   source ~/.bashrc  # or source ~/.zshrc
   ```

3. **Install Required Python Package**

   ```bash
   pip install pyjwt
   ```

### Step 6: Test the Setup (2 minutes)

Run the test script:

```bash
cd /Users/tobi/PycharmProjects/pythonProject/guest-processing
python test_service_account_calendar.py
```

**Expected Output:**
```
==================================================
  Google Service Account Calendar Test
==================================================

✅ Service Account File: /Users/yourusername/.google/mirror-talk-service-account.json
✅ Calendar ID: your-calendar@gmail.com
✅ Service account file exists

==================================================
  Creating Calendar Client
==================================================

✅ Calendar client created successfully
   Service Account Email: mirror-talk-calendar@your-project-123456.iam.gserviceaccount.com

==================================================
  Fetching Calendar Events
==================================================

✅ Successfully fetched X upcoming event(s)

Upcoming events:
  1. Interview with Guest Name
     Start: 2026-04-25T14:00:00+02:00
  ...

==================================================
  Test Complete
==================================================

✅ All tests passed!

Your service account calendar integration is working correctly.
You can now use this in your application without worrying about token expiration!
```

---

## ✅ Troubleshooting

### Error: "Service account file not found"

**Solution:**
- Check the path in `MIRROR_TALK_GOOGLE_SERVICE_ACCOUNT_FILE`
- Verify the file exists: `ls -la ~/.google/mirror-talk-service-account.json`
- Use absolute path, not relative

### Error: "Calendar not shared with service account"

**Solution:**
- Double-check you shared the calendar with the service account email
- Wait 1-2 minutes for permissions to propagate
- Verify the calendar ID is correct

### Error: "Calendar API not enabled"

**Solution:**
- Go to: https://console.cloud.google.com/apis/library/calendar-json.googleapis.com
- Click "ENABLE"
- Wait 1 minute and try again

### Error: "Invalid JSON in service account file"

**Solution:**
- Re-download the service account key from Google Cloud Console
- Make sure you selected JSON format (not P12)
- Check the file isn't corrupted: `cat ~/.google/mirror-talk-service-account.json | jq .`

---

## 🔄 Using in Your Application

### Method 1: Environment Variables (Recommended)

```python
from guest_database_manager.google_service_account_calendar import create_client_from_env

# Automatically uses environment variables
client = create_client_from_env()

if client:
    events = client.list_upcoming_events(days_ahead=30)
    print(f"Found {len(events)} events")
else:
    print("Service account not configured")
```

### Method 2: Direct Instantiation

```python
from guest_database_manager.google_service_account_calendar import GoogleServiceAccountCalendarClient

client = GoogleServiceAccountCalendarClient(
    service_account_file="/path/to/service-account.json",
    calendar_id="your-calendar@gmail.com",
)

events = client.list_upcoming_events(days_ahead=30)
```

---

## 🎉 Next Steps

1. ✅ **Test in Development**
   - Run your application with the service account
   - Verify all calendar features work

2. ✅ **Update Production**
   - Add environment variables to your production environment
   - Deploy the updated code

3. ✅ **Remove Old Credentials** (after confirming everything works)
   - Remove `MIRROR_TALK_GOOGLE_REFRESH_TOKEN`
   - Keep `MIRROR_TALK_GOOGLE_CLIENT_ID/SECRET` if using OAuth for other features

4. ✅ **Document for Team**
   - Share service account email with team
   - Document where the key file is stored
   - Add to your deployment documentation

---

## 🔐 Security Best Practices

### Do:
- ✅ Store key file in secure location (`~/.google/`)
- ✅ Set restrictive permissions: `chmod 600`
- ✅ Add key file to `.gitignore`
- ✅ Use environment variables, not hardcoded paths
- ✅ Rotate keys every 90 days (create new key, delete old)

### Don't:
- ❌ Commit key file to git
- ❌ Share key file in Slack/email
- ❌ Store in public/shared folders
- ❌ Use the same key across multiple projects
- ❌ Share service account email publicly

---

## 📚 Additional Resources

- **Service Account Documentation**: https://cloud.google.com/iam/docs/service-accounts
- **Calendar API Reference**: https://developers.google.com/calendar/api/v3/reference
- **Your Code**: `src/guest_database_manager/google_service_account_calendar.py`
- **Full Solutions Guide**: `GOOGLE_OAUTH_TESTING_MODE_SOLUTIONS.md`

---

## 💡 Benefits Summary

| Aspect | Refresh Token (Old) | Service Account (New) |
|--------|-------------------|---------------------|
| **Expiration** | 7 days (Testing mode) | Never ❌ |
| **Manual Refresh** | Every week 😩 | Never needed 🎉 |
| **User Interaction** | Required | Not required |
| **Production Ready** | Blocked by Google | Yes ✅ |
| **Reliability** | Low | High |
| **Setup Complexity** | Low | Medium |
| **Maintenance** | High | None |

---

## ❓ Questions?

If you run into issues:

1. **Re-run the test script** with verbose output
2. **Check all steps** were completed exactly
3. **Wait 2-3 minutes** after making changes (propagation delay)
4. **Verify permissions** in Google Calendar settings
5. **Check API is enabled** in Cloud Console

For detailed troubleshooting, see: `GOOGLE_OAUTH_TESTING_MODE_SOLUTIONS.md`

---

**Ready to say goodbye to token expiration issues?** 🎉

Follow the steps above and you'll never have to manually refresh tokens again!
