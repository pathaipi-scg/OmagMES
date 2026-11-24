from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .sql_source import DROP_COUNTER_TAG

BANGKOK = "Asia/Bangkok"


def _moment(value: Any, zone: ZoneInfo) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            return None
    else:
        return None
    # PRESS._TIMESTAMP is SQL datetime containing Thailand local wall time.
    # Keep its displayed clock fields verbatim; never interpret them as UTC.
    return parsed.replace(tzinfo=None).replace(tzinfo=zone)


def detect_dropcnt_envelope(
    observations: list[dict[str, Any]],
    *,
    production_date: str,
    cutoff_version_id: int,
    start_at: datetime,
    end_at: datetime,
    source_timezone: str,
    source_timezone_confirmed: bool,
    valid_quality_codes: tuple[int, ...],
    max_gap_minutes: int | None,
    truncated: bool = False,
) -> dict[str, Any]:
    """Compatibility response: Python intentionally does not calculate Press Diff or ACC."""
    del observations, source_timezone, source_timezone_confirmed, valid_quality_codes, max_gap_minutes
    return {
        "production_date": production_date,
        "cutoff_version_id": cutoff_version_id,
        "window": {"start_at": start_at.isoformat(), "end_at_exclusive": end_at.isoformat(), "interval_semantics": "[start, end)"},
        "candidates": [],
        "warnings": [
            "Press Diff, PressQty and Lot ACC are calculated only by the SQL Server views; Python does not estimate Drops.",
            "Candidate windows are available only after the DBA-approved SQL candidate schema and synchronization are installed.",
            *( ["The source query reached its row limit; reset evidence may be incomplete."] if truncated else [] ),
        ],
        "source_tag": DROP_COUNTER_TAG,
        "source": "LIVE PRESS · READ ONLY",
        "truncated": truncated,
    }


def preview_dropcnt_observation_intervals(
    observations: list[dict[str, Any]],
    *,
    source_timezone: str,
    source_timezone_confirmed: bool,
    valid_quality_codes: tuple[int, ...],
    truncated: bool = False,
) -> dict[str, Any]:
    """Deprecated compatibility API: activity envelopes are no longer Lots."""
    del observations, source_timezone, source_timezone_confirmed, valid_quality_codes
    return {
        "intervals": [],
        "warnings": [
            "Daily activity envelopes are disabled; Lot boundaries require DropCnt zero transitions.",
            *( ["PRESS result reached its row limit; complete history is unavailable."] if truncated else [] ),
        ],
        "truncated": truncated,
    }


