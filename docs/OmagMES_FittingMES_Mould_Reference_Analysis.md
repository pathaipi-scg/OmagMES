# OmagMES — FittingMES Mould Management Reference Analysis

**Prepared:** 2026-11-03  
**Scope:** Read-only source review and bounded live SQL Server metadata/data inspection; design recommendations only.  
**Disposition:** No FittingMES or OmagMES source, configuration, database, or existing design document was modified. Only this requested analysis file is being created.

## 1. Scope, access and evidence labels

Verified project paths:

- Reference: `D:\AI\FittingMES` (directory exists; `.env` exists).
- Target: `D:\AI\OmagMES` (directory exists).
- Requested output: `D:\AI\OmagMES\docs\OmagMES_FittingMES_Mould_Reference_Analysis.md`.

The FittingMES `.env` was loaded locally through its established loader in [app/database.py](../../FittingMES/app/database.py); no credential values were printed or copied. The configured database resolved to **SB23**. The connection string used `ApplicationIntent=ReadOnly`; all statements issued were bounded SELECTs or metadata SELECTs. No stored procedure or user-defined database function was executed. The only SQL function calls were read-only built-ins used in SELECTs for database identification and metadata aggregation. SQL module definitions were read from metadata. The configured account's effective write permissions were not probed; no write operation was attempted. `ApplicationIntent=ReadOnly` is a connection intent, not proof that the SQL principal itself is permission-restricted.

Labels used below:

- **Verified in code**: established from checked-in application/tests/migration source.
- **Confirmed in live DB**: established from the connected SQL Server's catalog, object definitions, or bounded result rows.
- **Proposed for OmagMES**: design adaptation, not existing implementation.
- **Risk / unresolved**: requires an owner decision, data-source validation, or explicit implementation test.

## 2. Mandatory database skills

Both applicable skill files were located and read before database inspection:

1. FittingMES: [skill/DATABASE_ID_FIRST_DESIGN_SKILL.md](../../FittingMES/skill/DATABASE_ID_FIRST_DESIGN_SKILL.md) — verified absolute path `D:\AI\FittingMES\skill\DATABASE_ID_FIRST_DESIGN_SKILL.md`.
2. OmagMES: [skill/DATABASE_ID_FIRST_DESIGN_SKILL.md](../skill/DATABASE_ID_FIRST_DESIGN_SKILL.md) — verified absolute path `D:\AI\OmagMES\skill\DATABASE_ID_FIRST_DESIGN_SKILL.md`.

Both specify for new tables an opaque `id bigint IDENTITY(1,1)` primary key, `Rectime datetime NOT NULL DEFAULT (GETDATE())`, and ID-based foreign keys to authoritative rows. FittingMES's existing mould schema is legacy/current implementation and includes composite product keys and `datetime2` audit columns; its physical schema should not be copied as an OmagMES schema exception.

## 3. Source files inspected

### FittingMES

- [app/database.py](../../FittingMES/app/database.py) — dotenv loading, SQL Server driver and connection construction.
- [app/mould.py](../../FittingMES/app/mould.py) — mould reads, registration validation, mutation calls, history reads.
- [app/main.py](../../FittingMES/app/main.py) — `/mould` page and POST route handlers.
- [app/templates/mould.html](../../FittingMES/app/templates/mould.html) — mould-management template, embedded JavaScript, and CSS. There is no separate mould JavaScript file; filter persistence, dependent Product selection, confirmation and form synchronization are inline.
- [app/press_production.py](../../FittingMES/app/press_production.py) — eligible mould list, assignment validation, locks, usage reconciliation and release/correction paths.
- [tests/test_mould.py](../../FittingMES/tests/test_mould.py) — mould UI/service route tests and fake SQL behavior.
- [tests/test_press_production.py](../../FittingMES/tests/test_press_production.py) — production mould eligibility, assignment uniqueness, corrections, release/undo and rollback tests.
- [sql/023_product_family_id.sql](../../FittingMES/sql/023_product_family_id.sql) — ProductFamilyID migration, composite product relationship, `vw_MouldList`, and registration procedure definition.

### OmagMES

