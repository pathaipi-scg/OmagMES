/*
READ-ONLY PREDEPLOY PREFLIGHT for Migration 004.
SELECT-only: this script does not use temporary/table variables or DDL/DML.
Run against the specifically authorized OMAG target before any DBA deployment.
A PASS does not authorize or execute Migration 004; every BLOCKER needs review.
*/
SET NOCOUNT ON;

SELECT N'TARGET_DATABASE' AS CheckName,
       DB_NAME() AS ObservedValue,
       CASE WHEN DB_NAME() = N'OMAG' THEN N'PASS' ELSE N'BLOCKER' END AS Status;

SELECT N'REQUIRED_PREREQUISITE' AS CheckType,
       required.SchemaName,
       required.ObjectName,
       required.ObjectType,
       CASE WHEN o.object_id IS NULL THEN N'BLOCKER: MISSING' ELSE N'PASS: PRESENT' END AS Status
FROM (VALUES
    (N'omagmes', N'ProductionDayCutoffVersion', N'U'),
    (N'omagmes', N'ShiftScheduleVersion', N'U'),
    (N'omagmes', N'ShiftScheduleShift', N'U'),
    (N'omagmes', N'Shift', N'U'),
    (N'omagmes', N'Product', N'U'),
    (N'omagmes', N'ProductionLot', N'U')
) AS required(SchemaName, ObjectName, ObjectType)
LEFT JOIN sys.objects AS o
  ON o.schema_id = SCHEMA_ID(required.SchemaName)
 AND o.name = required.ObjectName
 AND o.type = required.ObjectType
ORDER BY required.ObjectName;

SELECT N'REQUIRED_COLUMN_AND_TYPE' AS CheckType,
       expected.SchemaName,
       expected.TableName,
       expected.ColumnName,
       expected.TypeName AS ExpectedType,
       actual_type.name AS ActualType,
       CASE WHEN c.column_id IS NULL THEN N'BLOCKER: MISSING TABLE OR COLUMN'
            WHEN actual_type.name <> expected.TypeName THEN N'BLOCKER: TYPE MISMATCH'
            WHEN expected.ColumnName = N'id'
                 AND NOT EXISTS (
                     SELECT 1
                     FROM sys.indexes AS pk
                     JOIN sys.index_columns AS pkc
                       ON pkc.object_id = pk.object_id AND pkc.index_id = pk.index_id
                     WHERE pk.object_id = c.object_id
                       AND pk.is_primary_key = 1
                       AND pkc.key_ordinal = 1
                       AND pkc.column_id = c.column_id
                 ) THEN N'BLOCKER: id IS NOT PRIMARY KEY'
            ELSE N'PASS' END AS Status
FROM (VALUES
    (N'dbo', N'PRESS', N'id', N'int'),
    (N'dbo', N'PRESS', N'_NAME', N'varchar'),
    (N'dbo', N'PRESS', N'_VALUE', N'varchar'),
    (N'dbo', N'PRESS', N'_TIMESTAMP', N'datetime'),
    (N'dbo', N'PRESS', N'_QUALITY', N'int'),
    (N'omagmes', N'ProductionDayCutoffVersion', N'id', N'bigint'),
    (N'omagmes', N'ProductionDayCutoffVersion', N'EffectiveFromProductionDate', N'date'),
    (N'omagmes', N'ProductionDayCutoffVersion', N'CutoffTime', N'time'),
    (N'omagmes', N'ShiftScheduleVersion', N'id', N'bigint'),
    (N'omagmes', N'Shift', N'id', N'bigint'),
    (N'omagmes', N'Product', N'id', N'bigint'),
    (N'omagmes', N'ProductionLot', N'id', N'bigint'),
    (N'omagmes', N'ProductionLot', N'LotNo', N'varchar'),
    (N'omagmes', N'ProductionLot', N'LotStartedAt', N'datetimeoffset'),
    (N'omagmes', N'ProductionLot', N'LotEndedAt', N'datetimeoffset'),
    (N'omagmes', N'ProductionLot', N'ProductionDate', N'date'),
    (N'omagmes', N'ProductionLot', N'ShiftID', N'bigint'),
    (N'omagmes', N'ProductionLot', N'ProductID', N'bigint'),
    (N'omagmes', N'ProductionLot', N'ColorCode', N'nvarchar'),
    (N'omagmes', N'ProductionLot', N'LotName', N'nvarchar')
) AS expected(SchemaName, TableName, ColumnName, TypeName)
LEFT JOIN sys.tables AS t
  ON t.schema_id = SCHEMA_ID(expected.SchemaName)
 AND t.name = expected.TableName
