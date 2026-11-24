/*
CLEAN DEVELOPMENT SETUP — DBA/OWNER MANUAL REVIEW ONLY. DO NOT EXECUTE AUTOMATICALLY.
Target: OMAG / omagmes. This creates only local AutoLot assignment identity/storage;
it does not alter any source view, Product/Mould master, ProductionLot, WorkTime,
PIS object, linked server, synonym, login mapping, credential, or password.
No legacy migration or seeding is included. Review and deploy manually as an
authorized database owner after source access and permissions are confirmed.

Identity notes:
- dbo.vw_PRESS_LotAuto exposes no immutable row ID. AutoLotID is a local IDENTITY;
    SourceKey is a unique fingerprint of the SQL-generated LotStart used to
    re-find that current view row on refresh. If LotStart is corrected upstream,
    reconciliation can preserve AutoLotID only when ProductionDate + LotNo match
    exactly one existing local row. If both LotStart and LotNo change, the view has
    no durable key to prove continuity; review is required before treating it as
    the same source Lot. SQL LotNo/shift/time/counter facts are copied verbatim and
    never calculated here.
- dbo.vw_OmagPlan exposes no source ID. PlanIdentityID references an immutable
  local snapshot row, uniquely keyed by a fingerprint of all reviewed plan-view
  columns. It is not represented as a PIS primary key. Identical duplicate rows
  are not assignable in the application.
*/
USE [OMAG];
GO
SET NOCOUNT ON;
SET XACT_ABORT ON;
IF DB_NAME()<>N'OMAG' OR (COALESCE(IS_SRVROLEMEMBER(N'sysadmin'),0)<>1 AND COALESCE(IS_MEMBER(N'db_owner'),0)<>1)
    THROW 55100, 'Assignment setup requires an authorized OMAG DBA/owner session.', 1;
IF SCHEMA_ID(N'omagmes') IS NULL OR DATABASE_PRINCIPAL_ID(N'OMAG_MES') IS NULL
    THROW 55101, 'Required omagmes schema or OMAG_MES principal is missing.', 1;
IF OBJECT_ID(N'dbo.vw_PRESS_LotAuto',N'V') IS NULL OR OBJECT_ID(N'dbo.vw_OmagPlan',N'V') IS NULL
   OR OBJECT_ID(N'omagmes.Product',N'U') IS NULL OR OBJECT_ID(N'omagmes.Mould',N'U') IS NULL
    THROW 55102, 'Required SQL AutoLot/Plan views or existing Product/Mould masters are missing.', 1;
IF COL_LENGTH(N'omagmes.Product',N'id') IS NULL OR COL_LENGTH(N'omagmes.Product',N'ProductCode') IS NULL
   OR COL_LENGTH(N'omagmes.Product',N'ProductName') IS NULL OR COL_LENGTH(N'omagmes.Product',N'IsActive') IS NULL
   OR COL_LENGTH(N'omagmes.Mould',N'id') IS NULL OR COL_LENGTH(N'omagmes.Mould',N'ProductID') IS NULL
   OR COL_LENGTH(N'omagmes.Mould',N'MouldCode') IS NULL OR COL_LENGTH(N'omagmes.Mould',N'MouldName') IS NULL
   OR COL_LENGTH(N'omagmes.Mould',N'StatusCode') IS NULL OR COL_LENGTH(N'omagmes.Mould',N'IsActive') IS NULL
    THROW 55103, 'Existing Product/Mould masters differ from the inspected ID-first contract.', 1;
IF OBJECT_ID(N'omagmes.AutoLot') IS NOT NULL OR OBJECT_ID(N'omagmes.PlanIdentity') IS NOT NULL
   OR OBJECT_ID(N'omagmes.AutoLotAssignment') IS NOT NULL
    THROW 55104, 'An assignment object already exists; inspect it rather than replacing it.', 1;
