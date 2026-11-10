# OmagMES Development Progress and Handoff

**Status key:** DONE · IN PROGRESS · PENDING · BLOCKED  
**Last updated:** 2026-11-10

## Project Overview and Approved Architecture

**DONE — Approved target architecture recorded.** React + TypeScript + Vite frontend → FastAPI REST API → Microsoft SQL Server database `OMAG`, new application schema `omagmes`; legacy `dbo` is read-only. Project target: `D:\AI\OmagMES`; reference: `D:\AI\FittingMES`.

- The React + TypeScript + Vite frontend and FastAPI REST prototype are implemented. Existing write/save routes remain process-local mock state. An authorized manual SELECT validation reached SQL Server, but the tested login is not least-privilege; do not enable live reads. The pyodbc timeout preflight bug is fixed and covered by passing regression tests.
- Workflow discovery, review-only SQL drafts, UI reference mapping, and project handoff documentation are present. SQL migrations remain unexecuted and production writes are disabled.
- Phase 2 read-only source integration and APP_PORT work were committed and pushed as `f9a8bc2ef15cb8753ae61ba71bb8aac50a849705` (`feat: add OmagMES Phase 2 read-only integration and port configuration`). The current factory-requirements review is documentation/analysis only. No files in FittingMES were modified.

## Factory Requirements and Master Workbook Review

**DONE — Requirements, both database skills, both supplied Excel workbooks, and the FittingMES Mould workflow were reviewed read-only on 2026-11-10.** This review is not approval to import workbook rows, query SQL, run migrations, modify production objects, or deploy.

- Read the full [factory-confirmed requirements](OmagMES_Factory_Confirmed_Requirements.md) and both applicable ID-first database skills: [OmagMES skill](../skill/DATABASE_ID_FIRST_DESIGN_SKILL.md) and [FittingMES skill](../../FittingMES/skill/DATABASE_ID_FIRST_DESIGN_SKILL.md). New tables require `id bigint IDENTITY(1,1)` and `Rectime datetime NOT NULL DEFAULT (GETDATE())`; relationships use authoritative IDs, business codes remain unique attributes, existing `OMAG.dbo` objects remain read-only, and all new application tables belong in the approved `omagmes` schema. No database connection was attempted.
- Inspected both XLSX files locally with read-only workbook access; no workbook was saved, recalculated, or changed, and no data was imported.
- [Omag_Product_Master.xlsx](../Master/Omag_Product_Master.xlsx), sheet `Std Data`: read-only workbook inspection confirms physical source columns A Product Code, B English name, C Thai name, BA Pieces/Drop candidate, and BC Cycle Time candidate. BA's stacked labels disagree (`ก้อน/Drop` in row 2 versus `pcs./pallet` in row 3), while BC is labeled `Cycle Time` / `Second`. Data rows 5–939 contain 917 nonempty rows: 910 have a code and 863 exact code values; 37 exact-code groups repeat (47 extra rows), and seven nonempty rows have no code. BA is populated on 859 data rows (58 blank); BC on 853 (64 blank). Repeated exact codes contain 8 BA conflicts and 13 BC conflicts (4 overlap); eight duplicate groups have differing English names. One case-only variant exists (`ZCC01041366M011` / `zcc01041366M011`). These findings are candidate data-quality evidence, not approval of any product or standard.
- [Omag_Mould_Master.xlsx](../Master/Omag_Mould_Master.xlsx), sheet `No.Mould`: read-only inspection confirms 41 nonempty A:I data rows; 39 contain a Mould No. in column H but only 37 distinct values. `NKFL01101` and `NKFL25001` each repeat; two nonempty records lack a Mould No. Column B is a Thai/mixed-language product description, not a Product Code/FK; no exact Product association can safely be inferred from this workbook alone. Column G (cancel/inactive date) is blank in all 39 numbered records. The workbook contains 3,774 formulas, 3,393 with external workbook references. Column I is a calculated recent-month usage value, not verified lifetime/current Press Drops. Treat the workbook as a review candidate only; do not import its usage values or infer a lifecycle status from the daily ACT grid.
- FittingMES source review covered [app/mould.py](../../FittingMES/app/mould.py), [app/templates/mould.html](../../FittingMES/app/templates/mould.html), Mould routes in [app/main.py](../../FittingMES/app/main.py), and [tests/test_mould.py](../../FittingMES/tests/test_mould.py) / [tests/test_mould_ui.cjs](../../FittingMES/tests/test_mould_ui.cjs). Reusable patterns are filterable list + selected detail, registration, restricted metadata edits, confirmation and dedicated lifecycle actions, and separate Status/Recondition/Usage histories. FittingMES's four statuses and its database procedures are reference behavior only; OmagMES statuses, actor identity, and transitions still need factory approval/adaptation.
- Current OmagMES application status: Product and Reject Reason master data are read-only demo review tables; there is no editable Product Master or explicit-click GET UPDATE PRODUCT operation. Product/Mould records and lifecycle actions are mock-only. The Mould UI does not yet provide the full filter/register/edit/detail/history workflow. Lot creation is mock-only, accepts a display LotName, and does not implement the confirmed automatic `C` + `DDMMYY` + shift + sequence + `B` Lot No.
- The existing review-only DDL is not approved and is not sufficient as-is for this handoff: `ProductionLot` has no generated Lot No.; `MouldUseEvent` is linked to Run rather than the required Lot and carries no per-Mould Drop attribution; current Mould status checks omit `DENIED`. Reconcile these gaps and audit existing schema before proposing an approved migration. Do not execute the review draft.

