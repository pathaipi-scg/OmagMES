/*
DBA REVIEW - PRODUCT MASTER IMPORT - MANUAL SSMS EXECUTION ONLY.
Standalone import of the approved 825 Product records from:
  Master/Omag_Product_Master.xlsx | Std Data | columns A:C only
Workbook SHA-256: 85a2ce34ab3bf63c38d3259591d4fb73385a8251817c07e799f2283ecbdfbe68

Each source value is embedded as an NVARCHAR Unicode literal. Product Standard
and all other workbook columns are excluded. Review this script and source
fingerprint before execution. No script execution is performed during generation.
*/
SET NOCOUNT ON;
SET XACT_ABORT ON;

DECLARE @ExpectedImportCount int = 825;
DECLARE @ExpectedDatabase sysname = N'OMAG';
DECLARE @ExpectedServerName nvarchar(128) = N'SCGLS-NK\SQLEXPRESS';
DECLARE @ExpectedInstanceName nvarchar(128) = N'SQLEXPRESS';
DECLARE @SourceSha256 char(64) = '85a2ce34ab3bf63c38d3259591d4fb73385a8251817c07e799f2283ecbdfbe68';
DECLARE @ExecutionOriginalLogin sysname = ORIGINAL_LOGIN();
DECLARE @ExecutionSqlLogin sysname = SUSER_SNAME();
DECLARE @ExecutionDatabaseUser sysname = USER_NAME();
DECLARE @ProductObjectID int;
DECLARE @ExistingProductCount bigint;
DECLARE @ProductStandardRevisionCount bigint;
DECLARE @InsertedCount int = 0;
DECLARE @FinalProductCount bigint;
DECLARE @FinalProductStandardRevisionCount bigint;

