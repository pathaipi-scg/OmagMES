/*
DBA REVIEW ONLY — DO NOT EXECUTE WITHOUT SEPARATE DBA/OWNER AUTHORIZATION.
OmagMES 010: enable the confirmed Nong Khae BLOCK SCG number configuration.
Changes check-constraint acceptance only; it does not insert, update, delete,
or renumber any ProductionLot or LotNumberSequence rows. Keep legacy C/B
number scopes and B machine suffixes valid for historical rows. New application
number proposals use PlantCode B, Shift 1/2/3, and LineCode A.
*/
SET NOCOUNT ON;
SET XACT_ABORT ON;

DECLARE @ExpectedDatabase sysname = N'OMAG';
DECLARE @ExpectedServerName nvarchar(128) = N'SCGLS-NK\SQLEXPRESS';
DECLARE @ExpectedInstanceName nvarchar(128) = N'SQLEXPRESS';
DECLARE @ExecutionOriginalLogin sysname = ORIGINAL_LOGIN();
DECLARE @ExecutionSqlLogin sysname = SUSER_SNAME();

IF @@TRANCOUNT <> 0
    THROW 54000, 'Run migration 010 without an ambient transaction.', 1;
IF DB_NAME() <> @ExpectedDatabase
    THROW 54001, 'Migration 010 stopped: database does not match OMAG.', 1;
IF ISNULL(CONVERT(nvarchar(128), @@SERVERNAME), N'') <> @ExpectedServerName
   OR ISNULL(CONVERT(nvarchar(128), SERVERPROPERTY(N'ServerName')), N'') <> @ExpectedServerName
   OR ISNULL(CONVERT(nvarchar(128), SERVERPROPERTY(N'InstanceName')), N'') <> @ExpectedInstanceName
    THROW 54002, 'Migration 010 stopped: SQL Server instance identity is not the approved OMAG instance.', 1;
IF LOWER(ISNULL(@ExecutionOriginalLogin, N'')) = N'omag_mes'
   OR LOWER(ISNULL(@ExecutionSqlLogin, N'')) = N'omag_mes'
    THROW 54003, 'Migration 010 must not be executed by the application runtime login.', 1;
IF OBJECT_ID(N'omagmes.ProductionLot', N'U') IS NULL
   OR OBJECT_ID(N'omagmes.LotNumberSequence', N'U') IS NULL
    THROW 54004, 'Migration 010 requires the existing ProductionLot and LotNumberSequence tables.', 1;
IF NOT EXISTS (SELECT 1 FROM sys.check_constraints WHERE parent_object_id=OBJECT_ID(N'omagmes.ProductionLot') AND name=N'CK_ProductionLot_NumberParts' AND is_disabled=0 AND is_not_trusted=0)
   OR NOT EXISTS (SELECT 1 FROM sys.check_constraints WHERE parent_object_id=OBJECT_ID(N'omagmes.LotNumberSequence') AND name=N'CK_LotNumberSequence_Plant' AND is_disabled=0 AND is_not_trusted=0)
   OR NOT EXISTS (SELECT 1 FROM sys.check_constraints WHERE parent_object_id=OBJECT_ID(N'omagmes.LotNumberSequence') AND name=N'CK_LotNumberSequence_Shift' AND is_disabled=0 AND is_not_trusted=0)
    THROW 54005, 'Migration 010 stopped: expected trusted numbering checks are missing; inspect the actual schema before proceeding.', 1;
IF NOT EXISTS (SELECT 1 FROM sys.key_constraints WHERE parent_object_id=OBJECT_ID(N'omagmes.ProductionLot') AND name=N'UQ_ProductionLot_LotNo' AND type=N'UQ')
   OR NOT EXISTS (SELECT 1 FROM sys.key_constraints WHERE parent_object_id=OBJECT_ID(N'omagmes.LotNumberSequence') AND name=N'UQ_LotNumberSequence_Scope' AND type=N'UQ')
    THROW 54006, 'Migration 010 stopped: official LotNo and sequence-scope uniqueness constraints are required.', 1;
IF EXISTS (
    SELECT 1 FROM sys.check_constraints
    WHERE parent_object_id IN (OBJECT_ID(N'omagmes.ProductionLot'), OBJECT_ID(N'omagmes.LotNumberSequence'))
      AND name IN (N'CK_ProductionLot_NumberParts',N'CK_LotNumberSequence_Plant',N'CK_LotNumberSequence_Shift')
      AND is_disabled=0 AND is_not_trusted=0
      AND definition LIKE N'%''A''%'
)
    THROW 54007, 'Migration 010 appears already applied or partially applied; inspect constraint definitions and stop.', 1;

BEGIN TRY
    BEGIN TRANSACTION;
    ALTER TABLE omagmes.ProductionLot DROP CONSTRAINT CK_ProductionLot_NumberParts;
    ALTER TABLE omagmes.LotNumberSequence DROP CONSTRAINT CK_LotNumberSequence_Plant;
    ALTER TABLE omagmes.LotNumberSequence DROP CONSTRAINT CK_LotNumberSequence_Shift;

    ALTER TABLE omagmes.ProductionLot WITH CHECK ADD CONSTRAINT CK_ProductionLot_NumberParts
        CHECK (LotSequence BETWEEN 1 AND 99 AND MachineCode IN ('A','B') AND LEN(LotNo)=11);
    ALTER TABLE omagmes.LotNumberSequence WITH CHECK ADD CONSTRAINT CK_LotNumberSequence_Plant
        CHECK (PlantCode IN ('B','C'));
    ALTER TABLE omagmes.LotNumberSequence WITH CHECK ADD CONSTRAINT CK_LotNumberSequence_Shift
        CHECK (ShiftCode IN ('1','2','3'));

    ALTER TABLE omagmes.ProductionLot CHECK CONSTRAINT CK_ProductionLot_NumberParts;
    ALTER TABLE omagmes.LotNumberSequence CHECK CONSTRAINT CK_LotNumberSequence_Plant;
    ALTER TABLE omagmes.LotNumberSequence CHECK CONSTRAINT CK_LotNumberSequence_Shift;
    COMMIT TRANSACTION;
END TRY
BEGIN CATCH
    IF XACT_STATE() <> 0 ROLLBACK TRANSACTION;
    THROW;
END CATCH;
