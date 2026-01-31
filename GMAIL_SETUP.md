# Gmail Email Setup Guide

## 🔧 Quick Fix for Gmail Authentication Error

If you see this error:
```
Failed to send email: (534, b'5.7.9 Application-specific password required...')
```

This means Gmail requires an **App Password** instead of your regular password.

## ✅ Step-by-Step Solution

### 1. Enable 2-Factor Authentication
- Go to [Google Account Security](https://myaccount.google.com/security)
- Click "2-Step Verification" 
- Follow the setup process if not already enabled

### 2. Generate App Password
- In Google Account → Security → **App passwords**
- Select **"Mail"** as the app type
- Choose your device or enter "Guest Database Manager"
- **Copy the 16-character password** that Google generates

### 3. Configure in the Application
In the Streamlit app sidebar:
- **Email Provider**: Select "Gmail"
- **SMTP Server**: `smtp.gmail.com` (auto-filled)
- **Port**: `587` (auto-filled)
- **Username**: Your full Gmail address (e.g., `your.email@gmail.com`)
- **Password**: **Use the 16-character App Password** (NOT your regular Gmail password)
- **From Email**: Your Gmail address
- **From Name**: Your preferred sender name

### 4. Test the Configuration
- Click "Save Email Settings"
- Try sending a test email to verify it works

## 🚨 Common Mistakes

❌ **Don't use your regular Gmail password**
✅ **Use the 16-character App Password**

❌ **Don't skip 2-Factor Authentication setup**
✅ **Enable 2FA first, then generate App Password**

## 🔗 Helpful Links

- [Google Account Security](https://myaccount.google.com/security)
- [Gmail App Password Help](https://support.google.com/mail/?p=InvalidSecondFactor)
- [2-Factor Authentication Setup](https://support.google.com/accounts/answer/185839)

## 📧 Alternative Email Providers

If Gmail setup is too complicated, consider:
- **Outlook/Hotmail**: Often works with regular password
- **Yahoo**: Also requires App Password
- **Business email**: Usually works with regular SMTP credentials

---

**Need more help?** Check the application's email configuration sidebar - it now provides step-by-step guidance for Gmail setup!
