from __future__ import annotations

import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from dotenv import load_dotenv

from .autocal import preview_autocal
from .models import LifecycleSave, LotCreate, LotRename, MouldTransition, ProductionSave, WetRejectSave, WetRunEventSave
from .live_autocal import calculate_camera_pieces, calculate_press_drops, calculate_wet_rejects
from .sql_source import MAX_QUERY_ROWS, MAX_WINDOW_DAYS, SQLServerReadOnlyRepository, SourceUnavailable
from .store import store

PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env", override=False)
try:
    APP_PORT = int(os.getenv("APP_PORT", "3001"))
except ValueError:
    APP_PORT = 3001
if not 1 <= APP_PORT <= 65535:
    APP_PORT = 3001

app = FastAPI(title="OmagMES Factory Review Prototype", version="0.1.0")
source_repository = SQLServerReadOnlyRepository()


@app.get("/api/health")
def health() -> dict[str, Any]:
    settings = source_repository.settings
    return {
        "status": "ok",
        "mode": settings.safe_mode_name,
        "application_port": APP_PORT,
        "database_connected": None,
        "note": "Application access uses the Vite port; FastAPI remains internal on port 8000. Database connection is not checked by API health; use /api/sources/health.",
    }


def source_call(operation: Any) -> Any:
    try:
        return operation()
    except SourceUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from None
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"SQL source query failed ({type(exc).__name__}).") from None


def safe_source_error(exc: Exception) -> str:
    if isinstance(exc, SourceUnavailable):
        return str(exc)
    return f"SQL source query failed ({type(exc).__name__})."


def validate_source_window(start_at: datetime, end_at: datetime, limit: int) -> None:
    try:
        source_repository._validate_range(start_at, end_at, limit)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None


@app.get("/api/sources/health")
def source_health() -> dict[str, Any]:
    return source_repository.health()


@app.get("/api/sources/wet/status")
def wet_status() -> dict[str, Any]:
    return source_call(source_repository.latest_wet_status)


@app.get("/api/sources/press/latest")
def latest_press_counter() -> dict[str, Any]:
    return {"observation": source_call(source_repository.latest_press_counter)}


@app.get("/api/sources/press/observations")
def press_observations(start_at: datetime, end_at: datetime, limit: int = 1000) -> dict[str, Any]:
    validate_source_window(start_at, end_at, limit)
    rows = source_call(lambda: source_repository.press_observations(start_at, end_at, limit))
    return {"observations": rows, "truncated": len(rows) == limit}


@app.get("/api/sources/camera/metadata")
def wet_camera_metadata() -> dict[str, Any]:
    return {"table": "dbo.product_count", "columns": source_call(source_repository.camera_metadata)}


@app.get("/api/sources/metadata")
def historian_metadata(table: str) -> dict[str, Any]:
    table_name = table.strip()
    if table_name not in {"PRESS", "REJECT_WET", "product_count"}:
        raise HTTPException(status_code=422, detail="Only PRESS, REJECT_WET, and product_count metadata is in scope.")
    return {"table": f"dbo.{table_name}", "columns": source_call(lambda: source_repository.historian_metadata(table_name))}


@app.get("/api/sources/camera/wet/observations")
def wet_camera_observations(start_at: datetime, end_at: datetime, limit: int = 1000) -> dict[str, Any]:
    validate_source_window(start_at, end_at, limit)
    rows = source_call(lambda: source_repository.wet_camera_observations(start_at, end_at, limit))
    return {"observations": rows, "truncated": len(rows) == limit}


@app.get("/api/sources/reject/counters")
def wet_reject_counters(start_at: datetime, end_at: datetime, limit: int = 1000) -> dict[str, Any]:
    validate_source_window(start_at, end_at, limit)
    tags = source_call(lambda: source_repository.wet_reject_counters(start_at, end_at, limit))
    return {"counters": tags, "source_rule": "cntR* quantity tags only; R* button-state tags excluded"}


