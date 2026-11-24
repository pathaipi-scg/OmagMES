from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from typing import Any

import pytest

from backend.app.configuration_repository import (
    ConfigurationSQLSettings,
    ConfigurationUnavailable,
    SQLServerConfigurationRepository,
)
from backend.app.daily_shift_configuration import (
    DailyShiftConfigurationError,
    initial_shift_periods,
    normalize_shift_configuration,
)


class SnapshotStore:
    def __init__(self) -> None:
        self.saves: list[dict[str, Any]] = []
        self.periods: list[dict[str, Any]] = []
        self.next_id = 1
        self.schema_available = True


class SnapshotConnection:
    def __init__(self, store: SnapshotStore, *, fail_child_insert: bool = False) -> None:
        self.store = store
        self.before = deepcopy((store.saves, store.periods, store.next_id))
        self.fail_child_insert = fail_child_insert
        self.timeout = 0
        self.committed = False
        self.rolled_back = False

    def cursor(self) -> "SnapshotCursor":
        return SnapshotCursor(self)

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        self.rolled_back = True
        self.store.saves, self.store.periods, self.store.next_id = deepcopy(self.before)

    def close(self) -> None:
        pass


class SnapshotCursor:
    def __init__(self, connection: SnapshotConnection) -> None:
        self.connection = connection
        self.rows: list[tuple[Any, ...]] = []

    def execute(self, sql: str, params: Any = ()) -> "SnapshotCursor":
        compact = " ".join(sql.split())
        store = self.connection.store
        self.rows = []
        if compact.startswith("EXECUTE AS") or compact == "REVERT":
            return self
        if "SELECT OBJECT_ID(N'omagmes.DailyShiftConfigurationSave'" in compact:
            self.rows = [(1 if store.schema_available else None, 2 if store.schema_available else None)]
        elif "SELECT TypeCode,COUNT_BIG(*),MIN(id) FROM omagmes.ShiftType" in compact:
            self.rows = [("TYPE 1", 1, 1), ("TYPE 2", 1, 2), ("TYPE 3", 1, 3)]
        elif "SELECT ShiftNumber,COUNT(DISTINCT ShiftID),MIN(ShiftID)" in compact:
            self.rows = [(1, 1, 101), (2, 1, 102), (3, 1, 103)]
        elif "sys.sp_getapplock" in compact:
            self.rows = [(0,)]
        elif "INSERT INTO omagmes.DailyShiftConfigurationSave" in compact:
            save_id = store.next_id
            store.next_id += 1
            save = {
                "id": save_id,
                "production_date": params[0],
                "selected_type": params[1],
                "selected_type_id": params[2],
                "save_time": datetime(2026, 11, 21, 12, 0, save_id),
                "complete": False,
            }
            store.saves.append(save)
            self.rows = [(save_id,)]
        elif "INSERT INTO omagmes.DailyShiftConfigurationPeriod" in compact:
            if self.connection.fail_child_insert:
                raise RuntimeError("simulated child-row failure")
            for index in range(0, len(params), 8):
                save_id, production_date, type_number, shift, type_id, shift_id, start, stop = params[index:index + 8]
                store.periods.append({
                    "save_id": save_id, "production_date": production_date,
                    "type": type_number, "shift": shift, "type_id": type_id,
                    "shift_id": shift_id, "start": start, "stop": stop,
                })
        elif "SELECT COUNT(*) FROM omagmes.DailyShiftConfigurationPeriod WHERE ConfigurationSaveID=?" in compact:
            save_id = params[0]
            self.rows = [(sum(row["save_id"] == save_id for row in store.periods),)]
        elif "UPDATE omagmes.DailyShiftConfigurationSave SET IsComplete=1 WHERE id=? AND IsComplete=0" in compact:
            save_id = params[0]
            save = next(row for row in store.saves if row["id"] == save_id)
            save["complete"] = True
        elif "SELECT Type,Shift,TypeID,ShiftID,CONVERT(char(5),[Start],108),CONVERT(char(5),[Stop],108)" in compact:
            save_id = params[0]
            self.rows = [
                (row["type"], row["shift"], row["type_id"], row["shift_id"], row["start"], row["stop"])
                for row in sorted(store.periods, key=lambda row: (row["type"], row["shift"]))
                if row["save_id"] == save_id
            ]
        elif "FROM omagmes.DailyShiftConfigurationSave WHERE id=? AND IsComplete=1" in compact:
            save = next((row for row in store.saves if row["id"] == params[0] and row["complete"]), None)
            if save:
                self.rows = [(save["id"], save["production_date"], save["selected_type"], save["selected_type_id"], save["save_time"])]
        elif "FROM omagmes.DailyShiftConfigurationSave WHERE IsComplete=1 AND ProductionDate=?" in compact:
            matching = [row for row in store.saves if row["complete"] and row["production_date"] == params[0]]
            matching.sort(key=lambda row: (row["save_time"], row["id"]), reverse=True)
            if matching:
                row = matching[0]
                self.rows = [(row["id"], row["production_date"], row["selected_type"], row["selected_type_id"], row["save_time"])]
        elif "FROM omagmes.DailyShiftConfigurationSave WHERE IsComplete=1" in compact:
            matching = [row for row in store.saves if row["complete"]]
            matching.sort(key=lambda row: (row["save_time"], row["id"]), reverse=True)
            if matching:
                row = matching[0]
                self.rows = [(row["id"], row["production_date"], row["selected_type"], row["selected_type_id"], row["save_time"])]
        else:
            raise AssertionError(f"Unexpected SQL in snapshot fake: {compact}")
        return self

    def fetchone(self) -> tuple[Any, ...] | None:
        return self.rows.pop(0) if self.rows else None

    def fetchall(self) -> list[tuple[Any, ...]]:
        rows, self.rows = self.rows, []
        return rows


