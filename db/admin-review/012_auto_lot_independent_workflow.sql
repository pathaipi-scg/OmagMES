/*
SUPERSEDED HISTORICAL DRAFT — DO NOT EXECUTE.
Use db/admin-review/autolot_clean_development_setup.sql as the sole clean setup artifact.
DBA REVIEW ONLY — MANUAL SSMS DEPLOYMENT CANDIDATE. DO NOT RUN AS THE APPLICATION.
Target: OMAG / omagmes. Requires the authorized database owner/sa and a verified backup/change window.
This migration is additive. It does not alter dbo.PRESS, dbo.vw_PRESS_LotDetect,
dbo.vw_OmagPlan, Product, Mould, Shift, ProductionLot, ProductionRun, or any
Curing, Wet Reject, Depallet, Dispatch, PIS, or FittingMES data.

Plan identity: dbo.vw_OmagPlan exposes no durable Plan ID. The application stores
an internal immutable PlanIdentity.id for an exact SHA-256 content snapshot; a
changed source snapshot receives a new identity. Exact duplicate plan rows are
not assignable. MaterialCode/ProductCode matching is byte/case-sensitive in the
application and never trims or rewrites either code.

Detection identity: dbo.vw_PRESS_LotDetect exposes no stable source ID. The
application uses SHA-256 of exact LotStart. Changes to LotStop/DropCnt update the
same AutoLot. A corrected LotStart that overlaps a retained AutoLot is withheld
from number allocation and flagged for review; prior AutoLots are never deleted.
*/
USE [OMAG];
GO
SET NOCOUNT ON;
SET XACT_ABORT ON;

IF DB_NAME() <> N'OMAG'
    THROW 54800, 'Migration 012 requires database OMAG.', 1;
IF IS_SRVROLEMEMBER(N'sysadmin') <> 1
    THROW 54801, 'Migration 012 is manual DBA/owner DDL and must not run as an application runtime.', 1;
IF SCHEMA_ID(N'omagmes') IS NULL
    THROW 54802, 'Required omagmes schema is missing.', 1;
IF DATABASE_PRINCIPAL_ID(N'OMAG_MES') IS NULL
    THROW 54803, 'The existing OMAG_MES database principal is missing; inspect runtime identity before deployment.', 1;
IF OBJECT_ID(N'dbo.vw_PRESS_LotDetect',N'V') IS NULL
   OR OBJECT_ID(N'dbo.vw_OmagPlan',N'V') IS NULL
   OR OBJECT_ID(N'omagmes.Product',N'U') IS NULL
   OR OBJECT_ID(N'omagmes.Mould',N'U') IS NULL
   OR OBJECT_ID(N'omagmes.Shift',N'U') IS NULL
   OR OBJECT_ID(N'omagmes.DailyShiftConfigurationSave',N'U') IS NULL
   OR OBJECT_ID(N'omagmes.LotNumberSequence',N'U') IS NULL
   OR OBJECT_ID(N'omagmes.ProductionLot',N'U') IS NULL
    THROW 54804, 'A verified detection, plan, master, shift, sequence, or official Lot prerequisite is missing.', 1;
IF COL_LENGTH(N'omagmes.Product',N'id') IS NULL
   OR COL_LENGTH(N'omagmes.Product',N'ProductCode') IS NULL
   OR COL_LENGTH(N'omagmes.Product',N'ProductName') IS NULL
   OR COL_LENGTH(N'omagmes.Product',N'IsActive') IS NULL
   OR COL_LENGTH(N'omagmes.Mould',N'id') IS NULL
   OR COL_LENGTH(N'omagmes.Mould',N'ProductID') IS NULL
   OR COL_LENGTH(N'omagmes.Mould',N'MouldCode') IS NULL
   OR COL_LENGTH(N'omagmes.Mould',N'StatusCode') IS NULL
   OR COL_LENGTH(N'omagmes.Mould',N'IsActive') IS NULL
   OR COL_LENGTH(N'omagmes.Shift',N'id') IS NULL
   OR COL_LENGTH(N'omagmes.DailyShiftConfigurationSave',N'id') IS NULL
   OR COL_LENGTH(N'omagmes.DailyShiftConfigurationSave',N'ProductionDate') IS NULL
   OR COL_LENGTH(N'omagmes.DailyShiftConfigurationSave',N'IsComplete') IS NULL
   OR COL_LENGTH(N'omagmes.LotNumberSequence',N'PlantCode') IS NULL
   OR COL_LENGTH(N'omagmes.LotNumberSequence',N'ProductionDate') IS NULL
   OR COL_LENGTH(N'omagmes.LotNumberSequence',N'ShiftCode') IS NULL
   OR COL_LENGTH(N'omagmes.LotNumberSequence',N'LastSequence') IS NULL
    THROW 54805, 'Verified master or sequence columns differ from the migration contract.', 1;
