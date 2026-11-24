from __future__ import annotations

from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime, time
from typing import Any, Iterator

import pytest
from fastapi.testclient import TestClient

from backend.app import main
from backend.app.production_repository import SQLServerProductionRepository
from backend.app.sql_source import SQLSourceSettings, SourceUnavailable


CONFIG_TIME = datetime(2026, 11, 24, 9, 30, 0)


def live_settings() -> SQLSourceSettings:
    return replace(
        SQLSourceSettings.from_environment(),
        mode="LIVE_READ_ONLY", server="127.0.0.1", database="OMAG",
        driver="ODBC Driver 17 for SQL Server", username="OMAG_MES",
        password="unit-test-password", target_confirmed=True,
    )


def worktime_row(
    record_id: int, work_type: str, shift_no: str, start: time | None, stop: time | None,
    *, rec_time: datetime = datetime(2026, 11, 23, 8), speed: int | None = None,
) -> tuple[Any, ...]:
    return (record_id, rec_time, f"{work_type:<10}", shift_no, start, stop, speed)


class WorkTimeCursor:
    def __init__(self, connection: "WorkTimeConnection") -> None:
        self.connection = connection
        self.one: tuple[Any, ...] | None = None
        self.many: list[tuple[Any, ...]] = []
        self.statements: list[tuple[str, tuple[Any, ...]]] = []

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> "WorkTimeCursor":
        self.statements.append((sql, params))
        self.one = None
        self.many = []
        if "ORIGINAL_LOGIN()" in sql:
            self.one = ("OMAG_MES", "OMAG_MES", "OMAG", "SCGLS-NK\\SQLEXPRESS", "SQLEXPRESS", 0)
        elif "WITH RankedWorkTime AS" in sql:
            latest: dict[tuple[str, str], tuple[Any, ...]] = {}
            for row in self.connection.work_rows:
                key = (str(row[2] or "").strip(), str(row[3] or "").strip())
                if key[0] not in {"1", "2", "3"}:
                    continue
                if key not in latest or (row[1], row[0]) > (latest[key][1], latest[key][0]):
                    latest[key] = row
            self.many = [
                (row[0], row[1], key[0], key[1], row[4], row[5], row[6], 1)
                for key, row in sorted(latest.items())
            ]
        elif sql == "SELECT GETDATE()":
            self.one = (CONFIG_TIME,)
        elif sql.startswith("INSERT INTO dbo.WorkTime"):
            self.connection.insert_attempts += 1
            if self.connection.fail_on_insert == self.connection.insert_attempts:
                raise RuntimeError("simulated WorkTime insert failure")
            rec_time, work_type, shift_no, start_time, stop_time, speed = params
            next_id = max([row[0] for row in self.connection.work_rows] + [0]) + 1
            self.connection.work_rows.append(worktime_row(
                next_id, work_type, shift_no, start_time, stop_time,
                rec_time=rec_time, speed=speed,
            ))
        return self

    def fetchone(self) -> tuple[Any, ...] | None:
        value = self.one
        self.one = None
        return value

    def fetchall(self) -> list[tuple[Any, ...]]:
        rows = self.many
        self.many = []
        return rows


class WorkTimeConnection:
    def __init__(self, rows: list[tuple[Any, ...]], *, fail_on_insert: int | None = None) -> None:
        self.initial_rows = list(rows)
        self.work_rows = list(rows)
        self.cursor_instance = WorkTimeCursor(self)
        self.fail_on_insert = fail_on_insert
        self.insert_attempts = 0
        self.commits = 0
        self.rollbacks = 0
        self.closed = False
        self.timeout = 0

    def cursor(self) -> WorkTimeCursor:
        return self.cursor_instance

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1
        self.work_rows = list(self.initial_rows)

    def close(self) -> None:
        self.closed = True


def repository(rows: list[tuple[Any, ...]], *, fail_on_insert: int | None = None):
    connection = WorkTimeConnection(rows, fail_on_insert=fail_on_insert)
    repo = SQLServerProductionRepository(live_settings(), lambda *_args, **_kwargs: connection)
    return repo, connection


def test_get_returns_latest_worktype_shiftno_and_keeps_latest_null_inactive_row() -> None:
    old_active = worktime_row(3, "1", "2", time(16), time(0), rec_time=datetime(2026, 11, 22, 8))
    latest_inactive = worktime_row(4, "1", "2", None, None, rec_time=datetime(2026, 11, 23, 8))
    rows = [
        worktime_row(1, "1", "1", time(8), time(16)),
        old_active,
        latest_inactive,
        worktime_row(5, "3", "1", time(8), time(20)),
        worktime_row(6, "3", "2", time(20), time(8)),
        worktime_row(7, "day", "1", time(8), time(8)),
    ]
    repo, connection = repository(rows)

    result = repo.worktime_shift_settings()

    type1_shift2 = next(row for row in result["rows"] if row["work_type"] == "1" and row["shift_no"] == "2")
    assert type1_shift2["record_id"] == 4
    assert type1_shift2["active"] is False
    assert type1_shift2["start_time"] is None and type1_shift2["stop_time"] is None
    assert len(result["rows"]) == 4
    query = next(sql for sql, _ in connection.cursor_instance.statements if "WITH RankedWorkTime AS" in sql)
    assert "PARTITION BY RTRIM(WorkType),RTRIM(ShiftNo)" in query
    assert "ORDER BY RecTime DESC,id DESC" in query
    assert "StartTime IS NOT NULL" not in query and "StopTime IS NOT NULL" not in query
    assert "RTRIM(WorkType) IN ('1','2','3')" in query
    assert connection.commits == 0 and connection.rollbacks == 1