def _settings() -> ConfigurationSQLSettings:
    return ConfigurationSQLSettings(
        server="10.28.255.98\\SQLEXPRESS", database="OMAG", driver="ODBC Driver 18 for SQL Server",
        username="test-config-user", password="not-a-real-password", trusted_connection=False,
        target_confirmed=True, writes_confirmed=True, encrypt=True, trust_server_certificate=False,
    )


def _repository(store: SnapshotStore, connections: list[SnapshotConnection] | None = None, *, fail_child_insert: bool = False) -> SQLServerConfigurationRepository:
    def connect(*_args: Any, **_kwargs: Any) -> SnapshotConnection:
        connection = SnapshotConnection(store, fail_child_insert=fail_child_insert and not connections)
        if connections is not None:
            connections.append(connection)
        return connection

    return SQLServerConfigurationRepository(_settings(), connect)


def test_templates_have_confirmed_type_shift_mapping_and_overnight_spans() -> None:
    selected_type, periods = normalize_shift_configuration(3, initial_shift_periods())
    assert selected_type == 3
    assert {(row["type"], row["shift"]) for row in periods} == {
        (1, 1), (2, 1), (2, 2), (3, 2), (3, 3),
    }
    assert next(row for row in periods if row["type"] == 3 and row["shift"] == 2)["end_next_day"] is True


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda rows: rows.pop(), "five configured periods"),
        (lambda rows: rows.__setitem__(0, {**rows[0], "shift": 2}), "fixed"),
        (lambda rows: rows.__setitem__(0, {**rows[0], "start": "08:00", "stop": "08:00"}), "zero-length"),
        (lambda rows: rows.__setitem__(1, {**rows[1], "stop": "18:00"}), "overlap"),
    ],
)
def test_invalid_fixed_mappings_and_periods_are_rejected(mutate: Any, message: str) -> None:
    periods = initial_shift_periods()
    mutate(periods)
    with pytest.raises(DailyShiftConfigurationError, match=message):
        normalize_shift_configuration(1, periods)


def test_save_persists_one_complete_five_row_snapshot_and_fresh_reads_it_back() -> None:
    store = SnapshotStore()
    connections: list[SnapshotConnection] = []
    repository = _repository(store, connections)

    result = repository.save_daily_shift_configuration(
        production_date="2026-11-13", selected_type=3, periods=initial_shift_periods(),
    )

    assert result["status"] == "SAVED"
    assert result["configuration_save_id"] == 1
    assert len(store.saves) == 1 and store.saves[0]["complete"] is True
    assert len(store.periods) == 5
    assert result["schedule"]["periods"] == [
        {"shift_id": 102, "shift_number": 2, "period_order": 1, "start_time": "20:00", "end_time": "08:00", "end_next_day": True, "active": True},
        {"shift_id": 103, "shift_number": 3, "period_order": 2, "start_time": "08:00", "end_time": "20:00", "end_next_day": False, "active": True},
    ]
    assert len(connections) == 2
    assert connections[0].committed and connections[1].committed is False


def test_unsaved_date_inherits_latest_complete_snapshot_without_persisting_it() -> None:
    store = SnapshotStore()
    repository = _repository(store)
    repository.save_daily_shift_configuration(
        production_date="2026-11-13", selected_type=2, periods=initial_shift_periods(),
    )

    inherited = repository.get_daily_shift_configuration("2026-11-14")

    assert inherited["status"] == "DEFAULT"
    assert inherited["source_production_date"] == "2026-11-13"
    assert inherited["selected_type"] == 2
    assert len(store.saves) == 1


def test_date_specific_complete_snapshot_wins_over_global_default() -> None:
    store = SnapshotStore()
    repository = _repository(store)
    repository.save_daily_shift_configuration(
        production_date="2026-11-13", selected_type=2, periods=initial_shift_periods(),
    )
    repository.save_daily_shift_configuration(
        production_date="2026-11-14", selected_type=3, periods=initial_shift_periods(),
    )

    exact = repository.get_daily_shift_configuration("2026-11-13")

    assert exact["status"] == "SAVED"
    assert exact["selected_type"] == 2
    assert exact["source_production_date"] == "2026-11-13"


def test_saved_parent_must_reference_the_matching_shift_type_identity() -> None:
    store = SnapshotStore()
    repository = _repository(store)
    repository.save_daily_shift_configuration(
        production_date="2026-11-13", selected_type=2, periods=initial_shift_periods(),
    )
    store.saves[0]["selected_type_id"] = 3

    with pytest.raises(ConfigurationUnavailable, match="wrong authoritative Shift Type identity"):
        repository.get_daily_shift_configuration("2026-11-13")


def test_failed_period_insert_rolls_back_parent_and_child_rows() -> None:
    store = SnapshotStore()
    connections: list[SnapshotConnection] = []
    repository = _repository(store, connections, fail_child_insert=True)

    with pytest.raises(ConfigurationUnavailable, match="operation failed"):
        repository.save_daily_shift_configuration(
            production_date="2026-11-13", selected_type=1, periods=initial_shift_periods(),
        )

    assert store.saves == [] and store.periods == []
    assert connections[0].rolled_back


def test_missing_migration_reports_authorized_dba_requirement() -> None:
    store = SnapshotStore()
    store.schema_available = False
    repository = _repository(store)

    with pytest.raises(ConfigurationUnavailable, match="authorized DBA must review and apply migration 011"):
        repository.get_daily_shift_configuration("2026-11-21")
