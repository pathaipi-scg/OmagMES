/*
READ-ONLY PREFLIGHT for Migration 003. SELECT-only; no DDL/DML.
Requires the separately deployed Migration 002 configuration objects.
Factory-owner decision (2026-11-17): Migration 003 is the canonical Product/Run/Lot
design; the incompatible, unexecuted 001 foundation draft is superseded and must not
be applied. This preflight still stops on any existing 003 object collision.
*/
SET NOCOUNT ON;

SELECT N'TARGET_DATABASE' AS CheckType, DB_NAME() AS ObservedValue,
       CASE WHEN DB_NAME() = N'OMAG' THEN N'PASS' ELSE N'BLOCKER' END AS Status;

SELECT N'REQUIRED_CONFIGURATION_OBJECT' AS CheckType,
       required.ObjectName,
       CASE WHEN t.object_id IS NULL THEN N'BLOCKER: MISSING' ELSE N'PASS: PRESENT' END AS Status
FROM (VALUES
    (N'ProductionDayCutoffVersion'), (N'Shift'),
    (N'ShiftScheduleVersion'), (N'ShiftScheduleShift')
) AS required(ObjectName)
LEFT JOIN sys.tables AS t
  ON t.schema_id = SCHEMA_ID(N'omagmes') AND t.name = required.ObjectName
ORDER BY required.ObjectName;

SELECT N'REQUIRED_CONFIGURATION_COLUMN' AS CheckType,
       expected.TableName, expected.ColumnName, expected.TypeName AS ExpectedType,
       actual_type.name AS ActualType,
       CASE WHEN c.column_id IS NULL THEN N'BLOCKER: MISSING'
            WHEN actual_type.name <> expected.TypeName THEN N'BLOCKER: TYPE MISMATCH'
            ELSE N'PASS' END AS Status
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
LEFT JOIN sys.columns AS c ON c.object_id = t.object_id AND c.name = expected.ColumnName
LEFT JOIN sys.types AS actual_type ON actual_type.user_type_id = c.user_type_id
ORDER BY expected.TableName, expected.ColumnName;

SELECT N'PRODUCTION_OBJECT_COLLISION' AS CheckType, expected.ObjectName,
       CASE WHEN o.object_id IS NULL THEN N'PASS: AVAILABLE' ELSE N'BLOCKER: EXISTS' END AS Status
FROM (VALUES
    (N'Product'), (N'ProductStandardRevision'), (N'ProductionRun'), (N'ProductionLot'),
    (N'AutoLotResetReview'), (N'LotNumberSequence'), (N'ProductionLotNameHistory'),
    (N'ProductionEntry'), (N'ProductionEntryCorrection'), (N'CuringInputEntry'),
    (N'DepalletEvent'), (N'Dispatch'), (N'DispatchLine')
) AS expected(ObjectName)
LEFT JOIN sys.objects AS o
  ON o.schema_id = SCHEMA_ID(N'omagmes') AND o.name = expected.ObjectName
ORDER BY expected.ObjectName;

SELECT N'SCHEDULE_SHIFT_COMPOSITE_KEY' AS CheckType,
       CASE WHEN EXISTS (
           SELECT 1
           FROM sys.key_constraints AS kc
           JOIN sys.index_columns AS first_key
             ON first_key.object_id = kc.parent_object_id
            AND first_key.index_id = kc.unique_index_id AND first_key.key_ordinal = 1
           JOIN sys.columns AS first_column
             ON first_column.object_id = first_key.object_id AND first_column.column_id = first_key.column_id
           JOIN sys.index_columns AS second_key
             ON second_key.object_id = kc.parent_object_id
            AND second_key.index_id = kc.unique_index_id AND second_key.key_ordinal = 2
           JOIN sys.columns AS second_column
             ON second_column.object_id = second_key.object_id AND second_column.column_id = second_key.column_id
           WHERE kc.parent_object_id = OBJECT_ID(N'omagmes.ShiftScheduleShift', N'U')
             AND kc.type = N'UQ'
             AND first_column.name = N'ShiftScheduleVersionID'
             AND second_column.name = N'ShiftID'
       ) THEN N'PASS' ELSE N'BLOCKER: REQUIRED UNIQUE COMPOSITE KEY MISSING' END AS Status;

SELECT N'SUPERSEDED_FOUNDATION_DRAFT' AS CheckType,
       N'db/review-only/001_omagmes_foundation.sql defines an incompatible Product, ProductionRun, and ProductionLot model. Per factory-owner direction, do not apply 001; Migration 003 is canonical.' AS Detail,
       N'RESOLVED: APPLY 003 ONLY; STOP ON ANY OBJECT COLLISION' AS Status;
