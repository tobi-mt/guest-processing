#!/bin/bash
# Quick deployment script for Railway with Google Service Account

set -e  # Exit on error

echo "======================================================================"
echo "  Railway Deployment - Google Service Account Setup"
echo "======================================================================"
echo ""

# Check if Railway CLI is installed
if ! command -v railway &> /dev/null; then
    echo "❌ Railway CLI not found"
    echo ""
    echo "Install it with:"
    echo "  npm i -g @railway/cli"
    echo ""
    exit 1
fi

echo "✅ Railway CLI found"
echo ""

# Check if service account file exists
SERVICE_ACCOUNT_FILE="/Users/tobi/Documents/PODCAST/mt-wp-forms-1732226728680-bc52eed2795a.json"

if [ ! -f "$SERVICE_ACCOUNT_FILE" ]; then
    echo "❌ Service account file not found: $SERVICE_ACCOUNT_FILE"
    echo ""
    echo "Please update the SERVICE_ACCOUNT_FILE path in this script"
    exit 1
fi

echo "✅ Service account file found"
echo ""

# Encode service account to base64
echo "Encoding service account to base64..."
SERVICE_ACCOUNT_BASE64=$(base64 -i "$SERVICE_ACCOUNT_FILE" | tr -d '\n')

if [ -z "$SERVICE_ACCOUNT_BASE64" ]; then
    echo "❌ Failed to encode service account"
    exit 1
fi

echo "✅ Service account encoded (${#SERVICE_ACCOUNT_BASE64} characters)"
echo ""

# Check if logged in to Railway
echo "Checking Railway login status..."
if ! railway whoami &> /dev/null; then
    echo "❌ Not logged in to Railway"
    echo ""
    echo "Login with:"
    echo "  railway login"
    echo ""
    exit 1
fi

echo "✅ Logged in to Railway as: $(railway whoami)"
echo ""

# Set environment variables
echo "======================================================================"
echo "  Setting Railway Environment Variables"
echo "======================================================================"
echo ""

# Service Account (base64 encoded)
echo "Setting MIRROR_TALK_GOOGLE_SERVICE_ACCOUNT_BASE64..."
railway variables set MIRROR_TALK_GOOGLE_SERVICE_ACCOUNT_BASE64="$SERVICE_ACCOUNT_BASE64"
echo "✅ Service account variable set"
echo ""

# Calendar ID
echo "Setting MIRROR_TALK_GOOGLE_CALENDAR_ID..."
railway variables set MIRROR_TALK_GOOGLE_CALENDAR_ID="podcast.mirrortalk@gmail.com"
echo "✅ Calendar ID set"
echo ""

# Timezone (optional)
echo "Setting MIRROR_TALK_GOOGLE_CALENDAR_TIMEZONE..."
railway variables set MIRROR_TALK_GOOGLE_CALENDAR_TIMEZONE="Europe/Berlin"
echo "✅ Timezone set"
echo ""

# Optional: Remove old OAuth variables (uncomment if ready to fully switch)
# echo "Removing old OAuth variables..."
# railway variables delete MIRROR_TALK_GOOGLE_CLIENT_ID || true
# railway variables delete MIRROR_TALK_GOOGLE_CLIENT_SECRET || true
# railway variables delete MIRROR_TALK_GOOGLE_REFRESH_TOKEN || true
# echo "✅ Old OAuth variables removed"
# echo ""

echo "======================================================================"
echo "  Deployment Summary"
echo "======================================================================"
echo ""
echo "✅ Service account configured in Railway"
echo "✅ Calendar ID: podcast.mirrortalk@gmail.com"
echo "✅ Timezone: Europe/Berlin"
echo ""
echo "Next steps:"
echo "  1. Verify variables: railway variables"
echo "  2. Deploy: railway up"
echo "  3. Check logs: railway logs"
echo "  4. Test calendar features in deployed app"
echo ""
echo "Once confirmed working, remove OAuth variables by running:"
echo "  railway variables delete MIRROR_TALK_GOOGLE_CLIENT_ID"
echo "  railway variables delete MIRROR_TALK_GOOGLE_CLIENT_SECRET"
echo "  railway variables delete MIRROR_TALK_GOOGLE_REFRESH_TOKEN"
echo ""
echo "======================================================================"
echo "🎉 Configuration complete! Your app will never have token expiration issues again!"
echo "======================================================================"
