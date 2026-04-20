# Google OAuth Testing Mode - Quick Reference

## 🚨 The Problem

Your Google OAuth app is stuck in **Testing mode**, causing:
- Refresh tokens expire every **7 days**
- Constant manual token regeneration required
- Limited to 100 test users
- Google won't approve production status for internal/personal apps

---

## ✅ Best Solution: Service Account

**Setup Time:** 10 minutes  
**Token Expiration:** Never ❌  
**Manual Refresh:** Never needed  

### Quick Start

```bash
# 1. Run the setup wizard
python setup_service_account.py

# 2. Test the configuration
python test_service_account_calendar.py

# 3. Done! No more token expiration issues
```

### Manual Setup

1. **Create Service Account** (Google Cloud Console)
   - Go to: IAM & Admin → Service Accounts → Create
   - Download JSON key file

2. **Share Calendar**
   - Share your calendar with service account email
   - Grant "Make changes to events" permission

3. **Set Environment Variables**
   ```bash
   export MIRROR_TALK_GOOGLE_SERVICE_ACCOUNT_FILE="~/.google/service-account.json"
   export MIRROR_TALK_GOOGLE_CALENDAR_ID="your-calendar@gmail.com"
   ```

4. **Install Dependencies**
   ```bash
   pip install pyjwt
   ```

### Usage in Code

```python
from guest_database_manager.google_service_account_calendar import create_client_from_env

# Auto-detects environment variables
client = create_client_from_env()

if client:
    events = client.list_upcoming_events(days_ahead=30)
    # No token expiration, no manual refresh needed!
```

---

## 🔄 Alternative: OAuth Playground (Current Method)

If you can't use service account, improve your current workflow:

### Quick Token Refresh

1. Go to: https://developers.google.com/oauthplayground/
2. Click ⚙️ → Use your own OAuth credentials
3. Enter your Client ID and Secret
4. Select Calendar API v3 scopes
5. Authorize and exchange for tokens
6. Copy refresh_token
7. Update: `export MIRROR_TALK_GOOGLE_REFRESH_TOKEN="new_token"`

### Automate Reminder

```bash
# Add to calendar - repeat every 6 days
"Refresh Google Calendar Token"
```

---

## 📊 Solution Comparison

| Aspect | Service Account ⭐ | OAuth Playground | Desktop OAuth |
|--------|------------------|-----------------|---------------|
| **Expires?** | ❌ Never | ✅ 7 days | ✅ 7 days |
| **Manual Work?** | ❌ None | ✅ Weekly | ✅ Weekly |
| **Setup Time** | 10 min | 2 min | 5 min |
| **Reliability** | ⭐⭐⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐ |
| **Production Ready?** | ✅ Yes | ❌ No | ❌ No |

---

## 🆘 Troubleshooting

### Service Account: "Failed to fetch events"

1. ✅ Calendar shared with service account email?
2. ✅ Calendar API enabled in Cloud Console?
3. ✅ Wait 1-2 minutes for permissions to propagate

### OAuth: "Refresh token expired"

- Tokens expire after 7 days in Testing mode
- Must manually refresh using OAuth Playground
- Consider switching to service account

### Both: "API not enabled"

- Go to: https://console.cloud.google.com/apis/library/calendar-json.googleapis.com
- Click "ENABLE"

---

## 📁 Files Created

| File | Purpose |
|------|---------|
| `SERVICE_ACCOUNT_SETUP.md` | Step-by-step local setup guide |
| `RAILWAY_DEPLOYMENT.md` | Complete Railway deployment guide |
| `RAILWAY_START_COMMAND.md` | Quick Railway start command reference |
| `GOOGLE_OAUTH_TESTING_MODE_SOLUTIONS.md` | All solutions reference |
| `setup_service_account.py` | Interactive setup wizard |
| `test_service_account_calendar.py` | Test your configuration |
| `decode_service_account.py` | Railway/cloud deployment helper |
| `deploy_to_railway.sh` | Automated Railway deployment script |
| `src/.../google_service_account_calendar.py` | Service account client code |

---

## 🎯 Recommended Action

1. ✅ **Read**: `SERVICE_ACCOUNT_SETUP.md` ← DONE
2. ✅ **Run**: `python setup_service_account.py` ← DONE
3. ✅ **Test**: `python test_service_account_calendar.py` ← DONE (17 events found!)
4. ⬜ **Deploy to Railway**: 
   - Quick: See `RAILWAY_START_COMMAND.md` (copy-paste start command)
   - Detailed: See `RAILWAY_DEPLOYMENT.md` (full guide)
   - Automated: Run `./deploy_to_railway.sh`
5. ⬜ **Celebrate**: No more weekly token refresh! 🎉

---

## 💡 Why Service Account is Better

| Problem | Refresh Token | Service Account |
|---------|--------------|----------------|
| Token expires every 7 days | 😩 Yes | 🎉 Never |
| Manual intervention needed | 😩 Weekly | 🎉 Never |
| Breaks during vacation | 😩 Yes | 🎉 No |
| Production deployment | 😩 Risky | 🎉 Reliable |
| Scalable | 😩 No | 🎉 Yes |

---

## 🔐 Security Checklist

- [ ] Service account key stored securely (`~/.google/`)
- [ ] File permissions restricted: `chmod 600`
- [ ] Key file added to `.gitignore`
- [ ] Using environment variables (not hardcoded paths)
- [ ] Calendar shared with minimal permissions
- [ ] Rotate keys every 90 days

---

## 📞 Need Help?

**Local Setup:**
1. **Read**: `SERVICE_ACCOUNT_SETUP.md` for detailed steps
2. **Read**: `GOOGLE_OAUTH_TESTING_MODE_SOLUTIONS.md` for all options
3. **Run**: `python setup_service_account.py` for interactive setup
4. **Test**: `python test_service_account_calendar.py` to verify

**Railway Deployment:**
1. **Quick Reference**: `RAILWAY_START_COMMAND.md` - Copy-paste start command
2. **Full Guide**: `RAILWAY_DEPLOYMENT.md` - Complete deployment steps
3. **Automated**: `./deploy_to_railway.sh` - One-command setup

---

**Bottom Line:** Switch to service account and never worry about token expiration again! 🎉
