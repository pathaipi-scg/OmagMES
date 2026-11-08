from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .autocal import preview_autocal
from .models import LifecycleSave, LotCreate, LotRename, MouldTransition, ProductionSave, WetRejectSave, WetRunEventSave
from .store import store

app = FastAPI(title="OmagMES Factory Review Prototype", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {"status": "ok", "mode": "mock-only", "database_connected": False}


@app.get("/api/bootstrap")
def bootstrap() -> dict[str, Any]:
    return store.snapshot()


@app.get("/api/autocal/preview")
def autocal_preview() -> dict[str, Any]:
    return preview_autocal()


def require_lot(lot_id: int) -> dict[str, Any]:
    lot = next((item for item in store.lots if item["id"] == lot_id), None)
    if lot is None:
        raise HTTPException(status_code=404, detail="Lot ID was not found in mock data")
    return lot


@app.post("/api/production/save", status_code=201)
def save_production(payload: ProductionSave) -> dict[str, Any]:
    require_lot(payload.lot_id)
    record = {
        "id": store.next_id(),
        "lot_id": payload.lot_id,
        "actual_drops": payload.actual_drops,
        "wet_good_pieces": payload.wet_good_pieces,
        "operator_note": payload.operator_note,
        "saved_at": datetime.now().astimezone().isoformat(),
        "mode": "MOCK SAVED",
    }
    return store.save(store.production_entries, record)


@app.post("/api/wet-reject/save", status_code=201)
def save_wet_reject(payload: WetRejectSave) -> dict[str, Any]:
    require_lot(payload.lot_id)
    allowed = {item["code"] for item in store.reject_reasons}
    unknown = sorted(set(payload.quantities) - allowed)
    if unknown:
        raise HTTPException(status_code=422, detail=f"Unknown mock reject reason(s): {', '.join(unknown)}")
    if any(value < 0 for value in payload.quantities.values()):
        raise HTTPException(status_code=422, detail="Reject quantities cannot be negative")
    record = {
        "id": store.next_id(),
        "lot_id": payload.lot_id,
        "quantities": dict(payload.quantities),
        "total": sum(payload.quantities.values()),
        "operator_note": payload.operator_note,
        "saved_at": datetime.now().astimezone().isoformat(),
        "mode": "MOCK SAVED",
    }
    return store.save(store.reject_entries, record)


@app.post("/api/wet-run-log/events", status_code=201)
def save_wet_run_event(payload: WetRunEventSave) -> dict[str, Any]:
    if payload.ended_at is not None and payload.ended_at < payload.started_at:
        raise HTTPException(status_code=422, detail="Event end must be at or after start")
    record = {
        "id": store.next_id(),
        "category": payload.category,
        "started_at": payload.started_at.isoformat(),
        "ended_at": payload.ended_at.isoformat() if payload.ended_at else None,
        "note": payload.note,
        "source": "MANUAL OPERATOR ENTRY",
        "saved_at": datetime.now().astimezone().isoformat(),
        "mode": "MOCK SAVED",
    }
    return store.save(store.run_events, record)


@app.get("/api/wet-oee/preview")
def wet_oee_preview() -> dict[str, Any]:
    return {
        "mode": "SIMULATED — not production data",
        "window": "08 Nov 2026 · 07:00–15:00 Asia/Bangkok",
        "availability": 0.92,
        "performance": 0.88,
        "quality": 0.975,
        "oee": round(0.92 * 0.88 * 0.975, 4),
        "actual_drops": 820,
        "wet_good_pieces": 742,
        "standard_status": "DEMO ONLY — no approved Product standard loaded",
        "notes": [
            "Values are illustrative and are not calculated from live sources.",
            "Dry Line / Depallet time is excluded.",
            "Production standards and source attribution require owner approval before operational use.",
        ],
    }


def save_lifecycle(collection: list[dict[str, Any]], payload: LifecycleSave) -> dict[str, Any]:
    require_lot(payload.lot_id)
    record = {
        "id": store.next_id(),
        "lot_id": payload.lot_id,
        "quantity": payload.quantity,
        "note": payload.note,
        "saved_at": datetime.now().astimezone().isoformat(),
        "mode": "MOCK SAVED — quantity/unit semantics need owner review",
    }
    return store.save(collection, record)


@app.post("/api/curing/entries", status_code=201)
def save_curing(payload: LifecycleSave) -> dict[str, Any]:
    return save_lifecycle(store.curing_entries, payload)


@app.post("/api/depallet/events", status_code=201)
def save_depal(payload: LifecycleSave) -> dict[str, Any]:
    return save_lifecycle(store.depal_entries, payload)


@app.post("/api/lots", status_code=201)
def create_lot(payload: LotCreate) -> dict[str, Any]:
    product = next((item for item in store.products if item["id"] == payload.product_id), None)
    if product is None:
        raise HTTPException(status_code=404, detail="Product ID was not found in mock data")
    if not payload.lot_name.strip():
        raise HTTPException(status_code=422, detail="Lot name is required")
    previous = require_lot(payload.previous_lot_id)
    if payload.transition == "COLOR_CHANGE" and previous["product_id"] != payload.product_id:
        raise HTTPException(status_code=422, detail="A Color change keeps the Product and Run unchanged")
    record = {
        "id": store.next_id(),
        "run_id": previous["run_id"] if payload.transition == "COLOR_CHANGE" else store.next_id(),
        "product_id": payload.product_id,
        "color": payload.color,
        "lot_name": payload.lot_name.strip(),
        "started_at": datetime.now().astimezone().isoformat(),
        "mode": "MOCK ONLY — no production database write",
        "transition": payload.transition,
    }
    store.lots.append(record)
    return record


@app.post("/api/lots/{lot_id}/rename")
def rename_lot(lot_id: int, payload: LotRename) -> dict[str, Any]:
    lot = require_lot(lot_id)
    new_name = payload.new_name.strip()
    reason = payload.reason.strip()
    if not new_name or not reason:
        raise HTTPException(status_code=422, detail="New LotName and change reason are required")
    if new_name == lot["lot_name"]:
        raise HTTPException(status_code=422, detail="New LotName must differ from the current name")
    history = {
        "id": store.next_id(),
        "lot_id": lot_id,
        "old_name": lot["lot_name"],
        "new_name": new_name,
        "actor": "DEMO-OPERATOR",
        "changed_at": datetime.now().astimezone().isoformat(),
        "reason": reason,
    }
    store.lot_name_history.append(history)
    lot["lot_name"] = new_name
    return {"lot": lot, "history": history, "mode": "MOCK ONLY"}


@app.post("/api/moulds/{mould_id}/transition")
def transition_mould(mould_id: int, payload: MouldTransition) -> dict[str, Any]:
    mould = next((item for item in store.moulds if item["id"] == mould_id), None)
    if mould is None:
        raise HTTPException(status_code=404, detail="Mould ID was not found in mock data")
    reason = payload.reason.strip()
    if not reason:
        raise HTTPException(status_code=422, detail="A reason is required")
    if payload.action == "SEND_TO_RECONDITION":
        if mould["status"] != "ACTIVE":
            raise HTTPException(status_code=409, detail="Only an active Mould can be sent to recondition")
        mould["status"] = "RECONDITION"
    else:
        if mould["status"] != "RECONDITION":
            raise HTTPException(status_code=409, detail="Only a Mould in recondition can have an approved return")
        mould["status"] = "ACTIVE"
        mould["current_age_drops"] = 0
        mould["recondition_cycle"] += 1
    history = {
        "id": store.next_id(),
        "mould_id": mould_id,
        "action": payload.action,
        "actor": "DEMO-APPROVER",
        "changed_at": datetime.now().astimezone().isoformat(),
        "reason": reason,
        "current_age_drops": mould["current_age_drops"],
        "lifetime_age_drops": mould["lifetime_age_drops"],
    }
    store.mould_history.append(history)
    return {"mould": mould, "history": history, "mode": "MOCK ONLY"}
