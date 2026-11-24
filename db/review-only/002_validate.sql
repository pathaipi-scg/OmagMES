/*
READ-ONLY VALIDATION DRAFT for 002_production_day_and_shift_configuration.sql.
Not run against SQL Server. Execute only after approved migration under reviewed target access.
*/
SET NOCOUNT ON;
IF DB_NAME() <> N'OMAG'
    THROW 51300, 'Validation draft targets database OMAG only.', 1;

DECLARE @RequiredTables table (TableName sysname NOT NULL PRIMARY KEY);
INSERT INTO @RequiredTables(TableName) VALUES
    (N'ProductionDayCutoffVersion'), (N'Shift'), (N'ShiftScheduleVersion'), (N'ShiftScheduleShift');

SELECT r.TableName AS MissingTable
FROM @RequiredTables AS r
LEFT JOIN sys.schemas AS s ON s.name = N'omagmes'
LEFT JOIN sys.tables AS t ON t.schema_id = s.schema_id AND t.name = r.TableName
WHERE t.object_id IS NULL;

SELECT t.name AS TableName,
       MAX(CASE WHEN c.name = N'id' AND ty.name = N'bigint' AND c.is_identity = 1 THEN 1 ELSE 0 END) AS HasRequiredIdentityID,
       MAX(CASE WHEN c.name = N'Rectime' AND ty.name = N'datetime' AND c.is_nullable = 0 THEN 1 ELSE 0 END) AS HasRequiredRectime,
       MAX(CASE WHEN kc.type = N'PK' AND c.name = N'id' THEN 1 ELSE 0 END) AS IDIsPrimaryKey
FROM sys.schemas AS s
JOIN sys.tables AS t ON t.schema_id = s.schema_id
JOIN sys.columns AS c ON c.object_id = t.object_id
JOIN sys.types AS ty ON ty.user_type_id = c.user_type_id
LEFT JOIN sys.key_constraints AS kc ON kc.parent_object_id = t.object_id AND kc.type = N'PK'
WHERE s.name = N'omagmes' AND t.name IN (SELECT TableName FROM @RequiredTables)
GROUP BY t.name
ORDER BY t.name;

SELECT fk.name AS ForeignKeyName, OBJECT_NAME(fk.parent_object_id) AS SourceTable,
       OBJECT_NAME(fk.referenced_object_id) AS TargetTable, fk.is_disabled AS IsDisabled
FROM sys.foreign_keys AS fk
WHERE OBJECT_SCHEMA_NAME(fk.parent_object_id) = N'omagmes'
  AND OBJECT_NAME(fk.parent_object_id) IN (N'ShiftScheduleShift')
ORDER BY SourceTable, ForeignKeyName;

SELECT tr.name AS TriggerName, OBJECT_NAME(tr.parent_id) AS TableName, tr.is_disabled AS IsDisabled
FROM sys.triggers AS tr
WHERE tr.name IN (N'TR_ProductionDayCutoffVersion_Immutable', N'TR_ShiftScheduleVersion_Immutable',
                  N'TR_ShiftScheduleShift_Immutable', N'TR_Shift_Immutable')
ORDER BY tr.name;

SELECT N'No seed records are expected in this migration. Owner-approved cutoff/schedule bootstrap is a separate gate.' AS SeedReview;
