# WordPress Integration Guide

This file is retained for reference only.

The recommended live flow is now:

- host the intake page on Railway
- link to the hosted intake page from WordPress
- submit directly into the backend/database

The earlier WordPress-native plugin approach is no longer the recommended launch path.

Plugin location:

```text
wordpress/mirror-talk-guest-intake/
```

## Integration Model

- Public website page on WordPress
- Shortcode renders a branded native multi-step form
- Form submits to the Python intake API hosted separately, for example on `apply.mirrortalkpodcast.com`
- Submissions still go to the Python backend and existing database
- Public form is intentionally trimmed to a shorter, premium 3-step application

## Why This Is The Safer Setup

- WordPress handles the page and editorial content
- The Python app handles application logic and database access
- The embed keeps the live WordPress theme stable
- You can redesign the intake app without rewriting WordPress templates

## Shortcode

```text
[mirror_talk_guest_intake]
```

Optional shortcode example:

```text
[mirror_talk_guest_intake title="Be Our Next Guest" subtitle="Tell us about your story through a short guided application."]
```

## Suggested Deployment

1. Deploy the Python intake backend on Railway or another host:
   `https://ask-mirror-talk-production.up.railway.app/api/intake`
2. Install the plugin in WordPress.
3. Set the plugin intake API URL in:
   `Settings -> Mirror Talk Intake`
4. Add the shortcode to the guest application page.
5. Use your child theme for any final spacing or typography polish.
6. Allow cross-origin requests from `https://www.mirrortalkpodcast.com` to the intake backend.
7. Set the Railway environment variable `MIRROR_TALK_INTAKE_API_TOKEN` to the same secret used in the WordPress bridge plugin.

## Files Included

- `wordpress/mirror-talk-guest-intake/mirror-talk-guest-intake.php`
- `wordpress/mirror-talk-guest-intake/assets/css/mirror-talk-guest-intake.css`
- `wordpress/mirror-talk-guest-intake/assets/js/mirror-talk-guest-intake.js`
- `wordpress/mirror-talk-guest-intake/README.md`
