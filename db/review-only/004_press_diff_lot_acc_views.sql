:ON ERROR EXIT
/*
REVIEW-ONLY DRAFT — DO NOT EXECUTE WITHOUT SEPARATE DBA/OWNER AUTHORIZATION.
Version 004 / 2026-11-17. Requires reviewed/applied migrations 002 and 003.
All new tables, indexes and views belong to OMAG.omagmes. The source
OMAG.dbo.PRESS is read-only and is never altered or copied.

Daily Diff policy:
* LAG spans the complete exact DropCnt history ordered by _TIMESTAMP,id; view
  consumers must filter outside the view so the predecessor is not lost at 07:00.
* NULL source timestamps are excluded from ordered Diff rows because they cannot
    be placed in event-time order; preflight/source monitoring must report them.
* A decrease is a reset baseline, not a Drop: Diff=0 and ResetDetected=1.
  The reset sample's absolute value is deliberately not credited. Its preceding
  interval is uncertain and excluded; the next valid sample can establish a
  normal delta. Equal samples produce zero; positive jumps retain the full delta.
* _QUALITY is informational and never gates Diff. Positive increases count;
    unchanged samples and reset/decrease samples produce zero; invalid values and
    missing predecessors remain explicitly classified. The legacy
    IsQualityEligible output is retained as a deprecated alias for valid numeric
    current/predecessor pairs, independent of _QUALITY.
* ProductionDate uses persisted effective-dated cutoff rows and raw SQL wall
  clock timestamps. Historian timestamp semantics still require confirmation.

Allocation policy:
* Half-open [StartTime,EndTime) windows. A delta is allocated only when both
    its CURRENT source sample timestamp falls inside a window; the previous sample
    may be outside it. Thus an event at a Lot start belongs to the new Lot. Official
    Lots take precedence over candidate windows. Multiple matching windows of the
    same identity type are AMBIGUOUS and receive no Drops. Events matching no
    window are UNALLOCATED.
* Candidate window edits are separate from immutable original proposals and are
  audited. Official Lot linkage is unique; linked drafts are excluded from views.
* No time aggregation, counter re-differencing, or ACC calculation occurs in
  Python. These views are the sole Diff/ACC implementation for OmagMES/Grafana.

No seed rows, candidate rows, Lots, source modifications, or permissions are
created outside this schema. The OMAG_MES principal has no DDL rights; DBA must
execute only after review. See 004_validate.sql, 004_rollback.sql, and the Grafana
query examples in docs/grafana_press_lot_queries.sql.
If separately approved, run in SQLCMD mode on one connection with :ON ERROR EXIT
enabled; stop on the first error and disconnect/rollback any open transaction.
*/
SET NOCOUNT ON;
SET XACT_ABORT ON;
IF DB_NAME() <> N'OMAG'
    THROW 53400, 'Review draft 004 only applies to database OMAG.', 1;
IF SCHEMA_ID(N'omagmes') IS NULL
    THROW 53401, 'Required omagmes schema is missing.', 1;
IF OBJECT_ID(N'omagmes.ProductionLot', N'U') IS NULL
   OR OBJECT_ID(N'omagmes.ProductionDayCutoffVersion', N'U') IS NULL
    OR OBJECT_ID(N'omagmes.ShiftScheduleVersion', N'U') IS NULL
   OR OBJECT_ID(N'omagmes.Product', N'U') IS NULL
   OR OBJECT_ID(N'omagmes.Shift', N'U') IS NULL
    THROW 53402, 'Migrations 002 and 003 must be reviewed and installed first.', 1;
IF OBJECT_ID(N'omagmes.AutoLotCandidateWindow') IS NOT NULL
    OR OBJECT_ID(N'omagmes.PressDiffQualityPolicy') IS NOT NULL
    OR OBJECT_ID(N'omagmes.AutoLotCandidateWindowHistory') IS NOT NULL
    OR OBJECT_ID(N'omagmes.v_PressDailyDiff') IS NOT NULL
    OR OBJECT_ID(N'omagmes.v_PressLotDiff') IS NOT NULL
    OR OBJECT_ID(N'omagmes.v_PressLotACC') IS NOT NULL
    OR OBJECT_ID(N'omagmes.v_PressDiffReconciliation') IS NOT NULL
    OR OBJECT_ID(N'omagmes.v_PressLotSummary') IS NOT NULL
    THROW 53403, 'One or more migration 004 objects already exist; inspect before proceeding.', 1;
