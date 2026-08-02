# Scale gate and PostgreSQL decision record

SQLite remains the supported store while this service has one application
process and one outbox worker. Review the gate monthly and before adding another
web or worker replica.

Move to PostgreSQL when any two capacity signals or any one recovery signal is
breached for two consecutive review periods:

| Signal | SQLite operating limit |
|---|---:|
| Concurrent writers (p95) | 2 |
| Database lock wait (p95) | 250 ms |
| Sustained writes | 10/second |
| Web/worker processes | 1 writer process |
| Online backup duration | 5 minutes |
| Database size | 5 GB |
| Recovery point objective | 24 hours |
| Recovery time objective | 30 minutes |

The current app does not collect evidence that these gates are breached, so a
production PostgreSQL migration is deliberately not authorized yet. When it is:

Run `guest-manager scale-report --db guest_database.db` during each monthly
review to capture database size and a timed online-backup signal. Concurrency,
lock-wait, write-rate, topology, RPO, and RTO still require production telemetry
and an owner sign-off; the command intentionally cannot authorize migration by
itself.

1. Freeze schema changes and take a verified SQLite backup.
2. Create PostgreSQL tables from the migration ledger, mapping SQLite booleans
   to `boolean`, autoincrement keys to identity columns, and timestamps to
   `timestamptz`.
3. Copy parent tables before children in this order: guests, applications,
   interviews, episodes, outbox, attempts, proposals, audit events.
4. Reconcile row counts, foreign keys, normalized identities, lifecycle states,
   and a sample of before/after JSON events.
5. Run the full contract suite against PostgreSQL in staging, then rehearse
   cutover and rollback. Do not dual-write until reconciliation is automated.
6. Cut over during a write pause. Keep the SQLite backup read-only until the
   rollback window closes.

The migration is considered rehearsed only when staging meets the same integrity,
backup/restore, worker recovery, API, and browser gates as SQLite. A local SQL
translation alone is not a rehearsal.
