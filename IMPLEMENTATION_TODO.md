# Guest Processing Modernization Backlog

This backlog converts the August 2, 2026 production audit into an executable,
risk-ordered delivery program. Check an item only after its acceptance criteria
and the relevant verification gate pass.

## Delivery rules

- Preserve production data before every migration or repair operation.
- Route lifecycle changes through one transition boundary; never infer and write
  a new state during a read.
- Require an idempotency key for every externally visible side effect.
- Keep guest-facing communication and editorial publication human-approved
  until their automation policy is explicitly changed.
- Add regression tests before or with every defect fix.
- Do not deploy with failing tests, migrations, recovery checks, or smoke tests.

## P0 — Contain current risk

- [x] Restore a green test suite.
  - [x] Restore or deliberately replace the legacy `get_column_value` contract.
  - [x] Make the refactored database module importable.
  - [x] Prevent Dashboard-to-Planning handoff from changing editing episodes to
        released merely because a release date is in the past.
  - [x] Repair and test booking-confirmation fallback encoding.
  - [x] Rebalance scheduling freshness so old recordings cannot dominate fresh,
        seasonally relevant candidates.
  - Acceptance: complete — 287 tests pass and targeted undefined-name lint passes.
- [x] Replace transient zero KPI states with loading, stale, and failure states.
- [x] Add a read-only production integrity command covering duplicates, null
      identity keys, invalid states, orphan records, and conflicting dates.
- [x] Document and verify backup and restore before data remediation.

## P1 — Data and lifecycle foundation

- [x] Add a versioned migration ledger and transactional migration runner.
- [x] Enable SQLite foreign-key enforcement on every connection and verify it.
- [x] Add canonical status constants plus database checks or validation triggers.
- [x] Normalize email and identity keys; define duplicate and merge policy.
- [x] Separate guest/person identity from application/submission history.
- [x] Add immutable audit events with actor, source, reason, correlation ID, and
      before/after state.
- [x] Implement central transition services for Application, Booking, Interview,
      Episode, Release, and Communication lifecycles.
- [x] Make all API writes use optimistic concurrency or an equivalent conflict
      check.
- Acceptance: migrations pass on empty, current, and representative legacy
  databases; invalid and orphan transitions fail deterministically; rollback and
  restore are exercised.

## P1 — Reliable automation and security

- [x] Run the communication outbox continuously outside request threads.
- [x] Add atomic claim/lease, idempotency key, bounded exponential backoff,
      attempt history, terminal failure state, and dead-letter review.
- [x] Add outbox health metrics and an operator recovery console.
- [x] Reconcile calendar changes through proposed actions and explicit policy.
- [x] Add automation-run records, correlation IDs, structured logs, metrics, and
      alert thresholds.
- [x] Add login throttling, session expiry and rotation, CSRF protection, CSP,
      frame, content-type, referrer, and transport-security headers.
- [x] Add role-ready authorization boundaries for destructive, communication,
      scheduling, publishing, and administrative actions.
- [x] Remove sensitive record payloads from browser session storage; cache only
      non-sensitive summaries where needed.
- Acceptance: duplicate delivery and worker-crash tests prove at-most-once
  external effects for one idempotency key; security integration tests pass.

## P2 — Shared application shell and interaction model

- [x] Replace large hero panels with a compact workspace/status header.
- [x] Add consistent prioritized queue, filter bar, saved views, detail drawer,
      activity timeline, and one state-aware primary action.
- [x] Group secondary actions and move import, backup, export, research, and
      configuration into Administration or contextual menus.
- [x] Add skeleton loading, empty, stale, partial, permission, and error states.
- [x] Make filters URL-addressable and keyboard operable.
- [x] Add bulk-action preview showing affected records and side effects.
- [x] Establish reusable UI tokens and components; split monolithic scripts and
      service handlers along domain boundaries.

## P2 — Guest Dashboard: “Who needs a decision?”

- [x] Default to needs-review ordered by SLA breach and application age.
- [x] Use compact rows with source, age, completeness, fit, risk, owner, and next
      action; open evidence and full application in the detail drawer.
