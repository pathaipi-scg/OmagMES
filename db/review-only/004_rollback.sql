/*
REVIEW-ONLY rollback draft for migration 004. DBA executes only after approval.
This drops OmagMES objects and their candidate/audit data. Export/archive first.
It does not alter OMAG.dbo.PRESS or any migration 001-003 object.
*/
SET NOCOUNT ON;
SET XACT_ABORT ON;
IF DB_NAME() <> N'OMAG'
    THROW 53420, 'Migration 004 rollback only applies to OMAG.', 1;
IF SCHEMA_ID(N'omagmes') IS NULL
    THROW 53421, 'The omagmes schema is missing.', 1;
IF OBJECT_ID(N'omagmes.PressDiffQualityPolicy', N'U') IS NULL
   OR OBJECT_ID(N'omagmes.AutoLotCandidateWindow', N'U') IS NULL
   OR OBJECT_ID(N'omagmes.AutoLotCandidateWindowHistory', N'U') IS NULL
    THROW 53422, 'Migration 004 tables are incomplete; inspect manually and do not run rollback.', 1;
IF EXISTS (SELECT 1 FROM omagmes.PressDiffQualityPolicy)
   OR EXISTS (SELECT 1 FROM omagmes.AutoLotCandidateWindow)
   OR EXISTS (SELECT 1 FROM omagmes.AutoLotCandidateWindowHistory)
    THROW 53423, 'Rollback refused because policy/candidate/audit rows exist; export/archive and use a reviewed forward migration.', 1;

BEGIN TRANSACTION;
IF OBJECT_ID(N'omagmes.v_PressLotSummary', N'V') IS NOT NULL DROP VIEW omagmes.v_PressLotSummary;
IF OBJECT_ID(N'omagmes.v_PressDiffReconciliation', N'V') IS NOT NULL DROP VIEW omagmes.v_PressDiffReconciliation;
IF OBJECT_ID(N'omagmes.v_PressLotACC', N'V') IS NOT NULL DROP VIEW omagmes.v_PressLotACC;
IF OBJECT_ID(N'omagmes.v_PressLotDiff', N'V') IS NOT NULL DROP VIEW omagmes.v_PressLotDiff;
IF OBJECT_ID(N'omagmes.v_PressDailyDiff', N'V') IS NOT NULL DROP VIEW omagmes.v_PressDailyDiff;
IF OBJECT_ID(N'omagmes.AutoLotCandidateWindowHistory', N'U') IS NOT NULL DROP TABLE omagmes.AutoLotCandidateWindowHistory;
IF OBJECT_ID(N'omagmes.AutoLotCandidateWindow', N'U') IS NOT NULL DROP TABLE omagmes.AutoLotCandidateWindow;
IF OBJECT_ID(N'omagmes.PressDiffQualityPolicy', N'U') IS NOT NULL DROP TABLE omagmes.PressDiffQualityPolicy;
COMMIT TRANSACTION;
