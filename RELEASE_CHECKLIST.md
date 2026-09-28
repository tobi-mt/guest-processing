# Release and rollback checklist

## Before deployment

- Record the commit and migration versions.
- Run unit, API integration, browser, keyboard, accessibility, lint, migration,
  worker-recovery, and backup/restore gates.
- Download a full backup and run `guest-manager verify-backup` against the exact
  production database snapshot.
- Set `MIRROR_TALK_ENV=production`, an HTTPS origin in `MIRROR_TALK_PUBLIC_URL`,
  and a randomly generated `MIRROR_TALK_DASHBOARD_SESSION_SECRET` of at least 32 characters.
  Production startup intentionally fails closed when these are missing or weak.
- Confirm dashboard credentials/roles, Resend key, sender domain,
  calendar service account, and public URLs are environment variables—not files.
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
- A dry-run calendar read creates no interview changes.
- A test outbox item is claimed once and records its attempt.
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
