from __future__ import annotations

import os
import re
import getpass
import json
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Iterator
from uuid import UUID

from dotenv import load_dotenv
from .production_day import ProductionDayConfigurationError, minimum_safe_cutoff_effective_date, parse_production_date
from .daily_shift_configuration import (
    DailyShiftConfigurationError,
    initial_shift_periods,
    normalize_shift_configuration,
    template_periods,
)
from .shift_schedule import resolve_schedule_context, validate_shift_definitions, validate_shift_period_definitions
from .shift_type_schedule import ShiftTypeValidationError, validate_shift_type_periods

SYSTEM_CONFIGURATION_CHANGE_REASON = "SYSTEM CONFIGURATION SAVE"

APPROVED_SQL_SERVER = re.compile(r"^10\.28\.255\.98(?:\\SQLEXPRESS)?(?:,\d{1,5})?$", re.IGNORECASE)
PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_ENV_FILE = PROJECT_ROOT / "config" / ".env.omagmes"
SUPPORTED_TIME_ZONE = "Asia/Bangkok"


class ConfigurationUnavailable(RuntimeError):
    """SQL-backed operational configuration cannot be safely read or changed."""


class ConfigurationConflict(RuntimeError):
    """A concurrent or conflicting immutable configuration version exists."""


@dataclass(frozen=True)
class ConfigurationSQLSettings:
    server: str
    database: str
    driver: str
    username: str
    password: str
    trusted_connection: bool
    target_confirmed: bool
    writes_confirmed: bool
    encrypt: bool
    trust_server_certificate: bool

    @classmethod
    def from_environment(cls) -> "ConfigurationSQLSettings":
        load_dotenv(CONFIG_ENV_FILE, override=False)

        def flag(name: str) -> bool:
            return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}

        return cls(
            server=os.getenv("OMAGMES_CONFIG_SQL_SERVER", "").strip(),
            database=os.getenv("OMAGMES_CONFIG_SQL_DATABASE", "").strip(),
            driver=os.getenv("OMAGMES_CONFIG_SQL_DRIVER", "").strip(),
            username=os.getenv("OMAGMES_CONFIG_SQL_USER", "").strip(),
            password=os.getenv("OMAGMES_CONFIG_SQL_PASS", ""),
            trusted_connection=flag("OMAGMES_CONFIG_SQL_TRUSTED_CONNECTION"),
            target_confirmed=flag("OMAGMES_CONFIG_TARGET_CONFIRMED"),
            writes_confirmed=flag("OMAGMES_CONFIG_WRITE_CONFIRMED"),
            encrypt=flag("OMAGMES_CONFIG_SQL_ENCRYPT"),
            trust_server_certificate=flag("OMAGMES_CONFIG_SQL_TRUST_SERVER_CERTIFICATE"),
        )

    def validate(self, *, write: bool) -> None:
        if not self.target_confirmed:
            raise ConfigurationUnavailable("SQL configuration storage is disabled until the OMAG target is explicitly verified.")
        if not APPROVED_SQL_SERVER.fullmatch(self.server) or self.database.casefold() != "omag":
            raise ConfigurationUnavailable("SQL configuration storage must target the approved OMAG SQL Server and database.")
        if not self.driver or (not self.trusted_connection and (not self.username or not self.password)):
            raise ConfigurationUnavailable("A SQL configuration identity is not configured.")
        if not self.encrypt:
            raise ConfigurationUnavailable("SQL configuration storage requires encrypted transport.")
        if write and not self.writes_confirmed:
            raise ConfigurationUnavailable("SQL configuration writes are disabled until the DBA confirms schema-scoped permissions.")

    def connection_string(self) -> str:
        def brace(value: str) -> str:
            return "{" + value.replace("}", "}}") + "}"

        auth = "Trusted_Connection=yes;" if self.trusted_connection else f"UID={brace(self.username)};PWD={brace(self.password)};"
        return (f"DRIVER={brace(self.driver)};SERVER={self.server};DATABASE={self.database};{auth}"
            f"Encrypt={'yes' if self.encrypt else 'no'};"
            f"TrustServerCertificate={'yes' if self.trust_server_certificate else 'no'};")


