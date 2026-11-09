from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time, timedelta
from typing import Any, Iterable
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


BANGKOK = "Asia/Bangkok"
PRESS_COUNTER_TAG = "OPC.OMAG.OMAG.PRESS.ProductCnt"
AUTORUN_TAG = "OPC.OMAG.OMAG.PRESS.AutoRun"


def _timestamp(value: Any, zone: ZoneInfo) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            return None
    else:
        return None
    return parsed.replace(tzinfo=zone) if parsed.tzinfo is None else parsed.astimezone(zone)


def _identity(value: Any) -> tuple[int, str]:
    try:
        return (0, f"{int(value):020d}")
    except (TypeError, ValueError):
        return (1, str(value))


def _bucket(moment: datetime) -> date:
    local = moment.astimezone(ZoneInfo(BANGKOK))
    return local.date() if local.time() >= time(7, 0) else local.date() - timedelta(days=1)


def calculate_counter_window(
    observations: Iterable[dict[str, Any]],
    start_at: datetime,
    end_at: datetime,
    *,
    value_key: str = "_VALUE",
    timestamp_key: str = "_TIMESTAMP",
    quality_key: str = "_QUALITY",
    tag_key: str = "_NAME",
    allowed_tags: set[str] | None = None,
    valid_quality_codes: tuple[int, ...] = (),
    source_timezone: str = "",
    source_timezone_confirmed: bool = False,
    max_gap_minutes: int | None = None,
) -> dict[str, Any]:
    """Sum measured counter deltas only; reset/gap/quality uncertainty is explicit."""
    warnings: list[str] = []
    if not valid_quality_codes:
        return {"suggestion": None, "warnings": ["PLC quality semantics have not been approved; no counter quantity was calculated."], "samples_used": 0}
    if not source_timezone_confirmed or source_timezone != BANGKOK:
        return {"suggestion": None, "warnings": ["Source timestamp timezone has not been verified as Asia/Bangkok."], "samples_used": 0}
    if start_at.tzinfo is None or end_at.tzinfo is None or start_at >= end_at:
        return {"suggestion": None, "warnings": ["A valid timezone-aware Lot window is required."], "samples_used": 0}
    if max_gap_minutes is None or max_gap_minutes <= 0:
        return {"suggestion": None, "warnings": ["No approved maximum counter-gap threshold is configured; no counter quantity was calculated."], "samples_used": 0}
    try:
        zone = ZoneInfo(source_timezone)
    except ZoneInfoNotFoundError:
        return {"suggestion": None, "warnings": ["Configured source timezone is unavailable."], "samples_used": 0}

    raw = list(observations)
    parsed: list[tuple[datetime, tuple[int, str], dict[str, Any]]] = []
    for row in raw:
        if allowed_tags is not None and row.get(tag_key) not in allowed_tags:
            continue
        moment = _timestamp(row.get(timestamp_key), zone)
        if moment is None:
            warnings.append("One or more observations have an invalid timestamp and were excluded.")
            continue
        parsed.append((moment, _identity(row.get("id")), row))

    original_times = [item[0] for item in parsed]
    if any(right < left for left, right in zip(original_times, original_times[1:])):
        warnings.append("Out-of-order source observations were sorted by timestamp and source ID.")
    parsed.sort(key=lambda item: (item[0], item[1]))

    by_timestamp: dict[datetime, list[tuple[datetime, tuple[int, str], dict[str, Any]]]] = defaultdict(list)
    for item in parsed:
        by_timestamp[item[0]].append(item)
    unique: list[tuple[datetime, tuple[int, str], dict[str, Any]]] = []
    conflicted_times: set[datetime] = set()
    for moment, items in by_timestamp.items():
        if len(items) > 1:
            values = {(str(item[2].get(value_key)), str(item[2].get(quality_key))) for item in items}
            if len(values) > 1:
                warnings.append("Conflicting duplicate timestamps were excluded.")
                conflicted_times.add(moment)
                continue
            warnings.append("Duplicate timestamps were deduplicated by source ID.")
        unique.append(items[0])
    unique.sort(key=lambda item: (item[0], item[1]))

    valid_samples: list[tuple[datetime, int, dict[str, Any]]] = []
    invalid_times: set[datetime] = set(conflicted_times)
    for moment, _source_id, row in unique:
        quality = row.get(quality_key)
        try:
            quality_value = int(quality)
        except (TypeError, ValueError):
            quality_value = -1
        try:
            count = int(row.get(value_key))
            numeric_value = float(row.get(value_key))
        except (TypeError, ValueError, OverflowError):
            warnings.append("Invalid counter values were excluded.")
            invalid_times.add(moment)
            continue
        if quality_value not in valid_quality_codes or numeric_value != count or count < 0:
            warnings.append("Bad-quality or invalid counter values were excluded.")
            invalid_times.add(moment)
            continue
        valid_samples.append((moment, count, row))

    start_local = start_at.astimezone(zone)
    end_local = end_at.astimezone(zone)
    warnings.extend([
        "The Lot start boundary has no exact counter sample; partial Drops before the first in-window sample are unknown."
    ] if not any(item[0] == start_local for item in valid_samples) else [])
    warnings.extend([
        "The Lot end boundary has no exact counter sample; partial Drops after the last in-window sample are unknown."
    ] if not any(item[0] == end_local for item in valid_samples) else [])
    total: int | None = None
    used = 0
    previous: tuple[datetime, int, dict[str, Any]] | None = None
    for current in valid_samples:
        moment, value, _row = current
        if previous is None:
            previous = current
            reset_at = datetime.combine(_bucket(moment), time(7, 0), tzinfo=zone)
            reset_gap_seconds = (moment - reset_at).total_seconds()
            if start_local <= reset_at < end_local and moment >= reset_at:
                gap_ok = reset_gap_seconds <= max_gap_minutes * 60
                invalid_after_reset = any(reset_at < invalid_time <= moment for invalid_time in invalid_times)
                if gap_ok and not invalid_after_reset:
                    total = value
                    used += 1
                    warnings.append("The first observed post-07:00 value was used only because the selected Lot spans that reset boundary.")
                else:
                    warnings.append("The first post-reset counter value was omitted because its reset interval is incomplete or invalid.")
            continue

        prior_time, prior_value, _prior_row = previous
        if any(prior_time < invalid_time <= moment for invalid_time in invalid_times):
            warnings.append("Counter delta spanning an invalid observation was omitted.")
            previous = current
            continue

        delta: int | None = None
        reset_delta = False
        prior_bucket, current_bucket = _bucket(prior_time), _bucket(moment)
        if prior_bucket == current_bucket:
            if value < prior_value:
                warnings.append("A counter decrease outside the confirmed daily reset was not counted; a new baseline was established.")
            elif (moment - prior_time).total_seconds() > max_gap_minutes * 60:
                warnings.append("A counter data gap exceeded the configured limit; its delta was omitted.")
            else:
                delta = value - prior_value
        else:
            reset_day = current_bucket
            reset_at = datetime.combine(reset_day, time(7, 0), tzinfo=zone)
            if current_bucket - prior_bucket == timedelta(days=1) and start_local <= reset_at < end_local:
                if (moment - prior_time).total_seconds() > max_gap_minutes * 60:
                    warnings.append("The 07:00 reset was crossed by a long observation gap; post-reset quantity was omitted.")
                else:
                    delta = value
                    reset_delta = True
                    warnings.append("The first observed post-07:00 value was used only because the selected Lot spans that reset boundary.")
            else:
                warnings.append("A daily reset or multi-day gap was not attributable within this Lot window; no cross-reset delta was counted.")

        if moment <= end_local and delta is not None and (start_local <= prior_time or reset_delta):
            total = (total or 0) + delta
            used += 1
        previous = current

    if total is None:
        warnings.append("No complete, valid counter interval was available inside the selected Lot window.")
    return {"suggestion": total, "warnings": list(dict.fromkeys(warnings)), "samples_used": used}


