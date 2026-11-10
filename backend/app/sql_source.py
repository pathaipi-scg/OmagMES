from __future__ import annotations

import os
import re
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterator, Sequence
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env", override=False)
EXPECTED_SERVER = "10.28.255.98"
EXPECTED_DATABASE = "OMAG"
MAX_QUERY_ROWS = 5_000
MAX_WINDOW_DAYS = 31
COUNTER_TAG = re.compile(r"^MODBUS\.WET_REJECT\.cntR[0-9]+$")


class SourceUnavailable(RuntimeError):
    """Safe-to-display source error that never contains credentials or SQL text."""


@dataclass(frozen=True)
class SQLSourceSettings:
    mode: str
    server: str
    database: str
    driver: str
    username: str
    password: str
    encrypt: bool
    trust_server_certificate: bool
    target_confirmed: bool
    select_only_confirmed: bool
    connect_timeout: int
    query_timeout: int
    camera_id_column: str
    camera_timestamp_column: str
    camera_quality_column: str
    camera_duplicate_column: str
    camera_quality_values: tuple[str, ...]
    camera_duplicate_clear_values: tuple[str, ...]
    camera_metadata_reviewed: bool
    historian_metadata_reviewed: bool
    camera_boundary_policy_confirmed: bool
    source_timezone: str
    source_timezone_confirmed: bool
    valid_plc_quality_codes: tuple[int, ...]
    max_counter_gap_minutes: int | None
    lot_window_source_confirmed: bool

    @classmethod
    def from_environment(cls) -> "SQLSourceSettings":
        def flag(name: str) -> bool:
            return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}

        def csv(name: str) -> tuple[str, ...]:
            return tuple(value.strip() for value in os.getenv(name, "").split(",") if value.strip())

        def optional_positive_int(name: str) -> int | None:
            raw = os.getenv(name, "").strip()
            if not raw:
                return None
            try:
                value = int(raw)
            except ValueError:
                return None
            return value if value > 0 else None

        try:
            quality_codes = tuple(int(value) for value in csv("OMAGMES_VALID_PLC_QUALITY_CODES"))
        except ValueError:
            quality_codes = ()

        return cls(
            mode=os.getenv("OMAGMES_SOURCE_MODE", "MOCK").strip().upper(),
            server=os.getenv("SQL_SERVER", "").strip(),
            database=os.getenv("SQL_DB", "").strip(),
            driver=os.getenv("SQL_DRIVER", "").strip(),
            username=os.getenv("SQL_USER", "").strip(),
            password=os.getenv("SQL_PASS", ""),
            encrypt=flag("SQL_ENCRYPT"),
            trust_server_certificate=flag("SQL_TRUST_SERVER_CERTIFICATE"),
            target_confirmed=flag("OMAGMES_SQL_TARGET_CONFIRMED"),
            select_only_confirmed=flag("OMAGMES_SQL_SELECT_ONLY_CONFIRMED"),
            connect_timeout=optional_positive_int("OMAGMES_SQL_CONNECT_TIMEOUT_SECONDS") or 5,
            query_timeout=optional_positive_int("OMAGMES_SQL_QUERY_TIMEOUT_SECONDS") or 10,
            camera_id_column=os.getenv("OMAGMES_CAMERA_ID_COLUMN", "").strip(),
            camera_timestamp_column=os.getenv("OMAGMES_CAMERA_TIMESTAMP_COLUMN", "").strip(),
            camera_quality_column=os.getenv("OMAGMES_CAMERA_QUALITY_COLUMN", "").strip(),
            camera_duplicate_column=os.getenv("OMAGMES_CAMERA_DUPLICATE_COLUMN", "").strip(),
            camera_quality_values=csv("OMAGMES_CAMERA_QUALITY_VALUES"),
            camera_duplicate_clear_values=csv("OMAGMES_CAMERA_DUPLICATE_CLEAR_VALUES"),
            camera_metadata_reviewed=flag("OMAGMES_CAMERA_METADATA_REVIEWED"),
            historian_metadata_reviewed=flag("OMAGMES_HISTORIAN_METADATA_REVIEWED"),
            camera_boundary_policy_confirmed=flag("OMAGMES_CAMERA_BOUNDARY_POLICY_CONFIRMED"),
            source_timezone=os.getenv("OMAGMES_SOURCE_TIMEZONE", "").strip(),
            source_timezone_confirmed=flag("OMAGMES_SOURCE_TIMEZONE_CONFIRMED"),
            valid_plc_quality_codes=quality_codes,
            max_counter_gap_minutes=optional_positive_int("OMAGMES_MAX_COUNTER_GAP_MINUTES"),
            lot_window_source_confirmed=flag("OMAGMES_LOT_WINDOW_SOURCE_CONFIRMED"),
        )

    @property
    def live_requested(self) -> bool:
        return self.mode == "LIVE_READ_ONLY"

    @property
    def safe_mode_name(self) -> str:
        return "LIVE READ-ONLY" if self.live_requested else ("MOCK" if self.mode == "MOCK" else "UNKNOWN")

    def live_gate_errors(self) -> list[str]:
        errors: list[str] = []
        if self.mode != "LIVE_READ_ONLY":
            errors.append("Live read-only source mode is not enabled.")
            return errors
        if not self.target_confirmed:
            errors.append("Owner confirmation of the exact SQL Server instance and OMAG database is required.")
        if not self.select_only_confirmed:
            errors.append("DBA confirmation of SELECT-only source permissions is required.")
        if not re.fullmatch(r"10\.28\.255\.98(?:\\[A-Za-z0-9_.-]+)?(?:,\d{1,5})?", self.server):
            errors.append(f"Configured SQL server must match the approved host {EXPECTED_SERVER}.")
        if self.database.casefold() != EXPECTED_DATABASE.casefold():
            errors.append("Configured database must be OMAG.")
        if not self.username or not self.password:
            errors.append("SQL credentials are not configured in the local environment.")
        if not self.driver:
            errors.append("SQL_DRIVER is not configured.")
        return errors