### Automatic draft Lot, post-detection plan and Mould intervals — documentation review

**DONE — Permanent workflow reference prepared on 2026-11-10; direct FittingMES source inspection, OmagMES gap review, and authorized SELECT-only PRESS history validation are complete.** No FittingMES files/database/tests, workbook, migration, production data, or SQL schema were changed; no commit or push was performed.

- New reference: [OmagMES_AutoLot_Mould_Assignment.md](OmagMES_AutoLot_Mould_Assignment.md). It records confirmed requirements, source evidence and limitations, OmagMES gaps, unresolved decisions, recommended stages, and acceptance scenarios.
- Updated [factory-confirmed requirements](OmagMES_Factory_Confirmed_Requirements.md) with the confirmed historian configuration: ProductCnt was previously logged hourly; the factory recently switched to on-change DropCnt logging. Both tags represent the same `DB3.DBW2` counter, but DropCnt is authoritative for new Auto Lot Detection and ProductCnt is historical reference only. The longer ProductCnt and shorter DropCnt histories are expected after the change; never merge/sum the histories. Use SQL `_TIMESTAMP` to locate counter transitions only after timestamp/timezone semantics are verified; no row is generated while the value is unchanged. SQL observations show DropCnt persists as `_NAME='OMAG.PRESS.OEE.DropCnt'`; the available sample was 332 rows, all quality 192, with values 101–414 and no observed decrease. The table has only a clustered `id` key, so bounded queries may scan. Reset semantics and timestamp/timezone interpretation remain unresolved.
- Confirmed workflow requirements: detect a draft production record before plan selection; retain stable ID, detected start/end, raw Drop count, operator-confirmed Drop count and review status; allow operator correction/dismissal without altering raw PLC data; select plan after detection; exact-match `MaterialCode` to Product Master `ProductCode`; keep approved Pieces/Drop and Cycle Time Product-owned; assign multiple Mould intervals within one official Lot; no new official Lot solely for Mould replacement if Product/Color are unchanged; separate draft identity/detection from official Lot ID/number; do not infer Product/Color change from a counter reset; and calculate Mould age in Drops only.
- Directly inspected FittingMES plan and Lot paths: `app/main.py` (`production_page`, `mark_used`, `choose_plan`, `save_plan`, plan/production handlers), `app/prod_api.py` (`read_historical_plans`), `app/products.py` (`confirm_mapping`), `app/lots.py` (Lot locks, insert/update/delete/history), and `app/templates/production.html` (plan selection, Lot forms, Press/Mould assignment UI). FittingMES selects plans before Lot creation and its Product mapping is material-prefix based; both differ from OmagMES's new post-detection exact-match requirements.
- Directly inspected FittingMES Mould and availability paths: `app/mould.py` (list/detail, lifecycle service calls and three histories), Mould routes in `app/main.py`, `app/templates/mould.html`, `app/resource_availability.py` (`resolve_effective_interval`, `find_assignment_conflict`, `validate_lot_resource_availability`), and `app/press_production.py` (`read_eligible_moulds`, Product/status validation, interval availability, resource locks, `save_press_production`, usage reconciliation). FittingMES uses interval intersection, fail-closed unresolved intervals, and transaction/application locks; this is a pattern reference, not an OmagMES implementation specification.
- Inspected FittingMES evidence/tests: `sql/023_product_family_id.sql`, `sql/027_shift_aware_press_production.sql`, `tests/test_mould.py`, and `tests/test_press_production.py`. Its per-PressProduction `MouldUsage` row is reconciled in place from `CounterQty`; this is not an immutable Lot-linked Mould interval/Drop attribution ledger. Relevant tests use fake SQL cursors/connections and were not run for this documentation task.
- Evidence limitations: FittingMES source does not establish OmagMES's PLC draft-detection logic, and the checked-in repository does not include the `vw_MouldLifeSummary` definition or all lifecycle procedure definitions. Actual DB-side age/reset rules and live source behavior were not verified. FittingMES field `CounterQty` / `UsageCycles` is not proof of Drop semantics.
- Current OmagMES gaps remain: no PLC-derived draft queue with correction/deletion; no plan assignment after detection; no exact MaterialCode-to-ProductCode resolution in this workflow; no explicit Lot-linked multi-Mould interval records or per-interval verified Drop allocation. Existing AutoCal's `ProductCnt` and current review-only DDL do not satisfy these requirements.