- [docs/OmagMES_Database_Design.md](OmagMES_Database_Design.md) — current logical design, including `Mould`, optional `ProductMouldCompatibility`, and `MouldUseEvent` candidates.
- [docs/OmagMES_Confirmed_Business_Rules.md](OmagMES_Confirmed_Business_Rules.md) — confirmed Lot/Product/line rules and unresolved mould requirements.
- [docs/OmagMES_Database_Assessment.md](OmagMES_Database_Assessment.md) — design assessment and implementation boundary.

The OmagMES documents are logical design only, not an implemented mould schema. The Press counter behavior and requirements in this request are treated as owner-confirmed inputs; no OmagMES database connection was made.

## 4. FittingMES UI, API and service workflow

### Registration and Product association

**Verified in code:** The Mould Management page reads active Product choices from `ProductCodeMaster` joined to `ProductFamilyMaster`. The registration form submits one `ProductFamilyID` and one `ProductCode`; UI JavaScript synchronizes them from one selected Product. `register_mould()` validates the name, family ID, and two-character Product Code, then calls `dbo.sp_Mould_Register`. The database procedure resolves that family/Product pair, takes the next `Seq_MouldNo` value, formats a number as `M` plus six zero-padded digits (for example `M000001`), inserts one `MouldMaster` row with status `ACTIVE` and recondition number zero, writes a `REGISTER` status-history row, commits, and returns the view row. The UI does not accept a user-supplied Mould No.

`update_mould_info()` only updates Mould name and remark; the Mould No. and Product fields are not editable through this workflow.

**Conclusion:** One FittingMES Mould row is bound to exactly one Product pair. It does not support one Mould linked to multiple Products. Separate Mould master rows would be needed for separate Product capabilities under this schema.

### Status and recondition lifecycle

**Verified in code and live procedure definitions:** Four status values are allowed: `ACTIVE`, `RECONDITION`, `RETIRED`, and `DENIED`.

- Registration creates `ACTIVE` and records `NULL -> ACTIVE / REGISTER`.
- Send to recondition is a dedicated `sp_Mould_SendToRecondition` operation. It accepts only `ACTIVE`, snapshots current-cycle and lifetime age into a new recondition-history row, sets status to `RECONDITION`, and writes `ACTIVE -> RECONDITION / SEND_RECONDITION`. `CurrentReconditionNo` does not increment on send.
- Return is a dedicated `sp_Mould_ReturnFromRecondition` operation. It accepts only `RECONDITION` and requires an open history row for the next recondition number. It closes the history row with `ReturnDate`, optionally updates its remark, increments `CurrentReconditionNo`, sets status `ACTIVE`, and records `RECONDITION -> ACTIVE / RETURN_RECONDITION`.
- The general status operation accepts `ACTIVE`, `RETIRED`, and `DENIED`, rejects direct use for `RECONDITION`, and prevents a no-op status change. The UI offers retire/deny from `ACTIVE`, and reactivation from `RETIRED` or `DENIED`. The stored procedure does not encode a narrower transition matrix for those non-recondition statuses.
- The UI displays Status History, Recondition History, and Usage / Production History. The latter joins Mould usage to `PressProduction` and `ProductionLot`.

The status and recondition procedures were inspected as definitions only; none was called. The implementation uses a recondition-history row that is opened at send and updated at return, rather than two immutable event rows.

### Status history and audit limitations

`MouldStatusHistory` records FromStatus, ToStatus, ChangeType, Remark, ChangedBy, and ChangedAt. `sp_Mould_UpdateInfo` does not write an audit-history row. The application supplies the fixed actor string `FittingMES` for registration and lifecycle/status changes; it does not identify the human operator in this module. Recondition history has no actor column and the return updates the same record; there is no separate append-only correction/audit trail for the prior values.

### Production selection and eligibility

**Verified in code:** `read_eligible_moulds()` selects from `vw_MouldList` and filters by the Lot Product family/code and `Status='ACTIVE'`. An “already assigned” indicator considers unreleased `PressProduction` assignments for the selected production date and, when supported, shift. On save, server-side validation re-reads the Mould under `UPDLOCK,HOLDLOCK`, checks existence, `ACTIVE` status, and exact Product family/code match. The database is authoritative; the selector is not the only check.

A mould cannot be assigned to more than one active Press assignment in the same production date/shift scope. Production allocation uses transaction-owned application locks keyed by date/shift and Press/Mould, plus locked assignment queries. Unknown legacy shift assignments block allocation instead of being guessed.

