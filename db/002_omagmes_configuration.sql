/*
REPEATABLE OmagMES configuration schema + initial bootstrap.
Target: OMAG database, omagmes schema. Application-owned objects only.
Owner approval: initial effective Production Date 2026-11-10.
Initial Production Day Cutoff: 07:00 Asia/Bangkok.
Initial Shift Schedule: Shift 1 08:00-19:00; Shift 2 19:00-06:00; remaining daily time is unassigned.
Safe to rerun: existing tables and version rows are preserved; seed is added only when each version stream is empty.
Does not read/write/alter any OMAG.dbo legacy table. Runtime role is limited to SELECT/INSERT on these four tables.
*/
SET NOCOUNT ON;
SET XACT_ABORT ON;
GO
IF DB_NAME() <> N'OMAG'
    THROW 52000, 'This OmagMES configuration script only runs in database OMAG.', 1;
GO
IF SCHEMA_ID(N'omagmes') IS NULL
    EXEC(N'CREATE SCHEMA omagmes AUTHORIZATION dbo;');
GO
BEGIN TRANSACTION;
GO
IF OBJECT_ID(N'omagmes.ProductionDayCutoffVersion', N'U') IS NULL
BEGIN
    CREATE TABLE omagmes.ProductionDayCutoffVersion (
        id bigint IDENTITY(1,1) NOT NULL CONSTRAINT PK_ProductionDayCutoffVersion PRIMARY KEY,
        Rectime datetime NOT NULL CONSTRAINT DF_ProductionDayCutoffVersion_Rectime DEFAULT (GETDATE()),
        EffectiveFromProductionDate date NOT NULL,
        CutoffTime time(0) NOT NULL,
        TimeZone nvarchar(64) NOT NULL,
        CreatedAt datetime2(0) NOT NULL CONSTRAINT DF_ProductionDayCutoffVersion_CreatedAt DEFAULT (SYSUTCDATETIME()),
        CreatedBy nvarchar(200) NOT NULL,
        ChangeReason nvarchar(500) NOT NULL,
        CONSTRAINT UQ_ProductionDayCutoffVersion_EffectiveDate UNIQUE (EffectiveFromProductionDate),
        CONSTRAINT CK_ProductionDayCutoffVersion_TimeZone CHECK (TimeZone = N'Asia/Bangkok'),
        CONSTRAINT CK_ProductionDayCutoffVersion_Reason CHECK (LEN(LTRIM(RTRIM(ChangeReason))) > 0)
    );
    CREATE INDEX IX_ProductionDayCutoffVersion_EffectiveDate
        ON omagmes.ProductionDayCutoffVersion(EffectiveFromProductionDate DESC, id DESC);
END;
GO
IF OBJECT_ID(N'omagmes.Shift', N'U') IS NULL
BEGIN
    CREATE TABLE omagmes.Shift (
        id bigint IDENTITY(1,1) NOT NULL CONSTRAINT PK_Shift PRIMARY KEY,
        Rectime datetime NOT NULL CONSTRAINT DF_Shift_Rectime DEFAULT (GETDATE())
    );
END;
GO
IF OBJECT_ID(N'omagmes.ShiftScheduleVersion', N'U') IS NULL
BEGIN
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
    CREATE INDEX IX_ShiftScheduleVersion_EffectiveDate
        ON omagmes.ShiftScheduleVersion(EffectiveFromProductionDate DESC, id DESC);
END;
GO
IF OBJECT_ID(N'omagmes.ShiftScheduleShift', N'U') IS NULL
BEGIN
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
        CONSTRAINT CK_ShiftScheduleShift_DisplayOrder CHECK (DisplayOrder > 0)
    );
    CREATE INDEX IX_ShiftScheduleShift_Shift_Version
        ON omagmes.ShiftScheduleShift(ShiftID, ShiftScheduleVersionID);
END;
GO
/* Refuse to silently run against an incompatible pre-existing object. */
IF COL_LENGTH(N'omagmes.ProductionDayCutoffVersion', N'TimeZone') IS NULL
   OR COL_LENGTH(N'omagmes.ProductionDayCutoffVersion', N'EffectiveFromProductionDate') IS NULL
   OR COL_LENGTH(N'omagmes.ShiftScheduleVersion', N'EffectiveFromProductionDate') IS NULL
   OR COL_LENGTH(N'omagmes.ShiftScheduleShift', N'ShiftID') IS NULL
    THROW 52001, 'An existing OmagMES configuration object is incompatible; inspect and migrate it explicitly.', 1;
GO
/* Initial cutoff seed: do not replace or rewrite any existing history. */
IF NOT EXISTS (SELECT 1 FROM omagmes.ProductionDayCutoffVersion WITH (UPDLOCK, HOLDLOCK))
BEGIN
    INSERT INTO omagmes.ProductionDayCutoffVersion
        (EffectiveFromProductionDate, CutoffTime, TimeZone, CreatedAt, CreatedBy, ChangeReason)
    VALUES
        ('2026-11-10', '07:00', N'Asia/Bangkok', SYSUTCDATETIME(), N'OMAGMES INITIAL BOOTSTRAP', N'Owner-approved initial Production Day Cutoff');
