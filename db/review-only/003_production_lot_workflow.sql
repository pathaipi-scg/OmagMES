/*
REVIEW-ONLY DRAFT — DO NOT EXECUTE WITHOUT SEPARATE DBA/OWNER MIGRATION AUTHORIZATION.
Version 003 / 2026-11-17. Applies to an existing OMAG.omagmes schema containing
ProductionDayCutoffVersion, Shift, ShiftScheduleVersion, and ShiftScheduleShift.
Does not alter existing objects, configuration history, or any OMAG.dbo legacy object.
CANONICAL MODEL DECISION (2026-11-17): per factory-owner direction and confirmed
requirements, this migration is the canonical Product/ProductionRun/ProductionLot
schema. The incompatible, unexecuted 001_omagmes_foundation.sql is superseded and
must not be applied. No historical OmagMES production data migration is needed.
This draft's catalog preflight rejects existing collisions; any collision still
requires inspection and stop, never overwrite or drop.
No product/color seeds or test Lots are included. Product/Color master data, operator
identity/authentication, shift-code compatibility, and factory machine-code mapping
must be reviewed before use. This draft stores the confirmed SCG Lot format,
transaction-scoped sequence state, and per-production-entry occurrence timestamp/date/
shift context. Same Product + same Color continues the original immutable Lot across
shifts and Production Dates; only a Product or Color change creates a Lot. A counter
reset is evidence only and does not by itself create a Lot.
Sequence scope is Production Date + Shift Code; sequence 99 is exhausted and cannot
wrap or reuse an earlier value. Only the affected numbering scope is blocked.
*/
SET NOCOUNT ON;
SET XACT_ABORT ON;
IF DB_NAME() <> N'OMAG'
    THROW 53000, 'OmagMES migration 003 only applies to database OMAG.', 1;
IF SCHEMA_ID(N'omagmes') IS NULL
    THROW 53001, 'The existing omagmes schema is required; migration 003 will not create it.', 1;
IF OBJECT_ID(N'omagmes.ProductionDayCutoffVersion', N'U') IS NULL
   OR OBJECT_ID(N'omagmes.Shift', N'U') IS NULL
   OR OBJECT_ID(N'omagmes.ShiftScheduleVersion', N'U') IS NULL
   OR OBJECT_ID(N'omagmes.ShiftScheduleShift', N'U') IS NULL
    THROW 53002, 'Expected deployed OmagMES configuration tables are missing; inspect the target before migration.', 1;
IF OBJECT_ID(N'omagmes.Product', N'U') IS NOT NULL
   OR OBJECT_ID(N'omagmes.ProductionRun', N'U') IS NOT NULL
   OR OBJECT_ID(N'omagmes.ProductionLot', N'U') IS NOT NULL
    THROW 53003, 'A production identity object already exists; inspect and reconcile it instead of rerunning migration 003.', 1;
IF EXISTS (
    SELECT 1
    FROM (VALUES
        (N'Product'), (N'ProductStandardRevision'), (N'ProductionRun'), (N'ProductionLot'),
        (N'AutoLotResetReview'), (N'LotNumberSequence'), (N'ProductionLotNameHistory'),
        (N'ProductionEntry'), (N'ProductionEntryCorrection'), (N'CuringInputEntry'),
        (N'DepalletEvent'), (N'Dispatch'), (N'DispatchLine')
    ) AS expected(ObjectName)
    JOIN sys.objects AS existing
      ON existing.schema_id = SCHEMA_ID(N'omagmes')
     AND existing.name = expected.ObjectName
)
    THROW 53003, 'A Migration 003 object name is already in use; inspect and reconcile it instead of rerunning migration 003.', 1;
