# Release and rollback checklist

## Before deployment

- Record the commit and migration versions.
- Run unit, API integration, browser, keyboard, accessibility, lint, migration,
  worker-recovery, and backup/restore gates.
- Run `guest-manager podcast-release-readiness --db /path/to/guest_database.db`.
  Do not call Podcast Reach released until it exits successfully with zero blockers.
- Download a full backup and run `guest-manager verify-backup` against the exact
  production database snapshot.
- Set `MIRROR_TALK_ENV=production`, an HTTPS origin in `MIRROR_TALK_PUBLIC_URL`,
  and a randomly generated `MIRROR_TALK_DASHBOARD_SESSION_SECRET` of at least 32 characters.
  Production startup intentionally fails closed when these are missing or weak.
- Confirm dashboard credentials/roles, Resend key, sender domain,
  calendar service account, and public URLs are environment variables—not files.
- Configure the Resend webhook endpoint as
  `https://<public-host>/api/webhooks/resend` for `email.sent`, `email.delivered`,
  `email.delivery_delayed`, `email.bounced`, and `email.complained`. Store its
  `whsec_...` value in `MIRROR_TALK_RESEND_WEBHOOK_SECRET`.
- Optionally set `MIRROR_TALK_ARCHIVE_BCC_EMAIL` to a restricted internal mailbox.
  This archive recipient is sent as BCC and is not disclosed to guests or CC recipients.
- In Resend Domains, confirm the exact domain used by `MIRROR_TALK_FROM_EMAIL` is
  verified and its SPF and DKIM records are green. Confirm a public DMARC TXT record
  exists at `_dmarc.<sending-domain>` (or is inherited from the organizational domain).
- Use the persisted Accounts interface for all teammates. Keep the legacy credential
  variables only long enough to bootstrap `mt_admin`, verify its `super_admin` role,
  and set a strong password in Account settings. Remove multi-user JSON credentials
  after migration so environment plaintext is not the long-term identity store.
- Create teammates through one-time invitations. Never choose, transmit, or record
  another teammate's password. Deliver invitation and recovery links through an
  authenticated private channel; each link is single-use and expires within one hour.
- Review pending/dead-letter email and calendar proposal counts.

## Smoke checks

- `/healthz` returns 200 and `/readyz` returns 200.
- Login sets expiring session and CSRF cookies; unauthenticated private APIs fail.
- Production session cookies include `Secure`, `HttpOnly`, `SameSite=Strict`, and a
  bounded lifetime. Password changes, suspension, role changes, and “sign out
  everywhere” invalidate existing sessions.
- Dashboard, Operations, and Planning load with non-zero data or a truthful empty state.
- Podcast Reach release readiness reports current migration 46, complete public
  discovery, fresh YouTube analytics, connected Spotify and Apple collectors, and
  fresh provider evidence. Known unavailable destinations remain explicit warnings.
- Podcast Reach's global activity total reconciles to open-RSS downloads +
  Spotify-native plays + YouTube views for comparable windows. Confirm Apple-native
  plays are visible in the deep dive but excluded from the executive total.
- On the authorized operations Mac, both collector LaunchAgents are loaded, their
  latest runs succeeded, and no collector token or provider session appears in the
  plist, application logs, or Railway logs.
- For a new operations Mac, run the one-time `local_analytics_collector setup`
  command and confirm it registers Spotify and Apple, completes both owner-controlled
  login ceremonies, and installs the staggered 06:15/06:30 daily jobs.
- Website player analytics needs the theme's `podcast-player` report deployed and a
  WordPress Application Password in `MIRROR_TALK_WEBSITE_ANALYTICS_USER` and
  `MIRROR_TALK_WEBSITE_ANALYTICS_APP_PASSWORD`; leave them unset to keep the card in setup state.
- Leave `MIRROR_TALK_OPENPODCAST_AUTO_SYNC` unset unless the optional OpenPodcast
  account has passed a manual endpoint sync. If enabled, verify a failure enters the
  20-hour backoff instead of retrying every worker cycle.
- A dry-run calendar read creates no interview changes.
- A test outbox item is claimed once and records its attempt.
- A Resend test message records its provider ID, then changes from `accepted` to
  `delivered` after the signed webhook arrives. Replay the webhook and confirm it is
  idempotent. Verify delayed, bounced, and complained test events appear in Operations.
- Static versioned assets are cacheable; private JSON is `no-store`.
- Viewer accounts can read but not write; operators can update workflows; only
  admins can delete, import/export backups, or merge guest identities; only super
  admins can administer accounts or issue recovery links.
- Confirm at least two active super administrators before depending on account
  recovery operationally. Enroll TOTP MFA for each; production account administration
  is blocked until MFA is enabled. Store emergency recovery procedure access separately.

## Rollback

1. Stop web and worker processes to prevent new writes.
2. Redeploy the previous application commit.
3. If schema/data rollback is required, preserve the failed database, restore the
   verified pre-deploy backup to a new path, and point the service at that path.
4. Run integrity and readiness checks before reopening traffic.
5. Reconcile any provider-accepted idempotency keys and calendar actions created
   during the failed window; do not blindly resend or reapply them.
