from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEPLOY = PROJECT_ROOT / "db" / "admin-review" / "010_scg_lot_number_configuration.sql"
ROLLBACK = PROJECT_ROOT / "db" / "admin-review" / "010_scg_lot_number_configuration_rollback.sql"


def test_scg_numbering_migration_preserves_existing_rows_and_unique_constraints() -> None:
    sql = DEPLOY.read_text(encoding="utf-8")

    assert "DBA REVIEW ONLY" in sql
    assert "UQ_ProductionLot_LotNo" in sql
    assert "UQ_LotNumberSequence_Scope" in sql
    assert "MachineCode IN ('A','B')" in sql
    assert "PlantCode IN ('B','C')" in sql
    assert "ShiftCode IN ('1','2','3')" in sql
    assert "UPDATE omagmes.ProductionLot" not in sql
    assert "DELETE FROM omagmes.ProductionLot" not in sql
    assert "UPDATE omagmes.LotNumberSequence" not in sql
    assert "DELETE FROM omagmes.LotNumberSequence" not in sql
    assert "omag_mes" in sql.lower()


def test_scg_numbering_rollback_refuses_to_narrow_checks_over_new_rows() -> None:
    sql = ROLLBACK.read_text(encoding="utf-8")

    assert "DBA REVIEW ONLY" in sql
    assert "MachineCode <> 'B'" in sql
    assert "PlantCode <> 'C' OR ShiftCode NOT IN ('1','2')" in sql
    assert "MachineCode='B'" in sql
    assert "CHECK (PlantCode='C')" in sql
    assert "CHECK (ShiftCode IN ('1','2'))" in sql
