import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCHEMA_SCRIPT = ROOT / "db" / "002_omagmes_configuration.sql"
SHIFT_TYPE_SCRIPT = ROOT / "db" / "deploy" / "004_shift_type_daily_assignment.sql"


def test_configuration_schema_script_is_target_guarded_repeatable_and_owner_seeded() -> None:
    sql = SCHEMA_SCRIPT.read_text(encoding="utf-8")
    assert "IF DB_NAME() <> N'OMAG'" in sql
    assert "CREATE SCHEMA omagmes" in sql
    for table in ("ProductionDayCutoffVersion", "Shift", "ShiftScheduleVersion", "ShiftScheduleShift"):
        assert f"OBJECT_ID(N'omagmes.{table}', N'U') IS NULL" in sql
        match = re.search(rf"CREATE\s+TABLE\s+omagmes\.{table}\s*\((.*?)\n\s*\);", sql, re.IGNORECASE | re.DOTALL)
        assert match, table
        definition = match.group(1)
        assert re.search(r"\bid\s+bigint\s+IDENTITY\s*\(1,\s*1\)\s+NOT\s+NULL", definition, re.IGNORECASE), table
        assert re.search(r"\bRectime\s+datetime\s+NOT\s+NULL.*DEFAULT\s*\(GETDATE\(\)\)", definition, re.IGNORECASE | re.DOTALL), table
        assert re.search(r"CONSTRAINT\s+PK_\w+\s+PRIMARY\s+KEY", definition, re.IGNORECASE), table
    assert "2026-11-10" in sql
    assert "07:00" in sql
    assert "Asia/Bangkok" in sql
    assert "08:00" in sql and "19:00" in sql and "06:00" in sql
    assert "WITH (UPDLOCK, HOLDLOCK)" in sql


def test_configuration_runtime_role_is_object_scoped_and_append_only() -> None:
    sql = SCHEMA_SCRIPT.read_text(encoding="utf-8")
    assert "WITHOUT LOGIN" in sql
    for table in ("ProductionDayCutoffVersion", "Shift", "ShiftScheduleVersion", "ShiftScheduleShift"):
        assert f"GRANT SELECT, INSERT ON OBJECT::omagmes.{table}" in sql
    assert not re.search(r"GRANT\s+UPDATE|GRANT\s+DELETE|GRANT\s+CONTROL|GRANT\s+ALTER", sql, re.IGNORECASE)
    for trigger in (
        "TR_ProductionDayCutoffVersion_Immutable",
        "TR_ShiftScheduleVersion_Immutable",
        "TR_ShiftScheduleShift_Immutable",
        "TR_Shift_Immutable",
    ):
        assert trigger in sql
    assert "OMAG.dbo" in sql


def test_shift_type_deployment_is_additive_repeatable_and_does_not_seed_daily_assignments() -> None:
    sql = SHIFT_TYPE_SCRIPT.read_text(encoding="utf-8")
    assert "IF DB_NAME() <> N'OMAG'" in sql
    assert "BEGIN TRANSACTION" in sql and "ROLLBACK TRANSACTION" in sql
    for table in ("ShiftType", "ShiftTypeScheduleVersion", "ShiftTypeSchedulePeriod", "DailyShiftTypeAssignment"):
        assert f"OBJECT_ID(N'omagmes.{table}', N'U') IS NULL" in sql
        assert f"GRANT SELECT,INSERT ON OBJECT::omagmes.{table}" in sql
        assert f"TR_{table}_Immutable" in sql
    for code in ("TYPE 1", "TYPE 2", "TYPE 3"):
        assert f"N'{code}'" in sql
    assert "'08:00','16:00'" in sql
    assert "'16:00','00:00',1" in sql
    assert "'20:00','08:00',1" in sql
    assert "DailyShiftTypeAssignment' AS ObjectName,COUNT_BIG(*)" in sql
    assert not re.search(r"INSERT\s+INTO\s+omagmes\.DailyShiftTypeAssignment", sql, re.IGNORECASE)
    assert "TR_ShiftTypeSchedulePeriod_NoOverlap" in sql
