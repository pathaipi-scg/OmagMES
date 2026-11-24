# OmagMES — Factory Requirements and Implementation Handoff

**Status:** Requirements collected through 2026-11-10; updated 2026-11-17. The factory owner has explicitly directed applying Migrations 003 and 004 to the existing `OMAG` database (no separate test database), while preserving Migration 002 and all legacy objects. Execution is currently **blocked**: the verified `OMAG_MES` login lacks DDL permission and no full-backup record was found in `msdb`. No migration or database write has been executed. This instruction does not authorize master-data import, quality-policy activation, Grafana/candidate grants, official Lot saves, or changes to `dbo.PRESS`.

## 1. Mandatory implementation conventions

- Use **English** for all database schema/table/column names, API properties, application variables, and technical field labels. Examples: `ProductCode`, `ProductNameTH`, `StandardPiecesPerDrop`, `StandardCycleTimeSec`, `MouldNo`, `CurrentAgeDrops`, `LifetimeAgeDrops`.
- Thai product names and Thai operator-facing text may remain as **data/display values**; do not create Thai-named database columns copied from Excel.
- Inspect actual Excel workbook sheets/headers/types before mapping. Do not assume example column names are the physical workbook headers.
- Reuse the **FittingMES** menu layout and Setting/Mould management workflow as a UI/behavior reference, adapting to OmagMES's distinct business rules. Never change FittingMES itself.
- Before database-related work, locate, verify, read and report the applicable database skills in **both** `D:\AI\OmagMES` and `D:\AI\FittingMES`. Follow ID-first conventions and use a dedicated `omagmes` schema for new approved tables. Existing `OMAG.dbo` objects remain read-only.
- Maintain `docs/OmagMES_Development_Progress.md` with status, decisions, blockers, tests and resume instructions. Do not commit/push or execute migrations without separate authorization.

## 2. Reference sources

### Existing factory master workbooks

- `D:\AI\OmagMES\Master\Omag_Product_Master.xlsx`
- `D:\AI\OmagMES\Master\Omag_Mould_Master.xlsx`

Both workbooks were inspected locally in read-only mode on 2026-11-10. Sheet/column findings and duplicate/conflict counts are recorded in [the development handoff](OmagMES_Development_Progress.md). Inspection is not approval to import or resolve conflicts; do not assume the entire Excel data is approved for direct import.

### Production planning source

- SQL Server: `10.28.255.98`, database `OMAG`.
- `OMAG.dbo.OmagPlan` is a **SQL Server synonym** pointing to the production planning server. It already exists; do not recreate it or build a new planning-server integration.
- Observed planning columns include `MaterialCode`, `MaterialName`, `PlanName`, `Machine`, `PlanCount`, `StartTime`, `Duration`, `Shift`, `PlanWeek`, `VersionNo`, `Plant`, `Company`, `OperationCode` (verify actual metadata).
- Treat this source as read-only. Be mindful that querying the synonym reaches an external server.

### Existing machine / quality data sources

