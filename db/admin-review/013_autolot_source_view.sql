/*
SUPERSEDED HISTORICAL DRAFT — DO NOT EXECUTE.
Use db/admin-review/autolot_clean_development_setup.sql as the sole clean setup artifact.
DBA REVIEW ONLY — FOLLOW-UP MIGRATION 013 FOR 012. MANUAL SSMS DEPLOYMENT CANDIDATE.
Never run as OMAG_MES. No migration has been executed by the application agent.
This preserves AutoLot.id and every existing AutoLot row. LotNo is a business value
copied verbatim from dbo.vw_PRESS_LotAuto; A and B suffixes are retained because
012 may already have stored A-suffix records while the reviewed view currently
returns B-suffix values. LotSequence becomes nullable/legacy only and is never
allocated by the new workflow. The LotNo unique constraint remains authoritative.
*/
USE [OMAG];
GO
SET NOCOUNT ON;
SET XACT_ABORT ON;

IF DB_NAME()<>N'OMAG' OR IS_SRVROLEMEMBER(N'sysadmin')<>1
    THROW 54900, 'Migration 013 requires OMAG and an authorized DBA/owner session.', 1;
IF SCHEMA_ID(N'omagmes') IS NULL OR DATABASE_PRINCIPAL_ID(N'OMAG_MES') IS NULL
    THROW 54901, 'Required schema or OMAG_MES principal is missing.', 1;
IF OBJECT_ID(N'omagmes.AutoLot',N'U') IS NULL
   OR OBJECT_ID(N'omagmes.AutoLotAssignment',N'U') IS NULL
   OR OBJECT_ID(N'omagmes.PlanIdentity',N'U') IS NULL
   OR OBJECT_ID(N'dbo.vw_PRESS_LotAuto',N'V') IS NULL
    THROW 54902, 'Migration 012 or dbo.vw_PRESS_LotAuto is missing; stop and inspect.', 1;
IF COL_LENGTH(N'dbo.vw_PRESS_LotAuto',N'ProdDate') IS NULL
   OR COL_LENGTH(N'dbo.vw_PRESS_LotAuto',N'ShiftType') IS NULL
   OR COL_LENGTH(N'dbo.vw_PRESS_LotAuto',N'LotNo') IS NULL
   OR COL_LENGTH(N'dbo.vw_PRESS_LotAuto',N'rw') IS NULL
   OR COL_LENGTH(N'dbo.vw_PRESS_LotAuto',N'LotStart') IS NULL
   OR COL_LENGTH(N'dbo.vw_PRESS_LotAuto',N'LotStop') IS NULL
   OR COL_LENGTH(N'dbo.vw_PRESS_LotAuto',N'ShiftNo') IS NULL
   OR COL_LENGTH(N'dbo.vw_PRESS_LotAuto',N'StartTime') IS NULL
   OR COL_LENGTH(N'dbo.vw_PRESS_LotAuto',N'StopTime') IS NULL
   OR COL_LENGTH(N'dbo.vw_PRESS_LotAuto',N'pDropCnt') IS NULL
   OR COL_LENGTH(N'dbo.vw_PRESS_LotAuto',N'DropCnt') IS NULL
    THROW 54903, 'The AutoLot view columns differ from the inspected source contract.', 1;
IF EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id=OBJECT_ID(N'omagmes.AutoLot')
      AND name IN (N'SourceShiftType',N'SourceRowNumber',N'SourceShiftNo',N'SourceStartTime',N'SourceStopTime')
)
    THROW 54904, 'One or more Migration 013 columns already exist; inspect partial deployment.', 1;
IF NOT EXISTS (SELECT 1 FROM sys.check_constraints WHERE parent_object_id=OBJECT_ID(N'omagmes.AutoLot') AND name=N'CK_AutoLot_LotNumber')
   OR NOT EXISTS (SELECT 1 FROM sys.key_constraints WHERE parent_object_id=OBJECT_ID(N'omagmes.AutoLot') AND name=N'UQ_AutoLot_DateShiftSequence')
   OR NOT EXISTS (SELECT 1 FROM sys.check_constraints WHERE parent_object_id=OBJECT_ID(N'omagmes.AutoLot') AND name=N'CK_AutoLot_ReconciliationStatus')
    THROW 54905, 'Migration 012 constraints differ from the reviewed baseline; stop and inspect.', 1;