class SQLServerConfigurationRepository:
    """SQL Server persistence for append-only Production Day and Shift settings.

    This repository intentionally uses dedicated OMAGMES_CONFIG_SQL_* settings;
    it never reuses legacy historian credentials and never creates schema at runtime.
    """

    def __init__(self, settings: ConfigurationSQLSettings | None = None, connect_factory: Any = None) -> None:
        self.settings = settings or ConfigurationSQLSettings.from_environment()
        self._connect_factory = connect_factory

    @contextmanager
    def _connection(self, *, write: bool = False) -> Iterator[tuple[Any, Any]]:
        self.settings.validate(write=write)
        try:
            if self._connect_factory is None:
                import pyodbc

                connection = pyodbc.connect(self.settings.connection_string(), timeout=5, autocommit=False)
            else:
                connection = self._connect_factory(self.settings.connection_string(), timeout=5, autocommit=False)
            connection.timeout = 10
            cursor = connection.cursor()
            cursor.execute("EXECUTE AS USER = 'omagmes_config_runtime_user'")
        except ConfigurationUnavailable:
            raise
        except Exception as exc:
            raise ConfigurationUnavailable(f"SQL configuration database is unavailable ({type(exc).__name__}).") from None
        try:
            yield connection, cursor
            if write:
                connection.commit()
        except (ConfigurationConflict, ProductionDayConfigurationError):
            connection.rollback()
            raise
        except ConfigurationUnavailable:
            connection.rollback()
            raise
        except Exception as exc:
            connection.rollback()
            raise ConfigurationUnavailable(f"SQL configuration operation failed ({type(exc).__name__}).") from None
        finally:
            try:
                cursor.execute("REVERT")
            except Exception:
                pass
            connection.close()

    @staticmethod
    def _text(value: Any) -> str:
        return value.isoformat() if hasattr(value, "isoformat") else str(value)

    def get_cutoff_versions(self) -> list[dict[str, Any]]:
        with self._connection() as (_, cursor):
            cursor.execute(
                "SELECT id, EffectiveFromProductionDate, CutoffTime, TimeZone, CreatedAt, CreatedBy, ChangeReason "
                "FROM omagmes.ProductionDayCutoffVersion ORDER BY EffectiveFromProductionDate, id"
            )
            rows = cursor.fetchall()
        return [{
            "id": int(row[0]),
            "effective_from": self._text(row[1])[:10],
            "cutoff_time": self._text(row[2])[:5],
            "time_zone": str(row[3]),
            "created_at": self._text(row[4]),
            "created_by": str(row[5]),
            "change_reason": str(row[6]),
        } for row in rows]

    def get_shift_versions(self) -> list[dict[str, Any]]:
        with self._connection() as (_, cursor):
            cursor.execute("SELECT OBJECT_ID(N'omagmes.ShiftScheduleShiftPeriod', N'U')")
            has_period_table = cursor.fetchone()[0] is not None
            period_columns = ", p.id, p.PeriodOrder, p.StartTime, p.EndTime, p.IsActive " if has_period_table else ", NULL, NULL, NULL, NULL, NULL "
            period_join = (
                "LEFT JOIN omagmes.ShiftScheduleShiftPeriod AS p "
                "ON p.ShiftScheduleVersionID = d.ShiftScheduleVersionID AND p.ShiftID = d.ShiftID "
            ) if has_period_table else ""
            cursor.execute(
                "SELECT v.id, v.EffectiveFromProductionDate, v.CreatedAt, v.CreatedBy, v.ChangeReason, "
                "s.id, d.ShiftName, d.ShiftCode, d.StartTime, d.EndTime, d.DisplayOrder, d.IsActive "
                + period_columns
                + "FROM omagmes.ShiftScheduleVersion AS v "
                "LEFT JOIN omagmes.ShiftScheduleShift AS d ON d.ShiftScheduleVersionID = v.id "
                + period_join
                + "LEFT JOIN omagmes.Shift AS s ON s.id = d.ShiftID "
                "ORDER BY v.EffectiveFromProductionDate, v.id, d.DisplayOrder, s.id"
            )
            rows = cursor.fetchall()
        versions_by_id: dict[int, dict[str, Any]] = {}
        for row in rows:
            version_id = int(row[0])
            version = versions_by_id.setdefault(version_id, {
                "id": version_id,
                "effective_from": self._text(row[1])[:10],
                "created_at": self._text(row[2]),
                "created_by": str(row[3]),
                "change_reason": str(row[4]),
                "shifts": [],
            })
            if row[5] is not None:
                shift_id = int(row[5])
                shift = next((item for item in version["shifts"] if item["id"] == shift_id), None)
                if shift is None:
                    shift = {
                        "id": shift_id,
                        "shift_name": str(row[6]),
                        "shift_code": str(row[7]),
                        "start_time": self._text(row[8])[:5],
                        "end_time": self._text(row[9])[:5],
                        "display_order": int(row[10]),
                        "active": bool(row[11]),
                        "periods": [],
                    }
                    version["shifts"].append(shift)
                if has_period_table and row[12] is not None:
                    shift["periods"].append({
                        "period_id": int(row[12]), "display_order": int(row[13]),
                        "start_time": self._text(row[14])[:5], "end_time": self._text(row[15])[:5],
                        "active": bool(row[16]),
                    })
                elif not shift["periods"]:
                    shift["periods"].append({
                        "display_order": 1,
                        "start_time": shift["start_time"], "end_time": shift["end_time"],
                        "active": shift["active"],
                    })
        return list(versions_by_id.values())

    @staticmethod
    def _insert_history(
        cursor: Any,
        *,
        configuration_type: str,
        identity: str,
        version_id: int,
        old_value: Any | None,
        new_value: Any | None,
        changed_by: str,
        effective_from: str,
        reason: str,
    ) -> None:
        encode = lambda value: json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str) if value is not None else None
        cursor.execute(
            "INSERT INTO omagmes.ConfigurationChangeHistory "
            "(ConfigurationType, ConfigurationIdentity, VersionID, OldValue, NewValue, ChangedBy, EffectiveFromProductionDate, ChangeReason) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (configuration_type, identity, version_id, encode(old_value), encode(new_value), changed_by, effective_from, reason),
        )

    def get_configuration_history(self, limit: int = 500) -> list[dict[str, Any]]:
        with self._connection() as (_, cursor):
            cursor.execute(
                "WITH Changes AS ("
                "SELECT id, ConfigurationType, ConfigurationIdentity, VersionID, OldValue, NewValue, ChangedAt, ChangedBy, "
                "EffectiveFromProductionDate, ChangeReason, "
                "LEAD(EffectiveFromProductionDate) OVER (PARTITION BY ConfigurationType, ConfigurationIdentity "
                "ORDER BY EffectiveFromProductionDate, VersionID, id) AS EffectiveToExclusive "
                "FROM omagmes.ConfigurationChangeHistory) "
                "SELECT TOP (?) id, ConfigurationType, ConfigurationIdentity, VersionID, OldValue, NewValue, ChangedAt, ChangedBy, "
                "EffectiveFromProductionDate, EffectiveToExclusive, ChangeReason FROM Changes "
                "ORDER BY EffectiveFromProductionDate DESC, ChangedAt DESC, id DESC",
                (max(1, min(int(limit), 1000)),),
            )
            rows = cursor.fetchall()
        return [{
            "id": int(row[0]), "type": str(row[1]), "identity": str(row[2]), "version_id": int(row[3]),
            "old_value": row[4], "new_value": row[5], "changed_at": self._text(row[6]), "changed_by": str(row[7]),
            "effective_from": self._text(row[8])[:10],
            "effective_to_exclusive": self._text(row[9])[:10] if row[9] is not None else None,
            "change_reason": str(row[10]),
        } for row in rows]

    def shift_period_schema_available(self) -> bool:
        with self._connection() as (_, cursor):
            cursor.execute("SELECT OBJECT_ID(N'omagmes.ShiftScheduleShiftPeriod', N'U')")
            return cursor.fetchone()[0] is not None

    def get_shift_type_catalog(self) -> list[dict[str, Any]]:
        """Return all immutable Shift Type schedule snapshots and periods."""
        with self._connection() as (_, cursor):
            cursor.execute(
                "SELECT t.id,t.TypeCode,t.Description,t.IsActive,v.id,v.VersionNo,v.EffectiveFromProductionDate,"
                "v.CreatedAt,v.CreatedBy,v.ChangeReason,p.id,p.ShiftID,p.ShiftNumber,p.PeriodOrder,p.StartTime,p.EndTime,p.EndNextDay,p.IsActive "
                "FROM omagmes.ShiftType t LEFT JOIN omagmes.ShiftTypeScheduleVersion v ON v.ShiftTypeID=t.id "
                "LEFT JOIN omagmes.ShiftTypeSchedulePeriod p ON p.ShiftTypeScheduleVersionID=v.id "
                "ORDER BY t.TypeCode,v.VersionNo,p.PeriodOrder"
            )
            rows = cursor.fetchall()
        types: dict[int, dict[str, Any]] = {}
        for row in rows:
            type_id = int(row[0])
            item = types.setdefault(type_id, {
                "id": type_id, "type_code": str(row[1]), "description": str(row[2]),
                "active": bool(row[3]), "schedule_versions": [],
            })
            if row[4] is None:
                continue
            version_id = int(row[4])
            versions = item["schedule_versions"]
            version = next((entry for entry in versions if entry["id"] == version_id), None)
            if version is None:
                version = {
                    "id": version_id, "version_no": int(row[5]),
                    "effective_from": self._text(row[6])[:10], "created_at": self._text(row[7]),
                    "created_by": str(row[8]), "change_reason": str(row[9]), "periods": [],
                }
                versions.append(version)
            if row[10] is not None:
                version["periods"].append({
                    "id": int(row[10]), "shift_id": int(row[11]), "shift_number": int(row[12]),
                    "period_order": int(row[13]), "start_time": self._text(row[14])[:5],
                    "end_time": self._text(row[15])[:5], "end_next_day": bool(row[16]),
                    "active": bool(row[17]),
                })
        return list(types.values())

    @staticmethod
    def _require_daily_shift_schema(cursor: Any) -> None:
        cursor.execute(
            "SELECT OBJECT_ID(N'omagmes.DailyShiftConfigurationSave',N'U'),"
            "OBJECT_ID(N'omagmes.DailyShiftConfigurationPeriod',N'U')"
        )
        objects = cursor.fetchone()
        if objects is None or objects[0] is None or objects[1] is None:
            raise ConfigurationUnavailable(
                "Daily Shift configuration schema is not deployed. An authorized DBA must review and apply migration 011."
            )

    @staticmethod
    def _daily_shift_periods(cursor: Any, configuration_save_id: int) -> list[dict[str, Any]]:
        cursor.execute(
            "SELECT Type,Shift,TypeID,ShiftID,CONVERT(char(5),[Start],108),CONVERT(char(5),[Stop],108) "
            "FROM omagmes.DailyShiftConfigurationPeriod WHERE ConfigurationSaveID=? ORDER BY Type,Shift",
            (configuration_save_id,),
        )
        return [
            {"type": int(row[0]), "shift": int(row[1]), "type_id": int(row[2]), "shift_id": int(row[3]),
             "start": str(row[4]), "stop": str(row[5])}
            for row in cursor.fetchall()
        ]

    @staticmethod
    def _daily_shift_type_id_map(cursor: Any) -> dict[int, int]:
        cursor.execute(
            "SELECT TypeCode,COUNT_BIG(*),MIN(id) FROM omagmes.ShiftType "
            "WHERE TypeCode IN (N'TYPE 1',N'TYPE 2',N'TYPE 3') GROUP BY TypeCode"
        )
        mapping: dict[int, int] = {}
        for row in cursor.fetchall():
            type_code = str(row[0])
            type_number = int(type_code[-1])
            if int(row[1]) != 1:
                raise ConfigurationUnavailable(f"{type_code} does not resolve to exactly one existing Shift Type identity.")
            mapping[type_number] = int(row[2])
        if set(mapping) != {1, 2, 3}:
            raise ConfigurationUnavailable("Existing Shift Type identities TYPE 1, TYPE 2, and TYPE 3 are required.")
        return mapping

    @staticmethod
    def _daily_shift_id_map(cursor: Any) -> dict[int, int]:
        cursor.execute(
            "SELECT ShiftNumber,COUNT(DISTINCT ShiftID),MIN(ShiftID) "
            "FROM omagmes.ShiftTypeSchedulePeriod WHERE ShiftNumber IN (1,2,3) GROUP BY ShiftNumber"
        )
        mapping: dict[int, int] = {}
        for row in cursor.fetchall():
            number, count, shift_id = int(row[0]), int(row[1]), int(row[2])
            if count != 1:
                raise ConfigurationUnavailable(f"Shift {number} does not resolve to exactly one existing Shift identity.")
            mapping[number] = shift_id
        if set(mapping) != {1, 2, 3}:
            raise ConfigurationUnavailable("Existing Shift identities 1, 2, and 3 are required for daily Shift configuration.")
        return mapping

    def _daily_configuration_result(
        self,
        *,
        production_date: str,
        selected_type: int,
        periods: list[dict[str, Any]],
        status: str,
        source_production_date: str | None,
        save_id: int | None = None,
        save_time: Any | None = None,
        selected_shift_type_id: int | None = None,
        shift_type_id_map: dict[int, int],
        shift_id_map: dict[int, int],
    ) -> dict[str, Any]:
        expected_selected_type_id = shift_type_id_map.get(selected_type)
        if expected_selected_type_id is None:
            raise ConfigurationUnavailable("Selected Shift Type does not resolve to an authoritative identity.")
        if selected_shift_type_id is not None and int(selected_shift_type_id) != expected_selected_type_id:
            raise ConfigurationUnavailable("Saved configuration references the wrong authoritative Shift Type identity.")
        try:
            _, normalized = normalize_shift_configuration(selected_type, periods)
        except DailyShiftConfigurationError as exc:
            raise ConfigurationUnavailable(f"Saved Shift configuration is incomplete or invalid: {exc}") from None
        stored_shift_ids: dict[tuple[int, int], int] = {}
        for row in periods:
            type_number, shift_number = int(row["type"]), int(row["shift"])
            if row.get("type_id") is not None and int(row["type_id"]) != shift_type_id_map[type_number]:
                raise ConfigurationUnavailable("Saved Shift row references the wrong authoritative Shift Type identity.")
            if row.get("shift_id") is not None:
                shift_id = int(row["shift_id"])
                if shift_id != shift_id_map[shift_number]:
                    raise ConfigurationUnavailable("Saved Shift row references the wrong authoritative Shift identity.")
                stored_shift_ids[(type_number, shift_number)] = shift_id
        public_periods = template_periods(normalized)
        schedule_periods = [
            {
                "shift_id": stored_shift_ids.get((item["type"], item["shift"]), shift_id_map[item["shift"]]),
                "shift_number": item["shift"],
                "period_order": index,
                "start_time": item["start"],
                "end_time": item["stop"],
                "end_next_day": item["stop"] <= item["start"],
                "active": True,
            }
            for index, item in enumerate((period for period in normalized if period["type"] == selected_type), start=1)
        ]
        return {
            "status": status,
            "production_date": production_date,
            "selected_type": selected_type,
            "selected_shift_type_id": shift_type_id_map[selected_type],
            "type_code": f"TYPE {selected_type}",
            "periods": public_periods,
            "source_production_date": source_production_date,
            "configuration_save_id": save_id,
            "save_time": self._text(save_time) if save_time is not None else None,
            "schedule": {
                "id": save_id,
                "effective_production_date": production_date,
                "periods": schedule_periods,
            },
        }

    def get_daily_shift_configuration(self, production_date: str) -> dict[str, Any]:
        """Load a date's latest complete save, else copy the latest global save as a draft default."""
        selected_date = parse_production_date(production_date).isoformat()
        with self._connection() as (_, cursor):
            self._require_daily_shift_schema(cursor)
            shift_type_id_map = self._daily_shift_type_id_map(cursor)
            shift_id_map = self._daily_shift_id_map(cursor)
            cursor.execute(
                "SELECT TOP (1) id,ProductionDate,SelectedType,SelectedShiftTypeID,SaveTime "
                "FROM omagmes.DailyShiftConfigurationSave WHERE IsComplete=1 AND ProductionDate=? "
                "ORDER BY SaveTime DESC,id DESC",
                (selected_date,),
            )
            saved = cursor.fetchone()
            if saved is not None:
                rows = self._daily_shift_periods(cursor, int(saved[0]))
                return self._daily_configuration_result(
                    production_date=selected_date, selected_type=int(saved[2]), periods=rows,
                    status="SAVED", source_production_date=selected_date,
                    save_id=int(saved[0]), save_time=saved[4],
                    selected_shift_type_id=int(saved[3]),
                    shift_type_id_map=shift_type_id_map, shift_id_map=shift_id_map,
                )

            cursor.execute(
                "SELECT TOP (1) id,ProductionDate,SelectedType,SelectedShiftTypeID,SaveTime "
                "FROM omagmes.DailyShiftConfigurationSave WHERE IsComplete=1 "
                "ORDER BY SaveTime DESC,id DESC"
            )
            latest = cursor.fetchone()
            if latest is None:
                return self._daily_configuration_result(
                    production_date=selected_date, selected_type=1, periods=initial_shift_periods(),
                    status="NOT_SAVED", source_production_date=None,
                    shift_type_id_map=shift_type_id_map, shift_id_map=shift_id_map,
                )
            rows = self._daily_shift_periods(cursor, int(latest[0]))
            return self._daily_configuration_result(
                production_date=selected_date, selected_type=int(latest[2]), periods=rows,
                status="DEFAULT", source_production_date=self._text(latest[1])[:10],
                save_id=int(latest[0]), save_time=latest[4],
                selected_shift_type_id=int(latest[3]),
                shift_type_id_map=shift_type_id_map, shift_id_map=shift_id_map,
            )

    def save_daily_shift_configuration(
        self, *, production_date: str, selected_type: int, periods: list[dict[str, Any]],
    ) -> dict[str, Any]:
        selected_date = parse_production_date(production_date).isoformat()
        try:
            normalized_type, normalized_periods = normalize_shift_configuration(selected_type, periods)
        except DailyShiftConfigurationError as exc:
            raise ProductionDayConfigurationError(str(exc)) from None
        persisted_periods = template_periods(normalized_periods)
        with self._connection(write=True) as (_, cursor):
            self._require_daily_shift_schema(cursor)
            cursor.execute(
                "SET TRANSACTION ISOLATION LEVEL SERIALIZABLE; "
                "DECLARE @LockResult int; "
                "EXEC @LockResult=sys.sp_getapplock @Resource=N'omagmes.DailyShiftConfiguration.Save', "
                "@LockMode=N'Exclusive',@LockOwner=N'Transaction',@LockTimeout=10000; "
                "SELECT @LockResult"
            )
            lock_row = cursor.fetchone()
            if lock_row is None or int(lock_row[0]) < 0:
                raise ConfigurationConflict("Another Shift configuration save is in progress; retry SAVE.")
            shift_type_id_map = self._daily_shift_type_id_map(cursor)
            shift_id_map = self._daily_shift_id_map(cursor)
            cursor.execute(
                "INSERT INTO omagmes.DailyShiftConfigurationSave (ProductionDate,SelectedType,SelectedShiftTypeID) "
                "OUTPUT INSERTED.id VALUES (?,?,?)",
                (selected_date, normalized_type, shift_type_id_map[normalized_type]),
            )
            save_id = int(cursor.fetchone()[0])
            placeholders = ",".join("(?,?,?,?,?,?,?,?)" for _ in persisted_periods)
            params: list[Any] = []
            for item in persisted_periods:
                params.extend((
                    save_id, selected_date, item["type"], item["shift"],
                    shift_type_id_map[item["type"]], shift_id_map[item["shift"]],
                    item["start"], item["stop"],
                ))
            cursor.execute(
                "INSERT INTO omagmes.DailyShiftConfigurationPeriod "
                "(ConfigurationSaveID,ProductionDate,Type,Shift,TypeID,ShiftID,[Start],[Stop]) VALUES " + placeholders,
                tuple(params),
            )
            cursor.execute(
                "SELECT COUNT(*) FROM omagmes.DailyShiftConfigurationPeriod WHERE ConfigurationSaveID=?",
                (save_id,),
            )
            period_count = cursor.fetchone()
            if period_count is None or int(period_count[0]) != 5:
                raise ConfigurationUnavailable("Daily Shift configuration save is incomplete; the transaction was rolled back.")
            cursor.execute(
                "UPDATE omagmes.DailyShiftConfigurationSave SET IsComplete=1 WHERE id=? AND IsComplete=0",
                (save_id,),
            )
            cursor.execute(
                "SELECT id,ProductionDate,SelectedType,SelectedShiftTypeID,SaveTime "
                "FROM omagmes.DailyShiftConfigurationSave WHERE id=? AND IsComplete=1",
                (save_id,),
            )
            saved = cursor.fetchone()
            if saved is None:
                raise ConfigurationUnavailable("Shift configuration was not marked complete; the transaction was rolled back.")
            saved_rows = self._daily_shift_periods(cursor, save_id)
            self._daily_configuration_result(
                production_date=selected_date, selected_type=int(saved[2]), periods=saved_rows,
                status="SAVED", source_production_date=selected_date,
                save_id=save_id, save_time=saved[4],
                selected_shift_type_id=int(saved[3]),
                shift_type_id_map=shift_type_id_map, shift_id_map=shift_id_map,
            )
        # Verify the committed snapshot over a fresh connection before returning success.
        result = self.get_daily_shift_configuration(selected_date)
        if result.get("status") != "SAVED" or result.get("configuration_save_id") != save_id:
            raise ConfigurationUnavailable("Shift configuration committed but read-back did not find the saved snapshot; reconcile before retrying.")
        return result

    def get_daily_shift_type_assignment(self, production_date: str) -> dict[str, Any]:
        selected_date = parse_production_date(production_date).isoformat()
        with self._connection() as (_, cursor):
            cursor.execute(
                "SELECT TOP (1) a.id,a.AssignmentVersionNo,a.ProductionDate,a.ShiftTypeID,t.TypeCode,t.Description,"
                "a.ShiftTypeScheduleVersionID,v.VersionNo,v.EffectiveFromProductionDate,a.ProductionDayCutoffVersionID,"
                "a.CreatedAt,a.CreatedBy,a.ChangeReason "
                "FROM omagmes.DailyShiftTypeAssignment a JOIN omagmes.ShiftType t ON t.id=a.ShiftTypeID "
                "JOIN omagmes.ShiftTypeScheduleVersion v ON v.id=a.ShiftTypeScheduleVersionID "
                "WHERE a.ProductionDate=? ORDER BY a.AssignmentVersionNo DESC,a.id DESC",
                (selected_date,),
            )
            row = cursor.fetchone()
            if row is None:
                return {"status": "SHIFT TYPE NOT SELECTED", "production_date": selected_date, "assignment": None}
            cursor.execute(
                "SELECT id,ShiftID,ShiftNumber,PeriodOrder,StartTime,EndTime,EndNextDay,IsActive "
                "FROM omagmes.ShiftTypeSchedulePeriod WHERE ShiftTypeScheduleVersionID=? ORDER BY PeriodOrder",
                (int(row[6]),),
            )
            periods = [{
                "id": int(period[0]), "shift_id": int(period[1]), "shift_number": int(period[2]),
                "period_order": int(period[3]), "start_time": self._text(period[4])[:5],
                "end_time": self._text(period[5])[:5], "end_next_day": bool(period[6]), "active": bool(period[7]),
            } for period in cursor.fetchall()]
        assignment = {
            "id": int(row[0]), "assignment_version_no": int(row[1]), "production_date": self._text(row[2])[:10],
            "shift_type_id": int(row[3]), "type_code": str(row[4]), "description": str(row[5]),
            "schedule_version_id": int(row[6]), "schedule_version_no": int(row[7]),
            "schedule_effective_from": self._text(row[8])[:10], "cutoff_version_id": int(row[9]),
            "created_at": self._text(row[10]), "created_by": str(row[11]), "change_reason": str(row[12]),
            "schedule": {"id": int(row[6]), "version_no": int(row[7]), "effective_production_date": self._text(row[8])[:10], "periods": periods},
        }
        return {"status": "SAVED", "production_date": selected_date, "assignment": assignment, **assignment}

    def save_daily_shift_type_assignment(
        self, *, production_date: str, shift_type_id: int,
        expected_assignment_id: int | None,
    ) -> dict[str, Any]:
        selected_date = parse_production_date(production_date).isoformat()
        if shift_type_id <= 0:
            raise ProductionDayConfigurationError("A valid Shift Type is required.")
        changed_by = f"INTERNAL DEVELOPMENT · {getpass.getuser()}"
        with self._connection(write=True) as (_, cursor):
            cursor.execute(
                "SELECT TOP (1) a.id,a.AssignmentVersionNo,a.ShiftTypeID,t.TypeCode,a.ShiftTypeScheduleVersionID,"
                "a.ProductionDayCutoffVersionID,v.VersionNo "
                "FROM omagmes.DailyShiftTypeAssignment a WITH (UPDLOCK,HOLDLOCK) "
                "JOIN omagmes.ShiftType t ON t.id=a.ShiftTypeID "
                "JOIN omagmes.ShiftTypeScheduleVersion v ON v.id=a.ShiftTypeScheduleVersionID "
                "WHERE a.ProductionDate=? ORDER BY a.AssignmentVersionNo DESC,a.id DESC",
                (selected_date,),
            )
            current = cursor.fetchone()
            current_id = int(current[0]) if current else None
            if current_id != expected_assignment_id:
                raise ConfigurationConflict("The saved Shift Type assignment changed; reload this Production Date before saving.")
            cursor.execute("SELECT TypeCode,Description,IsActive FROM omagmes.ShiftType WHERE id=?", (shift_type_id,))
            type_row = cursor.fetchone()
            if type_row is None or not bool(type_row[2]):
                raise ProductionDayConfigurationError("Selected Shift Type does not exist or is inactive.")
            type_code, description = str(type_row[0]), str(type_row[1])
            cursor.execute(
                "SELECT TOP (1) id,VersionNo,EffectiveFromProductionDate FROM omagmes.ShiftTypeScheduleVersion "
                "WHERE ShiftTypeID=? AND EffectiveFromProductionDate<=? ORDER BY EffectiveFromProductionDate DESC,VersionNo DESC",
                (shift_type_id, selected_date),
            )
            schedule_row = cursor.fetchone()
            if schedule_row is None:
                raise ProductionDayConfigurationError("No Shift Type schedule version applies to this Production Date.")
            schedule_id, schedule_version_no = int(schedule_row[0]), int(schedule_row[1])
            cursor.execute(
                "SELECT ShiftID,ShiftNumber,PeriodOrder,StartTime,EndTime,EndNextDay,IsActive "
                "FROM omagmes.ShiftTypeSchedulePeriod WHERE ShiftTypeScheduleVersionID=? ORDER BY PeriodOrder",
                (schedule_id,),
            )
            periods = [{
                "shift_id": int(p[0]), "shift_number": int(p[1]), "period_order": int(p[2]),
                "start_time": self._text(p[3])[:5], "end_time": self._text(p[4])[:5],
                "end_next_day": bool(p[5]), "active": bool(p[6]),
            } for p in cursor.fetchall()]
            try:
                validate_shift_type_periods(type_code, periods)
            except ShiftTypeValidationError as exc:
                raise ProductionDayConfigurationError(f"Selected Shift Type schedule is invalid: {exc}") from None
            cursor.execute(
                "SELECT TOP (1) id FROM omagmes.ProductionDayCutoffVersion WHERE EffectiveFromProductionDate<=? "
                "ORDER BY EffectiveFromProductionDate DESC,id DESC", (selected_date,),
            )
            cutoff_row = cursor.fetchone()
            if cutoff_row is None:
                raise ProductionDayConfigurationError("No Production Date Cutoff version applies to this date.")
            cutoff_id = int(cutoff_row[0])
            if current and int(current[2]) == shift_type_id and int(current[4]) == schedule_id and int(current[5]) == cutoff_id:
                assignment = {
                    "id": current_id, "assignment_version_no": int(current[1]), "production_date": selected_date,
                    "shift_type_id": shift_type_id, "type_code": type_code, "description": description,
                    "schedule_version_id": schedule_id, "schedule_version_no": schedule_version_no,
                    "schedule_effective_from": self._text(schedule_row[2])[:10], "cutoff_version_id": cutoff_id,
                    "schedule": {"id": schedule_id, "version_no": schedule_version_no,
                                     "effective_production_date": self._text(schedule_row[2])[:10], "periods": periods},
                }
                return {"status": "SAVED", "production_date": selected_date, "assignment": assignment, **assignment}
            cursor.execute(
                "SELECT COALESCE(MAX(AssignmentVersionNo),0)+1 FROM omagmes.DailyShiftTypeAssignment WITH (UPDLOCK,HOLDLOCK) WHERE ProductionDate=?",
                (selected_date,),
            )
            assignment_version_no = int(cursor.fetchone()[0])
            cursor.execute(
                "INSERT INTO omagmes.DailyShiftTypeAssignment "
                "(ProductionDate,AssignmentVersionNo,ShiftTypeID,ShiftTypeScheduleVersionID,ProductionDayCutoffVersionID,CreatedBy,ChangeReason) "
                "OUTPUT INSERTED.id VALUES (?,?,?,?,?,?,?)",
                (selected_date, assignment_version_no, shift_type_id, schedule_id, cutoff_id, changed_by, SYSTEM_CONFIGURATION_CHANGE_REASON),
            )
            assignment_id = int(cursor.fetchone()[0])
            old_value = None if current is None else {
                "type_code": str(current[3]), "shift_type_id": int(current[2]),
                "schedule_version_id": int(current[4]), "schedule_version_no": int(current[6]),
            }
            new_value = {
                "type_code": type_code, "shift_type_id": shift_type_id,
                "schedule_version_id": schedule_id, "schedule_version_no": schedule_version_no,
            }
            self._insert_history(
                cursor, configuration_type="DAILY_SHIFT_TYPE_ASSIGNMENT", identity=selected_date,
                version_id=assignment_id, old_value=old_value, new_value=new_value,
                changed_by=changed_by, effective_from=selected_date, reason=SYSTEM_CONFIGURATION_CHANGE_REASON,
            )
        return self.get_daily_shift_type_assignment(selected_date)

    def create_shift_type_schedule_version(
        self, *, shift_type_id: int, effective_from: str, base_schedule_version_id: int,
        current_production_date: str, periods: list[dict[str, Any]],
    ) -> dict[str, Any]:
        effective = parse_production_date(effective_from).isoformat()
        current_date = parse_production_date(current_production_date).isoformat()
        changed_by = f"INTERNAL DEVELOPMENT · {getpass.getuser()}"
        if effective <= current_date:
            raise ProductionDayConfigurationError("Shift Type schedule changes require a future effective Production Date.")
        with self._connection(write=True) as (_, cursor):
            cursor.execute("SELECT TypeCode,IsActive FROM omagmes.ShiftType WHERE id=?", (shift_type_id,))
            type_row = cursor.fetchone()
            if type_row is None or not bool(type_row[1]):
                raise ProductionDayConfigurationError("Selected Shift Type does not exist or is inactive.")
            type_code = str(type_row[0])
            try:
                normalized = validate_shift_type_periods(type_code, periods)
            except ShiftTypeValidationError as exc:
                raise ProductionDayConfigurationError(str(exc)) from None
            cursor.execute(
                "SELECT TOP (1) id,VersionNo,EffectiveFromProductionDate FROM omagmes.ShiftTypeScheduleVersion WITH (UPDLOCK,HOLDLOCK) "
                "WHERE ShiftTypeID=? ORDER BY EffectiveFromProductionDate DESC,VersionNo DESC",
                (shift_type_id,),
            )
            latest = cursor.fetchone()
            if latest is None:
                raise ConfigurationUnavailable("Shift Type has no initialized schedule version.")
            if int(latest[0]) != base_schedule_version_id:
                raise ConfigurationConflict("A newer Shift Type schedule exists; reload before saving.")
            if effective <= self._text(latest[2])[:10]:
                raise ConfigurationConflict("Shift Type schedule versions must be effective after the latest version.")
            cursor.execute(
                "SELECT ShiftID,ShiftNumber,PeriodOrder,StartTime,EndTime,EndNextDay,IsActive FROM omagmes.ShiftTypeSchedulePeriod "
                "WHERE ShiftTypeScheduleVersionID=? ORDER BY PeriodOrder", (base_schedule_version_id,),
            )
            old_periods = [{
                "shift_id": int(p[0]), "shift_number": int(p[1]), "period_order": int(p[2]),
                "start_time": self._text(p[3])[:5], "end_time": self._text(p[4])[:5],
                "end_next_day": bool(p[5]), "active": bool(p[6]),
            } for p in cursor.fetchall()]
            identity_by_number = {p["shift_number"]: p["shift_id"] for p in old_periods}
            if any(identity_by_number.get(period["shift_number"]) != period["shift_id"] for period in normalized):
                raise ProductionDayConfigurationError("Shift IDs must remain the stable identity assigned to each confirmed Shift number.")
            version_no = int(latest[1]) + 1
            cursor.execute(
                "INSERT INTO omagmes.ShiftTypeScheduleVersion(ShiftTypeID,VersionNo,EffectiveFromProductionDate,CreatedBy,ChangeReason) "
                "OUTPUT INSERTED.id VALUES(?,?,?,?,?)",
                (shift_type_id, version_no, effective, changed_by, SYSTEM_CONFIGURATION_CHANGE_REASON),
            )
            version_id = int(cursor.fetchone()[0])
            for period in normalized:
                cursor.execute(
                    "INSERT INTO omagmes.ShiftTypeSchedulePeriod "
                    "(ShiftTypeScheduleVersionID,ShiftTypeID,ShiftID,ShiftNumber,PeriodOrder,StartTime,EndTime,EndNextDay,IsActive) "
                    "VALUES(?,?,?,?,?,?,?,?,?)",
                    (version_id, shift_type_id, period["shift_id"], period["shift_number"], period["period_order"],
                     period["start_time"], period["end_time"], period["end_next_day"], period["active"]),
                )
            self._insert_history(
                cursor, configuration_type="SHIFT_TYPE_SCHEDULE", identity=type_code,
                version_id=version_id, old_value=old_periods, new_value=normalized,
                changed_by=changed_by, effective_from=effective, reason=SYSTEM_CONFIGURATION_CHANGE_REASON,
            )
        return {
            "id": version_id, "shift_type_id": shift_type_id, "type_code": type_code,
            "version_no": version_no, "effective_from": effective, "created_by": changed_by,
            "change_reason": SYSTEM_CONFIGURATION_CHANGE_REASON, "periods": normalized,
        }

    def create_cutoff_version(
        self,
        *,
        effective_from: str,
        cutoff_time: str,
        time_zone: str,
        base_version_id: int,
        reason: str,
        current_production_date: str,
    ) -> dict[str, Any]:
        effective_date = parse_production_date(effective_from)
        if time_zone != SUPPORTED_TIME_ZONE:
            raise ProductionDayConfigurationError(f"Production Day Cutoff timezone must be {SUPPORTED_TIME_ZONE}.")
        minimum_date = date.fromisoformat(minimum_safe_cutoff_effective_date(current_production_date))
        if effective_date < minimum_date:
            raise ConfigurationConflict(f"Cutoff changes must be effective no earlier than {minimum_date.isoformat()} to protect started Production Days.")
        with self._connection(write=True) as (_, cursor):
            cursor.execute(
                "SELECT TOP (1) id, EffectiveFromProductionDate, CutoffTime, TimeZone FROM omagmes.ProductionDayCutoffVersion WITH (UPDLOCK, HOLDLOCK) "
                "ORDER BY EffectiveFromProductionDate DESC, id DESC"
            )
            latest = cursor.fetchone()
            if latest is None:
                raise ConfigurationUnavailable("Initial Production Day Cutoff must be installed by the reviewed database bootstrap migration.")
            if int(latest[0]) != base_version_id:
                raise ConfigurationConflict("A newer cutoff version exists; reload the settings before saving.")
            if effective_date <= latest[1]:
                raise ConfigurationConflict("Cutoff versions must have unique, forward-only effective Production Dates.")
            cursor.execute(
                "INSERT INTO omagmes.ProductionDayCutoffVersion "
                "(EffectiveFromProductionDate, CutoffTime, TimeZone, CreatedAt, CreatedBy, ChangeReason) "
                "OUTPUT INSERTED.id VALUES (?, ?, ?, SYSUTCDATETIME(), ?, ?)",
                (effective_from, cutoff_time, time_zone, f"INTERNAL DEVELOPMENT · {getpass.getuser()}", reason),
            )
            row = cursor.fetchone()
            created_by = f"INTERNAL DEVELOPMENT · {getpass.getuser()}"
            self._insert_history(
                cursor,
                configuration_type="PRODUCTION_DAY_CUTOFF",
                identity="PRODUCTION_DAY_CUTOFF",
                version_id=int(row[0]),
                old_value={"cutoff_time": self._text(latest[2])[:5], "time_zone": str(latest[3])},
                new_value={"cutoff_time": cutoff_time, "time_zone": time_zone},
                changed_by=created_by,
                effective_from=effective_from,
                reason=reason,
            )
            return {"id": int(row[0]), "effective_from": effective_from, "cutoff_time": cutoff_time,
                    "time_zone": time_zone, "created_at": "DATABASE UTC",
                    "created_by": created_by, "change_reason": reason}

    def create_shift_version(
        self,
        *,
        effective_from: str,
        base_version_id: int,
        reason: str,
        shifts: list[dict[str, Any]],
        reviewed_through_date: str,
    ) -> dict[str, Any]:
        normalized = validate_shift_definitions(shifts)
        effective_date = parse_production_date(effective_from)
        reviewed_date = parse_production_date(reviewed_through_date)
        with self._connection(write=True) as (_, cursor):
            cursor.execute("SELECT OBJECT_ID(N'omagmes.ShiftScheduleShiftPeriod', N'U')")
            has_period_table = cursor.fetchone()[0] is not None
            cursor.execute(
                "SELECT TOP (1) id, EffectiveFromProductionDate FROM omagmes.ShiftScheduleVersion WITH (UPDLOCK, HOLDLOCK) "
                "ORDER BY EffectiveFromProductionDate DESC, id DESC"
            )
            latest = cursor.fetchone()
            if latest is None:
                raise ConfigurationUnavailable("Initial Shift Schedule must be installed by the reviewed database bootstrap migration.")
            if int(latest[0]) != base_version_id:
                raise ConfigurationConflict("A newer Shift Schedule version exists; reload before saving.")
            if effective_date <= latest[1] or effective_date <= reviewed_date:
                raise ConfigurationConflict("A Shift Schedule version must start after the latest version and selected Production Date.")
            cursor.execute(
                "SELECT d.ShiftID, d.ShiftName, d.ShiftCode, d.DisplayOrder, d.IsActive, "
                "d.StartTime, d.EndTime, p.PeriodOrder, p.StartTime, p.EndTime, p.IsActive "
                "FROM omagmes.ShiftScheduleShift d LEFT JOIN omagmes.ShiftScheduleShiftPeriod p "
                "ON p.ShiftScheduleVersionID=d.ShiftScheduleVersionID AND p.ShiftID=d.ShiftID "
                "WHERE d.ShiftScheduleVersionID=? ORDER BY d.DisplayOrder, p.PeriodOrder",
                (base_version_id,),
            )
            old_shifts: dict[int, dict[str, Any]] = {}
            for row in cursor.fetchall():
                shift_id = int(row[0])
                old = old_shifts.setdefault(shift_id, {
                    "id": shift_id, "shift_name": str(row[1]), "shift_code": str(row[2]),
                    "display_order": int(row[3]), "active": bool(row[4]), "periods": [],
                })
                old["periods"].append({
                    "display_order": int(row[7]) if row[7] is not None else 1,
                    "start_time": self._text(row[8] if row[8] is not None else row[5])[:5],
                    "end_time": self._text(row[9] if row[9] is not None else row[6])[:5],
                    "active": bool(row[10]) if row[10] is not None else bool(row[4]),
                })
            cursor.execute("SELECT ShiftID FROM omagmes.ShiftScheduleShift WHERE ShiftScheduleVersionID = ?", (base_version_id,))
            latest_shift_ids = {int(row[0]) for row in cursor.fetchall()}
            cursor.execute("SELECT id FROM omagmes.Shift")
            known_shift_ids = {int(row[0]) for row in cursor.fetchall()}
            for shift in normalized:
                shift_id = shift["id"]
                if shift_id is not None and shift_id not in known_shift_ids:
                    raise ProductionDayConfigurationError("Shift ID is not a known stable Shift identity.")
                if shift_id is not None and shift_id not in latest_shift_ids:
                    raise ProductionDayConfigurationError("Only Shift identities in the latest schedule version may be reused.")
                if shift_id is None:
                    cursor.execute("INSERT INTO omagmes.Shift OUTPUT INSERTED.id DEFAULT VALUES")
                    shift["id"] = int(cursor.fetchone()[0])
            cursor.execute(
                "INSERT INTO omagmes.ShiftScheduleVersion (EffectiveFromProductionDate, CreatedAt, CreatedBy, ChangeReason) "
                "OUTPUT INSERTED.id VALUES (?, SYSUTCDATETIME(), ?, ?)",
                (effective_from, f"INTERNAL DEVELOPMENT · {getpass.getuser()}", reason),
            )
            version_id = int(cursor.fetchone()[0])
            for shift in normalized:
                cursor.execute(
                    "INSERT INTO omagmes.ShiftScheduleShift "
                    "(ShiftScheduleVersionID, ShiftID, ShiftName, ShiftCode, StartTime, EndTime, DisplayOrder, IsActive) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (version_id, shift["id"], shift["shift_name"], shift["shift_code"], shift["start_time"],
                     shift["end_time"], shift["display_order"], shift["active"]),
                )
                if has_period_table:
                    cursor.execute(
                        "INSERT INTO omagmes.ShiftScheduleShiftPeriod "
                        "(ShiftScheduleVersionID, ShiftID, PeriodOrder, StartTime, EndTime, IsActive) VALUES (?, ?, 1, ?, ?, ?)",
                        (version_id, shift["id"], shift["start_time"], shift["end_time"], shift["active"]),
                    )
            return {
                "id": version_id, "effective_from": effective_from, "created_at": "DATABASE UTC",
                "created_by": f"INTERNAL DEVELOPMENT · {getpass.getuser()}", "change_reason": reason,
                "shifts": normalized,
            }

    def create_shift_period_version(
        self,
        *,
        effective_from: str,
        base_version_id: int,
        reason: str,
        shifts: list[dict[str, Any]],
        reviewed_through_date: str,
    ) -> dict[str, Any]:
        normalized = validate_shift_period_definitions(shifts)
        effective_date = parse_production_date(effective_from)
        reviewed_date = parse_production_date(reviewed_through_date)
        with self._connection(write=True) as (_, cursor):
            cursor.execute("SELECT OBJECT_ID(N'omagmes.ShiftScheduleShiftPeriod', N'U')")
            if cursor.fetchone()[0] is None:
                raise ConfigurationUnavailable("Shift Period schema is not deployed. The DBA-reviewed additive migration must be approved and applied separately.")
            cursor.execute(
                "SELECT TOP (1) id, EffectiveFromProductionDate FROM omagmes.ShiftScheduleVersion WITH (UPDLOCK, HOLDLOCK) "
                "ORDER BY EffectiveFromProductionDate DESC, id DESC"
            )
            latest = cursor.fetchone()
            if latest is None:
                raise ConfigurationUnavailable("Initial Shift Schedule must be installed by the reviewed database bootstrap migration.")
            if int(latest[0]) != base_version_id:
                raise ConfigurationConflict("A newer Shift Schedule version exists; reload before saving.")
            if effective_date <= latest[1] or effective_date <= reviewed_date:
                raise ConfigurationConflict("A Shift Schedule version must start after the latest version and selected Production Date.")
            cursor.execute(
                "SELECT d.ShiftID, d.ShiftName, d.ShiftCode, d.DisplayOrder, d.IsActive, "
                "d.StartTime, d.EndTime, p.PeriodOrder, p.StartTime, p.EndTime, p.IsActive "
                "FROM omagmes.ShiftScheduleShift d LEFT JOIN omagmes.ShiftScheduleShiftPeriod p "
                "ON p.ShiftScheduleVersionID=d.ShiftScheduleVersionID AND p.ShiftID=d.ShiftID "
                "WHERE d.ShiftScheduleVersionID=? ORDER BY d.DisplayOrder, p.PeriodOrder",
                (base_version_id,),
            )
            old_shifts: dict[int, dict[str, Any]] = {}
            for row in cursor.fetchall():
                shift_id = int(row[0])
                old = old_shifts.setdefault(shift_id, {
                    "id": shift_id, "shift_name": str(row[1]), "shift_code": str(row[2]),
                    "display_order": int(row[3]), "active": bool(row[4]), "periods": [],
                })
                old["periods"].append({
                    "display_order": int(row[7]) if row[7] is not None else 1,
                    "start_time": self._text(row[8] if row[8] is not None else row[5])[:5],
                    "end_time": self._text(row[9] if row[9] is not None else row[6])[:5],
                    "active": bool(row[10]) if row[10] is not None else bool(row[4]),
                })
            cursor.execute("SELECT ShiftID FROM omagmes.ShiftScheduleShift WHERE ShiftScheduleVersionID = ?", (base_version_id,))
            latest_shift_ids = {int(row[0]) for row in cursor.fetchall()}
            cursor.execute("SELECT id FROM omagmes.Shift")
            known_shift_ids = {int(row[0]) for row in cursor.fetchall()}
            for shift in normalized:
                shift_id = shift["id"]
                if shift_id is not None and shift_id not in known_shift_ids:
                    raise ProductionDayConfigurationError("Shift ID is not a known stable Shift identity.")
                if shift_id is not None and shift_id not in latest_shift_ids:
                    raise ProductionDayConfigurationError("Only Shift identities in the latest schedule version may be reused.")
                if shift_id is None:
                    cursor.execute("INSERT INTO omagmes.Shift OUTPUT INSERTED.id DEFAULT VALUES")
                    shift["id"] = int(cursor.fetchone()[0])
            cursor.execute(
                "INSERT INTO omagmes.ShiftScheduleVersion (EffectiveFromProductionDate, CreatedAt, CreatedBy, ChangeReason) "
                "OUTPUT INSERTED.id VALUES (?, SYSUTCDATETIME(), ?, ?)",
                (effective_from, f"INTERNAL DEVELOPMENT · {getpass.getuser()}", reason),
            )
            version_id = int(cursor.fetchone()[0])
            for shift in normalized:
                first_period = shift["periods"][0]
                cursor.execute(
                    "INSERT INTO omagmes.ShiftScheduleShift "
                    "(ShiftScheduleVersionID, ShiftID, ShiftName, ShiftCode, StartTime, EndTime, DisplayOrder, IsActive) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (version_id, shift["id"], shift["shift_name"], shift["shift_code"], first_period["start_time"],
                     first_period["end_time"], shift["display_order"], shift["active"]),
                )
                for period in shift["periods"]:
                    cursor.execute(
                        "INSERT INTO omagmes.ShiftScheduleShiftPeriod "
                        "(ShiftScheduleVersionID, ShiftID, PeriodOrder, StartTime, EndTime, IsActive) VALUES (?, ?, ?, ?, ?, ?)",
                        (version_id, shift["id"], period["display_order"], period["start_time"], period["end_time"], period["active"]),
                    )
            changed_by = f"INTERNAL DEVELOPMENT · {getpass.getuser()}"
            new_shifts = {int(item["id"]): item for item in normalized}
            for shift_id in sorted(set(old_shifts) | set(new_shifts)):
                old = old_shifts.get(shift_id)
                new = new_shifts.get(shift_id)
                old_identity = {key: old[key] for key in ("shift_name", "shift_code", "display_order", "active")} if old else None
                new_identity = {key: new[key] for key in ("shift_name", "shift_code", "display_order", "active")} if new else None
                if old_identity != new_identity:
                    self._insert_history(
                        cursor, configuration_type="SHIFT", identity=f"SHIFT:{shift_id}", version_id=version_id,
                        old_value=old_identity, new_value=new_identity, changed_by=changed_by,
                        effective_from=effective_from, reason=reason,
                    )
                old_periods = {int(item["display_order"]): item for item in (old["periods"] if old else [])}
                new_periods = {int(item["display_order"]): item for item in (new["periods"] if new else [])}
                for period_order in sorted(set(old_periods) | set(new_periods)):
                    old_period = old_periods.get(period_order)
                    new_period = new_periods.get(period_order)
                    if old_period != new_period:
                        self._insert_history(
                            cursor, configuration_type="SHIFT_PERIOD",
                            identity=f"SHIFT:{shift_id}:PERIOD:{period_order}", version_id=version_id,
                            old_value=old_period, new_value=new_period, changed_by=changed_by,
                            effective_from=effective_from, reason=reason,
                        )
            return {
                "id": version_id, "effective_from": effective_from, "created_at": "DATABASE UTC",
                "created_by": changed_by, "change_reason": reason,
                "shifts": normalized,
            }

    @staticmethod
    def validate_schedule_date(versions: list[dict[str, Any]], production_date: str) -> None:
        resolve_schedule_context(versions, production_date)
