# Direct-Web Frontend Guide

This directory is framework-free HTML, CSS, and JavaScript served by `web_interface.py`.

## Page ownership

- `index.html` + `app.js`: Guest Dashboard.
- `operations.html` + `operations.js`: interview operations.
- `planning.html` + `planning.js` + `planning-sort.js`: release planning.
- `styles.css`: shared tokens and components.
- `operations.css`: Operations and Planning workspace components.
- `performance-utils.js`: shared request, caching, keyboard, and rendering helpers.

## UI rules

- Keep the three private workspaces visually consistent, but optimize information density for each workflow.
- Use semantic elements, explicit labels, `aria-live` only for changing status, dialog semantics, keyboard escape/close, and focus restoration.
- Construct untrusted dynamic content with safe DOM APIs or `escapeHtml`; never interpolate stored guest or episode data unescaped.
- Keep working and published episode titles visually distinct.
- Preserve loading, empty, stale, permission, and error states.
- At roughly 1050px, workspace heroes stack and KPIs become horizontal bands. At 640px, stats use at most two columns and actions remain touch-sized.
- Avoid fixed heights for content cards. Use `align-items: start` so unequal grid children do not create dead space.
- Keep controls at least 44px high where practical and prevent positive horizontal page overflow.
- Version changed CSS/JS URLs in every HTML consumer.

## Verification

- Run `tests/test_static_accessibility.py`, `tests/test_static_xss_regression.py`, and relevant web integration tests.
- Run `node --check` for every changed script and `node --test tests/planning_sort.test.js` when sorting changes.
- Visually inspect Dashboard, Operations, and Planning with seeded/representative data—not only empty states.
- Exercise tabs, filters/sorts, modal open/close/focus, calendar details, and cross-workspace links.
- Do not send email, sync calendars, publish, or alter production data during visual QA.
