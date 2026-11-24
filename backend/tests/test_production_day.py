from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from backend.app.production_day import (
    PRODUCTION_TIMEZONE,
    ProductionDayConfigurationError,
    cutoff_version_for_date,
    production_day_window,
    resolve_cutoff_context,
    resolve_production_date,
)


BANGKOK = ZoneInfo(PRODUCTION_TIMEZONE)
CUTOFF_VERSIONS = [
    {"id": 1, "effective_from": "2026-01-01", "cutoff_time": "07:00", "change_reason": "Initial"},
]


def test_cutoff_boundary_is_inclusive_and_calendar_midnight_is_not_production_midnight() -> None:
    assert resolve_production_date(datetime(2026, 6, 14, 23, 59, 59, tzinfo=BANGKOK), CUTOFF_VERSIONS) == ("2026-06-14", 1)
    assert resolve_production_date(datetime(2026, 6, 15, 0, 0, tzinfo=BANGKOK), CUTOFF_VERSIONS) == ("2026-06-14", 1)
    assert resolve_production_date(datetime(2026, 6, 15, 6, 59, 59, tzinfo=BANGKOK), CUTOFF_VERSIONS) == ("2026-06-14", 1)
    assert resolve_production_date(datetime(2026, 6, 15, 7, 0, tzinfo=BANGKOK), CUTOFF_VERSIONS) == ("2026-06-15", 1)


def test_naive_timestamp_is_interpreted_as_bangkok_local_time() -> None:
    assert resolve_production_date(datetime(2026, 6, 15, 6, 59, 59), CUTOFF_VERSIONS) == ("2026-06-14", 1)


def test_effective_dated_cutoff_transition_uses_new_boundary_without_rewriting_history() -> None:
    versions = [
        *CUTOFF_VERSIONS,
        {"id": 2, "effective_from": "2026-06-15", "cutoff_time": "06:00", "change_reason": "Approved change"},
    ]
    assert resolve_production_date(datetime(2026, 6, 15, 5, 59, 59, tzinfo=BANGKOK), versions) == ("2026-06-14", 1)
    assert resolve_production_date(datetime(2026, 6, 15, 6, 0, tzinfo=BANGKOK), versions) == ("2026-06-15", 2)
    assert cutoff_version_for_date(versions, "2026-06-14")["id"] == 1
    assert cutoff_version_for_date(versions, "2026-06-15")["id"] == 2


def test_transition_day_window_is_contiguous_and_can_be_23_hours() -> None:
    versions = [
        *CUTOFF_VERSIONS,
        {"id": 2, "effective_from": "2026-06-15", "cutoff_time": "06:00", "change_reason": "Approved change"},
    ]
    previous_day = production_day_window("2026-06-14", versions)
    next_day = production_day_window("2026-06-15", versions)
    assert previous_day["start_at"] == "2026-06-14T07:00:00+07:00"
    assert previous_day["end_at_exclusive"] == next_day["start_at"] == "2026-06-15T06:00:00+07:00"
    assert previous_day["duration_seconds"] == 23 * 60 * 60
    assert next_day["duration_seconds"] == 24 * 60 * 60
    assert previous_day["interval_semantics"] == "[start, end)"


def test_later_cutoff_transition_can_make_a_25_hour_day() -> None:
    versions = [
        *CUTOFF_VERSIONS,
        {"id": 2, "effective_from": "2026-06-15", "cutoff_time": "08:00", "change_reason": "Approved change"},
    ]
    day = production_day_window("2026-06-14", versions)
    assert day["duration_seconds"] == 25 * 60 * 60
    assert day["end_at_exclusive"] == "2026-06-15T08:00:00+07:00"


def test_selected_historical_production_date_is_resolved_without_mutating_version_rows() -> None:
    versions = [
        *CUTOFF_VERSIONS,
        {"id": 2, "effective_from": "2026-06-15", "cutoff_time": "06:00", "change_reason": "Approved change"},
    ]
    before = [dict(version) for version in versions]
    context = resolve_cutoff_context("2026-06-14", versions)
    assert context["applicable_version"]["id"] == 1
    assert context["versions"][0]["effective_to_exclusive"] == "2026-06-15"
    assert context["window"]["end_cutoff_version_id"] == 2
    assert versions == before


@pytest.mark.parametrize("value", ["2026-02-30", "2026-6-01", "not-a-date"])
def test_invalid_production_date_is_rejected(value: str) -> None:
    with pytest.raises(ProductionDayConfigurationError):
        cutoff_version_for_date(CUTOFF_VERSIONS, value)


def test_missing_initial_or_applicable_cutoff_version_fails_closed() -> None:
    with pytest.raises(ProductionDayConfigurationError, match="No persisted"):
        cutoff_version_for_date([], "2026-06-14")
