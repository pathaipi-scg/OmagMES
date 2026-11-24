/*
DBA REVIEW ONLY — MANUAL SSMS DEPLOYMENT CANDIDATE
Target: OMAG / omagmes. Run as the authorized database owner/sa in SSMS.
Copilot did not and must not execute this script. Do not provide or store sa credentials.

Additive only: creates the two date-owned snapshot tables, their constraints,
indexes and triggers, then grants the runtime role least-privilege access to
these new objects only. It does not alter/delete ProductionLot, ProductionEntry,
DailyShiftTypeAssignment, ShiftScheduleVersion, ShiftTypeScheduleVersion,
ConfigurationChangeHistory, PRESS, FittingMES or PIS data.

Safe to rerun after a successful deployment. Incompatible/partial objects fail
closed. Review the SSMS Messages and verification result sets after execution.
*/
USE [OMAG];
GO
SET NOCOUNT ON;
SET XACT_ABORT ON;

/* Preflight: correct database, prerequisites, role mapping and source IDs. */
IF DB_NAME() <> N'OMAG'
    THROW 54600, 'Migration 011 requires database OMAG.', 1;
IF SCHEMA_ID(N'omagmes') IS NULL
    THROW 54601, 'Required omagmes schema is missing.', 1;
IF DATABASE_PRINCIPAL_ID(N'omagmes_config_runtime_role') IS NULL
    THROW 54602, 'The configuration runtime role is missing; deployment refused.', 1;
IF DATABASE_PRINCIPAL_ID(N'omagmes_config_runtime_user') IS NULL
   OR IS_ROLEMEMBER(N'omagmes_config_runtime_role',N'omagmes_config_runtime_user') <> 1
    THROW 54603, 'The runtime user is missing from its expected role; deployment refused.', 1;
IF OBJECT_ID(N'omagmes.ShiftType',N'U') IS NULL
   OR OBJECT_ID(N'omagmes.Shift',N'U') IS NULL
   OR OBJECT_ID(N'omagmes.ShiftTypeScheduleVersion',N'U') IS NULL
   OR OBJECT_ID(N'omagmes.ShiftTypeSchedulePeriod',N'U') IS NULL
    THROW 54604, 'Required existing Shift Type/Shift master and schedule tables are missing.', 1;
IF COL_LENGTH(N'omagmes.ShiftType',N'id') IS NULL
   OR COL_LENGTH(N'omagmes.ShiftType',N'TypeCode') IS NULL
   OR COL_LENGTH(N'omagmes.Shift',N'id') IS NULL
   OR COL_LENGTH(N'omagmes.ShiftTypeScheduleVersion',N'id') IS NULL
   OR COL_LENGTH(N'omagmes.ShiftTypeScheduleVersion',N'ShiftTypeID') IS NULL
   OR COL_LENGTH(N'omagmes.ShiftTypeSchedulePeriod',N'ShiftTypeScheduleVersionID') IS NULL
   OR COL_LENGTH(N'omagmes.ShiftTypeSchedulePeriod',N'ShiftTypeID') IS NULL
   OR COL_LENGTH(N'omagmes.ShiftTypeSchedulePeriod',N'ShiftID') IS NULL
   OR COL_LENGTH(N'omagmes.ShiftTypeSchedulePeriod',N'ShiftNumber') IS NULL
    THROW 54605, 'Existing Shift Type/Shift ID columns do not match the reviewed schema.', 1;
IF EXISTS (
    SELECT TypeCode FROM omagmes.ShiftType
    WHERE TypeCode IN (N'TYPE 1',N'TYPE 2',N'TYPE 3')
    GROUP BY TypeCode HAVING COUNT_BIG(*) <> 1
) OR (SELECT COUNT_BIG(*) FROM omagmes.ShiftType
      WHERE TypeCode IN (N'TYPE 1',N'TYPE 2',N'TYPE 3')) <> 3
    THROW 54606, 'TYPE 1/2/3 must each resolve to exactly one existing ShiftType.id.', 1;
IF EXISTS (
    SELECT ShiftNumber FROM omagmes.ShiftTypeSchedulePeriod
    WHERE ShiftNumber IN (1,2,3)
    GROUP BY ShiftNumber HAVING COUNT(DISTINCT ShiftID) <> 1
) OR (SELECT COUNT(DISTINCT ShiftNumber) FROM omagmes.ShiftTypeSchedulePeriod
      WHERE ShiftNumber IN (1,2,3)) <> 3
    THROW 54607, 'Shift 1/2/3 must each resolve to exactly one existing Shift.id.', 1;
