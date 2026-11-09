# OmagMES Development Progress and Handoff

**Status key:** DONE · IN PROGRESS · PENDING · BLOCKED  
**Last updated:** 2026-11-09

## Project Overview and Approved Architecture

**DONE — Approved target architecture recorded.** React + TypeScript + Vite frontend → FastAPI REST API → Microsoft SQL Server database `OMAG`, new application schema `omagmes`; legacy `dbo` is read-only. Project target: `D:\AI\OmagMES`; reference: `D:\AI\FittingMES`.

- The React + TypeScript + Vite frontend and FastAPI REST prototype are implemented. Existing write/save routes remain process-local mock state; an explicitly gated, read-only SQL source adapter is implemented but has not connected to SQL Server and its source schema is unverified.
- Workflow discovery, review-only SQL drafts, UI reference mapping, and project handoff documentation are present. SQL migrations remain unexecuted and production writes are disabled.
- Phase 2 implementation changes are uncommitted and must be preserved. The workspace HEAD is the requested baseline `599f2657ac962fbcb9a1c786cf7e8d43e1f5c0bc`. No files in FittingMES were modified; no commit or push was made.

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

**IN PROGRESS — Review-only migration/validation/rollback drafts are prepared. Read-only Phase 2 source integration is implemented behind explicit gates, but live access and source schema verification are blocked pending endpoint reconciliation, owner/DBA approval, authoritative metadata and policy review.**

- Verified/read full OmagMES skill: [../skill/DATABASE_ID_FIRST_DESIGN_SKILL.md](../skill/DATABASE_ID_FIRST_DESIGN_SKILL.md).
- Verified/read full FittingMES skill: [../../FittingMES/skill/DATABASE_ID_FIRST_DESIGN_SKILL.md](../../FittingMES/skill/DATABASE_ID_FIRST_DESIGN_SKILL.md).
- Also read the Pylance `python-fact-grounded-coding` skill at `C:\Users\Administrator\.vscode\extensions\ms-python.vscode-pylance-2026.4.1\skills\python-fact-grounded-coding\SKILL.md` for the Python implementation/validation workflow.
- Required new-table conventions: `id bigint IDENTITY(1,1) NOT NULL PRIMARY KEY`; `Rectime datetime NOT NULL DEFAULT (GETDATE())`; ID-based FKs, unique business-code attributes, constraints, relevant indexes, safe key resolution, auditable revisions/corrections.
- Draft package: [review-only SQL drafts](../db/review-only/README.md) contains forward DDL, catalog validation and guarded empty-schema rollback. A static pytest checks ID/Rectime and forward/rollback table parity. These are not DBA-reviewed, SQL Server-parsed, or approved.
- SQL migrations: **not executed**. No SQL connection was attempted during this implementation session. The new adapter has only been exercised with fake-driver tests.
- Production database writes: **disabled / not enabled**. No SQL change has been run in this session.
- Legacy `OMAG.dbo` tables: **not changed**. Any source inspection must remain bounded and read-only.
- Connection configuration was inspected without exposing credential values; `.env` has host `127.0.0.1`, not owner-specified `10.28.255.98`. No connection/test was attempted and no settings were changed. The live adapter rejects this host before any connection attempt. See [schema implementation gate](OmagMES_Schema_Implementation_Gate.md).
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
- No live SQL connection, target identity, permission, actual source metadata, or production query has been verified.
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

1. Obtain owner confirmation of the exact approved SQL host and instance (expected host `10.28.255.98`) and DBA confirmation that the selected login has SELECT-only permissions on the three named source tables. Do not query until both are documented.
2. Resolve `.env` host `127.0.0.1` versus expected `10.28.255.98`; preserve secrets and do not change environment values without authorization.
3. After approval, verify target identity/permissions and review actual PRESS, REJECT_WET, and product_count metadata. Approve source timezone, PLC quality codes, counter-gap threshold, camera quality/duplicate/identity/boundary policy, and Lot-window source before enabling corresponding data paths.
4. Validate only bounded read-only source queries in an approved test window; continue to keep all SAVE actions mock-only and do not execute SQL migrations.
5. Continue operator review of the prototype; keep demo Lots, standards and Reject Reason mappings visibly unapproved and separate from live source observations.
6. Preserve local-only ignored files and historical workbooks; do not stage, commit, or push without a separate request.

## Resume From Here

**Current state:** Phase 2 read-only SQL integration and source-aware AutoCal are implemented but uncommitted on the requested baseline `599f2657ac962fbcb9a1c786cf7e8d43e1f5c0bc`. OmagMES uses root `.env` `APP_PORT=3001` (fallback 3001) for Vite's `0.0.0.0` listener; FastAPI stays internal at `127.0.0.1:8000`. Direct startup from `frontend/`, launcher startup, same-origin API proxy, 42 backend tests, frontend build, and browser network-interface URL were verified. One Starlette/httpx deprecation warning remains. Cross-computer access still depends on firewall/network policy. `.env` was changed only to add APP_PORT; SQL configuration is untouched. No SQL connection was attempted; source schema, target identity, and permissions remain unverified. Do not commit/push or access SQL until separately requested/authorized and owner/DBA gates are resolved. No FittingMES files were changed.