**SQL validation outcome and blockers:** `.env` still contains `SQL_SERVER=127.0.0.1`, `SQL_DB=OMAG`, `SQL_DRIVER=AUTO`; its values were not changed and credentials were not displayed. With a temporary in-memory override, the authorized connection reached `10.28.255.98`, database `OMAG`, SQL identity `SCGLS-NK\SQLEXPRESS` / instance `SQLEXPRESS`. Schema and bounded history were queried using SELECT statements only; there were no SQL writes or schema changes. The tested login has effective SELECT, INSERT, UPDATE, DELETE, ALTER and CONTROL permissions on `dbo.PRESS`, so it is **not read-only**; do not use it for application source access. Obtain a DBA-provisioned least-privilege login. The PRESS table has `id`, `_NAME`, `_NUMERICID`, `_VALUE`, `_TIMESTAMP`, `_QUALITY` and only a clustered `id` primary key. DropCnt persists as `OMAG.PRESS.OEE.DropCnt`; its 332 observed rows span 2026-11-10 10:00:07–14:05:25, all quality 192, value range 101–414, 312 increases/19 unchanged/no decreases, max gap ~14m26s. ProductCnt has a separate history of 69,604 rows from 2025-08-05 through 2026-11-10. Factory confirms the historian was recently switched from hourly ProductCnt to change-based DropCnt, so the shorter DropCnt history is expected; never combine aliases. Use `_TIMESTAMP` for transitions after confirming time semantics/timezone. A change logger emits no row while the value is unchanged. Reset details and transition segmentation remain open. The adapter's unsupported `cursor.timeout` assignment has been replaced with pyodbc's connection-level `timeout`, with regression coverage; focused tests and the complete backend suite pass (43 passed, one existing Starlette/httpx deprecation warning).

**Unresolved before implementation:** DBA must provision and verify a SELECT-only login. Confirm `_TIMESTAMP` semantics/timezone and DropCnt reset transitions; the recent switch explains the shorter history, while change-based logging means unchanged periods have no records. Define draft segmentation, gaps/quality/reset/out-of-order/late-data rules and idempotency; define plan identity/version/multiple rows and pending-standard behavior; resolve existing 06:00–08:00 and cross-shift Lot boundary rules before official Lot numbering; define Mould install/removal evidence, open-interval handling, overlap boundary semantics, status/return approval, counter-boundary attribution, correction audit, and access/retention. The reference marks half-open interval semantics as a proposal only, not a confirmed factory rule.

**Recommended resume sequence:** (1) DBA provisions a SELECT-only login; fix/test pyodbc query-timeout handling; then, after query-cost approval, continue bounded DropCnt history checks for timezone, retention and reset behavior without combining alias rows; (2) close detection segmentation, shift-boundary/06:00–08:00, plan identity/standards, Mould interval/attribution, and audit decisions; (3) audit schema and prepare ID-first `omagmes` logical design plus forward/rollback drafts for review only; (4) implement deterministic fake-source draft detection and isolated operator correction/deletion tests; (5) add exact plan/Product/standard snapshot workflow and explicit official Lot confirmation/numbering; (6) add Lot-linked sequential Mould intervals, overlap/concurrency checks and evidence-backed Drop allocation/age; (7) complete acceptance and factory/DBA/security approval. No import, migration, production write, deployment, or commit/push was performed.

### Factory decisions still required before implementation

- Product workbook: confirm that column BA means Pieces per Drop despite its conflicting stacked labels; resolve the repeated-code BA/BC values and repeated names; confirm Product/name source authority, exact-case uniqueness policy, approval/effective-date rules, and whether GET UPDATE PRODUCT previews missing codes or immediately creates Pending Standard rows. Discovery must query the planning synonym only after explicit button click, compare exact `MaterialCode`, never overwrite approved values, and retain missing standards blank.
- Lot numbering: define the 06:00–08:00 interval; resolve whether a continuing Product/Color run crossing the shift boundary retains its Lot or starts a shift-numbered Lot; define behavior beyond sequence 99, production date/timezone and concurrency locks, and audited manual correction permission. Product or Color changes create a new Lot; Mould replacement alone does not.
- Mould: reconcile duplicate/missing workbook Mould numbers and manually resolve each Mould-to-Product ID; confirm editable attributes, status vocabulary/transition matrix, return approval, assignment start/end capture, and whether workbook usage columns are for review only. Define how counter observations bracket installation intervals and how missing/gapped observations remain unallocated/uncertain.
- Database/security: the owner-approved host/database identity was verified with the authorized temporary override, but the tested login is overprivileged. Obtain a SELECT-only login before further application-level reads. No migration, production DDL/DML, workbook import, commit, or push was performed.

