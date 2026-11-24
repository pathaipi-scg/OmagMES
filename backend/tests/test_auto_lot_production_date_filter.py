from __future__ import annotations

from datetime import date, datetime, time
from types import SimpleNamespace
from typing import Any

import pytest

from backend.app import main
from backend.app.autolot_repository import SQLServerAutoLotRepository


PRODUCTION_DATE = "2026-11-13"


def _configuration(production_date: str, *, saved: bool = True) -> dict[str, Any]:
    return {
        "status": "SAVED" if saved else "DEFAULT",
        "production_date": production_date,
        "selected_type": 3,
        "type_code": "TYPE 3",
        "configuration_save_id": 44 if saved else None,
        "schedule": {
            "effective_production_date": production_date,
            "periods": [
                {"shift_id": 2, "shift_number": 2, "period_order": 1,
                 "start_time": "20:00", "end_time": "08:00", "end_next_day": True, "active": True},
                {"shift_id": 10004, "shift_number": 3, "period_order": 2,
                 "start_time": "08:00", "end_time": "20:00", "end_next_day": False, "active": True},
            ],
        } if saved else None,
    }


def _view_row(
    start: str | None,
    *,
    prod_date: str = PRODUCTION_DATE,
    lot_no: str | None = "B131169101B",
    shift_type: int = 3,
    shift_no: str | None = "1",
    start_time: time = time(8),
    stop_time: time = time(20),
    drop_count: int | None = 550,
    previous_drop_count: int | None = 0,
    rw: int = 1,
    stop: str | None = "2026-11-13T16:00:00",
    shift_status: str = "RESOLVED",
    lot_status: str = "ALLOCATED",
) -> dict[str, Any]:
    return {
        "ProdDate": date.fromisoformat(prod_date), "ShiftType": shift_type,
        "LotNo": lot_no, "rw": rw, "LotSequence": rw if lot_status == "ALLOCATED" else None,
        "SourceRowNumber": rw,
        "LotStart": datetime.fromisoformat(start) if start else None,
        "LotStop": datetime.fromisoformat(stop) if stop else None,
        "ShiftNo": shift_no, "StartTime": start_time, "StopTime": stop_time,
        "ShiftStatus": shift_status, "LotStatus": lot_status,
        "pDropCnt": previous_drop_count, "DropCnt": drop_count,
    }


class _ViewSource:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows
        self.settings = SimpleNamespace(live_requested=True)
        self.queried_dates: list[str] = []

    def press_lot_auto(self, production_date: str, _limit: int = 5000) -> dict[str, Any]:
        self.queried_dates.append(production_date)
        selected = date.fromisoformat(production_date)
        rows = [row for row in self.rows if row["ProdDate"] == selected]
        return {"source": "OMAG.dbo.vw_PRESS_LotAuto", "production_date": production_date,
                "rows": rows, "truncated": False, "identity_strategy": "LotStart"}


class _AutoLotRead:
    @staticmethod
    def normalize_detections(rows: list[dict[str, Any]], production_date: str):
        return SQLServerAutoLotRepository.normalize_detections(rows, production_date)

    @staticmethod
    def is_available() -> bool:
        return False

    @staticmethod
    def list_for_date(_production_date: str) -> list[dict[str, Any]]:
        return []


def _install(monkeypatch: pytest.MonkeyPatch, rows: list[dict[str, Any]], config: dict[str, Any]) -> _ViewSource:
    source = _ViewSource(rows)
    monkeypatch.setattr(main, "source_repository", source)
    monkeypatch.setattr(main, "auto_lot_repository", _AutoLotRead())
    monkeypatch.setattr(main, "production_repository", SimpleNamespace(production_day_lots=lambda *_args: []))
    monkeypatch.setattr(main.configuration_repository, "get_daily_shift_configuration", lambda _date: config)
    return source


def test_overview_reads_view_prod_date_and_returns_its_rows_unchanged(monkeypatch: pytest.MonkeyPatch) -> None:
    row = _view_row("2026-11-13T09:00:00", lot_no="B131169101B", drop_count=550)
    source = _install(monkeypatch, [row], _configuration(PRODUCTION_DATE))

    result = main.production_overview(PRODUCTION_DATE)

    assert source.queried_dates == [PRODUCTION_DATE]
    assert result["source"] == "OMAG.dbo.vw_PRESS_LotAuto"
    assert result["auto_lots"][0] == row
    assert result["auto_lots"][0]["LotNo"] == "B131169101B"
    assert result["auto_lots"][0]["DropCnt"] == 550
    assert result["auto_lot_status"] == "DIRECT SQL VIEW"


def test_overview_get_only_reads_saved_assignments_without_reconciling(monkeypatch: pytest.MonkeyPatch) -> None:
    row = _view_row("2026-11-13T09:00:00", lot_no="B131169101B")
    source = _install(monkeypatch, [row], _configuration(PRODUCTION_DATE))

    class ReadOnlyAssignments:
        @staticmethod
        def is_available() -> bool:
            return True

        @staticmethod
        def reconcile(*_args):
            raise AssertionError("overview GET must not write or reconcile")

        @staticmethod
        def list_for_date(_production_date: str) -> list[dict[str, Any]]:
            return []

        @staticmethod
        def attach_saved_assignments(rows, _saved):
            return rows

    monkeypatch.setattr(main, "auto_lot_repository", ReadOnlyAssignments())

    result = main.production_overview(PRODUCTION_DATE)

    assert source.queried_dates == [PRODUCTION_DATE]
    assert result["assignment_available"] is True
    assert result["auto_lots"] == [row]


