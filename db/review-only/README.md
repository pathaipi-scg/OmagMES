# Review-only SQL drafts

**These files are not deployment artifacts. They have not been executed, SQL Server-parsed, or approved.** No database connection was made during this session.

- `001_omagmes_foundation.sql`: forward DDL proposal, with OMAG database/schema preconditions and no seed records.
- `001_validate.sql`: read-only catalog checks for expected tables, ID/Rectime columns, PKs, and FKs.
- `001_rollback.sql`: destructive rollback proposal that refuses to proceed if any row exists in the `omagmes` schema.

Before any possible execution, resolve [the schema implementation gate](../../docs/OmagMES_Schema_Implementation_Gate.md), confirm the owner-specified SQL host `10.28.255.98` and target database `OMAG`, inspect only authorized target metadata under verified read-only access, receive database-owner/DBA approval, test against a disposable non-production database, and review backup/rollback. The existing project `.env` points elsewhere and was not changed or used for a connection.

No product, standard, color, reason, shift, equipment, user, or mould master data is seeded. The proposal's exact collation, status codes, date-time representation, optional Color, event details, approved standard interval overlap, concurrent transitions, and permission model are review items. In particular, Product standard numeric conflicts remain unapproved, there is no User Identity/authorization solution, and source observation key/timestamp semantics require verification. The API remains mock-only and does not use any of these scripts.
