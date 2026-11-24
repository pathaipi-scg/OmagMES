from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime
from typing import Any

import pytest

from backend.app.lot_numbering import LotNumberingError
from backend.app.production_repository import REQUIRED_PRODUCTION_COLUMNS, REQUIRED_PRODUCTION_TABLES, SQLServerProductionRepository, classify_lot_change
from backend.app.sql_source import SQLSourceSettings, SourceUnavailable


class FakeCursor:
    def __init__(self) -> None:
        self.current: tuple[Any, ...] | None = None
        self.rows: list[tuple[Any, ...]] = []
        self.statements: list[str] = []

    def execute(self, sql: str, *_params: Any) -> "FakeCursor":
        self.statements.append(sql)
        self.current = None
        self.rows = []
        if "ORIGINAL_LOGIN()" in sql:
            self.current = ("OMAG_MES", "OMAG_MES", "OMAG", "SCGLS-NK\\SQLEXPRESS", "SQLEXPRESS", 0)
        return self

    def fetchone(self) -> tuple[Any, ...] | None:
        value = self.current
        self.current = None
        return value

    def fetchall(self) -> list[tuple[Any, ...]]:
        result = self.rows
        self.rows = []
        return result


class FakeConnection:
    def __init__(self) -> None:
        self.statements: list[str] = []
        self.cursor_instance = FakeCursor()
        self.timeout = 0
        self.commits = 0
        self.rollbacks = 0
        self.closed = False

    def cursor(self) -> FakeCursor:
        return self.cursor_instance

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1

    def close(self) -> None:
        self.closed = True


def live_settings() -> SQLSourceSettings:
    settings = SQLSourceSettings.from_environment()
    return replace(
        settings,
        mode="LIVE_READ_ONLY",
        server="127.0.0.1",
        database="OMAG",
        driver="ODBC Driver 17 for SQL Server",
        username="OMAG_MES",
        password="unit-test-only",
        target_confirmed=True,
    )


def test_write_transaction_does_not_require_application_write_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OMAGMES_PRODUCTION_WRITES_ENABLED", "false")
    connection = FakeConnection()
    repository = SQLServerProductionRepository(live_settings(), lambda *_args, **_kwargs: connection)

    with repository._connection(write=True):
        assert connection.commits == 0

    assert connection.commits == 1
    assert connection.rollbacks == 0
    assert connection.closed


def test_runtime_rejects_sysadmin_identity() -> None:
    connection = FakeConnection()
    connection.cursor_instance = ScriptedCursor({
        "ORIGINAL_LOGIN()": [("OMAG_MES", "OMAG_MES", "OMAG", "SCGLS-NK\\SQLEXPRESS", "SQLEXPRESS", 1)],
    })
    repository = SQLServerProductionRepository(live_settings(), lambda *_args, **_kwargs: connection)

    with pytest.raises(SourceUnavailable, match="must not be a sysadmin"):
        with repository._connection(write=True):
            pytest.fail("Sysadmin SQL identities must not reach write operations")
    assert connection.commits == 0
    assert connection.rollbacks == 0
    assert connection.closed


def test_same_product_and_color_continues_original_lot_across_shift_and_date() -> None:
    # Shift/date context is intentionally absent from the boundary classifier.
    assert classify_lot_change(11, "Grey", 11, "Grey") == "CONTINUE"


def test_product_or_color_change_requires_a_new_lot() -> None:
    assert classify_lot_change(11, "Grey", 12, "Grey") == "PRODUCT_CHANGE"
    assert classify_lot_change(11, "Grey", 11, "Red") == "COLOR_CHANGE"


def test_official_lot_creation_requires_resolved_numbering_context() -> None:
    connection = FakeConnection()
    repository = SQLServerProductionRepository(live_settings(), lambda *_args, **_kwargs: connection)

    with pytest.raises(SourceUnavailable, match="Official Lot No. generation is not enabled"):
        repository.create_lot({"product_id": 1, "color": "Grey", "lot_name": "not-created", "operator_id": "operator"})

    assert connection.commits == 0
    assert connection.closed is False


def test_explicit_write_transaction_uses_omagmes_identity_and_commits_only_on_exit() -> None:
    connection = FakeConnection()
    connection_strings: list[str] = []

    def connect(connection_string: str, **_kwargs: Any) -> FakeConnection:
        connection_strings.append(connection_string)
        return connection

    repository = SQLServerProductionRepository(live_settings(), connect)
    with repository._connection(write=True):
        assert connection.commits == 0

    assert connection.commits == 1
    assert connection.rollbacks == 0
    assert connection.closed
    assert repository._last_identity is not None
    assert repository._last_identity["sql_login"] == "OMAG_MES"
    assert "ApplicationIntent=ReadOnly" not in connection_strings[0]