def test_cross_midnight_source_lot_uses_view_shift_fields_without_python_renumbering() -> None:
    row = _view_row(
        "2026-11-13T23:00:00", lot_no="B131169201B", shift_no="2",
        start_time=time(20), stop_time=time(8), stop="2026-11-14T07:50:00",
    )
    persistent, preview, warnings = SQLServerAutoLotRepository.normalize_detections(
        [row], PRODUCTION_DATE, _configuration(PRODUCTION_DATE),
    )
    assert not preview and not warnings
    assert persistent[0]["lot_number"] == "B131169201B"
    assert persistent[0]["shift_type"] == 3
    assert persistent[0]["shift_number"] == 2
    assert persistent[0]["shift_number"] == 2
    assert persistent[0]["source_row_number"] == 1
    assert persistent[0]["drop_count"] == 550
    assert persistent[0]["lot_start"] == row["LotStart"]


def test_view_shift_is_authoritative_even_when_saved_app_schedule_differs() -> None:
    row = _view_row("2026-11-13T10:00:00", shift_no="1", start_time=time(8), stop_time=time(20))
    persistent, preview, warnings = SQLServerAutoLotRepository.normalize_detections(
        [row], PRODUCTION_DATE, _configuration(PRODUCTION_DATE),
    )
    assert len(persistent) == 1
    assert not preview and not warnings
    assert persistent[0]["lot_number"] == row["LotNo"]


def test_view_type_and_shift_hours_are_not_recomputed_in_python() -> None:
    type_mismatch = _view_row("2026-11-13T10:00:00", shift_type=2)
    type_persistent, type_preview, _ = SQLServerAutoLotRepository.normalize_detections(
        [type_mismatch], PRODUCTION_DATE, _configuration(PRODUCTION_DATE),
    )
    assert len(type_persistent) == 1
    assert not type_preview

    outside = _view_row("2026-11-13T10:00:00", shift_no="2", start_time=time(20), stop_time=time(8))
    outside_persistent, outside_preview, _ = SQLServerAutoLotRepository.normalize_detections(
        [outside], PRODUCTION_DATE, _configuration(PRODUCTION_DATE),
    )
    assert len(outside_persistent) == 1
    assert not outside_preview


def test_view_production_date_filter_excludes_other_dates(monkeypatch: pytest.MonkeyPatch) -> None:
    rows = [
        _view_row("2026-11-13T09:00:00", prod_date=PRODUCTION_DATE),
        _view_row("2026-11-14T09:00:00", prod_date="2026-11-14", lot_no="B141169101B"),
    ]
    source = _install(monkeypatch, rows, _configuration(PRODUCTION_DATE))
    result = main.production_overview(PRODUCTION_DATE)
    assert source.queried_dates == [PRODUCTION_DATE]
    assert [row["LotNo"] for row in result["auto_lots"]] == ["B131169101B"]


def test_missing_view_lotstart_is_withheld_because_no_stable_source_identity() -> None:
    row = _view_row(None, lot_no="B131169301B")
    persistent, preview, warnings = SQLServerAutoLotRepository.normalize_detections(
        [row], PRODUCTION_DATE, _configuration(PRODUCTION_DATE),
    )
    assert not persistent and not preview
    assert any("no valid LotStart" in warning for warning in warnings)


def test_unresolved_worktime_and_number_status_are_explicit_previews() -> None:
    row = _view_row(
        "2026-11-13T21:00:00", stop=None, lot_no=None, shift_no=None,
        shift_status="NO_WORKTIME_MATCH", lot_status="NO_WORKTIME_MATCH",
    )
    persistent, preview, warnings = SQLServerAutoLotRepository.normalize_detections(
        [row], PRODUCTION_DATE, _configuration(PRODUCTION_DATE),
    )
    assert not persistent
    assert preview[0]["status"] == "SHIFT UNRESOLVED · NO_WORKTIME_MATCH"
    assert preview[0]["lot_number"] is None
    assert warnings


def test_duplicate_start_or_lotno_rejects_reconciliation_input() -> None:
    first = _view_row("2026-11-13T09:00:00", lot_no="B131169301B")
    duplicate_start = _view_row("2026-11-13T09:00:00", lot_no="B131169302B", rw=2)
    with pytest.raises(main.SourceUnavailable, match="duplicate LotStart"):
        SQLServerAutoLotRepository.normalize_detections(
            [first, duplicate_start], PRODUCTION_DATE, _configuration(PRODUCTION_DATE),
        )
    duplicate_lotno = _view_row("2026-11-13T10:00:00", lot_no="B131169301B", rw=2)
    with pytest.raises(main.SourceUnavailable, match="duplicate LotNo"):
        SQLServerAutoLotRepository.normalize_detections([first, duplicate_lotno], PRODUCTION_DATE)
