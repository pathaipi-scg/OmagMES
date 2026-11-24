# OmagMES database readiness — 2026-11-17

## Executive result

The live database is reachable read-only as the intended application SQL identity. The installed base OmagMES production schema is present, but the schema additions required for audited production-entry writes are not installed. No DDL or DML was executed during this inspection. Operational writes remain hard-disabled in application code.

## Live target and identity

Read-only catalog verification returned:

- Server: `SCGLS-NK\\SQLEXPRESS` (`SQLEXPRESS` instance)
- Database: `OMAG`
- `ORIGINAL_LOGIN()` / `SUSER_SNAME()` / database user: `OMAG_MES`
- `IS_SRVROLEMEMBER('sysadmin')`: `0`
- `HAS_PERMS_BY_NAME('omagmes','SCHEMA','ALTER')`: `0`
- Effective `omagmes` SELECT/INSERT/UPDATE/DELETE: `1`
- Database role membership observed: `db_datareader` only
- Explicit schema permissions currently present for `OMAG_MES`: GRANT DELETE, INSERT, UPDATE on `omagmes`
- Database user maps to the matching server login SID.

The proposed deployment script revokes `OMAG_MES` direct schema/table-wide DML and grants only the object-scoped DML needed by current SQL-backed production workflows. It does not grant ALTER or sysadmin. Existing read permissions/roles are preserved; broad SELECT scope should be reviewed separately.

## Installed schema compared with migration 007

The 13 base objects required by Migration 003 and referenced by current workflow code are present. Catalog inspection also confirmed the prerequisite Shift and Production Day configuration objects.

The following five Migration 007 tables are **missing**:

- `omagmes.ProductionEntryChangeHistory`
- `omagmes.WetRejectReason`
- `omagmes.WetRejectEntry`
- `omagmes.Mould`
- `omagmes.MouldHistory`

The following Migration 007 columns are **missing**:

- `omagmes.ProductionEntry.IsDeleted`
- `omagmes.ProductionEntry.DeletedAt`
- `omagmes.ProductionEntry.DeletedBy`
- `omagmes.ProductionEntry.DeleteReason`
- `omagmes.ProductionEntry.OperatorConfirmed`
- `omagmes.CuringInputEntry.OperatorConfirmed`

The original [007_operator_production_audit.sql](../db/migrations/007_operator_production_audit.sql) is a draft with all-or-none collision checks, not a safe rerunnable repair for partial deployment. Do not execute it as-is. The replacement DBA-review script is [007_operator_production_audit_deploy.sql](../db/admin-review/007_operator_production_audit_deploy.sql). It is additive, transactional, rerunnable for its own completed schema, checks existing metadata/constraints/defaults, stops on incompatible partial objects, and performs no master-data seeding.

## Data state observed

A fresh read-only count query showed zero rows in the base Product, Product Standard, Run, Lot, production entry/correction, Curing, Depallet, Dispatch, Lot Number Sequence, and Auto Lot Reset Review tables. Shift/configuration data exists (2 Shift rows, 4 schedule rows, 2 schedule versions, 2 cutoff versions). No 007 master or audit table exists yet. The zero-count result is consistent with the owner’s statement that OmagMES has never been used in production; no history migration is required.

## PIS Linked Server

A fresh application-repository read succeeded from `OMAG.dbo.vw_OmagPlan` with the exact filters `Company=SCGLS`, `Machine=OMAG`, `Plant=3251`. It returned **104** snapshots, was not truncated at the 1,000-row cap, and reported the expected view source. The live Edit Log page rendered those 104 plan rows even while the production schema was incomplete. PIS remains read-only and separate from saved production entries.

## Write enablement and audit identity

Application `OMAG_MES` must not run schema DDL. Schema deployment remains a separate DBA task, and the service login needs only scoped object DML, not ALTER or sysadmin. Per the confirmed operating decision, there is no application authentication or authorization requirement. The code-level auth gate and the `OMAGMES_PRODUCTION_WRITES_ENABLED` authorization switch have been removed. SQL writes proceed through verified target identity, schema readiness, SQL permissions, and real transactions; unavailable SQL or missing schema still fails closed.

Any name entered for `EnteredBy`/`ChangedBy` is user-supplied text and is not verified. The UI labels it unverified; no authenticated identity is claimed. Press/Curing/Delete confirmation controls confirm the submitted action/data and are not login checks.

The `Edit Log` supports audited Press quantity EDIT and soft DELETE in repository code. DELETE now requires server-validated explicit confirmation and a reason. Wet Run and Mould mutation routes have no SQL transaction implementation and now reject requests instead of saving to process-local mock storage. Depallet also fails closed outside its SQL-backed LIVE path. Candidate review/draft helpers remain explicitly provisional process-local features and must not be used as official production records.

## Test and deployment blockers

- Full backend suite after the no-auth write-gate change: **142 passed, 7 skipped**. The opt-in SQL integration tests require a separately provisioned disposable database and the `OMAG_MES` service login.
- Live Jinja smoke check: Production page rendered the schema warning with no SAVE form (HTTP 503); Edit Log rendered successfully (HTTP 200), displayed the schema warning, and rendered all **104** read-only PIS plan rows.
- No isolated SQL Server test database was provisioned during this task, so committed SAVE/EDIT/DELETE, rollback, and fresh-connection persistence have not been verified against a real SQL Server test dataset. Mock-cursor transaction tests cover atomic audit rollback, but they are not integration evidence.
- The deployment script is **not executed**. DBA must review it and verify post-deployment object metadata and effective permissions.
- Migration 007 creates empty Wet Reject Reason and Mould masters; owner-approved master data must be supplied separately before those workflows are useful.
- No real SQL transaction/reconnect test could run without the isolated database. Do not claim real SQL SAVE/EDIT/DELETE verification until that test setup is available and the DBA-reviewed deployment has been applied.
- React/Vite files remain until Jinja workflows are fully verified against the deployed schema on the isolated SQL test database.
