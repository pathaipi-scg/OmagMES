from __future__ import annotations

from contextlib import contextmanager
from datetime import date, datetime
from typing import Any, Iterator

from fastapi.testclient import TestClient

from backend.app import main
from backend.app.production_repository import SQLServerProductionRepository


class Cursor:
    def __init__(self, row: tuple[Any, ...] | None) -> None:
        self.row = row
        self.sql = ""
        self.params: tuple[Any, ...] = ()

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> "Cursor":
        self.sql = sql
        self.params = params
        return self

    def fetchone(self) -> tuple[Any, ...] | None:
        return self.row


def _repository_for(cursor: Cursor, monkeypatch: Any) -> SQLServerProductionRepository:
    repository = SQLServerProductionRepository()
    writes: list[bool] = []

    @contextmanager
    def connection(*, write: bool = False) -> Iterator[tuple[None, Cursor]]:
        writes.append(write)
        yield None, cursor

    monkeypatch.setattr(repository, "_connection", connection)
    repository._test_writes = writes  # type: ignore[attr-defined]
    return repository


def test_get_production_shift_type_returns_type_3_default_without_a_row(monkeypatch: Any) -> None:
    cursor = Cursor(None)
    repository = _repository_for(cursor, monkeypatch)

    result = repository.production_shift_type("2026-11-13")

    assert result == {
        "production_date": "2026-11-13", "selected_type": 3, "type_code": "TYPE 3",
        "status": "DEFAULT", "record_id": None, "update_time": None,
    }
    assert "FROM dbo.vw_ProductionDetails WHERE ProdDate=?" in cursor.sql
    assert "ORDER BY UpdateTime DESC,id DESC" in cursor.sql
    assert cursor.params == (date(2026, 11, 13),)
    assert repository._test_writes == [False]  # type: ignore[attr-defined]


def test_get_production_shift_type_normalizes_existing_type_value(monkeypatch: Any) -> None:
    cursor = Cursor((81, datetime(2026, 11, 13, 9), date(2026, 11, 13), "2"))
    repository = _repository_for(cursor, monkeypatch)

    result = repository.production_shift_type("2026-11-13")

    assert result["selected_type"] == 2
    assert result["type_code"] == "TYPE 2"
    assert result["status"] == "SAVED"
    assert result["record_id"] == 81
    assert result["update_time"] == "2026-11-13T09:00:00"


def test_post_inserts_selected_type_and_database_getdate_without_live_database(monkeypatch: Any) -> None:
    cursor = Cursor((82, datetime(2026, 11, 13, 10), date(2026, 11, 13), "1"))
    repository = _repository_for(cursor, monkeypatch)

    result = repository.save_production_shift_type("2026-11-13", 1)

    assert cursor.sql == (
        "INSERT INTO dbo.ProductionDetails (UpdateTime,ProdDate,ShiftType) "
        "OUTPUT INSERTED.id,INSERTED.UpdateTime,INSERTED.ProdDate,INSERTED.ShiftType "
        "VALUES (GETDATE(),?,?)"
    )
    assert cursor.params == (date(2026, 11, 13), "1")
    assert repository._test_writes == [True]  # type: ignore[attr-defined]
    assert result["status"] == "SAVED"
    assert result["record_id"] == 82
    assert result["selected_type"] == 1


def test_production_shift_type_api_get_and_post_contract(monkeypatch: Any) -> None:
    monkeypatch.setattr(main, "production_repository", type("Repo", (), {
        "production_shift_type": staticmethod(lambda selected: {
            "production_date": selected, "selected_type": 3, "type_code": "TYPE 3",
            "status": "DEFAULT", "record_id": None, "update_time": None,
        }),
        "save_production_shift_type": staticmethod(lambda selected, kind: {
            "production_date": selected, "selected_type": kind, "type_code": f"TYPE {kind}",
            "status": "SAVED", "record_id": 9, "update_time": "2026-11-13T10:00:00",
        }),
    })())
    client = TestClient(main.app)

    loaded = client.get("/api/production/shift-type", params={"production_date": "2026-11-13"})
    saved = client.post("/api/production/shift-type", json={"production_date": "2026-11-13", "selected_type": 2})

    assert loaded.status_code == 200
    assert loaded.json()["selected_type"] == 3
    assert loaded.json()["status"] == "DEFAULT"
    assert saved.status_code == 201
    assert saved.json()["selected_type"] == 2
    assert saved.json()["status"] == "SAVED"
