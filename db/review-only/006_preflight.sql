/*
SELECT-only preflight for Migration 006. Run in existing OMAG before the
authorized DBA deployment. This script performs no DDL/DML and does not query
remote plan rows or modify dbo.PRESS.
*/
SET NOCOUNT ON;
IF DB_NAME() <> N'OMAG'
    THROW 53610, 'Migration 006 preflight only applies to OMAG.', 1;

SELECT @@SERVERNAME AS ServerName, DB_NAME() AS DatabaseName,
       ORIGINAL_LOGIN() AS OriginalLogin, SUSER_SNAME() AS SqlLogin,
       USER_NAME() AS DatabaseUser, IS_SRVROLEMEMBER(N'sysadmin') AS IsSysadmin,
       HAS_PERMS_BY_NAME(N'omagmes.AutoLotCandidateWindow',N'OBJECT',N'ALTER') AS CanAlterCandidate,
       HAS_PERMS_BY_NAME(N'omagmes.AutoLotCandidateWindowHistory',N'OBJECT',N'ALTER') AS CanAlterHistory,
       HAS_PERMS_BY_NAME(N'omagmes.v_PressDailyDiff',N'OBJECT',N'ALTER') AS CanAlterDailyDiff;

SELECT s.name AS SchemaName, o.name AS ObjectName, o.type_desc AS ObjectType
FROM sys.objects AS o
JOIN sys.schemas AS s ON s.schema_id=o.schema_id
WHERE s.name=N'omagmes'
  AND o.name IN (N'AutoLotCandidateWindow',N'AutoLotCandidateWindowHistory',
                 N'v_PressDailyDiff',N'v_PressLotDiff',N'v_PressLotACC',
                 N'v_AutoLotDetectedWindow')
ORDER BY o.name;

SELECT t.name AS TableName, c.name AS ColumnName, ty.name AS DataType,
       c.max_length AS MaxLengthBytes, c.is_nullable AS IsNullable,
       c.is_identity AS IsIdentity
FROM sys.tables AS t
JOIN sys.schemas AS s ON s.schema_id=t.schema_id
JOIN sys.columns AS c ON c.object_id=t.object_id
JOIN sys.types AS ty ON ty.user_type_id=c.user_type_id
WHERE s.name=N'omagmes'
  AND t.name IN (N'AutoLotCandidateWindow',N'AutoLotCandidateWindowHistory')
ORDER BY t.name,c.column_id;

SELECT c.column_id,c.name,ty.name AS DataType,c.max_length,c.precision,c.scale,c.is_nullable
FROM sys.columns AS c
JOIN sys.types AS ty ON ty.user_type_id=c.user_type_id
WHERE c.object_id=OBJECT_ID(N'dbo.vw_OmagPlan',N'V')
ORDER BY c.column_id;

SELECT CandidateKind,CandidateStatus,COUNT_BIG(*) AS CandidateCount
FROM omagmes.AutoLotCandidateWindow
GROUP BY CandidateKind,CandidateStatus;

SELECT N'REQUIRED_INSTALLED_OBJECT' AS CheckName, name AS ObjectName,
       CASE WHEN OBJECT_ID(N'omagmes.'+QUOTENAME(name)) IS NULL THEN N'MISSING' ELSE N'PRESENT' END AS CheckResult
FROM (VALUES (N'AutoLotCandidateWindow'),(N'AutoLotCandidateWindowHistory'),
             (N'v_PressDailyDiff'),(N'v_PressLotDiff'),(N'v_PressLotACC')) AS required(name);

/* Stop if any 006 column/view already exists; inspect partial deployment. */
SELECT N'006_OBJECT_COLLISION' AS CheckName, OBJECT_ID(N'omagmes.v_AutoLotDetectedWindow') AS DetectedWindowViewID,
       COL_LENGTH(N'omagmes.AutoLotCandidateWindow',N'PlanSourceKey') AS PlanSourceKeyColumnLength,
  COL_LENGTH(N'omagmes.AutoLotCandidateWindow',N'PlanSnapshotJson') AS PlanSnapshotColumnLength,
  COL_LENGTH(N'omagmes.AutoLotCandidateWindow',N'PlanMaterialCode') AS PlanMaterialColumnLength,
  COL_LENGTH(N'omagmes.AutoLotCandidateWindow',N'PlanMatchStatus') AS PlanMatchStatusColumnLength,
  COL_LENGTH(N'omagmes.AutoLotCandidateWindow',N'PlanSelectedAt') AS PlanSelectedAtColumnLength,
  COL_LENGTH(N'omagmes.AutoLotCandidateWindow',N'PlanSelectedBy') AS PlanSelectedByColumnLength,
  COL_LENGTH(N'omagmes.AutoLotCandidateWindow',N'OperatorBoundaryConfirmed') AS BoundaryConfirmedColumnLength,
  COL_LENGTH(N'omagmes.AutoLotCandidateWindowHistory',N'ChangeSource') AS ChangeSourceColumnLength,
  COL_LENGTH(N'omagmes.AutoLotCandidateWindowHistory',N'PreviousStateJson') AS BeforeStateColumnLength,
  COL_LENGTH(N'omagmes.AutoLotCandidateWindowHistory',N'NewStateJson') AS AfterStateColumnLength,
       (SELECT index_id FROM sys.indexes WHERE object_id=OBJECT_ID(N'omagmes.AutoLotCandidateWindow')
         AND name=N'IX_AutoLotCandidateWindow_PlanSourceKey') AS PlanIndexID,
  OBJECT_ID(N'omagmes.DF_AutoLotCandidateWindow_BoundaryConfirmed') AS BoundaryDefaultID,
  OBJECT_ID(N'omagmes.DF_AutoLotCandidateWindowHistory_ChangeSource') AS HistoryDefaultID;