ConnectFactory = Callable[..., Any]


class SQLServerReadOnlyRepository:
    """Bounded SELECT-only access to the three approved legacy source tables."""

    def __init__(
        self,
        settings: SQLSourceSettings | None = None,
        connect_factory: ConnectFactory | None = None,
    ) -> None:
        self.settings = settings or SQLSourceSettings.from_environment()
        self._connect_factory = connect_factory

    def _connection_string(self) -> str:
        settings = self.settings
        driver = settings.driver
        if driver.upper() == "AUTO":
            import pyodbc

            installed = pyodbc.drivers()
            driver = next(
                (name for name in ("ODBC Driver 17 for SQL Server", "ODBC Driver 18 for SQL Server") if name in installed),
                "",
            )
        if not driver:
            raise SourceUnavailable("No supported SQL Server ODBC driver is installed or configured.")

        def brace(value: str) -> str:
            return "{" + value.replace("}", "}}") + "}"

        return (
            f"DRIVER={brace(driver)};SERVER={settings.server};DATABASE={settings.database};"
            f"UID={brace(settings.username)};PWD={brace(settings.password)};"
            f"Encrypt={'yes' if settings.encrypt else 'no'};"
            f"TrustServerCertificate={'yes' if settings.trust_server_certificate else 'no'};"
            "ApplicationIntent=ReadOnly;"
        )

    @contextmanager
    def _connection(self) -> Iterator[Any]:
        errors = self.settings.live_gate_errors()
        if errors:
            raise SourceUnavailable(" ".join(errors))
        try:
            if self._connect_factory is None:
                import pyodbc

                connection = pyodbc.connect(
                    self._connection_string(),
                    timeout=self.settings.connect_timeout,
                    autocommit=True,
                )
            else:
                connection = self._connect_factory(
                    self._connection_string(),
                    timeout=self.settings.connect_timeout,
                    autocommit=True,
                )
        except SourceUnavailable:
            raise
        except Exception as exc:
            raise SourceUnavailable(f"SQL source connection failed ({type(exc).__name__}).") from None
        try:
            self._verify_connection(connection)
        except SourceUnavailable:
            connection.close()
            raise
        except Exception as exc:
            connection.close()
            raise SourceUnavailable(f"SQL source preflight failed ({type(exc).__name__}).") from None
        try:
            yield connection
        finally:
            connection.close()

    def _verify_connection(self, connection: Any) -> dict[str, Any]:
        connection.timeout = self.settings.query_timeout
        cursor = connection.cursor()
        cursor.execute(
            """SELECT @@SERVERNAME AS server_name,
                      DB_NAME() AS database_name,
                      CAST(SERVERPROPERTY('InstanceName') AS nvarchar(128)) AS instance_name"""
        )
        row = cursor.fetchone()
        if row is None:
            raise SourceUnavailable("SQL target identity could not be verified.")
        server_name, database_name, instance_name = row[0], row[1], row[2]
        if str(database_name).casefold() != EXPECTED_DATABASE.casefold():
            raise SourceUnavailable("Connected database is not the approved OMAG database.")
        configured_instance = self.settings.server.partition("\\")[2].split(",", 1)[0] or None
        actual_instance = str(instance_name) if instance_name is not None else None
        if configured_instance != actual_instance:
            raise SourceUnavailable("Connected SQL Server instance does not match the confirmed instance in SQL_SERVER.")

        object_names = ("dbo.PRESS", "dbo.REJECT_WET", "dbo.product_count")
        permission_sql = "SELECT " + ", ".join(
            f"HAS_PERMS_BY_NAME(?, 'OBJECT', '{permission}')"
            for permission in ("SELECT", "INSERT", "UPDATE", "DELETE", "ALTER", "CONTROL")
        )
        for object_name in object_names:
            cursor.execute(permission_sql, (object_name,) * 6)
            permissions = cursor.fetchone()
            if permissions is None or permissions[0] != 1 or any(value == 1 for value in permissions[1:]):
                raise SourceUnavailable("The SQL login does not have verified SELECT-only access to all required source tables.")
            if any(value is None for value in permissions):
                raise SourceUnavailable("SQL permissions for a required source table could not be verified.")

        return {
            "server": str(server_name or ""),
            "instance": str(instance_name) if instance_name is not None else None,
            "database": str(database_name),
            "read_only_permissions_verified": True,
        }

    def health(self) -> dict[str, Any]:
        if not self.settings.live_requested:
            return {
                "mode": self.settings.safe_mode_name,
                "connected": False,
                "server": None,
                "instance": None,
                "database": None,
                "read_only_permissions_verified": False,
                "error": "Live read-only source mode is not enabled.",
            }
        try:
            with self._connection() as connection:
                cursor = self._cursor(connection)
                cursor.execute("SELECT @@SERVERNAME, DB_NAME(), CAST(SERVERPROPERTY('InstanceName') AS nvarchar(128))")
                row = cursor.fetchone()
                identity = {
                    "server": str(row[0] or ""),
                    "instance": str(row[2]) if row[2] is not None else None,
                    "database": str(row[1]),
                    "read_only_permissions_verified": True,
                }
            return {"mode": self.settings.safe_mode_name, "connected": True, **identity, "error": None}
        except SourceUnavailable as exc:
            return {
                "mode": self.settings.safe_mode_name,
                "connected": False,
                "server": None,
                "instance": None,
                "database": None,
                "read_only_permissions_verified": False,
                "error": str(exc),
            }
        except Exception as exc:
            return {
                "mode": self.settings.safe_mode_name,
                "connected": False,
                "server": None,
                "instance": None,
                "database": None,
                "read_only_permissions_verified": False,
                "error": f"SQL source preflight failed ({type(exc).__name__}).",
            }

    def _cursor(self, connection: Any) -> Any:
        connection.timeout = self.settings.query_timeout
        cursor = connection.cursor()
        return cursor

    def _table_columns(self, connection: Any, table_name: str) -> list[str]:
        cursor = self._cursor(connection)
        cursor.execute(
            "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = ? AND TABLE_NAME = ? ORDER BY ORDINAL_POSITION",
            ("dbo", table_name),
        )
        return [str(row[0]) for row in cursor.fetchall()]

    def historian_metadata(self, table_name: str) -> list[str]:
        if table_name not in {"PRESS", "REJECT_WET", "product_count"}:
            raise ValueError("Only the approved read-only source table names are supported.")
        with self._connection() as connection:
            return self._table_columns(connection, table_name)

    @staticmethod
    def _row_dict(cursor: Any, row: Any) -> dict[str, Any]:
        names = [column[0] for column in cursor.description]
        result = dict(zip(names, row))
        for key, value in tuple(result.items()):
            if isinstance(value, datetime):
                result[key] = value.isoformat()
            elif hasattr(value, "item"):
                try:
                    result[key] = value.item()
                except (ValueError, TypeError):
                    pass
        return result

    @staticmethod
    def _validate_range(start_at: datetime, end_at: datetime, limit: int) -> None:
        if start_at.tzinfo is None or end_at.tzinfo is None:
            raise ValueError("Time bounds must include a timezone.")
        if start_at >= end_at:
            raise ValueError("start_at must be earlier than end_at.")
        if (end_at - start_at).total_seconds() > MAX_WINDOW_DAYS * 86_400:
            raise ValueError(f"Time range cannot exceed {MAX_WINDOW_DAYS} days.")
        if not 1 <= limit <= MAX_QUERY_ROWS:
            raise ValueError(f"limit must be between 1 and {MAX_QUERY_ROWS}.")

    def _source_naive_timestamp(self, value: datetime) -> datetime:
        if not self.settings.source_timezone_confirmed or not self.settings.source_timezone:
            raise SourceUnavailable("Source timestamp timezone is not verified; bounded production queries are disabled.")
        try:
            zone = ZoneInfo(self.settings.source_timezone)
        except ZoneInfoNotFoundError:
            raise SourceUnavailable("Configured source timezone is unavailable.") from None
        return value.astimezone(zone).replace(tzinfo=None)

    def _fetch_press(self, table: str, tag_filter_sql: str, params: Sequence[Any], order: str, limit: int) -> list[dict[str, Any]]:
        table_name = table.rsplit(".", 1)[-1]
        sql = (
            f"SELECT TOP (?) id, _NAME, _VALUE, _TIMESTAMP, _QUALITY FROM {table} "
            f"WHERE {tag_filter_sql} ORDER BY _TIMESTAMP {order}, id {order}"
        )
        with self._connection() as connection:
            columns = set(self._table_columns(connection, table_name))
            required = {"id", "_NAME", "_VALUE", "_TIMESTAMP", "_QUALITY"}
            if not required.issubset(columns):
                raise SourceUnavailable(f"dbo.{table_name} does not expose the reviewed historian columns.")
            if not self.settings.historian_metadata_reviewed:
                raise SourceUnavailable("PRESS/REJECT_WET metadata has not been reviewed; historian row queries are disabled.")
            cursor = self._cursor(connection)
            cursor.execute(sql, (limit, *params))
            return [self._row_dict(cursor, row) for row in cursor.fetchall()]

    def latest_wet_status(self) -> dict[str, Any]:
        rows = self._fetch_press(
            "dbo.PRESS", "_NAME = ?", ("OPC.OMAG.OMAG.PRESS.AutoRun",), "DESC", 1
        )
        row = rows[0] if rows else None
        value = row.get("_VALUE") if row else None
        try:
            quality = int(row.get("_QUALITY")) if row else None
            numeric_value = int(value)
            valid = quality in self.settings.valid_plc_quality_codes and value == numeric_value and numeric_value in (0, 1)
        except (TypeError, ValueError, OverflowError):
            valid = False
            numeric_value = None
        status = "RUNNING" if valid and numeric_value == 1 else "STOPPED" if valid and numeric_value == 0 else "UNKNOWN"
        warning = None if valid else "AutoRun value/quality is not verified; status is UNKNOWN."
        return {"status": status, "observation": row, "warning": warning}

    def latest_press_counter(self) -> dict[str, Any] | None:
        rows = self._fetch_press(
            "dbo.PRESS", "_NAME = ?", ("OPC.OMAG.OMAG.PRESS.ProductCnt",), "DESC", 1
        )
        return rows[0] if rows else None

    def press_observations(self, start_at: datetime, end_at: datetime, limit: int) -> list[dict[str, Any]]:
        self._validate_range(start_at, end_at, limit)
        return self._fetch_press(
            "dbo.PRESS",
            "_NAME = ? AND _TIMESTAMP >= ? AND _TIMESTAMP < ?",
            ("OPC.OMAG.OMAG.PRESS.ProductCnt", self._source_naive_timestamp(start_at), self._source_naive_timestamp(end_at)),
            "ASC",
            limit,
        )

    def wet_reject_observations(self, start_at: datetime, end_at: datetime, limit: int) -> list[dict[str, Any]]:
        self._validate_range(start_at, end_at, limit)
        rows = self._fetch_press(
            "dbo.REJECT_WET",
            "_NAME LIKE ? AND _TIMESTAMP >= ? AND _TIMESTAMP < ?",
            ("MODBUS.WET_REJECT.cntR%", self._source_naive_timestamp(start_at), self._source_naive_timestamp(end_at)),
            "ASC",
            limit,
        )
        return [row for row in rows if isinstance(row.get("_NAME"), str) and COUNTER_TAG.fullmatch(row["_NAME"])]

    def wet_reject_counters(self, start_at: datetime, end_at: datetime, limit: int) -> list[str]:
        names = {row["_NAME"] for row in self.wet_reject_observations(start_at, end_at, limit)}
        return sorted(names, key=lambda tag: int(tag.rsplit("cntR", 1)[1]))

    def latest_wet_reject_counters(self, start_at: datetime, end_at: datetime, limit: int) -> list[dict[str, Any]]:
        self._validate_range(start_at, end_at, limit)
        observations = self._fetch_press(
            "dbo.REJECT_WET",
            "_NAME LIKE ? AND _TIMESTAMP >= ? AND _TIMESTAMP < ?",
            ("MODBUS.WET_REJECT.cntR%", self._source_naive_timestamp(start_at), self._source_naive_timestamp(end_at)),
            "DESC",
            limit,
        )
        observations = [row for row in observations if isinstance(row.get("_NAME"), str) and COUNTER_TAG.fullmatch(row["_NAME"])]
        latest: dict[str, dict[str, Any]] = {}
        for row in observations:
            tag = row["_NAME"]
            previous = latest.get(tag)
            if previous is None or (row.get("_TIMESTAMP"), row.get("id")) > (previous.get("_TIMESTAMP"), previous.get("id")):
                latest[tag] = row
        return [latest[tag] for tag in sorted(latest, key=lambda value: int(value.rsplit("cntR", 1)[1]))]

    def camera_metadata(self) -> list[str]:
        with self._connection() as connection:
            return self._table_columns(connection, "product_count")

    def wet_camera_observations(self, start_at: datetime, end_at: datetime, limit: int) -> list[dict[str, Any]]:
        self._validate_range(start_at, end_at, limit)
        settings = self.settings
        if not settings.camera_metadata_reviewed:
            raise SourceUnavailable("product_count metadata has not been reviewed and mapped.")
        mappings = (
            settings.camera_id_column,
            settings.camera_timestamp_column,
            settings.camera_quality_column,
            settings.camera_duplicate_column,
        )
        if any(not value for value in mappings):
            raise SourceUnavailable("Camera record ID, timestamp, quality, and duplicate columns must be explicitly mapped after metadata review.")
        columns = self.camera_metadata()
        if any(value not in columns for value in mappings) or not {"line", "value_cnt"}.issubset(columns):
            raise SourceUnavailable("Configured camera metadata mapping does not match dbo.product_count.")

        def identifier(value: str) -> str:
            return "[" + value.replace("]", "]]" ) + "]"

        selected = [*mappings, "line", "value_cnt"]
        projection = ", ".join(identifier(column) for column in selected)
        timestamp_column = identifier(settings.camera_timestamp_column)
        sql = (
            f"SELECT TOP (?) {projection} FROM dbo.product_count "
            f"WHERE [line] = ? AND {timestamp_column} >= ? AND {timestamp_column} < ? "
            f"ORDER BY {timestamp_column} ASC, {identifier(settings.camera_id_column)} ASC"
        )
        with self._connection() as connection:
            cursor = self._cursor(connection)
            cursor.execute(sql, (limit, "wet", self._source_naive_timestamp(start_at), self._source_naive_timestamp(end_at)))
            rows = [self._row_dict(cursor, row) for row in cursor.fetchall()]

        return [
            {
                "source_id": row[settings.camera_id_column],
                "timestamp": row[settings.camera_timestamp_column],
                "quality": row[settings.camera_quality_column],
                "duplicate": row[settings.camera_duplicate_column],
                "line": row["line"],
                "value_cnt": row["value_cnt"],
            }
            for row in rows
        ]


repository = SQLServerReadOnlyRepository()