IF EXISTS (
    SELECT 1
    FROM (VALUES
        (N'ProductionDayCutoffVersion', N'id', N'bigint'),
        (N'ProductionDayCutoffVersion', N'EffectiveFromProductionDate', N'date'),
        (N'ProductionDayCutoffVersion', N'CutoffTime', N'time'),
        (N'Shift', N'id', N'bigint'),
        (N'ShiftScheduleVersion', N'id', N'bigint'),
        (N'ShiftScheduleShift', N'ShiftScheduleVersionID', N'bigint'),
        (N'ShiftScheduleShift', N'ShiftID', N'bigint'),
        (N'ShiftScheduleShift', N'ShiftCode', N'nvarchar')
    ) AS expected(TableName, ColumnName, TypeName)
    LEFT JOIN sys.tables AS t
      ON t.schema_id = SCHEMA_ID(N'omagmes') AND t.name = expected.TableName
    LEFT JOIN sys.columns AS c
      ON c.object_id = t.object_id AND c.name = expected.ColumnName
    LEFT JOIN sys.types AS ty ON ty.user_type_id = c.user_type_id
    WHERE c.column_id IS NULL OR ty.name <> expected.TypeName
)
    THROW 53004, 'Migration 002 prerequisite columns or types do not match Migration 003 expectations.', 1;
IF EXISTS (
    SELECT 1
    FROM (VALUES
        (N'ProductionDayCutoffVersion'), (N'Shift'), (N'ShiftScheduleVersion')
    ) AS expected(TableName)
    JOIN sys.tables AS t ON t.schema_id = SCHEMA_ID(N'omagmes') AND t.name = expected.TableName
    JOIN sys.columns AS c ON c.object_id = t.object_id AND c.name = N'id'
    WHERE c.is_identity = 0 OR NOT EXISTS (
        SELECT 1
        FROM sys.indexes AS i
        JOIN sys.index_columns AS ic ON ic.object_id = i.object_id AND ic.index_id = i.index_id
        WHERE i.object_id = t.object_id AND i.is_primary_key = 1
          AND ic.column_id = c.column_id AND ic.key_ordinal = 1
    )
)
    THROW 53005, 'Migration 002 prerequisite id columns must be IDENTITY primary keys.', 1;
IF NOT EXISTS (
    SELECT 1
    FROM sys.key_constraints AS kc
    JOIN sys.index_columns AS first_key ON first_key.object_id = kc.parent_object_id AND first_key.index_id = kc.unique_index_id AND first_key.key_ordinal = 1
    JOIN sys.columns AS first_column ON first_column.object_id = first_key.object_id AND first_column.column_id = first_key.column_id
    JOIN sys.index_columns AS second_key ON second_key.object_id = kc.parent_object_id AND second_key.index_id = kc.unique_index_id AND second_key.key_ordinal = 2
    JOIN sys.columns AS second_column ON second_column.object_id = second_key.object_id AND second_column.column_id = second_key.column_id
    WHERE kc.parent_object_id = OBJECT_ID(N'omagmes.ShiftScheduleShift', N'U')
      AND kc.type = N'UQ'
      AND first_column.name = N'ShiftScheduleVersionID'
      AND second_column.name = N'ShiftID'
      AND NOT EXISTS (
          SELECT 1 FROM sys.index_columns AS extra_key
          WHERE extra_key.object_id = kc.parent_object_id
            AND extra_key.index_id = kc.unique_index_id
            AND extra_key.key_ordinal > 2
      )
)
    THROW 53006, 'Migration 002 ShiftScheduleShift must have a unique (ShiftScheduleVersionID, ShiftID) key.', 1;
BEGIN TRANSACTION;

CREATE TABLE omagmes.Product (
    id bigint IDENTITY(1,1) NOT NULL CONSTRAINT PK_Product PRIMARY KEY,
    Rectime datetime NOT NULL CONSTRAINT DF_Product_Rectime DEFAULT (GETDATE()),
    ProductCode nvarchar(100) COLLATE Latin1_General_100_BIN2 NOT NULL,
    ProductName nvarchar(200) NOT NULL,
    ProductFamily nvarchar(100) NULL,
    IsActive bit NOT NULL CONSTRAINT DF_Product_IsActive DEFAULT (1),
    CONSTRAINT UQ_Product_ProductCode UNIQUE (ProductCode),
    CONSTRAINT CK_Product_ProductCode CHECK (LEN(LTRIM(RTRIM(ProductCode))) > 0),
    CONSTRAINT CK_Product_ProductName CHECK (LEN(LTRIM(RTRIM(ProductName))) > 0)
);