- PLC/HMI -> Kepware -> existing `OMAG.dbo.PRESS` and `OMAG.dbo.REJECT_WET` data tables.
- IP camera -> existing `OMAG.dbo.product_count` table; do **not** imply the camera flows through Kepware unless verified.
- Factory-confirmed Kepware mapping: `OMAG.PRESS.ProductCnt` and `OMAG.PRESS.OEE.DropCnt` both address `DB3.DBW2`, type Word, scan 100 ms, and are aliases for the same physical Press Drop counter. Historically, ProductCnt was logged to SQL once per hour; the factory recently switched to logging DropCnt whenever its value changes. Use DropCnt as the authoritative source for **new Auto Lot Detection**; ProductCnt is historical reference data only. **Never merge, union, or sum the histories.** The 07:00 time is the Production Date cutoff, not a PLC reset rule. ProductCnt decreases can occur at any time and are evidence of possible new Product runs, not proof of a Product/Color change; a reset alone never creates a Lot. On-change logging produces no row while the value is unchanged, so absence of rows does not show the press stopped. Persisted keys are `_NAME='OMAG.PRESS.OEE.DropCnt'` and `OPC.OMAG.OMAG.PRESS.ProductCnt`.
- SQL access finding: the test connected to the expected host/database identity, but the tested login had effective SELECT, INSERT, UPDATE, DELETE, ALTER and CONTROL permissions on `dbo.PRESS`. The validation issued SELECT statements only and made no writes, but this login is not SELECT-only. Do not enable live application reads with it; obtain a DBA-provisioned least-privilege identity first. The PRESS table has `id`, `_NAME`, `_NUMERICID`, `_VALUE`, `_TIMESTAMP`, `_QUALITY` columns and only a clustered primary-key index on `id` (no tag/time index).
- Kepware Server 7 Data Logger -> PRESS logs `OMAG.PRESS.OEE.AutoRun`, `AutoStart`, `DropCnt`, `ResetProduction`, `StartProduction`, `StopProduction`, and `ElevatorFull`. PRESS Trigger1 is change-based: Log on Data Change Yes; Log on Static Interval No; Monitor Item No; Deadband None. This is not continuous fixed-interval sampling; **missing SQL rows do not prove machine stoppage**. Do not modify PLC or Kepware configuration.
- The detailed Auto Lot workflow, draft-vs-official Lot distinction, and SQL verification gates are recorded in [OmagMES_AutoLot_Mould_Assignment.md](OmagMES_AutoLot_Mould_Assignment.md).
- `PRESS.AutoRun` is machine-state evidence, not a substitute for operator-approved time classification.
- `REJECT_WET.cntR*` represents cumulative reason quantities; `R*` momentary bits are not reject quantities.
- Wet camera `product_count.value_cnt` is **per-tray Pieces**, not a cumulative counter. Wet and Dry data must remain separate.
- Existing collection is already connected and running; the OmagMES application may consume existing SQL sources read-only after source/identity/timezone/permission verification.

## 3. Product Master and manual GET UPDATE PRODUCT

### Factory-confirmed behavior

1. The production plan's `MaterialCode` (exact `ZCC...` Product Code) is the key used to look up Product Master.
2. Product Master contains product name and production standards: **Pieces per Drop** and **Cycle Time (seconds per Drop)**. These standards belong to the Product, not to the Mould.
3. OmagMES must provide an editable **SETTING -> PRODUCT MASTER** page for adding/editing future products and standards.
4. Provide a **GET UPDATE PRODUCT** button. **Only when explicitly clicked**, query distinct `MaterialCode` values from `OMAG.dbo.OmagPlan`, compare with the OmagMES Product Master, and surface/add newly discovered Product Codes to the local master workflow. Do **not** query the synonym automatically on page open, on every page refresh, or on a background schedule.
5. Existing Product Codes must be matched exactly and never duplicated or have approved standards overwritten by the discovery operation.
6. Newly discovered products must be visible as **Pending Standard**, with Pieces/Drop and Cycle Time empty until an authorized operator fills and saves them. Never invent defaults.
7. Show update results (new/existing/error and last attempted/successful update). If the planning server is unavailable, preserve the existing master.
8. A Product that disappears from a recent plan must **not** be deleted from Product Master.
9. Maintain edit/audit history. Preserve the historical standard used by old Lots/OEE; later master edits must not silently recalculate historical results.
10. Product Standard Speed (Drops/min) is calculated as `60 / StandardCycleTimeSec`, where Cycle Time > 0.

### Bounded DropCnt history check (2026-11-17; evidence, not factory-rule approval)

