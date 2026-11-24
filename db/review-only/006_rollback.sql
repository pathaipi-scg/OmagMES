:ON ERROR EXIT
/*
REVIEW-ONLY rollback for Migration 006. DBA-only; do not run automatically.
It refuses if any AUTO candidate, plan assignment, new action, or non-legacy
audit snapshot exists. It never deletes master/history rows or touches PRESS.
*/
SET NOCOUNT ON;
SET XACT_ABORT ON;
USE OMAG;
GO
IF DB_NAME() <> N'OMAG'
    THROW 53630, 'Migration 006 rollback only applies to OMAG.', 1;
IF OBJECT_ID(N'omagmes.AutoLotCandidateWindow',N'U') IS NULL
   OR OBJECT_ID(N'omagmes.AutoLotCandidateWindowHistory',N'U') IS NULL
   OR OBJECT_ID(N'omagmes.v_AutoLotDetectedWindow',N'V') IS NULL
   OR COL_LENGTH(N'omagmes.AutoLotCandidateWindow',N'PlanSourceKey') IS NULL
    OR COL_LENGTH(N'omagmes.AutoLotCandidateWindow',N'OperatorBoundaryConfirmed') IS NULL
   OR COL_LENGTH(N'omagmes.AutoLotCandidateWindowHistory',N'PreviousStateJson') IS NULL
    THROW 53631, 'Migration 006 is absent or partial; inspect manually.', 1;
IF EXISTS (
    SELECT 1 FROM omagmes.AutoLotCandidateWindow
    WHERE CandidateKind='AUTO' OR PlanSourceKey IS NOT NULL OR PlanSnapshotJson IS NOT NULL
       OR PlanMaterialCode IS NOT NULL OR PlanMatchStatus IS NOT NULL
         OR PlanSelectedAt IS NOT NULL OR PlanSelectedBy IS NOT NULL OR OperatorBoundaryConfirmed=1
)
    THROW 53632, 'Rollback refused: AUTO candidate or Production Plan snapshot data exists.', 1;
IF EXISTS (
    SELECT 1 FROM omagmes.AutoLotCandidateWindowHistory
    WHERE ChangeSource<>'LEGACY' OR PreviousStateJson IS NOT NULL OR NewStateJson IS NOT NULL
       OR ActionCode IN ('CREATE_AUTO','CREATE_MANUAL','UPDATE_START','UPDATE_STOP','MOVE',
                         'PLAN_ASSIGN','PLAN_CHANGE','SOFT_DELETE','RESTORE','CLASSIFY')
)
    THROW 53633, 'Rollback refused: Migration 006 history has been recorded.', 1;
IF EXISTS (
    SELECT 1 FROM sys.sql_expression_dependencies
    WHERE referenced_id=OBJECT_ID(N'omagmes.v_AutoLotDetectedWindow',N'V')
      AND referencing_id<>OBJECT_ID(N'omagmes.v_AutoLotDetectedWindow',N'V')
)
    THROW 53634, 'Rollback refused: another object depends on v_AutoLotDetectedWindow.', 1;
GO

BEGIN TRANSACTION;
GO
DROP VIEW omagmes.v_AutoLotDetectedWindow;
DROP INDEX IX_AutoLotCandidateWindow_PlanSourceKey ON omagmes.AutoLotCandidateWindow;
ALTER TABLE omagmes.AutoLotCandidateWindowHistory
    DROP CONSTRAINT CK_AutoLotCandidateWindowHistory_Action;
ALTER TABLE omagmes.AutoLotCandidateWindowHistory
    ADD CONSTRAINT CK_AutoLotCandidateWindowHistory_Action
    CHECK (ActionCode IN ('CREATED','EDITED','SPLIT','MERGED','DISMISSED','OFFICIAL_LINK'));
ALTER TABLE omagmes.AutoLotCandidateWindowHistory
    DROP CONSTRAINT DF_AutoLotCandidateWindowHistory_ChangeSource;
ALTER TABLE omagmes.AutoLotCandidateWindowHistory
    DROP COLUMN ChangeSource,PreviousStateJson,NewStateJson;
ALTER TABLE omagmes.AutoLotCandidateWindow
    DROP CONSTRAINT CK_AutoLotCandidateWindow_Kind;
ALTER TABLE omagmes.AutoLotCandidateWindow
    ADD CONSTRAINT CK_AutoLotCandidateWindow_Kind
    CHECK (CandidateKind IN ('RESET','MANUAL','SPLIT'));
ALTER TABLE omagmes.AutoLotCandidateWindow
    DROP CONSTRAINT DF_AutoLotCandidateWindow_BoundaryConfirmed;
ALTER TABLE omagmes.AutoLotCandidateWindow
    DROP COLUMN PlanSourceKey,PlanSnapshotJson,PlanMaterialCode,PlanMatchStatus,PlanSelectedAt,PlanSelectedBy,
                OperatorBoundaryConfirmed;
GO
COMMIT TRANSACTION;
GO