IF EXISTS (
    SELECT expected.TypeCode,expected.ShiftNumber
    FROM (VALUES (N'TYPE 1',1),(N'TYPE 2',1),(N'TYPE 2',2),(N'TYPE 3',2),(N'TYPE 3',3))
         AS expected(TypeCode,ShiftNumber)
    WHERE NOT EXISTS (
        SELECT 1
        FROM omagmes.ShiftType t
        JOIN omagmes.ShiftTypeScheduleVersion v ON v.ShiftTypeID=t.id
        JOIN omagmes.ShiftTypeSchedulePeriod p
          ON p.ShiftTypeScheduleVersionID=v.id AND p.ShiftTypeID=t.id
        WHERE t.TypeCode=expected.TypeCode AND p.ShiftNumber=expected.ShiftNumber
    )
)
    THROW 54608, 'One or more of the five fixed Type/Shift ID mappings is absent.', 1;
IF (OBJECT_ID(N'omagmes.DailyShiftConfigurationSave') IS NULL
    AND OBJECT_ID(N'omagmes.DailyShiftConfigurationPeriod') IS NOT NULL)
   OR (OBJECT_ID(N'omagmes.DailyShiftConfigurationSave') IS NOT NULL
       AND OBJECT_ID(N'omagmes.DailyShiftConfigurationPeriod') IS NULL)
    THROW 54609, 'Only one paired snapshot table exists; inspect manually before deployment.', 1;
IF OBJECT_ID(N'omagmes.DailyShiftConfigurationSave') IS NOT NULL
   AND OBJECT_ID(N'omagmes.DailyShiftConfigurationSave',N'U') IS NULL
    THROW 54610, 'A non-table object uses DailyShiftConfigurationSave.', 1;
IF OBJECT_ID(N'omagmes.DailyShiftConfigurationPeriod') IS NOT NULL
   AND OBJECT_ID(N'omagmes.DailyShiftConfigurationPeriod',N'U') IS NULL
    THROW 54611, 'A non-table object uses DailyShiftConfigurationPeriod.', 1;
IF OBJECT_ID(N'omagmes.TR_DailyShiftConfigurationSave_Complete',N'TR') IS NOT NULL
    AND (SELECT parent_id FROM sys.triggers
        WHERE object_id=OBJECT_ID(N'omagmes.TR_DailyShiftConfigurationSave_Complete',N'TR'))
       <> OBJECT_ID(N'omagmes.DailyShiftConfigurationSave',N'U')
    THROW 54612, 'Existing snapshot trigger name is attached to a different table.', 1;
IF OBJECT_ID(N'omagmes.TR_DailyShiftConfigurationPeriod_Immutable',N'TR') IS NOT NULL
    AND (SELECT parent_id FROM sys.triggers
        WHERE object_id=OBJECT_ID(N'omagmes.TR_DailyShiftConfigurationPeriod_Immutable',N'TR'))
       <> OBJECT_ID(N'omagmes.DailyShiftConfigurationPeriod',N'U')
    THROW 54613, 'Existing period trigger name is attached to a different table.', 1;