END;
GO
/* Initial schedule seed: capture generated opaque IDs; never assume identity values. */
IF NOT EXISTS (SELECT 1 FROM omagmes.ShiftScheduleVersion WITH (UPDLOCK, HOLDLOCK))
BEGIN
    DECLARE @NewShiftIDs table (Ordinal int NOT NULL PRIMARY KEY, ShiftID bigint NOT NULL);
    DECLARE @ScheduleVersionID bigint;

    INSERT INTO omagmes.Shift DEFAULT VALUES;
    INSERT INTO @NewShiftIDs (Ordinal, ShiftID) VALUES (1, CONVERT(bigint, SCOPE_IDENTITY()));

    INSERT INTO omagmes.Shift DEFAULT VALUES;
    INSERT INTO @NewShiftIDs (Ordinal, ShiftID) VALUES (2, CONVERT(bigint, SCOPE_IDENTITY()));

    INSERT INTO omagmes.ShiftScheduleVersion
        (EffectiveFromProductionDate, CreatedAt, CreatedBy, ChangeReason)
    VALUES
        ('2026-11-10', SYSUTCDATETIME(), N'OMAGMES INITIAL BOOTSTRAP', N'Owner-approved initial two-shift schedule');
    SET @ScheduleVersionID = CONVERT(bigint, SCOPE_IDENTITY());

    INSERT INTO omagmes.ShiftScheduleShift
        (ShiftScheduleVersionID, ShiftID, ShiftName, ShiftCode, StartTime, EndTime, DisplayOrder, IsActive)
    SELECT @ScheduleVersionID, ShiftID,
           CASE Ordinal WHEN 1 THEN N'Shift 1' ELSE N'Shift 2' END,
           CASE Ordinal WHEN 1 THEN N'1' ELSE N'2' END,
           CASE Ordinal WHEN 1 THEN CONVERT(time(0), '08:00') ELSE CONVERT(time(0), '19:00') END,
           CASE Ordinal WHEN 1 THEN CONVERT(time(0), '19:00') ELSE CONVERT(time(0), '06:00') END,
           Ordinal, 1
    FROM @NewShiftIDs;
END;
GO
/* Append-only defense in depth. Runtime role receives no UPDATE or DELETE grants. */
IF OBJECT_ID(N'omagmes.TR_ProductionDayCutoffVersion_Immutable', N'TR') IS NULL
    EXEC(N'CREATE TRIGGER omagmes.TR_ProductionDayCutoffVersion_Immutable ON omagmes.ProductionDayCutoffVersion AFTER UPDATE, DELETE AS
    BEGIN SET NOCOUNT ON; THROW 52010, ''Production Day Cutoff versions are append-only.'', 1; END;');
GO
IF OBJECT_ID(N'omagmes.TR_ShiftScheduleVersion_Immutable', N'TR') IS NULL
    EXEC(N'CREATE TRIGGER omagmes.TR_ShiftScheduleVersion_Immutable ON omagmes.ShiftScheduleVersion AFTER UPDATE, DELETE AS
    BEGIN SET NOCOUNT ON; THROW 52011, ''Shift Schedule versions are append-only.'', 1; END;');
GO
IF OBJECT_ID(N'omagmes.TR_ShiftScheduleShift_Immutable', N'TR') IS NULL
    EXEC(N'CREATE TRIGGER omagmes.TR_ShiftScheduleShift_Immutable ON omagmes.ShiftScheduleShift AFTER UPDATE, DELETE AS
    BEGIN SET NOCOUNT ON; THROW 52012, ''Shift Schedule version rows are append-only.'', 1; END;');
GO
IF OBJECT_ID(N'omagmes.TR_Shift_Immutable', N'TR') IS NULL
    EXEC(N'CREATE TRIGGER omagmes.TR_Shift_Immutable ON omagmes.Shift AFTER UPDATE, DELETE AS
    BEGIN SET NOCOUNT ON; THROW 52013, ''Stable Shift identities cannot be changed or deleted.'', 1; END;');
GO
/* A no-login database principal used by the internal development API via EXECUTE AS. */
IF DATABASE_PRINCIPAL_ID(N'omagmes_config_runtime_role') IS NULL
    CREATE ROLE omagmes_config_runtime_role AUTHORIZATION dbo;
GO
IF DATABASE_PRINCIPAL_ID(N'omagmes_config_runtime_user') IS NULL
    CREATE USER omagmes_config_runtime_user WITHOUT LOGIN;
GO
IF NOT EXISTS (
    SELECT 1
    FROM sys.database_role_members AS rm
    JOIN sys.database_principals AS r ON r.principal_id = rm.role_principal_id
    JOIN sys.database_principals AS m ON m.principal_id = rm.member_principal_id
    WHERE r.name = N'omagmes_config_runtime_role'
      AND m.name = N'omagmes_config_runtime_user'
)
    ALTER ROLE omagmes_config_runtime_role ADD MEMBER omagmes_config_runtime_user;
GO
GRANT SELECT, INSERT ON OBJECT::omagmes.ProductionDayCutoffVersion TO omagmes_config_runtime_role;
GRANT SELECT, INSERT ON OBJECT::omagmes.Shift TO omagmes_config_runtime_role;
GRANT SELECT, INSERT ON OBJECT::omagmes.ShiftScheduleVersion TO omagmes_config_runtime_role;
GRANT SELECT, INSERT ON OBJECT::omagmes.ShiftScheduleShift TO omagmes_config_runtime_role;
GO
COMMIT TRANSACTION;
GO
/* Seed verification result; deployment runner must confirm one initial row per stream. */
SELECT N'ProductionDayCutoffVersion' AS Configuration, COUNT_BIG(*) AS VersionCount,
       MIN(EffectiveFromProductionDate) AS FirstEffectiveDate, MAX(CutoffTime) AS CutoffTime, MAX(TimeZone) AS TimeZone
FROM omagmes.ProductionDayCutoffVersion;
SELECT N'ShiftScheduleVersion' AS Configuration,
       (SELECT COUNT_BIG(*) FROM omagmes.ShiftScheduleVersion) AS VersionCount,
       (SELECT MIN(EffectiveFromProductionDate) FROM omagmes.ShiftScheduleVersion) AS FirstEffectiveDate,
       (SELECT COUNT_BIG(*) FROM omagmes.ShiftScheduleShift) AS ShiftRows;
GO