GO

BEGIN TRANSACTION;
GO
CREATE TABLE omagmes.PressDiffQualityPolicy (
    id bigint IDENTITY(1,1) NOT NULL CONSTRAINT PK_PressDiffQualityPolicy PRIMARY KEY,
    Rectime datetime NOT NULL CONSTRAINT DF_PressDiffQualityPolicy_Rectime DEFAULT (GETDATE()),
    QualityCode int NOT NULL,
    EffectiveFrom datetime2(7) NOT NULL,
    EffectiveTo datetime2(7) NULL,
    IsAccepted bit NOT NULL,
    ChangeReason nvarchar(500) NOT NULL,
    CreatedBy nvarchar(200) NOT NULL,
    CONSTRAINT CK_PressDiffQualityPolicy_Period CHECK (EffectiveTo IS NULL OR EffectiveTo > EffectiveFrom),
    CONSTRAINT CK_PressDiffQualityPolicy_Reason CHECK (LEN(LTRIM(RTRIM(ChangeReason))) > 0)
);
CREATE INDEX IX_PressDiffQualityPolicy_Code_Period
    ON omagmes.PressDiffQualityPolicy(QualityCode, EffectiveFrom DESC, EffectiveTo);

CREATE TABLE omagmes.AutoLotCandidateWindow (
    id bigint IDENTITY(1,1) NOT NULL CONSTRAINT PK_AutoLotCandidateWindow PRIMARY KEY,
    Rectime datetime NOT NULL CONSTRAINT DF_AutoLotCandidateWindow_Rectime DEFAULT (GETDATE()),
    CandidateKey nvarchar(200) COLLATE Latin1_General_100_BIN2 NOT NULL,
    CandidateKind varchar(20) NOT NULL,
    SourceTag nvarchar(100) NOT NULL,
    FirstSourceID bigint NULL,
    ResetSourceID bigint NULL,
    ResetPreviousSourceID bigint NULL,
    ResetObservedAt datetime2(7) NULL,
    ResetPreviousAt datetime2(7) NULL,
    ResetValue bigint NULL,
    ResetPreviousValue bigint NULL,
    InitialProposedStartTime datetime2(7) NOT NULL,
    InitialProposedEndTime datetime2(7) NULL,
    CurrentProposedStartTime datetime2(7) NOT NULL,
    CurrentProposedEndTime datetime2(7) NULL,
    EffectiveStartTime datetime2(7) NOT NULL,
    EffectiveEndTime datetime2(7) NULL,
    OperatorTimeOverride bit NOT NULL CONSTRAINT DF_AutoLotCandidateWindow_OperatorTimeOverride DEFAULT (0),
    CandidateStatus varchar(20) NOT NULL CONSTRAINT DF_AutoLotCandidateWindow_CandidateStatus DEFAULT ('OPEN'),
    ProductionDate date NULL,
    CutoffVersionID bigint NULL,
    ShiftScheduleVersionID bigint NULL,
    ShiftID bigint NULL,
    ProductID bigint NULL,
    ColorCode nvarchar(60) COLLATE Latin1_General_100_BIN2 NULL,
    OfficialProductionLotID bigint NULL,
    CreatedBy nvarchar(200) NOT NULL CONSTRAINT DF_AutoLotCandidateWindow_CreatedBy DEFAULT (N'AUTO DETECTOR'),
    LastDetectedAt datetime2(7) NOT NULL,
    LastOperatorID nvarchar(200) NULL,
    LastOperatorReason nvarchar(500) NULL,
    CONSTRAINT UQ_AutoLotCandidateWindow_CandidateKey UNIQUE (CandidateKey),
    CONSTRAINT FK_AutoLotCandidateWindow_Cutoff FOREIGN KEY (CutoffVersionID) REFERENCES omagmes.ProductionDayCutoffVersion(id),
    CONSTRAINT FK_AutoLotCandidateWindow_Schedule FOREIGN KEY (ShiftScheduleVersionID) REFERENCES omagmes.ShiftScheduleVersion(id),
    CONSTRAINT FK_AutoLotCandidateWindow_Shift FOREIGN KEY (ShiftID) REFERENCES omagmes.Shift(id),
    CONSTRAINT FK_AutoLotCandidateWindow_Product FOREIGN KEY (ProductID) REFERENCES omagmes.Product(id),
    CONSTRAINT FK_AutoLotCandidateWindow_OfficialLot FOREIGN KEY (OfficialProductionLotID) REFERENCES omagmes.ProductionLot(id),
    CONSTRAINT CK_AutoLotCandidateWindow_Kind CHECK (CandidateKind IN ('RESET','MANUAL','SPLIT')),
    CONSTRAINT CK_AutoLotCandidateWindow_Status CHECK (CandidateStatus IN ('OPEN','CLOSED','REVIEWED','DISMISSED','MERGED')),
    CONSTRAINT CK_AutoLotCandidateWindow_Source CHECK (CandidateKind <> 'RESET' OR (ResetSourceID IS NOT NULL AND ResetPreviousSourceID IS NOT NULL AND ResetObservedAt IS NOT NULL AND ResetPreviousAt IS NOT NULL)),
    CONSTRAINT CK_AutoLotCandidateWindow_InitialPeriod CHECK (InitialProposedEndTime IS NULL OR InitialProposedEndTime > InitialProposedStartTime),
    CONSTRAINT CK_AutoLotCandidateWindow_CurrentPeriod CHECK (CurrentProposedEndTime IS NULL OR CurrentProposedEndTime > CurrentProposedStartTime),
    CONSTRAINT CK_AutoLotCandidateWindow_EffectivePeriod CHECK (EffectiveEndTime IS NULL OR EffectiveEndTime > EffectiveStartTime),
    CONSTRAINT CK_AutoLotCandidateWindow_OperatorMinutePrecision CHECK (
        OperatorTimeOverride = 0
        OR (DATEPART(SECOND, EffectiveStartTime) = 0 AND DATEPART(NANOSECOND, EffectiveStartTime) = 0
            AND (EffectiveEndTime IS NULL OR (DATEPART(SECOND, EffectiveEndTime) = 0 AND DATEPART(NANOSECOND, EffectiveEndTime) = 0)))
    ),
    CONSTRAINT CK_AutoLotCandidateWindow_ResetValues CHECK ((ResetValue IS NULL AND ResetPreviousValue IS NULL) OR (ResetValue >= 0 AND ResetPreviousValue >= 0)),
    CONSTRAINT CK_AutoLotCandidateWindow_LinkStatus CHECK (OfficialProductionLotID IS NULL OR CandidateStatus IN ('CLOSED','MERGED'))
);
CREATE UNIQUE INDEX UX_AutoLotCandidateWindow_OfficialLot
    ON omagmes.AutoLotCandidateWindow(OfficialProductionLotID) WHERE OfficialProductionLotID IS NOT NULL;
