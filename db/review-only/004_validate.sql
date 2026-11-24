/*
REVIEW-ONLY validator for migration 004. DBA executes only after approval.
Read-only checks; it does not write or alter schema/data.
*/
SET NOCOUNT ON;
IF DB_NAME() <> N'OMAG'
    THROW 53410, 'Migration 004 validation only applies to OMAG.', 1;

SELECT r.ObjectName, r.ObjectType,
       CASE WHEN o.object_id IS NULL THEN 'MISSING' ELSE 'PRESENT' END AS ValidationStatus
FROM (VALUES
    (N'PressDiffQualityPolicy', 'U'),
    (N'AutoLotCandidateWindow', 'U'),
    (N'AutoLotCandidateWindowHistory', 'U'),
    (N'v_PressDailyDiff', 'V'),
    (N'v_PressLotDiff', 'V'),
    (N'v_PressLotACC', 'V'),
    (N'v_PressDiffReconciliation', 'V'),
    (N'v_PressLotSummary', 'V')
) AS r(ObjectName, ObjectType)
LEFT JOIN sys.objects AS o ON o.schema_id = SCHEMA_ID(N'omagmes')
                          AND o.name = r.ObjectName AND o.type = r.ObjectType
ORDER BY r.ObjectName;

IF EXISTS (
    SELECT 1 FROM (VALUES
        (N'PressDiffQualityPolicy', 'U'),
        (N'AutoLotCandidateWindow', 'U'),
        (N'AutoLotCandidateWindowHistory', 'U'),
        (N'v_PressDailyDiff', 'V'),
        (N'v_PressLotDiff', 'V'),
        (N'v_PressLotACC', 'V'),
        (N'v_PressDiffReconciliation', 'V'),
        (N'v_PressLotSummary', 'V')
    ) AS r(ObjectName, ObjectType)
    WHERE NOT EXISTS (SELECT 1 FROM sys.objects AS o
                      WHERE o.schema_id = SCHEMA_ID(N'omagmes')
                        AND o.name = r.ObjectName AND o.type = r.ObjectType)
)
    THROW 53411, 'One or more migration 004 objects are missing.', 1;

IF EXISTS (
    SELECT 1
    FROM sys.sql_expression_dependencies AS d
    WHERE d.referencing_id = OBJECT_ID(N'omagmes.v_PressDailyDiff', N'V')
      AND d.referenced_id = OBJECT_ID(N'omagmes.PressDiffQualityPolicy', N'U')
)
    THROW 53412, 'v_PressDailyDiff still depends on PressDiffQualityPolicy; apply the targeted quality-independent view patch.', 1;

SELECT OBJECT_SCHEMA_NAME(referencing_id) AS SchemaName,
       OBJECT_NAME(referencing_id) AS ViewName,
       referenced_schema_name AS ReferencedSchema,
       referenced_entity_name AS ReferencedObject
FROM sys.sql_expression_dependencies
WHERE referencing_id IN (
    OBJECT_ID(N'omagmes.v_PressDailyDiff'), OBJECT_ID(N'omagmes.v_PressLotDiff'),
    OBJECT_ID(N'omagmes.v_PressLotACC'), OBJECT_ID(N'omagmes.v_PressDiffReconciliation'),
    OBJECT_ID(N'omagmes.v_PressLotSummary'))
ORDER BY ViewName, ReferencedSchema, ReferencedObject;

SELECT name AS CandidateIndex
FROM sys.indexes
WHERE object_id = OBJECT_ID(N'omagmes.AutoLotCandidateWindow')
  AND name IN (N'UX_AutoLotCandidateWindow_OfficialLot', N'IX_AutoLotCandidateWindow_EffectiveWindow', N'IX_AutoLotCandidateWindow_ProductionDate');

SELECT OBJECT_NAME(object_id) AS ViewName, definition
FROM sys.sql_modules
WHERE object_id IN (
    OBJECT_ID(N'omagmes.v_PressDailyDiff'), OBJECT_ID(N'omagmes.v_PressLotDiff'),
    OBJECT_ID(N'omagmes.v_PressLotACC'), OBJECT_ID(N'omagmes.v_PressDiffReconciliation'),
    OBJECT_ID(N'omagmes.v_PressLotSummary'));

/* Smoke-test reads; _QUALITY is informational and does not gate Diff.
    These queries are intentionally not aggregated into a presumed business total. */
SELECT TOP (20) SourceID, RecTime, PreviousSourceID, PreviousRecTime,
       CounterValue, PreviousCounterValue, QualityCode, Diff, DiffStatus,
       ProductionDate, ProductionDateUnresolved
FROM omagmes.v_PressDailyDiff
ORDER BY RecTime DESC, SourceID DESC;

/* Owner-confirmed rule check: these pairs must calculate from counter values
    regardless of QualityCode. The result is observational; it writes no data. */
SELECT TOP (100) SourceID, RecTime, CounterValue, PreviousCounterValue,
         QualityCode, Diff, DiffStatus, ResetDetected
FROM omagmes.v_PressDailyDiff
WHERE (CounterValue = 202 AND PreviousCounterValue = 201)
    OR (CounterValue = 197 AND PreviousCounterValue = 197)
    OR ResetDetected = 1
ORDER BY RecTime DESC, SourceID DESC;

SELECT TOP (100) SourceID, RecTime, LotIdentityType, LotIdentityID,
       AllocationStatus, Diff, AllocatedDiff, LotACC
FROM omagmes.v_PressLotACC
ORDER BY RecTime DESC, SourceID DESC;

SELECT * FROM omagmes.v_PressDiffReconciliation ORDER BY ProductionDate DESC;
SELECT * FROM omagmes.v_PressLotSummary ORDER BY StartTime DESC, LotIdentityID DESC;