### Proposed implementation sequence — pending approval

1. Factory review of workbook conflicts, Mould identity-to-Product mapping, status/actions, and the open Lot boundary/numbering questions; publish an approved import mapping and exception list, still with no writes.
2. Update logical schema and migration/rollback drafts to include Lot No. sequencing, Lot-to-Mould intervals with attribution, Product standard revisions/snapshots, Mould lifecycle/audit, and any approved master structures. Re-audit schema and both ID-first rules before requesting DBA review; do not execute SQL.
3. Implement editable Setting -> Product Master and Setting -> Mould Master UI/API in mock/test mode first, with exact ProductCode matching, Pending Standard validation, immutable IDs, audited edits, approved lifecycle transitions, and FittingMES-inspired list/detail/history patterns.
4. Separately implement GET UPDATE PRODUCT behind an explicit click only, gated read-only access to the existing OmagPlan synonym, idempotent exact-code discovery, failure reporting, and no existing-standard overwrite. Test using fakes; do not query the live synonym until the host/permissions and owner approval are documented.
5. Implement Lot-number generation and Mould assignment/drop attribution only after the open business rules are approved; add boundary, concurrency, duplicate/retry, lifecycle, history, and uncertainty tests. Keep all persistence mock-only until separate database-write/migration authorization.
6. Conduct factory acceptance and DBA/security review. Import data, run migrations, connect to production sources, and deploy only after separate explicit approvals.

## Application Access Port Configuration

**DONE — OmagMES uses root `.env` setting `APP_PORT=3001` as the shared browser-access port (fallback: 3001).**

- Root `.env` and `.env.example` contain `APP_PORT=3001`. Vite explicitly loads the root `.env` even when launched from `frontend/`, validates the value, and uses it for dev/preview listeners on `0.0.0.0`; its fallback is 3001. `/api` requests proxy to FastAPI at `127.0.0.1:8000`, which remains unchanged and loopback-only.
- The React client uses same-origin relative API paths. FastAPI explicitly loads the root `.env` and reports the application port in `/api/health`; this does not change its internal listening port. Obsolete localhost-only CORS settings were removed.
- `run_omagmes.bat` loads only `APP_PORT` from the root `.env`, starts FastAPI, waits for `/api/health`, then starts Vite with that environment value. Starting Vite directly from `frontend/` also loads the root `.env`. README documents the launcher and access URLs.
- Validation on 2026-11-09: direct `npm run dev` from `frontend/` read the root setting and started Vite on port 3001; the launcher started listeners on `0.0.0.0:3001` and `127.0.0.1:8000`. Browser access to `http://10.28.255.98:3001/` loaded the UI, reported API connected, and `/api/health` returned mock-mode JSON through the same origin.
- Cross-computer access was not tested. Windows Firewall and network ACLs must permit inbound TCP 3001; actual reachability depends on the selected host IP/network route. No SQL Server/Kepware configuration or database connection was changed.

## Confirmed Business Rules

**DONE — Existing owner-confirmed rules reviewed in the current repository.** Refer to [OmagMES_Confirmed_Business_Rules.md](OmagMES_Confirmed_Business_Rules.md), [OmagMES_Database_Design.md](OmagMES_Database_Design.md), and [OmagMES_Product_Production_Standard_Master_Design.md](OmagMES_Product_Production_Standard_Master_Design.md).

- Press + Wet Line form one coupled Wet unit; Dry/Depallet is independent; Block/Fence are Product families, not physical lines.
- Product identity uses immutable internal IDs and exact Product Code spelling. Product and Color are separate. Product change creates a Run and Lot; Color change creates a Lot; Mould/shift/day/pause alone do not.
- Lot ID is immutable through production, curing and depallet. LotName may duplicate and requires audited edits.
- One Mould belongs to one Product; current and lifetime age use Press Drops; only approved recondition return resets current age.
- BA means Pieces per Drop; BC means seconds per Drop; values remain Product-owned and versioned. 25 Product Codes still have numeric source conflicts and must not be auto-selected or imported.
- PLC AutoRun is supporting Wet line-status evidence; ProductCnt is the Drop counter; CYC is not the quantity counter. ProductCnt daily reset at 07:00 Asia/Bangkok is owner-confirmed for this implementation instruction.
- Wet IP Camera `line='wet'` records are individual tray Pieces; Wet Reject quantity uses cumulative `cntR*` tags, not button-state `R*` tags.
- AutoCal is suggestion-only; operator review and explicit SAVE are required. Initial persistence must be mock-only, not production SQL.
- Wet Run Log is manually classified; AutoRun does not overwrite operator classifications. Wet OEE preview uses clearly labeled simulated values.