### Usage and corrections

FittingMES `MouldUsage` is associated one-to-one with a `PressProduction` row. On an eligible production save, it writes `UsageCycles` from that row's `CounterQty`; this is the application's entered production counter quantity, not proof of a continuous PLC counter interval. The service inserts a usage row when absent and updates the existing row in place when reconciling an edit. A Mould-only correction retains the existing PressProduction identity and persisted quantities, updates the usage Mould/ReconditionNo as appropriate, and does not add the cycles a second time. Release retains the prior assignment/usage history; undo/reassignment paths are guarded against a Mould already being reassigned.

The database unique index on `MouldUsage.PressProductionID` prevents duplicate usage rows for one PressProduction. `UsageCycles` is constrained nonnegative. Exceptions roll back the encompassing application transaction. Tests cover no duplicate rows/cumulative increment on repeated edits, Mould reassignment correction, release retention, availability conflicts, and rollback.

**Important difference:** FittingMES's `CounterQty` and `MouldUsage.UsageCycles` are stored as per-PressProduction quantities. OmagMES's confirmed `PRESS.ProductCnt` is Press strokes, not finished pieces; that source value must not be copied into FittingMES's production-quantity semantics.

## 5. Live FittingMES database objects and actual relationships

The actual configured database was `SB23`. Catalog inspection confirmed these relevant objects:

- Tables: `dbo.MouldMaster`, `dbo.MouldReconditionHistory`, `dbo.MouldStatusHistory`, `dbo.MouldUsage`.
- Views: `dbo.vw_MouldLifeSummary`, `dbo.vw_MouldList`, `dbo.vw_MouldReconditionHistory`.
- Procedures: `dbo.sp_Mould_Register`, `dbo.sp_Mould_UpdateInfo`, `dbo.sp_Mould_SendToRecondition`, `dbo.sp_Mould_ReturnFromRecondition`, `dbo.sp_Mould_SetStatus`.
- Number generator: `dbo.Seq_MouldNo`.
- Relevant Product/production tables: `dbo.ProductFamilyMaster`, `dbo.ProductCodeMaster`, `dbo.PressProduction`, `dbo.ProductionLot`.

### Actual keys and important constraints

| Object | Confirmed keys/relationship |
|---|---|
| `MouldMaster` | PK `MouldID` (`bigint`); unique `MouldNo`; Product is stored as `ProductFamilyID` plus `ProductCode`. Composite FK from those two columns to `ProductCodeMaster(ProductFamilyID, ProductCode)`. Check constraint allows only the four stated statuses. |
| `MouldReconditionHistory` | PK `ReconditionID` (`bigint`); unique `(MouldID, ReconditionNo)`; FK `MouldID -> MouldMaster.MouldID`. |
| `MouldStatusHistory` | PK `StatusHistoryID` (`bigint`); FK `MouldID -> MouldMaster.MouldID`; nonunique index `(MouldID, ChangedAt)`; ToStatus check. |
| `MouldUsage` | PK `MouldUsageID` (`bigint`); unique `PressProductionID`; FKs `MouldID -> MouldMaster.MouldID` and `PressProductionID -> PressProduction.PressProductionID`; nonnegative `UsageCycles`. |
| `PressProduction` | FK `MouldID -> MouldMaster.MouldID`. |

The inspected relevant FKs were enabled and trusted. Product capability is **not** a many-to-many relation: a MouldMaster row contains one Product pair. The existing Product pair key is a composite natural key in `ProductCodeMaster`, unlike OmagMES's mandated ID-first design.

`MouldMaster` has `MouldID`, `MouldNo`, `MouldName`, `ProductFamily`, `ProductFamilyID`, `ProductCode`, `Status`, `CurrentReconditionNo`, `Remark`, `CreatedAt`, and `UpdatedAt`. It does **not** store CurrentAge or LifetimeAge. Mould history tables use `datetime2`/`date` fields and `CreatedAt`; they do not have the Omag skill's new-table `Rectime datetime` convention.

`MouldReconditionHistory` stores `CycleCountBefore` as nullable `int` and `LifetimeCountAtRecondition` as nullable `bigint`. The send procedure caps the saved CurrentAge to `int` max. `MouldUsage.UsageCycles` is `int`; CurrentAge/LifetimeAge are `bigint` aggregates. The live Mould master Remark is `nvarchar(1000)`, while some application/procedure validation parameters permit up to 2,000 characters; this is a length mismatch risk for long remarks.

