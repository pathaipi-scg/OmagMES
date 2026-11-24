from __future__ import annotations

from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

from backend.app.autolot_repository import SQLServerAutoLotRepository, detection_source_key, source_lot_number_changed
from backend.app.production_plans import PLAN_VIEW_COLUMNS, aggregate_plan_rows


ROOT = Path(__file__).resolve().parents[2]
SETUP = ROOT / "db" / "admin-review" / "autolot_clean_development_setup.sql"


def _view_row(
    *, prod_date: str = "2026-11-18", start: str = "2026-11-18T09:00:00",
    lot_no: str | None = "B181169101B", sequence: int | None = 1,
    shift_no: str | None = "1", shift_status: str = "RESOLVED",
    lot_status: str = "ALLOCATED", drop_count: int = 550, row_number: int = 1,
) -> dict:
    return {
        "ProdDate": datetime.fromisoformat(prod_date), "ShiftType": 3,
        "LotNo": lot_no, "rw": sequence, "LotSequence": sequence,
        "SourceRowNumber": row_number, "LotStart": datetime.fromisoformat(start),
        "LotStop": None, "ShiftNo": shift_no, "StartTime": "08:00:00",
        "StopTime": "20:00:00", "ShiftStatus": shift_status,
        "LotStatus": lot_status, "DropCnt": drop_count, "pDropCnt": 0,
    }


def test_normalization_accepts_sql_worktime_and_numbering_without_saved_shift_configuration() -> None:
    row = _view_row()
    persistent, preview, warnings = SQLServerAutoLotRepository.normalize_detections(
        [row], "2026-11-18", {"status": "DEFAULT"},
    )
    assert len(persistent) == 1
    assert not preview and not warnings
    item = persistent[0]
    assert item["lot_number"] == "B181169101B"
    assert item["lot_sequence"] == 1
    assert item["shift_number"] == 1
    assert item["shift_status"] == "RESOLVED"
    assert item["drop_count"] == 550
    assert item["source_key"] == detection_source_key(datetime(2026, 11, 18, 9))
    assert "shift_id" not in item and "schedule_save_id" not in item


def test_overnight_worktime_shift_and_sql_fields_are_not_recomputed_in_python() -> None:
    row = _view_row(start="2026-11-18T23:00:00", lot_no="B181169201B", shift_no="2")
    row.update({"StartTime": "20:00:00", "StopTime": "08:00:00", "DropCnt": 731})
    persistent, preview, warnings = SQLServerAutoLotRepository.normalize_detections(
        [row], "2026-11-18", None,
    )
    assert not preview and not warnings
    assert persistent[0]["shift_number"] == 2
    assert persistent[0]["source_start_time"] == "20:00"
    assert persistent[0]["source_stop_time"] == "08:00"
    assert persistent[0]["drop_count"] == 731
    assert persistent[0]["lot_number"] == "B181169201B"


def test_unresolved_worktime_and_sequence_exhaustion_remain_explicit_previews() -> None:
    unresolved = _view_row(lot_no=None, sequence=None, shift_no=None,
                           shift_status="AMBIGUOUS_WORKTIME_MATCH", lot_status="AMBIGUOUS_WORKTIME_MATCH")
    exhausted = _view_row(start="2026-11-18T10:00:00", lot_no=None, sequence=100,
                          lot_status="SEQUENCE_EXHAUSTED", row_number=2)
    persistent, preview, warnings = SQLServerAutoLotRepository.normalize_detections(
        [unresolved, exhausted], "2026-11-18", {"status": "NOT_SAVED"},
    )
    assert not persistent
    assert preview[0]["status"] == "SHIFT UNRESOLVED · AMBIGUOUS_WORKTIME_MATCH"
    assert preview[0]["lot_number"] is None
    assert preview[1]["status"] == "LOT NUMBER UNRESOLVED · SEQUENCE_EXHAUSTED"
    assert preview[1]["lot_number"] is None
    assert any("unresolved" in warning for warning in warnings)


