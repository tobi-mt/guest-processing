# Railway Start Command

Copy and paste this exact command into your Railway project settings:

## Start Command

```bash
python -m pip install --upgrade pip && python -m pip install -e . && python decode_service_account.py && PYTHONPATH=src python -m guest_database_manager.cli web --host 0.0.0.0 --port $PORT --db /app/data/guest_database.db --no-browser
```

## What This Does

1. `python -m pip install --upgrade pip` - Updates pip to latest version
2. `python -m pip install -e .` - Installs your application in editable mode
3. `python decode_service_account.py` - Decodes the service account from base64 env var
4. `PYTHONPATH=src python -m guest_database_manager.cli web ...` - Starts your web application

## Environment Variables Needed

Make sure these are set in Railway:

```bash
# Service Account (Required)
MIRROR_TALK_GOOGLE_SERVICE_ACCOUNT_BASE64=<base64-encoded-service-account-json>
MIRROR_TALK_GOOGLE_CALENDAR_ID=podcast.mirrortalk@gmail.com

# Optional
MIRROR_TALK_GOOGLE_CALENDAR_TIMEZONE=Europe/Berlin
```

## Quick Setup

Run this to set up all Railway variables at once:

```bash
./deploy_to_railway.sh
```

Or manually:

```bash
# Encode service account
base64 -i /Users/tobi/Documents/PODCAST/mt-wp-forms-1732226728680-bc52eed2795a.json | tr -d '\n'

# Set in Railway
railway variables set MIRROR_TALK_GOOGLE_SERVICE_ACCOUNT_BASE64="<paste-base64-here>"
railway variables set MIRROR_TALK_GOOGLE_CALENDAR_ID="podcast.mirrortalk@gmail.com"
railway variables set MIRROR_TALK_GOOGLE_CALENDAR_TIMEZONE="Europe/Berlin"
```

## Verify Deployment

After deploying, check the logs:

```bash
railway logs
```

Look for:
```
✅ Service account decoded and saved to: /tmp/google-service-account.json
✅ Service Account Email: mirror-talk-calendar@mt-wp-forms-1732226728680.iam.gserviceaccount.com
```

## Troubleshooting

### If you see: "MIRROR_TALK_GOOGLE_SERVICE_ACCOUNT_BASE64 not set"

- Make sure you set the environment variable in Railway dashboard
- Verify the variable name is exactly: `MIRROR_TALK_GOOGLE_SERVICE_ACCOUNT_BASE64`

### If you see: "Failed to decode base64"

- Check that you copied the entire base64 string (no line breaks)
- Use `tr -d '\n'` to remove line breaks when encoding

### If you see: "Failed to fetch events"

- Verify calendar is shared with: `mirror-talk-calendar@mt-wp-forms-1732226728680.iam.gserviceaccount.com`
- Check that Calendar API is enabled in Google Cloud Console
- Permission should be: "Make changes to events"

## Next Steps

1. Set environment variables (use `./deploy_to_railway.sh` or manually)
2. Update start command in Railway dashboard (copy from above)
3. Deploy: `railway up` or push to your connected branch
4. Check logs: `railway logs`
5. Test calendar features in your deployed app
6. Remove old OAuth variables once confirmed working

🎉 No more token expiration issues!