- Separate exact-tag, parameterized SELECTs queried raw SQL wall-clock interval `[2026-11-10 07:00, 2026-11-17 07:00)`: DropCnt 11,527 samples; ProductCnt 27 samples. No alias histories were combined. The current verified SQL identity was `OMAG_MES` in OMAG; the inspection issued no writes and reported no source write capability. The local secret was not displayed or changed.
- DropCnt samples were quality 192, nonnegative integers; 27 decreases were observed across different times of day. They are decrease/reset-like events only, not verified resets or Product/Color boundaries. The maximum adjacent gap was 20.012 minutes. Nov 15 had 144 repeated observations of value 108 at about 10-minute intervals, which needs logger/source review.
- ProductCnt's 27 samples were confined to Nov 10 and did not bracket the DropCnt events. No paired timing consistency result was established. The bounded check compared raw SQL datetime values without timezone conversion; writer/timezone semantics remain unconfirmed. Quality 192 and a 30-minute gap parameter remain provisional. Positive-delta sums are lower-bound source calculations, not certified production totals.

### Review needed before implementation

- Determine how the Product Master workbook maps to English schema fields and whether any duplicate/conflicting standards exist for the same exact Product Code. Previously reviewed historical reports had conflicting standards; do not silently pick one.
- Decide whether discovery only previews missing Product Codes until SAVE or creates **pending** master rows immediately. In either case, no standards are fabricated and no existing rows are overwritten.
- Define how multiple `MaterialName` values for the same `MaterialCode` are handled; distinct by **MaterialCode**, not by every combination of code and name.
- Verify safe query strategy and permissions against the planning synonym; run it only on button click.

## 4. Automatic Lot No. generation

### Draft detection and official Lot separation

- First detect editable **draft production records**, not official Production Lots, from the read-only SQL history of preferred tag `OMAG.PRESS.OEE.DropCnt`; candidate segments use counter activity and resets as evidence, but a counter reset alone does not establish a Product or Color change.
- Drafts retain a stable internal identity, detected start, detected end when available, raw PLC Drop count, operator-confirmed Drop count, and review status. Operators may correct times/quantities or delete/dismiss an invalid draft without changing raw PLC evidence.
- Only after draft review may an operator select a Production Plan, take its `MaterialCode`, resolve the exact Product Master key, use approved Product standards, assign one or more Moulds, and explicitly save/confirm the official production information.
- Draft detection does not itself assign an official Lot No. Draft internal IDs and official immutable Production Lot IDs are separate concepts; assign a human-readable official Lot No. only after the relevant production information is confirmed.
- Product and Color define the confirmed Lot boundary. A Mould change alone does not create another official Lot. Do not infer a Product/Color change from a counter reset.
- See [OmagMES_AutoLot_Mould_Assignment.md](OmagMES_AutoLot_Mould_Assignment.md) for the full sequence and unapproved technical design proposals.

**Implementation status (2026-11-17):** A fail-closed read-only candidate API and Production-page evidence review UI now exist. When enabled with every source safety policy approved, the API queries only the exact `OMAG.PRESS.OEE.DropCnt` tag inside the selected Production Date's persisted cutoff window. It emits at most one explicitly uncertain observed-activity envelope per Production Date, not a verified machine run or Lot segment; a positive adjacent counter transition is required. Gaps, decreases/resets, invalid quality, timestamp order/conflicts, statistical outliers, and lower-bound count semantics are displayed as evidence/warnings. Operator corrections/review/dismissal are process-local only and never update PRESS or create an official Lot. Current source mode remains `MOCK`; the target, SELECT-only identity, historian metadata, timestamp timezone, quality codes, and gap threshold are not configured/confirmed. Therefore no Phase 2 live PRESS query or comprehensive current-history analysis has been performed, and this UI currently returns unavailable without querying source SQL. The prior 332-row observation below is historical limited evidence only, not a current revalidation or adequate basis for segmentation.

### Confirmed format

`C` + `DD` + `MM` + `YY` + `Shift` + `Sequence2` + `B`

Example: `C021126201B` means factory C, production date 02 Nov 2026, shift 2, second-digit sequence 01, Block factory B.

