from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

import backend.app.main as main_module
from backend.app.main import app
from backend.app.shift_schedule import initial_schedule_versions
from backend.app.store import store


client = TestClient(app, client=("127.0.0.1", 50001))


@pytest.fixture(autouse=True)
def reset_configuration_fixtures() -> None:
    store.shift_schedule_versions[:] = initial_schedule_versions()
    store.auto_lot_drafts.clear()
    store._next_shift_id = 3
    store._next_schedule_version_id = 2


def fix_current_production_date(monkeypatch: pytest.MonkeyPatch) -> None:
    now = datetime(2026, 6, 14, 8, 0, tzinfo=ZoneInfo("Asia/Bangkok"))
    monkeypatch.setattr(main_module, "current_production_day", lambda: ("2026-06-14", 1, now))


def cutoff_payload(**updates: object) -> dict[str, object]:
    return {
        "effective_from": "2026-06-16",
        "cutoff_time": "06:00",
        "reviewed_through_date": "2026-06-14",
        "base_version_id": 1,
        "change_reason": "Approved factory change",
        **updates,
    }


def test_configuration_write_allows_factory_lan_clients(monkeypatch: pytest.MonkeyPatch) -> None:
    fix_current_production_date(monkeypatch)
    repository = main_module.configuration_repository
    monkeypatch.setattr(repository, "create_cutoff_version", lambda **kwargs: {"status": "SAVED", **kwargs})
    remote_client = TestClient(app, client=("10.28.255.40", 50003))
    remote = remote_client.post("/api/production-day-cutoff/versions", json=cutoff_payload())
    assert remote.status_code == 201
    assert remote.json()["status"] == "SAVED"


def test_current_date_and_selected_historical_cutoff_are_distinct(monkeypatch: pytest.MonkeyPatch) -> None:
    fix_current_production_date(monkeypatch)
    current = client.get("/api/production-date/current")
    selected = client.get("/api/production-day-cutoff", params={"production_date": "2026-06-13"})
    assert current.status_code == selected.status_code == 200
    assert current.json()["calendar_date"] == "2026-06-14"
    assert current.json()["production_date"] == "2026-06-14"
    assert selected.json()["production_date"] == "2026-06-13"
    assert selected.json()["applicable_version"]["cutoff_time"] == "07:00"
    assert selected.json()["window"]["interval_semantics"] == "[start, end)"


def test_configuration_history_api_returns_identity_version_values_and_effective_dates(monkeypatch: pytest.MonkeyPatch) -> None:
    event = {
        "id": 9, "type": "SHIFT_PERIOD", "identity": "SHIFT:1:PERIOD:2", "version_id": 4,
        "old_value": None, "new_value": '{"start_time":"13:00"}', "changed_at": "2026-06-14T01:00:00",
        "changed_by": "INTERNAL DEVELOPMENT", "effective_from": "2026-06-20",
        "effective_to_exclusive": None, "change_reason": "Split shift",
    }
    monkeypatch.setattr(main_module.configuration_repository, "get_configuration_history", lambda: [event])
    response = client.get("/api/configuration-history")
    assert response.status_code == 200
    assert response.json()["events"] == [event]


def test_cutoff_save_is_append_only_and_independent_from_schedule(monkeypatch: pytest.MonkeyPatch) -> None:
    fix_current_production_date(monkeypatch)
    repository = main_module.configuration_repository
    schedule_before = [dict(version) for version in store.shift_schedule_versions]
    response = client.post("/api/production-day-cutoff/versions", json=cutoff_payload())
    assert response.status_code == 201
    assert len(repository.cutoff_versions) == 2
    assert repository.cutoff_versions[-1]["cutoff_time"] == "06:00"
    assert store.shift_schedule_versions == schedule_before
    assert client.get("/api/production-day-cutoff", params={"production_date": "2026-06-16"}).json()["applicable_version"]["id"] == 2


