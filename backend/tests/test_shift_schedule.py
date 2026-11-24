from copy import deepcopy
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

import backend.app.main as main_module
from backend.app.main import app
from backend.app.shift_schedule import (
    ScheduleValidationError,
    initial_schedule_versions,
    resolve_schedule_context,
    validate_shift_definitions,
)
from backend.app.store import store

client = TestClient(app, client=("127.0.0.1", 50002))


@pytest.fixture(autouse=True)
def reset_schedule_state(monkeypatch: pytest.MonkeyPatch):
    store.shift_schedule_versions[:] = initial_schedule_versions()
    store.auto_lot_drafts.clear()
    store._next_shift_id = 2
    store._next_schedule_version_id = 1
    now = datetime(2026, 11, 10, 8, 0, tzinfo=ZoneInfo("Asia/Bangkok"))
    monkeypatch.setattr(main_module, "current_production_day", lambda: ("2026-11-10", 1, now))
    yield


def test_approved_initial_schedule_resolves_overnight_and_explicit_gap():
    context = resolve_schedule_context(store.shift_schedule_versions, "2026-11-10")
    assert context["applicable_version_id"] == 1
    assert [(row["shift_name"], row["start_at"], row["end_at"]) for row in context["resolved_shifts"]] == [
        ("Shift 1", "2026-11-10T08:00:00+07:00", "2026-11-10T19:00:00+07:00"),
        ("Shift 2", "2026-11-10T19:00:00+07:00", "2026-11-11T06:00:00+07:00"),
    ]
    assert context["unassigned_gaps"] == [{"start_time": "06:00", "end_time": "08:00"}]


def test_dynamic_shift_names_codes_and_three_shift_configuration_are_independent():
    shifts = validate_shift_definitions([
        {"id": 1, "shift_name": "Alpha / night crew", "shift_code": "N-01", "start_time": "22:00", "end_time": "06:00", "display_order": 1, "active": True},
        {"id": 2, "shift_name": "14:00 team", "shift_code": "AFTERNOON", "start_time": "14:00", "end_time": "22:00", "display_order": 2, "active": True},
        {"shift_name": "Morning", "shift_code": "M", "start_time": "06:00", "end_time": "14:00", "display_order": 3, "active": True},
    ])
    assert len(shifts) == 3
    assert shifts[0]["shift_name"] == "Alpha / night crew"
    assert shifts[0]["shift_code"] == "N-01"
    assert shifts[2]["id"] is None


def test_overlaps_duplicates_equal_times_and_duplicate_order_are_rejected():
    base = [
        {"shift_name": "Night", "shift_code": "N", "start_time": "19:00", "end_time": "06:00", "display_order": 1, "active": True},
        {"shift_name": "Early", "shift_code": "E", "start_time": "05:00", "end_time": "10:00", "display_order": 2, "active": True},
    ]
    with pytest.raises(ScheduleValidationError, match="overlap"):
        validate_shift_definitions(base)

    for invalid, match in [
        ([{"shift_name": "A", "shift_code": "X", "start_time": "08:00", "end_time": "09:00", "display_order": 1}, {"shift_name": "B", "shift_code": "x", "start_time": "10:00", "end_time": "11:00", "display_order": 2}], "Duplicate Shift Code"),
        ([{"shift_name": "A", "shift_code": "X", "start_time": "08:00", "end_time": "09:00", "display_order": 1}, {"shift_name": "a", "shift_code": "Y", "start_time": "10:00", "end_time": "11:00", "display_order": 2}], "Duplicate Shift Name"),
        ([{"shift_name": "A", "shift_code": "X", "start_time": "08:00", "end_time": "08:00", "display_order": 1}], "cannot be equal"),
        ([{"shift_name": "A", "shift_code": "X", "start_time": "08:00", "end_time": "09:00", "display_order": 1}, {"shift_name": "B", "shift_code": "Y", "start_time": "10:00", "end_time": "11:00", "display_order": 1}], "Display order"),
    ]:
        with pytest.raises(ScheduleValidationError, match=match):
            validate_shift_definitions(invalid)


