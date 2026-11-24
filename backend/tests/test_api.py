from dataclasses import replace
from datetime import datetime

from fastapi.testclient import TestClient

from backend.app import main
from backend.app.main import app
from backend.app.main import normalize_operator_lot_time
from backend.app.sql_source import SQLServerReadOnlyRepository
from backend.app.store import store
from backend.app.shift_schedule import initial_schedule_versions

client = TestClient(app, client=("127.0.0.1", 50000))
main.source_repository = SQLServerReadOnlyRepository(replace(main.source_repository.settings, mode="MOCK"))


def setup_function() -> None:
    store.shift_schedule_versions[:] = initial_schedule_versions()
    store.auto_lot_drafts.clear()
    store._next_shift_id = 2
    store._next_schedule_version_id = 1
    store.lots[:] = [
        {"id": 501, "run_id": 101, "product_id": 1, "color": "Grey", "lot_name": "DEMO-LOT-A", "started_at": "2026-11-08T07:00:00+07:00", "is_open": True},
        {"id": 502, "run_id": 102, "product_id": 2, "color": "Natural", "lot_name": "DEMO-LOT-B", "started_at": "2026-11-08T08:30:00+07:00", "is_open": True},
    ]


    store.moulds[:] = [
        {"id": 71, "code": "DEMO-MOULD-01", "product_id": 1, "status": "ACTIVE", "current_age_drops": 18420, "lifetime_age_drops": 126550, "recondition_cycle": 0},
        {"id": 72, "code": "DEMO-MOULD-02", "product_id": 2, "status": "RECONDITION", "current_age_drops": 3250, "lifetime_age_drops": 88400, "recondition_cycle": 1},
    ]
    store.mould_history.clear()
    store.production_entries.clear()
    store.reject_entries.clear()
    store.run_events[:] = [
        {"id": 1, "category": "RUNNING", "started_at": "2026-11-08T07:00:00+07:00", "ended_at": None, "note": "Operator-confirmed demo interval"}
    ]


def test_operator_lot_time_normalization_preserves_local_date_and_minute() -> None:
    normalized = normalize_operator_lot_time(datetime.fromisoformat("2026-11-17T17:05:48.123456+00:00"))
    assert normalized.isoformat() == "2026-11-18T00:05:00+07:00"

    naive_local = normalize_operator_lot_time(datetime(2026, 11, 17, 23, 59, 59, 999999))
    assert naive_local == datetime(2026, 11, 17, 23, 59)


def test_health_is_mock_only_and_not_connected_to_database() -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["mode"] == "MOCK"
    assert response.json()["application_port"] == 3001
    assert response.json()["database_connected"] is None


def test_server_rendered_pages_render_but_fail_closed_without_live_sql() -> None:
    production = client.get("/")
    edit_log = client.get("/edit-log")

    assert production.status_code == edit_log.status_code == 503
    assert "text/html" in production.headers["content-type"]
    assert "Production SQL is unavailable" in production.text
    assert "No mock records are displayed or written" in production.text
    assert "Edit Log" in edit_log.text
    assert "Production records and their audit history are separate" in edit_log.text
    assert "Mock data and mock SAVE paths are disabled" in edit_log.text


def test_edit_log_loads_read_only_pis_when_production_schema_is_not_ready(monkeypatch) -> None:
    context = {
        "page_title": "Edit Log", "active_page": "edit-log", "runtime_label": "LIVE SQL · OMAG_MES",
        "production_date": "2026-11-17", "connected": True,
        "writes_enabled": False, "connection_error": "", "schema_error": "Migration 007 missing",
        "error": "", "success": "", "products": [], "lots": [], "entries": [
            {"id": 8001, "lot_id": 501, "production_at": "2026-11-17T10:00:00+07:00",
             "production_date": "2026-11-17", "shift_id": 1, "actual_drops": 5,
             "wet_good_pieces": 12, "entered_by": "test-operator"},
        ], "reject_reasons": [], "moulds": [], "plans": [], "plans_error": "",
        "plans_truncated": False, "plan_limit": 1000, "audit_by_entry": {},
        "press_total": None, "press_error": "", "schedule_version_id": 1,
        "default_time": "2026-11-17T10:00",
    }
    plan = {"plan_name": "IT plan", "material_code": "TEST-01", "planned_start": "2026-11-17",
            "shift": "1", "plan_count": 5, "duplicate_count": 1,
            "snapshot": {"OperationCode": "IT-OP"}}
    monkeypatch.setattr(main, "_web_status_context", lambda *_args, **_kwargs: dict(context))
    monkeypatch.setattr(main.source_repository, "production_plan_snapshots", lambda: {
        "plans": [plan], "truncated": False, "limit": 1000,
    })

    response = client.get("/edit-log?production_date=2026-11-17")

    assert response.status_code == 200
    assert "IT plan" in response.text
    assert "8001" in response.text
    assert "Refreshing PIS never writes or replaces a Production Entry" in response.text


