from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "db" / "admin-review" / "011_daily_shift_configuration.sql"
ROLLBACK = ROOT / "db" / "admin-review" / "011_daily_shift_configuration_rollback.sql"


def test_daily_shift_migration_is_additive_grouped_and_repeatable() -> None:
    sql = MIGRATION.read_text(encoding="utf-8")
    assert "DBA REVIEW ONLY" in sql
    assert "MANUAL SSMS DEPLOYMENT CANDIDATE" in sql
    assert "USE [OMAG]" in sql
    assert re.search(r"IF\s+DB_NAME\(\)\s*<>\s*N'OMAG'", sql)
    assert "BEGIN TRANSACTION" in sql and "ROLLBACK TRANSACTION" in sql and "COMMIT TRANSACTION" in sql
    assert "CREATE OR ALTER TRIGGER" in sql
    assert "Post-deployment verification result sets" in sql
    assert "DailyShiftConfigurationSave" in sql
    assert "DailyShiftConfigurationPeriod" in sql
    assert "SaveTime datetime2(0) NOT NULL" in sql
    assert "DEFAULT (GETDATE())" in sql
    assert "IsComplete" in sql and "ConfigurationSaveID" in sql
    assert "TR_DailyShiftConfigurationSave_Complete" in sql
    assert "TR_DailyShiftConfigurationPeriod_Immutable" in sql
    assert len(re.findall(r"FROM\s+sys\.triggers\s+WHERE\s+object_id", sql, re.IGNORECASE)) == 4
    assert len(re.findall(r"SELECT\s+parent_id\s+FROM\s+sys\.triggers", sql, re.IGNORECASE)) == 2
    assert not re.search(r"SELECT\s+parent_object_id\s+FROM\s+sys\.triggers", sql, re.IGNORECASE)
    # parent_object_id remains valid and intentional in key, FK, check, and object catalog views.
    assert "FROM sys.key_constraints WHERE parent_object_id=" in sql
    assert "FROM sys.foreign_keys WHERE parent_object_id" in sql
    assert "FROM sys.check_constraints" in sql and "WHERE parent_object_id IN" in sql
    assert "FOREIGN KEY (ConfigurationSaveID,ProductionDate)" in sql
    assert "FOREIGN KEY (SelectedShiftTypeID)" in sql
    assert "FOREIGN KEY (TypeID)" in sql
    assert "FOREIGN KEY (ShiftID)" in sql
    assert "CONCAT(N''TYPE '',p.Type)" in sql
    assert "ShiftScheduleVersion" in sql and "DailyShiftTypeAssignment" in sql
    assert not re.search(r"\bDROP\s+(?:TABLE|COLUMN)\b", sql, re.IGNORECASE)
    assert not re.search(r"\bDELETE\s+FROM\s+omagmes\.", sql, re.IGNORECASE)
    assert "REVOKE " not in sql
    assert "GRANT SELECT ON OBJECT::omagmes.DailyShiftConfigurationSave TO omagmes_config_runtime_role" in sql
    assert "GRANT SELECT ON OBJECT::omagmes.DailyShiftConfigurationPeriod TO omagmes_config_runtime_role" in sql
    assert "GRANT INSERT ON OBJECT::omagmes.DailyShiftConfigurationSave TO omagmes_config_runtime_role" in sql
    assert "GRANT UPDATE (IsComplete)" in sql
    assert "GRANT INSERT ON OBJECT::omagmes.DailyShiftConfigurationPeriod TO omagmes_config_runtime_role" in sql
    assert not re.search(r"GRANT\s+INSERT\s*\(", sql, re.IGNORECASE)
    assert "HAS_PERMS_BY_NAME(N'omagmes.DailyShiftConfigurationSave',N'OBJECT',N'INSERT')" in sql
    assert "HAS_PERMS_BY_NAME(N'omagmes.DailyShiftConfigurationPeriod',N'OBJECT',N'INSERT')" in sql
    assert "HAS_PERMS_BY_NAME(N'omagmes.DailyShiftConfigurationSave',N'OBJECT',N'DELETE')" in sql
    assert "HAS_PERMS_BY_NAME(N'omagmes.DailyShiftConfigurationPeriod',N'OBJECT',N'DELETE')" in sql
    assert not re.search(r"HAS_PERMS_BY_NAME\([^\n]*,N'COLUMN',N'INSERT'", sql, re.IGNORECASE)
    assert "HAS_PERMS_BY_NAME(N'omagmes.DailyShiftConfigurationSave',N'OBJECT',N'UPDATE',N'IsComplete')" in sql
    assert "GRANT DELETE" not in sql
    assert "GRANT INSERT,UPDATE ON OBJECT::omagmes.DailyShiftConfigurationSave" not in sql
    for table in ("DailyShiftConfigurationSave", "DailyShiftConfigurationPeriod"):
        definition = re.search(rf"CREATE TABLE omagmes\.{table}\s*\((.*?)\n\s*\);", sql, re.IGNORECASE | re.DOTALL)
        assert definition, table
        assert re.search(r"\bid\s+bigint\s+IDENTITY\s*\(1,\s*1\)", definition.group(1), re.IGNORECASE)
        assert re.search(r"\bRectime\s+datetime\s+NOT NULL.*DEFAULT\s*\(GETDATE\(\)\)", definition.group(1), re.IGNORECASE | re.DOTALL)


