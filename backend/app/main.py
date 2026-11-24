from __future__ import annotations

import os
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from dotenv import load_dotenv

from .autocal import preview_autocal
from .auto_lot_detection import detect_dropcnt_envelope, detect_dropcnt_reset_candidates
from .configuration_repository import ConfigurationConflict, ConfigurationUnavailable, SQLServerConfigurationRepository
from .models import AutoLotAssignmentSave, AutoLotReconcileRequest, AutoLotCandidateAction, AutoLotCandidateClassify, AutoLotDraftCreate, AutoLotDraftDismiss, AutoLotDraftReview, AutoLotPlanAssign, AutoLotWindowCreate, AutoLotWindowDismiss, AutoLotWindowEdit, AutoLotWindowMerge, AutoLotWindowRestore, AutoLotWindowSplit, DispatchSave, LifecycleSave, LotCreate, LotRename, MouldTransition, ProductionCorrection, ProductionDayCutoffSave, ProductionDelete, ProductionSave, ProductionShiftTypeSave, ShiftPeriodScheduleSave, ShiftScheduleSave, WetRejectSave, WetRunEventSave, WorkTimeShiftSettingsSave
from .live_autocal import calculate_camera_pieces, calculate_press_drops, calculate_wet_rejects
from .production_day import PRODUCTION_TIMEZONE, ProductionDayConfigurationError, cutoff_version_for_date, minimum_safe_cutoff_effective_date, parse_cutoff_time, parse_production_date, production_day_window, resolve_cutoff_context, resolve_production_date
from .shift_schedule import ScheduleValidationError, draft_requires_schedule_review, resolve_schedule_context, shift_for_timestamp, validate_draft_interval
from .shift_type_schedule import ShiftTypeValidationError, resolve_lot_start_context, shift_for_type_timestamp
from .sql_source import MAX_QUERY_ROWS, MAX_WINDOW_DAYS, SQLServerReadOnlyRepository, SourceUnavailable
from .production_repository import SQLServerProductionRepository
from .lot_numbering import SCG_LINE_CODE, LotNumberingError
from .store import store
from .autolot_repository import SQLServerAutoLotRepository

PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env", override=False)
try:
    APP_PORT = int(os.getenv("APP_PORT", "3001"))
except ValueError:
    APP_PORT = 3001
if not 1 <= APP_PORT <= 65535:
    APP_PORT = 3001

app = FastAPI(title="OmagMES Factory Review Prototype", version="0.1.0")
app.mount("/static", StaticFiles(directory=str(PROJECT_ROOT / "static")), name="static")
templates = Jinja2Templates(directory=str(PROJECT_ROOT / "templates"))
source_repository = SQLServerReadOnlyRepository()
production_repository = SQLServerProductionRepository(source_repository.settings)
configuration_repository = SQLServerConfigurationRepository()
auto_lot_repository = SQLServerAutoLotRepository(production_repository)


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


def reject_unpersisted_operation(operation: str) -> None:
    raise HTTPException(
        status_code=503,
        detail=f"{operation} persistence is unavailable; no mock write was made.",
    )


def safe_source_error(exc: Exception) -> str:
    if isinstance(exc, SourceUnavailable):
        return str(exc)
    return f"SQL source query failed ({type(exc).__name__})."


def validate_source_window(start_at: datetime, end_at: datetime, limit: int) -> None:
    try:
        source_repository._validate_range(start_at, end_at, limit)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None


def normalize_operator_lot_time(value: datetime) -> datetime:
    """Normalize an operator boundary to local HH:mm:00 without changing its date."""
    local_value = value.astimezone(ZoneInfo(PRODUCTION_TIMEZONE)) if value.tzinfo else value
    return local_value.replace(second=0, microsecond=0)


@app.get("/api/sources/health")
def source_health() -> dict[str, Any]:
    result = source_repository.health()
    if source_repository.settings.live_requested and result.get("connected"):
        try:
            result["production_storage"] = production_repository.health()
        except SourceUnavailable as exc:
            result["production_storage"] = {"connected": False, "schema_ready": False, "error": str(exc)}
    return result


def _web_date(value: str | None) -> str:
    if value:
        try:
            parsed = parse_production_date(value)
        except ProductionDayConfigurationError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from None
        return parsed.isoformat()
    production_date, _, _ = current_production_day()
    return production_date


def _web_status_context(production_date: str, *, active_page: str, error: str = "", success: str = "") -> dict[str, Any]:
    settings = source_repository.settings
    context: dict[str, Any] = {
        "page_title": "Production" if active_page == "production" else "Edit Log",
        "active_page": active_page,
        "runtime_label": "LIVE SQL · OMAG_MES" if settings.live_requested else "SQL SOURCE NOT ACTIVE",
        "production_date": production_date,
        "connected": False,
        "writes_enabled": False,
        "connection_error": "",
        "schema_error": "",
        "error": error,
        "success": success,
        "products": [], "lots": [], "entries": [], "reject_reasons": [], "moulds": [],
        "plans": [], "plans_error": "", "plans_truncated": False, "plan_limit": 1000,
        "audit_by_entry": {}, "press_total": None, "press_error": "",
        "schedule_version_id": None,
        "default_time": datetime.now(ZoneInfo(PRODUCTION_TIMEZONE)).strftime("%Y-%m-%dT%H:%M"),
    }
    if not settings.live_requested:
        context["connection_error"] = "LIVE_READ_ONLY is not configured. Mock data and mock SAVE paths are disabled."
        return context
    try:
        storage = production_repository.health()
        context["connected"] = True
        context["writes_enabled"] = bool(storage["schema_ready"])
        if not storage["schema_ready"]:
            missing_schema = [*storage["missing_tables"], *storage.get("missing_columns", [])]
            context["schema_error"] = "Required production schema is incomplete. Missing: " + ", ".join(missing_schema)
            return context
        snapshot = production_repository.bootstrap({})
        context.update({
            "products": snapshot["products"], "lots": snapshot["lots"], "reject_reasons": snapshot["reject_reasons"],
            "moulds": snapshot["moulds"], "entries": production_repository.production_entries(production_date),
            "audit_by_entry": production_repository.production_audit_history(),
        })
        schedule = resolve_schedule_context(read_shift_versions(), production_date)
        context["schedule_version_id"] = schedule["applicable_version_id"]
        try:
            press = source_repository.press_daily_diff_total(production_date)
            context["press_total"] = press["press_drops"]
        except Exception as exc:
            context["press_error"] = safe_source_error(exc)
    except Exception as exc:
        context["connected"] = False
        context["connection_error"] = safe_source_error(exc)
    return context


def _web_redirect(path: str, production_date: str, *, error: str = "", success: str = "") -> RedirectResponse:
    params = {"production_date": production_date}
    if error:
        params["error"] = error
    if success:
        params["success"] = success
    return RedirectResponse(f"{path}?{urlencode(params)}", status_code=303)


@app.get("/", response_class=HTMLResponse)
def production_web_page(request: Request, production_date: str | None = None, error: str = "", success: str = "") -> HTMLResponse:
    try:
        selected_date = _web_date(production_date)
    except HTTPException as exc:
        selected_date = production_date or ""
        context = _web_status_context(selected_date, active_page="production", error=str(exc.detail))
        return templates.TemplateResponse(request=request, name="production.html", context=context, status_code=422, headers={"Cache-Control": "no-store"})
    context = _web_status_context(selected_date, active_page="production", error=error, success=success)
    status_code = 200 if context["connected"] and not context["schema_error"] else 503
    return templates.TemplateResponse(request=request, name="production.html", context=context, status_code=status_code, headers={"Cache-Control": "no-store"})


@app.get("/edit-log", response_class=HTMLResponse)
def edit_log_web_page(request: Request, production_date: str | None = None, error: str = "", success: str = "") -> HTMLResponse:
    try:
        selected_date = _web_date(production_date)
    except HTTPException as exc:
        selected_date = production_date or ""
        context = _web_status_context(selected_date, active_page="edit-log", error=str(exc.detail))
        return templates.TemplateResponse(request=request, name="edit_log.html", context=context, status_code=422, headers={"Cache-Control": "no-store"})
    context = _web_status_context(selected_date, active_page="edit-log", error=error, success=success)
    if context["connected"]:
        try:
            plans = source_repository.production_plan_snapshots()
            context["plans"] = plans["plans"]
            context["plans_truncated"] = plans["truncated"]
            context["plan_limit"] = plans["limit"]
        except Exception as exc:
            context["plans_error"] = safe_source_error(exc)
    status_code = 200 if context["connected"] and (not context["schema_error"] or not context["plans_error"]) else 503
    return templates.TemplateResponse(request=request, name="edit_log.html", context=context, status_code=status_code, headers={"Cache-Control": "no-store"})


