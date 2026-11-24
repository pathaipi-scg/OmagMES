from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient

from backend.app import main
from backend.app.live_autocal import (
    AUTORUN_TAG,
    PRESS_COUNTER_TAG,
    calculate_camera_pieces,
    calculate_press_drops,
    calculate_wet_rejects,
)
from backend.app.shift_schedule import initial_schedule_versions
from backend.app.sql_source import DROP_COUNTER_TAG, SQLServerReadOnlyRepository, SQLSourceSettings, SourceUnavailable
from backend.app.production_plans import PLAN_VIEW_COLUMNS


class FakeCursor:
    def __init__(self, connection: "FakeConnection") -> None:
        self.connection = connection
        self.description: list[tuple[str]] = []
        self._one: tuple[Any, ...] | None = None
        self._many: list[tuple[Any, ...]] = []

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> "FakeCursor":
        self.connection.statements.append((sql, params, self.connection.timeout))
        self._one = None
        self._many = []
        if "@@SERVERNAME" in sql:
            self._one = ("OMAG_MES", "OMAG_MES", "SCGLS-NK\\SQLEXPRESS", "OMAG", "SQLEXPRESS", "dbo", 0)
        elif "HAS_PERMS_BY_NAME" in sql:
            self._one = (1, 0, 0, 0, 0, 0)
        elif "INFORMATION_SCHEMA.COLUMNS" in sql:
            table = params[-1]
            cols = {
                "PRESS": ["id", "_NAME", "_VALUE", "_TIMESTAMP", "_QUALITY"],
                "REJECT_WET": ["id", "_NAME", "_VALUE", "_TIMESTAMP", "_QUALITY"],
                "product_count": ["id", "TimeStamp", "line", "value_cnt", "quality_flag", "is_duplicate"],
                "vw_OmagPlan": list(PLAN_VIEW_COLUMNS),
                "vw_PRESS_LotAuto": ["ProdDate", "ShiftType", "LotNo", "rw", "LotStart", "LotStop", "ShiftNo", "StartTime", "StopTime", "pDropCnt", "DropCnt"],
            }[table]
            self.description = [("COLUMN_NAME",)]
            self._many = [(column,) for column in cols]
        elif sql.startswith("SELECT TOP (?)"):
            if "FROM dbo.vw_PRESS_LotAuto" in sql:
                self.description = [(name,) for name in ("ProdDate", "ShiftType", "LotNo", "rw", "LotStart", "LotStop", "ShiftNo", "StartTime", "StopTime", "pDropCnt", "DropCnt")]
                self._many = [(datetime(2026, 11, 23).date(), 3, "B231169201B", 1,
                               datetime(2026, 11, 23, 10, 23), datetime(2026, 11, 23, 17, 23),
                               "2", datetime.strptime("20:00", "%H:%M").time(),
                               datetime.strptime("08:00", "%H:%M").time(), 0, 90)]
                return self
            if "FROM dbo.vw_OmagPlan" in sql:
                self.description = [(name,) for name in PLAN_VIEW_COLUMNS]
                return self
            if "FROM dbo.product_count" in sql:
                self.description = [(name,) for name in ("id", "TimeStamp", "quality_flag", "is_duplicate", "line", "value_cnt")]
                self._many = [(31, datetime(2026, 11, 8, 7, 10), "192", "0", "wet", 4)]
                return self
            self.description = [(name,) for name in ("id", "_NAME", "_VALUE", "_TIMESTAMP", "_QUALITY")]
            if "_NAME = ?" in sql:
                tag = params[1]
                timestamp = params[2] + timedelta(minutes=5) if len(params) >= 4 else datetime(2026, 11, 8, 7, 5)
                value = 1 if tag == AUTORUN_TAG else 100
                self._many = [(17, tag, value, timestamp, 192)]
                if tag == DROP_COUNTER_TAG and len(params) >= 4:
                    self._many.append((18, tag, value + 1, timestamp + timedelta(minutes=5), 192))
            elif "_NAME IN" in sql:
                self._many = [(18, PRESS_COUNTER_TAG, 44, datetime(2026, 11, 8, 7, 10), 192)]
            elif "_NAME LIKE ?" in sql:
                self._many = [
                    (20, "MODBUS.WET_REJECT.cntR1", 6, datetime(2026, 11, 8, 7, 10), 192),
                    (21, "MODBUS.WET_REJECT.R1", 1, datetime(2026, 11, 8, 7, 10), 192),
                ]
        elif sql.startswith("SELECT ["):
            self.description = [(name.strip("[]"),) for name in ("id", "TimeStamp", "quality_flag", "is_duplicate", "line", "value_cnt")]
            self._many = []
        return self

    def fetchone(self) -> tuple[Any, ...] | None:
        value = self._one
        self._one = None
        if value is not None:
            return value
        if self._many:
            return self._many.pop(0)
        return None

    def fetchall(self) -> list[tuple[Any, ...]]:
        values = self._many
        self._many = []
        return values


