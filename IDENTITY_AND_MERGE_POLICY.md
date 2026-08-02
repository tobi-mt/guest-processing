# Guest identity and merge policy

Guest identity is separate from each application. Email and name matching uses
Unicode-aware lowercase plus surrounding-whitespace removal; it does not rewrite
Gmail dots, aliases, domains, or social handles.

- An exact normalized email can attach a new submission to an existing active
  identity.
- A matching name without an exact email is a review signal, never proof of the
  same person.
- Blank and placeholder emails do not establish identity.
- A merge requires an administrator, a named survivor, a reason, and a shared
  normalized email or name.
- Merge moves applications, interviews, and episodes to the survivor. It retains
  the duplicate as a `merged` tombstone and appends an immutable audit event, so
  the operation remains explainable and recoverable from backup.
- Unmerge is intentionally not automated. Restore or corrective data work must
  be reviewed against the audit event and a verified backup.