CREATE INDEX IX_AutoLotCandidateWindow_EffectiveWindow
    ON omagmes.AutoLotCandidateWindow(CandidateStatus, EffectiveStartTime, EffectiveEndTime)
    INCLUDE (OfficialProductionLotID, ProductionDate, ProductID, ColorCode, CandidateKey);
CREATE INDEX IX_AutoLotCandidateWindow_ProductionDate
    ON omagmes.AutoLotCandidateWindow(ProductionDate, CandidateStatus, id);

CREATE TABLE omagmes.AutoLotCandidateWindowHistory (
    id bigint IDENTITY(1,1) NOT NULL CONSTRAINT PK_AutoLotCandidateWindowHistory PRIMARY KEY,
    Rectime datetime NOT NULL CONSTRAINT DF_AutoLotCandidateWindowHistory_Rectime DEFAULT (GETDATE()),
    CandidateWindowID bigint NOT NULL,
    ActionCode varchar(20) NOT NULL,
    PreviousStartTime datetime2(7) NULL,
    PreviousEndTime datetime2(7) NULL,
    NewStartTime datetime2(7) NULL,
    NewEndTime datetime2(7) NULL,
    PreviousStatus varchar(20) NULL,
    NewStatus varchar(20) NULL,
    RelatedCandidateWindowID bigint NULL,
    ChangedBy nvarchar(200) NOT NULL,
    ChangeReason nvarchar(500) NOT NULL,
    ChangedAt datetime2(7) NOT NULL CONSTRAINT DF_AutoLotCandidateWindowHistory_ChangedAt DEFAULT (SYSUTCDATETIME()),
    CONSTRAINT FK_AutoLotCandidateWindowHistory_Candidate FOREIGN KEY (CandidateWindowID) REFERENCES omagmes.AutoLotCandidateWindow(id),
    CONSTRAINT FK_AutoLotCandidateWindowHistory_RelatedCandidate FOREIGN KEY (RelatedCandidateWindowID) REFERENCES omagmes.AutoLotCandidateWindow(id),
    CONSTRAINT CK_AutoLotCandidateWindowHistory_Action CHECK (ActionCode IN ('CREATED','EDITED','SPLIT','MERGED','DISMISSED','OFFICIAL_LINK')),
    CONSTRAINT CK_AutoLotCandidateWindowHistory_Reason CHECK (LEN(LTRIM(RTRIM(ChangeReason))) > 0)
);
CREATE INDEX IX_AutoLotCandidateWindowHistory_Candidate_ChangedAt
    ON omagmes.AutoLotCandidateWindowHistory(CandidateWindowID, ChangedAt DESC, id DESC);
