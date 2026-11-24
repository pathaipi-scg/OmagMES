/*
Additive OmagMES Setting support. Execute only against the verified OMAG database.
Creates missing Shift Period and configuration-change history tables; reuses only compatible objects.
Does not seed, update, or delete existing configuration or application data.
Existing whole-Shift schedule snapshots remain readable as their single legacy period.
*/
SET NOCOUNT ON;
SET XACT_ABORT ON;
IF DB_NAME() <> N'OMAG' THROW 54300, 'This OmagMES Setting deployment only runs in database OMAG.', 1;
IF SCHEMA_ID(N'omagmes') IS NULL THROW 54301, 'Required omagmes schema is missing.', 1;
IF OBJECT_ID(N'omagmes.Shift', N'U') IS NULL OR OBJECT_ID(N'omagmes.ShiftScheduleVersion', N'U') IS NULL OR OBJECT_ID(N'omagmes.ShiftScheduleShift', N'U') IS NULL OR OBJECT_ID(N'omagmes.ProductionDayCutoffVersion', N'U') IS NULL
    THROW 54302, 'Required existing Shift and cutoff tables are missing; deployment refused.', 1;
IF DATABASE_PRINCIPAL_ID(N'omagmes_config_runtime_role') IS NULL
    THROW 54303, 'The existing configuration runtime role is missing; deployment refused.', 1;
IF NOT EXISTS (
    SELECT 1
    FROM sys.indexes i
    JOIN sys.index_columns a ON a.object_id=i.object_id AND a.index_id=i.index_id AND a.key_ordinal=1
    JOIN sys.columns ca ON ca.object_id=a.object_id AND ca.column_id=a.column_id
    JOIN sys.index_columns b ON b.object_id=i.object_id AND b.index_id=i.index_id AND b.key_ordinal=2
    JOIN sys.columns cb ON cb.object_id=b.object_id AND cb.column_id=b.column_id
    WHERE i.object_id=OBJECT_ID(N'omagmes.ShiftScheduleShift') AND i.is_unique=1
      AND ca.name=N'ShiftScheduleVersionID' AND cb.name=N'ShiftID'
)
    THROW 54304, 'The existing schedule-to-Shift composite key is missing; deployment refused.', 1;
IF OBJECT_ID(N'omagmes.ShiftScheduleShiftPeriod') IS NOT NULL AND OBJECT_ID(N'omagmes.ShiftScheduleShiftPeriod', N'U') IS NULL
    THROW 54305, 'A non-table object already uses the Shift Period name; deployment refused.', 1;
IF OBJECT_ID(N'omagmes.ConfigurationChangeHistory') IS NOT NULL AND OBJECT_ID(N'omagmes.ConfigurationChangeHistory', N'U') IS NULL
    THROW 54306, 'A non-table object already uses the configuration history name; deployment refused.', 1;