BEGIN TRY
    BEGIN TRANSACTION;

    IF OBJECT_ID(N'omagmes.DailyShiftConfigurationSave',N'U') IS NULL
    BEGIN
        CREATE TABLE omagmes.DailyShiftConfigurationSave (
            id bigint IDENTITY(1,1) NOT NULL CONSTRAINT PK_DailyShiftConfigurationSave PRIMARY KEY,
            Rectime datetime NOT NULL CONSTRAINT DF_DailyShiftConfigurationSave_Rectime DEFAULT (GETDATE()),
            SaveTime datetime2(0) NOT NULL CONSTRAINT DF_DailyShiftConfigurationSave_SaveTime DEFAULT (GETDATE()),
            ProductionDate date NOT NULL,
            SelectedType int NOT NULL,
            SelectedShiftTypeID bigint NOT NULL,
            IsComplete bit NOT NULL CONSTRAINT DF_DailyShiftConfigurationSave_IsComplete DEFAULT (0),
            CONSTRAINT UQ_DailyShiftConfigurationSave_ID_Date UNIQUE (id,ProductionDate),
            CONSTRAINT CK_DailyShiftConfigurationSave_Type CHECK (SelectedType BETWEEN 1 AND 3),
            CONSTRAINT FK_DailyShiftConfigurationSave_Type FOREIGN KEY (SelectedShiftTypeID)
                REFERENCES omagmes.ShiftType(id)
        );
    END;

    IF OBJECT_ID(N'omagmes.DailyShiftConfigurationPeriod',N'U') IS NULL
    BEGIN
        CREATE TABLE omagmes.DailyShiftConfigurationPeriod (
            id bigint IDENTITY(1,1) NOT NULL CONSTRAINT PK_DailyShiftConfigurationPeriod PRIMARY KEY,
            Rectime datetime NOT NULL CONSTRAINT DF_DailyShiftConfigurationPeriod_Rectime DEFAULT (GETDATE()),
            ConfigurationSaveID bigint NOT NULL,
            ProductionDate date NOT NULL,
            Type int NOT NULL,
            Shift int NOT NULL,
            TypeID bigint NOT NULL,
            ShiftID bigint NOT NULL,
            [Start] time(0) NOT NULL,
            [Stop] time(0) NOT NULL,
            CONSTRAINT FK_DailyShiftConfigurationPeriod_SaveDate FOREIGN KEY (ConfigurationSaveID,ProductionDate)
                REFERENCES omagmes.DailyShiftConfigurationSave(id,ProductionDate),
            CONSTRAINT UQ_DailyShiftConfigurationPeriod_Save_Type_Shift UNIQUE (ConfigurationSaveID,Type,Shift),
            CONSTRAINT FK_DailyShiftConfigurationPeriod_Type FOREIGN KEY (TypeID)
                REFERENCES omagmes.ShiftType(id),
            CONSTRAINT FK_DailyShiftConfigurationPeriod_Shift FOREIGN KEY (ShiftID)
                REFERENCES omagmes.Shift(id),
            CONSTRAINT CK_DailyShiftConfigurationPeriod_TypeShift CHECK (
                (Type=1 AND Shift=1) OR (Type=2 AND Shift IN (1,2)) OR (Type=3 AND Shift IN (2,3))
            ),
            CONSTRAINT CK_DailyShiftConfigurationPeriod_Nonzero CHECK ([Start]<>[Stop])
        );
    END;

    IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id=OBJECT_ID(N'omagmes.DailyShiftConfigurationSave') AND name=N'IX_DailyShiftConfigurationSave_Date_Latest')
        CREATE INDEX IX_DailyShiftConfigurationSave_Date_Latest
            ON omagmes.DailyShiftConfigurationSave(ProductionDate,IsComplete,SaveTime DESC,id DESC);
    IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id=OBJECT_ID(N'omagmes.DailyShiftConfigurationSave') AND name=N'IX_DailyShiftConfigurationSave_Global_Latest')
        CREATE INDEX IX_DailyShiftConfigurationSave_Global_Latest
            ON omagmes.DailyShiftConfigurationSave(IsComplete,SaveTime DESC,id DESC)
            INCLUDE (ProductionDate,SelectedType);
    IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id=OBJECT_ID(N'omagmes.DailyShiftConfigurationPeriod') AND name=N'IX_DailyShiftConfigurationPeriod_Save')
        CREATE INDEX IX_DailyShiftConfigurationPeriod_Save
            ON omagmes.DailyShiftConfigurationPeriod(ConfigurationSaveID,Type,Shift);

    /* Fail closed on partial/incompatible pre-existing tables; never reshape them. */
    IF COL_LENGTH(N'omagmes.DailyShiftConfigurationSave',N'id') IS NULL
       OR COL_LENGTH(N'omagmes.DailyShiftConfigurationSave',N'Rectime') IS NULL
       OR COL_LENGTH(N'omagmes.DailyShiftConfigurationSave',N'SaveTime') IS NULL
       OR COL_LENGTH(N'omagmes.DailyShiftConfigurationSave',N'ProductionDate') IS NULL
       OR COL_LENGTH(N'omagmes.DailyShiftConfigurationSave',N'SelectedType') IS NULL
       OR COL_LENGTH(N'omagmes.DailyShiftConfigurationSave',N'SelectedShiftTypeID') IS NULL
       OR COL_LENGTH(N'omagmes.DailyShiftConfigurationSave',N'IsComplete') IS NULL
       OR COL_LENGTH(N'omagmes.DailyShiftConfigurationPeriod',N'id') IS NULL
       OR COL_LENGTH(N'omagmes.DailyShiftConfigurationPeriod',N'Rectime') IS NULL
       OR COL_LENGTH(N'omagmes.DailyShiftConfigurationPeriod',N'ConfigurationSaveID') IS NULL
       OR COL_LENGTH(N'omagmes.DailyShiftConfigurationPeriod',N'ProductionDate') IS NULL
       OR COL_LENGTH(N'omagmes.DailyShiftConfigurationPeriod',N'Type') IS NULL
       OR COL_LENGTH(N'omagmes.DailyShiftConfigurationPeriod',N'Shift') IS NULL
       OR COL_LENGTH(N'omagmes.DailyShiftConfigurationPeriod',N'TypeID') IS NULL
       OR COL_LENGTH(N'omagmes.DailyShiftConfigurationPeriod',N'ShiftID') IS NULL
       OR COL_LENGTH(N'omagmes.DailyShiftConfigurationPeriod',N'Start') IS NULL
       OR COL_LENGTH(N'omagmes.DailyShiftConfigurationPeriod',N'Stop') IS NULL
        THROW 54614, 'A snapshot table is incomplete or incompatible; no existing object was modified.', 1;

    IF EXISTS (
        SELECT 1
        FROM (VALUES
            (N'DailyShiftConfigurationSave',N'id',N'bigint',0,1),
            (N'DailyShiftConfigurationSave',N'Rectime',N'datetime',0,0),
            (N'DailyShiftConfigurationSave',N'SaveTime',N'datetime2',0,0),
            (N'DailyShiftConfigurationSave',N'ProductionDate',N'date',0,0),
            (N'DailyShiftConfigurationSave',N'SelectedType',N'int',0,0),
            (N'DailyShiftConfigurationSave',N'SelectedShiftTypeID',N'bigint',0,0),
            (N'DailyShiftConfigurationSave',N'IsComplete',N'bit',0,0),
            (N'DailyShiftConfigurationPeriod',N'id',N'bigint',0,1),
            (N'DailyShiftConfigurationPeriod',N'Rectime',N'datetime',0,0),
            (N'DailyShiftConfigurationPeriod',N'ConfigurationSaveID',N'bigint',0,0),
            (N'DailyShiftConfigurationPeriod',N'ProductionDate',N'date',0,0),
            (N'DailyShiftConfigurationPeriod',N'Type',N'int',0,0),
            (N'DailyShiftConfigurationPeriod',N'Shift',N'int',0,0),
            (N'DailyShiftConfigurationPeriod',N'TypeID',N'bigint',0,0),
            (N'DailyShiftConfigurationPeriod',N'ShiftID',N'bigint',0,0),
            (N'DailyShiftConfigurationPeriod',N'Start',N'time',0,0),
            (N'DailyShiftConfigurationPeriod',N'Stop',N'time',0,0)
        ) expected(TableName,ColumnName,DataType,IsNullable,IsIdentity)
        LEFT JOIN sys.tables t ON t.object_id=OBJECT_ID(N'omagmes.'+expected.TableName,N'U')
        LEFT JOIN sys.columns c ON c.object_id=t.object_id AND c.name=expected.ColumnName
        LEFT JOIN sys.types ty ON ty.user_type_id=c.user_type_id
        WHERE c.column_id IS NULL OR ty.name<>expected.DataType
           OR c.is_nullable<>expected.IsNullable OR c.is_identity<>expected.IsIdentity
    )
        THROW 54622, 'Snapshot columns/types/nullability/identity differ from the reviewed design; deployment rolled back.', 1;
    IF IDENT_SEED(N'omagmes.DailyShiftConfigurationSave')<>1
       OR IDENT_INCR(N'omagmes.DailyShiftConfigurationSave')<>1
       OR IDENT_SEED(N'omagmes.DailyShiftConfigurationPeriod')<>1
       OR IDENT_INCR(N'omagmes.DailyShiftConfigurationPeriod')<>1
        THROW 54625, 'Snapshot IDs must use IDENTITY(1,1); deployment rolled back.', 1;
    IF EXISTS (
        SELECT 1 FROM sys.columns c
        WHERE (c.object_id=OBJECT_ID(N'omagmes.DailyShiftConfigurationSave')
               AND c.name=N'SaveTime' AND c.scale<>0)
           OR (c.object_id=OBJECT_ID(N'omagmes.DailyShiftConfigurationPeriod')
               AND c.name IN (N'Start',N'Stop') AND c.scale<>0)
    )
        THROW 54626, 'SaveTime and shift boundaries must use zero fractional-second precision.', 1;
    IF EXISTS (
        SELECT 1
        FROM (VALUES
            (N'DailyShiftConfigurationSave',N'Rectime',N'getdate'),
            (N'DailyShiftConfigurationSave',N'SaveTime',N'getdate'),
            (N'DailyShiftConfigurationSave',N'IsComplete',N'0'),
            (N'DailyShiftConfigurationPeriod',N'Rectime',N'getdate')
        ) expected(TableName,ColumnName,ExpectedDefinition)
        JOIN sys.tables t ON t.object_id=OBJECT_ID(N'omagmes.'+expected.TableName,N'U')
        JOIN sys.schemas s ON s.schema_id=t.schema_id AND s.name=N'omagmes'
        JOIN sys.columns c ON c.object_id=t.object_id AND c.name=expected.ColumnName
        LEFT JOIN sys.default_constraints dc
          ON dc.parent_object_id=c.object_id AND dc.parent_column_id=c.column_id
        CROSS APPLY (
            SELECT LOWER(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(
                COALESCE(dc.definition,N''),N' ',N''),CHAR(9),N''),CHAR(10),N''),CHAR(13),N''),N'(',N''),N')',N''))
                AS NormalizedDefinition
        ) normalized
        WHERE c.default_object_id=0 OR normalized.NormalizedDefinition<>expected.ExpectedDefinition
    )
        THROW 54623, 'A required snapshot default is missing or differs from its intended expression; deployment rolled back.', 1;
    IF NOT EXISTS (SELECT 1 FROM sys.key_constraints WHERE parent_object_id=OBJECT_ID(N'omagmes.DailyShiftConfigurationSave') AND name=N'PK_DailyShiftConfigurationSave')
       OR NOT EXISTS (SELECT 1 FROM sys.key_constraints WHERE parent_object_id=OBJECT_ID(N'omagmes.DailyShiftConfigurationPeriod') AND name=N'PK_DailyShiftConfigurationPeriod')
       OR NOT EXISTS (SELECT 1 FROM sys.key_constraints WHERE parent_object_id=OBJECT_ID(N'omagmes.DailyShiftConfigurationSave') AND name=N'UQ_DailyShiftConfigurationSave_ID_Date')
       OR NOT EXISTS (SELECT 1 FROM sys.key_constraints WHERE parent_object_id=OBJECT_ID(N'omagmes.DailyShiftConfigurationPeriod') AND name=N'UQ_DailyShiftConfigurationPeriod_Save_Type_Shift')
       OR NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE parent_object_id=OBJECT_ID(N'omagmes.DailyShiftConfigurationSave') AND name=N'FK_DailyShiftConfigurationSave_Type')
       OR NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE parent_object_id=OBJECT_ID(N'omagmes.DailyShiftConfigurationPeriod') AND name=N'FK_DailyShiftConfigurationPeriod_SaveDate')
       OR NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE parent_object_id=OBJECT_ID(N'omagmes.DailyShiftConfigurationPeriod') AND name=N'FK_DailyShiftConfigurationPeriod_Type')
       OR NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE parent_object_id=OBJECT_ID(N'omagmes.DailyShiftConfigurationPeriod') AND name=N'FK_DailyShiftConfigurationPeriod_Shift')
       OR NOT EXISTS (SELECT 1 FROM sys.check_constraints WHERE parent_object_id=OBJECT_ID(N'omagmes.DailyShiftConfigurationSave') AND name=N'CK_DailyShiftConfigurationSave_Type')
       OR NOT EXISTS (SELECT 1 FROM sys.check_constraints WHERE parent_object_id=OBJECT_ID(N'omagmes.DailyShiftConfigurationPeriod') AND name=N'CK_DailyShiftConfigurationPeriod_TypeShift')
       OR NOT EXISTS (SELECT 1 FROM sys.check_constraints WHERE parent_object_id=OBJECT_ID(N'omagmes.DailyShiftConfigurationPeriod') AND name=N'CK_DailyShiftConfigurationPeriod_Nonzero')
             OR NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id=OBJECT_ID(N'omagmes.DailyShiftConfigurationSave') AND name=N'IX_DailyShiftConfigurationSave_Date_Latest')
             OR NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id=OBJECT_ID(N'omagmes.DailyShiftConfigurationSave') AND name=N'IX_DailyShiftConfigurationSave_Global_Latest')
             OR NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id=OBJECT_ID(N'omagmes.DailyShiftConfigurationPeriod') AND name=N'IX_DailyShiftConfigurationPeriod_Save')
        THROW 54615, 'Required snapshot keys/foreign keys/check constraints are absent; deployment rolled back.', 1;

            IF EXISTS (
                SELECT expected.FKName,expected.ParentTable,expected.ParentColumn,expected.ReferencedTable,expected.ReferencedColumn
                FROM (VALUES
                    (N'FK_DailyShiftConfigurationSave_Type',N'DailyShiftConfigurationSave',N'SelectedShiftTypeID',N'ShiftType',N'id'),
                    (N'FK_DailyShiftConfigurationPeriod_SaveDate',N'DailyShiftConfigurationPeriod',N'ConfigurationSaveID',N'DailyShiftConfigurationSave',N'id'),
                    (N'FK_DailyShiftConfigurationPeriod_SaveDate',N'DailyShiftConfigurationPeriod',N'ProductionDate',N'DailyShiftConfigurationSave',N'ProductionDate'),
                    (N'FK_DailyShiftConfigurationPeriod_Type',N'DailyShiftConfigurationPeriod',N'TypeID',N'ShiftType',N'id'),
                    (N'FK_DailyShiftConfigurationPeriod_Shift',N'DailyShiftConfigurationPeriod',N'ShiftID',N'Shift',N'id')
                ) expected(FKName,ParentTable,ParentColumn,ReferencedTable,ReferencedColumn)
                WHERE NOT EXISTS (
                    SELECT 1
                    FROM sys.foreign_keys fk
                    JOIN sys.foreign_key_columns fkc ON fkc.constraint_object_id=fk.object_id
                    JOIN sys.columns pc ON pc.object_id=fkc.parent_object_id AND pc.column_id=fkc.parent_column_id
                    JOIN sys.columns rc ON rc.object_id=fkc.referenced_object_id AND rc.column_id=fkc.referenced_column_id
                    WHERE fk.name=expected.FKName
                      AND fkc.parent_object_id=OBJECT_ID(N'omagmes.'+expected.ParentTable,N'U')
                      AND pc.name=expected.ParentColumn
                      AND fkc.referenced_object_id=OBJECT_ID(N'omagmes.'+expected.ReferencedTable,N'U')
                      AND rc.name=expected.ReferencedColumn
                )
            )
                THROW 54627, 'A snapshot foreign key does not target its authoritative ID column; deployment rolled back.', 1;

        IF EXISTS (SELECT 1 FROM sys.foreign_keys
                             WHERE parent_object_id IN (OBJECT_ID(N'omagmes.DailyShiftConfigurationSave'),OBJECT_ID(N'omagmes.DailyShiftConfigurationPeriod'))
                                 AND (is_disabled=1 OR is_not_trusted=1))
             OR EXISTS (SELECT 1 FROM sys.check_constraints
                                    WHERE parent_object_id IN (OBJECT_ID(N'omagmes.DailyShiftConfigurationSave'),OBJECT_ID(N'omagmes.DailyShiftConfigurationPeriod'))
                                        AND (is_disabled=1 OR is_not_trusted=1))
                THROW 54624, 'A snapshot constraint is disabled or untrusted; deployment rolled back.', 1;

    DECLARE @SaveTrigger nvarchar(max) = N'CREATE OR ALTER TRIGGER omagmes.TR_DailyShiftConfigurationSave_Complete
        ON omagmes.DailyShiftConfigurationSave AFTER UPDATE,DELETE AS
        BEGIN
            SET NOCOUNT ON;
            IF EXISTS (SELECT 1 FROM deleted WHERE IsComplete=1)
                THROW 54616,''A completed Shift configuration save is immutable.'',1;
            IF EXISTS (SELECT 1 FROM inserted WHERE IsComplete=0 AND EXISTS (SELECT 1 FROM deleted))
                THROW 54617,''A Shift configuration save can only transition from incomplete to complete.'',1;
            IF EXISTS (
                SELECT 1 FROM inserted s WHERE s.IsComplete=1 AND (
                    (SELECT COUNT_BIG(*) FROM omagmes.DailyShiftConfigurationPeriod p WHERE p.ConfigurationSaveID=s.id)<>5
                    OR NOT EXISTS (SELECT 1 FROM omagmes.DailyShiftConfigurationPeriod p WHERE p.ConfigurationSaveID=s.id AND p.Type=1 AND p.Shift=1)
                    OR NOT EXISTS (SELECT 1 FROM omagmes.DailyShiftConfigurationPeriod p WHERE p.ConfigurationSaveID=s.id AND p.Type=2 AND p.Shift=1)
                    OR NOT EXISTS (SELECT 1 FROM omagmes.DailyShiftConfigurationPeriod p WHERE p.ConfigurationSaveID=s.id AND p.Type=2 AND p.Shift=2)
                    OR NOT EXISTS (SELECT 1 FROM omagmes.DailyShiftConfigurationPeriod p WHERE p.ConfigurationSaveID=s.id AND p.Type=3 AND p.Shift=2)
                    OR NOT EXISTS (SELECT 1 FROM omagmes.DailyShiftConfigurationPeriod p WHERE p.ConfigurationSaveID=s.id AND p.Type=3 AND p.Shift=3)
                    OR NOT EXISTS (SELECT 1 FROM omagmes.ShiftType t WHERE t.id=s.SelectedShiftTypeID AND t.TypeCode=CONCAT(N''TYPE '',s.SelectedType))
                    OR EXISTS (
                        SELECT 1 FROM omagmes.DailyShiftConfigurationPeriod p
                        WHERE p.ConfigurationSaveID=s.id AND NOT EXISTS (
                            SELECT 1 FROM omagmes.ShiftType t
                            JOIN omagmes.ShiftTypeScheduleVersion v ON v.ShiftTypeID=t.id
                            JOIN omagmes.ShiftTypeSchedulePeriod sp
                              ON sp.ShiftTypeScheduleVersionID=v.id AND sp.ShiftTypeID=t.id
                            WHERE t.id=p.TypeID AND t.TypeCode=CONCAT(N''TYPE '',p.Type)
                              AND sp.ShiftID=p.ShiftID AND sp.ShiftNumber=p.Shift
                        )
                    )
                )
            ) THROW 54618,''A complete Shift configuration requires the five fixed Type/Shift IDs.'',1;
        END;';
    EXEC sys.sp_executesql @SaveTrigger;

    DECLARE @PeriodTrigger nvarchar(max) = N'CREATE OR ALTER TRIGGER omagmes.TR_DailyShiftConfigurationPeriod_Immutable
        ON omagmes.DailyShiftConfigurationPeriod AFTER INSERT,UPDATE,DELETE AS
        BEGIN
            SET NOCOUNT ON;
            IF EXISTS (
                SELECT 1 FROM inserted i JOIN omagmes.DailyShiftConfigurationSave s ON s.id=i.ConfigurationSaveID
                WHERE s.IsComplete=1
            ) OR EXISTS (
                SELECT 1 FROM deleted d JOIN omagmes.DailyShiftConfigurationSave s ON s.id=d.ConfigurationSaveID
                WHERE s.IsComplete=1
            ) THROW 54619,''Periods cannot be changed after their Shift configuration save is complete.'',1;
        END;';
    EXEC sys.sp_executesql @PeriodTrigger;

    /* Minimum runtime permissions: read and insert these new objects; update only completion flag. */
    GRANT SELECT ON OBJECT::omagmes.DailyShiftConfigurationSave TO omagmes_config_runtime_role;
    GRANT INSERT ON OBJECT::omagmes.DailyShiftConfigurationSave TO omagmes_config_runtime_role;
    GRANT UPDATE (IsComplete)
        ON OBJECT::omagmes.DailyShiftConfigurationSave TO omagmes_config_runtime_role;
    GRANT SELECT ON OBJECT::omagmes.DailyShiftConfigurationPeriod TO omagmes_config_runtime_role;
    GRANT INSERT ON OBJECT::omagmes.DailyShiftConfigurationPeriod TO omagmes_config_runtime_role;
    /* No DELETE grant is required or issued for either table. */

    IF EXISTS (SELECT 1 FROM sys.triggers WHERE object_id=OBJECT_ID(N'omagmes.TR_DailyShiftConfigurationSave_Complete') AND is_disabled=1)
       OR EXISTS (SELECT 1 FROM sys.triggers WHERE object_id=OBJECT_ID(N'omagmes.TR_DailyShiftConfigurationPeriod_Immutable') AND is_disabled=1)
        THROW 54620, 'A required snapshot trigger is disabled; deployment rolled back.', 1;

    COMMIT TRANSACTION;
