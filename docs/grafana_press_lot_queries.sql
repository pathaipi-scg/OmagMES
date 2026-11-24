/*
OmagMES / Grafana SQL Server query examples for the shared SQL Views.
Use a SQL Server data source pointed at OMAG. Do not query dbo.PRESS directly in
Grafana; all panels use the same omagmes views as the API. Bind Grafana variables
as parameters where supported; the dashboard time filter applies to RecTime.
These are examples, not migrations or commands to execute as a write.
*/

-- Lot ACC timeline. Filter on the time-series field; ACC itself is SQL-derived.
SELECT a.RecTime AS [time],
       CONCAT(a.LotIdentityType, ':', a.LotIdentityID) AS series,
       a.LotACC AS value,
       a.AllocationStatus AS allocation_status,
       a.DiffStatus AS diff_status
FROM omagmes.v_PressLotACC AS a
WHERE $__timeFilter(a.RecTime)
  AND a.LotIdentityID IS NOT NULL
ORDER BY a.RecTime, a.SourceID;

-- Per-Lot live summary, including candidates and official Lots.
SELECT s.LotIdentityType, s.LotIdentityID, s.OfficialProductionLotID,
       s.CandidateWindowID, s.LotNumber, s.LotStatus, s.LotName,
       s.ProductID, s.ColorCode, s.StartTime, s.EndTime,
       s.CalculatedPressQty, s.LatestLotACC, s.LatestDiffAt,
       s.AmbiguousEventCount, s.QualityWarningCount, s.ResetEventCount,
       s.HasDataWarnings
FROM omagmes.v_PressLotSummary AS s
WHERE s.StartTime >= $__timeFrom() AND s.StartTime < $__timeTo()
ORDER BY s.StartTime, s.LotIdentityType, s.LotIdentityID;

-- Production Date reconciliation. Any non-zero unallocated/ambiguous values or
-- excluded events require investigation; do not hide them in a dashboard total.
SELECT r.ProductionDate, r.TotalEligibleDailyDiff, r.AllocatedDiff,
       r.UnallocatedOrAmbiguousDiff, r.ExcludedDiffEventCount,
       r.AmbiguousAllocationCount, r.UnallocatedEventCount,
      r.BoundaryOverlapEventCount,
       r.ProductionDateUnresolvedCount
FROM omagmes.v_PressDiffReconciliation AS r
WHERE r.ProductionDate >= CAST($__timeFrom() AS date)
  AND r.ProductionDate <= CAST($__timeTo() AS date)
ORDER BY r.ProductionDate;

-- Event-level audit panel for reset/quality/allocation warnings.
SELECT d.RecTime AS [time], d.SourceID, d.PreviousSourceID,
       d.CounterValue, d.PreviousCounterValue, d.QualityCode,
       d.Diff, d.DiffStatus, d.ResetDetected,
       d.LotIdentityType, d.LotIdentityID, d.AllocationStatus,
       d.UnallocatedOrAmbiguousDiff
FROM omagmes.v_PressLotDiff AS d
WHERE $__timeFilter(d.RecTime)
  AND (d.DiffStatus NOT IN ('POSITIVE_DELTA','UNCHANGED')
       OR d.AllocationStatus LIKE 'AMBIGUOUS%'
       OR d.AllocationStatus = 'UNALLOCATED_NO_WINDOW')
ORDER BY d.RecTime, d.SourceID;