## Database Schema and Migration Status

**IN PROGRESS — Review-only migration/validation/rollback drafts are prepared. Manual SELECT inspection verified the OMAG target and part of PRESS metadata/history; application live access remains blocked by broad login permissions, incomplete DropCnt history, and unresolved source policy.**

- Verified/read full OmagMES skill: [../skill/DATABASE_ID_FIRST_DESIGN_SKILL.md](../skill/DATABASE_ID_FIRST_DESIGN_SKILL.md).
- Verified/read full FittingMES skill: [../../FittingMES/skill/DATABASE_ID_FIRST_DESIGN_SKILL.md](../../FittingMES/skill/DATABASE_ID_FIRST_DESIGN_SKILL.md).
- Also read the Pylance `python-fact-grounded-coding` skill at `C:\Users\Administrator\.vscode\extensions\ms-python.vscode-pylance-2026.4.1\skills\python-fact-grounded-coding\SKILL.md` for the Python implementation/validation workflow.
- Required new-table conventions: `id bigint IDENTITY(1,1) NOT NULL PRIMARY KEY`; `Rectime datetime NOT NULL DEFAULT (GETDATE())`; ID-based FKs, unique business-code attributes, constraints, relevant indexes, safe key resolution, auditable revisions/corrections.
- Draft package: [review-only SQL drafts](../db/review-only/README.md) contains forward DDL, catalog validation and guarded empty-schema rollback. A static pytest checks ID/Rectime and forward/rollback table parity. These are not DBA-reviewed, SQL Server-parsed, or approved.
- SQL migrations: **not executed**. An authorized, manual SELECT-only validation was performed; it was not an application integration test. The adapter timeout preflight bug was fixed and validated by tests; the tested SQL login remains unsuitable for application use.
- Production database writes: **disabled / not enabled**. No SQL change has been run in this session.
- Legacy `OMAG.dbo` tables: **not changed**. Any source inspection must remain bounded and read-only.
- Connection configuration was inspected without exposing credential values; `.env` remains at host `127.0.0.1`; no settings were changed. A temporary in-memory override connected to `10.28.255.98` / `OMAG` and verified identity, but the tested login had broad write/DDL permissions. Do not use it for the application; get a SELECT-only login. See [schema implementation gate](OmagMES_Schema_Implementation_Gate.md).
- Schema-critical items remain: authoritative Product/Color/Reject Reason/Mould/User masters; actual `REJECT_WET` mappings; camera source timestamp/identity and duplicate policy; approved Product standards/effective periods; counter feed/time/quality/gap behavior; event grain; permissions and rollback review. No unapproved master or standard seed data.

## FittingMES Reference Analysis Status

**DONE — Read-only source-level workflow analysis completed; mapping recorded.**

- Actual FittingMES routes, services, templates, SQL migrations, and focused tests were inspected for Product, Lot, production/cure, reject and reason workflows, explicit SAVE, time events, Mould, and audit.
- Deliverable: [OmagMES_FittingMES_Workflow_Implementation_Mapping.md](OmagMES_FittingMES_Workflow_Implementation_Mapping.md).
- Do not copy FittingMES schema or machine assumptions; document actual reusable behaviors and OmagMES differences with source references.

## React Frontend Implementation Status

**DONE — React + TypeScript + Vite prototype implemented and built.**

- Required Vite + React + TypeScript operator prototype; no Jinja2, Next.js, WebSockets, or UI dependencies beyond React/Vite/TypeScript.
- Navigation: Production, Wet Reject, Wet Run Log, Wet OEE, Curing, Depallet, Settings.
- Also includes a Mould/recondition screen, audited mock LotName rename, and Product-vs-Color Run/Lot transition controls.
- Use explicitly labeled mock data; AutoCal → edit → explicit SAVE only in process-local mock backend.
- Confirmed values must not be prefilled from conflicting sources.

## FastAPI Backend and REST API Status

**DONE — Mock FastAPI REST API implemented; Phase 2 live-source endpoints are present but gated and unverified.**