def test_source_date_conflict_is_previewed_and_source_values_are_preserved() -> None:
    row = _view_row(prod_date="2026-11-19", start="2026-11-18T20:10:00",
                    lot_no="B191169201B", sequence=1, shift_no="2")
    persistent, preview, _warnings = SQLServerAutoLotRepository.normalize_detections(
        [row], "2026-11-18", None,
    )
    assert not persistent
    assert preview[0]["status"] == "SOURCE PRODUCTION DATE MISMATCH"
    assert preview[0]["lot_number"] == "B191169201B"
    assert preview[0]["drop_count"] == 550
    assert preview[0]["source_key"] == detection_source_key(datetime(2026, 11, 18, 20, 10))


def test_duplicate_start_lotno_and_date_shift_sequence_are_rejected() -> None:
    first = _view_row()
    duplicate_start = _view_row(lot_no="B181169102B", sequence=2, row_number=2)
    try:
        SQLServerAutoLotRepository.normalize_detections([first, duplicate_start], "2026-11-18")
    except Exception as exc:
        assert "duplicate LotStart" in str(exc)
    else:
        raise AssertionError("duplicate LotStart must fail closed")

    second_start = _view_row(start="2026-11-18T10:00:00", row_number=2)
    try:
        SQLServerAutoLotRepository.normalize_detections([first, second_start], "2026-11-18")
    except Exception as exc:
        assert "duplicate LotNo" in str(exc)
    else:
        raise AssertionError("duplicate LotNo must fail closed")


def test_plan_mapping_is_exact_and_requires_one_active_product_match() -> None:
    class Cursor:
        def execute(self, *_args):
            return None

        def fetchall(self):
            return [
                (1, "P-001", "Product One", None, True),
                (2, "p-001", "Lowercase Product", None, True),
                (3, "P-DUP", "Duplicate A", None, True),
                (4, "P-DUP", "Duplicate B", None, True),
            ]

    class Connection:
        def __enter__(self):
            return None, Cursor()

        def __exit__(self, *_args):
            return None

    repository = SQLServerAutoLotRepository(SimpleNamespace(_connection=lambda **_kwargs: Connection()))
    plans = [{"material_code": code} for code in ("P-001", "p-001", "P-DUP", "MISSING")]
    mapped = repository.plans_with_product_matches(plans)
    assert [item["product_match"]["status"] for item in mapped] == [
        "MATCHED", "MATCHED", "AMBIGUOUS", "PRODUCT NOT FOUND",
    ]
    assert mapped[0]["product_match"]["product_id"] == 1
    assert mapped[1]["product_match"]["product_id"] == 2


def test_clean_setup_is_one_identity_first_manual_script_and_never_touches_official_data() -> None:
    sql = SETUP.read_text(encoding="utf-8")
    for table in ("PlanIdentity", "AutoLot", "AutoLotAssignment"):
        declaration = sql.split(f"CREATE TABLE omagmes.{table}", 1)[1].split("\n    );", 1)[0]
        assert "id bigint IDENTITY(1,1)" in declaration
        assert "Rectime datetime NOT NULL" in declaration
    assert "CONSTRAINT UQ_AutoLot_SourceKey UNIQUE (SourceKey)" in sql
    assert "CONSTRAINT UQ_AutoLotAssignment_AutoLot UNIQUE (AutoLotID)" in sql
    assert "FOREIGN KEY (ProductID) REFERENCES omagmes.Product(id)" in sql
    assert "FOREIGN KEY (MouldID) REFERENCES omagmes.Mould(id)" in sql
    assert "PlanSnapshotJson nvarchar(max) NOT NULL" in sql
    assert "DO NOT EXECUTE AUTOMATICALLY" in sql
    assert "CREATE OR ALTER VIEW" not in sql.upper()
    assert "ALTER VIEW" not in sql.upper()
    assert "dbo.vw_PRESS_LotAuto" in sql and "dbo.vw_OmagPlan" in sql
    assert "dbo.PRESS" not in sql
    assert "DROP TABLE" not in sql.upper()
    assert "TRUNCATE TABLE" not in sql.upper()
    assert "DELETE FROM" not in sql.upper()
    assert "sysadmin" in sql.lower() and "manual review only" in sql.lower()