CREATE TABLE omagmes.ProductStandardRevision (
    id bigint IDENTITY(1,1) NOT NULL CONSTRAINT PK_ProductStandardRevision PRIMARY KEY,
    Rectime datetime NOT NULL CONSTRAINT DF_ProductStandardRevision_Rectime DEFAULT (GETDATE()),
    ProductID bigint NOT NULL,
    RevisionNo int NOT NULL,
    StandardPiecesPerDrop int NOT NULL,
    StandardCycleTimeSec decimal(12,4) NOT NULL,
    EffectiveFrom datetimeoffset(0) NOT NULL,
    EffectiveTo datetimeoffset(0) NULL,
    StatusCode varchar(12) NOT NULL,
    ApprovedBy nvarchar(200) NULL,
    ApprovedAt datetimeoffset(0) NULL,
    ChangeReason nvarchar(500) NOT NULL,
    CONSTRAINT FK_ProductStandardRevision_Product FOREIGN KEY (ProductID) REFERENCES omagmes.Product(id),
    CONSTRAINT UQ_ProductStandardRevision_Product_Revision UNIQUE (ProductID, RevisionNo),
    CONSTRAINT UQ_ProductStandardRevision_id_Product UNIQUE (id, ProductID),
    CONSTRAINT CK_ProductStandardRevision_Revision CHECK (RevisionNo > 0),
    CONSTRAINT CK_ProductStandardRevision_Values CHECK (StandardPiecesPerDrop > 0 AND StandardCycleTimeSec > 0),
    CONSTRAINT CK_ProductStandardRevision_Period CHECK (EffectiveTo IS NULL OR EffectiveTo > EffectiveFrom),
    CONSTRAINT CK_ProductStandardRevision_Status CHECK (StatusCode IN ('PENDING','APPROVED','RETIRED')),
    CONSTRAINT CK_ProductStandardRevision_Approval CHECK (StatusCode <> 'APPROVED' OR (ApprovedBy IS NOT NULL AND ApprovedAt IS NOT NULL)),
    CONSTRAINT CK_ProductStandardRevision_Reason CHECK (LEN(LTRIM(RTRIM(ChangeReason))) > 0)
);
CREATE INDEX IX_ProductStandardRevision_Product_Period ON omagmes.ProductStandardRevision(ProductID, StatusCode, EffectiveFrom, EffectiveTo);

CREATE TABLE omagmes.ProductionRun (
    id bigint IDENTITY(1,1) NOT NULL CONSTRAINT PK_ProductionRun PRIMARY KEY,
    Rectime datetime NOT NULL CONSTRAINT DF_ProductionRun_Rectime DEFAULT (GETDATE()),
    ProductID bigint NOT NULL,
    StartedAt datetimeoffset(0) NOT NULL,
    EndedAt datetimeoffset(0) NULL,
    StatusCode varchar(12) NOT NULL CONSTRAINT DF_ProductionRun_StatusCode DEFAULT ('OPEN'),
    CreatedBy nvarchar(200) NOT NULL,
    CONSTRAINT FK_ProductionRun_Product FOREIGN KEY (ProductID) REFERENCES omagmes.Product(id),
    CONSTRAINT UQ_ProductionRun_id_Product UNIQUE (id, ProductID),
    CONSTRAINT CK_ProductionRun_Times CHECK (EndedAt IS NULL OR EndedAt >= StartedAt),
    CONSTRAINT CK_ProductionRun_Status CHECK (StatusCode IN ('OPEN', 'CLOSED'))
);
CREATE UNIQUE INDEX UX_ProductionRun_OneOpen ON omagmes.ProductionRun(StatusCode) WHERE StatusCode = 'OPEN';

