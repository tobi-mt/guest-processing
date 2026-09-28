# Dashboard account security runbook

## Roles

- `viewer`: authenticated read-only access.
- `operator`: normal guest, interview, and planning writes.
- `admin`: destructive and system-administration operations already classified by the API policy.
- `super_admin`: all admin permissions plus account creation, suspension, role management, and recovery.

`mt_admin` is promoted to `super_admin` during legacy bootstrap. Maintain at least two
active super administrators. The application prevents the final super administrator
from removing their own access.

Super administrators must enroll a TOTP authenticator before account administration
is available in production. TOTP secrets are encrypted at rest with a key derived from
the session secret, accepted codes cannot be replayed, and disabling MFA requires both
the current password and a fresh authenticator code. Changing the session secret is
therefore a coordinated global sign-out and MFA-key rotation event; recover affected
administrators through the audited recovery flow.

## Account lifecycle

1. A super administrator creates the identity in `/accounts`.
2. The application creates a random unusable credential and a single-use invitation.
   The administrator sends that link through an authenticated private channel.
3. The teammate chooses their own password. Passwords must be 12–256 characters,
   contain letters and numbers, exclude common defaults, and not contain the username
   or email name.
4. Suspend access immediately when a teammate leaves. Suspension, role changes,
   password changes, and session invalidation increment the account authentication
   version, invalidating every previously issued session.

Passwords are stored using salted PBKDF2-HMAC-SHA256 with 600,000 iterations. Raw
passwords and raw invitation/recovery tokens are never persisted. Account lifecycle
events retain actor, timestamp, type, and non-secret details.

## Recovery

A super administrator issues a recovery link from `/accounts` after independently
verifying the teammate's identity. Recovery links expire after 30 minutes, are
single-use, and invalidate all existing sessions when completed. Never place links in
tickets, shared documents, or logs. If a link may have been exposed, issue a new one;
doing so invalidates any earlier unused link.

The public completion endpoint is IP-rate-limited and validates the token before
performing password hashing. It does not reveal whether a username or email exists.

## Production configuration

Required:

```text
MIRROR_TALK_ENV=production
MIRROR_TALK_PUBLIC_URL=https://your-service.example
MIRROR_TALK_DASHBOARD_SESSION_SECRET=<at least 32 random characters>
```

Production startup fails rather than silently accepting a weak session secret,
non-HTTPS public origin, credentials in the origin, or an origin containing a path.
Rotate the session secret only as a planned global sign-out.

The initial legacy environment credential is bootstrap-only. After verifying the
persisted `mt_admin` account and changing its password in `/account-settings`, remove
the legacy password and multi-user JSON variables from the deployment environment.

## Incident response

1. Suspend the affected account or use “Sign out everywhere.”
2. Preserve `dashboard_account_events` and relevant request/security logs.
3. Issue a recovery link only after identity verification.
4. Rotate the global session secret if session-signing material may be exposed.
5. Verify database backup integrity before remediation that changes account tables.