- Mock endpoints cover health/bootstrap, Lots and LotName rename, AutoCal preview, production/reject explicit SAVE, manual Wet Run Log events, simulated Wet OEE, Curing/Depallet mock records, and Mould recondition transitions.
- `backend/app/sql_source.py` adds explicitly gated, bounded, parameterized SELECT access for approved legacy `PRESS`, `REJECT_WET`, and `product_count` sources, with configured timeouts, target identity and SELECT-only permission preflight, and sanitized failures. Metadata/data queries require review flags. Actual source metadata has not been inspected or approved.
- Read-only API routes cover source health, Wet status, latest/history ProductCnt, dynamic `cntR*` Reject counters, Wet camera metadata/observations, historian metadata, and a source dashboard. No route writes to SQL; all existing SAVE routes remain mock-only.
- `backend/app/live_autocal.py` calculates suggestions only from verified PLC quality/timezone/gap settings, uses the confirmed 07:00 Asia/Bangkok reset rule, rejects incomplete/ambiguous intervals, and withholds Wet Camera Lot suggestions unless metadata and boundary/duplicate/quality policies are configured.
- All mock state remains in-process memory and resets at backend restart. Live mode reads `.env` through `python-dotenv`, but a connection has not been attempted.

## PLC / IP Camera / HMI AutoCal Status

**DONE — Mock suggestions remain available; live-read-only AutoCal is implemented behind source and Lot-window approval gates.**

- Prototype AutoCal excludes `CYC`, treats the 07:00 Asia/Bangkok ProductCnt reset as a daily boundary, keeps the first post-reset value as the new daily baseline, and flags mock-source limitations. It does not sum across the reset.
- Wet Camera `value_cnt` is per observation/tray; inspect timestamp and identity before proposing Lot attribution; conveyor delay at changeovers is unresolved.
- Wet Reject discovers/represents `cntR*` counters and excludes `R*` button states; source counter suggestions remain separate from unapproved demo reason codes and are never silently mapped. Verify actual reason definitions/mappings before finalizing master data.
- AutoRun is not written into Wet Run Log classifications. For prototype, provide deterministic mock suggestions and visibly label them; no raw legacy data writes.
- Live Press history selects ProductCnt only. Counter suggestions require a configured positive maximum-gap threshold; missing approval withholds the computed quantity.

## FittingMES UI Reference and OmagMES Adaptation

**DONE — FittingMES frontend patterns inspected and documented before the React UI edits.** See [OmagMES_FittingMES_UI_Reference.md](OmagMES_FittingMES_UI_Reference.md) for the source inventory, mapped design patterns, OmagMES menu map, and deliberate differences.

**FittingMES source files referenced:**

- `D:/AI/FittingMES/app/templates/navigation.html` — horizontal Production / Depallet / Setting groups, expandable compact subnav, selected route and retained context.
- `D:/AI/FittingMES/app/templates/api_base.html` — shared header, no-sidebar shell, compact gray-blue panels/forms/tables, focus and status styling.
- `D:/AI/FittingMES/app/templates/production.html` — selected Lot and editable table with explicit Save/status.
- `D:/AI/FittingMES/app/templates/reject.html` — context-first Reject form, explicit save/edit/cancel and saved-entry table.
- `D:/AI/FittingMES/app/templates/logger.html` and `logger_summary.html` — compact event entry, status, history and separate summary view.
- `D:/AI/FittingMES/app/templates/mould.html` — filter/list/detail/history layout and confirm-before-lifecycle controls.
- `D:/AI/FittingMES/app/templates/press_mc.html` and `logger_master.html` — master list/detail and read-only review-table patterns. FittingMES Press/machine data and behavior were not ported.

**UI changes completed:** replaced OmagMES's fixed sidebar and dashboard-style green/rounded visual treatment with FittingMES's compact horizontal, three-group tab navigation and gray-blue operator layout; grouped Production, Wet Run Log, Wet Reject, Wet OEE and Curing under Production; Depallet under Depallet; Mould and Settings under Setting. Curing is placed with the production-related Usage analogue, while Wet Reject remains with the Wet workflow. Kept all OmagMES workflows in React, retained selected Lot ID/context in app state, added read-only Product/standard and dynamic reject-counter review tables to Settings, changed Wet Reject's suggestion action to explicit RECAL wording, added confirmation before Mould lifecycle transitions, and differentiated success from validation messages accessibly. Existing AutoCal/review/edit/explicit SAVE and Lot rename dialog behavior remains.

