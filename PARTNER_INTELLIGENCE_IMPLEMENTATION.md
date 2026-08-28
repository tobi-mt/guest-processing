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

## Provider configuration

- `APOLLO_API_KEY` is server-side only and must never be exposed to browser code.
- Live Apollo People Search is disabled by default. Enable it with `APOLLO_LIVE_ENRICHMENT_ENABLED=true` only after the Apollo plan permits API People Search and a controlled live check succeeds.
- Apollo CSV import and public-source research remain available when live enrichment is disabled.
- Approving and queueing a pitch is an externally visible email action. Confirm the email provider, sender domain, approver roles, and test recipient before enabling production outreach.

## Free public-source enrichment

- First-party research checks the organisation host only, respects `robots.txt`, blocks private/local network destinations, and extracts published contacts plus JSON-LD person/role metadata without guessing emails.
- RSS/Atom feeds and sitemaps provide first-party publication and timing signals.
- Wikidata provides medium-confidence structured identity signals.
- OpenAlex checks institutions first, then broadens to relevant indexed works when no institution match exists.
- Crossref provides publication and publisher signals.
- GDELT provides low-confidence news discovery that always requires editorial review. If the document API is unavailable, it checks a bounded recent official GKG snapshot and reports zero matches honestly.
- ORCID uses first-party identifiers when present and otherwise performs a public affiliation search; affiliation results remain review-required.
- Each attempted provider records `completed` even when it truthfully returns zero matches; zero-match runs carry `no_results`. Network/provider errors remain `failed`, and one unavailable provider cannot block the others.
