from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.store import store

client = TestClient(app)


def setup_function() -> None:
    store.lots[:] = [
        {"id": 501, "run_id": 101, "product_id": 1, "color": "Grey", "lot_name": "DEMO-LOT-A", "started_at": "2026-11-08T07:00:00+07:00"},
        {"id": 502, "run_id": 102, "product_id": 2, "color": "Natural", "lot_name": "DEMO-LOT-B", "started_at": "2026-11-08T08:30:00+07:00"},
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


def test_health_is_mock_only_and_not_connected_to_database() -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "mode": "mock-only", "database_connected": False}


def test_autocal_is_a_suggestion_until_explicit_save() -> None:
    preview = client.get("/api/autocal/preview").json()
    assert preview["suggested_actual_drops"] == 820
    assert preview["suggested_wet_rejects"] == {"cntR1": 12, "cntR2": 7, "cntR3": 3}
    assert "CYC" in {item["tag"] for item in preview["raw_observations"]}
    assert len(store.production_entries) == 0


def test_operator_can_edit_autocal_values_before_explicit_save() -> None:
    response = client.post("/api/production/save", json={"lot_id": 501, "actual_drops": 777, "wet_good_pieces": 701, "operator_note": "Reviewed override"})
    assert response.status_code == 201
    assert response.json()["actual_drops"] == 777
    assert response.json()["wet_good_pieces"] == 701
    assert len(store.production_entries) == 1


def test_wet_reject_accepts_dynamic_counter_ids_and_rejects_button_states() -> None:
    ok = client.post("/api/wet-reject/save", json={"lot_id": 501, "quantities": {"cntR1": 3, "cntR3": 2}})
    assert ok.status_code == 201
    assert ok.json()["total"] == 5
    bad = client.post("/api/wet-reject/save", json={"lot_id": 501, "quantities": {"R1": 1}})
    assert bad.status_code == 422


def test_run_log_is_manual_and_not_derived_from_autorun() -> None:
    response = client.post("/api/wet-run-log/events", json={"category": "BREAKDOWN", "started_at": "2026-11-08T09:00:00+07:00", "ended_at": "2026-11-08T09:30:00+07:00", "note": "Operator classification"})
    assert response.status_code == 201
    assert response.json()["source"] == "MANUAL OPERATOR ENTRY"
    assert response.json()["category"] == "BREAKDOWN"


def test_oee_is_labeled_as_simulated() -> None:
    result = client.get("/api/wet-oee/preview").json()
    assert result["mode"].startswith("SIMULATED")
    assert result["standard_status"].startswith("DEMO ONLY")
    assert 0 < result["oee"] < 1


def test_lifecycle_records_keep_the_original_lot_id() -> None:
    curing = client.post("/api/curing/entries", json={"lot_id": 501, "quantity": 0, "note": "Mock event"})
    depal = client.post("/api/depallet/events", json={"lot_id": 501, "quantity": 0, "note": "Mock event"})
    assert curing.status_code == depal.status_code == 201
    assert curing.json()["lot_id"] == depal.json()["lot_id"] == 501


def test_lot_name_can_repeat_because_identity_is_the_id() -> None:
    payload = {"product_id": 1, "previous_lot_id": 501, "transition": "COLOR_CHANGE", "color": "Grey", "lot_name": "SAME-NAME"}
    first = client.post("/api/lots", json=payload)
    second = client.post("/api/lots", json=payload)
    assert first.status_code == second.status_code == 201
    assert first.json()["id"] != second.json()["id"]
    assert first.json()["run_id"] == second.json()["run_id"] == 101


def test_product_change_starts_a_new_run_and_color_change_cannot_switch_product() -> None:
    new_run = client.post("/api/lots", json={"product_id": 2, "previous_lot_id": 501, "transition": "PRODUCT_CHANGE", "color": "Natural", "lot_name": "RETURN-TO-B"})
    assert new_run.status_code == 201
    assert new_run.json()["run_id"] != 101
    mismatch = client.post("/api/lots", json={"product_id": 2, "previous_lot_id": 501, "transition": "COLOR_CHANGE", "color": "Natural", "lot_name": "INVALID"})
    assert mismatch.status_code == 422


def test_lot_rename_keeps_id_and_records_actor_reason_history() -> None:
    response = client.post("/api/lots/501/rename", json={"new_name": "RENAMED-DEMO", "reason": "Factory review correction"})
    assert response.status_code == 200
    assert response.json()["lot"]["id"] == 501
    assert response.json()["history"]["old_name"] == "DEMO-LOT-A"
    assert response.json()["history"]["reason"] == "Factory review correction"
    assert store.lots[0]["lot_name"] == "RENAMED-DEMO"


def test_approved_mould_return_resets_current_age_not_lifetime_age() -> None:
    response = client.post("/api/moulds/72/transition", json={"action": "APPROVE_RETURN", "reason": "Demo approved return"})
    assert response.status_code == 200
    mould = response.json()["mould"]
    assert mould["current_age_drops"] == 0
    assert mould["lifetime_age_drops"] == 88400
    assert mould["recondition_cycle"] == 2
    assert response.json()["history"]["reason"] == "Demo approved return"
