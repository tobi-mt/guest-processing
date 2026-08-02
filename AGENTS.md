# Guest Processing Agent Guide

Use this file as the routing map. Read only the files relevant to the current change, plus the nearest nested `AGENTS.md`. Do not load every roadmap or audit document by default.

## Product and runtime

- The primary product is the authenticated direct web app served by `web_interface.py` at `/dashboard`, `/operations`, and `/planning`.
- `app.py` is the older Streamlit surface. Do not assume a direct-web change must also be duplicated there unless the request includes Streamlit.
- Production data is SQLite today. PostgreSQL work is gated by `SCALE_AND_POSTGRES.md`.
- Guest communication, calendar reconciliation, publication, destructive changes, and bulk disposition remain human-approved.

## Repository map

- `src/guest_database_manager/web_interface.py`: HTTP routes, API validation, service orchestration.
- `src/guest_database_manager/database.py`: persistence and transactional write boundaries.
- `src/guest_database_manager/schema_manager.py`: ordered, repeatable migrations.
- `src/guest_database_manager/lifecycle.py`: valid state transitions and optimistic concurrency.
- `src/guest_database_manager/security.py`: sessions, roles, CSRF, and security policy.
- `src/guest_database_manager/maintenance.py`: integrity, readiness, backup/restore checks.
- `src/guest_database_manager/metrics.py`: metric definitions and operational health.
- `src/guest_database_manager/static/`: direct-web HTML, CSS, and JavaScript; see its nested guide.
- `tests/`: maintained regression suite. Root-level `test_*.py` files are legacy compatibility tests but still run in the full suite.

## Non-negotiable invariants

- Never identify or merge episodes by episode number alone.
- Keep `working_title`, `published_title`, and transcript provenance separate. Transcript sync must be previewed and explicitly approved; it must not erase editorial metadata.
- Reads must not silently mutate lifecycle state.
- Route lifecycle writes through validation/transition boundaries and preserve optimistic-concurrency checks.
- Externally visible side effects require idempotency and outbox handling where supported.
- Preserve audit events, actor/source/reason, and correlation IDs for material transitions.
- Never use the tracked `guest_database.db` for destructive tests, migrations, or visual fixtures. Copy it to a temporary directory first.
- Do not expose secrets, guest payloads, session material, or raw exception details to clients or logs.

## Efficient workflow

1. Use `rg` to locate the owning route, database method, UI handler, and closest regression test.
2. Read the smallest relevant slice. Use `IMPLEMENTATION_TODO.md` only for roadmap status and the domain documents only when their subject is in scope.
3. Add or update a regression test with the change.
4. Run the narrow test first, then the full gate before handoff.
5. Report exact tests run and any untested production-only dependency. Never claim deployment or production verification from local results.

## Commands

```bash
python -m pip install -e '.[dev]'
pytest -q
ruff check --select F src tests
python -m compileall -q src tests
node --check src/guest_database_manager/static/app.js
node --check src/guest_database_manager/static/operations.js
node --check src/guest_database_manager/static/planning.js
node --check src/guest_database_manager/static/planning-sort.js
node --test tests/planning_sort.test.js
git diff --check
```

For local direct-web QA, use a temporary database and explicit test-only credentials:

```bash
qa_dir=$(mktemp -d)
cp guest_database.db "$qa_dir/guest_database.db"
MIRROR_TALK_DASHBOARD_USERNAME=codex \
MIRROR_TALK_DASHBOARD_PASSWORD=local-only \
MIRROR_TALK_DASHBOARD_SESSION_SECRET=local-only-secret \
PYTHONPATH=src python -c "from guest_database_manager.web_interface import run_web_interface; run_web_interface(port=8765, db_path='$qa_dir/guest_database.db', open_browser=False)"
```

## Definition of done

- Relevant narrow tests and the full suite pass.
- Migration changes are rehearsed on empty, current, and representative legacy copies and are rollback-safe.
- Data changes have backup/restore verification.
- UI changes are checked with real or seeded data, keyboard interaction, no horizontal overflow, and responsive rules.
- Static CSS/JS asset query versions are bumped when browser caching could hide the change.
- `git diff --check` passes and unrelated user changes remain untouched.

## Read only when relevant

- `IDENTITY_AND_MERGE_POLICY.md`: identity, deduplication, and merge behavior.
- `BACKUP_AND_RECOVERY.md`: migration, remediation, restore, and recovery work.
- `RELEASE_CHECKLIST.md`: pre-deploy and rollback gates.
- `SCALE_AND_POSTGRES.md`: persistence scaling decisions.
- `IMPLEMENTATION_TODO.md`: P0–P4 scope and acceptance status.
