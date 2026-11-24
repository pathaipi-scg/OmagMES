/*
SUPERSEDED HISTORICAL ROLLBACK — DO NOT EXECUTE.
This rollback targets the retired 013 schema, not the clean development setup.
DBA REVIEW ONLY — MANUAL SSMS ROLLBACK CANDIDATE for Migration 013.
This rollback preserves AutoLot rows and refuses to discard source attribution,
B-suffix LotNo values, statuses, NULL sequences, or conflicting sequence scopes.
Never run as OMAG_MES. Inspect and plan forward recovery if any refusal condition fires.
*/
USE [OMAG];
GO
SET NOCOUNT ON;
SET XACT_ABORT ON;
IF DB_NAME()<>N'OMAG' OR IS_SRVROLEMEMBER(N'sysadmin')<>1
    THROW 54950, 'Rollback 013 requires OMAG and an authorized DBA/owner session.', 1;
IF OBJECT_ID(N'omagmes.AutoLot',N'U') IS NULL
    THROW 54951, 'AutoLot table is missing; stop and inspect.', 1;
IF COL_LENGTH(N'omagmes.AutoLot',N'SourceShiftType') IS NULL
   OR COL_LENGTH(N'omagmes.AutoLot',N'SourceRowNumber') IS NULL
   OR COL_LENGTH(N'omagmes.AutoLot',N'SourceShiftNo') IS NULL
   OR COL_LENGTH(N'omagmes.AutoLot',N'SourceStartTime') IS NULL
   OR COL_LENGTH(N'omagmes.AutoLot',N'SourceStopTime') IS NULL
    THROW 54952, 'Migration 013 column set is incomplete; stop and inspect manually.', 1;
IF EXISTS (
    SELECT 1 FROM omagmes.AutoLot
    WHERE SourceShiftType IS NOT NULL OR SourceRowNumber IS NOT NULL OR SourceShiftNo IS NOT NULL
       OR SourceStartTime IS NOT NULL OR SourceStopTime IS NOT NULL
       OR LotSequence IS NULL OR RIGHT(LotNo,1)='B'
       OR ReconciliationStatus IN ('SOURCE_NUMBER_REVIEW','SOURCE_SHIFT_REVIEW','SOURCE_DATE_REVIEW')
)
    THROW 54953, 'Rollback refused: source-view attribution or B-suffix AutoLot data exists; retain it and recover forward.', 1;
IF EXISTS (
    SELECT ProductionDate,ShiftNumber,LotSequence FROM omagmes.AutoLot
    GROUP BY ProductionDate,ShiftNumber,LotSequence HAVING COUNT_BIG(*)>1
)
    THROW 54954, 'Rollback refused: restoring the former date/shift/sequence key would conflict.', 1;
IF EXISTS (SELECT 1 FROM sys.foreign_keys WHERE referenced_object_id=OBJECT_ID(N'omagmes.AutoLot') AND parent_object_id<>OBJECT_ID(N'omagmes.AutoLotAssignment'))
    THROW 54955, 'Rollback refused: external foreign keys reference AutoLot.', 1;
GO

BEGIN TRY
    BEGIN TRANSACTION;
    ALTER TABLE omagmes.AutoLot DROP CONSTRAINT CK_AutoLot_LotNumber;
    ALTER TABLE omagmes.AutoLot DROP CONSTRAINT CK_AutoLot_ReconciliationStatus;
    ALTER TABLE omagmes.AutoLot DROP COLUMN SourceShiftType,SourceRowNumber,SourceShiftNo,SourceStartTime,SourceStopTime;
    ALTER TABLE omagmes.AutoLot ALTER COLUMN LotSequence tinyint NOT NULL;
    ALTER TABLE omagmes.AutoLot WITH CHECK ADD CONSTRAINT UQ_AutoLot_DateShiftSequence
        UNIQUE (ProductionDate,ShiftNumber,LotSequence);
    ALTER TABLE omagmes.AutoLot WITH CHECK ADD CONSTRAINT CK_AutoLot_LotNumber
        CHECK (
            LotNo LIKE 'B[0-9][0-9][0-9][0-9][0-9][0-9][1-3][0-9][0-9]A'
            AND LotSequence BETWEEN 1 AND 99
            AND CONVERT(int,SUBSTRING(LotNo,8,1))=ShiftNumber
            AND CONVERT(int,SUBSTRING(LotNo,9,2))=LotSequence
            AND ShiftNumber IN (1,2,3)
        );
    ALTER TABLE omagmes.AutoLot WITH CHECK ADD CONSTRAINT CK_AutoLot_ReconciliationStatus
        CHECK (ReconciliationStatus IN ('CURRENT','SOURCE_MISSING','SCHEDULE_REVIEW','POSSIBLE_SOURCE_CORRECTION'));
    COMMIT TRANSACTION;
END TRY
BEGIN CATCH
    IF XACT_STATE()<>0 ROLLBACK TRANSACTION;
    THROW;
END CATCH;
GO
