# Review-only SQL drafts

**Current state (2026-11-17): Migrations 003/004 and all five SQL views are installed; the owner reports Patch 005 is installed and verified.** Migration 006 remains a review-only proposal and has not been executed. Live catalog inspection confirmed the candidate master/history exist and are empty. Production-plan view metadata is available, but plan rows fail with linked-server login-mapping error 7416. No candidate writes, DDL, or `dbo.PRESS` changes were made for Migration 006. The current authorized action is review/preflight only; the DBA must resolve the plan-source access and approve the backup/change-control path before deciding whether to execute 006.

- `001_omagmes_foundation.sql`: superseded incompatible foundation draft; **never apply**. Migration 003 is canonical.
- `001_validate.sql`: validator for the superseded 001 model; do not use for the selected 003 schema.
- `001_rollback.sql`: destructive rollback for the superseded 001 model; **never run against the existing OMAG database**.
- `002_production_day_and_shift_configuration.sql`: append-only configuration-history table proposal for Production Day Cutoff and independent Shift Schedule versions; contains no seeds.
- `002_validate.sql`: read-only catalog checks for the four configuration tables, ID/Rectime columns, foreign keys, and immutability triggers.
- `002_rollback.sql`: refuses to remove configuration history; no automated rollback is approved.
- `003_production_lot_workflow.sql`: historical Migration 003 source; it is already installed in OMAG and must not be rerun. It defines production identity/workflow schema with versioned standards and ID-based lifecycle links; no seed data.
- `003_preflight.sql`: SELECT-only check for Migration 003 prerequisites, expected types/key shape, and object-name collisions. It records the resolved decision to apply 003 only.
- `003_validate.sql`: read-only post-migration catalog checklist; the current deployment status is recorded in the handoff below.
- `003_rollback.sql`: destructive rollback draft that refuses when production/master rows exist; not approved or run.
- `004_press_diff_lot_acc_views.sql`: historical Migration 004 source for the installed candidate-window/audit tables and SQL-owned Daily Diff, Lot allocation, ACC, reconciliation, and summary views. Do not rerun it. `_QUALITY` is informational and does not gate Diff. The targeted installed-view patch is [005_press_daily_diff_quality_independent.sql](../patches/005_press_daily_diff_quality_independent.sql).
- `004_preflight.sql`: SELECT-only pre-deployment checks for target identity, Migration 002/003 prerequisites, object-name collisions, source columns/indexes, and SQL Server compatibility. A PASS is not deployment authorization.
- `004_validate.sql`: SELECT-only post-deployment catalog, dependency, view-definition, and smoke-query checks; it uses no table-variable INSERT.
- `004_rollback.sql`: destructive DBA-only rollback draft for Migration 004 objects; refuses when any quality-policy, candidate, or candidate-history rows exist. Not approved or run.
- `004_optional_reader_grants.sql`: separate SELECT-only grants for a dedicated Grafana principal; not part of schema deployment.
- `004_optional_candidate_grants.sql`: separately authorized candidate SELECT/INSERT/UPDATE and history SELECT/INSERT grants; no DELETE, quality-policy, or Official Lot writes.
- `../backend/tests/test_sql_migration_integration.py`: opt-in isolated integration suite retained for later non-LIVE use; it refuses the verified LIVE server. Do not configure or create a separate test database for this owner-directed deployment.

## Historical predeployment preflight (superseded after installation)

Historical, before Migration 003/004 installation: the SELECT-only preflights found the then-expected prerequisites and the `OMAG_MES` account lacked DDL permissions; those findings do not authorize or describe a current full migration. The installed-state and current permission check are recorded below. `dbo.PRESS` remains read-only and unmodified.

