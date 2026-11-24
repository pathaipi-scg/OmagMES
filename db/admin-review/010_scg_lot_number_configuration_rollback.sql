/*
DBA REVIEW ONLY — DO NOT EXECUTE WITHOUT SEPARATE DBA/OWNER AUTHORIZATION.
Rollback for db/admin-review/010_scg_lot_number_configuration.sql.
Refuses to narrow constraints if any new B/A/Shift-3 rows exist; it never edits
or deletes Lot or sequence records. Existing rows must remain untouched.
*/
SET NOCOUNT ON;
SET XACT_ABORT ON;

DECLARE @ExpectedDatabase sysname = N'OMAG';
DECLARE @ExpectedServerName nvarchar(128) = N'SCGLS-NK\SQLEXPRESS';
DECLARE @ExpectedInstanceName nvarchar(128) = N'SQLEXPRESS';
DECLARE @ExecutionOriginalLogin sysname = ORIGINAL_LOGIN();
DECLARE @ExecutionSqlLogin sysname = SUSER_SNAME();

IF @@TRANCOUNT <> 0
    THROW 54020, 'Run rollback 010 without an ambient transaction.', 1;
IF DB_NAME() <> @ExpectedDatabase
    THROW 54021, 'Rollback 010 stopped: database does not match OMAG.', 1;
IF ISNULL(CONVERT(nvarchar(128), @@SERVERNAME), N'') <> @ExpectedServerName
   OR ISNULL(CONVERT(nvarchar(128), SERVERPROPERTY(N'ServerName')), N'') <> @ExpectedServerName
   OR ISNULL(CONVERT(nvarchar(128), SERVERPROPERTY(N'InstanceName')), N'') <> @ExpectedInstanceName
    THROW 54022, 'Rollback 010 stopped: SQL Server instance identity is not the approved OMAG instance.', 1;
IF LOWER(ISNULL(@ExecutionOriginalLogin, N'')) = N'omag_mes'
   OR LOWER(ISNULL(@ExecutionSqlLogin, N'')) = N'omag_mes'
    THROW 54023, 'Rollback 010 must not be executed by the application runtime login.', 1;
IF OBJECT_ID(N'omagmes.ProductionLot', N'U') IS NULL
   OR OBJECT_ID(N'omagmes.LotNumberSequence', N'U') IS NULL
    THROW 54024, 'Rollback 010 requires the existing ProductionLot and LotNumberSequence tables.', 1;
IF EXISTS (SELECT 1 FROM omagmes.ProductionLot WHERE MachineCode <> 'B')
   OR EXISTS (SELECT 1 FROM omagmes.LotNumberSequence WHERE PlantCode <> 'C' OR ShiftCode NOT IN ('1','2'))
    THROW 54025, 'Rollback 010 refused: rows use the confirmed new numbering configuration; preserve them and keep the expanded checks.', 1;

BEGIN TRY
    BEGIN TRANSACTION;
    ALTER TABLE omagmes.ProductionLot DROP CONSTRAINT CK_ProductionLot_NumberParts;
    ALTER TABLE omagmes.LotNumberSequence DROP CONSTRAINT CK_LotNumberSequence_Plant;
    ALTER TABLE omagmes.LotNumberSequence DROP CONSTRAINT CK_LotNumberSequence_Shift;

    ALTER TABLE omagmes.ProductionLot WITH CHECK ADD CONSTRAINT CK_ProductionLot_NumberParts
        CHECK (LotSequence BETWEEN 1 AND 99 AND MachineCode='B' AND LEN(LotNo)=11);
    ALTER TABLE omagmes.LotNumberSequence WITH CHECK ADD CONSTRAINT CK_LotNumberSequence_Plant
        CHECK (PlantCode='C');
    ALTER TABLE omagmes.LotNumberSequence WITH CHECK ADD CONSTRAINT CK_LotNumberSequence_Shift
        CHECK (ShiftCode IN ('1','2'));

    ALTER TABLE omagmes.ProductionLot CHECK CONSTRAINT CK_ProductionLot_NumberParts;
    ALTER TABLE omagmes.LotNumberSequence CHECK CONSTRAINT CK_LotNumberSequence_Plant;
    ALTER TABLE omagmes.LotNumberSequence CHECK CONSTRAINT CK_LotNumberSequence_Shift;
    COMMIT TRANSACTION;
END TRY
BEGIN CATCH
    IF XACT_STATE() <> 0 ROLLBACK TRANSACTION;
    THROW;
END CATCH;