class FakeConnection:
    def __init__(self) -> None:
        self.statements: list[tuple[str, tuple[Any, ...], int]] = []
        self.closed = False
        self.timeout = 0

    def cursor(self) -> FakeCursor:
        return FakeCursor(self)

    def close(self) -> None:
        self.closed = True


def live_settings(**updates: Any) -> SQLSourceSettings:
    values = dict(
        mode="LIVE_READ_ONLY",
        server="127.0.0.1",
        database="OMAG",
        driver="ODBC Driver 17 for SQL Server",
        username="OMAG_MES",
        password="unit-test-password",
        encrypt=True,
        trust_server_certificate=False,
        target_confirmed=True,
        select_only_confirmed=True,
        connect_timeout=3,
        query_timeout=7,
        camera_id_column="id",
        camera_timestamp_column="TimeStamp",
        camera_quality_column="quality_flag",
        camera_duplicate_column="is_duplicate",
        camera_quality_values=("192",),
        camera_duplicate_clear_values=("0", "False"),
        camera_metadata_reviewed=True,
        historian_metadata_reviewed=True,
        camera_boundary_policy_confirmed=True,
        source_timezone="Asia/Bangkok",
        source_timezone_confirmed=True,
        valid_plc_quality_codes=(192,),
        max_counter_gap_minutes=20,
        lot_window_source_confirmed=False,
    )
    values.update(updates)
    return SQLSourceSettings(**values)


def observation(tag: str, moment: str, value: int, *, quality: int = 192, row_id: int = 1) -> dict[str, Any]:
    return {"id": row_id, "_NAME": tag, "_VALUE": value, "_TIMESTAMP": moment, "_QUALITY": quality}


def test_live_source_refuses_sa_fallback_identity() -> None:
    settings = live_settings(username="sa")
    assert any("dedicated OMAG_MES login" in error for error in settings.live_gate_errors())


def window(start: str = "2026-11-08T06:00:00+07:00", end: str = "2026-11-08T09:00:00+07:00") -> tuple[datetime, datetime]:
    return datetime.fromisoformat(start), datetime.fromisoformat(end)


def test_press_query_is_parameterized_and_time_bounded() -> None:
    connection = FakeConnection()
    repository = SQLServerReadOnlyRepository(live_settings(), lambda *_args, **_kwargs: connection)
    start, end = window()

    rows = repository.press_observations(start, end, 75)

    statement, params, timeout = next(item for item in connection.statements if "SELECT TOP (?)" in item[0])
    assert rows[0]["_NAME"] == PRESS_COUNTER_TAG
    assert "_NAME = ?" in statement
    assert "AutoRun" not in statement
    assert "_TIMESTAMP >= ? AND _TIMESTAMP < ?" in statement
    assert params == (75, PRESS_COUNTER_TAG, start.replace(tzinfo=None), end.replace(tzinfo=None))
    assert timeout == 7
    assert connection.timeout == 7
    assert connection.closed


