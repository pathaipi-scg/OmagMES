:ON ERROR EXIT
/*
REVIEW-ONLY / DBA-EXECUTION REQUIRED — Migration 006.
Target: existing OMAG.omagmes schema only. Requires installed Migration 004
and quality-independent v_PressDailyDiff (Patch 005).

Reuses AutoLotCandidateWindow as the sole AUTO/MANUAL candidate master and
AutoLotCandidateWindowHistory as its append-only history. Adds plan snapshots
without an FK to the external plan source because dbo.vw_OmagPlan exposes no
source row ID. The source snapshot key is a content fingerprint, not a claimed
immutable external plan identity. No separate master table is created.

The new view derives counter epochs only. Its timestamps are proposals, not
verified Lot boundaries. Counter resets, AutoRun transitions, Product or Color
are never inferred by this view. Product/Color confirmation remains an operator
decision. Daily Diff, allocation, PressQty and ACC remain owned by existing SQL
views. Does not modify dbo.PRESS, dbo.vw_OmagPlan, official ProductionLots, or
candidate/history rows. Run in SSMS SQLCMD mode on one connection after the
read-only 006 preflight and approved backup/change control.
*/
SET NOCOUNT ON;
SET XACT_ABORT ON;
USE OMAG;
GO
IF DB_NAME() <> N'OMAG'
    THROW 53600, 'Migration 006 only applies to database OMAG.', 1;
IF OBJECT_ID(N'omagmes.AutoLotCandidateWindow', N'U') IS NULL
   OR OBJECT_ID(N'omagmes.AutoLotCandidateWindowHistory', N'U') IS NULL
   OR OBJECT_ID(N'omagmes.v_PressDailyDiff', N'V') IS NULL
   OR OBJECT_ID(N'omagmes.v_PressLotDiff', N'V') IS NULL
   OR OBJECT_ID(N'omagmes.v_PressLotACC', N'V') IS NULL
    THROW 53601, 'Required installed Migration 004 objects are missing; stop.', 1;
IF OBJECT_ID(N'omagmes.v_AutoLotDetectedWindow') IS NOT NULL
   OR COL_LENGTH(N'omagmes.AutoLotCandidateWindow', N'PlanSourceKey') IS NOT NULL
    OR COL_LENGTH(N'omagmes.AutoLotCandidateWindow', N'OperatorBoundaryConfirmed') IS NOT NULL
   OR COL_LENGTH(N'omagmes.AutoLotCandidateWindowHistory', N'PreviousStateJson') IS NOT NULL
    THROW 53602, 'Migration 006 objects/columns already exist; inspect before proceeding.', 1;
IF EXISTS (
    SELECT 1 FROM sys.sql_expression_dependencies
    WHERE referencing_id = OBJECT_ID(N'omagmes.v_PressDailyDiff', N'V')
      AND referenced_id = OBJECT_ID(N'omagmes.PressDiffQualityPolicy', N'U')
)
    THROW 53603, 'Patch 005 is not installed: Daily Diff still depends on the legacy quality policy.', 1;
GO

BEGIN TRANSACTION;
GO
ALTER TABLE omagmes.AutoLotCandidateWindow
    ADD PlanSourceKey char(64) COLLATE Latin1_General_100_BIN2 NULL,
        PlanSnapshotJson nvarchar(max) NULL,
        PlanMaterialCode nvarchar(100) COLLATE Latin1_General_100_BIN2 NULL,
        PlanMatchStatus varchar(20) NULL,
        PlanSelectedAt datetime2(7) NULL,
        PlanSelectedBy nvarchar(200) NULL;
ALTER TABLE omagmes.AutoLotCandidateWindow
    ADD OperatorBoundaryConfirmed bit NOT NULL
        CONSTRAINT DF_AutoLotCandidateWindow_BoundaryConfirmed DEFAULT (0) WITH VALUES;

ALTER TABLE omagmes.AutoLotCandidateWindow
    DROP CONSTRAINT CK_AutoLotCandidateWindow_Kind;
ALTER TABLE omagmes.AutoLotCandidateWindow
    ADD CONSTRAINT CK_AutoLotCandidateWindow_Kind
    CHECK (CandidateKind IN ('RESET','AUTO','MANUAL','SPLIT'));

ALTER TABLE omagmes.AutoLotCandidateWindowHistory
    ADD ChangeSource varchar(20) NOT NULL
        CONSTRAINT DF_AutoLotCandidateWindowHistory_ChangeSource DEFAULT ('LEGACY') WITH VALUES;
ALTER TABLE omagmes.AutoLotCandidateWindowHistory
    ADD PreviousStateJson nvarchar(max) NULL,
        NewStateJson nvarchar(max) NULL;

ALTER TABLE omagmes.AutoLotCandidateWindowHistory
    DROP CONSTRAINT CK_AutoLotCandidateWindowHistory_Action;
ALTER TABLE omagmes.AutoLotCandidateWindowHistory
    ADD CONSTRAINT CK_AutoLotCandidateWindowHistory_Action
    CHECK (ActionCode IN (
        'CREATED','EDITED','SPLIT','MERGED','DISMISSED','OFFICIAL_LINK',
        'CREATE_AUTO','CREATE_MANUAL','UPDATE_START','UPDATE_STOP','MOVE',
        'PLAN_ASSIGN','PLAN_CHANGE','SOFT_DELETE','RESTORE','CLASSIFY'
    ));

