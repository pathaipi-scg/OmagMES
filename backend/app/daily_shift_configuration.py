from __future__ import annotations

import re
from datetime import time
from typing import Any


_EXPECTED_SHIFTS = {1: {1}, 2: {1, 2}, 3: {2, 3}}
_TIME_PATTERN = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")


class DailyShiftConfigurationError(ValueError):
    """Invalid daily Shift Type or one of its complete period templates."""


def initial_shift_periods() -> list[dict[str, Any]]:
    return [
        {"type": 1, "shift": 1, "start": "08:00", "stop": "16:00"},
        {"type": 2, "shift": 1, "start": "08:00", "stop": "16:00"},
        {"type": 2, "shift": 2, "start": "16:00", "stop": "00:00"},
        {"type": 3, "shift": 3, "start": "08:00", "stop": "20:00"},
        {"type": 3, "shift": 2, "start": "20:00", "stop": "08:00"},
    ]


def normalize_shift_configuration(selected_type: Any, raw_periods: Any) -> tuple[int, list[dict[str, Any]]]:
    try:
        selected = int(selected_type)
    except (TypeError, ValueError):
        raise DailyShiftConfigurationError("Select Shift Type 1, 2, or 3.") from None
    if selected not in _EXPECTED_SHIFTS:
        raise DailyShiftConfigurationError("Select Shift Type 1, 2, or 3.")
    if not isinstance(raw_periods, list) or len(raw_periods) != 5:
        raise DailyShiftConfigurationError("The complete Shift table must contain all five configured periods.")

    normalized: list[dict[str, Any]] = []
    seen: set[tuple[int, int]] = set()
    by_type: dict[int, list[dict[str, Any]]] = {1: [], 2: [], 3: []}
    for index, raw in enumerate(raw_periods, start=1):
        if not isinstance(raw, dict):
            raise DailyShiftConfigurationError(f"Period {index} is invalid.")
        try:
            type_number = int(raw["type"])
            shift_number = int(raw["shift"])
        except (KeyError, TypeError, ValueError):
            raise DailyShiftConfigurationError(f"Period {index} must include its fixed Type and Shift numbers.") from None
        if type_number not in _EXPECTED_SHIFTS or shift_number not in _EXPECTED_SHIFTS[type_number]:
            raise DailyShiftConfigurationError("Shift Number mappings are fixed: Type 1 uses Shift 1, Type 2 uses Shifts 1 and 2, and Type 3 uses Shifts 3 and 2.")
        key = (type_number, shift_number)
        if key in seen:
            raise DailyShiftConfigurationError("Each Type and Shift period must appear exactly once.")
        seen.add(key)
        start = raw.get("start")
        stop = raw.get("stop")
        if not isinstance(start, str) or not _TIME_PATTERN.fullmatch(start):
            raise DailyShiftConfigurationError(f"Type {type_number} Shift {shift_number} start must be a valid HH:MM time.")
        if not isinstance(stop, str) or not _TIME_PATTERN.fullmatch(stop):
            raise DailyShiftConfigurationError(f"Type {type_number} Shift {shift_number} stop must be a valid HH:MM time.")
        start_time = time.fromisoformat(start)
        stop_time = time.fromisoformat(stop)
        if start_time == stop_time:
            raise DailyShiftConfigurationError(f"Type {type_number} Shift {shift_number} cannot have a zero-length period.")
        period = {
            "type": type_number, "shift": shift_number,
            "start": start, "stop": stop,
            "start_minute": start_time.hour * 60 + start_time.minute,
            "stop_minute": stop_time.hour * 60 + stop_time.minute,
            "end_next_day": stop_time <= start_time,
        }
        normalized.append(period)
        by_type[type_number].append(period)

    if seen != {(type_number, shift) for type_number, shifts in _EXPECTED_SHIFTS.items() for shift in shifts}:
        raise DailyShiftConfigurationError("The Shift table is missing one or more required periods.")

    for type_number, periods in by_type.items():
        segments: list[tuple[int, int, int]] = []
        for period in periods:
            start_minute = period["start_minute"]
            stop_minute = period["stop_minute"]
            if period["end_next_day"]:
                segments.append((start_minute, 1440, period["shift"]))
                if stop_minute:
                    segments.append((0, stop_minute, period["shift"]))
            else:
                segments.append((start_minute, stop_minute, period["shift"]))
        for index, left in enumerate(segments):
            for right in segments[index + 1:]:
                if left[2] != right[2] and max(left[0], right[0]) < min(left[1], right[1]):
                    raise DailyShiftConfigurationError(f"Type {type_number} periods for Shift {left[2]} and Shift {right[2]} overlap.")

    normalized.sort(key=lambda period: (period["type"], period["shift"]))
    return selected, normalized


def template_periods(raw_periods: list[dict[str, Any]]) -> list[dict[str, int | str]]:
    """Return the persisted five-row template without internal validation fields."""
    return [
        {"type": int(period["type"]), "shift": int(period["shift"]),
         "start": str(period["start"]), "stop": str(period["stop"])}
        for period in raw_periods
    ]