LEFT JOIN sys.columns AS c
  ON c.object_id = t.object_id
 AND c.name = expected.ColumnName
LEFT JOIN sys.types AS actual_type ON actual_type.user_type_id = c.user_type_id
ORDER BY expected.SchemaName, expected.TableName, expected.ColumnName;

SELECT N'MIGRATION_004_NAME_COLLISION' AS CheckType,
       expected.ObjectName,
       expected.ObjectType,
       CASE WHEN o.object_id IS NULL THEN N'PASS: AVAILABLE' ELSE N'BLOCKER: EXISTS' END AS Status
FROM (VALUES
    (N'PressDiffQualityPolicy', N'U'),
    (N'AutoLotCandidateWindow', N'U'),
    (N'AutoLotCandidateWindowHistory', N'U'),
    (N'v_PressDailyDiff', N'V'),
    (N'v_PressLotDiff', N'V'),
    (N'v_PressLotACC', N'V'),
    (N'v_PressDiffReconciliation', N'V'),
    (N'v_PressLotSummary', N'V')
) AS expected(ObjectName, ObjectType)
LEFT JOIN sys.objects AS o
  ON o.schema_id = SCHEMA_ID(N'omagmes')
 AND o.name = expected.ObjectName
ORDER BY expected.ObjectName;

SELECT N'PRESS_SOURCE_COLUMN' AS CheckType,
       expected.ColumnName,
       expected.TypeName AS ExpectedType,
       actual_type.name AS ActualType,
       c.is_nullable AS IsNullable,
       CASE WHEN c.column_id IS NULL THEN N'BLOCKER: MISSING'
            WHEN actual_type.name <> expected.TypeName THEN N'BLOCKER: TYPE MISMATCH'
            ELSE N'PASS: PRESENT' END AS Status
FROM (VALUES
    (N'id', N'int'),
    (N'_NAME', N'varchar'),
    (N'_VALUE', N'varchar'),
    (N'_TIMESTAMP', N'datetime'),
    (N'_QUALITY', N'int')
) AS expected(ColumnName, TypeName)
LEFT JOIN sys.columns AS c
  ON c.object_id = OBJECT_ID(N'dbo.PRESS', N'U')
 AND c.name = expected.ColumnName
LEFT JOIN sys.types AS actual_type ON actual_type.user_type_id = c.user_type_id
ORDER BY expected.ColumnName;

SELECT N'PRESS_SOURCE_INDEX' AS CheckType,
       i.name AS IndexName,
       c.name AS KeyColumn,
       i.type_desc,
       CASE WHEN i.is_primary_key = 1 AND c.name = N'id' AND i.type = 1
            THEN N'PASS: CLUSTERED ID KEY'
            ELSE N'REVIEW: INDEX ACCESS PATH' END AS Status
FROM sys.indexes AS i
JOIN sys.index_columns AS ic
  ON ic.object_id = i.object_id AND ic.index_id = i.index_id AND ic.key_ordinal = 1
JOIN sys.columns AS c ON c.object_id = ic.object_id AND c.column_id = ic.column_id
WHERE i.object_id = OBJECT_ID(N'dbo.PRESS', N'U')
  AND i.is_hypothetical = 0
ORDER BY i.index_id;

SELECT N'DATABASE_COMPATIBILITY' AS CheckType,
       d.compatibility_level AS CompatibilityLevel,
       CAST(SERVERPROPERTY(N'ProductVersion') AS nvarchar(128)) AS ProductVersion,
       CASE WHEN d.compatibility_level >= 110 THEN N'PASS: LAG supported'
            ELSE N'BLOCKER: LAG requires compatibility level 110 or later' END AS Status
FROM sys.databases AS d
WHERE d.name = DB_NAME();
