/*
REVIEW-ONLY ROLLBACK DRAFT — DO NOT EXECUTE WITHOUT SEPARATE DBA/OWNER AUTHORIZATION.
Destructive: refuses to proceed if any Production Lot/run/transaction data exists.
Never run as a deployment convenience; take and verify an approved backup first.
*/
SET NOCOUNT ON;
SET XACT_ABORT ON;
IF DB_NAME() <> N'OMAG'
    THROW 53100, 'OmagMES migration 003 rollback only applies to database OMAG.', 1;
IF OBJECT_ID(N'omagmes.ProductionLot', N'U') IS NULL
    THROW 53101, 'ProductionLot is absent; rollback is not applicable.', 1;
IF EXISTS (SELECT 1 FROM omagmes.ProductionLot)
   OR EXISTS (SELECT 1 FROM omagmes.ProductionRun)
   OR EXISTS (SELECT 1 FROM omagmes.Product)
   OR EXISTS (SELECT 1 FROM omagmes.ProductionEntry)
   OR EXISTS (SELECT 1 FROM omagmes.CuringInputEntry)
   OR EXISTS (SELECT 1 FROM omagmes.DepalletEvent)
   OR EXISTS (SELECT 1 FROM omagmes.DispatchLine)
   OR EXISTS (SELECT 1 FROM omagmes.Dispatch)
    OR EXISTS (SELECT 1 FROM omagmes.LotNumberSequence)
    OR EXISTS (SELECT 1 FROM omagmes.AutoLotResetReview)
    THROW 53102, 'Rollback refused because production/master rows exist; preserve data and create a reviewed forward migration instead.', 1;
BEGIN TRANSACTION;
DROP TABLE omagmes.LotNumberSequence;
DROP TABLE omagmes.AutoLotResetReview;
DROP TABLE omagmes.DispatchLine;
DROP TABLE omagmes.Dispatch;
DROP TABLE omagmes.DepalletEvent;
DROP TABLE omagmes.CuringInputEntry;
DROP TABLE omagmes.ProductionEntryCorrection;
DROP TABLE omagmes.ProductionEntry;
DROP TABLE omagmes.ProductionLotNameHistory;
DROP TABLE omagmes.ProductionLot;
DROP TABLE omagmes.ProductionRun;
DROP TABLE omagmes.ProductStandardRevision;
DROP TABLE omagmes.Product;
COMMIT TRANSACTION;
GO
