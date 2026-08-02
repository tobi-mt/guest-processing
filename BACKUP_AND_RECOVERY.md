# Backup and recovery runbook

Run these steps before every schema migration, bulk repair, or production import.

1. Stop or drain background workers and prevent new writes.
2. Run `guest-database-manager integrity --db /path/to/guest_database.db` and save
   the JSON report with the release evidence.
3. Run `guest-database-manager verify-backup --db /path/to/guest_database.db`.
   This creates a temporary SQLite backup, restores it into a second temporary
   database, runs `PRAGMA integrity_check`, and compares row counts.
4. Generate the normal downloadable system backup and copy it outside the Railway
   volume. Record its timestamp, size, and responsible operator.
5. Apply the migration to a restored copy first and run the full automated suite.
6. Apply the production migration only after the rehearsal passes.
7. Run integrity, application smoke tests, and representative read/write checks.

## Rollback

If verification fails, stop application writes, retain the failed database for
forensics, restore the pre-change database to a new path, run the integrity and
backup-verification commands against it, and only then switch the application to
the verified restored file. Never overwrite the sole backup in place.
