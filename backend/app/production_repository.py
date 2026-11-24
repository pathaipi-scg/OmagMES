from __future__ import annotations

import os
import json
from contextlib import contextmanager
from datetime import datetime, time
from typing import Any, Callable, Iterator
from zoneinfo import ZoneInfo

from .sql_source import EXPECTED_DATABASE, EXPECTED_INSTANCE, EXPECTED_SERVER_NAME, EXPECTED_SQL_LOGIN, SQLServerReadOnlyRepository, SQLSourceSettings, SourceUnavailable
from .lot_numbering import (
    SCG_LINE_CODE,
    SCG_PLANT_CODE,
    LotNumberingError,
    build_scg_lot_number,
    next_lot_sequence,
)
from .production_plans import plan_snapshot


BANGKOK = ZoneInfo("Asia/Bangkok")
ConnectFactory = Callable[..., Any]
REQUIRED_PRODUCTION_TABLES = (
    "Product", "ProductStandardRevision", "ProductionRun", "ProductionLot", "ProductionLotNameHistory",
    "ProductionEntry", "ProductionEntryCorrection", "CuringInputEntry",
    "DepalletEvent", "Dispatch", "DispatchLine", "LotNumberSequence", "AutoLotResetReview",
    "ProductionEntryChangeHistory", "WetRejectReason", "WetRejectEntry", "Mould", "MouldHistory",
)
REQUIRED_PRODUCTION_COLUMNS = {
    "Product": ("id", "ProductCode", "ProductName", "ProductFamily", "IsActive"),
    "ProductStandardRevision": ("id", "ProductID", "RevisionNo", "StandardPiecesPerDrop", "StandardCycleTimeSec", "EffectiveFrom", "EffectiveTo", "StatusCode", "ApprovedBy", "ApprovedAt", "ChangeReason"),
    "ProductionRun": ("id", "ProductID", "StartedAt", "EndedAt", "StatusCode", "CreatedBy"),
    "ProductionLot": ("id", "ProductionRunID", "ProductID", "ColorCode", "ProductFamilySnapshot", "ProductStandardRevisionID", "StandardPiecesPerDropSnapshot", "StandardCycleTimeSecSnapshot", "LotNo", "ProductionDate", "ShiftScheduleVersionID", "ShiftID", "LotSequence", "MachineCode", "LotName", "LotStartedAt", "LotEndedAt", "CreatedBy"),
    "ProductionLotNameHistory": ("id", "ProductionLotID", "OldLotName", "NewLotName", "ChangedBy", "ChangedAt", "ChangeReason"),
    "ProductionEntry": ("id", "ProductionLotID", "PressDrops", "WetGoodPieces", "SuggestedPressDrops", "SuggestedWetGoodPieces", "ProductStandardRevisionID", "StandardPiecesPerDropSnapshot", "StandardCycleTimeSecSnapshot", "SourceCode", "OperatorNote", "EnteredBy", "RecordedAt", "ProductionAt", "ProductionDate", "ShiftScheduleVersionID", "ShiftID", "OperatorConfirmed", "IsDeleted", "DeletedAt", "DeletedBy", "DeleteReason"),
    "ProductionEntryCorrection": ("id", "ProductionEntryID", "OldPressDrops", "NewPressDrops", "OldWetGoodPieces", "NewWetGoodPieces", "ChangedBy", "ChangedAt", "ChangeReason"),
    "CuringInputEntry": ("id", "ProductionLotID", "InputQuantity", "QuantityUnitCode", "RecordedAt", "OperatorNote", "EnteredBy", "OperatorConfirmed"),
    "DepalletEvent": ("id", "ProductionLotID", "Quantity", "QuantityUnitCode", "RecordedAt", "OperatorNote", "EnteredBy"),
    "Dispatch": ("id", "DispatchReference", "DispatchedAt", "EnteredBy", "OperatorNote"),
    "DispatchLine": ("id", "DispatchID", "ProductionLotID", "Quantity", "QuantityUnitCode"),
    "LotNumberSequence": ("id", "PlantCode", "ProductionDate", "ShiftCode", "LastSequence"),
    "AutoLotResetReview": ("id", "CandidateID", "ProductionLotID", "ProductionDate", "ShiftID", "ShiftScheduleVersionID", "ConfirmedBy", "ConfirmationReason", "ReviewedAt"),
    "ProductionEntryChangeHistory": ("id", "ProductionEntryID", "ChangeType", "ChangedBy", "ChangedAt", "ChangeReason", "BeforeStateJson", "AfterStateJson"),
    "WetRejectReason": ("id", "ReasonCode", "ReasonName", "IsActive"),
    "WetRejectEntry": ("id", "ProductionLotID", "RejectReasonID", "Quantity", "RecordedAt", "EnteredBy", "OperatorNote", "IsDeleted"),
    "Mould": ("id", "ProductID", "MouldCode", "MouldName", "CurrentAgeDrops", "LifetimeAgeDrops", "StatusCode", "IsActive"),
    "MouldHistory": ("id", "MouldID", "ActionCode", "ChangedBy", "ChangedAt", "ChangeReason", "PreviousStateJson", "NewStateJson"),
}
# Factory confirmed Nong Khae / BLOCK number configuration. Official Lot
# persistence remains separately gated until the deployed schema is reviewed.
SCG_LOT_NUMBER_PROPOSALS_READY = True
OFFICIAL_LOT_NUMBERING_READY = False


def classify_lot_change(active_product_id: int, active_color: str, selected_product_id: int, selected_color: str) -> str:
    """Classify only Product/Color changes; Shift and Production Date are not Lot boundaries."""
    if active_product_id != selected_product_id:
        return "PRODUCT_CHANGE"
    if active_color != selected_color:
        return "COLOR_CHANGE"
    return "CONTINUE"


