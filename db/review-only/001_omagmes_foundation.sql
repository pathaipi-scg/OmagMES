/*
REVIEW-ONLY DRAFT — DO NOT EXECUTE.
Version: 001 / 2026-11-08
Target: SQL Server database OMAG, application schema omagmes.
This draft has not been run, parsed by SQL Server, reviewed by a DBA, or approved by process owners.
No authoritative master seeds are included. Prototype code is mock-only and does not use this script.
See docs/OmagMES_Schema_Implementation_Gate.md. Target host/configuration mismatch remains unresolved.
*/
SET XACT_ABORT ON;
GO
IF DB_NAME() <> N'OMAG'
    THROW 51000, 'Review draft targets database OMAG only; execution stopped.', 1;
IF SCHEMA_ID(N'omagmes') IS NOT NULL
    THROW 51001, 'Schema omagmes already exists; review actual state before any new migration.', 1;
GO
BEGIN TRANSACTION;
GO
EXEC(N'CREATE SCHEMA omagmes AUTHORIZATION dbo;');
GO
CREATE TABLE omagmes.AppUser (
    id bigint IDENTITY(1,1) NOT NULL CONSTRAINT PK_AppUser PRIMARY KEY,
    Rectime datetime NOT NULL CONSTRAINT DF_AppUser_Rectime DEFAULT (GETDATE()),
    ExternalUserKey nvarchar(200) NOT NULL,
    DisplayName nvarchar(160) NOT NULL,
    IsActive bit NOT NULL CONSTRAINT DF_AppUser_IsActive DEFAULT (1),
    CONSTRAINT UQ_AppUser_ExternalUserKey UNIQUE (ExternalUserKey)
);
GO
CREATE TABLE omagmes.Plant (
    id bigint IDENTITY(1,1) NOT NULL CONSTRAINT PK_Plant PRIMARY KEY,
    Rectime datetime NOT NULL CONSTRAINT DF_Plant_Rectime DEFAULT (GETDATE()),
    PlantCode nvarchar(40) NOT NULL,
    PlantName nvarchar(160) NOT NULL,
    IsActive bit NOT NULL CONSTRAINT DF_Plant_IsActive DEFAULT (1),
    CONSTRAINT UQ_Plant_PlantCode UNIQUE (PlantCode)
);
GO
CREATE TABLE omagmes.ProductionLine (
    id bigint IDENTITY(1,1) NOT NULL CONSTRAINT PK_ProductionLine PRIMARY KEY,
    Rectime datetime NOT NULL CONSTRAINT DF_ProductionLine_Rectime DEFAULT (GETDATE()),
    PlantID bigint NOT NULL,
    LineCode nvarchar(40) NOT NULL,
    LineName nvarchar(160) NOT NULL,
    IsActive bit NOT NULL CONSTRAINT DF_ProductionLine_IsActive DEFAULT (1),
    CONSTRAINT FK_ProductionLine_Plant FOREIGN KEY (PlantID) REFERENCES omagmes.Plant(id),
    CONSTRAINT UQ_ProductionLine_Plant_LineCode UNIQUE (PlantID, LineCode)
);
GO
CREATE TABLE omagmes.ProductFamily (
    id bigint IDENTITY(1,1) NOT NULL CONSTRAINT PK_ProductFamily PRIMARY KEY,
    Rectime datetime NOT NULL CONSTRAINT DF_ProductFamily_Rectime DEFAULT (GETDATE()),
    FamilyCode nvarchar(40) NOT NULL,
    FamilyName nvarchar(120) NOT NULL,
    IsActive bit NOT NULL CONSTRAINT DF_ProductFamily_IsActive DEFAULT (1),
    CONSTRAINT UQ_ProductFamily_FamilyCode UNIQUE (FamilyCode)
);
GO
CREATE TABLE omagmes.Product (
    id bigint IDENTITY(1,1) NOT NULL CONSTRAINT PK_Product PRIMARY KEY,
    Rectime datetime NOT NULL CONSTRAINT DF_Product_Rectime DEFAULT (GETDATE()),
    ProductFamilyID bigint NOT NULL,
    ProductName nvarchar(200) NOT NULL,
    IsActive bit NOT NULL CONSTRAINT DF_Product_IsActive DEFAULT (1),
    CONSTRAINT FK_Product_ProductFamily FOREIGN KEY (ProductFamilyID) REFERENCES omagmes.ProductFamily(id),
    CONSTRAINT UQ_Product_id_Family UNIQUE (id, ProductFamilyID)
);
GO
CREATE TABLE omagmes.ProductCodeAssignment (
    id bigint IDENTITY(1,1) NOT NULL CONSTRAINT PK_ProductCodeAssignment PRIMARY KEY,
    Rectime datetime NOT NULL CONSTRAINT DF_ProductCodeAssignment_Rectime DEFAULT (GETDATE()),
    ProductID bigint NOT NULL,
    ProductCode nvarchar(100) COLLATE Latin1_General_100_BIN2 NOT NULL,
    ValidFrom datetime2(0) NOT NULL,
    ValidTo datetime2(0) NULL,
    ChangeReason nvarchar(500) NULL,
    CONSTRAINT FK_ProductCodeAssignment_Product FOREIGN KEY (ProductID) REFERENCES omagmes.Product(id),
    CONSTRAINT CK_ProductCodeAssignment_Validity CHECK (ValidTo IS NULL OR ValidTo > ValidFrom),
    CONSTRAINT UQ_ProductCodeAssignment_id_Product UNIQUE (id, ProductID)
);
GO
CREATE UNIQUE INDEX UX_ProductCodeAssignment_CurrentCode
    ON omagmes.ProductCodeAssignment(ProductCode)
    WHERE ValidTo IS NULL;
