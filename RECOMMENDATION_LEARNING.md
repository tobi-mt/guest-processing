# Recommendation Learning System

This is the implementation and operating checklist for the governed release-recommendation learning loop.
The system improves ranking from explicitly recorded outcomes while preserving editorial control, auditability,
rollback, and the rule that reads never mutate state.

## Phase 1 — Evidence foundation

- [x] Version every active recommendation policy.
- [x] Store immutable recommendation observations with policy version, feature-schema version, score, rank,
  feature vector, full snapshot, timestamp, and correlation ID.
- [x] Store idempotent outcomes separately from observations.
- [x] Support accepted, rejected, booked, released, delayed, cancelled, and normalized performance outcomes.
- [x] Link outcomes to the latest observation without inventing an observation when none exists.
- [x] Record actor, source, occurrence time, metadata, and audit events.
- [x] Exclude names, emails, beliefs, faith, gender, ethnicity, and other sensitive identity data from features.
- [x] Make baseline reads side-effect free.
- [x] Seed `release-planner-v1` as the reversible governed baseline.

Acceptance: duplicate observations/outcomes are idempotent, unobserved outcomes cannot train the model, and all
material writes are attributable.

## Phase 2 — Offline learning and evaluation

- [x] Use an explainable bounded logistic rank adjustment rather than opaque online retraining.
- [x] Train only from outcomes linked to snapshots using `release-features-v1`.
- [x] Enforce a configurable minimum sample count (hard floor: 20).
- [x] Reserve the newest 20% of time-ordered samples as a holdout set.
- [x] compare candidate and champion log loss and calculate relative uplift.
- [x] Bound every feature-weight change and total per-recommendation score adjustment.
- [x] Reject candidates with excessive prediction shift.
- [x] Persist candidate weights, training summary, evaluation report, and guardrail results.
- [x] Produce `insufficient_data`, `failed`, or `passed` states without changing production ranking.

Acceptance: running evaluation never activates a candidate and repeated training is reproducible for the same data.

## Phase 3 — Champion/challenger governance

- [x] Keep exactly one active policy through a partial unique database index.
- [x] Require a passed evaluation before promotion.
- [x] Require administrator authorization, a reason, and the expected row version.
- [x] Store the previous policy and evaluation on every deployment.
- [x] Apply the active policy in memory after rule-based recommendation generation.
- [x] Cap learned adjustments at ±10 points.
- [x] Provide one-step rollback to the previous deployed policy.
- [x] Audit activation and rollback.

Acceptance: stale approvals fail, failed/unevaluated candidates cannot ship, and rollback restores the prior policy.

## Phase 4 — Bounded evolution and monitoring

- [x] Keep automation disabled by default.
- [x] Keep an independent kill switch enabled by default.
- [x] Bound minimum samples, minimum uplift, and maximum weight changes at the API boundary.
- [x] Provide a single-cycle entry point suitable for an external scheduler.
- [x] Block automatic promotion when automation is disabled, the kill switch is active, evaluation fails, or outcome
  drift exceeds 0.20.
- [x] Monitor recent-versus-previous outcome means over two 30-outcome windows.
- [x] Retain manual promotion and rollback even when automation is disabled.

Acceptance: a scheduler can safely call one cycle repeatedly; safety gates default closed and cannot be bypassed by
the automatic path.

## Operator/API workflow

All routes require an authenticated dashboard session. Mutating routes require CSRF; settings, promotion, rollback,
and cycle execution require the administrator role.

1. `GET /api/recommendation-learning` — inspect policy, evidence counts, evaluations, settings, and drift.
2. Recommendation rejection atomically records its displayed snapshot and a negative outcome. Restoration only
   removes suppression; it is deliberately not treated as positive acceptance.
3. `POST /api/recommendation-learning/outcomes` — record later booking, release, delay, cancellation, or performance.
4. `POST /api/recommendation-learning/evaluate` — create a draft challenger and offline evaluation.
5. `POST /api/recommendation-learning/promote` — activate a passed challenger with `version`, `row_version`, and reason.
6. `POST /api/recommendation-learning/rollback` — restore the previous policy with a reason.
7. `POST /api/recommendation-learning/settings` — manage bounded thresholds and the kill switch.
8. `POST /api/recommendation-learning/cycle` — run one guarded automation cycle.

## Production operating checklist

- [ ] Define the editorial owner accountable for outcome definitions and promotion decisions.
- [ ] Backfill only outcomes whose provenance and timestamps can be verified.
- [ ] Keep performance values normalized to 0–1 using one documented measurement window.
- [ ] Review data quality and missingness before reducing the default sample threshold.
- [ ] Perform a manual evaluation and rollback drill before enabling automation.
- [ ] Run at least one full editorial cycle in observation-only mode.
- [ ] Enable automation only after the owner signs off; turn the kill switch off as a separate action.
- [ ] Schedule at most one cycle per reporting period and alert on blocked/drift results.
- [ ] Review feature relevance, drift, and unintended category effects quarterly.
- [ ] Preserve database backups and deployment/audit history according to the recovery policy.

These final items are operational approvals, not missing software behavior. They must be completed with real production
data and accountable humans; local tests must never manufacture that approval.