def _next_version(effective_from: str, shifts=None):
    return client.post("/api/shift-schedule/versions", json={
        "effective_from": effective_from,
        "reviewed_through_date": "2026-11-10",
        "base_version_id": max(store.shift_schedule_versions, key=lambda version: version["effective_from"])["id"],
        "change_reason": "Approved factory schedule review",
        "shifts": shifts or [
            {"id": 1, "shift_name": "Day crew", "shift_code": "D", "start_time": "08:00", "end_time": "19:00", "display_order": 1, "active": True},
            {"id": 2, "shift_name": "Night crew", "shift_code": "N", "start_time": "19:00", "end_time": "06:00", "display_order": 2, "active": True},
        ],
    })


def test_schedule_versions_are_effective_date_resolved_and_previous_snapshot_is_retained():
    original = deepcopy(store.shift_schedule_versions[0])
    saved = _next_version("2026-11-12")
    assert saved.status_code == 201
    assert saved.json()["id"] == 2
    assert saved.json()["shifts"][0]["id"] == 1
    assert store.shift_schedule_versions[0] == original

    before = client.get("/api/shift-schedule", params={"production_date": "2026-11-11"}).json()
    on_effective_date = client.get("/api/shift-schedule", params={"production_date": "2026-11-12"}).json()
    assert before["applicable_version_id"] == 1
    assert on_effective_date["applicable_version_id"] == 2
    assert before["schedule_versions"][0]["effective_to_exclusive"] == "2026-11-12"
    assert on_effective_date["applicable_version"]["effective_from"] == "2026-11-12"


def test_schedule_versions_reject_backdating_and_invalid_effective_dates():
    assert _next_version("2025-12-31").status_code == 409
    assert _next_version("2026-01-01").status_code == 409
    assert _next_version("2026-11-10").status_code == 409
    assert _next_version("not-a-date").status_code == 422


def test_mock_production_save_is_rejected_without_fallback():
    response = client.post("/api/production/save", json={
        "lot_id": 501,
        "production_at": "2026-11-10T08:15:00+07:00",
        "actual_drops": 100,
        "wet_good_pieces": 80,
        "production_date": "2026-11-10",
        "shift_schedule_version_id": 1,
        "operator_id": "test-operator",
        "operator_confirmed": True,
    })
    assert response.status_code == 503
    assert "no mock write was made" in response.json()["detail"]

    stale = client.post("/api/production/save", json={
        "lot_id": 501,
        "production_at": "2026-11-10T08:15:00+07:00",
        "actual_drops": 100,
        "wet_good_pieces": 80,
        "production_date": "2026-11-10",
        "shift_schedule_version_id": 999,
        "operator_id": "test-operator",
        "operator_confirmed": True,
    })
    assert stale.status_code == 503


def test_provisional_draft_is_version_linked_and_mismatch_requires_explicit_review():
    assert _next_version("2026-11-12").status_code == 201
    draft = client.post("/api/auto-lot/drafts", json={
        "production_date": "2026-11-20",
        "schedule_version_id": 2,
        "shift_id": 1,
        "started_at": "2026-11-20T08:30:00+07:00",
        "ended_at": "2026-11-20T09:30:00+07:00",
        "raw_drop_count": 42,
    })
    assert draft.status_code == 201
    draft_row = draft.json()
    assert draft_row["status"].startswith("PROVISIONAL")
    assert draft_row["official_lot_id"] is None

    # A newer version begins before the future draft date. The draft keeps its original version until reviewed.
    third = client.post("/api/shift-schedule/versions", json={
        "effective_from": "2026-11-14",
        "reviewed_through_date": "2026-11-10",
        "base_version_id": 2,
        "change_reason": "New version reviewed",
        "shifts": [
            {"id": 1, "shift_name": "Day crew", "shift_code": "D", "start_time": "08:00", "end_time": "19:00", "display_order": 1, "active": True},
            {"id": 2, "shift_name": "Night crew", "shift_code": "N", "start_time": "19:00", "end_time": "06:00", "display_order": 2, "active": True},
        ],
    })
    assert third.status_code == 201
    listed = client.get("/api/auto-lot/drafts", params={"production_date": "2026-11-20"}).json()
    assert listed["applicable_schedule_version_id"] == 3
    assert listed["drafts"][0]["schedule_version_id"] == 2
    assert listed["drafts"][0]["requires_schedule_review"] is True

    reviewed = client.post(f"/api/auto-lot/drafts/{draft_row['id']}/review", json={
        "schedule_version_id": 3,
        "shift_id": 1,
        "started_at": "2026-11-20T08:35:00+07:00",
        "ended_at": "2026-11-20T09:30:00+07:00",
        "operator_confirmed_drop_count": 40,
        "reason": "Reviewed against changed schedule",
    })
    assert reviewed.status_code == 200
    assert reviewed.json()["schedule_version_id"] == 3
    assert reviewed.json()["raw_drop_count"] == 42
    assert reviewed.json()["operator_confirmed_drop_count"] == 40
    assert reviewed.json()["audit_history"][0]["schedule_version_id"] == 2
    assert reviewed.json()["official_lot_id"] is None


