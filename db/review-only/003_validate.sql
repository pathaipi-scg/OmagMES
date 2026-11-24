/*
READ-ONLY VALIDATION DRAFT for migration 003. Does not execute DDL/DML and has not
been run against SQL Server. Run only after separately authorized migration execution.
*/
SET NOCOUNT ON;
IF DB_NAME() <> N'OMAG'
  THROW 53310, 'Migration 003 validation only applies to OMAG.', 1;

IF EXISTS (
  SELECT 1
  FROM (VALUES
    (N'Product'), (N'ProductStandardRevision'), (N'ProductionRun'), (N'ProductionLot'),
    (N'ProductionLotNameHistory'), (N'ProductionEntry'), (N'ProductionEntryCorrection'),
    (N'CuringInputEntry'), (N'DepalletEvent'), (N'Dispatch'), (N'DispatchLine'),
    (N'LotNumberSequence'), (N'AutoLotResetReview')
  ) AS required(name)
  WHERE OBJECT_ID(N'omagmes.' + required.name, N'U') IS NULL
)
  THROW 53311, 'One or more Migration 003 tables are missing.', 1;

SELECT required.name AS RequiredTable,
       CASE WHEN t.object_id IS NULL THEN CAST(0 AS bit) ELSE CAST(1 AS bit) END AS ExistsInOmagmes
FROM (VALUES
    (N'Product'), (N'ProductStandardRevision'), (N'ProductionRun'), (N'ProductionLot'),
    (N'ProductionLotNameHistory'), (N'ProductionEntry'), (N'ProductionEntryCorrection'),
    (N'CuringInputEntry'), (N'DepalletEvent'), (N'Dispatch'), (N'DispatchLine'),
    (N'LotNumberSequence'), (N'AutoLotResetReview')
) AS required(name)
LEFT JOIN sys.tables AS t ON t.schema_id = SCHEMA_ID(N'omagmes') AND t.name = required.name
ORDER BY required.name;

IF EXISTS (
  SELECT 1
  FROM sys.tables AS t
  CROSS APPLY (VALUES (N'id'), (N'Rectime')) AS expected(ColumnName)
  LEFT JOIN sys.columns AS c ON c.object_id = t.object_id AND c.name = expected.ColumnName
  WHERE t.schema_id = SCHEMA_ID(N'omagmes')
    AND t.name IN (N'Product',N'ProductStandardRevision',N'ProductionRun',N'ProductionLot',
      N'ProductionLotNameHistory',N'ProductionEntry',N'ProductionEntryCorrection',
      N'CuringInputEntry',N'DepalletEvent',N'Dispatch',N'DispatchLine',N'LotNumberSequence',N'AutoLotResetReview')
    AND (c.column_id IS NULL OR (expected.ColumnName = N'id' AND (c.is_identity = 0 OR c.is_nullable = 1))
       OR (expected.ColumnName = N'Rectime' AND (TYPE_NAME(c.user_type_id) <> N'datetime' OR c.is_nullable = 1)))
)
  THROW 53312, 'A Migration 003 id/Rectime base-column check failed.', 1;

IF EXISTS (
  SELECT 1
  FROM (VALUES
    (N'FK_ProductionLot_RunProduct'), (N'FK_ProductionLot_Product'),
    (N'FK_ProductionLot_StandardRevision'), (N'FK_ProductionLot_ShiftScheduleVersion'),
    (N'FK_ProductionLot_Shift'), (N'FK_ProductionLot_ScheduledShift'),
    (N'FK_AutoLotResetReview_Lot'), (N'FK_AutoLotResetReview_Shift'),
    (N'FK_AutoLotResetReview_Schedule'), (N'FK_ProductionEntry_Lot'),
    (N'FK_ProductionEntry_LotStandard'), (N'FK_ProductionEntry_ShiftScheduleVersion'),
    (N'FK_ProductionEntry_Shift'), (N'FK_ProductionEntry_ScheduledShift'),
    (N'FK_ProductionEntryCorrection_Entry'), (N'FK_CuringInputEntry_Lot'),
    (N'FK_DepalletEvent_Lot'), (N'FK_DispatchLine_Dispatch'), (N'FK_DispatchLine_Lot')
  ) AS required(name)
  WHERE NOT EXISTS (SELECT 1 FROM sys.foreign_keys AS fk WHERE fk.schema_id = SCHEMA_ID(N'omagmes') AND fk.name = required.name)
)
  THROW 53313, 'One or more Migration 003 relationship foreign keys are missing.', 1;

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id = OBJECT_ID(N'omagmes.LotNumberSequence') AND name = N'UQ_LotNumberSequence_Scope' AND is_unique = 1)
   OR NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id = OBJECT_ID(N'omagmes.ProductionLot') AND name = N'UX_ProductionLot_OneOpenPerRun' AND is_unique = 1)
  THROW 53314, 'Migration 003 sequence scope or one-open-Lot index is missing.', 1;

SELECT s.name AS TableName, c.name AS ColumnName, ty.name AS SqlType,
       c.is_nullable AS IsNullable, c.is_identity AS IsIdentity,
       dc.definition AS DefaultDefinition
FROM sys.tables AS t
JOIN sys.schemas AS s ON s.schema_id = t.schema_id
JOIN sys.columns AS c ON c.object_id = t.object_id
JOIN sys.types AS ty ON ty.user_type_id = c.user_type_id
LEFT JOIN sys.default_constraints AS dc ON dc.parent_object_id = c.object_id AND dc.parent_column_id = c.column_id
WHERE s.name = N'omagmes'
  AND t.name IN (N'Product',N'ProductStandardRevision',N'ProductionRun',N'ProductionLot',
      N'ProductionLotNameHistory',N'ProductionEntry',N'ProductionEntryCorrection',
      N'CuringInputEntry',N'DepalletEvent',N'Dispatch',N'DispatchLine',N'LotNumberSequence',N'AutoLotResetReview')
ORDER BY t.name, c.column_id;

SELECT fk.name AS ForeignKeyName, OBJECT_NAME(fk.parent_object_id) AS ChildTable,
       OBJECT_NAME(fk.referenced_object_id) AS ParentTable
FROM sys.foreign_keys AS fk
WHERE fk.schema_id = SCHEMA_ID(N'omagmes')
  AND OBJECT_NAME(fk.parent_object_id) IN (N'ProductStandardRevision',N'ProductionRun',N'ProductionLot',
      N'ProductionLotNameHistory',N'ProductionEntry',N'ProductionEntryCorrection',
      N'CuringInputEntry',N'DepalletEvent',N'DispatchLine',N'LotNumberSequence',N'AutoLotResetReview')
ORDER BY ChildTable, fk.name;
