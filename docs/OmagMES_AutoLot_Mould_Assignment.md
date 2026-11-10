# OmagMES Auto Lot, Production Plan, and Mould Assignment Workflow

**Prepared:** 2026-11-10
**Status:** Permanent implementation reference; requirements and code inspection plus an authorized SELECT-only SQL validation. Kepware mapping/configuration is factory-verified; the preferred SQL historian alias was independently observed. No feature implementation, SQL write, migration, workbook import, FittingMES edit, or commit/push was performed.

This document records the latest factory-confirmed workflow for automatic draft Lot detection, Production Plan assignment, and time-bounded Mould usage. It supplements—not replaces—the [factory requirements](OmagMES_Factory_Confirmed_Requirements.md) and [development handoff](OmagMES_Development_Progress.md). Where a rule is not yet defined, this document marks it **OPEN** rather than inferring behavior.

## 1. Database design skills read

Before database-related inspection, the applicable skills were located and read in full:

1. OmagMES: [OmagMES database design skill](../skill/DATABASE_ID_FIRST_DESIGN_SKILL.md).
2. FittingMES: [FittingMES database design skill](../../FittingMES/skill/DATABASE_ID_FIRST_DESIGN_SKILL.md).

Both require each new table to have `id bigint IDENTITY(1,1) NOT NULL PRIMARY KEY` and `Rectime datetime NOT NULL DEFAULT (GETDATE())`; relational references use authoritative IDs, not names or display codes. Business identifiers remain separate unique attributes. Existing `OMAG.dbo` objects and planning sources are read-only; any approved OmagMES writes must be confined to the `omagmes` schema. Existing schema, keys, constraints, and relationships must be audited before proposing new DDL. These conventions do not authorize a migration or database connection.

## 2. Factory-confirmed Kepware facts

The Kepware mapping and logger configuration below were supplied as factory-verified; they were not independently checked against the Kepware project. SQL historian observations are separately identified in Section 8.

### 2.1 PLC tag mapping

| Kepware tag | PLC address | Type | Scan rate | Meaning |
|---|---|---|---|---|
| `OMAG.PRESS.ProductCnt` | `DB3.DBW2` | Word | 100 ms | Press Drop counter |
| `OMAG.PRESS.OEE.DropCnt` | `DB3.DBW2` | Word | 100 ms | Same Press Drop counter; preferred SQL history for Auto Lot Detection |

The two names are Kepware organizational aliases of the same PLC value. Select the `DropCnt` alias for Auto Lot Detection. **Do not union, merge, or sum the histories for the two names.** Existing OmagMES source code reads the ProductCnt-named history; it must not be treated as already reading the preferred DropCnt history. The authorized SQL check below independently verified the exact persisted DropCnt `_NAME`, schema, timestamp/value/quality columns, and a small available history sample. The sample is too short to establish retention, timezone, reset behavior, or segmentation readiness.

Factory confirms the previous `ProductCnt` SQL logging was once per hour. The factory recently switched logging to `DropCnt`, stored whenever its value changes. The longer ProductCnt history and shorter DropCnt history are expected after this configuration change: ProductCnt is historical reference data only, while DropCnt is the authoritative historian source for **new Auto Lot Detection**. Use each row's SQL `_TIMESTAMP` to locate the recorded counter transition, subject to confirming timestamp/timezone semantics. Because logging is change-based, no row is generated while the value remains unchanged; absence of rows does not show that the press stopped or give a fixed-interval sample.

### 2.2 Data Logger configuration

Kepware Server 7 Data Logger -> PRESS contains `OMAG.PRESS.OEE.AutoRun`, `AutoStart`, `DropCnt`, `ResetProduction`, `StartProduction`, `StopProduction`, and `ElevatorFull`. PRESS Trigger1 is configured as:

- Log on Data Change: Yes.
- Log on Static Interval: No.
- Monitor Item: No.
- Deadband: None.

This is **change-based logging**, not fixed-interval sampling. Absence of SQL rows is not evidence that the machine stopped; do not infer machine state from silence. Do not change PLC or Kepware configuration.

## 3. Latest factory-confirmed workflow requirements

### 3.1 Automatically detected draft production records

- OmagMES must automatically detect draft production records (not yet official Production Lots) from the SQL-recorded PLC tag **`OMAG.PRESS.OEE.DropCnt`**.
- Detection must create a draft production record **before** an operator selects a Production Plan. A candidate segment can be based on counter activity and reset evidence; a reset alone does not prove a Product or Color change.
- The draft has a stable internal ID, detected start time, detected end time when available, raw PLC Drop count, operator-confirmed Drop count, and review status.
- Operators must be able to review a detected draft, correct its start/end times and Drop quantity, or delete/dismiss an invalid draft.
- Corrections and deletion apply to the OmagMES draft/review record only. They must **never update, delete, rewrite, or otherwise alter the raw PLC/source observations**.
- The draft is subject to operator review; automatic detection is not by itself approval of a production record or a source-data correction.
- Draft detection and official Production Lot numbering are separate. Do not assign an official Lot No. merely because a candidate segment was detected.