@app.get("/api/sources/reject/latest")
def latest_wet_reject_counters(start_at: datetime, end_at: datetime, limit: int = 1000) -> dict[str, Any]:
    validate_source_window(start_at, end_at, limit)
    rows = source_call(lambda: source_repository.latest_wet_reject_counters(start_at, end_at, limit))
    return {"observations": rows, "semantics": "latest cumulative cntR* source values; not Lot quantities"}


@app.get("/api/sources/reject/observations")
def wet_reject_observations(start_at: datetime, end_at: datetime, limit: int = 1000) -> dict[str, Any]:
    validate_source_window(start_at, end_at, limit)
    rows = source_call(lambda: source_repository.wet_reject_observations(start_at, end_at, limit))
    return {"observations": rows, "truncated": len(rows) == limit}


@app.get("/api/sources/dashboard")
def source_dashboard(start_at: datetime, end_at: datetime) -> dict[str, Any]:
    validate_source_window(start_at, end_at, MAX_QUERY_ROWS)
    health_status = source_repository.health()
    result: dict[str, Any] = {
        "mode": health_status["mode"],
        "connected": health_status["connected"],
        "wet_status": None,
        "press_counter": None,
        "wet_camera_pieces": None,
        "wet_reject_counts": {},
        "last_observation_at": None,
        "warnings": [],
        "source_errors": {},
    }
    if not health_status["connected"]:
        result["source_errors"]["connection"] = health_status["error"]
        return result

    timestamps: list[str] = []
    try:
        result["wet_status"] = source_repository.latest_wet_status()
        status_row = result["wet_status"].get("observation")
        if status_row and status_row.get("_TIMESTAMP"):
            timestamps.append(str(status_row["_TIMESTAMP"]))
    except Exception as exc:
        result["source_errors"]["wet_status"] = safe_source_error(exc)
    try:
        result["press_counter"] = source_repository.latest_press_counter()
        if result["press_counter"] and result["press_counter"].get("_TIMESTAMP"):
            timestamps.append(str(result["press_counter"]["_TIMESTAMP"]))
    except Exception as exc:
        result["source_errors"]["press"] = safe_source_error(exc)
    try:
        bounded_start = end_at - timedelta(days=1)
        reject_rows = source_repository.latest_wet_reject_counters(bounded_start, end_at, MAX_QUERY_ROWS)
        result["wet_reject_counts"] = {str(row["_NAME"]): row.get("_VALUE") for row in reject_rows}
        timestamps.extend(str(row["_TIMESTAMP"]) for row in reject_rows if row.get("_TIMESTAMP"))
    except Exception as exc:
        result["source_errors"]["wet_reject"] = safe_source_error(exc)
    result["warnings"].append("Wet Camera Pieces and per-Lot reject differences are withheld until a verified Lot window and camera boundary policy are available.")
    result["warnings"].append("Latest Wet Reject counters are raw cumulative source values observed in the bounded trailing 24-hour query window.")
    result["last_observation_at"] = max(timestamps) if timestamps else None
    result["warnings"] = list(dict.fromkeys(result["warnings"]))
    return result


@app.get("/api/bootstrap")
def bootstrap() -> dict[str, Any]:
    return store.snapshot()