def test_jinja_operational_post_routes_fail_closed_without_live_sql() -> None:
    form_client = TestClient(app, follow_redirects=False)
    original_settings = main.production_repository.settings
    main.production_repository.settings = replace(original_settings, mode="MOCK")
    original_state = {
        "production": list(store.production_entries), "reject": list(store.reject_entries),
        "curing": list(store.curing_entries), "depal": list(store.depal_entries),
        "lots": [dict(item) for item in store.lots],
    }
    try:
        responses = [
            form_client.post("/web/production/save", data={
                "lot_id": 501, "production_date": "2026-11-17", "schedule_version_id": 1,
                "production_at": "2026-11-17T10:00", "actual_drops": 10,
                "wet_good_pieces": 20, "operator_id": "unverified", "operator_confirmed": "yes",
            }),
            form_client.post("/web/production/1/edit", data={
                "production_date": "2026-11-17", "actual_drops": 11,
                "wet_good_pieces": 21, "operator_id": "unverified", "reason": "test",
                "operator_confirmed": "yes",
            }),
            form_client.post("/web/production/1/delete", data={
                "production_date": "2026-11-17", "operator_id": "unverified",
                "reason": "test", "operator_confirmed": "yes",
            }),
            form_client.post("/web/curing/save", data={
                "production_date": "2026-11-17", "lot_id": 501, "quantity": 1,
                "unit_code": "pcs", "operator_id": "unverified", "operator_confirmed": "yes",
            }),
            form_client.post("/web/reject/save", data={
                "production_date": "2026-11-17", "lot_id": 501,
                "operator_id": "unverified", "reason_1": 1,
            }),
            form_client.post("/web/lots/create", data={
                "production_date": "2026-11-17", "schedule_version_id": 1,
                "product_id": 1, "color": "Grey", "lot_name": "IT-NOT-SAVED",
                "started_at": "2026-11-17T10:00", "operator_id": "unverified",
            }),
            form_client.post("/web/lots/501/rename", data={
                "production_date": "2026-11-17", "new_name": "IT-NOT-RENAMED",
                "operator_id": "unverified", "reason": "test",
            }),
        ]
    finally:
        main.production_repository.settings = original_settings

    assert all(response.status_code == 303 for response in responses), [
        (response.status_code, response.headers.get("location"), response.text[:200])
        for response in responses
    ]
    assert all("error=" in response.headers["location"] for response in responses)
    assert store.production_entries == original_state["production"]
    assert store.reject_entries == original_state["reject"]
    assert store.curing_entries == original_state["curing"]
    assert store.depal_entries == original_state["depal"]
    assert store.lots == original_state["lots"]


def test_autocal_is_a_suggestion_until_explicit_save() -> None:
    preview = client.get("/api/autocal/preview").json()
    assert preview["suggested_actual_drops"] == 820
    assert preview["suggested_wet_rejects"] == {"cntR1": 12, "cntR2": 7, "cntR3": 3}
    assert "CYC" in {item["tag"] for item in preview["raw_observations"]}
    assert len(store.production_entries) == 0


def test_operator_cannot_save_production_to_process_local_mock_storage() -> None:
    suggestion = client.get("/api/autocal/preview")
    assert suggestion.status_code == 200
    assert suggestion.json()["suggested_actual_drops"] == 820
    response = client.post("/api/production/save", json={"lot_id": 501, "actual_drops": 777, "wet_good_pieces": 701, "operator_note": "Reviewed override", "operator_id": "test-operator", "operator_confirmed": True})
    assert response.status_code == 503
    assert "no mock write was made" in response.json()["detail"]
    assert len(store.production_entries) == 0


def test_production_entry_keeps_original_lot_and_actual_occurrence_shift_date_time() -> None:
    response = client.post("/api/production/save", json={
        "lot_id": 501, "production_at": "2026-11-11T20:15:00+07:00",
        "actual_drops": 15, "wet_good_pieces": 45, "operator_id": "test-operator",
        "operator_confirmed": True,
    })

    assert response.status_code == 503
    assert "no mock write was made" in response.json()["detail"]
    assert store.production_entries == []


def test_wet_reject_requires_database_reason_ids_and_never_saves_to_mock() -> None:
    response = client.post("/api/wet-reject/save", json={
        "lot_id": 501, "quantities": {1: 3, 3: 2}, "operator_id": "test-operator",
    })
    assert response.status_code == 503
    assert "no mock write was made" in response.json()["detail"]
    assert store.reject_entries == []

    bad = client.post("/api/wet-reject/save", json={
        "lot_id": 501, "quantities": {"R1": 1}, "operator_id": "test-operator",
    })
    assert bad.status_code == 422