def test_legacy_012_and_013_files_are_marked_superseded() -> None:
    for name in ("012_auto_lot_independent_workflow.sql", "013_autolot_source_view.sql"):
        sql = (ROOT / "db" / "admin-review" / name).read_text(encoding="utf-8")
        assert "SUPERSEDED HISTORICAL DRAFT — DO NOT EXECUTE" in sql
        assert "autolot_clean_development_setup.sql" in sql


def test_source_lotno_comparison_and_plan_snapshot_contract() -> None:
    assert source_lot_number_changed("B231169201A", "B231169201B")
    assert not source_lot_number_changed("B231169201B  ", "B231169201B")
    assert source_lot_number_changed(None, "B231169201B")
    row = {column: None for column in PLAN_VIEW_COLUMNS}
    row.update({"MaterialCode": "P-001", "PlanName": "Plan A"})
    plan = aggregate_plan_rows([row])[0]
    assert plan["identity_kind"] == "CONTENT_FINGERPRINT_NOT_SOURCE_ID"
    assert len(plan["plan_key"]) == 64


def test_assignment_merge_keeps_every_sql_view_row_and_only_adds_saved_values() -> None:
    source_rows = [_view_row(), _view_row(start="2026-11-18T10:00:00", lot_no="B181169102B", sequence=2)]
    saved = [{
        "source_key": detection_source_key(datetime(2026, 11, 18, 9)),
        "auto_lot_id": 91,
        "plan_identity_id": 33,
        "plan_key": "f" * 64,
        "plan_name": "Plan A",
        "material_code": "P-001",
        "material_name": "Product plan",
        "product_id": 12,
        "product_code": "P-001",
        "product_name": "Product One",
        "mould_id": 18,
        "mould_code": "M018",
        "mould_name": "Mould 18",
    }]

    result = SQLServerAutoLotRepository.attach_saved_assignments(source_rows, saved)

    assert len(result) == len(source_rows)
    assert result[0]["LotNo"] == source_rows[0]["LotNo"]
    assert result[0]["DropCnt"] == source_rows[0]["DropCnt"]
    assert result[0]["auto_lot_id"] == 91
    assert result[0]["assignment"]["plan_name"] == "Plan A"
    assert result[1]["auto_lot_id"] is None
    assert result[1]["assignment"] is None


def test_assignment_setup_is_consolidated_into_existing_clean_setup_path() -> None:
    assert not (ROOT / "db" / "admin-review" / "autolot_plan_mould_assignment_clean_setup.sql").exists()


def test_reconcile_preserves_local_identity_when_unique_lot_start_is_corrected() -> None:
    class Cursor:
        def __init__(self) -> None:
            self.result = []
            self.statements: list[tuple[str, tuple]] = []

        def execute(self, query, parameters=()):
            self.statements.append((query, parameters))
            if "CASE WHEN OBJECT_ID" in query:
                self.result = [(1,)]
            elif "sp_getapplock" in query:
                self.result = [(0,)]
            elif "WHERE SourceKey=?" in query:
                self.result = []
            elif "RTRIM(LotNo)=?" in query:
                self.result = [(91,)]
            else:
                self.result = []
            return self

        def fetchone(self):
            return self.result.pop(0) if self.result else None

        def fetchall(self):
            rows, self.result = self.result, []
            return rows

    class Connection:
        def __init__(self, cursor) -> None:
            self.cursor = cursor

        def __enter__(self):
            return None, self.cursor

        def __exit__(self, *_args):
            return None

    cursor = Cursor()
    repository = SQLServerAutoLotRepository(SimpleNamespace(
        _connection=lambda **_kwargs: Connection(cursor),
    ))
    corrected = _view_row(start="2026-11-18T09:05:00")

    result = repository.reconcile("2026-11-18", None, [corrected])

    assert result["created"] == 0
    assert result["updated"] == 1
    updates = [(query, params) for query, params in cursor.statements if query.startswith("UPDATE omagmes.AutoLot SET")]
    assert len(updates) == 1
    assert updates[0][1][1] == detection_source_key(corrected["LotStart"])
    assert updates[0][1][-1] == 91
    assert not any(query.startswith("INSERT INTO omagmes.AutoLotAssignment") for query, _ in cursor.statements)
