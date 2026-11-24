/*
REVIEW-ONLY DRAFT — DO NOT EXECUTE.
Version: 002 / 2026-11-08
Target: SQL Server database OMAG, application schema omagmes.
Requires reviewed migration 001 to have been separately approved and applied.
Not SQL Server parsed, DBA reviewed, owner approved, or executed. No seed rows are included:
factory owners must approve the initial cutoff effective date and Shift Schedule before bootstrap.
*/
SET XACT_ABORT ON;
GO
IF DB_NAME() <> N'OMAG'
    THROW 51200, 'Review draft targets database OMAG only; execution stopped.', 1;
IF SCHEMA_ID(N'omagmes') IS NULL
    THROW 51201, 'Required omagmes schema is missing; review migration 001 first.', 1;
IF OBJECT_ID(N'omagmes.ProductionDayCutoffVersion', N'U') IS NOT NULL
   OR OBJECT_ID(N'omagmes.Shift', N'U') IS NOT NULL
   OR OBJECT_ID(N'omagmes.ShiftScheduleVersion', N'U') IS NOT NULL
   OR OBJECT_ID(N'omagmes.ShiftScheduleShift', N'U') IS NOT NULL
    THROW 51202, 'One or more configuration tables already exist; inspect actual state before proceeding.', 1;
GO
BEGIN TRANSACTION;
GO
CREATE TABLE omagmes.ProductionDayCutoffVersion (
    id bigint IDENTITY(1,1) NOT NULL CONSTRAINT PK_ProductionDayCutoffVersion PRIMARY KEY,
    Rectime datetime NOT NULL CONSTRAINT DF_ProductionDayCutoffVersion_Rectime DEFAULT (GETDATE()),
    EffectiveFromProductionDate date NOT NULL,
    CutoffTime time(0) NOT NULL,
    CreatedAt datetime2(0) NOT NULL CONSTRAINT DF_ProductionDayCutoffVersion_CreatedAt DEFAULT (SYSUTCDATETIME()),
    CreatedBy nvarchar(200) NOT NULL,
    ChangeReason nvarchar(500) NOT NULL,
    CONSTRAINT UQ_ProductionDayCutoffVersion_EffectiveDate UNIQUE (EffectiveFromProductionDate),
    CONSTRAINT CK_ProductionDayCutoffVersion_MinutePrecision CHECK (DATEPART(SECOND, CutoffTime) = 0),
    CONSTRAINT CK_ProductionDayCutoffVersion_Reason CHECK (LEN(LTRIM(RTRIM(ChangeReason))) > 0)
);
GO
CREATE TABLE omagmes.Shift (
    id bigint IDENTITY(1,1) NOT NULL CONSTRAINT PK_Shift PRIMARY KEY,
    Rectime datetime NOT NULL CONSTRAINT DF_Shift_Rectime DEFAULT (GETDATE())
);
GO
CREATE TABLE omagmes.ShiftScheduleVersion (
    id bigint IDENTITY(1,1) NOT NULL CONSTRAINT PK_ShiftScheduleVersion PRIMARY KEY,
    Rectime datetime NOT NULL CONSTRAINT DF_ShiftScheduleVersion_Rectime DEFAULT (GETDATE()),
    EffectiveFromProductionDate date NOT NULL,
    CreatedAt datetime2(0) NOT NULL CONSTRAINT DF_ShiftScheduleVersion_CreatedAt DEFAULT (SYSUTCDATETIME()),
    CreatedBy nvarchar(200) NOT NULL,
    ChangeReason nvarchar(500) NOT NULL,
    CONSTRAINT UQ_ShiftScheduleVersion_EffectiveDate UNIQUE (EffectiveFromProductionDate),
    CONSTRAINT CK_ShiftScheduleVersion_Reason CHECK (LEN(LTRIM(RTRIM(ChangeReason))) > 0)
);
GO
CREATE TABLE omagmes.ShiftScheduleShift (
    id bigint IDENTITY(1,1) NOT NULL CONSTRAINT PK_ShiftScheduleShift PRIMARY KEY,
    Rectime datetime NOT NULL CONSTRAINT DF_ShiftScheduleShift_Rectime DEFAULT (GETDATE()),
    ShiftScheduleVersionID bigint NOT NULL,
    ShiftID bigint NOT NULL,
    ShiftName nvarchar(100) NOT NULL,
    ShiftCode nvarchar(40) COLLATE Latin1_General_100_BIN2 NOT NULL,
    StartTime time(0) NOT NULL,
    EndTime time(0) NOT NULL,
    DisplayOrder int NOT NULL,
    IsActive bit NOT NULL CONSTRAINT DF_ShiftScheduleShift_IsActive DEFAULT (1),
    CONSTRAINT FK_ShiftScheduleShift_Version FOREIGN KEY (ShiftScheduleVersionID) REFERENCES omagmes.ShiftScheduleVersion(id),
    CONSTRAINT FK_ShiftScheduleShift_Shift FOREIGN KEY (ShiftID) REFERENCES omagmes.Shift(id),
    CONSTRAINT UQ_ShiftScheduleShift_Version_Shift UNIQUE (ShiftScheduleVersionID, ShiftID),
    CONSTRAINT UQ_ShiftScheduleShift_Version_Code UNIQUE (ShiftScheduleVersionID, ShiftCode),
    CONSTRAINT UQ_ShiftScheduleShift_Version_Order UNIQUE (ShiftScheduleVersionID, DisplayOrder),
    CONSTRAINT CK_ShiftScheduleShift_DisplayOrder CHECK (DisplayOrder > 0),
    CONSTRAINT CK_ShiftScheduleShift_MinutePrecision CHECK (DATEPART(SECOND, StartTime) = 0 AND DATEPART(SECOND, EndTime) = 0)
);
GO
CREATE INDEX IX_ProductionDayCutoffVersion_EffectiveDate
    ON omagmes.ProductionDayCutoffVersion(EffectiveFromProductionDate DESC, id DESC);
