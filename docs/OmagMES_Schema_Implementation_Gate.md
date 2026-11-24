# OmagMES Schema Implementation Gate

**Prepared:** 2026-11-08; status refreshed 2026-11-17
**Current status:** The factory owner explicitly directed applying Migrations 003/004 directly to existing `SCGLS-NK\SQLEXPRESS` / `OMAG`; no separate test database. Migration 003 is canonical and 001 is superseded. Execution is blocked because the verified `OMAG_MES` identity has no DDL permissions and no full-backup record was found in `msdb`. No migration or DML was executed. See [the deployment handoff](../db/review-only/README.md).
**Safety boundary:** New objects belong only in `OMAG.omagmes`; `OMAG.dbo.PRESS` and all other legacy objects remain strictly read-only. Do not bypass SQL permissions or execute a migration until a DBA verifies a restorable backup and uses an authorized DDL identity.

## 1. Current connection and permission finding

The current application connection was verified by SQL Server as `SCGLS-NK\SQLEXPRESS`, instance `SQLEXPRESS`, database `OMAG`, login/user `OMAG_MES`. Credentials were not displayed or changed. The login is not sysadmin and is not a member of `db_owner` or `db_ddladmin`; database `CREATE TABLE`, `ALTER ANY SCHEMA`, `CREATE VIEW`, and `omagmes` schema `ALTER` checks all returned false. It has SELECT but no INSERT/UPDATE/DELETE/ALTER/CONTROL on `dbo.PRESS`. This is not a DDL identity. The database is ONLINE, writable, SIMPLE recovery, compatibility 170. Queryable `msdb` history showed no recorded full backup. No DDL, DML, or backup was attempted. Historical credential observations in older sections are not current; use this status and the deployment handoff.

## 2. Schema-critical review questions

| Topic | Known rule / safe prototype behavior | Required before production schema or integration |
|---|---|---|
| Product identity | Exact Product Code; immutable Product ID; no code normalization, suffix stripping, alias inference, or unapproved CSV seed. | Approved authoritative Product master; case-sensitive comparison/collation; code assignment/effective-date and code reuse policy. |
| Standard revisions | Product owns positive integer Pieces/Drop and positive decimal seconds/Drop; conflicting source numbers remain blank/unapproved. | Approved sources and numeric values, decimal precision, approvers, revision/effective-date rules, and how an open Run/Lot handles a mid-context change. |
| Run/Lot transitions | Product change => new Run + Lot; Color change => new Lot; shift/day/pause/Mould change alone => no boundary. Lot ID immutable; LotName duplicate/editable with audit. | Run open/close/reopen and correction semantics; nullable Color policy; authorization for LotName edits; authenticated user identity. |
| Production entries | AutoCal is suggestion-only; explicit review and SAVE; Drops and Pieces distinct. Mock backend only. | Production quantity grain/categories/units, edit/reversal and audit requirements, shift/work-date policy. |
| `product_count` | Wet `line='wet'` values are individual tray Pieces; preserve timestamp/identity and do not infer missing data. | Approved source access; timestamp timezone; stable source key; duplicate/correction/latency policy; Lot attribution and changeover conveyor delay. |
| ProductCnt / accumulator | Cumulative Drops; daily Asia/Bangkok reset at 07:00 is owner-confirmed; `CYC` is not quantity. Preserve raw values and uncertainty. | Actual source identity, reset observations, timezone, quality semantics, gap threshold, late-arrival/replay behavior, and whether daily reset is supplied as a known event or must be verified. |
| Wet Reject | Dynamic `cntR*` quantity counters only; exclude `R*` button states; AutoCal proposal, operator review, explicit SAVE. | Actual `REJECT_WET` source tag/reason mapping, authoritative reason master, reset and unknown-counter handling. |
| Wet Run Log | Manual event classification; AutoRun is evidence only and cannot overwrite operator classification. | Event schema and interval overlap, categories, planned/operating-time rules, edit/correction authorization, timezone/shift boundaries. |
| Wet OEE | Simulation only; formulas use Drops, Product standards, Wet camera Pieces, and manually classified Wet time. | Formula eligibility, time-window alignment, mixed-Product aggregation, missing/zero-denominator and above-100% policies, persistence/audit design. |
| Curing / Depallet | Multiple operations may reference original immutable Lot ID; prototype uses clearly labeled sample records only. | Event grain, quantities/units/times, partial transfers, reversals, actual master fields. Do not infer fields from summary sheets. |
| Mould | One Product per Mould; Color irrelevant; current age reset only on approved recondition return; lifetime age never resets. | Approved Mould register, event/boundary evidence, recondition workflow, counter attribution policy. |
| SQL namespace / permissions | No production DB usage in prototype. All API writes are in-memory mock state. | Verify owner-specified server, target DB/schema collision, login rights, approved source reads, backup/rollback, and deployment principal; do not inspect unrelated `dbo` objects. |

## 3. Drafting disposition