**SQL verification status:** Factory confirms `ProductCnt` and `DropCnt` are the same PLC address/counter. OmagMES currently queries only SQL `_NAME='OPC.OMAG.OMAG.PRESS.ProductCnt'`, which is historical reference data and is not the authoritative source for new Auto Lot Detection. A SELECT-only query verified DropCnt persists as `_NAME='OMAG.PRESS.OEE.DropCnt'` (without the `OPC.OMAG` prefix used by ProductCnt). Available DropCnt rows, quality, value progression, and the lack of a supporting tag/time index are summarized in Section 8. The shorter DropCnt history is expected following the recent logging switch, not evidence of missing historical DropCnt rows before that change. Timestamp semantics and the 07:00 reset behavior still require confirmation. Do not merge or sum aliases.

### 3.2 Production Plan assignment (after detection)

- After a draft is detected and reviewed, an operator may select a Production Plan. This order differs from FittingMES's plan-first Lot creation.
- Resolve the selected Plan's `MaterialCode` by an **exact match** to Product Master `ProductCode`.
- Use that Product's approved `StandardPiecesPerDrop` and `StandardCycleTimeSec` for the Lot's production context. Standards are Product-owned, never Mould-owned.
- A missing Product or pending/unapproved standard must remain visibly unresolved. Do not infer a Product from a similar name, a code prefix, or a mould description; do not invent, copy, or default standards.
- Store/retain the selected plan identity and the Product/standard revision or immutable standard snapshot used by the Lot so later plan/master edits do not silently rewrite history.

The exact plan identity fields, handling of multiple plan rows for one MaterialCode, and whether a discovered Product is previewed or immediately created as `Pending Standard` remain subject to the existing plan/Product-master decisions in the factory requirements.

### 3.3 Multiple Mould assignment intervals per Lot

- One Lot may contain multiple sequential Mould assignments, each represented by its own installation/usage interval.
- Replacing a Mould by itself does **not** create a new Lot when Product and Color are unchanged. Product or Color change remains a Lot boundary under the previously confirmed rules.
- An assignment must identify the immutable Lot ID, physical Mould ID, interval start/end, and Drops attributable to that interval. The factory's external Mould No. remains a business identifier, not the relational key.
- A Mould is eligible only for its associated Product and when its lifecycle status is production-ready. Mould availability is based on whether its assignment time interval overlaps another active assignment, **not** on a whole shift or the entirety of a Lot. A Mould may be reused after its earlier assignment interval has ended.
- Mould age uses **Press Drops only**, never Pieces. `CurrentAgeDrops` accumulates since the most recently approved return from reconditioning; only that approval resets it. `LifetimeAgeDrops` remains cumulative for the physical Mould's life. PLC resets are not Mould age resets.
- Allocate Drops to Moulds only where the verified observations and installation boundaries support the attribution. Do not assign a Lot's full count to every Mould used on that Lot. Missing or ambiguous boundaries/gaps remain explicitly uncertain/unallocated rather than being fabricated or proportionally interpolated.

### 3.4 Immutable source and audit boundary

Raw PLC observations are read-only source evidence. Draft detection, operator adjustments, plan assignment, Mould interval corrections, and invalid-draft deletion are application review events. Preserve the source observations and retain an auditable record of any draft correction or deletion, including previous/new values, actor, time, reason, and source references, subject to owner approval of authentication and retention policy. Never represent a local draft edit as a change to the PLC counter.

## 4. FittingMES implementation inspected (reference only)

Inspection was read-only and covered FittingMES UI/template code, route handlers, application services, SQL migration/view/procedure definitions available in the repository, and focused tests. No FittingMES files, database, or tests were changed/executed during this review. A passing test in the repository means behavior asserted against test doubles; it does not prove a live SQL Server procedure or schema.

### 4.1 Plan selection and Lot creation/reference

