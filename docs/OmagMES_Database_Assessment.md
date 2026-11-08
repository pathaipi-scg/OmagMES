# OmagMES Database Assessment — Consolidated Rules Revision

**Prepared:** 2026-11-08  
**Status:** Documentation and logical-design review only; plant-owner review is required before implementation.  
**Scope:** Independent OmagMES model. Unrelated legacy systems/tables, application code, credentials, and database objects are outside this revision.

## 1. Executive assessment

The earlier assessment and design predated confirmed rules for the single shared physical line, exact Product identity, Production Run and Lot boundaries, immutable internal Lot identity, editable non-unique LotName, and lifecycle traceability. The companion design is revised around those rules rather than treating workbook row, shift, date, or Lot text as authoritative identity.

Key assessment conclusions:

- There is **one physical ProductionLine** shared by Block and Fence product families. ProductFamily is not a line. Equipment and OEE/downtime attach to the actual physical line/equipment.
- Product identity is an immutable `Product.id`; Product Codes are exact, authoritative-master-controlled attributes/assignments. Similar codes or suffixes are not merged.
- Product identifies shape; Color is an independent coating variation. A Product change creates a new Run and Lot; a Color change creates a new Lot within the same Product Run. A pause, shift/day change, or Mould change alone does not create a Lot.
- Each physical Mould belongs to exactly one Product; multiple Moulds may reference one Product. No many-to-many Mould/Product capability table is permitted, and Color is not a Mould eligibility dimension.
- The database-generated `ProductionLot.id` is the only Lot identity. `LotName` is editable, duplicate values are allowed, and no unique constraint or relationship may use it. Rename history is required.
- Production, curing, depallet, and future dispatch records preserve the same Lot ID. Multiple curing/depal/dispatch records per Lot are supported where the process requires them.
- One shared accumulator processes approximately five-minute Kepware DataLogger observations and accumulates Press strokes across PLC resets. It uses idempotent ordered processing and explicit uncertainty for gaps/reset ambiguity; strokes remain separate from finished-product quantities and OEE.
- Historical workbook strings and conflicts are evidence for reconciliation, not database identities or permission to auto-correct. An exception-reviewed source mapping is recommended before any import.
- Newly confirmed: Product owns both positive integer Standard Pieces/Drop and positive decimal Standard Cycle Time in seconds per press Drop; a stroke is one Drop, not a Piece. Wet Press and Wet Line share one Wet Run Log/OEE, while Dry Line/Depallet is independent and excluded. Performance uses Product-specific cycle time and actual Drops; Quality uses IP Camera Wet good Pieces against expected Pieces; Availability comes from the Wet Run Log.

The focused [Product Production Standard Master design](OmagMES_Product_Production_Standard_Master_Design.md) proposes Product-owned effective-dated revisions, approval/change audit, and Run/Lot snapshots. The Excel review found `Std Data!BC` labeled Cycle Time / Second, but its historical per-Drop basis, authority, and effective dates are unverified. `Std Data!BA2` says `ก้อน/Drop`, while `BA3` says `pcs./pallet`; BA values cannot be certified as Pieces/Drop. A duplicate-aware scan also found same-month duplicate-code conflicts (BA: 12 codes/98 code-month cases; BC: 10 codes/69 code-month cases). These observations prevent selecting one standard per Product from a simplistic lookup. The legacy Excel Performance formula does not explicitly use Press Drops or IP Camera good Pieces and is not adopted as Wet OEE.

See the complete labeled rule set and ER summary in [OmagMES_Confirmed_Business_Rules.md](OmagMES_Confirmed_Business_Rules.md); see entity-level logical definitions in [OmagMES_Database_Design.md](OmagMES_Database_Design.md).
Product-standard revision, snapshot, source mapping, and Wet OEE decisions are detailed in [OmagMES_Product_Production_Standard_Master_Design.md](OmagMES_Product_Production_Standard_Master_Design.md).
The proposed SQL Server DDL for review only is in [OmagMES_Proposed_Database_DDL_Review.md](OmagMES_Proposed_Database_DDL_Review.md); it is not approved or executable.

## 2. Mandatory database standard

The exact applicable file was located and read: [skill/DATABASE_ID_FIRST_DESIGN_SKILL.md](../skill/DATABASE_ID_FIRST_DESIGN_SKILL.md) (absolute path at review: `D:\AI\OmagMES\skill\DATABASE_ID_FIRST_DESIGN_SKILL.md`). It specifies for every new table:

- `id bigint IDENTITY(1,1) NOT NULL PRIMARY KEY`
- `Rectime datetime NOT NULL DEFAULT (GETDATE())`, representing record creation time
- ID-based foreign keys to authoritative surrogate IDs; business codes, names and mutable labels are not relational identity
- Opaque numeric IDs, safe master resolution by unique business code, and no unapproved legacy redesign

Those rules are applied to the proposed logical tables. No SQL/DDL or schema objects are included or created here.

## 3. Evidence reviewed and evidence boundary

