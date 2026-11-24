/*
OPTIONAL, REVIEW-ONLY Auto Lot candidate and operator-window grants.
Do not execute as part of schema deployment. Run only after timestamp basis,
owner authorization, and the OMAG_MES candidate-write identity are approved.
Official Lot SAVE and quality-policy writes are deliberately not included.
*/
SET NOCOUNT ON;
IF DB_NAME() <> N'OMAG'
    THROW 53440, 'Optional Migration 004 candidate grants only apply to OMAG.', 1;
IF DATABASE_PRINCIPAL_ID(N'OMAG_MES') IS NULL
    THROW 53441, 'OMAG_MES principal is missing; candidate grants were not applied.', 1;
IF OBJECT_ID(N'omagmes.AutoLotCandidateWindow', N'U') IS NULL
   OR OBJECT_ID(N'omagmes.AutoLotCandidateWindowHistory', N'U') IS NULL
    THROW 53442, 'Migration 004 candidate tables must exist before optional grants.', 1;
/* Current API uses one separately gated principal for candidate sync and operator
   edits: SELECT/INSERT/UPDATE candidate window; SELECT/INSERT append-only history.
   No DELETE, quality-policy DML, Official Lot DML, or schema-wide permissions. */
GRANT SELECT, INSERT, UPDATE ON OBJECT::omagmes.AutoLotCandidateWindow TO [OMAG_MES];
GRANT SELECT, INSERT ON OBJECT::omagmes.AutoLotCandidateWindowHistory TO [OMAG_MES];
GO