GO

/* _QUALITY remains visible as source metadata only; it is not a Diff gate. */
CREATE OR ALTER VIEW omagmes.v_PressDailyDiff
AS
WITH SourceRows AS (
    SELECT p.id AS SourceID,
           CONVERT(datetime2(7), p._TIMESTAMP) AS RecTime,
           p._NAME AS SourceTag,
           p._VALUE AS RawCounterValue,
           p._QUALITY AS QualityCode,
           TRY_CONVERT(decimal(20,0), NULLIF(LTRIM(RTRIM(p._VALUE)), '')) AS CounterValue,
                     TRY_CONVERT(decimal(20,6), NULLIF(LTRIM(RTRIM(p._VALUE)), '')) AS NumericCounterValue,
                     CASE WHEN TRY_CONVERT(decimal(20,0), NULLIF(LTRIM(RTRIM(p._VALUE)), '')) IS NOT NULL
                                         AND TRY_CONVERT(decimal(20,6), NULLIF(LTRIM(RTRIM(p._VALUE)), '')) = TRY_CONVERT(decimal(20,0), NULLIF(LTRIM(RTRIM(p._VALUE)), ''))
                                         AND TRY_CONVERT(decimal(20,0), NULLIF(LTRIM(RTRIM(p._VALUE)), '')) BETWEEN 0 AND 9223372036854775807
                                THEN 1 ELSE 0 END AS CurrentValueValid
    FROM OMAG.dbo.PRESS AS p
        WHERE p._NAME COLLATE Latin1_General_100_BIN2 = 'OMAG.PRESS.OEE.DropCnt' COLLATE Latin1_General_100_BIN2
            AND p._TIMESTAMP IS NOT NULL
), OrderedRows AS (
    SELECT s.*,
           LAG(s.SourceID) OVER (ORDER BY s.RecTime, s.SourceID) AS PreviousSourceID,
           LAG(s.RecTime) OVER (ORDER BY s.RecTime, s.SourceID) AS PreviousRecTime,
           LAG(s.CounterValue) OVER (ORDER BY s.RecTime, s.SourceID) AS PreviousCounterValue,
           LAG(s.CurrentValueValid) OVER (ORDER BY s.RecTime, s.SourceID) AS PreviousValueValid
    FROM SourceRows AS s
), DateContext AS (
    SELECT o.*,
           currentCutoff.CutoffTime AS CurrentDateCutoff,
           priorCutoff.CutoffTime AS PriorDateCutoff,
           CASE WHEN o.RecTime >= DATEADD(SECOND, DATEDIFF(SECOND, CONVERT(time(0),'00:00'), currentCutoff.CutoffTime), CONVERT(datetime2(7), CONVERT(date, o.RecTime)))
                THEN CONVERT(date, o.RecTime)
                WHEN priorCutoff.CutoffTime IS NOT NULL THEN DATEADD(DAY, -1, CONVERT(date, o.RecTime))
                ELSE NULL END AS ProductionDate
    FROM OrderedRows AS o
    OUTER APPLY (
        SELECT TOP (1) c.CutoffTime
        FROM omagmes.ProductionDayCutoffVersion AS c
        WHERE c.EffectiveFromProductionDate <= CONVERT(date, o.RecTime)
        ORDER BY c.EffectiveFromProductionDate DESC, c.id DESC
    ) AS currentCutoff
    OUTER APPLY (
        SELECT TOP (1) c.CutoffTime
        FROM omagmes.ProductionDayCutoffVersion AS c
        WHERE c.EffectiveFromProductionDate <= DATEADD(DAY, -1, CONVERT(date, o.RecTime))
        ORDER BY c.EffectiveFromProductionDate DESC, c.id DESC
    ) AS priorCutoff
), Classified AS (
    SELECT d.*,
           CASE WHEN d.PreviousSourceID IS NULL THEN 'FIRST_SAMPLE'
                WHEN d.CurrentValueValid = 0 THEN 'INVALID_COUNTER_VALUE'
                WHEN d.PreviousValueValid = 0 THEN 'PREVIOUS_COUNTER_INVALID'
                WHEN d.CounterValue < d.PreviousCounterValue THEN 'RESET_BASELINE_NOT_CREDITED'
                WHEN d.CounterValue = d.PreviousCounterValue THEN 'UNCHANGED'
                ELSE 'POSITIVE_DELTA' END AS DiffStatus
    FROM DateContext AS d
)
SELECT c.SourceID,
       c.RecTime,
       c.SourceTag,
       c.QualityCode,
       c.CounterValue,
       c.PreviousSourceID,
       c.PreviousRecTime,
       c.PreviousCounterValue,
    CAST(CASE WHEN c.CurrentValueValid = 1 AND c.PreviousValueValid = 1
              AND c.CounterValue < c.PreviousCounterValue THEN 1 ELSE 0 END AS bit) AS ResetDetected,
    CAST(CASE WHEN c.CurrentValueValid = 1 AND c.PreviousValueValid = 1
              AND c.CounterValue = c.PreviousCounterValue THEN 1 ELSE 0 END AS bit) AS Unchanged,
    CAST(CASE WHEN c.CurrentValueValid = 1 AND c.PreviousValueValid = 1 THEN 1 ELSE 0 END AS bit) AS IsQualityEligible,
       CASE WHEN c.DiffStatus = 'POSITIVE_DELTA' THEN CONVERT(bigint, c.CounterValue - c.PreviousCounterValue)
            WHEN c.DiffStatus IN ('UNCHANGED','RESET_BASELINE_NOT_CREDITED') THEN CONVERT(bigint, 0)
            ELSE CONVERT(bigint, NULL) END AS Diff,
       c.DiffStatus,
       c.ProductionDate,
       CAST(CASE WHEN c.ProductionDate IS NULL THEN 1 ELSE 0 END AS bit) AS ProductionDateUnresolved
