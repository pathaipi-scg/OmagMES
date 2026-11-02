# OmagMES Database Assessment

**Prepared:** 2026-11-02  
**Status:** Read-only assessment; proposed design is for review only. No database objects or data were changed.  
**Project scope:** OmagMES is treated as an independent MES project. Existing tables belonging to unrelated systems are out of scope and were not inventoried or analyzed.

## 1. Executive summary

- The configured SQL Server connection succeeded using ODBC Driver 18. The session verified that the active database is `OMAG` on the configured SQL Server instance. Connection secrets and the connection string were not displayed or recorded.
- A deliberately narrow metadata query checked only whether the proposed `omagmes` schema exists. It does not exist. Since it was absent, there were no objects within that proposed namespace to list. No other schemas, tables, columns, keys, or data were inspected.
- The workbook discovery indicates potential OmagMES capabilities around production reporting, material consumption, equipment stoppages, quality measurements, and product/material standards. The workbooks are operational reports, not an authoritative database catalog or validated process specification.
- The design proposal uses a dedicated `omagmes` namespace and creates no dependency on, and proposes no change to, unrelated legacy systems. Any future integration or reuse of another system's masters requires separate scope and authorization.
- No DDL, seed data, migration, or other database mutation was executed. Approval is required before implementation.

## 2. Scope and evidence

This assessment draws on:

1. The project database standard in [`skill/DATABASE_ID_FIRST_DESIGN_SKILL.md`](../skill/DATABASE_ID_FIRST_DESIGN_SKILL.md).
2. The read-only workbook findings in [`OmagMES_Initial_Discovery.md`](OmagMES_Initial_Discovery.md), covering 15 non-lock workbooks under `doc/Oct26`.
3. A read-only connection and namespace-existence check against the configured `OMAG` database.

The discovery report confirms visible reporting concepts including plants/factories, shifts, product and material codes, product/material standards, production date/shift/lot fields, mixer/logger observations, machine and reason codes, stoppage events, and quality measurements. These are candidate business concepts only. Workbook formulas, saved external links, cached values, and visible labels do not establish approved master ownership, lifecycle, record grain, or authoritative KPI definitions.

## 3. Connection and namespace check

| Check | Result |
|---|---|
| SQL Server connection | Successful; ODBC Driver 18 used. |
| Active database | `OMAG`, verified with `DB_NAME()`. |
| Proposed namespace | Schema `omagmes` does not exist. |
| Namespace object listing | Not applicable because the schema is absent. |
| Query scope | Schema existence only; no unrelated schemas or data inspected. |
| Database changes | None. |

This confirms the proposed schema name was not already present at the time of this check. It is not a full database collision audit, does not establish that an application principal has permissions to create it, and does not guarantee no concurrent change occurs before an eventual approved deployment. Recheck immediately before any separately approved migration.

## 4. Standard compliance assessment

The proposed design in [`OmagMES_Database_Design.md`](OmagMES_Database_Design.md) follows the project's stated ID-first rules:

- Every proposed table includes `id bigint IDENTITY(1,1) NOT NULL PRIMARY KEY` and `Rectime datetime NOT NULL DEFAULT (GETDATE())`.
- Relationships use surrogate IDs through foreign keys; business codes remain separate unique attributes.
- IDs are opaque and carry no business meaning. Seed or setup logic must resolve IDs by unique business code and fail if resolution is missing or ambiguous.
- Classification and mappings that owners may configure are represented as master data, rather than application-side hard-coded code lists.
- Workbook values and labels are not treated as authoritative master data or as validated business rules.
- No legacy table redesign, migration, or seed operation is proposed in this assessment.

The standard document refers to FittingMES in its purpose text. For this proposal its ID-first conventions are applied as the supplied database standard for OmagMES; confirm the intended scope if the standard itself is meant to govern a different project.

## 5. Conceptual comparison and reuse position

Because the user identified existing database tables as belonging to unrelated systems and out of scope, no attempt was made to reuse or assess their masters. In this context, “reuse” means carry forward a workbook-identified concept into a new OmagMES master or record after business validation—not reuse an unrelated database table.