The bounded exact-tag read for `[2026-11-10 07:00, 2026-11-17 07:00)` returned 11,527 DropCnt rows, all quality 192, integer/nonnegative values and non-NULL timestamps; 27 decreases and 684 unchanged adjacent readings were observed, with a maximum adjacent gap of 1,201 seconds. There were no duplicate timestamps in the bounded window. This does not approve quality code 192, verify timestamp timezone/writer semantics, establish reset causes, certify production totals, or demonstrate full-history view performance. The source has no supporting tag/time index, so the proposed full-history LAG views require explicit DBA query-cost review. No quality policy was seeded and no live object/data was changed. Workspace review found Kepware Data Logger documentation but no writer configuration proving `_TIMESTAMP` timezone or `_QUALITY` encoding; see [the quality and timestamp policy proposal](../../docs/OmagMES_Press_Quality_and_Timestamp_Policy.md).

## Historical full-migration checklist — DO NOT USE; migrations are installed

1. **Backup:** Historical requirement for the superseded full-migration sequence; this checklist is archival and is not the current patch procedure.
2. **Preflight:** reconfirm `SCGLS-NK\\SQLEXPRESS` / `OMAG`, run `003_preflight.sql` then `004_preflight.sql` as the authorized account, and inspect all object-name collisions. Preserve Migration 002 and all unrelated database objects. Stop on any unexpected object, dependency, or permission.
3. **Canonical foundation:** do not run 001 or re-run 002. Apply only `003_production_lot_workflow.sql`; this owner-selected design covers the confirmed Product Code/standard, Product-Color Lot boundary, shift/date identity and Lot numbering requirements. No historic OmagMES transaction migration is required.
4. **Validate 003:** run `003_validate.sql`; confirm every table, type, FK, unique key and index assertion; inspect existing object inventory before proceeding.
5. **Migration 004:** rerun `004_preflight.sql`, then apply `004_press_diff_lot_acc_views.sql` in SQLCMD mode on one connection with stop-on-error. It creates only `omagmes` objects and grants SELECT on the five views to `OMAG_MES`; it must not alter `dbo.PRESS` or other legacy objects.
6. **Validate view runtime:** run `004_validate.sql` and separate read-only SELECTs for all five views, plus the documented Grafana query. Confirm view dependencies compile and source values/timestamps are preserved. Inspect actual query IO/plan; stop if performance is unacceptable.
7. **Diff behavior:** `_QUALITY` is informational only by owner decision. Do not create or populate `PressDiffQualityPolicy` to make Diff work. The targeted 005 patch makes an increase count, unchanged/reset yield zero, and missing/invalid values remain explicit. Verify current-sample allocation and reset-aware ACC using existing source rows and approved windows; do not alter source history.
8. **Temporary candidate tests:** only if separately approved, create uniquely tagged candidate windows within one explicit transaction, query the five views, then `ROLLBACK` the transaction. `_QUALITY` approval is not needed for Diff. This is the cleanup procedure: no test candidate/history row may be committed; verify the unique test keys are absent afterward. Never delete by broad date/status and never touch official Lots or unrelated rows.
9. **Permissions:** 004 grants view SELECT to `OMAG_MES`. Grafana principal is not yet identified; do not run `004_optional_reader_grants.sql` until DBA confirms its exact database principal. Candidate DML grants are not needed for a rollback-only DBA fixture; do not run optional candidate grants. Keep Official Lot SAVE disabled.
10. **Application verification:** after view runtime validation, run backend tests and frontend build; enable no candidate sync or official Lot write gate as part of this deployment.

Historical, before Migration 003/004 installation: the then-connected `OMAG_MES` account lacked DDL permission and no full backup was found in SQL Server history. That full-migration sequence is superseded; do not reinstall 003/004. Patch 005 has since been reported installed and verified by the owner; see the current Migration 006 review-only procedure below. No new database is to be created.

The above full-migration checklist and predeployment paragraphs are archival only; they do not apply to the current single-view change. Do not rerun migrations 003/004, preflights, grants, or rollback scripts for this request. No secrets are recorded in this README.

