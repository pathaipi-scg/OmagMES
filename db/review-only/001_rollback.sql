/*
DESTRUCTIVE ROLLBACK DRAFT — DO NOT EXECUTE.
Only considered after DBA approval, verified backup, confirmed OMAG target, and proof the schema is an empty disposable non-production installation.
This draft will refuse rollback if any row exists in any omagmes table. It has not been tested on SQL Server.
*/
SET XACT_ABORT ON;
IF DB_NAME() <> N'OMAG'
    THROW 51200, 'Rollback draft targets database OMAG only; execution stopped.', 1;
IF SCHEMA_ID(N'omagmes') IS NULL
    THROW 51201, 'Schema omagmes does not exist; nothing to roll back.', 1;
GO
DECLARE @TableName sysname;
DECLARE @HasRows bit;
DECLARE @Sql nvarchar(max);
DECLARE table_cursor CURSOR LOCAL FAST_FORWARD FOR
    SELECT name FROM sys.tables WHERE schema_id = SCHEMA_ID(N'omagmes');
OPEN table_cursor;
FETCH NEXT FROM table_cursor INTO @TableName;
WHILE @@FETCH_STATUS = 0
BEGIN
    SET @HasRows = 0;
    SET @Sql = N'SELECT @HasRows = CASE WHEN EXISTS (SELECT 1 FROM omagmes.' + QUOTENAME(@TableName) + N') THEN 1 ELSE 0 END;';
    EXEC sys.sp_executesql @Sql,
        N'@HasRows bit OUTPUT', @HasRows = @HasRows OUTPUT;
    IF @HasRows = 1
    BEGIN
        CLOSE table_cursor;
        DEALLOCATE table_cursor;
        THROW 51202, 'Rollback refused: omagmes contains data.', 1;
    END;
    FETCH NEXT FROM table_cursor INTO @TableName;
END;
CLOSE table_cursor;
DEALLOCATE table_cursor;
GO
BEGIN TRANSACTION;
DROP TABLE omagmes.PressCounterStep;
DROP TABLE omagmes.PressCounterAccumulator;
DROP TABLE omagmes.WetCameraObservation;
DROP TABLE omagmes.PressCounterResetBoundary;
DROP TABLE omagmes.PressCounterObservation;
DROP TABLE omagmes.MouldUseEvent;
DROP TABLE omagmes.MouldReconditionCycle;
DROP TABLE omagmes.MouldStatusHistory;
DROP TABLE omagmes.Mould;
DROP TABLE omagmes.DepalletEvent;
DROP TABLE omagmes.CuringRecord;
DROP TABLE omagmes.WetRunEvent;
DROP TABLE omagmes.WetRejectEntry;
DROP TABLE omagmes.WetRejectReason;
DROP TABLE omagmes.ProductionEntryCorrection;
DROP TABLE omagmes.ProductionEntry;
DROP TABLE omagmes.LotNameChangeHistory;
DROP TABLE omagmes.ProductionLot;
DROP TABLE omagmes.ProductionRun;
DROP TABLE omagmes.ProductProductionStandard;
DROP TABLE omagmes.Color;
DROP TABLE omagmes.ProductCodeAssignment;
DROP TABLE omagmes.Product;
DROP TABLE omagmes.ProductFamily;
DROP TABLE omagmes.ProductionLine;
DROP TABLE omagmes.Plant;
DROP TABLE omagmes.AppUser;
DROP SCHEMA omagmes;
COMMIT TRANSACTION;
GO
