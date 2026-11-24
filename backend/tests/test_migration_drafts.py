import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DRAFTS = ROOT / "db" / "review-only"


def test_migration_draft_is_review_only_and_all_tables_follow_id_first() -> None:
    sql = (DRAFTS / "001_omagmes_foundation.sql").read_text(encoding="utf-8")
    assert "SUPERSEDED FOUNDATION DRAFT — DO NOT EXECUTE" in sql
    assert "Migration 003 is the canonical Product/Run/Lot design" in sql
    tables = re.findall(r"CREATE\s+TABLE\s+omagmes\.(\w+)\s*\((.*?)\n\);", sql, re.IGNORECASE | re.DOTALL)
    assert tables
    for table_name, definition in tables:
        assert re.search(r"\bid\s+bigint\s+IDENTITY\s*\(1,\s*1\)\s+NOT\s+NULL", definition, re.IGNORECASE), table_name
        assert re.search(r"\bRectime\s+datetime\s+NOT\s+NULL", definition, re.IGNORECASE), table_name
        assert re.search(r"CONSTRAINT\s+PK_\w+\s+PRIMARY\s+KEY", definition, re.IGNORECASE), table_name


def test_rollback_draft_matches_proposed_tables_and_requires_empty_schema() -> None:
    forward = (DRAFTS / "001_omagmes_foundation.sql").read_text(encoding="utf-8")
    rollback = (DRAFTS / "001_rollback.sql").read_text(encoding="utf-8")
    forward_tables = {name.lower() for name in re.findall(r"CREATE\s+TABLE\s+omagmes\.(\w+)", forward, re.IGNORECASE)}
    dropped_tables = {name.lower() for name in re.findall(r"DROP\s+TABLE\s+omagmes\.(\w+)", rollback, re.IGNORECASE)}
    assert forward_tables == dropped_tables
    assert "DESTRUCTIVE ROLLBACK DRAFT — DO NOT EXECUTE" in rollback
    assert "Rollback refused: omagmes contains data." in rollback
    assert "DROP SCHEMA omagmes" in rollback


def test_validation_checklist_covers_every_proposed_table() -> None:
    forward = (DRAFTS / "001_omagmes_foundation.sql").read_text(encoding="utf-8")
    validation = (DRAFTS / "001_validate.sql").read_text(encoding="utf-8")
    forward_tables = {name.lower() for name in re.findall(r"CREATE\s+TABLE\s+omagmes\.(\w+)", forward, re.IGNORECASE)}
    required_tables = {name.lower() for name in re.findall(r"\(N'([^']+)'\)", validation)}
    assert forward_tables == required_tables


def test_migration_has_no_seed_or_data_modification_statements() -> None:
    sql = (DRAFTS / "001_omagmes_foundation.sql").read_text(encoding="utf-8")
    assert re.search(r"\bINSERT\s+INTO\b|\bUPDATE\s+omagmes\.|\bDELETE\s+FROM\s+omagmes\.", sql, re.IGNORECASE) is None
    assert "CREATE SCHEMA omagmes" in sql


def test_production_day_configuration_migration_is_id_first_append_only_and_unseeded() -> None:
    sql = (DRAFTS / "002_production_day_and_shift_configuration.sql").read_text(encoding="utf-8")
    assert "REVIEW-ONLY DRAFT — DO NOT EXECUTE" in sql
    tables = re.findall(r"CREATE\s+TABLE\s+omagmes\.(\w+)\s*\((.*?)\n\);", sql, re.IGNORECASE | re.DOTALL)
    assert {name for name, _ in tables} == {"ProductionDayCutoffVersion", "Shift", "ShiftScheduleVersion", "ShiftScheduleShift"}
    for table_name, definition in tables:
        assert re.search(r"\bid\s+bigint\s+IDENTITY\s*\(1,\s*1\)\s+NOT\s+NULL", definition, re.IGNORECASE), table_name
        assert re.search(r"\bRectime\s+datetime\s+NOT\s+NULL", definition, re.IGNORECASE), table_name
        assert re.search(r"CONSTRAINT\s+PK_\w+\s+PRIMARY\s+KEY", definition, re.IGNORECASE), table_name
    assert "OUTPUT INSERTED" not in sql
    assert "INSERT INTO" not in sql
    for trigger in (
        "TR_ProductionDayCutoffVersion_Immutable",
        "TR_ShiftScheduleVersion_Immutable",
        "TR_ShiftScheduleShift_Immutable",
        "TR_Shift_Immutable",
    ):
        assert trigger in sql
    validation = (DRAFTS / "002_validate.sql").read_text(encoding="utf-8")
    for table_name, _ in tables:
        assert f"(N'{table_name}')" in validation


