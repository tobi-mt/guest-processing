---
applyTo: "src/guest_database_manager/**/*.py,tests/**/*.py"
---

- Keep HTTP parsing/orchestration in `web_interface.py`, persistence in `database.py`, migrations in `schema_manager.py`, and lifecycle validation in `lifecycle.py`.
- Use parameterized SQL and the shared connection helpers. Preserve foreign-key enforcement and transactional migrations.
- Never use episode number alone as identity; never collapse submission history into a guest record.
- Test conflicts, retries/idempotency, invalid transitions, legacy migrations, and rollback-sensitive changes.
- Use temporary database fixtures; do not write to `guest_database.db`.
