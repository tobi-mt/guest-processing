# Production governance v1.1 — approved design decisions

Decision record created 2026-09-12 following review of production governance v1.0.
This record defines the system design direction. It does not publish, reschedule,
unpublish, contact guests, or alter external platforms.

Production governance v1.0 was formally approved by Tobi Ojekunle and became
effective on 2026-09-12. The contradiction-correction release is v1.0.1; it keeps
the same effective date and implements the approved design clarifications below.

## 2. Review horizons

- 2026-12-09 is the end-of-cycle operational checkpoint.
- Per-release evaluation remains T+1, T+7, and T+30.
- 2027-01-14 is the mature cycle review, allowing the 2026-12-08 release to reach
  T+30 plus a reporting-lag allowance.
- Cohort reports must identify their data cutoff and exclude or visibly mark immature
  observations. Missing data must never be treated as zero.

## 3. Evidence-backed readiness

`ready` is a derived summary, not primary evidence. Each applicable release requires
individually attributable checks for editorial approval, master media, rights/consent,
claim and safety review, metadata, artwork, captions/transcript, links/tracking,
destination preview, guest fact verification, and scheduling confirmation.

Checks have `pending`, `passed`, `failed`, or `not_applicable` status. `not_applicable`
requires evidence and an actor. Hard enforcement remains disabled until check ownership
and the full rule catalogue are approved.

## 4. Exceptions

Exceptions are separate records containing policy version, stable rule identifier,
requester, approver, reason, risk assessment, scope/episode, effective window, decision
timestamp, and lifecycle state. A note on an episode is not approval. Tobi Ojekunle is
the sole final approver for locked-policy exceptions until an explicit delegate matrix
is approved.

## 5. Release class and format

`flagship` is a content/release class. `guest_conversation` and `host_reflection` are
format types. Every flagship must declare one of those formats. A host reflection may
enter the main RSS feed only when it is an approved flagship; its format alone does
not grant eligibility.

## 6. Safety and trust controls

Before publication automation is enabled, the rule catalogue must cover consent and
licence scope, withdrawal/takedown handling, corrections, privacy/retention, high-risk
claims, safeguarding, conflicts, accessibility, AI-assisted content, incident response,
and emergency publication stops. Synthetic or materially altered guest identity remains
prohibited.

## 7. Guest evaluation

Editorial admission and distribution planning are separate decision dimensions. Editorial
fit, story depth, credibility, and listener value determine suitability. Distribution
commitment remains visible for planning but cannot by itself push an otherwise qualified
guest below the editorial acceptance threshold. Every score requires evidence and an
exception path; periodic bias review is required.

## 8. Document architecture

Governance is split into:

1. durable policy, changed rarely through formal approval;
2. operating standards, changed through controlled operational improvement;
3. dated cycle plans containing baselines, targets, experiments, release dates, and
   immediate actions, which expire at the end of their stated period.

Machine-readable versions must have an unambiguous lifecycle (`draft`, `approved`, or
`retired`), effective timestamp, approval timestamp, source digest, and immutable version.
An approved version may not be edited in place; corrections create a new version.

## Implementation status — 2026-09-12

- One canonical classifier now serves intake decision support, episode planning,
  scheduling intelligence, and editorial-mix reporting.
- Human-confirmed episode pillars take precedence over advisory keyword inference.
- Intake displays inferred focus and keeps distribution planning separate from
  editorial eligibility.
- Non-flagship assets are excluded from flagship scheduling recommendations.
- Flagship scheduling uses Tuesday 05:00 Europe/Berlin with the Monday 12:00 lock.
- Legacy unclassified episodes remain eligible but carry a classification-review
  warning so historical records are not silently removed from planning.
