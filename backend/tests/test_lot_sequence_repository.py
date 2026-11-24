from datetime import date

from backend.app.production_repository import SQLServerProductionRepository


class Cursor:
    def __init__(self, last: int | None, official: int | None = None) -> None:
        self.last = last
        self.official = official
        self.executed: list[tuple[str, tuple[object, ...]]] = []
        self.current = None

    def execute(self, sql: str, params: tuple[object, ...] = ()) -> "Cursor":
        self.executed.append((sql, params))
        if sql.startswith("SELECT LastSequence"):
            self.current = (self.last,) if self.last is not None else None
        elif sql.startswith("SELECT MAX(TRY_CONVERT(int,SUBSTRING(LotNo,9,2)))"):
            self.current = (self.official,)
        return self

    def fetchone(self):
        return self.current


def test_sequence_allocation_locks_scope_and_updates_last_committed_number() -> None:
    cursor = Cursor(7)

    sequence = SQLServerProductionRepository._allocate_lot_sequence(cursor, date(2026, 8, 15), "1")

    assert sequence == 8
    select_sql, select_params = cursor.executed[0]
    assert "WITH (UPDLOCK,HOLDLOCK)" in select_sql
    assert select_params == ("B", date(2026, 8, 15), "1")
    assert "WITH (UPDLOCK,HOLDLOCK)" in cursor.executed[1][0]
    assert cursor.executed[1][1] == ("B1508691",)
    update_sql, update_params = cursor.executed[2]
    assert update_sql.startswith("UPDATE omagmes.LotNumberSequence")
    assert update_params[0] == 8
    assert update_params[1:] == ("B", date(2026, 8, 15), "1")
    assert all("dbo." not in sql for sql, _ in cursor.executed)


def test_first_sequence_is_inserted_as_01_without_max_plus_one() -> None:
    cursor = Cursor(None)

    sequence = SQLServerProductionRepository._allocate_lot_sequence(cursor, date(2026, 8, 15), "2")

    assert sequence == 1
    insert_sql, insert_params = cursor.executed[2]
    assert insert_sql.startswith("INSERT INTO omagmes.LotNumberSequence")
    assert insert_params == ("B", date(2026, 8, 15), "2", 1)


def test_official_lot_collision_advances_even_if_sequence_state_is_behind() -> None:
    cursor = Cursor(1, official=4)

    sequence = SQLServerProductionRepository._allocate_lot_sequence(cursor, date(2026, 11, 13), "2")

    assert sequence == 5
    assert cursor.executed[-1][0].startswith("UPDATE omagmes.LotNumberSequence")


def test_first_sequence_advances_past_existing_official_numbers() -> None:
    cursor = Cursor(None, official=3)

    sequence = SQLServerProductionRepository._allocate_lot_sequence(cursor, date(2026, 11, 13), "3")

    assert sequence == 4
    assert cursor.executed[-1][0].startswith("INSERT INTO omagmes.LotNumberSequence")


def test_sequence_starts_at_01_for_each_date_and_actual_shift_scope() -> None:
    scopes = [
        (date(2026, 11, 13), "1"),
        (date(2026, 11, 13), "2"),
        (date(2026, 11, 13), "3"),
        (date(2026, 11, 14), "2"),
    ]

    for production_date, shift_code in scopes:
        cursor = Cursor(None)
        assert SQLServerProductionRepository._allocate_lot_sequence(cursor, production_date, shift_code) == 1
        assert cursor.executed[0][1] == ("B", production_date, shift_code)
        assert cursor.executed[2][1] == ("B", production_date, shift_code, 1)