BEGIN TRY
    IF @@TRANCOUNT <> 0
        THROW 53900, 'Run this import in a session without an ambient transaction.', 1;
    IF DB_NAME() <> @ExpectedDatabase
        THROW 53901, 'Import stopped: database does not match OMAG.', 1;
    IF ISNULL(CONVERT(nvarchar(128), @@SERVERNAME), N'') <> @ExpectedServerName
        THROW 53902, 'Import stopped: @@SERVERNAME does not match the approved target.', 1;
    IF ISNULL(CONVERT(nvarchar(128), SERVERPROPERTY(N'ServerName')), N'') <> @ExpectedServerName
        THROW 53903, 'Import stopped: SQL Server instance identity does not match the approved target.', 1;
    IF ISNULL(CONVERT(nvarchar(128), SERVERPROPERTY(N'InstanceName')), N'') <> @ExpectedInstanceName
        THROW 53904, 'Import stopped: SQL Server instance name does not match the approved target.', 1;
    IF SCHEMA_ID(N'omagmes') IS NULL
        THROW 53905, 'Import stopped: schema omagmes does not exist.', 1;
    IF LOWER(ISNULL(@ExecutionOriginalLogin, N'')) = N'omag_mes'
       OR LOWER(ISNULL(@ExecutionSqlLogin, N'')) = N'omag_mes'
        THROW 53906, 'Import stopped: OMAG_MES is the application service login; execute only with the separately authorized DBA account.', 1;

    SET @ProductObjectID = OBJECT_ID(N'omagmes.Product', N'U');
    IF @ProductObjectID IS NULL
        THROW 53907, 'Import stopped: table omagmes.Product does not exist.', 1;
    IF ISNULL(HAS_PERMS_BY_NAME(N'omagmes.Product', N'OBJECT', N'INSERT'), 0) <> 1
        THROW 53908, 'Import stopped: execution account lacks INSERT on omagmes.Product.', 1;
    IF ISNULL(HAS_PERMS_BY_NAME(N'omagmes.Product', N'OBJECT', N'SELECT'), 0) <> 1
        THROW 53909, 'Import stopped: execution account lacks SELECT on omagmes.Product.', 1;
    IF OBJECT_ID(N'omagmes.ProductStandardRevision', N'U') IS NULL
        THROW 53910, 'Import stopped: table omagmes.ProductStandardRevision is missing.', 1;
    IF ISNULL(HAS_PERMS_BY_NAME(N'omagmes.ProductStandardRevision', N'OBJECT', N'SELECT'), 0) <> 1
        THROW 53911, 'Import stopped: execution account lacks SELECT on ProductStandardRevision.', 1;

    /* Verify every column used or relied upon, including database-generated values. */
    IF NOT EXISTS (
        SELECT 1 FROM sys.columns c JOIN sys.types t ON t.user_type_id = c.user_type_id
        WHERE c.object_id = @ProductObjectID AND c.name = N'id'
          AND t.name = N'bigint' AND c.is_identity = 1 AND c.is_nullable = 0 AND c.is_computed = 0
    )
        THROW 53912, 'Import stopped: Product.id is not a non-null bigint IDENTITY.', 1;
    IF NOT EXISTS (
        SELECT 1 FROM sys.columns c JOIN sys.types t ON t.user_type_id = c.user_type_id
        JOIN sys.default_constraints dc ON dc.parent_object_id = c.object_id AND dc.parent_column_id = c.column_id
        WHERE c.object_id = @ProductObjectID AND c.name = N'Rectime'
          AND t.name = N'datetime' AND c.is_nullable = 0 AND c.is_computed = 0
          AND LOWER(REPLACE(REPLACE(REPLACE(REPLACE(dc.definition, N'(', N''), N')', N''), N' ', N''), NCHAR(9), N'')) = N'getdate'
    )
        THROW 53913, 'Import stopped: Product.Rectime lacks datetime NOT NULL DEFAULT GETDATE().', 1;
    IF NOT EXISTS (
        SELECT 1 FROM sys.columns c JOIN sys.types t ON t.user_type_id = c.user_type_id
        WHERE c.object_id = @ProductObjectID AND c.name = N'ProductCode'
          AND t.name = N'nvarchar' AND c.max_length = 200 AND c.is_nullable = 0 AND c.is_computed = 0
          AND c.collation_name = N'Latin1_General_100_BIN2'
    )
        THROW 53914, 'Import stopped: ProductCode is not nvarchar(100) NOT NULL with binary collation.', 1;
    IF NOT EXISTS (
        SELECT 1 FROM sys.columns c JOIN sys.types t ON t.user_type_id = c.user_type_id
        WHERE c.object_id = @ProductObjectID AND c.name = N'ProductName'
          AND t.name = N'nvarchar' AND c.max_length = 400 AND c.is_nullable = 0 AND c.is_computed = 0
    )
        THROW 53915, 'Import stopped: ProductName is not nvarchar(200) NOT NULL.', 1;
    IF NOT EXISTS (
        SELECT 1 FROM sys.columns c JOIN sys.types t ON t.user_type_id = c.user_type_id
        WHERE c.object_id = @ProductObjectID AND c.name = N'ProductNameThai'
          AND t.name = N'nvarchar' AND c.max_length = 400 AND c.is_nullable = 1 AND c.is_computed = 0
          AND c.collation_name = N'Thai_CI_AS'
    )
        THROW 53916, 'Import stopped: ProductNameThai is not nvarchar(200) NULL Thai_CI_AS.', 1;
    IF NOT EXISTS (
        SELECT 1 FROM sys.columns c JOIN sys.types t ON t.user_type_id = c.user_type_id
        WHERE c.object_id = @ProductObjectID AND c.name = N'ProductFamily'
          AND t.name = N'nvarchar' AND c.max_length = 200 AND c.is_nullable = 1 AND c.is_computed = 0
    )
        THROW 53917, 'Import stopped: ProductFamily is not nullable nvarchar(100).', 1;
    IF NOT EXISTS (
        SELECT 1 FROM sys.columns c JOIN sys.types t ON t.user_type_id = c.user_type_id
        JOIN sys.default_constraints dc ON dc.parent_object_id = c.object_id AND dc.parent_column_id = c.column_id
        WHERE c.object_id = @ProductObjectID AND c.name = N'IsActive'
          AND t.name = N'bit' AND c.is_nullable = 0 AND c.is_computed = 0
          AND REPLACE(REPLACE(REPLACE(REPLACE(LOWER(dc.definition), N'(', N''), N')', N''), N' ', N''), NCHAR(9), N'') = N'1'
    )
        THROW 53918, 'Import stopped: Product.IsActive is not bit NOT NULL DEFAULT 1.', 1;

    /* Require the deployed one-column unique ProductCode constraint/index. */
    IF NOT EXISTS (
        SELECT 1
        FROM sys.key_constraints kc
        JOIN sys.indexes i ON i.object_id = kc.parent_object_id AND i.index_id = kc.unique_index_id
        WHERE kc.parent_object_id = @ProductObjectID
                    AND kc.name = N'UQ_Product_ProductCode' AND kc.type = N'UQ'
                    AND i.is_unique = 1 AND i.is_unique_constraint = 1
                    AND i.is_disabled = 0 AND i.has_filter = 0 AND i.filter_definition IS NULL
          AND (SELECT COUNT(*) FROM sys.index_columns kic
               WHERE kic.object_id = i.object_id AND kic.index_id = i.index_id AND kic.key_ordinal > 0) = 1
          AND EXISTS (SELECT 1 FROM sys.index_columns kic JOIN sys.columns kc2
                      ON kc2.object_id = kic.object_id AND kc2.column_id = kic.column_id
                      WHERE kic.object_id = i.object_id AND kic.index_id = i.index_id
                        AND kic.key_ordinal = 1 AND kc2.name = N'ProductCode')
    )
        THROW 53919, 'Import stopped: unique ProductCode constraint/index is missing or incompatible.', 1;
    IF NOT EXISTS (SELECT 1 FROM sys.check_constraints WHERE parent_object_id = @ProductObjectID AND name = N'CK_Product_ProductCode' AND is_disabled = 0 AND is_not_trusted = 0)
        THROW 53920, 'Import stopped: ProductCode nonblank check is missing, disabled, or untrusted.', 1;
    IF NOT EXISTS (SELECT 1 FROM sys.check_constraints WHERE parent_object_id = @ProductObjectID AND name = N'CK_Product_ProductName' AND is_disabled = 0 AND is_not_trusted = 0)
        THROW 53921, 'Import stopped: ProductName nonblank check is missing, disabled, or untrusted.', 1;
    IF EXISTS (SELECT 1 FROM sys.triggers WHERE parent_id = @ProductObjectID AND is_disabled = 0)
        THROW 53922, 'Import stopped: enabled Product trigger could modify unrelated data.', 1;

    DECLARE @Source TABLE (
        SourceRow int NOT NULL PRIMARY KEY,
        ProductCode nvarchar(100) COLLATE Latin1_General_100_BIN2 NOT NULL UNIQUE,
        ProductName nvarchar(200) COLLATE Thai_CI_AS NOT NULL,
        ProductNameThai nvarchar(200) COLLATE Thai_CI_AS NOT NULL
    );
    INSERT INTO @Source (SourceRow, ProductCode, ProductName, ProductNameThai)
    VALUES
    (4, N'ZCC010010060011du', N'UNI PAVE 6 CM. - GREY DU', N'คดกริช 6 ซม. สีเทา DU'),
    (5, N'ZCC010010060011FT', N'UNI PAVE 6 CM. - GREY', N'คดกริช 6 ซม. สีเทา FT'),
    (6, N'ZCC010010060011FTC', N'UNI PAVE 6 CM. - GREY', N'คดกริช 6 ซม. สีเทา FTC'),
    (7, N'ZCC010010060021FTC', N'UNI PAVE 6 CM. - RED', N'คดกริช 6 ซม. สีแดงFTC'),
    (8, N'ZCC010010060011', N'UNI PAVE 6 CM. - GREY', N'คดกริช 6 ซม. สีเทา '),
    (9, N'ZCC010010060011A', N'UNI 6 CM. (Suksawat RingRoad) - Grey', N'คดกริช 6 ซม. สีเทา (วงแหวนสุขสวัสดิ์)'),
    (10, N'ZCC010010060011B', N'UNI PAVE 6 CM. - GREY (Project sand)', N'คดกริช 6 ซม. สีเทา (โครงการ ทรายหยาบ)'),
    (11, N'ZCC010010060021du', N'UNI PAVE 6 CM. - RED', N'คดกริช 6 ซม. สีแดงDU'),
    (12, N'ZCC010010060021FT', N'UNI PAVE 6 CM. - RED', N'คดกริช 6 ซม. สีแดงFT'),
    (13, N'ZCC010010060021', N'UNI PAVE 6 CM. - RED', N'คดกริช 6 ซม. สีแดง'),
    (14, N'ZCC010010060031du', N'UNI PAVE 6 CM. - ORANGEdu', N'คดกริช 6 ซม. สีส้มdu'),
    (15, N'ZCC010010060031', N'UNI PAVE 6 CM. - ORANGE', N'คดกริช 6 ซม. สีส้ม'),
    (16, N'ZCC010010060041du', N'UNI PAVE 6 CM. - YELLOWdu', N'คดกริช 6 ซม. สีเหลืองDU'),
    (17, N'ZCC010010060041', N'UNI PAVE 6 CM. - YELLOW', N'คดกริช 6 ซม. สีเหลือง'),
    (18, N'ZCC010010060051', N'UNI PAVE 6 CM. - BROWN', N'คดกริช 6 ซม. สีน้ำตาล'),
    (19, N'ZCC010010060052', N'UNI PAVE 6 CM. - RED BROWN', N'คดกริช 6 ซม. สีน้ำตาลเข้ม'),
    (20, N'ZCC010010060061', N'UNI PAVE 6 CM. - BLACK', N'คดกริช 6 ซม. สีดำ'),
    (21, N'ZCC010010060071', N'UNI PAVE 6 CM. - BLUE', N'คดกริช 6 ซม. สีฟ้า (ใหม่)'),
    (22, N'ZCC010010060081', N'UNI PAVE 6 CM. - GREEN', N'คดกริช 6 ซม. สีเขียว'),
    (23, N'ZCC010010080011', N'UNI 8 CM - GREY', N'คดกริช 8 ซม. สีเทา '),
    (24, N'ZCC010020080011', N'UNI(HS) 8 CM - GREY', N'คดกริช 8 ซม. สีเทา (HS)'),
    (25, N'ZCC010020080021', N'UNI(HS) 8 CM - RED', N'คดกริช 8 ซม. สีแดง (HS)'),
    (26, N'ZCC010020080042', N'UNI(HS) 8 CM - YELLOW', N'คดกริช 8 ซม. สีเหลือง (HS)'),
    (27, N'ZCC010010100011', N'UNI PAVE 10 CM - GREY', N'คดกริช 10 ซม. สีเทา'),
    (28, N'ZCC011240100011', N'UNI NO FACING 10 CM.-GREY', N'คดกริช 10 ซม. สีเทา (ไม่มีผิวหน้า)'),
    (29, N'ZCC010010100021', N'UNI PAVE 10 CM - RED', N'คดกริช 10 ซม. สีแดง'),
    (30, N'ZCC010010100031', N'UNI PAVE 10 CM - ORANGE', N'คดกริช 10 ซม. สีส้ม'),
    (31, N'ZCC010010100041', N'UNI PAVE 10 CM - YELLOW', N'คดกริช 10 ซม. สีเหลือง'),
    (32, N'ZCC010010100051', N'UNI PAVE 10 CM -  BROWN', N'คดกริช 10 ซม. สีน้ำตาล'),
    (33, N'ZCC010010100061', N'UNI PAVE 10 CM - BLACK', N'คดกริช 10 ซม. สีดำ'),
    (34, N'ZCC010010100071', N'UNI PAVE 10 CM - BLUE', N'คดกริช 10 ซม. สีฟ้า (ใหม่)'),
    (35, N'ZCC010020100011', N'UNI PAVE(HS) 10 CM - GREY ', N'คดกริช 10 ซม. สีเทา (HS) '),
    (36, N'ZCC010010120011', N'UNI PAVE 12 CM - GREY', N'คดกริช 12 ซม. สีเทา'),
    (37, N'ZCC010010120021', N'UNI PAVE 12 CM - RED', N'คดกริช 12 ซม. สีแดง'),
    (38, N'ZCC010020120011', N'UNI(HS) 12 CM - GREY', N'คดกริช 12 ซม. สีเทา (HS) '),
    (39, N'ZCC010020120011-1', N'UNI(HS) 12 CM - GREY (Test)', N'คดกริช 12 ซม. สีเทา (HS) (ทดสอบ)'),
    (40, N'ZCC010020120011A', N'UNI 12 CM. (Klong Tuey Port) - Grey', N'คดกริช 12 ซม. สีเทา (ท่าเรือคลองเตย) '),
    (41, N'ZCC010080060081-1', N'CUBE 6CM - GREEN', N'จัตุรัส 6 ซม. สีเขียว'),
    (42, N'ZCC010080060061-1', N'CUBE 6CM - BLACK', N'จัตุรัส 6 ซม. สีดำ '),
    (43, N'ZCC010080060021-1', N'CUBE 6 CM - RED', N'จัตุรัส 6 ซม. สีแดง'),
    (44, N'ZCC010080060011-1', N'CUBE 6 CM - GREY', N'จัตุรัส 6 ซม. สีเทา'),
    (45, N'ZCC010080060051-1', N'CUBE 6CM - BROWN', N'จัตุรัส 6 ซม. สีน้ำตาล'),
    (46, N'ZCC010080060071-1', N'CUBE 6 CM - BLUE', N'จัตุรัส 6 ซม. สีฟ้า (ใหม่)'),
    (47, N'ZCC010080060031-1', N'CUBE 6CM - ORANGE', N'จัตุรัส 6 ซม. สีส้ม'),
    (48, N'ZCC010080060041-1', N'CUBE 6 CM - YELLOW', N'จัตุรัส 6 ซม. สีเหลือง'),
    (49, N'ZCC010080060081', N'CUBE(PACK) 6CM - GREEN', N'จัตุรัส 6 ซม. (ห่อ) สีเขียว'),
    (50, N'ZCC010080060061', N'CUBE(PACK) 6CM - BLACK', N'จัตุรัส 6 ซม. (ห่อ) สีดำ '),
    (51, N'ZCC010080060021', N'CUBE(PACK) 6 CM - RED', N'จัตุรัส 6 ซม. (ห่อ) สีแดง'),
    (52, N'ZCC010080060011', N'CUBE(PACK) 6 CM - GREY', N'จัตุรัส 6 ซม. (ห่อ) สีเทา'),
    (53, N'ZCC010080060051', N'CUBE(PACK) 6CM - BROWN', N'จัตุรัส 6 ซม. (ห่อ) สีน้ำตาล'),
    (54, N'ZCC010080060071', N'CUBE(PACK) 6CM - BLUE', N'จัตุรัส 6 ซม. (ห่อ) สีฟ้า (ใหม่)'),
    (55, N'ZCC010080060031', N'CUBE(PACK) 6CM - ORANGE', N'จัตุรัส 6 ซม. (ห่อ) สีส้ม'),
    (56, N'ZCC010080060041', N'CUBE(PACK) 6 CM - YELLOW', N'จัตุรัส 6 ซม. (ห่อ) สีเหลือง'),
    (57, N'ZCC010060060011', N'OCTA 6 CM -  GREY', N'อัฐศิลา 6 ซม. สีเทา'),
    (58, N'ZCC010060060021', N'OCTA 6 CM - RED', N'อัฐศิลา 6 ซม. สีแดง'),
    (59, N'ZCC010060060031', N'OCTA 6 CM -  ORANGE', N'อัฐศิลา 6 ซม. สีส้ม'),
    (60, N'ZCC010060060041', N'OCTA 6 CM -YELLOW', N'อัฐศิลา 6 ซม. สีเหลือง'),
    (61, N'ZCC010060060051', N'OCTA 6 CM -   BROWN', N'อัฐศิลา 6 ซม. สีน้ำตาล'),
    (62, N'ZCC010060060061', N'OCTA 6 CM -  BLACK', N'อัฐศิลา 6 ซม. สีดำ'),
    (63, N'ZCC010060060071', N'OCTA 6 CM -   BLUE', N'อัฐศิลา 6 ซม. สีฟ้า'),
    (64, N'ZCC010060060081', N'OCTA 6 CM -  GREEN', N'อัฐศิลา 6 ซม. สีเขียว'),
    (65, N'ZCC010090060011', N'RHOMBIC 6 CM -  GREY', N'ศิลาหกเหลี่ยม 6 ซม. สีเทา'),
    (66, N'ZCC010090060021', N'RHOMBIC 6 CM -   RED', N'ศิลาหกเหลี่ยม 6 ซม. สีแดง'),
    (67, N'ZCC010090060031', N'RHOMBIC 6 CM -  ORANGE', N'ศิลาหกเหลี่ยม 6 ซม. สีส้ม'),
    (68, N'ZCC010090060051', N'RHOMBIC 6 CM -   BROWN', N'ศิลาหกเหลี่ยม 6 ซม. สีน้ำตาล'),
    (69, N'ZCC010090060061', N'RHOMBIC 6 CM -  BLACK', N'ศิลาหกเหลี่ยม 6 ซม. สีดำ'),
    (70, N'ZCC010090060071', N'RHOMBIC 6 CM -  BLUE', N'ศิลาหกเหลี่ยม 6 ซม. สีฟ้า (ใหม่)'),
    (71, N'ZCC010090060081', N'RHOMBIC 6 CM -   GREEN', N'ศิลาหกเหลี่ยม 6 ซม. สีเขียว'),
    (72, N'ZCC010100060011', N'QUADRA 6 CM -  GREY', N'คฑา 6 ซม. สีเทา'),
    (73, N'ZCC010100060021', N'QUADRA 6 CM - RED', N'คฑา 6 ซม. สีแดง'),
    (74, N'ZCC010100060031', N'QUADRA 6 CM -  ORANGE', N'คฑา 6 ซม. สีส้ม'),
    (75, N'ZCC010100060041', N'QUADRA 6 CM -  YELLOW', N'คฑา 6 ซม. สีเหลือง'),
    (76, N'ZCC010100060051', N'QUADRA 6 CM -   BROWN', N'คฑา 6 ซม. สีน้ำตาล'),
    (77, N'ZCC010100060061', N'QUADRA 6 CM -   BLACK', N'คฑา 6 ซม. สีดำ'),
    (78, N'ZCC010100060071', N'QUADRA 6 CM -   BLUE', N'คฑา 6 ซม. สีฟ้า (ใหม่)'),
    (79, N'ZCC010100060081', N'QUADRA 6 CM -  GREEN', N'คฑา 6 ซม. สีเขียว'),
    (80, N'ZCC010110060011', N'ARROW BLOCK 6 CM - GREY', N'ศรศิลา 6 ซม. สีเทา'),
    (81, N'ZCC010110060021', N'ARROW BLOCK 6 CM - RED', N'ศรศิลา 6 ซม. สีแดง'),
    (82, N'ZCC010110060031', N'ARROW BLOCK 6 CM - ORANGE', N'ศรศิลา 6 ซม. สีส้ม'),
    (83, N'ZCC010110060041', N'ARROW BLOCK 6 CM - BROWN', N'ศรศิลา 6 ซม. สีน้ำตาล'),
    (84, N'ZCC010110060061', N'ARROW BLOCK 6 CM - BLACK', N'ศรศิลา 6 ซม. สีดำ'),
    (85, N'ZCC010110060071', N'ARROW BLOCK 6 CM - BLUE', N'ศรศิลา 6 ซม. สีฟ้า (ใหม่)'),
    (86, N'ZCC010110060081', N'ARROW BLOCK 6 CM - GREEN', N'ศรศิลา 6 ซม. สีเขียว'),
    (87, N'ZCC010130060011', N'BEHATON 6 CM -  GREY', N'ตัวไอ 6 ซม. สีเทา'),
    (88, N'ZCC010130060021', N'BEHATON 6 CM -  RED', N'ตัวไอ 6 ซม. สีแดง'),
    (89, N'ZCC010130060031', N'BEHATON 6 CM -  ORANGE', N'ตัวไอ 6 ซม. สีส้ม'),
    (90, N'ZCC010130060041', N'BEHATON 6 CM -  YELLOW', N'ตัวไอ 6 ซม. สีเหลือง'),
    (91, N'ZCC010130060071', N'BEHATON 6 CM -  BLUE', N'ตัวไอ 6 ซม. สีฟ้า'),
    (93, N'ZCC010150060011', N'DYWIDAG 6 CM. - GREY', N'รวงผึ้ง 6 ซม. สีเทา'),
    (94, N'ZCC010150060021', N'DYWIDAG 6 CM. - RED', N'รวงผึ้ง 6 ซม. สีแดง'),
    (95, N'ZCC010150060041', N'DYWIDAG 6 CM. - YELLOW', N'รวงผึ้ง 6 ซม. สีเหลือง'),
    (96, N'ZCC010150060061', N'DYWIDAG 6 CM. - BLACK', N'รวงผึ้ง 6 ซม. สีดำ'),
    (97, N'ZCC010150060081', N'DYWIDAG 6 CM. - GREEN', N'รวงผึ้ง 6 ซม. สีเขียว'),
    (98, N'ZCC010150060514', N'DYWIDAG 6 CM.  PINK', N'รวงผึ้ง 6 ซม. สี PINK'),
    (99, N'ZCC010150060515', N'DYWIDAG 6 CM. - Honey PURPLE', N'รวงผึ้ง 6 ซม. สี Honey PURPLE'),
    (101, N'ZCC010150060517', N'DYWIDAG 6 CM. - Honey BLACK', N'รวงผึ้ง 6 ซม. สี Honey BLACK'),
    (102, N'ZCC010180060011', N'BISHOP HAT 6 CM. GREY', N'ศิลา 5 เหลี่ยม 6 ซม. สีเทา'),
    (103, N'ZCC010180060021', N'BISHOP HAT 6 CM. RED', N'ศิลา 5 เหลี่ยม 6 ซม. สีแดง'),
    (104, N'ZCC010180060031', N'BISHOP HAT 6 CM. ORANGE', N'ศิลา 5 เหลี่ยม 6 ซม. สีส้ม'),
    (105, N'ZCC010180060051', N'BISHOP HAT 6 CM. LIGHT BROWN', N'ศิลา 5 เหลี่ยม 6 ซม. สีน้ำตาลอ่อน'),
    (106, N'ZCC010180060052', N'BISHOP HAT 6 CM. RED BROWN', N'ศิลา 5 เหลี่ยม 6 ซม. สีน้ำตาลเข้ม'),
    (107, N'ZCC010180060081', N'BISHOP HAT 6 CM. GREEN', N'ศิลา 5 เหลี่ยม 6 ซม. สีเขียว'),
    (108, N'zcc010123380011', N'Square Turf 8 CM - GREY', N'สแควร์ เทิร์ฟ 8 ซม. สีเทา'),
    (109, N'ZCC010370080011DU', N'TURF STONE 8 CM - GREY (FACING)DU', N'บล็อคปลูกหญ้า 8 ซม. สีเทา (มีผิวหน้า)DU'),
    (110, N'ZCC010370080011', N'TURF STONE 8 CM - GREY (FACING)', N'บล็อคปลูกหญ้า 8 ซม. สีเทา (มีผิวหน้า)'),
    (111, N'ZCC010370080031', N'TURF STONE 8 CM -ORANGE  (FACING)', N'บล็อคปลูกหญ้า 8 ซม. สีส้ม (มีผิวหน้า)'),
    (112, N'ZCC010370080051', N'TURF STONE 8 CM -  BROWN (FACING)', N'บล็อคปลูกหญ้า 8 ซม. สีน้ำตาล (มีผิวหน้า)'),
    (113, N'ZCC010120080081', N'TURF STONE 8 CM - GREEN', N'บล็อคปลูกหญ้า 8 ซม. สีเขียว'),
    (114, N'ZCC010120080011du', N'TURF STONE 8 CM - GREY (NO FACING)', N'บล็อคปลูกหญ้า 8 ซม. สีเทาDU (ไม่มีผิวหน้า)'),
    (115, N'ZCC010120080011', N'TURF STONE 8 CM - GREY (NO FACING)', N'บล็อคปลูกหญ้า 8 ซม. สีเทา (ไม่มีผิวหน้า)'),
    (116, N'ZCC010120080011P', N'TURF STONE 8 CM - GREY (NO FACING) (P)', N'บล็อคปลูกหญ้า 8 ซม. สีเทา (ไม่มีผิวหน้า) (โครงการ)'),
    (117, N'ZCC010370090011', N'TURF STONE 9 CM - GREY (FACING)', N'บล็อคปลูกหญ้า 9 ซม. สีเทา (มีผิวหน้า)'),
    (118, N'ZCC010120090011', N'TURF STONE 9 CM - GREY (NO FACING)', N'บล็อคปลูกหญ้า 9 ซม. สีเทา (ไม่มีผิวหน้า)'),
    (119, N'ZCC010120090081', N'TURF STONE 9 CM - GREEN', N'บล็อคปลูกหญ้า 9 ซม. สีเขียว'),
    (120, N'ZCC010224350011', N'SLAB 40x40x3.5 CM.GREY', N'แผ่นปูทางเท้า 40x40x3.5 ซม. สีเทา (ผิวหน้าปกติ)'),
    (121, N'ZCC010224350021', N'SLAB 40x40x3.5 CM.RED', N'แผ่นปูทางเท้า 40x40x3.5 ซม. สีแดง (ผิวหน้าปกติ)'),
    (122, N'ZCC010224350041', N'SLAB 40x40x3.5 CM.YELLOW', N'แผ่นปูทางเท้า 40x40x3.5 ซม. สีเหลือง (ผิวหน้าปกติ)'),
    (123, N'ZCC010224350061', N'SLAB 40x40x3.5 CM.BLACK', N'แผ่นปูทางเท้า 40x40x3.5 ซม. สีดำ (ผิวหน้าปกติ)'),
    (124, N'ZCC010224350071', N'SLAB 40x40x3.5 CM.BLUE', N'แผ่นปูทางเท้า 40x40x3.5 ซม. สีฟ้า (ผิวหน้าปกติ)'),
    (125, N'ZCC011114350011', N'SLAB 40x40x3.5 CM.GREY(FACING 10 MM.)', N'แผ่นปูทางเท้า 40x40x3.5 ซม. สีเทา (ผิวหน้า 10 มม.มอก.826)'),
    (126, N'ZCC011114350021', N'SLAB 40x40x3.5 CM.RED(FACING 10 MM.)', N'แผ่นปูทางเท้า 40x40x3.5 ซม. สีแดง (ผิวหน้า 10 มม. มอก 826)'),
    (127, N'ZCC011114350061', N'SLAB 40x40x3.5 CM.BLACK(FACING 10 MM.)', N'แผ่นปูทางเท้า 40x40x3.5 ซม. สีดำ (ผิวหน้า 10 มม. มอก 826)'),
    (128, N'ZCC011114350011P', N'SLAB 40x40x3.5 CM.GREY(FACING 10 MM. No-Spacer)', N'แผ่นปูทางเท้า 40x40x3.5 ซม. สีเทา (ผิวหน้า 10 มม. No-Spacer)'),
    (129, N'ZCC011114350021P', N'SLAB 40x40x3.5 CM.RED(FACING 10 MM. No-Spacer)', N'แผ่นปูทางเท้า 40x40x3.5 ซม. สีแดง (ผิวหน้า 10 มม. No-Spacer)'),
    (130, N'zcc01166438NO11', N'แผ่นปูทางเท้า 40X40X3.8 สีเทา ลายพัดโบก', N'แผ่นปูทางเท้า 40X40X3.8 สีเทา ลายพัดโบก'),
    (131, N'zcc01171438NO21', N'กระเบื้อง 40X40X3.8 สีแดง ลายเกลียวคลื่น', N'กระเบื้อง 40X40X3.8 สีแดงลายเกลียวคลื่น'),
    (132, N'zcc011714350011FT', N'กระเบื้อง 40X40X3.8 สีเทา ลายเกลียวคลื่น', N'กระเบื้อง 40X40X3.8 สีเทา ลายเกลียวคลื่น'),
    (133, N'ZCC011714380011FT', N'กระเบื้อง 40X40X3.8 สีเทาลายเกลียวคลื่น FT', N'กระเบื้อง 40X40X3.8 สีเทาลายเกลียวคลื่น FT'),
    (135, N'zcc01172438NO11', N'กระเบื้อง 40X40X3.8 สีเทา หมากรุก  No-Space', N'กระเบื้อง 40X40X3.8 สีเทา หมากรุก  No-Space'),
    (136, N'zcc01160438NO11', N'กบ. 40X40X3.8 ซม.สานเส้นเทา', N'กบ. 40X40X3.8 ซม.สานเส้นเทา'),
    (138, N'ZCC011604380021A', N'กบ. 40X40X3.8 ซม.สานเส้นแดง FT', N'กบ. 40X40X3.8 ซม.สานเส้นแดง FT'),
    (139, N'ZCC011604380011A', N'กบ. 40X40X3.8 ซม.สานเส้นเทา FT', N'กบ. 40X40X3.8 ซม.สานเส้นเทา FT'),
    (140, N'ZCC010224440011FT', N'SLAB 40X40X4 CM - GREY(FACING)FT', N'แผ่นปูทางเท้า 40X40X4 สีเทา (มีผิวหน้า)FT'),
    (141, N'ZCC010224440011FTC', N'SLAB 40X40X4 CM - GREY(FACING)', N'แผ่นปูทางเท้า 40X40X4 สีเทา (มีผิวหน้า)FTC'),
    (142, N'ZCC010224440011', N'SLAB 40X40X4 CM - GREY(FACING)', N'แผ่นปูทางเท้า 40X40X4 สีเทา (มีผิวหน้า)'),
    (143, N'ZCC010354440011', N'SLAB [NO FACING] 40X40X4 CM - GREY', N'แผ่นปูทางเท้า 40X40X4 สีเทา (ไม่มีผิวหน้า)'),
    (144, N'zcc01175444NS11FT', N'แผ่นปูทางเท้า40X40X4 สีเทาNo Spacer(ลายสานเส้น)FT', N'แผ่นปูทางเท้า40X40X4 สีเทาNo Spacer(ลายสานเส้น)FT'),
    (145, N'zcc01175444NS21FT', N'แผ่นปูทางเท้า40X40X4 สีแดงNo Spacer(ลายสานเส้น)FT', N'แผ่นปูทางเท้า40X40X4 สีแดงNo Spacer(ลายสานเส้น)FT'),
    (146, N'zcc01175444NS11', N'แผ่นปูทางเท้า40X40X4 สีเทา(ลายสานเส้น)', N'แผ่นปูทางเท้า40X40X4 สีเทา(ลายสานเส้น)'),
    (147, N'zcc01175444NS21', N'แผ่นปูทางเท้า40X40X4 สีแดง(ลายสานเส้น)', N'แผ่นปูทางเท้า40X40X4 สีแดง(ลายสานเส้น)'),
    (148, N'ZCC010224440021', N'SLAB 40X40X4 CM - RED', N'แผ่นปูทางเท้า 40X40X4 สีแดง'),
    (149, N'ZCC010224440031', N'SLAB 40X40X4 CM - ORANGE', N'แผ่นปูทางเท้า 40X40X4 สีส้ม'),
    (150, N'ZCC010224440041', N'SLAB 40X40X4 CM - YELLOW', N'แผ่นปูทางเท้า 40X40X4 สีเหลือง'),
    (151, N'ZCC010224440061', N'SLAB 40X40X4 CM - BLACK', N'แผ่นปูทางเท้า 40X40X4 สีดำ'),
    (152, N'ZCC010224440071', N'SLAB 40X40X4 CM - BLUE', N'แผ่นปูทางเท้า 40X40X4 สีฟ้า'),
    (153, N'ZCC010224440011A', N'SLAB 40X40X4 CM - GREY(EKACHAI BANGBON)', N'แผ่นปูทางเท้า 40X40X4 สีเทา (เอกชัยบางบอน)'),
    (154, N'ZCC010224440011B', N'SLAB 40X40X4 CM - GREY( Project )', N'แผ่นปูทางเท้า 40X40X4 สีเทา (โครงการ)'),
    (155, N'ZCC010224440011C', N'SLAB 40X40X4 CM - GREY(Phra TeeNang)', N'แผ่นปูทางเท้า 40X40X4 สีเทา (พระที่นั่ง)'),
    (156, N'ZCC010224440011P', N'SLAB 40X40X4 CM - GREY(PhraNangKrual)', N'แผ่นปูทางเท้า 40X40X4 สีเทา (พระนั่งเกล้า) '),
    (157, N'ZCC010354460011', N'SLAB 40X40X6 CM - GREY [NO FACING]', N'แผ่นปูทางเท้า 40X40X6 สีเทา (ไม่มีผิวหน้า)'),
    (158, N'ZCC010224460031', N'SLAB 40x40x6 - ORANGE', N'แผ่นปูทางเท้า 40x40x6 สีส้ม'),
    (159, N'ZCC010224460051', N'SLAB 40x40x6 - LIGHT BROWN', N'แผ่นปูทางเท้า 40x40x6 สีน้ำตาลอ่อน'),
    (160, N'ZCC010224460081', N'SLAB 40x40x6 - GREEN', N'แผ่นปูทางเท้า 40X40X6 สีเขียว'),
    (161, N'ZCC010171160081-1', N'LINEA 10X10X6 - GREEN', N'ศิลาเหลี่ยม 10X10X6 ซม. สีเขียว'),
    (162, N'ZCC010171160035-1', N'LINEA 10X10X6 - LIGHT ORANGE', N'ศิลาเหลี่ยม 10X10X6 ซม. สีแคนา'),
    (163, N'ZCC010171160036-1', N'LINEA 10X10X6 - MEDIUM ORANGE', N'ศิลาเหลี่ยม 10X10X6 ซม. สีแคส้ม'),
    (164, N'ZCC010171160037-1', N'LINEA 10X10X6 - DARK ORANGE', N'ศิลาเหลี่ยม 10X10X6 ซม. สีแคแสด'),
    (165, N'ZCC010171160061-1', N'LINEA 10X10X6 - BLACK', N'ศิลาเหลี่ยม 10X10X6 ซม. สีดำ'),
    (166, N'ZCC010171160021-1', N'LINEA 10X10X6 - RED', N'ศิลาเหลี่ยม 10X10X6 ซม. สีแดง'),
    (167, N'ZCC010171160011-1T', N'LINEA 10X10X6 - GREY (สินค้าทดลอง)', N'ศิลาเหลี่ยม 10X10X6 ซม. สีเทา(สินค้าทดลอง)'),
    (168, N'ZCC010171160011-1', N'LINEA 10X10X6 - GREY', N'ศิลาเหลี่ยม 10X10X6 ซม. สีเทา'),
    (169, N'ZCC010171160019-1', N'LINEA 10X10X6 - DARK GREY', N'ศิลาเหลี่ยม 10X10X6 ซม. สีเทาพยับหมอก'),
    (170, N'ZCC010171160018-1', N'LINEA 10X10X6 - MEDIUM GREY', N'ศิลาเหลี่ยม 10X10X6 ซม. สีเทาเมฆา'),
    (171, N'ZCC010171160017-1', N'LINEA 10X10X6 - LIGHT GREY', N'ศิลาเหลี่ยม 10X10X6 ซม. สีเทาวาตะ'),
    (172, N'ZCC010171160052-1', N'LINEA 10X10X6 - RED BROWN', N'ศิลาเหลี่ยม 10X10X6 ซม. สีน้ำตาลเข้ม'),
    (173, N'ZCC010171160051-1', N'LINEA 10X10X6 - LIGHT BROWN', N'ศิลาเหลี่ยม 10X10X6 ซม. สีน้ำตาลอ่อน'),
    (174, N'ZCC010171160071-1', N'LINEA 10X10X6 - BLUE', N'ศิลาเหลี่ยม 10X10X6 ซม. สีฟ้าใหม่'),
    (175, N'ZCC010171160031-1', N'LINEA 10X10X6 - ORANGE', N'ศิลาเหลี่ยม 10X10X6 ซม. สีส้ม'),
    (176, N'ZCC010171160041-1', N'LINEA 10X10X6 - YELLOW', N'ศิลาเหลี่ยม 10X10X6 ซม. สีเหลือง'),
    (177, N'ZCC010171160011', N'LINEA 10X10X6(PACK) - GREY', N'ศิลาเหลี่ยม 10X10X6 ซม. (ห่อ) สีเทา'),
    (178, N'ZCC010171160021', N'LINEA 10X10X6(PACK) - RED', N'ศิลาเหลี่ยม 10X10X6 ซม. (ห่อ) สีแดง'),
    (179, N'ZCC010171160031', N'LINEA 10X10X6(PACK) - ORANGE', N'ศิลาเหลี่ยม 10X10X6 ซม. (ห่อ) สีส้ม'),
    (180, N'ZCC010171160041', N'LINEA 10X10X6(PACK) - YELLOW', N'ศิลาเหลี่ยม 10X10X6 ซม. (ห่อ) สีเหลือง'),
    (181, N'ZCC010171160051', N'LINEA 10X10X6(PACK) - LIGHT BROWN', N'ศิลาเหลี่ยม 10X10X6 ซม. (ห่อ) สีน้ำตาลอ่อน'),
    (182, N'ZCC010171160052', N'LINEA 10X10X6(PACK) - RED BROWN', N'ศิลาเหลี่ยม 10X10X6 ซม. (ห่อ) สีน้ำตาลเข้ม'),
    (183, N'ZCC010171160061', N'LINEA 10X10X6(PACK) - BLACK', N'ศิลาเหลี่ยม 10X10X6 ซม. (ห่อ) สีดำ'),
    (184, N'ZCC010171160071', N'LINEA 10X10X6(PACK) - BLUE', N'ศิลาเหลี่ยม 10X10X6 ซม. (ห่อ) สีฟ้าใหม่'),
    (185, N'ZCC010171160081', N'LINEA 10X10X6(PACK) - GREEN', N'ศิลาเหลี่ยม 10X10X6 ซม. (ห่อ) สีเขียว'),
    (186, N'ZCC010171160017', N'LINEA 10X10X6(PACK) - LIGHT GREY', N'ศิลาเหลี่ยม 10X10X6 ซม. (ห่อ) สีเทาวาตะ'),
    (187, N'ZCC010171160018', N'LINEA 10X10X6(PACK) - MEDIUM GREY', N'ศิลาเหลี่ยม 10X10X6 ซม. (ห่อ) สีเทาเมฆา'),
    (188, N'ZCC010171160019', N'LINEA 10X10X6(PACK) - DARK GREY', N'ศิลาเหลี่ยม 10X10X6 ซม. (ห่อ) สีเทาพยับหมอก'),
    (189, N'ZCC010171160035', N'LINEA 10X10X6(PACK) - LIGHT ORANGE', N'ศิลาเหลี่ยม 10X10X6 ซม. (ห่อ) สีแคนา'),
    (190, N'ZCC010171160036', N'LINEA 10X10X6(PACK) - MEDIUM ORANGE', N'ศิลาเหลี่ยม 10X10X6 ซม. (ห่อ) สีแคส้ม'),
    (191, N'ZCC010171160037', N'LINEA 10X10X6(PACK) - DARK ORANGE', N'ศิลาเหลี่ยม 10X10X6 ซม. (ห่อ) สีแคแสด'),
    (194, N'ZCC010161260021', N'LINEA 10X20X6 - RED', N'ศิลาเหลี่ยม 10X20X6 ซม. สีแดง'),
    (195, N'ZCC010161260031FT', N'LINEA 10X20X6 - ORANGE FT', N'ศิลาเหลี่ยม 10X20X6 ซม. สีส้มFT'),
    (196, N'ZCC010161260031', N'LINEA 10X20X6 - ORANGE', N'ศิลาเหลี่ยม 10X20X6 ซม. สีส้ม'),
    (197, N'ZCC010161260035', N'LINEA 10X20X6 - LIGHT ORANGE', N'ศิลาเหลี่ยม 10X20X6 ซม. สีแคนา'),
    (198, N'ZCC010161260036', N'LINEA 10X20X6 - MEDIUM ORANGE', N'ศิลาเหลี่ยม 10X20X6 ซม. สีแคส้ม'),
    (199, N'ZCC010161260037', N'LINEA 10X20X6 - DARK ORANGE', N'ศิลาเหลี่ยม 10X20X6 ซม. สีแคแสด'),
    (200, N'ZCC010161260038', N'LINEA 10X20X6 - (NoChamfer) BRICK ORANGE', N'ศิลาเหลี่ยม 10X20X6 (ไม่ลบมุม) สีส้มอิฐ'),
    (201, N'ZCC010161260041', N'LINEA 10X20X6 - YELLOW(U)', N'ศิลาเหลี่ยม 10X20X6 ซม. สีเหลืองคดกริช'),
    (202, N'ZCC010161260051', N'LINEA 10X20X6 - LIGHT BROWN', N'ศิลาเหลี่ยม 10X20X6 ซม. สีน้ำตาลอ่อน'),
    (203, N'ZCC010161260052FT', N'LINEA 10X20X6 - RED BROWNFT', N'ศิลาเหลี่ยม 10X20X6 ซม. สีน้ำตาลเข้มFT'),
    (204, N'ZCC010161260052', N'LINEA 10X20X6 - RED BROWN', N'ศิลาเหลี่ยม 10X20X6 ซม. สีน้ำตาลเข้ม'),
    (205, N'ZCC010161260061', N'LINEA 10X20X6 - BLACK', N'ศิลาเหลี่ยม 10X20X6 ซม. สีดำ'),
    (206, N'ZCC010161260071', N'LINEA 10X20X6 - BLUE', N'ศิลาเหลี่ยม 10X20X6 ซม. สีฟ้า (ใหม่)'),
    (207, N'ZCC010161260081', N'LINEA 10X20X6 - GREEN', N'ศิลาเหลี่ยม 10X20X6 ซม. สีเขียว'),
    (208, N'ZCC010161260017', N'LINEA 10X20X6 - LIGHT GREY', N'ศิลาเหลี่ยม 10X20X6 ซม. สีเทาวาตะ'),
    (209, N'ZCC010161260018', N'LINEA 10X20X6 - MEDIUM GREY', N'ศิลาเหลี่ยม 10X20X6 ซม. สีเทาเมฆา'),
    (210, N'ZCC010161260019', N'LINEA 10X20X6 - DARK GREY', N'ศิลาเหลี่ยม 10X20X6 ซม. สีเทาพยับหมอก'),
    (211, N'ZCC010161260091', N'LINEA 10X20X6 - LIGHT GREY', N'ศิลาเหลี่ยม 10X20X6 ซม. สีเทาอ่อน'),
    (212, N'ZCC010161260092', N'LINEA 10X20X6 - MEDIUM GREY', N'ศิลาเหลี่ยม 10X20X6 ซม. สีน้ำตาลอ่อน'),
    (213, N'ZCC010161260093', N'LINEA 10X20X6 - DARK GREY', N'ศิลาเหลี่ยม 10X20X6 ซม. สีเขียวน้ำทะเล'),
    (214, N'ZCC010161280011', N'LINEA 10X20X8 GREY', N'ศิลาเหลี่ยม 10X20X8 ซม. สีเทา'),
    (215, N'ZCC010161280021', N'LINEA 10X20X8 - RED', N'ศิลาเหลี่ยม 10X20X8 ซม. สีแดง'),
    (216, N'ZCC010161280031', N'LINEA 10X20X8 - ORANGE', N'ศิลาเหลี่ยม 10X20X8 ซม. สีส้ม'),
    (217, N'ZCC010161280041', N'LINEA 10X20X8 CM.- YELLOW', N'ศิลาเหลี่ยม 10X20X8 ซม. สีเหลือง'),
    (218, N'ZCC010161280052', N'LINEA 10X20X8 R-BROWN', N'ศิลาเหลี่ยม 10X20X8 ซม. สีน้ำตาลเข้ม'),
    (219, N'ZCC010161280061', N'LINEA 10X20X8 - BLACK', N'ศิลาเหลี่ยม 10X20X8 ซม. สีดำ'),
    (220, N'ZCC010161280081', N'LINEA 10X20X8 - GREEN', N'ศิลาเหลี่ยม 10X20X8 ซม. สีเขียว'),
    (221, N'ZCC010161280091', N'LINEA 10X20X8 - WHITE', N'ศิลาเหลี่ยม 10X20X8 ซม. สีขาว'),
    (222, N'ZCC010161280525', N'LINEA 10X20X8 CM. - Light Maroon', N'ศิลาเหลี่ยม 10X20X8 ซม. สี Light Maroon'),
    (223, N'ZCC010161280528', N'LINEA 10X20X8 CM. - Light Brown', N'ศิลาเหลี่ยม 10X20X8 ซม. สี Light Brown'),
    (224, N'ZCC0107A1280525', N'Porous Block 10x20x8 CM. Light Maroon', N'บล็อคระบายน้ำเร็ว 10X20X8 ซม. สี Light Maroon'),
    (225, N'ZCC0107A1280528', N'Porous Block 10x20x8 CM. Light Brown', N'บล็อคระบายน้ำเร็ว 10X20X8 ซม. สี Light Brown'),
    (226, N'ZCC010161220011', N'LINEA 10X20X12 - GREY', N'ศิลาเหลี่ยม 10X20X12 ซม. สีเทา'),
    (227, N'ZCC010162260011', N'LINEA 20X20X6 - GREY', N'ศิลาเหลี่ยม 20X20X6 ซม. สีเทา'),
    (228, N'ZCC011831960031', N'LAGUNA 20X20X6 cm. ส้มซากุระ', N'LAGUNA 20X20X6 cm. ส้มซากุระ'),
    (229, N'ZCC011831960041', N'LAGUNA 20X20X6 cm. เหลืองซากุระ', N'LAGUNA 20X20X6 cm. เหลืองซากุระ'),
    (232, N'ZCC011831960011', N'LAGUNA 20X20X6 cm. เทาซากุระ', N'LAGUNA 20X20X6 cm. เทาซากุระ'),
    (233, N'ZCC011831960203', N'LAGUNA 20X20X6 cm. ชมพูซากุระ', N'LAGUNA 20X20X6 cm. ชมพูซากุระ'),
    (234, N'ZCC011831960061', N'LAGUNA 20X20X6 cm.ดำซากุระ', N'LAGUNA 20X20X6 cm. ดำซากุระ'),
    (235, N'ZCC011831960091', N'LAGUNA 20X20X6 cm. ขาวซากุระ', N'LAGUNA 20X20X6 cm. ขาวซากุระ'),
    (236, N'ZCC010162260017', N'LINEA 20X20X6 - LIGHT GREY', N'ศิลาเหลี่ยม 20X20X6 ซม. สีเทาวาตะ'),
    (237, N'ZCC010162260018', N'LINEA 20X20X6 - MEDIUM GREY', N'ศิลาเหลี่ยม 20X20X6 ซม. สีเทาเมฆา'),
    (238, N'ZCC010162260019', N'LINEA 20X20X6 - DARK GREY', N'ศิลาเหลี่ยม 20X20X6 ซม. สีเทาพยับหมอก'),
    (239, N'ZCC010162260021', N'LINEA 20X20X6 - RED', N'ศิลาเหลี่ยม 20X20X6 ซม. สีแดง'),
    (240, N'ZCC010162260031', N'LINEA 20X20X6 - ORANGE', N'ศิลาเหลี่ยม 20X20X6 ซม. สีส้ม'),
    (241, N'ZCC010162260035', N'LINEA 20X20X6 - LIGHT ORANGE', N'ศิลาเหลี่ยม 20X20X6 ซม. สีแคนา'),
    (242, N'ZCC010162260036', N'LINEA 20X20X6 - MEDIUM ORANGE', N'ศิลาเหลี่ยม 20X20X6 ซม. สีแคส้ม'),
    (243, N'ZCC010162260037', N'LINEA 20X20X6 - DARK ORANGE', N'ศิลาเหลี่ยม 20X20X6 ซม. สีแคแสด'),
    (244, N'ZCC010162260041', N'LINEA 20X20X6 - YELLOW', N'ศิลาเหลี่ยม 20X20X6 ซม. สีเหลือง'),
    (245, N'ZCC010162260051', N'LINEA 20X20X6 - LIGHT BROWN', N'ศิลาเหลี่ยม 20X20X6 ซม. สีน้ำตาลอ่อน'),
    (246, N'ZCC010162260052', N'LINEA 20X20X6 - RED BROWN', N'ศิลาเหลี่ยม 20X20X6 ซม. สีน้ำตาลเข้ม'),
    (247, N'ZCC010162260061', N'LINEA 20X20X6 - BLACK', N'ศิลาเหลี่ยม 20X20X6 ซม. สีดำ'),
    (248, N'ZCC010162260071', N'LINEA 20X20X6 - BLUE', N'ศิลาเหลี่ยม 20X20X6 ซม. สีฟ้า'),
    (249, N'ZCC010162260081', N'LINEA 20X20X6 - GREEN', N'ศิลาเหลี่ยม 20X20X6 ซม. สีเขียว'),
    (250, N'ZCC0101A2360011', N'Diamond 20x34.6x6 CM. - สีเทา', N'บล็อกไดมอนด์ 20x34.6x6 ซม. - สีเทา'),
    (251, N'ZCC0101A2360021', N'Diamond 20x34.6x6 CM. - สีแดง', N'บล็อกไดมอนด์ 20x34.6x6 ซม. - สีแดง'),
    (252, N'ZCC0101A2360031', N'Diamond 20x34.6x6 CM. - สีส้ม', N'บล็อกไดมอนด์ 20x34.6x6 ซม. - สีส้ม'),
    (253, N'ZCC0101A2360051', N'Diamond 20x34.6x6 CM. - สีน้ำตาลอ่อน', N'บล็อกไดมอนด์ 20x34.6x6 ซม. - สีน้ำตาลอ่อน'),
    (254, N'ZCC0101A2360052', N'Diamond 20x34.6x6 CM. - สีน้ำตาลเข้ม', N'บล็อกไดมอนด์ 20x34.6x6 ซม. - สีน้ำตาลเข้ม'),
    (255, N'ZCC0101A2360053', N'Diamond 20x34.6x6 CM. - สีน้ำตาล', N'บล็อกไดมอนด์ 20x34.6x6 ซม. - สีน้ำตาล'),
    (256, N'ZCC0101A2360061', N'Diamond 20x34.6x6 CM. - สีดำ', N'บล็อกไดมอนด์ 20x34.6x6 ซม. - สีดำ'),
    (257, N'ZCC010162360011', N'LINEA 20X30X6 - GREY', N'ศิลาเหลี่ยม 20X30X6 ซม. สีเทา'),
    (258, N'ZCC010162360021', N'LINEA 20X30X6 - RED', N'ศิลาเหลี่ยม 20X30X6 ซม. สีแดง'),
    (259, N'ZCC010162360031', N'LINEA 20X30X6 - ORANGE', N'ศิลาเหลี่ยม 20X30X6 ซม. สีส้ม'),
    (260, N'ZCC010162360051', N'LINEA 20X30X6 - LIGHT BROWN', N'ศิลาเหลี่ยม 20X30X6 ซม. สีน้ำตาลอ่อน'),
    (261, N'ZCC010162360052', N'LINEA 20X30X6 - RED BROWN', N'ศิลาเหลี่ยม 20X30X6 ซม. สีน้ำตาลเข้ม'),
    (262, N'ZCC010162360081', N'LINEA 20X30X6 - GREEN', N'ศิลาเหลี่ยม 20X30X6 ซม. สีเขียว'),
    (263, N'ZCC010163330081R', N'กระเบื้องหน้าเรียบ 30*30*3.5สี GREEN', N'กระเบื้องหน้าเรียบ 30*30*3.5สี เขียว'),
    (264, N'ZCC010163330011R', N'กระเบื้องหน้าเรียบ 30*30*3.5สีเทา', N'กระเบื้องหน้าเรียบ 30*30*3.5สีเทา'),
    (265, N'ZCC010163330059P', N'LINER 30X30X3.5 BROWN', N'ศิลาเหลี่ยม 30X30X3.5 ซม. น้ำตาล โปรเจค'),
    (266, N'ZCC010163330011', N'LINEA 30X30X3.5 GREY(FACING 10 CM)', N'ศิลาเหลี่ยม 30X30X3.5 ซม. สีเทา (ผิวหน้า 10 มม.)'),
    (267, N'ZCC010163330019', N'LINEA 30X30X3.5  DARK GREY (FACING 10 MM)', N'ศิลาเหลี่ยม 30X30X3.5 ซม. สีเทาเข้ม (ผิวหน้า 10 มม.)'),
    (268, N'ZCC010163330061', N'LINEA 30X30X3.5  BLACK (FACING 10 MM)', N'ศิลาเหลี่ยม 30X30X3.5 ซม. สีดำ (ผิวหน้า 10 มม.)'),
    (269, N'ZCC010163330021', N'LINEA 30X30X3.5  RED (FACING 10 MM)', N'ศิลาเหลี่ยม 30X30X3.5 ซม. สีแดง (ผิวหน้า 10 มม.)'),
    (270, N'ZCC010163330031', N'LINEA 30X30X3.5  ORANGE (FACING 10 MM)', N'ศิลาเหลี่ยม 30X30X3.5 ซม. สีส้ม (ผิวหน้า 10 มม.)'),
    (271, N'ZCC010163330071', N'LINEA 30X30X3.5  BLUE', N'ศิลาเหลี่ยม 30X30X3.5 ซม. สีฟ้า'),
    (272, N'ZCC010163350011', N'LINEA 30X30X5 - GREY', N'ศิลาเหลี่ยม 30X30X5 ซม. สีเทา'),
    (273, N'ZCC010163350021', N'LINEA 30X30X5 - RED', N'ศิลาเหลี่ยม 30X30X5 ซม. สีแดง'),
    (274, N'ZCC010163350031', N'LINEA 30X30X5 - ORANGE', N'ศิลาเหลี่ยม 30X30X5 ซม. สีส้ม'),
    (275, N'ZCC010163350081', N'LINEA 30X30X5 - GREEN', N'ศิลาเหลี่ยม 30X30X5 ซม. สีเขียว'),
    (276, N'ZCC010163360011du', N'LINEA 30X30X6 - GREYDU', N'ศิลาเหลี่ยม 30X30X6 ซม. สีเทาDU'),
    (277, N'ZCC010163360011FTC', N'LINEA 30X30X6 - GREYFT', N'ศิลาเหลี่ยม 30X30X6 ซม. สีเทาFTC'),
    (278, N'ZCC010163360011', N'LINEA 30X30X6 - GREY', N'ศิลาเหลี่ยม 30X30X6 ซม. สีเทา'),
    (279, N'ZCC010163360011A', N'Linear 30X30X6 (Klong Tuey Port) - Grey', N'ศิลาเหลี่ยม 30X30X6 ซม. สีเทา (ท่าเรือคลองเตย)'),
    (280, N'ZCC010163360011C', N'LINEA 30X30X6 -GREY (Ratchada-Satu)', N'ศิลาเหลี่ยม 30X30X6 ซม. สีเทา (รัชดา-สาธุ)'),
    (281, N'ZCC010163360021FTC', N'LINEA 30X30X6 - REDDU', N'ศิลาเหลี่ยม 30X30X6 ซม. สีแดงFTC'),
    (282, N'ZCC010163360021', N'LINEA 30X30X6 - RED', N'ศิลาเหลี่ยม 30X30X6 ซม. สีแดง'),
    (283, N'ZCC010163360031FTC', N'LINEA 30X30X6 - ORANGEFT', N'ศิลาเหลี่ยม 30X30X6 ซม. สีส้มFTC'),
    (284, N'ZCC010163360031FT', N'LINEA 30X30X6 - ORANGEFT', N'ศิลาเหลี่ยม 30X30X6 ซม. สีส้มFT'),
    (285, N'ZCC010163360031', N'LINEA 30X30X6 - ORANGE', N'ศิลาเหลี่ยม 30X30X6 ซม. สีส้ม'),
    (286, N'ZCC010163360041', N'LINEA 30X30X6 - YELLOW', N'ศิลาเหลี่ยม 30X30X6 ซม. สีเหลือง'),
    (287, N'ZCC010163360045', N'LINEA 30X30X6 - YELLOW (PROJECT)', N'ศิลาเหลี่ยม 30X30X6 ซม. สีเหลือง (โครงการ)'),
    (288, N'ZCC010163360051', N'LINEA 30X30X6 - LIGHT BROWN', N'ศิลาเหลี่ยม 30X30X6 ซม. สีน้ำตาลอ่อน'),
    (289, N'ZCC010163360052', N'LINEA 30X30X6 - RED BROWN', N'ศิลาเหลี่ยม 30X30X6 ซม. สีน้ำตาลเข้ม'),
    (290, N'ZCC010163360061', N'La Linear 30X30X6 cm. BLACK', N'ศิลาเหลี่ยม 30X30X6 ซม. สีดำ'),
    (291, N'ZCC010163360071', N'LINEA 30X30X6 - BLUE', N'ศิลาเหลี่ยม 30X30X6 ซม. สีฟ้า'),
    (292, N'ZCC010163360081', N'LINEA 30X30X6 - GREEN', N'ศิลาเหลี่ยม 30X30X6 ซม. สีเขียว'),
    (293, N'ZCC010163360084', N'LINEA 30X30X6 - GREEN BLUE', N'ศิลาเหลี่ยม 30X30X6 ซม. - สีเขียวอมฟ้า'),
    (294, N'ZCC010163360011P', N'LINEA 30X30X6 - GREY ( NO SPACER )', N'ศิลาเหลี่ยม 30X30X6 ซม. สีเทา ( No Spacer)'),
    (295, N'ZCC010163360021P', N'LINEA 30X30X6 - RED  (NO SPACER )', N'ศิลาเหลี่ยม 30X30X6 ซม. สีแดง ( No Spacer)'),
    (296, N'ZCC011433360011', N'LINEA 30X30X6 - GREY (FACING 10 MM. NO.SPACER)', N'ศิลาเหลี่ยม 30X30X6 ซม. สีเทา (ผิวหน้า 10 มม. No.Spacer)'),
    (297, N'ZCC011433360021', N'LINEA 30X30X6 - RED (FACING 10 MM. NO.SPACER)', N'ศิลาเหลี่ยม 30X30X6 ซม. สีแดง (ผิวหน้า 10 มม. No.Spacer)'),
    (298, N'ZCC010163660011', N'LINEAR 30x60x6 - GREY', N'ศิลาเหลี่ยม 30X60X6 ซม. สีเทา'),
    (299, N'ZCC010224460011', N'LA 40X40X6 CM - GREY', N'ศิลาเหลี่ยม 40X40X6 สีเทา (มีผิวหน้า)'),
    (300, N'ZCC010224460011B2+3', N'LA 40X40X6 CM - GREY B2+3', N'ศิลาเหลี่ยม 40X40X6 สีเทา (มีผิวหน้า) B2+3'),
    (301, N'ZCC010224460011GB4+2', N'LA 40X40X6 CM - GREY GB4+2', N'ศิลาเหลี่ยม 40X40X6 สีเทา (มีผิวหน้า) GB4+2'),
    (302, N'ZCC010252260013', N'NATURA BLOCK 20X20X6 - GREY GREEN', N'บล็อคหน้าธรรมชาติ 20X20X6 ซม. สีเทาเขียว'),
    (303, N'ZCC010252260024', N'NATURA BLOCK 20X20X6 - VIOLET RED', N'บล็อคหน้าธรรมชาติ 20X20X6 ซม. สีม่วงแดง'),
    (304, N'ZCC010252260033', N'NATURA BLOCK 20X20X6 - ORANGE', N'บล็อคหน้าธรรมชาติ 20X20X6 ซม. สีส้ม'),
    (305, N'ZCC010252260055', N'NATURA BLOCK 20X20X6 - BROWN SAND', N'บล็อคหน้าธรรมชาติ 20X20X6 ซม. สีน้ำตาลทราย'),
    (306, N'ZCC010252260081', N'NATURA BLOCK 20X20X6 - GREEN', N'บล็อคหน้าธรรมชาติ 20X20X6 ซม. สีเขียว'),
    (307, N'ZCC010252260203', N'NATURA BLOCK 20X20X6 - PINK', N'บล็อคหน้าธรรมชาติ 20X20X6 ซม. สีชมพู'),
    (308, N'ZCC010253360011', N'NATURA BLOCK 30*30*6  GREY', N'บล็อคหน้าธรรมชาติ 30X30X6 ซม. สีเทา'),
    (309, N'ZCC010253360013', N'NATURA BLOCK 30X30X6 - GREY GREEN', N'บล็อคหน้าธรรมชาติ 30X30X6 ซม. สีเทาเขียว'),
    (310, N'ZCC010253360024', N'NATURA BLOCK 30X30X6 - VIOLET RED', N'บล็อคหน้าธรรมชาติ 30X30X6 ซม. สีม่วงแดง'),
    (311, N'ZCC010253360033', N'NATURA BLOCK 30X30X6 - ORANGE', N'บล็อคหน้าธรรมชาติ 30X30X6 ซม. สีส้ม'),
    (312, N'ZCC010253360055', N'NATURA BLOCK 30X30X6 - BROWN SAND', N'บล็อคหน้าธรรมชาติ 30X30X6 ซม. สีน้ำตาลทราย'),
    (313, N'ZCC010253360061', N'NATURA BLOCK 30X30X6 - BLACK', N'บล็อคหน้าธรรมชาติ 30X30X6 ซม. สีดำ'),
    (314, N'ZCC010253360071', N'NATURA BLOCK 30X30X6 - BLUE', N'บล็อคหน้าธรรมชาติ 30X30X6 ซม. สีฟ้า'),
    (315, N'ZCC010253360081', N'NATURA BLOCK 30X30X6 - GREEN', N'บล็อคหน้าธรรมชาติ 30X30X6 ซม. สีเขียว'),
    (316, N'ZCC010253660013', N'NATURA BLOCK 30X60X6 - GREY GREENE', N'บล็อคหน้าธรรมชาติ 30X60X6 ซม. สีเทาเขียว'),
    (317, N'ZCC010253660024', N'NATURA BLOCK 30X60X6 - VIOLET RED', N'บล็อคหน้าธรรมชาติ 30X60X6 ซม. สีม่วงแดง'),
    (318, N'ZCC010253660033', N'NATURA BLOCK 30X60X6 - ORANGE', N'บล็อคหน้าธรรมชาติ 30X60X6 ซม. สีส้ม'),
    (319, N'ZCC010253660055', N'NATURA BLOCK 30X60X6 - BROWN SAND', N'บล็อคหน้าธรรมชาติ 30X60X6 ซม. สีน้ำตาลทราย'),
    (320, N'ZCC010253660081', N'NATURA BLOCK 30X60X6 - GREEN', N'บล็อคหน้าธรรมชาติ 30X60X6 ซม. สีเขียว'),
    (321, N'ZCC010253660203', N'NATURA BLOCK 30X60X6 - PINK', N'บล็อคหน้าธรรมชาติ 30X60X6 ซม. สีชมพู'),
    (322, N'ZCC010254460013', N'NATURA BLOCK 40X40X6 - GREY GREEN', N'บล็อคหน้าธรรมชาติ 40X40X6 ซม. สีเทาเขียว'),
    (323, N'ZCC010254460024', N'NATURA BLOCK 40X40X6 - VIOLET RED', N'บล็อคหน้าธรรมชาติ 40X40X6 ซม. สีม่วงแดง'),
    (324, N'ZCC010254460031', N'NATURA BLOCK 40X40X6 - ORANGE', N'บล็อคหน้าธรรมชาติ 40X40X6 ซม. สีส้ม'),
    (325, N'ZCC010254460055', N'NATURA BLOCK 40X40X6 - BROWN SAND', N'บล็อคหน้าธรรมชาติ 40X40X6 ซม. สีน้ำตาลทราย'),
    (326, N'ZCC010401280091', N'REFLECTIVE10X20X8 CM(HS) - WHITE', N'บล็อคสะท้อนแสง 10X20X8 ซม.(HS)-ขาว'),
    (327, N'ZCC011353360041', N'LALINEAR- Lines 30x30x6 cm. Yellow', N'ศิลาเหลี่ยม 30X30X6 ซม. สีเหลือง (สานเส้น)'),
    (328, N'zcc01041366M011LPN', N'LAGUNA 30x60x6 CM.  สีเทา(LPN)', N'ลากูน่า 30x60x6 ซม. สีเทา(LPN)'),
    (329, N'zcc01041366M061LPN', N'LAGUNA 30x60x6 CM.  สีดำ(LPN)', N'ลากูน่า 30x60x6 ซม. สีดำ(LPN)'),
    (330, N'ZCC01041366M011', N'LAGUNA 30x60x6 CM.  สีเทามัลดีฟ', N'ลากูน่า 30x60x6 ซม. สีเทา(มัลดีฟ)'),
    (333, N'ZCC0103A3660021', N'LA 30x60x6 CM. กราฟฟิค 01 - สีแดง', N'ศิลาเหลี่ยม 30x60x6 ซม. กราฟฟิค 01 - สีแดง'),
    (334, N'ZCC0103A3660031', N'LA 30x60x6 CM. กราฟฟิค 01 - สีส้ม', N'ศิลาเหลี่ยม 30x60x6 ซม. กราฟฟิค 01 - สีส้ม'),
    (335, N'ZCC0103A3660051', N'LA 30x60x6 CM. กราฟฟิค 01 - น้ำตาล', N'ศิลาเหลี่ยม 30x60x6 ซม. กราฟฟิค 01 - น้ำตาล'),
    (336, N'ZCC0103B3660011', N'LA 30x60x6 CM. กราฟฟิค 02 - สีเทา', N'ศิลาเหลี่ยม 30x60x6 ซม. กราฟฟิค 02 - สีเทา'),
    (337, N'ZCC0103B3660021', N'LA 30x60x6 CM. กราฟฟิค 02 - สีแดง', N'ศิลาเหลี่ยม 30x60x6 ซม. กราฟฟิค 02 - สีแดง'),
    (338, N'ZCC0103B3660031', N'LA 30x60x6 CM. กราฟฟิค 02 - สีส้ม', N'ศิลาเหลี่ยม 30x60x6 ซม. กราฟฟิค 02 - สีส้ม'),
    (339, N'ZCC0103B3660051', N'LA 30x60x6 CM. กราฟฟิค 02 - น้ำตาล', N'ศิลาเหลี่ยม 30x60x6 ซม. กราฟฟิค 02 - น้ำตาล'),
    (340, N'ZCC0103C3660011', N'LA 30x60x6 CM. กราฟฟิค 03 - สีเทา', N'ศิลาเหลี่ยม 30x60x6 ซม. กราฟฟิค 03 - สีเทา'),
    (341, N'ZCC0103C3660021', N'LA 30x60x6 CM. กราฟฟิค 03 - สีแดง', N'ศิลาเหลี่ยม 30x60x6 ซม. กราฟฟิค 03 - สีแดง'),
    (342, N'zcc01041366M011', N'Laguna 30x60x6_PORUS', N'Laguna 30x60x6_PORUS'),
    (343, N'ZCC0103C3660031', N'LA 30x60x6 CM. กราฟฟิค 03 - สีส้ม', N'ศิลาเหลี่ยม 30x60x6 ซม. กราฟฟิค 03 - สีส้ม'),
    (344, N'ZCC0103C3660051', N'LA 30x60x6 CM. กราฟฟิค 03 - น้ำตาล', N'ศิลาเหลี่ยม 30x60x6 ซม. กราฟฟิค 03 - น้ำตาล'),
    (345, N'ZCC011354440041', N'LALINEAR- Lines 40x40x4 cm. Yellow', N'ศิลาเหลี่ยม 40X40X4 ซม. สีเหลือง (สานเส้น)'),
    (346, N'ZCC011354460041', N'LALINEAR- Lines 40x40x6 cm. Yellow', N'ศิลาเหลี่ยม 40X40X6 ซม. สีเหลือง (สานเส้น)'),
    (347, N'ZCC010415560002K', N'LA 50x50x6 CM.Grey Stone (GGN)พระเมรุมาศ', N'LA 50x50x6 CM.Grey Stone (GGN)'),
    (352, N'ZCC0102A5560021', N'LA 50x50x6 CM. ลายดาราวดี - RED', N'ศิลาเหลี่ยม 50x50x6 ซม. ลายดาราวดี - สีแดง'),
    (353, N'ZCC0102A5560031', N'LA 50x50x6 CM. ลายดาราวดี - ORANGE', N'ศิลาเหลี่ยม 50x50x6 ซม. ลายดาราวดี - สีส้ม'),
    (354, N'ZCC0102A5560051', N'LA 50x50x6 CM. ลายดาราวดี - BROWN', N'ศิลาเหลี่ยม 50x50x6 ซม. ลายดาราวดี - สีน้ำตาล'),
    (355, N'ZCC0102B5560011', N'LA 50x50x6 CM. ลายสัตตบงกช - GREY', N'ศิลาเหลี่ยม 50x50x6 ซม. ลายสัตตบงกช - สีเทา'),
    (356, N'ZCC0102B5560021', N'LA 50x50x6 CM. ลายสัตตบงกช - RED', N'ศิลาเหลี่ยม 50x50x6 ซม. ลายสัตตบงกช - สีแดง'),
    (357, N'ZCC0102B5560031', N'LA 50x50x6 CM. ลายสัตตบงกช - ORANGE', N'ศิลาเหลี่ยม 50x50x6 ซม. ลายสัตตบงกช - สีส้ม'),
    (358, N'ZCC0102B5560051', N'LA 50x50x6 CM. ลายสัตตบงกช - BROWN', N'ศิลาเหลี่ยม 50x50x6 ซม. ลายสัตตบงกช - สีน้ำตาล'),
    (361, N'ZCC010193360042', N'บล็อคนำทาง 30X30X6 ซม. ปุ่มเหลือง', N'บล็อคนำทาง 30X30X6 ซม. ปุ่มเหลือง'),
    (362, N'ZCC010203360042', N'บล็อคนำทาง 30X30X6 ซม. แถบเหลือง', N'บล็อคนำทาง 30X30X6 ซม. แถบเหลือง'),
    (363, N'ZCC011373360011', N'LALINEAR - PATBOK 30X30X6 - GREY', N'ศิลาเหลี่ยม 30X30X6 ซม. สีเทา (ลายพัดโบก)'),
    (364, N'ZCC011443360052', N'LALINEAR - PATBOK 30X30X6 - RED', N'ศิลาเหลี่ยม 30x30x6 ซม. สีแดง-พัดโบก'),
    (365, N'ZCC011373360011A', N'LALINEAR - PATBOK 30X30X6 - RED', N'ศิลาเหลี่ยม 30X30X6 ซม. สีแดง(ลายพัดโบก) ทดลอง'),
    (366, N'ZCC011373360011B', N'LALINEAR - PATBOK 30X30X6 - BROWN', N'ศิลาเหลี่ยม 30X30X6 ซม. สีน้ำตาล (ลายพัดโบก) ทดลอง'),
    (367, N'ZCC011363360011', N'NATURA BLOCK 30X30X6 PATBOK - GREY ', N'บล็อคหน้าธรรมชาติ 30X30X6 ซม. สีเทา (ลายพัดโบก)'),
    (368, N'ZCC011363360021', N'NATURA BLOCK 30X30X6 PATBOK - RED ', N'บล็อคหน้าธรรมชาติ 30X30X6 ซม. สีแดง (ลายพัดโบก)'),
    (369, N'ZCC010301160132-1', N'EARTHTONE10X10X6 MEDIUM VIOLET RED', N'บล็อคEARTHTONE 10X10X6 สีม่วงแดงกลาง'),
    (370, N'ZCC010301160131-1', N'EARTHTONE 10X10X6 DARK VIOLET RED', N'บล็อคEARTHTONE 10X10X6 สีม่วงแดงเข้ม'),
    (371, N'ZCC010301160133-1', N'EARTHTONE 10X10X6 LIGHT VIOLET RED', N'บล็อคEARTHTONE 10X10X6 สีม่วงแดงอ่อน'),
    (372, N'ZCC010301160142-1', N'EARTHTONE10X10X6 MEDUIM YELLOW GREEN', N'บล็อคEARTHTONE 10X10X6 สีเหลืองเขียวกลาง'),
    (373, N'ZCC010301160141-1', N'EARTHTONE10X10X6 DARK YELLOW GREEN', N'บล็อคEARTHTONE 10X10X6 สีเหลืองเขียวเข้ม'),
    (374, N'ZCC010301160143-1', N'EARTHTONE10X10X6 LIGHT YELLOW GREEN', N'บล็อคEARTHTONE 10X10X6 สีเหลืองเขียวอ่อน'),
    (375, N'ZCC010301160132', N'EARTHTONE10X10X6 MEDIUM VIOLET RED(PACK)', N'บล็อคEARTHTONE 10X10X6 (ห่อ) สีม่วงแดงกลาง'),
    (376, N'ZCC010301160131', N'EARTHTONE 10X10X6 DARK VIOLET RED(PACK)', N'บล็อคEARTHTONE 10X10X6 (ห่อ) สีม่วงแดงเข้ม'),
    (377, N'ZCC010301160133', N'EARTHTONE 10X10X6 LIGHT VIOLET RED(PACK)', N'บล็อคEARTHTONE 10X10X6 (ห่อ) สีม่วงแดงอ่อน'),
    (378, N'ZCC010301160142', N'EARTHTONE10X10X6 MEDUIM YELLOW GREEN(PAC', N'บล็อคEARTHTONE 10X10X6 (ห่อ) สีเหลืองเขียวกลาง'),
    (379, N'ZCC010301160141', N'EARTHTONE10X10X6 DARK YELLOW GREEN(PACK)', N'บล็อคEARTHTONE 10X10X6 (ห่อ) สีเหลืองเขียวเข้ม'),
    (380, N'ZCC010301160143', N'EARTHTONE10X10X6 LIGHT YELLOW GREEN(PACK', N'บล็อคEARTHTONE 10X10X6 (ห่อ) สีเหลืองเขียวอ่อน'),
    (381, N'ZCC010301260131', N'EARTHTONE BLOCK 10X20X6 DARK VIOLET RED', N'บล็อคEARTHTONE 10X20X6 ซม. สีม่วงแดงเข้ม'),
    (382, N'ZCC010301260132', N'EARTHTONE BLOCK10X20X6 MEDUIM VIOLET RED', N'บล็อคEARTHTONE 10X20X6 ซม. สีม่วงแดงกลาง'),
    (383, N'ZCC010301260133', N'EARTHTONE BLOCK 10X20X6 LIGHT VIOLET RED', N'บล็อคEARTHTONE 10X20X6 ซม. สีม่วงแดงอ่อน'),
    (384, N'ZCC010301260141', N'EARTHTONE 10X20X6 CM. DARK YELLOW GREEN', N'บล็อคEARTHTONE 10X20X6 ซม. สีเหลืองเขียวเข้ม'),
    (385, N'ZCC010301260142', N'EARTHTONE 10X20X6 CM.MEDIUM YELLOW GREEN', N'บล็อคEARTHTONE 10X20X6 ซม. สีเหลืองเขียวกลาง'),
    (386, N'ZCC010301260143', N'EARTHTONE 10X20X6 CM.LIGHT YELLOW GREEN', N'บล็อคEARTHTONE 10X20X6 ซม. สีเหลืองเขียวอ่อน'),
    (387, N'ZCC010301280031', N'EARTHTONE 10x20x8 ORANGE', N'บล็อคEARTHTONE 10x20x8 ซม. สีส้ม'),
    (388, N'ZCC010301280041', N'EARTHTONE 10x20x8 YELLOW', N'บล็อคEARTHTONE 10x20x8 ซม. สีเหลือง'),
    (389, N'ZCC010301280131', N'EARTHTONE 10X20X8 CM. DARK VIOLET RED', N'บล็อคEARTHTONE 10x20x8 ซม. สีม่วงแดงเข้ม'),
    (390, N'ZCC010301280132', N'EARTHTONE 10X20X8 CM. MEDIUM VIOLET RED', N'บล็อคEARTHTONE 10x20x8 ซม. สีม่วงแดงกลาง'),
    (391, N'ZCC010301280133', N'EARTHTONE 10X20X8 CM. LIGHT VIOLET RED', N'บล็อคEARTHTONE 10x20x8 ซม. สีม่วงแดงอ่อน'),
    (392, N'ZCC010301280141', N'EARTHTONE 10X20X8 DARK YELLOW GREEN', N'บล็อคEARTHTONE 10X20X8 ซม. สีเหลืองเขียวเข้ม'),
    (393, N'ZCC010301280142', N'EARTHTONE 10X20X8 MEDIUM YELLOW GREEN', N'บล็อคEARTHTONE 10X20X8 ซม. สีเหลืองเขียวกลาง'),
    (394, N'ZCC010301280143', N'EARTHTONE 10X20X8 LIGHT YELLOW GREEN', N'บล็อคEARTHTONE 10X20X8 ซม. สีเหลืองเขียวอ่อน'),
    (395, N'ZCC010440080111', N'COBBLE STONE RT1-CARBON BLACK', N'COBBLE STONE RT1-CARBON BLACK'),
    (396, N'ZCC010440080112', N'COBBLE STONE RT1-MOSS GREY', N'COBBLE STONE RT1-MOSS GREY'),
    (397, N'ZCC010440080113', N'COBBLE STONE RT1-LILY PURPLE', N'COBBLE STONE RT1-LILY PURPLE'),
    (398, N'ZCC010440080114', N'COBBLE STONE RT1 - COFFEE BROWN', N'COBBLE STONE RT1-COFFEE BROWN'),
    (399, N'ZCC010440080115', N'COBBLE STONE RT1-ROSY PINK', N'COBBLE STONE RT1-ROSY PINK'),
    (400, N'ZCC010440080116', N'COBBLE STONE RT1-PLUM PURPLE', N'COBBLE STONE RT1-PLUM PURPLE'),
    (401, N'ZCC010440080117', N'COBBLE STONE RT1-MOONY YELLOW', N'COBBLE STONE RT1-MOONY YELLOW'),
    (402, N'ZCC010440080118', N'COBBLE STONE RT1-LEMON GREEN', N'COBBLE STONE RT1-LEMON GREEN'),
    (403, N'ZCC010440080119', N'COBBLE STONE RT1-MOCCA BROWN', N'COBBLE STONE RT1-MOCCA BROWN'),
    (404, N'ZCC010450060111', N'COBBLE STONE RT2-CARBON BLACK', N'COBBLE STONE RT2-CARBON BLACK'),
    (405, N'ZCC010450060112', N'COBBLE STONE RT2-MOSS GREY', N'COBBLE STONE RT2-MOSS GREY'),
    (406, N'ZCC010450060113', N'COBBLE STONE RT2-LILY PURPLE', N'COBBLE STONE RT2-LILY PURPLE'),
    (407, N'ZCC010450060114', N'COBBLE STONE RT2 - COFFEE BROWN', N'COBBLE STONE RT2-COFFEE BROWN'),
    (408, N'ZCC010450060115', N'COBBLE STONE RT2-ROSY PINK', N'COBBLE STONE RT2-ROSY PINK'),
    (409, N'ZCC010450060116', N'COBBLE STONE RT2-PLUM PURPLE', N'COBBLE STONE RT2-PLUM PURPLE'),
    (410, N'ZCC010450060117', N'COBBLE STONE RT2-MOONY YELLOW', N'COBBLE STONE RT2-MOONY YELLOW'),
    (411, N'ZCC010450060118', N'COBBLE STONE RT2-LEMON GREEN', N'COBBLE STONE RT2-LEMON GREEN'),
    (412, N'ZCC010450060119', N'COBBLE STONE RT2-MOCCA BROWN', N'COBBLE STONE RT2-MOCCA BROWN'),
    (413, N'ZCC010450060120', N'COBBLE STONE RT2-SEA BLUE', N'COBBLE STONE RT2-SEA BLUE'),
    (414, N'ZCC010460060111', N'COBBLE STONE RT3-CARBON BLACK', N'COBBLE STONE RT3-CARBON BLACK'),
    (415, N'ZCC010460060112', N'COBBLE STONE RT3-MOSS GREY', N'COBBLE STONE RT3-MOSS GREY'),
    (416, N'ZCC010460060113', N'COBBLE STONE RT3-LILY PURPLE', N'COBBLE STONE RT3-LILY PURPLE'),
    (417, N'ZCC010460060114', N'COBBLE STONE RT3 - COFFEE BROWN', N'COBBLE STONE RT3-COFFEE BROWN'),
    (418, N'ZCC010460060115', N'COBBLE STONE RT3-ROSY PINK', N'COBBLE STONE RT3-ROSY PINK'),
    (419, N'ZCC010460060117', N'COBBLE STONE RT3-MOONY YELLOW', N'COBBLE STONE RT3-MOONY YELLOW'),
    (420, N'ZCC010460060118', N'COBBLE STONE RT3-LEMON GREEN', N'COBBLE STONE RT3-LEMON GREEN'),
    (421, N'ZCC010460060116', N'COBBLE STONE RT3-PLUM PURPLE', N'COBBLE STONE RT3-PLUM PURPLE'),
    (422, N'ZCC010460060119', N'COBBLE STONE RT3-MOCCA BROWN', N'COBBLE STONE RT3-MOCCA BROWN'),
    (423, N'ZCC010470080111', N'COBBLE STONE RT4-CARBON BLACK', N'COBBLE STONE RT4-CARBON BLACK'),
    (424, N'ZCC010470080112', N'COBBLE STONE RT4-MOSS GREY', N'COBBLE STONE RT4-MOSS GREY'),
    (425, N'ZCC010470080113', N'COBBLE STONE RT4-LILY PURPLE', N'COBBLE STONE RT4-LILY PURPLE'),
    (426, N'ZCC010470080114', N'COBBLE STONE RT4 - COFFEE BROWN', N'COBBLE STONE RT4-COFFEE BROWN'),
    (427, N'ZCC010470080115', N'COBBLE STONE RT4-ROSY PINK', N'COBBLE STONE RT4-ROSY PINK'),
    (428, N'ZCC010470080116', N'COBBLE STONE RT4-PLUM PURPLE', N'COBBLE STONE RT4-PLUM PURPLE'),
    (429, N'ZCC010470080117', N'COBBLE STONE RT4-MOONY YELLOW', N'COBBLE STONE RT4-MOONY YELLOW'),
    (430, N'ZCC010470080118', N'COBBLE STONE RT4-LEMON GREEN', N'COBBLE STONE RT4-LEMON GREEN'),
    (431, N'ZCC010470080119', N'COBBLE STONE RT4-MOCCA BROWN', N'COBBLE STONE RT4-MOCCA BROWN'),
    (432, N'ZCC010480080111', N'COBBLE STONE TZ1-CARBON BLACK', N'COBBLE STONE TZ1-CARBON BLACK'),
    (433, N'ZCC010480080112', N'COBBLE STONE TZ1-MOSS GREY', N'COBBLE STONE TZ1-MOSS GREY'),
    (434, N'ZCC010480080113', N'COBBLE STONE TZ1-LILY PURPLE', N'COBBLE STONE TZ1-LILY PURPLE'),
    (435, N'ZCC010480080114', N'COBBLE STONE TZ1 - COFFEE BROWN', N'COBBLE STONE TZ1-COFFEE BROWN'),
    (436, N'ZCC010480080115', N'COBBLE STONE TZ1-ROSY PINK', N'COBBLE STONE TZ1-ROSY PINK'),
    (437, N'ZCC010480080116', N'COBBLE STONE TZ1-PLUM PURPLE', N'COBBLE STONE TZ1-PLUM PURPLE'),
    (438, N'ZCC010480080117', N'COBBLE STONE TZ1-MOONY YELLOW', N'COBBLE STONE TZ1-MOONY YELLOW'),
    (439, N'ZCC010480080118', N'COBBLE STONE TZ1-LEMON GREEN', N'COBBLE STONE TZ1-LEMON GREEN'),
    (440, N'ZCC010480080119', N'COBBLE STONE TZ1-MOCCA BROWN', N'COBBLE STONE TZ1-MOCCA BROWN'),
    (441, N'ZCC010480080120', N'COBBLE STONE TZ1-SEA BLUE', N'COBBLE STONE TZ1-SEA BLUE'),
    (442, N'ZCC010490060111', N'COBBLE STONE TZ2-CARBON BLACK', N'COBBLE STONE TZ2-CARBON BLACK'),
    (443, N'ZCC010490060112', N'COBBLE STONE TZ2-MOSS GREY', N'COBBLE STONE TZ2-MOSS GREY'),
    (444, N'ZCC010490060113', N'COBBLE STONE TZ2-LILY PURPLE', N'COBBLE STONE TZ2-LILY PURPLE'),
    (445, N'ZCC010490060114', N'COBBLE STONE TZ2 - COFFEE BROWN', N'COBBLE STONE TZ2-COFFEE BROWN'),
    (446, N'ZCC010490060115', N'COBBLE STONE TZ2-ROSY PINK', N'COBBLE STONE TZ2-ROSY PINK'),
    (447, N'ZCC010490060116', N'COBBLE STONE TZ2-PLUM PURPLE', N'COBBLE STONE TZ2-PLUM PURPLE'),
    (448, N'ZCC010490060117', N'COBBLE STONE TZ2-MOONY YELLOW', N'COBBLE STONE TZ2-MOONY YELLOW'),
    (449, N'ZCC010490060118', N'COBBLE STONE TZ2-LEMON GREEN', N'COBBLE STONE TZ2-LEMON GREEN'),
    (450, N'ZCC010490060119', N'COBBLE STONE TZ2-MOCCA BROWN', N'COBBLE STONE TZ2-MOCCA BROWN'),
    (451, N'ZCC010490060120', N'COBBLE STONE TZ2-SEA BLUE', N'COBBLE STONE TZ2-SEA BLUE'),
    (452, N'ZCC010500060111', N'COBBLE STONE CE-CARBON BLACK', N'COBBLE STONE CE-CARBON BLACK'),
    (453, N'ZCC010500060112', N'COBBLE STONE CE-MOSS GREY', N'COBBLE STONE CE-MOSS GREY'),
    (454, N'ZCC010500060113', N'COBBLE STONE CE-LILY PURPLE', N'COBBLE STONE CE-LILY PURPLE'),
    (455, N'ZCC010500080114', N'COBBLE STONE CE - COFFEE BROWN', N'COBBLE STONE CE-COFFEE BROWN'),
    (456, N'ZCC010500080115', N'COBBLE STONE CE-ROSY PINK', N'COBBLE STONE CE-ROSY PINK'),
    (457, N'ZCC010500080116', N'COBBLE STONE CE-PLUM PURPLE', N'COBBLE STONE CE-PLUM PURPLE'),
    (458, N'ZCC010500080117', N'COBBLE STONE CE-MOONY YELLOW', N'COBBLE STONE CE-MOONY YELLOW'),
    (459, N'ZCC010500080118', N'COBBLE STONE CE-LEMON GREEN', N'COBBLE STONE CE-LEMON GREEN'),
    (460, N'ZCC010500080119', N'COBBLE STONE CE-MOCCA BROWN', N'COBBLE STONE CE-MOCCA BROWN'),
    (461, N'ZCC010532260031', N'CPAC DRAIN BLOCK (END) - ORANGE', N'รางระบายน้ำซีแพค(แนวปิด) - สีส้ม'),
    (462, N'ZCC010532260161', N'CPAC DRAIN BLOCK (END) - GREY GREEN', N'รางระบายน้ำซีแพค(แบบปิด) - สีเทาเขียว'),
    (463, N'ZCC010532260162', N'CPAC DRAIN BLOCK (END) - MUSTARD', N'รางระบายน้ำซีแพค(แบบปิด) - สีมัสตาร์ด'),
    (464, N'ZCC010532260163', N'CPAC DRAIN BLOCK (END) - BURGUNDY', N'รางระบายน้ำซีแพค(แบบปิด) - สีแดงองุ่น'),
    (465, N'ZCC010532260166', N'CPAC DRAIN BLOCK (END)-MOSS GREY', N'รางระบายน้ำซีแพค(แนวปิด) - MOSS GREY'),
    (466, N'ZCC010532260167', N'CPAC DRAIN BLOCK (END)-LEMON YELLOW', N'รางระบายน้ำซีแพค(แนวปิด) - LEMON YELLOW'),
    (467, N'ZCC010532260168', N'CPAC DRAIN BLOCK (END)-HONEY BROWN', N'รางระบายน้ำซีแพค(แนวปิด) - HONEY BROWN'),
    (468, N'ZCC010532260169', N'CPAC DRAIN BLOCK (END)-PASSION BROWN', N'รางระบายน้ำซีแพค(แนวปิด) - PASSION BROWN'),
    (469, N'ZCC010542260161', N'CPAC DRAIN BLOCK(T SHAPE) - GREY GREEN', N'รางระบายน้ำซีแพค(ตัว T) - สีเทาเขียว'),
    (470, N'ZCC010542260162', N'CPAC DRAIN BLOCK(T SHAPE) - MUSTARD', N'รางระบายน้ำซีแพค(ตัว T) - สีมัสตาร์ด'),
    (471, N'ZCC010542260163', N'CPAC DRAIN BLOCK(T SHAPE) - BURGUNDY', N'รางระบายน้ำซีแพค(ตัว T) - สีแดงองุ่น'),
    (472, N'ZCC010542260166', N'CPAC DRAIN BLOCK(T SHAPE)-MOSS GREY', N'รางระบายน้ำซีแพค(ตัว T) - MOSS GREY'),
    (473, N'ZCC010542260167', N'CPAC DRAIN BLOCK(T SHAPE)-LEMON YELLOW', N'รางระบายน้ำซีแพค(ตัว T) - LEMON YELLOW'),
    (474, N'ZCC010542260168', N'CPAC DRAIN BLOCK(T SHAPE)-HONEY BROWN', N'รางระบายน้ำซีแพค(ตัว T) - HONEY BROWN'),
    (475, N'ZCC010542260169', N'CPAC DRAIN BLOCK(T SHAPE)-PASSION BROWN', N'รางระบายน้ำซีแพค(ตัว T) - PASSION BROWN'),
    (476, N'ZCC010552260031', N'CPAC DRAIN BLOCK (STRAIGHT) - ORANGE', N'รางระบายน้ำซีแพค(แนวตรง) - สีส้ม'),
    (477, N'ZCC010552260161', N'CPAC DRAIN BLOCK (STRAIGHT) - GREY GREEN', N'รางระบายน้ำซีแพค(แนวตรง) - สีเทาเขียว'),
    (478, N'ZCC010552260162', N'CPAC DRAIN BLOCK (STRAIGHT) - MUSTARD', N'รางระบายน้ำซีแพค(แนวตรง) - สีมัสตาร์ด'),
    (479, N'ZCC010552260163', N'CPAC DRAIN BLOCK (STRAIGHT) - BURGUNDY', N'รางระบายน้ำซีแพค(แนวตรง) - สีแดงองุ่น'),
    (480, N'ZCC010552260166', N'CPAC DRAIN BLOCK (STRAIGHT)-MOSS GREY', N'รางระบายน้ำซีแพค(แนวตรง) - MOSS GREY'),
    (481, N'ZCC010552260167', N'CPAC DRAIN BLOCK(STRAIGHT)-LEMON YELLOW', N'รางระบายน้ำซีแพค(แนวตรง) - LEMON YELLOW'),
    (482, N'ZCC010552260168', N'CPAC DRAIN BLOCK(STRAIGHT) HONEY BROWN', N'รางระบายน้ำซีแพค(แนวตรง) - HONEY BROWN'),
    (483, N'ZCC010552260169', N'CPAC DRAIN BLOCK(STRAIGHT)-PASSION BROWN', N'รางระบายน้ำซีแพค(แนวตรง) - PASSION BROWN'),
    (484, N'ZCC010562260161', N'CPAC DRAIN BLOCK (90 DEGREE)- GREY GREEN', N'รางระบายน้ำซีแพค(90 องศา) - สีเทาเขียว'),
    (485, N'ZCC010562260162', N'CPAC DRAIN BLOCK (90 DEGREE) - MUSTARD', N'รางระบายน้ำซีแพค(90 องศา) - สีมัสตาร์ด'),
    (486, N'ZCC010562260163', N'CPAC DRAIN BLOCK (90 DEGREE) - BURGUNDY', N'รางระบายน้ำซีแพค(90 องศา) - สีแดงองุ่น'),
    (487, N'ZCC010562260166', N'CPAC DRAIN BLOCK(90 DEGREE)-MOSS GREY', N'รางระบายน้ำซีแพค(90 องศา) - MOSS GREY'),
    (488, N'ZCC010562260167', N'CPAC DRAIN BLOCK(90 DEGREE)-LEMON YELLOW', N'รางระบายน้ำซีแพค(90 องศา) - LEMON YELLOW'),
    (489, N'ZCC010562260168', N'CPAC DRAIN BLOCK(90 DEGREE)-HONEY BROWN', N'รางระบายน้ำซีแพค(90 องศา) - HONEY BROWN'),
    (490, N'ZCC010562260169', N'CPAC DRAINBLOCK(90 DEGREE)-PASSION BROWN', N'รางระบายน้ำซีแพค(90 องศา) - PASSION BROWN'),
    (491, N'ZCC010572260161', N'CPAC DRAIN BLOCK (DRAIN OUT1)-GREY GREEN', N'รางระบายน้ำซีแพค(DRAIN OUT1) - สีเทาเขียว'),
    (492, N'ZCC010572260162', N'CPAC DRAIN BLOCK (DRAIN OUT1) - MUSTARD', N'รางระบายน้ำซีแพค(DRAIN OUT1) - สีมัสตาร์ด'),
    (493, N'ZCC010572260163', N'CPAC DRAIN BLOCK (DRAIN OUT1) - BURGUNDY', N'รางระบายน้ำซีแพค(DRAIN OUT1) - สีแดงองุ่น'),
    (494, N'ZCC010572260166', N'CPACDRAINBLOCK(DRAIN OUT1)-MOSS GREY', N'รางระบายน้ำซีแพค(DRAIN OUT1) - MOSS GREY'),
    (495, N'ZCC010572260168', N'CPACDRAINBLOCK(DRAIN OUT1)-HONEY BROWN', N'รางระบายน้ำซีแพค(DRAIN OUT1) - HONEY BROWN'),
    (496, N'ZCC010582260161', N'CPAC DRAIN BLOCK (DRAIN OUT2)-GREY GREEN', N'รางระบายน้ำซีแพค(DRAIN OUT2) - สีเทาเขียว'),
    (497, N'ZCC010582260162', N'CPAC DRAIN BLOCK (DRAIN OUT2) - MUSTARD', N'รางระบายน้ำซีแพค(DRAIN OUT2) - สีมัสตาร์ด'),
    (498, N'ZCC010582260163', N'CPAC DRAIN BLOCK (DRAIN OUT2) - BURGUNDY', N'รางระบายน้ำซีแพค(DRAIN OUT2) - สีแดงองุ่น'),
    (499, N'ZCC010582260166', N'CPAC DRAIN BLOCK(DRAIN OUT2)-MOSS GREY', N'รางระบายน้ำซีแพค(DRAIN OUT2) - MOSS GREY'),
    (500, N'ZCC010582260168', N'CPACDRAINBLOCK(DRAIN OUT2)-HONEY BROWN', N'รางระบายน้ำซีแพค(DRAIN OUT2) - HONEY BROWN'),
    (501, N'ZCC010592260161', N'CPAC DRAIN BLOCK (DRAIN OUT3)-GREY GREEN', N'รางระบายน้ำซีแพค(DRAIN OUT3) - สีเทาเขียว'),
    (502, N'ZCC010592260162', N'CPAC DRAIN BLOCK (DRAIN OUT3) - MUSTARD', N'รางระบายน้ำซีแพค(DRAIN OUT3) - สีมัสตาร์ด'),
    (503, N'ZCC010592260163', N'CPAC DRAIN BLOCK (DRAIN OUT3) - BURGUNDY', N'รางระบายน้ำซีแพค(DRAIN OUT3) - สีแดงองุ่น'),
    (504, N'ZCC010592260166', N'CPAC DRAIN BLOCK(DRAIN OUT3)-MOSS GREY', N'รางระบายน้ำซีแพค(DRAIN OUT3) - MOSS GREY'),
    (505, N'ZCC010592260168', N'CPAC DRAIN BLOCK(DRAIN OUT3)-HONEY BROWN', N'รางระบายน้ำซีแพค(DRAIN OUT3) - HONEY BROWN'),
    (506, N'ZCC025010000011(ทดลอง)', N'CURB 15X30X100 CM. - GREY(ทดลอง)', N'ขอบคันหินใหญ่ทรงมน สีเทา(ทดลอง)'),
    (507, N'zcc02514000M011', N'ขอบลากูน่า มัลดิฟ15*30*100 ซ.ม. เกรย์รีฟ', N'ขอบลากูน่า มัลดิฟ15*30*100 ซ.ม. เกรย์รีฟ'),
    (509, N'ZCC025010000011', N'CURB 15X30X100 CM. - GREY', N'ขอบคันหินใหญ่ทรงมน สีเทา'),
    (510, N'ZCC025010000011DU', N'CURB 15X30X100 CM. - GREY', N'ขอบคันหินใหญ่ทรงมน สีเทาDU'),
    (511, N'ZCC025010000011A', N'CURB 15X30X100 (Klong Tuey Port) - GREY', N'ขอบคันหินใหญ่ทรงมน 15X30X100 ซม. สีเทา (คลองเตย)'),
    (512, N'ZCC025010000021', N'CURB 15X30X100 CM. - RED', N'ขอบคันหินใหญ่ทรงมน 15X30X100 ซม. สีแดง'),
    (513, N'ZCC025040000011', N'ANGULAR CURB GREY', N'ขอบคันหินใหญ่ทรงเหลี่ยม-สีเทา'),
    (514, N'ZCC025040000021', N'ANGULAR CURB RED', N'ขอบคันหินใหญ่ทรงเหลี่ยม-สีแดง'),
    (515, N'ZCC025040000031', N'ANGULAR CURB ORANGE', N'ขอบคันหินใหญ่ทรงเหลี่ยม-สีส้ม'),
    (516, N'ZCC025250000011', N'ANGULAR CURB 20X28.5X100 GREY', N'ขอบคันหินใหญ่ทรงเหลี่ยม 20X28.5X100 สีเทา '),
    (517, N'ZCC025020000011(พร้อมขอบเข้ามุม)', N'CURB 11X20X50 CM. - GREY', N'ขอบคันหินเล็กทรงมน สีเทา'),
    (518, N'ZCC025020000011du', N'CURB 11X20X50 CM. - GREY', N'ขอบคันหินเล็กทรงมน สีเทา DU'),
    (519, N'ZCC025020000011', N'CURB 11X20X50 CM. - GREY', N'ขอบคันหินเล็กทรงมน สีเทา'),
    (520, N'ZCC025100000011', N'CURB 11X20X50 CM. - GREY', N'ขอบคันหินเล็กทรงเหลี่ยม สีเทา'),
    (521, N'ZCC025130000161', N'CPAC GARDEN CURB (STRAIGHT) - GREY GREEN', N'ขอบชุดสวนซีแพค (ตรง) - GREY GREEN'),
    (522, N'ZCC025130000162', N'CPAC GARDEN CURB (STRAIGHT) - MUSTARD', N'ขอบชุดสวนซีแพค (ตรง) - MUSTARD'),
    (523, N'ZCC025130000163', N'CPAC GARDEN CURB (STRAIGHT) - BURGUNDY', N'ขอบชุดสวนซีแพค (ตรง) - สีแดงองุ่น'),
    (524, N'ZCC025130000166', N'CPAC GARDEN CURB(STRAIGHT)-MOSS GREY', N'ขอบชุดสวนซีแพค (ตรง)-MOSS GREY'),
    (525, N'ZCC025130000167', N'CPAC GARDEN CURB(STRAIGHT)-LEMON YELLOW', N'ขอบชุดสวนซีแพค (ตรง)-LEMON YELLOW'),
    (526, N'ZCC025130000168', N'CPAC GARDEN CURB(STRAIGHT)-HONEY BROWN', N'ขอบชุดสวนซีแพค (ตรง)-HONEY BROWN'),
    (527, N'ZCC025130000169', N'CPAC GARDEN CURB(STRAIGHT)-PASSION BROWN', N'ขอบชุดสวนซีแพค (ตรง)-PASSION BROWN'),
    (528, N'ZCC025150000166', N'CPAC GARDEN CURB(OUT BAND)-MOSS GREY', N'ขอบชุดสวนซีแพค (วงนอก)-MOSS GREY'),
    (529, N'ZCC025150000167', N'CPAC GARDEN CURB(OUT BAND)-LEMON YELLOW', N'ขอบชุดสวนซีแพค (วงนอก)-LEMON YELLOW'),
    (530, N'ZCC025150000168', N'CPAC GARDEN CURB(OUT BAND)-HONEY BROWN', N'ขอบชุดสวนซีแพค (วงนอก)-HONEY BROWN'),
    (531, N'ZCC025150000169', N'CPAC GARDEN CURB(OUT BAND)-PASSION BROWN', N'ขอบชุดสวนซีแพค (วงนอก)-PASSION BROWN'),
    (532, N'ZCC025160000166', N'CPAC GARDEN CURB(IN  BAND)-MOSS GREY', N'ขอบชุดสวนซีแพค (วงใน)-MOSS GREY'),
    (533, N'ZCC025160000167', N'CPAC GARDEN CURB(IN  BAND)-LEMON YELLOW', N'ขอบชุดสวนซีแพค (วงใน)-LEMON YELLOW'),
    (534, N'ZCC025160000168', N'CPAC GARDEN CURB(IN  BAND)-HONEY BROWN', N'ขอบชุดสวนซีแพค (วงใน)-HONEY BROWN'),
    (535, N'ZCC025160000169', N'CPAC GARDEN CURB(IN  BAND)-PASSION BROWN', N'ขอบชุดสวนซีแพค (วงใน)-PASSION BROWN'),
    (536, N'ZCC025170000166', N'CPAC GARDENCURB(CONN-OUT)-MOSS GREY', N'ขอบชุดสวนซีแพค (มุมนอก)-MOSS GREY'),
    (537, N'ZCC025170000167', N'CPAC GARDENCURB(CONN-OUT)-LEMON YELLOW', N'ขอบชุดสวนซีแพค (มุมนอก)-LEMON YELLOW'),
    (538, N'ZCC025170000168', N'CPAC GARDENCURB(CONN-OUT)-HONEY BROWN', N'ขอบชุดสวนซีแพค (มุมนอก)-HONEY BROWN'),
    (539, N'ZCC025170000169', N'CPAC GARDENCURB(CONN-OUT)-PASSION BROWN', N'ขอบชุดสวนซีแพค (มุมนอก)-PASSION BROWN'),
    (540, N'ZCC025180000166', N'CPAC GARDENCURB(CONN-IN)-MOSS GREY', N'ขอบชุดสวนซีแพค (มุมใน)-MOSS GREY'),
    (541, N'ZCC025180000167', N'CPAC GARDENCURB(CONN-IN)-LEMON YELLOW', N'ขอบชุดสวนซีแพค (มุมใน)-LEMON YELLOW'),
    (542, N'ZCC025180000168', N'CPAC GARDENCURB(CONN-IN)-HONEY BROWN', N'ขอบชุดสวนซีแพค (มุมใน)-HONEY BROWN'),
    (543, N'ZCC025180000169', N'CPAC GARDENCURB(CONN-IN)-PASSION BROWN', N'ขอบชุดสวนซีแพค (มุมใน)-PASSION BROWN'),
    (544, N'ZCC025110000161', N'CPAC GARDEN CURB (CONVEX) - GREY GREEN', N'ขอบชุดสวนซีแพค (วงนอก) - สีเทาเขียว'),
    (545, N'ZCC025110000162', N'CPAC GARDEN CURB (CONVEX) - MUSTARD', N'CPAC GARDEN CURB (CONVEX) - MUSTARD'),
    (546, N'ZCC025110000163', N'CPAC GARDEN CURB (CONVEX) - BURGUNDY', N'ขอบชุดสวนซีแพค (วงนอก) - สีแดงองุ่น'),
    (547, N'ZCC025120000161', N'CPAC GARDEN CURB (CONCAVE) - GREY GREEN', N'CPAC GARDEN CURB (CONCAVE) - GREY GREEN'),
    (548, N'ZCC025120000162', N'CPAC GARDEN CURB (CONCAVE) - MUSTARD', N'CPAC GARDEN CURB (CONCAVE) - MUSTARD'),
    (549, N'ZCC025120000163', N'CPAC GARDEN CURB (CONCAVE) - BURGUNDY', N'ขอบชุดสวนซีแพค (วงใน) - สีแดงองุ่น'),
    (550, N'ZCC010901620059', N'TRUE NATURE 6X15X2 - BROWN (PACK)', N'TRUE NATURE 6X15X2 - BROWN (PACK)'),
    (551, N'ZCC010901620011', N'TRUE NATURE 6X15X2 - GREY (PACK)', N'TRUE NATURE 6X15X2 - GREY (PACK)'),
    (552, N'ZCC010901620091', N'TRUE NATURE 6X15X2 - WHITE (PACK)', N'TRUE NATURE 6X15X2 - WHITE (PACK)'),
    (553, N'ZCC010901620501', N'TRUE NATURE 6X15X2 - BEACH BRONZE (PACK)', N'TRUE NATURE 6X15X2 - BEACH BRONZE (PACK)'),
    (554, N'ZCC010901620505', N'TRUE NATURE 6X15X2 - CORAL YELLOW (PACK)', N'TRUE NATURE 6X15X2 - CORAL YELLOW (PACK)'),
    (555, N'ZCC010901620504', N'TRUE NATURE 6X15X2 - DESERT BROWN (PACK)', N'TRUE NATURE 6X15X2 - DESERT BROWN (PACK)'),
    (556, N'ZCC010901620503', N'TRUE NATURE 6X15X2 - EARTH ORANGE (PACK)', N'TRUE NATURE 6X15X2 - EARTH ORANGE (PACK)'),
    (557, N'ZCC010901620502', N'TRUE NATURE 6X15X2 - LAVA RED (PACK)', N'TRUE NATURE 6X15X2 - LAVA RED (PACK)'),
    (558, N'ZCC010901620506', N'TRUE NATURE 6X15X2 - ROCKY BLACK (PACK)', N'TRUE NATURE 6X15X2 - ROCKY BLACK (PACK)'),
    (559, N'ZCC010931620011', N'TRUE NATURE CORNER GREY 15x6x2 (PACK)', N'TRUE NATURE เข้ามุม GREY 15x6x2 (PACK)'),
    (560, N'ZCC010931620059', N'TRUE NATURE CORNER BROWN 15x6x2 (PACK)', N'TRUE NATURE เข้ามุม BROWN 15x6x2 (PACK)'),
    (561, N'ZCC010931620091', N'TRUE NATURE CORNER WHITE 15x6x2 (PACK)', N'TRUE NATURE เข้ามุม WHITE 15x6x2 (PACK)'),
    (562, N'ZCC010931620501', N'TRUE NATURE CORNER BEACH BRONZE 15x6x2 (PACK)', N'TRUE NATURE เข้ามุม BEACH BRONZE 15x6x2 (PACK)'),
    (563, N'ZCC010931620502', N'TRUE NATURE CORNER LAVA RED 15x6x2 (PACK)', N'TRUE NATURE เข้ามุม LAVA RED 15x6x2 (PACK)'),
    (564, N'ZCC010931620503', N'TRUE NATURE CORNER EARTH ORANGE 15x6x2 (PACK)', N'TRUE NATURE เข้ามุม EARTH ORANGE 15x6x2 (PACK)'),
    (565, N'ZCC010931620504', N'TRUE NATURE CORNER DESERT BROWN 15x6x2 (PACK)', N'TRUE NATURE เข้ามุม DESERT BROWN 15x6x2 (PACK)'),
    (566, N'ZCC010931620505', N'TRUE NATURE CORNER CORAL YELLOW 15x6x2 (PACK)', N'TRUE NATURE เข้ามุม CORAL YELLOW 15x6x2 (PACK)'),
    (567, N'ZCC010931620506', N'TRUE NATURE CORNER ROCKY BLACK 15x6x2 (PACK)', N'TRUE NATURE เข้ามุม ROCKY BLACK 15x6x2 (PACK)'),
    (568, N'ZCC025220000014', N'THIN CURB  20x60x8 CM. BLACK GREY', N'ขอบตกแต่งแบบบาง 20x60x8 ซม. BLACK GREY'),
    (569, N'ZCC025220000023', N'THIN CURB  20x60x8 CM. DARK RED', N'ขอบตกแต่งแบบบาง 20x60x8 ซม. DARK RED'),
    (570, N'ZCC025220000051', N'THIN CURB  20x60x8 CM. LIGHT BROWN', N'ขอบตกแต่งแบบบาง 20x60x8 ซม. LIGHT BROWN'),
    (571, N'ZCC025220000052', N'THIN CURB  20x60x8 CM. DARK BROWN', N'ขอบตกแต่งแบบบาง 20x60x8 ซม. DARK BROWN'),
    (577, N'ZCC025270000011', N'คอนกรีตล้อมคอกต้นไม้ แบบA ขนาด 120X120 ซม.', N'คอนกรีตล้อมคอกต้นไม้ แบบA ขนาด 120X120 ซม.'),
    (578, N'ZCC025260000011', N'คอนกรีตล้อมคอกต้นไม้ แบบC ขนาด 7X30X8 ซม.', N'คอนกรีตล้อมคอกต้นไม้ แบบC ขนาด 7X30X8 ซม.'),
    (579, N'ZCC038135510061', N'Growing Unit  50x50x19 cm. – BLACK', N'กระบะปลูก ขนาด 50x50x19 ซม.- สีดำ '),
    (581, N'ZCCFAA002110001-ผลิตพร้อมทับหลังเล็ก', N'CPAC CASTLE STONE 20x10x10 - BUFF', N'CASTLE ตัวก้อน 20x10x10 - BUFF'),
    (582, N'ZCCFAA002110002-ผลิตพร้อมทับหลังเล็ก', N'CPAC CASTLE STONE 20x10x10 - TAN', N'CASTLE ตัวก้อน 20x10x10 - TAN'),
    (583, N'ZCC010901620059-1', N'TRUE NATURE 6X15X2 - BROWN', N'TRUE NATURE 6X15X2 - BROWN'),
    (584, N'ZCC010901620011-1', N'TRUE NATURE 6X15X2 - GREY', N'TRUE NATURE 6X15X2 - GREY'),
    (585, N'ZCC010901620091-1', N'TRUE NATURE 6X15X2 - WHITE', N'TRUE NATURE 6X15X2 - WHITE'),
    (586, N'ZCC010901620501-1', N'TRUE NATURE 6X15X2 -BEACH BRONZE', N'TRUE NATURE 6X15X2 - BEACH BRONZE'),
    (587, N'ZCC010901620505-1', N'TRUE NATURE 6X15X2 -CORAL YELLOW', N'TRUE NATURE 6X15X2 - CORAL YELLOW'),
    (588, N'ZCC010901620504-1', N'TRUE NATURE 6X15X2 -DESERT BROWN', N'TRUE NATURE 6X15X2 - DESERT BROWN'),
    (589, N'ZCC010901620503-1', N'TRUE NATURE 6X15X2 -EARTH ORANGE', N'TRUE NATURE 6X15X2 - EARTH ORANGE'),
    (590, N'ZCC010901620502-1', N'TRUE NATURE 6X15X2 -LAVA RED', N'TRUE NATURE 6X15X2 - LAVA RED'),
    (591, N'ZCC010901620506-1', N'TRUE NATURE 6X15X2 -ROCKY  BLACK', N'TRUE NATURE 6X15X2 - ROCKY BLACK'),
    (592, N'ZCC010931620011-1', N'TRUE NATURE CORNER GREY 15x6x2', N'TRUE NATURE เข้ามุม GREY 15x6x2'),
    (593, N'ZCC010931620059-1', N'TRUE NATURE CORNER BROWN 15x6x2', N'TRUE NATURE เข้ามุม BROWN 15x6x2'),
    (594, N'ZCC010931620091-1', N'TRUE NATURE CORNER WHITE 15x6x2', N'TRUE NATURE เข้ามุม WHITE 15x6x2'),
    (595, N'ZCC010931620501-1', N'TRUE NATURE CORNER BEACH BRONZE 15x6x2', N'TRUE NATURE เข้ามุม BEACH BRONZE 15x6x2'),
    (596, N'ZCC010931620502-1', N'TRUE NATURE CORNER LAVA RED 15x6x2', N'TRUE NATURE เข้ามุม LAVA RED 15x6x2'),
    (597, N'ZCC010931620503-1', N'TRUE NATURE CORNER EARTH ORANGE 15x6x2', N'TRUE NATURE เข้ามุม EARTH ORANGE 15x6x2'),
    (598, N'ZCC010931620504-1', N'TRUE NATURE CORNER DESERT BROWN 15x6x2', N'TRUE NATURE เข้ามุม DESERT BROWN 15x6x2'),
    (599, N'ZCC010931620505-1', N'TRUE NATURE CORNER CORAL YELLOW 15x6x2', N'TRUE NATURE เข้ามุม CORAL YELLOW 15x6x2'),
    (600, N'ZCC010931620506-1', N'TRUE NATURE CORNER ROCKY BLACK 15x6x2', N'TRUE NATURE เข้ามุม ROCKY BLACK 15x6x2'),
    (602, N'ZCC011270080112', N'MINI COBBLE : SMALL : MOSS GREY', N'MINI COBBLE : วงเล็ก : สี MOSS GREY'),
    (603, N'ZCC011270080115', N'MINI COBBLE : SMALL : ROSY PINK', N'MINI COBBLE : วงเล็ก : สี ROSY PINK'),
    (604, N'ZCC011270080116', N'MINI COBBLE : SMALL : PLUM PURPLE', N'MINI COBBLE : วงเล็ก : สี PLUM PURPLE'),
    (605, N'ZCC011270080118', N'MINI COBBLE : SMALL : LEMON GREEN', N'MINI COBBLE : วงเล็ก : สี LEMON GREEN'),
    (606, N'ZCC011270080119', N'MINI COBBLE : SMALL : MOCCA BROWN', N'MINI COBBLE : วงเล็ก : สี MOCCA BROWN'),
    (607, N'ZCC011270080113', N'MINI COBBLE : SMALL : LILY PURPLE', N'MINI COBBLE : วงเล็ก : สี LILY PURPLE'),
    (608, N'ZCC011270080114', N'MINI COBBLE : SMALL : COFFEE BROWN', N'MINI COBBLE : วงเล็ก : สี COFFEE BROWN'),
    (609, N'ZCC011270080117', N'MINI COBBLE : SMALL : MOONY YELLOW', N'MINI COBBLE : วงเล็ก : สี MOONY YELLOW'),
    (610, N'ZCCBMAAAA01', N'GARDEN  SET 1 - BUFF', N'GARDEN  SET 1 - BUFF'),
    (611, N'ZCCBMAAAA02', N'GARDEN  SET 2 - BUFF', N'GARDEN  SET 2 - BUFF'),
    (612, N'ZCCBMAAAA03', N'GARDEN  SET 3 - BUFF', N'GARDEN  SET 3 - BUFF'),
    (613, N'ZCCBMAAAA04', N'GARDEN  SET 4 - BUFF', N'GARDEN  SET 4 - BUFF'),
    (614, N'ZCCBMAAAA05', N'GARDEN  SET 5 - BUFF', N'GARDEN  SET 5 - BUFF'),
    (615, N'ZCCBMAAAA06', N'GARDEN  SET 6 - BUFF', N'GARDEN  SET 6 - BUFF'),
    (616, N'ZCCBMAAAA07', N'GARDEN  SET 7 - BUFF', N'GARDEN  SET 7 - BUFF'),
    (617, N'ZCCBMAAAA08', N'GARDEN  SET 8 - BUFF', N'GARDEN  SET 8 - BUFF'),
    (618, N'ZCCBMAAAA09', N'GARDEN  SET 9 - BUFF', N'GARDEN  SET 9 - BUFF'),
    (619, N'ZCCBMAAAA10', N'GARDEN  SET 10 - BUFF', N'GARDEN  SET 10 - BUFF'),
    (620, N'ZCCBMAAAA11', N'GARDEN  SET 11 - BUFF', N'GARDEN  SET 11 - BUFF'),
    (621, N'ZCCBMAAAA12', N'GARDEN  SET 12 - BUFF', N'GARDEN  SET 12 - BUFF'),
    (622, N'ZCCBMAAAA13', N'GARDEN  SET 13 - BUFF', N'GARDEN  SET 13 - BUFF'),
    (623, N'ZCCBMAAAA14', N'GARDEN  SET 14 - BUFF', N'GARDEN  SET 14 - BUFF'),
    (624, N'ZCCBMAAAB01', N'GARDEN  SET 1 - TAN', N'GARDEN  SET 1 - TAN'),
    (625, N'ZCCBMAAAB02', N'GARDEN  SET 2 - TAN', N'GARDEN  SET 2 - TAN'),
    (626, N'ZCCBMAAAB03', N'GARDEN  SET 3 - TAN', N'GARDEN  SET 3 - TAN'),
    (627, N'ZCCBMAAAB04', N'GARDEN  SET 4 - TAN', N'GARDEN  SET 4 - TAN'),
    (628, N'ZCCBMAAAB05', N'GARDEN  SET 5 - TAN', N'GARDEN  SET 5 - TAN'),
    (629, N'ZCCBMAAAB06', N'GARDEN  SET 6 - TAN', N'GARDEN  SET 6 - TAN'),
    (630, N'ZCCBMAAAB07', N'GARDEN  SET 7 - TAN', N'GARDEN  SET 7 - TAN'),
    (631, N'ZCCBMAAAB08', N'GARDEN  SET 8 - TAN', N'GARDEN  SET 8 - TAN'),
    (632, N'ZCCBMAAAB09', N'GARDEN  SET 9 - TAN', N'GARDEN  SET 9 - TAN'),
    (633, N'ZCCBMAAAB10', N'GARDEN  SET 10 - TAN', N'GARDEN  SET 10 - TAN'),
    (634, N'ZCCBMAAAB11', N'GARDEN  SET 11 - TAN', N'GARDEN  SET 11 - TAN'),
    (635, N'ZCCBMAAAB12', N'GARDEN  SET 12 - TAN', N'GARDEN  SET 12 - TAN'),
    (636, N'ZCCBMAAAB13', N'GARDEN  SET 13 - TAN', N'GARDEN  SET 13 - TAN'),
    (637, N'ZCCBMAAAB14', N'GARDEN  SET 14 - TAN', N'GARDEN  SET 14 - TAN'),
    (639, N'PM', N'PM', N'PM'),
    (640, N'ไม่มีผลิต', N'ไม่มีผลิต', N'ไม่มีผลิต'),
    (641, N'หยุดประจำสัปดาห์', N'หยุดประจำสัปดาห์', N'หยุดประจำสัปดาห์'),
    (642, N'หยุดวันเสาร์', N'หยุดวันเสาร์', N'หยุดวันเสาร์'),
    (643, N'หยุดวันอาทิตย์', N'หยุดวันอาทิตย์', N'หยุดวันอาทิตย์'),
    (644, N'หยุดวันจักรี', N'หยุดวันจักรี', N'หยุดวันจักรี'),
    (645, N'หยุดวันอาสฬบูชา', N'หยุดวันอาสฬบูชา', N'หยุดวันอาสฬบูชา'),
    (646, N'หยุดวันเข้าพรรษา', N'หยุดวันเข้าพรรษา', N'หยุดวันเข้าพรรษา'),
    (647, N'หยุดวันเฉลิมพระชนมพรรษาฯ', N'หยุดวันเฉลิมพระชนมพรรษาฯ', N'หยุดวันเฉลิมพระชนมพรรษาฯ'),
    (648, N'ไม่มีสินค้าเข้า stock', N'ไม่มีสินค้าเข้า stock', N'ไม่มีสินค้าเข้า stock'),
    (649, N'หยุดผลิตวันขึ้นปีใหม่', N'หยุดผลิตวันขึ้นปีใหม่', N'หยุดผลิตวันขึ้นปีใหม่'),
    (650, N'หยุดผลิตวันสงกรานต์', N'หยุดผลิตวันสงกรานต์', N'หยุดผลิตวันสงกรานต์'),
    (651, N'หยุดเตรียม OVERHAUL', N'หยุดเตรียม OVERHAUL', N'หยุดเตรียม OVERHAUL'),
    (652, N'หยุด OVERHAUL', N'หยุด OVERHAUL', N'หยุด OVERHAUL'),
    (653, N'ปรับปรุงโรงงาน', N'ปรับปรุงโรงงาน', N'ปรับปรุงโรงงาน'),
    (654, N'ZCC01002010001111', N'ผสมคอนกรีตเทพื้นให้โรงซ่อม', N'ผสมคอนกรีตเทพื้นให้โรงซ่อม'),
    (656, N'ZCC0100201000111', N'ทดลองผลิตUNI PAVE(HS) 10 CM - GREY ', N'ทดลองคดกริช 10 ซม. สีเทา (HS) 6/3/52'),
    (657, N'ZCC025290000011', N'คอนกรีตล้อมคอกต้นไม้ สีเทา (1 ชุด)', N'คอนกรีตล้อมคอกต้นไม้ สีเทา (1 ชุด)'),
    (658, N'ZCC011213350011', N'บล็อคตกแต่งพื้นลายดอกไม้ 30x30x5 สีเทา', N'บล็อคตกแต่งพื้นลายดอกไม้ 30x30x5 สีเทา'),
    (660, N'ZCC010470080112-1', N'COBBLE STONE RT4-COOL PLUS : Earth Grey (ทดลอง)', N'COBBLE STONE RT4-COOL PLUS : Earth Grey (ทดลอง)'),
    (661, N'ZCC010470080118-1', N'COBBLE STONE RT4-COOL PLUS : Earrth Green (ทดลอง)', N'COBBLE STONE RT4-COOL PLUS : Earrth Green (ทดลอง)'),
    (662, N'ZCC010470080114-1', N'COBBLE STONE RT4 Cool Plus Eart Brown (ทดลอง )', N'COBBLE STONE RT4 Cool Plus Eart Brown'),
    (663, N'ZCC010470080117-1', N'COBBLE STONE RT4 Cool Plus Eart Yellow (ทดลอง)', N'COBBLE STONE RT4 Cool Plus Eart Yellow (ทดลอง)'),
    (664, N'ZCC010120090081-1', N'TURF STONE 9 CM -COOL PLUS : Earrth Green (ทดลอง)', N'บล็อคปลูกหญ้า 9 ซม.COOL PLUS : Earrth Green (ทดลอง)'),
    (665, N'ZCC010460080112-1', N'COBBLE STONE RT3-COOL PLUS : Earth Grey (ทดลอง)', N'COBBLE STONE RT3-COOL PLUS : Earth Grey (ทดลอง)'),
    (666, N'ZCC010460080118-1', N'COBBLE STONE RT3-COOL PLUS : Earrth Green (ทดลอง)', N'COBBLE STONE RT3-COOL PLUS : Earrth Green (ทดลอง)'),
    (667, N'ZCC010460080119-1', N'COBBLE STONE RT3 Cool Plus Eart Brown (ทดลอง )', N'COBBLE STONE RT3 Cool Plus Eart Brown (ทดลอง )'),
    (668, N'ZCC010460080117-1', N'COBBLE STONE RT3 Cool Plus Eart Yellow (ทดลอง)', N'COBBLE STONE RT3 Cool Plus Eart Yellow (ทดลอง)'),
    (669, N'ZCCFAB002180006-1', N'CASTLE SMOOTH  20x10x8 - งาช้าง (ทดลอง)', N'CASTLE SMOOTH ตัวก้อน 20x10x8 - งาช้าง (ทดลอง)'),
    (670, N'ZCC01002012001-1-1', N'UNI(HS) 12 CM - GREY (Test)', N'คดกริช 12 ซม. สีเทา (HS)  (Test)'),
    (672, N'ZCC0106A1260507', N'Cool Plus Shape D 10x20x6 CM. Soft Green', N'Cool Plus Shape D 10x20x6 CM. สีเขียว'),
    (673, N'ZCC011411260508', N'Cool Plus Shape D 10x20x6 CM. Sea Blue', N'Cool Plus Shape D 10x20x6 CM. สีฟ้า'),
    (674, N'ZCC011411260509', N'Cool Plus Shape D 10x20x6 CM. Saddle Brown', N'Cool Plus Shape D 10x20x6 CM. สีน้ำตาล'),
    (675, N'ZCC011411260510', N'Cool Plus Shape D 10x20x6 CM. Jazzy Orane', N'Cool Plus Shape D 10x20x6 CM. สีส้ม'),
    (676, N'ZCC011460060507', N'Cool Plus Shape A  9x12x6 Soft Green', N'Cool Plus Shape A 9x12x6 CM. สีเขียว'),
    (677, N'ZCC011460060508', N'Cool Plus Shape A  9x12x6 Sea Blue', N'Cool Plus Shape A 9x12x6 CM. สีฟ้า'),
    (678, N'ZCC011460060509', N'Cool Plus Shape A  9x12x6 Saddle Brown', N'Cool Plus Shape A 9x12x6 CM. สีน้ำตาล'),
    (679, N'ZCC011460060510', N'Cool Plus Shape A  9x12x6 Jazzy Orange', N'Cool Plus Shape A 9x12x6 CM. สีส้ม'),
    (680, N'ZCC0106A0800011', N'Cool Plus RT2 6 CM. Grey', N'Cool Plus RT2 6 CM. สีเทา'),
    (681, N'ZCC0106A0800061', N'Cool Plus RT2 6 CM. Black', N'Cool Plus RT2 6 CM. สีดำ'),
    (682, N'ZCC011470060507', N'Cool Plus Shape B 11.8x11.8x6 Soft Green', N'Cool Plus Shape B 11.8x11.8x6 CM. สีเขียว'),
    (683, N'ZCC011470060508', N'Cool Plus Shape B 11.8x11.8x6 Sea Blue', N'Cool Plus Shape B 11.8x11.8x6 CM. สีฟ้า'),
    (684, N'ZCC011470060509', N'Cool Plus Shape B 11.8x11.8x6 Saddle Brown', N'Cool Plus Shape B 11.8x11.8x6 CM. สีน้ำตาล'),
    (685, N'ZCC011470060510', N'Cool Plus Shape B 11.8x11.8x6 Jazzy Orange', N'Cool Plus Shape B 11.8x11.8x6 CM. สีส้ม'),
    (686, N'ZCC011480060507', N'Cool Plus Shape C 17.8x11.77x6 Soft Green', N'Cool Plus Shape C 17.8x11.77x6 CM. สีเขียว'),
    (687, N'ZCC011480060508', N'Cool Plus Shape C 17.8x11.77x6 Sea Blue', N'Cool Plus Shape C 17.8x11.77x6 CM. สีฟ้า'),
    (688, N'ZCC011480060509', N'Cool Plus Shape C17.8x11.77x6 Saddle Brown', N'Cool Plus Shape C 17.8x11.77x6 CM. สีน้ำตาล'),
    (689, N'ZCC011480060510', N'Cool Plus Shape C17.8x11.77x6 Jazzy Orange', N'Cool Plus Shape C 17.8x11.77x6 CM. สีส้ม'),
    (690, N'ZCC0106A2260507', N'Cool Plus 20x20x6 CM. Soft Green', N'Cool Plus 20x20x6 CM. สีเขียว'),
    (692, N'ZCC010010060011 - N', N'UNI PAVE 6 CM -GREY', N'คดกริช 6 ซม. สีเทา  - Normal'),
    (693, N'ZCC010010060011 - S', N'UNI PAVE 6 CM -GREY', N'คดกริช 6 ซม. สีเทา  - Survival Plane'),
    (694, N'ZCC010010060011 - 1', N'UNI PAVE 6 CM -GREY', N'คดกริช 6 ซม. สีเทา - สูตร 1'),
    (695, N'ZCC010010060011 - 2', N'UNI PAVE 6 CM -GREY', N'คดกริช 6 ซม. สีเทา - สูตร 2'),
    (696, N'ZCC010010060011 - 3', N'UNI PAVE 6 CM -GREY', N'คดกริช 6 ซม. สีเทา - สูตร 3'),
    (697, N'ZCC010010060011 - 4', N'UNI PAVE 6 CM -GREY', N'คดกริช 6 ซม. สีเทา - สูตร 4'),
    (698, N'ZCC010010060011 - 5', N'UNI PAVE 6 CM -GREY', N'คดกริช 6 ซม. สีเทา - สูตร 5'),
    (700, N'ZCC010010060011 - 11', N'UNI PAVE 6 CM - GREY', N'คดกริช 6 ซม. สีเทา - สูตร 1'),
    (701, N'ZCC010010060011 - 22', N'UNI PAVE 6 CM - RED', N'คดกริช 6 ซม. สีแดง - สูตร 2'),
    (702, N'ZCC010010060011 - 33', N'UNI PAVE 6 CM - RED', N'คดกริช 6 ซม. สีแดง - สูตร 3 (หินทรายจ่าสาย)'),
    (703, N'ZCC010010060011 - 44', N'UNI PAVE 6 CM - RED', N'คดกริช 6 ซม. สีแดง - สูตร 4 (หินทรายจ่าสาย)'),
    (704, N'ZCC010010060011 - 55', N'UNI PAVE 6 CM - GREY', N'คดกริช 6 ซม. สีเทา - สูตร 5'),
    (705, N'ZCC010010060011 - 66', N'UNI PAVE 6 CM - GREY', N'คดกริช 6 ซม. สีเทา - สูตร 6'),
    (719, N'ZCC010010060011-4', N'UNI PAVE 6 CM - GREY (Normal)', N'คดกริช 6 ซม. สีเทา ((Normal)'),
    (720, N'ZCC010010060011-5', N'UNI PAVE 6 CM - GREY (Survival Plan)', N'คดกริช 6 ซม. สีเทา (Survival Plan)'),
    (721, N'ZCC010010060011-6', N'UNI PAVE 6 CM - GREY (Fighting product)', N'คดกริช 6 ซม. สีเทา (Fighting product)'),
    (723, N'ZCC010010060011-11', N'UNI PAVE 6 CM - GREY (ทดลองสูตร F6)', N'คดกริช 6 ซม. สีเทา (ทดลองสูตร F6)'),
    (724, N'ZCC010010060011-22', N'UNI PAVE 6 CM - GREY (ทดลองสูตร F14)', N'คดกริช 6 ซม. สีเทา (ทดลองสูตร F14)'),
    (725, N'ZCC010211260011', N'LAGUNA 10X20X6 cm. GRAVEL', N'ลากูน่า 10x20x6  ซม. กรวดล้าง'),
    (726, N'ZCC01186126M011', N'ลากูน่า มัลดีฟ  พอรัส 10x20x6 ซม. สีเกรย์รีฟ', N'ลากูน่า มัลดีฟ  พอรัส 10x20x6 ซม. สีเกรย์รีฟ'),
    (727, N'ZCC01186126M021', N'ลากูน่า มัลดีฟ  พอรัส 10x20x6 ซม. สีแดง', N'ลากูน่า มัลดีฟ  พอรัส 10x20x6 ซม. สีแดง'),
    (728, N'ZCC01186126M061', N'ลากูน่า มัลดีฟ 10x20x6 ซม. สีแบล็คเพิร์ล', N'ลากูน่า มัลดีฟ พอรัส 10x20x6 ซม. สีแบล็คเพิร์ล'),
    (729, N'ZCC01041126M021', N'Laguna Maldives10x20x6 cm. - Red Coral', N'ลากูน่า มัลดีฟ 10x20x6 ซม. สีแดง'),
    (730, N'ZCC01041126M091', N'Laguna Maldives10x20x6 cm. - White Beach', N'ลากูน่า มัลดีฟ 10x20x6 ซม. สีขาว'),
    (731, N'ZCC01041126M041', N'Laguna Maldives10x20x6 cm - Yellow Sandy', N'ลากูน่า มัลดีฟ 10x20x6 ซม. สีเหลือง'),
    (732, N'ZCC01041126M061', N'Laguna Maldives10x20x6 cm. - Black Pearl', N'ลากูน่า มัลดีฟ 10x20x6 ซม. สีดำ'),
    (733, N'ZCC01041126M011', N'Laguna Maldives10x20x6 cm. - Grey Reef', N'ลากูน่า มัลดีฟ 10x20x6 ซม. สีเกรย์รีฟ'),
    (734, N'ZCC010411260011', N'LAGUNA 10X20X6 cm. GREY', N'ลากูน่า 10x20x6  ซม. เทา'),
    (735, N'ZCC010411260023', N'LAGUNA 10X20X6 cm. CRIMSON', N'ลากูน่า 10x20x6  ซม. เลือดหมู'),
    (736, N'ZCC010411260031', N'LAGUNA 10X20X6 cm. ORANGE', N'ลากูน่า 10x20x6  ซม. ส้ม'),
    (737, N'ZCC010411260061', N'LAGUNA 10X20X6 cm. BLACK', N'ลากูน่า 10x20x6  ซม.ดำ'),
    (738, N'ZCC010411260091', N'LAGUNA 10X20X6 cm. WHITE', N'ลากูน่า 10x20x6  ซม. ขาว'),
    (739, N'ZCC010212260011', N'LAGUNA 20X20X6 cm. GRAVEL', N'ลากูน่า 20x20x6  ซม. กรวดล้าง'),
    (740, N'ZCC01041226M011', N'ลากูน่า 20x20x6  ซม.มัลดีฟเทา', N'ลากูน่า 20x20x6  ซม.มัลดีฟเทา'),
    (741, N'ZCC01041226M021', N'LAGUNA 20X20X6 cm. แดง', N'ลากูน่า 20x20x6  ซม.มัลดีฟแดง'),
    (742, N'ZCC01041226M041', N'LAGUNA 20X20X6 cm.เหลือง', N'ลากูน่า 20x20x6  ซม.มัลดีฟ เหลือง'),
    (743, N'ZCC010412260011', N'LAGUNA 20X20X6 cm. GREY', N'ลากูน่า 20x20x6  ซม. เทา'),
    (744, N'ZCC010412260023', N'LAGUNA 20X20X6 cm. CREMSON', N'ลากูน่า 20x20x6  ซม. เลือดหมู'),
    (745, N'ZCC010412260031', N'LAGUNA 20X20X6 cm. ORANGE', N'ลากูน่า 20x20x6  ซม. ส้ม'),
    (746, N'ZCC010412260061', N'LAGUNA 20X20X6 cm. BLACK', N'ลากูน่า 20x20x6  ซม. ดำ'),
    (747, N'ZCC010412260091', N'LAGUNA 20X20X6 cm. WHITE', N'ลากูน่า 20x20x6  ซม. ขาว'),
    (748, N'ZCC010413361LG4', N'Laguna 30x30x6 cm. - Grey Stone(SG) พระเมรุมาศ ', N'Laguna 30x30x6 cm. - Grey Stone(SG)พระเมรุมาศ'),
    (749, N'ZCC010413361LG3', N'Laguna 30x30x6 cm. - Grey Stone(GGN)พระเมรุมาศ', N'Laguna 30x30x6 cm. - Grey Stone(GGN)พระเมรุมาศ'),
    (750, N'zcc010413369LG7', N'Laguna30x30x6 cm. - White Stone(SW)พระเมรุมาศ', N'Laguna30x30x6 cm. - White Stone(SW)พระเมรุมาศ'),
    (751, N'zcc010413369LG6', N'Laguna30x30x6 cm. - White Stone(G100)พระเมรุมาศ', N'Laguna30x30x6 cm. - White Stone(G100)พระเมรุมาศ'),
    (752, N'zcc010413364LG9', N'Laguna30x30x6 cm. - Yellow Stone(Gsy3)พระเมรุมาศ', N'Laguna30x30x6 cm. - Yellow Stone(Gsy3)พระเมรุมาศ'),
    (753, N'zcc010413364LG8', N'Laguna30x30x6 cm. - Yellow Stone(Mgy3)พระเมรุมาศ', N'Laguna30x30x6 cm. - Yellow Stone(Mgy3)พระเมรุมาศ'),
    (754, N'ZCC010413365LG10', N'Laguna30x30x6 cm. -Brown Stone(ดิน)พระเมรุมาศ', N'Laguna30x30x6 cm. -Brown Stone(ดิน)พระเมรุมาศ'),
    (755, N'ZCC0102A3360011', N'LINER 30*30*6cm ดาราวดี เทา', N'ศิลาเหลี่ยม 30*30*6cm ดาราวดี สีเทา'),
    (756, N'ZCC0102A3360031', N'LINER 30*30*6cm ดาราวดี  สีส้ม', N'ศิลาเหลี่ยม 30*30*6cm ดาราวดี สีส้ม'),
    (757, N'ZCC0102A3360051', N'LINER 30*30*6cm ดาราวดี  สีน้ำตาล', N'ศิลาเหลี่ยม 30*30*6cm ดาราวดี สีน้ำตาล'),
    (759, N'ZCC01041336M011', N'Laguna Maldives30x30x6 cm. - Grey Reef', N'ลากูน่า มัลดีฟ 30x30x6 ซม. สีเทา'),
    (760, N'ZCC01041336M021', N'Laguna Maldives30x30x6 cm. - Red Coral', N'ลากูน่า มัลดีฟ 30x30x6 ซม. สีแดง'),
    (761, N'zcc010141366m011', N'Laguna Maldives30x30x6 cm. - White Beach', N'ลากูน่า มัลดีฟ 30x30x6 ซม. สีขาว'),
    (763, N'ZCC01041336M061', N'Laguna Maldives30x30x6 cm. - Black Pearl', N'ลากูน่า มัลดีฟ 30x30x6 ซม. สีดำ'),
    (764, N'ZCC01041336M041', N'Laguna Maldives30x30x6 cm - Yellow Sandy', N'ลากูน่า มัลดีฟ 30x30x6 ซม. สีเหลือง'),
    (766, N'ZCC01041556M011', N'Laguna 50x50x6 cm. -GREY Ston มัลดีฟ', N'Laguna มัลดีฟ 50*50*6 ซม. สีเทา'),
    (767, N'ZCC01041556M091', N'Laguna 50x50x6 cm. -White Ston มัลดีฟ', N'Laguna มัลดีฟ 50*50*6 ซม. สีขาว'),
    (768, N'zcc010165560051', N'Laguna 50x50x6 cm. น้ำตาล', N'Laguna 50x50x6 cm. น้ำตาล'),
    (772, N'ZCC01041665M061', N'Laguna 60x60x5 cm. ดำ มัลดีฟ', N'Laguna 60x60x5 cm. ดำมัลดีฟ'),
    (773, N'ZCC010415564LG2', N'Laguna 50x50x6 cm. -Yellow Ston (MGY3)', N'Laguna 50x50x6 cm. -Yellow Ston (MGY3)'),
    (774, N'zcc01186336M011', N'Laguna Maldives30x30x6 cm. POROUS เทา', N'ลากูน่าบล็อกระบายน้ำเร็ว 30x30x6 CM เทา'),
    (775, N'ZCC010283360021', N'LAGUNA 30X30X6 -  Rad', N'ลากูน่า 30x30x6  ซม. แดง'),
    (776, N'ZCC010283360041', N'LAGUNA 30X30X6 -  Yellow', N'ลากูน่า 30x30x6  ซม. เหลือง'),
    (777, N'ZCC010283360000', N'LAGUNA 30X30X6 - GREY', N'ลากูน่า 30x30x6  ซม. เทา'),
    (778, N'ZCC010413360023', N'LAGUNA 30X30X6 - CRIMSON', N'ลากูนา 30X30X6 ซม. เลือดหมู'),
    (779, N'ZCC010413360031', N'LAGUNA 30X30X6 - ORANGE ', N'ลากูนา 30X30X6 ซม. หินส้ม '),
    (780, N'ZCC010413360061', N'LAGUNA 30X30X6 - BLACK', N'ลากูนา 30X30X6 ซม. ดำ'),
    (781, N'ZCC010413360091', N'LAGUNA 30X30X6 - WHITE', N'ลากูนา 30X30X6 ซม. ขาว'),
    (782, N'zcc010411169LG5', N'Laguna 10x10x6 cm. - White ston(G100)พระเมรุมาศ', N'Laguna 10x10x6 cm. - White ston(G100)พระเมรุมาศ'),
    (789, N'ZCC01041116M011-1', N'Laguna Maldives 10x10x6 cm. - Grey Reef', N'ลากูน่า มัลดีฟ 10x10x6 ซม. สีเทา'),
    (790, N'ZCC01041116M021-1', N'Laguna Maldives 10x10x6 cm. - Red Coral', N'ลากูน่า มัลดีฟ 10x10x6 ซม. สีแดง'),
    (791, N'ZCC01041116M091-1', N'Laguna Maldives10x10x6 cm. - White Beach', N'ลากูน่า มัลดีฟ 10x10x6 ซม. สีขาว'),
    (794, N'ZCC01041116M041-1', N'Laguna Maldives10x10x6 cm - Yellow Sandy', N'ลากูน่า มัลดีฟ 10x10x6 ซม. สีเหลือง'),
    (795, N'zcc011311160011', N'LAGUNA 10X10X6 CM. กรวดล้าง', N'ลากูน่า 10x10x6  ซม.กรวดล้าง'),
    (796, N'ZCC011281160011-1', N'LAGUNA 10X10X6 CM. GREY', N'ลากูน่า 10x10x6  ซม. เทา'),
    (797, N'ZCC011281160023-1', N'LAGUNA 10X10X6 CM. CRIMSON', N'ลากูน่า 10x10x6  ซม. เลือดหมู'),
    (798, N'ZCC011281160031-1', N'LAGUNA 10X10X6 CM. ORANGE', N'ลากูน่า 10x10x6  ซม. ส้ม'),
    (799, N'ZCC011281160061-1', N'LAGUNA 10X10X6 CM. BLACK', N'ลากูน่า 10x10x6  ซม. ดำ'),
    (800, N'ZCC011281160091-1', N'LAGUNA 10X10X6 CM. WHITE', N'ลากูน่า 10x10x6  ซม. ขาว'),
    (809, N'ZCC011281160011', N'LAGUNA 10X10X6 CM. GREY (PACK)', N'ลากูน่า 10x10x6  ซม. เทา (ห่อ)'),
    (810, N'ZCC011281160023', N'LAGUNA 10X10X6 CM. CRIMSON  (PACK)', N'ลากูน่า 10x10x6  ซม. เลือดหมู  (ห่อ)'),
    (811, N'ZCC011281160031', N'LAGUNA 10X10X6 CM. ORANGE  (PACK)', N'ลากูน่า 10x10x6  ซม. ส้ม (ห่อ)'),
    (812, N'ZCC011281160061', N'LAGUNA 10X10X6 CM. BLACK  (PACK)', N'ลากูน่า 10x10x6  ซม. ดำ (ห่อ)'),
    (813, N'ZCC011281160091', N'LAGUNA 10X10X6 CM. WHITE (PACK)', N'ลากูน่า 10x10x6  ซม. ขาว (ห่อ)'),
    (814, N'ZCC01A032260021D', N'LA-LINEAR 20X20X6 CM. (FT) RED (D)', N'ศิลาเหลี่ยม 20X20X6 ซม.  (FT)  สีแดง (D) '),
    (815, N'ZCC01A032260031D', N'LA-LINEAR 20X20X6 CM. (FT)  (D)', N'ศิลาเหลี่ยม 20X20X6 ซม.  (FT)  สีส้ม  (D) '),
    (816, N'ZCC01A032260052D', N'LA-LINEAR 20X20X6 CM. (FT) RED (D)', N'ศิลาเหลี่ยม 20X20X6 ซม.  (FT)  สีน้ำตาลเข้ม (D) '),
    (817, N'ZCC01A020060021D', N'UNI 6 CM. (FT)  RED (D)', N'คดกริช 6 ซม. (FT) แดง (D)'),
    (818, N'ZCC01A020060031D', N'UNI 6 CM. (FT) ORANGE (D)', N'คดกริช 6 ซม. (FT) ส้ม (D)'),
    (819, N'สินค้าทดลองผลิตสีน้ำตาล', N'TURF STONE 8 CM BROWN', N'บล็อคปลูกหญ้า 8 ซม. สีน้ำตาล'),
    (820, N'สินค้าทดลองผลิตสีส้ม', N'TURF STONE 8 CM ORANGE', N'บล็อคปลูกหญ้า 8 ซม.สีส้ม'),
    (821, N'ZCC01041446M011', N'Laguna Maldivea 40*40*6cm.เทา', N'Laguna มัลดีฟ 40*40*6 ซม. สีเทา'),
    (822, N'ZCC010354460011M', N'Laguna Maldivea 40*40*6cm. Black', N'Laguna มัลดีฟ 40*40*6 ซม. สีดำ'),
    (823, N'ZCC010224460021', N'LA 40X40X6 CM - RED', N'ศิลาเหลี่ยม 40X40X6 สีแดง '),
    (825, N'zcc01A040060021H', N'OCTA 6 CM - RED(F)', N'อัฐศิลา 6 ซม. สีแดง(F)'),
    (826, N'zcc010162260205', N'LINEA 20X20X6 - Pink (04)', N'ศิลาเหลี่ยม 20X20X6 ซม. สีชมพู (04)'),
    (827, N'zcc010162260206', N'LINEA 20X20X6 - Pink (06)', N'ศิลาเหลี่ยม 20X20X6 ซม. สีชมพู (06)'),
    (828, N'zcc010162260207', N'LINEA 20X20X6 - Pink (20)', N'ศิลาเหลี่ยม 20X20X6 ซม. สีชมพู (20)'),
    (829, N'zcc010161260205', N'LINEA 10X20X6 - Pink (04)', N'ศิลาเหลี่ยม 10X20X6 ซม.สีชมพู (04)'),
    (830, N'zcc010161260206', N'LINEA 10X20X6 - Pink (06)', N'ศิลาเหลี่ยม 10X20X6 ซม. สีชมพู (06)'),
    (831, N'ZCC01041RT6M011', N'LAGUNA RT3- 6 Cm. มัลดิฟ เทา', N'LAGUNA RT3- 6 Cm. มัลดิฟ เทา'),
    (832, N'ZCC01041RT6M061', N'LAGUNA RT3- 6 Cm. มัลดิฟ ดำ', N'LAGUNA RT3- 6 Cm. มัลดิฟ ดำ'),
    (833, N'zcc010161260207', N'LINEA 10X20X6 - Pink (20)', N'ศิลาเหลี่ยม 10X20X6 ซม. สีชมพู (20)'),
    (834, N'zcc010224440011T', N'SLAB [NO FACING] 40X40X4 CM - GREY', N'แผ่นปูทางเท้า 40X40X4 สีเทา (ไม่มีผิวหน้า) ท่าอิฐ'),
    (835, N'zcc010162260011C', N'LINEA 20X20X6 -เทา (C)', N'ศิลาเหลี่ยม 20X20X6 ซม. เทา'),
    (836, N'ZCC010162260045', N'LINEA 20X20X6 - YELLOW', N'ศิลาเหลี่ยม 20X20X6 ซม. สีเหลืองอ่อน'),
    (837, N'zcc011491260509', N'บล็อกระบายน้ำเร็ว 10x20x6 CM น้ำตาลเข้ม', N'บล็อกระบายน้ำเร็ว 10x20x6 CM น้ำตาลเข้ม'),
    (839, N'zcc011491260507', N'POROUS 10x20x6 CM- SOFT GREEN', N'บล็อกระบายน้ำเร็ว 10x20x6 CM SOFT GREEN'),
    (840, N'zcc011491260061(ทดลอง)', N'POROUS 10x20x6 CM', N'บล็อกระบายน้ำเร็ว 10x20x6 CM ดำ(ทดลอง)'),
    (841, N'zcc011491260011(ทดลอง)', N'POROUS 10x20x6 CM', N'บล็อกระบายน้ำเร็ว 10x20x6 CM  เทา(ทดลอง)'),
    (842, N'ZCC010166650011', N'LA 60*60*5cm GREY', N'ศิลาเหลี่ยม 60*60*5 CM เทา'),
    (843, N'ZCC010166650065', N'LA 60*60*5cm R-Black', N'ศิลาเหลี่ยม 60*60*5 CM ดำเข้ม'),
    (844, N'zcc010224850011', N'LA 40*80*5cm GREY', N'ศิลาเหลี่ยม 40*80*5 ซม-เทา'),
    (845, N'zcc011491260011', N'POROUS 10x20x6 CM', N'บล็อกระบายน้ำเร็ว 10x20x6 CM  เทา'),
    (846, N'zcc011614460011', N'LALINEAR-  40x40x6 cm. เทา(suwan)', N'ศิลาเหลี่ยม 40X40X6 ซม. เทา (ลายสุวรรณ์)'),
    (847, N'zcc011614460021', N'LALINEAR-  40x40x6 cm. แดง(suwan)', N'ศิลาเหลี่ยม 40X40X6 ซม. แดง (ลายสุวรรณ์)'),
    (848, N'ZCC010122480011', N'TURF STONE 8 CM - ผิวหน้าหินล้าง-เทา', N'บล็อคปลูกหญ้า 8 ซม. สีเทา ผิวหน้าล้าง - เทา'),
    (850, N'ZCC010224460011-1', N'LALINEAR-  40x40x6 cm. เทา อ่อน', N'ศิลาเหลี่ยม 40X40X6 ซม. เทา อ่อน'),
    (851, N'ZCC010224460011-2', N'LALINEAR-  40x40x6 cm. เทา เข้ม', N'ศิลาเหลี่ยม 40X40X6 ซม. เทา เข้ม'),
    (852, N'ZCC010224460011-3', N'LALINEAR-  40x40x6 cm. RB2', N'ศิลาเหลี่ยม 40X40X6 ซม. RB2'),
    (853, N'ZCC010224460011-4', N'LALINEAR-  40x40x6 cm. RB4', N'ศิลาเหลี่ยม 40X40X6 ซม. RB4'),
    (854, N'ZCC010224460011-5', N'LALINEAR-  40x40x6 cm. RB5', N'ศิลาเหลี่ยม 40X40X6 ซม. RB5'),
    (855, N'ZCC010224460011-6', N'LALINEAR-  40x40x6 cm. B2', N'ศิลาเหลี่ยม 40X40X6 ซม. B2'),
    (857, N'ZCC010162260011-1', N'LINEA 20X20X6  เทา อ่อน', N'ศิลาเหลี่ยม 20X20X6 ซม.เทา อ่อน'),
    (858, N'ZCC010162260011-2', N'LINEA 20X20X6  เทา เข้ม', N'ศิลาเหลี่ยม 20X20X6 ซม.เทา เข้ม'),
    (859, N'ZCC010162260011-3', N'LINEA 20X20X6  RB2', N'ศิลาเหลี่ยม 20X20X6 ซม.RB2'),
    (860, N'ZCC010162260011-4', N'LINEA 20X20X6  RB4', N'ศิลาเหลี่ยม 20X20X6 ซม.RB4'),
    (861, N'ZCC010162260011-5', N'LINEA 20X20X6 - เทา เข้ม', N'ศิลาเหลี่ยม 20X20X6 ซม.RB5'),
    (862, N'ZCC010162260011-6', N'LINEA 20X20X6 B2', N'ศิลาเหลี่ยม 20X20X6 ซม.B2'),
    (863, N'ZCC010165560021', N'LA 50x50x6 CM.  -แดง', N'ศิลาเหลี่ยม 50x50x6 ซม. สีแดง'),
    (864, N'ZCC010163330021R', N'กระเบื้องหน้าเรียบ 30*30*3.5สีแดง', N'กระเบื้องหน้าเรียบ 30*30*3.5สีแดง'),
    (866, N'zcc012001160127-3', N'แกรนิตโค้ทติ้งสโตน 10X10X6 ซม. เบจ', N'แกรนิตโค้ทติ้งสโตน 10X10X6 ซม. เบจ'),
    (867, N'ZCC010171160011-2 ทดลองผลิต', N'LINEA 10X10X6 - GREY', N'ศิลาเหลี่ยม 10X10X3.5ซม.  ทดลองผลิต'),
    (868, N'ZCC012001260127', N'แกรนิตโค้ทติ้งสโตน 10X20X6 ซม. เบจ', N'แกรนิตโค้ทติ้งสโตน 10X20X6 ซม. เบจ'),
    (869, N'zcc012003360019', N'แกรนิตโค้ทติ้งสโตน 30X30X6  เทาเข้ม', N'แกรนิตโค้ทติ้งสโตน 30X30X6  เทา เข้ม'),
    (870, N'zcc012003360061', N'แกรนิตโค้ทติ้งสโตน 30X30X6  ดำ', N'แกรนิตโค้ทติ้งสโตน 30X30X6 ดำ'),
    (871, N'ZCC012003360011', N'แกรนิตโค้ทติ้งสโตน 30X30X6  เทา', N'แกรนิตโค้ทติ้งสโตน 30X30X6 เทา'),
    (872, N'zcc012003360127', N'แกรนิตโค้ทติ้งสโตน 30X30X6  เบจ', N'แกรนิตโค้ทติ้งสโตน 30X30X6 เบจ'),
    (874, N'ZCC012001160127-2', N'Lucky stone 10*10*3.5 Cm Grey ', N'Lucky stone 10*10*3.5 Cm Grey 1'),
    (875, N'ZCC012001160061-2', N'Lucky stone 10*10*3.5 Cm Black 4.0 kg ( ทดลอง )', N'Lucky stone 10*10*3.5 Cm Black 4.0 kg ( ทดลอง )'),
    (876, N'ZCC012001160011-2', N'Lucky stone 10*10*3.5 Cm Grey 2 ( ทดลอง )', N'Lucky stone 10*10*3.5 Cm Grey 2 (ทดลอง)'),
    (877, N'ZCC012001160061-1', N'แกรนิตโค้ทติ้งสโตน 10X10X6  ดำ', N'แกรนิตโค้ทติ้งสโตน 10X10X6  ดำ'),
    (878, N'ZCC012001160011-1', N'แกรนิตโค้ทติ้งสโตน 10x10x6ซม. เทา', N'แกรนิตโค้ทติ้งสโตน 10x10x6ซม. เทา'),
    (879, N'ZCC012001160019-1', N'แกรนิตโค้ทติ้งสโตน 10x10x6ซม. เทาเข้ม', N'แกรนิตโค้ทติ้งสโตน 10x10x6ซม. เทาเข้ม'),
    (880, N'ZCC012001160127-1', N'แกรนิตโค้ทติ้งสโตน 10x10x6ซม. บจ', N'แกรนิตโค้ทติ้งสโตน 10x10x6ซม. เบจ'),
    (881, N'zcc012001160061', N'แกรนิตโค้ทติ้งสโตน 10X10X6  ดำ', N'แกรนิตโค้ทติ้งสโตน 10X10X6  ดำ (ห่อ)'),
    (882, N'ZCC012001160011', N'แกรนิตโค้ทติ้งสโตน 10x10x6ซม. เทา', N'แกรนิตโค้ทติ้งสโตน 10x10x6ซม. เทา (ห่อ)'),
    (883, N'ZCC012001160019', N'แกรนิตโค้ทติ้งสโตน 10x10x6ซม. เทาเข้ม', N'แกรนิตโค้ทติ้งสโตน 10x10x6ซม. เทาเข้ม  (ห่อ)'),
    (884, N'ZCC012001160127', N'แกรนิตโค้ทติ้งสโตน 10x10x6ซม. บจ', N'แกรนิตโค้ทติ้งสโตน 10x10x6ซม. เบจ  (ห่อ)'),
    (886, N'ZCC012001350011', N'แกรนิตโค้ทติ้งสโตน 10x10x3.5ซม. เทา', N'แกรนิตโค้ทติ้งสโตน 10x10x3.5ซม. เทา'),
    (887, N'ZCC012001350061', N'แกรนิตโค้ทติ้งสโตน 10X10X3.5ซม  ดำ', N'แกรนิตโค้ทติ้งสโตน 10X10X3.5 ซม ดำ'),
    (888, N'ZCC012001350019', N'แกรนิตโค้ทติ้งสโตน 10X10X3.5ซม  เทาเข้ม', N'แกรนิตโค้ทติ้งสโตน 10X10X3.5 ซม เทาเข้ม'),
    (889, N'ZCC012001350127', N'แกรนิตโค้ทติ้งสโตน 10X10X3.5ซม  เบท', N'แกรนิตโค้ทติ้งสโตน 10X10X3.5 ซม เบท'),
    (890, N'zcc01166438NO11 ทดลองผลิต', N'แผ่นปูทางเท้า 40X40X3.8 สีเทา  ทดลองผลิต', N'แผ่นปูทางเท้า 40X40X3.8 สีเทา  ทดลองผลิต'),
    (891, N'ZCC010224460011 ทดลองผลิต', N'LA 40X40X6 CM - GREY  ทดลองผลิต', N'ศิลาเหลี่ยม 40X40X6 สีเทา (มีผิวหน้า)'),
    (892, N'ZCC010163360011-2', N'Laguna Smooth  30X30X6 - GREY  ทดลองผลิต', N'ลากูน่า  สมูท 30X30X6 ซม. สีเทา  ทดลองผลิต'),
    (922, N'ZCC01016446B23S', N'LALINEAR-  40x40x6 cm. สีฟ้า B2+3', N'ศิลาเหลี่ยม 40X40X6 ซม. สีฟ้า B2+3S '),
    (923, N'ZCC01016446GB4S', N'LALINEAR-  40x40x6 cm. สีฟ้า GB4 S', N'ศิลาเหลี่ยม 40X40X6 ซม. สีฟ้า GB4 S'),
    (924, N'ZCC01016446GB5S', N'LALINEAR-  40x40x6 cm. สีฟ้า GB5 S', N'ศิลาเหลี่ยม 40X40X6 ซม. สีฟ้า GB5 S'),
    (925, N'ZCC01016446GB2S', N'LALINEAR-  40x40x6 cm. สีฟ้า GB2 S', N'ศิลาเหลี่ยม 40X40X6 ซม. สีฟ้า GB2 S'),
    (926, N'ZCC01016226GB2S', N'ศิลาเหลี่ยม  20X20X6  ซม.  สีฟ้า  GB2 S', N'ศิลาเหลี่ยม  20X20X6  ซม.  สีฟ้า  GB2 S'),
    (927, N'ZCC01016226GB5S', N'ศิลาเหลี่ยม  20X20X6  ซม.  สีฟ้า  GB5 S', N'ศิลาเหลี่ยม  20X20X6  ซม.  สีฟ้า  GB5 S'),
    (928, N'ZCC01016226GB4S', N'ศิลาเหลี่ยม  20X20X6  ซม.  สีฟ้า  GB4 S', N'ศิลาเหลี่ยม  20X20X6  ซม.  สีฟ้า  GB4 S'),
    (929, N'ZCC010164460019C', N'ศิลาเหลี่ยม 40x40x6 cm. สีเทาเข้ม C', N'ศิลาเหลี่ยม 40x40x6 cm. สีเทาเข้ม C'),
    (930, N'ZCC010171160021-1 ทดลองผลิต', N'LINEA 10X10X6 - RED  ทดลองผลิต', N'LINEA 10X10X6 - RED  ทดลองผลิต');

    IF (SELECT COUNT(*) FROM @Source) <> @ExpectedImportCount
        THROW 53923, 'Import stopped: embedded source record count is not exactly 825.', 1;
    IF EXISTS (
        SELECT 1 FROM @Source
        WHERE DATALENGTH(ProductCode) = 0
           OR DATALENGTH(LTRIM(RTRIM(ProductCode))) <> DATALENGTH(ProductCode)
           OR DATALENGTH(LTRIM(RTRIM(ProductName))) = 0
           OR DATALENGTH(LTRIM(RTRIM(ProductNameThai))) = 0
    )
        THROW 53924, 'Import stopped: source contains a blank name/code or a whitespace-padded ProductCode.', 1;

    DECLARE @Inserted TABLE (
        ProductCode nvarchar(100) COLLATE Latin1_General_100_BIN2 NOT NULL PRIMARY KEY,
        ProductName nvarchar(200) COLLATE Thai_CI_AS NOT NULL,
        ProductNameThai nvarchar(200) COLLATE Thai_CI_AS NOT NULL,
        ProductFamily nvarchar(100) COLLATE Thai_CI_AS NULL,
        IsActive bit NOT NULL
    );

    SET TRANSACTION ISOLATION LEVEL SERIALIZABLE;
    BEGIN TRANSACTION;

    IF EXISTS (
        SELECT 1 FROM omagmes.Product p WITH (UPDLOCK, HOLDLOCK)
        JOIN @Source s ON p.ProductCode = s.ProductCode
    )
        THROW 53925, 'Import stopped: a source ProductCode already exists; rerun is refused.', 1;
    IF EXISTS (
        SELECT ProductCode FROM omagmes.Product WITH (UPDLOCK, HOLDLOCK)
        GROUP BY ProductCode HAVING COUNT_BIG(*) > 1
    )
        THROW 53926, 'Import stopped: duplicate ProductCode values already exist in Product.', 1;

    SELECT @ExistingProductCount = COUNT_BIG(*) FROM omagmes.Product WITH (UPDLOCK, HOLDLOCK);
    SELECT @ProductStandardRevisionCount = COUNT_BIG(*) FROM omagmes.ProductStandardRevision WITH (HOLDLOCK);

    INSERT INTO omagmes.Product (ProductCode, ProductName, ProductFamily, IsActive, ProductNameThai)
        OUTPUT INSERTED.ProductCode, INSERTED.ProductName, INSERTED.ProductNameThai, INSERTED.ProductFamily, INSERTED.IsActive
        INTO @Inserted (ProductCode, ProductName, ProductNameThai, ProductFamily, IsActive)
    SELECT ProductCode, ProductName, NULL, CONVERT(bit, 1), ProductNameThai
    FROM @Source;
    SET @InsertedCount = @@ROWCOUNT;
    IF @InsertedCount <> @ExpectedImportCount OR (SELECT COUNT(*) FROM @Inserted) <> @ExpectedImportCount
        THROW 53927, 'Import stopped: inserted row count is not exactly 825.', 1;

    IF EXISTS (
        SELECT 1 FROM @Source s
        WHERE NOT EXISTS (
            SELECT 1 FROM @Inserted i
            WHERE CONVERT(varbinary(max), i.ProductCode) = CONVERT(varbinary(max), s.ProductCode)
              AND CONVERT(varbinary(max), i.ProductName) = CONVERT(varbinary(max), s.ProductName)
              AND CONVERT(varbinary(max), i.ProductNameThai) = CONVERT(varbinary(max), s.ProductNameThai)
              AND i.ProductFamily IS NULL AND i.IsActive = CONVERT(bit, 1)
        )
    )
        THROW 53928, 'Import stopped: inserted output does not exactly match approved source values.', 1;
    IF EXISTS (
        SELECT 1 FROM @Source s
        WHERE NOT EXISTS (
            SELECT 1 FROM omagmes.Product p
            WHERE CONVERT(varbinary(max), p.ProductCode) = CONVERT(varbinary(max), s.ProductCode)
              AND CONVERT(varbinary(max), p.ProductName) = CONVERT(varbinary(max), s.ProductName)
              AND CONVERT(varbinary(max), p.ProductNameThai) = CONVERT(varbinary(max), s.ProductNameThai)
              AND p.ProductFamily IS NULL AND p.IsActive = CONVERT(bit, 1)
        )
    )
        THROW 53929, 'Import stopped: persisted Product values do not exactly match source values.', 1;
    IF EXISTS (SELECT ProductCode FROM omagmes.Product GROUP BY ProductCode HAVING COUNT_BIG(*) > 1)
        THROW 53930, 'Import stopped: ProductCode uniqueness check failed after insertion.', 1;
    IF EXISTS (SELECT 1 FROM omagmes.Product WHERE ProductName IS NULL OR DATALENGTH(LTRIM(RTRIM(ProductName))) = 0
               OR ProductNameThai IS NULL OR DATALENGTH(LTRIM(RTRIM(ProductNameThai))) = 0)
        THROW 53931, 'Import stopped: blank English or Thai Product names detected after insertion.', 1;

    SELECT @FinalProductCount = COUNT_BIG(*) FROM omagmes.Product WITH (HOLDLOCK);
    SELECT @FinalProductStandardRevisionCount = COUNT_BIG(*) FROM omagmes.ProductStandardRevision WITH (HOLDLOCK);
    IF @FinalProductCount <> @ExistingProductCount + @ExpectedImportCount
        THROW 53932, 'Import stopped: final Product row count does not equal baseline plus 825.', 1;
    IF @FinalProductStandardRevisionCount <> @ProductStandardRevisionCount
        THROW 53933, 'Import stopped: ProductStandardRevision count changed during import.', 1;

    COMMIT TRANSACTION;
    SET TRANSACTION ISOLATION LEVEL READ COMMITTED;
END TRY
BEGIN CATCH
    IF XACT_STATE() <> 0
        ROLLBACK TRANSACTION;
    SET TRANSACTION ISOLATION LEVEL READ COMMITTED;
    THROW;
END CATCH;

SELECT N'COMMITTED' AS TransactionStatus,
    @ExecutionOriginalLogin AS ExecutionOriginalLogin,
    @ExecutionSqlLogin AS ExecutionSqlLogin,
    @ExecutionDatabaseUser AS ExecutionDatabaseUser,
       @InsertedCount AS InsertedCount,
       @ExpectedImportCount AS ExpectedCount,
       @ExistingProductCount AS ProductCountBefore,
       @FinalProductCount AS ProductCountAfter,
       @ProductStandardRevisionCount AS ProductStandardRevisionCountBefore,
       @FinalProductStandardRevisionCount AS ProductStandardRevisionCountAfter,
       @SourceSha256 AS SourceWorkbookSHA256;
