# OmagMES Phase 1 Operator Prototype — Discovery and Implementation Plan

**Prepared:** 2026-11-08  
**Status:** Discovery complete; implementation plan for owner approval. No application code, schema, database records, migrations, or source workbooks were changed in this task.  
**Approval gate:** Do not begin implementation until the owner approves this plan and resolves the explicitly listed decisions.

## Executive summary

The OmagMES repository currently contains documentation, a database-design skill, environment/virtual-environment files, and historical source data, but no application source, README, dependency manifest, routes, models, SQL migrations, or tests. The configured OMAG database is reachable with `ApplicationIntent=ReadOnly`; its `omagmes` schema does not exist. Catalog inspection found candidate legacy tables `dbo.LOG_LOT` and `dbo.product_count` but no Product, Color, Mould, or OmagMES Logger master. Those legacy tables were not read or modified.

The Product Master CSV contains 855 unique exact Product Codes: 118 marked observed in production and 737 not observed. Reconciliation against the ten daily production reports found 116 distinct exact raw codes; 94 exactly match the CSV, while all 116 have a case-insensitive counterpart. This is an exception list, not permission to normalize codes. The reports also contain repeated Lot labels and same-label/multi-code conflicts. The CSV has no structured Color field; color words in descriptions and code suffixes must not be used to infer Color identity.

The bounded `AutoRun` history has 12,739 rows, all with `_QUALITY=192` and values 0/1, representing 64 observed 1→0 transitions and 64 0→1 transitions. It includes many repeated state samples and long gaps; a stopped-to-running interval in the sample spans 62 hours 24 minutes with missing observations in between. The source supports transition detection but does not support treating every elapsed interval as confirmed downtime. Keep raw source evidence immutable, distinguish uncertain gaps, and store operator classifications separately.

**Architecture superseded:** this earlier plan recommended FastAPI/Jinja. The current implementation direction is React + TypeScript + Vite frontend → FastAPI REST API → SQL Server `OMAG`, using only the new `omagmes` schema. The Jinja recommendation below is retained as historical context, not current guidance. Reuse FittingMES workflow patterns, not its schema or machine-specific assumptions.

Newly confirmed owner requirements make Product the owner of both positive integer `StandardPiecesPerDrop` and positive decimal `StandardCycleTimeSec` (seconds per press Drop), not the Mould. One stroke is one Drop, not a finished piece. Wet Press and Wet Line form one coupled Wet Run Log/OEE; Dry Line/Depallet is independent and its stops are excluded. Performance uses Product-specific cycle time and actual Press Drops; Quality uses IP Camera Wet good Pieces against expected Pieces; Availability comes from the Wet Run Log. The read-only Excel evidence and the focused [Product Production Standard Master design](OmagMES_Product_Production_Standard_Master_Design.md) document source conflicts, effective-dated revisions, production snapshots, and owner decisions. The historical formula is not the Wet OEE baseline.

## 1. Scope, evidence labels, and safety

This report separates **verified** repository/database/workbook observations, **confirmed** business rules already recorded by the owner, **proposed** implementation choices, and **unresolved** decisions. Historical spreadsheet values are not automatically authoritative.

- The complete database skill was read at the verified absolute path `D:\AI\OmagMES\skill\DATABASE_ID_FIRST_DESIGN_SKILL.md`.
- Excel files were opened read-only using saved values. No workbook was saved, recalculated, macro-executed, or refreshed from external links.
- SQL inspection used the existing OmagMES environment settings without printing them and requested `ApplicationIntent=ReadOnly`. Queries were SELECTs against `OMAG.dbo.PRESS` and system catalogs; no write was attempted. Read-only intent does not prove that the configured login is technically denied writes.
- The FittingMES reference was inspected as source only. No FittingMES code, database, or configuration was changed.
- No commit or push was made. Existing OmagMES changes are preserved; see Section 2.

## 2. Repository and database status

### OmagMES repository