def test_future_cutoff_version_does_not_reassign_existing_historical_facts(monkeypatch: pytest.MonkeyPatch) -> None:
    fix_current_production_date(monkeypatch)
    existing_fact = {"id": 8001, "production_date": "2026-06-14", "production_day_cutoff_version_id": 1}
    store.production_entries[:] = [dict(existing_fact)]
    response = client.post("/api/production-day-cutoff/versions", json=cutoff_payload())
    assert response.status_code == 201
    assert store.production_entries == [existing_fact]
    assert client.get("/api/production-day-cutoff", params={"production_date": "2026-06-14"}).json()["applicable_version"]["id"] == 1


def test_cutoff_requires_reason_safe_future_date_and_latest_base(monkeypatch: pytest.MonkeyPatch) -> None:
    fix_current_production_date(monkeypatch)
    missing_reason = client.post("/api/production-day-cutoff/versions", json=cutoff_payload(change_reason="   "))
    unsafe_date = client.post("/api/production-day-cutoff/versions", json=cutoff_payload(effective_from="2026-06-15"))
    assert missing_reason.status_code == 422
    assert unsafe_date.status_code == 409
    first = client.post("/api/production-day-cutoff/versions", json=cutoff_payload())
    stale = client.post("/api/production-day-cutoff/versions", json=cutoff_payload(effective_from="2026-06-17"))
    assert first.status_code == 201
    assert stale.status_code == 409
    assert len(main_module.configuration_repository.cutoff_versions) == 2


def test_shift_schedule_save_is_a_separate_version_stream(monkeypatch: pytest.MonkeyPatch) -> None:
    fix_current_production_date(monkeypatch)
    repository = main_module.configuration_repository
    cutoff_before = [dict(version) for version in repository.cutoff_versions]
    payload = {
        "effective_from": "2026-06-15",
        "reviewed_through_date": "2026-06-14",
        "base_version_id": 1,
        "change_reason": "Approved shift review",
        "shifts": [
            {"id": 1, "shift_code": "1", "shift_name": "Shift 1", "start_time": "08:00", "end_time": "19:00", "display_order": 1, "active": True},
            {"id": 2, "shift_code": "2", "shift_name": "Shift 2", "start_time": "19:00", "end_time": "06:00", "display_order": 2, "active": True},
        ],
    }
    response = client.post("/api/shift-schedule/versions", json=payload)
    assert response.status_code == 201
    assert len(store.shift_schedule_versions) == 2
    assert repository.cutoff_versions == cutoff_before
    assert client.get("/api/shift-schedule", params={"production_date": "2026-06-15"}).json()["applicable_version_id"] == 2


def test_shift_schedule_api_rejects_overlapping_active_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    fix_current_production_date(monkeypatch)
    payload = {
        "effective_from": "2026-06-15", "reviewed_through_date": "2026-06-14", "base_version_id": 1,
        "change_reason": "Invalid overlap test",
        "shifts": [
            {"id": 1, "shift_code": "A", "shift_name": "A", "start_time": "08:00", "end_time": "16:00", "display_order": 1, "active": True},
            {"id": 2, "shift_code": "B", "shift_name": "B", "start_time": "15:00", "end_time": "20:00", "display_order": 2, "active": True},
        ],
    }
    response = client.post("/api/shift-schedule/versions", json=payload)
    assert response.status_code == 422
    assert "overlap" in response.json()["detail"]


def test_shift_period_schedule_api_resolves_periods_and_appends_a_future_version(monkeypatch: pytest.MonkeyPatch) -> None:
    fix_current_production_date(monkeypatch)
    initial = client.get("/api/shift-period-schedule", params={"production_date": "2026-06-14"})
    assert initial.status_code == 200
    assert initial.json()["periods_enabled"] is True
    assert len(initial.json()["resolved_shifts"]) == 2
    assert initial.json()["resolved_shifts"][0]["period_order"] == 1

    payload = {
        "effective_from": "2026-06-15", "reviewed_through_date": "2026-06-14", "base_version_id": 1,
        "change_reason": "Approved split-shift periods",
        "shifts": [
            {"id": 1, "shift_code": "1", "shift_name": "Shift 1", "start_time": "08:00", "end_time": "12:00", "display_order": 1, "active": True,
             "periods": [{"start_time": "08:00", "end_time": "12:00", "display_order": 1, "active": True}, {"start_time": "13:00", "end_time": "17:00", "display_order": 2, "active": True}]},
            {"id": 2, "shift_code": "2", "shift_name": "Shift 2", "start_time": "18:00", "end_time": "06:00", "display_order": 2, "active": True,
             "periods": [{"start_time": "18:00", "end_time": "06:00", "display_order": 1, "active": True}]},
        ],
    }
    saved = client.post("/api/shift-period-schedule/versions", json=payload)
    assert saved.status_code == 201
    future = client.get("/api/shift-period-schedule", params={"production_date": "2026-06-15"}).json()
    assert future["applicable_version_id"] == 2
    assert len(future["resolved_shifts"]) == 3
    assert future["resolved_shifts"][1]["period_order"] == 2