def calculate_press_drops(observations: Iterable[dict[str, Any]], start_at: datetime, end_at: datetime, **options: Any) -> dict[str, Any]:
    return calculate_counter_window(
        observations,
        start_at,
        end_at,
        allowed_tags={PRESS_COUNTER_TAG},
        **options,
    )


def calculate_wet_rejects(
    observations: Iterable[dict[str, Any]], start_at: datetime, end_at: datetime, **options: Any
) -> dict[str, Any]:
    by_tag: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in observations:
        tag = row.get("_NAME")
        if isinstance(tag, str) and tag.startswith("MODBUS.WET_REJECT.cntR"):
            suffix = tag.removeprefix("MODBUS.WET_REJECT.cntR")
            if suffix.isdigit():
                by_tag[tag].append(row)
    results: dict[str, Any] = {}
    warnings: list[str] = []
    for tag in sorted(by_tag, key=lambda value: int(value.rsplit("cntR", 1)[1])):
        result = calculate_counter_window(by_tag[tag], start_at, end_at, allowed_tags={tag}, **options)
        results[tag] = result["suggestion"]
        warnings.extend(f"{tag}: {warning}" for warning in result["warnings"])
    if not by_tag:
        warnings.append("No verified cntR* counter observations were found; button-state R* tags are excluded.")
    return {"suggestions": results, "warnings": list(dict.fromkeys(warnings))}


