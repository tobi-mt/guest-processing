# Railway Deployment Guide - Google Service Account

This guide shows you how to deploy your guest processing application to Railway with the Google Service Account configuration (no token expiration issues!).

---

## 🎯 Overview

Railway deployment with service account means:
- ✅ **No token expiration** - Service accounts never expire
- ✅ **No manual refresh** - Fully automated in production
- ✅ **Zero maintenance** - Set it up once and forget about it
- ✅ **Secure** - Service account key stored as Railway secret

---

## 📋 Prerequisites

- [ ] Railway account (free tier works)
- [ ] Google Service Account created and JSON key downloaded
- [ ] Calendar shared with service account email
- [ ] Railway CLI installed (optional but recommended)

---

## 🚀 Deployment Steps

### Method 1: Railway Dashboard (Recommended)

#### Step 1: Create New Project

1. Go to [Railway Dashboard](https://railway.app/dashboard)
2. Click **"New Project"**
3. Select **"Deploy from GitHub repo"** (or empty project)
4. Connect your repository

#### Step 2: Add Service Account as Secret

Railway doesn't support file uploads directly, so we'll encode the service account JSON as a base64 string:

**On your local machine:**

```bash
# Encode the service account file
base64 -i /Users/tobi/Documents/PODCAST/mt-wp-forms-1732226728680-bc52eed2795a.json > service-account-base64.txt

# Copy the output (it's one long string)
cat service-account-base64.txt
```

**In Railway Dashboard:**

1. Go to your project → **Variables** tab
2. Click **"New Variable"**
3. Add these variables:

```bash
# Service Account Configuration (RECOMMENDED - no token expiration)
MIRROR_TALK_GOOGLE_SERVICE_ACCOUNT_BASE64=<paste the base64 string from above>
MIRROR_TALK_GOOGLE_CALENDAR_ID=podcast.mirrortalk@gmail.com

# Optional: Fallback OAuth (if service account fails)
# MIRROR_TALK_GOOGLE_CLIENT_ID=your-client-id
# MIRROR_TALK_GOOGLE_CLIENT_SECRET=your-client-secret
# MIRROR_TALK_GOOGLE_REFRESH_TOKEN=your-refresh-token

# Other application variables
MIRROR_TALK_GOOGLE_CALENDAR_TIMEZONE=Europe/Berlin
```

4. Click **"Add"** for each variable

#### Step 3: Update Your Existing Startup Command

Your current Railway start command:

```bash
python -m pip install --upgrade pip && python -m pip install -e . && PYTHONPATH=src python -m guest_database_manager.cli web --host 0.0.0.0 --port $PORT --db /app/data/guest_database.db --no-browser
```

**Update it to include service account decoding:**

```bash
python -m pip install --upgrade pip && python -m pip install -e . && python decode_service_account.py && PYTHONPATH=src python -m guest_database_manager.cli web --host 0.0.0.0 --port $PORT --db /app/data/guest_database.db --no-browser
```

The only change is adding `python decode_service_account.py &&` before your application starts. This will:
- Decode the base64-encoded service account
- Save it to `/tmp/google-service-account.json`
- Set the environment variable for your app to use

#### Step 4: Add Decode Script

Create a file `decode_service_account.py` in your project root:

```python
#!/usr/bin/env python3
"""Decode service account from base64 environment variable."""

import base64
import json
import os
from pathlib import Path

def decode_service_account():
    """Decode service account from base64 env var and save to file."""
    base64_content = os.environ.get("MIRROR_TALK_GOOGLE_SERVICE_ACCOUNT_BASE64", "").strip()
    
    if not base64_content:
        print("⚠️  MIRROR_TALK_GOOGLE_SERVICE_ACCOUNT_BASE64 not set, skipping service account setup")
        return
    
    try:
        # Decode base64
        json_content = base64.b64decode(base64_content).decode('utf-8')
        
        # Validate it's valid JSON
        json.loads(json_content)
        
        # Save to file
        service_account_path = Path("/tmp/service-account.json")
        service_account_path.write_text(json_content)
        service_account_path.chmod(0o600)
        
        # Set environment variable to point to the file
        os.environ["MIRROR_TALK_GOOGLE_SERVICE_ACCOUNT_FILE"] = str(service_account_path)
        
        print(f"✅ Service account decoded and saved to {service_account_path}")
        
    except Exception as e:
        print(f"❌ Failed to decode service account: {e}")

if __name__ == "__main__":
    decode_service_account()
```

#### Step 5: Deploy

Railway will automatically deploy when you push to your connected branch.

---

### Method 2: Railway CLI

```bash
# Install Railway CLI
npm i -g @railway/cli

# Login
railway login

# Link to your project (or create new)
railway link

# Set environment variables
railway variables set MIRROR_TALK_GOOGLE_SERVICE_ACCOUNT_BASE64="$(base64 -i /Users/tobi/Documents/PODCAST/mt-wp-forms-1732226728680-bc52eed2795a.json)"
railway variables set MIRROR_TALK_GOOGLE_CALENDAR_ID="podcast.mirrortalk@gmail.com"
railway variables set MIRROR_TALK_GOOGLE_CALENDAR_TIMEZONE="Europe/Berlin"

# Deploy
railway up
```

---

## 🔧 Alternative: Direct File Upload (Simpler)

If Railway supports volume mounts or you use Docker:

### Dockerfile Approach

Create `Dockerfile`:

```dockerfile
FROM python:3.12-slim

WORKDIR /app

# Copy application files
COPY . .

# Install dependencies
RUN pip install --no-cache-dir -e .

# Copy service account (build-time - not recommended for secrets)
# COPY service-account.json /app/secrets/service-account.json

# Or decode at runtime (recommended)
COPY decode_service_account.py .

# Expose port
EXPOSE 8501

# Decode service account and run app
CMD python decode_service_account.py && \
    PYTHONPATH=src python -m guest_database_manager.cli web \
    --host 0.0.0.0 \
    --port $PORT \
    --db /app/data/guest_database.db \
    --no-browser
```

Then in Railway:
1. It will auto-detect the Dockerfile
2. Set environment variables as above
3. Deploy

---

## ✅ Verify Deployment

After deployment, check the logs:

```bash
railway logs
```

You should see:
```
✅ Service account decoded and saved to /tmp/service-account.json
✅ Streamlit app starting...
✅ Calendar client created successfully
```

Test calendar features in your deployed app to confirm it works.

---

## 🔒 Security Best Practices

### ✅ Do:
- Use base64 encoding for service account in environment variables
- Set file permissions to 600 after decoding
- Use Railway's encrypted environment variables
- Rotate service account keys every 90 days
- Use separate service accounts for dev/staging/production

### ❌ Don't:
- Commit service account JSON to git
- Share base64 string publicly
- Use same service account across multiple projects
- Store service account in public environment variables

---

## 🐛 Troubleshooting

### Error: "Service account file not found"

**Solution:** Check that `decode_service_account.py` ran successfully:
```bash
railway logs | grep "Service account"
```

### Error: "Invalid service account JSON"

**Solution:** Verify base64 encoding is correct:
```bash
# Test locally
echo "$MIRROR_TALK_GOOGLE_SERVICE_ACCOUNT_BASE64" | base64 -d | jq .
```

### Error: "Failed to fetch events"

**Solution:**
1. ✅ Calendar shared with service account email?
2. ✅ Calendar API enabled in Google Cloud Console?
3. ✅ Service account has correct permissions?

### Error: "Module not found: jwt"

**Solution:** Ensure `pyjwt` is in dependencies:
```toml
# pyproject.toml
dependencies = [
  ...
  "pyjwt>=2.8.0",
]
```

---

## 📊 Environment Variables Reference

| Variable | Required | Example | Purpose |
|----------|----------|---------|---------|
| `MIRROR_TALK_GOOGLE_SERVICE_ACCOUNT_BASE64` | ✅ Yes | `ewogICJ0eXB...` | Base64-encoded service account JSON |
| `MIRROR_TALK_GOOGLE_CALENDAR_ID` | ✅ Yes | `podcast.mirrortalk@gmail.com` | Your Google Calendar ID |
| `MIRROR_TALK_GOOGLE_CALENDAR_TIMEZONE` | ❌ No | `Europe/Berlin` | Default timezone for events |
| `MIRROR_TALK_GOOGLE_CLIENT_ID` | ❌ No | `123...apps.googleusercontent.com` | OAuth fallback (optional) |
| `MIRROR_TALK_GOOGLE_CLIENT_SECRET` | ❌ No | `GOCSPX-...` | OAuth fallback (optional) |
| `MIRROR_TALK_GOOGLE_REFRESH_TOKEN` | ❌ No | `1//04...` | OAuth fallback (optional) |

---

## 🔄 Migration from OAuth to Service Account

If you're currently using OAuth refresh tokens in Railway:

1. **Test Locally First**
   ```bash
   # Make sure service account works locally
   python test_service_account_calendar.py
   ```

2. **Add Service Account Variables**
   - Add `MIRROR_TALK_GOOGLE_SERVICE_ACCOUNT_BASE64`
   - Keep OAuth variables temporarily

3. **Deploy and Test**
   - App will try service account first
   - Falls back to OAuth if service account fails

4. **Remove OAuth Variables** (after confirming service account works)
   - Remove `MIRROR_TALK_GOOGLE_CLIENT_ID`
   - Remove `MIRROR_TALK_GOOGLE_CLIENT_SECRET`
   - Remove `MIRROR_TALK_GOOGLE_REFRESH_TOKEN`

---

## 🎉 Benefits in Production

| Aspect | OAuth Refresh Token | Service Account |
|--------|-------------------|----------------|
| **Token Expiration** | 7 days (Testing mode) | Never ❌ |
| **Manual Refresh** | Every week 😩 | Never needed 🎉 |
| **Production Downtime** | Yes, when token expires | No |
| **Deployment Complexity** | Low | Medium (one-time setup) |
| **Reliability** | ⭐⭐ | ⭐⭐⭐⭐⭐ |
| **Maintenance** | High | Zero |

---

## 📞 Need Help?

1. **Check Railway Logs**: `railway logs`
2. **Test Locally First**: Ensure service account works locally before deploying
3. **Verify Variables**: Double-check all environment variables are set correctly
4. **Check Permissions**: Ensure calendar is shared with service account

---

## 🚀 Quick Deploy Checklist

- [ ] Service account created in Google Cloud Console
- [ ] Calendar shared with service account email
- [ ] Service account JSON encoded to base64
- [ ] Base64 string added to Railway variables
- [ ] Calendar ID added to Railway variables
- [ ] `decode_service_account.py` added to repository
- [ ] Start command updated to decode service account first
- [ ] Deployment successful
- [ ] Calendar features tested in production
- [ ] OAuth variables removed (after confirming service account works)

**Once complete, you'll never have to worry about token expiration in production! 🎉**
