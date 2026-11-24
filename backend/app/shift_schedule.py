from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from .production_day import PRODUCTION_TIMEZONE


class ScheduleValidationError(ValueError):
    """Invalid mock shift schedule input."""


def initial_schedule_versions() -> list[dict[str, Any]]:
    return [
        {
            "id": 1,
            "effective_from": "2026-01-01",
            "created_at": "2026-01-01T00:00:00+07:00",
            "created_by": "APPROVED SHIFT TIMES · MOCK EFFECTIVE-DATE PLACEHOLDER",
            "shifts": [
                {"id": 1, "shift_code": "1", "shift_name": "Shift 1", "start_time": "08:00", "end_time": "19:00", "display_order": 1, "active": True},
                {"id": 2, "shift_code": "2", "shift_name": "Shift 2", "start_time": "19:00", "end_time": "06:00", "display_order": 2, "active": True},
            ],
        }
    ]


def _parse_clock(value: str, label: str) -> int:
    try:
        parsed = time.fromisoformat(value)
    except (TypeError, ValueError):
        raise ScheduleValidationError(f"{label} must use a valid 24-hour HH:MM time") from None
    if parsed.second or parsed.microsecond or parsed.tzinfo is not None:
        raise ScheduleValidationError(f"{label} must use a local HH:MM time without seconds or timezone")
    return parsed.hour * 60 + parsed.minute