def test_wet_run_log_without_sql_persistence_never_writes_mock_state() -> None:
    response = client.post("/api/wet-run-log/events", json={"category": "BREAKDOWN", "started_at": "2026-11-08T09:00:00+07:00", "ended_at": "2026-11-08T09:30:00+07:00", "note": "Operator classification"})
    assert response.status_code == 503
    assert "no mock write was made" in response.json()["detail"]
    assert store.run_events == [
        {"id": 1, "category": "RUNNING", "started_at": "2026-11-08T07:00:00+07:00", "ended_at": None, "note": "Operator-confirmed demo interval"},
    ]


def test_oee_is_labeled_as_simulated() -> None:
    result = client.get("/api/wet-oee/preview").json()
    assert result["mode"].startswith("SIMULATED")
    assert result["standard_status"].startswith("DEMO ONLY")
    assert 0 < result["oee"] < 1


def test_lifecycle_records_keep_the_original_lot_id() -> None:
    original_depal_entries = list(store.depal_entries)
    curing = client.post("/api/curing/entries", json={"lot_id": 501, "quantity": 0, "note": "Mock event"})
    depal = client.post("/api/depallet/events", json={"lot_id": 501, "quantity": 0, "note": "Mock event"})
    assert curing.status_code == depal.status_code == 503
    assert all("no mock write was made" in response.json()["detail"] for response in (curing, depal))
    assert store.depal_entries == original_depal_entries


def test_lot_name_can_repeat_because_identity_is_the_id() -> None:
    payload = {"product_id": 1, "previous_lot_id": 501, "transition": "COLOR_CHANGE", "color": "Red", "lot_name": "SAME-NAME"}
    first = client.post("/api/lots", json=payload)
    second = client.post("/api/lots", json={**payload, "color": "Blue"})
    assert first.status_code == second.status_code == 503
    assert "no mock Lot was created" in first.json()["detail"]
    assert [item["id"] for item in store.lots] == [501, 502]


def test_same_product_and_color_continues_original_lot_across_shift_and_production_date() -> None:
    original = next(item for item in store.lots if item["id"] == 501)
    original_start = original["started_at"]
    continuation = client.post("/api/lots", json={
        "product_id": 1, "previous_lot_id": 501, "transition": "PRODUCT_CHANGE",
        "color": "Grey", "lot_name": "ignored-for-continuation",
        "started_at": "2026-11-11T20:00:00+07:00", "production_date": "2026-11-11",
    })

    assert continuation.status_code == 503
    assert "no mock Lot was created" in continuation.json()["detail"]
    assert original["started_at"] == original_start
    assert len([item for item in store.lots if item["id"] == 501]) == 1


def test_product_change_starts_a_new_run_independent_of_requested_transition_label() -> None:
    new_run = client.post("/api/lots", json={"product_id": 2, "previous_lot_id": 501, "transition": "PRODUCT_CHANGE", "color": "Natural", "lot_name": "RETURN-TO-B"})
    assert new_run.status_code == 503
    assert "no mock Lot was created" in new_run.json()["detail"]
    assert [item["id"] for item in store.lots] == [501, 502]


def test_lot_rename_keeps_id_and_records_actor_reason_history() -> None:
    response = client.post("/api/lots/501/rename", json={"new_name": "RENAMED-DEMO", "reason": "Factory review correction"})
    assert response.status_code == 503
    assert "no mock rename was made" in response.json()["detail"]
    assert store.lots[0]["lot_name"] == "DEMO-LOT-A"


def test_mould_transition_without_sql_persistence_never_mutates_mock_master() -> None:
    response = client.post("/api/moulds/72/transition", json={"action": "APPROVE_RETURN", "reason": "Demo approved return"})
    assert response.status_code == 503
    assert "no mock write was made" in response.json()["detail"]
    assert next(item for item in store.moulds if item["id"] == 72)["current_age_drops"] == 3250
    assert store.mould_history == []


def test_live_mode_rejects_routes_without_sql_persistence() -> None:
    original_repository = main.source_repository
    main.source_repository = SQLServerReadOnlyRepository(replace(original_repository.settings, mode="LIVE_READ_ONLY"))
    try:
        wet_run = client.post("/api/wet-run-log/events", json={"category": "BREAKDOWN", "started_at": "2026-11-08T09:00:00+07:00"})
        mould = client.post("/api/moulds/71/transition", json={"action": "SEND_TO_RECONDITION", "reason": "not persisted"})
    finally:
        main.source_repository = original_repository

    assert wet_run.status_code == mould.status_code == 503
    assert all("no mock write was made" in response.json()["detail"] for response in (wet_run, mould))
