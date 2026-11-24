from datetime import datetime

import pytest

from backend.app.shift_schedule import (
    ScheduleValidationError,
    resolve_schedule_context,
    shift_for_timestamp,
    validate_draft_interval,
    validate_shift_period_definitions,
)


def definitions():
    return [
        {
            "id": 1,
            "shift_code": "1",
            "shift_name": "Shift 1",
            "display_order": 1,
            "active": True,
            "periods": [
                {"start_time": "08:00", "end_time": "12:00", "display_order": 1, "active": True},
                {"start_time": "13:00", "end_time": "17:00", "display_order": 2, "active": True},
            ],
        },
        {
            "id": 2,
            "shift_code": "2",
            "shift_name": "Shift 2",
            "display_order": 2,
            "active": True,
            "periods": [{"start_time": "18:00", "end_time": "06:00", "display_order": 1, "active": True}],
        },
    ]


def schedule():
    shifts = validate_shift_period_definitions(definitions())
    return resolve_schedule_context([{"id": 7, "effective_from": "2026-11-10", "shifts": shifts}], "2026-11-10")


def test_period_validation_accepts_multiple_and_overnight_intervals():
    normalized = validate_shift_period_definitions(definitions())
    assert len(normalized[0]["periods"]) == 2
    assert normalized[1]["periods"][0]["end_time"] == "06:00"


def test_period_validation_rejects_overlaps_across_shifts_and_periods():
    shifts = definitions()
    shifts[0]["periods"][1]["start_time"] = "11:30"
    with pytest.raises(ScheduleValidationError, match="overlap"):
        validate_shift_period_definitions(shifts)


def test_period_validation_rejects_duplicate_order_and_zero_duration():
    shifts = definitions()
    shifts[0]["periods"][1]["display_order"] = 1
    with pytest.raises(ScheduleValidationError, match="orders"):
        validate_shift_period_definitions(shifts)
    shifts = definitions()
    shifts[0]["periods"][0]["end_time"] = "08:00"
    with pytest.raises(ScheduleValidationError, match="cannot be equal"):
        validate_shift_period_definitions(shifts)


def test_schedule_resolves_each_period_and_unassigned_gaps():
    context = schedule()
    assert len(context["resolved_shifts"]) == 3
    overnight = next(row for row in context["resolved_shifts"] if row["id"] == 2)
    assert overnight["start_at"] == "2026-11-10T18:00:00+07:00"
    assert overnight["end_at"] == "2026-11-11T06:00:00+07:00"
    assert context["unassigned_gaps"] == [{"start_time": "06:00", "end_time": "08:00"}, {"start_time": "12:00", "end_time": "13:00"}, {"start_time": "17:00", "end_time": "18:00"}]


def test_shift_timestamp_and_draft_resolution_work_with_periods():
    context = schedule()
    assert shift_for_timestamp(context, datetime.fromisoformat("2026-11-10T14:00:00+07:00"))["id"] == 1
    assert shift_for_timestamp(context, datetime.fromisoformat("2026-11-10T12:30:00+07:00")) is None
    validate_draft_interval(context, 1, datetime.fromisoformat("2026-11-10T13:30:00+07:00"), datetime.fromisoformat("2026-11-10T16:30:00+07:00"))
    with pytest.raises(ScheduleValidationError, match="within"):
        validate_draft_interval(context, 1, datetime.fromisoformat("2026-11-10T12:30:00+07:00"), None)