Verified root: `D:\AI\OmagMES`. The visible repository contains `.env`, `.gitignore`, `.venv`, `doc/`, `docs/`, and `skill/`. The source/config search found no README, requirements file, application package, route/model/service modules, SQL migrations, or tests. The current project environment is Python 3.14.6 with `openpyxl` and `pyodbc`; the Pylance environment service reports an unrelated shared interpreter path, so the project-local `.venv` was used explicitly for read-only inspection. No application architecture exists in OmagMES to preserve or modify yet.

Git status at the end of discovery remains `main...origin/main` with these pre-existing changes:

- Modified: `docs/OmagMES_Confirmed_Business_Rules.md`
- Modified: `docs/OmagMES_Database_Assessment.md`
- Modified: `docs/OmagMES_Database_Design.md`
- Modified: `docs/OmagMES_FittingMES_Mould_Reference_Analysis.md`
- Modified: `docs/OmagMES_Press_Counter_Analysis.md`
- Untracked: `docs/OmagMES_Proposed_Database_DDL_Review.md`
- Untracked: `doc/` (historical-data directory; monthly Excel files are subject to existing ignore rules, and the CSV is visible as untracked)

FittingMES is clean on `main...origin/main`. Preserve all of the above; do not stage or revert it. **During this discovery task, the only file created is this report.**

### Database and candidate existing entities

The configured connection selected database `OMAG` on `SCGLS-NK\SQLEXPRESS`. A read-only catalog query found no `omagmes` schema. The candidate-name filter found only `dbo.LOG_LOT` and `dbo.product_count` among likely Product/Lot/Equipment/Logger names, in addition to the already inspected `dbo.PRESS` source. Catalog metadata shows:

- `dbo.LOG_LOT`: `id`, `mdt`, `DateStr`, `autoLot`, `startLot`, `stopLot`, `LotProdID`, `PlanID`, `DropCnt`, `speed`.
- `dbo.product_count`: `id`, `TimeStamp`, `value_cnt`, `line`, `remark`.
- `dbo.PRESS`: legacy PLC/history source, detailed in Section 6 and the prior [Press Counter Analysis](OmagMES_Press_Counter_Analysis.md).

These names/columns are **not proof** that the first two tables are approved OmagMES masters or that their values are suitable for Product/Lot identity. Their rows, constraints, and ownership were not inspected. No Product, Color, Mould, reason, or equipment master was identified in the candidate catalog search. Before any DDL, inspect only the approved target namespace and candidate legacy dependencies, verify ownership/permissions, and resolve whether any existing entity is authoritative.

## 3. Database skill requirements

The exact applicable skill is [DATABASE_ID_FIRST_DESIGN_SKILL.md](../skill/DATABASE_ID_FIRST_DESIGN_SKILL.md). Its mandatory table conventions apply to every eventual master, event, history, sequence, and staging table:

- `id bigint IDENTITY(1,1) NOT NULL PRIMARY KEY`
- `Rectime datetime NOT NULL DEFAULT (GETDATE())` for row creation time
- Foreign keys to authoritative surrogate IDs; no names, labels, or mutable business codes as relationship identity
- Opaque IDs; separately unique business codes where approved
- Safe seed resolution by a unique authoritative business key; fail if resolution is missing or ambiguous
- Never revise an applied migration; use reviewed new migrations and rollback plans
- Validate actual server state and permissions before deployment; test FKs, uniqueness, concurrency, migration rollback, and legacy compatibility

This report contains no executable DDL. The earlier proposed DDL remains a review copy and must not be run.

## 4. FittingMES reference: reuse and do not copy

FittingMES is a Python/FastAPI, Jinja-template, SQL Server/`pyodbc` application. Its routes and compact operator templates are useful workflow references. Relevant inspected sources include [lots.py](../../FittingMES/app/lots.py), [products.py](../../FittingMES/app/products.py), [logger.py](../../FittingMES/app/logger.py), [logger_page.py](../../FittingMES/app/logger_page.py), [logger_master.py](../../FittingMES/app/logger_master.py), [database.py](../../FittingMES/app/database.py), [main.py](../../FittingMES/app/main.py), [logger.html](../../FittingMES/app/templates/logger.html), [production.html](../../FittingMES/app/templates/production.html), [017_logger_event.sql](../../FittingMES/sql/017_logger_event.sql), [test_logger.py](../../FittingMES/tests/test_logger.py), and [test_logger_page.py](../../FittingMES/tests/test_logger_page.py).