CREATE TABLE omagmes.ProductionLot (
    id bigint IDENTITY(1,1) NOT NULL CONSTRAINT PK_ProductionLot PRIMARY KEY,
    Rectime datetime NOT NULL CONSTRAINT DF_ProductionLot_Rectime DEFAULT (GETDATE()),
    ProductionRunID bigint NOT NULL,
    ProductID bigint NOT NULL,
    ColorCode nvarchar(60) COLLATE Latin1_General_100_BIN2 NOT NULL,
    ProductFamilySnapshot nvarchar(100) NULL,
    ProductStandardRevisionID bigint NOT NULL,
    StandardPiecesPerDropSnapshot int NOT NULL,
    StandardCycleTimeSecSnapshot decimal(12,4) NOT NULL,
    LotNo varchar(11) COLLATE Latin1_General_100_BIN2 NOT NULL,
    ProductionDate date NOT NULL,
    ShiftScheduleVersionID bigint NOT NULL,
    ShiftID bigint NOT NULL,
    LotSequence tinyint NOT NULL,
    MachineCode char(1) COLLATE Latin1_General_100_BIN2 NOT NULL,
    LotName nvarchar(120) NOT NULL,
    LotStartedAt datetimeoffset(0) NOT NULL,
    LotEndedAt datetimeoffset(0) NULL,
    CreatedBy nvarchar(200) NOT NULL,
    CONSTRAINT FK_ProductionLot_RunProduct FOREIGN KEY (ProductionRunID, ProductID)
        REFERENCES omagmes.ProductionRun(id, ProductID),
    CONSTRAINT FK_ProductionLot_Product FOREIGN KEY (ProductID) REFERENCES omagmes.Product(id),
    CONSTRAINT FK_ProductionLot_StandardRevision FOREIGN KEY (ProductStandardRevisionID, ProductID)
        REFERENCES omagmes.ProductStandardRevision(id, ProductID),
    CONSTRAINT FK_ProductionLot_ShiftScheduleVersion FOREIGN KEY (ShiftScheduleVersionID) REFERENCES omagmes.ShiftScheduleVersion(id),
    CONSTRAINT FK_ProductionLot_Shift FOREIGN KEY (ShiftID) REFERENCES omagmes.Shift(id),
    CONSTRAINT FK_ProductionLot_ScheduledShift FOREIGN KEY (ShiftScheduleVersionID, ShiftID)
        REFERENCES omagmes.ShiftScheduleShift(ShiftScheduleVersionID, ShiftID),
    CONSTRAINT UQ_ProductionLot_LotNo UNIQUE (LotNo),
    CONSTRAINT UQ_ProductionLot_id_StandardRevision UNIQUE (id, ProductStandardRevisionID),
    CONSTRAINT CK_ProductionLot_Name CHECK (LEN(LTRIM(RTRIM(LotName))) > 0),
    CONSTRAINT CK_ProductionLot_Color CHECK (LEN(LTRIM(RTRIM(ColorCode))) > 0),
    CONSTRAINT CK_ProductionLot_NumberParts CHECK (LotSequence BETWEEN 1 AND 99 AND MachineCode='B' AND LEN(LotNo)=11),
    CONSTRAINT CK_ProductionLot_Times CHECK (LotEndedAt IS NULL OR LotEndedAt >= LotStartedAt),
    CONSTRAINT CK_ProductionLot_MinutePrecision CHECK (
        DATEPART(SECOND, LotStartedAt) = 0
        AND (LotEndedAt IS NULL OR DATEPART(SECOND, LotEndedAt) = 0)
    )
);
CREATE INDEX IX_ProductionLot_Product_StartedAt ON omagmes.ProductionLot(ProductID, LotStartedAt DESC, id DESC);
CREATE INDEX IX_ProductionLot_LotName ON omagmes.ProductionLot(LotName, id);
CREATE UNIQUE INDEX UX_ProductionLot_OneOpenPerRun ON omagmes.ProductionLot(ProductionRunID) WHERE LotEndedAt IS NULL;

