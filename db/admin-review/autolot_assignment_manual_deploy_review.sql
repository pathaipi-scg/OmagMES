/*
APPROVAL DRAFT — MANUAL SSMS EXECUTION BY sa ONLY — DO NOT RUN BEFORE APPROVAL.
Target: OMAG / omagmes. Additive deployment of the three local AutoLot assignment
storage tables only. No seed rows or data migration. No existing source view,
Product/Mould master, ProductionLot, WorkTime, PIS object, linked server, synonym,
login mapping, credential, or provider string is modified.

Source identity limitations:
- dbo.vw_PRESS_LotAuto has no immutable row ID. AutoLotID is local IDENTITY;
  SourceKey fingerprints LotStart. If LotStart is corrected, the application
  recovers the local ID only when ProductionDate + LotNo match exactly one row.
  If both values change, continuity cannot be proven from this view.
- dbo.vw_OmagPlan has no source ID. PlanIdentityID references a local immutable
  snapshot keyed by a fingerprint of all reviewed source-view columns. It is not
  represented as a PIS primary key; indistinguishable duplicate rows are blocked.

Runtime permissions granted to OMAG_MES are limited to:
- AutoLot: SELECT; INSERT/UPDATE only for columns used by reconciliation.
- PlanIdentity: SELECT; INSERT only for snapshot columns.
- AutoLotAssignment: SELECT; INSERT/UPDATE only for assignment columns.
No DELETE, ALTER, CONTROL, schema, linked-server, Product, or Mould grants.
Existing OMAG_MES SELECT access to the Plan/AutoLot views and Product/Mould was
verified separately through the application login before preparing this draft.
Re-verify those grants using OMAG_MES after deployment; sa-context permission
checks do not represent OMAG_MES effective permissions.
*/
USE [OMAG];
GO
SET NOCOUNT ON;
SET XACT_ABORT ON;

IF DB_NAME() <> N'OMAG'
    THROW 55100, 'Wrong database. Select OMAG before running this reviewed script.', 1;
IF SUSER_SNAME() <> N'sa' OR ORIGINAL_LOGIN() <> N'sa' OR IS_SRVROLEMEMBER(N'sysadmin') <> 1
    THROW 55101, 'Manual deployment is restricted to a direct sa sysadmin session.', 1;
IF SCHEMA_ID(N'omagmes') IS NULL OR DATABASE_PRINCIPAL_ID(N'OMAG_MES') IS NULL
    THROW 55102, 'Required omagmes schema or OMAG_MES database principal is missing.', 1;
IF OBJECT_ID(N'dbo.vw_PRESS_LotAuto', N'V') IS NULL
   OR OBJECT_ID(N'dbo.vw_OmagPlan', N'V') IS NULL
   OR OBJECT_ID(N'omagmes.Product', N'U') IS NULL
   OR OBJECT_ID(N'omagmes.Mould', N'U') IS NULL
    THROW 55103, 'Required source views or existing Product/Mould masters are missing.', 1;
IF NOT EXISTS (
             SELECT 1 FROM sys.columns
             WHERE object_id = OBJECT_ID(N'omagmes.Product')
                 AND name = N'id' AND TYPE_NAME(user_type_id) = N'bigint'
     )
     OR NOT EXISTS (
             SELECT 1 FROM sys.columns
             WHERE object_id = OBJECT_ID(N'omagmes.Mould')
                 AND name = N'id' AND TYPE_NAME(user_type_id) = N'bigint'
     )
     OR NOT EXISTS (
             SELECT 1 FROM sys.columns
             WHERE object_id = OBJECT_ID(N'omagmes.Mould')
                 AND name = N'ProductID' AND TYPE_NAME(user_type_id) = N'bigint'
     )
   OR COL_LENGTH(N'omagmes.Product', N'ProductCode') IS NULL
   OR COL_LENGTH(N'omagmes.Product', N'ProductName') IS NULL
   OR COL_LENGTH(N'omagmes.Product', N'ProductNameThai') IS NULL
   OR COL_LENGTH(N'omagmes.Product', N'IsActive') IS NULL
   OR COL_LENGTH(N'omagmes.Mould', N'id') IS NULL
   OR COL_LENGTH(N'omagmes.Mould', N'ProductID') IS NULL
   OR COL_LENGTH(N'omagmes.Mould', N'MouldCode') IS NULL
   OR COL_LENGTH(N'omagmes.Mould', N'MouldName') IS NULL
   OR COL_LENGTH(N'omagmes.Mould', N'StatusCode') IS NULL
   OR COL_LENGTH(N'omagmes.Mould', N'IsActive') IS NULL
    THROW 55104, 'Existing Product/Mould masters differ from the inspected ID-first contract.', 1;