IF EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id=OBJECT_ID(N'dbo.vw_PRESS_LotDetect')
      AND name IN (N'ProdDate',N'LotStart',N'LotStop',N'pDropCnt',N'DropCnt')
    GROUP BY object_id
    HAVING COUNT(*) <> 5
) OR (SELECT COUNT(*) FROM sys.columns
      WHERE object_id=OBJECT_ID(N'dbo.vw_PRESS_LotDetect')
        AND name IN (N'ProdDate',N'LotStart',N'LotStop',N'pDropCnt',N'DropCnt')) <> 5
    THROW 54806, 'dbo.vw_PRESS_LotDetect does not expose the five reviewed detection columns.', 1;
IF EXISTS (
    SELECT ProductCode FROM omagmes.Product
    GROUP BY ProductCode HAVING COUNT_BIG(*) > 1
)
    THROW 54807, 'Duplicate ProductCode rows exist; Plan/Product mapping must be reviewed before deployment.', 1;
IF EXISTS (
    SELECT 1 FROM sys.objects
    WHERE schema_id=SCHEMA_ID(N'omagmes')
      AND name IN (N'AutoLot',N'AutoLotAssignment',N'PlanIdentity')
)
    THROW 54808, 'One or more Migration 012 names already exist; inspect partial deployment before continuing.', 1;
IF NOT EXISTS (
    SELECT 1 FROM sys.key_constraints
    WHERE parent_object_id=OBJECT_ID(N'omagmes.DailyShiftConfigurationSave')
      AND name=N'UQ_DailyShiftConfigurationSave_ID_Date'
)
    THROW 54809, 'DailyShiftConfigurationSave must have its verified (id,ProductionDate) key.', 1;
IF NOT EXISTS (
    SELECT 1 FROM sys.key_constraints
    WHERE parent_object_id=OBJECT_ID(N'omagmes.LotNumberSequence')
      AND name=N'UQ_LotNumberSequence_Scope'
)
    THROW 54810, 'The shared Lot sequence scope uniqueness constraint is missing.', 1;
IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE object_id=OBJECT_ID(N'omagmes.ProductionLot') AND name=N'UQ_ProductionLot_LotNo' AND is_unique=1
)
    THROW 54811, 'Official ProductionLot.LotNo uniqueness is required before AutoLot numbering.', 1;
IF EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE object_id=OBJECT_ID(N'omagmes.Mould') AND name=N'UX_Mould_ID_ProductID_AutoLot'
)
    THROW 54812, 'The proposed additive Mould composite key index already exists; inspect before proceeding.', 1;

