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


SCRIPT = ROOT / "db" / "002_omagmes_configuration.sql"
GO_BATCH = re.compile(r"(?im)^\s*GO\s*(?:--.*)?$")


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply the repeatable OmagMES configuration schema/bootstrap to OMAG.")
    parser.add_argument("--apply", action="store_true", help="Confirm the owner-authorized schema/bootstrap operation.")
    args = parser.parse_args()
    if not args.apply:
        parser.error("pass --apply only after reviewing db/002_omagmes_configuration.sql and confirming OMAG target")

    repository = SQLServerConfigurationRepository()
    settings = repository.settings
    settings.validate(write=True)
    if not settings.trusted_connection:
        parser.error("the internal schema bootstrap runner requires the approved Windows integrated connection")
    sql = SCRIPT.read_text(encoding="utf-8-sig")
    batches = [batch.strip() for batch in GO_BATCH.split(sql) if batch.strip()]

    connection = pyodbc.connect(settings.connection_string(), timeout=5, autocommit=False)
    connection.timeout = 10
    cursor = connection.cursor()
    try:
        cursor.execute("SELECT DB_NAME(), @@SERVERNAME")
        target = cursor.fetchone()
        if target is None or str(target[0]).casefold() != "omag":
            raise RuntimeError("Connected database is not OMAG; no schema script was run.")
        print("Verified database target: OMAG")
        print("Applying application-owned configuration objects only; legacy dbo tables are out of scope.")
        for batch in batches:
            cursor.execute(batch)
        while True:
            if cursor.description:
                rows = cursor.fetchall()
                for row in rows:
                    print("SQL verification:", tuple(row))
            if not cursor.nextset():
                break
        connection.commit()
        print("Schema/bootstrap transaction completed and committed.")
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()
        connection.close()


if __name__ == "__main__":
    main()
