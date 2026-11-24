/*
SUPERSEDED HISTORICAL ROLLBACK — DO NOT EXECUTE.
This rollback targets the retired 012 schema, not the clean development setup.
DBA REVIEW ONLY — MANUAL SSMS ROLLBACK CANDIDATE for Migration 012.
Refuses to remove any AutoLot/PlanIdentity row or any object with external FKs.
Never run as the OMAG_MES runtime. Do not remove historical production data.
*/
USE [OMAG];
GO
SET NOCOUNT ON;
SET XACT_ABORT ON;
IF DB_NAME()<>N'OMAG' OR IS_SRVROLEMEMBER(N'sysadmin')<>1
    THROW 54850, 'Rollback 012 requires OMAG and an authorized DBA/owner session.', 1;
IF OBJECT_ID(N'omagmes.AutoLot',N'U') IS NULL
   OR OBJECT_ID(N'omagmes.AutoLotAssignment',N'U') IS NULL
   OR OBJECT_ID(N'omagmes.PlanIdentity',N'U') IS NULL
    THROW 54851, 'Migration 012 object set is incomplete; inspect manually and stop.', 1;
IF EXISTS (SELECT 1 FROM omagmes.AutoLot)
   OR EXISTS (SELECT 1 FROM omagmes.AutoLotAssignment)
   OR EXISTS (SELECT 1 FROM omagmes.PlanIdentity)
    THROW 54852, 'Rollback refused: AutoLot or PlanIdentity data exists and must be retained.', 1;
IF EXISTS (
    SELECT 1 FROM sys.foreign_keys
    WHERE referenced_object_id IN (OBJECT_ID(N'omagmes.AutoLot'),OBJECT_ID(N'omagmes.AutoLotAssignment'),OBJECT_ID(N'omagmes.PlanIdentity'))
      AND parent_object_id NOT IN (OBJECT_ID(N'omagmes.AutoLotAssignment'))
)
    THROW 54853, 'Rollback refused: external objects reference Migration 012 tables.', 1;
BEGIN TRY
    BEGIN TRANSACTION;
    DROP TABLE omagmes.AutoLotAssignment;
    DROP TABLE omagmes.AutoLot;
    DROP TABLE omagmes.PlanIdentity;
    IF EXISTS (SELECT 1 FROM sys.indexes WHERE object_id=OBJECT_ID(N'omagmes.Mould') AND name=N'UX_Mould_ID_ProductID_AutoLot')
        DROP INDEX UX_Mould_ID_ProductID_AutoLot ON omagmes.Mould;
    COMMIT TRANSACTION;
END TRY
BEGIN CATCH
    IF XACT_STATE()<>0 ROLLBACK TRANSACTION;
    THROW;
END CATCH;
GO
