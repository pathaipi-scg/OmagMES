from __future__ import annotations

from datetime import datetime

from backend.app.auto_lot_detection import detect_dropcnt_envelope, detect_dropcnt_lots, detect_dropcnt_reset_candidates, preview_dropcnt_observation_intervals
from backend.app.sql_source import DROP_COUNTER_TAG

START = datetime.fromisoformat("2026-11-10T07:00:00+07:00")
END = datetime.fromisoformat("2026-11-11T07:00:00+07:00")


def row(when: str, value: int, *, quality: int = 192, name: str = DROP_COUNTER_TAG, row_id: int = 1, numeric_id: int = 0):
    return {"id": row_id, "_NAME": name, "_NUMERICID": numeric_id, "_VALUE": value, "_TIMESTAMP": when, "_QUALITY": quality}


def analyze(rows: list[dict], **overrides):
    options = {
        "production_date": "2026-11-10",
        "cutoff_version_id": 1,
        "start_at": START,
        "end_at": END,
        "source_timezone": "Asia/Bangkok",
        "source_timezone_confirmed": True,
        "valid_quality_codes": (192,),
        "max_gap_minutes": 20,
    }
    options.update(overrides)
    return detect_dropcnt_envelope(rows, **options)


def test_python_detector_never_calculates_press_diff_or_acc() -> None:
    result = analyze([
        row("2026-11-10T07:00:00+07:00", 10, row_id=1),
        row("2026-11-10T07:05:00+07:00", 12, row_id=2),
    ])
    assert result["candidates"] == []
    assert result["window"]["interval_semantics"] == "[start, end)"
    assert any("SQL Server views" in warning for warning in result["warnings"])
    assert "raw_drop_count" not in result
    assert "evidence_deltas" not in result


def test_python_detector_refuses_python_diff_even_for_bad_settings() -> None:
    result = analyze(
        [row("2026-11-10T07:05:00+07:00", 100), row("2026-11-10T07:10:00+07:00", 110, row_id=2)],
        source_timezone_confirmed=False,
        valid_quality_codes=(),
        max_gap_minutes=None,
    )
    assert result["candidates"] == []
    assert "raw_drop_count" not in result


def test_reset_candidates_are_boundary_evidence_only_and_never_report_quantity() -> None:
    rows = [
        row("2026-11-10T06:59:50", 899, row_id=1),
        row("2026-11-10T07:00:05", 0, row_id=2),
        row("2026-11-10T07:00:20", 1, row_id=3),
    ]
    result = detect_dropcnt_reset_candidates(
        rows, start_at=START, end_at=END, source_timezone="Asia/Bangkok",
        source_timezone_confirmed=False, valid_quality_codes=(192,), max_gap_minutes=20,
    )
    candidate, = result["reset_candidates"]
    assert candidate["before_sample"]["value"] == 899
    assert candidate["decrease_sample"]["value"] == 0
    assert candidate["reset_time_interval"]["earliest_exclusive"] == "2026-11-10T06:59:50+07:00"
    assert candidate["restart_sample"]["value"] == 1
    assert candidate["official_lot_id"] is None
    assert candidate["timestamp_basis"] == "ASIA/BANGKOK · SQL LOCAL WALL CLOCK"
    assert "post_reset_run_drops_lower_bound" not in candidate
    assert "drops" not in candidate
    assert any("SQL Server views" in warning for warning in result["warnings"])


def test_reset_candidate_ids_are_stable_for_same_source_pair() -> None:
    rows = [row("2026-11-10T07:05:00+07:00", 500, row_id=100), row("2026-11-10T07:06:00+07:00", 0, row_id=101)]
    options = dict(start_at=START, end_at=END, source_timezone="Asia/Bangkok", source_timezone_confirmed=True,
                   valid_quality_codes=(192,), max_gap_minutes=None)
    first = detect_dropcnt_reset_candidates(rows, **options)["reset_candidates"]
    second = detect_dropcnt_reset_candidates(rows, **options)["reset_candidates"]
    assert first[0]["id"] == second[0]["id"]


