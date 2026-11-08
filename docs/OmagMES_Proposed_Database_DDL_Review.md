# OmagMES Proposed SQL Server DDL — Owner Review Copy

**Prepared:** 2026-11-04  
**Status:** Proposed DDL for review only. **Do not execute.** It is not a migration, seed script, deployment artifact, or authorization to change a database.  
**Scope:** Initial identity, Product/Color/Lot, Mould, and shared Press-stroke accumulator foundation. Curing/Depallet business event details, quality, inventory, OEE, dispatch, and historical imports are deferred where event grain or owner rules remain unresolved.

## 1. Review basis and mandatory conventions

Applicable database skill was located and read at the verified absolute path `D:\AI\OmagMES\skill\DATABASE_ID_FIRST_DESIGN_SKILL.md`. Every table below uses `id bigint IDENTITY(1,1) NOT NULL PRIMARY KEY` and `Rectime datetime NOT NULL DEFAULT (GETDATE())`. Relationships use surrogate IDs. `Rectime` records row creation only; operational timestamps use separate fields.

Read with these companion documents:

- [OmagMES_Confirmed_Business_Rules.md](OmagMES_Confirmed_Business_Rules.md)
- [OmagMES_Database_Assessment.md](OmagMES_Database_Assessment.md)
- [OmagMES_Database_Design.md](OmagMES_Database_Design.md)
- [OmagMES_FittingMES_Mould_Reference_Analysis.md](OmagMES_FittingMES_Mould_Reference_Analysis.md)
- [OmagMES_Press_Counter_Analysis.md](OmagMES_Press_Counter_Analysis.md)

### Confirmed rules reflected here

- Product is shape; Color is an independent coating variation. A Product or Color change creates a new immutable Lot ID. Product change also starts a new Product Run; Color change may create a new Lot within the same Product Run.
- LotName is editable and non-unique. It is not identity and does not participate in foreign keys.
- Each physical Mould belongs to exactly one Product. Multiple Moulds may reference the same Product. No many-to-many Mould/Product table or Mould/Color relationship.
- One shared accumulator processes approximately five-minute Kepware DataLogger samples. It is idempotent and ordered; counter decreases establish a new baseline, never a negative delta. Gaps/reset ambiguity remain uncertain. Counter resets do not reset Mould Age.
- Current Mould Age resets only after approved Return from Recondition; Lifetime Age never resets.
- Press strokes are not finished-product quantities, curing quantities, rejects, or OEE quantities.

### Proposed decisions and unresolved matters

- The DDL uses a product-bound `Color` master and makes `ProductionLot.ColorID` optional for colorless/unknown cases; owner approval is required for whether NULL is allowed or an explicit “no color” row is required.
- The DDL uses a Run-to-many-Lots relationship. The composite FK ensures a Lot's Product matches its Run.
- Exact Product Code collation, code reuse/effective-date overlap rules, Product master authority, and Color-to-Product validity are unresolved. The binary collation below is a proposed exact-comparison choice, not approved policy.
- The expected five-minute logger feed has not been proven to be the same source as legacy `OMAG.dbo.PRESS`; timestamp/timezone, stable observation key, quality semantics, reset behavior, long-gap threshold, and source retention require confirmation.
- Status vocabulary, Mould Number generation, recondition approval, audit identity provider, counter quality disposition, and stroke allocation reconciliation require owner approval before implementation.

## 2. Proposed DDL (documentation only)

This is illustrative SQL Server DDL for design review. Names, widths, status values, and indexes are proposals. Deployment must first repeat authorized namespace/master checks, receive owner approval, and be delivered as reviewed migration plus rollback and tests. Do not copy/run this block as-is.