- [x] Separate `Accept` from `Accept + send` and preview downstream effects.
- [x] Preserve every submission and decision; never reopen by overwriting history.
- [x] Reject placeholder social handles such as `NA` as links and validate URLs.
- [x] Display decision approval rate separately from intake disposition mix.
- [x] Add deduplication/merge review and incomplete-information workflows.

## P2 — Operations: “What must happen before the next interview?”

- [x] Add Today, Next 7 days, Needs confirmation, Reminder due, Booking risk, and
      Recently completed queues.
- [x] Make confirm, remind, reconcile, record outcome, and planning handoff the
      state-aware primary actions.
- [x] Show SLA, owner, last contact, delivery status, and chronological activity.
- [x] Hide add/edit forms until requested and remove them from confirmation views.
- [x] Add calendar cleanup/reconciliation workflow for cancelled, declined, and
      reschedule-requested interviews.
- [x] Remove duplicate empty-state copy and label every interactive control.

## P2 — Planning: “What should release next?”

- [x] Add an 8–12 week release calendar and backlog board:
      Recorded → Editing → Assets needed → Ready → Scheduled → Released.
- [x] Gate scheduling on required readiness fields and expose exceptions.
- [x] Add release, accelerate, refresh, hold, archive, and retire dispositions.
- [x] Add cadence, capacity, category/guest spacing, age, and seasonal controls.
- [x] Explain scheduling factors, freshness, confidence, and override rationale.
- [x] Prevent guest/title mismatches and duplicated generated-copy prefixes.
- [x] Make rank/date ordering explicit and report actual pagination counts.
- [x] Run a one-time disposition workflow for the 138-item unreleased backlog.
  - Delivery note: the bulk preview and explicit active/hold/archive/retire
    workflow are implemented and tested. Applying it to the production backlog
    remains a human-approved rollout operation after the pre-deploy backup.

## P3 — Measurement and responsible AI

- [x] Instrument append-only lifecycle and communication events.
- [x] Publish metric definitions, owners, freshness, and quality checks.
- [x] Measure guest decision lead time, interview-to-release lead time, and
      on-time release rate at median and 90th percentile where applicable.
- [x] Measure stage queue age/SLA, confirmation coverage, reminder delivery,
      readiness, scheduled coverage, and handling time.
- [x] Guard against duplicates, delivery failures, invalid transitions, stale
      enrichment, failed backups, and untested restores.
- [x] Evaluate fit and scheduling recommendations against historical decisions;
      report calibration, precision by score band, disagreement, and overrides.
- [x] Keep AI scores advisory, source-linked, freshness-aware, and versioned.

## P3 — Quality, accessibility, and release operations

- [x] Add API integration, browser end-to-end, keyboard, and automated
      accessibility coverage for all critical workflows.
- [x] Test phone, tablet, desktop, zoom, reduced motion, and high contrast.
- [x] Add stored-XSS regression tests and consistently escape or safely construct
      all dynamic DOM content.
- [x] Add migration, backup/restore, worker recovery, calendar, and email contract
      tests to CI.
- [x] Cache versioned static assets while keeping private API responses non-cacheable.
- [x] Add deployment smoke checks, health/readiness endpoints, rollback procedure,
      and a release checklist.

## P4 — Scale when operational evidence requires it

- [x] Define SQLite exit criteria using concurrency, lock time, worker topology,
      write volume, backup time, and recovery objectives.
- [x] Prepare and rehearse a PostgreSQL migration only when exit criteria are met.
  - Gate result: the measured SQLite signals do not currently authorize a
    PostgreSQL rehearsal, so the conditional rehearsal was correctly not run.
- [x] Add multi-user roles and assignment workflows when the operating model needs
      producers, editors, or assistants.

## Program definition of done

- All checklist items in the selected release milestone are complete.
- Unit, integration, end-to-end, accessibility, lint, migration, and recovery
  gates pass from a clean checkout.
- Production-impacting changes have a reversible rollout and verified backup.
- Dashboards expose trustworthy freshness, ownership, and exception states.
- A human can inspect who or what changed each lifecycle state and why.