FROM Classified AS c;
GO

CREATE VIEW omagmes.v_PressLotDiff
AS
WITH Windows AS (
    SELECT CAST('OFFICIAL' AS varchar(10)) AS LotIdentityType,
           l.id AS LotIdentityID,
           l.id AS OfficialProductionLotID,
           CAST(NULL AS bigint) AS CandidateWindowID,
           l.LotNo AS LotNumber,
           CAST('OFFICIAL' AS varchar(20)) AS LotStatus,
           CONVERT(datetime2(7), l.LotStartedAt) AS StartTime,
           CONVERT(datetime2(7), l.LotEndedAt) AS EndTime,
           l.ProductionDate,
           l.ShiftID,
           l.ProductID,
           l.ColorCode
    FROM omagmes.ProductionLot AS l
    UNION ALL
    SELECT CAST('CANDIDATE' AS varchar(10)),
           c.id,
           CAST(NULL AS bigint),
           c.id,
           CAST(NULL AS varchar(11)),
           c.CandidateStatus,
           c.EffectiveStartTime,
           c.EffectiveEndTime,
                     c.ProductionDate,
                     c.ShiftID,
                     c.ProductID,
           c.ColorCode
    FROM omagmes.AutoLotCandidateWindow AS c
    WHERE c.OfficialProductionLotID IS NULL
      AND c.CandidateStatus IN ('OPEN','CLOSED','REVIEWED')
), DiffRows AS (
    SELECT d.*
    FROM omagmes.v_PressDailyDiff AS d
    WHERE d.PreviousSourceID IS NOT NULL
), MatchCounts AS (
    SELECT d.SourceID,
        COUNT_BIG(CASE WHEN w.LotIdentityType = 'OFFICIAL' THEN 1 END) AS OfficialMatchCount,
        MIN(CASE WHEN w.LotIdentityType = 'OFFICIAL' THEN w.LotIdentityID END) AS OfficialLotID,
        COUNT_BIG(CASE WHEN w.LotIdentityType = 'CANDIDATE' THEN 1 END) AS CandidateMatchCount,
        MIN(CASE WHEN w.LotIdentityType = 'CANDIDATE' THEN w.LotIdentityID END) AS CandidateID
    FROM DiffRows AS d
    LEFT JOIN Windows AS w
      ON d.RecTime >= w.StartTime
     AND (w.EndTime IS NULL OR d.RecTime < w.EndTime)
    GROUP BY d.SourceID
), Chosen AS (
    SELECT d.*,
           m.OfficialMatchCount,
           CONVERT(bigint, 0) AS OfficialBoundaryCount,
           m.CandidateMatchCount,
           CONVERT(bigint, 0) AS CandidateBoundaryCount,
           CASE WHEN m.OfficialMatchCount = 1 THEN 'OFFICIAL'
                WHEN m.OfficialMatchCount > 1 THEN NULL
                WHEN m.CandidateMatchCount = 1 THEN 'CANDIDATE'
                ELSE NULL END AS LotIdentityType,
           CASE WHEN m.OfficialMatchCount = 1 THEN m.OfficialLotID
                WHEN m.OfficialMatchCount = 0 AND m.CandidateMatchCount = 1 THEN m.CandidateID
                ELSE NULL END AS LotIdentityID
    FROM DiffRows AS d
    JOIN MatchCounts AS m ON m.SourceID = d.SourceID
)
SELECT c.SourceID,
       c.RecTime,
       c.ProductionDate AS DiffProductionDate,
       c.QualityCode,
       c.CounterValue,
       c.PreviousSourceID,
       c.PreviousRecTime,
       c.PreviousCounterValue,
       c.ResetDetected,
       c.Unchanged,
       c.IsQualityEligible,
       c.Diff,
       c.DiffStatus,
             c.ProductionDateUnresolved,
       c.LotIdentityType,
       c.LotIdentityID,
       CASE WHEN c.LotIdentityType = 'OFFICIAL' THEN c.LotIdentityID END AS ProductionLotID,
       CASE WHEN c.LotIdentityType = 'CANDIDATE' THEN c.LotIdentityID END AS CandidateWindowID,
       w.LotNumber,
       w.LotStatus,
       w.StartTime,
       w.EndTime,
       w.ProductionDate AS LotStartProductionDate,
       w.ShiftID AS LotStartShiftID,
       w.ProductID,
       w.ColorCode,
       c.OfficialMatchCount,
     c.OfficialBoundaryCount,
       c.CandidateMatchCount,
     c.CandidateBoundaryCount,
     CAST(CASE WHEN c.Diff > 0 AND c.LotIdentityType IS NOT NULL THEN 1 ELSE 0 END AS bit) AS IsAllocated,
       CASE WHEN c.Diff IS NULL THEN 'DIFF_EXCLUDED'
            WHEN c.OfficialMatchCount > 1 THEN 'AMBIGUOUS_OFFICIAL_OVERLAP'
            WHEN c.OfficialMatchCount = 1 AND c.CandidateMatchCount > 0 THEN 'ALLOCATED_OFFICIAL_PRECEDENCE'
            WHEN c.OfficialMatchCount = 1 THEN 'ALLOCATED_OFFICIAL'
            WHEN c.CandidateMatchCount > 1 THEN 'AMBIGUOUS_CANDIDATE_OVERLAP'
            WHEN c.CandidateMatchCount = 1 THEN 'ALLOCATED_CANDIDATE'
            ELSE 'UNALLOCATED_NO_WINDOW' END AS AllocationStatus,
       CASE WHEN c.Diff IS NULL THEN 0 ELSE c.Diff END AS EligibleDiff,
     CASE WHEN c.Diff > 0 AND c.LotIdentityType IS NOT NULL THEN c.Diff ELSE CONVERT(bigint,0) END AS AllocatedDiff,
     CASE WHEN c.Diff > 0 AND c.LotIdentityType IS NULL THEN c.Diff ELSE CONVERT(bigint,0) END AS UnallocatedOrAmbiguousDiff
