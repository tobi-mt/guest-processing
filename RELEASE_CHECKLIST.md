# Release and rollback checklist

## Before deployment

- Record the commit and migration versions.
- Run unit, API integration, browser, keyboard, accessibility, lint, migration,
  worker-recovery, and backup/restore gates.
- Download a full backup and run `guest-manager verify-backup` against the exact
  production database snapshot.
- Confirm session secret, dashboard credentials/roles, Resend key, sender domain,
  calendar service account, and public URLs are environment variables—not files.
- For multiple operators, set `MIRROR_TALK_DASHBOARD_USERS_JSON` to an object such
  as `{"producer":{"password":"...","role":"operator"},"lead":{"password":"...","role":"admin"}}`.
  Keep the legacy single-user variables only during a controlled transition.
- Review pending/dead-letter email and calendar proposal counts.

## Smoke checks

- `/healthz` returns 200 and `/readyz` returns 200.
- Login sets expiring session and CSRF cookies; unauthenticated private APIs fail.
- Dashboard, Operations, and Planning load with non-zero data or a truthful empty state.
- A dry-run calendar read creates no interview changes.
- A test outbox item is claimed once and records its attempt.
- Static versioned assets are cacheable; private JSON is `no-store`.
- Viewer accounts can read but not write; operators can update workflows; only
  admins can delete, import/export backups, or merge guest identities.

## Rollback

1. Stop web and worker processes to prevent new writes.
2. Redeploy the previous application commit.
3. If schema/data rollback is required, preserve the failed database, restore the
   verified pre-deploy backup to a new path, and point the service at that path.
4. Run integrity and readiness checks before reopening traffic.
5. Reconcile any provider-accepted idempotency keys and calendar actions created
   during the failed window; do not blindly resend or reapply them.
