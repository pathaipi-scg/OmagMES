from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


PRODUCTION_TIMEZONE = "Asia/Bangkok"
_PRODUCTION_ZONE = ZoneInfo(PRODUCTION_TIMEZONE)
_CLOCK_PATTERN = re.compile(r"^(?:[01][0-9]|2[0-3]):[0-5][0-9]$")


class ProductionDayConfigurationError(ValueError):
    """Invalid, missing, or conflicting Production Day configuration."""


def parse_cutoff_time(value: str) -> time:
    if not isinstance(value, str) or not _CLOCK_PATTERN.fullmatch(value):
        raise ProductionDayConfigurationError("Cutoff time must use HH:MM in 24-hour time.")
    return time.fromisoformat(value)


def parse_production_date(value: str) -> date:
    try:
        parsed = date.fromisoformat(value)
    except (TypeError, ValueError):
        raise ProductionDayConfigurationError("Production Date must be an ISO calendar date (YYYY-MM-DD).") from None
    if parsed.isoformat() != value:
        raise ProductionDayConfigurationError("Production Date must be an ISO calendar date (YYYY-MM-DD).")
    return parsed


def localize_timestamp(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=_PRODUCTION_ZONE)
    return value.astimezone(_PRODUCTION_ZONE)


def cutoff_version_for_date(versions: list[dict[str, Any]], calendar_date: date | str) -> dict[str, Any]:
    selected_date = calendar_date if isinstance(calendar_date, date) else parse_production_date(calendar_date)
    applicable = [
        version for version in versions
        if parse_production_date(version["effective_from"]) <= selected_date
    ]
    if not applicable:
        raise ProductionDayConfigurationError(
            f"No persisted Production Day Cutoff version applies to {selected_date.isoformat()}."
        )
    selected_version = max(applicable, key=lambda version: (version["effective_from"], version["id"]))
    time_zone = selected_version.get("time_zone", PRODUCTION_TIMEZONE)
    if time_zone != PRODUCTION_TIMEZONE:
        raise ProductionDayConfigurationError(f"Production Day Cutoff timezone must be {PRODUCTION_TIMEZONE}.")
    return selected_version


def resolve_production_date(timestamp: datetime, versions: list[dict[str, Any]]) -> tuple[str, int]:
    """Resolve an instant using the cutoff version for its Bangkok calendar date.

    A version effective on calendar date D changes the single boundary at D's
    cutoff: Production Date D-1 ends there and D starts there. This yields
    contiguous half-open operational-day intervals even when the cutoff moves.
    """
    local_timestamp = localize_timestamp(timestamp)
    cutoff_version = cutoff_version_for_date(versions, local_timestamp.date())
    cutoff = parse_cutoff_time(cutoff_version["cutoff_time"])
    boundary = datetime.combine(local_timestamp.date(), cutoff, tzinfo=_PRODUCTION_ZONE)
    production_date = local_timestamp.date() if local_timestamp >= boundary else local_timestamp.date() - timedelta(days=1)
    return production_date.isoformat(), cutoff_version_for_date(versions, production_date)["id"]


def production_day_window(production_date: str, versions: list[dict[str, Any]]) -> dict[str, Any]:
    selected_date = parse_production_date(production_date)
    start_version = cutoff_version_for_date(versions, selected_date)
    end_date = selected_date + timedelta(days=1)
    end_version = cutoff_version_for_date(versions, end_date)
    start = datetime.combine(selected_date, parse_cutoff_time(start_version["cutoff_time"]), tzinfo=_PRODUCTION_ZONE)
    end = datetime.combine(end_date, parse_cutoff_time(end_version["cutoff_time"]), tzinfo=_PRODUCTION_ZONE)
    if end <= start:
        raise ProductionDayConfigurationError("Production Day cutoff versions produce a non-positive operational interval.")
    return {
        "production_date": selected_date.isoformat(),
        "start_at": start.isoformat(),
        "end_at_exclusive": end.isoformat(),
        "duration_seconds": int((end - start).total_seconds()),
        "time_zone": PRODUCTION_TIMEZONE,
        "start_cutoff_version_id": start_version["id"],
        "end_cutoff_version_id": end_version["id"],
        "interval_semantics": "[start, end)",
    }


def resolve_cutoff_context(production_date: str, versions: list[dict[str, Any]]) -> dict[str, Any]:
    selected_date = parse_production_date(production_date)
    applicable = cutoff_version_for_date(versions, selected_date)
    ordered = sorted(versions, key=lambda version: (version["effective_from"], version["id"]))
    current_index = ordered.index(applicable)
    next_version = ordered[current_index + 1] if current_index + 1 < len(ordered) else None
    return {
        "production_date": selected_date.isoformat(),
        "time_zone": PRODUCTION_TIMEZONE,
        "applicable_version": {**applicable, "effective_to_exclusive": next_version["effective_from"] if next_version else None},
        "versions": [
            {
                **version,
                "effective_to_exclusive": ordered[index + 1]["effective_from"] if index + 1 < len(ordered) else None,
            }
            for index, version in enumerate(ordered)
        ],
        "window": production_day_window(selected_date.isoformat(), versions),
    }


def minimum_safe_cutoff_effective_date(current_production_date: str) -> str:
    """A cutoff takes effect at the next calendar-day boundary, so protect the
    already-started preceding Production Date by scheduling at least two dates
    beyond the current Production Date.
    """
    return (parse_production_date(current_production_date) + timedelta(days=2)).isoformat()