FROM Chosen AS c
LEFT JOIN Windows AS w
  ON w.LotIdentityType = c.LotIdentityType
 AND w.LotIdentityID = c.LotIdentityID;
GO

CREATE VIEW omagmes.v_PressLotACC
AS
SELECT d.SourceID,
       d.RecTime,
       d.DiffProductionDate,
       d.QualityCode,
       d.PreviousSourceID,
       d.PreviousRecTime,
       d.CounterValue,
       d.PreviousCounterValue,
       d.ResetDetected,
       d.Unchanged,
       d.Diff,
       d.DiffStatus,
       d.LotIdentityType,
       d.LotIdentityID,
       d.ProductionLotID,
       d.CandidateWindowID,
       d.LotNumber,
       d.LotStatus,
       d.StartTime,
       d.EndTime,
       d.ProductID,
       d.ColorCode,
       d.AllocationStatus,
       d.IsAllocated,
       d.EligibleDiff,
       d.AllocatedDiff,
       d.UnallocatedOrAmbiguousDiff,
       CASE WHEN d.LotIdentityID IS NULL THEN CAST(NULL AS bigint)
            ELSE COALESCE(SUM(CASE WHEN d.IsAllocated = 1 THEN d.Diff ELSE CONVERT(bigint,0) END)
                 OVER (PARTITION BY d.LotIdentityType, d.LotIdentityID
                       ORDER BY d.RecTime, d.SourceID ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW), CONVERT(bigint,0))
       END AS LotACC