- Factory prefix is always **C** for this factory.
- Factory suffix is always **B** (Block). Fence uses F elsewhere, but this factory is Block.
- Shift 1: **08:00–19:00**.
- Shift 2: **19:00–06:00 the next calendar day**; use the **production date on which Shift 2 began** in its Lot number, including after midnight.
- Sequence starts at **01 per production date and shift** and increases when a new Lot is created. Avoid duplicate Lot numbers and sequence reuse after void/cancellation.
- **Create a new Lot when Product changes OR coating Color changes**, including returning to a previously produced Product/Color combination.
- When Shift 1 starts a Product Lot and Shift 2 continues the same Product without counter-reset evidence or Color change, continue the original Lot. Do not split at shift boundaries or the 07:00 Production Date cutoff. Preserve immutable `ProductionLot.id`, official SCG Lot No., original Lot-start Production Date and Shift Code, Product, Color, and Lot start time.
- Production quantities from later shifts or Production Dates continue referencing the same original `ProductionLot.id`, while each quantity entry stores its own actual production timestamp, resolved Production Date, Shift identity, and applicable schedule version. `RecordedAt` remains the save/audit time, separate from the production occurrence.
- A new Lot's SCG number uses the Production Date and Shift applicable at that new Lot's start; it does not replace or rewrite the prior Lot's number/context.
- **Do not create a new Lot merely because the physical Mould is changed**, including Mould breakdown/replacement, as long as Product and Color remain the same.
- Keep immutable internal `ProductionLot.id`; human-readable Lot No. is separate. Preserve end-to-end Lot identity for Production -> Curing -> Depallet -> Dispatch.
- A shift boundary and Production Date cutoff alone never create a new Lot. Same Product + same Color continues the existing Lot, regardless of counter silence or shift/date; Product or Color change is the Lot boundary.

### Open questions / validation gates

- Define how 06:00–08:00 is treated (outside the stated two shifts).
- The 19:00 cross-shift continuity rule is owner-confirmed: preserve the original Lot. More than 99 newly started Lots in one Production Date/Shift still exhausts the two-digit sequence; never wrap or reuse. An operational escalation/numbering-extension process remains to be approved.
- Confirm production-date and timezone handling and exact numbering/locking strategy under concurrent saves.
- Confirm if manual Lot No. correction is permitted; preserve audit and immutable ID.

## 5. Lot-to-Mould relationship and traceability

- Factory reports currently record **Lot No. and Mould No. together**.
- One Lot may have **multiple sequential Mould assignments** when a Mould is replaced, while retaining the same Lot if Product and Color are unchanged.
- Track `ProductionLotId`, `MouldId`, assignment start/end timestamps, and Press Drops attributable to each Mould, using actual verified schema names.
- A physical Mould belongs to exactly **one Product**; a Product may own multiple physical Moulds. Check Product compatibility when assigning.
- Prevent physically impossible overlapping Mould assignments; an eligible Mould can be reused when its previous assignment has ended.
- Use actual factory Mould numbers (e.g. `NKFL...`) as externally visible identifiers, with separate immutable internal IDs. Do not replace original numbers with arbitrary generated identifiers during import.

## 6. Mould Master and lifecycle management

### Factory-confirmed behavior

- Existing Mould Master is supplied as an Excel workbook; create a dedicated editable **SETTING -> MOULD MASTER** page.
- Inspect and adapt the UI and workflows from `D:\AI\FittingMES` **SETTING -> Mould** rather than inventing an unrelated interface.
- Support registration of new physical Moulds, editing permitted master attributes, Product association, Active/Inactive or other verified lifecycle statuses, **Send to Recondition**, **Return from Recondition**, retirement/denial where appropriate, remarks, status history, repair/recondition history and production usage history.
- Each Mould's age is counted in **Press Drops only**, never Pieces.
- `CurrentAgeDrops` accumulates since the most recently approved return from reconditioning; reset it only after that approved return event.
- `LifetimeAgeDrops` is cumulative across the entire life of the physical Mould and never resets.
- The 07:00 Production Date cutoff is **not** a PLC reset rule. ProductCnt/DropCnt decreases may occur at any time; preserve them as evidence/uncertainty. A counter reset alone never proves Product or Color changed and never creates a Lot. PLC counter changes do not reset Mould age.
- If Mould A is replaced with Mould B during the same Lot, split Drop attribution by verified installation intervals. Never attribute all Lot Drops to both Moulds.
- Preserve auditable lifecycle events, timestamps, operator, reason, and histories.
- Do not allow assignment of a Mould that is in repair, retired, denied or otherwise not production-ready.