**Remaining UI differences:** OmagMES is a single-page React application, so it switches content without FittingMES's server-rendered route/date refresh; OmagMES has a simulated Wet OEE and explicit Curing workflow that FittingMES does not provide; Product/Color Run/Lot selection replaces FittingMES's plans and machine assignments; Mould uses OmagMES Product/Press Drops rules. Settings master views are read-only because authoritative data and approvals are pending. These differences are intentional and are not production workflow approvals.

## Testing and Validation Results

**DONE — Phase 1 unit/API tests, static migration-draft checks, frontend build, and browser smoke checks. Phase 2 fake-source tests and frontend build also pass; live SQL is untested.**

- Backend tests after UI changes: **15 passed** (one Starlette/httpx deprecation warning); includes mock API lifecycle behavior and static review-only migration checks.
- Frontend production build after UI changes: `npm run build` **passed** (TypeScript and Vite).
- Phase 2 backend validation on the requested baseline: `pytest backend/tests -q` **42 passed**, one Starlette/httpx deprecation warning. The source integration tests use fake drivers; they do not open a SQL connection.
- Phase 2 frontend validation: `npm run build` **passed** (TypeScript and Vite). Workspace diagnostics report no errors.
- APP_PORT configuration validation: `pytest backend/tests -q` **42 passed**, including the `APP_PORT` health check; `npm run build` **passed** after Vite root-env loading changes.
- Port-change validation: `run_omagmes.bat` successfully started FastAPI on loopback `8000`, waited for `/api/health`, then started Vite on `0.0.0.0:3001`. Browser smoke check loaded the app at `http://10.28.255.98:3001/`, showed API connected, and confirmed `/api/health` returned successfully through the same external origin.
- Current network reachability from a separate workstation was not tested. Host firewall/network ACLs may still block inbound TCP 3001.
- Manual SQL connection and target identity were verified using a temporary host override; PRESS metadata and bounded DropCnt history were read with SELECTs. The account is not least-privilege, the application health gate fails, and history is too short to establish reset/retention semantics. No SQL writes or production changes were made.
- Browser smoke check: new horizontal group/subnav navigation, Production, Wet Reject, Curing, Depallet, Mould and Settings pages render; Lot #502 remained selected after switching from Production to Wet Reject. Mould's new lifecycle confirmation appeared and was canceled without a request. Settings Product/standard and reject-counter tables are read-only and visibly unapproved. At a narrow viewport the page width was checked after fixing table overflow; wide tables remain contained in their scroll wrappers.
- Previous browser smoke checks cover AutoCal no-autosave, manual Wet Run Log, simulated Wet OEE, Product/Color Lot transitions, Lot rename, and Mould recondition behavior. UI-only session used fallback data with API offline; no production API or SQL was connected.
- Pytest emitted a Starlette deprecation warning about its `httpx` test client integration; tests passed. No SQL Server syntax/runtime validation was performed.

## Files Created or Modified

**Created in earlier work:** this progress/handoff document; workflow mapping; schema gate; README; mock FastAPI modules/tests; React/Vite frontend; review-only forward/validation/rollback SQL drafts; and the FittingMES UI reference record.

**Implementation files:**

- `backend/app/` mock FastAPI app, models, mock store and deterministic AutoCal service.
- `backend/tests/` API and review-draft static checks.
- `backend/requirements.txt`.
- `frontend/` React/Vite/TypeScript app and npm lockfile.
- Phase 2 modified `backend/app/main.py`, `backend/requirements.txt`, `backend/tests/test_api.py`, and `frontend/src/App.tsx` / `frontend/src/main.tsx`; added `backend/app/sql_source.py`, `backend/app/live_autocal.py`, `backend/tests/test_live_sources.py`, and `frontend/src/source-mode.css` / `frontend/src/source-window.css`.
- Port configuration modified the ignored local `.env` to add only `APP_PORT=3001` (SQL settings preserved), added `.env.example`, and modified `backend/app/main.py`, `backend/tests/test_api.py`, `frontend/src/App.tsx`, `frontend/vite.config.ts`, `frontend/package.json`, and README; added `run_omagmes.bat`.
- Updated this handoff with Phase 2 scope, validation, exact skill references, blockers, and a safe resume plan.
- `backend/requirements.txt` now includes `pyodbc`, `python-dotenv`, and `tzdata` for the gated SQL adapter and Windows timezone support.
- `frontend/src/fittingmes-ui.css` FittingMES-inspired shell/control styling; navigation and read-only master review are implemented in `frontend/src/App.tsx`.
- [OmagMES_FittingMES_UI_Reference.md](OmagMES_FittingMES_UI_Reference.md) records the inspected FittingMES source files and pattern mapping.
- `db/review-only/` version 001 SQL review drafts; never executed.
- `.gitignore` extended for generated Node dependencies.
- [README.md](../README.md) contains local run/test steps and safety scope.