| Workbook concept | Assessment for independent OmagMES | Qualification |
|---|---|---|
| Plant/factory and shift | Candidate OmagMES reference masters | Codes, ownership, official shift schedule, and overnight date attribution need owner confirmation. |
| Block/Fence product line, product codes/names, material codes/names | Candidate OmagMES masters | Workbook `Std Data` and labels are evidence of vocabulary, not proof of current authoritative values or uniqueness. |
| Product-material standards | Candidate effective-dated configuration | Recipe/standard grain, revisions, applicability, units, and approvals are unconfirmed. |
| Equipment/machine and equipment group | Candidate OmagMES masters | Workbook machine list is report-like; route/workstation sequence and ownership are not established. |
| Downtime reason and stoppage class | Candidate configurable masters | Planned/unplanned classification, minor-stop threshold, standard minutes, and effective dates need confirmation. |
| Production report, plan/actual, lot, output and material-use records | Candidate transactional data | The authoritative event grain and relation between plan, lot, report, and production run need confirmation. |
| Mixer/logger channels and readings | Candidate integration/measurement records | Source interface, timestamp semantics, mix identity, channel units, and deduplication rules are unconfirmed. |
| Quality characteristic, specification, sample and measurement | Candidate quality module | Sampling, specification revision, acceptance, abnormality, and disposition rules need confirmation. |
| Mould/drop-life, receiving, Silo/inventory, pallet use, recycled material | Later candidate modules | Current formulas and process controls are not sufficiently validated to establish inventory or tooling transaction rules. |
| OEE, yield and cycle-time outputs | Prefer derived/reporting results after definitions are approved | Workbook formulas are not approved KPI definitions; no formula should be promoted as a business rule yet. |

## 6. Proposed namespace and object families

Use a new schema named `omagmes` to isolate OmagMES-owned objects from unrelated schemas. The design document proposes these new OmagMES table names, grouped by sequence:

- Reference/configuration: `Plant`, `Shift`, `ProductLine`, `UnitOfMeasure`, `Product`, `Material`, `EquipmentGroup`, `Equipment`, `ProductMaterialStandard`, `StoppageClass`, `DowntimeReason`.
- Production reporting: `ProductionReport`, `ProductionReportLine`, `ProductionMaterialUsage`.
- Equipment events: `StoppageEvent`.
- Quality: `QualityCharacteristic`, `ProductSpecification`, `QualityInspection`, `QualityMeasurement`.

These are proposals, not verified existing objects or approved physical schemas. Each is described in the companion design document. More uncertain capabilities—inventory movement, material receipt and moisture adjustment, Silo reconciliation, logger ingestion, mould life, pallet issues, recycled material, and persisted OEE/yield results—are intentionally deferred pending process and formula validation.

## 7. Gaps and risks

1. **Business definitions:** Shift boundaries, overnight attribution, production record grain, lot identity, output categories, and actual versus good quantity are unresolved.
2. **Formula trust:** Discovery found cached spreadsheet formula errors and external workbook links. These can make the reports unsuitable as unqualified acceptance criteria.
3. **Units and conversion:** Several reports use blocks, tons, area, kg, seconds, and minutes. Units and conversions need explicit ownership and validation.
4. **Standards and effective dates:** Product/material standards may vary by date, product line, mixer, body/face stream, or revision. The proposal's initial grain is provisional.
5. **Machine and event identity:** Equipment group, route, downtime reason ownership, planned-stop rules, and the division between downtime and minor stoppage are unconfirmed.
6. **Quality semantics:** Characteristics, units, sampling frequency, specification versioning, Cp/Cpk methods, and abnormal/reject workflow need quality-owner confirmation.
7. **Integration:** Logger source identifiers, source timestamps, duplicate handling, and offline/manual correction policy are unspecified.
8. **Security and operations:** The connection check verifies connectivity only; grants, deployment principal, backups, retention, audit policy, and environment separation were not assessed.
9. **Concurrency:** Schema absence is a point-in-time result. The existence/collision check must be repeated before a future implementation.

## 8. Decisions requested before implementation

Before approving DDL or application work, obtain business-owner decisions on:

1. Project scope by plant, product line, operations, and first release.
2. Master ownership and unique codes for plant, shift, product, material, equipment, and reasons.
3. Shift schedule and production date attribution.
4. Production report/run/lot grain, plan lifecycle, and quantity definitions.
5. Unit catalog and approved unit conversions.
6. Product-material standard revision, applicability, and approval workflow.
7. Downtime/minor stoppage classification and OEE formula/aggregation.
8. Logger channel mapping, source identity, timestamp interpretation, and reconciliation policy.
9. Quality sampling and specification revision/acceptance process.
10. Which deferred areas (inventory, Silo, moulds, pallets, recycled material) belong in the first release.

## 9. Recommended implementation order after approval

1. Approve scope, terminology, code ownership, units, and event grains.
2. Review and approve the companion logical design; resolve nullable fields, uniqueness rules, retention, and audit requirements.
3. Recheck schema and object-name collisions in `OMAG` immediately before deployment; confirm permissions and environment.
4. Produce reviewed SQL Server DDL and a matching rollback plan; do not modify unrelated schemas.
5. Add safe reference seeds resolved by unique business codes, with exact-one-row checks.
6. Add server-side validation and tests for ID-first relations, uniqueness, configuration-driven rules, and business constraints.
7. Validate imports/reconciliation against business-owner-approved source samples before enabling production use.

**Approval gate:** No database changes have been made. Do not execute DDL, seed data, or migrations until the user explicitly approves the reviewed design and implementation plan.