def test_stale_schedule_editor_must_reload_latest_version():
    payload = {
        "effective_from": "2026-11-12",
        "reviewed_through_date": "2026-11-10",
        "base_version_id": 1,
        "change_reason": "Concurrent editor test",
        "shifts": [
            {"id": 1, "shift_name": "Day crew", "shift_code": "D", "start_time": "08:00", "end_time": "19:00", "display_order": 1, "active": True},
            {"id": 2, "shift_name": "Night crew", "shift_code": "N", "start_time": "19:00", "end_time": "06:00", "display_order": 2, "active": True},
        ],
    }
    assert client.post("/api/shift-schedule/versions", json=payload).status_code == 201
    stale = {**payload, "effective_from": "2026-11-13"}
    response = client.post("/api/shift-schedule/versions", json=stale)
    assert response.status_code == 409


def test_draft_interval_must_fit_selected_shift_and_overnight_is_production_date_anchored():
    gap = client.post("/api/auto-lot/drafts", json={
        "production_date": "2026-11-10",
        "schedule_version_id": 1,
        "shift_id": 1,
        "started_at": "2026-11-10T07:00:00",
        "raw_drop_count": 12,
    })
    assert gap.status_code == 422

    crossing = client.post("/api/auto-lot/drafts", json={
        "production_date": "2026-11-10",
        "schedule_version_id": 1,
        "shift_id": 1,
        "started_at": "2026-11-10T18:30:00",
        "ended_at": "2026-11-10T19:30:00",
        "raw_drop_count": 12,
    })
    assert crossing.status_code == 422

    overnight = client.post("/api/auto-lot/drafts", json={
        "production_date": "2026-11-10",
        "schedule_version_id": 1,
        "shift_id": 2,
        "started_at": "2026-11-11T00:30:00",
        "ended_at": "2026-11-11T01:30:00",
        "raw_drop_count": 12,
    })
    assert overnight.status_code == 201
    assert overnight.json()["production_date"] == "2026-11-10"


def test_dismissed_draft_is_audited_and_never_becomes_an_official_lot():
    draft = client.post("/api/auto-lot/drafts", json={
        "production_date": "2026-11-10",
        "schedule_version_id": 1,
        "shift_id": 1,
        "started_at": "2026-11-10T08:30:00",
        "raw_drop_count": 12,
    }).json()
    dismissed = client.post(f"/api/auto-lot/drafts/{draft['id']}/dismiss", json={"reason": "Invalid mock candidate"})
    assert dismissed.status_code == 200
    assert dismissed.json()["status"].startswith("DISMISSED")
    assert dismissed.json()["official_lot_id"] is None
    assert dismissed.json()["audit_history"][0]["reason"] == "Invalid mock candidate"
    assert dismissed.json()["raw_drop_count"] == 12


def test_shift_schedule_does_not_activate_illustrative_three_shift_example_by_default():
    response = client.get("/api/shift-schedule", params={"production_date": "2026-11-08"})
    assert response.status_code == 200
    shifts = response.json()["applicable_version"]["shifts"]
    assert len(shifts) == 2
    assert [(item["start_time"], item["end_time"]) for item in shifts] == [("08:00", "19:00"), ("19:00", "06:00")]