END TRY
BEGIN CATCH
    IF XACT_STATE() <> 0 ROLLBACK TRANSACTION;
    THROW;
END CATCH;
GO

/* Post-deployment verification result sets. These are read-only. */
IF DB_NAME() <> N'OMAG'
    THROW 54621, 'Post-deployment verification is not running in OMAG.', 1;

SELECT DB_NAME() AS DatabaseName, N'omagmes' AS SchemaName,
       OBJECT_ID(N'omagmes.DailyShiftConfigurationSave',N'U') AS SaveTableObjectID,
       OBJECT_ID(N'omagmes.DailyShiftConfigurationPeriod',N'U') AS PeriodTableObjectID;

SELECT t.name AS TableName,c.name AS ColumnName,ty.name AS DataType,c.max_length,c.is_nullable,c.is_identity,
       dc.definition AS DefaultDefinition
FROM sys.tables t
JOIN sys.schemas s ON s.schema_id=t.schema_id
JOIN sys.columns c ON c.object_id=t.object_id
JOIN sys.types ty ON ty.user_type_id=c.user_type_id
LEFT JOIN sys.default_constraints dc ON dc.object_id=c.default_object_id
WHERE s.name=N'omagmes' AND t.name IN (N'DailyShiftConfigurationSave',N'DailyShiftConfigurationPeriod')
ORDER BY t.name,c.column_id;

