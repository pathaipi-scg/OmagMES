from __future__ import annotations

from datetime import datetime
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
from backend.app.sql_source import SQLServerReadOnlyRepository, SQLSourceSettings, SourceUnavailable


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
            self._one = ("OMAG-SQL\\PROD", "OMAG", "approved-instance")
        elif "HAS_PERMS_BY_NAME" in sql:
            self._one = (1, 0, 0, 0, 0, 0)
        elif "INFORMATION_SCHEMA.COLUMNS" in sql:
            table = params[-1]
            cols = {
                "PRESS": ["id", "_NAME", "_VALUE", "_TIMESTAMP", "_QUALITY"],
                "REJECT_WET": ["id", "_NAME", "_VALUE", "_TIMESTAMP", "_QUALITY"],
                "product_count": ["id", "TimeStamp", "line", "value_cnt", "quality_flag", "is_duplicate"],
            }[table]
            self.description = [("COLUMN_NAME",)]
            self._many = [(column,) for column in cols]
        elif sql.startswith("SELECT TOP (?)"):
            if "FROM dbo.product_count" in sql:
                self.description = [(name,) for name in ("id", "TimeStamp", "quality_flag", "is_duplicate", "line", "value_cnt")]
                self._many = [(31, datetime(2026, 11, 8, 7, 10), "192", "0", "wet", 4)]
                return self
            self.description = [(name,) for name in ("id", "_NAME", "_VALUE", "_TIMESTAMP", "_QUALITY")]
            if "_NAME = ?" in sql:
                tag = params[1]
                self._many = [(17, tag, 1, datetime(2026, 11, 8, 7, 5), 192)]
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
        server="10.28.255.98\\approved-instance",
        database="OMAG",
        driver="ODBC Driver 17 for SQL Server",
        username="unit-test-login",
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


def test_localhost_config_is_rejected_before_connection_attempt() -> None:
    calls = 0

    def should_not_connect(*_args: Any, **_kwargs: Any) -> FakeConnection:
        nonlocal calls
        calls += 1
        return FakeConnection()

    repository = SQLServerReadOnlyRepository(live_settings(server="127.0.0.1"), should_not_connect)
    with pytest.raises(SourceUnavailable, match="approved host"):
        repository.latest_press_counter()
    assert calls == 0


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

    with pytest.raises(SourceUnavailable, match="SELECT-only"):
        repository.latest_press_counter()
    assert connection.closed


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


def test_press_autocal_accounts_for_known_0700_reset_without_negative_delta() -> None:
    start, end = window()
    rows = [
        observation(PRESS_COUNTER_TAG, "2026-11-08T06:55:00+07:00", 4870, row_id=1),
        observation(PRESS_COUNTER_TAG, "2026-11-08T07:05:00+07:00", 10, row_id=2),
        observation(PRESS_COUNTER_TAG, "2026-11-08T07:10:00+07:00", 15, row_id=3),
    ]

    result = calculate_press_drops(
        rows, start, end, valid_quality_codes=(192,), source_timezone="Asia/Bangkok",
        source_timezone_confirmed=True, max_gap_minutes=20,
    )

    assert result["suggestion"] == 15
    assert any("post-07:00" in warning for warning in result["warnings"])


def test_press_autocal_flags_missing_boundary_and_does_not_add_pre_window_counter() -> None:
    start, end = window("2026-11-08T07:02:00+07:00", "2026-11-08T07:20:00+07:00")
    rows = [
        observation(PRESS_COUNTER_TAG, "2026-11-08T07:05:00+07:00", 100, row_id=1),
        observation(PRESS_COUNTER_TAG, "2026-11-08T07:10:00+07:00", 106, row_id=2),
    ]

    result = calculate_press_drops(
        rows, start, end, valid_quality_codes=(192,), source_timezone="Asia/Bangkok",
        source_timezone_confirmed=True, max_gap_minutes=20,
    )

    assert result["suggestion"] == 6
    assert any("Lot start boundary" in warning for warning in result["warnings"])
    assert any("Lot end boundary" in warning for warning in result["warnings"])