BEGIN TRY
    BEGIN TRANSACTION;

    /* A redundant unique key enables an ID-first composite FK that guarantees
       the selected physical Mould belongs to the resolved Product. */
    CREATE UNIQUE INDEX UX_Mould_ID_ProductID_AutoLot
        ON omagmes.Mould(id,ProductID);

    CREATE TABLE omagmes.PlanIdentity (
        id bigint IDENTITY(1,1) NOT NULL CONSTRAINT PK_PlanIdentity PRIMARY KEY,
        Rectime datetime NOT NULL CONSTRAINT DF_PlanIdentity_Rectime DEFAULT (GETDATE()),
        PlanKey char(64) COLLATE Latin1_General_100_BIN2 NOT NULL,
        PlanSnapshotJson nvarchar(max) NOT NULL,
        PlanName varchar(50) COLLATE Thai_CI_AS NULL,
        MaterialCode varchar(30) COLLATE Thai_CI_AS NULL,
        MaterialName varchar(100) COLLATE Thai_CI_AS NULL,
        PlannedStart date NULL,
        PlanCountText nvarchar(100) NULL,
        Machine varchar(20) COLLATE Thai_CI_AS NULL,
        Shift varchar(20) COLLATE Thai_CI_AS NULL,
        CONSTRAINT UQ_PlanIdentity_PlanKey UNIQUE (PlanKey),
        CONSTRAINT CK_PlanIdentity_Key CHECK (LEN(PlanKey)=64 AND PlanKey NOT LIKE '%[^0-9a-f]%')
    );
    CREATE INDEX IX_PlanIdentity_MaterialCode ON omagmes.PlanIdentity(MaterialCode,PlanKey);

    CREATE TABLE omagmes.AutoLot (
        id bigint IDENTITY(1,1) NOT NULL CONSTRAINT PK_AutoLot PRIMARY KEY,
        Rectime datetime NOT NULL CONSTRAINT DF_AutoLot_Rectime DEFAULT (GETDATE()),
        ProductionDate date NOT NULL,
        LotNo varchar(11) COLLATE Latin1_General_100_BIN2 NOT NULL,
        LotSequence tinyint NOT NULL,
        ShiftID bigint NOT NULL,
        ShiftNumber tinyint NOT NULL,
        ShiftConfigurationSaveID bigint NOT NULL,
        SourceKey char(64) COLLATE Latin1_General_100_BIN2 NOT NULL,
        SourceProdDate date NULL,
        LotStart datetime NOT NULL,
        LotStop datetime NULL,
        DropCnt int NULL,
        pDropCnt int NULL,
        FirstSeenAt datetime NOT NULL CONSTRAINT DF_AutoLot_FirstSeenAt DEFAULT (GETDATE()),
        LastSeenAt datetime NOT NULL CONSTRAINT DF_AutoLot_LastSeenAt DEFAULT (GETDATE()),
        UpdatedTime datetime NOT NULL CONSTRAINT DF_AutoLot_UpdatedTime DEFAULT (GETDATE()),
        IsCurrent bit NOT NULL CONSTRAINT DF_AutoLot_IsCurrent DEFAULT (1),
        ReconciliationStatus varchar(32) NOT NULL CONSTRAINT DF_AutoLot_ReconciliationStatus DEFAULT ('CURRENT'),
        CONSTRAINT UQ_AutoLot_LotNo UNIQUE (LotNo),
        CONSTRAINT UQ_AutoLot_SourceKey UNIQUE (SourceKey),
        CONSTRAINT UQ_AutoLot_DateShiftSequence UNIQUE (ProductionDate,ShiftNumber,LotSequence),
        CONSTRAINT FK_AutoLot_Shift FOREIGN KEY (ShiftID) REFERENCES omagmes.Shift(id),
        CONSTRAINT FK_AutoLot_ShiftConfiguration FOREIGN KEY (ShiftConfigurationSaveID,ProductionDate)
            REFERENCES omagmes.DailyShiftConfigurationSave(id,ProductionDate),
        CONSTRAINT CK_AutoLot_LotNumber CHECK (
            LotNo LIKE 'B[0-9][0-9][0-9][0-9][0-9][0-9][1-3][0-9][0-9]A'
            AND LotSequence BETWEEN 1 AND 99
            AND CONVERT(int,SUBSTRING(LotNo,8,1))=ShiftNumber
            AND CONVERT(int,SUBSTRING(LotNo,9,2))=LotSequence
            AND ShiftNumber IN (1,2,3)
        ),
        CONSTRAINT CK_AutoLot_SourceKey CHECK (LEN(SourceKey)=64 AND SourceKey NOT LIKE '%[^0-9a-f]%'),
        CONSTRAINT CK_AutoLot_SourceInterval CHECK (LotStop IS NULL OR LotStop>=LotStart),
        CONSTRAINT CK_AutoLot_ReconciliationStatus CHECK (
            ReconciliationStatus IN ('CURRENT','SOURCE_MISSING','SCHEDULE_REVIEW','POSSIBLE_SOURCE_CORRECTION')
        )
    );
    CREATE INDEX IX_AutoLot_Date_Start ON omagmes.AutoLot(ProductionDate,LotStart,id)
        INCLUDE (LotNo,DropCnt,ShiftID,ShiftNumber,IsCurrent,ReconciliationStatus);
    CREATE INDEX IX_AutoLot_SourceStart ON omagmes.AutoLot(LotStart,LotStop)
        INCLUDE (ProductionDate,SourceKey,IsCurrent);

    CREATE TABLE omagmes.AutoLotAssignment (
        id bigint IDENTITY(1,1) NOT NULL CONSTRAINT PK_AutoLotAssignment PRIMARY KEY,
        Rectime datetime NOT NULL CONSTRAINT DF_AutoLotAssignment_Rectime DEFAULT (GETDATE()),
        AutoLotID bigint NOT NULL,
        PlanIdentityID bigint NULL,
        ProductID bigint NULL,
        MouldID bigint NULL,
        UpdatedTime datetime NOT NULL CONSTRAINT DF_AutoLotAssignment_UpdatedTime DEFAULT (GETDATE()),
        CONSTRAINT UQ_AutoLotAssignment_AutoLot UNIQUE (AutoLotID),
        CONSTRAINT FK_AutoLotAssignment_AutoLot FOREIGN KEY (AutoLotID) REFERENCES omagmes.AutoLot(id),
        CONSTRAINT FK_AutoLotAssignment_Plan FOREIGN KEY (PlanIdentityID) REFERENCES omagmes.PlanIdentity(id),
        CONSTRAINT FK_AutoLotAssignment_Product FOREIGN KEY (ProductID) REFERENCES omagmes.Product(id),
        CONSTRAINT FK_AutoLotAssignment_MouldProduct FOREIGN KEY (MouldID,ProductID)
            REFERENCES omagmes.Mould(id,ProductID),
        CONSTRAINT CK_AutoLotAssignment_PlanProduct CHECK (
            (PlanIdentityID IS NULL AND ProductID IS NULL AND MouldID IS NULL)
            OR (PlanIdentityID IS NOT NULL AND ProductID IS NOT NULL)
        )
    );
    CREATE INDEX IX_AutoLotAssignment_Product ON omagmes.AutoLotAssignment(ProductID,AutoLotID)
        INCLUDE (PlanIdentityID,MouldID);
    CREATE INDEX IX_AutoLotAssignment_Mould ON omagmes.AutoLotAssignment(MouldID,AutoLotID)
        WHERE MouldID IS NOT NULL;

    /* The OMAG_MES runtime receives only the operations required by this feature.
       No DELETE, ALTER, CONTROL, or write grants to existing official production tables. */
    GRANT SELECT,INSERT ON OBJECT::omagmes.PlanIdentity TO OMAG_MES;
    GRANT SELECT,INSERT ON OBJECT::omagmes.AutoLot TO OMAG_MES;
    GRANT UPDATE (SourceProdDate,LotStop,DropCnt,pDropCnt,LastSeenAt,UpdatedTime,IsCurrent,ReconciliationStatus)
        ON OBJECT::omagmes.AutoLot TO OMAG_MES;
    GRANT SELECT,INSERT ON OBJECT::omagmes.AutoLotAssignment TO OMAG_MES;
    GRANT UPDATE (PlanIdentityID,ProductID,MouldID,UpdatedTime)
        ON OBJECT::omagmes.AutoLotAssignment TO OMAG_MES;
    /* AutoLot and official Lots share one sequence scope. The runtime can
       advance/create a scope row, but cannot change its identity columns. */
    GRANT SELECT ON OBJECT::omagmes.LotNumberSequence TO OMAG_MES;
    GRANT INSERT (PlantCode,ProductionDate,ShiftCode,LastSequence)
        ON OBJECT::omagmes.LotNumberSequence TO OMAG_MES;
    GRANT UPDATE (LastSequence)
        ON OBJECT::omagmes.LotNumberSequence TO OMAG_MES;

    COMMIT TRANSACTION;
