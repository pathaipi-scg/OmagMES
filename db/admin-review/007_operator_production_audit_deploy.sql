/*
    DBA-REVIEW SCRIPT ONLY — DO NOT EXECUTE FROM THE APPLICATION.
    Target: OMAG, schema omagmes. Based on a read-only catalog inspection on 2026-11-17.

    This is an idempotent, additive deployment for the objects/columns observed missing:
      ProductionEntry: IsDeleted, DeletedAt, DeletedBy, DeleteReason, OperatorConfirmed
      CuringInputEntry: OperatorConfirmed
      Tables: ProductionEntryChangeHistory, WetRejectReason, WetRejectEntry,
              Mould, MouldHistory

    It does not seed Product, WetRejectReason, Mould, or operational rows; does not
    modify dbo/legacy objects; does not create/change server logins; and does not
    grant OMAG_MES sysadmin or ALTER. Execute only after owner/DBA review, in SSMS,
    connected as an authorized administrator to database OMAG.

    Permission plan: remove OMAG_MES direct schema-wide/table-wide INSERT/UPDATE/DELETE
    grants in omagmes, then grant only the object-level DML used by the current SQL
    production workflows. Keep existing SELECT grants/roles unchanged; audit their
    scope separately before considering removal (source views and PIS rely on SELECT).
*/
SET NOCOUNT ON;
SET XACT_ABORT ON;

IF DB_NAME() <> N'OMAG'
    THROW 53720, 'This deployment script requires database OMAG.', 1;
IF SCHEMA_ID(N'omagmes') IS NULL
    THROW 53721, 'The omagmes schema is missing; stop and review configuration migrations first.', 1;
IF DATABASE_PRINCIPAL_ID(N'OMAG_MES') IS NULL
    THROW 53722, 'The OMAG_MES database principal is missing; have the DBA map the approved login first.', 1;
IF NOT EXISTS (
    SELECT 1
    FROM sys.database_principals dp
    JOIN sys.server_principals sp ON sp.sid = dp.sid
    WHERE dp.principal_id = DATABASE_PRINCIPAL_ID(N'OMAG_MES')
      AND sp.name = N'OMAG_MES'
      AND dp.type = 'S'
)
    THROW 53723, 'OMAG_MES is not mapped to the matching SQL login; stop and resolve login mapping.', 1;
IF EXISTS (
    SELECT 1
    FROM sys.database_role_members rm
    JOIN sys.database_principals rolep ON rolep.principal_id = rm.role_principal_id
    WHERE rm.member_principal_id = DATABASE_PRINCIPAL_ID(N'OMAG_MES')
      AND rolep.name NOT IN (N'db_datareader')
)
    THROW 53724, 'OMAG_MES has an unexpected database-role membership; review it before changing permissions.', 1;
IF EXISTS (
    SELECT 1 FROM (VALUES
        (N'Product'), (N'ProductStandardRevision'), (N'ProductionRun'), (N'ProductionLot'),
        (N'ProductionEntry'), (N'ProductionEntryCorrection'), (N'CuringInputEntry'),
        (N'DepalletEvent'), (N'Dispatch'), (N'DispatchLine'), (N'LotNumberSequence'),
        (N'AutoLotResetReview'), (N'ProductionLotNameHistory')
    ) AS expected(ObjectName)
    WHERE OBJECT_ID(N'omagmes.' + expected.ObjectName, N'U') IS NULL
)
    THROW 53725, 'A required installed OmagMES base table is missing; apply/review its migration separately.', 1;

