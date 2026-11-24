# OmagMES Auto Lot, Production Plan, and Mould Assignment Workflow

**Prepared:** 2026-11-10; implementation status updated 2026-11-18
**Status:** Permanent implementation reference. A bounded LIVE DropCnt evidence panel, reset-evidence review/link UI, explicit Product/Color Lot confirmation form and read-only/non-reserving SCG number preview are implemented. The official Lot SQL path and reset-review audit require the unapproved, unexecuted migration 003 and remain hard-disabled; no Lot was created. Factory has confirmed `PRESS._TIMESTAMP` is SQL recording-server local Thailand time; Auto Lot attribution uses these wall-clock fields directly with effective-dated Production Date Cutoff and Shift settings. Quality and gap policies remain provisional. No source SQL write, workbook import, FittingMES edit, or commit/push was performed.

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

**Timestamp interpretation confirmed 2026-11-18:** `OMAG.dbo.PRESS._TIMESTAMP` is the SQL recording server's local date/time, and that server is configured to Thailand time (UTC+07:00). Treat the SQL `datetime` as Asia/Bangkok wall-clock time; do not convert it from UTC or add/subtract seven hours. This owner confirmation supersedes earlier notes below that described timezone semantics as unconfirmed.

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
- [backend/app/main.py](../backend/app/main.py) exposes bounded DropCnt, reset-evidence and AutoCal endpoints, and separate mock endpoints. `/api/lots` has a LIVE SQL implementation, but it is hard-disabled pending schema/rule approvals; `/api/lots/number-proposal` is read-only and non-reserving. There is no post-detection plan API or Lot-linked Mould interval API.
- [backend/app/models.py](../backend/app/models.py) models the current mock Lot-create and production payloads, but has no draft review state, Production Plan association, official Lot No., or start/end Mould assignment interval model. [backend/app/store.py](../backend/app/store.py) explicitly holds process-local state reset on restart.
- [frontend/src/App.tsx](../frontend/src/App.tsx) implements the React mock production, Mould lifecycle, and read-only Settings screens. Production uses mock Lots/AutoCal; the Mould page displays a demo register/recondition transition; Settings has a Product review table. It has no Auto Lot draft queue, plan selection/GET UPDATE PRODUCT workflow, editable Product/Mould master, or Mould interval assignment UI.
- [backend/tests/test_live_sources.py](../backend/tests/test_live_sources.py) uses a fake SQL connection to assert bounded, parameterized SELECT behavior and ProductCnt-only counter processing; it is not live SQL verification. [backend/tests/test_api.py](../backend/tests/test_api.py) covers mock endpoints and Lot/Mould examples; [backend/tests/test_migration_drafts.py](../backend/tests/test_migration_drafts.py) statically checks unexecuted review-only SQL drafts. No tests were run for this documentation task.

The new workflow is a distinct pipeline, not merely the existing AutoCal form:

1. **Read-only source ingest:** acquire verified preferred-alias `DropCnt` observations with stable identity, timestamp/timezone, raw value, and quality. Do not combine with ProductCnt rows. Preserve source evidence unchanged and process deterministically/idempotently. Because logging is change-based, do not treat absent rows as stopped status or as regular time samples.
2. **Draft detection:** derive candidate start/end and raw Drop count from counter activity/reset evidence. Keep detection state separate from official Lot ID/number and define how continuity, resets, gaps, duplicate/out-of-order observations, and machine stops affect draft boundaries. A reset is not a Product/Color boundary.
3. **Operator draft review:** show the observations/range supporting each candidate. Allow an authorized operator to correct boundaries/count or invalidate/delete the draft. Record old/new values and reason; never alter raw PLC samples. Whether delete is soft invalidation or hard deletion of the local draft is an owner decision; retaining an audit tombstone is recommended.
4. **Plan assignment:** only after draft detection/review, permit plan selection; resolve `MaterialCode` exactly against Product Master. Require an unambiguous Product and approved standard for production calculations. Retain the selected plan identity and a historical standard snapshot; do not use fuzzy or prefix matching.
5. **Official Lot confirmation/numbering:** a new Lot requires explicit Product/previous-Lot, Color/LotName, actual start, confirmed factory code B, and SAVE. A reset candidate can be linked only as reviewed evidence with an operator reason; it never infers Product or Color. Production Date and effective Shift are resolved independently from the entered timestamp. A number preview is explicitly non-reserving; SAVE allocates under a transaction lock. Same Product+Color continues the original Lot across shifts and Production Dates; only Product or Color change creates a new Lot. The original Lot ID, official number, and start context remain immutable. The official write path stays disabled pending DBA/schema/security and remaining sequence-policy approvals. Mould-only changes do not create a Lot.
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

