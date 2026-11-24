from __future__ import annotations

import os
import re
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Iterator, Sequence
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dotenv import load_dotenv

from .production_plans import PLAN_VIEW_COLUMNS, aggregate_plan_rows

PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env", override=False)
EXPECTED_SERVER = "10.28.255.98"
EXPECTED_SERVER_NAME = "SCGLS-NK\\SQLEXPRESS"
EXPECTED_DATABASE = "OMAG"
EXPECTED_INSTANCE = "SQLEXPRESS"
EXPECTED_SQL_LOGIN = "OMAG_MES"
MAX_QUERY_ROWS = 5_000
MAX_WINDOW_DAYS = 31
COUNTER_TAG = re.compile(r"^MODBUS\.WET_REJECT\.cntR[0-9]+$")
DROP_COUNTER_TAG = "OMAG.PRESS.OEE.DropCnt"
SOURCE_PERMISSION_TABLES = ("dbo.PRESS", "dbo.REJECT_WET", "dbo.product_count")


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
        if not re.fullmatch(r"(?:127\.0\.0\.1|localhost|10\.28\.255\.98)(?:\\[A-Za-z0-9_.-]+)?(?:,\d{1,5})?", self.server, re.IGNORECASE):
            errors.append("Configured SQL server must use the approved local endpoint or OMAG SQL host.")
        if self.database.casefold() != EXPECTED_DATABASE.casefold():
            errors.append("Configured database must be OMAG.")
        if not self.username or not self.password:
            errors.append("SQL credentials are not configured in the local environment.")
        elif self.username.casefold() != EXPECTED_SQL_LOGIN.casefold():
            errors.append(f"SQL source must use the dedicated {EXPECTED_SQL_LOGIN} login; fallback identities are refused.")
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
        self._last_preflight: dict[str, Any] | None = None

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
    def _connection(self, permission_tables: Sequence[str] = SOURCE_PERMISSION_TABLES) -> Iterator[Any]:
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
            self._last_preflight = self._verify_connection(connection, permission_tables)
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

    def _verify_connection(
        self,
        connection: Any,
        permission_tables: Sequence[str] = SOURCE_PERMISSION_TABLES,
    ) -> dict[str, Any]:
        connection.timeout = self.settings.query_timeout
        cursor = connection.cursor()
        self._execute_select(
            cursor,
            """SELECT ORIGINAL_LOGIN() AS original_login,
                      SUSER_SNAME() AS sql_login,
                      @@SERVERNAME AS server_name,
                      DB_NAME() AS database_name,
                      CAST(SERVERPROPERTY('InstanceName') AS nvarchar(128)) AS instance_name,
                      USER_NAME() AS database_user,
                      IS_SRVROLEMEMBER('sysadmin') AS is_sysadmin""",
        )
        row = cursor.fetchone()
        if row is None:
            raise SourceUnavailable("SQL target identity could not be verified.")
        original_login, sql_login, server_name, database_name, instance_name = row[0], row[1], row[2], row[3], row[4]
        if str(original_login or "").casefold() != EXPECTED_SQL_LOGIN.casefold() or str(sql_login or "").casefold() != EXPECTED_SQL_LOGIN.casefold():
            raise SourceUnavailable(f"Connected SQL identity must be {EXPECTED_SQL_LOGIN}; fallback identities are refused.")
        if str(database_name).casefold() != EXPECTED_DATABASE.casefold():
            raise SourceUnavailable("Connected database is not the approved OMAG database.")
        if str(server_name or "").casefold() != EXPECTED_SERVER_NAME.casefold():
            raise SourceUnavailable("Connected SQL Server name does not match the owner-confirmed OMAG server.")
        configured_instance = self.settings.server.partition("\\")[2].split(",", 1)[0] or None
        actual_instance = str(instance_name) if instance_name is not None else None
        if actual_instance != EXPECTED_INSTANCE or (configured_instance and configured_instance.casefold() != actual_instance.casefold()):
            raise SourceUnavailable("Connected SQL Server instance does not match the confirmed instance in SQL_SERVER.")

        permission_sql = "SELECT " + ", ".join(
            f"HAS_PERMS_BY_NAME(?, 'OBJECT', '{permission}')"
            for permission in ("SELECT", "INSERT", "UPDATE", "DELETE", "ALTER", "CONTROL")
        )
        permission_results: dict[str, dict[str, bool]] = {}
        write_capabilities = ("INSERT", "UPDATE", "DELETE", "ALTER", "CONTROL")
        for object_name in permission_tables:
            self._execute_select(cursor, permission_sql, (object_name,) * 6)
            permissions = cursor.fetchone()
            if permissions is None or any(value is None for value in permissions):
                raise SourceUnavailable("SQL permissions for a required source table could not be verified.")
            if permissions[0] != 1:
                raise SourceUnavailable(f"The SQL login does not have SELECT permission on {object_name}.")
            permission_results[object_name] = {
                permission: value == 1
                for permission, value in zip(("SELECT", *write_capabilities), permissions)
            }

        writes_present = sorted({
            permission
            for permissions in permission_results.values()
            for permission in write_capabilities
            if permissions[permission]
        })

        return {
            "server": str(server_name or ""),
            "instance": str(instance_name) if instance_name is not None else None,
            "database": str(database_name),
            "original_login": str(original_login or ""),
            "sql_login": str(sql_login or ""),
            "database_user": str(row[5] or ""),
            "sysadmin_member": row[6] == 1,
            "permission_checks": permission_results,
            "select_access_verified": True,
            "read_only_permissions_verified": not writes_present and row[5] != 1,
            "write_capabilities_present": writes_present,
            "source_queries_select_only_enforced": True,
        }

    @staticmethod
    def _execute_select(cursor: Any, sql: str, params: Sequence[Any] = ()) -> Any:
        """Execute a SELECT statement only; source-repository DML is forbidden in code."""
        executable_sql = re.sub(r"'(?:''|[^'])*'|\"(?:\"\"|[^\"])*\"|--[^\r\n]*|/\*.*?\*/", " ", sql, flags=re.DOTALL)
        forbidden = re.compile(r"\b(?:INSERT|UPDATE|DELETE|MERGE|ALTER|DROP|TRUNCATE|EXEC(?:UTE)?|CREATE)\b", re.IGNORECASE)
        if not executable_sql.lstrip().upper().startswith("SELECT") or ";" in executable_sql or forbidden.search(executable_sql):
            raise SourceUnavailable("Source repository permits SELECT statements only.")
        return cursor.execute(sql, tuple(params))

    def health(self) -> dict[str, Any]:
        if not self.settings.live_requested:
            return {
                "mode": self.settings.safe_mode_name,
                "connected": False,
                "server": None,
                "instance": None,
                "database": None,
                "read_only_permissions_verified": False,
                "select_access_verified": False,
                "source_queries_select_only_enforced": True,
                "error": "Live read-only source mode is not enabled.",
            }
        try:
            with self._connection(permission_tables=("dbo.PRESS",)) as connection:
                identity = dict(self._last_preflight or {})
            return {"mode": self.settings.safe_mode_name, "connected": True, **identity, "error": None}
        except SourceUnavailable as exc:
            return {
                "mode": self.settings.safe_mode_name,
                "connected": False,
                "server": None,
                "instance": None,
                "database": None,
                "read_only_permissions_verified": False,
                "select_access_verified": False,
                "source_queries_select_only_enforced": True,
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
                "select_access_verified": False,
                "source_queries_select_only_enforced": True,
                "error": f"SQL source preflight failed ({type(exc).__name__}).",
            }

    def _cursor(self, connection: Any) -> Any:
        connection.timeout = self.settings.query_timeout
        cursor = connection.cursor()
        return cursor

    def _table_columns(self, connection: Any, table_name: str) -> list[str]:
        cursor = self._cursor(connection)
        self._execute_select(
            cursor,
            "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = ? AND TABLE_NAME = ? ORDER BY ORDINAL_POSITION",
            ("dbo", table_name),
        )
        return [str(row[0]) for row in cursor.fetchall()]

    def historian_metadata(self, table_name: str) -> list[str]:
        if table_name not in {"PRESS", "REJECT_WET", "product_count"}:
            raise ValueError("Only the approved read-only source table names are supported.")
        with self._connection(permission_tables=(f"dbo.{table_name}",)) as connection:
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

    def _source_naive_timestamp(self, value: datetime, *, require_confirmation: bool = True) -> datetime:
        if not self.settings.source_timezone or (require_confirmation and not self.settings.source_timezone_confirmed):
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
        with self._connection(permission_tables=(f"dbo.{table_name}",)) as connection:
            columns = set(self._table_columns(connection, table_name))
            required = {"id", "_NAME", "_VALUE", "_TIMESTAMP", "_QUALITY"}
            if not required.issubset(columns):
                raise SourceUnavailable(f"dbo.{table_name} does not expose the reviewed historian columns.")
            if not self.settings.historian_metadata_reviewed:
                raise SourceUnavailable("PRESS/REJECT_WET metadata has not been reviewed; historian row queries are disabled.")
            cursor = self._cursor(connection)
            self._execute_select(cursor, sql, (limit, *params))
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

    def dropcnt_observations(self, start_at: datetime, end_at: datetime, limit: int) -> list[dict[str, Any]]:
        """Read only the exact DropCnt historian tag for one bounded time window."""
        self._validate_range(start_at, end_at, limit)
        return self._fetch_press(
            "dbo.PRESS",
            "_NAME = ? AND _TIMESTAMP >= ? AND _TIMESTAMP < ?",
            (DROP_COUNTER_TAG, self._source_naive_timestamp(start_at, require_confirmation=False), self._source_naive_timestamp(end_at, require_confirmation=False)),
            "ASC",
            limit,
        )

    def press_activity_observations(self, start_at: datetime, end_at: datetime, limit: int = MAX_QUERY_ROWS) -> dict[str, Any]:
        """Read both reviewed production activity tags for one complete bounded day.

        Results use source event order (_TIMESTAMP,id) and include _NUMERICID
        and _QUALITY for audit/review. Unconfirmed historian timestamps are
        compared as raw SQL wall-clock values; no timezone conversion is guessed.
        """
        self._validate_range(start_at, end_at, limit)
        columns = set(self.historian_metadata("PRESS"))
        required = {"id", "_NAME", "_NUMERICID", "_VALUE", "_TIMESTAMP", "_QUALITY"}
        if not required.issubset(columns):
            missing = sorted(required - columns)
            raise SourceUnavailable("dbo.PRESS does not expose the reviewed activity columns: " + ", ".join(missing) + ".")
        if not self.settings.historian_metadata_reviewed:
            raise SourceUnavailable("PRESS metadata has not been reviewed; historian row queries are disabled.")
        if self.settings.source_timezone_confirmed:
            start_value = self._source_naive_timestamp(start_at)
            end_value = self._source_naive_timestamp(end_at)
            timestamp_basis = self.settings.source_timezone
        else:
            start_value = start_at.replace(tzinfo=None)
            end_value = end_at.replace(tzinfo=None)
            timestamp_basis = "RAW SQL WALL CLOCK · UNVERIFIED"
        sql = (
            "SELECT TOP (?) [id],[_NAME],[_NUMERICID],[_VALUE],[_TIMESTAMP],[_QUALITY] "
            "FROM dbo.PRESS WHERE [_NAME] IN (?,?) AND [_TIMESTAMP]>=? AND [_TIMESTAMP]<? "
            "ORDER BY [_TIMESTAMP] ASC,[id] ASC"
        )
        with self._connection(permission_tables=("dbo.PRESS",)) as connection:
            cursor = self._cursor(connection)
            self._execute_select(cursor, sql, (limit + 1, "OMAG.PRESS.OEE.DropCnt", "OMAG.PRESS.OEE.AutoRun", start_value, end_value))
            rows = [self._row_dict(cursor, row) for row in cursor.fetchall()]
        truncated = len(rows) > limit
        return {
            "observations": rows[:limit], "truncated": truncated, "limit": limit,
            "timestamp_basis": timestamp_basis,
            "source": "OMAG.dbo.PRESS",
            "tags": [DROP_COUNTER_TAG, "OMAG.PRESS.OEE.AutoRun"],
            "order": ["_TIMESTAMP", "id"],
        }

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
        with self._connection(permission_tables=("dbo.product_count",)) as connection:
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
        with self._connection(permission_tables=("dbo.product_count",)) as connection:
            cursor = self._cursor(connection)
            self._execute_select(cursor, sql, (limit, "wet", self._source_naive_timestamp(start_at), self._source_naive_timestamp(end_at)))
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

    def production_plan_snapshots(self, limit: int = 1000, production_date: str | None = None) -> dict[str, Any]:
        """Read the existing production-plan view; never access its synonym directly."""
        if not 1 <= limit <= MAX_QUERY_ROWS:
            raise ValueError(f"limit must be between 1 and {MAX_QUERY_ROWS}.")
        start_date = None
        end_date = None
        if production_date is not None:
            try:
                start_date = date.fromisoformat(production_date)
            except ValueError:
                raise ValueError("production_date must use YYYY-MM-DD format.") from None
            if start_date.isoformat() != production_date:
                raise ValueError("production_date must use YYYY-MM-DD format.")
            end_date = start_date + timedelta(days=1)
        with self._connection(permission_tables=("dbo.vw_OmagPlan",)) as connection:
            columns = set(self._table_columns(connection, "vw_OmagPlan"))
            if not set(PLAN_VIEW_COLUMNS).issubset(columns):
                missing = sorted(set(PLAN_VIEW_COLUMNS) - columns)
                raise SourceUnavailable(f"dbo.vw_OmagPlan column metadata differs from the reviewed source contract; missing columns: {', '.join(missing)}.")
            cursor = self._cursor(connection)
            projection = ",".join(f"[{column}]" for column in PLAN_VIEW_COLUMNS)
            order = ",".join(f"[{column}]" for column in ("StartTime", "Company", "Plant", "Shift", "PlanWeek", "VersionNo", "PlanName", "Machine", "MaterialCode", "OperationCode"))
            date_filter = " AND [StartTime] >= ? AND [StartTime] < ?" if start_date is not None else ""
            params: tuple[Any, ...] = (limit + 1, "SCGLS", "OMAG", "3251")
            if start_date is not None and end_date is not None:
                params += (start_date, end_date)
            self._execute_select(
                cursor,
                f"SELECT TOP (?) {projection} FROM dbo.vw_OmagPlan "
                f"WHERE [Company] = ? AND [Machine] = ? AND [Plant] = ?{date_filter} ORDER BY {order}",
                params,
            )
            raw_rows = [self._row_dict(cursor, row) for row in cursor.fetchall()]
        truncated = len(raw_rows) > limit
        plans = aggregate_plan_rows(raw_rows[:limit])
        return {
            "source": "OMAG.dbo.vw_OmagPlan",
            "filters": {"Company": "SCGLS", "Machine": "OMAG", "Plant": "3251"},
            "production_date": production_date,
            "plans": plans,
            "truncated": truncated,
            "limit": limit,
            "identity_kind": "CONTENT_FINGERPRINT_NOT_SOURCE_ID",
            "warnings": [
                "The plan view exposes no durable row ID; identical rows cannot be distinguished and are not assignable.",
                "Planned StartTime is display/scheduling context only and is never copied into actual Lot boundaries.",
                "MaterialCode is matched exactly to ProductCode; it is never interpreted as a coating Color.",
            ],
        }

    def press_lot_auto(self, production_date: str, limit: int = MAX_QUERY_ROWS) -> dict[str, Any]:
        """Read the SQL-generated AutoLot business rows for one source ProdDate."""
        try:
            parsed_date = date.fromisoformat(production_date)
        except ValueError:
            raise ValueError("production_date must use YYYY-MM-DD format.") from None
        if parsed_date.isoformat() != production_date:
            raise ValueError("production_date must use YYYY-MM-DD format.")
        if not 1 <= limit <= MAX_QUERY_ROWS:
            raise ValueError(f"limit must be between 1 and {MAX_QUERY_ROWS}.")
        required = {
            "ProdDate", "ShiftType", "LotNo", "rw", "LotStart", "LotStop",
            "ShiftNo", "StartTime", "StopTime", "pDropCnt", "DropCnt",
        }
        with self._connection(permission_tables=("dbo.vw_PRESS_LotAuto",)) as connection:
            columns = set(self._table_columns(connection, "vw_PRESS_LotAuto"))
            if not required.issubset(columns):
                missing = sorted(required - columns)
                raise SourceUnavailable(
                    "dbo.vw_PRESS_LotAuto differs from the reviewed AutoLot contract; missing columns: "
                    + ", ".join(missing) + "."
                )
            cursor = self._cursor(connection)
            self._execute_select(
                cursor,
                "SELECT TOP (?) ProdDate,ShiftType,LotNo,rw,LotStart,LotStop,"
                "ShiftNo,StartTime,StopTime,pDropCnt,DropCnt "
                "FROM dbo.vw_PRESS_LotAuto WHERE ProdDate=? "
                "ORDER BY LotStart,LotNo,rw",
                (limit + 1, parsed_date),
            )
            rows = [self._row_dict(cursor, row) for row in cursor.fetchall()]
        if len(rows) > limit:
            raise SourceUnavailable(
                "vw_PRESS_LotAuto exceeded the bounded reconciliation row limit; no partial AutoLot reconciliation was performed."
            )
        return {
            "source": "OMAG.dbo.vw_PRESS_LotAuto",
            "production_date": production_date,
            "rows": rows,
            "truncated": False,
            "limit": limit,
            "identity_strategy": "Direct current dbo.vw_PRESS_LotAuto columns; LotNo, ShiftNo, and DropCnt are SQL-owned.",
        }

    def press_daily_diff_total(self, production_date: str) -> dict[str, Any]:
        """Sum the installed reset-aware SQL Diff view for one configured Production Date."""
        try:
            parsed_date = datetime.fromisoformat(production_date).date()
        except ValueError:
            raise ValueError("production_date must use YYYY-MM-DD format.") from None
        if parsed_date.isoformat() != production_date:
            raise ValueError("production_date must use YYYY-MM-DD format.")
        with self._connection(permission_tables=("omagmes.v_PressDailyDiff",)) as connection:
            cursor = self._cursor(connection)
            self._execute_select(
                cursor,
                "SELECT COALESCE(SUM(CONVERT(bigint,Diff)),0),COUNT_BIG(*) "
                "FROM omagmes.v_PressDailyDiff WHERE ProductionDate=? AND SourceTag=? AND Diff>=0",
                (parsed_date, DROP_COUNTER_TAG),
            )
            row = cursor.fetchone()
        if row is None:
            raise SourceUnavailable("Reset-aware Press Diff summary returned no result.")
        return {"production_date": production_date, "press_drops": int(row[0]), "sample_count": int(row[1]),
                "source": "OMAG.omagmes.v_PressDailyDiff", "counter_tag": DROP_COUNTER_TAG,
                "reset_aware": True}

    def auto_lot_detected_windows(self, production_date: str | None = None, limit: int = 1000) -> dict[str, Any]:
        """Read SQL-derived counter epochs as provisional proposals, not Lot facts."""
        if not 1 <= limit <= MAX_QUERY_ROWS:
            raise ValueError(f"limit must be between 1 and {MAX_QUERY_ROWS}.")
        sql = (
            "SELECT TOP (?) CandidateKey,SourceTag,CounterEpoch,FirstSourceID,ResetSourceID,ResetPreviousSourceID,ResetValue,ResetPreviousValue,"
            "ProposedStartTime,ProposedEndTime,BoundaryEvidence,BoundaryEarliestEvidenceAt,BoundaryLatestEvidenceAt,"
            "ProductionDate,CutoffVersionID,ShiftScheduleVersionID,ShiftID,RequiresOperatorConfirmation,IsProvisional,DetectionNote "
            "FROM omagmes.v_AutoLotDetectedWindow "
        )
        params: tuple[Any, ...] = (limit + 1,)
        if production_date is not None:
            parse_date = datetime.fromisoformat(production_date).date()
            if parse_date.isoformat() != production_date:
                raise ValueError("production_date must use YYYY-MM-DD format.")
            sql += "WHERE ProductionDate=? "
            params += (parse_date,)
        sql += "ORDER BY ProposedStartTime DESC,FirstSourceID DESC"
        with self._connection(permission_tables=("omagmes.v_AutoLotDetectedWindow",)) as connection:
            cursor = self._cursor(connection)
            self._execute_select(cursor, sql, params)
            rows = [self._row_dict(cursor, row) for row in cursor.fetchall()]
        truncated = len(rows) > limit
        return {
            "source": "OMAG.omagmes.v_AutoLotDetectedWindow",
            "rows": rows[:limit],
            "truncated": truncated,
            "limit": limit,
            "warning": "Counter epochs are provisional evidence. They do not prove Product/Color change, actual start/stop, or create official ProductionLots.",
        }

    def press_lot_summary(self, production_date: str | None = None, limit: int = MAX_QUERY_ROWS) -> list[dict[str, Any]]:
        """Read the shared SQL Lot summary view; never calculate Diff/ACC in Python."""
        if not 1 <= limit <= MAX_QUERY_ROWS:
            raise ValueError(f"limit must be between 1 and {MAX_QUERY_ROWS}.")
        sql = (
            "SELECT TOP (?) LotIdentityType,LotIdentityID,OfficialProductionLotID,CandidateWindowID,"
            "LotNumber,LotStatus,LotName,ProductID,ColorCode,StartTime,EndTime,"
            "OriginalProposedStartTime,OriginalProposedEndTime,CurrentProposedStartTime,CurrentProposedEndTime,OperatorTimeOverride,"
            "ProductionDate,ShiftID,"
            "CalculatedPressQty,LatestLotACC,LatestDiffAt,AmbiguousEventCount,BoundaryOverlapEventCount,QualityWarningCount,"
            "ResetEventCount,HasDataWarnings FROM omagmes.v_PressLotSummary "
        )
        params: tuple[Any, ...] = (limit + 1,)
        if production_date is not None:
            sql += "WHERE ProductionDate=? "
            params += (production_date,)
        sql += "ORDER BY StartTime DESC,LotIdentityType,LotIdentityID"
        with self._connection(permission_tables=("omagmes.v_PressLotSummary",)) as connection:
            cursor = self._cursor(connection)
            self._execute_select(cursor, sql, params)
            rows = [self._row_dict(cursor, row) for row in cursor.fetchall()]
        if len(rows) > limit:
            raise SourceUnavailable("SQL Lot summary exceeded the approved row limit; narrow the Production Date query.")
        return rows

    def press_lot_acc(self, start_at: datetime, end_at: datetime, limit: int = MAX_QUERY_ROWS) -> list[dict[str, Any]]:
        """Read SQL-calculated Lot Diff/ACC events for a bounded time interval."""
        self._validate_range(start_at, end_at, limit)
        sql = (
            "SELECT TOP (?) SourceID,RecTime,DiffProductionDate,QualityCode,PreviousSourceID,PreviousRecTime,"
            "CounterValue,PreviousCounterValue,ResetDetected,Unchanged,Diff,DiffStatus,LotIdentityType,"
            "LotIdentityID,ProductionLotID,CandidateWindowID,LotNumber,LotStatus,StartTime,EndTime,ProductID,"
            "ColorCode,AllocationStatus,IsAllocated,EligibleDiff,AllocatedDiff,UnallocatedOrAmbiguousDiff,LotACC "
            "FROM omagmes.v_PressLotACC WHERE RecTime>=? AND RecTime<? "
            "ORDER BY RecTime,SourceID"
        )
        params = (
            limit + 1,
            self._source_naive_timestamp(start_at, require_confirmation=False),
            self._source_naive_timestamp(end_at, require_confirmation=False),
        )
        with self._connection(permission_tables=("omagmes.v_PressLotACC",)) as connection:
            cursor = self._cursor(connection)
            self._execute_select(cursor, sql, params)
            rows = [self._row_dict(cursor, row) for row in cursor.fetchall()]
        if len(rows) > limit:
            raise SourceUnavailable("SQL Lot ACC query exceeded the approved row limit; narrow the time interval.")
        return rows


repository = SQLServerReadOnlyRepository()