Reviewed the four requested project documents:

- [OmagMES_Initial_Discovery.md](OmagMES_Initial_Discovery.md)
- [OmagMES_Manufacturing_Process_Analysis_Jan_Oct_2026.md](OmagMES_Manufacturing_Process_Analysis_Jan_Oct_2026.md)
- [OmagMES_Database_Assessment.md](OmagMES_Database_Assessment.md) (previous version as context)
- [OmagMES_Database_Design.md](OmagMES_Database_Design.md) (previous version as context)

The manufacturing analysis provides a predicate-based scan of production rows across Jan–Oct 2026 and targeted cell/row references. It documents repeat Lot strings, same-Lot/multi-code conflicts, date inconsistency, selected production-to-curing references, and dry-output limitations. Examples include October `PLAN-ACTUAL` rows 5–6 for Lot `01161`, daily Lot `C300926201B` with inconsistent code/date evidence, and June production rows cross-referenced to curing rows. These observed records do not override the owner-confirmed rules and must not be automatically corrected or merged. The FittingMES mould reference and Press counter analysis were also reviewed; the former's earlier optional capability-mapping recommendation is superseded by the confirmed one-Product-per-Mould rule, while the latter's bounded `PRESS` sample cadence differs from the approximately five-minute DataLogger requirement and must not be assumed to be the same feed.

The discovery report and process analysis also state limits: many auxiliary formula caches/errors and external links, incomplete quantity/event reconciliation, no verified authoritative Product Master in the reviewed workbook set, and dry-output summaries not validated as independent Depallet transactions. No claim is made here that every historical workbook cell or every auxiliary event has been audited.

### Database and file safety

The prior 2026-11-02 assessment recorded a narrow, read-only SQL Server connection and `omagmes` schema-existence check. That historical point-in-time statement is retained for transparency only; this revision did not repeat the connection or use database contents to design the rules. No unrelated legacy tables were inspected for this revision. No `.env` content was read or disclosed. No SQL, DDL, DML, migration, seed, database object, workbook, or application file was changed.

The monthly folders `doc/Jan26` through `doc/Oct26` remain excluded by the existing [.gitignore](../.gitignore); no source workbook was edited.

## 4. Assessment of prior proposal and required design changes

| Prior design topic | Assessment against confirmed rules | Revision |
|---|---|---|
| `ProductLine` with Block/Fence labels | Conflated physical line and product grouping; conflicts with the confirmed one-line plant. | Replace with one actual `ProductionLine` entity and separate `ProductFamily` master; products reference family, runs/equipment reference the physical line. |
| Product Code stored directly as Product identity | Does not represent controlled code changes or protect against misleadingly similar codes. | Give Product its own immutable ID; store exact Product Code assignments separately with controlled effective dates and audit. Do not merge based on spelling. |
| Production report line with nullable `LotCode` | Treats a text Lot label as if it were the lifecycle identity and lacks Run boundaries. | Add immutable `ProductionLot` and `ProductionRun`; output/shift facts refer to Lot ID. LotName remains non-unique display text. |
| Shift/date report interpreted as production grain | Can accidentally split a continuous Run at shift/day boundaries. | Shift and work date are attributes of output/summary records only; they do not create Runs or Lots. |
| No LotName lifecycle/audit | Cannot safely rename a Lot or explain historical names. | Add `LotNameChangeHistory` with old/new name, actor ID, timestamp, reason; no LotName uniqueness. |
| Curing/Depallet omitted | Cannot represent confirmed same-Lot lifecycle or multiple operations. | Add `CuringEntry` and `DepalletEvent`, each FK to original Lot.id; future dispatch lines also FK to Lot.id. |
| Equipment and mould not independently modeled | Workbook identifiers are not authoritative, but equipment/mould must not be inferred from Product codes. | Model Equipment/ProductionLine association and Mould independently; capture explicit MouldUseEvent without making a mould change a Lot boundary. |
| Historical reconciliation absent | Repeated labels and conflicts could be silently collapsed. | Recommend staged source references, immutable internal IDs, exception review and auditable explicit mapping; no import in this task. |

## 5. Logical design disposition

The revised design retains the following candidate core: `Plant`, `ProductionLine`, `ProductFamily`, `Product`, `ProductCodeAssignment`, `ProductProductionStandard` (Product-owned effective revisions with both values), `Color`, `Shift`, `UnitOfMeasure`, `ProductionOutputType`, `EquipmentGroup`, `Equipment`, `Mould` (with exactly one `ProductID`), `ProductionRun`, `ProductionLot`, `ProductionOutput`, `MouldUseEvent`, `PressCounterObservation`, `PressCounterAccumulator`, `PressCounterStep`, `StoppageCategory`, `StoppageReason`, `StoppageEvent`, `CuringRoom`, `CuringEntry`, `DepalletEvent`, `LotNameChangeHistory`, and `AppUser`, with Wet OEE, quality and future dispatch entities as separately reviewed candidate modules. Run/Lot production contexts snapshot the selected standard revision and values; no later master edit can rewrite historical OEE inputs. There is no `ProductMouldCompatibility` table. The catalog defines relationships and controls but does not imply every module is approved for the first release.

