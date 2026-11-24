from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class ProductionDayCutoffSave(BaseModel):
    effective_from: str
    cutoff_time: str
    time_zone: str = "Asia/Bangkok"
    reviewed_through_date: str
    base_version_id: int = Field(gt=0)
    change_reason: str = Field(min_length=1, max_length=500)


class ProductionSave(BaseModel):
    lot_id: int = Field(gt=0)
    production_at: datetime | None = None
    actual_drops: int = Field(ge=0)
    wet_good_pieces: int = Field(ge=0)
    operator_note: str = ""
    operator_id: str = Field(min_length=1, max_length=200, description="User-supplied audit label; not authenticated or verified.")
    operator_confirmed: bool = False
    suggested_actual_drops: int | None = Field(default=None, ge=0)
    suggested_wet_good_pieces: int | None = Field(default=None, ge=0)
    production_date: str | None = None
    shift_schedule_version_id: int | None = Field(default=None, gt=0)
    production_day_cutoff_version_id: int | None = Field(default=None, gt=0)


class WetRejectSave(BaseModel):
    lot_id: int = Field(gt=0)
    quantities: dict[int, int]
    operator_note: str = ""
    operator_id: str = Field(min_length=1, max_length=200, description="User-supplied audit label; not authenticated or verified.")
    production_date: str | None = None
    shift_schedule_version_id: int | None = Field(default=None, gt=0)
    production_day_cutoff_version_id: int | None = Field(default=None, gt=0)


class WetRunEventSave(BaseModel):
    category: Literal[
        "RUNNING", "SETUP", "CHANGEOVER", "IDLE", "CLEANING", "BREAKDOWN", "SMDT"
    ]
    started_at: datetime
    ended_at: datetime | None = None
    note: str = ""
    production_date: str | None = None
    shift_schedule_version_id: int | None = Field(default=None, gt=0)
    production_day_cutoff_version_id: int | None = Field(default=None, gt=0)


class LifecycleSave(BaseModel):
    lot_id: int = Field(gt=0)
    quantity: int = Field(ge=0)
    note: str = ""
    unit_code: str = ""
    operator_id: str = ""
    operator_confirmed: bool = False
    production_date: str | None = None
    shift_schedule_version_id: int | None = Field(default=None, gt=0)
    production_day_cutoff_version_id: int | None = Field(default=None, gt=0)


class LotCreate(BaseModel):
    product_id: int = Field(gt=0)
    previous_lot_id: int | None = Field(default=None, gt=0)
    transition: Literal["PRODUCT_CHANGE", "COLOR_CHANGE"]
    color: str
    lot_name: str
    production_date: str | None = None
    shift_schedule_version_id: int | None = Field(default=None, gt=0)
    production_day_cutoff_version_id: int | None = Field(default=None, gt=0)
    operator_id: str = ""
    started_at: datetime | None = None
    machine_code: Literal["A"] | None = None
    reset_candidate_id: str | None = Field(default=None, max_length=200)
    reset_confirmation_reason: str = Field(default="", max_length=500)


class ShiftPeriodInput(BaseModel):
    start_time: str
    end_time: str
    display_order: int = Field(gt=0)
    active: bool = True


class ShiftDefinitionInput(BaseModel):
    id: int | None = Field(default=None, gt=0)
    shift_code: str
    shift_name: str
    start_time: str
    end_time: str
    display_order: int = Field(gt=0)
    active: bool = True
    periods: list[ShiftPeriodInput] = Field(default_factory=list)


class ShiftScheduleSave(BaseModel):
    effective_from: str
    reviewed_through_date: str
    base_version_id: int = Field(gt=0)
    change_reason: str = Field(min_length=1, max_length=500)
    shifts: list[ShiftDefinitionInput] = Field(min_length=1)


class ShiftPeriodScheduleSave(BaseModel):
    effective_from: str
    reviewed_through_date: str
    base_version_id: int = Field(gt=0)
    change_reason: str = Field(min_length=1, max_length=500)
    shifts: list[ShiftDefinitionInput] = Field(min_length=1)


class ShiftTypePeriodInput(BaseModel):
    shift_id: int = Field(gt=0)
    shift_number: int = Field(ge=1, le=9)
    period_order: int = Field(gt=0)
    start_time: str
    end_time: str
    end_next_day: bool = False
    active: bool = True


class ShiftTypeScheduleVersionSave(BaseModel):
    effective_from: str
    base_schedule_version_id: int = Field(gt=0)
    periods: list[ShiftTypePeriodInput] = Field(min_length=1)


class DailyShiftTypeAssignmentSave(BaseModel):
    production_date: str
    shift_type_id: int = Field(gt=0)
    expected_assignment_id: int | None = Field(default=None, gt=0)


class ProductionShiftTypeSave(BaseModel):
    production_date: str
    selected_type: Literal[1, 2, 3]