def test_counter_decrease_outside_daily_reset_rebaselines_without_negative_quantity() -> None:
    start, end = window("2026-11-08T07:00:00+07:00", "2026-11-08T08:00:00+07:00")
    rows = [
        observation(PRESS_COUNTER_TAG, "2026-11-08T07:05:00+07:00", 100, row_id=1),
        observation(PRESS_COUNTER_TAG, "2026-11-08T07:10:00+07:00", 110, row_id=2),
        observation(PRESS_COUNTER_TAG, "2026-11-08T07:15:00+07:00", 3, row_id=3),
        observation(PRESS_COUNTER_TAG, "2026-11-08T07:20:00+07:00", 8, row_id=4),
    ]

    result = calculate_press_drops(
        rows, start, end, valid_quality_codes=(192,), source_timezone="Asia/Bangkok",
        source_timezone_confirmed=True, max_gap_minutes=20,
    )

    assert result["suggestion"] == 115
    assert any("decrease outside" in warning for warning in result["warnings"])


def test_first_post_reset_value_is_used_when_no_pre_reset_sample_exists() -> None:
    start, end = window("2026-11-08T06:30:00+07:00", "2026-11-08T08:00:00+07:00")
    rows = [
        observation(PRESS_COUNTER_TAG, "2026-11-08T07:05:00+07:00", 12, row_id=1),
        observation(PRESS_COUNTER_TAG, "2026-11-08T07:10:00+07:00", 19, row_id=2),
    ]
    result = calculate_press_drops(
        rows, start, end, valid_quality_codes=(192,), source_timezone="Asia/Bangkok",
        source_timezone_confirmed=True, max_gap_minutes=20,
    )
    assert result["suggestion"] == 19


def test_counter_gap_quality_duplicate_and_out_of_order_conditions_are_explicit() -> None:
    start, end = window("2026-11-08T07:00:00+07:00", "2026-11-08T08:00:00+07:00")
    rows = [
        observation(PRESS_COUNTER_TAG, "2026-11-08T07:10:00+07:00", 10, row_id=2),
        observation(PRESS_COUNTER_TAG, "2026-11-08T07:05:00+07:00", 5, row_id=1),
        observation(PRESS_COUNTER_TAG, "2026-11-08T07:40:00+07:00", 40, row_id=3),
        observation(PRESS_COUNTER_TAG, "2026-11-08T07:45:00+07:00", 45, quality=0, row_id=4),
    ]

    result = calculate_press_drops(
        rows, start, end, valid_quality_codes=(192,), source_timezone="Asia/Bangkok",
        source_timezone_confirmed=True, max_gap_minutes=10,
    )

    assert result["suggestion"] == 10
    assert any("Out-of-order" in warning for warning in result["warnings"])
    assert any("gap" in warning.lower() for warning in result["warnings"])
    assert any("quality" in warning.lower() for warning in result["warnings"])


def test_duplicate_counter_timestamps_are_deduplicated_or_withheld_when_conflicting() -> None:
    start, end = window("2026-11-08T07:00:00+07:00", "2026-11-08T08:00:00+07:00")
    same = [
        observation(PRESS_COUNTER_TAG, "2026-11-08T07:05:00+07:00", 5, row_id=1),
        observation(PRESS_COUNTER_TAG, "2026-11-08T07:05:00+07:00", 5, row_id=2),
        observation(PRESS_COUNTER_TAG, "2026-11-08T07:10:00+07:00", 10, row_id=3),
    ]
    same_result = calculate_press_drops(
        same, start, end, valid_quality_codes=(192,), source_timezone="Asia/Bangkok",
        source_timezone_confirmed=True, max_gap_minutes=20,
    )
    assert same_result["suggestion"] == 10
    assert any("deduplicated" in warning for warning in same_result["warnings"])

    conflicting = [same[0], observation(PRESS_COUNTER_TAG, "2026-11-08T07:05:00+07:00", 7, row_id=4), same[-1]]
    conflict_result = calculate_press_drops(
        conflicting, start, end, valid_quality_codes=(192,), source_timezone="Asia/Bangkok",
        source_timezone_confirmed=True, max_gap_minutes=20,
    )
    assert conflict_result["suggestion"] is None
    assert any("Conflicting duplicate" in warning for warning in conflict_result["warnings"])


