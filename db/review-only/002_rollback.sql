/*
REVIEW-ONLY ROLLBACK DRAFT — DO NOT EXECUTE.
Refuses to remove any configuration history. Dropping populated append-only history is not an approved rollback.
*/
SET NOCOUNT ON;
IF DB_NAME() <> N'OMAG'
    THROW 51400, 'Rollback draft targets database OMAG only.', 1;
IF OBJECT_ID(N'omagmes.ProductionDayCutoffVersion', N'U') IS NULL
    THROW 51401, 'Configuration migration objects are not present.', 1;
IF EXISTS (SELECT 1 FROM omagmes.ProductionDayCutoffVersion)
   OR EXISTS (SELECT 1 FROM omagmes.Shift)
   OR EXISTS (SELECT 1 FROM omagmes.ShiftScheduleVersion)
   OR EXISTS (SELECT 1 FROM omagmes.ShiftScheduleShift)
    THROW 51402, 'Rollback refused: configuration history exists and must not be deleted.', 1;
THROW 51403, 'No automated rollback is approved. Obtain DBA and factory-owner review.', 1;