def test_dropcnt_query_uses_exact_tag_separate_from_productcnt() -> None:
    connection = FakeConnection()
    repository = SQLServerReadOnlyRepository(live_settings(), lambda *_args, **_kwargs: connection)
    start, end = window()

    rows = repository.dropcnt_observations(start, end, 75)

    statement, params, _ = next(item for item in connection.statements if "SELECT TOP (?)" in item[0])
    assert rows[0]["_NAME"] == DROP_COUNTER_TAG
    assert params == (75, DROP_COUNTER_TAG, start.replace(tzinfo=None), end.replace(tzinfo=None))
    assert "_TIMESTAMP >= ? AND _TIMESTAMP < ?" in statement
    assert "ProductCnt" not in statement
    permission_checks = [params for sql, params, _ in connection.statements if "HAS_PERMS_BY_NAME" in sql]
    assert permission_checks == [("dbo.PRESS",) * 6]
    assert all(sql.lstrip().upper().startswith("SELECT") for sql, _, _ in connection.statements)


def test_production_plan_query_uses_exact_pis_scope_as_parameters() -> None:
    connection = FakeConnection()
    repository = SQLServerReadOnlyRepository(live_settings(), lambda *_args, **_kwargs: connection)

    result = repository.production_plan_snapshots(limit=25)

    statement, params, _ = next(item for item in connection.statements if "FROM dbo.vw_OmagPlan" in item[0])
    assert result["source"] == "OMAG.dbo.vw_OmagPlan"
    assert result["filters"] == {"Company": "SCGLS", "Machine": "OMAG", "Plant": "3251"}
    assert "WHERE [Company] = ? AND [Machine] = ? AND [Plant] = ?" in statement
    assert params == (26, "SCGLS", "OMAG", "3251")
    assert "SCGLS" not in statement and "OMAG" not in statement and "3251" not in statement
    assert connection.closed


def test_production_plan_query_filters_selected_date_with_parameters() -> None:
    connection = FakeConnection()
    repository = SQLServerReadOnlyRepository(live_settings(), lambda *_args, **_kwargs: connection)

    result = repository.production_plan_snapshots(limit=25, production_date="2026-11-17")

    statement, params, _ = next(item for item in connection.statements if "FROM dbo.vw_OmagPlan" in item[0])
    assert result["production_date"] == "2026-11-17"
    assert "[StartTime] >= ? AND [StartTime] < ?" in statement
    assert params == (26, "SCGLS", "OMAG", "3251", datetime(2026, 11, 17).date(), datetime(2026, 11, 18).date())
    assert "2026-11-17" not in statement
    assert connection.closed


def test_production_plan_query_rejects_noncanonical_date() -> None:
    repository = SQLServerReadOnlyRepository(live_settings(), lambda *_args, **_kwargs: FakeConnection())

    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        repository.production_plan_snapshots(production_date="2026-11-17T00:00:00")


def test_query_timeout_uses_connection_property_supported_by_pyodbc() -> None:
    connection = FakeConnection()
    repository = SQLServerReadOnlyRepository(live_settings(), lambda *_args, **_kwargs: connection)

    result = repository.health()

    assert result["connected"] is True
    assert connection.timeout == 7
    assert connection.closed


def test_current_wet_status_uses_autorun_tag_and_verified_quality() -> None:
    connection = FakeConnection()
    repository = SQLServerReadOnlyRepository(live_settings(), lambda *_args, **_kwargs: connection)

    status = repository.latest_wet_status()

    assert status["status"] == "RUNNING"
    assert status["observation"]["_NAME"] == AUTORUN_TAG
    assert status["observation"]["_QUALITY"] == 192


def test_reject_query_filters_button_state_tags_even_if_returned_by_driver() -> None:
    connection = FakeConnection()
    repository = SQLServerReadOnlyRepository(live_settings(), lambda *_args, **_kwargs: connection)
    start, end = window()

    rows = repository.wet_reject_observations(start, end, 50)
    statement, params, _ = next(item for item in connection.statements if "SELECT TOP (?)" in item[0])

    assert [row["_NAME"] for row in rows] == ["MODBUS.WET_REJECT.cntR1"]
    assert "_NAME LIKE ?" in statement
    assert params[1] == "MODBUS.WET_REJECT.cntR%"
    assert "R1" not in [row["_NAME"] for row in rows]


