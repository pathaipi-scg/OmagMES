/*
    SUPERSEDED DRAFT — DO NOT EXECUTE. Use db/admin-review/007_operator_production_audit_deploy.sql after DBA approval.
    OmagMES 007 — production entry audit/delete, Wet Reject master, Mould master.
    Additive only. Does not seed master or transaction data and does not touch dbo/legacy objects.
    Requires DBA review and explicit deployment. Application runtime OMAG_MES must not run this script.
*/
SET XACT_ABORT ON;
GO
IF DB_NAME() <> N'OMAG'
    THROW 53710, 'Migration 007 requires the OMAG database.', 1;
IF SCHEMA_ID(N'omagmes') IS NULL
    THROW 53711, 'Migration 007 requires the installed omagmes schema.', 1;
IF OBJECT_ID(N'omagmes.ProductionEntry', N'U') IS NULL
   OR OBJECT_ID(N'omagmes.CuringInputEntry', N'U') IS NULL
   OR OBJECT_ID(N'omagmes.ProductionLot', N'U') IS NULL
   OR OBJECT_ID(N'omagmes.Product', N'U') IS NULL
    THROW 53712, 'Required installed OmagMES production tables are missing.', 1;
IF OBJECT_ID(N'omagmes.ProductionEntryChangeHistory', N'U') IS NOT NULL
   OR OBJECT_ID(N'omagmes.WetRejectReason', N'U') IS NOT NULL
   OR OBJECT_ID(N'omagmes.WetRejectEntry', N'U') IS NOT NULL
   OR OBJECT_ID(N'omagmes.Mould', N'U') IS NOT NULL
   OR OBJECT_ID(N'omagmes.MouldHistory', N'U') IS NOT NULL
    THROW 53713, 'A Migration 007 object already exists; inspect before proceeding.', 1;
IF COL_LENGTH(N'omagmes.ProductionEntry', N'IsDeleted') IS NOT NULL
   OR COL_LENGTH(N'omagmes.ProductionEntry', N'OperatorConfirmed') IS NOT NULL
   OR COL_LENGTH(N'omagmes.CuringInputEntry', N'OperatorConfirmed') IS NOT NULL
    THROW 53714, 'A Migration 007 column already exists; inspect before proceeding.', 1;
GO
BEGIN TRANSACTION;
ALTER TABLE omagmes.ProductionEntry ADD
    IsDeleted bit NOT NULL CONSTRAINT DF_ProductionEntry_IsDeleted_007 DEFAULT (0),
    DeletedAt datetimeoffset(0) NULL,
    DeletedBy nvarchar(200) NULL,
    DeleteReason nvarchar(500) NULL,
    OperatorConfirmed bit NOT NULL CONSTRAINT DF_ProductionEntry_OperatorConfirmed_007 DEFAULT (0);
ALTER TABLE omagmes.CuringInputEntry ADD
    OperatorConfirmed bit NOT NULL CONSTRAINT DF_CuringInputEntry_OperatorConfirmed_007 DEFAULT (0);

CREATE TABLE omagmes.ProductionEntryChangeHistory (
    id bigint IDENTITY(1,1) NOT NULL CONSTRAINT PK_ProductionEntryChangeHistory PRIMARY KEY,
    Rectime datetime NOT NULL CONSTRAINT DF_ProductionEntryChangeHistory_Rectime DEFAULT (GETDATE()),
    ProductionEntryID bigint NOT NULL,
    ChangeType varchar(10) NOT NULL,
    ChangedBy nvarchar(200) NOT NULL,
    ChangedAt datetimeoffset(0) NOT NULL,
    ChangeReason nvarchar(500) NOT NULL,
    BeforeStateJson nvarchar(max) NULL,
    AfterStateJson nvarchar(max) NULL,
    CONSTRAINT FK_ProductionEntryChangeHistory_Entry FOREIGN KEY (ProductionEntryID) REFERENCES omagmes.ProductionEntry(id),
    CONSTRAINT CK_ProductionEntryChangeHistory_Type CHECK (ChangeType IN ('SAVE','EDIT','DELETE')),
    CONSTRAINT CK_ProductionEntryChangeHistory_Reason CHECK (LEN(LTRIM(RTRIM(ChangeReason))) > 0)
);
CREATE INDEX IX_ProductionEntryChangeHistory_Entry_ChangedAt ON omagmes.ProductionEntryChangeHistory(ProductionEntryID, ChangedAt DESC, id DESC);

