/*
Additive Shift Type schedules and per-Production-Date Shift Type assignments for OmagMES.
Target: verified OMAG database; uses existing immutable Shift identities, cutoff versions,
configuration history, and runtime role. Existing schedules/cutoff/history are never updated or deleted.
Three confirmed types are seeded idempotently; no daily Production Date assignment is seeded.
*/
SET NOCOUNT ON;
SET XACT_ABORT ON;
IF DB_NAME() <> N'OMAG' THROW 54400, 'This Shift Type deployment only runs in database OMAG.', 1;
IF SCHEMA_ID(N'omagmes') IS NULL THROW 54401, 'Required omagmes schema is missing.', 1;
IF OBJECT_ID(N'omagmes.Shift', N'U') IS NULL OR OBJECT_ID(N'omagmes.ShiftScheduleVersion', N'U') IS NULL
   OR OBJECT_ID(N'omagmes.ShiftScheduleShift', N'U') IS NULL OR OBJECT_ID(N'omagmes.ProductionDayCutoffVersion', N'U') IS NULL
   OR OBJECT_ID(N'omagmes.ConfigurationChangeHistory', N'U') IS NULL
    THROW 54402, 'Required existing Shift, cutoff, and configuration history tables are missing; deployment refused.', 1;
IF DATABASE_PRINCIPAL_ID(N'omagmes_config_runtime_role') IS NULL
    THROW 54403, 'The existing configuration runtime role is missing; deployment refused.', 1;