FROM omagmes.v_PressLotDiff AS d;
GO

CREATE VIEW omagmes.v_PressDiffReconciliation
AS
SELECT d.DiffProductionDate AS ProductionDate,
       SUM(CASE WHEN d.Diff > 0 THEN d.Diff ELSE CONVERT(bigint,0) END) AS TotalEligibleDailyDiff,
       SUM(d.AllocatedDiff) AS AllocatedDiff,
       SUM(d.UnallocatedOrAmbiguousDiff) AS UnallocatedOrAmbiguousDiff,
       SUM(CASE WHEN d.Diff IS NULL THEN CONVERT(bigint,1) ELSE CONVERT(bigint,0) END) AS ExcludedDiffEventCount,
       SUM(CASE WHEN d.AllocationStatus LIKE 'AMBIGUOUS%' AND d.Diff > 0 THEN CONVERT(bigint,1) ELSE CONVERT(bigint,0) END) AS AmbiguousAllocationCount,
       SUM(CASE WHEN d.AllocationStatus = 'UNALLOCATED_NO_WINDOW' AND d.Diff > 0 THEN CONVERT(bigint,1) ELSE CONVERT(bigint,0) END) AS UnallocatedEventCount,
         CONVERT(bigint,0) AS BoundaryOverlapEventCount,
       SUM(CASE WHEN d.ProductionDateUnresolved = 1 THEN CONVERT(bigint,1) ELSE CONVERT(bigint,0) END) AS ProductionDateUnresolvedCount
FROM omagmes.v_PressLotDiff AS d
GROUP BY d.DiffProductionDate;
GO