Useful patterns:

- Server-side validation against current master data; transactional insert/update; database-generated IDs; operator-facing error feedback.
- Lot creation previews, protected concurrent writes, Lot history, searchable Product selection, and compact responsive forms.
- LOGGER fields and hierarchy/classification UI: duration, machine/instance, cause, stop type/subtype, M/E/O, stop/start, note, saved-event list, and master-review page.
- LOGGER detects invalid hierarchy, validates stop/start and shift context, snapshots display labels, and prevents overlapping time events.

Do **not** copy these FittingMES decisions as OmagMES rules:

- FittingMES uses Product-family-specific prefixes and `MAX(RunningNo)+1`; its deletion/voiding can make an active number available again. That fails OmagMES's shared monthly sequence and no-reuse requirement.
- Its machine model includes many presses, instances, related machines, submachines, and Fitting-specific causes. OmagMES starts with one `PRESS` and one `LINE`; equipment/reason lists must come from approved OmagMES references.
- FittingMES `LoggerEvent` uses `LoggerEventID`, lacks the OmagMES-required `id`/`Rectime`, and requires both stop and start timestamps. It cannot represent an open PLC stop interval. Treat it as a UI/validation reference, not a compatible schema.
- FittingMES shift rules, Thai-year prefix, M/E/O shortcuts, type thresholds, and its specific master values are not automatically valid for OmagMES.
- FittingMES `StandardSpeed` is Press–Product capability data in `pcs/min`, is mutable without speed effective history, and is joined into historic OEE. OmagMES standards belong to Product independent of Mould and must be effective-revision controlled and snapshotted for production; a later edit must not change historical OEE.

## 5. Product, Color, Mould, and historical Lot evidence

### Product standards and Wet OEE discovery update

The owner-confirmed requirements are detailed in [OmagMES_Confirmed_Business_Rules.md](OmagMES_Confirmed_Business_Rules.md). The owner has confirmed `Std Data!BA` means Pieces/Drop and `Std Data!BC` means seconds/Drop; the historical BA header stack (`BA2` `ก้อน/Drop`, `BA3` `pcs./pallet`) still needs explanation. A full Jan–Oct duplicate-aware inspection found 25 exact Product Codes with numeric conflicts (13 BA, 17 BC); 22 exactly match the CSV and 3 do not. One-row-per-code extraction can conceal conflicting duplicate rows. These values remain unapproved and must not be selected or bulk-seeded. See the [complete conflict review](OmagMES_Product_Standard_Conflict_Review.md), [Product standards Excel analysis](OmagMES_Product_Standards_and_Wet_OEE_Excel_Analysis.md), and [focused standard master design](OmagMES_Product_Production_Standard_Master_Design.md). Derived Drops/minute, Drops/hour, and Pieces/hour can be calculated from the two confirmed standards; they are not independent master values without approval.

All ten `OEE Report.xlsx` copies inspected use an `OEE_Monitor` chain where Performance is `(Standard Cycle Time / Actual Cycle Time) × (Actual Cycle Time / Operating Time)`. Block and Fence cycle-time totals are summed. The source formula does not explicitly use actual Press Drops or IP Camera good Pieces and is not the confirmed Wet OEE definition. No formulas were refreshed and no source workbook was changed.

### Product Master and exact reconciliation

The CSV [Omag_Product_Master_Jan_Oct_2026.csv](../doc/Omag_Product_Master_Jan_Oct_2026.csv) has columns `ProductCode`, `EnglishName`, `ThaiName`, `ObservedInProduction`, `MonthsObserved`, `ProductionRows`, and `SampleLots`:

| CSV classification | Count | Interpretation |
|---|---:|---|
| Total rows / distinct exact Product Codes | 855 / 855 | No duplicate ProductCode values in this file. |
| `ObservedInProduction=YES` / `NO` | 118 / 737 | Useful initial prioritization signal, not independent proof of master authority. |
| Sum of `ProductionRows` column | 829 | CSV metric; not a certified count of physical production events. |

A read-only saved-value scan of the ten monthly `Production Report (Block)` workbooks used the existing daily-row predicate (Product Code column B + Lot column M, rows 58–100) and `PLAN-ACTUAL` values (Lot column D + Product Code column E):

| Source set | Distinct exact codes | Exact CSV match | Unmatched exact strings |
|---|---:|---:|---:|
| Daily production rows | 116 | 94 | 22 |
| `PLAN-ACTUAL` rows | 130 | 110 | 20 |

All 116 daily raw codes had a case-insensitive CSV counterpart, but exact code comparison is required by the existing confirmed rules. Do not case-fold or rewrite the 22 exact mismatches. Among daily codes, 93 intersect the CSV's `YES` set; 25 CSV `YES` codes were not found by this particular daily-row scan, and 23 daily raw codes were not marked `YES`. These mismatches need owner/data-master review, not automatic activation or merging. The `PLAN-ACTUAL` unmatched strings include case variations, code suffix variations and at least one test/description-like value.

**Dropdown proposal:** retain all 855 rows for searchable master maintenance. Initially prioritize the 118 `YES` candidates (for example, in a “Historically used” group ordered by months/rows) and keep other records searchable but inactive until an authorized activation. Also expose exact historical values that failed matching in an exception/review view; never silently normalize them into an active master code. The CSV must be confirmed as the approved Product Master source before importing/seeding it.

### Product vs Color vs Mould

The CSV has English and Thai names but no structured Color column. Names may mention colors, and code variants may look color-related; neither is an authoritative Color assignment. Preserve the owner-confirmed rule: Product identifies shape; Color is independent. A Product or Color change creates a Lot; Product change also starts a new Run, while Color change can create a Lot within the current Product Run. Each physical Mould belongs to exactly one Product; multiple Moulds may belong to a Product. Color is not a Mould attribute or eligibility condition.

The ten production reports contain a `No.Mould` sheet with mould/product descriptions, mould numbers, usage/drop fields and other production attributes. The separate monthly Mould-drop workbooks record period/day ACT values; sampled codes include `NKFL...`. These are useful source references but do not establish an approved Mould master or a timestamped, Lot-linked Mould-use event. Register/assign moulds only from an owner-approved list; do not infer Product/Mould mapping from text or code patterns.

### Lot strings and historical conflicts

The daily report scan found 495 distinct raw Lot strings over the ten folders; 265 strings appeared in multiple scanned daily rows and 49 Lot strings were associated with more than one exact Product Code. Examples include daily values such as `C300326101B` and short numeric `PLAN-ACTUAL` values such as `01161`. The [Manufacturing Process Analysis](OmagMES_Manufacturing_Process_Analysis_Jan_Oct_2026.md) documents additional date mismatches and same-Lot/multi-code examples.

Historical values do not verify the requested `FactoryCode-YY-MM-RunningNumber` format: examples include multiple raw patterns, generally without hyphen separators, and no approved FactoryCode, date-year convention, or running-number width was established. Do not infer that the leading `C` is a factory code. The planned Lot format is therefore a requirement template pending owner confirmation, not a verified historical format.

## 6. PLC `AutoRun` investigation and LOGGER detection

### Read-only sample results

A bounded SELECT from `OMAG.dbo.PRESS` used the exact tag `OPC.OMAG.OMAG.PRESS.AutoRun` and clustered ID range `250000..301860`; rows were ordered by `_TIMESTAMP, id` for event analysis and also checked in ID order:

- 12,739 rows, spanning stored timestamps 2026-10-06 11:37 through 2026-11-02 22:33.
- All 12,739 had `_QUALITY=192`; values were exactly `1` for 12,667 rows and `0` for 72. This does not establish the OPC server's documented quality semantics.
- 12,610 adjacent rows repeated the preceding state; 128 state transitions: 64 `1→0` and 64 `0→1`.
- No duplicate timestamps or timestamp decreases in the sampled ID order. Median adjacent interval was 28.01 seconds; maximum gap was 224,664.85 seconds (about 62.4 hours); 257 gaps exceeded five minutes and 66 exceeded one hour.
- Sample starts and ends with state `1`; there was no open stop at the end of this bounded range. This does not prove that no open stop exists outside the range.
- One detected stop interval crosses a calendar date. One stop span is 2026-10-31 08:09:27 to 2026-11-02 22:33:51, about 62.4 hours, with no intermediate observation. The elapsed span cannot be treated as confirmed continuous downtime.
- State transitions occurred at varied clock times, including around midnight and near 06:00/07:00/19:00/20:00. No authoritative OmagMES shift schedule or timestamp timezone was established; do not infer shift IDs or a 07:00 reset from the samples.

These results characterize only the selected legacy tag/ID range, not all historian history or the approximately five-minute Kepware DataLogger counter feed. That Press counter is a separate tag and source question; do not combine the two ingestion paths without confirmation.

### Required detector behavior

1. Read source rows only. Preserve source `id`, exact tag, raw value, timestamp and quality as immutable source evidence in OmagMES-owned storage if approved; do not write to `dbo.PRESS`.
2. Process valid samples by event timestamp then stable source row ID. Record duplicate, late/out-of-order, invalid, bad-quality, or non-binary input for review; do not manufacture a state transition.
3. A supported `1→0` transition opens a stop interval at the observed transition timestamp. A supported `0→1` closes the interval at its observed timestamp. Repeated state rows are not new events. A last observed `0` remains open; never create a synthetic start.
4. A long observation gap creates a data-completeness warning. If a stop interval brackets a gap, retain its observed transition endpoints but mark its duration/continuous-downtime interpretation uncertain. Do not classify missing telemetry as confirmed downtime or interpolate the stop duration. The gap threshold must be owner-approved against the actual collection policy.
5. Keep raw PLC state and detected interval evidence immutable. Store operator classification in a separate record/history referencing the interval ID. Reason/category, M/E/O or other attributes, note, actor, edit time and correction reason are classifications, not PLC facts. A user correction must not rewrite source rows or erase the original detection.
6. A manually entered event is explicitly `MANUAL`, separate from PLC-derived intervals. If data are incomplete, operator action may review/annotate the uncertainty but must not be represented as a sourced PLC start or stop.

### Equipment and reason references

Monthly workbooks include `Loss Time Report`, `Minor Stoppage Losses`, and Mould-drop references. The October `Loss Time Report` `MC Code` sheet includes machine codes/descriptions and plant label `NEWA1`; its `Data` sheet includes reason codes such as cleaning, color change, setup and mould-change sizes, with standard minutes. Minor-stoppage forms aggregate shift/day categories and durations in seconds. These are reporting references, not verified authoritative live master data or an event-by-event AutoRun classification taxonomy. Review/approve Omag-specific `PRESS`, `LINE`, equipment/subsystem, stop-category and reason entries before seeding. Do not import FittingMES F1–F14 or its machine hierarchy.

## 7. Proposed data model and monthly Lot allocation

This is conceptual planning, not approved DDL. Keep the Phase 1 scope narrow:

- **Product / ProductCode:** immutable Product identity; exact code assignment and bilingual display names; active flag and history. Load all 855 only after CSV authority is approved. Store ProductFamily separately where approved.
- **Color:** independent master/variation and Lot FK; do not derive it from code suffixes or names. Determine whether colorless products permit NULL or use an explicit “no color” row.
- **ProductionLine / Equipment:** one actual OMAG physical line and one Press context; do not create Block/Fence lines. Add only approved equipment/reason identities.
- **Mould:** required single Product FK, one Product per physical Mould; no Mould/Product junction and no Color mapping.
- **ProductionRun / ProductionLot:** internal immutable IDs. Product change creates a new Run and Lot; Color change creates a new Lot within the same Product Run; pause, shift change, date change or mould change alone does not force a new Run/Lot.
- **LotNumber allocation:** keep generated, immutable `LotNumber` distinct from editable/non-unique `LotName` required by prior confirmed rules. If the owner means the generated number itself to be `LotName`, resolve that rule conflict before implementation; do not make a mutable display name the sequence key.
- **PLC source observation / detected stop interval / stop classification:** immutable observation reference and transition evidence; interval may remain open or uncertain; operator classification is separate and auditable.

### Sequence allocation proposal

After approval of the actual FactoryCode, exact separators, YY interpretation (Gregorian vs other), and running-number width, render the requested `FactoryCode-YY-MM-RunningNumber`. The production date selected by the operator determines the year-month sequence scope. The running number is shared across all Products and Colors in that FactoryCode/month.

Use a small transactional high-water allocator, not `MAX()` over active Lots:

- One sequence row per approved FactoryCode/year-month; atomically reserve the next number while creating the Lot.
- Persist an allocation/tombstone with a unique `(FactoryCode, YearMonth, RunningNumber)` key. Creation is transactional; cancellation/deletion marks the Lot/allocation cancelled and never decrements or frees the number.
- Prefer soft-cancel/no hard delete for a numbered Lot. If a Lot row is removed under an approved retention policy, the allocation record must survive independently so the number is still not reusable.
- Enforce uniqueness in the database and allocate in a transaction/lock. One known Lot-creating workstation means a simple SQL Server row lock or transaction-owned application lock is sufficient initially; no distributed counter service is justified. The database unique constraint remains the final safety net.
- Check exhaustion/width overflow before reserving; do not silently widen or wrap the number.

## 8. UI and operator workflow proposal

### Product and Lot

- Provide a searchable Product picker using exact Product Code and English/Thai names. Put historically used candidates at the top; retain all other Product Master rows for later activation/search. Display active status and unresolved code-match warnings.
- Show a separate Color picker based on approved Color master. Never infer Color from a Product name or suffix.
- Show selected production date, Product, Color, current Run status, generated-number preview, and a deliberate “Create Lot” confirmation. Derive YearMonth from the selected date, reserve the number on server submission, and return the immutable Lot ID/number.
- Show an explicit consumed-number message on cancellation. Search/selection and API submissions use internal Lot ID, not LotName alone.
- Keep Mould selection separate; only show Moulds explicitly assigned to the selected Product and approved status. Color does not filter eligibility.

### LOGGER

- Provide a review queue/table of detected Press stop intervals ordered by event time, with raw stop/start observation times, duration preview, source-row references, completeness status, and a prominent `OPEN`/`GAP — REVIEW` indicator.
- For a stopped Press with no later start sample, show an open interval and leave Start/Duration blank or clearly unknown. Never prefill a synthetic end.
- Keep the affected asset as the actual Press. If the operator must classify a line/equipment subsystem, offer only approved `PRESS`/`LINE`/equipment choices; remove FittingMES instance/hierarchy selectors unless Omag owners explicitly need them.
- Provide approved stop category/reason (and optional subtype/cause, M/E/O if confirmed), note, actor and auditable save/edit controls. Keep the machine transition times read-only by default; corrections require an authorized, explicit correction workflow and must preserve original evidence.
- Provide a separate manual-event form for events not represented by PLC data, visibly labeled manual. A detected PLC interval and its reason classification are separate facts.

## 9. Database and application impact

There is no OmagMES application source to extend at the time of this plan. The earlier recommendation to use FastAPI/Jinja is superseded by the React/Vite + FastAPI REST architecture stated above. Keep the prototype isolated from production SQL; do not reuse the FittingMES `.env` or expose credentials. Any future database connection must be explicitly configured for the owner-specified target and verified read-only before source inspection.