SELECT t.name AS TableName,o.name AS ConstraintOrIndexName,o.type_desc,
       fk.is_disabled AS ForeignKeyDisabled,fk.is_not_trusted AS ForeignKeyNotTrusted,
       cc.is_disabled AS CheckDisabled,cc.is_not_trusted AS CheckNotTrusted
FROM sys.objects o
JOIN sys.tables t ON t.object_id=o.parent_object_id
LEFT JOIN sys.foreign_keys fk ON fk.object_id=o.object_id
LEFT JOIN sys.check_constraints cc ON cc.object_id=o.object_id
WHERE t.name IN (N'DailyShiftConfigurationSave',N'DailyShiftConfigurationPeriod')
  AND (o.type IN (N'PK',N'UQ',N'F',N'C') OR o.type=N'IT')
ORDER BY t.name,o.type_desc,o.name;

SELECT fk.name AS ForeignKeyName,OBJECT_SCHEMA_NAME(fkc.parent_object_id) AS ParentSchema,
       OBJECT_NAME(fkc.parent_object_id) AS ParentTable,pc.name AS ParentColumn,
       OBJECT_SCHEMA_NAME(fkc.referenced_object_id) AS ReferencedSchema,
       OBJECT_NAME(fkc.referenced_object_id) AS ReferencedTable,rc.name AS ReferencedColumn,
       fk.is_disabled,fk.is_not_trusted
