from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from .production_day import PRODUCTION_TIMEZONE, localize_timestamp, resolve_production_date
from .shift_schedule import ScheduleValidationError


_EXPECTED_SHIFT_NUMBERS = {"TYPE 1": {1}, "TYPE 2": {1, 2}, "TYPE 3": {2, 3}}
_ZONE = ZoneInfo(PRODUCTION_TIMEZONE)


class ShiftTypeValidationError(ValueError):
    """Invalid Shift Type period configuration or date assignment."""


def _clock(value: Any, label: str) -> tuple[str, int]:
    if not isinstance(value, str):
        raise ShiftTypeValidationError(f"{label} must use HH:MM 24-hour time.")
    try:
        parsed = time.fromisoformat(value)
    except ValueError:
        raise ShiftTypeValidationError(f"{label} must use HH:MM 24-hour time.") from None
    if parsed.second or parsed.microsecond or parsed.tzinfo is not None:
        raise ShiftTypeValidationError(f"{label} must use local HH:MM time without seconds or timezone.")
    text = parsed.strftime("%H:%M")
    return text, parsed.hour * 60 + parsed.minute


def validate_shift_type_periods(type_code: str, periods: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if type_code not in _EXPECTED_SHIFT_NUMBERS:
        raise ShiftTypeValidationError("Unknown Shift Type code.")
    if not periods:
        raise ShiftTypeValidationError("A Shift Type schedule must contain its confirmed Shift periods.")
    normalized: list[dict[str, Any]] = []
    numbers: set[int] = set()
    orders: set[int] = set()
    segments: list[tuple[int, int, int]] = []
    for index, raw in enumerate(periods, 1):
        try:
            number = int(raw["shift_number"])
            shift_id = int(raw["shift_id"])
            order = int(raw.get("period_order", index))
        except (KeyError, TypeError, ValueError):
            raise ShiftTypeValidationError(f"Period {index}: Shift, Shift ID, and order are required.") from None
        if number not in range(1, 10) or shift_id <= 0 or order <= 0:
            raise ShiftTypeValidationError("Shift numbers, IDs, and period orders must be positive valid values.")
        if number in numbers or order in orders:
            raise ShiftTypeValidationError("Shift numbers and period orders must be unique within a Type.")
        numbers.add(number)
        orders.add(order)
        start_text, start = _clock(raw.get("start_time"), f"Shift {number} start time")
        end_text, end = _clock(raw.get("end_time"), f"Shift {number} end time")
        end_next_day = raw.get("end_next_day", False)
        active = raw.get("active", True)
        if not isinstance(end_next_day, bool) or not isinstance(active, bool):
            raise ShiftTypeValidationError("End-on-next-day and active values must be true or false.")
        if (end_next_day and end >= start) or (not end_next_day and end <= start):
            raise ShiftTypeValidationError(f"Shift {number} period must have a positive duration under its next-day setting.")
        normalized.append({
            "shift_id": shift_id, "shift_number": number, "period_order": order,
            "start_time": start_text, "end_time": end_text,
            "end_next_day": end_next_day, "active": active,
        })
        if active:
            if end_next_day:
                segments.extend(((start, 1440, number), (0, end, number)))
            else:
                segments.append((start, end, number))
    if numbers != _EXPECTED_SHIFT_NUMBERS[type_code]:
        expected = ", ".join(str(item) for item in sorted(_EXPECTED_SHIFT_NUMBERS[type_code]))
        raise ShiftTypeValidationError(f"{type_code} must retain the factory-confirmed Shift numbers: {expected}.")
    for index, left in enumerate(segments):
        for right in segments[index + 1:]:
            if left[2] != right[2] and max(left[0], right[0]) < min(left[1], right[1]):
                raise ShiftTypeValidationError(f"Shift {left[2]} and Shift {right[2]} periods overlap.")
    return sorted(normalized, key=lambda item: (item["period_order"], item["shift_number"]))


def schedule_period_bounds(production_date: str, period: dict[str, Any]) -> tuple[datetime, datetime]:
    selected_date = date.fromisoformat(production_date)
    start = datetime.combine(selected_date, time.fromisoformat(period["start_time"]), tzinfo=_ZONE)
    end_date = selected_date + timedelta(days=1) if period["end_next_day"] else selected_date
    end = datetime.combine(end_date, time.fromisoformat(period["end_time"]), tzinfo=_ZONE)
    return start, end


def shift_for_type_timestamp(
    schedule: dict[str, Any], timestamp: datetime, production_date: str | None = None,
) -> dict[str, Any] | None:
    local = localize_timestamp(timestamp)
    for period in schedule["periods"]:
        if not period["active"]:
            continue
        assigned_date = production_date or schedule["effective_production_date"]
        start, end = schedule_period_bounds(assigned_date, period)
        if start <= local < end:
            return period
    return None


def resolve_lot_start_context(
    timestamp: datetime,
    *,
    cutoff_versions: list[dict[str, Any]],
    assignment_for_date: Any,
) -> dict[str, Any]:
    """Resolve Lot ownership using saved daily assignments and overnight start-date ownership.

    If the prior Production Date's assigned next-day period contains the instant,
    that assignment owns the Lot even if a generic cutoff would select today's date.
    Otherwise the configured Production Date cutoff selects the assignment date.
    """
    local = localize_timestamp(timestamp)
    prior_date = (local.date() - timedelta(days=1)).isoformat()
    prior_assignment = assignment_for_date(prior_date)
    if prior_assignment and prior_assignment.get("status") == "SAVED":
        prior_schedule = prior_assignment.get("schedule")
        if prior_schedule:
            for period in prior_schedule["periods"]:
                if period["active"] and period["end_next_day"]:
                    start, end = schedule_period_bounds(prior_date, period)
                    if start <= local < end:
                        return _resolved_context(prior_assignment, period, prior_date, "OVERNIGHT SHIFT OWNING PRODUCTION DATE")

    production_date, cutoff_id = resolve_production_date(local, cutoff_versions)
    assignment = assignment_for_date(production_date)
    if not assignment or assignment.get("status") != "SAVED" or not assignment.get("schedule"):
        return {
            "status": "SHIFT TYPE NOT SELECTED", "production_date": production_date,
            "cutoff_version_id": cutoff_id, "shift_type_id": None,
            "shift_type_code": None, "shift_type_schedule_version_id": None,
            "shift_id": None, "shift_number": None, "shift_name": "SHIFT TYPE NOT SELECTED",
        }
    period = shift_for_type_timestamp(assignment["schedule"], local, production_date=production_date)
    if period is None:
        return {
            **_resolved_context(assignment, None, production_date, "OUTSIDE SCHEDULED SHIFT"),
            "cutoff_version_id": cutoff_id,
        }
    return {**_resolved_context(assignment, period, production_date, "ASSIGNED"), "cutoff_version_id": cutoff_id}


def _resolved_context(assignment: dict[str, Any], period: dict[str, Any] | None, production_date: str, status: str) -> dict[str, Any]:
    schedule = assignment["schedule"]
    return {
        "status": status,
        "production_date": production_date,
        "shift_type_id": assignment["shift_type_id"],
        "shift_type_code": assignment["type_code"],
        "shift_type_schedule_version_id": assignment["schedule_version_id"],
        "shift_id": period["shift_id"] if period else None,
        "shift_number": period["shift_number"] if period else None,
        "shift_name": f"Shift {period['shift_number']}" if period else "OUTSIDE SCHEDULED SHIFT",
        "period_order": period["period_order"] if period else None,
        "production_day_cutoff_version_id": assignment.get("cutoff_version_id"),
        "schedule": schedule,
    }
