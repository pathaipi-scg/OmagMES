/*
DBA REVIEW ONLY — DO NOT EXECUTE WITHOUT SEPARATE DBA/OWNER AUTHORIZATION.
Rollback for 011_daily_shift_configuration.sql. It removes only the two new tables
when they contain no saves or periods and have no external FK dependants. Existing
schedule/type/assignment objects, official Lots and historical references are untouched.
*/
SET NOCOUNT ON;
SET XACT_ABORT ON;

IF DB_NAME()<>N'OMAG' THROW 54620, 'Rollback 011 requires database OMAG.', 1;
IF OBJECT_ID(N'omagmes.DailyShiftConfigurationSave',N'U') IS NULL
   AND OBJECT_ID(N'omagmes.DailyShiftConfigurationPeriod',N'U') IS NULL
    RETURN;
IF OBJECT_ID(N'omagmes.DailyShiftConfigurationSave',N'U') IS NULL
   OR OBJECT_ID(N'omagmes.DailyShiftConfigurationPeriod',N'U') IS NULL
    THROW 54621, 'Rollback refused: only one of the paired configuration tables exists.', 1;
IF EXISTS (SELECT 1 FROM omagmes.DailyShiftConfigurationSave)
   OR EXISTS (SELECT 1 FROM omagmes.DailyShiftConfigurationPeriod)
    THROW 54622, 'Rollback refused: Shift configuration saves exist; preserve them and use a forward migration.', 1;
IF EXISTS (
    SELECT 1 FROM sys.foreign_keys
    WHERE referenced_object_id IN (
        OBJECT_ID(N'omagmes.DailyShiftConfigurationSave'),
        OBJECT_ID(N'omagmes.DailyShiftConfigurationPeriod')
    ) AND parent_object_id NOT IN (
        OBJECT_ID(N'omagmes.DailyShiftConfigurationSave'),
        OBJECT_ID(N'omagmes.DailyShiftConfigurationPeriod')
    )
)
    THROW 54623, 'Rollback refused: another database object references the new Shift configuration tables.', 1;

BEGIN TRY
    BEGIN TRANSACTION;
    DROP TABLE omagmes.DailyShiftConfigurationPeriod;
    DROP TABLE omagmes.DailyShiftConfigurationSave;
    COMMIT TRANSACTION;
END TRY
BEGIN CATCH
    IF XACT_STATE()<>0 ROLLBACK TRANSACTION;
    THROW;
END CATCH;