CREATE INDEX IX_AutoLotCandidateWindow_PlanSourceKey
    ON omagmes.AutoLotCandidateWindow(PlanSourceKey)
    WHERE PlanSourceKey IS NOT NULL;
GO

CREATE OR ALTER VIEW omagmes.v_AutoLotDetectedWindow
AS
WITH Ordered AS (
    SELECT d.SourceID, d.RecTime, d.SourceTag, d.PreviousSourceID,
           d.PreviousRecTime, d.PreviousCounterValue, d.CounterValue,
           d.ResetDetected, d.ProductionDate,
           SUM(CONVERT(bigint, CASE WHEN d.ResetDetected = 1 THEN 1 ELSE 0 END))
               OVER (ORDER BY d.RecTime, d.SourceID ROWS UNBOUNDED PRECEDING) AS CounterEpoch
    FROM omagmes.v_PressDailyDiff AS d
    WHERE d.PreviousSourceID IS NOT NULL OR d.DiffStatus = 'FIRST_SAMPLE'
), Sequenced AS (
    SELECT o.*,
           ROW_NUMBER() OVER (PARTITION BY o.CounterEpoch ORDER BY o.RecTime, o.SourceID) AS EpochOrdinal
    FROM Ordered AS o
), EpochStarts AS (
    SELECT CounterEpoch, SourceID AS FirstSourceID,
           RecTime AS ProposedStartTime, ProductionDate,
           CASE WHEN ResetDetected = 1 THEN 'COUNTER_DECREASE'
                ELSE 'FIRST_OBSERVED_BASELINE' END AS BoundaryEvidence,
           PreviousSourceID AS ResetPreviousSourceID,
         CounterValue AS ResetValue,
         PreviousCounterValue AS ResetPreviousValue,
           PreviousRecTime AS BoundaryEarliestEvidenceAt,
           RecTime AS BoundaryLatestEvidenceAt
    FROM Sequenced
    WHERE EpochOrdinal = 1
), Bounds AS (
    SELECT e.*,
           LEAD(e.FirstSourceID) OVER (ORDER BY e.CounterEpoch) AS NextEpochFirstSourceID,
           LEAD(e.ProposedStartTime) OVER (ORDER BY e.CounterEpoch) AS ProposedEndTime
    FROM EpochStarts AS e
)
SELECT CONVERT(nvarchar(200), N'autolot:dropcnt-reset:' + CONVERT(nvarchar(30), b.FirstSourceID)) AS CandidateKey,
       N'OMAG.PRESS.OEE.DropCnt' AS SourceTag,
       b.CounterEpoch,
       b.FirstSourceID,
       CASE WHEN b.BoundaryEvidence = 'COUNTER_DECREASE' THEN b.FirstSourceID END AS ResetSourceID,
       b.ResetPreviousSourceID,
    CASE WHEN b.BoundaryEvidence = 'COUNTER_DECREASE' THEN b.ResetValue END AS ResetValue,
    CASE WHEN b.BoundaryEvidence = 'COUNTER_DECREASE' THEN b.ResetPreviousValue END AS ResetPreviousValue,
       b.ProposedStartTime,
       b.ProposedEndTime,
       b.BoundaryEvidence,
       b.BoundaryEarliestEvidenceAt,
       b.BoundaryLatestEvidenceAt,
       b.ProductionDate,
       cutoff.id AS CutoffVersionID,
       schedule.id AS ShiftScheduleVersionID,
       CAST(NULL AS bigint) AS ShiftID,
       CAST(1 AS bit) AS RequiresOperatorConfirmation,
       CAST(1 AS bit) AS IsProvisional,
       N'Counter epoch only; not evidence of a Product/Color change or actual Lot start/stop.' AS DetectionNote
FROM Bounds AS b
OUTER APPLY (
    SELECT TOP (1) c.id
    FROM omagmes.ProductionDayCutoffVersion AS c
    WHERE c.EffectiveFromProductionDate <= b.ProductionDate
    ORDER BY c.EffectiveFromProductionDate DESC, c.id DESC
) AS cutoff
OUTER APPLY (
    SELECT TOP (1) s.id
    FROM omagmes.ShiftScheduleVersion AS s
    WHERE s.EffectiveFromProductionDate <= b.ProductionDate
    ORDER BY s.EffectiveFromProductionDate DESC, s.id DESC
) AS schedule
WHERE b.BoundaryEvidence = 'COUNTER_DECREASE';
GO
COMMIT TRANSACTION;
GO

/* Read-only deployment summary. This is not a runtime acceptance test. */
SELECT CandidateKind, CandidateStatus, COUNT_BIG(*) AS CandidateCount
FROM omagmes.AutoLotCandidateWindow
GROUP BY CandidateKind, CandidateStatus;
SELECT TOP (20) CandidateKey, FirstSourceID, ResetSourceID,
       ProposedStartTime, ProposedEndTime, BoundaryEvidence,
       BoundaryEarliestEvidenceAt, BoundaryLatestEvidenceAt,
       RequiresOperatorConfirmation, IsProvisional
FROM omagmes.v_AutoLotDetectedWindow
ORDER BY ProposedStartTime DESC, FirstSourceID DESC;