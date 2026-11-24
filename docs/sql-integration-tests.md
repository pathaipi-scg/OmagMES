# Isolated SQL integration tests

`backend/tests/test_sql_production_integration.py` contains real SQL Server tests for committed Production SAVE, audited EDIT, soft DELETE, transaction rollback, and visibility after a fresh repository/connection is created. They are **opt-in** and are skipped in ordinary developer/test runs.

## Safety requirements

- Use a disposable, local SQL Server database whose name begins `OMAGMES_TEST_`. The suite refuses the production database name and non-local SQL endpoints.
- Prepare the database separately as an administrator with the reviewed 002/configuration, 003 production, 004/005/006 (only if required for a compatible schema), and 007 deployment objects. Do not have pytest apply DDL.
- Map the dedicated `OMAG_MES` SQL login to that test database; it must not be `sysadmin`. Apply only reviewed object-scoped runtime grants.
- Create one isolated Lot in the test database with a LotName beginning `IT-`, an approved Product Standard Revision, and valid Shift/Schedule references. The suite inserts entries under that Lot and soft-deletes them; it does not physically delete audit rows.
- Do not point these variables at the operational `OMAG` database. The suite requires explicit confirmation, a local endpoint, and an `OMAGMES_TEST_*` database name.

## Opt-in variables

Set these in the test process environment (do not commit credentials):

- `OMAGMES_TEST_SQL_CONFIRMATION=I_CONFIRM_ISOLATED_TEST_DATABASE`
- `OMAGMES_TEST_SQL_SERVER=localhost\SQLEXPRESS` (or `127.0.0.1` with an approved local instance/port)
- `OMAGMES_TEST_SQL_DATABASE=OMAGMES_TEST_<disposable-name>`
- `OMAGMES_TEST_SQL_DRIVER=<installed SQL Server ODBC driver name>`
- `OMAGMES_TEST_SQL_PASSWORD=<test OMAG_MES credential>`
- `OMAGMES_TEST_LOT_ID=<database ID of the IT- test Lot>`

The tests connect only with `OMAG_MES`. They do not accept an administrator or `sa` runtime identity. Without explicit configuration, both SQL integration tests are skipped. A fresh repository and connection is used to verify SQL persistence, which demonstrates persistence beyond a repository instance; it is not a full OS-process/server restart test.

The tests do not require or override an application authentication gate. Any actor label stored by the fixture is test-supplied text, not a verified identity. This is why the suite is limited to a separately provisioned disposable database and the dedicated `OMAG_MES` service login.