def test_save_inserts_only_changed_rows_once_with_same_sql_timestamp_and_preserved_speed() -> None:
    rows = [
        worktime_row(1, "2", "1", time(8), time(16), speed=800),
        worktime_row(2, "2", "2", time(16), time(0), speed=900),
    ]
    repo, connection = repository(rows)

    result = repo.save_worktime_shift_settings([
        {"work_type": "2", "shift_no": "1", "start_time": "09:00", "stop_time": "16:00"},
        {"work_type": "2", "shift_no": "2", "start_time": "00:00", "stop_time": "08:00"},
    ])

    inserts = [(sql, params) for sql, params in connection.cursor_instance.statements if sql.startswith("INSERT INTO dbo.WorkTime")]
    assert len(inserts) == 2
    assert all("VALUES (?,?,?,?,?,?)" in sql for sql, _ in inserts)
    assert all(params[0] == CONFIG_TIME for _, params in inserts)
    assert [params[-1] for _, params in inserts] == [800, 900]
    assert all(not any(word in sql.upper() for word in ("UPDATE", "DELETE")) for sql, _ in connection.cursor_instance.statements)
    assert connection.commits == 1 and connection.rollbacks == 0
    assert len(connection.work_rows) == 4
    assert result["status"] == "SAVED" and result["inserted_count"] == 2
    assert next(row for row in result["rows"] if row["shift_no"] == "2")["stop_time"] == "08:00:00"


def test_unchanged_shift_rows_do_not_insert_worktime_records() -> None:
    rows = [worktime_row(1, "1", "1", time(8), time(16))]
    repo, connection = repository(rows)

    result = repo.save_worktime_shift_settings([
        {"work_type": "1", "shift_no": "1", "start_time": "08:00:00", "stop_time": "16:00:00"},
    ])

    assert result["status"] == "NO_CHANGES"
    assert result["inserted_count"] == 0
    assert not any(sql.startswith("INSERT INTO dbo.WorkTime") for sql, _ in connection.cursor_instance.statements)
    assert connection.commits == 1
    assert len(connection.work_rows) == 1


def test_failed_multirow_save_rolls_back_all_worktime_inserts() -> None:
    rows = [
        worktime_row(1, "3", "1", time(8), time(20)),
        worktime_row(2, "3", "2", time(20), time(8)),
    ]
    repo, connection = repository(rows, fail_on_insert=2)

    with pytest.raises(SourceUnavailable, match=r"transaction failed \(RuntimeError\)"):
        repo.save_worktime_shift_settings([
            {"work_type": "3", "shift_no": "1", "start_time": "09:00", "stop_time": "20:00"},
            {"work_type": "3", "shift_no": "2", "start_time": "20:00", "stop_time": "09:00"},
        ])

    assert connection.commits == 0 and connection.rollbacks == 1
    assert connection.work_rows == rows
    assert connection.closed


def test_save_validates_time_but_allows_overnight_and_rejects_zero_length() -> None:
    repo, connection = repository([worktime_row(1, "2", "2", time(16), time(0))])

    with pytest.raises(ValueError, match="zero-length"):
        repo.save_worktime_shift_settings([
            {"work_type": "2", "shift_no": "2", "start_time": "16:00", "stop_time": "16:00"},
        ])
    assert connection.commits == 0
    assert connection.closed is False


def test_worktime_shift_settings_api_returns_sql_rows_and_accepts_changes(monkeypatch: pytest.MonkeyPatch) -> None:
    class Repo:
        @staticmethod
        def worktime_shift_settings():
            return {"source": "OMAG.dbo.WorkTime", "schedule_view": "OMAG.dbo.vw_TypeShift", "rows": [], "latest_update_time": None}

        @staticmethod
        def save_worktime_shift_settings(changes: list[dict[str, Any]]):
            return {"source": "OMAG.dbo.WorkTime", "schedule_view": "OMAG.dbo.vw_TypeShift", "status": "SAVED", "inserted_count": len(changes), "rows": [], "latest_update_time": None}

    monkeypatch.setattr(main, "production_repository", Repo())
    client = TestClient(main.app)

    loaded = client.get("/api/worktime/shift-settings")
    saved = client.post("/api/worktime/shift-settings", json={"changes": [
        {"work_type": "3", "shift_no": "1", "start_time": "08:00", "stop_time": "20:00"},
    ]})

    assert loaded.status_code == 200 and loaded.json()["source"] == "OMAG.dbo.WorkTime"
    assert saved.status_code == 200 and saved.json()["inserted_count"] == 1


    def test_legacy_daily_shift_settings_routes_are_retired() -> None:
        client = TestClient(main.app)

        for path in (
            "/api/shift-configuration?production_date=2026-11-21",
            "/api/shift-types?production_date=2026-11-21",
            "/api/daily-shift-type?production_date=2026-11-21",
        ):
            assert client.get(path).status_code == 404
