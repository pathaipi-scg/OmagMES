# OmagMES Schema Implementation Gate

**Prepared:** 2026-11-08  
**Status:** Pre-implementation risk register. No database connection, SQL, DDL, or DML was attempted in this implementation session.  
**Safety boundary:** SQL Server `OMAG`, schema `omagmes`; legacy `dbo` must remain read-only and unchanged. Migration scripts, when separately prepared, are drafts and must never be executed in this session.

## 1. Connection/configuration finding

The existing OmagMES `.env` was inspected without displaying any credential values. Its configured server is `127.0.0.1`, which does not match the owner-specified SQL host `10.28.255.98`. The configured host was not contacted and no connection attempt was made. Do not silently replace environment settings or try credentials against the owner-specified server. The target database remains `OMAG`; connection and permission verification must be a separately authorized, read-only preflight.

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
- Review-only draft package now exists in [db/review-only](../db/review-only/README.md): version 001 forward DDL, catalog validation, and an empty-schema-only rollback proposal. A static test checks ID/Rectime compliance and forward/rollback table-set parity; this does not validate T-SQL syntax or execute SQL Server.
- The draft includes no Product, standard, Color, reject-reason, shift, equipment, user, or Mould seed data. It is an initial table proposal, not a fully approved production schema; effective-period overlap, identity/authentication, update immutability, source-key semantics, event capture, permissions, and source/database alignment remain unresolved.
- Do not execute migrations. Before any possible future execution, reconcile the endpoint, verify exact target and read-only access, receive DBA/owner approval, review destructive rollback, and test against a disposable non-production database.
- No migration is to be executed, and no SQL target connection is to be attempted until the owner-specified endpoint and read-only access scope are reconciled and explicitly verified.