@app.post("/web/production/save")
def production_web_save(
    lot_id: int = Form(...), production_date: str = Form(...), schedule_version_id: int = Form(...),
    production_at: datetime = Form(...), actual_drops: int = Form(...), wet_good_pieces: int = Form(...),
    operator_id: str = Form(...), operator_note: str = Form(""), operator_confirmed: str | None = Form(None),
) -> RedirectResponse:
    try:
        result = save_production(ProductionSave(
            lot_id=lot_id, production_at=production_at, actual_drops=actual_drops,
            wet_good_pieces=wet_good_pieces, operator_id=operator_id, operator_note=operator_note,
            operator_confirmed=operator_confirmed == "yes", shift_schedule_version_id=schedule_version_id,
        ))
        return _web_redirect("/", production_date, success=f"Production Entry #{result['id']} saved to SQL.")
    except (HTTPException, ValueError, SourceUnavailable) as exc:
        detail = exc.detail if isinstance(exc, HTTPException) else str(exc)
        return _web_redirect("/", production_date, error=str(detail))


@app.post("/web/production/{entry_id}/edit")
def production_web_edit(
    entry_id: int, production_date: str = Form(...), actual_drops: int = Form(...), wet_good_pieces: int = Form(...),
    operator_id: str = Form(...), reason: str = Form(...), operator_confirmed: str | None = Form(None),
) -> RedirectResponse:
    try:
        result = production_repository.correct_production(
            entry_id, actual_drops=actual_drops, wet_good_pieces=wet_good_pieces,
            reason=reason, operator_id=operator_id, operator_confirmed=operator_confirmed == "yes",
        )
        return _web_redirect("/edit-log", production_date, success=f"Production Entry #{result['id']} edited and audited.")
    except (ValueError, SourceUnavailable) as exc:
        return _web_redirect("/edit-log", production_date, error=str(exc))


@app.post("/web/production/{entry_id}/delete")
def production_web_delete(
    entry_id: int, production_date: str = Form(...), operator_id: str = Form(...), reason: str = Form(...),
    operator_confirmed: str | None = Form(None),
) -> RedirectResponse:
    try:
        production_repository.delete_production(
            entry_id, reason=reason, operator_id=operator_id,
            operator_confirmed=operator_confirmed == "yes",
        )
        return _web_redirect("/edit-log", production_date, success=f"Production Entry #{entry_id} was soft-deleted; audit history retained.")
    except (ValueError, SourceUnavailable) as exc:
        return _web_redirect("/edit-log", production_date, error=str(exc))


@app.post("/web/curing/save")
def curing_web_save(
    production_date: str = Form(...), lot_id: int = Form(...), quantity: int = Form(...), unit_code: str = Form(...),
    operator_id: str = Form(...), note: str = Form(""), operator_confirmed: str | None = Form(None),
) -> RedirectResponse:
    if operator_confirmed != "yes":
        return _web_redirect("/", production_date, error="Operator confirmation is required before Curing SAVE.")
    try:
        result = production_repository.save_curing({"lot_id": lot_id, "quantity": quantity, "unit_code": unit_code,
                                                     "operator_id": operator_id, "note": note, "operator_confirmed": True})
        return _web_redirect("/", production_date, success=f"Curing entry #{result['id']} saved to SQL.")
    except (ValueError, SourceUnavailable) as exc:
        return _web_redirect("/", production_date, error=str(exc))


@app.post("/web/reject/save")
async def wet_reject_web_save(request: Request) -> RedirectResponse:
    form = await request.form()
    production_date = str(form.get("production_date") or "")
    try:
        quantities = {
            int(key.removeprefix("reason_")): int(value)
            for key, value in form.multi_items()
            if key.startswith("reason_")
        }
        payload = WetRejectSave(
            lot_id=int(str(form.get("lot_id") or "")), quantities=quantities,
            operator_id=str(form.get("operator_id") or ""),
            operator_note=str(form.get("operator_note") or ""),
        )
        result = save_wet_reject(payload)
        return _web_redirect("/", production_date, success=f"{len(result['entries'])} Wet Reject record(s) saved to SQL.")
    except (HTTPException, ValueError, SourceUnavailable) as exc:
        detail = exc.detail if isinstance(exc, HTTPException) else str(exc)
        return _web_redirect("/", production_date, error=str(detail))


@app.post("/web/lots/create")
def lot_web_create(
    production_date: str = Form(...), schedule_version_id: int = Form(...), product_id: int = Form(...),
    previous_lot_id: str = Form(""), color: str = Form(...), lot_name: str = Form(...),
    started_at: datetime = Form(...), operator_id: str = Form(...),
) -> RedirectResponse:
    try:
        result = create_lot(LotCreate(
            product_id=product_id, previous_lot_id=int(previous_lot_id) if previous_lot_id else None,
            transition="PRODUCT_CHANGE", color=color, lot_name=lot_name, production_date=production_date,
            shift_schedule_version_id=schedule_version_id, operator_id=operator_id, started_at=started_at,
            machine_code="A",
        ))
        return _web_redirect("/", production_date, success=f"Lot ID #{result['id']} · {result['transition']} · {result['lot_number']}.")
    except (HTTPException, ValueError, SourceUnavailable) as exc:
        detail = exc.detail if isinstance(exc, HTTPException) else str(exc)
        return _web_redirect("/", production_date, error=str(detail))


@app.post("/web/lots/{lot_id}/rename")
def lot_web_rename(
    lot_id: int, production_date: str = Form(...), new_name: str = Form(...),
    operator_id: str = Form(...), reason: str = Form(...),
) -> RedirectResponse:
    try:
        rename_lot(lot_id, LotRename(new_name=new_name, operator_id=operator_id, reason=reason))
        return _web_redirect("/", production_date, success=f"Lot ID #{lot_id} renamed; ID and linked records are unchanged.")
    except (HTTPException, ValueError, SourceUnavailable) as exc:
        detail = exc.detail if isinstance(exc, HTTPException) else str(exc)
        return _web_redirect("/", production_date, error=str(detail))


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
    snapshot = store.snapshot()
    if source_repository.settings.live_requested:
        return source_call(lambda: production_repository.bootstrap(snapshot))
    return snapshot


def read_cutoff_versions() -> list[dict[str, Any]]:
    try:
        versions = configuration_repository.get_cutoff_versions()
    except ConfigurationUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from None
    if not versions:
        raise HTTPException(status_code=503, detail="Production Day Cutoff is not initialized in SQL Server; apply the reviewed configuration bootstrap migration.")
    return versions


def read_shift_versions() -> list[dict[str, Any]]:
    try:
        versions = configuration_repository.get_shift_versions()
    except ConfigurationUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from None
    if not versions:
        raise HTTPException(status_code=503, detail="Shift Schedule is not initialized in SQL Server; apply the reviewed configuration bootstrap migration.")
    return versions


def current_production_day() -> tuple[str, int, datetime]:
    now = datetime.now(ZoneInfo(PRODUCTION_TIMEZONE))
    try:
        production_date, cutoff_version_id = resolve_production_date(now, read_cutoff_versions())
    except ProductionDayConfigurationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    return production_date, cutoff_version_id, now


def production_context(
    production_date: str | None,
    schedule_version_id: int | None,
    cutoff_version_id: int | None = None,
) -> tuple[str, int, int]:
    cutoff_versions = read_cutoff_versions()
    if production_date is None:
        selected_date, applicable_cutoff_version_id, _ = current_production_day()
    else:
        try:
            selected_date = parse_production_date(production_date).isoformat()
            applicable_cutoff_version_id = cutoff_version_for_date(cutoff_versions, selected_date)["id"]
        except ProductionDayConfigurationError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from None
    try:
        context = resolve_schedule_context(read_shift_versions(), selected_date)
    except ScheduleValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    applicable_version_id = context["applicable_version_id"]
    if schedule_version_id is not None and schedule_version_id != applicable_version_id:
        raise HTTPException(status_code=409, detail="Shift Schedule version changed for this Production Date; review the entry before saving")
    if cutoff_version_id is not None and cutoff_version_id != applicable_cutoff_version_id:
        raise HTTPException(status_code=409, detail="Production Day Cutoff version changed for this Production Date; review the entry before saving")
    return selected_date, applicable_version_id, applicable_cutoff_version_id


