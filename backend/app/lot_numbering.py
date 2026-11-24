from __future__ import annotations

import re
from datetime import date


class LotNumberingError(ValueError):
    """The selected production context cannot be represented by the SCG Lot format."""


_PLANT_CODE = re.compile(r"^[A-Z]$")
_SHIFT_CODE = re.compile(r"^[123]$")
_LINE_CODE = re.compile(r"^[A-Z]$")
SCG_PLANT_CODE = "B"
SCG_LINE_CODE = "A"


def build_scg_lot_number(
    production_date: date,
    shift_code: str,
    sequence: int,
    line_code: str = SCG_LINE_CODE,
    *,
    plant_code: str = SCG_PLANT_CODE,
) -> str:
    """Format the factory-confirmed SCG number without changing its sequence."""
    if not _PLANT_CODE.fullmatch(plant_code):
        raise LotNumberingError("Plant code must be one uppercase letter.")
    if not _SHIFT_CODE.fullmatch(str(shift_code)):
        raise LotNumberingError("Shift number must be 1, 2, or 3 for the confirmed SCG Lot format.")
    if not _LINE_CODE.fullmatch(line_code):
        raise LotNumberingError("Line code must be one uppercase letter.")
    if plant_code != SCG_PLANT_CODE:
        raise LotNumberingError("Nong Khae SCG Lot numbers require Plant Code B.")
    if line_code != SCG_LINE_CODE:
        raise LotNumberingError("Nong Khae BLOCK SCG Lot numbers require Line Code A.")
    if not 1 <= sequence <= 99:
        raise LotNumberingError("Lot sequence is exhausted for this Production Date and Shift; sequence 99 cannot wrap.")
    buddhist_year_two_digits = (production_date.year + 543) % 100
    return (
        f"{plant_code}{production_date.day:02d}{production_date.month:02d}"
        f"{buddhist_year_two_digits:02d}{shift_code}{sequence:02d}{line_code}"
    )


def next_lot_sequence(last_sequence: int | None) -> int:
    """Return the next 01–99 sequence; never wraps or reuses a consumed value."""
    if last_sequence is None:
        return 1
    if not 1 <= last_sequence <= 99:
        raise LotNumberingError("Stored Lot sequence is outside the supported 01–99 range.")
    if last_sequence == 99:
        raise LotNumberingError("Lot sequence 99 is exhausted for this Production Date and Shift.")
    return last_sequence + 1