IF EXISTS (
    SELECT LotNo FROM dbo.vw_PRESS_LotAuto
    WHERE LotNo IS NOT NULL GROUP BY LotNo HAVING COUNT_BIG(*)>1
)
    THROW 54906, 'dbo.vw_PRESS_LotAuto currently contains duplicate LotNo values; no persistent reconciliation is safe.', 1;
IF EXISTS (
    SELECT 1 FROM dbo.vw_PRESS_LotAuto
    WHERE LotStart IS NOT NULL AND LotNo IS NULL
)
    THROW 54907, 'A view row has LotStart but no LotNo; inspect source data before deployment.', 1;

BEGIN TRY
    BEGIN TRANSACTION;

    /* Existing values remain untouched. This removes only the application-side
       sequence rule; SQL-generated LotNo itself remains unique and immutable per AutoLot. */
    ALTER TABLE omagmes.AutoLot DROP CONSTRAINT UQ_AutoLot_DateShiftSequence;
    ALTER TABLE omagmes.AutoLot DROP CONSTRAINT CK_AutoLot_LotNumber;
    ALTER TABLE omagmes.AutoLot DROP CONSTRAINT CK_AutoLot_ReconciliationStatus;
    ALTER TABLE omagmes.AutoLot ALTER COLUMN LotSequence tinyint NULL;

    ALTER TABLE omagmes.AutoLot ADD
        SourceShiftType int NULL,
        SourceRowNumber bigint NULL,
        SourceShiftNo nchar(2) NULL,
        SourceStartTime time(7) NULL,
        SourceStopTime time(7) NULL;

    ALTER TABLE omagmes.AutoLot WITH CHECK ADD CONSTRAINT CK_AutoLot_LotNumber
        CHECK (
            DATALENGTH(LotNo)=11
            AND LotNo LIKE 'B[0-9][0-9][0-9][0-9][0-9][0-9][1-3][0-9][0-9][AB]'
            AND ShiftNumber IN (1,2,3)
            AND CONVERT(int,SUBSTRING(LotNo,8,1))=ShiftNumber
        );
    ALTER TABLE omagmes.AutoLot WITH CHECK ADD CONSTRAINT CK_AutoLot_ReconciliationStatus
        CHECK (ReconciliationStatus IN (
            'CURRENT','SOURCE_MISSING','SCHEDULE_REVIEW','POSSIBLE_SOURCE_CORRECTION',
            'SOURCE_NUMBER_REVIEW','SOURCE_SHIFT_REVIEW','SOURCE_DATE_REVIEW'
        ));

    GRANT UPDATE (SourceProdDate,LotStop,DropCnt,pDropCnt,SourceShiftType,SourceRowNumber,
                  SourceShiftNo,SourceStartTime,SourceStopTime,LastSeenAt,UpdatedTime,IsCurrent,ReconciliationStatus)
        ON OBJECT::omagmes.AutoLot TO OMAG_MES;

    COMMIT TRANSACTION;
END TRY
BEGIN CATCH
    IF XACT_STATE()<>0 ROLLBACK TRANSACTION;
    THROW;
END CATCH;
GO

/* Read-only deployment verification. */
SELECT c.name,t.name AS DataType,c.max_length,c.precision,c.scale,c.is_nullable
FROM sys.columns c JOIN sys.types t ON t.user_type_id=c.user_type_id
WHERE c.object_id=OBJECT_ID(N'omagmes.AutoLot')
  AND c.name IN (N'id',N'LotNo',N'LotSequence',N'ShiftType',N'SourceShiftType',N'SourceRowNumber',N'SourceShiftNo',N'SourceStartTime',N'SourceStopTime')
ORDER BY c.column_id;
SELECT name,is_disabled,is_not_trusted FROM sys.check_constraints
WHERE parent_object_id=OBJECT_ID(N'omagmes.AutoLot')
  AND name IN (N'CK_AutoLot_LotNumber',N'CK_AutoLot_ReconciliationStatus');
EXECUTE AS USER=N'OMAG_MES';
SELECT HAS_PERMS_BY_NAME(N'omagmes.AutoLot',N'OBJECT',N'UPDATE',N'SourceShiftType',N'COLUMN') AS SourceShiftTypeUpdate,
       HAS_PERMS_BY_NAME(N'omagmes.AutoLot',N'OBJECT',N'UPDATE',N'SourceRowNumber',N'COLUMN') AS SourceRowNumberUpdate,
       HAS_PERMS_BY_NAME(N'omagmes.AutoLot',N'OBJECT',N'UPDATE',N'LotNo',N'COLUMN') AS LotNoUpdate;
REVERT;
GO