def test_shift_period_schedule_api_rejects_overlapping_periods(monkeypatch: pytest.MonkeyPatch) -> None:
    fix_current_production_date(monkeypatch)
    payload = {
        "effective_from": "2026-06-15", "reviewed_through_date": "2026-06-14", "base_version_id": 1,
        "change_reason": "Invalid period overlap",
        "shifts": [
            {"id": 1, "shift_code": "1", "shift_name": "Shift 1", "start_time": "08:00", "end_time": "12:00", "display_order": 1, "active": True,
             "periods": [{"start_time": "08:00", "end_time": "12:00", "display_order": 1, "active": True}]},
            {"id": 2, "shift_code": "2", "shift_name": "Shift 2", "start_time": "11:00", "end_time": "15:00", "display_order": 2, "active": True,
             "periods": [{"start_time": "11:00", "end_time": "15:00", "display_order": 1, "active": True}]},
        ],
    }
    response = client.post("/api/shift-period-schedule/versions", json=payload)
    assert response.status_code == 422
    assert "overlap" in response.json()["detail"]


def test_auto_lot_fixture_returns_cutoff_window_and_rejects_mismatched_date(monkeypatch: pytest.MonkeyPatch) -> None:
    fix_current_production_date(monkeypatch)
    schedule = client.get("/api/shift-schedule", params={"production_date": "2026-06-14"}).json()
    response = client.post("/api/auto-lot/drafts", json={
        "production_date": "2026-06-14",
        "schedule_version_id": schedule["applicable_version_id"],
        "cutoff_version_id": schedule["cutoff_version_id"],
        "shift_id": 1,
        "started_at": "2026-06-14T08:00:00+07:00",
        "ended_at": None,
        "raw_drop_count": 100,
    })
    assert response.status_code == 201
    assert response.json()["cutoff_version_id"] == 1
    assert response.json()["production_day_window"]["start_at"] == "2026-06-14T07:00:00+07:00"
    drafts = client.get("/api/auto-lot/drafts", params={"production_date": "2026-06-14"}).json()
    assert drafts["cutoff_version_id"] == 1
    assert len(drafts["drafts"]) == 1
    wrong_day = client.post("/api/auto-lot/drafts", json={
        "production_date": "2026-06-14", "schedule_version_id": 1, "cutoff_version_id": 999,
        "shift_id": 1, "started_at": "2026-06-14T08:00:00+07:00", "raw_drop_count": 1,
    })
    assert wrong_day.status_code == 409


def test_auto_lot_draft_requires_review_when_cutoff_version_changes(monkeypatch: pytest.MonkeyPatch) -> None:
    fix_current_production_date(monkeypatch)
    schedule = client.get("/api/shift-schedule", params={"production_date": "2026-06-16"}).json()
    created = client.post("/api/auto-lot/drafts", json={
        "production_date": "2026-06-16", "schedule_version_id": schedule["applicable_version_id"],
        "cutoff_version_id": schedule["cutoff_version_id"], "shift_id": 1,
        "started_at": "2026-06-16T08:00:00+07:00", "raw_drop_count": 20,
    })
    assert created.status_code == 201
    saved = client.post("/api/production-day-cutoff/versions", json=cutoff_payload())
    assert saved.status_code == 201
    listed = client.get("/api/auto-lot/drafts", params={"production_date": "2026-06-16"}).json()["drafts"][0]
    assert listed["requires_cutoff_review"] is True
    assert listed["requires_configuration_review"] is True