class SQLServerProductionRepository:
    """Transactional persistence for approved existing SQL targets only."""

    def __init__(self, settings: SQLSourceSettings | None = None, connect_factory: ConnectFactory | None = None) -> None:
        self.settings = settings or SQLSourceSettings.from_environment()
        self._connect_factory = connect_factory
        self._connection_string_builder = SQLServerReadOnlyRepository(self.settings, connect_factory)
        self._last_identity: dict[str, Any] | None = None

    @contextmanager
    def _connection(self, *, write: bool = False) -> Iterator[tuple[Any, Any]]:
        errors = self.settings.live_gate_errors()
        if errors:
            raise SourceUnavailable(" ".join(errors))
        connection: Any | None = None
        try:
            if self._connect_factory is None:
                import pyodbc

                connection = pyodbc.connect(
                    self._connection_string_builder._connection_string().replace("ApplicationIntent=ReadOnly;", ""),
                    timeout=self.settings.connect_timeout,
                    autocommit=False,
                )
            else:
                connection = self._connect_factory(
                    self._connection_string_builder._connection_string().replace("ApplicationIntent=ReadOnly;", ""),
                    timeout=self.settings.connect_timeout,
                    autocommit=False,
                )
            connection.timeout = self.settings.query_timeout
            cursor = connection.cursor()
            cursor.execute(
                "SELECT ORIGINAL_LOGIN(), SUSER_SNAME(), DB_NAME(), @@SERVERNAME, "
                "CAST(SERVERPROPERTY('InstanceName') AS nvarchar(128)), IS_SRVROLEMEMBER('sysadmin')"
            )
            identity = cursor.fetchone()
            if identity is None:
                raise SourceUnavailable("SQL production target identity could not be verified.")
            original_login, login, database, server, instance = (str(value or "") for value in identity[:5])
            if original_login.casefold() != EXPECTED_SQL_LOGIN.casefold() or login.casefold() != EXPECTED_SQL_LOGIN.casefold():
                raise SourceUnavailable(f"Production persistence requires {EXPECTED_SQL_LOGIN}; fallback SQL identities are refused.")
            if identity[5] != 0:
                raise SourceUnavailable("The OMAG_MES runtime login must not be a sysadmin member.")
            if database.casefold() != EXPECTED_DATABASE.casefold() or server.casefold() != EXPECTED_SERVER_NAME.casefold() or instance.casefold() != EXPECTED_INSTANCE.casefold():
                raise SourceUnavailable("SQL production target is not the verified OMAG instance.")
            self._last_identity = {
                "original_login": original_login,
                "sql_login": login,
                "database": database,
                "server": server,
                "instance": instance,
            }
        except SourceUnavailable:
            if connection is not None:
                try:
                    connection.close()
                except Exception:
                    pass
            raise
        except Exception as exc:
            if connection is not None:
                try:
                    connection.close()
                except Exception:
                    pass
            raise SourceUnavailable(f"SQL production connection failed ({type(exc).__name__}).") from None
        try:
            yield connection, cursor
            if write:
                connection.commit()
            else:
                connection.rollback()
        except SourceUnavailable:
            connection.rollback()
            raise
        except Exception as exc:
            connection.rollback()
            raise SourceUnavailable(f"OmagMES production transaction failed ({type(exc).__name__}).") from None
        finally:
            connection.close()

    def production_shift_type(self, production_date: str) -> dict[str, Any]:
        """Read the selected date's latest ShiftType from the existing dbo view."""
        try:
            selected_date = datetime.fromisoformat(production_date).date()
        except ValueError:
            raise ValueError("production_date must use YYYY-MM-DD format.") from None
        if selected_date.isoformat() != production_date:
            raise ValueError("production_date must use YYYY-MM-DD format.")
        with self._connection() as (_, cursor):
            cursor.execute(
                "SELECT TOP (1) id,UpdateTime,ProdDate,ShiftType "
                "FROM dbo.vw_ProductionDetails WHERE ProdDate=? "
                "ORDER BY UpdateTime DESC,id DESC",
                (selected_date,),
            )
            row = cursor.fetchone()
        if row is None:
            return {
                "production_date": production_date,
                "selected_type": 3,
                "type_code": "TYPE 3",
                "status": "DEFAULT",
                "record_id": None,
                "update_time": None,
            }
        raw_type = str(row[3] or "").strip().upper()
        normalized_type = raw_type.removeprefix("TYPE ")
        if normalized_type not in {"1", "2", "3"}:
            raise SourceUnavailable("dbo.vw_ProductionDetails returned an unsupported ShiftType value.")
        selected_type = int(normalized_type)
        return {
            "production_date": production_date,
            "selected_type": selected_type,
            "type_code": f"TYPE {selected_type}",
            "status": "SAVED",
            "record_id": int(row[0]),
            "update_time": self._text(row[1]),
        }

    def save_production_shift_type(self, production_date: str, selected_type: int) -> dict[str, Any]:
        """Append the operator's Type selection to the existing dbo.ProductionDetails table."""
        try:
            selected_date = datetime.fromisoformat(production_date).date()
        except ValueError:
            raise ValueError("production_date must use YYYY-MM-DD format.") from None
        if selected_date.isoformat() != production_date:
            raise ValueError("production_date must use YYYY-MM-DD format.")
        if selected_type not in (1, 2, 3):
            raise ValueError("selected_type must be 1, 2, or 3.")
        with self._connection(write=True) as (_, cursor):
            cursor.execute(
                "INSERT INTO dbo.ProductionDetails (UpdateTime,ProdDate,ShiftType) "
                "OUTPUT INSERTED.id,INSERTED.UpdateTime,INSERTED.ProdDate,INSERTED.ShiftType "
                "VALUES (GETDATE(),?,?)",
                (selected_date, str(selected_type)),
            )
            row = cursor.fetchone()
            if row is None:
                raise SourceUnavailable("ShiftType insert returned no row; the transaction was rolled back.")
        return {
            "production_date": row[2].isoformat(),
            "selected_type": selected_type,
            "type_code": f"TYPE {selected_type}",
            "status": "SAVED",
            "record_id": int(row[0]),
            "update_time": self._text(row[1]),
        }

    @staticmethod
    def _latest_worktime_rows(cursor: Any) -> list[dict[str, Any]]:
        cursor.execute(
            "WITH RankedWorkTime AS ("
            "SELECT id,RecTime,RTRIM(WorkType) AS WorkType,RTRIM(ShiftNo) AS ShiftNo,"
            "StartTime,StopTime,speed,ROW_NUMBER() OVER ("
            "PARTITION BY RTRIM(WorkType),RTRIM(ShiftNo) ORDER BY RecTime DESC,id DESC"
            ") AS rw FROM dbo.WorkTime WHERE RTRIM(WorkType) IN ('1','2','3')) "
            "SELECT id,RecTime,WorkType,ShiftNo,StartTime,StopTime,speed,rw "
            "FROM RankedWorkTime WHERE rw=1 ORDER BY WorkType,ShiftNo"
        )
        return [
            {
                "record_id": int(row[0]),
                "rec_time": SQLServerProductionRepository._text(row[1]),
                "work_type": str(row[2] or "").strip(),
                "shift_no": str(row[3] or "").strip(),
                "start_time": SQLServerProductionRepository._text(row[4]),
                "stop_time": SQLServerProductionRepository._text(row[5]),
                "speed": row[6],
                "rw": int(row[7]),
                "active": row[4] is not None and row[5] is not None,
            }
            for row in cursor.fetchall()
        ]

    def worktime_shift_settings(self) -> dict[str, Any]:
        """Return the latest WorkTime record for each trimmed WorkType/ShiftNo."""
        with self._connection() as (_, cursor):
            rows = self._latest_worktime_rows(cursor)
        update_times = [row["rec_time"] for row in rows if row["rec_time"]]
        return {
            "source": "OMAG.dbo.WorkTime",
            "schedule_view": "OMAG.dbo.vw_TypeShift",
            "rows": rows,
            "latest_update_time": max(update_times) if update_times else None,
        }

    @staticmethod
    def _parse_worktime_time(value: Any, label: str) -> time:
        if not isinstance(value, str):
            raise ValueError(f"{label} must be a valid time.")
        try:
            parsed = time.fromisoformat(value.strip())
        except ValueError:
            raise ValueError(f"{label} must use HH:MM or HH:MM:SS format.") from None
        if parsed.tzinfo is not None:
            raise ValueError(f"{label} must not include a timezone.")
        return parsed

    @staticmethod
    def _validate_worktime_intervals(rows: list[dict[str, Any]]) -> None:
        by_type: dict[str, list[tuple[str, float, float]]] = {}
        for row in rows:
            start = row.get("start_time")
            stop = row.get("stop_time")
            if start is None or stop is None:
                continue

            def minutes(value: time) -> float:
                return value.hour * 60 + value.minute + value.second / 60 + value.microsecond / 60_000_000

            start_minute = minutes(start)
            stop_minute = minutes(stop)
            segments = [(start_minute, stop_minute)] if stop_minute > start_minute else [(start_minute, 1440.0)]
            if stop_minute < start_minute and stop_minute > 0:
                segments.append((0.0, stop_minute))
            by_type.setdefault(row["work_type"], []).extend(
                (row["shift_no"], segment_start, segment_stop)
                for segment_start, segment_stop in segments
            )

        for work_type, segments in by_type.items():
            for index, (shift_no, start, stop) in enumerate(segments):
                for other_shift, other_start, other_stop in segments[index + 1:]:
                    if shift_no != other_shift and max(start, other_start) < min(stop, other_stop):
                        raise ValueError(f"WorkType {work_type} Shift {shift_no} overlaps Shift {other_shift}.")

    def save_worktime_shift_settings(self, changes: list[dict[str, Any]]) -> dict[str, Any]:
        """Append changed shift rows atomically; preserve current speed and history."""
        normalized: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        for change in changes:
            work_type = str(change.get("work_type", "")).strip()
            shift_no = str(change.get("shift_no", "")).strip()
            if work_type not in {"1", "2", "3"}:
                raise ValueError("work_type must be 1, 2, or 3.")
            if len(shift_no) != 1:
                raise ValueError("shift_no must be one character from the SQL WorkTime source.")
            key = (work_type, shift_no)
            if key in seen:
                raise ValueError(f"WorkType {work_type} Shift {shift_no} was submitted more than once.")
            seen.add(key)
            start_time = self._parse_worktime_time(change.get("start_time"), "start_time")
            stop_time = self._parse_worktime_time(change.get("stop_time"), "stop_time")
            if start_time == stop_time:
                raise ValueError(f"WorkType {work_type} Shift {shift_no} cannot have a zero-length period.")
            normalized.append({
                "work_type": work_type,
                "shift_no": shift_no,
                "start_time": start_time,
                "stop_time": stop_time,
            })

        inserted = 0
        with self._connection(write=True) as (_, cursor):
            current_rows = self._latest_worktime_rows(cursor)
            current_by_key = {(row["work_type"], row["shift_no"]): row for row in current_rows}
            pending: list[tuple[str, str, time, time, Any]] = []
            candidate_by_key: dict[tuple[str, str], dict[str, Any]] = {}
            for current in current_rows:
                candidate_by_key[(current["work_type"], current["shift_no"])] = {
                    "work_type": current["work_type"], "shift_no": current["shift_no"],
                    "start_time": self._parse_worktime_time(current["start_time"], "current StartTime") if current["start_time"] is not None else None,
                    "stop_time": self._parse_worktime_time(current["stop_time"], "current StopTime") if current["stop_time"] is not None else None,
                }
            for change in normalized:
                key = (change["work_type"], change["shift_no"])
                current = current_by_key.get(key)
                if current is None:
                    raise ValueError(f"WorkType {key[0]} Shift {key[1]} is not present in dbo.WorkTime.")
                current_start = candidate_by_key[key]["start_time"]
                current_stop = candidate_by_key[key]["stop_time"]
                candidate_by_key[key] = {
                    **candidate_by_key[key],
                    "start_time": change["start_time"], "stop_time": change["stop_time"],
                }
                if current_start == change["start_time"] and current_stop == change["stop_time"]:
                    continue
                pending.append((key[0], key[1], change["start_time"], change["stop_time"], current["speed"]))

            self._validate_worktime_intervals(list(candidate_by_key.values()))

            if pending:
                cursor.execute("SELECT GETDATE()")
                timestamp_row = cursor.fetchone()
                if timestamp_row is None or timestamp_row[0] is None:
                    raise SourceUnavailable("SQL Server did not return a WorkTime configuration timestamp.")
                configuration_time = timestamp_row[0]
                for work_type, shift_no, start_time, stop_time, speed in pending:
                    cursor.execute(
                        "INSERT INTO dbo.WorkTime (RecTime,WorkType,ShiftNo,StartTime,StopTime,speed) "
                        "VALUES (?,?,?,?,?,?)",
                        (configuration_time, work_type, shift_no, start_time, stop_time, speed),
                    )
                    inserted += 1
            latest_rows = self._latest_worktime_rows(cursor)

        update_times = [row["rec_time"] for row in latest_rows if row["rec_time"]]
        return {
            "source": "OMAG.dbo.WorkTime",
            "schedule_view": "OMAG.dbo.vw_TypeShift",
            "status": "SAVED" if inserted else "NO_CHANGES",
            "inserted_count": inserted,
            "update_time": self._text(configuration_time) if inserted else None,
            "latest_update_time": max(update_times) if update_times else None,
            "rows": latest_rows,
        }

    @staticmethod
    def _now() -> datetime:
        return datetime.now(BANGKOK).replace(microsecond=0)

    @staticmethod
    def _moment(value: datetime | str | None) -> datetime:
        if value is None:
            return SQLServerProductionRepository._now()
        moment = value if isinstance(value, datetime) else datetime.fromisoformat(value)
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=BANGKOK)
        return moment

    @staticmethod
    def _text(value: Any) -> str | None:
        return value.isoformat() if hasattr(value, "isoformat") else (None if value is None else str(value))

    def _readback(self, sql: str, params: tuple[Any, ...]) -> Any:
        try:
            with self._connection() as (_, cursor):
                cursor.execute(sql, params)
                row = cursor.fetchone()
        except SourceUnavailable as exc:
            raise SourceUnavailable(f"The SQL transaction committed, but subsequent read-back failed ({exc}); reconcile before retrying.") from None
        if row is None:
            raise SourceUnavailable("The SQL transaction committed, but its subsequent read-back found no row; reconcile the database before retrying.")
        return row

    @staticmethod
    def _require_text(value: str, label: str, maximum: int) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError(f"{label} is required.")
        if len(normalized) > maximum:
            raise ValueError(f"{label} must be {maximum} characters or fewer.")
        return normalized

    def health(self) -> dict[str, Any]:
        with self._connection() as (_, cursor):
            missing, missing_columns = self._schema_readiness(cursor)
        schema_ready = not missing and not missing_columns
        return {"connected": True, "schema_ready": schema_ready,
            "missing_tables": missing, "missing_columns": missing_columns,
            "writes_enabled": schema_ready,
            "scg_lot_number_proposals_ready": SCG_LOT_NUMBER_PROPOSALS_READY,
            "official_lot_numbering_ready": OFFICIAL_LOT_NUMBERING_READY,
            "identity": self._last_identity}

    def bootstrap(self, mock_context: dict[str, Any]) -> dict[str, Any]:
        status = self.health()
        live_context = {
            **mock_context,
            "products": [], "lots": [], "production_entries": [], "reject_entries": [],
            "run_events": [], "curing_entries": [], "depal_entries": [], "moulds": [],
            "mould_history": [], "lot_name_history": [], "auto_lot_drafts": [],
            "reject_reasons": [],
        }
        if not status["schema_ready"]:
            return {**live_context, "mode": "LIVE SOURCES · LOT SCHEMA NOT INSTALLED", "production_storage": status}
        with self._connection() as (_, cursor):
            cursor.execute(
                "SELECT p.id,p.ProductCode,p.ProductName,p.ProductNameThai,p.ProductFamily,s.StandardPiecesPerDrop,s.StandardCycleTimeSec,p.IsActive "
                "FROM omagmes.Product p OUTER APPLY (SELECT TOP (1) StandardPiecesPerDrop,StandardCycleTimeSec "
                "FROM omagmes.ProductStandardRevision WHERE ProductID=p.id AND StatusCode='APPROVED' "
                "AND EffectiveFrom<=SYSDATETIMEOFFSET() AND (EffectiveTo IS NULL OR EffectiveTo>SYSDATETIMEOFFSET()) "
                "ORDER BY RevisionNo DESC) s WHERE p.IsActive=1 ORDER BY p.ProductCode,p.id"
            )
            products = [{"id": int(r[0]), "code": str(r[1]), "name": str(r[2]), "name_thai": r[3], "family": r[4] or "", "standard_pieces_per_drop": r[5], "standard_cycle_time_sec": r[6], "active": bool(r[7])} for r in cursor.fetchall()]
            cursor.execute(
                "SELECT l.id, l.ProductionRunID, l.ProductID, l.ColorCode, l.LotName, l.LotStartedAt, "
                "p.ProductCode, p.ProductName, l.LotNo, l.ProductionDate, l.ShiftID, l.ShiftScheduleVersionID, l.LotEndedAt "
                "FROM omagmes.ProductionLot l "
                "JOIN omagmes.Product p ON p.id=l.ProductID ORDER BY l.LotStartedAt DESC,l.id DESC"
            )
            lots = [{"id": int(r[0]), "run_id": int(r[1]), "product_id": int(r[2]), "color": str(r[3]), "lot_name": str(r[4]), "started_at": self._text(r[5]), "product_code": str(r[6]), "product_name": str(r[7]), "lot_number": str(r[8]), "lot_start_production_date": r[9].isoformat(), "lot_start_shift_id": int(r[10]), "lot_start_shift_schedule_version_id": int(r[11]), "is_open": r[12] is None} for r in cursor.fetchall()]
            cursor.execute("SELECT id, ProductionLotID, PressDrops, WetGoodPieces, SuggestedPressDrops, SuggestedWetGoodPieces, SourceCode, OperatorNote, EnteredBy, RecordedAt, ProductionAt, ProductionDate, ShiftScheduleVersionID, ShiftID FROM omagmes.ProductionEntry WHERE IsDeleted=0 ORDER BY ProductionAt DESC,id DESC")
            production = [{"id": int(r[0]), "lot_id": int(r[1]), "actual_drops": int(r[2]), "wet_good_pieces": int(r[3]), "suggested_actual_drops": r[4], "suggested_wet_good_pieces": r[5], "source": str(r[6]), "operator_note": r[7], "entered_by": str(r[8]), "saved_at": self._text(r[9]), "production_at": self._text(r[10]), "production_date": r[11].isoformat(), "shift_schedule_version_id": int(r[12]), "shift_id": int(r[13]) if r[13] is not None else None, "mode": "SQL PERSISTED"} for r in cursor.fetchall()]
            cursor.execute("SELECT id,ReasonCode,ReasonName FROM omagmes.WetRejectReason WHERE IsActive=1 ORDER BY ReasonCode,id")
            reject_reasons = [{"id": int(r[0]), "code": str(r[1]), "label": str(r[2])} for r in cursor.fetchall()]
            cursor.execute("SELECT m.id,m.ProductID,m.MouldCode,m.MouldName,m.CurrentAgeDrops,m.LifetimeAgeDrops,m.StatusCode,p.ProductCode FROM omagmes.Mould m JOIN omagmes.Product p ON p.id=m.ProductID WHERE m.IsActive=1 ORDER BY m.MouldCode,m.id")
            moulds = [{"id": int(r[0]), "product_id": int(r[1]), "code": str(r[2]), "name": str(r[3]), "current_age_drops": int(r[4]), "lifetime_age_drops": int(r[5]), "status": str(r[6]), "product_code": str(r[7])} for r in cursor.fetchall()]
            cursor.execute("SELECT id, ProductionLotID, InputQuantity, QuantityUnitCode, OperatorNote, EnteredBy, RecordedAt FROM omagmes.CuringInputEntry ORDER BY RecordedAt DESC,id DESC")
            curing = [{"id": int(r[0]), "lot_id": int(r[1]), "quantity": int(r[2]), "unit_code": str(r[3]), "note": r[4], "entered_by": str(r[5]), "saved_at": self._text(r[6]), "mode": "SQL PERSISTED"} for r in cursor.fetchall()]
            cursor.execute("SELECT id, ProductionLotID, Quantity, QuantityUnitCode, OperatorNote, EnteredBy, RecordedAt FROM omagmes.DepalletEvent ORDER BY RecordedAt DESC,id DESC")
            depallet = [{"id": int(r[0]), "lot_id": int(r[1]), "quantity": int(r[2]), "unit_code": str(r[3]), "note": r[4], "entered_by": str(r[5]), "saved_at": self._text(r[6]), "mode": "SQL PERSISTED"} for r in cursor.fetchall()]
        return {**live_context, "mode": "LIVE SQL · PRODUCTION WORKFLOW", "products": products, "lots": lots,
            "production_entries": production, "curing_entries": curing, "depal_entries": depallet,
            "reject_reasons": reject_reasons, "moulds": moulds,
                "production_storage": {**status, "schema_ready": True}}

    def production_day_lots(self, production_date: str, start_at: datetime, end_at: datetime) -> list[dict[str, Any]]:
        """Read official Lots whose actual interval overlaps the selected operating day."""
        try:
            parsed = datetime.fromisoformat(production_date).date()
        except ValueError:
            raise ValueError("production_date must use YYYY-MM-DD format.") from None
        if parsed.isoformat() != production_date or start_at >= end_at:
            raise ValueError("A valid Production Date and positive operating-day interval are required.")
        with self._connection() as (_, cursor):
            cursor.execute(
                "SELECT l.id,l.LotNo,l.LotName,l.ProductID,p.ProductCode,p.ProductName,l.ColorCode,"
                "l.ProductionDate,l.ShiftID,l.LotStartedAt,l.LotEndedAt "
                "FROM omagmes.ProductionLot l JOIN omagmes.Product p ON p.id=l.ProductID "
                "WHERE l.LotStartedAt<? AND (l.LotEndedAt IS NULL OR l.LotEndedAt>?) "
                "ORDER BY l.LotStartedAt,l.id",
                (end_at.replace(tzinfo=None), start_at.replace(tzinfo=None)),
            )
            rows = cursor.fetchall()
        return [{
            "id": int(row[0]), "lot_number": str(row[1]) if row[1] else "PENDING", "lot_name": str(row[2]),
            "product_id": int(row[3]), "product_code": str(row[4] or ""), "product_name": str(row[5] or ""),
            "color": str(row[6]), "lot_start_production_date": row[7].isoformat(),
            "shift_id": int(row[8]) if row[8] is not None else None,
            "started_at": self._text(row[9]), "ended_at": self._text(row[10]),
            "source": "OMAGMES OFFICIAL PRODUCTION LOT",
        } for row in rows]

    @staticmethod
    def _schema_readiness(cursor: Any) -> tuple[list[str], list[str]]:
        cursor.execute(
            "SELECT name FROM sys.tables WHERE schema_id=SCHEMA_ID(N'omagmes') AND name IN ("
            + ",".join("?" for _ in REQUIRED_PRODUCTION_TABLES)
            + ")",
            REQUIRED_PRODUCTION_TABLES,
        )
        existing = {str(row[0]) for row in cursor.fetchall()}
        missing_tables = [name for name in REQUIRED_PRODUCTION_TABLES if name not in existing]
        cursor.execute(
            "SELECT t.name,c.name FROM sys.tables t "
            "JOIN sys.schemas s ON s.schema_id=t.schema_id "
            "JOIN sys.columns c ON c.object_id=t.object_id "
            "WHERE s.name=N'omagmes' AND t.name IN ("
            + ",".join("?" for _ in REQUIRED_PRODUCTION_TABLES)
            + ")",
            REQUIRED_PRODUCTION_TABLES,
        )
        existing_columns = {(str(row[0]), str(row[1])) for row in cursor.fetchall()}
        missing_columns = [
            f"{table}.{column}"
            for table, columns in REQUIRED_PRODUCTION_COLUMNS.items()
            for column in columns
            if (table, column) not in existing_columns
        ]
        return missing_tables, missing_columns

    def _ensure_schema(self, cursor: Any) -> None:
        missing_tables, missing_columns = self._schema_readiness(cursor)
        if missing_tables or missing_columns:
            details = []
            if missing_tables:
                details.append("missing tables: " + ", ".join(missing_tables))
            if missing_columns:
                details.append("missing columns: " + ", ".join(missing_columns))
            raise SourceUnavailable("OmagMES production schema is incomplete; no data was written (" + "; ".join(details) + ").")

    def create_lot(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not OFFICIAL_LOT_NUMBERING_READY:
            raise SourceUnavailable("Official Lot No. generation is not enabled; Lot numbering policy requires review.")
        name = self._require_text(str(payload.get("lot_name", "")), "LotName", 120)
        color = self._require_text(str(payload.get("color", "")), "Color", 60)
        actor = self._require_text(str(payload.get("operator_id", "")), "Operator ID", 200)
        product_id = int(payload["product_id"])
        started = self._moment(payload.get("started_at")).replace(second=0, microsecond=0)
        production_date = str(payload.get("production_date") or "")
        shift_id = int(payload.get("shift_id") or 0)
        shift_code = str(payload.get("shift_code") or "")
        machine_code = str(payload.get("machine_code") or "")
        if not production_date or shift_id <= 0:
            raise SourceUnavailable("Effective Production Date and Shift identity are required for official Lot numbering.")
        try:
            lot_date = datetime.fromisoformat(production_date).date()
            shift_schedule_version_id = int(payload.get("shift_schedule_version_id") or 0)
            if shift_schedule_version_id <= 0:
                raise ValueError("Effective Shift Schedule version is required for official Lot numbering.")
            build_scg_lot_number(lot_date, shift_code, 1, machine_code)
        except (ValueError, LotNumberingError) as exc:
            raise SourceUnavailable(str(exc)) from None
        with self._connection(write=True) as (_, cursor):
            cursor.execute("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE")
            self._ensure_schema(cursor)
            cursor.execute(
                "SELECT p.ProductFamily,s.id,s.StandardPiecesPerDrop,s.StandardCycleTimeSec "
                "FROM omagmes.Product p WITH (UPDLOCK,HOLDLOCK) "
                "OUTER APPLY (SELECT id,StandardPiecesPerDrop,StandardCycleTimeSec FROM omagmes.ProductStandardRevision s "
                "WITH (UPDLOCK,HOLDLOCK) WHERE s.ProductID=p.id AND s.StatusCode='APPROVED' "
                "AND s.EffectiveFrom<=? AND (s.EffectiveTo IS NULL OR s.EffectiveTo>?) ) s "
                "WHERE p.id=? AND p.IsActive=1",
                (started, started, product_id),
            )
            product_matches = cursor.fetchall()
            if not product_matches:
                raise SourceUnavailable("Selected Product ID is not an active authoritative OmagMES Product.")
            if len(product_matches) != 1:
                raise SourceUnavailable("Multiple approved Product standard revisions apply at this Lot start; standard history requires reconciliation.")
            product_info = product_matches[0]
            if product_info[1] is None:
                raise SourceUnavailable("No approved Product standard revision applies at this Lot start; no production Lot was written.")
            cursor.execute("SELECT TOP (1) id, ProductID, StartedAt FROM omagmes.ProductionRun WITH (UPDLOCK,HOLDLOCK) WHERE StatusCode='OPEN' ORDER BY id DESC")
            active_run = cursor.fetchone()
            active_lot = None
            if active_run is not None:
                cursor.execute("SELECT TOP (1) id, ColorCode, ProductStandardRevisionID, LotStartedAt FROM omagmes.ProductionLot WITH (UPDLOCK,HOLDLOCK) WHERE ProductionRunID=? AND LotEndedAt IS NULL ORDER BY id DESC", (int(active_run[0]),))
                active_lot = cursor.fetchone()
                if active_lot is None:
                    raise SourceUnavailable("Open Production Run has no open Lot; operator reconciliation is required.")
                if payload.get("previous_lot_id") is not None and int(payload["previous_lot_id"]) != int(active_lot[0]):
                    raise SourceUnavailable("Selected previous Lot is stale; reload the official Lot list.")
                if started < self._moment(active_run[2]) or started < self._moment(active_lot[3]):
                    raise ValueError("A new Lot cannot start before the active Run or Lot start timestamp.")
                transition = classify_lot_change(int(active_run[1]), str(active_lot[1]), product_id, color)
                if transition == "CONTINUE":
                    cursor.execute(
                        "SELECT l.id,l.ProductionRunID,l.ProductID,l.ColorCode,l.LotName,l.LotStartedAt,p.ProductCode,p.ProductName,l.LotNo "
                        "FROM omagmes.ProductionLot l JOIN omagmes.Product p ON p.id=l.ProductID WHERE l.id=?",
                        (int(active_lot[0]),),
                    )
                    return self._lot_row(cursor.fetchone(), "CONTINUED")
                if transition == "COLOR_CHANGE" and int(active_lot[2]) != int(product_info[1]):
                    raise SourceUnavailable("A Product standard revision became effective during the open Run; Lot snapshot transition policy is unresolved.")
                if transition == "COLOR_CHANGE":
                    run_id = int(active_run[0])
                elif transition == "PRODUCT_CHANGE":
                    cursor.execute("UPDATE omagmes.ProductionLot SET LotEndedAt=? WHERE id=? AND LotEndedAt IS NULL", (started, int(active_lot[0])))
                    cursor.execute("UPDATE omagmes.ProductionRun SET EndedAt=?, StatusCode='CLOSED' WHERE id=? AND StatusCode='OPEN'", (started, int(active_run[0])))
                    cursor.execute("INSERT INTO omagmes.ProductionRun (ProductID, StartedAt, StatusCode, CreatedBy) OUTPUT INSERTED.id VALUES (?, ?, 'OPEN', ?)", (product_id, started, actor))
                    run_id = int(cursor.fetchone()[0])
                    active_lot = None
            else:
                transition = "INITIAL"
                run_id = 0
            if transition == "INITIAL":
                cursor.execute("INSERT INTO omagmes.ProductionRun (ProductID, StartedAt, StatusCode, CreatedBy) OUTPUT INSERTED.id VALUES (?, ?, 'OPEN', ?)", (product_id, started, actor))
                run_id = int(cursor.fetchone()[0])
            if transition == "COLOR_CHANGE" and active_lot is not None:
                cursor.execute("UPDATE omagmes.ProductionLot SET LotEndedAt=? WHERE id=? AND LotEndedAt IS NULL", (started, int(active_lot[0])))
            sequence = self._allocate_lot_sequence(cursor, lot_date, shift_code)
            lot_number = build_scg_lot_number(lot_date, shift_code, sequence, machine_code)
            cursor.execute(
                "INSERT INTO omagmes.ProductionLot (ProductionRunID, ProductID, ColorCode, ProductFamilySnapshot, "
                "ProductStandardRevisionID, StandardPiecesPerDropSnapshot, StandardCycleTimeSecSnapshot, LotName, LotStartedAt, CreatedBy, "
                "LotNo, ProductionDate, ShiftScheduleVersionID, ShiftID, LotSequence, MachineCode) "
                "OUTPUT INSERTED.id VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (run_id, product_id, color, product_info[0], int(product_info[1]), int(product_info[2]), product_info[3], name, started, actor,
                 lot_number, lot_date, shift_schedule_version_id, shift_id, sequence, machine_code),
            )
            lot_id = int(cursor.fetchone()[0])
            reset_evidence = payload.get("auto_lot_reset_evidence")
            if reset_evidence is not None:
                reason = self._require_text(str(payload.get("reset_confirmation_reason", "")), "Reset review reason", 500)
                before = reset_evidence["before_sample"]
                decreased = reset_evidence["decrease_sample"]
                restart = reset_evidence.get("restart_sample")
                cursor.execute(
                    "INSERT INTO omagmes.AutoLotResetReview "
                    "(CandidateID,SourceTag,BeforeSourceID,BeforeAt,BeforeValue,DecreaseSourceID,DecreaseAt,DecreaseValue,"
                    "RestartSourceID,RestartAt,RestartValue,PostResetDropsLowerBound,ProductionLotID,ProductionDate,ShiftID,"
                    "ShiftScheduleVersionID,ConfirmedBy,ConfirmationReason,ReviewedAt) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (reset_evidence["id"], reset_evidence["source_tag"], int(before["source_id"]),
                     self._moment(datetime.fromisoformat(before["timestamp"])), before["value"], int(decreased["source_id"]),
                     self._moment(datetime.fromisoformat(decreased["timestamp"])), decreased["value"],
                     int(restart["source_id"]) if restart else None,
                     self._moment(datetime.fromisoformat(restart["timestamp"])) if restart else None,
                     restart["value"] if restart else None, reset_evidence["post_reset_run_drops_lower_bound"],
                     lot_id, lot_date, shift_id, shift_schedule_version_id, actor, reason, self._now()),
                )
            cursor.execute(
                "SELECT l.id,l.ProductionRunID,l.ProductID,l.ColorCode,l.LotName,l.LotStartedAt,p.ProductCode,p.ProductName,l.LotNo "
                "FROM omagmes.ProductionLot l JOIN omagmes.Product p ON p.id=l.ProductID WHERE l.id=?",
                (lot_id,),
            )
            row = cursor.fetchone()
        row = self._readback(
            "SELECT l.id,l.ProductionRunID,l.ProductID,l.ColorCode,l.LotName,l.LotStartedAt,p.ProductCode,p.ProductName,l.LotNo "
            "FROM omagmes.ProductionLot l JOIN omagmes.Product p ON p.id=l.ProductID WHERE l.id=?",
            (lot_id,),
        )
        return self._lot_row(row, transition)

    @staticmethod
    def _allocate_lot_sequence(cursor: Any, production_date: Any, shift_code: str) -> int:
        """Lock one scope and advance past both sequence state and saved Lots."""
        cursor.execute(
            "SELECT LastSequence FROM omagmes.LotNumberSequence WITH (UPDLOCK,HOLDLOCK) "
            "WHERE PlantCode=? AND ProductionDate=? AND ShiftCode=?",
            (SCG_PLANT_CODE, production_date, shift_code),
        )
        row = cursor.fetchone()
        prefix = SQLServerProductionRepository._lot_number_prefix(production_date, shift_code)
        cursor.execute(
            "SELECT MAX(TRY_CONVERT(int,SUBSTRING(LotNo,9,2))) "
            "FROM omagmes.ProductionLot WITH (UPDLOCK,HOLDLOCK) "
            "WHERE LEFT(LotNo,8)=?",
            (prefix,),
        )
        official_row = cursor.fetchone()
        official_sequence = int(official_row[0]) if official_row and official_row[0] is not None else 0
        stored_sequence = int(row[0]) if row is not None else 0
        last_sequence = max(stored_sequence, official_sequence) or None
        sequence = next_lot_sequence(last_sequence)
        if row is None:
            cursor.execute(
                "INSERT INTO omagmes.LotNumberSequence (PlantCode,ProductionDate,ShiftCode,LastSequence) VALUES (?,?,?,?)",
                (SCG_PLANT_CODE, production_date, shift_code, sequence),
            )
            return sequence
        cursor.execute(
            "UPDATE omagmes.LotNumberSequence SET LastSequence=? WHERE PlantCode=? AND ProductionDate=? AND ShiftCode=?",
            (sequence, SCG_PLANT_CODE, production_date, shift_code),
        )
        return sequence

    @staticmethod
    def _lot_number_prefix(production_date: Any, shift_code: str) -> str:
        lot_date = production_date if hasattr(production_date, "year") else datetime.fromisoformat(str(production_date)).date()
        buddhist_year_two_digits = (lot_date.year + 543) % 100
        return f"{SCG_PLANT_CODE}{lot_date.day:02d}{lot_date.month:02d}{buddhist_year_two_digits:02d}{shift_code}"

    def propose_lot_numbers(
        self, *, production_date: str, shift_code: str, count: int, line_code: str = SCG_LINE_CODE,
    ) -> list[dict[str, Any]]:
        """Return distinct, non-reserving proposals based on saved sequence state."""
        if not SCG_LOT_NUMBER_PROPOSALS_READY:
            raise SourceUnavailable("SCG Lot number proposals are not configured.")
        if count <= 0:
            raise SourceUnavailable("At least one Lot is required to propose a sequence.")
        try:
            lot_date = datetime.fromisoformat(production_date).date()
            build_scg_lot_number(lot_date, shift_code, 1, line_code)
        except (ValueError, LotNumberingError) as exc:
            raise SourceUnavailable(str(exc)) from None
        with self._connection() as (_, cursor):
            self._ensure_schema(cursor)
            cursor.execute(
                "SELECT LastSequence FROM omagmes.LotNumberSequence "
                "WHERE PlantCode=? AND ProductionDate=? AND ShiftCode=?",
                (SCG_PLANT_CODE, lot_date, shift_code),
            )
            row = cursor.fetchone()
            number_prefix = self._lot_number_prefix(lot_date, shift_code)
            cursor.execute(
                "SELECT MAX(TRY_CONVERT(int,SUBSTRING(LotNo,9,2))) "
                "FROM omagmes.ProductionLot WHERE LEFT(LotNo,8)=?",
                (number_prefix,),
            )
            official_row = cursor.fetchone()
        committed_sequence = int(row[0]) if row is not None else 0
        official_sequence = int(official_row[0]) if official_row is not None and official_row[0] is not None else 0
        last_sequence = max(committed_sequence, official_sequence) or None
        proposals = []
        for _ in range(count):
            sequence = next_lot_sequence(last_sequence)
            proposals.append({
                "proposed_lot_number": build_scg_lot_number(lot_date, shift_code, sequence, line_code),
                "sequence": sequence,
                "reserved": False,
                "note": "Display-only proposal; sequence is rechecked and allocated under a transaction lock only on explicit SAVE.",
            })
            last_sequence = sequence
        return proposals

    def propose_lot_number(
        self, *, production_date: str, shift_code: str, machine_code: str = SCG_LINE_CODE,
    ) -> dict[str, Any]:
        """Compatibility wrapper for one non-reserving SCG Lot number proposal."""
        return self.propose_lot_numbers(
            production_date=production_date, shift_code=shift_code, count=1, line_code=machine_code,
        )[0]

    @staticmethod
    def _lot_row(row: Any, transition: str | None = None) -> dict[str, Any]:
        return {"id": int(row[0]), "run_id": int(row[1]), "product_id": int(row[2]), "color": str(row[3]),
                "lot_name": str(row[4]), "started_at": SQLServerProductionRepository._text(row[5]),
                "product_code": str(row[6]), "product_name": str(row[7]),
                "lot_number": str(row[8]) if len(row) > 8 and row[8] is not None else None,
                "mode": "SQL PERSISTED · OFFICIAL LOT", "transition": transition}

    def rename_lot(self, lot_id: int, *, new_name: str, reason: str, operator_id: str) -> dict[str, Any]:
        name = self._require_text(new_name, "New LotName", 120)
        why = self._require_text(reason, "Change reason", 500)
        actor = self._require_text(operator_id, "Operator ID", 200)
        changed_at = self._now()
        with self._connection(write=True) as (_, cursor):
            self._ensure_schema(cursor)
            cursor.execute("SELECT LotName FROM omagmes.ProductionLot WITH (UPDLOCK,HOLDLOCK) WHERE id=?", (lot_id,))
            row = cursor.fetchone()
            if row is None:
                raise SourceUnavailable("Official Lot ID was not found.")
            old_name = str(row[0])
            if old_name == name:
                raise ValueError("New LotName must differ from the current name.")
            cursor.execute("UPDATE omagmes.ProductionLot SET LotName=? WHERE id=?", (name, lot_id))
            cursor.execute("INSERT INTO omagmes.ProductionLotNameHistory (ProductionLotID,OldLotName,NewLotName,ChangedBy,ChangedAt,ChangeReason) VALUES (?,?,?,?,?,?)", (lot_id, old_name, name, actor, changed_at, why))
            cursor.execute("SELECT l.id,l.ProductionRunID,l.ProductID,l.ColorCode,l.LotName,l.LotStartedAt,p.ProductCode,p.ProductName FROM omagmes.ProductionLot l JOIN omagmes.Product p ON p.id=l.ProductID WHERE l.id=?", (lot_id,))
            lot = self._lot_row(cursor.fetchone())
            cursor.execute("SELECT TOP (1) id,OldLotName,NewLotName,ChangedBy,ChangedAt,ChangeReason FROM omagmes.ProductionLotNameHistory WHERE ProductionLotID=? ORDER BY id DESC", (lot_id,))
            history = cursor.fetchone()
        lot_row = self._readback(
            "SELECT l.id,l.ProductionRunID,l.ProductID,l.ColorCode,l.LotName,l.LotStartedAt,p.ProductCode,p.ProductName "
            "FROM omagmes.ProductionLot l JOIN omagmes.Product p ON p.id=l.ProductID WHERE l.id=?",
            (lot_id,),
        )
        history = self._readback("SELECT TOP (1) id,OldLotName,NewLotName,ChangedBy,ChangedAt,ChangeReason FROM omagmes.ProductionLotNameHistory WHERE ProductionLotID=? ORDER BY id DESC", (lot_id,))
        return {"lot": self._lot_row(lot_row), "history": {"id": int(history[0]), "lot_id": lot_id, "old_name": history[1], "new_name": history[2], "actor": history[3], "changed_at": self._text(history[4]), "reason": history[5]}, "mode": "SQL PERSISTED"}

    def save_production(self, payload: dict[str, Any]) -> dict[str, Any]:
        if payload.get("operator_confirmed") is not True:
            raise ValueError("Operator confirmation is required before saving Press production quantities.")
        actor = self._require_text(str(payload.get("operator_id", "")), "Operator ID", 200)
        reason = self._require_text(str(payload.get("change_reason") or "Operator-confirmed production SAVE"), "Audit reason", 500)
        recorded = self._now()
        production_at = self._moment(payload.get("production_at"))
        try:
            production_date = datetime.fromisoformat(str(payload["production_date"])).date()
            schedule_version_id = int(payload["shift_schedule_version_id"])
            shift_id = int(payload["shift_id"]) if payload.get("shift_id") is not None else None
        except (KeyError, TypeError, ValueError) as exc:
            raise SourceUnavailable(f"Actual Production Date and Shift Schedule version are required ({type(exc).__name__}).") from None
        with self._connection(write=True) as (_, cursor):
            self._ensure_schema(cursor)
            cursor.execute("SELECT ProductStandardRevisionID,StandardPiecesPerDropSnapshot,StandardCycleTimeSecSnapshot FROM omagmes.ProductionLot WHERE id=?", (int(payload["lot_id"]),))
            lot_snapshot = cursor.fetchone()
            if lot_snapshot is None:
                raise SourceUnavailable("Production entry must reference an official ProductionLot.id.")
            cursor.execute("INSERT INTO omagmes.ProductionEntry (ProductionLotID,PressDrops,WetGoodPieces,SuggestedPressDrops,SuggestedWetGoodPieces,ProductStandardRevisionID,StandardPiecesPerDropSnapshot,StandardCycleTimeSecSnapshot,SourceCode,OperatorNote,EnteredBy,RecordedAt,ProductionAt,ProductionDate,ShiftScheduleVersionID,ShiftID,OperatorConfirmed) OUTPUT INSERTED.id VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1)", (int(payload["lot_id"]), int(payload["actual_drops"]), int(payload["wet_good_pieces"]), payload.get("suggested_actual_drops"), payload.get("suggested_wet_good_pieces"), int(lot_snapshot[0]), int(lot_snapshot[1]), lot_snapshot[2], "AUTOCAL_REVIEWED" if payload.get("suggested_actual_drops") is not None else "MANUAL", payload.get("operator_note") or None, actor, recorded, production_at, production_date, schedule_version_id, shift_id))
            entry_id = int(cursor.fetchone()[0])
            cursor.execute("SELECT id,ProductionLotID,PressDrops,WetGoodPieces,SuggestedPressDrops,SuggestedWetGoodPieces,SourceCode,OperatorNote,EnteredBy,RecordedAt,ProductionAt,ProductionDate,ShiftScheduleVersionID,ShiftID FROM omagmes.ProductionEntry WHERE id=?", (entry_id,))
            row = cursor.fetchone()
            after = self._production_state(row)
            cursor.execute("INSERT INTO omagmes.ProductionEntryChangeHistory (ProductionEntryID,ChangeType,ChangedBy,ChangedAt,ChangeReason,BeforeStateJson,AfterStateJson) VALUES (?,'SAVE',?,?,?,NULL,?)", (entry_id, actor, recorded, reason, json.dumps(after, default=str, sort_keys=True)))
        return {"id": int(row[0]), "lot_id": int(row[1]), "actual_drops": int(row[2]), "wet_good_pieces": int(row[3]), "suggested_actual_drops": row[4], "suggested_wet_good_pieces": row[5], "source": str(row[6]), "operator_note": row[7], "entered_by": str(row[8]), "saved_at": self._text(row[9]), "production_at": self._text(row[10]), "production_date": row[11].isoformat(), "shift_schedule_version_id": int(row[12]), "shift_id": int(row[13]) if row[13] is not None else None, "mode": "SQL PERSISTED"}

    @staticmethod
    def _production_state(row: Any) -> dict[str, Any]:
        if row is None:
            raise SourceUnavailable("Production entry could not be read inside its transaction.")
        names = ("id", "lot_id", "actual_drops", "wet_good_pieces", "suggested_actual_drops", "suggested_wet_good_pieces", "source", "operator_note", "entered_by", "saved_at", "production_at", "production_date", "shift_schedule_version_id", "shift_id")
        state = {name: value for name, value in zip(names, row)}
        state["production_date"] = state["production_date"].isoformat() if hasattr(state["production_date"], "isoformat") else state["production_date"]
        for key in ("saved_at", "production_at"):
            state[key] = SQLServerProductionRepository._text(state[key])
        return state

    def production_entries(self, production_date: str | None = None) -> list[dict[str, Any]]:
        query = ("SELECT TOP (1000) id,ProductionLotID,PressDrops,WetGoodPieces,SuggestedPressDrops,SuggestedWetGoodPieces,"
                 "SourceCode,OperatorNote,EnteredBy,RecordedAt,ProductionAt,ProductionDate,ShiftScheduleVersionID,ShiftID "
                 "FROM omagmes.ProductionEntry WHERE IsDeleted=0")
        params: tuple[Any, ...] = ()
        if production_date:
            parsed = datetime.fromisoformat(production_date).date()
            if parsed.isoformat() != production_date:
                raise ValueError("production_date must use YYYY-MM-DD format.")
            query += " AND ProductionDate=?"
            params = (parsed,)
        query += " ORDER BY ProductionAt DESC,id DESC"
        with self._connection() as (_, cursor):
            cursor.execute(query, params)
            rows = cursor.fetchall()
        return [{**self._production_state(row), "mode": "SQL PERSISTED"} for row in rows]

    def production_entry_history(self, entry_id: int) -> list[dict[str, Any]]:
        with self._connection() as (_, cursor):
            cursor.execute("SELECT id,ChangeType,ChangedBy,ChangedAt,ChangeReason,BeforeStateJson,AfterStateJson FROM omagmes.ProductionEntryChangeHistory WHERE ProductionEntryID=? ORDER BY ChangedAt,id", (entry_id,))
            rows = cursor.fetchall()
        return [{"id": int(row[0]), "action": str(row[1]), "operator_id": str(row[2]), "changed_at": self._text(row[3]), "reason": str(row[4]), "before": json.loads(row[5]) if row[5] else None, "after": json.loads(row[6]) if row[6] else None} for row in rows]

    def production_audit_history(self) -> dict[int, list[dict[str, Any]]]:
        with self._connection() as (_, cursor):
            cursor.execute("SELECT ProductionEntryID,id,ChangeType,ChangedBy,ChangedAt,ChangeReason,BeforeStateJson,AfterStateJson FROM omagmes.ProductionEntryChangeHistory ORDER BY ProductionEntryID,ChangedAt,id")
            rows = cursor.fetchall()
        result: dict[int, list[dict[str, Any]]] = {}
        for row in rows:
            result.setdefault(int(row[0]), []).append({"id": int(row[1]), "action": str(row[2]), "operator_id": str(row[3]), "changed_at": self._text(row[4]), "reason": str(row[5]), "before": json.loads(row[6]) if row[6] else None, "after": json.loads(row[7]) if row[7] else None})
        return result

    def correct_production(self, entry_id: int, *, actual_drops: int, wet_good_pieces: int, reason: str, operator_id: str, operator_confirmed: bool) -> dict[str, Any]:
        if operator_confirmed is not True:
            raise ValueError("Operator confirmation is required before editing Press production quantities.")
        actor = self._require_text(operator_id, "Operator ID", 200)
        why = self._require_text(reason, "Correction reason", 500)
        changed_at = self._now()
        with self._connection(write=True) as (_, cursor):
            self._ensure_schema(cursor)
            cursor.execute("SELECT id,ProductionLotID,PressDrops,WetGoodPieces,SuggestedPressDrops,SuggestedWetGoodPieces,SourceCode,OperatorNote,EnteredBy,RecordedAt,ProductionAt,ProductionDate,ShiftScheduleVersionID,ShiftID FROM omagmes.ProductionEntry WITH (UPDLOCK,HOLDLOCK) WHERE id=? AND IsDeleted=0", (entry_id,))
            old_row = cursor.fetchone()
            if old_row is None:
                raise SourceUnavailable("Production entry ID was not found.")
            before = self._production_state(old_row)
            cursor.execute("UPDATE omagmes.ProductionEntry SET PressDrops=?,WetGoodPieces=?,OperatorConfirmed=1 WHERE id=? AND IsDeleted=0", (actual_drops, wet_good_pieces, entry_id))
            cursor.execute("INSERT INTO omagmes.ProductionEntryCorrection (ProductionEntryID,OldPressDrops,NewPressDrops,OldWetGoodPieces,NewWetGoodPieces,ChangedBy,ChangedAt,ChangeReason) OUTPUT INSERTED.id VALUES (?,?,?,?,?,?,?,?)", (entry_id, int(old_row[2]), actual_drops, int(old_row[3]), wet_good_pieces, actor, changed_at, why))
            correction_id = int(cursor.fetchone()[0])
            cursor.execute("SELECT id,ProductionLotID,PressDrops,WetGoodPieces,SuggestedPressDrops,SuggestedWetGoodPieces,SourceCode,OperatorNote,EnteredBy,RecordedAt,ProductionAt,ProductionDate,ShiftScheduleVersionID,ShiftID FROM omagmes.ProductionEntry WHERE id=?", (entry_id,))
            result = cursor.fetchone()
            after = self._production_state(result)
            cursor.execute("INSERT INTO omagmes.ProductionEntryChangeHistory (ProductionEntryID,ChangeType,ChangedBy,ChangedAt,ChangeReason,BeforeStateJson,AfterStateJson) VALUES (?,'EDIT',?,?,?,?,?)", (entry_id, actor, changed_at, why, json.dumps(before, default=str, sort_keys=True), json.dumps(after, default=str, sort_keys=True)))
            cursor.execute("SELECT id,OldPressDrops,NewPressDrops,OldWetGoodPieces,NewWetGoodPieces,ChangedBy,ChangedAt,ChangeReason FROM omagmes.ProductionEntryCorrection WHERE id=?", (correction_id,))
            correction = cursor.fetchone()
        return {"id": int(result[0]), "lot_id": int(result[1]), "actual_drops": int(result[2]), "wet_good_pieces": int(result[3]),
                "mode": "SQL PERSISTED", "correction": {"id": int(correction[0]), "old_drops": int(correction[1]),
                "new_drops": int(correction[2]), "old_wet_good_pieces": int(correction[3]),
                "new_wet_good_pieces": int(correction[4]), "operator_id": str(correction[5]),
                "changed_at": self._text(correction[6]), "reason": str(correction[7])}}

    def delete_production(self, entry_id: int, *, reason: str, operator_id: str, operator_confirmed: bool) -> dict[str, Any]:
        if operator_confirmed is not True:
            raise ValueError("Operator confirmation is required before deleting a Production Entry.")
        actor = self._require_text(operator_id, "Operator ID", 200)
        why = self._require_text(reason, "Delete reason", 500)
        changed_at = self._now()
        with self._connection(write=True) as (_, cursor):
            self._ensure_schema(cursor)
            cursor.execute("SELECT id,ProductionLotID,PressDrops,WetGoodPieces,SuggestedPressDrops,SuggestedWetGoodPieces,SourceCode,OperatorNote,EnteredBy,RecordedAt,ProductionAt,ProductionDate,ShiftScheduleVersionID,ShiftID FROM omagmes.ProductionEntry WITH (UPDLOCK,HOLDLOCK) WHERE id=? AND IsDeleted=0", (entry_id,))
            row = cursor.fetchone()
            if row is None:
                raise SourceUnavailable("Active production entry ID was not found.")
            before = self._production_state(row)
            cursor.execute("UPDATE omagmes.ProductionEntry SET IsDeleted=1,DeletedAt=?,DeletedBy=?,DeleteReason=? WHERE id=? AND IsDeleted=0", (changed_at, actor, why, entry_id))
            cursor.execute("INSERT INTO omagmes.ProductionEntryChangeHistory (ProductionEntryID,ChangeType,ChangedBy,ChangedAt,ChangeReason,BeforeStateJson,AfterStateJson) VALUES (?,'DELETE',?,?,?,?,NULL)", (entry_id, actor, changed_at, why, json.dumps(before, default=str, sort_keys=True)))
        return {"id": entry_id, "mode": "SQL PERSISTED · SOFT DELETED", "deleted_at": changed_at.isoformat()}

    def save_curing(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._save_lifecycle("CuringInputEntry", "InputQuantity", payload)

    def save_wet_reject(self, payload: dict[str, Any]) -> dict[str, Any]:
        actor = self._require_text(str(payload.get("operator_id", "")), "Operator ID", 200)
        lot_id = int(payload["lot_id"])
        quantities = payload.get("quantities") or {}
        if not isinstance(quantities, dict) or any(int(value) < 0 for value in quantities.values()):
            raise ValueError("Wet Reject quantities must be nonnegative whole numbers.")
        recorded_at = self._now()
        saved: list[dict[str, Any]] = []
        with self._connection(write=True) as (_, cursor):
            self._ensure_schema(cursor)
            cursor.execute("SELECT id FROM omagmes.ProductionLot WITH (UPDLOCK,HOLDLOCK) WHERE id=?", (lot_id,))
            if cursor.fetchone() is None:
                raise SourceUnavailable("Wet Reject entry must reference an official ProductionLot.id.")
            cursor.execute("SELECT id,ReasonCode,ReasonName FROM omagmes.WetRejectReason WITH (UPDLOCK,HOLDLOCK) WHERE IsActive=1")
            active_reasons = {int(row[0]): (str(row[1]), str(row[2])) for row in cursor.fetchall()}
            unknown = sorted(set(int(key) for key in quantities) - set(active_reasons))
            if unknown:
                raise ValueError("One or more RejectReason IDs are inactive or unknown; reload the database master.")
            for reason_id, quantity in quantities.items():
                amount = int(quantity)
                if amount == 0:
                    continue
                cursor.execute("INSERT INTO omagmes.WetRejectEntry (ProductionLotID,RejectReasonID,Quantity,RecordedAt,EnteredBy,OperatorNote) OUTPUT INSERTED.id VALUES (?,?,?,?,?,?)", (lot_id, int(reason_id), amount, recorded_at, actor, payload.get("operator_note") or None))
                entry_id = int(cursor.fetchone()[0])
                code, name = active_reasons[int(reason_id)]
                saved.append({"id": entry_id, "lot_id": lot_id, "reason_id": int(reason_id), "reason_code": code,
                              "reason_name": name, "quantity": amount, "recorded_at": recorded_at.isoformat(),
                              "entered_by": actor})
        return {"entries": saved, "mode": "SQL PERSISTED"}

    def save_depal(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._save_lifecycle("DepalletEvent", "Quantity", payload)

    def _save_lifecycle(self, table: str, quantity_column: str, payload: dict[str, Any]) -> dict[str, Any]:
        if table not in {"CuringInputEntry", "DepalletEvent"}:
            raise ValueError("Unsupported production lifecycle table.")
        actor = self._require_text(str(payload.get("operator_id", "")), "Operator ID", 200)
        if table == "CuringInputEntry" and payload.get("operator_confirmed") is not True:
            raise ValueError("Operator confirmation is required before saving Curing quantities.")
        unit = self._require_text(str(payload.get("unit_code", "")), "Quantity unit", 40)
        recorded = self._now()
        with self._connection(write=True) as (_, cursor):
            self._ensure_schema(cursor)
            cursor.execute("SELECT id FROM omagmes.ProductionLot WHERE id=?", (int(payload["lot_id"]),))
            if cursor.fetchone() is None:
                raise SourceUnavailable("Lifecycle entry must reference an official ProductionLot.id.")
            if table == "CuringInputEntry":
                cursor.execute(f"INSERT INTO omagmes.{table} (ProductionLotID,{quantity_column},QuantityUnitCode,RecordedAt,OperatorNote,EnteredBy,OperatorConfirmed) OUTPUT INSERTED.id VALUES (?,?,?,?,?,?,1)", (int(payload["lot_id"]), int(payload["quantity"]), unit, recorded, payload.get("note") or None, actor))
            else:
                cursor.execute(f"INSERT INTO omagmes.{table} (ProductionLotID,{quantity_column},QuantityUnitCode,RecordedAt,OperatorNote,EnteredBy) OUTPUT INSERTED.id VALUES (?,?,?,?,?,?)", (int(payload["lot_id"]), int(payload["quantity"]), unit, recorded, payload.get("note") or None, actor))
            record_id = int(cursor.fetchone()[0])
            cursor.execute(f"SELECT id,ProductionLotID,{quantity_column},QuantityUnitCode,OperatorNote,EnteredBy,RecordedAt FROM omagmes.{table} WHERE id=?", (record_id,))
            row = cursor.fetchone()
        row = self._readback(f"SELECT id,ProductionLotID,{quantity_column},QuantityUnitCode,OperatorNote,EnteredBy,RecordedAt FROM omagmes.{table} WHERE id=?", (record_id,))
        return {"id": int(row[0]), "lot_id": int(row[1]), "quantity": int(row[2]), "unit_code": str(row[3]),
                "note": row[4] or "", "entered_by": str(row[5]), "saved_at": self._text(row[6]), "mode": "SQL PERSISTED"}

    def save_dispatch(self, payload: dict[str, Any]) -> dict[str, Any]:
        actor = self._require_text(str(payload.get("operator_id", "")), "Operator ID", 200)
        unit = self._require_text(str(payload.get("unit_code", "")), "Quantity unit", 40)
        reference = (payload.get("dispatch_reference") or "").strip() or None
        recorded = self._now()
        with self._connection(write=True) as (_, cursor):
            self._ensure_schema(cursor)
            cursor.execute("SELECT id FROM omagmes.ProductionLot WHERE id=?", (int(payload["lot_id"]),))
            if cursor.fetchone() is None:
                raise SourceUnavailable("Dispatch line must reference an official ProductionLot.id.")
            cursor.execute("INSERT INTO omagmes.Dispatch (DispatchReference,DispatchedAt,EnteredBy,OperatorNote) OUTPUT INSERTED.id VALUES (?,?,?,?)", (reference, recorded, actor, payload.get("note") or None))
            dispatch_id = int(cursor.fetchone()[0])
            cursor.execute("INSERT INTO omagmes.DispatchLine (DispatchID,ProductionLotID,Quantity,QuantityUnitCode) OUTPUT INSERTED.id VALUES (?,?,?,?)", (dispatch_id, int(payload["lot_id"]), int(payload["quantity"]), unit))
            line_id = int(cursor.fetchone()[0])
            cursor.execute("SELECT l.id,l.DispatchID,l.ProductionLotID,l.Quantity,l.QuantityUnitCode,d.DispatchReference,d.DispatchedAt FROM omagmes.DispatchLine l JOIN omagmes.Dispatch d ON d.id=l.DispatchID WHERE l.id=?", (line_id,))
            row = cursor.fetchone()
        row = self._readback("SELECT l.id,l.DispatchID,l.ProductionLotID,l.Quantity,l.QuantityUnitCode,d.DispatchReference,d.DispatchedAt FROM omagmes.DispatchLine l JOIN omagmes.Dispatch d ON d.id=l.DispatchID WHERE l.id=?", (line_id,))
        return {"id": int(row[0]), "dispatch_id": int(row[1]), "lot_id": int(row[2]), "quantity": int(row[3]),
                "unit_code": str(row[4]), "dispatch_reference": row[5], "dispatched_at": self._text(row[6]), "mode": "SQL PERSISTED"}

    @contextmanager
    def _auto_lot_read_connection(self) -> Iterator[tuple[Any, Any]]:
        """Read-only candidate/history access; never depends on the DML opt-in flag."""
        errors = self.settings.live_gate_errors()
        if errors:
            raise SourceUnavailable(" ".join(errors))
        connection: Any | None = None
        try:
            if self._connect_factory is None:
                import pyodbc
                connection = pyodbc.connect(
                    self._connection_string_builder._connection_string(),
                    timeout=self.settings.connect_timeout,
                    autocommit=True,
                )
            else:
                connection = self._connect_factory(
                    self._connection_string_builder._connection_string(),
                    timeout=self.settings.connect_timeout,
                    autocommit=True,
                )
            connection.timeout = self.settings.query_timeout
            cursor = connection.cursor()
            cursor.execute(
                "SELECT ORIGINAL_LOGIN(),SUSER_SNAME(),DB_NAME(),@@SERVERNAME,"
                "CAST(SERVERPROPERTY('InstanceName') AS nvarchar(128)),"
                "HAS_PERMS_BY_NAME('omagmes.AutoLotCandidateWindow','OBJECT','SELECT'),"
                "HAS_PERMS_BY_NAME('omagmes.AutoLotCandidateWindowHistory','OBJECT','SELECT'),"
                "HAS_PERMS_BY_NAME('omagmes.v_PressLotSummary','OBJECT','SELECT')"
            )
            row = cursor.fetchone()
            if row is None:
                raise SourceUnavailable("Auto Lot read target identity could not be verified.")
            if (str(row[0] or "").casefold() != EXPECTED_SQL_LOGIN.casefold()
                    or str(row[1] or "").casefold() != EXPECTED_SQL_LOGIN.casefold()
                    or str(row[2] or "").casefold() != EXPECTED_DATABASE.casefold()
                    or str(row[3] or "").casefold() != EXPECTED_SERVER_NAME.casefold()
                    or str(row[4] or "") != EXPECTED_INSTANCE):
                raise SourceUnavailable("Auto Lot read target is not the verified OMAG_MES instance.")
            if tuple(row[5:8]) != (1, 1, 1):
                raise SourceUnavailable("Candidate, history, or Lot summary SELECT permission is unavailable.")
            cursor.execute(
                "SELECT OBJECT_ID(N'omagmes.AutoLotCandidateWindow',N'U'),"
                "OBJECT_ID(N'omagmes.AutoLotCandidateWindowHistory',N'U'),"
                "OBJECT_ID(N'omagmes.v_PressLotSummary',N'V')"
            )
            objects = cursor.fetchone()
            if objects is None or any(value is None for value in objects):
                raise SourceUnavailable("Installed candidate, history, or Lot summary objects are unavailable.")
            yield connection, cursor
        except SourceUnavailable:
            raise
        except Exception as exc:
            raise SourceUnavailable(f"Auto Lot read query failed ({type(exc).__name__}).") from None
        finally:
            if connection is not None:
                connection.close()

    @contextmanager
    def _auto_lot_connection(self) -> Iterator[tuple[Any, Any]]:
        """Dedicated candidate DML gate; independent of official Lot-number writes."""
        if os.getenv("OMAGMES_AUTOLOT_SYNC_ENABLED", "").strip().lower() not in {"1", "true", "yes", "on"}:
            raise SourceUnavailable("Auto Lot SQL synchronization is disabled by its optional feature flag; no data was written.")
        errors = self.settings.live_gate_errors()
        if errors:
            raise SourceUnavailable(" ".join(errors))
        connection: Any | None = None
        try:
            if self._connect_factory is None:
                import pyodbc
                connection = pyodbc.connect(
                    self._connection_string_builder._connection_string().replace("ApplicationIntent=ReadOnly;", ""),
                    timeout=self.settings.connect_timeout,
                    autocommit=False,
                )
            else:
                connection = self._connect_factory(
                    self._connection_string_builder._connection_string().replace("ApplicationIntent=ReadOnly;", ""),
                    timeout=self.settings.connect_timeout,
                    autocommit=False,
                )
            connection.timeout = self.settings.query_timeout
            cursor = connection.cursor()
            cursor.execute(
                "SELECT ORIGINAL_LOGIN(),SUSER_SNAME(),DB_NAME(),@@SERVERNAME,"
                "CAST(SERVERPROPERTY('InstanceName') AS nvarchar(128)),"
                "HAS_PERMS_BY_NAME('omagmes.AutoLotCandidateWindow','OBJECT','SELECT'),"
                "HAS_PERMS_BY_NAME('omagmes.AutoLotCandidateWindow','OBJECT','INSERT'),"
                "HAS_PERMS_BY_NAME('omagmes.AutoLotCandidateWindow','OBJECT','UPDATE'),"
                "HAS_PERMS_BY_NAME('omagmes.AutoLotCandidateWindowHistory','OBJECT','SELECT'),"
                "HAS_PERMS_BY_NAME('omagmes.AutoLotCandidateWindowHistory','OBJECT','INSERT'),"
                "HAS_PERMS_BY_NAME('omagmes.ProductionLot','OBJECT','SELECT'),"
                "HAS_PERMS_BY_NAME('omagmes.Product','OBJECT','SELECT')"
            )
            row = cursor.fetchone()
            if row is None:
                raise SourceUnavailable("Auto Lot SQL target identity could not be verified.")
            login = str(row[0] or "")
            connected_login = str(row[1] or "")
            if (login.casefold() != EXPECTED_SQL_LOGIN.casefold() or connected_login.casefold() != EXPECTED_SQL_LOGIN.casefold()
                    or str(row[2] or "").casefold() != EXPECTED_DATABASE.casefold()
                    or str(row[3] or "").casefold() != EXPECTED_SERVER_NAME.casefold()
                    or str(row[4] or "") != EXPECTED_INSTANCE):
                raise SourceUnavailable("Auto Lot SQL target identity is not the verified OMAG_MES instance.")
            if tuple(row[5:12]) != (1, 1, 1, 1, 1, 1, 1):
                raise SourceUnavailable("Scoped candidate/history permissions and ProductionLot/Product read access are unavailable.")
            cursor.execute(
                "SELECT OBJECT_ID(N'omagmes.AutoLotCandidateWindow',N'U'),"
                "OBJECT_ID(N'omagmes.AutoLotCandidateWindowHistory',N'U'),"
                "COL_LENGTH(N'omagmes.AutoLotCandidateWindow',N'PlanSourceKey'),"
                "COL_LENGTH(N'omagmes.AutoLotCandidateWindow',N'OperatorBoundaryConfirmed'),"
                "COL_LENGTH(N'omagmes.AutoLotCandidateWindowHistory',N'PreviousStateJson'),"
                "OBJECT_ID(N'omagmes.v_AutoLotDetectedWindow',N'V')"
            )
            tables = cursor.fetchone()
            if tables is None or any(value is None for value in tables):
                raise SourceUnavailable("Auto Lot migration 006 is not installed; no candidate was written.")
            cursor.execute("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE")
            yield connection, cursor
            connection.commit()
        except SourceUnavailable:
            if connection is not None:
                connection.rollback()
            raise
        except ValueError:
            if connection is not None:
                connection.rollback()
            raise
        except Exception as exc:
            if connection is not None:
                connection.rollback()
            raise SourceUnavailable(f"Auto Lot SQL transaction failed ({type(exc).__name__}); transaction rolled back.") from None
        finally:
            if connection is not None:
                connection.close()

    @staticmethod
    def _candidate_state(cursor: Any, window_id: int, *, lock: bool = True) -> dict[str, Any] | None:
        hint = " WITH (UPDLOCK,HOLDLOCK)" if lock else ""
        cursor.execute(
            "SELECT id,CandidateKey,CandidateKind,SourceTag,FirstSourceID,ResetSourceID,ResetPreviousSourceID,"
            "ResetObservedAt,ResetPreviousAt,ResetValue,ResetPreviousValue,InitialProposedStartTime,InitialProposedEndTime,"
            "CurrentProposedStartTime,CurrentProposedEndTime,EffectiveStartTime,EffectiveEndTime,OperatorTimeOverride,"
            "CandidateStatus,ProductionDate,CutoffVersionID,ShiftScheduleVersionID,ShiftID,ProductID,ColorCode,"
            "OfficialProductionLotID,CreatedBy,LastDetectedAt,LastOperatorID,LastOperatorReason,PlanSourceKey,"
            "PlanSnapshotJson,PlanMaterialCode,PlanMatchStatus,PlanSelectedAt,PlanSelectedBy,OperatorBoundaryConfirmed "
            f"FROM omagmes.AutoLotCandidateWindow{hint} WHERE id=?",
            (window_id,),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        return {column[0]: value for column, value in zip(cursor.description, row)}

    @staticmethod
    def _write_candidate_history(
        cursor: Any,
        *,
        window_id: int,
        action: str,
        actor: str,
        reason: str,
        before: dict[str, Any] | None,
        after: dict[str, Any] | None,
        change_source: str = "OPERATOR",
        related_id: int | None = None,
    ) -> None:
        cursor.execute(
            "INSERT omagmes.AutoLotCandidateWindowHistory "
            "(CandidateWindowID,ActionCode,PreviousStartTime,PreviousEndTime,NewStartTime,NewEndTime,"
            "PreviousStatus,NewStatus,RelatedCandidateWindowID,ChangedBy,ChangeReason,ChangedAt,ChangeSource,"
            "PreviousStateJson,NewStateJson) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,SYSUTCDATETIME(),?,?,?)",
            (
                window_id, action,
                before.get("EffectiveStartTime") if before else None,
                before.get("EffectiveEndTime") if before else None,
                after.get("EffectiveStartTime") if after else None,
                after.get("EffectiveEndTime") if after else None,
                before.get("CandidateStatus") if before else None,
                after.get("CandidateStatus") if after else None,
                related_id, actor, reason, change_source,
                json.dumps(before, ensure_ascii=False, sort_keys=True, default=lambda value: value.isoformat() if hasattr(value, "isoformat") else str(value)) if before else None,
                json.dumps(after, ensure_ascii=False, sort_keys=True, default=lambda value: value.isoformat() if hasattr(value, "isoformat") else str(value)) if after else None,
            ),
        )

    @staticmethod
    def _validate_candidate_window_overlap(
        cursor: Any,
        start_at: datetime,
        end_at: datetime | None,
        *,
        exclude_ids: tuple[int, ...] = (),
    ) -> None:
        if end_at is not None and end_at <= start_at:
            raise ValueError("End time must be after start time.")
        exclusions = "" if not exclude_ids else " AND id NOT IN (" + ",".join("?" for _ in exclude_ids) + ")"
        params: tuple[Any, ...] = (end_at, end_at, start_at, *exclude_ids)
        cursor.execute(
            "SELECT TOP (1) id FROM omagmes.AutoLotCandidateWindow WITH (UPDLOCK,HOLDLOCK) "
            "WHERE OfficialProductionLotID IS NULL AND CandidateStatus IN ('OPEN','CLOSED','REVIEWED') "
            "AND (? IS NULL OR EffectiveStartTime < ?) "
            "AND (EffectiveEndTime IS NULL OR EffectiveEndTime > ?)" + exclusions,
            params,
        )
        candidate = cursor.fetchone()
        if candidate is not None:
            raise ValueError(f"This half-open window overlaps active candidate #{int(candidate[0])}; adjust the boundaries to avoid ambiguous allocation.")
        cursor.execute(
            "SELECT TOP (1) id FROM omagmes.ProductionLot WITH (UPDLOCK,HOLDLOCK) "
            "WHERE (? IS NULL OR LotStartedAt < ?) "
            "AND (LotEndedAt IS NULL OR LotEndedAt > ?)",
            (end_at, end_at, start_at),
        )
        official = cursor.fetchone()
        if official is not None:
            raise ValueError(f"This half-open window overlaps official ProductionLot #{int(official[0])}; no candidate change was saved.")

    def list_auto_lot_windows(self, *, include_deleted: bool = False) -> list[dict[str, Any]]:
        with self._auto_lot_read_connection() as (_, cursor):
            cursor.execute(
                "SELECT c.id,c.CandidateKey,c.CandidateKind,c.CandidateStatus,c.SourceTag,c.FirstSourceID,"
                "c.ResetSourceID,c.ResetPreviousSourceID,c.ResetObservedAt,c.ResetPreviousAt,c.ResetValue,c.ResetPreviousValue,"
                "c.EffectiveStartTime,c.EffectiveEndTime,c.OperatorTimeOverride,c.OperatorBoundaryConfirmed,c.ProductionDate,c.ProductID,c.ColorCode,"
                "c.PlanSourceKey,c.PlanSnapshotJson,c.PlanMaterialCode,c.PlanMatchStatus,c.PlanSelectedAt,c.PlanSelectedBy,"
                "s.CalculatedPressQty,s.LatestLotACC,s.LatestDiffAt,s.AmbiguousEventCount,s.ResetEventCount,s.HasDataWarnings "
                "FROM omagmes.AutoLotCandidateWindow AS c "
                "LEFT JOIN omagmes.v_PressLotSummary AS s ON s.LotIdentityType='CANDIDATE' AND s.LotIdentityID=c.id "
                "WHERE (?=1 OR c.CandidateStatus<>'DISMISSED') ORDER BY c.EffectiveStartTime DESC,c.id DESC",
                (1 if include_deleted else 0,),
            )
            names = [column[0] for column in cursor.description]
            result = []
            for row in cursor.fetchall():
                item = {name: (value.isoformat() if hasattr(value, "isoformat") else value) for name, value in zip(names, row)}
                item["is_deleted"] = item["CandidateStatus"] == "DISMISSED"
                item["CalculatedPressQty"] = item.get("CalculatedPressQty") or 0
                item["LatestLotACC"] = item.get("LatestLotACC") or 0
                result.append(item)
        return result

    def auto_lot_window_history(self, window_id: int) -> list[dict[str, Any]]:
        with self._auto_lot_read_connection() as (_, cursor):
            cursor.execute(
                "SELECT id,CandidateWindowID,ActionCode,PreviousStatus,NewStatus,PreviousStartTime,PreviousEndTime,"
                "NewStartTime,NewEndTime,RelatedCandidateWindowID,ChangedBy,ChangedAt,ChangeSource,ChangeReason,"
                "PreviousStateJson,NewStateJson FROM omagmes.AutoLotCandidateWindowHistory "
                "WHERE CandidateWindowID=? ORDER BY ChangedAt,id",
                (window_id,),
            )
            names = [column[0] for column in cursor.description]
            return [
                {name: (value.isoformat() if hasattr(value, "isoformat") else value) for name, value in zip(names, row)}
                for row in cursor.fetchall()
            ]

    def sync_auto_lot_detected_windows(self, detected: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Idempotently reconcile SQL-derived counter epochs into the one candidate master."""
        if not detected:
            return []
        results: list[dict[str, Any]] = []
        with self._auto_lot_connection() as (_, cursor):
            for proposal in sorted(detected, key=lambda item: (item["ProposedStartTime"], int(item["FirstSourceID"]))):
                candidate_key = str(proposal["CandidateKey"])
                start = datetime.fromisoformat(str(proposal["ProposedStartTime"]))
                end = datetime.fromisoformat(str(proposal["ProposedEndTime"])) if proposal.get("ProposedEndTime") else None
                if end is not None and end <= start:
                    raise SourceUnavailable("SQL detector returned a non-positive proposed interval; synchronization was rolled back.")
                cursor.execute(
                    "SELECT id FROM omagmes.AutoLotCandidateWindow WITH (UPDLOCK,HOLDLOCK) WHERE CandidateKey=?",
                    (candidate_key,),
                )
                existing_row = cursor.fetchone()
                if existing_row is not None:
                    candidate_id = int(existing_row[0])
                    before = self._candidate_state(cursor, candidate_id)
                    if before is None:
                        raise SourceUnavailable("Existing Auto Lot candidate disappeared inside the synchronization transaction.")
                    # Tombstones/manual records and any operator edit are durable
                    # decisions; PLC re-detection must not restore or overwrite them.
                    if (before["CandidateKind"] != "AUTO" or before["CandidateStatus"] in ("DISMISSED", "MERGED")
                            or before["OperatorTimeOverride"] or before["OfficialProductionLotID"] is not None):
                        results.append({"id": candidate_id, "candidate_key": candidate_key, "created": False, "preserved": True})
                        continue
                    old_start = before["EffectiveStartTime"]
                    old_end = before["EffectiveEndTime"]
                    changed_start = old_start != start
                    changed_end = old_end != end
                    if changed_start or changed_end:
                        self._validate_candidate_window_overlap(cursor, start, end, exclude_ids=(candidate_id,))
                        cursor.execute(
                            "UPDATE omagmes.AutoLotCandidateWindow SET CurrentProposedStartTime=?,CurrentProposedEndTime=?,"
                            "EffectiveStartTime=?,EffectiveEndTime=?,CandidateStatus=CASE WHEN CandidateStatus='REVIEWED' THEN CandidateStatus "
                            "WHEN ? IS NULL THEN 'OPEN' ELSE 'CLOSED' END,LastDetectedAt=SYSUTCDATETIME() WHERE id=?",
                            (start, end, start, end, end, candidate_id),
                        )
                        after = self._candidate_state(cursor, candidate_id)
                        action = "MOVE" if changed_start and changed_end else ("UPDATE_START" if changed_start else "UPDATE_STOP")
                        self._write_candidate_history(
                            cursor, window_id=candidate_id, action=action, actor="AUTO DETECTOR",
                            reason="SQL DropCnt counter-epoch proposal changed; no operator override was present.",
                            before=before, after=after, change_source="AUTO_DETECTOR",
                        )
                    results.append({"id": candidate_id, "candidate_key": candidate_key, "created": False, "preserved": False})
                    continue

                # The view exposes only evidence; these candidate fields do not
                # claim actual Lot boundaries or Product/Color identity.
                self._validate_candidate_window_overlap(cursor, start, end)
                reset_id = proposal.get("ResetSourceID")
                previous_reset_id = proposal.get("ResetPreviousSourceID")
                reset_at = start if reset_id is not None else None
                previous_at = datetime.fromisoformat(str(proposal["BoundaryEarliestEvidenceAt"])) if proposal.get("BoundaryEarliestEvidenceAt") else None
                reset_value = int(proposal["ResetValue"]) if proposal.get("ResetValue") is not None else None
                previous_value = int(proposal["ResetPreviousValue"]) if proposal.get("ResetPreviousValue") is not None else None
                status = "OPEN" if end is None else "CLOSED"
                cursor.execute(
                    "INSERT omagmes.AutoLotCandidateWindow "
                    "(CandidateKey,CandidateKind,SourceTag,FirstSourceID,ResetSourceID,ResetPreviousSourceID,ResetObservedAt,ResetPreviousAt,ResetValue,ResetPreviousValue,"
                    "InitialProposedStartTime,InitialProposedEndTime,CurrentProposedStartTime,CurrentProposedEndTime,EffectiveStartTime,EffectiveEndTime,"
                    "ProductionDate,CutoffVersionID,ShiftScheduleVersionID,ShiftID,CandidateStatus,LastDetectedAt) "
                    "OUTPUT INSERTED.id VALUES (?,'AUTO',?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,SYSUTCDATETIME())",
                    (candidate_key, "OMAG.PRESS.OEE.DropCnt", int(proposal["FirstSourceID"]), reset_id,
                     previous_reset_id, reset_at, previous_at, reset_value, previous_value,
                     start, end, start, end, start, end, proposal.get("ProductionDate"),
                     proposal.get("CutoffVersionID"), proposal.get("ShiftScheduleVersionID"), None, status),
                )
                inserted = cursor.fetchone()
                if inserted is None:
                    raise SourceUnavailable("Auto Lot insert returned no identity; the transaction was rolled back.")
                candidate_id = int(inserted[0])
                after = self._candidate_state(cursor, candidate_id)
                self._write_candidate_history(
                    cursor, window_id=candidate_id, action="CREATE_AUTO", actor="AUTO DETECTOR",
                    reason="Created from SQL v_AutoLotDetectedWindow; Product/Color boundary requires operator confirmation.",
                    before=None, after=after, change_source="AUTO_DETECTOR",
                )
                results.append({"id": candidate_id, "candidate_key": candidate_key, "created": True, "preserved": False})
        return results

    def edit_auto_lot_candidate_window(self, window_id: int, start_at: datetime, end_at: datetime | None, actor: str, reason: str) -> dict[str, Any]:
        actor = self._require_text(actor, "Operator ID", 200)
        reason = self._require_text(reason, "Change reason", 500)
        with self._auto_lot_connection() as (_, cursor):
            before = self._candidate_state(cursor, window_id)
            if before is None:
                raise SourceUnavailable("Auto Lot candidate window was not found.")
            if before["OfficialProductionLotID"] is not None or before["CandidateStatus"] in ("DISMISSED", "MERGED"):
                raise SourceUnavailable("Officially linked, dismissed, or merged candidate windows cannot be edited.")
            effective_start = start_at if start_at == before["EffectiveStartTime"] else start_at.replace(second=0, microsecond=0)
            effective_end = end_at if end_at == before["EffectiveEndTime"] else (end_at.replace(second=0, microsecond=0) if end_at else None)
            if effective_end is not None and effective_end <= effective_start:
                raise ValueError("End time must be after start time at minute precision.")
            self._validate_candidate_window_overlap(cursor, effective_start, effective_end, exclude_ids=(window_id,))
            cursor.execute(
                "UPDATE omagmes.AutoLotCandidateWindow SET CurrentProposedStartTime=?,CurrentProposedEndTime=?,"
                "EffectiveStartTime=?,EffectiveEndTime=?,OperatorTimeOverride=1,OperatorBoundaryConfirmed=1,"
                "LastOperatorID=?,LastOperatorReason=? WHERE id=?",
                (effective_start, effective_end, effective_start, effective_end, actor, reason, window_id),
            )
            after = self._candidate_state(cursor, window_id)
            changed_start = effective_start != before["EffectiveStartTime"]
            changed_end = effective_end != before["EffectiveEndTime"]
            action = "MOVE" if changed_start and changed_end else ("UPDATE_START" if changed_start else "UPDATE_STOP")
            self._write_candidate_history(
                cursor, window_id=window_id, action=action, actor=actor, reason=reason,
                before=before, after=after,
            )
        return {"id": window_id, "start_at": effective_start.isoformat(), "end_at": effective_end.isoformat() if effective_end else None, "operator_time_override": True, "status": before["CandidateStatus"]}

    def create_auto_lot_window(self, candidate_key: str, start_at: datetime, end_at: datetime | None, actor: str, reason: str, production_date: str, cutoff_version_id: int) -> dict[str, Any]:
        candidate_key = self._require_text(candidate_key, "Candidate key", 200)
        actor = self._require_text(actor, "Operator ID", 200)
        reason = self._require_text(reason, "Change reason", 500)
        start_at = start_at.replace(second=0, microsecond=0)
        end_at = end_at.replace(second=0, microsecond=0) if end_at else None
        if end_at is not None and end_at <= start_at:
            raise ValueError("End time must be after start time at minute precision.")
        with self._auto_lot_connection() as (_, cursor):
            self._validate_candidate_window_overlap(cursor, start_at, end_at)
            cursor.execute(
                "INSERT omagmes.AutoLotCandidateWindow (CandidateKey,CandidateKind,SourceTag,InitialProposedStartTime,InitialProposedEndTime,CurrentProposedStartTime,CurrentProposedEndTime,EffectiveStartTime,EffectiveEndTime,ProductionDate,CutoffVersionID,OperatorTimeOverride,OperatorBoundaryConfirmed,CandidateStatus,LastDetectedAt,CreatedBy,LastOperatorID,LastOperatorReason) "
                "OUTPUT inserted.id VALUES (?,'MANUAL',N'OPERATOR WINDOW',?,?,?,?,?,?,?,?,1,1,'OPEN',SYSUTCDATETIME(),?,?,?)",
                (candidate_key, start_at, end_at, start_at, end_at, start_at, end_at, production_date, cutoff_version_id, actor, actor, reason),
            )
            row = cursor.fetchone()
            if row is None:
                raise SourceUnavailable("Manual Lot window insert returned no identity; transaction rolled back.")
            window_id = int(row[0])
            after = self._candidate_state(cursor, window_id)
            self._write_candidate_history(
                cursor, window_id=window_id, action="CREATE_MANUAL", actor=actor,
                reason=reason, before=None, after=after,
            )
        return {"id": window_id, "candidate_key": candidate_key, "start_at": start_at.isoformat(), "end_at": end_at.isoformat() if end_at else None, "status": "OPEN"}

    def split_auto_lot_window(self, window_id: int, split_at: datetime, new_candidate_key: str, actor: str, reason: str) -> dict[str, Any]:
        new_candidate_key = self._require_text(new_candidate_key, "Candidate key", 200)
        actor = self._require_text(actor, "Operator ID", 200)
        reason = self._require_text(reason, "Change reason", 500)
        split_at = split_at.replace(second=0, microsecond=0)
        with self._auto_lot_connection() as (_, cursor):
            before = self._candidate_state(cursor, window_id)
            if before is None or before["OfficialProductionLotID"] is not None or before["CandidateStatus"] not in ("OPEN", "CLOSED", "REVIEWED"):
                raise SourceUnavailable("Only an unlinked active candidate window can be split.")
            if split_at <= before["EffectiveStartTime"] or (before["EffectiveEndTime"] is not None and split_at >= before["EffectiveEndTime"]):
                raise SourceUnavailable("Split time must be strictly inside the effective Lot window.")
            self._validate_candidate_window_overlap(cursor, split_at, before["EffectiveEndTime"], exclude_ids=(window_id,))
            cursor.execute("UPDATE omagmes.AutoLotCandidateWindow SET CurrentProposedEndTime=?,EffectiveEndTime=?,OperatorTimeOverride=1,OperatorBoundaryConfirmed=1,LastOperatorID=?,LastOperatorReason=? WHERE id=?", (split_at, split_at, actor, reason, window_id))
            after_parent = self._candidate_state(cursor, window_id)
            cursor.execute("INSERT omagmes.AutoLotCandidateWindow (CandidateKey,CandidateKind,SourceTag,InitialProposedStartTime,InitialProposedEndTime,CurrentProposedStartTime,CurrentProposedEndTime,EffectiveStartTime,EffectiveEndTime,ProductionDate,CutoffVersionID,ShiftScheduleVersionID,ShiftID,ProductID,ColorCode,OperatorTimeOverride,OperatorBoundaryConfirmed,CandidateStatus,LastDetectedAt,CreatedBy,LastOperatorID,LastOperatorReason) OUTPUT inserted.id VALUES (?,'SPLIT',N'OPERATOR SPLIT',?,?,?,?,?,?,?,?,?,?,?,?,1,1,'OPEN',SYSUTCDATETIME(),?,?,?)", (new_candidate_key, split_at, before["EffectiveEndTime"], split_at, before["EffectiveEndTime"], split_at, before["EffectiveEndTime"], before["ProductionDate"], before["CutoffVersionID"], before["ShiftScheduleVersionID"], before["ShiftID"], before["ProductID"], before["ColorCode"], actor, actor, reason))
            row = cursor.fetchone()
            if row is None:
                raise SourceUnavailable("Split window insert returned no identity; transaction rolled back.")
            new_id = int(row[0])
            after_child = self._candidate_state(cursor, new_id)
            self._write_candidate_history(cursor, window_id=window_id, action="SPLIT", actor=actor, reason=reason, before=before, after=after_parent, related_id=new_id)
            self._write_candidate_history(cursor, window_id=new_id, action="SPLIT", actor=actor, reason=reason, before=None, after=after_child, related_id=window_id)
        return {"original_id": window_id, "new_id": new_id, "split_at": split_at.isoformat()}

    def merge_auto_lot_windows(self, target_id: int, source_id: int, actor: str, reason: str) -> dict[str, Any]:
        actor = self._require_text(actor, "Operator ID", 200)
        reason = self._require_text(reason, "Change reason", 500)
        if target_id == source_id:
            raise SourceUnavailable("A candidate window cannot be merged with itself.")
        with self._auto_lot_connection() as (_, cursor):
            target_before = self._candidate_state(cursor, target_id)
            source_before = self._candidate_state(cursor, source_id)
            if target_before is None or source_before is None:
                raise SourceUnavailable("Both candidate windows must exist to merge.")
            if any(row["OfficialProductionLotID"] is not None or row["CandidateStatus"] in ("DISMISSED", "MERGED") for row in (target_before, source_before)):
                raise SourceUnavailable("Officially linked, dismissed, or merged windows cannot be merged.")
            start_at = min(target_before["EffectiveStartTime"], source_before["EffectiveStartTime"])
            end_at = None if target_before["EffectiveEndTime"] is None or source_before["EffectiveEndTime"] is None else max(target_before["EffectiveEndTime"], source_before["EffectiveEndTime"])
            self._validate_candidate_window_overlap(cursor, start_at, end_at, exclude_ids=(target_id, source_id))
            cursor.execute("UPDATE omagmes.AutoLotCandidateWindow SET CurrentProposedStartTime=?,CurrentProposedEndTime=?,EffectiveStartTime=?,EffectiveEndTime=?,OperatorTimeOverride=1,OperatorBoundaryConfirmed=1,LastOperatorID=?,LastOperatorReason=? WHERE id=?", (start_at, end_at, start_at, end_at, actor, reason, target_id))
            cursor.execute("UPDATE omagmes.AutoLotCandidateWindow SET CandidateStatus='MERGED',LastOperatorID=?,LastOperatorReason=? WHERE id=?", (actor, reason, source_id))
            target_after = self._candidate_state(cursor, target_id)
            source_after = self._candidate_state(cursor, source_id)
            self._write_candidate_history(cursor, window_id=target_id, action="MERGED", actor=actor, reason=reason, before=target_before, after=target_after, related_id=source_id)
            self._write_candidate_history(cursor, window_id=source_id, action="MERGED", actor=actor, reason=reason, before=source_before, after=source_after, related_id=target_id)
        return {"target_id": target_id, "merged_source_id": source_id, "start_at": start_at.isoformat(), "end_at": end_at.isoformat() if end_at else None}

    def dismiss_auto_lot_window(self, window_id: int, actor: str, reason: str) -> dict[str, Any]:
        actor = self._require_text(actor, "Operator ID", 200)
        reason = self._require_text(reason, "Change reason", 500)
        with self._auto_lot_connection() as (_, cursor):
            before = self._candidate_state(cursor, window_id)
            if before is None:
                raise SourceUnavailable("Auto Lot candidate window was not found.")
            if before["OfficialProductionLotID"] is not None:
                raise SourceUnavailable("An officially linked candidate cannot be dismissed.")
            if before["CandidateStatus"] in ("DISMISSED", "MERGED"):
                raise SourceUnavailable("Candidate window is already dismissed or merged.")
            cursor.execute("UPDATE omagmes.AutoLotCandidateWindow SET CandidateStatus='DISMISSED',LastOperatorID=?,LastOperatorReason=? WHERE id=?", (actor, reason, window_id))
            after = self._candidate_state(cursor, window_id)
            self._write_candidate_history(cursor, window_id=window_id, action="SOFT_DELETE", actor=actor,
                                          reason=reason, before=before, after=after)
        return {"id": window_id, "status": "DISMISSED"}

    def restore_auto_lot_window(self, window_id: int, actor: str, reason: str) -> dict[str, Any]:
        actor = self._require_text(actor, "Operator ID", 200)
        reason = self._require_text(reason, "Change reason", 500)
        with self._auto_lot_connection() as (_, cursor):
            before = self._candidate_state(cursor, window_id)
            if before is None or before["CandidateStatus"] != "DISMISSED":
                raise SourceUnavailable("Only a soft-deleted candidate window can be restored.")
            if before["OfficialProductionLotID"] is not None:
                raise SourceUnavailable("An officially linked candidate cannot be restored as a working candidate.")
            cursor.execute(
                "SELECT TOP (1) PreviousStateJson FROM omagmes.AutoLotCandidateWindowHistory WITH (UPDLOCK,HOLDLOCK) "
                "WHERE CandidateWindowID=? AND ActionCode='SOFT_DELETE' ORDER BY ChangedAt DESC,id DESC",
                (window_id,),
            )
            history = cursor.fetchone()
            if history is None or not history[0]:
                raise SourceUnavailable("No complete soft-delete snapshot exists; this legacy row cannot be safely restored.")
            try:
                saved = json.loads(history[0])
                previous_status = saved["CandidateStatus"]
            except (TypeError, ValueError, KeyError):
                raise SourceUnavailable("The soft-delete audit snapshot is invalid; restore was refused.") from None
            if previous_status not in ("OPEN", "CLOSED", "REVIEWED"):
                raise SourceUnavailable("The saved candidate status is not restorable.")
            self._validate_candidate_window_overlap(cursor, before["EffectiveStartTime"], before["EffectiveEndTime"], exclude_ids=(window_id,))
            cursor.execute(
                "UPDATE omagmes.AutoLotCandidateWindow SET CandidateStatus=?,LastOperatorID=?,LastOperatorReason=? WHERE id=?",
                (previous_status, actor, reason, window_id),
            )
            after = self._candidate_state(cursor, window_id)
            self._write_candidate_history(cursor, window_id=window_id, action="RESTORE", actor=actor,
                                          reason=reason, before=before, after=after)
        return {"id": window_id, "status": previous_status}

    def assign_auto_lot_plan(
        self, window_id: int, plan: dict[str, Any], actor: str, reason: str,
    ) -> dict[str, Any]:
        actor = self._require_text(actor, "Operator ID", 200)
        reason = self._require_text(reason, "Change reason", 500)
        plan_key = self._require_text(str(plan.get("plan_key", "")), "Plan snapshot key", 64)
        if len(plan_key) != 64 or plan.get("identity_kind") != "CONTENT_FINGERPRINT_NOT_SOURCE_ID":
            raise ValueError("Plan identity must be the reviewed content fingerprint, not a fabricated source row ID.")
        if int(plan.get("duplicate_count", 0)) != 1:
            raise ValueError("This plan snapshot is duplicated in the source view and cannot be uniquely assigned.")
        snapshot = plan.get("snapshot")
        if not isinstance(snapshot, dict):
            raise ValueError("A complete source plan snapshot is required.")
        if plan_snapshot(snapshot)["plan_key"] != plan_key:
            raise ValueError("Plan fingerprint does not match the captured source snapshot.")
        raw_material_code = snapshot.get("MaterialCode")
        if not isinstance(raw_material_code, str) or not raw_material_code.strip():
            raise ValueError("Plan MaterialCode is required for exact ProductCode mapping.")
        if len(raw_material_code) > 100:
            raise ValueError("Plan MaterialCode exceeds the candidate snapshot column length.")
        material_code = raw_material_code
        snapshot_json = json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
        with self._auto_lot_connection() as (_, cursor):
            before = self._candidate_state(cursor, window_id)
            if before is None or before["CandidateStatus"] in ("DISMISSED", "MERGED"):
                raise SourceUnavailable("Only an active candidate window can be assigned a Production Plan.")
            if before["OfficialProductionLotID"] is not None:
                raise SourceUnavailable("An officially linked candidate cannot be assigned a working plan snapshot.")
            cursor.execute(
                "SELECT id FROM omagmes.Product WITH (UPDLOCK,HOLDLOCK) "
                "WHERE DATALENGTH(ProductCode)=DATALENGTH(?) "
                "AND ProductCode COLLATE Latin1_General_100_BIN2=? COLLATE Latin1_General_100_BIN2 AND IsActive=1",
                (material_code, material_code),
            )
            products = cursor.fetchall()
            if len(products) != 1:
                raise ValueError("Plan MaterialCode must exactly match one active authoritative ProductCode; no fuzzy mapping is allowed.")
            product_id = int(products[0][0])
            action = "PLAN_CHANGE" if before["PlanSourceKey"] is not None else "PLAN_ASSIGN"
            cursor.execute(
                "UPDATE omagmes.AutoLotCandidateWindow SET PlanSourceKey=?,PlanSnapshotJson=?,PlanMaterialCode=?,"
                "PlanMatchStatus='MATCHED',PlanSelectedAt=SYSUTCDATETIME(),PlanSelectedBy=?,"
                "ColorCode=CASE WHEN ProductID<>? THEN NULL ELSE ColorCode END,ProductID=?,"
                "LastOperatorID=?,LastOperatorReason=? WHERE id=?",
                (plan_key, snapshot_json, material_code, actor, product_id, product_id, actor, reason, window_id),
            )
            after = self._candidate_state(cursor, window_id)
            self._write_candidate_history(cursor, window_id=window_id, action=action, actor=actor,
                                          reason=reason, before=before, after=after)
        return {"id": window_id, "plan_key": plan_key, "product_id": product_id,
                "material_code": material_code, "color_code": before["ColorCode"],
                "planned_start_is_actual_start": False}

    def classify_auto_lot_candidate(
        self, window_id: int, product_id: int, color_code: str, actor: str, reason: str,
    ) -> dict[str, Any]:
        actor = self._require_text(actor, "Operator ID", 200)
        reason = self._require_text(reason, "Change reason", 500)
        color = self._require_text(color_code, "Color", 60)
        with self._auto_lot_connection() as (_, cursor):
            before = self._candidate_state(cursor, window_id)
            if before is None or before["CandidateStatus"] in ("DISMISSED", "MERGED"):
                raise SourceUnavailable("Only an active candidate window can be classified.")
            if before["OfficialProductionLotID"] is not None:
                raise SourceUnavailable("An officially linked candidate cannot be reclassified as a working candidate.")
            cursor.execute(
                "SELECT id FROM omagmes.Product WITH (UPDLOCK,HOLDLOCK) WHERE id=? AND IsActive=1",
                (product_id,),
            )
            product = cursor.fetchone()
            if product is None:
                raise ValueError("Product ID must reference one active authoritative OmagMES Product.")
            cursor.execute(
                "UPDATE omagmes.AutoLotCandidateWindow SET ProductID=?,ColorCode=?,"
                "CandidateStatus='REVIEWED',LastOperatorID=?,LastOperatorReason=? WHERE id=?",
                (product_id, color, actor, reason, window_id),
            )
            after = self._candidate_state(cursor, window_id)
            self._write_candidate_history(cursor, window_id=window_id, action="CLASSIFY", actor=actor,
                                          reason=reason, before=before, after=after)
        return {"id": window_id, "product_id": product_id, "color_code": color,
                "status": "REVIEWED", "official_lot_created": False}