No product, standard, color, reason, shift, equipment, user, or mould master data is seeded. Migration 002's bootstrap is already present and must be preserved, not rerun. Installed Migration 003 is canonical for official Lot numbering and reset-review evidence; it includes SCG LotNo/date/shift/sequence/machine fields, unique sequence-scope state, and an ID-first `AutoLotResetReview` link. Sequence allocation locks one unique Production Date/Shift scope, uses 01–99 with no wrap. The 06:00–08:00 interval is explicitly unassigned; timezone/writer semantics, authenticated actor, Product/Color/master readiness, source-event durability, and Mould assignment/trace remain open. The factory's current SCG suffix is Block-only `B` (not `F`). Production writes and `OFFICIAL_LOT_NUMBERING_READY` remain hard-disabled. No Lot/test data was written as part of this Press Diff task.

Migration 004 extends only the OmagMES-owned schema. Its SQL views are the sole DropCnt Daily Diff, effective-window allocation, PressQty, and Lot ACC authority; Python does not provide a Diff/ACC fallback. Exact-tag matching is binary; SQL `datetime` source precision is preserved as `datetime2(7)`; null-timestamp rows are excluded. Counter values must be nonnegative integers in `bigint` range. `_QUALITY` is informational and never suppresses Diff. A positive Diff is allocated using the **current sample timestamp** in `[StartTime, EndTime)`; the previous sample may be in another Lot. Overlapping windows of the same identity type are ambiguous and receive no Drops; one official Lot takes precedence over candidate windows. Operator-entered boundaries are minute-precision, while unedited Auto Lot suggestions retain source precision. The summary view exposes original suggestions separately from effective boundaries. The legacy `PressDiffQualityPolicy` table, if present, is dormant and must not be dropped or consulted. The targeted [005 view patch](../patches/005_press_daily_diff_quality_independent.sql) alters only `v_PressDailyDiff`; it preserves other views and objects. Candidate synchronization and Official Lot SAVE remain independently disabled. Grafana examples are in [grafana_press_lot_queries.sql](../../docs/grafana_press_lot_queries.sql).

## Current configuration deployment status