def test_reset_candidates_ignore_nonzero_decreases() -> None:
    result = detect_dropcnt_reset_candidates(
        [row("2026-11-10T07:05:00+07:00", 100, row_id=1), row("2026-11-10T07:06:00+07:00", 40, row_id=2)],
        start_at=START, end_at=END, source_timezone="Asia/Bangkok", source_timezone_confirmed=True,
        valid_quality_codes=(192,), max_gap_minutes=20,
    )
    assert result["reset_candidates"] == []


def test_reset_detector_rejects_bad_codes_and_truncated_data() -> None:
    rows = [row("2026-11-10T07:05:00+07:00", 100, row_id=1), row("2026-11-10T07:06:00+07:00", 0, row_id=2)]
    result = detect_dropcnt_reset_candidates(
        rows, start_at=START, end_at=END, source_timezone="Asia/Bangkok",
        source_timezone_confirmed=True, valid_quality_codes=(), max_gap_minutes=20,
    )
    assert result["reset_candidates"] == []
    assert any("No PLC quality codes" in warning for warning in result["warnings"])

    truncated = detect_dropcnt_reset_candidates(
        rows, start_at=START, end_at=END, source_timezone="Asia/Bangkok",
        source_timezone_confirmed=True, valid_quality_codes=(192,), max_gap_minutes=20, truncated=True,
    )
    assert truncated["reset_candidates"] == []
    assert truncated["truncated"] is True


def test_dropcnt_lot_starts_after_zero_and_ends_only_on_exact_zero() -> None:
    result = detect_dropcnt_lots(
        [
            row("2026-11-10T07:00:00", 0, row_id=1),
            row("2026-11-10T07:01:00", 1, row_id=2),
            row("2026-11-10T10:01:00", 42, row_id=3),
            row("2026-11-10T12:01:00", 10, row_id=4),  # nonzero decrease is not a boundary
            row("2026-11-10T17:01:00", 10, row_id=5),  # plateau does not close
            row("2026-11-10T18:01:00", 0, row_id=6),
            row("2026-11-10T18:02:00", 0, row_id=7),
            row("2026-11-10T18:03:00", 1, row_id=8),
        ],
        source_timezone="Asia/Bangkok", source_timezone_confirmed=False,
        valid_quality_codes=(192,),
    )

    first, second = result["lots"]
    assert first["id"] == "dropcnt-lot:2"
    assert first["proposed_start_at"] == "2026-11-10T07:01:00+07:00"
    assert first["proposed_end_at"] == "2026-11-10T18:01:00+07:00"
    assert first["end_source_id"] == 6
    assert second["id"] == "dropcnt-lot:8"
    assert second["proposed_end_at"] is None
    assert second["status"].startswith("OPEN")
    assert result["history"]["nonzero_decrease_count"] == 1
    assert all(lot["proposed_lot_number"] is None for lot in result["lots"])


def test_sql_datetime_wall_clock_is_not_converted_from_utc() -> None:
    result = detect_dropcnt_lots(
        [
            row("2026-11-17T01:59:00", 0, row_id=1),
            row("2026-11-17T02:00:00", 1, row_id=2),
        ],
        source_timezone="Asia/Bangkok", source_timezone_confirmed=False,
        valid_quality_codes=(192,),
    )

    lot, = result["lots"]
    assert lot["proposed_start_at"] == "2026-11-17T02:00:00+07:00"
    assert lot["timestamp_basis"] == "ASIA/BANGKOK · SQL LOCAL WALL CLOCK"
    assert any("no UTC conversion" in warning for warning in result["warnings"])


def test_dropcnt_initial_positive_has_no_invented_start() -> None:
    result = detect_dropcnt_lots(
        [row("2026-11-10T07:00:00", 5, row_id=1), row("2026-11-10T07:01:00", 9, row_id=2)],
        source_timezone="Asia/Bangkok", source_timezone_confirmed=False,
        valid_quality_codes=(192,),
    )
    assert result["lots"] == []


def test_dropcnt_invalid_quality_breaks_zero_to_positive_start_evidence() -> None:
    result = detect_dropcnt_lots(
        [
            row("2026-11-10T07:00:00", 0, row_id=1),
            row("2026-11-10T07:01:00", 0, quality=0, row_id=2),
            row("2026-11-10T07:02:00", 1, row_id=3),
            row("2026-11-10T07:03:00", 0, row_id=4),
            row("2026-11-10T07:04:00", 2, row_id=5),
        ],
        source_timezone="Asia/Bangkok", source_timezone_confirmed=False,
        valid_quality_codes=(192,),
    )
    assert len(result["lots"]) == 1
    assert result["lots"][0]["id"] == "dropcnt-lot:5"