- The Production Plan selector, plan refresh, Lot creation form, replacement-plan selector, and per-Lot Production/Press/Mould controls are in [FittingMES/app/templates/production.html](../../FittingMES/app/templates/production.html#L170-L197) and [the Lot/Press tables and forms](../../FittingMES/app/templates/production.html#L226-L303).
- `production_page()` reads plans for the selected date, marks plans already used by active Lots, and resolves a selected plan. `mark_used()` and `choose_plan()` reject a plan already assigned to another active Lot. Plan replacement is routed through `save_plan()`. See [FittingMES/app/main.py](../../FittingMES/app/main.py#L607-L780) and [plan confirmation / choose / save handlers](../../FittingMES/app/main.py#L840-L918).
- Plan rows are read by [FittingMES/app/prod_api.py](../../FittingMES/app/prod_api.py#L1-L40), whose query uses `dbo.P_ActivePlan` and includes `PlanName`, `MaterialCode`, `MaterialName`, `PlanCount`, `StartTime`, `Shift`, and version/source fields. This is FittingMES's plan source, not evidence that OmagMES may query the same object.
- `confirm_mapping()` in [FittingMES/app/products.py](../../FittingMES/app/products.py#L45-L81) resolves a material prefix through `MaterialProductMap`; `production_page()` passes `MaterialCode[:8]` to that mapping. This is a prefix-to-Product mapping, not OmagMES's required exact full `MaterialCode` to `ProductCode` match. Do not copy the prefix mapping or its editable mapping behavior into OmagMES.
- `insert_lot()` and `update_lot()` in [FittingMES/app/lots.py](../../FittingMES/app/lots.py#L44-L116) and [FittingMES/app/lots.py](../../FittingMES/app/lots.py#L204-L241) use a transaction-owned Lot lock, validate plan availability/mapping, and retain Lot history. The `dbo` schema, FittingMES numbering, and its Lot rules are not portable to OmagMES.
- Focused Lot/plan tests, including `insert_lot()`, `update_lot()`, `delete_lot()`, `mark_used()`, and `choose_plan()`, are in [FittingMES/tests/test_production.py](../../FittingMES/tests/test_production.py). These are code-level reference tests; no test was run as part of this documentation task.

### 4.2 Mould UI, service, routes, lifecycle, and history

- [FittingMES/app/templates/mould.html](../../FittingMES/app/templates/mould.html#L1-L140) implements the compact filterable Mould list, selected Mould details, registration/edit forms, explicit lifecycle actions, and separate Status History, Recondition History, and Usage / Production History tables. Its inline JavaScript preserves filters, synchronizes a selected Product, and requires confirmation for lifecycle actions ([template script](../../FittingMES/app/templates/mould.html#L138-L220)).
- [FittingMES/app/mould.py](../../FittingMES/app/mould.py#L32-L114): `read_mould_list()` filters the list; `read_mould_detail()` reads status, recondition, and usage history; `page_context()` composes the page data. `register_mould()`, `update_mould_info()`, `send_to_recondition()`, `return_from_recondition()`, and `set_mould_status()` validate inputs and call dedicated stored procedures through `_run_mutation()` ([service mutations](../../FittingMES/app/mould.py#L119-L209)). The service edits name/remark but not Mould No. or Product.
- [FittingMES/app/main.py](../../FittingMES/app/main.py#L1876-L1994): `mould_page()`, `mould_register_route()`, `mould_edit_route()`, `mould_send_route()`, `mould_return_route()`, and `mould_status_route()` serve the page and lifecycle mutations.
- The FittingMES UI/service supports `ACTIVE`, `RECONDITION`, `RETIRED`, and `DENIED`; the production assignment validator accepts only `ACTIVE`. Dedicated send/return actions are separate from generic status change. The precise database-side lifecycle matrix, operator authentication, and actual status/recondition procedure behavior cannot be concluded from application calls alone.
- [FittingMES/tests/test_mould.py](../../FittingMES/tests/test_mould.py#L153-L265) asserts filtered list/detail queries, all three histories, name/remark-only edit, registration, mocked send/return and status actions, and rollback behavior. [FittingMES/tests/test_mould_ui.cjs](../../FittingMES/tests/test_mould_ui.cjs#L1-L95) asserts UI filter persistence, Product selection, and related behavior. These tests use fakes/mocks, not live DB execution.

### 4.3 Assignment interval, availability, and concurrency

- [FittingMES/app/templates/production.html](../../FittingMES/app/templates/production.html#L248-L303) exposes an Add Fitting / Edit Fitting row with Shift, Press, Mould, start/end, quantities, explicit SAVE, and release actions. A Lot can have multiple Press Production records, each with a Mould and its own time fields.
- `read_eligible_moulds()` in [FittingMES/app/press_production.py](../../FittingMES/app/press_production.py#L66-L110) filters by the Lot Product, marks non-`ACTIVE` tools unavailable, and checks availability against the requested interval. `_lock_and_validate_mould()` re-reads the Mould under `UPDLOCK,HOLDLOCK`, checks status and exact Product pair, and `_lock_allocation_keys()` takes transaction-owned application locks ([assignment validation/locks](../../FittingMES/app/press_production.py#L367-L514)).
- [FittingMES/app/resource_availability.py](../../FittingMES/app/resource_availability.py#L1-L97): `resolve_effective_interval()` resolves assignment times, falling back to Lot times when assignment boundaries are absent; `find_assignment_conflict()` checks only unreleased assignments on active Lots and tests interval intersection. In effect its intersection treats end as exclusive (`existingStart < requestedEnd` and `requestedStart < existingEnd`). Invalid/unresolved existing intervals conservatively block allocation. `validate_lot_resource_availability()` rechecks assignment conflicts when Lot bounds change ([same module](../../FittingMES/app/resource_availability.py#L99-L121)).
- `save_press_production()` in [FittingMES/app/press_production.py](../../FittingMES/app/press_production.py#L593-L800) validates the active Lot, Product, Shift, Press and Mould; resolves the requested time interval; locks resources; checks conflicts; inserts/updates the assignment; and commits or rolls back. The availability list is prepared by `build_press_production_context()` ([FittingMES/app/press_production.py](../../FittingMES/app/press_production.py#L931-L1024)).
- Focused tests in [FittingMES/tests/test_press_production.py](../../FittingMES/tests/test_press_production.py#L590-L710) assert that Mould availability needs a resolvable interval; [tests for cross-Lot blocking and time reuse](../../FittingMES/tests/test_press_production.py#L708-L775) cover conflicts and non-overlapping assignments; [concurrency and correction tests](../../FittingMES/tests/test_press_production.py#L1345-L1457) assert serialized allocation and update behavior. These unit tests simulate database behavior; they do not prove all SQL locking races on a live server.

**Important limitation:** FittingMES also applies Shift selection and Shift context, and its assignment entity is `PressProduction`, not an OmagMES Lot-to-Mould interval entity. Reuse its interval conflict principle and authoritative revalidation/locking pattern, but do not use whole-shift exclusivity as OmagMES Mould availability. The tested implementation remains constrained by its own Lot/Press workflow.

### 4.4 Mould usage and age evidence

- `save_press_production()` reconciles one `MouldUsage` row per `PressProductionID`, writing `UsageCycles` from that row's `CounterQty`; a correction updates the row rather than adding the same amount again ([FittingMES/app/press_production.py](../../FittingMES/app/press_production.py#L741-L790)).
- `read_mould_detail()` joins `MouldUsage` to `PressProduction` and `ProductionLot` to present Lot No., machine, usage cycles, and production interval information ([FittingMES/app/mould.py](../../FittingMES/app/mould.py#L87-L98)). This is useful history presentation, but editing/reassigning the current row reconciles usage in place and is not an immutable Mould-change interval ledger.
- [FittingMES/sql/023_product_family_id.sql](../../FittingMES/sql/023_product_family_id.sql#L319-L370) defines `vw_MouldList` and `sp_Mould_Register`. The migration references `vw_MouldLifeSummary` but the repository does not include that view's definition. The lifecycle stored procedure definitions used by the application are likewise not present in the inspected repository. Therefore the exact live age formula, source-unit meaning of `CounterQty`, database-side age reset, and actual lifecycle history writes are **not verified by the checked-in source**.
- `test_mould.py` includes fake return data where Current Age becomes zero and Lifetime Age remains unchanged; `test_press_production.py` checks usage-row reconciliation without double accumulation. Those tests are assertions against fakes, not evidence that the actual SQL procedures/view implement Press-Drop-only age.

## 5. FittingMES-to-OmagMES applicability matrix

| Requirement | FittingMES evidence | OmagMES treatment |
|---|---|---|
| Automatically detect draft Lots from `OMAG.PRESS.OEE.DropCnt` | No such PLC-derived draft Lot workflow was found in the inspected FittingMES frontend, service, or tests. FittingMES Lot creation starts from a selected plan. | New OmagMES workflow. Keep source samples read-only; create/reconcile draft records separately. Confirm exact tag metadata and detection boundaries first. |
| Operator correction/delete of draft times and Drops without editing PLC data | FittingMES edits saved Lot/Production and Press Production forms; no equivalent auto-detected PLC draft review/delete workflow was identified. | New workflow. Preserve raw-source data, audit draft edits, and define deletion as draft invalidation/removal only; never send updates to the source system. |
| Assign plan after auto-detection; exact `MaterialCode` to Product Master | FittingMES uses selected plan before Lot creation and its checked-in `confirm_mapping()` maps a material prefix to Product family/code. | New sequencing and exact match. OmagMES requires full exact `MaterialCode` equality to Product `ProductCode`, then use Product-owned approved standard revisions/snapshots. |
| Multiple Mould intervals within one Lot | FittingMES supports multiple `PressProduction` rows per Lot, each with its own Mould and interval. | Reusable conceptual support, but OmagMES needs explicit Lot/Mould usage intervals with immutable audit and attributed Drops; Mould swap alone retains the Lot if Product/Color are unchanged. |
| Interval-based Mould availability | FittingMES has interval resolution, overlap checks, Product/status validation, and transaction locks in its service. | Reuse pattern, not schema. OmagMES availability must be by overlapping Mould assignment time intervals, not a whole shift or Lot. Choose/approve boundary semantics and handle unresolved intervals conservatively. |
| Mould age strictly from Press Drops | FittingMES records `CounterQty` as `UsageCycles`; source/view/procedure evidence available in the repo does not prove this is Press Drops. | OmagMES must attribute verified Drop deltas only. No Piece-derived age and no inference from the FittingMES field name or mock values. |
| Auditable lifecycle and usage history | FittingMES UI has separate histories; service calls dedicated procedures; DB definitions and authenticated human actor behavior are not fully verifiable from repository source. | Reuse UI organization. OmagMES must meet its own actor/time/reason/history requirements and make interval corrections traceable without erasing prior allocation decisions. |

## 6. OmagMES current implementation and boundaries

### Existing OmagMES code inspected

- [backend/app/sql_source.py](../backend/app/sql_source.py) defines `SQLSourceSettings` and `SQLServerReadOnlyRepository`. Historian queries require `id`, `_NAME`, `_VALUE`, `_TIMESTAMP`, `_QUALITY`, use parameterized bounded timestamps, `TOP`, a configured timeout, and exact tag filters. Its `latest_press_counter()` / `press_observations()` currently target only `OPC.OMAG.OMAG.PRESS.ProductCnt`; no method reads the preferred DropCnt history. Connection preflight requires exact target and SELECT-only gates.
- [backend/app/live_autocal.py](../backend/app/live_autocal.py) defines `PRESS_COUNTER_TAG`, `calculate_counter_window()`, and `calculate_press_drops()`. It computes reset/gap/quality-aware suggestions for ProductCnt and withholds results when critical metadata/policy is missing. This is a Lot-window AutoCal calculator, not an automatic segment detector, persistent draft queue, or confirmed Lot workflow.
- [backend/app/main.py](../backend/app/main.py) exposes bounded source/AutoCal endpoints and process-local mock endpoints. `/api/lots` creates a Lot from mock Product and prior-Lot choices; `/api/production/save` persists only to the in-memory store. There is no post-detection plan API, automatic draft detection/review/delete API, official shift-sequence Lot No. assignment, or Lot-linked Mould interval API.
- [backend/app/models.py](../backend/app/models.py) models the current mock Lot-create and production payloads, but has no draft review state, Production Plan association, official Lot No., or start/end Mould assignment interval model. [backend/app/store.py](../backend/app/store.py) explicitly holds process-local state reset on restart.
- [frontend/src/App.tsx](../frontend/src/App.tsx) implements the React mock production, Mould lifecycle, and read-only Settings screens. Production uses mock Lots/AutoCal; the Mould page displays a demo register/recondition transition; Settings has a Product review table. It has no Auto Lot draft queue, plan selection/GET UPDATE PRODUCT workflow, editable Product/Mould master, or Mould interval assignment UI.
- [backend/tests/test_live_sources.py](../backend/tests/test_live_sources.py) uses a fake SQL connection to assert bounded, parameterized SELECT behavior and ProductCnt-only counter processing; it is not live SQL verification. [backend/tests/test_api.py](../backend/tests/test_api.py) covers mock endpoints and Lot/Mould examples; [backend/tests/test_migration_drafts.py](../backend/tests/test_migration_drafts.py) statically checks unexecuted review-only SQL drafts. No tests were run for this documentation task.

The new workflow is a distinct pipeline, not merely the existing AutoCal form:

1. **Read-only source ingest:** acquire verified preferred-alias `DropCnt` observations with stable identity, timestamp/timezone, raw value, and quality. Do not combine with ProductCnt rows. Preserve source evidence unchanged and process deterministically/idempotently. Because logging is change-based, do not treat absent rows as stopped status or as regular time samples.
2. **Draft detection:** derive candidate start/end and raw Drop count from counter activity/reset evidence. Keep detection state separate from official Lot ID/number and define how continuity, resets, gaps, duplicate/out-of-order observations, and machine stops affect draft boundaries. A reset is not a Product/Color boundary.
3. **Operator draft review:** show the observations/range supporting each candidate. Allow an authorized operator to correct boundaries/count or invalidate/delete the draft. Record old/new values and reason; never alter raw PLC samples. Whether delete is soft invalidation or hard deletion of the local draft is an owner decision; retaining an audit tombstone is recommended.
4. **Plan assignment:** only after draft detection/review, permit plan selection; resolve `MaterialCode` exactly against Product Master. Require an unambiguous Product and approved standard for production calculations. Retain the selected plan identity and a historical standard snapshot; do not use fuzzy or prefix matching.
5. **Official Lot confirmation/numbering:** create/finalize an official Lot and assign its human Lot No. only after the operator confirms relevant production information. The draft ID remains distinct from immutable official Production Lot ID. Apply the stated Lot No. format only after the open 06:00–08:00, shift-boundary, sequence-limit, timezone, and concurrency decisions are resolved. Product/Color changes start a new Lot; Mould-only changes do not.
6. **Mould interval assignment:** record zero or more sequential Lot-linked Mould intervals, validate Product match and production-ready status on the server, and reject overlapping active intervals for the same physical Mould. A Mould can be reused after the prior interval ends. Keep the installation interval independent of Shift/Lot-wide availability windows.
7. **Drop attribution and age:** allocate only source-supported Drop deltas to each interval. Preserve unallocated/uncertain Drops. Derive Current/Lifetime age from confirmed Drops and approved recondition events; never use pieces or reset age at the PLC's daily counter reset.

This is a recommended implementation decomposition. It does not specify or authorize SQL tables, migrations, data imports, live source reads, or production writes.

## 7. Open factory/technical decisions

Resolve these before production use or schema migration; the listed questions do not weaken the confirmed requirements above.

### SQL history and automatic detection

- The authorized validation verified the `dbo.PRESS` columns/indexes and exact persisted DropCnt `_NAME`; see Section 8. Resolve why the stored DropCnt name differs from the existing ProductCnt naming convention, and update the application source contract only after review. Keep alias histories separate.
- Confirm the historian timezone and `_TIMESTAMP` semantics before using timestamps as transition times. Confirm future DropCnt samples show expected cumulative counter/reset behavior, restart conditions and the 07:00 reset. The shorter DropCnt history is expected because change-based logging was introduced recently; missing rows during unchanged values are normal, not proof of a stopped press.
- Obtain a dedicated least-privilege SQL identity: the credential used for this authorized test had effective SELECT, INSERT, UPDATE, DELETE, ALTER and CONTROL permissions on `dbo.PRESS`. All statements actually issued in this validation were SELECTs only, but the credential is **not** verified read-only and must not be used by the application.
- What starts/ends a draft Lot: counter movement, idle duration, operator signal, Product/Color boundary, or another verified signal? Define behavior for startup baselines, repeated/equal values, missing samples, gaps, counter decreases, downtime, and adjacent/overlapping detected drafts.
- Define acceptable source quality, maximum observation gap, duplicate/out-of-order handling, late-arriving samples, Data Logger deadband/change behavior impact, and whether corrections cause redetection or remain operator-only overrides. Missing rows must not imply STOPPED; AutoRun/Start/Stop tags may be evidence only after their stored semantics and reliable association are reviewed.

### Plan assignment and standards

- Identify the authoritative plan key/version and distinguish separate plans that share the same exact `MaterialCode`.
- Confirm missing/multiple Product match behavior and how `Pending Standard` blocks or permits Lot confirmation and downstream calculations.
- Confirm standard revision/effective-date selection and snapshot boundary when a plan or Product standard changes after draft detection.
- Preserve the existing GET UPDATE PRODUCT rule: query the existing `OMAG.dbo.OmagPlan` synonym only on explicit button click; do not add a competing planning integration or automatic background query.

### Mould intervals, availability, and age

- Define who/what records actual install/removal time, whether boundaries are operator-entered or machine-evidenced, clock precision/timezone, allowed corrections, and whether a short gap is permitted between sequential Mould intervals.
- Approve overlap semantics. A half-open interval `[StartedAt, EndedAt)` is a recommended convention so one Mould may be removed and reinstalled at the same instant another interval ends; not yet factory-confirmed.
- Define whether an open interval blocks all later assignments of that Mould until explicitly ended and how a lost/unknown end time is resolved. An unresolved interval should fail closed for availability rather than assume the Mould is free.
- Define Drop allocation when counter observations straddle a Mould-change time, contain gaps, cross a reset, or have invalid quality. No interpolation or allocation to both Moulds without explicit approved evidence/rule.
- Confirm exact production-ready statuses and transition/return approval policy; FittingMES `ACTIVE`, `RECONDITION`, `RETIRED`, and `DENIED` are not automatically OmagMES status approvals.
- Confirm correction/reversal authority and how Current/Lifetime age is recomputed from an immutable, auditable Drop attribution history.

### Operator review and audit

- Define who can edit/delete drafts, required reason fields, soft-delete/audit retention, approval state, and downstream behavior if an already-assigned plan or Mould interval is changed.
- Confirm whether an operator correction of the detected Drop total overrides only the Lot draft quantity or also creates a separately auditable allocation reconciliation. It must not rewrite PLC observations.
- Confirm operator identity/authentication and audit retention before using “operator” fields as accountable identities.

## 8. SQL source verification results and remaining gates

### Authorized read-only query findings

- Using the existing `.env` credentials without displaying them, a temporary in-memory override connected to `10.28.255.98` / database `OMAG`; `.env` was not changed. SQL identity reported `SCGLS-NK\SQLEXPRESS`, instance `SQLEXPRESS`.
- **Security blocker:** `HAS_PERMS_BY_NAME` returned effective `1` for SELECT, INSERT, UPDATE, DELETE, ALTER, and CONTROL on `dbo.PRESS`. Therefore the login is not SELECT-only. Every statement actually issued for this check was a SELECT, and no database writes/schema changes were performed. Do not enable the application or make further source reads with this login; ask the DBA for a dedicated least-privilege account and re-check permissions.
- `dbo.PRESS` columns: `id int NOT NULL`, `_NAME varchar`, `_NUMERICID int`, `_VALUE varchar`, `_TIMESTAMP datetime`, `_QUALITY int` (the remaining fields nullable). Only one index exists: clustered primary key on `id`; there is no index on `_NAME` or `_TIMESTAMP`. Query cost/latency was not benchmarked, and bounded time predicates may still scan the table.
- Exact DropCnt row key is `_NAME='OMAG.PRESS.OEE.DropCnt'`. A bounded last-24-hour query returned 332 rows, all with quality `192`; `_TIMESTAMP` spans 2026-11-10 10:00:07.007 through 14:05:25.570 (SQL `datetime`, timezone/transition-time meaning not established). Values were non-null integral strings; the observed range was `101` to `414`, with 312 increases, 19 unchanged transitions and no decreases. Maximum adjacent timestamp gap was about 14m26s. One exact-tag aggregate across available history also reported 332 total rows. The factory-confirmed recent change from hourly ProductCnt logging to on-change DropCnt logging explains why ProductCnt history is longer; the short DropCnt period is expected, not a basis to infer a retention defect. Still, the available DropCnt observations are insufficient to validate daily reset/draft segmentation.
- For historical comparison only, exact ProductCnt name `OPC.OMAG.OMAG.PRESS.ProductCnt` had 69,604 rows spanning 2025-08-05 through 2026-11-10. ProductCnt is not an alternate/new-detection input. Keep these histories separate: do not merge, union, or sum them. Use DropCnt `_TIMESTAMP` for detected transitions only after its timestamp/timezone semantics are verified. The 07:00 reset rule cannot be inferred from the limited DropCnt sample.
- The application adapter's earlier `health()` preflight failed because pyodbc does not support assigning `cursor.timeout`. The adapter now sets the supported connection-level timeout instead; regression tests and the backend suite pass. This does not resolve the separate least-privilege credential and source-policy blockers. Do not bypass its gates in application code.

For a DBA with an approved **read-only** identity, recheck target identity and effective permissions before any additional query. Do not union, combine, or sum alias results. First inspect schema and supporting indexes:

```sql
SELECT @@SERVERNAME AS ServerName, DB_NAME() AS DatabaseName,
       HAS_PERMS_BY_NAME(N'dbo.PRESS', N'OBJECT', N'SELECT') AS CanSelect,
       HAS_PERMS_BY_NAME(N'dbo.PRESS', N'OBJECT', N'INSERT') AS CanInsert,
       HAS_PERMS_BY_NAME(N'dbo.PRESS', N'OBJECT', N'UPDATE') AS CanUpdate,
       HAS_PERMS_BY_NAME(N'dbo.PRESS', N'OBJECT', N'DELETE') AS CanDelete,
       HAS_PERMS_BY_NAME(N'dbo.PRESS', N'OBJECT', N'ALTER') AS CanAlter,
       HAS_PERMS_BY_NAME(N'dbo.PRESS', N'OBJECT', N'CONTROL') AS CanControl;

SELECT COLUMN_NAME, DATA_TYPE
FROM OMAG.INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = N'dbo' AND TABLE_NAME = N'PRESS'
ORDER BY ORDINAL_POSITION;

SELECT i.name AS IndexName, i.type_desc, c.name AS ColumnName, ic.key_ordinal,
       ic.is_included_column
FROM OMAG.sys.indexes AS i
JOIN OMAG.sys.index_columns AS ic ON ic.object_id = i.object_id AND ic.index_id = i.index_id
JOIN OMAG.sys.columns AS c ON c.object_id = ic.object_id AND c.column_id = ic.column_id
WHERE i.object_id = OBJECT_ID(N'OMAG.dbo.PRESS')
ORDER BY i.name, ic.key_ordinal, ic.index_column_id;
```

After the DBA confirms SELECT-only permissions and query cost is acceptable, inspect a short approved DropCnt interval in isolation:

```sql
DECLARE @StartAt datetime = '2026-11-09T00:00:00';
DECLARE @EndAt   datetime = '2026-11-10T00:00:00';

SELECT TOP (1000) id, _NAME, _VALUE, _TIMESTAMP, _QUALITY
FROM OMAG.dbo.PRESS
WHERE _NAME = N'OMAG.PRESS.OEE.DropCnt'
  AND _TIMESTAMP >= @StartAt
  AND _TIMESTAMP <  @EndAt
ORDER BY _TIMESTAMP ASC, id ASC;
```

The exact DropCnt row key is already verified; keep future queries exact-name and bounded. The ProductCnt comparison is optional, must be separately authorized and must not be joined/unioned/summed. The example timestamps are SQL-naive; confirm timezone before interpretation. `TOP (1000)` truncation means the operator must verify range completeness; narrow the interval rather than removing bounds or increasing without review. Do not execute the examples with the currently tested credential because its effective write/DDL permissions are broad.

## 9. Recommended next implementation and acceptance sequence

1. **Source contract review:** have the DBA provision a SELECT-only identity, fix/test the pyodbc cursor-timeout preflight, and document `_TIMESTAMP`/timezone and reset semantics. The exact DropCnt row key/schema are verified; its shorter history is expected after the recent logging switch. Use DropCnt for new Auto Lot Detection and ProductCnt only as historical reference; never combine alias histories. Requery bounded DropCnt history only after least-privilege and query-cost approval.
2. **Rule closure:** factory resolves draft segmentation, plan-key/version behavior, pending-standard handling, Lot boundaries/numbering conflicts, interval timestamps/overlap, Drop attribution uncertainty, and lifecycle approvals.
3. **Logical design and DBA review:** audit existing schema; propose ID-first `omagmes` draft/source/plan association/Mould interval/audit structures and migration plus rollback for review only. Keep legacy `OMAG.dbo` and the plan synonym read-only.
4. **Mock/test workflow:** implement ingestion/detection and operator review against deterministic fake observations first; preserve raw fixtures and test correction/deletion isolation. Add exact plan matching and standard snapshot behavior, then multiple Mould intervals and availability checks.
5. **Lifecycle and age:** implement server-authoritative Mould eligibility, interval concurrency protection, Drop-only attribution, uncertainty handling, and current/lifetime age reset at approved return. No live source or database writes at this stage.
6. **Acceptance before gated integration:** test idempotency, exact source/tag identity, counter resets/gaps/quality, interval overlaps/non-overlaps/open intervals, boundary swaps, wrong Product/status, corrections, deletion audit, no double counting, and recondition reset behavior. Obtain factory acceptance and separate DBA/security approval before any further application SQL connection/source reads, import, migration, production persistence, or deployment.

### Minimum test scenarios

- Duplicate/replayed and out-of-order DropCnt observations do not create duplicate drafts or double-count Drops.
- Valid counter reset/baseline, unexpected decrease, invalid quality, and over-threshold gap remain distinguishable; uncertain Drops are not fabricated.
- Detected draft stores start/end/count; operator edits affect only the draft/audit, and invalid-draft deletion leaves raw observations unchanged.
- A plan can be selected after detection; exact full MaterialCode matches only the exact ProductCode; similar codes/names, missing match, duplicate plan identity, or pending standards fail safely.
- A Lot can carry multiple sequential Mould intervals without generating a new Lot when Product/Color remain unchanged; Product or Color change still follows the separate Lot-boundary rule.
- Same Mould overlapping intervals are rejected across Lots; non-overlapping intervals allow reuse regardless of Shift; open/unresolved intervals fail closed.
- Mould/Product mismatch, non-ready status, and unauthenticated/unauthorized transition are rejected server-side.
- Drop attribution is split only where interval/source evidence brackets the boundary; no Lot total is duplicated across Moulds; PLC reset does not reset Mould age; approved recondition return resets Current Age only; Lifetime Age never resets.

## 10. Current OmagMES implementation status

The authorized SQL validation verified target identity, PRESS schema/indexes, and persisted `OMAG.PRESS.OEE.DropCnt` samples, but found the tested credential has broad write/DDL permissions and the available sample history is short. The adapter timeout bug has been fixed and tested; its current counter methods still query only ProductCnt. Auto Lot is therefore **not ready for implementation against live history or operational use** until a least-privilege identity, DropCnt source integration, and timestamp/reset semantics are approved. Lot/production saves and Mould controls remain process-local mock behavior. There is no PLC-derived draft queue with correction/dismissal, no post-detection plan assignment workflow, no official shift-sequence Lot No. assignment, and no Lot-linked set of Mould usage intervals or per-interval verified Drop allocation. Existing review-only DDL is unexecuted and does not by itself satisfy this workflow.

This reference records requested requirements and verified FittingMES/source behavior; it is not implementation approval. Do not perform further SQL reads with the tested account, import workbook data, execute migrations, modify production objects, or deploy without the separate least-privilege credentials and authorizations required by the factory handoff.