**Pre-existing user work observed and preserved:**

- Modified: `docs/OmagMES_Confirmed_Business_Rules.md`
- Modified: `docs/OmagMES_Database_Assessment.md`
- Modified: `docs/OmagMES_Database_Design.md`
- Modified: `docs/OmagMES_Phase1_Discovery_and_Implementation_Plan.md`
- Modified: `docs/OmagMES_Product_Production_Standard_Master_Design.md`
- Modified: `docs/OmagMES_Product_Standards_and_Wet_OEE_Excel_Analysis.md`
- Untracked: `doc/` historical data directory
- Untracked: `docs/OmagMES_Product_Standard_Conflict_Review.csv`
- Untracked: `docs/OmagMES_Product_Standard_Conflict_Review.md`
- Untracked: `docs/OmagMES_Product_Standard_Factory_Review.xlsx`

No existing code or source workbook was overwritten.

## Pending Issues and Unresolved Decisions

**PENDING / OWNER REVIEW:**

- Reconcile the endpoint: owner-specified `10.28.255.98` versus existing `.env` host `127.0.0.1`; do not test either with project credentials until scope is authorized.
- Approve exact DDL/collation, schema collision and permissions, authentication/AppUser mapping, migration review, non-production test, backup and rollback. No SQL syntax check against SQL Server was possible/performed.
- Identify authoritative Product/Color/Reject Reason/Mould masters and actual `cntR*` mappings; retain conflicting standards unseeded.
- Confirm source identity/timezone/quality, daily ProductCnt reset behavior, camera timestamp/dedup/latency, Wet OEE segmentation and threshold policies.
- Confirm run event edit/correction policy and Curing/Depallet event details/units. Current prototype fields are mock-only and explicitly flagged.
- Add user authentication and immutable database-backed audit before operational use. The displayed demo operator/approver is not authenticated.

## Next Actions

1. Ask the DBA for a SELECT-only source identity, then verify its effective permissions on each approved source table. Do not use the currently tested account for application reads.
2. Keep the pyodbc connection-level timeout regression covered by the passing full backend suite. Do not weaken source/permission gates.
3. After least-privilege and query-cost approval, continue only bounded DropCnt history checks to confirm timestamp/timezone and reset semantics; do not combine ProductCnt and DropCnt histories. The DropCnt persisted name is `OMAG.PRESS.OEE.DropCnt`, unlike the ProductCnt prefix convention currently in code.
4. Review PRESS source mapping and any planned adapter change; separately verify REJECT_WET and product_count metadata only after approved permissions. Approve PLC quality/gap rules, camera quality/duplicate/identity/boundary policy, and Lot-window source before enabling data paths.
5. Continue to keep all SAVE actions mock-only and do not execute SQL migrations. Preserve `.env` and secrets; no workbook import, commit, or push without separate authorization.
6. Continue operator review of the prototype; keep demo Lots, standards and Reject Reason mappings visibly unapproved and separate from live source observations.
7. Preserve local-only ignored files and historical workbooks; do not stage, commit, or push without a separate request.

## Resume From Here

**Current state:** Phase 2 source integration and root `.env` `APP_PORT=3001` are committed and pushed at `f9a8bc2ef15cb8753ae61ba71bb8aac50a849705`. Vite listens on `0.0.0.0:3001`; FastAPI remains internal at `127.0.0.1:8000`. Existing UI/tests/build results are recorded above. `.env` SQL settings were not changed and credentials were not disclosed. The authorized SELECT-only test used a temporary in-memory override to connect to `10.28.255.98` / `OMAG` (`SCGLS-NK\SQLEXPRESS`). Factory confirms logging recently switched from hourly ProductCnt to on-change DropCnt; DropCnt is authoritative for new Auto Lot Detection, ProductCnt is historical reference only, and the histories must never be combined. Use DropCnt `_TIMESTAMP` for transitions after timestamp semantics/timezone are confirmed; on-change logging emits no row while unchanged. The persisted DropCnt name is `OMAG.PRESS.OEE.DropCnt`. **Do not use the tested credential for application reads:** it has effective INSERT/UPDATE/DELETE/ALTER/CONTROL on PRESS despite this validation issuing SELECT statements only. The pyodbc timeout bug is fixed; all 43 backend tests pass, with one existing Starlette/httpx deprecation warning. Next: get a least-privilege SQL login and review bounded DropCnt time/reset semantics before any integration. No SQL writes/schema changes, workbook imports, migrations, production edits, commits, or pushes occurred. Product/Mould master management, AutoLot draft review, post-detection plan assignment, official Lot numbering, and Lot/Mould Drop attribution remain unimplemented. No FittingMES files were changed.
