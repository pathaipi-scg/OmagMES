import pytest

from backend.app.configuration_repository import ConfigurationSQLSettings, ConfigurationUnavailable, SQLServerConfigurationRepository


def settings(**updates: object) -> ConfigurationSQLSettings:
    values: dict[str, object] = {
        "server": "10.28.255.98\\SQLEXPRESS",
        "database": "OMAG",
        "driver": "ODBC Driver 18 for SQL Server",
        "username": "dedicated-config-user",
        "password": "not-a-real-password",
        "trusted_connection": False,
        "target_confirmed": True,
        "writes_confirmed": True,
        "encrypt": True,
        "trust_server_certificate": False,
    }
    values.update(updates)
    return ConfigurationSQLSettings(**values)  # type: ignore[arg-type]


def test_configuration_reads_require_explicit_target_and_encrypted_transport() -> None:
    with pytest.raises(ConfigurationUnavailable, match="target is explicitly verified"):
        ConfigurationSQLSettings(**{**settings().__dict__, "target_confirmed": False}).validate(write=False)
    with pytest.raises(ConfigurationUnavailable, match="target is explicitly verified"):
        ConfigurationSQLSettings(**{**settings().__dict__, "target_confirmed": False}).validate(write=True)
    with pytest.raises(ConfigurationUnavailable, match="encrypted transport"):
        ConfigurationSQLSettings(**{**settings().__dict__, "encrypt": False}).validate(write=False)
    settings().validate(write=False)


def test_factory_configuration_writes_require_only_explicit_sql_gates() -> None:
    settings().validate(write=True)


def test_configuration_writes_still_require_dba_permission_confirmation() -> None:
    repository = SQLServerConfigurationRepository(
        settings=settings(writes_confirmed=False),
        connect_factory=lambda *_args, **_kwargs: pytest.fail("must not connect"),
    )
    with pytest.raises(ConfigurationUnavailable, match="schema-scoped permissions"):
        repository.create_cutoff_version(
            effective_from="2026-12-01",
            cutoff_time="07:00",
            time_zone="Asia/Bangkok",
            base_version_id=1,
            reason="Test change",
            current_production_date="2026-11-10",
        )


def test_factory_mode_allows_integrated_sql_identity_only_after_explicit_gates() -> None:
    integrated = settings(username="", password="", trusted_connection=True)
    integrated.validate(write=True)
    assert "Trusted_Connection=yes" in integrated.connection_string()
    assert "UID=" not in integrated.connection_string()