BEGIN TRY
    BEGIN TRANSACTION;

    /* Additive, rerunnable columns. Existing data (if any) receives safe defaults. */
    IF COL_LENGTH(N'omagmes.ProductionEntry', N'IsDeleted') IS NULL
        ALTER TABLE omagmes.ProductionEntry ADD IsDeleted bit NOT NULL
            CONSTRAINT DF_ProductionEntry_IsDeleted_007 DEFAULT (0) WITH VALUES;
    IF COL_LENGTH(N'omagmes.ProductionEntry', N'DeletedAt') IS NULL
        ALTER TABLE omagmes.ProductionEntry ADD DeletedAt datetimeoffset(0) NULL;
    IF COL_LENGTH(N'omagmes.ProductionEntry', N'DeletedBy') IS NULL
        ALTER TABLE omagmes.ProductionEntry ADD DeletedBy nvarchar(200) NULL;
    IF COL_LENGTH(N'omagmes.ProductionEntry', N'DeleteReason') IS NULL
        ALTER TABLE omagmes.ProductionEntry ADD DeleteReason nvarchar(500) NULL;
    IF COL_LENGTH(N'omagmes.ProductionEntry', N'OperatorConfirmed') IS NULL
        ALTER TABLE omagmes.ProductionEntry ADD OperatorConfirmed bit NOT NULL
            CONSTRAINT DF_ProductionEntry_OperatorConfirmed_007 DEFAULT (0) WITH VALUES;
    IF COL_LENGTH(N'omagmes.CuringInputEntry', N'OperatorConfirmed') IS NULL
        ALTER TABLE omagmes.CuringInputEntry ADD OperatorConfirmed bit NOT NULL
            CONSTRAINT DF_CuringInputEntry_OperatorConfirmed_007 DEFAULT (0) WITH VALUES;
    IF NOT EXISTS (
        SELECT 1 FROM sys.default_constraints d
        JOIN sys.columns c ON c.object_id=d.parent_object_id AND c.column_id=d.parent_column_id
        WHERE d.parent_object_id=OBJECT_ID(N'omagmes.ProductionEntry') AND c.name=N'IsDeleted'
    )
        ALTER TABLE omagmes.ProductionEntry ADD CONSTRAINT DF_ProductionEntry_IsDeleted_007 DEFAULT (0) FOR IsDeleted;
    IF NOT EXISTS (
        SELECT 1 FROM sys.default_constraints d
        JOIN sys.columns c ON c.object_id=d.parent_object_id AND c.column_id=d.parent_column_id
        WHERE d.parent_object_id=OBJECT_ID(N'omagmes.ProductionEntry') AND c.name=N'OperatorConfirmed'
    )
        ALTER TABLE omagmes.ProductionEntry ADD CONSTRAINT DF_ProductionEntry_OperatorConfirmed_007 DEFAULT (0) FOR OperatorConfirmed;
    IF NOT EXISTS (
        SELECT 1 FROM sys.default_constraints d
        JOIN sys.columns c ON c.object_id=d.parent_object_id AND c.column_id=d.parent_column_id
        WHERE d.parent_object_id=OBJECT_ID(N'omagmes.CuringInputEntry') AND c.name=N'OperatorConfirmed'
    )
        ALTER TABLE omagmes.CuringInputEntry ADD CONSTRAINT DF_CuringInputEntry_OperatorConfirmed_007 DEFAULT (0) FOR OperatorConfirmed;

    /*
       Compile the catalog check only after the ALTER statements have run. SQL Server
       can compile a static catalog query against the pre-ALTER metadata for this
       batch; sp_executesql creates a fresh compilation while preserving this transaction.
    */
    DECLARE @Migration007ColumnMismatch bit = 0;
    EXEC sys.sp_executesql
        N'SELECT @Mismatch = CASE WHEN EXISTS (
            SELECT 1
            FROM (VALUES
                (N''ProductionEntry'',N''IsDeleted'',N''bit'',1,0),
                (N''ProductionEntry'',N''DeletedAt'',N''datetimeoffset'',8,1),
                (N''ProductionEntry'',N''DeletedBy'',N''nvarchar'',400,1),
                (N''ProductionEntry'',N''DeleteReason'',N''nvarchar'',1000,1),
                (N''ProductionEntry'',N''OperatorConfirmed'',N''bit'',1,0),
                (N''CuringInputEntry'',N''OperatorConfirmed'',N''bit'',1,0)
            ) AS expected(TableName,ColumnName,TypeName,MaxLength,IsNullable)
            JOIN sys.tables t ON t.schema_id=SCHEMA_ID(N''omagmes'') AND t.name=expected.TableName
            LEFT JOIN sys.columns c ON c.object_id=t.object_id AND c.name=expected.ColumnName
            LEFT JOIN sys.types ty ON ty.user_type_id=c.user_type_id
            WHERE c.column_id IS NULL OR ty.name<>expected.TypeName
               OR c.max_length<>expected.MaxLength OR c.is_nullable<>expected.IsNullable
        ) THEN 1 ELSE 0 END;',
        N'@Mismatch bit OUTPUT',
        @Mismatch = @Migration007ColumnMismatch OUTPUT;

    IF @Migration007ColumnMismatch = 1
        THROW 53726, 'A Migration 007 column has an incompatible type, length, or nullability; rollback and inspect.', 1;

    /* Production Entry audit history. */
    IF OBJECT_ID(N'omagmes.ProductionEntryChangeHistory', N'U') IS NULL
    BEGIN
        CREATE TABLE omagmes.ProductionEntryChangeHistory (
            id bigint IDENTITY(1,1) NOT NULL CONSTRAINT PK_ProductionEntryChangeHistory PRIMARY KEY,
            Rectime datetime NOT NULL CONSTRAINT DF_ProductionEntryChangeHistory_Rectime DEFAULT (GETDATE()),
            ProductionEntryID bigint NOT NULL,
            ChangeType varchar(10) NOT NULL,
            ChangedBy nvarchar(200) NOT NULL,
            ChangedAt datetimeoffset(0) NOT NULL,
            ChangeReason nvarchar(500) NOT NULL,
            BeforeStateJson nvarchar(max) NULL,
            AfterStateJson nvarchar(max) NULL,
            CONSTRAINT FK_ProductionEntryChangeHistory_Entry FOREIGN KEY (ProductionEntryID) REFERENCES omagmes.ProductionEntry(id),
            CONSTRAINT CK_ProductionEntryChangeHistory_Type CHECK (ChangeType IN ('SAVE','EDIT','DELETE')),
            CONSTRAINT CK_ProductionEntryChangeHistory_Reason CHECK (LEN(LTRIM(RTRIM(ChangeReason))) > 0)
        );
    END;
    IF OBJECT_ID(N'omagmes.ProductionEntryChangeHistory', N'U') IS NULL
        THROW 53727, 'ProductionEntryChangeHistory creation failed.', 1;
    IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id=OBJECT_ID(N'omagmes.ProductionEntryChangeHistory') AND name=N'IX_ProductionEntryChangeHistory_Entry_ChangedAt')
        CREATE INDEX IX_ProductionEntryChangeHistory_Entry_ChangedAt ON omagmes.ProductionEntryChangeHistory(ProductionEntryID,ChangedAt DESC,id DESC);

    /* Database-owned Wet Reject reason master and entries; no demo reasons are seeded. */
    IF OBJECT_ID(N'omagmes.WetRejectReason', N'U') IS NULL
    BEGIN
        CREATE TABLE omagmes.WetRejectReason (
            id bigint IDENTITY(1,1) NOT NULL CONSTRAINT PK_WetRejectReason PRIMARY KEY,
            Rectime datetime NOT NULL CONSTRAINT DF_WetRejectReason_Rectime DEFAULT (GETDATE()),
            ReasonCode nvarchar(40) COLLATE Latin1_General_100_BIN2 NOT NULL,
            ReasonName nvarchar(200) NOT NULL,
            IsActive bit NOT NULL CONSTRAINT DF_WetRejectReason_IsActive DEFAULT (1),
            CONSTRAINT UQ_WetRejectReason_ReasonCode UNIQUE (ReasonCode),
            CONSTRAINT CK_WetRejectReason_Code CHECK (LEN(LTRIM(RTRIM(ReasonCode))) > 0),
            CONSTRAINT CK_WetRejectReason_Name CHECK (LEN(LTRIM(RTRIM(ReasonName))) > 0)
        );
    END;
    IF OBJECT_ID(N'omagmes.WetRejectEntry', N'U') IS NULL
    BEGIN
        CREATE TABLE omagmes.WetRejectEntry (
            id bigint IDENTITY(1,1) NOT NULL CONSTRAINT PK_WetRejectEntry PRIMARY KEY,
            Rectime datetime NOT NULL CONSTRAINT DF_WetRejectEntry_Rectime DEFAULT (GETDATE()),
            ProductionLotID bigint NOT NULL,
            RejectReasonID bigint NOT NULL,
            Quantity bigint NOT NULL,
            RecordedAt datetimeoffset(0) NOT NULL,
            EnteredBy nvarchar(200) NOT NULL,
            OperatorNote nvarchar(1000) NULL,
            IsDeleted bit NOT NULL CONSTRAINT DF_WetRejectEntry_IsDeleted DEFAULT (0),
            CONSTRAINT FK_WetRejectEntry_Lot FOREIGN KEY (ProductionLotID) REFERENCES omagmes.ProductionLot(id),
            CONSTRAINT FK_WetRejectEntry_Reason FOREIGN KEY (RejectReasonID) REFERENCES omagmes.WetRejectReason(id),
            CONSTRAINT CK_WetRejectEntry_Quantity CHECK (Quantity >= 0)
        );
    END;
    IF NOT EXISTS (
        SELECT 1 FROM sys.default_constraints d
        JOIN sys.columns c ON c.object_id=d.parent_object_id AND c.column_id=d.parent_column_id
        WHERE d.parent_object_id=OBJECT_ID(N'omagmes.WetRejectEntry') AND c.name=N'IsDeleted'
    )
        ALTER TABLE omagmes.WetRejectEntry ADD CONSTRAINT DF_WetRejectEntry_IsDeleted_007 DEFAULT (0) FOR IsDeleted;
    IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id=OBJECT_ID(N'omagmes.WetRejectEntry') AND name=N'IX_WetRejectEntry_Lot_RecordedAt')
        CREATE INDEX IX_WetRejectEntry_Lot_RecordedAt ON omagmes.WetRejectEntry(ProductionLotID,RecordedAt DESC,id DESC);

    /* Mould master/history schema only; no Mould mutation workflow is enabled here. */
    IF OBJECT_ID(N'omagmes.Mould', N'U') IS NULL
    BEGIN
        CREATE TABLE omagmes.Mould (
            id bigint IDENTITY(1,1) NOT NULL CONSTRAINT PK_Mould PRIMARY KEY,
            Rectime datetime NOT NULL CONSTRAINT DF_Mould_Rectime DEFAULT (GETDATE()),
            ProductID bigint NOT NULL,
            MouldCode nvarchar(100) COLLATE Latin1_General_100_BIN2 NOT NULL,
            MouldName nvarchar(200) NOT NULL,
            CurrentAgeDrops bigint NOT NULL CONSTRAINT DF_Mould_CurrentAgeDrops DEFAULT (0),
            LifetimeAgeDrops bigint NOT NULL CONSTRAINT DF_Mould_LifetimeAgeDrops DEFAULT (0),
            StatusCode varchar(20) NOT NULL CONSTRAINT DF_Mould_StatusCode DEFAULT ('ACTIVE'),
            IsActive bit NOT NULL CONSTRAINT DF_Mould_IsActive DEFAULT (1),
            CONSTRAINT FK_Mould_Product FOREIGN KEY (ProductID) REFERENCES omagmes.Product(id),
            CONSTRAINT UQ_Mould_MouldCode UNIQUE (MouldCode),
            CONSTRAINT CK_Mould_Ages CHECK (CurrentAgeDrops >= 0 AND LifetimeAgeDrops >= CurrentAgeDrops),
            CONSTRAINT CK_Mould_Status CHECK (StatusCode IN ('ACTIVE','RECONDITION','RETIRED'))
        );
    END;
    IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id=OBJECT_ID(N'omagmes.Mould') AND name=N'IX_Mould_Product_Status')
        CREATE INDEX IX_Mould_Product_Status ON omagmes.Mould(ProductID,StatusCode,IsActive);
    IF OBJECT_ID(N'omagmes.MouldHistory', N'U') IS NULL
    BEGIN
        CREATE TABLE omagmes.MouldHistory (
            id bigint IDENTITY(1,1) NOT NULL CONSTRAINT PK_MouldHistory PRIMARY KEY,
            Rectime datetime NOT NULL CONSTRAINT DF_MouldHistory_Rectime DEFAULT (GETDATE()),
            MouldID bigint NOT NULL,
            ActionCode varchar(30) NOT NULL,
            ChangedBy nvarchar(200) NOT NULL,
            ChangedAt datetimeoffset(0) NOT NULL,
            ChangeReason nvarchar(500) NOT NULL,
            PreviousStateJson nvarchar(max) NULL,
            NewStateJson nvarchar(max) NULL,
            CONSTRAINT FK_MouldHistory_Mould FOREIGN KEY (MouldID) REFERENCES omagmes.Mould(id),
            CONSTRAINT CK_MouldHistory_Reason CHECK (LEN(LTRIM(RTRIM(ChangeReason))) > 0)
        );
    END;
    IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id=OBJECT_ID(N'omagmes.MouldHistory') AND name=N'IX_MouldHistory_Mould_ChangedAt')
        CREATE INDEX IX_MouldHistory_Mould_ChangedAt ON omagmes.MouldHistory(MouldID,ChangedAt DESC,id DESC);

    /* Fail rather than report readiness if an existing partial object is incompatible. */
    IF EXISTS (
        SELECT required.TableName, required.ColumnName
        FROM (VALUES
            (N'ProductionEntryChangeHistory',N'id'),(N'ProductionEntryChangeHistory',N'ProductionEntryID'),
            (N'ProductionEntryChangeHistory',N'ChangeType'),(N'ProductionEntryChangeHistory',N'ChangedBy'),
            (N'ProductionEntryChangeHistory',N'ChangedAt'),(N'ProductionEntryChangeHistory',N'ChangeReason'),
            (N'ProductionEntryChangeHistory',N'BeforeStateJson'),(N'ProductionEntryChangeHistory',N'AfterStateJson'),
            (N'WetRejectReason',N'id'),(N'WetRejectReason',N'ReasonCode'),(N'WetRejectReason',N'ReasonName'),(N'WetRejectReason',N'IsActive'),
            (N'WetRejectEntry',N'id'),(N'WetRejectEntry',N'ProductionLotID'),(N'WetRejectEntry',N'RejectReasonID'),
            (N'WetRejectEntry',N'Quantity'),(N'WetRejectEntry',N'RecordedAt'),(N'WetRejectEntry',N'EnteredBy'),(N'WetRejectEntry',N'OperatorNote'),(N'WetRejectEntry',N'IsDeleted'),
            (N'Mould',N'id'),(N'Mould',N'ProductID'),(N'Mould',N'MouldCode'),(N'Mould',N'MouldName'),
            (N'Mould',N'CurrentAgeDrops'),(N'Mould',N'LifetimeAgeDrops'),(N'Mould',N'StatusCode'),(N'Mould',N'IsActive'),
            (N'MouldHistory',N'id'),(N'MouldHistory',N'MouldID'),(N'MouldHistory',N'ActionCode'),(N'MouldHistory',N'ChangedBy'),
            (N'MouldHistory',N'ChangedAt'),(N'MouldHistory',N'ChangeReason'),(N'MouldHistory',N'PreviousStateJson'),(N'MouldHistory',N'NewStateJson')
        ) required(TableName,ColumnName)
        LEFT JOIN sys.tables t ON t.schema_id=SCHEMA_ID(N'omagmes') AND t.name=required.TableName
        LEFT JOIN sys.columns c ON c.object_id=t.object_id AND c.name=required.ColumnName
        WHERE c.column_id IS NULL
    )
        THROW 53728, 'A required Migration 007 table/column is missing or incompatible; inspect before runtime use.', 1;

    IF EXISTS (
        SELECT 1
        FROM (VALUES
            (N'ProductionEntryChangeHistory',N'id',N'bigint',8,0),
            (N'ProductionEntryChangeHistory',N'Rectime',N'datetime',8,0),
            (N'ProductionEntryChangeHistory',N'ProductionEntryID',N'bigint',8,0),
            (N'ProductionEntryChangeHistory',N'ChangeType',N'varchar',10,0),
            (N'ProductionEntryChangeHistory',N'ChangedBy',N'nvarchar',400,0),
            (N'ProductionEntryChangeHistory',N'ChangedAt',N'datetimeoffset',8,0),
            (N'ProductionEntryChangeHistory',N'ChangeReason',N'nvarchar',1000,0),
            (N'ProductionEntryChangeHistory',N'BeforeStateJson',N'nvarchar',-1,1),
            (N'ProductionEntryChangeHistory',N'AfterStateJson',N'nvarchar',-1,1),
            (N'WetRejectReason',N'id',N'bigint',8,0),
            (N'WetRejectReason',N'Rectime',N'datetime',8,0),
            (N'WetRejectReason',N'ReasonCode',N'nvarchar',80,0),
            (N'WetRejectReason',N'ReasonName',N'nvarchar',400,0),
            (N'WetRejectReason',N'IsActive',N'bit',1,0),
            (N'WetRejectEntry',N'id',N'bigint',8,0),
            (N'WetRejectEntry',N'Rectime',N'datetime',8,0),
            (N'WetRejectEntry',N'ProductionLotID',N'bigint',8,0),
            (N'WetRejectEntry',N'RejectReasonID',N'bigint',8,0),
            (N'WetRejectEntry',N'Quantity',N'bigint',8,0),
            (N'WetRejectEntry',N'RecordedAt',N'datetimeoffset',8,0),
            (N'WetRejectEntry',N'EnteredBy',N'nvarchar',400,0),
            (N'WetRejectEntry',N'OperatorNote',N'nvarchar',2000,1),
            (N'WetRejectEntry',N'IsDeleted',N'bit',1,0),
            (N'Mould',N'id',N'bigint',8,0),
            (N'Mould',N'Rectime',N'datetime',8,0),
            (N'Mould',N'ProductID',N'bigint',8,0),
            (N'Mould',N'MouldCode',N'nvarchar',200,0),
            (N'Mould',N'MouldName',N'nvarchar',400,0),
            (N'Mould',N'CurrentAgeDrops',N'bigint',8,0),
            (N'Mould',N'LifetimeAgeDrops',N'bigint',8,0),
            (N'Mould',N'StatusCode',N'varchar',20,0),
            (N'Mould',N'IsActive',N'bit',1,0),
            (N'MouldHistory',N'id',N'bigint',8,0),
            (N'MouldHistory',N'Rectime',N'datetime',8,0),
            (N'MouldHistory',N'MouldID',N'bigint',8,0),
            (N'MouldHistory',N'ActionCode',N'varchar',30,0),
            (N'MouldHistory',N'ChangedBy',N'nvarchar',400,0),
            (N'MouldHistory',N'ChangedAt',N'datetimeoffset',8,0),
            (N'MouldHistory',N'ChangeReason',N'nvarchar',1000,0),
            (N'MouldHistory',N'PreviousStateJson',N'nvarchar',-1,1),
            (N'MouldHistory',N'NewStateJson',N'nvarchar',-1,1)
        ) expected(TableName,ColumnName,TypeName,MaxLength,IsNullable)
        JOIN sys.tables t ON t.schema_id=SCHEMA_ID(N'omagmes') AND t.name=expected.TableName
        LEFT JOIN sys.columns c ON c.object_id=t.object_id AND c.name=expected.ColumnName
        LEFT JOIN sys.types ty ON ty.user_type_id=c.user_type_id
        WHERE c.column_id IS NULL OR ty.name<>expected.TypeName
           OR c.max_length<>expected.MaxLength OR c.is_nullable<>expected.IsNullable
    )
        THROW 53729, 'An existing Migration 007 table has incompatible column metadata; inspect and reconcile before continuing.', 1;

    IF EXISTS (
        SELECT 1
        FROM (VALUES
            (N'ProductionEntryChangeHistory',N'FK_ProductionEntryChangeHistory_Entry'),
            (N'ProductionEntryChangeHistory',N'CK_ProductionEntryChangeHistory_Type'),
            (N'ProductionEntryChangeHistory',N'CK_ProductionEntryChangeHistory_Reason'),
            (N'WetRejectReason',N'UQ_WetRejectReason_ReasonCode'),
            (N'WetRejectReason',N'CK_WetRejectReason_Code'),
            (N'WetRejectReason',N'CK_WetRejectReason_Name'),
            (N'WetRejectEntry',N'FK_WetRejectEntry_Lot'),
            (N'WetRejectEntry',N'FK_WetRejectEntry_Reason'),
            (N'WetRejectEntry',N'CK_WetRejectEntry_Quantity'),
            (N'Mould',N'FK_Mould_Product'),
            (N'Mould',N'UQ_Mould_MouldCode'),
            (N'Mould',N'CK_Mould_Ages'),
            (N'Mould',N'CK_Mould_Status'),
            (N'MouldHistory',N'FK_MouldHistory_Mould'),
            (N'MouldHistory',N'CK_MouldHistory_Reason')
        ) expected(TableName,ConstraintName)
        JOIN sys.tables t ON t.schema_id=SCHEMA_ID(N'omagmes') AND t.name=expected.TableName
        LEFT JOIN sys.objects o ON o.parent_object_id=t.object_id AND o.name=expected.ConstraintName
        WHERE o.object_id IS NULL
    )
        THROW 53730, 'A required Migration 007 constraint is missing; inspect the partial schema before runtime use.', 1;
    IF EXISTS (
        SELECT 1
        FROM (VALUES
            (N'ProductionEntry',N'IsDeleted'),
            (N'ProductionEntry',N'OperatorConfirmed'),
            (N'CuringInputEntry',N'OperatorConfirmed'),
            (N'ProductionEntryChangeHistory',N'Rectime'),
            (N'WetRejectReason',N'Rectime'),
            (N'WetRejectReason',N'IsActive'),
            (N'WetRejectEntry',N'Rectime'),
            (N'WetRejectEntry',N'IsDeleted'),
            (N'Mould',N'Rectime'),
            (N'Mould',N'CurrentAgeDrops'),
            (N'Mould',N'LifetimeAgeDrops'),
            (N'Mould',N'StatusCode'),
            (N'Mould',N'IsActive'),
            (N'MouldHistory',N'Rectime')
        ) expected(TableName,ColumnName)
        JOIN sys.tables t ON t.schema_id=SCHEMA_ID(N'omagmes') AND t.name=expected.TableName
        JOIN sys.columns c ON c.object_id=t.object_id AND c.name=expected.ColumnName
        LEFT JOIN sys.default_constraints d ON d.parent_object_id=t.object_id AND d.parent_column_id=c.column_id
        WHERE d.object_id IS NULL
    )
        THROW 53731, 'A required Migration 007 default is missing.', 1;
    IF EXISTS (
        SELECT 1
        FROM (VALUES
            (N'ProductionEntryChangeHistory'),(N'WetRejectReason'),(N'WetRejectEntry'),
            (N'Mould'),(N'MouldHistory')
        ) expected(TableName)
        JOIN sys.tables t ON t.schema_id=SCHEMA_ID(N'omagmes') AND t.name=expected.TableName
        JOIN sys.columns c ON c.object_id=t.object_id AND c.name=N'id'
        WHERE c.is_identity<>1 OR NOT EXISTS (
            SELECT 1 FROM sys.indexes i
            JOIN sys.index_columns ic ON ic.object_id=i.object_id AND ic.index_id=i.index_id
            WHERE i.object_id=t.object_id AND i.is_primary_key=1
              AND ic.column_id=c.column_id AND ic.key_ordinal=1
        )
    )
        THROW 53732, 'Every new table must have an IDENTITY primary key on id.', 1;
    IF NOT EXISTS (
        SELECT 1 FROM sys.default_constraints d
        JOIN sys.columns c ON c.object_id=d.parent_object_id AND c.column_id=d.parent_column_id
        WHERE d.parent_object_id=OBJECT_ID(N'omagmes.WetRejectEntry') AND c.name=N'IsDeleted'
    )
        THROW 53733, 'WetRejectEntry.IsDeleted must default to false.', 1;

    /* Scope DML. OMAG_MES must not belong to db_owner/db_datawriter or another writer role. */
    REVOKE INSERT, UPDATE, DELETE ON SCHEMA::omagmes FROM OMAG_MES;
    DECLARE @RevokeSql nvarchar(max) = N'';
    SELECT @RevokeSql = @RevokeSql + N'REVOKE INSERT, UPDATE, DELETE ON OBJECT::omagmes.' + QUOTENAME(t.name) + N' FROM OMAG_MES;' + CHAR(10)
    FROM sys.tables t WHERE t.schema_id=SCHEMA_ID(N'omagmes');
    IF @RevokeSql <> N'' EXEC sys.sp_executesql @RevokeSql;

    GRANT SELECT ON OBJECT::omagmes.Product TO OMAG_MES;
    GRANT SELECT ON OBJECT::omagmes.ProductStandardRevision TO OMAG_MES;
    GRANT SELECT, INSERT, UPDATE ON OBJECT::omagmes.ProductionRun TO OMAG_MES;
    GRANT SELECT, INSERT, UPDATE ON OBJECT::omagmes.ProductionLot TO OMAG_MES;
    GRANT SELECT, INSERT, UPDATE ON OBJECT::omagmes.LotNumberSequence TO OMAG_MES;
    GRANT SELECT, INSERT ON OBJECT::omagmes.AutoLotResetReview TO OMAG_MES;
    GRANT SELECT, INSERT ON OBJECT::omagmes.ProductionLotNameHistory TO OMAG_MES;
    GRANT SELECT, INSERT, UPDATE ON OBJECT::omagmes.ProductionEntry TO OMAG_MES;
    GRANT SELECT, INSERT ON OBJECT::omagmes.ProductionEntryCorrection TO OMAG_MES;
    GRANT SELECT, INSERT ON OBJECT::omagmes.ProductionEntryChangeHistory TO OMAG_MES;
    GRANT SELECT, INSERT ON OBJECT::omagmes.CuringInputEntry TO OMAG_MES;
    GRANT SELECT ON OBJECT::omagmes.WetRejectReason TO OMAG_MES;
    GRANT SELECT, INSERT ON OBJECT::omagmes.WetRejectEntry TO OMAG_MES;
    GRANT SELECT, INSERT ON OBJECT::omagmes.DepalletEvent TO OMAG_MES;
    GRANT SELECT, INSERT ON OBJECT::omagmes.Dispatch TO OMAG_MES;
    GRANT SELECT, INSERT ON OBJECT::omagmes.DispatchLine TO OMAG_MES;
    GRANT SELECT ON OBJECT::omagmes.Mould TO OMAG_MES;
    GRANT SELECT ON OBJECT::omagmes.MouldHistory TO OMAG_MES;

    COMMIT TRANSACTION;