def validate_shift_definitions(shifts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not shifts:
        raise ScheduleValidationError("A schedule version must contain at least one shift definition")

    normalized: list[dict[str, Any]] = []
    seen_ids: set[int] = set()
    seen_codes: set[str] = set()
    seen_names: set[str] = set()
    seen_orders: set[int] = set()
    intervals: list[tuple[int, int, int]] = []

    for index, item in enumerate(shifts, start=1):
        name = str(item.get("shift_name", "")).strip()
        code = str(item.get("shift_code", "")).strip()
        if not name or len(name) > 100:
            raise ScheduleValidationError(f"Shift {index}: Shift Name is required and must be at most 100 characters")
        if not code or len(code) > 40:
            raise ScheduleValidationError(f"Shift {index}: Shift Code is required and must be at most 40 characters")

        folded_name = name.casefold()
        folded_code = code.casefold()
        if folded_name in seen_names:
            raise ScheduleValidationError(f"Duplicate Shift Name: {name}")
        if folded_code in seen_codes:
            raise ScheduleValidationError(f"Duplicate Shift Code: {code}")
        seen_names.add(folded_name)
        seen_codes.add(folded_code)

        raw_id = item.get("id")
        shift_id = int(raw_id) if raw_id is not None else None
        if shift_id is not None:
            if shift_id <= 0 or shift_id in seen_ids:
                raise ScheduleValidationError("Shift IDs must be positive and unique within a version")
            seen_ids.add(shift_id)

        start = _parse_clock(str(item.get("start_time", "")), f"Shift {name} start time")
        end = _parse_clock(str(item.get("end_time", "")), f"Shift {name} end time")
        if start == end:
            raise ScheduleValidationError(f"Shift {name} start and end times cannot be equal")

        try:
            display_order = int(item.get("display_order", index))
        except (TypeError, ValueError):
            raise ScheduleValidationError(f"Shift {name} display order must be a positive integer") from None
        if display_order <= 0 or display_order in seen_orders:
            raise ScheduleValidationError("Display order values must be positive and unique")
        seen_orders.add(display_order)

        active = item.get("active", True)
        if not isinstance(active, bool):
            raise ScheduleValidationError(f"Shift {name} active status must be true or false")

        normalized.append({
            "id": shift_id,
            "shift_code": code,
            "shift_name": name,
            "start_time": str(item["start_time"]).strip(),
            "end_time": str(item["end_time"]).strip(),
            "display_order": display_order,
            "active": active,
        })

        if active:
            if start < end:
                intervals.append((start, end, index))
            else:
                intervals.extend(((start, 1440, index), (0, end, index)))

    for position, left in enumerate(intervals):
        for right in intervals[position + 1:]:
            if left[2] != right[2] and max(left[0], right[0]) < min(left[1], right[1]):
                raise ScheduleValidationError("Active shift time windows overlap")

    return sorted(normalized, key=lambda item: (item["display_order"], item["id"] or 0))


def validate_shift_period_definitions(shifts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Normalize Shift master snapshots and their separately ordered time periods."""
    if not shifts:
        raise ScheduleValidationError("A schedule version must contain at least one Shift")
    normalized: list[dict[str, Any]] = []
    shift_ids: set[int] = set()
    codes: set[str] = set()
    names: set[str] = set()
    shift_orders: set[int] = set()
    global_intervals: list[tuple[int, int, str]] = []
    for index, raw in enumerate(shifts, 1):
        name = str(raw.get("shift_name", "")).strip()
        code = str(raw.get("shift_code", "")).strip()
        if not name or len(name) > 100 or not code or len(code) > 40:
            raise ScheduleValidationError(f"Shift {index}: Shift Name and Shift Code are required and must fit the configured limits")
        if name.casefold() in names or code.casefold() in codes:
            raise ScheduleValidationError("Shift Names and Shift Codes must be unique within a version")
        names.add(name.casefold())
        codes.add(code.casefold())
        raw_id = raw.get("id")
        shift_id = int(raw_id) if raw_id is not None else None
        if shift_id is not None and (shift_id <= 0 or shift_id in shift_ids):
            raise ScheduleValidationError("Shift IDs must be positive and unique within a version")
        if shift_id is not None:
            shift_ids.add(shift_id)
        try:
            shift_order = int(raw.get("display_order", index))
        except (TypeError, ValueError):
            raise ScheduleValidationError(f"Shift {name} display order must be a positive integer") from None
        if shift_order <= 0 or shift_order in shift_orders:
            raise ScheduleValidationError("Shift display order values must be positive and unique")
        shift_orders.add(shift_order)
        active = raw.get("active", True)
        if not isinstance(active, bool):
            raise ScheduleValidationError(f"Shift {name} active status must be true or false")

        raw_periods = raw.get("periods") or []
        if not raw_periods:
            raise ScheduleValidationError(f"Shift {name} must have at least one period")
        periods: list[dict[str, Any]] = []
        period_orders: set[int] = set()
        for period_index, raw_period in enumerate(raw_periods, 1):
            start_text = str(raw_period.get("start_time", "")).strip()
            end_text = str(raw_period.get("end_time", "")).strip()
            start = _parse_clock(start_text, f"Shift {name} period {period_index} start time")
            end = _parse_clock(end_text, f"Shift {name} period {period_index} end time")
            if start == end:
                raise ScheduleValidationError(f"Shift {name} period {period_index} start and end times cannot be equal")
            try:
                period_order = int(raw_period.get("display_order", period_index))
            except (TypeError, ValueError):
                raise ScheduleValidationError(f"Shift {name} period order must be a positive integer") from None
            if period_order <= 0 or period_order in period_orders:
                raise ScheduleValidationError(f"Shift {name} period orders must be positive and unique")
            period_orders.add(period_order)
            period_active = raw_period.get("active", True)
            if not isinstance(period_active, bool):
                raise ScheduleValidationError(f"Shift {name} period active status must be true or false")
            if period_active and not active:
                raise ScheduleValidationError(f"Inactive Shift {name} cannot have active periods")
            if period_active:
                pieces = ((start, end),) if start < end else ((start, 1440), (0, end))
                for piece_start, piece_end in pieces:
                    global_intervals.append((piece_start, piece_end, f"{name} period {period_order}"))
            periods.append({"start_time": start_text, "end_time": end_text, "display_order": period_order, "active": period_active})
        if active and not any(period["active"] for period in periods):
            raise ScheduleValidationError(f"Active Shift {name} must have an active period")
        periods.sort(key=lambda item: item["display_order"])
        normalized.append({
            "id": shift_id, "shift_code": code, "shift_name": name,
            "start_time": periods[0]["start_time"], "end_time": periods[0]["end_time"],
            "display_order": shift_order, "active": active, "periods": periods,
        })

    for index, left in enumerate(global_intervals):
        for right in global_intervals[index + 1:]:
            if left[2] != right[2] and max(left[0], right[0]) < min(left[1], right[1]):
                raise ScheduleValidationError(f"Active Shift periods overlap: {left[2]} and {right[2]}")
    return sorted(normalized, key=lambda item: (item["display_order"], item["id"] or 0))


def _clock_text(minutes: int) -> str:
    minutes %= 1440
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def _unassigned_gaps(shifts: list[dict[str, Any]]) -> list[dict[str, str]]:
    intervals: list[tuple[int, int]] = []
    for shift in shifts:
        if not shift["active"]:
            continue
        periods = shift.get("periods") or [{"start_time": shift["start_time"], "end_time": shift["end_time"], "active": True}]
        for period in periods:
            if not period.get("active", True):
                continue
            start = _parse_clock(period["start_time"], "Shift period start time")
            end = _parse_clock(period["end_time"], "Shift period end time")
            intervals.extend(((start, end),) if start < end else ((start, 1440), (0, end)))

    merged: list[list[int]] = []
    for start, end in sorted(intervals):
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])

    if not merged:
        return [{"start_time": "00:00", "end_time": "24:00"}]

    gaps: list[dict[str, str]] = []
    for index, current in enumerate(merged):
        next_interval = merged[(index + 1) % len(merged)]
        gap_start = current[1]
        gap_end = next_interval[0] + (1440 if index == len(merged) - 1 else 0)
        if gap_end > gap_start:
            gaps.append({"start_time": _clock_text(gap_start), "end_time": _clock_text(gap_end)})
    return gaps


def resolve_schedule_context(versions: list[dict[str, Any]], production_date: str) -> dict[str, Any]:
    try:
        selected_date = date.fromisoformat(production_date)
    except (TypeError, ValueError):
        raise ScheduleValidationError("Production Date must be an ISO calendar date (YYYY-MM-DD)") from None

    ordered = sorted(versions, key=lambda item: item["effective_from"])
    applicable_index = next(
        (index for index in range(len(ordered) - 1, -1, -1) if ordered[index]["effective_from"] <= production_date),
        None,
    )
    if applicable_index is None:
        raise ScheduleValidationError("No Shift Schedule version applies to the selected Production Date")

    version = ordered[applicable_index]
    next_version = ordered[applicable_index + 1] if applicable_index + 1 < len(ordered) else None
    effective_to = next_version["effective_from"] if next_version else None
    selected_shifts = sorted(version["shifts"], key=lambda item: (item["display_order"], item["id"]))
    resolved: list[dict[str, Any]] = []
    for shift in selected_shifts:
        periods = shift.get("periods") or [{"start_time": shift["start_time"], "end_time": shift["end_time"], "display_order": 1, "active": True}]
        for period in periods:
            start_time = time.fromisoformat(period["start_time"])
            end_time = time.fromisoformat(period["end_time"])
            start_at = datetime.combine(selected_date, start_time, tzinfo=ZoneInfo(PRODUCTION_TIMEZONE))
            end_date = selected_date + timedelta(days=1) if end_time <= start_time else selected_date
            end_at = datetime.combine(end_date, end_time, tzinfo=ZoneInfo(PRODUCTION_TIMEZONE))
            resolved.append({**shift, **period, "period_order": period.get("display_order", 1), "start_at": start_at.isoformat(), "end_at": end_at.isoformat(), "interval_semantics": "[start, end)"})

    return {
        "production_date": selected_date.isoformat(),
        "time_zone": PRODUCTION_TIMEZONE,
        "applicable_version_id": version["id"],
        "applicable_version": {**version, "effective_to_exclusive": effective_to},
        "resolved_shifts": resolved,
        "unassigned_gaps": _unassigned_gaps(selected_shifts),
        "schedule_versions": [{
            **item,
            "effective_to_exclusive": ordered[index + 1]["effective_from"] if index + 1 < len(ordered) else None,
        } for index, item in enumerate(ordered)],
    }


def draft_requires_schedule_review(draft: dict[str, Any], applicable_version_id: int) -> bool:
    return draft["schedule_version_id"] != applicable_version_id


def shift_for_timestamp(schedule_context: dict[str, Any], timestamp: datetime) -> dict[str, Any] | None:
    """Return the active shift containing a Bangkok-local timestamp, or None for a gap.

    Shift resolution is deliberately independent of Production Day cutoff logic.
    """
    from .production_day import localize_timestamp

    local_timestamp = localize_timestamp(timestamp)
    for shift in schedule_context["resolved_shifts"]:
        if not shift["active"]:
            continue
        start = datetime.fromisoformat(shift["start_at"])
        end = datetime.fromisoformat(shift["end_at"])
        if start <= local_timestamp < end:
            return shift
    return None


def validate_draft_interval(schedule_context: dict[str, Any], shift_id: int, started_at: datetime, ended_at: datetime | None) -> None:
    shifts = [item for item in schedule_context["resolved_shifts"] if item["id"] == shift_id and item["active"]]
    if not shifts:
        raise ScheduleValidationError("Draft must reference an active Shift ID in the applicable schedule version")
    # Production Date schedule boundaries are local wall-clock values. The actual historian timezone remains a separate integration gate.
    from .production_day import localize_timestamp

    candidate_start = localize_timestamp(started_at)
    candidate_end = localize_timestamp(ended_at) if ended_at else None
    containing = [item for item in shifts if datetime.fromisoformat(item["start_at"]) <= candidate_start < datetime.fromisoformat(item["end_at"])]
    if not containing:
        raise ScheduleValidationError("Draft start must fall within the selected Production Date shift interval")
    shift_end = datetime.fromisoformat(containing[0]["end_at"])
    if candidate_end is not None and candidate_end > shift_end:
        raise ScheduleValidationError("Draft end cannot extend beyond the selected shift interval; split it into shift-bounded drafts")