```sql
CREATE SCHEMA omagmes;
GO

CREATE TABLE omagmes.Plant (
    id              bigint IDENTITY(1,1) NOT NULL CONSTRAINT PK_Plant PRIMARY KEY,
    Rectime         datetime NOT NULL CONSTRAINT DF_Plant_Rectime DEFAULT (GETDATE()),
    PlantCode       nvarchar(40) NOT NULL,
    PlantName       nvarchar(160) NOT NULL,
    IsActive        bit NOT NULL CONSTRAINT DF_Plant_IsActive DEFAULT (1),
    CONSTRAINT UQ_Plant_PlantCode UNIQUE (PlantCode)
);
GO

CREATE TABLE omagmes.ProductionLine (
    id              bigint IDENTITY(1,1) NOT NULL CONSTRAINT PK_ProductionLine PRIMARY KEY,
    Rectime         datetime NOT NULL CONSTRAINT DF_ProductionLine_Rectime DEFAULT (GETDATE()),
    PlantID         bigint NOT NULL,
    LineCode        nvarchar(40) NOT NULL,
    LineName        nvarchar(160) NOT NULL,
    IsActive        bit NOT NULL CONSTRAINT DF_ProductionLine_IsActive DEFAULT (1),
    CONSTRAINT FK_ProductionLine_Plant FOREIGN KEY (PlantID) REFERENCES omagmes.Plant(id),
    CONSTRAINT UQ_ProductionLine_Plant_LineCode UNIQUE (PlantID, LineCode)
);
GO

CREATE TABLE omagmes.ProductFamily (
    id              bigint IDENTITY(1,1) NOT NULL CONSTRAINT PK_ProductFamily PRIMARY KEY,
    Rectime         datetime NOT NULL CONSTRAINT DF_ProductFamily_Rectime DEFAULT (GETDATE()),
    FamilyCode      nvarchar(40) NOT NULL,
    FamilyName      nvarchar(120) NOT NULL,
    IsActive        bit NOT NULL CONSTRAINT DF_ProductFamily_IsActive DEFAULT (1),
    CONSTRAINT UQ_ProductFamily_FamilyCode UNIQUE (FamilyCode)
);
GO

CREATE TABLE omagmes.Product (
    id              bigint IDENTITY(1,1) NOT NULL CONSTRAINT PK_Product PRIMARY KEY,
    Rectime         datetime NOT NULL CONSTRAINT DF_Product_Rectime DEFAULT (GETDATE()),
    ProductFamilyID bigint NOT NULL,
    ProductName     nvarchar(200) NOT NULL,
    IsActive        bit NOT NULL CONSTRAINT DF_Product_IsActive DEFAULT (1),
    CONSTRAINT FK_Product_ProductFamily FOREIGN KEY (ProductFamilyID) REFERENCES omagmes.ProductFamily(id),
    CONSTRAINT UQ_Product_id_ProductFamily UNIQUE (id, ProductFamilyID)
);
GO

CREATE TABLE omagmes.ProductCodeAssignment (
    id              bigint IDENTITY(1,1) NOT NULL CONSTRAINT PK_ProductCodeAssignment PRIMARY KEY,
    Rectime         datetime NOT NULL CONSTRAINT DF_ProductCodeAssignment_Rectime DEFAULT (GETDATE()),
    ProductID       bigint NOT NULL,
    ProductCode     nvarchar(100) COLLATE Latin1_General_100_BIN2 NOT NULL,
    ValidFrom       datetime2(0) NOT NULL,
    ValidTo         datetime2(0) NULL,
    ChangeReason    nvarchar(500) NULL,
    CONSTRAINT FK_ProductCodeAssignment_Product FOREIGN KEY (ProductID) REFERENCES omagmes.Product(id),
    CONSTRAINT CK_ProductCodeAssignment_Validity CHECK (ValidTo IS NULL OR ValidTo > ValidFrom),
    CONSTRAINT UQ_ProductCodeAssignment_id_Product UNIQUE (id, ProductID)
);
GO

CREATE UNIQUE INDEX UX_ProductCodeAssignment_CurrentCode
    ON omagmes.ProductCodeAssignment (ProductCode)
    WHERE ValidTo IS NULL;
GO

CREATE TABLE omagmes.Color (
    id              bigint IDENTITY(1,1) NOT NULL CONSTRAINT PK_Color PRIMARY KEY,
    Rectime         datetime NOT NULL CONSTRAINT DF_Color_Rectime DEFAULT (GETDATE()),
    ColorCode       nvarchar(60) COLLATE Latin1_General_100_BIN2 NOT NULL,
    ColorName       nvarchar(160) NOT NULL,
    IsActive        bit NOT NULL CONSTRAINT DF_Color_IsActive DEFAULT (1),
    CONSTRAINT UQ_Color_ColorCode UNIQUE (ColorCode)
);
GO

CREATE TABLE omagmes.AppUser (
    id              bigint IDENTITY(1,1) NOT NULL CONSTRAINT PK_AppUser PRIMARY KEY,
    Rectime         datetime NOT NULL CONSTRAINT DF_AppUser_Rectime DEFAULT (GETDATE()),
    ExternalUserKey nvarchar(200) NOT NULL,
    DisplayName     nvarchar(160) NOT NULL,
    IsActive        bit NOT NULL CONSTRAINT DF_AppUser_IsActive DEFAULT (1),
    CONSTRAINT UQ_AppUser_ExternalUserKey UNIQUE (ExternalUserKey)
);
GO

CREATE TABLE omagmes.ProductionRun (
    id              bigint IDENTITY(1,1) NOT NULL CONSTRAINT PK_ProductionRun PRIMARY KEY,
    Rectime         datetime NOT NULL CONSTRAINT DF_ProductionRun_Rectime DEFAULT (GETDATE()),
    ProductionLineID bigint NOT NULL,
    ProductID       bigint NOT NULL,
    StartedAt       datetime2(0) NOT NULL,
    EndedAt         datetime2(0) NULL,
    StatusCode      varchar(24) NOT NULL,
    CreatedByUserID bigint NULL,
    CONSTRAINT FK_ProductionRun_Line FOREIGN KEY (ProductionLineID) REFERENCES omagmes.ProductionLine(id),
    CONSTRAINT FK_ProductionRun_Product FOREIGN KEY (ProductID) REFERENCES omagmes.Product(id),
    CONSTRAINT FK_ProductionRun_CreatedBy FOREIGN KEY (CreatedByUserID) REFERENCES omagmes.AppUser(id),
    CONSTRAINT CK_ProductionRun_Times CHECK (EndedAt IS NULL OR EndedAt >= StartedAt),
    CONSTRAINT UQ_ProductionRun_id_Product UNIQUE (id, ProductID)
);
GO

CREATE TABLE omagmes.ProductionLot (
    id              bigint IDENTITY(1,1) NOT NULL CONSTRAINT PK_ProductionLot PRIMARY KEY,
    Rectime         datetime NOT NULL CONSTRAINT DF_ProductionLot_Rectime DEFAULT (GETDATE()),
    ProductionRunID bigint NOT NULL,
    ProductID       bigint NOT NULL,
    ColorID         bigint NULL,
    LotName         nvarchar(120) NOT NULL,
    LotStartedAt    datetime2(0) NOT NULL,
    LotEndedAt      datetime2(0) NULL,
    CreatedByUserID bigint NULL,
    CONSTRAINT FK_ProductionLot_RunProduct FOREIGN KEY (ProductionRunID, ProductID)
        REFERENCES omagmes.ProductionRun(id, ProductID),
    CONSTRAINT FK_ProductionLot_Color FOREIGN KEY (ColorID) REFERENCES omagmes.Color(id),
    CONSTRAINT FK_ProductionLot_CreatedBy FOREIGN KEY (CreatedByUserID) REFERENCES omagmes.AppUser(id),
    CONSTRAINT CK_ProductionLot_Times CHECK (LotEndedAt IS NULL OR LotEndedAt >= LotStartedAt),
    CONSTRAINT UQ_ProductionLot_id_Product UNIQUE (id, ProductID)
);
GO

CREATE INDEX IX_ProductionLot_Product_Start
    ON omagmes.ProductionLot (ProductID, LotStartedAt DESC);
GO

CREATE INDEX IX_ProductionLot_LotName
    ON omagmes.ProductionLot (LotName);
GO

CREATE TABLE omagmes.LotNameChangeHistory (
    id              bigint IDENTITY(1,1) NOT NULL CONSTRAINT PK_LotNameChangeHistory PRIMARY KEY,
    Rectime         datetime NOT NULL CONSTRAINT DF_LotNameChangeHistory_Rectime DEFAULT (GETDATE()),
    ProductionLotID bigint NOT NULL,
    OldLotName      nvarchar(120) NOT NULL,
    NewLotName      nvarchar(120) NOT NULL,
    ChangedByUserID bigint NOT NULL,
    ChangedAt       datetime2(0) NOT NULL,
    ChangeReason    nvarchar(500) NOT NULL,
    CONSTRAINT FK_LotNameChangeHistory_Lot FOREIGN KEY (ProductionLotID) REFERENCES omagmes.ProductionLot(id),
    CONSTRAINT FK_LotNameChangeHistory_User FOREIGN KEY (ChangedByUserID) REFERENCES omagmes.AppUser(id),
    CONSTRAINT CK_LotNameChangeHistory_Changed CHECK (OldLotName <> NewLotName)
);
GO

CREATE INDEX IX_LotNameChangeHistory_Lot_ChangedAt
    ON omagmes.LotNameChangeHistory (ProductionLotID, ChangedAt DESC);
GO

CREATE TABLE omagmes.Mould (
    id              bigint IDENTITY(1,1) NOT NULL CONSTRAINT PK_Mould PRIMARY KEY,
    Rectime         datetime NOT NULL CONSTRAINT DF_Mould_Rectime DEFAULT (GETDATE()),
    ProductID       bigint NOT NULL,
    MouldCode       nvarchar(80) COLLATE Latin1_General_100_BIN2 NOT NULL,
    MouldName       nvarchar(160) NOT NULL,
    StatusCode      varchar(24) NOT NULL,
    RegisteredAt    datetime2(0) NOT NULL,
    RetiredAt       datetime2(0) NULL,
    Remark          nvarchar(1000) NULL,
    CONSTRAINT FK_Mould_Product FOREIGN KEY (ProductID) REFERENCES omagmes.Product(id),
    CONSTRAINT UQ_Mould_MouldCode UNIQUE (MouldCode),
    CONSTRAINT UQ_Mould_id_Product UNIQUE (id, ProductID),
    CONSTRAINT CK_Mould_Status CHECK (StatusCode IN ('ACTIVE', 'RECONDITION', 'RETIRED', 'DENIED'))
);
GO

CREATE INDEX IX_Mould_Product_Status
    ON omagmes.Mould (ProductID, StatusCode);
GO

CREATE TABLE omagmes.MouldStatusHistory (
    id              bigint IDENTITY(1,1) NOT NULL CONSTRAINT PK_MouldStatusHistory PRIMARY KEY,
    Rectime         datetime NOT NULL CONSTRAINT DF_MouldStatusHistory_Rectime DEFAULT (GETDATE()),
    MouldID         bigint NOT NULL,
    FromStatus      varchar(24) NULL,
    ToStatus        varchar(24) NOT NULL,
    ChangeType      varchar(40) NOT NULL,
    ChangedAt       datetime2(0) NOT NULL,
    ChangedByUserID bigint NOT NULL,
    Reason          nvarchar(500) NULL,
    CONSTRAINT FK_MouldStatusHistory_Mould FOREIGN KEY (MouldID) REFERENCES omagmes.Mould(id),
    CONSTRAINT FK_MouldStatusHistory_User FOREIGN KEY (ChangedByUserID) REFERENCES omagmes.AppUser(id),
    CONSTRAINT CK_MouldStatusHistory_ToStatus CHECK (ToStatus IN ('ACTIVE', 'RECONDITION', 'RETIRED', 'DENIED'))
);
GO

CREATE INDEX IX_MouldStatusHistory_Mould_ChangedAt
    ON omagmes.MouldStatusHistory (MouldID, ChangedAt DESC);
GO

CREATE TABLE omagmes.MouldReconditionCycle (
    id                      bigint IDENTITY(1,1) NOT NULL CONSTRAINT PK_MouldReconditionCycle PRIMARY KEY,
    Rectime                 datetime NOT NULL CONSTRAINT DF_MouldReconditionCycle_Rectime DEFAULT (GETDATE()),
    MouldID                 bigint NOT NULL,
    CycleNo                 int NOT NULL,
    SentAt                  datetime2(0) NOT NULL,
    SentByUserID            bigint NOT NULL,
    ApprovedReturnAt        datetime2(0) NULL,
    ApprovedReturnByUserID  bigint NULL,
    CurrentAgeAtSend        bigint NULL,
    LifetimeAgeAtSend       bigint NULL,
    ServiceReference        nvarchar(120) NULL,
    Remark                  nvarchar(1000) NULL,
    CONSTRAINT FK_MouldReconditionCycle_Mould FOREIGN KEY (MouldID) REFERENCES omagmes.Mould(id),
    CONSTRAINT FK_MouldReconditionCycle_SentBy FOREIGN KEY (SentByUserID) REFERENCES omagmes.AppUser(id),
    CONSTRAINT FK_MouldReconditionCycle_ReturnBy FOREIGN KEY (ApprovedReturnByUserID) REFERENCES omagmes.AppUser(id),
    CONSTRAINT UQ_MouldReconditionCycle_Mould_Cycle UNIQUE (MouldID, CycleNo),
    CONSTRAINT CK_MouldReconditionCycle_CycleNo CHECK (CycleNo > 0),
    CONSTRAINT CK_MouldReconditionCycle_Return CHECK (
        (ApprovedReturnAt IS NULL AND ApprovedReturnByUserID IS NULL)
        OR (ApprovedReturnAt IS NOT NULL AND ApprovedReturnByUserID IS NOT NULL AND ApprovedReturnAt >= SentAt)
    ),
    CONSTRAINT CK_MouldReconditionCycle_Ages CHECK (
        (CurrentAgeAtSend IS NULL OR CurrentAgeAtSend >= 0)
        AND (LifetimeAgeAtSend IS NULL OR LifetimeAgeAtSend >= 0)
    )
);
GO

CREATE UNIQUE INDEX UX_MouldReconditionCycle_Open
    ON omagmes.MouldReconditionCycle (MouldID)
    WHERE ApprovedReturnAt IS NULL;
GO

CREATE TABLE omagmes.MouldUseEvent (
    id              bigint IDENTITY(1,1) NOT NULL CONSTRAINT PK_MouldUseEvent PRIMARY KEY,
    Rectime         datetime NOT NULL CONSTRAINT DF_MouldUseEvent_Rectime DEFAULT (GETDATE()),
    ProductionRunID bigint NOT NULL,
    MouldID         bigint NOT NULL,
    ProductID       bigint NOT NULL,
    StartedAt       datetime2(0) NOT NULL,
    EndedAt         datetime2(0) NULL,
    MouldCycleNo    int NOT NULL,
    StartedByUserID bigint NULL,
    EndedByUserID   bigint NULL,
    CONSTRAINT FK_MouldUseEvent_RunProduct FOREIGN KEY (ProductionRunID, ProductID)
        REFERENCES omagmes.ProductionRun(id, ProductID),
    CONSTRAINT FK_MouldUseEvent_MouldProduct FOREIGN KEY (MouldID, ProductID)
        REFERENCES omagmes.Mould(id, ProductID),
    CONSTRAINT FK_MouldUseEvent_StartedBy FOREIGN KEY (StartedByUserID) REFERENCES omagmes.AppUser(id),
    CONSTRAINT FK_MouldUseEvent_EndedBy FOREIGN KEY (EndedByUserID) REFERENCES omagmes.AppUser(id),
    CONSTRAINT CK_MouldUseEvent_Times CHECK (EndedAt IS NULL OR EndedAt >= StartedAt),
    CONSTRAINT CK_MouldUseEvent_Cycle CHECK (MouldCycleNo >= 0),
    CONSTRAINT UQ_MouldUseEvent_id_Mould_Cycle UNIQUE (id, MouldID, MouldCycleNo)
);
GO

CREATE UNIQUE INDEX UX_MouldUseEvent_OpenPerRun
    ON omagmes.MouldUseEvent (ProductionRunID)
    WHERE EndedAt IS NULL;
GO

CREATE INDEX IX_MouldUseEvent_Mould_StartedAt
    ON omagmes.MouldUseEvent (MouldID, StartedAt);
GO

CREATE TABLE omagmes.PressCounterObservation (
    id                  bigint IDENTITY(1,1) NOT NULL CONSTRAINT PK_PressCounterObservation PRIMARY KEY,
    Rectime             datetime NOT NULL CONSTRAINT DF_PressCounterObservation_Rectime DEFAULT (GETDATE()),
    SourceSystem        nvarchar(80) NOT NULL,
    SourceObservationKey nvarchar(200) NOT NULL,
    TagName             nvarchar(200) NOT NULL,
    SourceTimestamp     datetime2(3) NOT NULL,
    RawValue            nvarchar(100) NULL,
    ParsedValue         bigint NULL,
    QualityCode         int NULL,
    ReceivedAt          datetime2(3) NOT NULL,
    ParseStatus         varchar(24) NOT NULL,
    CONSTRAINT UQ_PressCounterObservation_Source UNIQUE (SourceSystem, SourceObservationKey),
    CONSTRAINT CK_PressCounterObservation_Parsed CHECK (ParsedValue IS NULL OR ParsedValue >= 0),
    CONSTRAINT CK_PressCounterObservation_ParseStatus CHECK (ParseStatus IN ('VALID', 'INVALID', 'REVIEW'))
);
GO

CREATE INDEX IX_PressCounterObservation_Tag_Time
    ON omagmes.PressCounterObservation (TagName, SourceTimestamp, id);
GO

CREATE TABLE omagmes.PressCounterAccumulator (
    id                      bigint IDENTITY(1,1) NOT NULL CONSTRAINT PK_PressCounterAccumulator PRIMARY KEY,
    Rectime                 datetime NOT NULL CONSTRAINT DF_PressCounterAccumulator_Rectime DEFAULT (GETDATE()),
    CounterKey              nvarchar(120) NOT NULL,
    TagName                 nvarchar(200) NOT NULL,
    LastObservationID       bigint NULL,
    LastRawValue            bigint NULL,
    ConfirmedStrokeTotal    bigint NOT NULL CONSTRAINT DF_PressCounterAccumulator_Total DEFAULT (0),
    UncertaintyStatus       varchar(24) NOT NULL,
    LastProcessedAt         datetime2(3) NULL,
    CONSTRAINT FK_PressCounterAccumulator_LastObservation FOREIGN KEY (LastObservationID)
        REFERENCES omagmes.PressCounterObservation(id),
    CONSTRAINT UQ_PressCounterAccumulator_CounterKey UNIQUE (CounterKey),
    CONSTRAINT CK_PressCounterAccumulator_Total CHECK (ConfirmedStrokeTotal >= 0),
    CONSTRAINT CK_PressCounterAccumulator_LastRaw CHECK (LastRawValue IS NULL OR LastRawValue >= 0),
    CONSTRAINT CK_PressCounterAccumulator_Uncertainty CHECK (UncertaintyStatus IN ('CLEAR', 'GAP', 'RESET_REVIEW', 'QUALITY_REVIEW'))
);
GO

CREATE TABLE omagmes.PressCounterStep (
    id                  bigint IDENTITY(1,1) NOT NULL CONSTRAINT PK_PressCounterStep PRIMARY KEY,
    Rectime             datetime NOT NULL CONSTRAINT DF_PressCounterStep_Rectime DEFAULT (GETDATE()),
    AccumulatorID       bigint NOT NULL,
    PreviousObservationID bigint NULL,
    CurrentObservationID bigint NOT NULL,
    DecisionCode        varchar(24) NOT NULL,
    StrokeDelta         bigint NULL,
    MouldUseEventID     bigint NULL,
    MouldID             bigint NULL,
    MouldCycleNo        int NULL,
    UncertaintyCode     varchar(40) NULL,
    DecisionAt          datetime2(3) NOT NULL,
    CONSTRAINT FK_PressCounterStep_Accumulator FOREIGN KEY (AccumulatorID) REFERENCES omagmes.PressCounterAccumulator(id),
    CONSTRAINT FK_PressCounterStep_PreviousObservation FOREIGN KEY (PreviousObservationID) REFERENCES omagmes.PressCounterObservation(id),
    CONSTRAINT FK_PressCounterStep_CurrentObservation FOREIGN KEY (CurrentObservationID) REFERENCES omagmes.PressCounterObservation(id),
    CONSTRAINT FK_PressCounterStep_MouldUseCycle FOREIGN KEY (MouldUseEventID, MouldID, MouldCycleNo)
        REFERENCES omagmes.MouldUseEvent(id, MouldID, MouldCycleNo),
    CONSTRAINT UQ_PressCounterStep_Accumulator_Current UNIQUE (AccumulatorID, CurrentObservationID),
    CONSTRAINT CK_PressCounterStep_Delta CHECK (StrokeDelta IS NULL OR StrokeDelta >= 0),
    CONSTRAINT CK_PressCounterStep_Decision CHECK (DecisionCode IN ('DELTA', 'BASELINE', 'RESET_BASELINE', 'UNCERTAIN', 'REJECTED')),
    CONSTRAINT CK_PressCounterStep_Attribution CHECK (
        (MouldUseEventID IS NULL AND MouldID IS NULL AND MouldCycleNo IS NULL)
        OR (MouldUseEventID IS NOT NULL AND MouldID IS NOT NULL AND MouldCycleNo IS NOT NULL AND StrokeDelta IS NOT NULL)
    )
);
GO
```