### Review needed

- Inspect exact Mould workbook columns and data quality; establish stable mapping and safe first-import review before any database writes.
- Confirm how a particular physical Mould's installed interval is established and how missing/gapped counter observations are handled; do not fabricate Drops.
- Verify which FittingMES lifecycle statuses and actions transfer unchanged versus require OmagMES adaptation.

## 7. Settings navigation and UI reference

- Place **all master-data management** under **SETTING**, including Product Master, Mould Master and Reject Reason Master; other master pages may be added as verified.
- Use the compact gray/blue FittingMES visual language and horizontal tab/menu patterns where appropriate.
- Reuse FittingMES Mould Management layout concepts: filterable Mould list, registration form, selected Mould details, lifecycle buttons, Status History, Recondition History and Usage/Production History.
- Keep OmagMES-specific Production, Wet Run Log, Wet Reject, Wet OEE, Curing and Depallet workflows distinct; UI copying must not import FittingMES-specific manufacturing logic.

## 8. Production, AutoCal and OEE safeguards

- One physically coupled **Wet Press + Wet Line** is the Wet production unit; Dry/Depallet remains independent and must not affect Wet OEE.
- Press stroke = **one Drop** (one tray/pallet), not one Piece.
- Production quantities (Drops), Wet camera good Pieces and Wet Reject reason quantities use separate, correctly typed sources.
- For each Lot, AutoCal may suggest values; operator may edit; only explicit **SAVE** approves/persists. Never save as a side effect of AutoCal.
- Until approved SQL integration, preserve clearly marked mock behavior and do not misrepresent simulated values as live.
- Wet OEE: Availability = OperatingTime / PlannedProductionTime; Performance = ActualDrops × StandardCycleTimeSec / OperatingSeconds; Quality = WetCameraGoodPieces / (ActualDrops × StandardPiecesPerDrop). Require approved data/standard snapshots before production use.
- Keep legacy `OMAG.dbo` source tables and the planning synonym read-only. New OmagMES writes must use approved `omagmes` schema only after explicit authorization.

## 9. Copilot workflow / acceptance checks

1. Read this entire requirements document and the existing `docs/OmagMES_Development_Progress.md` before coding.
2. Read both master workbooks **locally on the user's machine**, inspect sheet names, exact column positions, data types, duplicate keys and missing standards; summarize mapping with English target field names.
3. Inspect FittingMES Setting/Mould UI and relevant backend services as a reference, without editing FittingMES.
4. Locate/read/report both projects' database skills before database design or SQL work.
5. Produce an implementation plan and list unresolved factory decisions before any destructive or production-writing step. Migration 003/004 deployment was separately authorized by the owner on 2026-11-17, subject to a verified backup, no-overwrite preflight, and an authorized DDL identity.
6. Keep read-only SQL discovery separated from approved master-data writes; do not assume `.env` SQL host or production access is verified merely because the UI runs on port 3001.
7. Implement only the scope the user subsequently authorizes. Add tests for exact Product Code matching, idempotent GET UPDATE PRODUCT, pending standards, Mould lifecycle, Mould Drop age, Lot numbering, shift/date boundaries and audit.
8. Update the progress handoff after each meaningful milestone, including what was actually verified and what remains pending.
9. Do not commit/push, import workbook rows, or modify production SQL outside explicitly approved scope. The 2026-11-17 owner authorization covers only Migrations 003/004 on existing OMAG; the later Press Diff authorization confirms `_QUALITY` is informational and authorizes only the targeted quality-independent view fix. It does not waive the required DDL identity/permission or any unrelated safety gates, and raw timestamp semantics remain unresolved.

## 10. Decision register