def test_daily_shift_rollback_refuses_nonempty_or_referenced_tables() -> None:
    sql = ROLLBACK.read_text(encoding="utf-8")
    assert "DBA REVIEW ONLY" in sql
    assert "IF EXISTS (SELECT 1 FROM omagmes.DailyShiftConfigurationSave)" in sql
    assert "sys.foreign_keys" in sql
    assert "DROP TABLE omagmes.DailyShiftConfigurationPeriod" in sql
    assert "DROP TABLE omagmes.DailyShiftConfigurationSave" in sql
    assert re.search(r"IF\s+DB_NAME\(\)\s*<>\s*N'OMAG'", sql)


def test_daily_shift_migration_validates_each_intended_default_expression() -> None:
    sql = MIGRATION.read_text(encoding="utf-8")
    expected_defaults = (
        "(N'DailyShiftConfigurationSave',N'Rectime',N'getdate')",
        "(N'DailyShiftConfigurationSave',N'SaveTime',N'getdate')",
        "(N'DailyShiftConfigurationSave',N'IsComplete',N'0')",
        "(N'DailyShiftConfigurationPeriod',N'Rectime',N'getdate')",
    )
    for expected in expected_defaults:
        assert expected in sql

    default_check = sql.split(") expected(TableName,ColumnName,ExpectedDefinition)", 1)[1].split(
        "THROW 54623", 1
    )[0]
    assert "sys.default_constraints" in default_check
    assert "normalized.NormalizedDefinition<>expected.ExpectedDefinition" in default_check
    assert "REPLACE" in default_check and "N'(',N''" in default_check and "N')',N''" in default_check


def test_post_deployment_row_counts_skip_missing_tables_after_rollback() -> None:
    sql = MIGRATION.read_text(encoding="utf-8")
    verification = sql.split("/* Post-deployment verification result sets. These are read-only. */", 1)[1]
    guard = verification.split("/* Effective runtime checks", 1)[0]
    assert "IF OBJECT_ID(N'omagmes.DailyShiftConfigurationSave',N'U') IS NULL" in guard
    assert "OR OBJECT_ID(N'omagmes.DailyShiftConfigurationPeriod',N'U') IS NULL" in guard
    assert "Snapshot row-count verification skipped" in guard
    assert "EXEC sys.sp_executesql N'" in guard
    assert re.search(
        r"EXEC\s+sys\.sp_executesql\s+N'.*?FROM\s+omagmes\.DailyShiftConfigurationSave.*?"
        r"FROM\s+omagmes\.DailyShiftConfigurationPeriod",
        guard,
        re.IGNORECASE | re.DOTALL,
    )
