# Contributing

## Before changing code

Read `AGENTS.md` and the nearest nested guide. Search for the owning implementation and existing regression tests before introducing a new abstraction.

Create changes on a focused branch. Never commit credentials, production exports, session material, temporary databases, screenshots containing private guest data, or generated caches.

## Development gate

Install with Python 3.12:

```bash
python -m pip install -e '.[dev]'
```

Before requesting review, run:

```bash
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

Use a temporary copy of `guest_database.db` for migrations and local browser QA.

## Pull requests

Keep pull requests cohesive. Describe the user outcome, data/migration impact, security and side-effect impact, tests run, visual QA, rollback path, and any deliberately deferred work. Include screenshots only with synthetic or redacted data.

Do not combine a production data remediation or external send/sync operation with an application-code pull request.
