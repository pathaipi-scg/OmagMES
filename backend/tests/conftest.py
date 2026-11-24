from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

import backend.app.main as main_module
from backend.app.production_day import minimum_safe_cutoff_effective_date, parse_production_date, parse_cutoff_time
from backend.app.shift_schedule import validate_shift_definitions, validate_shift_period_definitions
from backend.app.store import store


class TestConfigurationRepository:
    """Deterministic API-test double; production never selects this repository."""

    def __init__(self) -> None:
        self.settings = SimpleNamespace(target_confirmed=True, writes_confirmed=True)
        self.cutoff_versions: list[dict[str, Any]] = [{
            "id": 1,
            "effective_from": "2026-01-01",
            "cutoff_time": "07:00",
            "time_zone": "Asia/Bangkok",
            "created_at": "2026-01-01T00:00:00+00:00",
            "created_by": "TEST FIXTURE",
            "change_reason": "Test baseline only",
        }]

    def get_cutoff_versions(self) -> list[dict[str, Any]]:
        return self.cutoff_versions

    def get_shift_versions(self) -> list[dict[str, Any]]:
        return store.shift_schedule_versions

    @staticmethod
    def get_daily_shift_type_assignment(production_date: str) -> dict[str, Any]:
        return {"status": "SHIFT TYPE NOT SELECTED", "production_date": production_date, "assignment": None}

    @staticmethod
    def get_daily_shift_configuration(production_date: str) -> dict[str, Any]:
        return {
            "status": "NOT_SAVED", "production_date": production_date, "selected_type": 1,
            "type_code": "TYPE 1", "periods": [], "source_production_date": None,
            "configuration_save_id": None, "save_time": None, "schedule": None,
        }

    def get_configuration_history(self, limit: int = 500) -> list[dict[str, Any]]:
        del limit
        return []

    @staticmethod
    def shift_period_schema_available() -> bool:
        return True

    def create_cutoff_version(self, *, effective_from: str, cutoff_time: str, time_zone: str, base_version_id: int,
                              reason: str, current_production_date: str) -> dict[str, Any]:
        parse_cutoff_time(cutoff_time)
        if time_zone != "Asia/Bangkok":
            from backend.app.production_day import ProductionDayConfigurationError
            raise ProductionDayConfigurationError("Unsupported test cutoff timezone")
        effective = parse_production_date(effective_from)
        if effective_from < minimum_safe_cutoff_effective_date(current_production_date):
            from backend.app.configuration_repository import ConfigurationConflict
            raise ConfigurationConflict("Unsafe cutoff effective date")
        latest = self.cutoff_versions[-1]
        if latest["id"] != base_version_id or effective <= parse_production_date(latest["effective_from"]):
            from backend.app.configuration_repository import ConfigurationConflict
            raise ConfigurationConflict("Conflicting cutoff version")
        version = {"id": latest["id"] + 1, "effective_from": effective.isoformat(), "cutoff_time": cutoff_time, "time_zone": time_zone,
                   "created_at": "TEST UTC", "created_by": "TEST FIXTURE", "change_reason": reason}
        self.cutoff_versions.append(version)
        return version

    def create_shift_version(self, *, effective_from: str, base_version_id: int, reason: str,
                             shifts: list[dict[str, Any]], reviewed_through_date: str) -> dict[str, Any]:
        normalized = validate_shift_definitions(shifts)
        versions = store.shift_schedule_versions
        latest = versions[-1]
        if latest["id"] != base_version_id or effective_from <= latest["effective_from"] or effective_from <= reviewed_through_date:
            from backend.app.configuration_repository import ConfigurationConflict
            raise ConfigurationConflict("Conflicting schedule version")
        known = {item["id"] for version in versions for item in version["shifts"]}
        latest_ids = {item["id"] for item in latest["shifts"]}
        for shift in normalized:
            if shift["id"] is not None and (shift["id"] not in known or shift["id"] not in latest_ids):
                from backend.app.production_day import ProductionDayConfigurationError
                raise ProductionDayConfigurationError("Unknown test shift identity")
            if shift["id"] is None:
                shift["id"] = store.next_shift_id()
        version = {"id": latest["id"] + 1, "effective_from": effective_from, "created_at": "TEST UTC",
                   "created_by": "TEST FIXTURE", "change_reason": reason, "shifts": normalized}
        versions.append(version)
        return version

    def create_shift_period_version(self, *, effective_from: str, base_version_id: int, reason: str,
                                    shifts: list[dict[str, Any]], reviewed_through_date: str) -> dict[str, Any]:
        normalized = validate_shift_period_definitions(shifts)
        versions = store.shift_schedule_versions
        latest = versions[-1]
        if latest["id"] != base_version_id or effective_from <= latest["effective_from"] or effective_from <= reviewed_through_date:
            from backend.app.configuration_repository import ConfigurationConflict
            raise ConfigurationConflict("Conflicting schedule version")
        latest_ids = {item["id"] for item in latest["shifts"]}
        known_ids = {item["id"] for version in versions for item in version["shifts"]}
        for shift in normalized:
            if shift["id"] is not None and (shift["id"] not in known_ids or shift["id"] not in latest_ids):
                from backend.app.production_day import ProductionDayConfigurationError
                raise ProductionDayConfigurationError("Unknown test shift identity")
            if shift["id"] is None:
                shift["id"] = store.next_shift_id()
        version = {"id": latest["id"] + 1, "effective_from": effective_from, "created_at": "TEST UTC",
                   "created_by": "TEST FIXTURE", "change_reason": reason, "shifts": normalized}
        versions.append(version)
        return version


@pytest.fixture(autouse=True)
def use_test_configuration_repository(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(main_module, "configuration_repository", TestConfigurationRepository())
