from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DEPLOYMENT_SQL = ROOT / "db" / "admin-review" / "007_operator_production_audit_deploy.sql"


def test_admin_deployment_script_is_guarded_additive_and_rerunnable() -> None:
    sql = DEPLOYMENT_SQL.read_text(encoding="utf-8")
    normalized = " ".join(sql.split()).casefold()

    assert "if db_name() <> n'omag'" in normalized
    assert "begin try" in normalized and "begin transaction" in normalized
    assert "commit transaction" in normalized and "rollback transaction" in normalized
    assert "declare @migration007columnmismatch bit = 0" in normalized
    assert "exec sys.sp_executesql" in normalized
    assert "@mismatch = @migration007columnmismatch output" in normalized
    assert "if @migration007columnmismatch = 1" in normalized
    assert "(n''productionentry'',n''deletedat'',n''datetimeoffset'',8,1)" in normalized
    assert "(n'productionentrychangehistory',n'changedat',n'datetimeoffset',8,0)" in normalized
    assert "(n'wetrejectentry',n'recordedat',n'datetimeoffset',8,0)" in normalized
    assert "(n'mouldhistory',n'changedat',n'datetimeoffset',8,0)" in normalized
    assert "(n''productionentry'',n''isdeleted'',n''bit'',1,0)" in normalized
    assert "(n''curinginputentry'',n''operatorconfirmed'',n''bit'',1,0)" in normalized
    validation_start = normalized.index("declare @migration007columnmismatch bit = 0")
    for add_statement in (
        "alter table omagmes.productionentry add isdeleted bit not null",
        "alter table omagmes.productionentry add deletedat datetimeoffset(0) null",
        "alter table omagmes.productionentry add deletedby nvarchar(200) null",
        "alter table omagmes.productionentry add deletereason nvarchar(500) null",
        "alter table omagmes.productionentry add operatorconfirmed bit not null",
        "alter table omagmes.curinginputentry add operatorconfirmed bit not null",
    ):
        assert normalized.index(add_statement) < validation_start
    assert "if object_id(n'omagmes.productionentrychangehistory', n'u') is null" in normalized
    assert "if object_id(n'omagmes.wetrejectreason', n'u') is null" in normalized
    assert "if object_id(n'omagmes.wetrejectentry', n'u') is null" in normalized
    assert "if object_id(n'omagmes.mould', n'u') is null" in normalized
    assert "if object_id(n'omagmes.mouldhistory', n'u') is null" in normalized
    assert "revoke insert, update, delete on schema::omagmes from omag_mes" in normalized
    assert "grant select, insert, update on object::omagmes.productionentry to omag_mes" in normalized
    assert "grant select, insert on object::omagmes.productionentrychangehistory to omag_mes" in normalized
    assert "grant alter on" not in normalized
    assert "alter login" not in normalized
    assert "create login" not in normalized
    assert "create user" not in normalized
    assert "insert into omagmes.wetrejectreason" not in normalized
    assert "insert into omagmes.mould" not in normalized