### Owner-authorized bounded query findings (2026-11-17)

- Using existing root `.env` credentials without displaying or changing the secret values, host-only `10.28.255.98` connected to database `OMAG`; SQL reported `SCGLS-NK\\SQLEXPRESS`, instance `SQLEXPRESS`. Named-instance connection had failed discovery; host-only was verified.
- **Privilege disclosure:** identity is `sa` / database user `dbo`, sysadmin, with effective SELECT, INSERT, UPDATE, DELETE, ALTER and CONTROL on `dbo.PRESS`. It is not a read-only credential. The owner explicitly authorized this bounded read. No INSERT, UPDATE, DELETE, DDL, or other source writes were issued. Repository access now funnels through a guard that accepts a single SELECT statement only; this is a code-level control, not a database permission boundary. Do not deploy this elevated credential; obtain least privilege before broader use.
- `dbo.PRESS` columns: `id int NOT NULL`, `_NAME varchar(64)`, `_NUMERICID int`, `_VALUE varchar(64)`, `_TIMESTAMP datetime`, `_QUALITY int` (nullable except `id`). Only a clustered `id` key was observed; no `_NAME`/`_TIMESTAMP` index. Query cost/latency was not benchmarked; bounded time predicates may still scan the table.
- Exact `_NAME='OMAG.PRESS.OEE.DropCnt'`, half-open interval `[2026-11-10 07:00, 2026-11-17 07:00)`: **11,527 rows**, all returned within the 20,000-row cap; timestamp range 2026-11-10 10:00:07.007–2026-11-17 06:59:32.400; every `_QUALITY` was 192 and values parsed as integers. SQL `GETDATE()` and `GETUTCDATE()` differed by 420 minutes, supporting (but not proving writer semantics for) Bangkok-local timestamps.
- Per raw-wall-clock Production Date counts, with value ranges and adjacent observations: Nov 10: 1,922, 0–1,131, 1 decrease; Nov 11: 2,388, 0–1,211, 2 decreases; Nov 12: 2,270, 0–1,298, 4 decreases; Nov 13: 2,344, 0–1,238, 2 decreases; Nov 14: 1,385, 0–1,197, 14 decreases; Nov 15: 144, constant 108; Nov 16: 1,074, 0–476, 4 decreases. Total **27 decreases**, occurring at 07:53, evening and daytime as well as other periods; they are reset/restart-like evidence, not proof of daily reset or Lot boundaries.
- Maximum adjacent per-day sample gaps were 19.041, 20.012, 10.037, 10.034, 10.322, 10.051, and 10.142 minutes respectively; no gaps exceeded 30 minutes. **30 minutes is a provisional review threshold** (>1.5× observed maximum), not factory-approved. Nov 15 had repeated constant-value observations about every 10 minutes, which conflicts with the described change-only logger behavior and needs source/logger review.
- ProductCnt remains separate historical context only. No ProductCnt observations were used in this DropCnt analysis or Auto Lot candidate.
- SQL `datetime` has no timezone offset and writer/PLC timestamp semantics remain unconfirmed. Production query compares raw SQL wall-clock values against persisted 07:00 cutoff bounds with no conversion; date attribution is explicitly provisional. The evidence supports, but does not certify, Bangkok-local interpretation.

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

The authorized SQL validation verified target identity, PRESS schema/indexes, and seven days of exact `OMAG.PRESS.OEE.DropCnt` samples. A bounded live evidence-envelope query and review UI are implemented and verified; the identity has broad write/DDL permissions, so repository-level SELECT enforcement and explicit UI disclosure are in place, but the credential is not least-privilege. Timestamp, quality, gap, reset and query-cost approvals remain open; the envelope is not an operational Lot segment. Lot/production saves and Mould controls remain process-local mock behavior. There is no confirmed PLC-derived Lot segmentation, post-detection plan assignment workflow, official shift-sequence Lot No. assignment, or Lot-linked set of Mould usage intervals/per-interval verified Drop allocation. Existing review-only DDL is unexecuted and does not by itself satisfy this workflow.

This reference records requested requirements and verified FittingMES/source behavior; it is not implementation approval. Do not perform further SQL reads with the tested account, import workbook data, execute migrations, modify production objects, or deploy without the separate least-privilege credentials and authorizations required by the factory handoff.

## 11. Shared Production Date and effective Shift Schedule (current handoff)