| Area | Decision | Status |
|---|---|---|
| Planning source | Read `OMAG.dbo.OmagPlan` synonym, no new planning integration | Confirmed |
| Product discovery | Only on **GET UPDATE PRODUCT** click | Confirmed |
| Product identity | Exact `MaterialCode` / `ZCC...` match | Confirmed |
| Product standards | Product-owned Pieces/Drop and Cycle Time | Confirmed |
| Master UI | All master pages under SETTING, FittingMES-inspired | Confirmed |
| Mould lifecycle | Register, edit, repair/send, return, history | Confirmed |
| Mould age | Drops only; Current vs Lifetime | Confirmed |
| Mould swap | Same Lot if Product/Color unchanged | Confirmed |
| New Lot trigger | Product or Color change | Confirmed |
| Lot numbering | `C` + DDMMYY + Shift + sequence + `B` | Confirmed |
| Shift times | Shift 1 08:00–19:00, Shift 2 19:00–06:00 | Confirmed |
| Kepware counter aliases and historian | Same PLC counter; ProductCnt logged hourly in the former configuration; recently switched to change-based DropCnt. Use DropCnt for new Auto Lot Detection, ProductCnt as historical reference only; never merge/sum histories; timestamp transitions from `_TIMESTAMP` after semantics check | Mapping and logging change factory-confirmed; persisted names/schema and short DropCnt sample verified |
| Data Logger | PRESS Trigger1 change-based; no static interval, monitoring, or deadband | Factory-confirmed configuration |
| Auto Lot | Detect/review draft before plan selection; raw PLC data immutable; operator may correct/delete/dismiss draft | Confirmed |
| Official Lot assignment | Draft detection is separate; assign official Lot ID/number after operator confirms production information | Confirmed |
| Reset as Lot boundary | Counter reset alone does not establish Product or Color change | Confirmed |
| 06:00–08:00 | Treatment unknown | Open |
| Cross-shift Lot continuity | Same Product + same Color continues original Lot across shifts and 07:00 cutoff; per-entry reporting retains actual occurrence context | Confirmed 2026-11-17 |
| DropCnt SQL history | Persisted `_NAME`, `_TIMESTAMP` meaning/timezone, quality, change-based transition history and query performance | `_NAME`, columns, and short sample verified; timestamp semantics/reset unresolved; least-privilege login required; shorter history expected after recent switch |
| First master import | Excel mapping, conflicts and approval | Open |
| Database writes/migrations | Separate explicit approval required | Gated |

## 11. Shared Production Date and Dynamic Shift Schedule

This section is the current requirements authority for the shared date context and configurable Shift Time workflow. A workspace-wide search found no existing OmagMES `requirement.md`; this existing factory-confirmed requirements handoff is updated rather than creating a competing requirements document.

### Shared Production Date context

- Distinguish **Calendar Date** (Bangkok-local date of an instant), **Production Date** (operational day selected by the effective cutoff), and **Shift** (schedule interval assigned independently by the Shift Schedule version).
- Use `Asia/Bangkok` for factory Production Date resolution. A Production Day is the half-open interval `[cutoff on Production Date, cutoff on following calendar date)`; midnight alone never changes Production Date.
- The main-header **Selected Production Date** is shared across Production, Depallet, and Setting. A valid URL date takes precedence; otherwise restore an explicitly saved date. Only when neither exists, request the server's current Production Date from persisted cutoff configuration. Do not substitute browser/system today and do not auto-roll an explicit historical selection at midnight.
- Keep Production Date separate from event timestamps, row `Rectime`/creation timestamps, and actual Lot start/end bounds. It is a report/work-date context, not a rewrite of event time. Pass selected Production Date and both applicable configuration version IDs to date-scoped context and draft workflows; stale IDs require review/conflict, not silent reassignment.

### Persisted Production Day Cutoff

