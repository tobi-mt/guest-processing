# Mirror Talk Partner Intelligence — Production Checklist

This module is a separate, review-first workflow inside the authenticated Mirror Talk operations environment. It does not send messages, publish content, or contact a prospect automatically.

## Phase 0 — Product and governance foundation

- [x] Define the product boundary: research, ranking, drafting, review, and outcome capture.
- [x] Define the public-facing Mirror Talk collaboration value proposition and excluded partner categories.
- [x] Establish hard controls: source provenance, factual/inference separation, human approval, suppression, audit events, and no auto-send.
- [x] Define outcome metrics: review approval, evidence accuracy, time-to-draft, reply, meeting, booking, opt-out, and complaint rates.
- [ ] Obtain production owner approval for brand voice, excluded categories, retention period, and lawful-basis assessment for each outreach market.

## Phase 1 — Data foundation

- [x] Add dedicated prospect, evidence, draft, outreach, and suppression tables through a repeatable migration.
- [x] Provide transactional repository operations and immutable audit events.
- [ ] Ingest Mirror Talk episode metadata/transcript-derived themes without changing episode titles or provenance.
- [x] Build a prospect profile from approved manual/public-source inputs.

## Phase 2 — Research and recommendation intelligence

- [x] Require two independent public sources before a prospect can be pitch-ready.
- [x] Extract only attributable factual snippets and retain canonical source URLs.
- [x] Score fit transparently: mission, timeliness, editorial connection, mutual value, reachability, and safety.
- [x] Require reviewers to distinguish verified facts from suggested framing through source-linked evidence and editable drafts.
- [x] Block unsuitable categories and sensitive-data profiling.

## Phase 3 — Pitch drafting and review

- [x] Produce a source-backed, editable pitch draft; never fabricate metrics, relationships, or outcomes.
- [x] Create a review state machine: research → draft → approved / rejected / suppressed.
- [x] Enforce an explicit human approval before any export/handoff.
- [x] Version drafts, retain review reasons, and record every material change.

## Phase 4 — Operations and outcomes

- [x] Add an authenticated Partner Intelligence workspace and JSON API.
- [x] Permit manual CRM/email handoff only after approval; no sending capability in this module.
- [x] Capture replies, meetings, bookings, decline reasons, and opt-outs.
- [ ] Feed aggregate outcomes back into reports; do not silently retrain on sensitive data.

## Phase 5 — Quality and release readiness

- [x] Cover repository, validation, authorization, state transitions, XSS, and regression cases with tests.
- [ ] Rehearse migrations on empty/current/legacy database copies and verify backup/restore.
- [x] Run static checks and the full regression suite.
- [ ] Configure production secrets, retention job, monitoring, lawful-basis documentation, and named approvers before deployment.

## Non-code production gates

The implementation can be release-ready without contacting anyone. Production activation still requires the unchecked governance and deployment approvals above. These are deliberately human decisions and cannot be safely inferred or automated.