FROM sys.foreign_keys fk
JOIN sys.foreign_key_columns fkc ON fkc.constraint_object_id=fk.object_id
JOIN sys.columns pc ON pc.object_id=fkc.parent_object_id AND pc.column_id=fkc.parent_column_id
JOIN sys.columns rc ON rc.object_id=fkc.referenced_object_id AND rc.column_id=fkc.referenced_column_id
WHERE fkc.parent_object_id IN (OBJECT_ID(N'omagmes.DailyShiftConfigurationSave'),
                               OBJECT_ID(N'omagmes.DailyShiftConfigurationPeriod'))
ORDER BY fk.name,fkc.constraint_column_id;

SELECT t.name AS TableName,i.name AS IndexName,i.is_unique,i.is_primary_key,i.type_desc
FROM sys.indexes i
JOIN sys.tables t ON t.object_id=i.object_id
JOIN sys.schemas s ON s.schema_id=t.schema_id
WHERE s.name=N'omagmes' AND t.name IN (N'DailyShiftConfigurationSave',N'DailyShiftConfigurationPeriod')
ORDER BY t.name,i.name;

SELECT tr.name AS TriggerName,OBJECT_SCHEMA_NAME(tr.parent_id) AS SchemaName,
       OBJECT_NAME(tr.parent_id) AS ParentTable,tr.is_disabled
