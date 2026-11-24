from __future__ import annotations

from datetime import datetime
from threading import RLock
from typing import Any

from .shift_schedule import initial_schedule_versions


class MockStore:
    """Process-local prototype state. This store has no SQL connection or persistence."""

    def __init__(self) -> None:
        self._lock = RLock()
        self.products = [
            {"id": 1, "code": "DEMO-BLOCK-001", "name": "Demo Block — 6 cm", "family": "Block", "standard_pieces_per_drop": None, "standard_cycle_time_sec": None},
            {"id": 2, "code": "DEMO-FENCE-001", "name": "Demo Fence Panel", "family": "Fence", "standard_pieces_per_drop": None, "standard_cycle_time_sec": None},
            {"id": 3, "code": "DEMO-CURB-001", "name": "Demo Curb — Grey", "family": "Block", "standard_pieces_per_drop": None, "standard_cycle_time_sec": None},
        ]
        self.lots = [
            {"id": 501, "run_id": 101, "product_id": 1, "color": "Grey", "lot_name": "DEMO-LOT-A", "started_at": "2026-11-08T07:00:00+07:00", "is_open": True},
            {"id": 502, "run_id": 102, "product_id": 2, "color": "Natural", "lot_name": "DEMO-LOT-B", "started_at": "2026-11-08T08:30:00+07:00", "is_open": True},
        ]
        self.reject_reasons = [
            {"code": "cntR1", "label": "Edge damage"},
            {"code": "cntR2", "label": "Surface defect"},
            {"code": "cntR3", "label": "Dimension / shape"},
        ]
        self.production_entries: list[dict[str, Any]] = []
        self.reject_entries: list[dict[str, Any]] = []
        self.run_events = [
            {"id": 1, "category": "RUNNING", "started_at": "2026-11-08T07:00:00+07:00", "ended_at": None, "note": "Operator-confirmed demo interval"}
        ]
        self.curing_entries = [{"id": 1, "lot_id": 501, "quantity": 0, "note": "Demo only — quantity not inferred"}]
        self.depal_entries = [{"id": 1, "lot_id": 501, "quantity": 0, "note": "Demo only — quantity not inferred"}]
        self.lot_name_history: list[dict[str, Any]] = []
        self.moulds = [
            {"id": 71, "code": "DEMO-MOULD-01", "product_id": 1, "status": "ACTIVE", "current_age_drops": 18420, "lifetime_age_drops": 126550, "recondition_cycle": 0},
            {"id": 72, "code": "DEMO-MOULD-02", "product_id": 2, "status": "RECONDITION", "current_age_drops": 3250, "lifetime_age_drops": 88400, "recondition_cycle": 1},
        ]
        self.mould_history: list[dict[str, Any]] = []
        self.shift_schedule_versions = initial_schedule_versions()
        self.auto_lot_drafts: list[dict[str, Any]] = []
        self.auto_lot_candidate_reviews: list[dict[str, Any]] = []
        self.auto_lot_candidate_snapshots: dict[str, dict[str, Any]] = {}
        self.auto_lot_reset_snapshots: dict[str, dict[str, Any]] = {}
        self._next_id = 1000
        self._next_shift_id = 2
        self._next_schedule_version_id = 1

    def next_id(self) -> int:
        with self._lock:
            self._next_id += 1
            return self._next_id

    def next_shift_id(self) -> int:
        with self._lock:
            self._next_shift_id += 1
            return self._next_shift_id

    def next_schedule_version_id(self) -> int:
        with self._lock:
            self._next_schedule_version_id += 1
            return self._next_schedule_version_id

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "mode": "MOCK ONLY — process-local, reset on restart",
                "products": list(self.products),
                "lots": list(self.lots),
                "reject_reasons": list(self.reject_reasons),
                "production_entries": list(self.production_entries),
                "reject_entries": list(self.reject_entries),
                "run_events": list(self.run_events),
                "curing_entries": list(self.curing_entries),
                "depal_entries": list(self.depal_entries),
                "lot_name_history": list(self.lot_name_history),
                "moulds": list(self.moulds),
                "mould_history": list(self.mould_history),
                "shift_schedule_versions": list(self.shift_schedule_versions),
                "auto_lot_drafts": list(self.auto_lot_drafts),
                "auto_lot_candidate_reviews": list(self.auto_lot_candidate_reviews),
            }

    def save(self, collection: list[dict[str, Any]], record: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            collection.append(record)
        return record


store = MockStore()
