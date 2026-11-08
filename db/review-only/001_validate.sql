/*
READ-ONLY VALIDATION DRAFT for 001_omagmes_foundation.sql.
Not run against any SQL Server. Confirm target server/database separately; this script does not identify the host.
*/
SET NOCOUNT ON;
IF DB_NAME() <> N'OMAG'
    THROW 51100, 'Validation draft targets database OMAG only.', 1;

DECLARE @RequiredTables table (TableName sysname NOT NULL PRIMARY KEY);
INSERT INTO @RequiredTables(TableName) VALUES
    (N'AppUser'), (N'Plant'), (N'ProductionLine'), (N'ProductFamily'), (N'Product'),
    (N'ProductCodeAssignment'), (N'Color'), (N'ProductProductionStandard'),
    (N'ProductionRun'), (N'ProductionLot'), (N'LotNameChangeHistory'),
    (N'ProductionEntry'), (N'ProductionEntryCorrection'), (N'WetRejectReason'),
    (N'WetRejectEntry'), (N'WetRunEvent'), (N'CuringRecord'), (N'DepalletEvent'),
    (N'Mould'), (N'MouldStatusHistory'), (N'MouldReconditionCycle'), (N'MouldUseEvent'),
    (N'PressCounterObservation'), (N'PressCounterResetBoundary'), (N'WetCameraObservation'),
    (N'PressCounterAccumulator'), (N'PressCounterStep');

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
WHERE s.name = N'omagmes'
GROUP BY t.name
ORDER BY t.name;

SELECT fk.name AS ForeignKeyName,
       OBJECT_SCHEMA_NAME(fk.parent_object_id) AS SourceSchema,
       OBJECT_NAME(fk.parent_object_id) AS SourceTable,
       OBJECT_SCHEMA_NAME(fk.referenced_object_id) AS TargetSchema,
       OBJECT_NAME(fk.referenced_object_id) AS TargetTable,
       fk.is_disabled AS IsDisabled
FROM sys.foreign_keys AS fk
WHERE OBJECT_SCHEMA_NAME(fk.parent_object_id) = N'omagmes'
ORDER BY SourceTable, ForeignKeyName;

SELECT N'No seed records are expected in this review draft.' AS SeedReview;