## 6. Current Age and Lifetime Age — actual calculation

**Confirmed in live view definition:** `vw_MouldLifeSummary` derives both values from all rows in `MouldUsage` for a Mould. These are not stored columns on `MouldMaster` and are not recalculated from `PressProduction` timestamps or an external live counter.

$$
\text{LifetimeAge}(m) = \sum_{u:\,u.MouldID=m} u.UsageCycles
$$

$$
\text{CurrentAge}(m) = \sum_{u:\,u.MouldID=m\;\land\;u.ReconditionNo=m.CurrentReconditionNo} u.UsageCycles
$$

No matching usage rows yields zero via `COALESCE`. `UsageRecordCount` is the number of usage records; `LastUsageDateTime` is their maximum usage timestamp.

At send-to-recondition, current/lifetime totals are snapshotted. The current recondition number remains unchanged while status is `RECONDITION`, so the view still represents the old cycle during servicing. On return, `CurrentReconditionNo` advances; the view's current-cycle sum becomes zero until usage is recorded against the new cycle, while the lifetime sum remains cumulative.

**Live data cross-check:** bounded rows showed a Mould at recondition cycle 2 with Current Age 70 and Lifetime Age 220; its second recondition snapshot recorded 150 lifetime/current cycles before that return. Another returned Mould showed Current Age 0 and Lifetime Age 500, with historical recondition snapshots preserving the prior cumulative value. These samples agree with the view definition; they are examples, not a population-wide reconciliation.

## 7. Live database versus source and test evidence

The live schema and definitions confirm the implementation model described above. Bounded samples also contained active and denied Mould statuses, returned recondition rows, zero-usage Moulds, and usage records linked to PressProduction IDs. A bounded query initially used the wrong guessed recondition-history key name and returned a query error; the catalog exposed the actual `ReconditionID`, after which bounded SELECT inspection succeeded. No modifications resulted.

The checked-in migration `023_product_family_id.sql` defines the current composite Product relationship, Mould list view and registration procedure, but the live database is the source used here for the current recondition, life-summary, key and constraint definitions. The complete current recondition procedures and life-summary view were not present in the inspected checked-in migration, so no claim is made that that migration alone reproduces the complete live schema.

**Verified in code/tests is not the same as live production behavior:** the unit tests use fake connections and do not execute SQL Server transactions or prove production concurrency. Live catalog/data inspection confirms stored definitions and sample state; it does not prove all historical rows are consistent or that every race condition has occurred.

## 8. Differences and required OmagMES adaptations

| Topic | FittingMES reference behavior | OmagMES requirement/adaptation |
|---|---|---|
| Product capability | One Product pair in each Mould master. | One Mould may support multiple approved Products; use a separate Mould Settings/capability relation. Validate exact Product ID and effective approval. Never add Mould-to-Color capability. |
| Lot boundary | Fitting Press Production is attached to an existing Lot; Mould selection is assignment data. | Keep Omag's rule: new Lot for Product shape or coating Color change; pause without either change retains Lot. Mould change alone does not split a Lot. Mould-use intervals must link to the Lot and production Run. |
| Age source | Sum of entered `MouldUsage.UsageCycles` (from `CounterQty`). | Count Press strokes from read-only `OMAG.dbo.PRESS` history, specifically `OPC.OMAG.OMAG.PRESS.ProductCnt`. Do not treat strokes as finished quantity or multiply by pieces per stroke for mould life. |
| Usage grain | One usage row per PressProduction; no explicit start/end interval or counter sample FK. | Capture actual Mould-use intervals and reconcile counter samples to intervals; retain raw source reference, source timestamp, value and quality. |
| Recondition reset | Advance the recondition number only on return; current age is a view sum filtered by that number. | Preserve reset-on-approved-return and lifetime accumulation, but define explicit approval and an auditable stroke-ledger baseline/cycle identifier. |
| Audit/correction | Status history exists; info and usage corrections update current rows without a full before/after correction ledger. | Append-only actor/time/reason audit; preserve original counter allocations and represent corrections by reversal/replacement or adjustment entries. |
| Database conventions | Existing schema includes `MouldID`, composite Product key, `CreatedAt datetime2` and some narrower integer columns. | Apply Omag's verified ID-first `id bigint IDENTITY` and `Rectime datetime` rule for every new table; reference existing authoritative Product/Mould/Run/Lot IDs. |