CREATE TABLE omagmes.AutoLotResetReview (
    id bigint IDENTITY(1,1) NOT NULL CONSTRAINT PK_AutoLotResetReview PRIMARY KEY,
    Rectime datetime NOT NULL CONSTRAINT DF_AutoLotResetReview_Rectime DEFAULT (GETDATE()),
    CandidateID nvarchar(200) COLLATE Latin1_General_100_BIN2 NOT NULL,
    SourceTag nvarchar(100) NOT NULL,
    BeforeSourceID bigint NOT NULL,
    BeforeAt datetimeoffset(0) NOT NULL,
    BeforeValue bigint NOT NULL,
    DecreaseSourceID bigint NOT NULL,
    DecreaseAt datetimeoffset(0) NOT NULL,
    DecreaseValue bigint NOT NULL,
    RestartSourceID bigint NULL,
    RestartAt datetimeoffset(0) NULL,
    RestartValue bigint NULL,
    PostResetDropsLowerBound bigint NOT NULL,
    ProductionLotID bigint NOT NULL,
    ProductionDate date NOT NULL,
    ShiftID bigint NOT NULL,
    ShiftScheduleVersionID bigint NOT NULL,
    ConfirmedBy nvarchar(200) NOT NULL,
    ConfirmationReason nvarchar(500) NOT NULL,
    ReviewedAt datetimeoffset(0) NOT NULL,
    CONSTRAINT FK_AutoLotResetReview_Lot FOREIGN KEY (ProductionLotID) REFERENCES omagmes.ProductionLot(id),
    CONSTRAINT FK_AutoLotResetReview_Shift FOREIGN KEY (ShiftID) REFERENCES omagmes.Shift(id),
    CONSTRAINT FK_AutoLotResetReview_Schedule FOREIGN KEY (ShiftScheduleVersionID) REFERENCES omagmes.ShiftScheduleVersion(id),
    CONSTRAINT UQ_AutoLotResetReview_Candidate UNIQUE (CandidateID),
    CONSTRAINT CK_AutoLotResetReview_Values CHECK (BeforeValue >= 0 AND DecreaseValue >= 0 AND PostResetDropsLowerBound >= 0),
    CONSTRAINT CK_AutoLotResetReview_Restart CHECK ((RestartSourceID IS NULL AND RestartAt IS NULL AND RestartValue IS NULL) OR (RestartSourceID IS NOT NULL AND RestartAt IS NOT NULL AND RestartValue >= 0)),
    CONSTRAINT CK_AutoLotResetReview_Reason CHECK (LEN(LTRIM(RTRIM(ConfirmationReason))) > 0)
);
CREATE INDEX IX_AutoLotResetReview_Lot_ReviewedAt ON omagmes.AutoLotResetReview(ProductionLotID, ReviewedAt, id);

CREATE TABLE omagmes.LotNumberSequence (
    id bigint IDENTITY(1,1) NOT NULL CONSTRAINT PK_LotNumberSequence PRIMARY KEY,
    Rectime datetime NOT NULL CONSTRAINT DF_LotNumberSequence_Rectime DEFAULT (GETDATE()),
    PlantCode char(1) COLLATE Latin1_General_100_BIN2 NOT NULL,
    ProductionDate date NOT NULL,
    ShiftCode char(1) COLLATE Latin1_General_100_BIN2 NOT NULL,
    LastSequence tinyint NOT NULL,
    CONSTRAINT UQ_LotNumberSequence_Scope UNIQUE (PlantCode, ProductionDate, ShiftCode),
    CONSTRAINT CK_LotNumberSequence_Sequence CHECK (LastSequence BETWEEN 1 AND 99),
    CONSTRAINT CK_LotNumberSequence_Plant CHECK (PlantCode='C'),
    CONSTRAINT CK_LotNumberSequence_Shift CHECK (ShiftCode IN ('1','2'))
);

CREATE TABLE omagmes.ProductionLotNameHistory (
    id bigint IDENTITY(1,1) NOT NULL CONSTRAINT PK_ProductionLotNameHistory PRIMARY KEY,
    Rectime datetime NOT NULL CONSTRAINT DF_ProductionLotNameHistory_Rectime DEFAULT (GETDATE()),
    ProductionLotID bigint NOT NULL,
    OldLotName nvarchar(120) NOT NULL,
    NewLotName nvarchar(120) NOT NULL,
    ChangedBy nvarchar(200) NOT NULL,
    ChangedAt datetimeoffset(0) NOT NULL,
    ChangeReason nvarchar(500) NOT NULL,
    CONSTRAINT FK_ProductionLotNameHistory_Lot FOREIGN KEY (ProductionLotID) REFERENCES omagmes.ProductionLot(id),
    CONSTRAINT CK_ProductionLotNameHistory_Changed CHECK (OldLotName <> NewLotName),
    CONSTRAINT CK_ProductionLotNameHistory_Reason CHECK (LEN(LTRIM(RTRIM(ChangeReason))) > 0)
);
CREATE INDEX IX_ProductionLotNameHistory_Lot_ChangedAt ON omagmes.ProductionLotNameHistory(ProductionLotID, ChangedAt DESC, id DESC);

