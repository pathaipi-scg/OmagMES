"""Opt-in SQL Server integration tests; require a dedicated disposable server/database."""
from __future__ import annotations

import os
import re
from time import perf_counter
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

pyodbc = pytest.importorskip("pyodbc")

ROOT = Path(__file__).resolve().parents[2]
CONNECTION_ENV = "OMAGMES_TEST_SQL_CONNECTION_STRING"


def _batches(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8-sig")
    text = "\n".join(line for line in text.splitlines() if not line.strip().upper().startswith(":ON ERROR"))
    return [batch.strip() for batch in re.split(r"(?im)^\s*GO\s*(?:--.*)?$", text) if batch.strip()]


def _execute_script(cursor: Any, path: Path) -> None:
    for batch in _batches(path):
        cursor.execute(batch)
        while cursor.nextset():
            pass


def _one(cursor: Any, sql: str, params: tuple[Any, ...] = ()) -> tuple[Any, ...]:
    cursor.execute(sql, params)
    row = cursor.fetchone()
    assert row is not None, f"Expected a row from SQL: {sql}"
    return row


@pytest.fixture(scope="module")
def integrated_db():
    connection_string = os.getenv(CONNECTION_ENV, "").strip()
    if not connection_string:
        pytest.skip(f"Set {CONNECTION_ENV} to a dedicated disposable SQL Server database; no test SQL Server is configured.")

    connection = pyodbc.connect(connection_string, autocommit=False, timeout=10)
    cursor = connection.cursor()
    identity = _one(cursor, "SELECT DB_NAME(), @@SERVERNAME, CONVERT(nvarchar(128), SERVERPROPERTY('MachineName'))")
    db_name, server_name, machine_name = (str(value or "") for value in identity)
    assert db_name.upper() == "OMAG", "Integration database must be named OMAG because the migration guards require that name."
    assert server_name.casefold() != "scgls-nk\\sqlexpress" and machine_name.casefold() != "scgls-nk", (
        "Refusing to run migrations or fixtures on the verified LIVE OMAG server."
    )
    assert _one(cursor, "SELECT COUNT_BIG(*) FROM sys.tables WHERE schema_id=SCHEMA_ID(N'omagmes')")[0] == 0, (
        "Disposable test database must have no existing OmagMES tables; use a fresh database."
    )
    assert _one(cursor, "SELECT OBJECT_ID(N'dbo.PRESS',N'U')")[0] is None, (
        "Disposable test database must not contain a PRESS object; the integration test creates its own fixture."
    )

    db = ROOT / "db"
    _execute_script(cursor, db / "002_omagmes_configuration.sql")
    _execute_script(cursor, db / "review-only" / "003_production_lot_workflow.sql")
    cursor.execute(
        "CREATE TABLE dbo.PRESS (id int IDENTITY(1,1) NOT NULL CONSTRAINT PK_PRESS_Test PRIMARY KEY CLUSTERED, "
        "_NAME varchar(64) NULL, _VALUE varchar(64) NULL, _TIMESTAMP datetime NULL, _QUALITY int NULL)"
    )
    _execute_script(cursor, db / "review-only" / "004_press_diff_lot_acc_views.sql")
    _execute_script(cursor, db / "review-only" / "003_validate.sql")
    _execute_script(cursor, db / "review-only" / "004_validate.sql")

    cutoff_id = int(_one(cursor, "SELECT TOP (1) id FROM omagmes.ProductionDayCutoffVersion ORDER BY EffectiveFromProductionDate DESC,id DESC")[0])
    schedule_id = int(_one(cursor, "SELECT TOP (1) id FROM omagmes.ShiftScheduleVersion ORDER BY EffectiveFromProductionDate DESC,id DESC")[0])
    shift1, shift2 = (int(row[0]) for row in cursor.execute(
        "SELECT ShiftID FROM omagmes.ShiftScheduleShift WHERE ShiftScheduleVersionID=? ORDER BY DisplayOrder", (schedule_id,)
    ).fetchall())

    cursor.execute(
        "INSERT omagmes.Product (ProductCode,ProductName,ProductFamily) OUTPUT INSERTED.id "
        "VALUES (N'IT-PRESS',N'Integration Press',N'TEST')"
    )
    product_id = int(cursor.fetchone()[0])
    cursor.execute(
        "INSERT omagmes.ProductStandardRevision (ProductID,RevisionNo,StandardPiecesPerDrop,StandardCycleTimeSec,EffectiveFrom,StatusCode,ApprovedBy,ApprovedAt,ChangeReason) "
        "OUTPUT INSERTED.id VALUES (?,1,1,1,CONVERT(datetimeoffset(0),'2026-11-10T00:00:00+07:00'),'APPROVED',N'IT TEST',SYSDATETIMEOFFSET(),N'Disposable integration fixture')",
        (product_id,),
    )
    standard_id = int(cursor.fetchone()[0])
    cursor.execute(
        "INSERT omagmes.ProductionRun (ProductID,StartedAt,StatusCode,CreatedBy) "
        "OUTPUT INSERTED.id VALUES (?,CONVERT(datetimeoffset(0),'2026-11-17T09:00:00+07:00'),'OPEN',N'IT TEST')",
        (product_id,),
    )
    run_id = int(cursor.fetchone()[0])

    def insert_lot(lot_no: str, start: str, end: str | None, sequence: int, shift_id: int) -> int:
        cursor.execute(
            "INSERT omagmes.ProductionLot (ProductionRunID,ProductID,ColorCode,ProductFamilySnapshot,ProductStandardRevisionID,"
            "StandardPiecesPerDropSnapshot,StandardCycleTimeSecSnapshot,LotNo,ProductionDate,ShiftScheduleVersionID,ShiftID,"
            "LotSequence,MachineCode,LotName,LotStartedAt,LotEndedAt,CreatedBy) "
            "OUTPUT INSERTED.id VALUES (?,?,N'RED',N'TEST',?,1,1,?,'2026-11-17',?,?,?,?,?,CONVERT(datetimeoffset(0),?),"
            "CASE WHEN ? IS NULL THEN NULL ELSE CONVERT(datetimeoffset(0),?) END,N'IT TEST')",
            (run_id, product_id, standard_id, lot_no, schedule_id, shift_id, sequence, "B", lot_no,
             start, end, end),
        )
        return int(cursor.fetchone()[0])

    lot_a = insert_lot("C171126101B", "2026-11-17T10:00:00+07:00", "2026-11-17T10:15:00+07:00", 1, shift1)
    lot_b = insert_lot("C171126102B", "2026-11-17T10:15:00+07:00", "2026-11-17T10:16:00+07:00", 2, shift1)
    lot_c = insert_lot("C171126103B", "2026-11-17T10:16:00+07:00", None, 3, shift1)

    def insert_candidate(key: str, start: str, end: str | None, *, override: int = 0) -> int:
        cursor.execute(
            "INSERT omagmes.AutoLotCandidateWindow (CandidateKey,CandidateKind,SourceTag,InitialProposedStartTime,InitialProposedEndTime,"
            "CurrentProposedStartTime,CurrentProposedEndTime,EffectiveStartTime,EffectiveEndTime,OperatorTimeOverride,ProductionDate,LastDetectedAt) "
            "OUTPUT INSERTED.id VALUES (?,'MANUAL',N'IT FIXTURE',CONVERT(datetime2(7),?),CONVERT(datetime2(7),?),"
            "CONVERT(datetime2(7),?),CONVERT(datetime2(7),?),CONVERT(datetime2(7),?),CONVERT(datetime2(7),?),?,'2026-11-18',SYSUTCDATETIME())",
            (key, start, end, start, end, start, end, override),
        )
        return int(cursor.fetchone()[0])

    overlap_a = insert_candidate("it-overlap-a", "2026-11-18T01:00:00", "2026-11-18T01:10:00")
    overlap_b = insert_candidate("it-overlap-b", "2026-11-18T01:05:00", "2026-11-18T01:15:00")
    precise = insert_candidate("it-auto-precision", "2026-11-18T11:00:00.3330000", "2026-11-18T11:01:00.7770000")
    open_candidate = insert_candidate("it-open", "2026-11-19T00:00:00", None)

    samples = [
        ("2026-11-17T09:00:00", "98", 192),
        ("2026-11-17T09:01:00", "99", 192),
        ("2026-11-17T10:14:50", "201", 192),
        ("2026-11-17T10:15:23", "202", 777),
        ("2026-11-17T10:15:40", "202", 0),
        ("2026-11-17T10:15:50", "5", 999),
        ("2026-11-17T10:16:00", "7", 192),
        ("2026-11-17T10:16:30", "9", 200),
        ("2026-11-17T10:17:00", "10", 192),
        ("2026-11-17T10:18:00", "11", 192),
        ("2026-11-18T00:05:00", "12", 192),
        ("2026-11-18T00:50:00", "13", 192),
        ("2026-11-18T01:00:00", "14", 192),
        ("2026-11-18T01:05:00", "15", 192),
        ("2026-11-18T01:10:00", "16", 192),
        ("2026-11-18T11:00:00", "17", 192),
        ("2026-11-18T11:00:01.123", "18", 192),
    ]
    cursor.executemany(
        "INSERT dbo.PRESS (_NAME,_VALUE,_TIMESTAMP,_QUALITY) VALUES ('OMAG.PRESS.OEE.DropCnt',?,?,?)",
        samples,
    )
    connection.commit()
    yield connection, {
        "lot_a": lot_a, "lot_b": lot_b, "lot_c": lot_c,
        "overlap_a": overlap_a, "overlap_b": overlap_b, "precise": precise,
        "open_candidate": open_candidate,
    }
    connection.close()


def _event(cursor: Any, timestamp: str) -> dict[str, Any]:
    row = _one(cursor,
        "SELECT SourceID,PreviousRecTime,CounterValue,PreviousCounterValue,Diff,DiffStatus,ResetDetected,"
        "LotIdentityType,LotIdentityID,AllocationStatus,AllocatedDiff,LotACC,StartTime,EndTime "
        "FROM omagmes.v_PressLotACC WHERE RecTime=CONVERT(datetime,?)",
        (timestamp,),
    )
    return dict(zip(("source_id", "previous_time", "counter", "previous_counter", "diff", "status", "reset",
                     "identity_type", "identity_id", "allocation", "allocated", "acc", "start", "end"), row))


def test_current_sample_boundary_positive_and_duplicate_and_reset(integrated_db) -> None:
    connection, ids = integrated_db
    cursor = connection.cursor()
    event = _event(cursor, "2026-11-17T10:15:23")
    assert event["previous_time"] == datetime(2026, 11, 17, 10, 14, 50)
    assert event["previous_counter"] == 201 and event["counter"] == 202
    assert event["diff"] == 1 and event["allocated"] == 1
    assert event["identity_type"] == "OFFICIAL" and event["identity_id"] == ids["lot_b"]
    assert event["allocation"] == "ALLOCATED_OFFICIAL"
    assert event["acc"] == 1

    duplicate = _event(cursor, "2026-11-17T10:15:40")
    assert duplicate["diff"] == 0 and duplicate["status"] == "UNCHANGED"
    reset = _event(cursor, "2026-11-17T10:15:50")
    assert reset["reset"] and reset["diff"] == 0 and reset["status"] == "RESET_BASELINE_NOT_CREDITED"
    after_reset = _event(cursor, "2026-11-17T10:16:00")
    assert after_reset["diff"] == 2 and after_reset["identity_id"] == ids["lot_c"] and after_reset["acc"] == 2


def test_quality_is_informational_and_unallocated_overlap_never_double_count(integrated_db) -> None:
    connection, ids = integrated_db
    cursor = connection.cursor()
    unallocated = _event(cursor, "2026-11-17T09:01:00")
    assert unallocated["diff"] == 1 and unallocated["allocation"] == "UNALLOCATED_NO_WINDOW" and unallocated["allocated"] == 0
    unknown = _event(cursor, "2026-11-17T10:16:30")
    assert unknown["diff"] == 2 and unknown["status"] == "POSITIVE_DELTA"
    assert _one(cursor,
        "SELECT QualityCode,Diff,DiffStatus FROM omagmes.v_PressDailyDiff WHERE RecTime=CONVERT(datetime,?)",
        ("2026-11-17T10:16:30",),
    ) == (200, 2, "POSITIVE_DELTA")
    previous_unknown = _event(cursor, "2026-11-17T10:17:00")
    assert previous_unknown["diff"] == 1 and previous_unknown["status"] == "POSITIVE_DELTA"
    unchanged_any_quality = _one(cursor,
        "SELECT Diff,DiffStatus FROM omagmes.v_PressDailyDiff WHERE RecTime=CONVERT(datetime,?)",
        ("2026-11-17T10:15:40",),
    )
    assert unchanged_any_quality == (0, "UNCHANGED")

    first_overlap_window = _event(cursor, "2026-11-18T01:00:00")
    assert first_overlap_window["allocation"] == "ALLOCATED_CANDIDATE" and first_overlap_window["allocated"] == 1
    overlap = _event(cursor, "2026-11-18T01:05:00")
    assert overlap["allocation"] == "AMBIGUOUS_CANDIDATE_OVERLAP" and overlap["allocated"] == 0
    next_window = _event(cursor, "2026-11-18T01:10:00")
    assert next_window["allocation"] == "ALLOCATED_CANDIDATE" and next_window["allocated"] == 1


def test_cross_date_lot_acc_open_windows_and_live_recalculation(integrated_db) -> None:
    connection, ids = integrated_db
    cursor = connection.cursor()
    lot_c_id = ids["lot_c"]
    across_date = _event(cursor, "2026-11-18T00:05:00")
    assert across_date["identity_id"] == lot_c_id and across_date["diff"] == 1 and across_date["acc"] == 4
    assert _one(cursor,
        "SELECT LotStatus,LatestLotACC FROM omagmes.v_PressLotSummary WHERE LotIdentityType='OFFICIAL' AND LotIdentityID=?",
        (lot_c_id,),
    ) == ("OPEN", 4)

    open_candidate = ids["open_candidate"]
    assert _one(cursor,
        "SELECT LotStatus,LatestLotACC,EndTime FROM omagmes.v_PressLotSummary WHERE LotIdentityType='CANDIDATE' AND LotIdentityID=?",
        (open_candidate,),
    ) == ("OPEN", 0, None)

    precise = _event(cursor, "2026-11-18T11:00:01.123")
    assert precise["allocation"] == "ALLOCATED_CANDIDATE" and precise["allocated"] == 1
    assert precise["start"].microsecond == 333000
    cursor.execute("UPDATE omagmes.AutoLotCandidateWindow SET EffectiveStartTime=CONVERT(datetime2(7),'2026-11-18T11:00:02') WHERE id=?", (ids["precise"],))
    connection.commit()
    recalculated = _event(cursor, "2026-11-18T11:00:01.123")
    assert recalculated["allocation"] == "UNALLOCATED_NO_WINDOW" and recalculated["allocated"] == 0


def test_shared_views_support_grafana_style_selects_and_production_date_reconciliation(integrated_db) -> None:
    connection, _ = integrated_db
    cursor = connection.cursor()
    rows = cursor.execute(
        "SELECT a.RecTime AS [time], CONCAT(a.LotIdentityType, ':', a.LotIdentityID) AS series, a.LotACC AS value "
        "FROM omagmes.v_PressLotACC AS a WHERE a.RecTime>=? AND a.RecTime<? AND a.LotIdentityID IS NOT NULL ORDER BY a.RecTime,a.SourceID",
        ("2026-11-17T00:00:00", "2026-11-19T00:00:00"),
    ).fetchall()
    assert rows
    assert _one(cursor,
        "SELECT COUNT_BIG(*) FROM omagmes.v_PressDiffReconciliation WHERE ProductionDate='2026-11-17'",
    )[0] == 1


def test_actual_query_plan_and_fixture_query_runtime_are_captured(integrated_db) -> None:
    connection, _ = integrated_db
    cursor = connection.cursor()
    cursor.execute("SET STATISTICS IO ON; SET STATISTICS TIME ON; SET STATISTICS XML ON;")
    started = perf_counter()
    cursor.execute("SELECT COUNT_BIG(*) FROM omagmes.v_PressLotACC WHERE RecTime >= '2026-11-17' AND RecTime < '2026-11-19'")
    result_count = int(cursor.fetchone()[0])
    plans: list[str] = []
    while cursor.nextset():
        if cursor.description:
            for row in cursor.fetchall():
                plans.extend(str(value) for value in row if isinstance(value, str) and "ShowPlanXML" in value)
    elapsed_ms = (perf_counter() - started) * 1000
    cursor.execute("SET STATISTICS XML OFF; SET STATISTICS IO OFF; SET STATISTICS TIME OFF;")
    assert result_count > 0
    assert plans, "SQL Server STATISTICS XML did not return an actual execution plan result set."
    assert elapsed_ms >= 0