CREATE TABLE omagmes.WetRejectReason (
    id bigint IDENTITY(1,1) NOT NULL CONSTRAINT PK_WetRejectReason PRIMARY KEY,
    Rectime datetime NOT NULL CONSTRAINT DF_WetRejectReason_Rectime DEFAULT (GETDATE()),
    ReasonCode nvarchar(40) COLLATE Latin1_General_100_BIN2 NOT NULL,
    ReasonName nvarchar(200) NOT NULL,
    IsActive bit NOT NULL CONSTRAINT DF_WetRejectReason_IsActive DEFAULT (1),
    CONSTRAINT UQ_WetRejectReason_ReasonCode UNIQUE (ReasonCode),
    CONSTRAINT CK_WetRejectReason_Code CHECK (LEN(LTRIM(RTRIM(ReasonCode))) > 0),
    CONSTRAINT CK_WetRejectReason_Name CHECK (LEN(LTRIM(RTRIM(ReasonName))) > 0)
);

CREATE TABLE omagmes.WetRejectEntry (
    id bigint IDENTITY(1,1) NOT NULL CONSTRAINT PK_WetRejectEntry PRIMARY KEY,
    Rectime datetime NOT NULL CONSTRAINT DF_WetRejectEntry_Rectime DEFAULT (GETDATE()),
    ProductionLotID bigint NOT NULL,
    RejectReasonID bigint NOT NULL,
    Quantity bigint NOT NULL,
    RecordedAt datetimeoffset(0) NOT NULL,
    EnteredBy nvarchar(200) NOT NULL,
    OperatorNote nvarchar(1000) NULL,
    IsDeleted bit NOT NULL CONSTRAINT DF_WetRejectEntry_IsDeleted DEFAULT (0),
    CONSTRAINT FK_WetRejectEntry_Lot FOREIGN KEY (ProductionLotID) REFERENCES omagmes.ProductionLot(id),
    CONSTRAINT FK_WetRejectEntry_Reason FOREIGN KEY (RejectReasonID) REFERENCES omagmes.WetRejectReason(id),
    CONSTRAINT CK_WetRejectEntry_Quantity CHECK (Quantity >= 0)
);
CREATE INDEX IX_WetRejectEntry_Lot_RecordedAt ON omagmes.WetRejectEntry(ProductionLotID, RecordedAt DESC, id DESC);

CREATE TABLE omagmes.Mould (
    id bigint IDENTITY(1,1) NOT NULL CONSTRAINT PK_Mould PRIMARY KEY,
    Rectime datetime NOT NULL CONSTRAINT DF_Mould_Rectime DEFAULT (GETDATE()),
    ProductID bigint NOT NULL,
    MouldCode nvarchar(100) COLLATE Latin1_General_100_BIN2 NOT NULL,
    MouldName nvarchar(200) NOT NULL,
    CurrentAgeDrops bigint NOT NULL CONSTRAINT DF_Mould_CurrentAgeDrops DEFAULT (0),
    LifetimeAgeDrops bigint NOT NULL CONSTRAINT DF_Mould_LifetimeAgeDrops DEFAULT (0),
    StatusCode varchar(20) NOT NULL CONSTRAINT DF_Mould_StatusCode DEFAULT ('ACTIVE'),
    IsActive bit NOT NULL CONSTRAINT DF_Mould_IsActive DEFAULT (1),
    CONSTRAINT FK_Mould_Product FOREIGN KEY (ProductID) REFERENCES omagmes.Product(id),
    CONSTRAINT UQ_Mould_MouldCode UNIQUE (MouldCode),
    CONSTRAINT CK_Mould_Ages CHECK (CurrentAgeDrops >= 0 AND LifetimeAgeDrops >= CurrentAgeDrops),
    CONSTRAINT CK_Mould_Status CHECK (StatusCode IN ('ACTIVE','RECONDITION','RETIRED'))
);
CREATE INDEX IX_Mould_Product_Status ON omagmes.Mould(ProductID, StatusCode, IsActive);

CREATE TABLE omagmes.MouldHistory (
    id bigint IDENTITY(1,1) NOT NULL CONSTRAINT PK_MouldHistory PRIMARY KEY,
    Rectime datetime NOT NULL CONSTRAINT DF_MouldHistory_Rectime DEFAULT (GETDATE()),
    MouldID bigint NOT NULL,
    ActionCode varchar(30) NOT NULL,
    ChangedBy nvarchar(200) NOT NULL,
    ChangedAt datetimeoffset(0) NOT NULL,
    ChangeReason nvarchar(500) NOT NULL,
    PreviousStateJson nvarchar(max) NULL,
    NewStateJson nvarchar(max) NULL,
    CONSTRAINT FK_MouldHistory_Mould FOREIGN KEY (MouldID) REFERENCES omagmes.Mould(id),
    CONSTRAINT CK_MouldHistory_Reason CHECK (LEN(LTRIM(RTRIM(ChangeReason))) > 0)
);
CREATE INDEX IX_MouldHistory_Mould_ChangedAt ON omagmes.MouldHistory(MouldID, ChangedAt DESC, id DESC);
COMMIT TRANSACTION;
GO