def test_press_autocal_withholds_value_when_quality_semantics_are_not_configured() -> None:
    start, end = window()
    result = calculate_press_drops(
        [observation(PRESS_COUNTER_TAG, "2026-11-08T07:05:00+07:00", 10)], start, end,
        source_timezone="Asia/Bangkok", source_timezone_confirmed=True,
    )
    assert result["suggestion"] is None
    assert any("quality semantics" in warning for warning in result["warnings"])


def test_counter_autocal_withholds_value_when_maximum_gap_is_not_approved() -> None:
    start, end = window("2026-11-08T07:00:00+07:00", "2026-11-08T08:00:00+07:00")
    rows = [
        observation(PRESS_COUNTER_TAG, "2026-11-08T07:05:00+07:00", 10, row_id=1),
        observation(PRESS_COUNTER_TAG, "2026-11-08T07:10:00+07:00", 15, row_id=2),
    ]

    result = calculate_press_drops(
        rows, start, end, valid_quality_codes=(192,), source_timezone="Asia/Bangkok",
        source_timezone_confirmed=True, max_gap_minutes=None,
    )

    assert result["suggestion"] is None
    assert result["samples_used"] == 0
    assert any("maximum counter-gap threshold" in warning for warning in result["warnings"])


def test_wet_reject_cal_uses_only_dynamic_quantity_tags() -> None:
    start, end = window("2026-11-08T07:00:00+07:00", "2026-11-08T08:00:00+07:00")
    rows = [
        observation("MODBUS.WET_REJECT.cntR1", "2026-11-08T07:05:00+07:00", 3, row_id=1),
        observation("MODBUS.WET_REJECT.cntR1", "2026-11-08T07:10:00+07:00", 8, row_id=2),
        observation("MODBUS.WET_REJECT.R1", "2026-11-08T07:10:00+07:00", 1, row_id=3),
        observation("MODBUS.WET_REJECT.cntR27", "2026-11-08T07:05:00+07:00", 12, row_id=4),
        observation("MODBUS.WET_REJECT.cntR27", "2026-11-08T07:10:00+07:00", 15, row_id=5),
    ]

    result = calculate_wet_rejects(
        rows, start, end, valid_quality_codes=(192,), source_timezone="Asia/Bangkok",
        source_timezone_confirmed=True, max_gap_minutes=20,
    )

    assert result["suggestions"] == {"MODBUS.WET_REJECT.cntR1": 8, "MODBUS.WET_REJECT.cntR27": 15}
    assert all(".R1" not in tag for tag in result["suggestions"])


def test_wet_reject_autocal_obeys_0700_daily_reset() -> None:
    start, end = window("2026-11-08T06:00:00+07:00", "2026-11-08T08:00:00+07:00")
    rows = [
        observation("MODBUS.WET_REJECT.cntR4", "2026-11-08T06:55:00+07:00", 80, row_id=1),
        observation("MODBUS.WET_REJECT.cntR4", "2026-11-08T07:05:00+07:00", 2, row_id=2),
        observation("MODBUS.WET_REJECT.cntR4", "2026-11-08T07:10:00+07:00", 5, row_id=3),
    ]
    result = calculate_wet_rejects(
        rows, start, end, valid_quality_codes=(192,), source_timezone="Asia/Bangkok",
        source_timezone_confirmed=True, max_gap_minutes=20,
    )
    assert result["suggestions"]["MODBUS.WET_REJECT.cntR4"] == 5


