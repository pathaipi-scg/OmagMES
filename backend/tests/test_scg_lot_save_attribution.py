from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from fastapi import HTTPException

from backend.app import main
from backend.app.models import LotCreate


BANGKOK = ZoneInfo("Asia/Bangkok")
PRODUCTION_DATE = "2026-11-13"


def _type3_assignment() -> dict[str, Any]:
    return {
        "status": "SAVED",
        "production_date": PRODUCTION_DATE,
        "shift_type_id": 3,
        "type_code": "TYPE 3",
        "schedule_version_id": 33,
        "cutoff_version_id": 7,
        "schedule": {
            "effective_production_date": PRODUCTION_DATE,
            "periods": [
                {"shift_id": 3, "shift_number": 3, "period_order": 1, "start_time": "08:00", "end_time": "20:00", "end_next_day": False, "active": True},
                {"shift_id": 2, "shift_number": 2, "period_order": 2, "start_time": "20:00", "end_time": "08:00", "end_next_day": True, "active": True},
            ],
        },
    }


def _payload(**overrides: Any) -> LotCreate:
    values: dict[str, Any] = {
        "product_id": 1,
        "transition": "PRODUCT_CHANGE",
        "color": "Grey",
        "lot_name": "SCG-LOT",
        "operator_id": "operator",
        "started_at": datetime(2026, 11, 13, 20, 42, 55, tzinfo=BANGKOK),
        "production_date": PRODUCTION_DATE,
        "machine_code": "A",
    }
    values.update(overrides)
    return LotCreate(**values)


def _enable_live_route(monkeypatch: pytest.MonkeyPatch, saved_lot: dict[str, Any]) -> dict[str, Any]:
    captured: dict[str, Any] = {}
    monkeypatch.setattr(main, "source_repository", SimpleNamespace(settings=SimpleNamespace(live_requested=True)))
    monkeypatch.setattr(main, "read_cutoff_versions", lambda: [
        {"id": 7, "effective_from": "2026-01-01", "cutoff_time": "07:00", "time_zone": "Asia/Bangkok"},
    ])
    monkeypatch.setattr(main.configuration_repository, "get_daily_shift_type_assignment", lambda _date: _type3_assignment())
    monkeypatch.setattr(main, "read_shift_versions", lambda: pytest.fail("official Lot save must not resolve the global Shift Schedule"))

    class Repository:
        @staticmethod
        def create_lot(payload: dict[str, Any]) -> dict[str, Any]:
            captured.update(payload)
            return saved_lot

    monkeypatch.setattr(main, "production_repository", Repository())
    return captured


def test_official_save_uses_saved_type3_schedule_and_start_date_for_overnight_lot(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = _enable_live_route(monkeypatch, {"id": 9001, "lot_number": "B131169201A"})

    result = main.create_lot(_payload())

    assert result["lot_number"] == "B131169201A"
    assert captured["production_date"] == PRODUCTION_DATE
    assert captured["shift_id"] == 2
    assert captured["shift_code"] == "2"
    assert captured["shift_schedule_version_id"] == 33
    assert captured["production_day_cutoff_version_id"] == 7
    assert captured["machine_code"] == "A"
    assert captured["started_at"].date().isoformat() == PRODUCTION_DATE


def test_official_save_keeps_pinned_overnight_owner_after_midnight(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = _enable_live_route(monkeypatch, {"id": 9002, "lot_number": "B131169201A"})
    payload = _payload(started_at=datetime(2026, 11, 14, 7, 57, 3, tzinfo=BANGKOK))

    main.create_lot(payload)

    assert captured["started_at"].date().isoformat() == "2026-11-14"
    assert captured["production_date"] == PRODUCTION_DATE
    assert captured["shift_id"] == 2
    assert captured["shift_code"] == "2"
    assert captured["shift_schedule_version_id"] == 33


@pytest.mark.parametrize(
    ("missing", "message"),
    [
        ("production_date", "explicit Production Date"),
        ("started_at", "explicit Lot start timestamp"),
    ],
)
def test_official_save_refuses_to_infer_missing_production_context(
    monkeypatch: pytest.MonkeyPatch, missing: str, message: str,
) -> None:
    captured = _enable_live_route(monkeypatch, {})
    payload = _payload(**{missing: None})

    with pytest.raises(HTTPException) as error:
        main.create_lot(payload)

    assert error.value.status_code == 422
    assert message in error.value.detail
    assert captured == {}


def test_official_save_refuses_when_daily_shift_type_is_not_saved(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = _enable_live_route(monkeypatch, {})
    monkeypatch.setattr(main.configuration_repository, "get_daily_shift_type_assignment", lambda _date: {
        "status": "SHIFT TYPE NOT SELECTED", "schedule": None,
    })

    with pytest.raises(HTTPException) as error:
        main.create_lot(_payload())

    assert error.value.status_code == 409
    assert "saved daily Shift Type" in error.value.detail
    assert captured == {}
