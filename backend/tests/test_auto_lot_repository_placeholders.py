from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
from typing import Any

from backend.app.production_repository import SQLServerProductionRepository


class RecordingCursor:
    def __init__(self) -> None:
        self.sql = ""
        self.statements: list[str] = []
        self.executions: list[tuple[str, tuple[Any, ...]]] = []
        self.window_start = datetime(2026, 11, 1)
        self.window_end = datetime(2026, 11, 2)

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> "RecordingCursor":
        assert sql.count("?") == len(params), f"SQL parameter mismatch: {sql.count('?')} placeholders vs {len(params)} values in {sql}"
        self.sql = sql
        self.statements.append(sql)
        self.executions.append((sql, params))
        return self

    def fetchone(self) -> tuple[Any, ...] | None:
        if "SELECT id,CandidateKey,CandidateKind" in self.sql:
            state = {
                "id": 1, "CandidateKey": "candidate:1", "CandidateKind": "AUTO",
                "SourceTag": "OMAG.PRESS.OEE.DropCnt", "FirstSourceID": 10,
                "ResetSourceID": 10, "ResetPreviousSourceID": 9,
                "ResetObservedAt": self.window_start, "ResetPreviousAt": self.window_start,
                "ResetValue": 0, "ResetPreviousValue": 5,
                "InitialProposedStartTime": self.window_start, "InitialProposedEndTime": self.window_end,
                "CurrentProposedStartTime": self.window_start, "CurrentProposedEndTime": self.window_end,
                "EffectiveStartTime": self.window_start, "EffectiveEndTime": self.window_end,
                "OperatorTimeOverride": False, "CandidateStatus": "OPEN",
                "ProductionDate": self.window_start.date(), "CutoffVersionID": 1,
                "ShiftScheduleVersionID": 1, "ShiftID": 1, "ProductID": None,
                "ColorCode": None, "OfficialProductionLotID": None, "CreatedBy": "AUTO DETECTOR",
                "LastDetectedAt": self.window_start, "LastOperatorID": None,
                "LastOperatorReason": None, "PlanSourceKey": None, "PlanSnapshotJson": None,
                "PlanMaterialCode": None, "PlanMatchStatus": None, "PlanSelectedAt": None,
                "PlanSelectedBy": None, "OperatorBoundaryConfirmed": False,
            }
            self.description = [(name,) for name in state]
            return tuple(state.values())
        if "SELECT id FROM omagmes.AutoLotCandidateWindow" in self.sql and "CandidateKey=?" in self.sql:
            return None
        if "SELECT EffectiveStartTime" in self.sql:
            if "ProductionDate" in self.sql:
                return (datetime(2026, 11, 1), datetime(2026, 11, 2), "CLOSED", None, datetime(2026, 11, 1).date(), 1, 1, 1, 1, "RED")
            return (self.window_start, self.window_end, "OPEN", None)
        if "SELECT id,EffectiveStartTime" in self.sql:
            return None
        if "output inserted.id" in self.sql.casefold():
            return (100,)
        return None

    def fetchall(self) -> list[tuple[Any, ...]]:
        if "SELECT id FROM omagmes.Product" in self.sql:
            return [(1,)]
        if "SELECT id,EffectiveStartTime" in self.sql:
            return [
                (1, datetime(2026, 11, 1), datetime(2026, 11, 2), "CLOSED", None),
                (2, datetime(2026, 11, 2), None, "OPEN", None),
            ]
        return []



def test_auto_lot_write_statements_have_matching_parameter_counts(monkeypatch) -> None:
    monkeypatch.setenv("OMAGMES_AUTOLOT_SYNC_ENABLED", "1")
    repository = SQLServerProductionRepository()
    cursor = RecordingCursor()

    @contextmanager
    def fake_connection():
        yield object(), cursor

    monkeypatch.setattr(repository, "_auto_lot_connection", fake_connection)
    start = datetime(2026, 11, 1, 8)
    end = datetime(2026, 11, 2, 8)
    repository.create_auto_lot_window("manual:test", start, end, "operator", "review reason", "2026-11-01", 1)
    repository.edit_auto_lot_candidate_window(1, start, end, "operator", "edit reason")
    repository.split_auto_lot_window(1, datetime(2026, 11, 1, 12), "split:test", "operator", "split reason")
    repository.merge_auto_lot_windows(1, 2, "operator", "merge reason")
    repository.dismiss_auto_lot_window(1, "operator", "dismiss reason")

    assert any("CandidateWindowHistory" in sql for sql in cursor.statements)