CREATE TABLE omagmes.ProductionEntry (
    id bigint IDENTITY(1,1) NOT NULL CONSTRAINT PK_ProductionEntry PRIMARY KEY,
    Rectime datetime NOT NULL CONSTRAINT DF_ProductionEntry_Rectime DEFAULT (GETDATE()),
    ProductionLotID bigint NOT NULL,
    PressDrops bigint NOT NULL,
    WetGoodPieces bigint NOT NULL,
    SuggestedPressDrops bigint NULL,
    SuggestedWetGoodPieces bigint NULL,
    ProductStandardRevisionID bigint NOT NULL,
    StandardPiecesPerDropSnapshot int NOT NULL,
    StandardCycleTimeSecSnapshot decimal(12,4) NOT NULL,
    SourceCode varchar(20) NOT NULL,
    OperatorNote nvarchar(1000) NULL,
    EnteredBy nvarchar(200) NOT NULL,
    RecordedAt datetimeoffset(0) NOT NULL,
    ProductionAt datetimeoffset(0) NOT NULL,
    ProductionDate date NOT NULL,
    ShiftScheduleVersionID bigint NOT NULL,
    ShiftID bigint NULL,
    CONSTRAINT FK_ProductionEntry_Lot FOREIGN KEY (ProductionLotID) REFERENCES omagmes.ProductionLot(id),
    CONSTRAINT FK_ProductionEntry_LotStandard FOREIGN KEY (ProductionLotID, ProductStandardRevisionID)
        REFERENCES omagmes.ProductionLot(id, ProductStandardRevisionID),
    CONSTRAINT FK_ProductionEntry_ShiftScheduleVersion FOREIGN KEY (ShiftScheduleVersionID) REFERENCES omagmes.ShiftScheduleVersion(id),
    CONSTRAINT FK_ProductionEntry_Shift FOREIGN KEY (ShiftID) REFERENCES omagmes.Shift(id),
    CONSTRAINT FK_ProductionEntry_ScheduledShift FOREIGN KEY (ShiftScheduleVersionID, ShiftID)
        REFERENCES omagmes.ShiftScheduleShift(ShiftScheduleVersionID, ShiftID),
    CONSTRAINT CK_ProductionEntry_Quantities CHECK (PressDrops >= 0 AND WetGoodPieces >= 0 AND (SuggestedPressDrops IS NULL OR SuggestedPressDrops >= 0) AND (SuggestedWetGoodPieces IS NULL OR SuggestedWetGoodPieces >= 0)),
    CONSTRAINT CK_ProductionEntry_Source CHECK (SourceCode IN ('MANUAL', 'AUTOCAL_REVIEWED'))
);
CREATE INDEX IX_ProductionEntry_Lot_ProductionAt ON omagmes.ProductionEntry(ProductionLotID, ProductionAt DESC, id DESC);
CREATE INDEX IX_ProductionEntry_ProductionDate_Shift ON omagmes.ProductionEntry(ProductionDate, ShiftID, ProductionAt, id);

CREATE TABLE omagmes.ProductionEntryCorrection (
    id bigint IDENTITY(1,1) NOT NULL CONSTRAINT PK_ProductionEntryCorrection PRIMARY KEY,
    Rectime datetime NOT NULL CONSTRAINT DF_ProductionEntryCorrection_Rectime DEFAULT (GETDATE()),
    ProductionEntryID bigint NOT NULL,
    OldPressDrops bigint NOT NULL,
    NewPressDrops bigint NOT NULL,
    OldWetGoodPieces bigint NOT NULL,
    NewWetGoodPieces bigint NOT NULL,
    ChangedBy nvarchar(200) NOT NULL,
    ChangedAt datetimeoffset(0) NOT NULL,
    ChangeReason nvarchar(500) NOT NULL,
    CONSTRAINT FK_ProductionEntryCorrection_Entry FOREIGN KEY (ProductionEntryID) REFERENCES omagmes.ProductionEntry(id),
    CONSTRAINT CK_ProductionEntryCorrection_Quantities CHECK (OldPressDrops >= 0 AND NewPressDrops >= 0 AND OldWetGoodPieces >= 0 AND NewWetGoodPieces >= 0),
    CONSTRAINT CK_ProductionEntryCorrection_Reason CHECK (LEN(LTRIM(RTRIM(ChangeReason))) > 0)
);
CREATE INDEX IX_ProductionEntryCorrection_Entry_ChangedAt ON omagmes.ProductionEntryCorrection(ProductionEntryID, ChangedAt DESC, id DESC);