The first approved database migration set would likely need Product/ProductCode, Color, Line/Equipment/Mould, Run/Lot, sequence allocation, PLC observation/detected interval, and classification/audit entities, plus indexes and constraints for exact code validation, source-row idempotency, Lot-ID relationships, and monthly number uniqueness. Every new table must include skill-required `id` and `Rectime`. Any legacy source key (such as `PRESS.id`) is an external source identifier, not a replacement for the new table's PK. Existing `dbo.LOG_LOT` and `dbo.product_count` are not to be altered or adopted without a separate ownership/dependency review.

No existing migration was found in the OmagMES project. Any schema work must be a reviewed new migration plus rollback, validated against live SQL Server permissions, and tested in a non-production target first. The prior proposed DDL document is not a deployment artifact.

## 10. Implementation order after approval

1. **Owner decisions:** confirm Product Master authority and exact code comparison policy; resolve the numeric conflicts in [OmagMES_Product_Standard_Conflict_Review.md](OmagMES_Product_Standard_Conflict_Review.md), explain the historical `BA2`/`BA3` label mismatch, establish approved sources/effective dates, decimal scale, and standard-change approval; define Run/Lot snapshots and mid-Run/Lot change behavior. BA Pieces/Drop and BC seconds/Drop meanings are confirmed. Also confirm Color master semantics, FactoryCode/number format, yearly calendar, width/overflow policy, shift schedule/timezone, gap threshold, and LOGGER reason taxonomy.
2. **Project foundation:** create minimal app/config/templates/tests; secure environment loading, read-only source access and separate write target are explicitly tested.
3. **Database review and migration:** inventory only authorized target schema/masters; draft ID-first tables, unique constraints, indexes, seed resolution, rollback; obtain migration review before running.
4. **Master setup:** preserve all 855 Product rows as candidates; activate/prioritize only owner-approved Products; send code mismatches and unsupported standard values to review; seed only approved Product standards, Color, equipment and reasons. Never infer BA or missing standard values.
5. **Product/Run/Lot workflow:** exact Product selection, independent Color, approved transition rules, monthly shared no-reuse allocation, cancellation and authorization. Resolve one effective Product standard at the approved boundary and freeze revision/values on Run/Lot; master edits cannot change historic calculations.
6. **PLC detection:** bounded, ordered, idempotent ingestion from the approved source; open/close transition processing; gap and quality status; no source writes.
7. **Operator LOGGER classification:** classify eligible detected intervals; keep event evidence immutable; support explicit manual events and audited corrections.
8. **Operational validation:** concurrency, restart/replay, gap/transition cases, UI usability, permissions and acceptance checks; then owner sign-off before production deployment.

## 11. Risks and unresolved owner decisions

1. Is the CSV the authoritative Product Master, and may the `YES` field drive initial operator activation? Resolve the 22 exact daily-code mismatches, the 20 `PLAN-ACTUAL` unmatched values, and observed-status inconsistencies without editing historical files.
2. Resolve the 25 numeric BA/BC conflicts using [OmagMES_Product_Standard_Conflict_Review.md](OmagMES_Product_Standard_Conflict_Review.md); explain the historical `Std Data!BA2` (`ก้อน/Drop`) versus `BA3` (`pcs./pallet`) label mismatch; identify authoritative numeric sources, approval, and effective dates. BA Pieces/Drop and BC seconds/Drop are confirmed meanings. Review duplicate exact-code rows and do not select or seed a value silently.
3. Approve both positive Product standards, decimal precision, effective-period/approval policy, no-overlap behavior, correction/backdating rules, missing-standard status, and whether a standard revision during an open Run/Lot creates an application segment or waits for another approved boundary.
4. Does the new unique monthly `LotNumber` supersede, supplement, or differ from editable/non-unique `LotName`? Confirm FactoryCode, separators, Gregorian/other YY meaning, zero-padding width, maximum number, and whether reserved/cancelled values remain visible.
5. Confirm exact Lot creation trigger and user authorization; confirm how Product/Color change transitions relate to production Run and whether selecting a past production date is allowed.
6. Confirm authoritative Color/Product/one-Product-per-Mould masters and Mould reassignment/recondition rules.
7. Confirm whether the bounded `PRESS.AutoRun` table is the authoritative live logger feed, its retention/reload policy, timestamp timezone/source semantics, quality-code contract, expected cadence/deadband, and treatment of gaps/late rows.
8. Define maximum trusted observation gap and gap-close semantics. The 62.4-hour interval is not safe to treat as proven continuous downtime; current sample has no terminal open stop, but that is range-limited.
9. Approve shift boundaries and production-date attribution. The database timestamp is timezone-naive; no schedule or timezone was confirmed.
10. Approve Omag-specific equipment/reason hierarchy, whether `LINE` and `PRESS` are selectable separately, and optional M/E/O/subtype/cause fields. Historical workbook codes are not automatically authoritative.
11. Confirm user identity, permissions, audit retention, correction workflow, cancellation policy and database deployment rights. `ApplicationIntent=ReadOnly` on the investigation connection is not a write-permission test.
12. Verify the candidate legacy `LOG_LOT` and `product_count` ownership, FKs, data use, and retention only if future design must integrate them; no rows were examined in this discovery.