CREATE INDEX IX_ShiftScheduleVersion_EffectiveDate
    ON omagmes.ShiftScheduleVersion(EffectiveFromProductionDate DESC, id DESC);
CREATE INDEX IX_ShiftScheduleShift_Shift_Version
    ON omagmes.ShiftScheduleShift(ShiftID, ShiftScheduleVersionID);
GO
/*
Defense-in-depth against accidental mutation. Runtime principal permissions must
also deny UPDATE/DELETE and grant only scoped SELECT/INSERT after authorization is designed.
*/
EXEC(N'CREATE TRIGGER omagmes.TR_ProductionDayCutoffVersion_Immutable ON omagmes.ProductionDayCutoffVersion AFTER UPDATE, DELETE AS
BEGIN
    SET NOCOUNT ON;
    THROW 51210, ''Production Day Cutoff versions are append-only.'', 1;
END;');
GO
EXEC(N'CREATE TRIGGER omagmes.TR_ShiftScheduleVersion_Immutable ON omagmes.ShiftScheduleVersion AFTER UPDATE, DELETE AS
BEGIN
    SET NOCOUNT ON;
    THROW 51211, ''Shift Schedule versions are append-only.'', 1;
END;');
GO
EXEC(N'CREATE TRIGGER omagmes.TR_ShiftScheduleShift_Immutable ON omagmes.ShiftScheduleShift AFTER UPDATE, DELETE AS
BEGIN
    SET NOCOUNT ON;
    THROW 51212, ''Shift Schedule version rows are append-only.'', 1;
END;');
GO
EXEC(N'CREATE TRIGGER omagmes.TR_Shift_Immutable ON omagmes.Shift AFTER UPDATE, DELETE AS
BEGIN
    SET NOCOUNT ON;
    THROW 51213, ''Stable Shift identities cannot be changed or deleted.'', 1;
END;');
GO
COMMIT TRANSACTION;
GO
