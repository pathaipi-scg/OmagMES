from datetime import datetime

from backend.app.shift_schedule import resolve_schedule_context, shift_for_timestamp


def test_shift_resolution_is_independent_of_cutoff_and_preserves_unassigned_gap() -> None:
    schedule = resolve_schedule_context([
        {
            "id": 5,
            "effective_from": "2026-11-10",
            "shifts": [
                {"id": 1, "shift_code": "1", "shift_name": "Shift 1", "start_time": "08:00", "end_time": "19:00", "display_order": 1, "active": True},
                {"id": 2, "shift_code": "2", "shift_name": "Shift 2", "start_time": "19:00", "end_time": "06:00", "display_order": 2, "active": True},
            ],
        }
    ], "2026-11-10")

    assert shift_for_timestamp(schedule, datetime.fromisoformat("2026-11-10T07:30:00+07:00")) is None
    assert shift_for_timestamp(schedule, datetime.fromisoformat("2026-11-10T08:00:00+07:00"))["id"] == 1
    assert shift_for_timestamp(schedule, datetime.fromisoformat("2026-11-10T19:00:00+07:00"))["id"] == 2
    assert shift_for_timestamp(schedule, datetime.fromisoformat("2026-11-11T05:59:59+07:00"))["id"] == 2
    assert shift_for_timestamp(schedule, datetime.fromisoformat("2026-11-11T06:00:00+07:00")) is None


def test_shift_period_identifier_does_not_override_stable_shift_identity() -> None:
    schedule = resolve_schedule_context([{
        "id": 5,
        "effective_from": "2026-11-10",
        "shifts": [{
            "id": 17, "shift_code": "1", "shift_name": "Shift 1", "start_time": "08:00",
            "end_time": "12:00", "display_order": 1, "active": True,
            "periods": [{"period_id": 991, "display_order": 1, "start_time": "08:00", "end_time": "12:00", "active": True}],
        }],
    }], "2026-11-10")
    resolved = shift_for_timestamp(schedule, datetime.fromisoformat("2026-11-10T09:00:00+07:00"))
    assert resolved is not None
    assert resolved["id"] == 17
    assert resolved["period_order"] == 1
