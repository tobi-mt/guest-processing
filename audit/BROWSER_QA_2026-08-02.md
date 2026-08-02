# Browser QA evidence — 2026-08-02

Target: isolated local copy of `guest_database.db` served at `127.0.0.1` with
the same web entry point and migrations as production. No production records or
external providers were changed.

## Critical workflows

- Signed login redirected to Dashboard and issued CSRF-protected access.
- Dashboard defaulted to `needs_review`, SLA/age ordering, and reported matched
  versus total counts accurately.
- Named saved-view controls appeared on Dashboard, Operations, and Planning.
- Guest, interview, and episode activity controls loaded the audit-event API.
- Duplicate review loaded ten legacy review groups and required a reason plus a
  destructive-action confirmation before merge.
- Operations displayed Today, Next 7 Days, Needs Confirmation, Booking Risks,
  Past, and Recently Completed queues; the editor remained collapsed by default.
- Planning displayed the 12-week calendar, all six backlog stages, owner and
  row-version fields, and the disposition-review queue.
- Arrow-key navigation moved Planning from Release Planning to Scheduling
  Intelligence and updated `?tab=scheduling_intelligence`.

## Accessibility and responsive matrix

| Surface | 390×844 | 768×1024 | 1440×900 | Duplicate IDs | Unlabelled visible controls |
|---|---|---|---|---:|---:|
| Dashboard | no horizontal overflow | pass | pass | 0 | 0 |
| Operations | no horizontal overflow | pass | pass | 0 | 0 |
| Planning | no horizontal overflow | pass | pass | 0 | 0 |

The 768px layout also acts as the effective-width check for 200% desktop zoom.
Reduced-motion and Windows forced-colors rules are present in `styles.css`; all
critical controls retain text labels rather than color-only meaning.

## Stored-XSS regression

The following canaries were submitted through real local UI forms:

- guest name containing an `img onerror` payload;
- interview guest name containing an `img onerror` payload;
- episode guest/title containing `img onerror` and `svg onload` payloads.

Before hardening, the Operations and Planning canaries executed. After escaping
card, editor, preview, recommendation, and generated-copy sinks, all three
rendered as literal text with zero injected `img`/`svg` nodes and no canary side
effect. `tests/test_static_xss_regression.py` protects the corrected sinks in CI.

## Runtime result

Final fresh-page smoke checks on all three private surfaces produced no new
console errors or warnings. Versioned assets used immutable caching; private API
responses used `no-store`.

## Final layout and interaction follow-up

After the shared hero/stat redesign, Dashboard, Operations, and Planning were
rechecked in the in-app browser at an actual 1010×1189 viewport using an
isolated copy of the tracked database. Planning also used three synthetic
episodes so every calendar state could be inspected without altering production.

- Dashboard rendered representative KPI and guest data, defaulted to Needs
  Review, exposed saved views, and opened the activity dialog with semantic
  dialog markup and keyboard close behavior.
- Operations rendered its compact four-KPI band and switched cleanly between
  Upcoming Interviews and Weekly Confirmations.
- Planning rendered released, scheduled, and readiness-risk dots; the risk dot
  opened a readable episode-details modal; episode-number descending order was
  503, 502, 501; and Scheduling Intelligence became the selected panel.
- All three pages reported zero positive horizontal overflow. Cross-workspace
  navigation succeeded.

The earlier 390px, 768px, and 1440px matrix covered the broader workspace work.
The final hero patch was visually recaptured at 1010px; its 1050px and 640px
breakpoints are additionally protected by static layout/accessibility contracts,
but were not re-screenshot at those exact widths in the final follow-up.

Final local gate: 297 Python tests and 4 Node tests passed, together with Ruff
undefined-name checks, Python compilation, JavaScript syntax checks, YAML parsing,
and `git diff --check`.