def test_available_reject_counters_are_dynamic_and_latest_values_stay_cumulative() -> None:
    connection = FakeConnection()
    repository = SQLServerReadOnlyRepository(live_settings(), lambda *_args, **_kwargs: connection)
    start, end = window()

    rows = repository.latest_wet_reject_counters(start, end, 50)

    assert [row["_NAME"] for row in rows] == ["MODBUS.WET_REJECT.cntR1"]
    assert rows[0]["_VALUE"] == 6


def test_approved_localhost_config_can_connect_with_dedicated_login() -> None:
    calls = 0

    def should_not_connect(*_args: Any, **_kwargs: Any) -> FakeConnection:
        nonlocal calls
        calls += 1
        return FakeConnection()

    repository = SQLServerReadOnlyRepository(live_settings(server="127.0.0.1"), should_not_connect)
    repository.latest_press_counter()
    assert calls == 1


def test_camera_metadata_is_discovered_before_any_camera_data_query() -> None:
    connection = FakeConnection()
    repository = SQLServerReadOnlyRepository(live_settings(camera_metadata_reviewed=False), lambda *_args, **_kwargs: connection)

    columns = repository.camera_metadata()

    assert columns == ["id", "TimeStamp", "line", "value_cnt", "quality_flag", "is_duplicate"]
    assert all("INFORMATION_SCHEMA.COLUMNS" in sql or "HAS_PERMS_BY_NAME" in sql or "@@SERVERNAME" in sql for sql, _, _ in connection.statements)


def test_historian_row_query_waits_for_metadata_review() -> None:
    connection = FakeConnection()
    repository = SQLServerReadOnlyRepository(live_settings(historian_metadata_reviewed=False), lambda *_args, **_kwargs: connection)
    start, end = window()

    with pytest.raises(SourceUnavailable, match="metadata has not been reviewed"):
        repository.press_observations(start, end, 10)

    assert not any("SELECT TOP (?)" in sql for sql, _, _ in connection.statements)
    assert any("INFORMATION_SCHEMA.COLUMNS" in sql for sql, _, _ in connection.statements)


def test_camera_query_uses_reviewed_fields_and_parameterized_bounded_window() -> None:
    connection = FakeConnection()
    repository = SQLServerReadOnlyRepository(live_settings(), lambda *_args, **_kwargs: connection)
    start, end = window()

    rows = repository.wet_camera_observations(start, end, 25)

    statement, params, _ = next(item for item in connection.statements if "FROM dbo.product_count" in item[0])
    assert rows[0]["source_id"] == 31
    assert "WHERE [line] = ?" in statement
    assert "TimeStamp" not in statement or "[TimeStamp]" in statement
    assert params == (25, "wet", start.replace(tzinfo=None), end.replace(tzinfo=None))


def test_read_only_preflight_rejects_a_login_with_write_permission() -> None:
    class WritableCursor(FakeCursor):
        def execute(self, sql: str, params: tuple[Any, ...] = ()) -> FakeCursor:
            super().execute(sql, params)
            if "HAS_PERMS_BY_NAME" in sql:
                self._one = (1, 0, 1, 0, 0, 0)
            return self

    class WritableConnection(FakeConnection):
        def cursor(self) -> WritableCursor:
            return WritableCursor(self)

    connection = WritableConnection()
    repository = SQLServerReadOnlyRepository(live_settings(), lambda *_args, **_kwargs: connection)

    rows = repository.dropcnt_observations(*window(), 10)
    assert rows[0]["_NAME"] == DROP_COUNTER_TAG
    assert repository._last_preflight["read_only_permissions_verified"] is False
    assert repository._last_preflight["write_capabilities_present"] == ["UPDATE"]
    assert repository._last_preflight["source_queries_select_only_enforced"] is True
    assert connection.closed