IF EXISTS (
    SELECT 1 FROM sys.objects
    WHERE schema_id = SCHEMA_ID(N'omagmes')
      AND name IN (N'AutoLot', N'AutoLotAssignment', N'PlanIdentity')
)
    THROW 55106, 'An assignment object already exists; stop and review it. This script never replaces objects.', 1;
IF EXISTS (
    SELECT 1 FROM sys.synonyms
    WHERE schema_id = SCHEMA_ID(N'omagmes')
      AND name IN (N'AutoLot', N'AutoLotAssignment', N'PlanIdentity')
)
    THROW 55107, 'A same-named synonym exists; stop and review it. This script never replaces objects.', 1;

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
        CONSTRAINT CK_PlanIdentity_Key CHECK (LEN(PlanKey) = 64 AND PlanKey NOT LIKE '%[^0-9a-f]%')
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
        CONSTRAINT CK_AutoLot_SourceKey CHECK (LEN(SourceKey) = 64 AND SourceKey NOT LIKE '%[^0-9a-f]%')
    );
    CREATE INDEX IX_AutoLot_ProductionDate_LotStart
        ON omagmes.AutoLot(ProductionDate, LotStart, id);

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
    CREATE INDEX IX_AutoLotAssignment_Product
        ON omagmes.AutoLotAssignment(ProductID, AutoLotID);

    GRANT SELECT ON OBJECT::omagmes.PlanIdentity TO OMAG_MES;
    GRANT INSERT (PlanKey, PlanSnapshotJson, PlanName, MaterialCode, MaterialName,
                   PlannedStart, PlanCountText, Machine, Shift)
        ON OBJECT::omagmes.PlanIdentity TO OMAG_MES;

    GRANT SELECT ON OBJECT::omagmes.AutoLot TO OMAG_MES;
    GRANT INSERT (ProductionDate, SourceKey, LotNo, ShiftType, ShiftNo, LotStart,
                  LotStop, StartTime, StopTime, pDropCnt, DropCnt)
        ON OBJECT::omagmes.AutoLot TO OMAG_MES;
    GRANT UPDATE (ProductionDate, SourceKey, LotNo, ShiftType, ShiftNo, LotStart,
                  LotStop, StartTime, StopTime, pDropCnt, DropCnt)
        ON OBJECT::omagmes.AutoLot TO OMAG_MES;

    GRANT SELECT ON OBJECT::omagmes.AutoLotAssignment TO OMAG_MES;
    GRANT INSERT (AutoLotID, PlanIdentityID, ProductID, MouldID)
        ON OBJECT::omagmes.AutoLotAssignment TO OMAG_MES;
    GRANT UPDATE (PlanIdentityID, ProductID, MouldID, UpdatedTime)
        ON OBJECT::omagmes.AutoLotAssignment TO OMAG_MES;

    COMMIT TRANSACTION;
END TRY
BEGIN CATCH
    IF XACT_STATE() <> 0 ROLLBACK TRANSACTION;
    THROW;
END CATCH;
GO

/* Post-deployment verification only; all statements below are SELECT-only. */
SELECT s.name AS SchemaName, t.name AS TableName, c.name AS ConstraintName,
       c.type_desc AS ConstraintType
FROM sys.tables AS t
JOIN sys.schemas AS s ON s.schema_id = t.schema_id
JOIN sys.objects AS c ON c.parent_object_id = t.object_id
WHERE s.name = N'omagmes'
  AND t.name IN (N'PlanIdentity', N'AutoLot', N'AutoLotAssignment')
  AND c.type IN ('PK', 'UQ', 'F', 'C')
ORDER BY t.name, c.type_desc, c.name;

SELECT grantee.name AS Grantee, OBJECT_SCHEMA_NAME(permission.major_id) AS SchemaName,
             OBJECT_NAME(permission.major_id) AS ObjectName, permission.permission_name AS PermissionName,
             permission.state_desc AS PermissionState, permission.minor_id AS ColumnID,
             column_info.name AS ColumnName
FROM sys.database_permissions AS permission
JOIN sys.database_principals AS grantee
    ON grantee.principal_id = permission.grantee_principal_id
LEFT JOIN sys.columns AS column_info
    ON column_info.object_id = permission.major_id
 AND column_info.column_id = permission.minor_id
WHERE grantee.name = N'OMAG_MES'
    AND permission.class = 1
    AND permission.major_id IN (
            OBJECT_ID(N'omagmes.PlanIdentity'), OBJECT_ID(N'omagmes.AutoLot'),
            OBJECT_ID(N'omagmes.AutoLotAssignment')
    )
ORDER BY ObjectName, PermissionName, ColumnID;
