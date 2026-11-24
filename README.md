# OmagMES

OmagMES is a FastAPI application with server-rendered Jinja2 pages, static CSS/JavaScript, and SQL Server persistence in the `OMAG` database. The application SQL service identity is `OMAG_MES`; it is not an operator account and must never be granted `sysadmin` or `ALTER`.

## Operating model

- No application login, user-management system, authentication, or authorization middleware is used. Values entered into operator-label fields are user-supplied and unverified; they are audit context, not proof of identity.
- Production SAVE, EDIT, and soft DELETE use real SQL transactions and audit history. Operational writes never fall back to process-local mock storage.
- Writes fail closed if SQL target checks, schema-readiness checks, or database permissions fail. Do not configure the application to use `sa`.
- Database schema deployment is separate from application startup and must be performed by an authorized administrator. Review [the database readiness report](docs/database-readiness-2026-11-17.md) and [the idempotent Migration 007 deployment script](db/admin-review/007_operator_production_audit_deploy.sql) before applying schema changes.
- `OMAG.dbo.vw_OmagPlan` is queried read-only for PIS plan snapshots. Refreshing PIS never writes or replaces Production Entries.
- React/Vite files remain as legacy material during migration; the launcher starts FastAPI/Jinja. Remove the old frontend only after SQL-backed Jinja workflows pass isolated integration verification.

## Run locally (Windows)

Configure the Python environment and approved SQL connection settings in the local `.env` file. Do not commit credentials. Then start the application with `run_omagmes.bat`. It launches FastAPI on the configured application port, bound to all interfaces, following the FittingMES deployment pattern. Because there is no application authentication, expose it only to the intended trusted network and apply appropriate network controls.

The runtime must connect as `OMAG_MES` to the verified SQL Server instance and `OMAG` database. Do not run schema DDL from the application or its startup script.

## Validate

Run the backend suite from the repository root with the workspace virtual environment:

`\.venv\Scripts\python.exe -m pytest -q backend/tests`

Real SQL integration tests are opt-in. Use a disposable isolated SQL Server test database and follow [the SQL integration test instructions](docs/sql-integration-tests.md); never point integration tests at operational `OMAG`.

## Current status

The live database inspection found the base production schema but not the Migration 007 audit/delete, Wet Reject, and Mould objects. The runtime correctly keeps production forms unavailable until required schema is present. No historical transaction migration is needed because OmagMES has not been used in production. Real SQL SAVE/EDIT/DELETE and reconnect-persistence testing remains pending an isolated test database and DBA deployment.