The predeployment statements above describe historical status; migrations 003/004 are now installed and must not be rerun. Separately, after owner authorization, `../002_omagmes_configuration.sql` was applied to the verified `OMAG` database and its initial cutoff/schedule seeds plus API-created verification versions were confirmed after backend restart. See [the deployment record](../../docs/OmagMES_Development_Progress.md#sql-backed-production-day-cutoff-and-shift-time--deployment-verification-2026-11-10). Do not execute the review-only drafts as a substitute for that bootstrap or to alter the live configuration.

**Current state (2026-11-17): Migrations 003/004 and the 005 quality-independent view patch are installed per owner confirmation.** The candidate tables are empty; 006 has not been run. `PressDiffQualityPolicy` remains untouched/dormant. The 005 deployment procedure below is retained as historical reference only.

## Historical Patch 005 procedure — already completed per owner confirmation

Migration 003/004 are already installed; do not reinstall either migration. For this request, the exact change is only `db/patches/005_press_daily_diff_quality_independent.sql`:

1. Verify the SSMS connection is `SCGLS-NK\\SQLEXPRESS`, database `OMAG`, using the authorized DDL identity.
2. Confirm `dbo.PRESS` remains read-only and `omagmes.v_PressDailyDiff` exists; do not run any migration, grant script, rollback, or table DDL.
3. Run the exact 005 script in SSMS. It contains a target guard and one `CREATE OR ALTER VIEW omagmes.v_PressDailyDiff`; it does not depend on SQLCMD mode.
4. Check the SSMS Messages pane for errors, then run `004_validate.sql`. It verifies there is no policy dependency and returns counter-pair samples.
5. Verify the existing `201→202` pair yields Diff 1, equal values yield 0, reset rows yield 0 with `ResetDetected=1`, and arbitrary `_QUALITY` values do not change these results. Confirm Lot allocation still uses the current sample time and ACC remains reset-aware.
6. This procedure is historical. The owner now reports Patch 005 is installed and verified; do not rerun it as part of Migration 006.

Patch 005 is already completed per owner confirmation. No data fixtures were inserted by that patch.

## Migration 006 — review-only DBA procedure

Migration 006 is **not installed or authorized**. It reuses the installed candidate master/history, adds plan-snapshot and full-state audit fields, and creates a provisional SQL detector view over `v_PressDailyDiff`. It does not create another candidate master, write candidates, alter official Lots, or modify `dbo.PRESS`. Candidate DML requires the explicit `OMAGMES_AUTOLOT_SYNC_ENABLED` setting; official Lot SAVE remains separate and disabled.

1. As `OMAG_MES`, run [006_preflight.sql](006_preflight.sql) read-only against `SCGLS-NK\\SQLEXPRESS` / `OMAG`. Confirm installed objects, empty candidate/history tables, no 006 collisions, expected scoped permissions, and unchanged `dbo.PRESS`. Stop on any mismatch.
2. Separately test `dbo.vw_OmagPlan` row access under the approved source identity. The current linked-server error 7416 means plan rows are unavailable; do not infer rows or change the synonym/view. An authorized DBA must resolve the linked-server login mapping under its own change control. Plan assignment stays fail-closed until exact source rows are readable.
3. Before any DDL, obtain DBA review, approved backup/change control, and explicit authorization. Verify the same target/database in SSMS. Run only [006_autolot_plan_audit_view.sql](006_autolot_plan_audit_view.sql) in SQLCMD mode on one connection with stop-on-error enabled; never run it from application code or with `OMAG_MES`.
4. On that same connection, inspect all Messages and run [006_validate.sql](006_validate.sql). Confirm the new fields/view, candidate and history counts, reset-only provisional detector rows, SQL Lot ACC output, and no dependency from Daily Diff to `PressDiffQualityPolicy`. Plan-row access is a separate check and is not included in validation.
5. Do not enable `OMAGMES_AUTOLOT_SYNC_ENABLED` until migration validation, scoped candidate DML grants, actor/audit policy, and factory acceptance are complete. GET routes remain read-only; synchronization is an explicit POST. Candidate ACC/PressQty remain SQL-view outputs; an official Lot row is not required for candidate ACC.
6. [006_rollback.sql](006_rollback.sql) is a DBA-only emergency draft, not a routine rollback. It refuses if AUTO rows, plan snapshots, operator-confirmed boundaries, or non-legacy audit history exist. Never manually delete candidate/history rows to force the guard through.

Implementation limits: the SQL detector proposes counter-reset epochs only; it does not infer a Product/Color change, AutoRun state, actual boundary, or planned-start-as-actual-start. Operators must explicitly edit/confirm boundaries and classify Product/Color. MaterialCode maps only by exact, case-sensitive ProductCode match; Color is never derived. A content fingerprint is a captured snapshot key, not an external plan row ID. No live plan rows were available to validate this mapping.

## Linked-server 7416 investigation — 2026-11-17

**Read-only diagnosis; no linked-server security, credentials, views, or legacy tables were changed.** The application's configured connection was opened through `SQLServerReadOnlyRepository` and verified as `ORIGINAL_LOGIN()=OMAG_MES`, `SUSER_SNAME()=OMAG_MES`, `USER_NAME()=OMAG_MES`, database `OMAG`, server `SCGLS-NK\SQLEXPRESS`, instance `SQLEXPRESS`, `IS_SRVROLEMEMBER('sysadmin')=0`. On this local server, `HAS_PERMS_BY_NAME` returned SELECT=1 for both `dbo.vw_OmagPlan` and synonym `dbo.OmagPlan`; the application login is not sysadmin. Thus local SELECT is granted and is not the 7416 cause.

- Local catalog confirms `dbo.OmagPlan` is a synonym for `[172.18.8.139].[PIS].[dbo].[vw_ActivePlan]`; linked server `172.18.8.139` exists. Selecting either `dbo.OmagPlan` directly or `dbo.vw_OmagPlan` as the application's actual login reproduces SQL Server error 7416: “Access to the remote server is denied because no login-mapping exists.” The application’s `production_plan_snapshots()` query reproduces the same error. `sa` success in SSMS is consistent with `sa` having a different linked-server security context; it does not validate `OMAG_MES` access.
- The plan view exposes 29 columns and matches the application's inspected column contract. `OMAG_MES` has no `VIEW DEFINITION` permission for `dbo.vw_OmagPlan`; `OBJECT_DEFINITION` is NULL and dependency metadata functions return no visible rows. Therefore the exact local view text and its internal reference cannot be verified under the app login. The synonym's remote target and the direct synonym 7416 failure are confirmed; an authorized DBA must inspect the view definition using an approved metadata-visible account. The linked-login catalog query also returned no visible rows to `OMAG_MES`; do not treat that result as a complete server-level mapping inventory.
- Read-only [006_preflight.sql](006_preflight.sql) was executed through the application connection. It confirmed the five required installed objects, 29 plan columns, zero candidate/history rows (no grouped candidate counts), no 006 view/column/index/default-name collisions, and `ALTER=0` for the application login. This is a structural preflight PASS for DBA review, not authorization or proof that `OMAG_MES` can deploy DDL. Plan-row access remains blocked, and the 006 deployment guard must still be reviewed by the DBA.

### Minimum DBA-side remediation proposal — not executed

First, as an authorized DBA with linked-server security metadata visibility, inspect existing mappings and the exact `dbo.vw_OmagPlan` definition. If there is no explicit mapping for `OMAG_MES`, the narrow fix is one local-login mapping for `OMAG_MES` on linked server `172.18.8.139` to an **existing, dedicated remote login** that has only the required SELECT access to `[PIS].[dbo].[vw_ActivePlan]`. Do not map the application to remote `sa`, grant sysadmin, create a global/default mapping, change any password, or overwrite an existing mapping without separate review. Supply the existing remote credential only through the DBA's approved secure process; never put it in this repository or send it to the application.

The following is a guarded SSMS template, **not an instruction to run without DBA approval**. Replace both placeholders in the DBA's secure execution session; the script deliberately stops rather than replacing an existing explicit mapping:

```sql
USE [master];
GO
DECLARE @LinkedServer sysname = N'172.18.8.139';
DECLARE @LocalLogin sysname = N'OMAG_MES';

IF NOT EXISTS (SELECT 1 FROM sys.servers WHERE name = @LinkedServer AND is_linked = 1)
	THROW 53700, 'Expected linked server is missing; stop and inspect.', 1;
IF SUSER_ID(@LocalLogin) IS NULL
	THROW 53701, 'Expected local login is missing; stop and inspect.', 1;
IF EXISTS (
	SELECT 1
	FROM sys.linked_logins
	WHERE server_id = (SELECT server_id FROM sys.servers WHERE name = @LinkedServer)
	  AND local_principal_id = SUSER_ID(@LocalLogin)
)
	THROW 53702, 'An explicit mapping already exists; inspect it rather than overwriting it.', 1;

EXEC master.dbo.sp_addlinkedsrvlogin
	@rmtsrvname = @LinkedServer,
	@useself = N'False',
	@locallogin = @LocalLogin,
	@rmtuser = N'<existing_remote_read_only_login>',
	@rmtpassword = N'<enter_existing_secret_via_DBA_secure_process>';
GO
```

If the mapped remote principal lacks access, a remote DBA should grant SELECT on that exact remote view only after confirming the remote database user; do not broaden access to all of `PIS` or change the view. After the approved mapping is applied, verify `SELECT TOP (1) MaterialCode,MaterialName,StartTime,PlanCount FROM dbo.vw_OmagPlan` and the application's `production_plan_snapshots()` using the same actual `OMAG_MES` connection. Then rerun [006_preflight.sql](006_preflight.sql). None of these post-remediation checks can be reported as passed until the DBA change is made; no security change was executed in this investigation.