def test_source_repository_rejects_non_select_sql_before_cursor_execution() -> None:
    for sql in (
        "DELETE FROM dbo.PRESS",
        "SELECT 1; DELETE FROM dbo.PRESS",
    ):
        with pytest.raises(SourceUnavailable, match="SELECT statements only"):
            SQLServerReadOnlyRepository._execute_select(FakeCursor(FakeConnection()), sql)
    SQLServerReadOnlyRepository._execute_select(FakeCursor(FakeConnection()), "SELECT 'DELETE' AS sample /* UPDATE dbo.PRESS */")


def test_connection_error_does_not_expose_exception_text_or_credentials() -> None:
    repository = SQLServerReadOnlyRepository(
        live_settings(),
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("unit-test-password; private connection string")),
    )

    result = repository.health()

    assert result["connected"] is False
    assert "RuntimeError" in result["error"]
    assert "unit-test-password" not in result["error"]
    assert "connection string" not in result["error"]


def test_all_executed_source_statements_are_selects() -> None:
    connection = FakeConnection()
    repository = SQLServerReadOnlyRepository(live_settings(), lambda *_args, **_kwargs: connection)
    start, end = window()
    repository.press_observations(start, end, 20)
    repository.wet_reject_observations(start, end, 20)
    repository.camera_metadata()

    assert connection.statements
    assert all(sql.lstrip().upper().startswith("SELECT") for sql, _, _ in connection.statements)


