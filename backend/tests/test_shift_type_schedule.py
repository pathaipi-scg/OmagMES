from datetime import datetime

import pytest

from backend.app.shift_type_schedule import (
    ShiftTypeValidationError,
    resolve_lot_start_context,
    shift_for_type_timestamp,
    validate_shift_type_periods,
)


def periods(type_code: str) -> list[dict]:
    definitions = {
        "TYPE 1": [(10001, 1, "08:00", "16:00", False)],
        "TYPE 2": [(10001, 1, "08:00", "16:00", False), (10002, 2, "16:00", "00:00", True)],
        "TYPE 3": [(10003, 3, "08:00", "20:00", False), (10002, 2, "20:00", "08:00", True)],
    }
    return [
        {"shift_id": shift_id, "shift_number": number, "period_order": index, "start_time": start,
         "end_time": end, "end_next_day": next_day, "active": True}
        for index, (shift_id, number, start, end, next_day) in enumerate(definitions[type_code], 1)
    ]


def test_factory_type_period_sets_and_half_open_boundaries() -> None:
    for code in ("TYPE 1", "TYPE 2", "TYPE 3"):
        assert validate_shift_type_periods(code, periods(code))

    schedule = {"effective_production_date": "2026-11-18", "periods": periods("TYPE 3")}
    assert shift_for_type_timestamp(schedule, datetime.fromisoformat("2026-11-18T07:59:59+07:00")) is None
    assert shift_for_type_timestamp(schedule, datetime.fromisoformat("2026-11-18T08:00:00+07:00"))["shift_number"] == 3
    assert shift_for_type_timestamp(schedule, datetime.fromisoformat("2026-11-18T20:00:00+07:00"))["shift_number"] == 2
    assert shift_for_type_timestamp(schedule, datetime.fromisoformat("2026-11-19T07:59:59+07:00"))["shift_number"] == 2
    assert shift_for_type_timestamp(schedule, datetime.fromisoformat("2026-11-19T08:00:00+07:00")) is None


def test_type_validation_rejects_wrong_shift_set_invalid_duration_and_overlap() -> None:
    with pytest.raises(ShiftTypeValidationError, match="factory-confirmed"):
        validate_shift_type_periods("TYPE 3", periods("TYPE 2"))
    invalid_duration = periods("TYPE 1")
    invalid_duration[0]["end_time"] = "08:00"
    with pytest.raises(ShiftTypeValidationError, match="positive duration"):
        validate_shift_type_periods("TYPE 1", invalid_duration)

    overlapping = periods("TYPE 2")
    overlapping[1]["start_time"] = "15:00"
    overlapping[1]["end_time"] = "23:00"
    overlapping[1]["end_next_day"] = False
    with pytest.raises(ShiftTypeValidationError, match="overlap"):
        validate_shift_type_periods("TYPE 2", overlapping)


def test_type3_overnight_owns_lot_until_exact_0800_boundary_then_date_assignment_applies() -> None:
    cutoff_versions = [{"id": 7, "effective_from": "2026-11-10", "cutoff_time": "07:00"}]

    def assignment(selected_date: str) -> dict:
        code = "TYPE 3" if selected_date == "2026-11-18" else "TYPE 1"
        type_id = 3 if code == "TYPE 3" else 1
        version_id = 33 if code == "TYPE 3" else 11
        return {
            "status": "SAVED", "production_date": selected_date,
            "shift_type_id": type_id, "type_code": code,
            "schedule_version_id": version_id, "cutoff_version_id": 7,
            "schedule": {"effective_production_date": selected_date, "periods": periods(code)},
        }

    def get_assignment(selected_date: str) -> dict:
        return assignment(selected_date)

    overnight = resolve_lot_start_context(
        datetime.fromisoformat("2026-11-19T07:59:00+07:00"),
        cutoff_versions=cutoff_versions, assignment_for_date=get_assignment,
    )
    assert overnight["status"] == "OVERNIGHT SHIFT OWNING PRODUCTION DATE"
    assert overnight["production_date"] == "2026-11-18"
    assert overnight["shift_type_schedule_version_id"] == 33
    assert overnight["shift_number"] == 2

    boundary = resolve_lot_start_context(
        datetime.fromisoformat("2026-11-19T08:00:00+07:00"),
        cutoff_versions=cutoff_versions, assignment_for_date=get_assignment,
    )
    assert boundary["status"] == "ASSIGNED"
    assert boundary["production_date"] == "2026-11-19"
    assert boundary["shift_type_schedule_version_id"] == 11
    assert boundary["shift_number"] == 1


def test_assignment_uses_assigned_production_date_not_schedule_effective_from_date() -> None:
    saved = {
        "status": "SAVED", "production_date": "2026-11-18",
        "shift_type_id": 3, "type_code": "TYPE 3",
        "schedule_version_id": 33, "cutoff_version_id": 7,
        "schedule": {"effective_production_date": "2026-11-10", "periods": periods("TYPE 3")},
    }

    result = resolve_lot_start_context(
        datetime.fromisoformat("2026-11-18T17:41:50+07:00"),
        cutoff_versions=[{"id": 7, "effective_from": "2026-11-10", "cutoff_time": "07:00"}],
        assignment_for_date=lambda selected_date: saved if selected_date == "2026-11-18" else {
            "status": "SHIFT TYPE NOT SELECTED", "production_date": selected_date,
        },
    )

    assert result["status"] == "ASSIGNED"
    assert result["production_date"] == "2026-11-18"
    assert result["shift_type_schedule_version_id"] == 33
    assert result["shift_number"] == 3


def test_missing_date_assignment_never_falls_back_to_global_shift_schedule() -> None:
    result = resolve_lot_start_context(
        datetime.fromisoformat("2026-11-19T09:00:00+07:00"),
        cutoff_versions=[{"id": 7, "effective_from": "2026-11-10", "cutoff_time": "07:00"}],
        assignment_for_date=lambda selected_date: {"status": "SHIFT TYPE NOT SELECTED", "production_date": selected_date},
    )
    assert result["status"] == "SHIFT TYPE NOT SELECTED"
    assert result["shift_id"] is None
    assert result["shift_type_schedule_version_id"] is None
