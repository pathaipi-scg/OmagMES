# OmagMES — Factory Requirements and Implementation Handoff

**Status:** Requirements collected through 2026-11-10. This document is a requirements handoff, **not** authorization to change the production database, import master data, or deploy.

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
- Factory-confirmed Kepware mapping: `OMAG.PRESS.ProductCnt` and `OMAG.PRESS.OEE.DropCnt` both address `DB3.DBW2`, type Word, scan 100 ms, and are aliases for the same physical Press Drop counter. Historically, ProductCnt was logged to SQL once per hour; the factory recently switched to logging DropCnt whenever its value changes. The longer ProductCnt history and shorter DropCnt history are expected after this configuration change. Use DropCnt as the authoritative source for **new Auto Lot Detection**; ProductCnt is historical reference data only. **Never merge, union, or sum the histories.** Use SQL `_TIMESTAMP` to locate detected counter transitions, subject to verifying timestamp/timezone semantics. On-change logging produces no row while the value is unchanged, so absence of rows does not show the press stopped. An authorized SELECT-only validation found the persisted DropCnt key is `_NAME='OMAG.PRESS.OEE.DropCnt'`, while ProductCnt persists as `OPC.OMAG.OMAG.PRESS.ProductCnt`. The observed DropCnt sample contained 332 rows over about four hours, all quality 192, with values 101–414 and no observed decrease. The previously confirmed 07:00 reset semantics for ProductCnt refer to this same physical counter, but must be verified in DropCnt's own history before deriving totals.
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

### Confirmed format

`C` + `DD` + `MM` + `YY` + `Shift` + `Sequence2` + `B`

Example: `C021126201B` means factory C, production date 02 Nov 2026, shift 2, second-digit sequence 01, Block factory B.

- Factory prefix is always **C** for this factory.
- Factory suffix is always **B** (Block). Fence uses F elsewhere, but this factory is Block.
- Shift 1: **08:00–19:00**.
- Shift 2: **19:00–06:00 the next calendar day**; use the **production date on which Shift 2 began** in its Lot number, including after midnight.
- Sequence starts at **01 per production date and shift** and increases when a new Lot is created. Avoid duplicate Lot numbers and sequence reuse after void/cancellation.
- **Create a new Lot when Product changes OR coating Color changes**, including returning to a previously produced Product/Color combination.
- **Do not create a new Lot merely because the physical Mould is changed**, including Mould breakdown/replacement, as long as Product and Color remain the same.
- Keep immutable internal `ProductionLot.id`; human-readable Lot No. is separate. Preserve end-to-end Lot identity for Production -> Curing -> Depallet -> Dispatch.
- A shift boundary alone should not be assumed to create a new Lot without resolving the interaction between shift numbering and the previously confirmed Lot continuity rule.

### Open questions / validation gates

- Define how 06:00–08:00 is treated (outside the stated two shifts).
- Resolve whether a Product/Color run continuing across the 19:00 shift boundary retains its Lot or starts a shift-specific new Lot. The stated numbering is shift-based but the earlier Lot-boundary rule says shift alone is not a Lot trigger. **Do not guess.**
- Define how more than 99 new Lots in one shift are handled.
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
- Counter resets at 07:00 are data-source resets, **not** Mould age resets.
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
5. Produce an implementation plan and list unresolved factory decisions before any destructive, migration, or production-writing step.
6. Keep read-only SQL discovery separated from approved master-data writes; do not assume `.env` SQL host or production access is verified merely because the UI runs on port 3001.
7. Implement only the scope the user subsequently authorizes. Add tests for exact Product Code matching, idempotent GET UPDATE PRODUCT, pending standards, Mould lifecycle, Mould Drop age, Lot numbering, shift/date boundaries and audit.
8. Update the progress handoff after each meaningful milestone, including what was actually verified and what remains pending.
9. Do not commit/push, import workbook rows, run migrations, or modify production SQL without the user's explicit approval.

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
| Shift boundary vs same Lot | Conflict to resolve, no assumption | Open |
| DropCnt SQL history | Persisted `_NAME`, `_TIMESTAMP` meaning/timezone, quality, change-based transition history and query performance | `_NAME`, columns, and short sample verified; timestamp semantics/reset unresolved; least-privilege login required; shorter history expected after recent switch |
| First master import | Excel mapping, conflicts and approval | Open |
| Database writes/migrations | Separate explicit approval required | Gated |
