"""Opt-in SQL integration tests. Never target the production OMAG database.

Provision a disposable local SQL Server database named OMAGMES_TEST_* with the
reviewed OmagMES schema, an OMAG_MES login/user, object-scoped runtime grants, and
one isolated Lot whose LotName starts with IT-. Then set the OMAGMES_TEST_SQL_*
environment variables described in docs/sql-integration-tests.md.
"""
from __future__ import annotations

import os
import re
import uuid
from dataclasses import replace
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from backend.app import production_repository as repository_module
from backend.app.production_repository import SQLServerProductionRepository
from backend.app.daily_shift_configuration import initial_shift_periods
from backend.app.sql_source import SQLServerReadOnlyRepository, SQLSourceSettings, SourceUnavailable

BANGKOK = ZoneInfo("Asia/Bangkok")
_CONFIRMATION = "I_CONFIRM_ISOLATED_TEST_DATABASE"
_LOCAL_SQL_SERVER = re.compile(r"^(?:localhost|127\.0\.0\.1)(?:\\[A-Za-z0-9_.-]+)?(?:,\d{1,5})?$", re.IGNORECASE)


class _IsolatedTestSettings:
    """Test-only settings adapter; production application code never constructs this."""

    def __init__(self, base: SQLSourceSettings) -> None:
        self._base = base

    def __getattr__(self, name: str) -> Any:
        return getattr(self._base, name)

    def live_gate_errors(self) -> list[str]:
        if self.mode != "LIVE_READ_ONLY":
            return ["Test SQL mode must be LIVE_READ_ONLY."]
        if not self.database.startswith("OMAGMES_TEST_"):
            return ["Integration tests are restricted to OMAGMES_TEST_* databases."]
        if not _LOCAL_SQL_SERVER.fullmatch(self.server):
            return ["Integration tests may connect only to a local SQL Server endpoint."]
        if self.username != "OMAG_MES" or not self.password:
            return ["Integration tests require the dedicated OMAG_MES SQL login."]
        if not self.target_confirmed:
            return ["The isolated SQL test target has not been explicitly confirmed."]
        return []


def _test_target() -> tuple[_IsolatedTestSettings, int]:
    if os.getenv("OMAGMES_TEST_SQL_CONFIRMATION") != _CONFIRMATION:
        pytest.skip("Set OMAGMES_TEST_SQL_CONFIRMATION to opt into the isolated SQL integration database.")
    server = os.getenv("OMAGMES_TEST_SQL_SERVER", "").strip()
    database = os.getenv("OMAGMES_TEST_SQL_DATABASE", "").strip()
    driver = os.getenv("OMAGMES_TEST_SQL_DRIVER", "").strip()
    password = os.getenv("OMAGMES_TEST_SQL_PASSWORD", "")
    raw_lot_id = os.getenv("OMAGMES_TEST_LOT_ID", "").strip()
    if not all((server, database, driver, password, raw_lot_id)):
        pytest.fail("Explicit SQL integration opt-in requires server, database, driver, password, and test Lot ID environment variables.")
    if not database.startswith("OMAGMES_TEST_") or database.casefold() == "omag":
        pytest.fail("Refusing SQL integration tests unless the database name starts with OMAGMES_TEST_.")
    if not _LOCAL_SQL_SERVER.fullmatch(server):
        pytest.fail("Refusing SQL integration tests against non-local SQL Server endpoints.")
    try:
        lot_id = int(raw_lot_id)
    except ValueError:
        pytest.fail("OMAGMES_TEST_LOT_ID must be a positive integer.")
    if lot_id <= 0:
        pytest.fail("OMAGMES_TEST_LOT_ID must be a positive integer.")

    base = replace(
        SQLSourceSettings.from_environment(), mode="LIVE_READ_ONLY", server=server,
        database=database, driver=driver, username="OMAG_MES", password=password,
        target_confirmed=True, select_only_confirmed=True,
    )
    settings = _IsolatedTestSettings(base)
    assert settings.live_gate_errors() == []
    return settings, lot_id


def _connection_string(settings: _IsolatedTestSettings) -> str:
    return SQLServerReadOnlyRepository(settings)._connection_string().replace("ApplicationIntent=ReadOnly;", "")


def _open_isolated_connection(settings: _IsolatedTestSettings):
    import pyodbc

    return pyodbc.connect(
        _connection_string(settings),
        timeout=settings.connect_timeout,
        autocommit=False,
    )


def _connect_factory(connection_string: str, **kwargs: Any):
    import pyodbc

    return pyodbc.connect(connection_string, **kwargs)