@app.get("/api/autocal/preview")
def autocal_preview(lot_id: int | None = None, start_at: datetime | None = None, end_at: datetime | None = None, window_confirmed: bool = False) -> dict[str, Any]:
    settings = source_repository.settings
    if not settings.live_requested:
        return preview_autocal()
    if lot_id is None or lot_id <= 0 or start_at is None or end_at is None:
        raise HTTPException(status_code=422, detail="LIVE READ-ONLY AutoCal requires lot_id and explicit timezone-aware start_at/end_at bounds.")
    validate_source_window(start_at, end_at, MAX_QUERY_ROWS)
    if not window_confirmed or not settings.lot_window_source_confirmed:
        raise HTTPException(status_code=409, detail="AutoCal is withheld until the selected Lot time window is explicitly confirmed and the server is configured for an approved Lot-window source.")
    if (end_at - start_at).total_seconds() > (MAX_WINDOW_DAYS - 1) * 86_400:
        raise HTTPException(status_code=422, detail=f"Live AutoCal window cannot exceed {MAX_WINDOW_DAYS - 1} days.")

    errors: dict[str, str] = {}
    notes: list[str] = ["LIVE READ-ONLY source observations; preview does not save quantities."]
    try:
        press_rows = source_repository.press_observations(start_at, end_at, MAX_QUERY_ROWS)
        if len(press_rows) == MAX_QUERY_ROWS:
            errors["press"] = "Press result reached the row limit; no complete suggestion was produced."
            press_result = {"suggestion": None, "warnings": [errors["press"]], "samples_used": 0}
        else:
            press_result = calculate_press_drops(
                press_rows,
                start_at,
                end_at,
                valid_quality_codes=settings.valid_plc_quality_codes,
                source_timezone=settings.source_timezone,
                source_timezone_confirmed=settings.source_timezone_confirmed,
                max_gap_minutes=settings.max_counter_gap_minutes,
            )
    except Exception as exc:
        press_result = {"suggestion": None, "warnings": ["Press source unavailable; no value was substituted."], "samples_used": 0}
        errors["press"] = safe_source_error(exc)

    try:
        reject_rows = source_repository.wet_reject_observations(start_at, end_at, MAX_QUERY_ROWS)
        if len(reject_rows) == MAX_QUERY_ROWS:
            reject_result = {"suggestions": {}, "warnings": ["Wet Reject result reached the row limit; no complete suggestions were produced."]}
        else:
            reject_result = calculate_wet_rejects(
                reject_rows,
                start_at,
                end_at,
                valid_quality_codes=settings.valid_plc_quality_codes,
                source_timezone=settings.source_timezone,
                source_timezone_confirmed=settings.source_timezone_confirmed,
                max_gap_minutes=settings.max_counter_gap_minutes,
            )
    except Exception as exc:
        reject_result = {"suggestions": {}, "warnings": ["Wet Reject source unavailable; no values were substituted."]}
        errors["wet_reject"] = safe_source_error(exc)

    try:
        camera_rows = source_repository.wet_camera_observations(start_at, end_at, MAX_QUERY_ROWS)
        if len(camera_rows) == MAX_QUERY_ROWS:
            camera_result = {"suggestion": None, "observations_used": 0, "warnings": ["Camera result reached the row limit; no complete suggestion was produced."]}
        else:
            camera_result = calculate_camera_pieces(
                camera_rows,
                start_at,
                end_at,
                source_timezone=settings.source_timezone,
                source_timezone_confirmed=settings.source_timezone_confirmed,
                metadata_reviewed=settings.camera_metadata_reviewed,
                boundary_policy_confirmed=settings.camera_boundary_policy_confirmed,
                valid_quality_values=settings.camera_quality_values,
                duplicate_clear_values=settings.camera_duplicate_clear_values,
            )
    except Exception as exc:
        camera_result = {"suggestion": None, "observations_used": 0, "warnings": ["Wet Camera source unavailable; no value was substituted."]}
        errors["wet_camera"] = safe_source_error(exc)

    try:
        current_status = source_repository.latest_wet_status()
        current_counter = source_repository.latest_press_counter()
    except Exception as exc:
        current_status = {"status": "UNKNOWN", "observation": None}
        current_counter = None
        errors["current_status"] = safe_source_error(exc)

    warnings = [*press_result["warnings"], *reject_result["warnings"], *camera_result["warnings"]]
    return {
        "mode": "LIVE READ-ONLY",
        "lot_id": lot_id,
        "window": {"start_at": start_at.isoformat(), "end_at": end_at.isoformat()},
        "current_wet_status": current_status,
        "latest_press_counter": current_counter,
        "suggested_actual_drops": press_result["suggestion"],
        "suggested_wet_good_pieces": camera_result["suggestion"],
        "suggested_wet_rejects": reject_result["suggestions"],
        "source_errors": errors,
        "source_notes": list(dict.fromkeys([*notes, *warnings])),
    }


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
