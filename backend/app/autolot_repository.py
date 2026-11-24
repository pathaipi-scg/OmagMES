from __future__ import annotations

import hashlib
from datetime import date, datetime, time
from decimal import Decimal, InvalidOperation
from typing import Any

from .production_plans import plan_snapshot
from .production_repository import SQLServerProductionRepository
from .sql_source import SourceUnavailable


AUTOLOT_TABLES = ("AutoLot", "AutoLotAssignment", "PlanIdentity")


def parse_source_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value).replace(tzinfo=None)
        except ValueError:
            return None
    return None


def detection_source_key(lot_start: datetime) -> str:
    """Use the strongest available source identity while remaining compatible with 012 rows."""
    canonical = lot_start.replace(tzinfo=None).isoformat(timespec="microseconds")
    return hashlib.sha256(f"OMAG.dbo.vw_PRESS_LotDetect|LotStart|{canonical}".encode("utf-8")).hexdigest()


def _source_time(value: Any) -> str | None:
    if isinstance(value, time):
        return value.strftime("%H:%M")
    if isinstance(value, str):
        try:
            return time.fromisoformat(value.strip()).strftime("%H:%M")
        except ValueError:
            return None
    return None


def source_lot_number_changed(existing: str | None, incoming: str | None) -> bool:
    """A source-generated LotNo change is reviewable, never an update to AutoLot identity."""
    return (existing or "").rstrip() != (incoming or "").rstrip()