## 9. Proposed OmagMES Mould Management architecture

These are recommendations, not implemented schema. Use the existing OmagMES logical model's `ProductionRun`, `ProductionLot`, `Mould`, and `MouldUseEvent` concepts, with the changes below.

### Mould Master and Product capability settings

- **Mould Master:** immutable surrogate ID, independently registered Mould Number/business code with a unique constraint, name/serial/description as appropriate, current status, registration/retirement metadata, and current recondition-cycle pointer. Number issuance must be database-controlled and concurrency-safe; never derive identity from Product, Color, LotName, or a numeric ID's meaning.
- **Mould Product Capability / Mould Settings:** separate MouldID-to-ProductID mapping with active/approved status, effective dates where required, approval actor/time/reason, and history. Enforce one active row per exact Mould/Product mapping and prevent conflicting effective periods. Settings do not include Color. Do not infer capabilities from historical usage or code shape.
- **Registration:** resolve the Product and optional metadata against authoritative masters on the server; generate a unique Mould Number in a transaction; create initial status-history record atomically. Decide whether newly registered tools are immediately eligible or require a commissioning/approval state.

### Status and recondition workflow

- Keep explicit `ACTIVE`, `RECONDITION`, `RETIRED`, `DENIED` semantics if owners approve those exact labels. Production eligibility is `ACTIVE` only. Restrict transition commands on the server; recondition is a dedicated workflow, not a generic status edit.
- Record append-only status events with MouldID, old/new status, event type, actor ID, timestamp, and required reason. Audit Mould metadata and Product-capability changes separately.
- Recondition history should preserve the send event and approved return as auditable lifecycle facts. Store cycle number, sent-at/date, approved-return-at/date, actors, reason/service reference, and CurrentAge/LifetimeAge snapshots at send and return where useful. Do not silently overwrite prior event values.
- Only an approved return advances the cycle/reset boundary. Keep the servicing cycle frozen while status is `RECONDITION`; after return the new Current Age is zero and Lifetime Age remains the sum across all cycles. Retired/Denied reactivation must be explicitly permitted/audited; reactivation must not clear either age.

### Mould-use intervals and Press counter history

- Represent each Mould assignment/use as a time interval linked by IDs to Mould, ProductionRun, and original ProductionLot, with start/end event times and actor/source. A change to another Mould closes one interval and opens another in the same Run/Lot when Product and Color are unchanged. Product/Color changes follow Omag's separate Run/Lot boundary rules.
- Treat `OMAG.dbo.PRESS` as a read-only legacy source. Do not update it, reset it, or add application ownership of its rows. In the Omag namespace, ingest/reference eligible samples using the stable source row identity if one exists, tag name, `_TIMESTAMP`, `_VALUE`, and `_QUALITY`; deduplicate by source identity or a documented stable composite. Preserve raw value/time/quality for audit.
- Maintain a stroke allocation/life ledger whose additive rows are idempotent and attributable to a Mould-use interval and recondition cycle. A derived summary may expose Current Age and Lifetime Age, but the ledger—not a manually editable total—is the basis. Avoid storing both a cumulative total and its constituent increments as independently additive facts.
- On every Mould assignment change and approved recondition return, capture/associate a trustworthy counter sample at the boundary when operationally possible. An interval needs an explicit start and end counter boundary; samples are matched by event time, not merely by Lot name or daily totals.

### Reset-aware calculation and uncertainty controls

