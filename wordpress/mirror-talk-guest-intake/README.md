# Mirror Talk Guest Intake WordPress Plugin

This plugin adds a shortcode for rendering the Mirror Talk guest intake form directly inside WordPress pages.
The public intake is designed as a short, higher-conversion multi-step guest application that submits straight to your backend API.

## Shortcode

```text
[mirror_talk_guest_intake]
```

Optional attributes:

```text
[mirror_talk_guest_intake title="Be Our Next Guest" subtitle="Share your story with Mirror Talk through a short guided application."]
```

## Installation

1. Copy the `mirror-talk-guest-intake` folder into `wp-content/plugins/`.
2. Activate **Mirror Talk Guest Intake** in the WordPress admin.
3. Open `Settings -> Mirror Talk Intake`.
4. Set the intake API URL to your deployed backend endpoint, for example:

```text
https://apply.mirrortalkpodcast.com/api/intake
```

5. Add the shortcode to the desired page.

## Recommended Setup

- Keep the intake backend hosted outside WordPress, ideally on a subdomain such as `apply.mirrortalkpodcast.com`.
- Use the shortcode inside the guest application page on `www.mirrortalkpodcast.com`.
- Use your child theme only for extra visual overrides, not for the core plugin logic.
- Make sure your backend accepts cross-origin submissions from your WordPress domain.

## Suggested Child Theme CSS Overrides

```css
.mirror-talk-intake-wrapper {
  margin-top: 3rem;
}

.mirror-talk-intake-card {
  box-shadow: none;
}
```
