from datetime import date

import pytest

from backend.app.lot_numbering import LotNumberingError, build_scg_lot_number, next_lot_sequence


def test_scg_lot_number_uses_buddhist_year_and_confirmed_format() -> None:
    assert build_scg_lot_number(date(2026, 11, 13), "1", 1) == "B131169101A"
    assert build_scg_lot_number(date(2026, 11, 13), "2", 1) == "B131169201A"
    assert build_scg_lot_number(date(2026, 11, 13), "3", 2) == "B131169302A"


def test_sequence_is_two_digits_never_wraps_or_reuses() -> None:
    assert next_lot_sequence(None) == 1
    assert next_lot_sequence(1) == 2
    assert next_lot_sequence(98) == 99
    with pytest.raises(LotNumberingError, match="exhausted"):
        next_lot_sequence(99)
    with pytest.raises(LotNumberingError, match="exhausted"):
        build_scg_lot_number(date(2026, 8, 15), "1", 100)


def test_unrepresentable_shift_or_machine_is_operation_scoped_blocker() -> None:
    with pytest.raises(LotNumberingError, match="Shift number"):
        build_scg_lot_number(date(2026, 8, 15), "SHIFT-A", 1)
    with pytest.raises(LotNumberingError, match="require.*A"):
        build_scg_lot_number(date(2026, 8, 15), "1", 1, "B")
    with pytest.raises(LotNumberingError, match="Shift number"):
        build_scg_lot_number(date(2026, 8, 15), "4", 1)