- Interpret timestamps in the confirmed `Asia/Bangkok` operating timezone and identify the daily reset boundary at 07:00 local time. Normalize timestamps consistently while retaining source timestamps. Split counter deltas at each reset; do not treat a negative difference across 07:00 as a real negative increment or as a full-day wrap.
- Within a reset segment, accept only good-quality, ordered samples. For a monotonic same-day pair, the candidate increment is `new_value - old_value`; equal samples contribute zero. A negative same-segment delta is an anomaly requiring a documented reset/rollover decision, not an automatic positive correction.
- At the daily 07:00 reset, establish a new zero-based segment. A sample after reset can establish the new segment baseline/delta. If the last pre-reset sample is missing or stale, the unknown strokes between that sample and reset must remain explicitly unresolved; do not fabricate them from the new day's value. Counter samples that are stale, bad-quality, duplicated, out of order, or missing should create a visible gap/exception and a lower-confidence or unknown allocation, not an invented number.
- If a Mould change occurs between two counter samples, the delta spanning those samples cannot be assigned exactly to either Mould. Capture a boundary reading; otherwise retain an unresolved segment for operator/supervisor reconciliation. Do not prorate by elapsed time, production output, or assumed constant speed without an approved rule.
- Process each source sample pair/reset segment exactly once. Make the ingestion/allocation operation idempotent, enforce unique source identities/segment keys, and use transactional locks around current Run/Mould/cycle assignment and ledger insertion. Store corrections as append-only reversal/adjustment entries referencing the original ledger entry, with actor, reason, and source evidence. Recomputed totals must exclude reversed entries exactly once.

### Production eligibility validation

On selection and again during the authoritative server-side save transaction, require: registered Mould; current `ACTIVE` state; an active approved Mould Settings mapping for the exact Product ID on the selected Lot; valid effective dates; and no conflicting open Mould-use interval or machine assignment. Serialize concurrent selection/assignment using row/key locks or transaction-scoped application locks plus uniqueness constraints. UI filtering is convenience only. Color is deliberately not a Mould eligibility dimension.

## 10. Unresolved questions and implementation risks

1. Confirm the authoritative Omag Mould register, Mould Number format/uniqueness scope, identity/serial data, commissioning state, and duplicate-registration policy.
2. Confirm Product capability approval owner, whether capability is effective-dated, whether a Product may be removed from a Mould, and how historical capability changes are retained.
3. Confirm who may approve recondition return, whether status changes require separate authorization, the exact status transition matrix, and whether recondition dates are local dates or timestamps.
4. Confirm how the Press counter is sampled, `_QUALITY` acceptance policy, counter value type/range, stable source-row identity, polling gaps, and availability/retention. The legacy `PRESS` table was not independently inspected in this read-only reference exercise.
5. Confirm whether `_TIMESTAMP` is local time or UTC and establish exact 07:00 reset semantics (including downtime, daylight/clock changes, and samples exactly at reset).
6. Determine whether counter samples bracket Mould changes closely enough to allocate strokes. Missing pre-reset samples and Mould changes between samples create fundamentally unknowable portions unless operational boundary readings or an approved reconciliation policy exist.
7. Define correction authorization, evidence, approval, recomputation policy, and whether a historical usage interval may be corrected after downstream production/quality records exist.
8. Confirm what happens to an active Mould-use interval during a long pause, line stoppage, automatic forklift transfer, or a change of Lot/Color; the Press counter continues independently of Lot and Mould selection.
9. Confirm how production strokes relate to machine state and what portion of Press strokes counts toward mould wear (e.g. setup/test strokes). Do not infer finished pieces per stroke.
10. FittingMES uses integer `UsageCycles`, and its recondition snapshot narrows Current Age to `int`; Omag's stroke scale and lifetime duration should be sized safely using the confirmed ID-first and event-ledger conventions.
11. FittingMES's status/recondition procedures perform validation reads before starting their explicit transaction and do not use the same explicit lock protocol as its production-assignment service. Its production path has locks and a unique usage index, but unit tests with fakes do not prove all concurrent SQL behavior. Omag should serialize lifecycle transitions, interval boundaries, and assignments in one authoritative transaction and test races against the real SQL Server engine.
12. The reference schema's mutable usage correction path does not provide complete before/after audit. Omag should not copy that limitation; append-only ledger corrections are recommended.

## Review conclusion

FittingMES supplies a working reference for registration, generated numbering, single-Product capability, status/recondition history, derived age, ACTIVE-only production assignment, and in-place production usage reconciliation. Its core age calculation sums manually entered per-assignment `UsageCycles`; it does not solve OmagMES's continuous, daily-reset Press-stroke attribution problem. OmagMES should retain the useful workflow concepts while replacing single-Product storage with explicit Mould Settings, treating counter history as a read-only source, deriving life from reset-aware interval allocations, and preserving correction/audit history. This report is for review before any implementation.