def test_wet_camera_values_are_individual_tray_piece_counts() -> None:
    start, end = window("2026-11-08T07:00:00+07:00", "2026-11-08T08:00:00+07:00")
    rows = [
        {"source_id": 1, "timestamp": "2026-11-08T07:10:00+07:00", "quality": "192", "duplicate": "0", "line": "wet", "value_cnt": 4},
        {"source_id": 2, "timestamp": "2026-11-08T07:20:00+07:00", "quality": "192", "duplicate": "0", "line": "wet", "value_cnt": 5},
        {"source_id": 3, "timestamp": "2026-11-08T07:30:00+07:00", "quality": "192", "duplicate": "0", "line": "dry", "value_cnt": 999},
    ]

    result = calculate_camera_pieces(
        rows, start, end, source_timezone="Asia/Bangkok", source_timezone_confirmed=True,
        metadata_reviewed=True, boundary_policy_confirmed=True,
        valid_quality_values=("192",), duplicate_clear_values=("0",),
    )

    assert result["suggestion"] == 9
    assert result["observations_used"] == 2


def test_camera_duplicate_and_quality_rules_exclude_unverified_rows() -> None:
    start, end = window("2026-11-08T07:00:00+07:00", "2026-11-08T08:00:00+07:00")
    rows = [
        {"source_id": 1, "timestamp": "2026-11-08T07:10:00+07:00", "quality": "192", "duplicate": "0", "line": "wet", "value_cnt": 4},
        {"source_id": 2, "timestamp": "2026-11-08T07:20:00+07:00", "quality": "192", "duplicate": "1", "line": "wet", "value_cnt": 10},
        {"source_id": 3, "timestamp": "2026-11-08T07:30:00+07:00", "quality": "bad", "duplicate": "0", "line": "wet", "value_cnt": 7},
    ]
    result = calculate_camera_pieces(
        rows, start, end, source_timezone="Asia/Bangkok", source_timezone_confirmed=True,
        metadata_reviewed=True, boundary_policy_confirmed=True,
        valid_quality_values=("192",), duplicate_clear_values=("0",),
    )
    assert result["suggestion"] == 4
    assert any("duplicate" in warning for warning in result["warnings"])
    assert any("quality" in warning for warning in result["warnings"])


def test_camera_lot_attribution_is_withheld_without_approved_boundary_policy() -> None:
    start, end = window()
    result = calculate_camera_pieces(
        [{"source_id": 1, "timestamp": start.isoformat(), "quality": "192", "duplicate": "0", "line": "wet", "value_cnt": 5}],
        start, end, source_timezone="Asia/Bangkok", source_timezone_confirmed=True,
        metadata_reviewed=True, boundary_policy_confirmed=False,
        valid_quality_values=("192",), duplicate_clear_values=("0",),
    )
    assert result["suggestion"] is None
    assert any("attribution" in warning for warning in result["warnings"])


def test_live_failure_is_reported_without_switching_to_mock_or_saving() -> None:
    class FailedSource:
        settings = live_settings()

        @staticmethod
        def health() -> dict[str, Any]:
            return {"mode": "LIVE READ-ONLY", "connected": False, "error": "owner approval required"}

    original = main.source_repository
    main.source_repository = FailedSource()  # type: ignore[assignment]
    try:
        client = TestClient(main.app)
        health = client.get("/api/sources/health").json()
        assert health["mode"] == "LIVE READ-ONLY"
        assert health["connected"] is False
    finally:
        main.source_repository = original


def test_live_autocal_requires_verified_lot_window_before_querying_sources() -> None:
    original = main.source_repository
    main.source_repository = SQLServerReadOnlyRepository(live_settings(lot_window_source_confirmed=False))
    start, end = window()
    try:
        with pytest.raises(main.HTTPException, match="Lot time window"):
            main.autocal_preview(lot_id=501, start_at=start, end_at=end, window_confirmed=True)
    finally:
        main.source_repository = original


def test_no_production_save_is_triggered_by_live_preview() -> None:
    from backend.app.store import store

    before_production = len(store.production_entries)
    before_reject = len(store.reject_entries)
    response = TestClient(main.app).get("/api/autocal/preview")
    assert response.status_code == 200
    assert len(store.production_entries) == before_production
    assert len(store.reject_entries) == before_reject