FROM sys.triggers tr
WHERE tr.object_id IN (OBJECT_ID(N'omagmes.TR_DailyShiftConfigurationSave_Complete'),
                       OBJECT_ID(N'omagmes.TR_DailyShiftConfigurationPeriod_Immutable'))
ORDER BY tr.name;

SELECT grantee.name AS Grantee,dp.permission_name,dp.state_desc,
       OBJECT_NAME(dp.major_id) AS ObjectName,
       CASE WHEN dp.minor_id=0 THEN NULL ELSE COL_NAME(dp.major_id,dp.minor_id) END AS ColumnName
FROM sys.database_permissions dp
JOIN sys.database_principals grantee ON grantee.principal_id=dp.grantee_principal_id
WHERE grantee.name=N'omagmes_config_runtime_role'
  AND dp.major_id IN (OBJECT_ID(N'omagmes.DailyShiftConfigurationSave'),
                      OBJECT_ID(N'omagmes.DailyShiftConfigurationPeriod'))
ORDER BY ObjectName,dp.permission_name,ColumnName;

IF OBJECT_ID(N'omagmes.DailyShiftConfigurationSave',N'U') IS NULL
   OR OBJECT_ID(N'omagmes.DailyShiftConfigurationPeriod',N'U') IS NULL
BEGIN
    PRINT N'Snapshot row-count verification skipped: one or both tables are absent (deployment may have rolled back).';
