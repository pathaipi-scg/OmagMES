from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class ProductionSave(BaseModel):
    lot_id: int = Field(gt=0)
    actual_drops: int = Field(ge=0)
    wet_good_pieces: int = Field(ge=0)
    operator_note: str = ""


class WetRejectSave(BaseModel):
    lot_id: int = Field(gt=0)
    quantities: dict[str, int]
    operator_note: str = ""


class WetRunEventSave(BaseModel):
    category: Literal[
        "RUNNING", "SETUP", "CHANGEOVER", "IDLE", "CLEANING", "BREAKDOWN", "SMDT"
    ]
    started_at: datetime
    ended_at: datetime | None = None
    note: str = ""


class LifecycleSave(BaseModel):
    lot_id: int = Field(gt=0)
    quantity: int = Field(ge=0)
    note: str = ""


class LotCreate(BaseModel):
    product_id: int = Field(gt=0)
    previous_lot_id: int = Field(gt=0)
    transition: Literal["PRODUCT_CHANGE", "COLOR_CHANGE"]
    color: str
    lot_name: str


class LotRename(BaseModel):
    new_name: str
    reason: str


class MouldTransition(BaseModel):
    action: Literal["SEND_TO_RECONDITION", "APPROVE_RETURN"]
    reason: str