@app.get("/api/production-date/current")
def get_current_production_date() -> dict[str, Any]:
    production_date, cutoff_version_id, now = current_production_day()
    versions = read_cutoff_versions()
    version = next(item for item in versions if item["id"] == cutoff_version_id)
    calendar_version = cutoff_version_for_date(versions, now.date())
    return {
        "calendar_timestamp": now.isoformat(),
        "calendar_date": now.date().isoformat(),
        "production_date": production_date,
        "cutoff_time": version["cutoff_time"],
        "cutoff_version_id": cutoff_version_id,
        "calendar_boundary_cutoff_version_id": calendar_version["id"],
        "calendar_boundary_cutoff_time": calendar_version["cutoff_time"],
        "time_zone": PRODUCTION_TIMEZONE,
        "source": "SERVER CLOCK + SQL CONFIGURATION",
    }


@app.get("/api/production-day-cutoff")
def get_production_day_cutoff(production_date: str) -> dict[str, Any]:
    try:
        return resolve_cutoff_context(production_date, read_cutoff_versions())
    except ProductionDayConfigurationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None


@app.get("/api/configuration-history")
def get_configuration_history() -> dict[str, Any]:
    try:
        return {"events": configuration_repository.get_configuration_history()}
    except ConfigurationUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from None


@app.get("/api/production/shift-type")
def get_production_shift_type(production_date: str) -> dict[str, Any]:
    try:
        selected_date = parse_production_date(production_date).isoformat()
        return source_call(lambda: production_repository.production_shift_type(selected_date))
    except ProductionDayConfigurationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None


@app.post("/api/production/shift-type", status_code=201)
def save_production_shift_type(payload: ProductionShiftTypeSave) -> dict[str, Any]:
    try:
        selected_date = parse_production_date(payload.production_date).isoformat()
        return source_call(lambda: production_repository.save_production_shift_type(selected_date, payload.selected_type))
    except ProductionDayConfigurationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None


@app.get("/api/worktime/shift-settings")
def get_worktime_shift_settings() -> dict[str, Any]:
    return source_call(production_repository.worktime_shift_settings)


@app.post("/api/worktime/shift-settings")
def save_worktime_shift_settings(payload: WorkTimeShiftSettingsSave) -> dict[str, Any]:
    return source_call(lambda: production_repository.save_worktime_shift_settings(
        [change.model_dump() for change in payload.changes],
    ))


@app.get("/api/production-day-window")
def get_production_day_window(production_date: str) -> dict[str, Any]:
    try:
        return production_day_window(production_date, read_cutoff_versions())
    except ProductionDayConfigurationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None


@app.get("/api/press-lots/plans")
def get_auto_lot_plans(production_date: str | None = None) -> dict[str, Any]:
    """Return current Plan snapshots with server-resolved exact Product matches."""
    try:
        result = source_repository.production_plan_snapshots(MAX_QUERY_ROWS, production_date)
        result["plans"] = auto_lot_repository.plans_with_product_matches(result["plans"])
        result["assignment_available"] = not result["truncated"]
        if result["truncated"]:
            result["warnings"].append("Plan source was truncated; assignments are disabled because duplicate snapshots cannot be ruled out.")
        return result
    except Exception as exc:
        raise HTTPException(status_code=503, detail=safe_source_error(exc)) from None


@app.get("/api/products/{product_id}/active-moulds")
def get_active_product_moulds(product_id: int) -> dict[str, Any]:
    """List physical Moulds eligible for a resolved Product."""
    if product_id <= 0:
        raise HTTPException(status_code=422, detail="ProductID must be positive.")
    moulds = source_call(lambda: auto_lot_repository.active_moulds_for_product(product_id))
    return {"product_id": product_id, "moulds": moulds}


@app.get("/api/production/overview")
def production_overview(production_date: str, run_auto_lot: bool | None = None) -> dict[str, Any]:
    """Read current AutoLots directly from dbo.vw_PRESS_LotAuto; no AutoLot tables required."""
    del run_auto_lot  # Deprecated compatibility only; detection no longer has a manual RUN operation.
    try:
        selected_date = parse_production_date(production_date).isoformat()
        cutoff_versions = read_cutoff_versions()
        day_window = production_day_window(selected_date, cutoff_versions)
    except ProductionDayConfigurationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None

    response: dict[str, Any] = {
        "production_date": selected_date,
        "production_day_window": day_window,
        "source": "OMAG.dbo.vw_PRESS_LotAuto",
        "official_lots": [], "auto_lots": [], "preview_lots": [],
        "press_available": False, "press_error": None, "lot_error": None,
        "press_warnings": [], "auto_lot_status": "DIRECT SQL VIEW",
        "counter_source": "DropCnt FROM OMAG.dbo.vw_PRESS_LotAuto",
        "counter_integration_enabled": True,
        "assignment_available": False,
        "assignment_error": "AutoLot assignment storage setup is required before assignments can be saved.",
    }
    if not source_repository.settings.live_requested:
        response["press_error"] = "LIVE_READ_ONLY source mode is not active; no mock Lot rows are shown."
        return response

    try:
        detections = source_repository.press_lot_auto(selected_date)
        response["auto_lots"] = detections["rows"]
        response["press_available"] = bool(detections["rows"])
        response["detection_identity_strategy"] = detections["identity_strategy"]
        try:
            if auto_lot_repository.is_available():
                saved_rows = auto_lot_repository.list_for_date(selected_date)
                response["auto_lots"] = auto_lot_repository.attach_saved_assignments(
                    detections["rows"], saved_rows,
                )
                response["assignment_available"] = True
                response["assignment_error"] = None
        except Exception as exc:
            response["assignment_error"] = safe_source_error(exc)
    except (SourceUnavailable, ValueError) as exc:
        response["press_error"] = safe_source_error(exc) if isinstance(exc, Exception) else str(exc)
    try:
        response["official_lots"] = production_repository.production_day_lots(
            selected_date, datetime.fromisoformat(day_window["start_at"]),
            datetime.fromisoformat(day_window["end_at_exclusive"]),
        )
    except Exception as exc:
        response["lot_error"] = safe_source_error(exc)
    return response