## 3. DDL review notes and required corrections before implementation

1. **SQL Server schema creation:** `CREATE SCHEMA omagmes` is a proposed namespace only. Before any future migration, verify it does not exist and that the deployment principal has only approved rights. Do not run that statement during review.
2. **Single physical line:** the plant has one physical OMAG line. The DDL does not hardcode a one-line constraint because future plant scope and authoritative master IDs require assessment; seed/uniqueness policy must be approved.
3. **Product/Color and Lot transitions:** application transactions must close/open Runs and Lots atomically according to owner-approved events. DDL cannot enforce sequential non-overlapping Lots, ensure every Run has a Lot, or infer a Color transition. `ProductionLot.LotName` intentionally has no unique constraint.
4. **Product/Color eligibility:** `Color` is independent of Mould. A Product/Color master validity rule has not been confirmed; do not infer color identities from Product Code suffixes.
5. **Mould cycle number:** `MouldUseEvent.MouldCycleNo` is a cycle snapshot (zero before the first approved recondition return, then incremented on approved return). The application must validate it transactionally against the current Mould lifecycle. Define the authoritative cycle transition and age-query contract before implementation.
6. **Cross-entity Product validation:** `MouldUseEvent` includes ProductID and composite FKs to both `(ProductionRun.id, ProductID)` and `(Mould.id, ProductID)`, preventing a Mould/Product mismatch at database level. The application still revalidates active status and lifecycle eligibility in the same transaction.
7. **Counter source and order:** source observation key must be stable and unique across re-ingestion. The accumulator worker must lock one accumulator, process only event-time ordered inputs, and define a policy for late-arriving or corrected observations. `SourceTimestamp` timezone semantics and source-clock drift must be established before storing normalized time.
8. **Counter logic:** a valid, ordered nondecreasing pair may produce a nonnegative difference only when continuity is accepted. A decrease records a reset/restart and uses the new value as a baseline; it does not contribute a negative delta. A gap or reset ambiguity must remain explicit and may leave StrokeDelta NULL. Idempotency comes from the observation source key and unique accumulator/current-observation step key, plus a transaction that advances the accumulator and inserts the step atomically.
9. **Age projection:** derive Current Age from confirmed attributed deltas for the active recondition cycle and Lifetime Age from all confirmed attributed deltas. An approved return advances the cycle; it does not alter accumulated Press strokes. Ensure no count is added both to a persisted total and independently summed ledger entries. Snapshot columns at recondition send are for audit only, not a second source of truth.
10. **Data type/collation:** validate Product/Mould code lengths, case rules and SQL Server collation policy with the owners. Binary collation is shown as a proposed exact comparison, not a decision.
11. **Audit/authorization:** AppUser external-key source, status transitions, Mould code generation, recondition approval roles, correction/reversal workflow and retention are unresolved. Add actor/reason fields and immutable correction records where owners require them.
12. **Deferred modules:** Curing supports partial receipts; Depallet supports multiple operations. Their event fields/quantity units remain subject to event-grain approval and are intentionally not invented here. Each eventual Curing/Depallet/Dispatch record must FK to the original ProductionLot.id. Depallet GOOD/REJECT classification must not change production counters, Curing receipts, or Press OEE.
13. **ID-first compliance:** any future table added for Curing, Depallet, Product/Mould audits, counter corrections, dispatch, quality, or import staging must include the same `id bigint IDENTITY(1,1)` PK and `Rectime datetime NOT NULL DEFAULT (GETDATE())`, and all FK relationships must use IDs.

## 4. Owner review checklist

- Approve the Run-to-many-Lots model and clarify whether a Color change ends/starts a Run or only a Lot (this proposal treats it as Lot-only).
- Approve nullable ColorID versus a formal no-color master row and identify authoritative Color/Product masters.
- Confirm whether ProductCode may be reused, case policy, effective-date overlap policy and whether the shown binary collation is acceptable.
- Confirm whether Mould-to-Product assignment is permanent or may be changed under an audited re-registration procedure.
- Identify the actual DataLogger source, stable observation ID, expected cadence, timezone, quality policy, reset/restart policy, maximum trusted gap and late-arrival handling.
- Approve which deltas are safe to attribute to Mould intervals and the operational workflow for boundary samples and uncertain strokes.
- Approve Mould statuses, recondition cycle workflow, user identity source, audit retention and permitted correction/reversal controls.
- Approve deferred Curing, Depallet, output/reject, quality, OEE, dispatch and historical import scopes before adding their DDL.

**Review stop:** This document proposes structure only. No SQL was executed and no database, application, source workbook, or migration was modified. Await owner/design review before any implementation task.
