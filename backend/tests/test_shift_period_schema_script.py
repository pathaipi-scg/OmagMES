from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_shift_setting_deployment_is_repeatable_additive_and_id_first():
    script = (ROOT / "db" / "deploy" / "003_shift_setting_support.sql").read_text(encoding="utf-8")
    assert "IF DB_NAME() <> N'OMAG'" in script
    assert "CREATE TABLE omagmes.ShiftScheduleShiftPeriod" in script
    assert "CREATE TABLE omagmes.ConfigurationChangeHistory" in script
    assert "id bigint IDENTITY(1,1)" in script
    assert "Rectime datetime NOT NULL" in script
    assert "REFERENCES omagmes.ShiftScheduleShift(ShiftScheduleVersionID, ShiftID)" in script
    assert "OBJECT_ID(N'omagmes.ShiftScheduleShiftPeriod', N'U') IS NULL" in script
    assert "OBJECT_ID(N'omagmes.ConfigurationChangeHistory', N'U') IS NULL" in script
    assert "DROP TABLE" not in script
    assert "UPDATE omagmes.ShiftScheduleShift" not in script
    assert "DELETE FROM" not in script


def test_shift_setting_deployment_preserves_existing_rows_and_scopes_runtime_grants():
    script = (ROOT / "db" / "deploy" / "003_shift_setting_support.sql").read_text(encoding="utf-8")
    assert "Does not seed, update, or delete existing configuration or application data." in script
    assert "GRANT SELECT, INSERT ON OBJECT::omagmes.ShiftScheduleShiftPeriod TO omagmes_config_runtime_role" in script
    assert "GRANT SELECT, INSERT ON OBJECT::omagmes.ConfigurationChangeHistory TO omagmes_config_runtime_role" in script
    assert "GRANT UPDATE" not in script
    assert "GRANT DELETE" not in script
    assert "TR_ShiftScheduleShiftPeriod_Immutable" in script
    assert "TR_ConfigurationChangeHistory_Immutable" in script