def _date_value(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None
    return None


def _decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


class SQLServerAutoLotRepository:
    """Independent AutoLot persistence; never creates or mutates ProductionLot/Run rows."""

    def __init__(self, production_repository: SQLServerProductionRepository) -> None:
        self.production_repository = production_repository

    @staticmethod
    def schema_ready(cursor: Any) -> bool:
        cursor.execute(
            "SELECT CASE WHEN OBJECT_ID(N'omagmes.AutoLot',N'U') IS NOT NULL "
            "AND OBJECT_ID(N'omagmes.AutoLotAssignment',N'U') IS NOT NULL "
            "AND OBJECT_ID(N'omagmes.PlanIdentity',N'U') IS NOT NULL "
            "AND COL_LENGTH(N'omagmes.AutoLot',N'SourceKey') IS NOT NULL "
            "AND COL_LENGTH(N'omagmes.AutoLot',N'ProductionDate') IS NOT NULL "
            "AND COL_LENGTH(N'omagmes.AutoLot',N'LotNo') IS NOT NULL "
            "AND COL_LENGTH(N'omagmes.AutoLot',N'ShiftType') IS NOT NULL "
            "AND COL_LENGTH(N'omagmes.AutoLot',N'ShiftNo') IS NOT NULL "
            "AND COL_LENGTH(N'omagmes.AutoLot',N'LotStart') IS NOT NULL "
            "AND COL_LENGTH(N'omagmes.AutoLot',N'LotStop') IS NOT NULL "
            "AND COL_LENGTH(N'omagmes.AutoLot',N'StartTime') IS NOT NULL "
            "AND COL_LENGTH(N'omagmes.AutoLot',N'StopTime') IS NOT NULL "
            "AND COL_LENGTH(N'omagmes.AutoLot',N'pDropCnt') IS NOT NULL "
            "AND COL_LENGTH(N'omagmes.AutoLot',N'DropCnt') IS NOT NULL "
            "AND COL_LENGTH(N'omagmes.AutoLotAssignment',N'AutoLotID') IS NOT NULL "
            "AND COL_LENGTH(N'omagmes.AutoLotAssignment',N'PlanIdentityID') IS NOT NULL "
            "AND COL_LENGTH(N'omagmes.AutoLotAssignment',N'ProductID') IS NOT NULL "
            "AND COL_LENGTH(N'omagmes.AutoLotAssignment',N'MouldID') IS NOT NULL "
            "AND COL_LENGTH(N'omagmes.PlanIdentity',N'PlanKey') IS NOT NULL "
            "AND COL_LENGTH(N'omagmes.PlanIdentity',N'PlanSnapshotJson') IS NOT NULL "
            "AND OBJECT_ID(N'omagmes.UQ_AutoLot_SourceKey',N'UQ') IS NOT NULL "
            "AND OBJECT_ID(N'omagmes.UQ_AutoLotAssignment_AutoLot',N'UQ') IS NOT NULL "
            "AND OBJECT_ID(N'omagmes.UQ_PlanIdentity_PlanKey',N'UQ') IS NOT NULL THEN 1 ELSE 0 END"
        )
        row = cursor.fetchone()
        return bool(row and row[0] == 1)

    def is_available(self) -> bool:
        with self.production_repository._connection() as (_, cursor):
            return self.schema_ready(cursor)

    @staticmethod
    def _auto_lot_lock(cursor: Any, resource: str) -> None:
        cursor.execute(
            "DECLARE @LockResult int; "
            "EXEC @LockResult=sys.sp_getapplock @Resource=?,@LockMode='Exclusive',"
            "@LockOwner='Transaction',@LockTimeout=15000; SELECT @LockResult",
            (resource,),
        )
        row = cursor.fetchone()
        if row is None or int(row[0]) < 0:
            raise SourceUnavailable("Automatic Lot reconciliation could not acquire its SQL serialization lock.")

    @staticmethod
    def normalize_detections(
        rows: list[dict[str, Any]], production_date: str, daily_configuration: dict[str, Any] | None = None,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
        """Normalize view rows without re-resolving Shift or allocating LotNo in Python."""
        del daily_configuration  # Kept as a compatibility parameter; WorkTime in SQL is authoritative.
        selected_date = date.fromisoformat(production_date)
        persistent: list[dict[str, Any]] = []
        preview: list[dict[str, Any]] = []
        warnings: list[str] = []
        seen_starts: set[str] = set()
        seen_lot_numbers: set[str] = set()
        seen_sequences: set[tuple[date, int, int]] = set()
        for row in rows:
            start = parse_source_datetime(row.get("LotStart"))
            stop = parse_source_datetime(row.get("LotStop"))
            source_date = _date_value(row.get("ProdDate"))
            lot_number_value = row.get("LotNo")
            lot_number = str(lot_number_value) if lot_number_value is not None else ""
            if start is None:
                warnings.append("A detection with no valid LotStart was withheld because it has no stable source identity.")
                continue
            if stop is not None and stop < start:
                warnings.append(f"Detection at {start.isoformat()} has LotStop before LotStart and was withheld.")
                continue
            source_key = detection_source_key(start)
            if source_key in seen_starts:
                raise SourceUnavailable("vw_PRESS_LotAuto returned duplicate LotStart timestamps; no AutoLot reconciliation was performed.")
            if lot_number and lot_number in seen_lot_numbers:
                raise SourceUnavailable("vw_PRESS_LotAuto returned duplicate LotNo values; no AutoLot reconciliation was performed.")
            seen_starts.add(source_key)
            if lot_number:
                seen_lot_numbers.add(lot_number)
            try:
                source_shift_type = int(row["ShiftType"]) if row.get("ShiftType") is not None else None
            except (TypeError, ValueError):
                source_shift_type = None
            source_shift_no = str(row["ShiftNo"]).rstrip() if row.get("ShiftNo") is not None else None
            try:
                shift_number = int(source_shift_no.strip()) if source_shift_no and source_shift_no.strip() else None
            except ValueError:
                shift_number = None
            source_start_time = _source_time(row.get("StartTime"))
            source_stop_time = _source_time(row.get("StopTime"))
            try:
                lot_sequence = int(row["LotSequence"]) if row.get("LotSequence") is not None else None
            except (TypeError, ValueError):
                lot_sequence = None
            try:
                source_row_number = int(row["SourceRowNumber"]) if row.get("SourceRowNumber") is not None else (
                    int(row["rw"]) if row.get("rw") is not None else None
                )
            except (TypeError, ValueError):
                source_row_number = None
            shift_status = str(row.get("ShiftStatus") or "SHIFT_STATUS_MISSING").strip().upper()
            lot_status = str(row.get("LotStatus") or ("ALLOCATED" if lot_number else "LOT_STATUS_MISSING")).strip().upper()
            detected = {
                "source_key": source_key,
                "source_production_date": source_date,
                "lot_start": start,
                "lot_stop": stop,
                "lot_number": lot_number or None,
                "lot_sequence": lot_sequence,
                "source_row_number": source_row_number,
                "source_shift_type": source_shift_type,
                "shift_type": source_shift_type,
                "source_shift_no": source_shift_no,
                "source_start_time": source_start_time,
                "source_stop_time": source_stop_time,
                "shift_number": shift_number,
                "shift_status": shift_status,
                "lot_status": lot_status,
                "drop_count": row.get("DropCnt"),
                "previous_drop_count": row.get("pDropCnt"),
            }
            row_status = "ELIGIBLE"
            if source_date != selected_date:
                row_status = "SOURCE PRODUCTION DATE MISMATCH"
            elif shift_status != "RESOLVED" or shift_number is None:
                row_status = f"SHIFT UNRESOLVED · {shift_status}"
            elif lot_status != "ALLOCATED" or not lot_number or lot_sequence is None:
                row_status = f"LOT NUMBER UNRESOLVED · {lot_status}"
            elif not (lot_number.startswith("B") and lot_number.endswith("B") and len(lot_number) == 11):
                row_status = "SOURCE LOT NUMBER FORMAT INVALID"
            else:
                sequence_key = (selected_date, shift_number, lot_sequence)
                if sequence_key in seen_sequences:
                    raise SourceUnavailable("vw_PRESS_LotAuto returned duplicate date/shift LotSequence values; no reconciliation was performed.")
                seen_sequences.add(sequence_key)

            if row_status == "ELIGIBLE":
                detected.update({
                    "production_date": source_date,
                    "status": "READY FOR RECONCILIATION",
                })
                persistent.append(detected)
            else:
                detected.update({
                    "production_date": source_date or selected_date,
                    "auto_lot_id": None,
                    "status": row_status,
                })
                preview.append(detected)
                warnings.append(
                    f"Source detection at {start.isoformat()} is unresolved by dbo.vw_PRESS_LotAuto: {row_status}."
                )
        persistent.sort(key=lambda item: (item["lot_start"], item["source_key"]))
        preview.sort(key=lambda item: (item["lot_start"], item["source_key"]))
        return persistent, preview, list(dict.fromkeys(warnings))

    def reconcile(
        self, production_date: str, daily_configuration: dict[str, Any] | None, rows: list[dict[str, Any]],
    ) -> dict[str, Any]:
        del daily_configuration  # Shift/lot facts are copied from SQL, never re-resolved here.
        selected_date = date.fromisoformat(production_date)
        prepared: list[tuple[str, dict[str, Any], datetime]] = []
        seen: set[str] = set()
        seen_lot_numbers: set[str] = set()
        for row in rows:
            start = parse_source_datetime(row.get("LotStart"))
            if start is None:
                continue
            source_date = _date_value(row.get("ProdDate"))
            if source_date != selected_date:
                continue
            source_key = detection_source_key(start)
            if source_key in seen:
                raise SourceUnavailable("dbo.vw_PRESS_LotAuto returned duplicate LotStart timestamps; no assignment identity was created.")
            seen.add(source_key)
            lot_no = str(row["LotNo"]).rstrip() if row.get("LotNo") is not None else ""
            if lot_no and lot_no in seen_lot_numbers:
                raise SourceUnavailable("dbo.vw_PRESS_LotAuto returned duplicate LotNo values; no assignment identity was created.")
            if lot_no:
                seen_lot_numbers.add(lot_no)
            prepared.append((source_key, row, start))
        if len(prepared) != len(rows):
            raise SourceUnavailable("A detected AutoLot lacks the selected Production Date or a valid LotStart; assignment identities were not synchronized.")

        with self.production_repository._connection() as (_, cursor):
            if not self.schema_ready(cursor):
                return {"status": "SETUP_REQUIRED", "created": 0, "updated": 0,
                        "preview_count": len(rows),
                        "warnings": ["The reviewed AutoLot assignment setup has not been deployed; detections remain direct, read-only SQL view rows."]}

        created = updated = 0
        with self.production_repository._connection(write=True) as (_, cursor):
            cursor.execute("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE")
            self._auto_lot_lock(cursor, f"OMAGMES-AUTOLOT:{production_date}")
            if not self.schema_ready(cursor):
                raise SourceUnavailable("The reviewed AutoLot assignment setup is not deployed; no assignment identity was written.")

            for source_key, row, start in prepared:
                stop = parse_source_datetime(row.get("LotStop"))
                lot_no = str(row["LotNo"]) if row.get("LotNo") is not None else None
                shift_type = row.get("ShiftType")
                shift_no = str(row["ShiftNo"]).rstrip() if row.get("ShiftNo") is not None else None
                drop_count = row.get("DropCnt")
                previous_drop_count = row.get("pDropCnt")
                cursor.execute(
                    "SELECT id FROM omagmes.AutoLot WITH (UPDLOCK,HOLDLOCK) WHERE SourceKey=?",
                    (source_key,),
                )
                existing = cursor.fetchone()
                if existing is None and lot_no:
                    # LotStart is the best available key, but it can be corrected upstream.
                    # Recover the same local AutoLotID only when its date + LotNo match uniquely.
                    cursor.execute(
                        "SELECT id FROM omagmes.AutoLot WITH (UPDLOCK,HOLDLOCK) "
                        "WHERE ProductionDate=? AND RTRIM(LotNo)=? ORDER BY id",
                        (selected_date, lot_no),
                    )
                    corrected_matches = cursor.fetchall()
                    if len(corrected_matches) > 1:
                        raise SourceUnavailable(
                            f"Source correction for LotNo {lot_no} matches multiple stored AutoLots; no identity was changed."
                        )
                    if corrected_matches:
                        existing = corrected_matches[0]
                if existing is None:
                    cursor.execute(
                        "INSERT INTO omagmes.AutoLot (ProductionDate,SourceKey,LotNo,ShiftType,ShiftNo,LotStart,LotStop,StartTime,StopTime,pDropCnt,DropCnt) "
                        "OUTPUT INSERTED.id VALUES (?,?,?,?,?,?,?,CONVERT(time(7),?),CONVERT(time(7),?),?,?)",
                        (selected_date, source_key, lot_no, shift_type, shift_no, start, stop,
                         row.get("StartTime"), row.get("StopTime"), previous_drop_count, drop_count),
                    )
                    inserted = cursor.fetchone()
                    if inserted is None:
                        raise SourceUnavailable("AutoLot insert returned no identity; the transaction was rolled back.")
                    cursor.execute(
                        "INSERT INTO omagmes.AutoLotAssignment (AutoLotID,PlanIdentityID,ProductID,MouldID) VALUES (?,NULL,NULL,NULL)",
                        (int(inserted[0]),),
                    )
                    created += 1
                else:
                    cursor.execute(
                        "UPDATE omagmes.AutoLot SET ProductionDate=?,SourceKey=?,LotNo=?,ShiftType=?,ShiftNo=?,LotStart=?,LotStop=?,"
                        "StartTime=CONVERT(time(7),?),StopTime=CONVERT(time(7),?),pDropCnt=?,DropCnt=? WHERE id=?",
                        (selected_date, source_key, lot_no, shift_type, shift_no, start, stop,
                         row.get("StartTime"), row.get("StopTime"), previous_drop_count, drop_count, int(existing[0])),
                    )
                    updated += 1
        return {
            "status": "RECONCILED", "created": created, "updated": updated,
            "current_count": len(prepared), "source_count": len(rows), "warnings": [],
        }

    def list_for_date(self, production_date: str) -> list[dict[str, Any]]:
        with self.production_repository._connection() as (_, cursor):
            if not self.schema_ready(cursor):
                return []
            cursor.execute(
                "SELECT a.id,a.ProductionDate,a.LotNo,a.ShiftType,a.ShiftNo,a.LotStart,a.LotStop,a.DropCnt,a.pDropCnt,a.SourceKey,"
                "i.id,i.PlanKey,i.PlanName,i.MaterialCode,i.MaterialName,i.PlanSnapshotJson,"
                "x.ProductID,p.ProductCode,p.ProductName,p.ProductNameThai,x.MouldID,m.MouldCode,m.MouldName,m.StatusCode,m.IsActive "
                "FROM omagmes.AutoLot a "
                "LEFT JOIN omagmes.AutoLotAssignment x ON x.AutoLotID=a.id "
                "LEFT JOIN omagmes.PlanIdentity i ON i.id=x.PlanIdentityID "
                "LEFT JOIN omagmes.Product p ON p.id=x.ProductID "
                "LEFT JOIN omagmes.Mould m ON m.id=x.MouldID "
                "WHERE a.ProductionDate=? ORDER BY a.LotStart,a.id",
                (date.fromisoformat(production_date),),
            )
            rows = cursor.fetchall()
        result: list[dict[str, Any]] = []
        for row in rows:
            result.append({
                "auto_lot_id": int(row[0]), "production_date": row[1].isoformat(),
                "lot_number": str(row[2]) if row[2] is not None else None,
                "shift_type": int(row[3]) if row[3] is not None else None,
                "shift_number": str(row[4]).rstrip() if row[4] is not None else None,
                "lot_start": row[5].isoformat() if row[5] else None,
                "lot_stop": row[6].isoformat() if row[6] else None,
                "drop_count": int(row[7]) if row[7] is not None else None,
                "previous_drop_count": int(row[8]) if row[8] is not None else None,
                "source_key": str(row[9]),
                "plan_identity_id": int(row[10]) if row[10] is not None else None,
                "plan_key": str(row[11]).strip() if row[11] is not None else None,
                "plan_name": row[12], "material_code": row[13], "material_name": row[14],
                "plan_snapshot_json": row[15],
                "product_id": int(row[16]) if row[16] is not None else None,
                "product_code": row[17], "product_name": row[18], "product_name_thai": row[19],
                "mould_id": int(row[20]) if row[20] is not None else None,
                "mould_code": row[21], "mould_name": row[22], "mould_status": row[23],
                "mould_active": bool(row[24]) if row[24] is not None else None,
            })
        return result

    @staticmethod
    def attach_saved_assignments(
        source_rows: list[dict[str, Any]], saved_rows: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """LEFT-merge assignments by LotStart-derived local identity; never drop source Lots."""
        saved_by_source = {item["source_key"]: item for item in saved_rows}
        merged: list[dict[str, Any]] = []
        for source_row in source_rows:
            row = dict(source_row)
            lot_start = parse_source_datetime(row.get("LotStart"))
            saved = saved_by_source.get(detection_source_key(lot_start)) if lot_start is not None else None
            row["auto_lot_id"] = saved["auto_lot_id"] if saved else None
            row["assignment"] = ({
                "plan_key": saved["plan_key"], "plan_name": saved["plan_name"],
                "material_code": saved["material_code"], "material_name": saved["material_name"],
                "product_id": saved["product_id"], "product_code": saved["product_code"],
                "product_name": saved["product_name"], "mould_id": saved["mould_id"],
                "mould_code": saved["mould_code"], "mould_name": saved["mould_name"],
            } if saved and saved["plan_identity_id"] is not None else None)
            merged.append(row)
        return merged

    def plans_with_product_matches(self, plans: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Map Plan MaterialCode to exact active ProductCode without code normalization."""
        with self.production_repository._connection() as (_, cursor):
            cursor.execute(
                "SELECT id,ProductCode,ProductName,ProductNameThai,IsActive "
                "FROM omagmes.Product ORDER BY id"
            )
            products = cursor.fetchall()
        result: list[dict[str, Any]] = []
        for plan in plans:
            material = plan.get("material_code")
            matches = [row for row in products if material is not None and str(row[1]) == str(material) and bool(row[4])]
            if len(matches) == 1:
                product = matches[0]
                mapping = {
                    "status": "MATCHED", "product_id": int(product[0]), "product_code": str(product[1]),
                    "product_name": product[2], "product_name_thai": product[3],
                }
            elif len(matches) > 1:
                mapping = {"status": "AMBIGUOUS", "product_id": None, "product_code": material,
                           "product_name": None, "product_name_thai": None}
            else:
                mapping = {"status": "PRODUCT NOT FOUND", "product_id": None, "product_code": material,
                           "product_name": None, "product_name_thai": None}
            result.append({**plan, "product_match": mapping})
        return result

    def active_moulds_for_product(self, product_id: int) -> list[dict[str, Any]]:
        """Return only physical Moulds currently eligible for this Product."""
        with self.production_repository._connection() as (_, cursor):
            cursor.execute(
                "SELECT m.id,m.ProductID,m.MouldCode,m.MouldName,m.StatusCode "
                "FROM omagmes.Mould m JOIN omagmes.Product p ON p.id=m.ProductID AND p.IsActive=1 "
                "WHERE m.ProductID=? AND m.IsActive=1 AND m.StatusCode='ACTIVE' "
                "ORDER BY MouldCode,id",
                (product_id,),
            )
            rows = cursor.fetchall()
        return [{
            "id": int(row[0]), "product_id": int(row[1]), "code": str(row[2]),
            "name": row[3], "status": str(row[4]),
        } for row in rows]

    def product_id_for(self, auto_lot_id: int) -> int:
        with self.production_repository._connection() as (_, cursor):
            if not self.schema_ready(cursor):
                raise SourceUnavailable("The clean AutoLot setup is not deployed.")
            cursor.execute(
                "SELECT ProductID FROM omagmes.AutoLotAssignment WHERE AutoLotID=?",
                (auto_lot_id,),
            )
            row = cursor.fetchone()
        if row is None or row[0] is None:
            raise ValueError("Assign a uniquely matched Production Plan before selecting a Mould.")
        return int(row[0])

    def save_assignment(
        self, auto_lot_id: int, plan: dict[str, Any] | None, mould_id: int | None,
    ) -> dict[str, Any]:
        if plan is None or mould_id is None:
            raise ValueError("Select a Production Plan and a compatible active Mould before saving.")
        if int(plan.get("duplicate_count", 0)) != 1:
            raise ValueError("This Production Plan source row is duplicated or indistinguishable and cannot be assigned safely.")
        if plan.get("identity_kind") != "CONTENT_FINGERPRINT_NOT_SOURCE_ID":
            raise ValueError("The Plan identity is not a verified source snapshot.")
        material_code = plan.get("material_code")
        if not isinstance(material_code, str) or not material_code:
            raise ValueError("The selected Plan has no MaterialCode and cannot resolve a Product.")
        snapshot_record = plan_snapshot(plan.get("snapshot") or {})
        if snapshot_record["plan_key"] != plan.get("plan_key"):
            raise ValueError("The selected Plan snapshot changed; reload Production Plans and retry.")
        snapshot_json = snapshot_record["snapshot_json"]

        resolved_product: tuple[int, str] | None = None
        with self.production_repository._connection(write=True) as (_, cursor):
            cursor.execute("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE")
            self._auto_lot_lock(cursor, f"OMAGMES-AUTOLOT-ASSIGNMENT:{auto_lot_id}")
            if not self.schema_ready(cursor):
                raise SourceUnavailable("The reviewed AutoLot assignment setup is not deployed; assignment was not saved.")
            cursor.execute("SELECT id,ProductionDate FROM omagmes.AutoLot WITH (UPDLOCK,HOLDLOCK) WHERE id=?", (auto_lot_id,))
            auto_lot = cursor.fetchone()
            if auto_lot is None:
                raise ValueError("AutoLot was not found; reload the Production table.")
            cursor.execute(
                "SELECT id,ProductCode FROM omagmes.Product WITH (UPDLOCK,HOLDLOCK) WHERE IsActive=1 ORDER BY id"
            )
            product_matches = [(int(row[0]), str(row[1])) for row in cursor.fetchall() if str(row[1]) == material_code]
            if not product_matches:
                raise ValueError(f"PRODUCT NOT FOUND: MaterialCode {material_code} has no exact active ProductCode match.")
            if len(product_matches) != 1:
                raise ValueError(f"PRODUCT MATCH AMBIGUOUS: MaterialCode {material_code} matches multiple active Products.")
            resolved_product = product_matches[0]

            plan_identity_id: int | None = None
            snapshot = snapshot_record["snapshot"]
            count_value = _decimal(snapshot.get("PlanCount"))
            planned_start = _date_value(snapshot.get("StartTime"))
            cursor.execute(
                "SELECT id,PlanSnapshotJson FROM omagmes.PlanIdentity WITH (UPDLOCK,HOLDLOCK) WHERE PlanKey=?",
                (snapshot_record["plan_key"],),
            )
            identity = cursor.fetchone()
            if identity is not None:
                if str(identity[1]) != snapshot_json:
                    raise SourceUnavailable("Stored Plan identity fingerprint conflicts with its snapshot; assignment was not saved.")
                plan_identity_id = int(identity[0])
            else:
                cursor.execute(
                    "INSERT INTO omagmes.PlanIdentity (PlanKey,PlanSnapshotJson,PlanName,MaterialCode,MaterialName,"
                    "PlannedStart,PlanCountText,Machine,Shift) OUTPUT INSERTED.id VALUES (?,?,?,?,?,?,?,?,?)",
                    (snapshot_record["plan_key"], snapshot_json, snapshot.get("PlanName"), material_code,
                     snapshot.get("MaterialName"), planned_start,
                     str(count_value) if count_value is not None else None,
                     snapshot.get("Machine"), snapshot.get("Shift")),
                )
                inserted_plan = cursor.fetchone()
                if inserted_plan is None:
                    raise SourceUnavailable("Plan identity insert returned no ID; assignment was rolled back.")
                plan_identity_id = int(inserted_plan[0])

            if resolved_product is None:
                raise ValueError("A Mould requires a Plan with an exact Product match.")
            cursor.execute(
                "SELECT id FROM omagmes.Mould WITH (UPDLOCK,HOLDLOCK) "
                "WHERE id=? AND ProductID=? AND IsActive=1 AND StatusCode='ACTIVE'",
                (mould_id, resolved_product[0]),
            )
            if cursor.fetchone() is None:
                raise ValueError("Selected Mould is not active or is not registered to the Plan's resolved Product.")

            product_id = resolved_product[0] if resolved_product is not None else None
            cursor.execute(
                "SELECT id FROM omagmes.AutoLotAssignment WITH (UPDLOCK,HOLDLOCK) WHERE AutoLotID=?",
                (auto_lot_id,),
            )
            current_assignment = cursor.fetchone()
            if current_assignment is None:
                cursor.execute(
                    "INSERT INTO omagmes.AutoLotAssignment (AutoLotID,PlanIdentityID,ProductID,MouldID) VALUES (?,?,?,?)",
                    (auto_lot_id, plan_identity_id, product_id, mould_id),
                )
            else:
                cursor.execute(
                    "UPDATE omagmes.AutoLotAssignment SET PlanIdentityID=?,ProductID=?,MouldID=?,UpdatedTime=GETDATE() WHERE id=?",
                    (plan_identity_id, product_id, mould_id, int(current_assignment[0])),
                )
        production_date = auto_lot[1].isoformat()
        return next((row for row in self.list_for_date(production_date) if row["auto_lot_id"] == auto_lot_id),
                    {"auto_lot_id": auto_lot_id, "plan_identity_id": plan_identity_id,
                     "product_id": product_id, "mould_id": mould_id})

    def production_date_for(self, auto_lot_id: int) -> str:
        with self.production_repository._connection() as (_, cursor):
            if not self.schema_ready(cursor):
                raise SourceUnavailable("The clean AutoLot setup is not deployed.")
            cursor.execute("SELECT ProductionDate FROM omagmes.AutoLot WHERE id=?", (auto_lot_id,))
            row = cursor.fetchone()
        if row is None:
            raise ValueError("AutoLot was not found; reload the Production table.")
        return row[0].isoformat()