def test_auto_lot_candidate_api_is_fail_closed_in_mock_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = live_settings(mode="MOCK")
    connection = FakeConnection()
    repository = SQLServerReadOnlyRepository(settings, lambda *_args, **_kwargs: connection)
    query_calls = 0
    original_query = repository.dropcnt_observations

    def observe_query(*args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        nonlocal query_calls
        query_calls += 1
        return original_query(*args, **kwargs)

    repository.dropcnt_observations = observe_query  # type: ignore[method-assign]
    monkeypatch.setattr(main, "source_repository", repository)
    monkeypatch.setattr(main.configuration_repository, "get_cutoff_versions", lambda: [
        {"id": 1, "effective_from": "2026-01-01", "cutoff_time": "07:00", "time_zone": "Asia/Bangkok"},
    ])
    monkeypatch.setattr(main.configuration_repository, "get_shift_versions", lambda: initial_schedule_versions())

    response = TestClient(main.app).get("/api/auto-lot/candidates", params={"production_date": "2026-11-10"})

    assert response.status_code == 200
    assert response.json()["available"] is False
    assert response.json()["candidates"] == []
    assert response.json()["production_day_window"]["interval_semantics"] == "[start, end)"
    assert query_calls == 0
    assert connection.statements == []


def test_auto_lot_candidate_api_never_calculates_python_diff(monkeypatch: pytest.MonkeyPatch) -> None:
    connection = FakeConnection()
    repository = SQLServerReadOnlyRepository(live_settings(), lambda *_args, **_kwargs: connection)
    monkeypatch.setattr(main, "source_repository", repository)
    monkeypatch.setattr(main.configuration_repository, "get_cutoff_versions", lambda: [
        {"id": 1, "effective_from": "2026-01-01", "cutoff_time": "07:00", "time_zone": "Asia/Bangkok"},
    ])
    monkeypatch.setattr(main.configuration_repository, "get_shift_versions", lambda: initial_schedule_versions())
    monkeypatch.setattr(main.store, "auto_lot_candidate_reviews", [])
    monkeypatch.setattr(main.store, "auto_lot_candidate_snapshots", {})
    client = TestClient(main.app)

    response = client.get("/api/auto-lot/candidates", params={"production_date": "2026-11-10"})

    assert response.status_code == 200
    result = response.json()
    assert result["available"] is True
    assert result["candidates"] == []
    assert any("SQL Server views" in warning for warning in result["warnings"])
    assert "sql_candidate_sync" not in result
    assert any("FROM dbo.PRESS" in sql and "SELECT" in sql for sql, _, _ in connection.statements)
    assert all(sql.lstrip().upper().startswith("SELECT") for sql, _, _ in connection.statements)


def test_press_lot_api_repository_reads_only_bounded_sql_views() -> None:
    connection = FakeConnection()
    repository = SQLServerReadOnlyRepository(live_settings(), lambda *_args, **_kwargs: connection)
    start, end = window()

    assert repository.press_lot_summary("2026-11-10", 50) == []
    assert repository.press_lot_acc(start, end, 75) == []

    view_queries = [(sql, params) for sql, params, _ in connection.statements if "omagmes.v_PressLot" in sql]
    assert len(view_queries) == 2
    assert "WHERE ProductionDate=?" in view_queries[0][0]
    assert view_queries[0][1] == (51, "2026-11-10")
    assert "WHERE RecTime>=? AND RecTime<?" in view_queries[1][0]
    assert view_queries[1][1][0] == 76
    assert all(sql.lstrip().upper().startswith("SELECT") for sql, _, _ in connection.statements)


def test_press_lot_auto_reads_sql_generated_number_shift_and_count() -> None:
    connection = FakeConnection()
    repository = SQLServerReadOnlyRepository(live_settings(), lambda *_args, **_kwargs: connection)

    result = repository.press_lot_auto("2026-11-23", limit=10)

    assert result["source"] == "OMAG.dbo.vw_PRESS_LotAuto"
    assert result["production_date"] == "2026-11-23"
    assert result["rows"][0]["LotNo"] == "B231169201B"
    assert result["rows"][0]["ShiftType"] == 3
    assert result["rows"][0]["ShiftNo"] == "2"
    assert result["rows"][0]["DropCnt"] == 90
    query = next(sql for sql, _, _ in connection.statements if "FROM dbo.vw_PRESS_LotAuto" in sql)
    assert "WHERE ProdDate=?" in query
    assert "ORDER BY LotStart,LotNo,rw" in query
    assert all(sql.lstrip().upper().startswith("SELECT") for sql, _, _ in connection.statements)


def test_production_overview_uses_source_autolot_view_and_does_not_recalculate_shift(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = live_settings()
    source_row = {
        "ProdDate": datetime(2026, 11, 17).date(), "ShiftType": 3, "LotNo": "B171169201B", "rw": 2,
        "LotSequence": 1, "SourceRowNumber": 2, "ShiftStatus": "RESOLVED", "LotStatus": "ALLOCATED",
        "LotStart": datetime(2026, 11, 17, 21), "LotStop": datetime(2026, 11, 18, 7, 50),
        "ShiftNo": "2", "StartTime": datetime.strptime("20:00", "%H:%M").time(),
        "StopTime": datetime.strptime("08:00", "%H:%M").time(), "pDropCnt": 0, "DropCnt": 833,
    }

    class ViewSource:
        def __init__(self) -> None:
            self.settings = settings
            self.dates: list[str] = []

        def press_lot_auto(self, production_date: str, _limit: int = 5000) -> dict[str, Any]:
            self.dates.append(production_date)
            rows = [source_row] if production_date == "2026-11-17" else []
            return {"source": "OMAG.dbo.vw_PRESS_LotAuto", "rows": rows, "identity_strategy": "LotStart"}

    class AutoLotReader:
        @staticmethod
        def normalize_detections(rows: list[dict[str, Any]], production_date: str):
            return main.SQLServerAutoLotRepository.normalize_detections(rows, production_date)

        @staticmethod
        def is_available() -> bool:
            return False

        @staticmethod
        def list_for_date(_production_date: str) -> list[dict[str, Any]]:
            return []

    source = ViewSource()
    monkeypatch.setattr(main, "source_repository", source)
    monkeypatch.setattr(main, "auto_lot_repository", AutoLotReader())
    monkeypatch.setattr(main, "production_repository", type("ProductionStore", (), {
        "production_day_lots": staticmethod(lambda *_args: []),
    })())
    monkeypatch.setattr(main, "read_cutoff_versions", lambda: [
        {"id": 1, "effective_from": "2026-01-01", "cutoff_time": "07:00", "time_zone": "Asia/Bangkok"},
    ])
    monkeypatch.setattr(main.configuration_repository, "get_daily_shift_configuration", lambda selected: {
        "status": "SAVED", "production_date": selected, "selected_type": 3, "type_code": "TYPE 3",
        "configuration_save_id": 33, "schedule": {"effective_production_date": selected, "periods": [
            {"shift_id": 2, "shift_number": 2, "period_order": 1, "start_time": "20:00", "end_time": "08:00", "end_next_day": True, "active": True},
            {"shift_id": 10004, "shift_number": 3, "period_order": 2, "start_time": "08:00", "end_time": "20:00", "end_next_day": False, "active": True},
        ]},
    })

    result = main.production_overview("2026-11-17")

    assert source.dates == ["2026-11-17"]
    assert result["source"] == "OMAG.dbo.vw_PRESS_LotAuto"
    assert result["auto_lots"][0] == source_row
    assert result["auto_lots"][0]["LotNo"] == "B171169201B"
    assert result["auto_lots"][0]["DropCnt"] == 833
    assert result["auto_lots"][0]["ShiftNo"] == "2"
    assert result["press_error"] is None


def test_production_overview_does_not_require_saved_shift_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = live_settings()

    class ViewSource:
        def __init__(self) -> None:
            self.settings = settings
            self.queries = 0

        def press_lot_auto(self, production_date: str, _limit: int = 5000) -> dict[str, Any]:
            self.queries += 1
            return {"source": "OMAG.dbo.vw_PRESS_LotAuto", "rows": [{
                "ProdDate": datetime.fromisoformat(production_date).date(), "ShiftType": 3,
                "LotNo": "B171169101B", "rw": 1, "LotStart": datetime(2026, 11, 17, 10),
                "LotSequence": 1, "SourceRowNumber": 1, "ShiftStatus": "RESOLVED", "LotStatus": "ALLOCATED",
                "LotStop": datetime(2026, 11, 17, 13), "ShiftNo": "1",
                "StartTime": datetime.strptime("08:00", "%H:%M").time(),
                "StopTime": datetime.strptime("20:00", "%H:%M").time(), "pDropCnt": 0, "DropCnt": 186,
            }], "identity_strategy": "LotStart"}

    class AutoLotReader:
        @staticmethod
        def normalize_detections(rows: list[dict[str, Any]], production_date: str):
            return main.SQLServerAutoLotRepository.normalize_detections(rows, production_date)

        @staticmethod
        def is_available() -> bool:
            return False

        @staticmethod
        def list_for_date(_production_date: str) -> list[dict[str, Any]]:
            return []

    source = ViewSource()
    monkeypatch.setattr(main, "source_repository", source)
    monkeypatch.setattr(main, "auto_lot_repository", AutoLotReader())
    monkeypatch.setattr(main, "production_repository", type("ProductionStore", (), {
        "production_day_lots": staticmethod(lambda *_args: []),
    })())
    monkeypatch.setattr(main, "read_cutoff_versions", lambda: [
        {"id": 1, "effective_from": "2026-01-01", "cutoff_time": "07:00", "time_zone": "Asia/Bangkok"},
    ])
    monkeypatch.setattr(main.configuration_repository, "get_daily_shift_configuration", lambda selected: {
        "status": "DEFAULT", "production_date": selected, "selected_type": 3,
        "type_code": "TYPE 3", "configuration_save_id": 10, "schedule": None,
    })

    result = main.production_overview("2026-11-17")

    assert source.queries == 1
    assert result["auto_lot_status"] == "DIRECT SQL VIEW"
    assert result["auto_lots"][0]["LotNo"] == "B171169101B"
    assert result["auto_lots"][0]["DropCnt"] == 186