The design intentionally does **not** make a separate RunShift summary table mandatory initially: output records can be grouped by `ProductionLotID`, ShiftID and WorkDate without using those dimensions as identity boundaries. If owners need submission/revision metadata or an explicit shift-summary parent, add it only with a defined grain and constraints, and ensure it resolves back to the same Run/Lot without duplicated inconsistent Product IDs.

`DepalletReject` is not included as a retained table because rejection transaction requirements are not yet established. It is an optional future child/detail if owners confirm reject quantity/reason/disposition and its relationship to each DepalletEvent. No reject quantities are inferred from the current workbook analysis.

## 6. Proposed relationship summary

- Plant 1 → many ProductionLines; current confirmed operating count is one physical line at OMAG, not one per family.
- ProductionLine 1 → many ProductionRuns and, where assigned, Equipment.
- ProductFamily 1 → many Products; Product 1 → controlled ProductCode assignments.
- Product 1:M ProductionRun; each Run is for one Product and may contain multiple sequential Lots. Product or Color changes create a Lot; Product changes also create a Run. Enforce Lot/Run Product equality.
- Product 1:M Mould; each Mould has one ProductID. Color is independent and is not included in Mould eligibility.
- One shared counter accumulator maintains cumulative confirmed strokes across raw counter decreases/resets. Idempotent source-pair processing, nonnegative deltas, baselines after resets, and explicit gap uncertainty are required.
- ProductionLot 1 → many ProductionOutput, CuringEntry, DepalletEvent, LotNameChangeHistory, and future DispatchLine records.
- ProductionRun 1 → many MouldUseEvents and may be referenced by StoppageEvents; mould change does not create another Run/Lot.
- ProductionLine 1 → many StoppageEvents; an event may reference Equipment and the interrupted Run where known.

All relational links are by ID. LotName and ProductCode are not foreign keys. Duplicate LotNames are safe because selection resolves to a unique Lot.id after the UI presents the Lot ID, exact Product Code/Name, and production context; changing the name updates no foreign key.

## 7. Unresolved decisions / review gate

These topics must be confirmed before a migration design is approved:

1. Authoritative Product Master and exact Product Code comparison/collation; code assignment effective dates and whether a validated code change preserves Product identity.
2. Production Run operational start/close events, interruption event vocabulary, and correction/reopen workflow.
3. Official shift schedule, overnight WorkDate attribution, and detailed production quantity grain/categories/units.
4. Curing entry grain, room master, timing and partial-transfer semantics; whether curing quantity is captured in OmagMES.
5. Depallet event time/quantity/unit/status/reversal requirements and whether DepalletReject is needed.
6. Equipment-line assignment, equipment moves, line/equipment OEE scope, downtime classifications, and approved OEE formulas.
7. Product standard authority and exact unit interpretation: resolve the conflicting `Std Data!BA2`/`BA3` headers, historical `BC` per-Drop basis, duplicate exact-code row conflicts, approval/effective dates, decimal scale, and standard revision/change workflow. Decide how a new standard applies during an open Run/Lot and approve the snapshot design.
8. Wet Run Log planned/operating-time definitions; time alignment of standard snapshots, actual Drops and camera Wet good Pieces; mixed-Product aggregation; missing/zero-denominator eligibility; counter-boundary uncertainty; and above-100% review policy. Do not silently clamp or impute.
9. Authoritative Mould register, one-to-Product assignment source, mould-use intervals and maintenance/drop-life rules. Do not model many-to-many capabilities or Mould-to-Color settings.
10. Approved DataLogger source identity, actual sampling cadence, timestamp timezone, quality policy, reset/restart semantics, maximum trusted gap, and owner workflow for unresolved strokes. Historical `PRESS` samples and expected five-minute logger observations must be reconciled before implementation.
11. Quality sampling, specifications, reject/disposition linkage, user identity provider, and audit retention.
12. Future Dispatch header/document grain, customer/order identifiers and partial/return/reversal behavior.
13. Historical source file/version identifiers, row locators, match policy, reviewer roles and unresolved conflict escalation.
14. First-release modules, retention, access control, operational backup and deployment controls.

Review and sign off [OmagMES_Confirmed_Business_Rules.md](OmagMES_Confirmed_Business_Rules.md) and [OmagMES_Database_Design.md](OmagMES_Database_Design.md) with production, quality, maintenance, data-master and dispatch owners before preparing executable DDL.

## 8. Implementation boundary

This is documentation and logical design only. **No SQL was executed and no database objects were changed.** The historical namespace check must not be treated as current implementation readiness. Before any separately approved implementation, inspect only the explicitly authorized OmagMES namespace and authoritative masters, repeat collision/permission checks, and follow the ID-first skill, migration review, rollback, and testing requirements. Do not inspect unrelated legacy tables without separate explicit scope.