CREATE TABLE omagmes.CuringInputEntry (
    id bigint IDENTITY(1,1) NOT NULL CONSTRAINT PK_CuringInputEntry PRIMARY KEY,
    Rectime datetime NOT NULL CONSTRAINT DF_CuringInputEntry_Rectime DEFAULT (GETDATE()),
    ProductionLotID bigint NOT NULL,
    InputQuantity bigint NOT NULL,
    QuantityUnitCode nvarchar(40) NOT NULL,
    RecordedAt datetimeoffset(0) NOT NULL,
    OperatorNote nvarchar(1000) NULL,
    EnteredBy nvarchar(200) NOT NULL,
    CONSTRAINT FK_CuringInputEntry_Lot FOREIGN KEY (ProductionLotID) REFERENCES omagmes.ProductionLot(id),
    CONSTRAINT CK_CuringInputEntry_Quantity CHECK (InputQuantity >= 0),
    CONSTRAINT CK_CuringInputEntry_Unit CHECK (LEN(LTRIM(RTRIM(QuantityUnitCode))) > 0)
);
CREATE INDEX IX_CuringInputEntry_Lot_RecordedAt ON omagmes.CuringInputEntry(ProductionLotID, RecordedAt DESC, id DESC);

CREATE TABLE omagmes.DepalletEvent (
    id bigint IDENTITY(1,1) NOT NULL CONSTRAINT PK_DepalletEvent PRIMARY KEY,
    Rectime datetime NOT NULL CONSTRAINT DF_DepalletEvent_Rectime DEFAULT (GETDATE()),
    ProductionLotID bigint NOT NULL,
    Quantity bigint NOT NULL,
    QuantityUnitCode nvarchar(40) NOT NULL,
    RecordedAt datetimeoffset(0) NOT NULL,
    OperatorNote nvarchar(1000) NULL,
    EnteredBy nvarchar(200) NOT NULL,
    CONSTRAINT FK_DepalletEvent_Lot FOREIGN KEY (ProductionLotID) REFERENCES omagmes.ProductionLot(id),
    CONSTRAINT CK_DepalletEvent_Quantity CHECK (Quantity >= 0),
    CONSTRAINT CK_DepalletEvent_Unit CHECK (LEN(LTRIM(RTRIM(QuantityUnitCode))) > 0)
);
CREATE INDEX IX_DepalletEvent_Lot_RecordedAt ON omagmes.DepalletEvent(ProductionLotID, RecordedAt DESC, id DESC);

CREATE TABLE omagmes.Dispatch (
    id bigint IDENTITY(1,1) NOT NULL CONSTRAINT PK_Dispatch PRIMARY KEY,
    Rectime datetime NOT NULL CONSTRAINT DF_Dispatch_Rectime DEFAULT (GETDATE()),
    DispatchReference nvarchar(120) NULL,
    DispatchedAt datetimeoffset(0) NOT NULL,
    EnteredBy nvarchar(200) NOT NULL,
    OperatorNote nvarchar(1000) NULL
);

CREATE TABLE omagmes.DispatchLine (
    id bigint IDENTITY(1,1) NOT NULL CONSTRAINT PK_DispatchLine PRIMARY KEY,
    Rectime datetime NOT NULL CONSTRAINT DF_DispatchLine_Rectime DEFAULT (GETDATE()),
    DispatchID bigint NOT NULL,
    ProductionLotID bigint NOT NULL,
    Quantity bigint NOT NULL,
    QuantityUnitCode nvarchar(40) NOT NULL,
    CONSTRAINT FK_DispatchLine_Dispatch FOREIGN KEY (DispatchID) REFERENCES omagmes.Dispatch(id),
    CONSTRAINT FK_DispatchLine_Lot FOREIGN KEY (ProductionLotID) REFERENCES omagmes.ProductionLot(id),
    CONSTRAINT CK_DispatchLine_Quantity CHECK (Quantity >= 0),
    CONSTRAINT CK_DispatchLine_Unit CHECK (LEN(LTRIM(RTRIM(QuantityUnitCode))) > 0)
);
CREATE INDEX IX_DispatchLine_Lot_Dispatch ON omagmes.DispatchLine(ProductionLotID, DispatchID, id);

COMMIT TRANSACTION;
GO
/* No Product/Color seed rows, test Lots, or transaction samples are inserted. */