BEGIN TRY
    BEGIN TRANSACTION;

    IF OBJECT_ID(N'omagmes.ShiftType', N'U') IS NULL
    BEGIN
        CREATE TABLE omagmes.ShiftType (
            id bigint IDENTITY(1,1) NOT NULL CONSTRAINT PK_ShiftType PRIMARY KEY,
            Rectime datetime NOT NULL CONSTRAINT DF_ShiftType_Rectime DEFAULT (GETDATE()),
            TypeCode nvarchar(20) NOT NULL,
            Description nvarchar(200) NOT NULL,
            IsActive bit NOT NULL CONSTRAINT DF_ShiftType_IsActive DEFAULT (1),
            CONSTRAINT UQ_ShiftType_TypeCode UNIQUE (TypeCode),
            CONSTRAINT CK_ShiftType_Code CHECK (TypeCode IN (N'TYPE 1',N'TYPE 2',N'TYPE 3'))
        );
    END;
    IF COL_LENGTH(N'omagmes.ShiftType',N'id') IS NULL OR COL_LENGTH(N'omagmes.ShiftType',N'Rectime') IS NULL
       OR COL_LENGTH(N'omagmes.ShiftType',N'TypeCode') IS NULL OR COL_LENGTH(N'omagmes.ShiftType',N'Description') IS NULL
       OR COL_LENGTH(N'omagmes.ShiftType',N'IsActive') IS NULL
        THROW 54405, 'Existing ShiftType table is incompatible; deployment refused.', 1;

    IF OBJECT_ID(N'omagmes.ShiftTypeScheduleVersion', N'U') IS NULL
    BEGIN
        CREATE TABLE omagmes.ShiftTypeScheduleVersion (
            id bigint IDENTITY(1,1) NOT NULL CONSTRAINT PK_ShiftTypeScheduleVersion PRIMARY KEY,
            Rectime datetime NOT NULL CONSTRAINT DF_ShiftTypeScheduleVersion_Rectime DEFAULT (GETDATE()),
            ShiftTypeID bigint NOT NULL,
            VersionNo int NOT NULL,
            EffectiveFromProductionDate date NOT NULL,
            CreatedAt datetime2(0) NOT NULL CONSTRAINT DF_ShiftTypeScheduleVersion_CreatedAt DEFAULT (SYSUTCDATETIME()),
            CreatedBy nvarchar(200) NOT NULL,
            ChangeReason nvarchar(500) NOT NULL,
            CONSTRAINT FK_ShiftTypeScheduleVersion_Type FOREIGN KEY (ShiftTypeID) REFERENCES omagmes.ShiftType(id),
            CONSTRAINT UQ_ShiftTypeScheduleVersion_Type_Version UNIQUE (ShiftTypeID,VersionNo),
            CONSTRAINT UQ_ShiftTypeScheduleVersion_Type_Effective UNIQUE (ShiftTypeID,EffectiveFromProductionDate),
            CONSTRAINT UQ_ShiftTypeScheduleVersion_ID_Type UNIQUE (id,ShiftTypeID),
            CONSTRAINT CK_ShiftTypeScheduleVersion_No CHECK (VersionNo > 0),
            CONSTRAINT CK_ShiftTypeScheduleVersion_Reason CHECK (LEN(LTRIM(RTRIM(ChangeReason))) > 0)
        );
        CREATE INDEX IX_ShiftTypeScheduleVersion_Type_Effective
            ON omagmes.ShiftTypeScheduleVersion(ShiftTypeID,EffectiveFromProductionDate DESC,VersionNo DESC);
    END;
    IF COL_LENGTH(N'omagmes.ShiftTypeScheduleVersion',N'id') IS NULL OR COL_LENGTH(N'omagmes.ShiftTypeScheduleVersion',N'Rectime') IS NULL
       OR COL_LENGTH(N'omagmes.ShiftTypeScheduleVersion',N'ShiftTypeID') IS NULL OR COL_LENGTH(N'omagmes.ShiftTypeScheduleVersion',N'VersionNo') IS NULL
       OR COL_LENGTH(N'omagmes.ShiftTypeScheduleVersion',N'EffectiveFromProductionDate') IS NULL
        THROW 54406, 'Existing ShiftTypeScheduleVersion table is incompatible; deployment refused.', 1;

    IF OBJECT_ID(N'omagmes.ShiftTypeSchedulePeriod', N'U') IS NULL
    BEGIN
        CREATE TABLE omagmes.ShiftTypeSchedulePeriod (
            id bigint IDENTITY(1,1) NOT NULL CONSTRAINT PK_ShiftTypeSchedulePeriod PRIMARY KEY,
            Rectime datetime NOT NULL CONSTRAINT DF_ShiftTypeSchedulePeriod_Rectime DEFAULT (GETDATE()),
            ShiftTypeScheduleVersionID bigint NOT NULL,
            ShiftTypeID bigint NOT NULL,
            ShiftID bigint NOT NULL,
            ShiftNumber tinyint NOT NULL,
            PeriodOrder int NOT NULL,
            StartTime time(0) NOT NULL,
            EndTime time(0) NOT NULL,
            EndNextDay bit NOT NULL CONSTRAINT DF_ShiftTypeSchedulePeriod_EndNextDay DEFAULT (0),
            IsActive bit NOT NULL CONSTRAINT DF_ShiftTypeSchedulePeriod_IsActive DEFAULT (1),
            CONSTRAINT FK_ShiftTypeSchedulePeriod_VersionType FOREIGN KEY (ShiftTypeScheduleVersionID,ShiftTypeID)
                REFERENCES omagmes.ShiftTypeScheduleVersion(id,ShiftTypeID),
            CONSTRAINT FK_ShiftTypeSchedulePeriod_Shift FOREIGN KEY (ShiftID) REFERENCES omagmes.Shift(id),
            CONSTRAINT UQ_ShiftTypeSchedulePeriod_Version_Order UNIQUE (ShiftTypeScheduleVersionID,PeriodOrder),
            CONSTRAINT UQ_ShiftTypeSchedulePeriod_Version_Number UNIQUE (ShiftTypeScheduleVersionID,ShiftNumber),
            CONSTRAINT CK_ShiftTypeSchedulePeriod_ShiftNumber CHECK (ShiftNumber BETWEEN 1 AND 9),
            CONSTRAINT CK_ShiftTypeSchedulePeriod_Order CHECK (PeriodOrder > 0),
            CONSTRAINT CK_ShiftTypeSchedulePeriod_Duration CHECK
                ((EndNextDay=0 AND EndTime>StartTime) OR (EndNextDay=1 AND EndTime<StartTime))
        );
        CREATE INDEX IX_ShiftTypeSchedulePeriod_Version_Time
            ON omagmes.ShiftTypeSchedulePeriod(ShiftTypeScheduleVersionID,IsActive,StartTime,EndTime);
    END;
    IF COL_LENGTH(N'omagmes.ShiftTypeSchedulePeriod',N'id') IS NULL OR COL_LENGTH(N'omagmes.ShiftTypeSchedulePeriod',N'Rectime') IS NULL
       OR COL_LENGTH(N'omagmes.ShiftTypeSchedulePeriod',N'ShiftTypeScheduleVersionID') IS NULL
       OR COL_LENGTH(N'omagmes.ShiftTypeSchedulePeriod',N'ShiftTypeID') IS NULL OR COL_LENGTH(N'omagmes.ShiftTypeSchedulePeriod',N'ShiftID') IS NULL
       OR COL_LENGTH(N'omagmes.ShiftTypeSchedulePeriod',N'ShiftNumber') IS NULL OR COL_LENGTH(N'omagmes.ShiftTypeSchedulePeriod',N'EndNextDay') IS NULL
        THROW 54407, 'Existing ShiftTypeSchedulePeriod table is incompatible; deployment refused.', 1;

    IF OBJECT_ID(N'omagmes.DailyShiftTypeAssignment', N'U') IS NULL
    BEGIN
        CREATE TABLE omagmes.DailyShiftTypeAssignment (
            id bigint IDENTITY(1,1) NOT NULL CONSTRAINT PK_DailyShiftTypeAssignment PRIMARY KEY,
            Rectime datetime NOT NULL CONSTRAINT DF_DailyShiftTypeAssignment_Rectime DEFAULT (GETDATE()),
            ProductionDate date NOT NULL,
            AssignmentVersionNo int NOT NULL,
            ShiftTypeID bigint NOT NULL,
            ShiftTypeScheduleVersionID bigint NOT NULL,
            ProductionDayCutoffVersionID bigint NOT NULL,
            CreatedAt datetime2(0) NOT NULL CONSTRAINT DF_DailyShiftTypeAssignment_CreatedAt DEFAULT (SYSUTCDATETIME()),
            CreatedBy nvarchar(200) NOT NULL,
            ChangeReason nvarchar(500) NOT NULL,
            CONSTRAINT FK_DailyShiftTypeAssignment_Type FOREIGN KEY (ShiftTypeID) REFERENCES omagmes.ShiftType(id),
            CONSTRAINT FK_DailyShiftTypeAssignment_TypeVersion FOREIGN KEY (ShiftTypeScheduleVersionID,ShiftTypeID)
                REFERENCES omagmes.ShiftTypeScheduleVersion(id,ShiftTypeID),
            CONSTRAINT FK_DailyShiftTypeAssignment_Cutoff FOREIGN KEY (ProductionDayCutoffVersionID)
                REFERENCES omagmes.ProductionDayCutoffVersion(id),
            CONSTRAINT UQ_DailyShiftTypeAssignment_Date_Version UNIQUE (ProductionDate,AssignmentVersionNo),
            CONSTRAINT CK_DailyShiftTypeAssignment_Version CHECK (AssignmentVersionNo > 0),
            CONSTRAINT CK_DailyShiftTypeAssignment_Reason CHECK (LEN(LTRIM(RTRIM(ChangeReason))) > 0)
        );
        CREATE INDEX IX_DailyShiftTypeAssignment_Date_Current
            ON omagmes.DailyShiftTypeAssignment(ProductionDate,AssignmentVersionNo DESC,id DESC);
    END;
    IF COL_LENGTH(N'omagmes.DailyShiftTypeAssignment',N'id') IS NULL OR COL_LENGTH(N'omagmes.DailyShiftTypeAssignment',N'Rectime') IS NULL
       OR COL_LENGTH(N'omagmes.DailyShiftTypeAssignment',N'ProductionDate') IS NULL
       OR COL_LENGTH(N'omagmes.DailyShiftTypeAssignment',N'AssignmentVersionNo') IS NULL
       OR COL_LENGTH(N'omagmes.DailyShiftTypeAssignment',N'ShiftTypeID') IS NULL
       OR COL_LENGTH(N'omagmes.DailyShiftTypeAssignment',N'ShiftTypeScheduleVersionID') IS NULL
       OR COL_LENGTH(N'omagmes.DailyShiftTypeAssignment',N'ProductionDayCutoffVersionID') IS NULL
        THROW 54408, 'Existing DailyShiftTypeAssignment table is incompatible; deployment refused.', 1;

    /* Resolve stable Shift IDs from the latest existing schedule; never infer identity from ID values. */
    DECLARE @ShiftMap table (ShiftNumber tinyint PRIMARY KEY, ShiftID bigint NOT NULL);
    DECLARE @LatestLegacyVersionID bigint;
    SELECT TOP (1) @LatestLegacyVersionID=id FROM omagmes.ShiftScheduleVersion
        ORDER BY EffectiveFromProductionDate DESC,id DESC;
    IF @LatestLegacyVersionID IS NULL THROW 54409, 'No existing Shift Schedule version is available for stable Shift identity reuse.', 1;
    IF (SELECT COUNT(DISTINCT ShiftID) FROM omagmes.ShiftScheduleShift WHERE ShiftScheduleVersionID=@LatestLegacyVersionID AND ShiftCode IN (N'1',N'2')) <> 2
        THROW 54410, 'Latest existing Shift Schedule must contain exactly one stable Shift 1 and Shift 2 identity.', 1;
    INSERT INTO @ShiftMap(ShiftNumber,ShiftID)
        SELECT CONVERT(tinyint,ShiftCode),ShiftID FROM omagmes.ShiftScheduleShift
        WHERE ShiftScheduleVersionID=@LatestLegacyVersionID AND ShiftCode IN (N'1',N'2');
    IF (SELECT COUNT(DISTINCT ShiftID) FROM omagmes.ShiftScheduleShift WHERE ShiftCode=N'3') > 1
        THROW 54411, 'Multiple stable identities use Shift Code 3; deployment refused.', 1;
    IF EXISTS (SELECT 1 FROM omagmes.ShiftScheduleShift WHERE ShiftCode=N'3')
        INSERT INTO @ShiftMap(ShiftNumber,ShiftID)
            SELECT 3,MIN(ShiftID) FROM omagmes.ShiftScheduleShift WHERE ShiftCode=N'3';
    ELSE IF (SELECT COUNT(DISTINCT ShiftID) FROM omagmes.ShiftTypeSchedulePeriod WHERE ShiftNumber=3)=1
        INSERT INTO @ShiftMap(ShiftNumber,ShiftID)
            SELECT 3,MIN(ShiftID) FROM omagmes.ShiftTypeSchedulePeriod WHERE ShiftNumber=3;
    ELSE IF EXISTS (SELECT 1 FROM omagmes.ShiftTypeSchedulePeriod WHERE ShiftNumber=3)
        THROW 54420, 'Multiple stable identities use Shift Number 3; deployment refused.', 1;
    ELSE
    BEGIN
        INSERT INTO omagmes.Shift DEFAULT VALUES;
        INSERT INTO @ShiftMap(ShiftNumber,ShiftID) VALUES (3,CONVERT(bigint,SCOPE_IDENTITY()));
    END;

    /* Insert missing Type codes only; existing descriptions/IDs are never overwritten. */
    INSERT INTO omagmes.ShiftType(TypeCode,Description,IsActive)
    SELECT v.TypeCode,v.Description,1 FROM (VALUES
        (N'TYPE 1',N'ONE SHIFT'),(N'TYPE 2',N'TWO SHIFTS'),(N'TYPE 3',N'TWO SHIFTS, OVERNIGHT')
    ) v(TypeCode,Description)
    WHERE NOT EXISTS (SELECT 1 FROM omagmes.ShiftType t WHERE t.TypeCode=v.TypeCode);
    IF (SELECT COUNT(*) FROM omagmes.ShiftType WHERE TypeCode IN (N'TYPE 1',N'TYPE 2',N'TYPE 3'))<>3
        THROW 54412, 'Shift Type master codes are missing or duplicated; deployment refused.', 1;

    /* Initial effective versions are inserted only for a Type with no schedule history. */
    DECLARE @TypeSeeds table(TypeCode nvarchar(20),VersionID bigint,VersionNo int);
    DECLARE @TypeID bigint,@TypeCode nvarchar(20),@VersionID bigint,@VersionNo int;
    DECLARE type_cursor CURSOR LOCAL FAST_FORWARD FOR
        SELECT id,TypeCode FROM omagmes.ShiftType WHERE TypeCode IN (N'TYPE 1',N'TYPE 2',N'TYPE 3') ORDER BY TypeCode;
    OPEN type_cursor; FETCH NEXT FROM type_cursor INTO @TypeID,@TypeCode;
    WHILE @@FETCH_STATUS=0
    BEGIN
        IF NOT EXISTS (SELECT 1 FROM omagmes.ShiftTypeScheduleVersion WHERE ShiftTypeID=@TypeID)
        BEGIN
            SET @VersionNo=1;
            INSERT INTO omagmes.ShiftTypeScheduleVersion(ShiftTypeID,VersionNo,EffectiveFromProductionDate,CreatedBy,ChangeReason)
            VALUES(@TypeID,@VersionNo,'2026-11-10',N'OMAGMES FACTORY-CONFIRMED INITIAL CONFIGURATION',N'Factory-confirmed initial Shift Type periods');
            SET @VersionID=CONVERT(bigint,SCOPE_IDENTITY());
            DECLARE @Periods table(ShiftNumber tinyint,PeriodOrder int,StartTime time(0),EndTime time(0),EndNextDay bit);
            DELETE FROM @Periods;
            IF @TypeCode=N'TYPE 1' INSERT INTO @Periods VALUES(1,1,'08:00','16:00',0);
            IF @TypeCode=N'TYPE 2' INSERT INTO @Periods VALUES(1,1,'08:00','16:00',0),(2,2,'16:00','00:00',1);
            IF @TypeCode=N'TYPE 3' INSERT INTO @Periods VALUES(3,1,'08:00','20:00',0),(2,2,'20:00','08:00',1);
            INSERT INTO omagmes.ShiftTypeSchedulePeriod(ShiftTypeScheduleVersionID,ShiftTypeID,ShiftID,ShiftNumber,PeriodOrder,StartTime,EndTime,EndNextDay,IsActive)
                SELECT @VersionID,@TypeID,m.ShiftID,p.ShiftNumber,p.PeriodOrder,p.StartTime,p.EndTime,p.EndNextDay,1
                FROM @Periods p JOIN @ShiftMap m ON m.ShiftNumber=p.ShiftNumber;
            SET @VersionNo=1;
            INSERT INTO @TypeSeeds(TypeCode,VersionID,VersionNo) VALUES(@TypeCode,@VersionID,@VersionNo);
        END;
        FETCH NEXT FROM type_cursor INTO @TypeID,@TypeCode;
    END;
    CLOSE type_cursor; DEALLOCATE type_cursor;

    /* Protect all schedule/version/master rows and assignment history from UPDATE/DELETE. */
    IF OBJECT_ID(N'omagmes.TR_ShiftType_Immutable',N'TR') IS NULL
        EXEC(N'CREATE TRIGGER omagmes.TR_ShiftType_Immutable ON omagmes.ShiftType AFTER UPDATE,DELETE AS BEGIN SET NOCOUNT ON; THROW 54413,''Shift Type master identities are append-only.'',1; END;');
    ELSE ENABLE TRIGGER omagmes.TR_ShiftType_Immutable ON omagmes.ShiftType;
    IF OBJECT_ID(N'omagmes.TR_ShiftTypeScheduleVersion_Immutable',N'TR') IS NULL
        EXEC(N'CREATE TRIGGER omagmes.TR_ShiftTypeScheduleVersion_Immutable ON omagmes.ShiftTypeScheduleVersion AFTER UPDATE,DELETE AS BEGIN SET NOCOUNT ON; THROW 54414,''Shift Type schedule versions are append-only.'',1; END;');
    ELSE ENABLE TRIGGER omagmes.TR_ShiftTypeScheduleVersion_Immutable ON omagmes.ShiftTypeScheduleVersion;
    IF OBJECT_ID(N'omagmes.TR_ShiftTypeSchedulePeriod_Immutable',N'TR') IS NULL
        EXEC(N'CREATE TRIGGER omagmes.TR_ShiftTypeSchedulePeriod_Immutable ON omagmes.ShiftTypeSchedulePeriod AFTER UPDATE,DELETE AS BEGIN SET NOCOUNT ON; THROW 54415,''Shift Type schedule periods are append-only.'',1; END;');
    ELSE ENABLE TRIGGER omagmes.TR_ShiftTypeSchedulePeriod_Immutable ON omagmes.ShiftTypeSchedulePeriod;
    IF OBJECT_ID(N'omagmes.TR_DailyShiftTypeAssignment_Immutable',N'TR') IS NULL
        EXEC(N'CREATE TRIGGER omagmes.TR_DailyShiftTypeAssignment_Immutable ON omagmes.DailyShiftTypeAssignment AFTER UPDATE,DELETE AS BEGIN SET NOCOUNT ON; THROW 54416,''Daily Shift Type assignments are append-only.'',1; END;');
    ELSE ENABLE TRIGGER omagmes.TR_DailyShiftTypeAssignment_Immutable ON omagmes.DailyShiftTypeAssignment;

    IF OBJECT_ID(N'omagmes.TR_ShiftTypeSchedulePeriod_NoOverlap',N'TR') IS NULL
    EXEC(N'CREATE TRIGGER omagmes.TR_ShiftTypeSchedulePeriod_NoOverlap ON omagmes.ShiftTypeSchedulePeriod AFTER INSERT AS
    BEGIN
      SET NOCOUNT ON;
            IF EXISTS(SELECT 1 FROM
                                (SELECT p.id,p.ShiftTypeScheduleVersionID,p.IsActive,
                                                CASE WHEN n.SegmentNo=1 THEN DATEDIFF(MINUTE,CONVERT(time(0),''00:00''),p.StartTime) ELSE 0 END AS StartMinute,
                                                CASE WHEN n.SegmentNo=1 THEN CASE WHEN p.EndNextDay=1 THEN 1440 ELSE DATEDIFF(MINUTE,CONVERT(time(0),''00:00''),p.EndTime) END
                                                         ELSE DATEDIFF(MINUTE,CONVERT(time(0),''00:00''),p.EndTime) END AS EndMinute
                                 FROM omagmes.ShiftTypeSchedulePeriod p
                                 JOIN (VALUES(1),(2)) n(SegmentNo) ON n.SegmentNo=1 OR p.EndNextDay=1
                                 WHERE p.ShiftTypeScheduleVersionID IN (SELECT DISTINCT ShiftTypeScheduleVersionID FROM inserted)) a
                                JOIN
                                (SELECT p.id,p.ShiftTypeScheduleVersionID,p.IsActive,
                                                CASE WHEN n.SegmentNo=1 THEN DATEDIFF(MINUTE,CONVERT(time(0),''00:00''),p.StartTime) ELSE 0 END AS StartMinute,
                                                CASE WHEN n.SegmentNo=1 THEN CASE WHEN p.EndNextDay=1 THEN 1440 ELSE DATEDIFF(MINUTE,CONVERT(time(0),''00:00''),p.EndTime) END
                                                         ELSE DATEDIFF(MINUTE,CONVERT(time(0),''00:00''),p.EndTime) END AS EndMinute
                                 FROM omagmes.ShiftTypeSchedulePeriod p
                                 JOIN (VALUES(1),(2)) n(SegmentNo) ON n.SegmentNo=1 OR p.EndNextDay=1
                                 WHERE p.ShiftTypeScheduleVersionID IN (SELECT DISTINCT ShiftTypeScheduleVersionID FROM inserted)) b
                                ON a.ShiftTypeScheduleVersionID=b.ShiftTypeScheduleVersionID AND a.id<b.id
                WHERE a.IsActive=1 AND b.IsActive=1 AND a.StartMinute<b.EndMinute AND b.StartMinute<a.EndMinute)
        THROW 54417,''Active Shift Type periods cannot overlap.'',1;
    END;');
    ELSE ENABLE TRIGGER omagmes.TR_ShiftTypeSchedulePeriod_NoOverlap ON omagmes.ShiftTypeSchedulePeriod;

    /* Write initial schedule audit events only when this deployment created the version. */
    INSERT INTO omagmes.ConfigurationChangeHistory(ConfigurationType,ConfigurationIdentity,VersionID,OldValue,NewValue,ChangedBy,EffectiveFromProductionDate,ChangeReason)
    SELECT N'SHIFT_TYPE_SCHEDULE',s.TypeCode,v.VersionID,NULL,
           (SELECT p.ShiftNumber AS shift_number,p.PeriodOrder AS period_order,CONVERT(varchar(5),p.StartTime,108) AS start_time,
                   CONVERT(varchar(5),p.EndTime,108) AS end_time,p.EndNextDay AS end_next_day
            FROM omagmes.ShiftTypeSchedulePeriod p WHERE p.ShiftTypeScheduleVersionID=v.VersionID ORDER BY p.PeriodOrder FOR JSON PATH),
           N'OMAGMES FACTORY-CONFIRMED INITIAL CONFIGURATION','2026-11-10',N'Factory-confirmed initial Shift Type periods'
    FROM @TypeSeeds v JOIN omagmes.ShiftType s ON s.TypeCode=v.TypeCode;

    GRANT SELECT,INSERT ON OBJECT::omagmes.ShiftType TO omagmes_config_runtime_role;
    GRANT SELECT,INSERT ON OBJECT::omagmes.ShiftTypeScheduleVersion TO omagmes_config_runtime_role;
    GRANT SELECT,INSERT ON OBJECT::omagmes.ShiftTypeSchedulePeriod TO omagmes_config_runtime_role;
    GRANT SELECT,INSERT ON OBJECT::omagmes.DailyShiftTypeAssignment TO omagmes_config_runtime_role;
    GRANT SELECT,INSERT ON OBJECT::omagmes.Shift TO omagmes_config_runtime_role;
    GRANT SELECT,INSERT ON OBJECT::omagmes.ConfigurationChangeHistory TO omagmes_config_runtime_role;

    IF (SELECT COUNT(*) FROM omagmes.ShiftType WHERE TypeCode IN (N'TYPE 1',N'TYPE 2',N'TYPE 3'))<>3
        THROW 54418,'Shift Type seed verification failed.',1;
    IF EXISTS(SELECT 1 FROM omagmes.ShiftType t WHERE t.TypeCode IN (N'TYPE 1',N'TYPE 2',N'TYPE 3')
              AND NOT EXISTS(SELECT 1 FROM omagmes.ShiftTypeScheduleVersion v JOIN omagmes.ShiftTypeSchedulePeriod p ON p.ShiftTypeScheduleVersionID=v.id WHERE v.ShiftTypeID=t.id))
        THROW 54419,'A Shift Type has no persisted schedule version and periods.',1;

    COMMIT TRANSACTION;
END TRY
BEGIN CATCH
    IF XACT_STATE()<>0 ROLLBACK TRANSACTION;
    IF CURSOR_STATUS('local','type_cursor')>=0 CLOSE type_cursor;
    IF CURSOR_STATUS('local','type_cursor')>-3 DEALLOCATE type_cursor;
    THROW;
END CATCH;

SELECT t.TypeCode,t.id AS ShiftTypeID,v.id AS ScheduleVersionID,v.VersionNo,v.EffectiveFromProductionDate,
       p.id AS PeriodID,p.ShiftID,p.ShiftNumber,p.PeriodOrder,p.StartTime,p.EndTime,p.EndNextDay,p.IsActive
FROM omagmes.ShiftType t
JOIN omagmes.ShiftTypeScheduleVersion v ON v.ShiftTypeID=t.id
JOIN omagmes.ShiftTypeSchedulePeriod p ON p.ShiftTypeScheduleVersionID=v.id
WHERE t.TypeCode IN (N'TYPE 1',N'TYPE 2',N'TYPE 3')
ORDER BY t.TypeCode,v.VersionNo,p.PeriodOrder;
SELECT N'DailyShiftTypeAssignment' AS ObjectName,COUNT_BIG(*) AS ExistingRows FROM omagmes.DailyShiftTypeAssignment;
