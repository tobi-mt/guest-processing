# Partner Intelligence release readiness — 2026-08-27

## Code and data gates

- Full regression suite: 373 tests passed after the multi-source enrichment migration.
- JavaScript sorting suite: 5 tests passed.
- Python compile, Ruff undefined-name checks, JavaScript syntax, and `git diff --check`: passed.
- Empty database migration rehearsal: SQLite integrity `ok`, schema version 21.
- Current-database-copy migration rehearsal: SQLite integrity `ok`, schema version 21.
- Backup/restore rehearsal: restored integrity `ok`; source and restored row counts matched.
- Browser QA: authenticated `/partners` exercised at 1280 px, 640 px, and 375 px; no horizontal overflow or console errors. Draft comparison, selection, final preview, and source links were verified on a temporary database.
- No production database was migrated or modified during QA.

## Provider gates

- Apollo credential is stored in ignored `.env` configuration and is not tracked by Git.
- Live Apollo People Search returned HTTP 403 because it is not included in the current Free plan.
- `APOLLO_LIVE_ENRICHMENT_ENABLED` therefore defaults to `false`. Do not enable it until the Apollo plan permits People Search and a controlled live check passes.
- Apollo CSV import remains available and retains provider provenance, verification status, suppression checks, and human recipient selection.
- Public-source research remains the live-enrichment fallback.

## Required deployment procedure

1. Record the release commit and schema version 21.
2. Stop or drain the web/outbox worker.
3. Run `guest-manager integrity --db /path/to/production.db` and review all findings.
4. Run `guest-manager verify-backup --db /path/to/production.db`.
5. Store the verified backup outside the production volume.
6. Confirm dashboard users/roles, session secret, OpenAI key/model, Resend key, verified sender domain, and public URLs.
7. Leave `APOLLO_LIVE_ENRICHMENT_ENABLED=false` on the current Apollo plan.
8. Deploy the recorded commit and allow migrations to reach version 21.
9. Verify `/healthz`, `/readyz`, authentication, CSRF enforcement, `/partners`, and static asset versions.
10. Use a designated internal test recipient to approve and queue one pitch; verify exactly one outbox attempt and delivery before real outreach.

## Human approvals that code cannot infer

- Approve the Mirror Talk brand voice and excluded partner categories.
- Approve retention periods and lawful basis for each outreach market.
- Name the operators allowed to approve outreach.
- Review the current database's known duplicate-identity findings before release.

## Rollback

Stop web and worker processes, preserve the failed database, deploy the previous commit, restore the verified backup to a new path if schema rollback is required, run integrity/readiness checks, and reconcile provider-accepted idempotency keys before reopening traffic.
