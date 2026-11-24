/*
Targeted, non-destructive patch for existing OMAG.omagmes.v_PressDailyDiff.
Run in SSMS against database OMAG using an authorized DDL account.
This changes exactly one view definition. It does not create/drop tables, alter
other views, change candidate/quality-policy data, or modify dbo.PRESS.
_QUALITY remains visible but is informational only. The existing
IsQualityEligible output is retained as a compatibility alias for a valid
numeric current/predecessor pair; it does not inspect _QUALITY.
*/
SET NOCOUNT ON;
USE OMAG;
GO
IF DB_NAME() <> N'OMAG'
    THROW 53500, 'Patch 005 only applies to database OMAG.', 1;
IF OBJECT_ID(N'omagmes.v_PressDailyDiff', N'V') IS NULL
    THROW 53501, 'Expected installed view omagmes.v_PressDailyDiff is missing; stop and inspect the database.', 1;
GO

SET ANSI_NULLS ON;
GO
SET QUOTED_IDENTIFIER ON;
GO
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
                     AND TRY_CONVERT(decimal(20,6), NULLIF(LTRIM(RTRIM(p._VALUE)), '')) =
                         TRY_CONVERT(decimal(20,0), NULLIF(LTRIM(RTRIM(p._VALUE)), ''))
                     AND TRY_CONVERT(decimal(20,0), NULLIF(LTRIM(RTRIM(p._VALUE)), '')) BETWEEN 0 AND 9223372036854775807
                THEN 1 ELSE 0 END AS CurrentValueValid
    FROM OMAG.dbo.PRESS AS p
    WHERE p._NAME COLLATE Latin1_General_100_BIN2 =
          'OMAG.PRESS.OEE.DropCnt' COLLATE Latin1_General_100_BIN2
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
           CASE WHEN o.RecTime >= DATEADD(SECOND,
                    DATEDIFF(SECOND, CONVERT(time(0),'00:00'), currentCutoff.CutoffTime),
                    CONVERT(datetime2(7), CONVERT(date, o.RecTime)))
                THEN CONVERT(date, o.RecTime)
                WHEN priorCutoff.CutoffTime IS NOT NULL
                THEN DATEADD(DAY, -1, CONVERT(date, o.RecTime))
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
                      AND c.CounterValue < c.PreviousCounterValue
                 THEN 1 ELSE 0 END AS bit) AS ResetDetected,
       CAST(CASE WHEN c.CurrentValueValid = 1 AND c.PreviousValueValid = 1
                      AND c.CounterValue = c.PreviousCounterValue
                 THEN 1 ELSE 0 END AS bit) AS Unchanged,
       CAST(CASE WHEN c.CurrentValueValid = 1 AND c.PreviousValueValid = 1
                 THEN 1 ELSE 0 END AS bit) AS IsQualityEligible,
       CASE WHEN c.DiffStatus = 'POSITIVE_DELTA'
            THEN CONVERT(bigint, c.CounterValue - c.PreviousCounterValue)
            WHEN c.DiffStatus IN ('UNCHANGED','RESET_BASELINE_NOT_CREDITED')
            THEN CONVERT(bigint, 0)
            ELSE CONVERT(bigint, NULL) END AS Diff,
       c.DiffStatus,
       c.ProductionDate,
       CAST(CASE WHEN c.ProductionDate IS NULL THEN 1 ELSE 0 END AS bit) AS ProductionDateUnresolved
FROM Classified AS c;
GO

/* Read-only deployment verification; compare row counts before/after. */
SELECT DiffStatus, QualityCode, COUNT_BIG(*) AS SampleCount,
       COUNT_BIG(Diff) AS NonNullDiffCount,
       SUM(CASE WHEN Diff > 0 THEN Diff ELSE CONVERT(bigint,0) END) AS PositiveDiffTotal
FROM omagmes.v_PressDailyDiff
GROUP BY DiffStatus, QualityCode
ORDER BY DiffStatus, QualityCode;