END TRY
BEGIN CATCH
    IF XACT_STATE() <> 0 ROLLBACK TRANSACTION;
    THROW;
END CATCH;

/* Post-deployment review output. No user/role/permission changes run outside the transaction. */
SELECT t.name AS TableName, COUNT(c.column_id) AS ColumnCount
FROM sys.tables t JOIN sys.schemas s ON s.schema_id=t.schema_id
LEFT JOIN sys.columns c ON c.object_id=t.object_id
WHERE s.name=N'omagmes' AND t.name IN
 (N'ProductionEntryChangeHistory',N'WetRejectReason',N'WetRejectEntry',N'Mould',N'MouldHistory')
GROUP BY t.name ORDER BY t.name;
SELECT HAS_PERMS_BY_NAME(N'omagmes.ProductionEntry',N'OBJECT',N'INSERT') AS CanInsertProduction,
       HAS_PERMS_BY_NAME(N'omagmes.ProductionEntry',N'OBJECT',N'UPDATE') AS CanEditProduction,
       HAS_PERMS_BY_NAME(N'omagmes.ProductionEntryChangeHistory',N'OBJECT',N'INSERT') AS CanWriteAudit,
       HAS_PERMS_BY_NAME(N'omagmes',N'SCHEMA',N'ALTER') AS CanAlterSchema,
       IS_SRVROLEMEMBER(N'sysadmin') AS IsSysadmin;