def test_dropcnt_duplicate_samples_are_deduplicated_and_conflicts_are_withheld() -> None:
    result = detect_dropcnt_lots(
        [
            row("2026-11-10T07:00:00", 0, row_id=1),
            row("2026-11-10T07:01:00", 1, row_id=3),
            row("2026-11-10T07:01:00", 1, row_id=2),
            row("2026-11-10T07:02:00", 0, row_id=4),
        ],
        source_timezone="Asia/Bangkok", source_timezone_confirmed=False,
        valid_quality_codes=(192,),
    )
    assert len(result["lots"]) == 1
    assert result["lots"][0]["start_source_id"] == 2
    assert result["lots"][0]["end_source_id"] == 4

    conflict = detect_dropcnt_lots(
        [row("2026-11-10T07:00:00", 0, row_id=1), row("2026-11-10T07:01:00", 1, row_id=2),
         row("2026-11-10T07:01:00", 0, row_id=3)],
        source_timezone="Asia/Bangkok", source_timezone_confirmed=False,
        valid_quality_codes=(192,),
    )
    assert conflict["lots"] == []
    assert conflict["history"]["conflicting_timestamp_count"] == 1


def test_legacy_observation_interval_api_never_creates_activity_envelopes() -> None:
    result = preview_dropcnt_observation_intervals(
        [
            row("2026-11-10T07:05:00", 10, row_id=1),
            row("2026-11-10T07:05:00", 1, name="OMAG.PRESS.OEE.AutoRun", row_id=11),
            row("2026-11-10T07:10:00", 20, row_id=2),
            row("2026-11-10T07:10:00", 0, name="OMAG.PRESS.OEE.AutoRun", row_id=12),
            row("2026-11-10T07:15:00", 0, row_id=3),
            row("2026-11-10T07:15:00", 1, name="OMAG.PRESS.OEE.AutoRun", row_id=13),
            row("2026-11-10T07:20:00", 2, row_id=4),
            row("2026-11-10T07:20:00", 0, name="OMAG.PRESS.OEE.AutoRun", row_id=14),
        ],
        source_timezone="Asia/Bangkok", source_timezone_confirmed=False,
        valid_quality_codes=(192,),
    )

    assert result["intervals"] == []
    assert any("zero transitions" in warning for warning in result["warnings"])


def test_observation_intervals_fail_closed_for_truncated_or_unapproved_quality() -> None:
    rows = [row("2026-11-10T07:05:00", 10, row_id=1), row("2026-11-10T07:10:00", 20, row_id=2)]
    truncated = preview_dropcnt_observation_intervals(
        rows, source_timezone="Asia/Bangkok", source_timezone_confirmed=True,
        valid_quality_codes=(192,), truncated=True,
    )
    unapproved = preview_dropcnt_observation_intervals(
        rows, source_timezone="Asia/Bangkok", source_timezone_confirmed=True,
        valid_quality_codes=(),
    )

    assert truncated["intervals"] == [] and truncated["truncated"] is True
    assert unapproved["intervals"] == []


def test_no_activity_or_single_active_sample_does_not_create_interval() -> None:
    idle = preview_dropcnt_observation_intervals(
        [
            row("2026-11-10T07:05:00", 10, row_id=1),
            row("2026-11-10T07:10:00", 10, row_id=2),
            row("2026-11-10T07:10:00", 0, name="OMAG.PRESS.OEE.AutoRun", row_id=12),
        ],
        source_timezone="Asia/Bangkok", source_timezone_confirmed=True,
        valid_quality_codes=(192,),
    )
    one_active_sample = preview_dropcnt_observation_intervals(
        [row("2026-11-10T07:05:00", 1, name="OMAG.PRESS.OEE.AutoRun", row_id=21)],
        source_timezone="Asia/Bangkok", source_timezone_confirmed=True,
        valid_quality_codes=(192,),
    )

    assert idle["intervals"] == []
    assert one_active_sample["intervals"] == []