- Store cutoff changes as immutable, effective-dated versions in OMAG SQL Server. Each version requires an effective Production Date, `HH:MM` Bangkok-local cutoff, change reason, creation metadata, and stable ID. A version must not mutate historical cutoff rows or silently reassign confirmed facts.
- Cutoff configuration and Shift Schedule are independent version streams. Changing one does not edit or recreate versions in the other.
- The required initial cutoff time is **07:00 Asia/Bangkok**. The project owner confirmed **2026-11-10** as the initial effective Production Date for both initial cutoff and schedule configuration. This approval does not mean SQL bootstrap has been applied or verified.
- A version effective on calendar date D changes the boundary at D's configured cutoff. This can yield a 23-hour or 25-hour adjacent operational interval when the time changes, but consecutive `[start,end)` windows must remain contiguous with no overlap or gap.
- The API must reject changes that would alter an already-started Production Day, invalid times/dates, missing reasons, and stale base-version IDs. Historical selected dates resolve to their own effective cutoff version; saving a future version never changes old configuration rows.
- A repeatable SQL schema/bootstrap script and deterministic tests are not deployment verification. SQL persistence across application restarts is **not verified** until the OMAG target is reachable, schema is inspected, an approved configuration identity and narrowly scoped internal authorization are configured, bootstrap commits, and restart survival is tested.

### Dynamic, version-controlled Shift Time

- Add `SETTING > SHIFT TIME`. Support any number of shift definitions; arbitrary text `ShiftName`, separate `ShiftCode`, and immutable internal `ShiftID`; start/end time, display order, active status, edit/deactivate, version history, effective Production Date, and preview resolved for the selected Production Date.
- Initial confirmed schedule: Shift Name `Shift 1`, Shift Code `1`, 08:00–19:00; Shift Name `Shift 2`, Shift Code `2`, 19:00–06:00 next day. The 06:00–08:00 period is **explicitly unassigned**. The illustrative future three-shift schedule is an example only and must not be activated or saved by default.
- Each change creates a new immutable schedule version effective from a Production Date. Effective ranges are derived from successive effective dates and cannot overlap. Version creation is forward-only relative to the selected date/latest version. Previous versions and their shift definitions remain readable; historical records keep the version/shift identity (and immutable facts/snapshots) used when confirmed. Never recalculate confirmed history from the newest schedule.
- Resolve cross-midnight shifts against the selected Production Date: Shift 2 on 2026-11-10 ends at 2026-11-11 06:00 and remains associated with Production Date 2026-11-10. Shift start/end times are independent of the Production Day Cutoff. Use Bangkok local wall-clock values and half-open `[start, end)` windows.
- Reject active interval overlaps, duplicate Shift Names or Shift Codes within a version, duplicate display order, invalid/equal start/end, malformed effective dates, and invalid shift IDs. Inactive definitions remain in version history and do not resolve as assignable shifts. Any gap is visibly unassigned; do not infer a Shift.
- A draft created under an older schedule version remains provisional and visibly requires review if a newer version is applicable to its Production Date. Operator review can correct shift, start/end and count with a reason; dismiss must preserve audit history. Neither action modifies source evidence or creates an official Lot.
- Auto Lot Detection, when separately authorized and safely integrated, must pass the selected Production Date and applicable schedule version and query bounded `DropCnt` history for the derived shift intervals. Do not query solely by `CAST(_TIMESTAMP AS date)`. The current mock feature must not connect to SQL/PLC/Kepware.
- Lot No. remains a distinct human/business identifier and immutable Production Lot ID remains authoritative. Do not silently substitute arbitrary Shift Name into the existing Lot format's Shift segment. Compatibility of `ShiftCode` with the current numbering rule remains an explicit design decision before official Lot numbering.

### Effective-date and database design gates

- The mock Shift Schedule `effective_from=2026-01-01` remains a placeholder, not a confirmed bootstrap date. The new review-only migration 002 adds candidate cutoff/shift identity/version tables, each ID-first with `Rectime`; it contains no seed rows. Initial 07:00 cutoff and complete initial shifts require a separate owner-approved bootstrap.
- Migration 002 and its validator/rollback are unexecuted drafts. Database writes remain gated; current API has no authenticated operator identity and the required dedicated SQL settings are not present. Do not describe SQL persistence or restart survival as complete until that gate is closed and tested.
- Auto Lot remains a user-supplied mock draft only. It displays the selected Production Date window and retains cutoff/schedule version IDs; no new live detector or official Lot workflow is part of this scope.