def detect_dropcnt_lots(
    observations: list[dict[str, Any]],
    *,
    source_timezone: str,
    source_timezone_confirmed: bool,
    valid_quality_codes: tuple[int, ...],
    truncated: bool = False,
) -> dict[str, Any]:
    """Build read-only Lot proposals from confirmed zero transitions only.

    A Lot begins at a positive observation immediately following an observed
    zero. It stays open through plateaus, elapsed time, AutoRun changes, and
    nonzero counter decreases. Only an observed exact zero closes an open Lot.
    An initial positive value is not enough to invent a start; its start remains
    unknown until a subsequent confirmed zero and a later positive value.
    """
    warnings = [
        "Lot proposals use DropCnt only: a confirmed 0-to-positive transition starts a Lot and an exact zero closes it.",
        "Plateaus, elapsed time, AutoRun transitions, and nonzero decreases do not split a Lot.",
        "A positive counter at the beginning of available history has no inferred start; earlier source history is required.",
        "Proposals are read-only and are not persisted as official Lots.",
    ]
    if truncated:
        return {"lots": [], "warnings": warnings + ["DropCnt history reached its row limit; Lots are withheld because boundaries may be incomplete."], "truncated": True}
    if not valid_quality_codes:
        return {"lots": [], "warnings": warnings + ["No configured PLC quality codes are available; DropCnt Lots are withheld."], "truncated": False}
    try:
        zone = ZoneInfo(source_timezone)
    except ZoneInfoNotFoundError:
        return {"lots": [], "warnings": warnings + ["Configured source timezone is unavailable; DropCnt Lots are withheld."], "truncated": False}

    del source_timezone_confirmed  # Retained for compatibility; PRESS timestamps are confirmed Bangkok wall time.
    warnings.append("PRESS._TIMESTAMP is interpreted directly as Asia/Bangkok local wall-clock time; no UTC conversion is applied.")
    by_time: dict[datetime, list[dict[str, Any]]] = {}
    invalid_count = 0
    invalid_times: set[datetime] = set()
    for row in observations:
        if row.get("_NAME") != DROP_COUNTER_TAG:
            continue
        moment = _moment(row.get("_TIMESTAMP"), zone)
        if moment is None:
            invalid_count += 1
            continue
        by_time.setdefault(moment, []).append(row)

    samples: list[tuple[datetime, int, int]] = []
    conflicting_times = 0
    for moment, rows_at_time in by_time.items():
        normalized: list[tuple[int, int, int]] = []
        for row in rows_at_time:
            try:
                raw_value = row.get("_VALUE")
                value = int(raw_value)
                quality = int(row.get("_QUALITY"))
                source_id = int(row.get("id"))
                if float(raw_value) != value or value < 0 or quality not in valid_quality_codes:
                    raise ValueError
                normalized.append((source_id, value, quality))
            except (TypeError, ValueError, OverflowError):
                invalid_count += 1
                invalid_times.add(moment)
        identities = {(value, quality) for _, value, quality in normalized}
        if len(identities) > 1:
            conflicting_times += 1
            invalid_times.add(moment)
            continue
        if normalized and moment not in invalid_times:
            source_id, value, _ = min(normalized)
            samples.append((moment, source_id, value))
    samples.sort(key=lambda item: (item[0], item[1]))

    lots: list[dict[str, Any]] = []
    previous_value: int | None = None
    active: dict[str, Any] | None = None
    nonzero_decreases = 0
    samples_by_time = {sample[0]: sample for sample in samples}
    for moment in sorted(set(samples_by_time) | invalid_times):
        if moment in invalid_times:
            previous_value = None
            continue
        _, source_id, value = samples_by_time[moment]
        if active is not None and value == 0:
            active.update({
                "proposed_end_at": moment.isoformat(),
                "end_source_id": source_id,
                "last_observed_at": moment.isoformat(),
                "last_source_id": source_id,
                "status": "CLOSED · RESET TO ZERO OBSERVED",
            })
            lots.append(active)
            active = None
        elif active is None and previous_value == 0 and value > 0:
            active = {
                "id": f"dropcnt-lot:{source_id}",
                "proposed_start_at": moment.isoformat(),
                "proposed_end_at": None,
                "start_source_id": source_id,
                "end_source_id": None,
                "last_observed_at": moment.isoformat(),
                "last_source_id": source_id,
                "status": "OPEN · AWAITING RESET TO ZERO",
                "timestamp_basis": "ASIA/BANGKOK · SQL LOCAL WALL CLOCK",
                "proposed_lot_number": None,
                "number_status": "WITHHELD · PRODUCTION DATE/SHIFT/MACHINE CONFIGURATION NOT VERIFIED",
                "official_lot_id": None,
            }
        elif active is not None:
            if previous_value is not None and 0 < value < previous_value:
                nonzero_decreases += 1
            active["last_observed_at"] = moment.isoformat()
            active["last_source_id"] = source_id
        previous_value = value

    if active is not None:
        lots.append(active)
    if invalid_count:
        warnings.append(f"{invalid_count} invalid or unaccepted-quality DropCnt observations were excluded.")
    if conflicting_times:
        warnings.append(f"{conflicting_times} timestamps had conflicting DropCnt records; those timestamps were excluded.")
    if nonzero_decreases:
        warnings.append(f"{nonzero_decreases} nonzero decrease(s) were retained inside their Lot and did not close it.")
    if not samples:
        warnings.append("No valid DropCnt observations were available.")
    return {
        "lots": lots,
        "warnings": list(dict.fromkeys(warnings)),
        "truncated": False,
        "history": {
            "valid_sample_count": len(samples),
            "invalid_sample_count": invalid_count,
            "conflicting_timestamp_count": conflicting_times,
            "nonzero_decrease_count": nonzero_decreases,
            "first_observed_at": samples[0][0].isoformat() if samples else None,
            "last_observed_at": samples[-1][0].isoformat() if samples else None,
            "timestamp_basis": "ASIA/BANGKOK · SQL LOCAL WALL CLOCK",
        },
    }


