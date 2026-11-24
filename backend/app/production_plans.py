from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Mapping


# Catalog-inspected columns from OMAG.dbo.vw_OmagPlan. No row ID or primary
# key is exposed by this view, so a fingerprint identifies a snapshot only.
PLAN_VIEW_COLUMNS = (
    "Company", "Plant", "Shift", "PlanWeek", "VersionNo", "PlanName",
    "Machine", "MaterialCode", "MaterialName", "PlanWeight", "PlanCount",
    "StartTime", "Duration", "OperationCode", "SetupDuration",
    "CleaningDuration", "StartupDuration", "MS", "ES", "OS", "MC",
    "EC", "OC", "MSU", "ESU", "OSU", "Contractor", "BUName",
    "Description",
)


def _json_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def plan_snapshot(row: Mapping[str, Any]) -> dict[str, Any]:
    """Return a stable, loss-minimizing JSON snapshot and content fingerprint."""
    snapshot = {name: _json_value(row.get(name)) for name in PLAN_VIEW_COLUMNS}
    serialized = json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return {
        "plan_key": hashlib.sha256(serialized.encode("utf-8")).hexdigest(),
        "snapshot": snapshot,
        "snapshot_json": serialized,
        "identity_kind": "CONTENT_FINGERPRINT_NOT_SOURCE_ID",
    }


def aggregate_plan_rows(rows: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Group identical view rows so assignment can fail on indistinguishable plans."""
    grouped: dict[str, dict[str, Any]] = {}
    for row in rows:
        record = plan_snapshot(row)
        key = record["plan_key"]
        if key in grouped:
            grouped[key]["duplicate_count"] += 1
        else:
            snapshot = record["snapshot"]
            grouped[key] = {
                "plan_key": key,
                "snapshot": snapshot,
                "duplicate_count": 1,
                "identity_kind": record["identity_kind"],
                # This is scheduling context only; it is never used as Lot start.
                "planned_start": snapshot.get("StartTime"),
                "material_code": snapshot.get("MaterialCode"),
                "material_name": snapshot.get("MaterialName"),
                "plan_name": snapshot.get("PlanName"),
                "plan_count": snapshot.get("PlanCount"),
                "machine": snapshot.get("Machine"),
                "shift": snapshot.get("Shift"),
            }
    return sorted(
        grouped.values(),
        key=lambda plan: (
            str(plan.get("planned_start") or ""),
            str(plan.get("plan_name") or ""),
            str(plan.get("material_code") or ""),
            str(plan["plan_key"]),
        ),
        reverse=True,
    )