def test_failed_write_transaction_rolls_back() -> None:
    connection = FakeConnection()
    repository = SQLServerProductionRepository(live_settings(), lambda *_args, **_kwargs: connection)

    with pytest.raises(SourceUnavailable, match=r"production transaction failed \(RuntimeError\)"):
        with repository._connection(write=True):
            raise RuntimeError("test failure")

    assert connection.commits == 0
    assert connection.rollbacks == 1
    assert connection.closed


def test_live_bootstrap_never_returns_mock_lots_when_migration_is_missing() -> None:
    connection = FakeConnection()
    repository = SQLServerProductionRepository(live_settings(), lambda *_args, **_kwargs: connection)

    result = repository.bootstrap({"products": [{"id": 99}], "lots": [{"id": 998}], "reject_reasons": [{"code": "DEMO"}]})

    assert result["products"] == []
    assert result["lots"] == []
    assert result["reject_reasons"] == []
    assert result["mode"] == "LIVE SOURCES · LOT SCHEMA NOT INSTALLED"
    assert result["production_storage"]["missing_tables"] == list(REQUIRED_PRODUCTION_TABLES)
    assert connection.rollbacks == 1
    assert connection.closed


def test_schema_health_detects_missing_columns_when_tables_exist() -> None:
    responses = base_write_responses()
    responses["SELECT t.name,c.name FROM sys.tables"] = [[
        (table, column)
        for table, columns in REQUIRED_PRODUCTION_COLUMNS.items()
        for column in columns
        if not (table == "CuringInputEntry" and column == "OperatorConfirmed")
    ]]
    connection = FakeConnection()
    connection.cursor_instance = ScriptedCursor(responses)
    repository = SQLServerProductionRepository(live_settings(), lambda *_args, **_kwargs: connection)

    status = repository.health()

    assert status["missing_tables"] == []
    assert status["missing_columns"] == ["CuringInputEntry.OperatorConfirmed"]
    assert status["schema_ready"] is False


class ScriptedCursor(FakeCursor):
    def __init__(self, responses: dict[str, list[Any]], *, fail_on: str | None = None) -> None:
        super().__init__()
        self.responses = responses
        self.fail_on = fail_on

    def execute(self, sql: str, *_params: Any) -> "ScriptedCursor":
        self.statements.append(sql)
        self.current = None
        if self.fail_on and self.fail_on in sql:
            raise RuntimeError("simulated audit failure")
        for marker, values in self.responses.items():
            if marker in sql and values:
                result = values.pop(0)
                if isinstance(result, list):
                    self.rows = result
                else:
                    self.current = result
                break
        return self


def persisted_entry_row(*, drops: int = 12, wet_good: int = 30) -> tuple[Any, ...]:
    return (
        201, 501, drops, wet_good, None, None, "MANUAL", None, "operator",
        datetime(2026, 11, 8, 8, 0), datetime(2026, 11, 8, 8, 0),
        date(2026, 11, 8), 2, 1,
    )


def scripted_repository(
    responses: dict[str, list[Any]],
    *,
    fail_on: str | None = None,
) -> tuple[SQLServerProductionRepository, FakeConnection]:
    connection = FakeConnection()
    connection.cursor_instance = ScriptedCursor(responses, fail_on=fail_on)
    repository = SQLServerProductionRepository(live_settings(), lambda *_args, **_kwargs: connection)
    return repository, connection


def base_write_responses() -> dict[str, list[Any]]:
    return {
        "ORIGINAL_LOGIN()": [("OMAG_MES", "OMAG_MES", "OMAG", "SCGLS-NK\\SQLEXPRESS", "SQLEXPRESS", 0)],
        "SELECT name FROM sys.tables": [[(name,) for name in REQUIRED_PRODUCTION_TABLES]],
        "SELECT t.name,c.name FROM sys.tables": [[
            (table, column)
            for table, columns in REQUIRED_PRODUCTION_COLUMNS.items()
            for column in columns
        ]],
    }


def test_scg_proposals_skip_sequence_state_and_existing_official_numbers_without_reserving() -> None:
    responses = base_write_responses()
    responses.update({
        "SELECT LastSequence FROM omagmes.LotNumberSequence": [(1,)],
        "SELECT MAX(TRY_CONVERT(int,SUBSTRING(LotNo,9,2)))": [(2,)],
    })
    repository, connection = scripted_repository(responses)

    proposals = repository.propose_lot_numbers(
        production_date="2026-11-13", shift_code="2", count=2,
    )

    assert [item["proposed_lot_number"] for item in proposals] == ["B131169203A", "B131169204A"]
    assert [item["sequence"] for item in proposals] == [3, 4]
    assert all(item["reserved"] is False for item in proposals)
    assert all("SELECT" in sql for sql in connection.cursor_instance.statements if "LotNumberSequence" in sql or "ProductionLot WHERE" in sql)
    assert connection.commits == 0
    assert connection.rollbacks == 1