def detect_dropcnt_reset_candidates(
    observations: list[dict[str, Any]],
    *,
    start_at: datetime,
    end_at: datetime,
    source_timezone: str,
    source_timezone_confirmed: bool,
    valid_quality_codes: tuple[int, ...],
    max_gap_minutes: int | None,
    truncated: bool = False,
) -> dict[str, Any]:
    """Detect exact positive-to-zero reset evidence; never calculate quantity."""
    del max_gap_minutes  # Gap thresholds do not authorize omitting or estimating SQL Diff.
    warnings = [
        "Only a positive-to-exact-zero transition is reset evidence; nonzero decreases do not close a Lot.",
        "A reset-to-zero does not prove a Product/Color change or create an official Lot.",
        "Python returns no Press Diff, PressQty, post-reset quantity, or Lot ACC. SQL Server views are the calculation authority.",
    ]
    if truncated:
        return {"reset_candidates": [], "warnings": warnings + ["PRESS result reached the row limit; complete reset bracketing is unavailable."], "truncated": True}
    if source_timezone != BANGKOK:
        return {"reset_candidates": [], "warnings": warnings + ["A configured Asia/Bangkok wall-clock basis is required to resolve the requested window."], "truncated": False}
    if not valid_quality_codes:
        return {"reset_candidates": [], "warnings": warnings + ["No PLC quality codes are configured; reset evidence is withheld."], "truncated": False}
    try:
        zone = ZoneInfo(source_timezone)
    except ZoneInfoNotFoundError:
        return {"reset_candidates": [], "warnings": warnings + ["Configured source timezone is unavailable."], "truncated": False}

    del source_timezone_confirmed  # Retained for compatibility; SQL timestamps are Bangkok wall time.
    window_start = start_at.replace(tzinfo=None).replace(tzinfo=zone)
    window_end = end_at.replace(tzinfo=None).replace(tzinfo=zone)
    indexed: list[tuple[datetime, int, dict[str, Any]]] = []
    invalid_times: set[datetime] = set()
    timestamps: dict[datetime, list[dict[str, Any]]] = {}
    for row in observations:
        if row.get("_NAME") != DROP_COUNTER_TAG:
            continue
        moment = _moment(row.get("_TIMESTAMP"), zone)
        if moment is None:
            warnings.append("A source row with invalid timestamp was excluded from reset evidence.")
            continue
        timestamps.setdefault(moment, []).append(row)
    for moment, rows in timestamps.items():
        identities = {(str(row.get("_VALUE")), str(row.get("_QUALITY"))) for row in rows}
        if len(identities) != 1:
            invalid_times.add(moment)
            warnings.append(f"Conflicting records at {moment.isoformat()} were excluded from reset evidence.")
            continue
        if len(rows) > 1:
            warnings.append(f"Duplicate observations at {moment.isoformat()} were represented once for reset evidence.")
        row = min(rows, key=lambda item: (0, int(item.get("id", 0))) if str(item.get("id", "")).isdigit() else (1, str(item.get("id", ""))))
        try:
            value = int(row.get("_VALUE"))
            quality = int(row.get("_QUALITY"))
            numeric = float(row.get("_VALUE"))
            source_id = int(row.get("id"))
        except (TypeError, ValueError, OverflowError):
            invalid_times.add(moment)
            warnings.append(f"Invalid counter or quality value at {moment.isoformat()} was excluded from reset evidence.")
            continue
        if numeric != value or value < 0 or quality not in valid_quality_codes:
            invalid_times.add(moment)
            warnings.append(f"Invalid counter value or unaccepted-quality sample at {moment.isoformat()} was excluded from reset evidence.")
            continue
        indexed.append((moment, source_id, {"value": value, "quality": quality}))

    indexed.sort(key=lambda item: (item[0], item[1]))
    events: list[dict[str, Any]] = []
    for before, decreased in zip(indexed, indexed[1:]):
        before_at, before_id, before_data = before
        decreased_at, decreased_id, decreased_data = decreased
        if not window_start <= decreased_at < window_end or before_data["value"] <= 0 or decreased_data["value"] != 0:
            continue
        event_id = hashlib.sha256(f"{before_id}|{decreased_id}|{before_at.isoformat()}|{decreased_at.isoformat()}".encode("utf-8")).hexdigest()[:20]
        following = next((sample for sample in indexed if (sample[0], sample[1]) > (decreased_at, decreased_id)), None)
        if any(before_at < invalid_at <= decreased_at for invalid_at in invalid_times):
            warnings.append("A decrease spanning an invalid/conflicting sample was excluded from reset evidence.")
            continue
        event_warnings = [
            "Exact zero is observed; this closes only the counter-defined Auto Lot and does not infer a Product/Color change.",
            "The zero sample timestamp is the observed reset time, not an inferred timestamp from any nonzero decrease.",
        ]
        events.append({
            "id": f"dropcnt-reset:{event_id}",
            "source_tag": DROP_COUNTER_TAG,
            "before_sample": {"source_id": str(before_id), "timestamp": before_at.isoformat(), "value": before_data["value"]},
            "decrease_sample": {"source_id": str(decreased_id), "timestamp": decreased_at.isoformat(), "value": decreased_data["value"]},
            "reset_time_interval": {"earliest_exclusive": before_at.isoformat(), "latest_inclusive": decreased_at.isoformat()},
            "restart_sample": None if following is None else {"source_id": str(following[1]), "timestamp": following[0].isoformat(), "value": following[2]["value"]},
            "timestamp_basis": "ASIA/BANGKOK · SQL LOCAL WALL CLOCK",
            "candidate_status": "BOUNDARY EVIDENCE · SQL WINDOW SYNC REQUIRED",
            "official_lot_id": None,
            "warnings": event_warnings,
        })
    if not events:
        warnings.append("No valid positive-to-zero reset was observed in this bounded window.")
    return {
        "reset_candidates": events,
        "warnings": list(dict.fromkeys(warnings)),
        "timestamp_basis": "ASIA/BANGKOK · SQL LOCAL WALL CLOCK",
        "official_lot_creation": False,
        "truncated": False,
    }