BEGIN TRY
    BEGIN TRANSACTION;

    IF OBJECT_ID(N'omagmes.ShiftScheduleShiftPeriod', N'U') IS NULL
    BEGIN
        CREATE TABLE omagmes.ShiftScheduleShiftPeriod (
            id bigint IDENTITY(1,1) NOT NULL CONSTRAINT PK_ShiftScheduleShiftPeriod PRIMARY KEY,
            Rectime datetime NOT NULL CONSTRAINT DF_ShiftScheduleShiftPeriod_Rectime DEFAULT (GETDATE()),
            ShiftScheduleVersionID bigint NOT NULL,
            ShiftID bigint NOT NULL,
            PeriodOrder int NOT NULL,
            StartTime time(0) NOT NULL,
            EndTime time(0) NOT NULL,
            IsActive bit NOT NULL CONSTRAINT DF_ShiftScheduleShiftPeriod_IsActive DEFAULT (1),
            CONSTRAINT FK_ShiftScheduleShiftPeriod_ScheduleShift FOREIGN KEY (ShiftScheduleVersionID, ShiftID)
                REFERENCES omagmes.ShiftScheduleShift(ShiftScheduleVersionID, ShiftID),
            CONSTRAINT UQ_ShiftScheduleShiftPeriod_Version_Shift_Order UNIQUE (ShiftScheduleVersionID, ShiftID, PeriodOrder),
            CONSTRAINT CK_ShiftScheduleShiftPeriod_Order CHECK (PeriodOrder > 0),
            CONSTRAINT CK_ShiftScheduleShiftPeriod_Duration CHECK (StartTime <> EndTime)
        );
        CREATE INDEX IX_ShiftScheduleShiftPeriod_Version_Time
            ON omagmes.ShiftScheduleShiftPeriod(ShiftScheduleVersionID, IsActive, StartTime, EndTime, ShiftID);
    END;
    IF COL_LENGTH(N'omagmes.ShiftScheduleShiftPeriod', N'id') IS NULL
       OR COL_LENGTH(N'omagmes.ShiftScheduleShiftPeriod', N'Rectime') IS NULL
       OR COL_LENGTH(N'omagmes.ShiftScheduleShiftPeriod', N'ShiftScheduleVersionID') IS NULL
       OR COL_LENGTH(N'omagmes.ShiftScheduleShiftPeriod', N'ShiftID') IS NULL
       OR COL_LENGTH(N'omagmes.ShiftScheduleShiftPeriod', N'PeriodOrder') IS NULL
       OR COL_LENGTH(N'omagmes.ShiftScheduleShiftPeriod', N'StartTime') IS NULL
       OR COL_LENGTH(N'omagmes.ShiftScheduleShiftPeriod', N'EndTime') IS NULL
       OR COL_LENGTH(N'omagmes.ShiftScheduleShiftPeriod', N'IsActive') IS NULL
        THROW 54307, 'An existing Shift Period table is incompatible; no data was changed.', 1;
        IF NOT EXISTS (
                SELECT 1 FROM sys.columns c JOIN sys.types ty ON ty.user_type_id=c.user_type_id
                WHERE c.object_id=OBJECT_ID(N'omagmes.ShiftScheduleShiftPeriod') AND c.name=N'id'
                    AND ty.name=N'bigint' AND c.is_identity=1 AND c.is_nullable=0
        )
                THROW 54313, 'The Shift Period id is not the expected non-null bigint identity; deployment refused.', 1;
        IF NOT EXISTS (
                SELECT 1 FROM sys.foreign_keys fk
                WHERE fk.parent_object_id=OBJECT_ID(N'omagmes.ShiftScheduleShiftPeriod')
                    AND fk.referenced_object_id=OBJECT_ID(N'omagmes.ShiftScheduleShift')
                    AND (SELECT COUNT(*) FROM sys.foreign_key_columns fkc WHERE fkc.constraint_object_id=fk.object_id)=2
                    AND fk.name=N'FK_ShiftScheduleShiftPeriod_ScheduleShift'
        ) OR NOT EXISTS (
                SELECT 1 FROM sys.indexes i
                WHERE i.object_id=OBJECT_ID(N'omagmes.ShiftScheduleShiftPeriod') AND i.is_unique=1
                    AND (SELECT COUNT(*) FROM sys.index_columns ic WHERE ic.object_id=i.object_id AND ic.index_id=i.index_id AND ic.key_ordinal>0)=3
                    AND (SELECT COUNT(DISTINCT c.name) FROM sys.index_columns ic JOIN sys.columns c ON c.object_id=ic.object_id AND c.column_id=ic.column_id
                             WHERE ic.object_id=i.object_id AND ic.index_id=i.index_id AND ic.key_ordinal>0
                                 AND c.name IN (N'ShiftScheduleVersionID',N'ShiftID',N'PeriodOrder'))=3
        )
                THROW 54314, 'The Shift Period table is missing its expected composite FK or unique key; deployment refused.', 1;

    IF OBJECT_ID(N'omagmes.ConfigurationChangeHistory', N'U') IS NULL
    BEGIN
        CREATE TABLE omagmes.ConfigurationChangeHistory (
            id bigint IDENTITY(1,1) NOT NULL CONSTRAINT PK_ConfigurationChangeHistory PRIMARY KEY,
            Rectime datetime NOT NULL CONSTRAINT DF_ConfigurationChangeHistory_Rectime DEFAULT (GETDATE()),
            ConfigurationType nvarchar(40) NOT NULL,
            ConfigurationIdentity nvarchar(200) NOT NULL,
            VersionID bigint NOT NULL,
            OldValue nvarchar(max) NULL,
            NewValue nvarchar(max) NULL,
            ChangedAt datetime2(0) NOT NULL CONSTRAINT DF_ConfigurationChangeHistory_ChangedAt DEFAULT (SYSUTCDATETIME()),
            ChangedBy nvarchar(200) NOT NULL,
            EffectiveFromProductionDate date NOT NULL,
            ChangeReason nvarchar(500) NOT NULL,
            CONSTRAINT CK_ConfigurationChangeHistory_Value CHECK (OldValue IS NOT NULL OR NewValue IS NOT NULL),
            CONSTRAINT CK_ConfigurationChangeHistory_Reason CHECK (LEN(LTRIM(RTRIM(ChangeReason))) > 0)
        );
        CREATE INDEX IX_ConfigurationChangeHistory_Type_Identity_Version
            ON omagmes.ConfigurationChangeHistory(ConfigurationType, ConfigurationIdentity, VersionID DESC, id DESC);
        CREATE INDEX IX_ConfigurationChangeHistory_EffectiveDate
            ON omagmes.ConfigurationChangeHistory(EffectiveFromProductionDate DESC, id DESC);
    END;
    IF COL_LENGTH(N'omagmes.ConfigurationChangeHistory', N'id') IS NULL
       OR COL_LENGTH(N'omagmes.ConfigurationChangeHistory', N'Rectime') IS NULL
       OR COL_LENGTH(N'omagmes.ConfigurationChangeHistory', N'ConfigurationType') IS NULL
       OR COL_LENGTH(N'omagmes.ConfigurationChangeHistory', N'ConfigurationIdentity') IS NULL
       OR COL_LENGTH(N'omagmes.ConfigurationChangeHistory', N'VersionID') IS NULL
       OR COL_LENGTH(N'omagmes.ConfigurationChangeHistory', N'OldValue') IS NULL
       OR COL_LENGTH(N'omagmes.ConfigurationChangeHistory', N'NewValue') IS NULL
       OR COL_LENGTH(N'omagmes.ConfigurationChangeHistory', N'ChangedAt') IS NULL
       OR COL_LENGTH(N'omagmes.ConfigurationChangeHistory', N'ChangedBy') IS NULL
       OR COL_LENGTH(N'omagmes.ConfigurationChangeHistory', N'EffectiveFromProductionDate') IS NULL
       OR COL_LENGTH(N'omagmes.ConfigurationChangeHistory', N'ChangeReason') IS NULL
        THROW 54308, 'An existing configuration history table is incompatible; no data was changed.', 1;
    IF NOT EXISTS (
        SELECT 1 FROM sys.columns c JOIN sys.types ty ON ty.user_type_id=c.user_type_id
        WHERE c.object_id=OBJECT_ID(N'omagmes.ConfigurationChangeHistory') AND c.name=N'id'
          AND ty.name=N'bigint' AND c.is_identity=1 AND c.is_nullable=0
    )
        THROW 54315, 'The configuration history id is not the expected non-null bigint identity; deployment refused.', 1;
    IF NOT EXISTS (
        SELECT 1 FROM sys.indexes i
        JOIN sys.index_columns ic ON ic.object_id=i.object_id AND ic.index_id=i.index_id AND ic.key_ordinal=1
        JOIN sys.columns c ON c.object_id=ic.object_id AND c.column_id=ic.column_id
        WHERE i.object_id=OBJECT_ID(N'omagmes.ConfigurationChangeHistory') AND i.is_primary_key=1 AND c.name=N'id'
    )
        THROW 54316, 'The configuration history identity column is not its primary key; deployment refused.', 1;

    IF OBJECT_ID(N'omagmes.TR_ShiftScheduleShiftPeriod_Immutable', N'TR') IS NULL
        EXEC(N'CREATE TRIGGER omagmes.TR_ShiftScheduleShiftPeriod_Immutable ON omagmes.ShiftScheduleShiftPeriod AFTER UPDATE, DELETE AS
        BEGIN SET NOCOUNT ON; THROW 54309, ''Shift Period schedule snapshots are append-only.'', 1; END;');
    ELSE IF (SELECT parent_id FROM sys.triggers WHERE object_id=OBJECT_ID(N'omagmes.TR_ShiftScheduleShiftPeriod_Immutable')) <> OBJECT_ID(N'omagmes.ShiftScheduleShiftPeriod')
        THROW 54310, 'The Shift Period immutability trigger name is used by another object; deployment refused.', 1;
    ELSE
        ENABLE TRIGGER omagmes.TR_ShiftScheduleShiftPeriod_Immutable ON omagmes.ShiftScheduleShiftPeriod;

    IF OBJECT_ID(N'omagmes.TR_ConfigurationChangeHistory_Immutable', N'TR') IS NULL
        EXEC(N'CREATE TRIGGER omagmes.TR_ConfigurationChangeHistory_Immutable ON omagmes.ConfigurationChangeHistory AFTER UPDATE, DELETE AS
        BEGIN SET NOCOUNT ON; THROW 54311, ''Configuration change history is append-only.'', 1; END;');
    ELSE IF (SELECT parent_id FROM sys.triggers WHERE object_id=OBJECT_ID(N'omagmes.TR_ConfigurationChangeHistory_Immutable')) <> OBJECT_ID(N'omagmes.ConfigurationChangeHistory')
        THROW 54312, 'The configuration history trigger name is used by another object; deployment refused.', 1;
    ELSE
        ENABLE TRIGGER omagmes.TR_ConfigurationChangeHistory_Immutable ON omagmes.ConfigurationChangeHistory;

    GRANT SELECT, INSERT ON OBJECT::omagmes.ShiftScheduleShiftPeriod TO omagmes_config_runtime_role;
    GRANT SELECT, INSERT ON OBJECT::omagmes.ConfigurationChangeHistory TO omagmes_config_runtime_role;

    COMMIT TRANSACTION;
END TRY
BEGIN CATCH
    IF XACT_STATE() <> 0 ROLLBACK TRANSACTION;
    THROW;
END CATCH;

SELECT N'ShiftScheduleShiftPeriod' AS ObjectName, COUNT_BIG(*) AS ExistingRows FROM omagmes.ShiftScheduleShiftPeriod
UNION ALL
SELECT N'ConfigurationChangeHistory', COUNT_BIG(*) FROM omagmes.ConfigurationChangeHistory;