def test_scg_proposal_fails_when_sequence_scope_is_exhausted() -> None:
    responses = base_write_responses()
    responses.update({
        "SELECT LastSequence FROM omagmes.LotNumberSequence": [(99,)],
        "SELECT MAX(TRY_CONVERT(int,SUBSTRING(LotNo,9,2)))": [(98,)],
    })
    repository, connection = scripted_repository(responses)

    with pytest.raises(LotNumberingError, match="exhausted"):
        repository.propose_lot_number(production_date="2026-11-13", shift_code="3")

    assert connection.commits == 0
    assert connection.rollbacks == 1


def test_production_save_commits_entry_and_save_audit_together() -> None:
    responses = base_write_responses()
    responses.update({
        "SELECT ProductStandardRevisionID": [(7, 10, 4.5)],
        "INSERT INTO omagmes.ProductionEntry (": [(201,)],
        "SELECT id,ProductionLotID,PressDrops,": [persisted_entry_row()],
    })
    repository, connection = scripted_repository(responses)

    result = repository.save_production({
        "lot_id": 501, "actual_drops": 12, "wet_good_pieces": 30,
        "operator_id": "operator", "operator_confirmed": True,
        "production_at": datetime(2026, 11, 8, 8, 0),
        "production_date": "2026-11-08", "shift_schedule_version_id": 2, "shift_id": 1,
    })

    statements = connection.cursor_instance.statements
    assert result["id"] == 201
    assert any("ProductionEntryChangeHistory" in sql and "'SAVE'" in sql for sql in statements)
    assert connection.commits == 1
    assert connection.rollbacks == 0
    assert connection.closed


def test_production_edit_and_delete_commit_audit_history() -> None:
    edit_responses = base_write_responses()
    edit_responses.update({
        "SELECT id,ProductionLotID,PressDrops,": [persisted_entry_row(), persisted_entry_row(drops=18, wet_good=42)],
        "INSERT INTO omagmes.ProductionEntryCorrection": [(301,)],
        "SELECT id,OldPressDrops": [(301, 12, 18, 30, 42, "reviewer", datetime(2026, 11, 8, 9, 0), "review")],
    })
    edit_repository, edit_connection = scripted_repository(edit_responses)
    edited = edit_repository.correct_production(
        201, actual_drops=18, wet_good_pieces=42, reason="review",
        operator_id="reviewer", operator_confirmed=True,
    )
    assert edited["actual_drops"] == 18
    assert any("ProductionEntryChangeHistory" in sql and "'EDIT'" in sql for sql in edit_connection.cursor_instance.statements)
    assert edit_connection.commits == 1
    assert edit_connection.rollbacks == 0

    delete_responses = base_write_responses()
    delete_responses["SELECT id,ProductionLotID,PressDrops,"] = [persisted_entry_row()]
    delete_repository, delete_connection = scripted_repository(delete_responses)
    deleted = delete_repository.delete_production(
        201, reason="duplicate entry", operator_id="reviewer", operator_confirmed=True,
    )
    statements = delete_connection.cursor_instance.statements
    assert deleted["id"] == 201
    assert any("IsDeleted=1" in sql for sql in statements)
    assert any("ProductionEntryChangeHistory" in sql and "'DELETE'" in sql for sql in statements)
    assert delete_connection.commits == 1
    assert delete_connection.rollbacks == 0


def test_production_save_rolls_back_when_audit_insert_fails() -> None:
    responses = base_write_responses()
    responses.update({
        "SELECT ProductStandardRevisionID": [(7, 10, 4.5)],
        "INSERT INTO omagmes.ProductionEntry (": [(201,)],
        "SELECT id,ProductionLotID,PressDrops,": [persisted_entry_row()],
    })
    repository, connection = scripted_repository(
        responses, fail_on="INSERT INTO omagmes.ProductionEntryChangeHistory",
    )

    with pytest.raises(SourceUnavailable, match=r"production transaction failed \(RuntimeError\)"):
        repository.save_production({
            "lot_id": 501, "actual_drops": 12, "wet_good_pieces": 30,
            "operator_id": "operator", "operator_confirmed": True,
            "production_at": datetime(2026, 11, 8, 8, 0),
            "production_date": "2026-11-08", "shift_schedule_version_id": 2, "shift_id": 1,
        })

    assert connection.commits == 0
    assert connection.rollbacks == 1
    assert connection.closed