- A React/Vite UI and FastAPI API may be implemented against a deterministic, explicitly labeled in-memory mock repository. That work does not establish a production schema or allow database writes.
- Draft DDL may include only confirmed IDs, `Rectime`, approved relationships, and fields that have an owner-defined meaning. Any proposed unresolved field must be marked `REVIEW REQUIRED`, not hidden as a production decision.
- Review-only draft package now exists in [db/review-only](../db/review-only/README.md): version 001 foundation and version 002 cutoff/schedule DDL, catalog validation, and guarded rollback proposals. Static tests check ID/Rectime compliance and history retention; this does not validate T-SQL syntax or execute SQL Server.
- The draft includes no Product, standard, Color, reject-reason, shift, equipment, user, or Mould seed data. It is an initial table proposal, not a fully approved production schema; effective-period overlap, identity/authentication, update immutability, source-key semantics, event capture, permissions, and source/database alignment remain unresolved.
- Owner has resolved the Product/Run/Lot design in favor of Migration 003 based on the confirmed Product Code, standard revision, Color boundary, and SCG LotNo/date/shift/sequence requirements. Do not apply 001 or re-run the already deployed Migration 002.
- The owner has authorized the bounded 003/004 deployment to existing OMAG. Before DBA execution, verify a restorable backup, rerun read-only preflights, inspect every collision, and use an authorized DDL account. Do not create a separate test database or alter any legacy object. Current `OMAG_MES` cannot execute the migrations; the stop conditions are recorded in the deployment handoff.

## 4. Shared Production Date and Dynamic Shift Schedule gate

The React/FastAPI mock now has a shared date context and process-local dynamic schedule versions. This does **not** close any database or production-use gate.

### Configuration persistence proposal and deployment gate

- `Shift`: stable internal shift identity; never a Shift Name or Shift Code key.
- `ShiftScheduleVersion`: immutable version with `EffectiveFromProductionDate`; effective-to is the next version's effective date. The initial prototype's `2026-01-01` date is a placeholder, not factory confirmation.
- `ShiftScheduleShift`: ID-first membership linking a version to a stable Shift ID and versioned Name, Code, start/end local times, order and active state.
- `ProductionDayCutoffVersion`: independent immutable version with effective Production Date, 07:00 initial cutoff requirement, change reason and creation audit. Owner confirmed initial effective date 2026-11-10 for both initial cutoff and schedule bootstrap.
- Production facts: retain Production Date, schedule-version ID, versioned shift-row ID, and immutable snapshots only where approved. Preserve actual event time and `Rectime` independently.
- `AutoLotDraft` and `AutoLotDraftHistory`: provisional draft, selected date/version/shift, source references, raw vs operator-confirmed values and append-only correction/dismiss/review events. No automatic official Lot ID/No.

This paragraph's original “not applied” and failed-connection statements are historical and superseded by the verified Migration 002 deployment recorded below and in the current progress handoff. Preserve the existing configuration tables/history; do not rerun or roll them back during 003/004 deployment. Current 003/004 DDL and backup gates are in [the deployment handoff](../db/review-only/README.md).

### Mandatory unresolved checks before production integration

- Confirm the initial schedule's effective date, applicable timezone, whether operator times are plant-local, and exact historian `_TIMESTAMP` semantics. The prototype uses half-open `[start,end)` local clock intervals; this convention needs owner/DBA acceptance for production.
- Confirm authoritative Shift identities, unique Name/Code policy and audit actor/retention. Validate the date/version/shift FK and immutable production-history strategy against existing schema before DDL.
- Resolve Shift Code compatibility with the current official Lot No. Shift segment. Do not alter the Lot format or use arbitrary Shift Name as the number component.
- Operational Auto Lot/Lot creation remains disabled. The internal evidence-preview path is owner-authorized and limited to bounded exact-tag SELECTs; the SQL identity is not read-only. Before broader or deployed live access, require least-privilege credentials, acceptable bounded query cost, and factory confirmation of DropCnt timestamp/timezone/reset semantics and shift interval logic. No `CAST(_TIMESTAMP AS date)`-only filter.
- UI mock saves, Auto Lot draft fixtures and corrections remain process-local only; they neither write source observations nor create official Lots. Cutoff and schedule API persistence is designed for SQL Server but gated/unverified without safe settings, access-control implementation and approved bootstrap. No `.env` change, workbook import, FittingMES edit, migration execution, commit or push is permitted for this work.

### Deployment update — configuration settings bootstrap (2026-11-10)

The preceding status is historical and is superseded **only for Production Day Cutoff and Shift Schedule configuration**:

- The owner authorized app-owned configuration storage in `OMAG.omagmes`, confirmed initial effective date 2026-11-10, and authorized internal-development deployment. A read-only catalog check found no existing `omagmes` schema/tables before the change.
- The repeatable [configuration bootstrap script](../db/002_omagmes_configuration.sql) was executed and committed successfully against `OMAG`. It created four configuration tables, narrow role grants, constraints/indexes and append-only triggers; seeded the approved initial cutoff and two-shift schedule. It did not touch `OMAG.dbo` or any other application/source.
- Live API saves added unchanged, clearly labeled persistence-verification versions to both independent streams; SQL reads and a backend restart confirmed those versions persist. Details and exact values are recorded in [Development Progress](OmagMES_Development_Progress.md#sql-backed-production-day-cutoff-and-shift-time--deployment-verification-2026-11-10).
- The runtime enters a no-login SQL principal with object-level SELECT/INSERT grants, but the underlying Windows-integrated connection is still a broad owner identity; FastAPI/Vite save gates are loopback-only internal development controls, not user authentication or a production security boundary. Do not expose this configuration-write path to a shared network/production deployment without a dedicated least-privilege identity and authentication review.
- The review-only foundation SQL and other source integration/migration drafts remain unapplied. Product/Mould master, Auto Lot persistence, PLC/Kepware, historian, and legacy `dbo` integrations remain out of scope and disabled.