## 12. Test plan and Phase 1 acceptance criteria

### Minimum tests

- Product master exact matching, bilingual search, active/history prioritization, inactive search, and no automatic case/suffix normalization.
- Product/Color transition behavior; one Product per Lot; one Product per Mould; Color does not affect Mould eligibility.
- Product standards: positive integer Pieces/Drop; positive decimal seconds/Drop; missing/overlapping effective revisions; approval/audit; no implicit value from history; Run/Lot snapshot immutability after standard edits; unresolved mid-Run/Lot changes are explicit.
- Wet OEE: exact time-window/source alignment; mixed-Product standard aggregation; missing/zero-denominator statuses; counter reset/gap/boundary uncertainty; >100% retained and flagged, never silently clamped.
- Lot allocator: selected date chooses period; sequence shared across Products/Colors; month/year boundary; unique number under concurrent submissions; cancellation/deletion does not reuse; duplicate request/retry is idempotent; width exhaustion fails clearly.
- PLC: 1→0 opens, 0→1 closes, repeated values do not duplicate events, stable source ID prevents replay duplicates, out-of-order/timestamp ties are deterministic, invalid/bad quality is not silently accepted, open final stop stays open, and gaps mark uncertainty without inventing confirmed downtime.
- Midnight/shift-boundary crossings, unknown timezone, a 62-hour gap, and terminal state 0/1 edge cases.
- Operator classification can be added/edited without changing immutable PLC observations; manual events remain labeled manual; corrections preserve prior actor/reason/evidence.
- Database migration/rollback, ID/Rectime conventions, FK/unique constraints, safe seed resolution, transaction rollback, and server-side authorization.

### Phase 1 acceptance criteria

- A responsive operator UI runs in the new OmagMES app and supports searchable exact Product selection, Color selection where approved, and Lot creation for one physical line.
- All 855 CSV candidates are retained/searchable; approved historically used Products are prioritized; unresolved exact-code differences are visible and never silently normalized.
- Created Lots have immutable internal IDs and approved monthly shared Lot numbers; concurrent/retried submissions cannot duplicate a number, and cancelled/deleted numbers are never reissued.
- Product, Color, Run and Mould behavior matches the confirmed rules; no many-to-many Mould/Product or Color-based Mould rule is introduced.
- The logger shows PLC-derived stop intervals, supports open stops, flags data gaps, and permits operator classification separately from raw event evidence. Missing data is never displayed as proven downtime.
- Tests demonstrate idempotent replay, no fabricated start/end, no number reuse, and no source table/workbook writes.
- Owner reviews the live behavior and approves a separate production deployment task; passing tests alone is not deployment authorization.

## Approval gate

Review and approve this plan before any code, schema, database record, migration, or historical import is changed. In particular, resolve the numbered decisions in Section 11. No implementation was performed as part of this discovery task.