The current UI includes a central Production Date resolver backed by persisted effective cutoff history, separate Shift Schedule context, and a fail-closed DropCnt evidence review panel. It is not a full Auto Lot workflow. Requirements are consolidated in [the factory-confirmed requirements](OmagMES_Factory_Confirmed_Requirements.md#11-shared-production-date-and-dynamic-shift-schedule). This section supersedes earlier open wording that treated 06:00–08:00 merely as an unclassified question: the currently approved two-shift schedule leaves that interval explicitly unassigned.

- Distinguish Bangkok Calendar Date, cutoff-derived Production Date, and independently scheduled Shift. The URL's valid Production Date takes precedence, then an explicitly saved selection; on first use the backend provides current Production Date from persisted cutoff configuration. There is no fixed date default and no automatic midnight rollover of a selected historical date. This context is distinct from event time, creation time, and Lot bounds.
- `SETTING > SHIFT TIME` supports variable-count shifts, free-text Shift Name, separate Shift Code and immutable Shift ID, clock times, order, active state, new immutable versions, effective dates/history, and selected-date resolved-shift/gap preview. The initial visible shift times are the confirmed two shifts only; the illustrative 3-shift configuration is not preloaded.
- Effective versions are forward-only, non-overlapping by construction, and resolved by Production Date. Previous versions remain unchanged. The owner-approved SQL configuration history starts 2026-11-10; the `2026-01-01` date in the mock fallback is only a placeholder and is not the active SQL configuration. Do not rebuild the already-applied cutoff/schedule settings for Auto Lot work.
- Shift intervals resolve against the selected Production Date, including overnight end on the following calendar day, and never move when the independent cutoff changes. Production Day windows use the effective cutoff at each boundary, `Asia/Bangkok`, and half-open `[start, end)` intervals. A cutoff transition may create 23/25-hour days while remaining contiguous; gaps in Shift assignment remain unassigned.
- Process-local API state validates overlap, duplicate Name/Code/order, invalid clock values and effective dates. Existing mock writes receive Production Date and schedule version. A version mismatch is rejected for a new mock write and shown on a provisional Auto Lot draft; explicit operator review with a reason updates only the draft view and audit trail, while its raw mock count is retained. Dismissal is auditable. Official `ProductionLot.id` and Lot No. are never created by draft detection or review.
- Auto Lot UI requests the read-only DropCnt candidate endpoint. It uses the selected Production Date's persisted cutoff-resolved `[start, end)` window; Shift Schedule remains a distinct context. It displays no synthetic fallback. See Section 12 for current source gates and the intentionally limited envelope semantics.
- The existing Lot number's Shift field cannot be silently mapped from a free-text name. Shift Code compatibility remains unresolved and must be decided before official Lot numbering is implemented.

### SQL-backed Production Day and Shift configuration

The project owner-approved `omagmes` configuration schema/bootstrap is applied. Production Day Cutoff and Shift Schedule are separate immutable version streams; the initial effective date is 2026-11-10, with verification-only later versions retained. SQL persistence was verified across backend restart in the earlier settings phase. Do not rebuild these settings for Auto Lot detection. Auto Lot operator review state is still process-local; this does not change or persist Cutoff/Shift configuration and is not an accountable durable audit trail.

## 12. Phase 2 DropCnt evidence-envelope implementation status (2026-11-17)

### Implemented, tested behavior

- `backend/app/sql_source.py` has a distinct `dropcnt_observations()` query. It uses exact `_NAME='OMAG.PRESS.OEE.DropCnt'`, parameterized half-open `_TIMESTAMP` bounds, `TOP`, existing timeout, and the existing verified SELECT-only source preflight. It does not alter or reuse the ProductCnt query path.
- `backend/app/main.py` exposes `GET /api/auto-lot/candidates?production_date=YYYY-MM-DD`. It resolves the effective persisted Cutoff version/window and separately includes the Shift Schedule version. It requires the owner-confirmed target, metadata review, configured Bangkok wall-clock basis, observed quality code list, and gap threshold. If timestamp semantics are not confirmed, it can return a provisional candidate only by preserving raw SQL wall-clock values without conversion and adding explicit warnings; the resulting Production Date attribution is not certified.
- `backend/app/auto_lot_detection.py` emits at most one observed-activity envelope for a Production Date, and only when an accepted positive adjacent counter change exists. It does **not** segment multiple Lots or declare a confirmed machine run. A single value, reset/decrease, silence, invalid sample, conflicting timestamp, or truncated row-limit result cannot alone create a candidate. Accepted adjacent increases are labeled as a lower bound; over-threshold gaps are omitted, not interpolated. Reset, gap, sample order, quality, duplicate, large-delta, and other uncertainty is shown as evidence/warnings.
- Production UI allows operator time/count corrections, review, or dismissal. These actions are stored in process memory only and are reset on backend restart; no source rows are altered, no candidate action creates an official Lot, and no durable operator/audit claim is made. Corrections remain separate from raw evidence.
- Each possible decrease is displayed separately with pre-decrease/decrease samples, timestamp bracket, following sample and post-decrease positive-delta lower bound. No decrease is treated as a Product/Color change. A selected event may be linked to the explicit Lot form with a required operator reason; if enabled after approvals, its `AutoLotResetReview` row is written atomically with the Lot. Candidate source evidence remains session-loaded, not durably ingested.
- The explicit Lot form selects Product and previous official Lot, records operator-entered Color/LotName/start, resolves shift/date server-side, shows a preview as **not reserved**, and requires a separate explicit SAVE. Backend transition derives from official SQL state. Only B is accepted for this factory's SCG format. This SQL path remains hard-disabled and has not been exercised against SQL.
- Sequence allocation is designed for a serializable transaction with `UPDLOCK,HOLDLOCK` on the unique Plant/Production Date/Shift scope, 01–99 exhaustion, and no wrap. A non-reserving preview may become stale; SAVE re-allocates. Only fake-cursor tests cover this design; no live concurrency test was performed.
- Migration 003 draft includes Lot-number fields, `LotNumberSequence`, and ID-first `AutoLotResetReview`, plus validation/rollback parity. It remains review-only; schema isn't installed and `OFFICIAL_LOT_NUMBERING_READY` plus production writes remain disabled.
- Automated coverage includes exact DropCnt isolation from ProductCnt, bounded parameterized SELECT behavior, DML/multi-statement rejection, cutoff windows, boundary exclusion, reset/gap/quality/duplicate/out-of-order/truncation handling, raw-wall-clock provisional mode, and review-only API actions. Focused source/detector suite passed 38 tests (one existing Starlette/httpx deprecation warning); full backend suite and frontend build are pending after the latest edits.

### Live-analysis result and interpretation limit

Root `.env` now enables `LIVE_READ_ONLY`, points to the owner-approved host, records the target and metadata review, configures only observed quality 192 and provisional 30-minute gap, and explicitly leaves source-timezone confirmation false. Browser/API verification for 2026-11-10 returned 1,922 exact DropCnt rows and one review-only envelope (first/last observed 10:00:07.007–next day 06:59:36.987; 1,850 accepted adjacent positive deltas; one decrease). It creates no official Lot and reads no ProductCnt rows. The live UI reports `sa`/`dbo`, sysadmin/elevated rights, and the repository SELECT-only guard. No source writes occurred.

This verifies an evidence envelope only; it does not identify a confirmed machine run or Lot. Change-based logger silence cannot prove stoppages, the 27 observed decreases do not establish a daily reset, the all-192 quality distribution is observed rather than factory-approved, and the 30-minute gap threshold is provisional. The Nov 15 repeated constant values merit investigation. Source SQL `datetime` timezone/writer semantics remain unconfirmed; raw wall-clock values are compared to the persisted 07:00 cutoff without conversion, and date attribution is provisional.

No reliable Lot segmentation rule is approved or evidenced. Change-based logging cannot prove stoppages from silence; a counter decrease is evidence of a possible new Product run but is not itself a Product/Color boundary; an entire Production Day envelope can span multiple runs/Lots. The 07:00 time is only the Production Date cutoff, never a PLC reset rule. Do not treat the prototype envelope as an operational draft Lot, assign it to a product, or use its lower-bound count for official Production/OEE/Mould calculations.

### Required next gates

1. Keep this live path limited to explicitly authorized internal SELECT-only repository code; the SQL login itself is **not** read-only. DBA should provide a least-privilege identity before broader use or deployment. Reconfirm exact target and table permissions.
2. Factory/DBA confirms SQL `_TIMESTAMP` timezone/writer meaning, approved DropCnt quality values, maximum observation gap, expected reset/restart behavior, and acceptable bounded-query cost. Existing PRESS has no tag/time index, so bounded queries may scan; do not add a legacy index.
3. If approved, continue bounded, exact-tag DropCnt-only analysis. Report coverage, per Production Date, transitions, values/deltas, 07:00 behavior, gaps/jumps, and verified machine-state evidence separately. Keep ProductCnt history separate.
4. Factory defines and accepts actual candidate segmentation, durable source-evidence identity and actor audit, and how machine/plan/Product/Color evidence establishes Lot boundaries before operational use. No SQL write, official Lot creation, PLC/Kepware edit, commit, or push is included.
