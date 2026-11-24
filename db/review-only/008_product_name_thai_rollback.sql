/*
DBA REVIEW ONLY — DO NOT EXECUTE AUTOMATICALLY.

Target confirmed in backend/app/sql_source.py:
  SQL Server: SCGLS-NK\SQLEXPRESS
  Instance:   SQLEXPRESS
  Database:   OMAG

This rollback removes only the ProductNameThai column. It refuses to run
unless the explicit review flag below is changed after documented DBA review
and authorization, the executing principal has ALTER permission, the target
identity is correct, the column matches the Migration 008 definition, no
Product row has a non-NULL Thai name, and no catalog-visible dependent object
is found. It requires database VIEW DEFINITION permission for a complete
catalog review and takes an exclusive table lock while checking data and
dropping the column to prevent concurrent Product writes during the check.

Catalog dependency checks cannot reliably find references hidden in dynamic
SQL, external jobs, reports, or other systems. DBA must review those separately.
*/
SET NOCOUNT ON;
SET XACT_ABORT ON;

/* Leave disabled. Change to 1 only in a separately approved DBA execution copy. */
DECLARE @DbaReviewAuthorized bit = 0;

BEGIN TRY
    IF @DbaReviewAuthorized <> 1
        THROW 53820, 'Rollback is disabled until explicit DBA review and authorization are recorded.', 1;
    IF @@TRANCOUNT <> 0
        THROW 53821, 'Run this review-only rollback in a session without an ambient transaction.', 1;

    IF DB_NAME() <> N'OMAG'
        THROW 53822, 'Rollback requires database OMAG.', 1;
    IF ISNULL(CONVERT(nvarchar(128), @@SERVERNAME), N'') <> N'SCGLS-NK\SQLEXPRESS'
        THROW 53823, 'Rollback is connected to an unexpected SQL Server name.', 1;
    IF ISNULL(CONVERT(nvarchar(128), SERVERPROPERTY(N'ServerName')), N'') <> N'SCGLS-NK\SQLEXPRESS'
        THROW 53824, 'Rollback is connected to an unexpected SQL Server instance identity.', 1;
    IF ISNULL(CONVERT(nvarchar(128), SERVERPROPERTY(N'InstanceName')), N'') <> N'SQLEXPRESS'
        THROW 53825, 'Rollback is connected to an unexpected SQL Server instance.', 1;
    IF SCHEMA_ID(N'omagmes') IS NULL
        THROW 53826, 'Schema omagmes is missing; stop and review the target.', 1;

    DECLARE @ProductObjectID int = OBJECT_ID(N'omagmes.Product', N'U');
    IF @ProductObjectID IS NULL
        THROW 53827, 'Table omagmes.Product is missing; stop and review the target.', 1;
    IF ISNULL(HAS_PERMS_BY_NAME(N'omagmes.Product', N'OBJECT', N'ALTER'), 0) <> 1
        THROW 53828, 'The executing principal lacks ALTER permission on omagmes.Product.', 1;
    IF ISNULL(HAS_PERMS_BY_NAME(DB_NAME(), N'DATABASE', N'VIEW DEFINITION'), 0) <> 1
        THROW 53829, 'The executing principal lacks database VIEW DEFINITION permission for dependency checks.', 1;

    BEGIN TRANSACTION;

    DECLARE @ProductNameThaiColumnID int;
    SELECT @ProductNameThaiColumnID = c.column_id
    FROM sys.columns AS c
    WHERE c.object_id = @ProductObjectID
      AND c.name = N'ProductNameThai';

    IF @ProductNameThaiColumnID IS NULL
        THROW 53830, 'ProductNameThai is absent; nothing is eligible for rollback.', 1;

    IF NOT EXISTS (
        SELECT 1
        FROM sys.columns AS c
        JOIN sys.types AS t ON t.user_type_id = c.user_type_id
        WHERE c.object_id = @ProductObjectID
          AND c.column_id = @ProductNameThaiColumnID
          AND c.name = N'ProductNameThai'
          AND t.name = N'nvarchar'
          AND c.max_length = 400
          AND c.is_nullable = 1
          AND c.is_computed = 0
          AND c.collation_name = N'Thai_CI_AS'
    )
        THROW 53831, 'ProductNameThai metadata differs from Migration 008; rollback refused.', 1;

    /*
    Exclusive lock is held to transaction end, preventing concurrent Product
    inserts/updates after the NULL-value check and before DROP COLUMN.
    */
    IF EXISTS (
        SELECT 1
        FROM omagmes.Product WITH (TABLOCKX, HOLDLOCK)
        WHERE ProductNameThai IS NOT NULL
    )
        THROW 53832, 'Rollback refused: at least one Product row contains a non-NULL Thai name.', 1;

    /*
    referenced_minor_id = 0 is treated conservatively as an object-level or
    unresolved column dependency and blocks rollback pending DBA inspection.
    */
    IF EXISTS (
        SELECT 1
        FROM sys.sql_expression_dependencies AS d
        WHERE d.referenced_id = @ProductObjectID
          AND d.referenced_minor_id IN (0, @ProductNameThaiColumnID)
    )
        THROW 53833, 'Rollback refused: a SQL dependency references Product or ProductNameThai.', 1;

    IF EXISTS (
        SELECT 1
        FROM sys.index_columns AS ic
        WHERE ic.object_id = @ProductObjectID
          AND ic.column_id = @ProductNameThaiColumnID
    )
        THROW 53834, 'Rollback refused: an index depends on ProductNameThai.', 1;

    IF EXISTS (
        SELECT 1
        FROM sys.foreign_key_columns AS fkc
        WHERE (fkc.parent_object_id = @ProductObjectID AND fkc.parent_column_id = @ProductNameThaiColumnID)
           OR (fkc.referenced_object_id = @ProductObjectID AND fkc.referenced_column_id = @ProductNameThaiColumnID)
    )
        THROW 53835, 'Rollback refused: a foreign key depends on ProductNameThai.', 1;

    IF EXISTS (
        SELECT 1
        FROM sys.default_constraints AS dc
        WHERE dc.parent_object_id = @ProductObjectID
          AND dc.parent_column_id = @ProductNameThaiColumnID
    )
        THROW 53836, 'Rollback refused: a default constraint depends on ProductNameThai.', 1;

    IF EXISTS (
        SELECT 1
        FROM sys.check_constraints AS cc
        WHERE cc.parent_object_id = @ProductObjectID
          AND cc.parent_column_id = @ProductNameThaiColumnID
    )
        THROW 53837, 'Rollback refused: a check constraint depends on ProductNameThai.', 1;

    ALTER TABLE omagmes.Product DROP COLUMN ProductNameThai;

    COMMIT TRANSACTION;
END TRY
BEGIN CATCH
    IF XACT_STATE() <> 0
        ROLLBACK TRANSACTION;
    THROW;
END CATCH;