@app.post("/api/auto-lots/reconcile")
def reconcile_auto_lots(payload: AutoLotReconcileRequest) -> dict[str, Any]:
    """Controlled page-load reconciliation; serialized and idempotent in SQL."""
    try:
        selected_date = parse_production_date(payload.production_date).isoformat()
    except ProductionDayConfigurationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    if not source_repository.settings.live_requested:
        raise HTTPException(status_code=503, detail="Live SQL source mode is not active; AutoLot reconciliation is unavailable.")
    try:
        detections = source_repository.press_lot_auto(selected_date)
        result = auto_lot_repository.reconcile(selected_date, None, detections["rows"])
    except (ValueError, ShiftTypeValidationError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    except SourceUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from None
    return {"production_date": selected_date, "source": detections["source"], **result}


@app.post("/api/auto-lots/{auto_lot_id}/assignment")
def save_auto_lot_assignment(auto_lot_id: int, payload: AutoLotAssignmentSave) -> dict[str, Any]:
    if auto_lot_id <= 0:
        raise HTTPException(status_code=422, detail="AutoLotID must be positive.")
    production_date = source_call(lambda: auto_lot_repository.production_date_for(auto_lot_id))
    plan: dict[str, Any] | None = None
    if payload.plan_key is not None:
        plan_result = source_call(lambda: source_repository.production_plan_snapshots(MAX_QUERY_ROWS, production_date))
        if plan_result["truncated"]:
            raise HTTPException(status_code=409, detail="Production Plan source is truncated; assignment cannot be validated safely.")
        matches = [item for item in plan_result["plans"] if item["plan_key"] == payload.plan_key]
        if len(matches) != 1:
            raise HTTPException(status_code=409, detail="Selected Plan is no longer uniquely available; reload Plans and retry.")
        plan = matches[0]
        mapped = source_call(lambda: auto_lot_repository.plans_with_product_matches([plan]))[0]
        if mapped["product_match"]["status"] != "MATCHED":
            raise HTTPException(status_code=422, detail="PRODUCT NOT FOUND or ambiguous for this Plan MaterialCode; assignment was not saved.")
    return source_call(lambda: auto_lot_repository.save_assignment(auto_lot_id, plan, payload.mould_id))


@app.post("/api/production-day-cutoff/versions", status_code=201)
def create_production_day_cutoff_version(payload: ProductionDayCutoffSave) -> dict[str, Any]:
    try:
        effective = parse_production_date(payload.effective_from)
        parse_production_date(payload.reviewed_through_date)
        parse_cutoff_time(payload.cutoff_time)
    except ProductionDayConfigurationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    reason = payload.change_reason.strip()
    if not reason:
        raise HTTPException(status_code=422, detail="A cutoff change reason is required")
    current_date, _, _ = current_production_day()
    minimum_date = minimum_safe_cutoff_effective_date(current_date)
    if effective.isoformat() < minimum_date or effective.isoformat() <= payload.reviewed_through_date:
        raise HTTPException(status_code=409, detail=f"Cutoff changes must be effective no earlier than {minimum_date} to protect started Production Days")
    try:
        return configuration_repository.create_cutoff_version(
            effective_from=effective.isoformat(), cutoff_time=payload.cutoff_time,
            time_zone=payload.time_zone, base_version_id=payload.base_version_id,
            reason=reason, current_production_date=current_date,
        )
    except ConfigurationConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    except ProductionDayConfigurationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    except ConfigurationUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from None


@app.get("/api/shift-schedule")
def get_shift_schedule(production_date: str) -> dict[str, Any]:
    try:
        context = resolve_schedule_context(read_shift_versions(), production_date)
        context["production_day"] = production_day_window(production_date, read_cutoff_versions())
        context["cutoff_version_id"] = cutoff_version_for_date(read_cutoff_versions(), production_date)["id"]
        return context
    except ScheduleValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    except ProductionDayConfigurationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None


@app.get("/api/shift-period-schedule")
def get_shift_period_schedule(production_date: str) -> dict[str, Any]:
    try:
        context = resolve_schedule_context(read_shift_versions(), production_date)
        context["production_day"] = production_day_window(production_date, read_cutoff_versions())
        context["cutoff_version_id"] = cutoff_version_for_date(read_cutoff_versions(), production_date)["id"]
        context["periods_enabled"] = configuration_repository.shift_period_schema_available()
        return context
    except ScheduleValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    except ProductionDayConfigurationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None


@app.post("/api/shift-schedule/versions", status_code=201)
def create_shift_schedule_version(payload: ShiftScheduleSave) -> dict[str, Any]:
    try:
        parse_production_date(payload.effective_from)
        parse_production_date(payload.reviewed_through_date)
    except (ScheduleValidationError, ProductionDayConfigurationError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    reason = payload.change_reason.strip()
    if not reason:
        raise HTTPException(status_code=422, detail="A schedule change reason is required")
    current_date, _, _ = current_production_day()
    if payload.effective_from <= current_date:
        raise HTTPException(status_code=409, detail="A Shift Schedule version must be effective after the current Production Date")
    shifts = [{
        **item.model_dump(),
        "periods": [{"start_time": item.start_time, "end_time": item.end_time, "display_order": 1, "active": item.active}],
    } for item in payload.shifts]
    try:
        return configuration_repository.create_shift_period_version(
            effective_from=payload.effective_from, base_version_id=payload.base_version_id,
            reason=reason, shifts=shifts, reviewed_through_date=payload.reviewed_through_date,
        )
    except ConfigurationConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    except (ScheduleValidationError, ProductionDayConfigurationError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    except ConfigurationUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from None


@app.post("/api/shift-period-schedule/versions", status_code=201)
def create_shift_period_schedule_version(payload: ShiftPeriodScheduleSave) -> dict[str, Any]:
    try:
        parse_production_date(payload.effective_from)
        parse_production_date(payload.reviewed_through_date)
    except (ScheduleValidationError, ProductionDayConfigurationError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    reason = payload.change_reason.strip()
    if not reason:
        raise HTTPException(status_code=422, detail="A schedule change reason is required")
    current_date, _, _ = current_production_day()
    if payload.effective_from <= current_date:
        raise HTTPException(status_code=409, detail="A Shift Schedule version must be effective after the current Production Date")
    try:
        return configuration_repository.create_shift_period_version(
            effective_from=payload.effective_from, base_version_id=payload.base_version_id,
            reason=reason, shifts=[item.model_dump() for item in payload.shifts],
            reviewed_through_date=payload.reviewed_through_date,
        )
    except ConfigurationConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    except (ScheduleValidationError, ProductionDayConfigurationError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    except ConfigurationUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from None


@app.get("/api/autocal/preview")
def autocal_preview(lot_id: int | None = None, start_at: datetime | None = None, end_at: datetime | None = None, window_confirmed: bool = False) -> dict[str, Any]:
    settings = source_repository.settings
    if not settings.live_requested:
        return preview_autocal()
    if lot_id is None or lot_id <= 0 or start_at is None or end_at is None:
        raise HTTPException(status_code=422, detail="LIVE READ-ONLY AutoCal requires lot_id and explicit timezone-aware start_at/end bounds.")
    validate_source_window(start_at, end_at, MAX_QUERY_ROWS)
    if not window_confirmed or not settings.lot_window_source_confirmed:
        raise HTTPException(status_code=409, detail="AutoCal is withheld until the selected Lot time window is explicitly confirmed and the server is configured for an approved Lot-window source.")
    if (end_at - start_at).total_seconds() > (MAX_WINDOW_DAYS - 1) * 86_400:
        raise HTTPException(status_code=422, detail=f"Live AutoCal window cannot exceed {MAX_WINDOW_DAYS - 1} days.")
    errors: dict[str, str] = {}
    notes = ["LIVE READ-ONLY source observations; preview does not save quantities."]
    try:
        press_rows = source_repository.press_observations(start_at, end_at, MAX_QUERY_ROWS)
        press_result = calculate_press_drops(press_rows, start_at, end_at,
            valid_quality_codes=settings.valid_plc_quality_codes, source_timezone=settings.source_timezone,
            source_timezone_confirmed=settings.source_timezone_confirmed, max_gap_minutes=settings.max_counter_gap_minutes)
    except Exception as exc:
        press_result = {"suggestion": None, "warnings": ["Press source unavailable; no value was substituted."], "samples_used": 0}
        errors["press"] = safe_source_error(exc)
    try:
        reject_rows = source_repository.wet_reject_observations(start_at, end_at, MAX_QUERY_ROWS)
        reject_result = calculate_wet_rejects(reject_rows, start_at, end_at,
            valid_quality_codes=settings.valid_plc_quality_codes, source_timezone=settings.source_timezone,
            source_timezone_confirmed=settings.source_timezone_confirmed, max_gap_minutes=settings.max_counter_gap_minutes)
    except Exception as exc:
        reject_result = {"suggestions": {}, "warnings": ["Wet Reject source unavailable; no values were substituted."]}
        errors["wet_reject"] = safe_source_error(exc)
    try:
        camera_rows = source_repository.wet_camera_observations(start_at, end_at, MAX_QUERY_ROWS)
        camera_result = calculate_camera_pieces(camera_rows, start_at, end_at,
            source_timezone=settings.source_timezone, source_timezone_confirmed=settings.source_timezone_confirmed,
            metadata_reviewed=settings.camera_metadata_reviewed, boundary_policy_confirmed=settings.camera_boundary_policy_confirmed,
            valid_quality_values=settings.camera_quality_values, duplicate_clear_values=settings.camera_duplicate_clear_values)
    except Exception as exc:
        camera_result = {"suggestion": None, "observations_used": 0, "warnings": ["Wet Camera source unavailable; no value was substituted."]}
        errors["wet_camera"] = safe_source_error(exc)
    try:
        current_status = source_repository.latest_wet_status()
        current_counter = source_repository.latest_press_counter()
    except Exception as exc:
        current_status, current_counter = {"status": "UNKNOWN", "observation": None}, None
        errors["current_status"] = safe_source_error(exc)
    warnings = [*press_result["warnings"], *reject_result["warnings"], *camera_result["warnings"]]
    return {"mode": "LIVE READ-ONLY", "lot_id": lot_id,
        "window": {"start_at": start_at.isoformat(), "end_at": end_at.isoformat()},
        "current_wet_status": current_status, "latest_press_counter": current_counter,
        "suggested_actual_drops": press_result["suggestion"],
        "suggested_wet_good_pieces": camera_result["suggestion"],
        "suggested_wet_rejects": reject_result["suggestions"], "source_errors": errors,
        "source_notes": list(dict.fromkeys([*notes, *warnings]))}


@app.post("/api/production/save", status_code=201)
def save_production(payload: ProductionSave) -> dict[str, Any]:
    if not source_repository.settings.live_requested:
        raise HTTPException(status_code=503, detail="Production SAVE requires the verified LIVE SQL source; no mock write was made.")
    if not payload.operator_confirmed:
        raise HTTPException(status_code=422, detail="Operator confirmation is required before SAVE.")
    production_at = payload.production_at or datetime.now(ZoneInfo(PRODUCTION_TIMEZONE))
    try:
        production_date, cutoff_id = resolve_production_date(production_at, read_cutoff_versions())
        _, schedule_id, effective_cutoff_id = production_context(
            production_date, payload.shift_schedule_version_id,
            payload.production_day_cutoff_version_id or cutoff_id,
        )
        if effective_cutoff_id != cutoff_id:
            raise HTTPException(status_code=409, detail="Production Day Cutoff changed; reload production context before saving.")
        schedule = resolve_schedule_context(read_shift_versions(), production_date)
        shift = shift_for_timestamp(schedule, production_at)
    except HTTPException:
        raise
    except (ProductionDayConfigurationError, ScheduleValidationError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    live_payload = payload.model_dump()
    live_payload.update({"production_at": production_at, "production_date": production_date,
        "production_day_cutoff_version_id": cutoff_id, "shift_schedule_version_id": schedule_id,
        "shift_id": shift["id"] if shift else None})
    return source_call(lambda: production_repository.save_production(live_payload))


@app.post("/api/wet-reject/save", status_code=201)
def save_wet_reject(payload: WetRejectSave) -> dict[str, Any]:
    if not source_repository.settings.live_requested:
        raise HTTPException(status_code=503, detail="Wet Reject SAVE requires LIVE SQL and the database RejectReason master; no mock write was made.")
    return source_call(lambda: production_repository.save_wet_reject(payload.model_dump()))


@app.post("/api/wet-run-log/events", status_code=201)
def save_wet_run_event(payload: WetRunEventSave) -> dict[str, Any]:
    del payload
    reject_unpersisted_operation("Wet Run Log entry")


@app.get("/api/wet-oee/preview")
def wet_oee_preview() -> dict[str, Any]:
    return {"mode": "SIMULATED — not production data", "window": "08 Nov 2026 · 07:00–15:00 Asia/Bangkok",
        "availability": 0.92, "performance": 0.88, "quality": 0.975,
        "oee": round(0.92 * 0.88 * 0.975, 4), "actual_drops": 820, "wet_good_pieces": 742,
        "standard_status": "DEMO ONLY — no approved Product standard loaded",
        "notes": ["Values are illustrative and are not calculated from live sources.",
                  "Dry Line / Depallet time is excluded.",
                  "Production standards and source attribution require owner approval before operational use."]}


@app.post("/api/curing/entries", status_code=201)
def save_curing(payload: LifecycleSave) -> dict[str, Any]:
    if not source_repository.settings.live_requested:
        raise HTTPException(status_code=503, detail="Curing SAVE requires LIVE SQL; no mock write was made.")
    if not payload.operator_confirmed:
        raise HTTPException(status_code=422, detail="Operator confirmation is required before Curing SAVE.")
    return source_call(lambda: production_repository.save_curing(payload.model_dump()))


@app.post("/api/depallet/events", status_code=201)
def save_depal(payload: LifecycleSave) -> dict[str, Any]:
    if source_repository.settings.live_requested:
        return source_call(lambda: production_repository.save_depal(payload.model_dump()))
    raise HTTPException(status_code=503, detail="Depallet SAVE requires LIVE SQL persistence; no mock write was made.")


@app.post("/api/lots", status_code=201)
def create_lot(payload: LotCreate) -> dict[str, Any]:
    if not source_repository.settings.live_requested:
        raise HTTPException(status_code=503, detail="Lot creation requires LIVE SQL; no mock Lot was created.")
    if payload.started_at is None or payload.production_date is None:
        raise HTTPException(status_code=422, detail="An explicit Lot start timestamp and explicit Production Date are required for official Lot numbering.")
    started_at = normalize_operator_lot_time(payload.started_at)
    try:
        lot_context = resolve_lot_start_context(started_at, cutoff_versions=read_cutoff_versions(),
            assignment_for_date=configuration_repository.get_daily_shift_type_assignment)
        if lot_context.get("status") not in {"ASSIGNED", "OVERNIGHT SHIFT OWNING PRODUCTION DATE"}:
            raise HTTPException(status_code=409, detail="Lot start has no saved daily Shift Type assignment; official Lot numbering is blocked.")
        if payload.production_date != lot_context["production_date"]:
            raise HTTPException(status_code=422, detail=f"Lot start resolves to Production Date {lot_context['production_date']}, not the selected date")
        if payload.machine_code is None:
            raise HTTPException(status_code=422, detail="Select the confirmed BLOCK line code A before official Lot SAVE.")
        live_payload = payload.model_dump()
        live_payload.update({"started_at": started_at, "production_date": payload.production_date,
            "production_day_cutoff_version_id": lot_context["production_day_cutoff_version_id"],
            "shift_schedule_version_id": lot_context["shift_type_schedule_version_id"],
            "shift_id": lot_context["shift_id"], "shift_code": str(lot_context["shift_number"])})
        return production_repository.create_lot(live_payload)
    except HTTPException:
        raise
    except ConfigurationUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from None
    except (ProductionDayConfigurationError, ScheduleValidationError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    except LotNumberingError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    except SourceUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from None


@app.get("/api/lots/number-proposal")
def propose_lot_number(production_date: str, started_at: datetime, machine_code: str = SCG_LINE_CODE) -> dict[str, Any]:
    if not source_repository.settings.live_requested:
        raise HTTPException(status_code=409, detail="Official Lot numbering proposal is available only when SQL production schema is ready.")
    try:
        started_at = normalize_operator_lot_time(started_at)
        assignment = configuration_repository.get_daily_shift_type_assignment(production_date)
        if assignment.get("status") != "SAVED" or not assignment.get("schedule"):
            raise HTTPException(status_code=409, detail="A saved daily Shift Type assignment is required to propose an SCG Lot number.")
        shift = shift_for_type_timestamp(assignment["schedule"], started_at, production_date=production_date)
        if shift is None:
            raise HTTPException(status_code=409, detail="Lot start is outside the saved Shift Type schedule; no number can be proposed.")
        proposal = production_repository.propose_lot_number(production_date=production_date,
            shift_code=str(shift["shift_number"]), machine_code=machine_code)
    except HTTPException:
        raise
    except ConfigurationUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from None
    except (ProductionDayConfigurationError, ScheduleValidationError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    except (SourceUnavailable, LotNumberingError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from None
    return {**proposal, "production_date": production_date,
        "cutoff_version_id": assignment.get("cutoff_version_id"),
        "shift_type_schedule_version_id": assignment["schedule_version_id"],
        "shift_id": shift["shift_id"], "shift_number": shift["shift_number"],
        "shift_name": f"Shift {shift['shift_number']}"}


@app.post("/api/lots/{lot_id}/rename")
def rename_lot(lot_id: int, payload: LotRename) -> dict[str, Any]:
    if not source_repository.settings.live_requested:
        raise HTTPException(status_code=503, detail="LotName changes require LIVE SQL; no mock rename was made.")
    return source_call(lambda: production_repository.rename_lot(
        lot_id, new_name=payload.new_name, reason=payload.reason, operator_id=payload.operator_id))


@app.post("/api/production/entries/{entry_id}/correction")
def correct_production(entry_id: int, payload: ProductionCorrection) -> dict[str, Any]:
    if not source_repository.settings.live_requested:
        raise HTTPException(status_code=409, detail="Audited production corrections require LIVE SQL Lot persistence.")
    if not payload.operator_confirmed:
        raise HTTPException(status_code=422, detail="Operator confirmation is required before editing production quantities.")
    return source_call(lambda: production_repository.correct_production(
        entry_id, actual_drops=payload.actual_drops, wet_good_pieces=payload.wet_good_pieces,
        reason=payload.reason, operator_id=payload.operator_id, operator_confirmed=payload.operator_confirmed))


@app.delete("/api/production/entries/{entry_id}")
def delete_production_entry(entry_id: int, payload: ProductionDelete) -> dict[str, Any]:
    if not source_repository.settings.live_requested:
        raise HTTPException(status_code=409, detail="Production DELETE requires LIVE SQL persistence; no mock deletion was made.")
    if entry_id <= 0 or not payload.operator_confirmed:
        raise HTTPException(status_code=422, detail="Positive entry ID and operator confirmation are required before DELETE.")
    return source_call(lambda: production_repository.delete_production(
        entry_id, reason=payload.reason, operator_id=payload.operator_id,
        operator_confirmed=payload.operator_confirmed))


@app.post("/api/dispatch/entries", status_code=201)
def save_dispatch(payload: DispatchSave) -> dict[str, Any]:
    if not source_repository.settings.live_requested:
        raise HTTPException(status_code=409, detail="Dispatch persistence requires LIVE SQL Lot persistence.")
    return source_call(lambda: production_repository.save_dispatch(payload.model_dump()))


@app.post("/api/moulds/{mould_id}/transition")
def transition_mould(mould_id: int, payload: MouldTransition) -> dict[str, Any]:
    del mould_id, payload
    reject_unpersisted_operation("Mould transition")


@app.get("/api/auto-lot/candidates")
def list_auto_lot_candidates(production_date: str) -> dict[str, Any]:
    """Return the existing read-only legacy DropCnt evidence envelope."""
    try:
        cutoff_versions = read_cutoff_versions()
        schedule = resolve_schedule_context(read_shift_versions(), production_date)
        day_window = production_day_window(production_date, cutoff_versions)
        cutoff_version_id = cutoff_version_for_date(cutoff_versions, production_date)["id"]
    except (ScheduleValidationError, ProductionDayConfigurationError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    settings = source_repository.settings
    base = {
        "production_date": production_date, "cutoff_version_id": cutoff_version_id,
        "applicable_schedule_version_id": schedule["applicable_version_id"],
        "production_day_window": day_window, "source_tag": "OMAG.PRESS.OEE.DropCnt",
        "source": "LIVE PRESS · READ ONLY", "source_timezone_confirmed": settings.source_timezone_confirmed,
        "official_lot_creation": False,
    }
    blockers = settings.live_gate_errors()
    if not settings.historian_metadata_reviewed:
        blockers.append("PRESS historian metadata has not been reviewed.")
    if settings.source_timezone != PRODUCTION_TIMEZONE:
        blockers.append("A configured Asia/Bangkok wall-clock basis is required for the Production Day query window.")
    if not settings.valid_plc_quality_codes:
        blockers.append("No valid PLC quality codes are approved.")
    if settings.max_counter_gap_minutes is None:
        blockers.append("No maximum counter sample-gap threshold is approved.")
    if blockers:
        return {**base, "available": False, "candidates": [], "warnings": [
            "Live DropCnt detection is fail-closed; no source rows were queried.", *blockers,
        ]}
    try:
        start_at = datetime.fromisoformat(day_window["start_at"])
        end_at = datetime.fromisoformat(day_window["end_at_exclusive"])
        rows = source_repository.dropcnt_observations(start_at, end_at, MAX_QUERY_ROWS)
        history_start = start_at - timedelta(minutes=min(settings.max_counter_gap_minutes or 30, 30))
        reset_rows = source_repository.dropcnt_observations(history_start, end_at, MAX_QUERY_ROWS)
    except SourceUnavailable as exc:
        return {**base, "available": False, "candidates": [], "warnings": [
            "Live DropCnt detection is unavailable; no candidate was emitted.", str(exc),
        ]}
    result = detect_dropcnt_envelope(
        rows, production_date=production_date, cutoff_version_id=cutoff_version_id,
        start_at=start_at, end_at=end_at, source_timezone=settings.source_timezone,
        source_timezone_confirmed=settings.source_timezone_confirmed,
        valid_quality_codes=settings.valid_plc_quality_codes,
        max_gap_minutes=settings.max_counter_gap_minutes, truncated=len(rows) == MAX_QUERY_ROWS,
    )
    reset_analysis = detect_dropcnt_reset_candidates(
        reset_rows, start_at=start_at, end_at=end_at, source_timezone=settings.source_timezone,
        source_timezone_confirmed=settings.source_timezone_confirmed,
        valid_quality_codes=settings.valid_plc_quality_codes,
        max_gap_minutes=settings.max_counter_gap_minutes, truncated=len(reset_rows) == MAX_QUERY_ROWS,
    )
    for event in reset_analysis["reset_candidates"]:
        timestamp = datetime.fromisoformat(event["decrease_sample"]["timestamp"])
        try:
            resolved_date, event_cutoff_id = resolve_production_date(timestamp, cutoff_versions)
            event_schedule = resolve_schedule_context(read_shift_versions(), resolved_date)
            shift = shift_for_timestamp(event_schedule, timestamp)
            event.update({"production_date": resolved_date, "cutoff_version_id": event_cutoff_id,
                "shift_schedule_version_id": event_schedule["applicable_version_id"],
                "shift_id": shift["id"] if shift else None,
                "shift_code": shift["shift_code"] if shift else None,
                "shift_name": shift["shift_name"] if shift else None,
                "shift_assignment": "ASSIGNED" if shift else "UNASSIGNED · schedule gap",
                "configuration_attribution": "EFFECTIVE CONFIGURATION RESOLVED"})
            event["proposed_scg_lot_number"] = None
            event["number_proposal_note"] = "Sequence/machine proposal withheld until SQL Lot sequence history and factory machine-code mapping are available."
        except (ProductionDayConfigurationError, ScheduleValidationError) as exc:
            event["configuration_attribution"] = f"UNRESOLVED · {exc}"
            event["shift_assignment"] = "UNASSIGNED · configuration unresolved"
        if event.get("production_date") == production_date:
            store.auto_lot_reset_snapshots[event["id"]] = event
    quality_counts = dict(Counter(str(row.get("_QUALITY")) for row in rows))
    quality_note = (f"Observed _QUALITY distribution: {quality_counts}. Only configured code(s) "
        f"{list(settings.valid_plc_quality_codes)} were included; these values have not been independently approved as a valid-quality policy.")
    gap_note = (f"Configured sample-gap threshold: {settings.max_counter_gap_minutes} minutes. "
        "This is a provisional review parameter, not a factory-approved operating rule.")
    result["warnings"] = list(dict.fromkeys([*result["warnings"], quality_note, gap_note,
        "Candidate synchronization and lot accounting remain SQL Server view responsibilities."]))
    for candidate in result["candidates"]:
        candidate["quality_counts"] = quality_counts
        candidate["accepted_quality_codes_configured"] = list(settings.valid_plc_quality_codes)
        candidate["max_gap_threshold_minutes"] = settings.max_counter_gap_minutes
        candidate["warnings"] = list(dict.fromkeys([*candidate["warnings"], quality_note, gap_note]))
    reviews = {item["candidate_id"]: item for item in store.auto_lot_candidate_reviews}
    candidates = [{**item, "operator_review": reviews.get(item["id"])} for item in result["candidates"]]
    for candidate in candidates:
        store.auto_lot_candidate_snapshots[candidate["id"]] = candidate
    preflight = getattr(source_repository, "_last_preflight", None) or {}
    sql_access = {key: preflight.get(key) for key in (
        "server", "instance", "database", "sql_login", "database_user", "sysadmin_member",
        "permission_checks", "select_access_verified", "read_only_permissions_verified",
        "write_capabilities_present", "source_queries_select_only_enforced")}
    return {**base, "available": True, "status": "LIVE SQL CONNECTED", **result,
        "candidates": candidates, "reset_candidates": reset_analysis["reset_candidates"],
        "reset_analysis_warnings": reset_analysis["warnings"], "observed_intervals": [],
        "quality_counts_observed": quality_counts, "sql_access": sql_access,
        "review_storage": "PROCESS LOCAL · RESET ON BACKEND RESTART"}


@app.post("/api/auto-lot/candidates/sync")
def sync_auto_lot_candidates(production_date: str | None = None) -> dict[str, Any]:
    if production_date is not None:
        try:
            parse_production_date(production_date)
        except ProductionDayConfigurationError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from None
    if not source_repository.settings.lot_window_source_confirmed:
        raise HTTPException(status_code=503, detail="The Lot-window source policy must be confirmed before synchronizing candidate windows.")
    try:
        detection = source_repository.auto_lot_detected_windows(production_date, MAX_QUERY_ROWS)
        synced = production_repository.sync_auto_lot_detected_windows(detection["rows"])
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    except SourceUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from None
    return {"source": detection["source"], "rows_seen": len(detection["rows"]),
        "truncated": detection["truncated"], "synchronized": synced, "warning": detection["warning"]}


def record_auto_lot_candidate_action(candidate_id: str, payload: AutoLotCandidateAction, action: str) -> dict[str, Any]:
    if not payload.reason.strip():
        raise HTTPException(status_code=422, detail="An operator reason is required.")
    try:
        cutoff_versions = read_cutoff_versions()
        selected_cutoff = cutoff_version_for_date(cutoff_versions, payload.production_date)
        production_day_window(payload.production_date, cutoff_versions)
        resolve_schedule_context(read_shift_versions(), payload.production_date)
    except (ProductionDayConfigurationError, ScheduleValidationError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    if selected_cutoff["id"] != payload.cutoff_version_id:
        raise HTTPException(status_code=409, detail="Production Day Cutoff changed; reload the selected date before recording candidate review.")
    if candidate_id not in store.auto_lot_candidate_snapshots:
        raise HTTPException(status_code=404, detail="Candidate evidence has not been loaded in this backend session; reload the live candidate list first.")
    if action == "DISMISSED" and any(value is not None for value in (payload.corrected_started_at, payload.corrected_ended_at, payload.corrected_drop_count)):
        raise HTTPException(status_code=422, detail="Dismissal cannot include candidate corrections.")
    if payload.corrected_started_at and payload.corrected_ended_at and payload.corrected_ended_at <= payload.corrected_started_at:
        raise HTTPException(status_code=422, detail="Corrected end must be after corrected start.")
    record = {"candidate_id": candidate_id, "production_date": payload.production_date,
        "cutoff_version_id": payload.cutoff_version_id, "action": action, "reason": payload.reason.strip(),
        "corrected_started_at": payload.corrected_started_at.isoformat() if payload.corrected_started_at else None,
        "corrected_ended_at": payload.corrected_ended_at.isoformat() if payload.corrected_ended_at else None,
        "corrected_drop_count": payload.corrected_drop_count, "official_lot_id": None,
        "storage": "PROCESS LOCAL · RESET ON BACKEND RESTART",
        "recorded_at": datetime.now(ZoneInfo(PRODUCTION_TIMEZONE)).isoformat()}
    store.auto_lot_candidate_reviews.append(record)
    return record


@app.post("/api/auto-lot/candidates/{candidate_id}/review")
def review_auto_lot_candidate(candidate_id: str, payload: AutoLotCandidateAction) -> dict[str, Any]:
    return record_auto_lot_candidate_action(candidate_id, payload, "REVIEWED")


@app.post("/api/auto-lot/candidates/{candidate_id}/dismiss")
def dismiss_auto_lot_candidate(candidate_id: str, payload: AutoLotCandidateAction) -> dict[str, Any]:
    return record_auto_lot_candidate_action(candidate_id, payload, "DISMISSED")


@app.get("/api/auto-lot/drafts")
def list_auto_lot_drafts(production_date: str) -> dict[str, Any]:
    try:
        cutoff_versions = read_cutoff_versions()
        schedule = resolve_schedule_context(read_shift_versions(), production_date)
        day_window = production_day_window(production_date, cutoff_versions)
        cutoff_version_id = cutoff_version_for_date(cutoff_versions, production_date)["id"]
    except (ScheduleValidationError, ProductionDayConfigurationError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    rows = []
    for draft in store.auto_lot_drafts:
        if draft["production_date"] != production_date:
            continue
        schedule_mismatch = draft_requires_schedule_review(draft, schedule["applicable_version_id"])
        cutoff_mismatch = draft.get("cutoff_version_id") != cutoff_version_id
        requires_review = schedule_mismatch or cutoff_mismatch
        rows.append({**draft, "requires_schedule_review": schedule_mismatch,
            "requires_cutoff_review": cutoff_mismatch, "requires_configuration_review": requires_review,
            "review_status": "REVIEW REQUIRED · CONFIGURATION VERSION MISMATCH" if requires_review else draft["status"]})
    return {"production_date": production_date, "production_day_window": day_window,
        "cutoff_version_id": cutoff_version_id,
        "applicable_schedule_version_id": schedule["applicable_version_id"], "drafts": rows,
        "mode": "MOCK ONLY · NO PLC QUERY"}


@app.post("/api/auto-lot/drafts", status_code=201)
def create_auto_lot_draft(payload: AutoLotDraftCreate) -> dict[str, Any]:
    try:
        cutoff_versions = read_cutoff_versions()
        selected = resolve_schedule_context(read_shift_versions(), payload.production_date)
        resolved_date, cutoff_version_id = resolve_production_date(payload.started_at, cutoff_versions)
        day_window = production_day_window(payload.production_date, cutoff_versions)
    except (ScheduleValidationError, ProductionDayConfigurationError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    if resolved_date != payload.production_date:
        raise HTTPException(status_code=422, detail=f"Draft start resolves to Production Date {resolved_date}, not the selected date")
    if payload.cutoff_version_id is not None and payload.cutoff_version_id != cutoff_version_id:
        raise HTTPException(status_code=409, detail="Production Day Cutoff version changed; reload the selected Production Date before adding this draft")
    version = next((item for item in read_shift_versions() if item["id"] == payload.schedule_version_id), None)
    if version is None:
        raise HTTPException(status_code=404, detail="Shift Schedule version was not found")
    if selected["applicable_version_id"] != payload.schedule_version_id:
        raise HTTPException(status_code=409, detail="Draft creation requires the schedule version applicable to the selected Production Date")
    if payload.ended_at is not None and payload.ended_at < payload.started_at:
        raise HTTPException(status_code=422, detail="Draft end must be after its start")
    try:
        validate_draft_interval(selected, payload.shift_id, payload.started_at, payload.ended_at)
    except ScheduleValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    draft = {"id": store.next_id(), "production_date": payload.production_date,
        "schedule_version_id": payload.schedule_version_id, "cutoff_version_id": cutoff_version_id,
        "production_day_window": day_window, "shift_id": payload.shift_id,
        "started_at": payload.started_at.isoformat(),
        "ended_at": payload.ended_at.isoformat() if payload.ended_at else None,
        "raw_drop_count": payload.raw_drop_count, "operator_confirmed_drop_count": None,
        "status": "PROVISIONAL · MOCK SOURCE", "source": "USER-SUPPLIED MOCK REVIEW DATA · NO PLC QUERY",
        "official_lot_id": None, "audit_history": []}
    store.auto_lot_drafts.append(draft)
    return draft


@app.post("/api/auto-lot/drafts/{draft_id}/review")
def review_auto_lot_draft(draft_id: int, payload: AutoLotDraftReview) -> dict[str, Any]:
    draft = next((item for item in store.auto_lot_drafts if item["id"] == draft_id), None)
    if draft is None:
        raise HTTPException(status_code=404, detail="Draft ID was not found")
    try:
        versions = read_shift_versions()
        current = resolve_schedule_context(versions, draft["production_date"])
    except ScheduleValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    version = next((item for item in versions if item["id"] == payload.schedule_version_id), None)
    if version is None or payload.schedule_version_id != current["applicable_version_id"]:
        raise HTTPException(status_code=409, detail="Review must explicitly use the schedule version currently applicable to the draft Production Date")
    try:
        cutoff_versions = read_cutoff_versions()
        resolved_date, cutoff_version_id = resolve_production_date(payload.started_at, cutoff_versions)
    except ProductionDayConfigurationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    if resolved_date != draft["production_date"]:
        raise HTTPException(status_code=422, detail=f"Corrected start resolves to Production Date {resolved_date}, not the draft date")
    if payload.cutoff_version_id is not None and payload.cutoff_version_id != cutoff_version_id:
        raise HTTPException(status_code=409, detail="Production Day Cutoff version changed; reload before reviewing this draft")
    if payload.ended_at is not None and payload.ended_at < payload.started_at:
        raise HTTPException(status_code=422, detail="Draft end must be after its start")
    try:
        validate_draft_interval(current, payload.shift_id, payload.started_at, payload.ended_at)
    except ScheduleValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    reason = payload.reason.strip()
    if not reason:
        raise HTTPException(status_code=422, detail="A review reason is required")
    draft["audit_history"].append({"schedule_version_id": draft["schedule_version_id"],
        "cutoff_version_id": draft.get("cutoff_version_id"), "shift_id": draft["shift_id"],
        "started_at": draft["started_at"], "ended_at": draft["ended_at"],
        "operator_confirmed_drop_count": draft["operator_confirmed_drop_count"], "reason": reason,
        "recorded_at": datetime.now(ZoneInfo(PRODUCTION_TIMEZONE)).isoformat()})
    draft.update({"schedule_version_id": payload.schedule_version_id,
        "cutoff_version_id": cutoff_version_id, "shift_id": payload.shift_id,
        "started_at": payload.started_at.isoformat(),
        "ended_at": payload.ended_at.isoformat() if payload.ended_at else None,
        "operator_confirmed_drop_count": payload.operator_confirmed_drop_count,
        "status": "PROVISIONAL · OPERATOR REVIEWED · MOCK ONLY"})
    return {**draft, "official_lot_id": None}


@app.post("/api/auto-lot/drafts/{draft_id}/dismiss")
def dismiss_auto_lot_draft(draft_id: int, payload: AutoLotDraftDismiss) -> dict[str, Any]:
    draft = next((item for item in store.auto_lot_drafts if item["id"] == draft_id), None)
    if draft is None:
        raise HTTPException(status_code=404, detail="Draft ID was not found")
    reason = payload.reason.strip()
    if not reason:
        raise HTTPException(status_code=422, detail="A dismissal reason is required")
    if draft["status"].startswith("DISMISSED"):
        raise HTTPException(status_code=409, detail="Draft was already dismissed")
    draft["audit_history"].append({"schedule_version_id": draft["schedule_version_id"],
        "shift_id": draft["shift_id"], "raw_drop_count": draft["raw_drop_count"],
        "reason": reason, "action": "DISMISS",
        "recorded_at": datetime.now(ZoneInfo(PRODUCTION_TIMEZONE)).isoformat()})
    draft["status"] = "DISMISSED · MOCK ONLY"
    draft["official_lot_id"] = None
    return draft


@app.get("/api/press-lots/summary")
def press_lot_summary(production_date: str | None = None, limit: int = 1000) -> dict[str, Any]:
    if production_date is not None:
        try:
            parse_production_date(production_date)
        except ProductionDayConfigurationError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from None
    if not 1 <= limit <= MAX_QUERY_ROWS:
        raise HTTPException(status_code=422, detail=f"limit must be between 1 and {MAX_QUERY_ROWS}.")
    rows = source_call(lambda: source_repository.press_lot_summary(production_date, limit))
    return {"source": "OMAG.omagmes.v_PressLotSummary", "rows": rows, "calculation_authority": "SQL SERVER VIEW"}


@app.get("/api/press-lots/windows")
def list_press_lot_windows(include_deleted: bool = False) -> dict[str, Any]:
    rows = source_call(lambda: production_repository.list_auto_lot_windows(include_deleted=include_deleted))
    return {"source": "OMAG.omagmes.AutoLotCandidateWindow", "rows": rows}


@app.get("/api/press-lots/windows/{window_id}/history")
def press_lot_window_history(window_id: int) -> dict[str, Any]:
    if window_id <= 0:
        raise HTTPException(status_code=422, detail="Window ID must be positive.")
    rows = source_call(lambda: production_repository.auto_lot_window_history(window_id))
    return {"candidate_window_id": window_id, "rows": rows}


@app.get("/api/press-lots/acc")
def press_lot_acc(start_at: datetime, end_at: datetime, limit: int = 5000) -> dict[str, Any]:
    validate_source_window(start_at, end_at, limit)
    rows = source_call(lambda: source_repository.press_lot_acc(start_at, end_at, limit))
    return {"source": "OMAG.omagmes.v_PressLotACC", "rows": rows, "calculation_authority": "SQL SERVER VIEW"}


@app.post("/api/press-lots/windows", status_code=201)
def create_press_lot_window(payload: AutoLotWindowCreate) -> dict[str, Any]:
    start_at = normalize_operator_lot_time(payload.start_at)
    end_at = normalize_operator_lot_time(payload.end_at) if payload.end_at else None
    if end_at is not None and end_at <= start_at:
        raise HTTPException(status_code=422, detail="End time must be after start time.")
    try:
        production_date, cutoff_version_id = resolve_production_date(start_at, read_cutoff_versions())
    except ProductionDayConfigurationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    start_local = start_at.replace(tzinfo=None) if start_at.tzinfo else start_at
    end_local = end_at.replace(tzinfo=None) if end_at and end_at.tzinfo else end_at
    candidate_key = f"manual:{os.urandom(16).hex()}"
    try:
        return production_repository.create_auto_lot_window(candidate_key, start_local, end_local,
            payload.operator_id.strip(), payload.reason.strip(), production_date, cutoff_version_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    except SourceUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from None


@app.patch("/api/press-lots/windows/{window_id}")
def edit_press_lot_window(window_id: int, payload: AutoLotWindowEdit) -> dict[str, Any]:
    if window_id <= 0:
        raise HTTPException(status_code=422, detail="Window ID must be positive.")
    if payload.end_at is not None and payload.end_at <= payload.start_at:
        raise HTTPException(status_code=422, detail="End time must be after start time.")
    zone = ZoneInfo(PRODUCTION_TIMEZONE)
    start_value = payload.start_at.astimezone(zone) if payload.start_at.tzinfo else payload.start_at
    end_value = payload.end_at.astimezone(zone) if payload.end_at and payload.end_at.tzinfo else payload.end_at
    start_local = start_value.replace(tzinfo=None) if start_value.tzinfo else start_value
    end_local = end_value.replace(tzinfo=None) if end_value and end_value.tzinfo else end_value
    try:
        return production_repository.edit_auto_lot_candidate_window(window_id, start_local, end_local,
            payload.operator_id.strip(), payload.reason.strip())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    except SourceUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from None


@app.post("/api/press-lots/windows/{window_id}/split")
def split_press_lot_window(window_id: int, payload: AutoLotWindowSplit) -> dict[str, Any]:
    if window_id <= 0:
        raise HTTPException(status_code=422, detail="Window ID must be positive.")
    split_at = normalize_operator_lot_time(payload.split_at)
    split_at = split_at.replace(tzinfo=None) if split_at.tzinfo else split_at
    try:
        return production_repository.split_auto_lot_window(window_id, split_at,
            f"split:{window_id}:{os.urandom(12).hex()}", payload.operator_id.strip(), payload.reason.strip())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    except SourceUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from None


@app.post("/api/press-lots/windows/{window_id}/merge")
def merge_press_lot_window(window_id: int, payload: AutoLotWindowMerge) -> dict[str, Any]:
    if window_id <= 0:
        raise HTTPException(status_code=422, detail="Window ID must be positive.")
    try:
        return production_repository.merge_auto_lot_windows(window_id, payload.source_window_id,
            payload.operator_id.strip(), payload.reason.strip())
    except SourceUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from None


@app.post("/api/press-lots/windows/{window_id}/dismiss")
def dismiss_press_lot_window(window_id: int, payload: AutoLotWindowDismiss) -> dict[str, Any]:
    if window_id <= 0:
        raise HTTPException(status_code=422, detail="Window ID must be positive.")
    try:
        return production_repository.dismiss_auto_lot_window(window_id, payload.operator_id.strip(), payload.reason.strip())
    except SourceUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from None


@app.post("/api/press-lots/windows/{window_id}/restore")
def restore_press_lot_window(window_id: int, payload: AutoLotWindowRestore) -> dict[str, Any]:
    if window_id <= 0:
        raise HTTPException(status_code=422, detail="Window ID must be positive.")
    try:
        return production_repository.restore_auto_lot_window(window_id, payload.operator_id.strip(), payload.reason.strip())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    except SourceUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from None


@app.post("/api/press-lots/windows/{window_id}/plan")
def assign_press_lot_plan(window_id: int, payload: AutoLotPlanAssign) -> dict[str, Any]:
    if window_id <= 0:
        raise HTTPException(status_code=422, detail="Window ID must be positive.")
    try:
        plans = source_repository.production_plan_snapshots(MAX_QUERY_ROWS)
        if plans["truncated"]:
            raise HTTPException(status_code=503, detail="Production Plan list is truncated; refresh or narrow the source before assignment.")
        matches = [plan for plan in plans["plans"] if plan["plan_key"] == payload.plan_key]
        if len(matches) != 1:
            raise HTTPException(status_code=422, detail="Selected plan fingerprint is no longer present uniquely in the current plan view.")
        return production_repository.assign_auto_lot_plan(window_id, matches[0],
            payload.operator_id.strip(), payload.reason.strip())
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    except SourceUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from None


@app.post("/api/press-lots/windows/{window_id}/classify")
def classify_press_lot_window(window_id: int, payload: AutoLotCandidateClassify) -> dict[str, Any]:
    if window_id <= 0:
        raise HTTPException(status_code=422, detail="Window ID must be positive.")
    try:
        return production_repository.classify_auto_lot_candidate(window_id, payload.product_id,
            payload.color_code.strip(), payload.operator_id.strip(), payload.reason.strip())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    except SourceUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from None