GO
BEGIN TRY
    BEGIN TRANSACTION;

    CREATE TABLE omagmes.PlanIdentity
    (
        id bigint IDENTITY(1,1) NOT NULL CONSTRAINT PK_PlanIdentity PRIMARY KEY,
        Rectime datetime NOT NULL CONSTRAINT DF_PlanIdentity_Rectime DEFAULT (GETDATE()),
        PlanKey char(64) COLLATE Latin1_General_100_BIN2 NOT NULL,
        PlanSnapshotJson nvarchar(max) NOT NULL,
        PlanName nvarchar(200) NULL,
        MaterialCode nvarchar(200) NULL,
        MaterialName nvarchar(400) NULL,
        PlannedStart date NULL,
        PlanCountText nvarchar(100) NULL,
        Machine nvarchar(100) NULL,
        Shift nvarchar(100) NULL,
        CONSTRAINT UQ_PlanIdentity_PlanKey UNIQUE (PlanKey),
        CONSTRAINT CK_PlanIdentity_Key CHECK (LEN(PlanKey)=64 AND PlanKey NOT LIKE '%[^0-9a-f]%')
    );

    CREATE TABLE omagmes.AutoLot
    (
        id bigint IDENTITY(1,1) NOT NULL CONSTRAINT PK_AutoLot PRIMARY KEY,
        Rectime datetime NOT NULL CONSTRAINT DF_AutoLot_Rectime DEFAULT (GETDATE()),
        ProductionDate date NOT NULL,
        SourceKey char(64) COLLATE Latin1_General_100_BIN2 NOT NULL,
        LotNo nvarchar(100) NULL,
        ShiftType int NULL,
        ShiftNo nvarchar(20) NULL,
        LotStart datetime NOT NULL,
        LotStop datetime NULL,
        StartTime time(7) NULL,
        StopTime time(7) NULL,
        pDropCnt bigint NULL,
        DropCnt bigint NULL,
        CONSTRAINT UQ_AutoLot_SourceKey UNIQUE (SourceKey),
        CONSTRAINT CK_AutoLot_SourceKey CHECK (LEN(SourceKey)=64 AND SourceKey NOT LIKE '%[^0-9a-f]%')
    );
    CREATE INDEX IX_AutoLot_ProductionDate_LotStart ON omagmes.AutoLot(ProductionDate,LotStart,id);

    CREATE TABLE omagmes.AutoLotAssignment
    (
        id bigint IDENTITY(1,1) NOT NULL CONSTRAINT PK_AutoLotAssignment PRIMARY KEY,
        Rectime datetime NOT NULL CONSTRAINT DF_AutoLotAssignment_Rectime DEFAULT (GETDATE()),
        AutoLotID bigint NOT NULL,
        PlanIdentityID bigint NULL,
        ProductID bigint NULL,
        MouldID bigint NULL,
        UpdatedTime datetime NOT NULL CONSTRAINT DF_AutoLotAssignment_UpdatedTime DEFAULT (GETDATE()),
        CONSTRAINT UQ_AutoLotAssignment_AutoLot UNIQUE (AutoLotID),
        CONSTRAINT FK_AutoLotAssignment_AutoLot FOREIGN KEY (AutoLotID) REFERENCES omagmes.AutoLot(id),
        CONSTRAINT FK_AutoLotAssignment_Plan FOREIGN KEY (PlanIdentityID) REFERENCES omagmes.PlanIdentity(id),
        CONSTRAINT FK_AutoLotAssignment_Product FOREIGN KEY (ProductID) REFERENCES omagmes.Product(id),
        CONSTRAINT FK_AutoLotAssignment_Mould FOREIGN KEY (MouldID) REFERENCES omagmes.Mould(id),
        CONSTRAINT CK_AutoLotAssignment_Complete CHECK (
            (PlanIdentityID IS NULL AND ProductID IS NULL AND MouldID IS NULL)
            OR (PlanIdentityID IS NOT NULL AND ProductID IS NOT NULL AND MouldID IS NOT NULL)
        )
    );
    CREATE INDEX IX_AutoLotAssignment_Product ON omagmes.AutoLotAssignment(ProductID,AutoLotID);

    GRANT SELECT,INSERT ON OBJECT::omagmes.PlanIdentity TO OMAG_MES;
    GRANT SELECT,INSERT,UPDATE ON OBJECT::omagmes.AutoLot TO OMAG_MES;
    GRANT SELECT,INSERT ON OBJECT::omagmes.AutoLotAssignment TO OMAG_MES;
    GRANT UPDATE (PlanIdentityID,ProductID,MouldID,UpdatedTime)
        ON OBJECT::omagmes.AutoLotAssignment TO OMAG_MES;

    COMMIT TRANSACTION;
END TRY
BEGIN CATCH
    IF XACT_STATE()<>0 ROLLBACK TRANSACTION;
    THROW;
END CATCH;
GO
