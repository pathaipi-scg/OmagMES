/*
DBA REVIEW ONLY — DO NOT EXECUTE AUTOMATICALLY.

Target confirmed in backend/app/sql_source.py:
  SQL Server: SCGLS-NK\SQLEXPRESS
  Instance:   SQLEXPRESS
  Database:   OMAG

The sole schema change is nullable ProductNameThai on the existing
omagmes.Product table. No Product rows, IDs, keys, constraints, indexes,
standards, permissions, or other objects are changed. Existing rows receive
NULL. Obtain explicit DBA review, backup/change-control approval, and
deployment authorization before execution.
*/
SET NOCOUNT ON;
SET XACT_ABORT ON;

BEGIN TRY
    IF @@TRANCOUNT <> 0
        THROW 53800, 'Run this review-only migration in a session without an ambient transaction.', 1;

    IF DB_NAME() <> N'OMAG'
        THROW 53801, 'Migration 008 requires database OMAG.', 1;
    IF ISNULL(CONVERT(nvarchar(128), @@SERVERNAME), N'') <> N'SCGLS-NK\SQLEXPRESS'
        THROW 53802, 'Migration 008 is connected to an unexpected SQL Server name.', 1;
    IF ISNULL(CONVERT(nvarchar(128), SERVERPROPERTY(N'ServerName')), N'') <> N'SCGLS-NK\SQLEXPRESS'
        THROW 53803, 'Migration 008 is connected to an unexpected SQL Server instance identity.', 1;
    IF ISNULL(CONVERT(nvarchar(128), SERVERPROPERTY(N'InstanceName')), N'') <> N'SQLEXPRESS'
        THROW 53804, 'Migration 008 is connected to an unexpected SQL Server instance.', 1;
    IF SCHEMA_ID(N'omagmes') IS NULL
        THROW 53805, 'Schema omagmes is missing; stop and review the target.', 1;

    DECLARE @ProductObjectID int = OBJECT_ID(N'omagmes.Product', N'U');
    IF @ProductObjectID IS NULL
        THROW 53806, 'Table omagmes.Product is missing; stop and review the target.', 1;

    BEGIN TRANSACTION;

    IF COL_LENGTH(N'omagmes.Product', N'ProductNameThai') IS NULL
    BEGIN
        ALTER TABLE omagmes.Product
            ADD ProductNameThai nvarchar(200) COLLATE Thai_CI_AS NULL;
    END
    ELSE IF NOT EXISTS (
        SELECT 1
        FROM sys.columns AS c
        JOIN sys.types AS t ON t.user_type_id = c.user_type_id
        WHERE c.object_id = @ProductObjectID
          AND c.name = N'ProductNameThai'
          AND t.name = N'nvarchar'
          AND c.max_length = 400
          AND c.is_nullable = 1
          AND c.is_computed = 0
          AND c.collation_name = N'Thai_CI_AS'
    )
    BEGIN
        THROW 53807, 'ProductNameThai exists with incompatible metadata; no change is authorized.', 1;
    END;

    /* Verify the complete requested metadata before committing the DDL. */
    IF NOT EXISTS (
        SELECT 1
        FROM sys.columns AS c
        JOIN sys.types AS t ON t.user_type_id = c.user_type_id
        WHERE c.object_id = @ProductObjectID
          AND c.name = N'ProductNameThai'
          AND t.name = N'nvarchar'
          AND c.max_length = 400
          AND c.is_nullable = 1
          AND c.is_computed = 0
          AND c.collation_name = N'Thai_CI_AS'
    )
        THROW 53808, 'Post-change ProductNameThai metadata verification failed; transaction will roll back.', 1;

    SELECT c.name AS ColumnName,
           t.name AS DataType,
           CONVERT(int, c.max_length / 2) AS CharacterLength,
           c.is_nullable AS IsNullable,
           c.is_computed AS IsComputed,
           c.collation_name AS CollationName
    FROM sys.columns AS c
    JOIN sys.types AS t ON t.user_type_id = c.user_type_id
    WHERE c.object_id = @ProductObjectID
      AND c.name = N'ProductNameThai';

    COMMIT TRANSACTION;
END TRY
BEGIN CATCH
    IF XACT_STATE() <> 0
        ROLLBACK TRANSACTION;
    THROW;
END CATCH;