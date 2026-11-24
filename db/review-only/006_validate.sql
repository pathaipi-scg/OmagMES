/*
SELECT-only validation for Migration 006 after an authorized DBA deployment.
Does not insert test data and never modifies dbo.PRESS or production plans.
*/
SET NOCOUNT ON;
IF DB_NAME() <> N'OMAG'
    THROW 53620, 'Migration 006 validation only applies to OMAG.', 1;

SELECT v.ObjectName,
       CASE WHEN o.object_id IS NULL THEN N'MISSING' ELSE N'PRESENT' END AS ValidationStatus
FROM (VALUES
    (N'AutoLotCandidateWindow',N'U'),
    (N'AutoLotCandidateWindowHistory',N'U'),
    (N'v_AutoLotDetectedWindow',N'V'),
    (N'v_PressDailyDiff',N'V'),
    (N'v_PressLotDiff',N'V'),
    (N'v_PressLotACC',N'V'),
    (N'v_PressLotSummary',N'V')
) AS v(ObjectName,ObjectType)
LEFT JOIN sys.objects AS o ON o.schema_id=SCHEMA_ID(N'omagmes')
                         AND o.name=v.ObjectName AND o.type=v.ObjectType
ORDER BY v.ObjectName;

SELECT t.name AS TableName,c.name AS ColumnName,ty.name AS DataType,
       c.max_length,c.is_nullable,c.is_identity
FROM sys.tables AS t
JOIN sys.schemas AS s ON s.schema_id=t.schema_id
JOIN sys.columns AS c ON c.object_id=t.object_id
JOIN sys.types AS ty ON ty.user_type_id=c.user_type_id
WHERE s.name=N'omagmes'
  AND ((t.name=N'AutoLotCandidateWindow' AND c.name IN
        (N'PlanSourceKey',N'PlanSnapshotJson',N'PlanMaterialCode',N'PlanMatchStatus',N'PlanSelectedAt',N'PlanSelectedBy',N'OperatorBoundaryConfirmed'))
    OR (t.name=N'AutoLotCandidateWindowHistory' AND c.name IN
        (N'ChangeSource',N'PreviousStateJson',N'NewStateJson')))
ORDER BY t.name,c.column_id;

SELECT CandidateKind,CandidateStatus,COUNT_BIG(*) AS CandidateCount
FROM omagmes.AutoLotCandidateWindow
GROUP BY CandidateKind,CandidateStatus;

SELECT TOP (100) CandidateKey,FirstSourceID,ResetSourceID,ResetPreviousSourceID,
       ProposedStartTime,ProposedEndTime,BoundaryEvidence,
       BoundaryEarliestEvidenceAt,BoundaryLatestEvidenceAt,
       ProductionDate,CutoffVersionID,ShiftScheduleVersionID,ShiftID,
       RequiresOperatorConfirmation,IsProvisional,DetectionNote
FROM omagmes.v_AutoLotDetectedWindow
ORDER BY ProposedStartTime DESC,FirstSourceID DESC;

SELECT TOP (100) LotIdentityType,LotIdentityID,CandidateWindowID,LotStatus,
       StartTime,EndTime,Diff,DiffStatus,AllocationStatus,IsAllocated,
       AllocatedDiff,LotACC
FROM omagmes.v_PressLotACC
WHERE LotIdentityType=N'CANDIDATE'
ORDER BY RecTime DESC,SourceID DESC;

SELECT d.SourceID,d.PreviousSourceID,d.PreviousRecTime,d.RecTime,
       d.PreviousCounterValue,d.CounterValue,d.Diff,d.ResetDetected,
       d.Unchanged,d.DiffStatus,d.QualityCode
FROM omagmes.v_PressDailyDiff AS d
WHERE d.DiffStatus IN (N'POSITIVE_DELTA',N'UNCHANGED',N'RESET_BASELINE_NOT_CREDITED')
ORDER BY d.RecTime DESC,d.SourceID DESC;

SELECT fk.name AS ForeignKeyName,OBJECT_NAME(fk.parent_object_id) AS ParentTable,
       OBJECT_NAME(fk.referenced_object_id) AS ReferencedTable
FROM sys.foreign_keys AS fk
WHERE fk.parent_object_id IN (OBJECT_ID(N'omagmes.AutoLotCandidateWindow'),
                              OBJECT_ID(N'omagmes.AutoLotCandidateWindowHistory'))
ORDER BY fk.name;

SELECT name AS CandidateIndex,is_unique,filter_definition
FROM sys.indexes
WHERE object_id=OBJECT_ID(N'omagmes.AutoLotCandidateWindow')
  AND name=N'IX_AutoLotCandidateWindow_PlanSourceKey';

SELECT d.referenced_schema_name,d.referenced_entity_name
FROM sys.sql_expression_dependencies AS d
WHERE d.referencing_id=OBJECT_ID(N'omagmes.v_PressDailyDiff',N'V')
  AND d.referenced_id=OBJECT_ID(N'omagmes.PressDiffQualityPolicy',N'U');

/* Plan view metadata is local catalog metadata; a SELECT of remote plan rows
   separately requires the linked-server login mapping and is not run here. */
SELECT c.column_id,c.name,ty.name AS DataType,c.max_length,c.precision,c.scale,c.is_nullable
FROM sys.columns AS c
JOIN sys.types AS ty ON ty.user_type_id=c.user_type_id
WHERE c.object_id=OBJECT_ID(N'dbo.vw_OmagPlan',N'V')
ORDER BY c.column_id;