def test_operator_window_create_and_split_normalize_to_minute_precision(monkeypatch) -> None:
    monkeypatch.setenv("OMAGMES_AUTOLOT_SYNC_ENABLED", "1")
    repository = SQLServerProductionRepository()
    cursor = RecordingCursor()

    @contextmanager
    def fake_connection():
        yield object(), cursor

    monkeypatch.setattr(repository, "_auto_lot_connection", fake_connection)
    start = datetime(2026, 11, 1, 23, 58, 47, 123456)
    end = datetime(2026, 11, 2, 0, 3, 59, 999999)
    repository.create_auto_lot_window("manual:minute", start, end, "operator", "review", "2026-11-01", 1)
    insert = next(sql for sql in cursor.statements if "INSERT omagmes.AutoLotCandidateWindow (CandidateKey" in sql)
    insert_params = next(params for sql, params in cursor.executions if sql is insert)
    assert insert_params[1] == datetime(2026, 11, 1, 23, 58)
    assert insert_params[2] == datetime(2026, 11, 2, 0, 3)


def test_auto_proposal_precision_is_retained_until_a_boundary_is_changed(monkeypatch) -> None:
    monkeypatch.setenv("OMAGMES_AUTOLOT_SYNC_ENABLED", "1")
    repository = SQLServerProductionRepository()
    cursor = RecordingCursor()

    @contextmanager
    def fake_connection():
        yield object(), cursor

    monkeypatch.setattr(repository, "_auto_lot_connection", fake_connection)
    proposed_start = datetime(2026, 11, 1, 8, 0, 12, 340000)
    proposed_end = datetime(2026, 11, 1, 12, 0, 55, 670000)
    cursor.window_start = proposed_start
    cursor.window_end = proposed_end
    repository.edit_auto_lot_candidate_window(1, proposed_start, proposed_end, "operator", "review")
    update = next(sql for sql in cursor.statements if "UPDATE omagmes.AutoLotCandidateWindow SET CurrentProposedStartTime" in sql)
    update_params = next(params for sql, params in cursor.executions if sql is update)
    assert update_params[:4] == (proposed_start, proposed_end, proposed_start, proposed_end)

    cursor = RecordingCursor()
    cursor.window_start = proposed_start
    cursor.window_end = proposed_end
    monkeypatch.setattr(repository, "_auto_lot_connection", fake_connection)
    repository.edit_auto_lot_candidate_window(
        1, datetime(2026, 11, 1, 8, 1, 47), proposed_end, "operator", "minute edit",
    )
    update = next(sql for sql in cursor.statements if "UPDATE omagmes.AutoLotCandidateWindow SET CurrentProposedStartTime" in sql)
    update_params = next(params for sql, params in cursor.executions if sql is update)
    assert update_params[:4] == (
        datetime(2026, 11, 1, 8, 1), proposed_end,
        datetime(2026, 11, 1, 8, 1), proposed_end,
    )


def test_detector_sync_uses_stable_source_key_and_complete_create_audit(monkeypatch) -> None:
    monkeypatch.setenv("OMAGMES_AUTOLOT_SYNC_ENABLED", "1")
    repository = SQLServerProductionRepository()
    cursor = RecordingCursor()

    @contextmanager
    def fake_connection():
        yield object(), cursor

    monkeypatch.setattr(repository, "_auto_lot_connection", fake_connection)
    start = datetime(2026, 11, 1, 9, 15, 2)
    end = datetime(2026, 11, 1, 13, 30, 4)
    result = repository.sync_auto_lot_detected_windows([{
        "CandidateKey": "autolot:dropcnt-reset:98765",
        "SourceTag": "OMAG.PRESS.OEE.DropCnt",
        "FirstSourceID": 98765,
        "ResetSourceID": 98765,
        "ResetPreviousSourceID": 98764,
        "ResetValue": 0,
        "ResetPreviousValue": 52,
        "ProposedStartTime": start,
        "ProposedEndTime": end,
        "BoundaryEarliestEvidenceAt": datetime(2026, 11, 1, 9, 15),
        "ProductionDate": start.date(),
        "CutoffVersionID": 1,
        "ShiftScheduleVersionID": 2,
        "ShiftID": None,
    }])

    assert result == [{"id": 100, "candidate_key": "autolot:dropcnt-reset:98765", "created": True, "preserved": False}]
    insert = next(sql for sql in cursor.statements if "INSERT omagmes.AutoLotCandidateWindow" in sql)
    insert_params = next(params for sql, params in cursor.executions if sql is insert)
    assert insert_params[0] == "autolot:dropcnt-reset:98765"
    history = next(sql for sql in cursor.statements if "INSERT omagmes.AutoLotCandidateWindowHistory" in sql)
    assert "PreviousStateJson" in history and "NewStateJson" in history
    history_params = next(params for sql, params in cursor.executions if sql is history)
    assert history_params[1] == "CREATE_AUTO"

