from __future__ import annotations

import inspect
import re
from pathlib import Path

import backend.app.main as main_module
from backend.app.production_plans import PLAN_VIEW_COLUMNS, aggregate_plan_rows, plan_snapshot
from backend.app.sql_source import SourceUnavailable
from backend.app.store import store
from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[2]
SQL = ROOT / "db" / "review-only"


def test_candidate_get_route_is_read_only_and_sync_is_explicit() -> None:
    source = inspect.getsource(main_module.list_auto_lot_candidates)
    assert "sync_auto_lot" not in source
    sync_source = inspect.getsource(main_module.sync_auto_lot_candidates)
    assert "sync_auto_lot_detected_windows" in sync_source
    assert "post" in main_module.app.openapi()["paths"]["/api/auto-lot/candidates/sync"]


def test_migration_006_reuses_candidate_tables_and_audits_full_states() -> None:
    forward = (SQL / "006_autolot_plan_audit_view.sql").read_text(encoding="utf-8")
    assert "CREATE TABLE omagmes.AutoLotCandidateWindow" not in forward
    assert "CREATE TABLE omagmes.AutoLotCandidateWindowHistory" not in forward
    assert "PreviousStateJson nvarchar(max)" in forward
    assert "NewStateJson nvarchar(max)" in forward
    assert "OperatorBoundaryConfirmed bit NOT NULL" in forward
    assert "CandidateKind IN ('RESET','AUTO','MANUAL','SPLIT')" in forward
    assert "autolot:dropcnt-reset:" in forward
    assert "WHERE b.BoundaryEvidence = 'COUNTER_DECREASE'" in forward
    legacy_dml = re.compile(r"\b(?:INSERT\s+INTO|UPDATE|DELETE\s+FROM)\s+(?:OMAG\.)?DBO\.PRESS\b", re.IGNORECASE)
    assert legacy_dml.search(forward) is None


def test_rollback_refuses_any_new_candidate_or_operator_audit_state() -> None:
    rollback = (SQL / "006_rollback.sql").read_text(encoding="utf-8")
    assert "CandidateKind='AUTO'" in rollback
    assert "OperatorBoundaryConfirmed=1" in rollback
    assert "CREATE_AUTO" in rollback and "PLAN_ASSIGN" in rollback and "SOFT_DELETE" in rollback
    assert "DROP TABLE" not in rollback
    legacy_dml = re.compile(r"\b(?:INSERT\s+INTO|UPDATE|DELETE\s+FROM)\s+(?:OMAG\.)?DBO\.PRESS\b", re.IGNORECASE)
    assert legacy_dml.search(rollback) is None


def test_plan_fingerprints_are_deterministic_and_duplicate_rows_are_ambiguous() -> None:
    row = {column: None for column in PLAN_VIEW_COLUMNS}
    row.update({"MaterialCode": "P-001", "PlanName": "Test", "StartTime": "2026-11-17T08:00:00"})
    first = plan_snapshot(row)
    second = plan_snapshot(dict(reversed(list(row.items()))))
    assert first["plan_key"] == second["plan_key"]
    plans = aggregate_plan_rows([row, row])
    assert len(plans) == 1
    assert plans[0]["duplicate_count"] == 2
    assert plans[0]["identity_kind"] == "CONTENT_FINGERPRINT_NOT_SOURCE_ID"


def test_plan_endpoint_reports_source_outage_without_touching_saved_entries(monkeypatch) -> None:
    before = [dict(entry) for entry in store.production_entries]

    def unavailable(_limit: int = 1000, _production_date: str | None = None):
        raise SourceUnavailable("Linked plan source is temporarily unavailable.")

    monkeypatch.setattr(main_module.source_repository, "production_plan_snapshots", unavailable)
    response = TestClient(main_module.app).get("/api/press-lots/plans")

    assert response.status_code == 503
    assert response.json()["detail"] == "Linked plan source is temporarily unavailable."
    assert store.production_entries == before


def test_plan_endpoint_converts_driver_errors_to_safe_service_unavailable(monkeypatch) -> None:
    def driver_error(_limit: int = 1000, _production_date: str | None = None):
        raise RuntimeError("remote login mapping details")

    monkeypatch.setattr(main_module.source_repository, "production_plan_snapshots", driver_error)
    response = TestClient(main_module.app).get("/api/press-lots/plans")

    assert response.status_code == 503
    assert response.json()["detail"] == "SQL source query failed (RuntimeError)."
    assert "remote login mapping details" not in response.text


def test_assignment_route_resolves_current_plan_and_saves_only_valid_mould(monkeypatch) -> None:
    plan_row = {column: None for column in PLAN_VIEW_COLUMNS}
    plan_row.update({"PlanName": "Plan A", "MaterialCode": "P-001", "MaterialName": "Product One"})
    plan = aggregate_plan_rows([plan_row])[0]
    mapped = {**plan, "product_match": {"status": "MATCHED", "product_id": 21}}
    saved: list[tuple[int, dict | None, int | None]] = []

    monkeypatch.setattr(main_module.auto_lot_repository, "production_date_for", lambda lot_id: "2026-11-18")
    monkeypatch.setattr(main_module.source_repository, "production_plan_snapshots", lambda *_args: {
        "plans": [plan], "truncated": False,
    })
    monkeypatch.setattr(main_module.auto_lot_repository, "plans_with_product_matches", lambda _plans: [mapped])
    monkeypatch.setattr(main_module.auto_lot_repository, "save_assignment", lambda lot_id, chosen_plan, mould_id: (
        saved.append((lot_id, chosen_plan, mould_id)) or {"auto_lot_id": lot_id}
    ))

    response = TestClient(main_module.app).post(
        "/api/auto-lots/77/assignment",
        json={"plan_key": plan["plan_key"], "mould_id": 9},
    )

    assert response.status_code == 200
    assert response.json() == {"auto_lot_id": 77}
    assert saved == [(77, plan, 9)]


def test_assignment_route_blocks_missing_product_match_before_save(monkeypatch) -> None:
    plan_row = {column: None for column in PLAN_VIEW_COLUMNS}
    plan_row.update({"PlanName": "Plan A", "MaterialCode": "MISSING"})
    plan = aggregate_plan_rows([plan_row])[0]
    monkeypatch.setattr(main_module.auto_lot_repository, "production_date_for", lambda _lot_id: "2026-11-18")
    monkeypatch.setattr(main_module.source_repository, "production_plan_snapshots", lambda *_args: {
        "plans": [plan], "truncated": False,
    })
    monkeypatch.setattr(main_module.auto_lot_repository, "plans_with_product_matches", lambda _plans: [{
        **plan, "product_match": {"status": "PRODUCT NOT FOUND"},
    }])
    monkeypatch.setattr(main_module.auto_lot_repository, "save_assignment", lambda *_args: (_ for _ in ()).throw(AssertionError("must not save")))

    response = TestClient(main_module.app).post(
        "/api/auto-lots/77/assignment",
        json={"plan_key": plan["plan_key"], "mould_id": 9},
    )

    assert response.status_code == 422
    assert "PRODUCT NOT FOUND" in response.json()["detail"]