CREATE VIEW omagmes.v_PressLotSummary
AS
WITH Windows AS (
    SELECT CAST('OFFICIAL' AS varchar(10)) AS LotIdentityType,
           l.id AS LotIdentityID,
           l.id AS OfficialProductionLotID,
           CAST(NULL AS bigint) AS CandidateWindowID,
           l.LotNo AS LotNumber,
           CAST(CASE WHEN l.LotEndedAt IS NULL THEN 'OPEN' ELSE 'CLOSED' END AS varchar(20)) AS LotStatus,
           CONVERT(datetime2(7), l.LotStartedAt) AS StartTime,
           CONVERT(datetime2(7), l.LotEndedAt) AS EndTime,
           l.ProductionDate,
           l.ShiftID,
           l.ProductID,
           l.ColorCode,
           l.LotName,
           CONVERT(datetime2(7), NULL) AS OriginalProposedStartTime,
           CONVERT(datetime2(7), NULL) AS OriginalProposedEndTime,
           CONVERT(datetime2(7), NULL) AS CurrentProposedStartTime,
           CONVERT(datetime2(7), NULL) AS CurrentProposedEndTime,
           CONVERT(bit, 0) AS OperatorTimeOverride
    FROM omagmes.ProductionLot AS l
    UNION ALL
        SELECT CAST('CANDIDATE' AS varchar(10)), c.id, CAST(NULL AS bigint), c.id,
            CAST(NULL AS varchar(11)), c.CandidateStatus,
            c.EffectiveStartTime, c.EffectiveEndTime, c.ProductionDate, c.ShiftID,
            c.ProductID, c.ColorCode, CAST(NULL AS nvarchar(120)),
            c.InitialProposedStartTime, c.InitialProposedEndTime,
            c.CurrentProposedStartTime, c.CurrentProposedEndTime,
            c.OperatorTimeOverride
    FROM omagmes.AutoLotCandidateWindow AS c
    WHERE c.OfficialProductionLotID IS NULL
      AND c.CandidateStatus IN ('OPEN','CLOSED','REVIEWED')
), Accumulated AS (
    SELECT a.LotIdentityType, a.LotIdentityID,
           MAX(a.LotACC) AS LatestLotACC,
           SUM(a.AllocatedDiff) AS CalculatedPressQty,
           MAX(a.RecTime) AS LatestDiffAt,
           SUM(CASE WHEN a.AllocationStatus LIKE 'AMBIGUOUS%' THEN CONVERT(bigint,1) ELSE CONVERT(bigint,0) END) AS AmbiguousEventCount,
           CONVERT(bigint,0) AS BoundaryOverlapEventCount,
           SUM(CASE WHEN a.DiffStatus LIKE '%QUALITY%' OR a.DiffStatus LIKE '%INVALID%' THEN CONVERT(bigint,1) ELSE CONVERT(bigint,0) END) AS QualityWarningCount,
           SUM(CASE WHEN a.ResetDetected = 1 THEN CONVERT(bigint,1) ELSE CONVERT(bigint,0) END) AS ResetEventCount
    FROM omagmes.v_PressLotACC AS a
    WHERE a.LotIdentityID IS NOT NULL
    GROUP BY a.LotIdentityType, a.LotIdentityID
)
SELECT w.LotIdentityType,
       w.LotIdentityID,
       w.OfficialProductionLotID,
       w.CandidateWindowID,
       w.LotNumber,
       w.LotStatus,
       w.LotName,
       w.ProductID,
       w.ColorCode,
       w.StartTime,
       w.EndTime,
    w.OriginalProposedStartTime,
    w.OriginalProposedEndTime,
    w.CurrentProposedStartTime,
    w.CurrentProposedEndTime,
    w.OperatorTimeOverride,
       w.ProductionDate,
       w.ShiftID,
       COALESCE(a.CalculatedPressQty, CONVERT(bigint,0)) AS CalculatedPressQty,
       COALESCE(a.LatestLotACC, CONVERT(bigint,0)) AS LatestLotACC,
       a.LatestDiffAt,
       COALESCE(a.AmbiguousEventCount, CONVERT(bigint,0)) AS AmbiguousEventCount,
             COALESCE(a.BoundaryOverlapEventCount, CONVERT(bigint,0)) AS BoundaryOverlapEventCount,
       COALESCE(a.QualityWarningCount, CONVERT(bigint,0)) AS QualityWarningCount,
       COALESCE(a.ResetEventCount, CONVERT(bigint,0)) AS ResetEventCount,
    CAST(CASE WHEN a.AmbiguousEventCount > 0 OR a.BoundaryOverlapEventCount > 0 OR a.QualityWarningCount > 0 OR a.ResetEventCount > 0 THEN 1 ELSE 0 END AS bit) AS HasDataWarnings
FROM Windows AS w
LEFT JOIN Accumulated AS a
  ON a.LotIdentityType = w.LotIdentityType
 AND a.LotIdentityID = w.LotIdentityID;
GO

/* Optional least-privilege read grants only. Candidate mutations and quality-policy
    approval remain unavailable to the application until separately authorized. */
IF DATABASE_PRINCIPAL_ID(N'OMAG_MES') IS NOT NULL
BEGIN
    GRANT SELECT ON OBJECT::omagmes.v_PressDailyDiff TO [OMAG_MES];
    GRANT SELECT ON OBJECT::omagmes.v_PressLotDiff TO [OMAG_MES];
    GRANT SELECT ON OBJECT::omagmes.v_PressLotACC TO [OMAG_MES];
    GRANT SELECT ON OBJECT::omagmes.v_PressLotSummary TO [OMAG_MES];
    GRANT SELECT ON OBJECT::omagmes.v_PressDiffReconciliation TO [OMAG_MES];
END;
COMMIT TRANSACTION;
GO