class WorkTimeShiftSettingChange(BaseModel):
    work_type: Literal["1", "2", "3"]
    shift_no: str = Field(min_length=1, max_length=1)
    start_time: str
    stop_time: str


class WorkTimeShiftSettingsSave(BaseModel):
    changes: list[WorkTimeShiftSettingChange] = Field(max_length=100)


class DailyShiftPeriodValue(BaseModel):
    type: int = Field(ge=1, le=3)
    shift: int = Field(ge=1, le=3)
    start: str
    stop: str


class DailyShiftConfigurationSave(BaseModel):
    production_date: str
    selected_type: int = Field(ge=1, le=3)
    periods: list[DailyShiftPeriodValue] = Field(min_length=5, max_length=5)


class AutoLotDraftCreate(BaseModel):
    production_date: str
    schedule_version_id: int = Field(gt=0)
    cutoff_version_id: int | None = Field(default=None, gt=0)
    shift_id: int = Field(gt=0)
    started_at: datetime
    ended_at: datetime | None = None
    raw_drop_count: int = Field(ge=0)


class AutoLotDraftReview(BaseModel):
    schedule_version_id: int = Field(gt=0)
    cutoff_version_id: int | None = Field(default=None, gt=0)
    shift_id: int = Field(gt=0)
    started_at: datetime
    ended_at: datetime | None = None
    operator_confirmed_drop_count: int = Field(ge=0)
    reason: str


class AutoLotDraftDismiss(BaseModel):
    reason: str


class AutoLotCandidateAction(BaseModel):
    production_date: str
    cutoff_version_id: int = Field(gt=0)
    reason: str = Field(min_length=1, max_length=500)
    corrected_started_at: datetime | None = None
    corrected_ended_at: datetime | None = None
    corrected_drop_count: int | None = Field(default=None, ge=0)


class LotRename(BaseModel):
    new_name: str
    reason: str
    operator_id: str = Field(default="", max_length=200, description="Optional user-supplied audit label; not authenticated or verified.")


class ProductionCorrection(BaseModel):
    actual_drops: int = Field(ge=0)
    wet_good_pieces: int = Field(ge=0)
    reason: str = Field(min_length=1, max_length=500)
    operator_id: str = Field(min_length=1, max_length=200, description="User-supplied audit label; not authenticated or verified.")
    operator_confirmed: bool = False


class ProductionDelete(BaseModel):
    reason: str = Field(min_length=1, max_length=500)
    operator_id: str = Field(min_length=1, max_length=200, description="User-supplied audit label; not authenticated or verified.")
    operator_confirmed: bool = False


class DispatchSave(BaseModel):
    lot_id: int = Field(gt=0)
    quantity: int = Field(ge=0)
    unit_code: str = Field(min_length=1, max_length=40)
    operator_id: str = Field(min_length=1, max_length=200, description="User-supplied audit label; not authenticated or verified.")
    dispatch_reference: str = Field(default="", max_length=120)
    note: str = Field(default="", max_length=1000)


class MouldTransition(BaseModel):
    action: Literal["SEND_TO_RECONDITION", "APPROVE_RETURN"]
    reason: str


class AutoLotWindowCreate(BaseModel):
    start_at: datetime
    end_at: datetime | None = None
    operator_id: str = Field(min_length=1, max_length=200)
    reason: str = Field(min_length=1, max_length=500)


class AutoLotWindowEdit(BaseModel):
    start_at: datetime
    end_at: datetime | None = None
    operator_id: str = Field(min_length=1, max_length=200)
    reason: str = Field(min_length=1, max_length=500)


class AutoLotWindowSplit(BaseModel):
    split_at: datetime
    operator_id: str = Field(min_length=1, max_length=200)
    reason: str = Field(min_length=1, max_length=500)


class AutoLotWindowMerge(BaseModel):
    source_window_id: int = Field(gt=0)
    operator_id: str = Field(min_length=1, max_length=200)
    reason: str = Field(min_length=1, max_length=500)


class AutoLotWindowDismiss(BaseModel):
    operator_id: str = Field(min_length=1, max_length=200)
    reason: str = Field(min_length=1, max_length=500)


class AutoLotWindowRestore(BaseModel):
    operator_id: str = Field(min_length=1, max_length=200)
    reason: str = Field(min_length=1, max_length=500)


class AutoLotPlanAssign(BaseModel):
    plan_key: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")
    operator_id: str = Field(min_length=1, max_length=200)
    reason: str = Field(min_length=1, max_length=500)


class AutoLotReconcileRequest(BaseModel):
    production_date: str


class AutoLotAssignmentSave(BaseModel):
    plan_key: str | None = Field(default=None, min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")
    mould_id: int | None = Field(default=None, gt=0)


class AutoLotCandidateClassify(BaseModel):
    product_id: int = Field(gt=0)
    color_code: str = Field(min_length=1, max_length=60)
    operator_id: str = Field(min_length=1, max_length=200)
    reason: str = Field(min_length=1, max_length=500)
