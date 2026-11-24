from __future__ import annotations

import argparse
import re
from pathlib import Path
import sys

import pyodbc

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.configuration_repository import SQLServerConfigurationRepository

SCRIPT = ROOT / "db" / "deploy" / "004_shift_type_daily_assignment.sql"
GO_BATCH = re.compile(r"(?im)^\s*GO\s*(?:--.*)?$")


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply additive OmagMES Shift Type and daily assignment objects to OMAG.")
    parser.add_argument("--apply", action="store_true", help="Confirm the authorized Shift Type schema deployment.")
    args = parser.parse_args()
    if not args.apply:
        parser.error("pass --apply to execute the authorized Shift Type deployment")

    repository = SQLServerConfigurationRepository()
    settings = repository.settings
    settings.validate(write=True)
    if not settings.trusted_connection:
        parser.error("the internal schema deployment runner requires the approved Windows integrated connection")
    batches = [batch.strip() for batch in GO_BATCH.split(SCRIPT.read_text(encoding="utf-8-sig")) if batch.strip()]
    connection = pyodbc.connect(settings.connection_string(), timeout=5, autocommit=False)
    connection.timeout = 10
    cursor = connection.cursor()
    try:
        cursor.execute("SELECT DB_NAME(), @@SERVERNAME")
        target = cursor.fetchone()
        if target is None or str(target[0]).casefold() != "omag" or str(target[1]).casefold() != "scgls-nk\\sqlexpress":
            raise RuntimeError("Connected SQL target is not the verified OMAG database/instance; deployment refused.")
        print("Verified database target: OMAG / SCGLS-NK\\SQLEXPRESS")
        print("Applying additive Shift Type, schedule version, period, and daily assignment objects only.")
        for batch in batches:
            cursor.execute(batch)
            while True:
                if cursor.description:
                    for row in cursor.fetchall():
                        print("SQL verification:", tuple(row))
                if not cursor.nextset():
                    break
        connection.commit()
        print("Shift Type deployment transaction committed.")
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()
        connection.close()


if __name__ == "__main__":
    main()