GO
CREATE TABLE omagmes.Color (
    id bigint IDENTITY(1,1) NOT NULL CONSTRAINT PK_Color PRIMARY KEY,
    Rectime datetime NOT NULL CONSTRAINT DF_Color_Rectime DEFAULT (GETDATE()),
    ColorCode nvarchar(60) COLLATE Latin1_General_100_BIN2 NOT NULL,
    ColorName nvarchar(160) NOT NULL,
    IsActive bit NOT NULL CONSTRAINT DF_Color_IsActive DEFAULT (1),
    CONSTRAINT UQ_Color_ColorCode UNIQUE (ColorCode)
);
GO
CREATE TABLE omagmes.ProductProductionStandard (
    id bigint IDENTITY(1,1) NOT NULL CONSTRAINT PK_ProductProductionStandard PRIMARY KEY,
    Rectime datetime NOT NULL CONSTRAINT DF_ProductProductionStandard_Rectime DEFAULT (GETDATE()),
    ProductID bigint NOT NULL,
    RevisionNo int NOT NULL,
    StandardPiecesPerDrop int NULL,
    StandardCycleTimeSec decimal(12,4) NULL,
    EffectiveFrom datetime2(0) NOT NULL,
    EffectiveTo datetime2(0) NULL,
    StatusCode varchar(16) NOT NULL,
    SourceReference nvarchar(500) NULL,
    ChangeReason nvarchar(500) NULL,
    ApprovedByUserID bigint NULL,
    ApprovedAt datetime2(0) NULL,
    CONSTRAINT FK_ProductProductionStandard_Product FOREIGN KEY (ProductID) REFERENCES omagmes.Product(id),
    CONSTRAINT FK_ProductProductionStandard_Approver FOREIGN KEY (ApprovedByUserID) REFERENCES omagmes.AppUser(id),
    CONSTRAINT UQ_ProductProductionStandard_Product_Revision UNIQUE (ProductID, RevisionNo),
    CONSTRAINT UQ_ProductProductionStandard_id_Product UNIQUE (id, ProductID),
    CONSTRAINT CK_ProductProductionStandard_Status CHECK (StatusCode IN ('DRAFT', 'APPROVED', 'RETIRED')),
    CONSTRAINT CK_ProductProductionStandard_Effective CHECK (EffectiveTo IS NULL OR EffectiveTo > EffectiveFrom),
    CONSTRAINT CK_ProductProductionStandard_ApprovedValues CHECK (
        StatusCode <> 'APPROVED' OR
        (StandardPiecesPerDrop IS NOT NULL AND StandardPiecesPerDrop > 0
         AND StandardCycleTimeSec IS NOT NULL AND StandardCycleTimeSec > 0
         AND ApprovedByUserID IS NOT NULL AND ApprovedAt IS NOT NULL)
    )
);
GO
CREATE TABLE omagmes.ProductionRun (
    id bigint IDENTITY(1,1) NOT NULL CONSTRAINT PK_ProductionRun PRIMARY KEY,
    Rectime datetime NOT NULL CONSTRAINT DF_ProductionRun_Rectime DEFAULT (GETDATE()),
    ProductionLineID bigint NOT NULL,
    ProductID bigint NOT NULL,
    StartedAt datetimeoffset(0) NOT NULL,
    EndedAt datetimeoffset(0) NULL,
    StatusCode varchar(16) NOT NULL,
    CreatedByUserID bigint NULL,
    CONSTRAINT FK_ProductionRun_Line FOREIGN KEY (ProductionLineID) REFERENCES omagmes.ProductionLine(id),
    CONSTRAINT FK_ProductionRun_Product FOREIGN KEY (ProductID) REFERENCES omagmes.Product(id),
    CONSTRAINT FK_ProductionRun_CreatedBy FOREIGN KEY (CreatedByUserID) REFERENCES omagmes.AppUser(id),
    CONSTRAINT UQ_ProductionRun_id_Product UNIQUE (id, ProductID),
    CONSTRAINT CK_ProductionRun_Times CHECK (EndedAt IS NULL OR EndedAt >= StartedAt),
    CONSTRAINT CK_ProductionRun_Status CHECK (StatusCode IN ('OPEN', 'CLOSED', 'VOID'))
);
GO
CREATE TABLE omagmes.ProductionLot (
    id bigint IDENTITY(1,1) NOT NULL CONSTRAINT PK_ProductionLot PRIMARY KEY,
    Rectime datetime NOT NULL CONSTRAINT DF_ProductionLot_Rectime DEFAULT (GETDATE()),
    ProductionRunID bigint NOT NULL,
    ProductID bigint NOT NULL,
    ColorID bigint NULL,
    LotName nvarchar(120) NOT NULL,
    LotStartedAt datetimeoffset(0) NOT NULL,
    LotEndedAt datetimeoffset(0) NULL,
    ProductProductionStandardID bigint NULL,
    StandardPiecesPerDropSnapshot int NULL,
    StandardCycleTimeSecSnapshot decimal(12,4) NULL,
    CreatedByUserID bigint NULL,
    CONSTRAINT FK_ProductionLot_RunProduct FOREIGN KEY (ProductionRunID, ProductID)
        REFERENCES omagmes.ProductionRun(id, ProductID),
    CONSTRAINT FK_ProductionLot_Color FOREIGN KEY (ColorID) REFERENCES omagmes.Color(id),
    CONSTRAINT FK_ProductionLot_StandardProduct FOREIGN KEY (ProductProductionStandardID, ProductID)
        REFERENCES omagmes.ProductProductionStandard(id, ProductID),
    CONSTRAINT FK_ProductionLot_CreatedBy FOREIGN KEY (CreatedByUserID) REFERENCES omagmes.AppUser(id),
    CONSTRAINT UQ_ProductionLot_id_Product UNIQUE (id, ProductID),
    CONSTRAINT CK_ProductionLot_Times CHECK (LotEndedAt IS NULL OR LotEndedAt >= LotStartedAt),
    CONSTRAINT CK_ProductionLot_StandardSnapshot CHECK (
        (ProductProductionStandardID IS NULL AND StandardPiecesPerDropSnapshot IS NULL AND StandardCycleTimeSecSnapshot IS NULL)
        OR (ProductProductionStandardID IS NOT NULL
            AND StandardPiecesPerDropSnapshot IS NOT NULL AND StandardPiecesPerDropSnapshot > 0
            AND StandardCycleTimeSecSnapshot IS NOT NULL AND StandardCycleTimeSecSnapshot > 0)
    )
);
GO
CREATE INDEX IX_ProductionLot_Product_StartedAt ON omagmes.ProductionLot(ProductID, LotStartedAt DESC);
CREATE INDEX IX_ProductionLot_LotName ON omagmes.ProductionLot(LotName);
GO
CREATE TABLE omagmes.LotNameChangeHistory (
    id bigint IDENTITY(1,1) NOT NULL CONSTRAINT PK_LotNameChangeHistory PRIMARY KEY,
    Rectime datetime NOT NULL CONSTRAINT DF_LotNameChangeHistory_Rectime DEFAULT (GETDATE()),
    ProductionLotID bigint NOT NULL,
    OldLotName nvarchar(120) NOT NULL,
    NewLotName nvarchar(120) NOT NULL,
    ChangedByUserID bigint NOT NULL,
    ChangedAt datetimeoffset(0) NOT NULL,
    ChangeReason nvarchar(500) NOT NULL,
    CONSTRAINT FK_LotNameChangeHistory_Lot FOREIGN KEY (ProductionLotID) REFERENCES omagmes.ProductionLot(id),
    CONSTRAINT FK_LotNameChangeHistory_User FOREIGN KEY (ChangedByUserID) REFERENCES omagmes.AppUser(id),
    CONSTRAINT CK_LotNameChangeHistory_Changed CHECK (OldLotName <> NewLotName)
);
GO
CREATE INDEX IX_LotNameChangeHistory_Lot_ChangedAt ON omagmes.LotNameChangeHistory(ProductionLotID, ChangedAt DESC);
GO
CREATE TABLE omagmes.ProductionEntry (
    id bigint IDENTITY(1,1) NOT NULL CONSTRAINT PK_ProductionEntry PRIMARY KEY,
    Rectime datetime NOT NULL CONSTRAINT DF_ProductionEntry_Rectime DEFAULT (GETDATE()),
    ProductionLotID bigint NOT NULL,
    RecordedAt datetimeoffset(0) NOT NULL,
    ActualDrops bigint NOT NULL,
    WetGoodPieces bigint NOT NULL,
    SourceCode varchar(20) NOT NULL,
    OperatorNote nvarchar(1000) NULL,
    EnteredByUserID bigint NULL,
    CONSTRAINT FK_ProductionEntry_Lot FOREIGN KEY (ProductionLotID) REFERENCES omagmes.ProductionLot(id),
    CONSTRAINT FK_ProductionEntry_User FOREIGN KEY (EnteredByUserID) REFERENCES omagmes.AppUser(id),
    CONSTRAINT CK_ProductionEntry_Quantities CHECK (ActualDrops >= 0 AND WetGoodPieces >= 0),
    CONSTRAINT CK_ProductionEntry_Source CHECK (SourceCode IN ('MANUAL', 'AUTOCAL_REVIEWED'))
);
GO
CREATE TABLE omagmes.ProductionEntryCorrection (
    id bigint IDENTITY(1,1) NOT NULL CONSTRAINT PK_ProductionEntryCorrection PRIMARY KEY,
    Rectime datetime NOT NULL CONSTRAINT DF_ProductionEntryCorrection_Rectime DEFAULT (GETDATE()),
    ProductionEntryID bigint NOT NULL,
    OldActualDrops bigint NOT NULL,
    NewActualDrops bigint NOT NULL,
    OldWetGoodPieces bigint NOT NULL,
    NewWetGoodPieces bigint NOT NULL,
    CorrectedAt datetimeoffset(0) NOT NULL,
    CorrectedByUserID bigint NOT NULL,
    CorrectionReason nvarchar(500) NOT NULL,
    CONSTRAINT FK_ProductionEntryCorrection_Entry FOREIGN KEY (ProductionEntryID) REFERENCES omagmes.ProductionEntry(id),
    CONSTRAINT FK_ProductionEntryCorrection_User FOREIGN KEY (CorrectedByUserID) REFERENCES omagmes.AppUser(id),
    CONSTRAINT CK_ProductionEntryCorrection_Values CHECK (
        OldActualDrops >= 0 AND NewActualDrops >= 0 AND OldWetGoodPieces >= 0 AND NewWetGoodPieces >= 0
    )
);
GO
CREATE TABLE omagmes.WetRejectReason (
    id bigint IDENTITY(1,1) NOT NULL CONSTRAINT PK_WetRejectReason PRIMARY KEY,
    Rectime datetime NOT NULL CONSTRAINT DF_WetRejectReason_Rectime DEFAULT (GETDATE()),
    ReasonCode nvarchar(60) COLLATE Latin1_General_100_BIN2 NOT NULL,
    ReasonName nvarchar(160) NOT NULL,
    CounterTag nvarchar(120) COLLATE Latin1_General_100_BIN2 NULL,
    IsActive bit NOT NULL CONSTRAINT DF_WetRejectReason_IsActive DEFAULT (1),
    CONSTRAINT UQ_WetRejectReason_ReasonCode UNIQUE (ReasonCode),
    CONSTRAINT UQ_WetRejectReason_CounterTag UNIQUE (CounterTag)
);
GO
CREATE TABLE omagmes.WetRejectEntry (
    id bigint IDENTITY(1,1) NOT NULL CONSTRAINT PK_WetRejectEntry PRIMARY KEY,
    Rectime datetime NOT NULL CONSTRAINT DF_WetRejectEntry_Rectime DEFAULT (GETDATE()),
    ProductionLotID bigint NOT NULL,
    WetRejectReasonID bigint NOT NULL,
    Quantity bigint NOT NULL,
    RecordedAt datetimeoffset(0) NOT NULL,
    SourceCode varchar(20) NOT NULL,
    OperatorNote nvarchar(1000) NULL,
    EnteredByUserID bigint NULL,
    CONSTRAINT FK_WetRejectEntry_Lot FOREIGN KEY (ProductionLotID) REFERENCES omagmes.ProductionLot(id),
    CONSTRAINT FK_WetRejectEntry_Reason FOREIGN KEY (WetRejectReasonID) REFERENCES omagmes.WetRejectReason(id),
    CONSTRAINT FK_WetRejectEntry_User FOREIGN KEY (EnteredByUserID) REFERENCES omagmes.AppUser(id),
    CONSTRAINT CK_WetRejectEntry_Quantity CHECK (Quantity >= 0),
    CONSTRAINT CK_WetRejectEntry_Source CHECK (SourceCode IN ('MANUAL', 'AUTOCAL_REVIEWED'))
);
GO
CREATE TABLE omagmes.WetRunEvent (
    id bigint IDENTITY(1,1) NOT NULL CONSTRAINT PK_WetRunEvent PRIMARY KEY,
    Rectime datetime NOT NULL CONSTRAINT DF_WetRunEvent_Rectime DEFAULT (GETDATE()),
    ProductionRunID bigint NULL,
    CategoryCode varchar(20) NOT NULL,
    StartedAt datetimeoffset(0) NOT NULL,
    EndedAt datetimeoffset(0) NULL,
    OperatorNote nvarchar(1000) NULL,
    EnteredByUserID bigint NOT NULL,
    CONSTRAINT FK_WetRunEvent_Run FOREIGN KEY (ProductionRunID) REFERENCES omagmes.ProductionRun(id),
    CONSTRAINT FK_WetRunEvent_User FOREIGN KEY (EnteredByUserID) REFERENCES omagmes.AppUser(id),
    CONSTRAINT CK_WetRunEvent_Category CHECK (CategoryCode IN ('RUNNING', 'SETUP', 'CHANGEOVER', 'IDLE', 'CLEANING', 'BREAKDOWN', 'SMDT')),
    CONSTRAINT CK_WetRunEvent_Times CHECK (EndedAt IS NULL OR EndedAt >= StartedAt)
);
GO
CREATE TABLE omagmes.CuringRecord (
    id bigint IDENTITY(1,1) NOT NULL CONSTRAINT PK_CuringRecord PRIMARY KEY,
    Rectime datetime NOT NULL CONSTRAINT DF_CuringRecord_Rectime DEFAULT (GETDATE()),
    ProductionLotID bigint NOT NULL,
    EventAt datetimeoffset(0) NULL,
    SourceReference nvarchar(200) NULL,
    Remark nvarchar(1000) NULL,
    CONSTRAINT FK_CuringRecord_Lot FOREIGN KEY (ProductionLotID) REFERENCES omagmes.ProductionLot(id)
);
GO
CREATE TABLE omagmes.DepalletEvent (
    id bigint IDENTITY(1,1) NOT NULL CONSTRAINT PK_DepalletEvent PRIMARY KEY,
    Rectime datetime NOT NULL CONSTRAINT DF_DepalletEvent_Rectime DEFAULT (GETDATE()),
    ProductionLotID bigint NOT NULL,
    EventAt datetimeoffset(0) NULL,
    SourceReference nvarchar(200) NULL,
    Remark nvarchar(1000) NULL,
    CONSTRAINT FK_DepalletEvent_Lot FOREIGN KEY (ProductionLotID) REFERENCES omagmes.ProductionLot(id)
);
GO
CREATE TABLE omagmes.Mould (
    id bigint IDENTITY(1,1) NOT NULL CONSTRAINT PK_Mould PRIMARY KEY,
    Rectime datetime NOT NULL CONSTRAINT DF_Mould_Rectime DEFAULT (GETDATE()),
    ProductID bigint NOT NULL,
    MouldCode nvarchar(80) COLLATE Latin1_General_100_BIN2 NOT NULL,
    MouldName nvarchar(160) NOT NULL,
    StatusCode varchar(20) NOT NULL,
    CONSTRAINT FK_Mould_Product FOREIGN KEY (ProductID) REFERENCES omagmes.Product(id),
    CONSTRAINT UQ_Mould_MouldCode UNIQUE (MouldCode),
    CONSTRAINT UQ_Mould_id_Product UNIQUE (id, ProductID),
    CONSTRAINT CK_Mould_Status CHECK (StatusCode IN ('ACTIVE', 'RECONDITION', 'RETIRED'))
);
GO
CREATE TABLE omagmes.MouldStatusHistory (
    id bigint IDENTITY(1,1) NOT NULL CONSTRAINT PK_MouldStatusHistory PRIMARY KEY,
    Rectime datetime NOT NULL CONSTRAINT DF_MouldStatusHistory_Rectime DEFAULT (GETDATE()),
    MouldID bigint NOT NULL,
    FromStatus varchar(20) NULL,
    ToStatus varchar(20) NOT NULL,
    ChangeType varchar(40) NOT NULL,
    ChangedAt datetimeoffset(0) NOT NULL,
    ChangedByUserID bigint NOT NULL,
    Reason nvarchar(500) NOT NULL,
    CONSTRAINT FK_MouldStatusHistory_Mould FOREIGN KEY (MouldID) REFERENCES omagmes.Mould(id),
    CONSTRAINT FK_MouldStatusHistory_User FOREIGN KEY (ChangedByUserID) REFERENCES omagmes.AppUser(id),
    CONSTRAINT CK_MouldStatusHistory_ToStatus CHECK (ToStatus IN ('ACTIVE', 'RECONDITION', 'RETIRED'))
);
GO
CREATE TABLE omagmes.MouldReconditionCycle (
    id bigint IDENTITY(1,1) NOT NULL CONSTRAINT PK_MouldReconditionCycle PRIMARY KEY,
    Rectime datetime NOT NULL CONSTRAINT DF_MouldReconditionCycle_Rectime DEFAULT (GETDATE()),
    MouldID bigint NOT NULL,
    CycleNo int NOT NULL,
    SentAt datetimeoffset(0) NOT NULL,
    SentByUserID bigint NOT NULL,
    ApprovedReturnAt datetimeoffset(0) NULL,
    ApprovedReturnByUserID bigint NULL,
    CurrentAgeAtSend bigint NULL,
    LifetimeAgeAtSend bigint NULL,
    ServiceReference nvarchar(120) NULL,
    Reason nvarchar(1000) NULL,
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
    ON omagmes.MouldReconditionCycle(MouldID)
    WHERE ApprovedReturnAt IS NULL;
GO
CREATE TABLE omagmes.MouldUseEvent (
    id bigint IDENTITY(1,1) NOT NULL CONSTRAINT PK_MouldUseEvent PRIMARY KEY,
    Rectime datetime NOT NULL CONSTRAINT DF_MouldUseEvent_Rectime DEFAULT (GETDATE()),
    ProductionRunID bigint NOT NULL,
    MouldID bigint NOT NULL,
    ProductID bigint NOT NULL,
    StartedAt datetimeoffset(0) NOT NULL,
    EndedAt datetimeoffset(0) NULL,
    CONSTRAINT FK_MouldUseEvent_RunProduct FOREIGN KEY (ProductionRunID, ProductID)
        REFERENCES omagmes.ProductionRun(id, ProductID),
    CONSTRAINT FK_MouldUseEvent_MouldProduct FOREIGN KEY (MouldID, ProductID)
        REFERENCES omagmes.Mould(id, ProductID),
    CONSTRAINT CK_MouldUseEvent_Times CHECK (EndedAt IS NULL OR EndedAt >= StartedAt)
);
GO
CREATE TABLE omagmes.PressCounterObservation (
    id bigint IDENTITY(1,1) NOT NULL CONSTRAINT PK_PressCounterObservation PRIMARY KEY,
    Rectime datetime NOT NULL CONSTRAINT DF_PressCounterObservation_Rectime DEFAULT (GETDATE()),
    SourceSystem nvarchar(80) NOT NULL,
    SourceObservationKey nvarchar(200) NOT NULL,
    TagName nvarchar(200) NOT NULL,
    SourceTimestampRaw nvarchar(80) NOT NULL,
    SourceTimestamp datetimeoffset(3) NULL,
    RawValue nvarchar(100) NULL,
    ParsedValue bigint NULL,
    QualityCode int NULL,
    ReceivedAt datetimeoffset(3) NOT NULL,
    ParseStatus varchar(16) NOT NULL,
    CONSTRAINT UQ_PressCounterObservation_Source UNIQUE (SourceSystem, SourceObservationKey),
    CONSTRAINT CK_PressCounterObservation_Value CHECK (ParsedValue IS NULL OR ParsedValue >= 0),
    CONSTRAINT CK_PressCounterObservation_Status CHECK (ParseStatus IN ('VALID', 'INVALID', 'REVIEW'))
);
GO
CREATE TABLE omagmes.PressCounterResetBoundary (
    id bigint IDENTITY(1,1) NOT NULL CONSTRAINT PK_PressCounterResetBoundary PRIMARY KEY,
    Rectime datetime NOT NULL CONSTRAINT DF_PressCounterResetBoundary_Rectime DEFAULT (GETDATE()),
    CounterKey nvarchar(120) NOT NULL,
    ProductionDate date NOT NULL,
    BoundaryAt datetimeoffset(0) NOT NULL,
    BoundaryType varchar(24) NOT NULL,
    EvidenceStatus varchar(32) NOT NULL,
    CONSTRAINT UQ_PressCounterResetBoundary_Counter_Date UNIQUE (CounterKey, ProductionDate),
    CONSTRAINT CK_PressCounterResetBoundary_Type CHECK (BoundaryType = 'DAILY_0700_BANGKOK'),
    CONSTRAINT CK_PressCounterResetBoundary_Evidence CHECK (EvidenceStatus IN ('RULE_CONFIRMED', 'OBSERVED', 'MISSING_OBSERVATION', 'REVIEW'))
);
GO
CREATE TABLE omagmes.WetCameraObservation (
    id bigint IDENTITY(1,1) NOT NULL CONSTRAINT PK_WetCameraObservation PRIMARY KEY,
    Rectime datetime NOT NULL CONSTRAINT DF_WetCameraObservation_Rectime DEFAULT (GETDATE()),
    SourceSystem nvarchar(80) NOT NULL,
    SourceObservationKey nvarchar(200) NOT NULL,
    SourceTimestampRaw nvarchar(80) NOT NULL,
    SourceTimestamp datetimeoffset(3) NULL,
    LineCode varchar(12) NOT NULL,
    ValueCount bigint NULL,
    QualityCode int NULL,
    ReceivedAt datetimeoffset(3) NOT NULL,
    ParseStatus varchar(16) NOT NULL,
    CONSTRAINT UQ_WetCameraObservation_Source UNIQUE (SourceSystem, SourceObservationKey),
    CONSTRAINT CK_WetCameraObservation_Line CHECK (LineCode = 'wet'),
    CONSTRAINT CK_WetCameraObservation_Count CHECK (ValueCount IS NULL OR ValueCount >= 0),
    CONSTRAINT CK_WetCameraObservation_Status CHECK (ParseStatus IN ('VALID', 'INVALID', 'REVIEW'))
);
GO
CREATE INDEX IX_WetCameraObservation_Line_Time ON omagmes.WetCameraObservation(LineCode, SourceTimestamp, id);
GO
CREATE INDEX IX_PressCounterObservation_Tag_Time ON omagmes.PressCounterObservation(TagName, SourceTimestamp, id);
GO
CREATE TABLE omagmes.PressCounterAccumulator (
    id bigint IDENTITY(1,1) NOT NULL CONSTRAINT PK_PressCounterAccumulator PRIMARY KEY,
    Rectime datetime NOT NULL CONSTRAINT DF_PressCounterAccumulator_Rectime DEFAULT (GETDATE()),
    CounterKey nvarchar(120) NOT NULL,
    LastObservationID bigint NULL,
    LastRawValue bigint NULL,
    ConfirmedStrokeTotal bigint NOT NULL CONSTRAINT DF_PressCounterAccumulator_Total DEFAULT (0),
    UncertaintyStatus varchar(20) NOT NULL,
    LastProcessedAt datetimeoffset(3) NULL,
    CONSTRAINT FK_PressCounterAccumulator_LastObservation FOREIGN KEY (LastObservationID) REFERENCES omagmes.PressCounterObservation(id),
    CONSTRAINT UQ_PressCounterAccumulator_CounterKey UNIQUE (CounterKey),
    CONSTRAINT CK_PressCounterAccumulator_Total CHECK (ConfirmedStrokeTotal >= 0),
    CONSTRAINT CK_PressCounterAccumulator_LastRaw CHECK (LastRawValue IS NULL OR LastRawValue >= 0),
    CONSTRAINT CK_PressCounterAccumulator_Uncertainty CHECK (UncertaintyStatus IN ('CLEAR', 'GAP', 'RESET_REVIEW', 'QUALITY_REVIEW'))
);
GO
CREATE TABLE omagmes.PressCounterStep (
    id bigint IDENTITY(1,1) NOT NULL CONSTRAINT PK_PressCounterStep PRIMARY KEY,
    Rectime datetime NOT NULL CONSTRAINT DF_PressCounterStep_Rectime DEFAULT (GETDATE()),
    AccumulatorID bigint NOT NULL,
    PreviousObservationID bigint NULL,
    CurrentObservationID bigint NOT NULL,
    DecisionCode varchar(20) NOT NULL,
    StrokeDelta bigint NULL,
    UncertaintyCode varchar(40) NULL,
    DecisionAt datetimeoffset(3) NOT NULL,
    CONSTRAINT FK_PressCounterStep_Accumulator FOREIGN KEY (AccumulatorID) REFERENCES omagmes.PressCounterAccumulator(id),
    CONSTRAINT FK_PressCounterStep_PreviousObservation FOREIGN KEY (PreviousObservationID) REFERENCES omagmes.PressCounterObservation(id),
    CONSTRAINT FK_PressCounterStep_CurrentObservation FOREIGN KEY (CurrentObservationID) REFERENCES omagmes.PressCounterObservation(id),
    CONSTRAINT UQ_PressCounterStep_Accumulator_Current UNIQUE (AccumulatorID, CurrentObservationID),
    CONSTRAINT CK_PressCounterStep_Delta CHECK (StrokeDelta IS NULL OR StrokeDelta >= 0),
    CONSTRAINT CK_PressCounterStep_Decision CHECK (DecisionCode IN ('DELTA', 'BASELINE', 'RESET_BASELINE', 'UNCERTAIN', 'REJECTED'))
);
GO
COMMIT TRANSACTION;
GO