def test_configuration_rollback_refuses_to_delete_version_history() -> None:
    rollback = (DRAFTS / "002_rollback.sql").read_text(encoding="utf-8")
    assert "Rollback refused: configuration history exists" in rollback
    assert "No automated rollback is approved" in rollback


def test_production_lot_workflow_draft_is_id_first_unseeded_and_still_review_only() -> None:
    forward = (DRAFTS / "003_production_lot_workflow.sql").read_text(encoding="utf-8")
    rollback = (DRAFTS / "003_rollback.sql").read_text(encoding="utf-8")
    validation = (DRAFTS / "003_validate.sql").read_text(encoding="utf-8")
    assert "REVIEW-ONLY DRAFT — DO NOT EXECUTE" in forward
    tables = re.findall(r"CREATE\s+TABLE\s+omagmes\.(\w+)\s*\((.*?)\n\);", forward, re.IGNORECASE | re.DOTALL)
    assert tables
    for table_name, definition in tables:
        assert re.search(r"\bid\s+bigint\s+IDENTITY\s*\(1,\s*1\)\s+NOT\s+NULL", definition, re.IGNORECASE), table_name
        assert re.search(r"\bRectime\s+datetime\s+NOT\s+NULL", definition, re.IGNORECASE), table_name
        assert re.search(r"CONSTRAINT\s+PK_\w+\s+PRIMARY\s+KEY", definition, re.IGNORECASE), table_name
    forward_tables = {name.lower() for name, _ in tables}
    dropped_tables = {name.lower() for name in re.findall(r"DROP\s+TABLE\s+omagmes\.(\w+)", rollback, re.IGNORECASE)}
    required_table_rows = validation.split(") AS required(name)", maxsplit=1)[0]
    validated_tables = {name.lower() for name in re.findall(r"\(N'([^']+)'\)", required_table_rows)}
    assert forward_tables == dropped_tables == validated_tables
    assert "No product/color seeds or test Lots are included" in forward
    assert "sequence 99 is exhausted" in forward.lower() and "cannot\nwrap" in forward.lower()
    assert re.search(r"LotNo\s+varchar\(11\)", forward, re.IGNORECASE)
    assert "MachineCode='B'" in forward
    assert "CREATE TABLE omagmes.AutoLotResetReview" in forward
    assert "ProductionLotID bigint NOT NULL" in forward
    production_entry = next(definition for name, definition in tables if name == "ProductionEntry")
    for column in ("ProductionAt datetimeoffset(0) NOT NULL", "ProductionDate date NOT NULL", "ShiftScheduleVersionID bigint NOT NULL", "ShiftID bigint NULL"):
        assert column in production_entry
    assert "FOREIGN KEY (ProductionLotID) REFERENCES omagmes.ProductionLot(id)" in production_entry
    assert "IX_ProductionEntry_ProductionDate_Shift" in forward
    assert re.search(r"\bINSERT\s+INTO\b|\bUPDATE\s+omagmes\.|\bDELETE\s+FROM\s+omagmes\.", forward, re.IGNORECASE) is None
    assert "Rollback refused because production/master rows exist" in rollback


def test_migration_003_preflight_guards_prerequisites_and_factory_minute_boundaries() -> None:
    forward = (DRAFTS / "003_production_lot_workflow.sql").read_text(encoding="utf-8")
    preflight = (DRAFTS / "003_preflight.sql").read_text(encoding="utf-8")
    assert "CK_ProductionLot_MinutePrecision" in forward
    assert "DATEPART(SECOND, LotStartedAt) = 0" in forward
    assert "Migration 002 prerequisite columns or types" in forward
    assert "REQUIRED_CONFIGURATION_COLUMN" in preflight
    assert "SCHEDULE_SHIFT_COMPOSITE_KEY" in preflight
    assert "PRODUCTION_OBJECT_COLLISION" in preflight
    assert "SUPERSEDED_FOUNDATION_DRAFT" in preflight
    assert "RESOLVED: APPLY 003 ONLY" in preflight
    assert "this migration is the canonical Product/ProductionRun/ProductionLot" in forward
    assert "001_omagmes_foundation.sql is superseded" in forward


def test_sql_server_integration_suite_requires_explicit_disposable_target() -> None:
    integration = (ROOT / "backend" / "tests" / "test_sql_migration_integration.py").read_text(encoding="utf-8")
    assert "OMAGMES_TEST_SQL_CONNECTION_STRING" in integration
    assert "Refusing to run migrations or fixtures on the verified LIVE OMAG server" in integration
    assert "002_omagmes_configuration.sql" in integration
    assert "003_production_lot_workflow.sql" in integration
    assert "004_press_diff_lot_acc_views.sql" in integration
    assert "2026-11-17T10:15:23" in integration