END TRY
BEGIN CATCH
    IF XACT_STATE()<>0 ROLLBACK TRANSACTION;
    THROW;
END CATCH;
GO

/* Read-only deployment verification. Stop if any result differs from the intended contract. */
SELECT N'AUTOLOT_TABLE' AS CheckType,t.name AS ObjectName,c.name AS ColumnName,ty.name AS DataType,c.is_nullable,c.is_identity
FROM sys.tables t JOIN sys.schemas s ON s.schema_id=t.schema_id
JOIN sys.columns c ON c.object_id=t.object_id JOIN sys.types ty ON ty.user_type_id=c.user_type_id
WHERE s.name=N'omagmes' AND t.name IN (N'AutoLot',N'AutoLotAssignment',N'PlanIdentity')
ORDER BY t.name,c.column_id;
SELECT N'AUTOLOT_CONSTRAINT' AS CheckType,OBJECT_NAME(parent_object_id) AS ParentObject,name,is_disabled,is_not_trusted
FROM sys.foreign_keys WHERE parent_object_id IN (OBJECT_ID(N'omagmes.AutoLot'),OBJECT_ID(N'omagmes.AutoLotAssignment'))
UNION ALL
SELECT N'AUTOLOT_CHECK',OBJECT_NAME(parent_object_id),name,is_disabled,is_not_trusted
FROM sys.check_constraints WHERE parent_object_id IN (OBJECT_ID(N'omagmes.AutoLot'),OBJECT_ID(N'omagmes.AutoLotAssignment'));
EXECUTE AS USER = N'OMAG_MES';
SELECT N'RUNTIME_PERMISSION' AS CheckType,
       HAS_PERMS_BY_NAME(N'omagmes.AutoLot',N'OBJECT',N'SELECT') AS AutoLotSelect,
       HAS_PERMS_BY_NAME(N'omagmes.AutoLot',N'OBJECT',N'INSERT') AS AutoLotInsert,
       HAS_PERMS_BY_NAME(N'omagmes.AutoLot',N'OBJECT',N'DELETE') AS AutoLotDelete,
       HAS_PERMS_BY_NAME(N'omagmes.AutoLotAssignment',N'OBJECT',N'SELECT') AS AssignmentSelect,
       HAS_PERMS_BY_NAME(N'omagmes.AutoLotAssignment',N'OBJECT',N'INSERT') AS AssignmentInsert,
    HAS_PERMS_BY_NAME(N'omagmes.PlanIdentity',N'OBJECT',N'SELECT') AS PlanIdentitySelect,
    HAS_PERMS_BY_NAME(N'omagmes.LotNumberSequence',N'OBJECT',N'SELECT') AS SequenceSelect,
    HAS_PERMS_BY_NAME(N'omagmes.LotNumberSequence',N'OBJECT',N'INSERT',N'PlantCode',N'COLUMN') AS SequencePlantInsert,
    HAS_PERMS_BY_NAME(N'omagmes.LotNumberSequence',N'OBJECT',N'INSERT',N'ProductionDate',N'COLUMN') AS SequenceDateInsert,
    HAS_PERMS_BY_NAME(N'omagmes.LotNumberSequence',N'OBJECT',N'INSERT',N'ShiftCode',N'COLUMN') AS SequenceShiftInsert,
    HAS_PERMS_BY_NAME(N'omagmes.LotNumberSequence',N'OBJECT',N'INSERT',N'LastSequence',N'COLUMN') AS SequenceValueInsert,
    HAS_PERMS_BY_NAME(N'omagmes.LotNumberSequence',N'OBJECT',N'UPDATE',N'LastSequence',N'COLUMN') AS SequenceValueUpdate;
REVERT;