END
ELSE
BEGIN
    EXEC sys.sp_executesql N'
        SELECT N''DailyShiftConfigurationSave'' AS TableName,COUNT_BIG(*) AS ExistingRows
        FROM omagmes.DailyShiftConfigurationSave
        UNION ALL
        SELECT N''DailyShiftConfigurationPeriod'',COUNT_BIG(*)
        FROM omagmes.DailyShiftConfigurationPeriod;';
END;

/* Effective runtime checks should report SELECT/INSERT and only parent IsComplete UPDATE; DELETE=0. */
EXECUTE AS USER = N'omagmes_config_runtime_user';
BEGIN TRY
SELECT USER_NAME() AS EffectiveDatabaseUser,
       HAS_PERMS_BY_NAME(N'omagmes.DailyShiftConfigurationSave',N'OBJECT',N'SELECT') AS SaveSelect,
         HAS_PERMS_BY_NAME(N'omagmes.DailyShiftConfigurationSave',N'OBJECT',N'INSERT') AS SaveInsert,
    HAS_PERMS_BY_NAME(N'omagmes.DailyShiftConfigurationSave',N'OBJECT',N'UPDATE',N'IsComplete') AS SaveCompleteUpdate,
       HAS_PERMS_BY_NAME(N'omagmes.DailyShiftConfigurationSave',N'OBJECT',N'DELETE') AS SaveDelete,
       HAS_PERMS_BY_NAME(N'omagmes.DailyShiftConfigurationPeriod',N'OBJECT',N'SELECT') AS PeriodSelect,
         HAS_PERMS_BY_NAME(N'omagmes.DailyShiftConfigurationPeriod',N'OBJECT',N'INSERT') AS PeriodInsert,
       HAS_PERMS_BY_NAME(N'omagmes.DailyShiftConfigurationPeriod',N'OBJECT',N'DELETE') AS PeriodDelete;
REVERT;
END TRY
BEGIN CATCH
    REVERT;
    THROW;
END CATCH;
GO
