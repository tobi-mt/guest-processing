# Production governance v1.0 — engineering review

Reviewed against `Mirror_Talk_Production_Governance_v1.0.yaml` on 2026-09-12.
The supplied file is the approved policy source. Its contents remain policy and data,
not direct software commands; implementation changes still pass engineering controls.

Status update: Tobi Ojekunle formally approved v1.0 on 2026-09-12 and made it
effective immediately. The policy is now authoritative; externally visible and
destructive actions still require the approvals stated within it.

Correction update: approved contradiction fixes were recorded as v1.0.1 rather
than editing the approved version without a version increment. The effective date
remains 2026-09-12.

## Recommendation

Adopt the editorial intent, measurement separation, human-approval rules, and episode
classification model. Do not enable hard scheduling or readiness enforcement until the
decisions below are resolved and recorded in a revised governance version.

## Blocking decisions for v1.1

1. **Resolved 2026-09-12 — document status.** Tobi approved v1.0 and changed its
   lifecycle state to `approved`, effective 2026-09-12. A future machine-readable
   revision should also carry a full approval timestamp, not only a date.
2. **Separate policy from a dated operating plan.** Baselines, release dates, immediate
   actions, targets, and source-review notes will age independently of durable policy.
   Put them in a versioned cycle plan that references the policy version.
3. **Fix the review horizon.** The final release is 2026-12-08 but the governance review
   is 2026-12-09, before its 7-day and 30-day results exist. Define a cohort cutoff and
   a later final evaluation, or explicitly exclude immature releases.
4. **Define readiness as evidence, not one status.** Specify required checks per content
   class, who approves each check, timestamps, and which checks may be waived. A single
   `ready` value cannot establish that rights, facts, captions, links, assets, and
   destination previews were reviewed.
5. **Define exceptions completely.** Every exception needs rule identifier, requester,
   approver, reason, risk, expiry/effective window, and audit timestamp. A free-text
   reason alone is insufficient for locked-policy exceptions.
6. **Clarify flagship versus host reflection.** The current model makes host reflection
   both a content class and conditionally a flagship. Choose one primary class with a
   format subtype, or define precedence explicitly.

## Material blindspots

- Rights, releases, music/image licences, consent scope, withdrawal/takedown handling,
  and retention/deletion policy are missing.
- Safeguarding and editorial risk need a documented escalation owner, evidence standard,
  correction policy, incident response, and emergency stop/unpublish procedure.
- AI use needs boundaries for generated copy/assets, fact verification, disclosure,
  personal data, prompt/data retention, and a ban on synthetic guest identity.
- Accessibility acceptance criteria are absent for captions, transcripts, thumbnails,
  articles, and the web experience.
- Guest scoring can reject strong editorial guests for weak distribution reach. Consider
  making distribution commitment a planning signal or guardrail rather than part of the
  editorial admission threshold; also require score evidence and bias review.
- Schedule rules need DST-safe instants, platform scheduling failure handling, lateness
  tolerance, and an explicit definition of which timestamp is canonical.
- Metrics need immutable source observations, source/definition versions, attribution
  windows, timezone/cutoff rules, correction handling, zero denominators, bot filtering,
  and cohort inclusion/exclusion rules.
- “100% complete” conflicts with platform-dependent outputs such as Spotify Clips. Define
  `not_applicable` separately from missing or failed.
- UTM governance needs an exact schema, allowed values, case policy, URL canonicalisation,
  ownership, and validation before links are published.
- Role descriptions lack a RACI-style approval matrix and segregation-of-duties rules for
  high-risk claims, publication, corrections, and destructive actions.

## Safe foundation implemented

- Episode records now support content class, one primary pillar, an optional distinct
  secondary pillar, governance version, and exception reason.
- Values are validated at the service boundary; invalid classes/pillars and duplicate
  primary/secondary pillars are rejected.
- Existing rows migrate to `unclassified` without inferred editorial decisions.
- Planning UI exposes these fields while preserving optimistic concurrency and audit
  snapshots already used by episode writes.

## Proposed next approval

Approve a v1.1 policy split into:

1. durable governance policy;
2. a dated 90-day operating plan and baselines;
3. machine-readable controlled vocabularies and rule identifiers;
4. readiness-check and exception records with explicit approvers.

Only after that approval should the application block scheduling or publication based on
governance rules. Production data, scheduled items, communications, and external platform
state were not changed by this implementation.