def calculate_camera_pieces(
    observations: Iterable[dict[str, Any]],
    start_at: datetime,
    end_at: datetime,
    *,
    source_timezone: str,
    source_timezone_confirmed: bool,
    metadata_reviewed: bool,
    boundary_policy_confirmed: bool,
    valid_quality_values: tuple[str, ...],
    duplicate_clear_values: tuple[str, ...],
) -> dict[str, Any]:
    warnings: list[str] = []
    if not metadata_reviewed:
        return {"suggestion": None, "observations_used": 0, "warnings": ["Camera timestamp, record identity, quality, and duplicate metadata have not been reviewed."]}
    if not boundary_policy_confirmed:
        return {"suggestion": None, "observations_used": 0, "warnings": ["Lot boundary/changeover attribution policy for individual Wet trays is not approved."]}
    if not source_timezone_confirmed or source_timezone != BANGKOK:
        return {"suggestion": None, "observations_used": 0, "warnings": ["Camera source timezone has not been verified as Asia/Bangkok."]}
    if not valid_quality_values or not duplicate_clear_values:
        return {"suggestion": None, "observations_used": 0, "warnings": ["Camera quality and duplicate-value rules are not configured."]}
    try:
        zone = ZoneInfo(source_timezone)
    except ZoneInfoNotFoundError:
        return {"suggestion": None, "observations_used": 0, "warnings": ["Configured camera timezone is unavailable."]}

    seen_ids: set[str] = set()
    pieces = 0
    used = 0
    for row in observations:
        if row.get("line") != "wet":
            continue
        source_id = str(row.get("source_id"))
        if source_id in seen_ids:
            warnings.append("Duplicate camera source IDs were excluded.")
            continue
        seen_ids.add(source_id)
        if str(row.get("quality")) not in valid_quality_values:
            warnings.append("Camera observations with unapproved quality were excluded.")
            continue
        if str(row.get("duplicate")) not in duplicate_clear_values:
            warnings.append("Camera observations marked duplicate or with unknown duplicate status were excluded.")
            continue
        moment = _timestamp(row.get("timestamp"), zone)
        if moment is None:
            warnings.append("Camera observations with invalid timestamps were excluded.")
            continue
        if not (start_at.astimezone(zone) <= moment < end_at.astimezone(zone)):
            continue
        try:
            value = int(row.get("value_cnt"))
            numeric_value = float(row.get("value_cnt"))
        except (TypeError, ValueError, OverflowError):
            warnings.append("Invalid individual tray counts were excluded.")
            continue
        if numeric_value != value or value < 0:
            warnings.append("Invalid individual tray counts were excluded.")
            continue
        pieces += value
        used += 1
    if used == 0:
        warnings.append("No verified Wet tray observations were attributable to this Lot window.")
        return {"suggestion": None, "observations_used": 0, "warnings": list(dict.fromkeys(warnings))}
    return {"suggestion": pieces, "observations_used": used, "warnings": list(dict.fromkeys(warnings))}