@pytest.fixture(scope="module")
def sql_repo():
    settings, lot_id = _test_target()

    identity_connection = _open_isolated_connection(settings)
    try:
        identity_cursor = identity_connection.cursor()
        identity_cursor.execute(
            "SELECT ORIGINAL_LOGIN(), SUSER_SNAME(), DB_NAME(), @@SERVERNAME, "
            "CAST(SERVERPROPERTY('InstanceName') AS nvarchar(128)), IS_SRVROLEMEMBER('sysadmin')"
        )
        identity = identity_cursor.fetchone()
        if identity is None:
            pytest.fail("Isolated SQL Server identity could not be verified.")
        if str(identity[0]).casefold() != "omag_mes" or str(identity[1]).casefold() != "omag_mes":
            pytest.fail("Integration database connection did not use OMAG_MES.")
        if str(identity[2]) != settings.database or int(identity[5] or 0) != 0:
            pytest.fail("Integration target identity is not the confirmed non-sysadmin test database.")
        original_target = (
            repository_module.EXPECTED_DATABASE,
            repository_module.EXPECTED_SERVER_NAME,
            repository_module.EXPECTED_INSTANCE,
        )
        repository_module.EXPECTED_DATABASE = settings.database
        repository_module.EXPECTED_SERVER_NAME = str(identity[3])
        repository_module.EXPECTED_INSTANCE = str(identity[4])
        identity_cursor.execute(
            "SELECT l.id,l.LotName,l.ProductionDate,l.ShiftScheduleVersionID,l.ShiftID "
            "FROM omagmes.ProductionLot l WHERE l.id=?",
            (lot_id,),
        )
        lot = identity_cursor.fetchone()
        if lot is None or not str(lot[1]).startswith("IT-"):
            pytest.fail("The configured test Lot must exist and its LotName must start with IT-.")
        identity_cursor.execute(
            "SELECT COUNT_BIG(*) FROM sys.tables WHERE schema_id=SCHEMA_ID(N'omagmes') "
            "AND name IN (" + ",".join("?" for _ in repository_module.REQUIRED_PRODUCTION_TABLES) + ")",
            repository_module.REQUIRED_PRODUCTION_TABLES,
        )
        if int(identity_cursor.fetchone()[0]) != len(repository_module.REQUIRED_PRODUCTION_TABLES):
            pytest.fail("The isolated SQL database does not have all required 003/007 tables.")
    finally:
        identity_connection.close()

    repo = SQLServerProductionRepository(settings, _connect_factory)
    try:
        status = repo.health()
        if not status["schema_ready"]:
            pytest.fail(f"Isolated SQL database schema is incomplete: {status['missing_tables']}")
        yield repo, settings, lot_id, lot
    finally:
        (repository_module.EXPECTED_DATABASE,
         repository_module.EXPECTED_SERVER_NAME,
         repository_module.EXPECTED_INSTANCE) = original_target


def _write_repository(settings: _IsolatedTestSettings) -> SQLServerProductionRepository:
    return SQLServerProductionRepository(settings, _connect_factory)


def test_save_edit_delete_and_new_repository_see_committed_audit(sql_repo) -> None:
    repo, settings, lot_id, lot = sql_repo
    production_at = datetime.now(BANGKOK).replace(second=0, microsecond=0)
    production_date = lot[2].isoformat() if hasattr(lot[2], "isoformat") else str(lot[2])
    new_entry = repo.save_production({
        "lot_id": lot_id, "actual_drops": 7, "wet_good_pieces": 19,
        "operator_id": "IT-AUTOMATED", "operator_confirmed": True,
        "production_at": production_at, "production_date": production_date,
        "shift_schedule_version_id": int(lot[3]), "shift_id": int(lot[4]),
    })
    entry_id = int(new_entry["id"])

    # A fresh repository/connection simulates application restart and proves SQL persistence.
    restarted = _write_repository(settings)
    saved = next(entry for entry in restarted.production_entries(production_date) if entry["id"] == entry_id)
    assert saved["actual_drops"] == 7

    edited = restarted.correct_production(
        entry_id, actual_drops=8, wet_good_pieces=21, reason="integration edit",
        operator_id="IT-AUTOMATED", operator_confirmed=True,
    )
    assert edited["actual_drops"] == 8
    history = restarted.production_entry_history(entry_id)
    assert [item["action"] for item in history] == ["SAVE", "EDIT"]

    deleted = restarted.delete_production(
        entry_id, reason="integration cleanup", operator_id="IT-AUTOMATED", operator_confirmed=True,
    )
    assert deleted["id"] == entry_id
    assert all(entry["id"] != entry_id for entry in restarted.production_entries(production_date))
    assert [item["action"] for item in restarted.production_entry_history(entry_id)] == ["SAVE", "EDIT", "DELETE"]


def test_sql_transaction_rollback_survives_reconnect(sql_repo) -> None:
    repo, settings, lot_id, _lot = sql_repo
    before_repo = _write_repository(settings)
    with before_repo._connection() as (_, cursor):
        cursor.execute("SELECT LotName FROM omagmes.ProductionLot WHERE id=?", (lot_id,))
        original_name = str(cursor.fetchone()[0])

    with pytest.raises(SourceUnavailable, match="transaction failed"):
        with repo._connection(write=True) as (_, cursor):
            cursor.execute("UPDATE omagmes.ProductionLot SET LotName=? WHERE id=?", (original_name + "-ROLLBACK", lot_id))
            raise RuntimeError("integration rollback probe")

    after_repo = _write_repository(settings)
    with after_repo._connection() as (_, cursor):
        cursor.execute("SELECT LotName FROM omagmes.ProductionLot WHERE id=?", (lot_id,))
        assert str(cursor.fetchone()[0]) == original_name
