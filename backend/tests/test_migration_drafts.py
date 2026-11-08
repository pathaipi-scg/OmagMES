import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DRAFTS = ROOT / "db" / "review-only"


def test_migration_draft_is_review_only_and_all_tables_follow_id_first() -> None:
    sql = (DRAFTS / "001_omagmes_foundation.sql").read_text(encoding="utf-8")
    assert "REVIEW-ONLY DRAFT — DO NOT EXECUTE" in sql
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
