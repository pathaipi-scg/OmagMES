from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "db" / "review-only" / "004_press_diff_lot_acc_views.sql"
PREFLIGHT = ROOT / "db" / "review-only" / "004_preflight.sql"
VALIDATOR = ROOT / "db" / "review-only" / "004_validate.sql"
ROLLBACK = ROOT / "db" / "review-only" / "004_rollback.sql"
READER_GRANTS = ROOT / "db" / "review-only" / "004_optional_reader_grants.sql"
CANDIDATE_GRANTS = ROOT / "db" / "review-only" / "004_optional_candidate_grants.sql"
QUALITY_INDEPENDENT_PATCH = ROOT / "db" / "patches" / "005_press_daily_diff_quality_independent.sql"


def test_review_migration_declares_sql_views_as_the_diff_acc_authority() -> None:
    sql = MIGRATION.read_text(encoding="utf-8")
    for view in (
        "v_PressDailyDiff", "v_PressLotDiff", "v_PressLotACC",
        "v_PressDiffReconciliation", "v_PressLotSummary",
    ):
        expected = f"CREATE OR ALTER VIEW omagmes.{view}" if view == "v_PressDailyDiff" else f"CREATE VIEW omagmes.{view}"
        assert expected in sql
    assert "LAG(s.CounterValue) OVER (ORDER BY s.RecTime, s.SourceID)" in sql
    assert "ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW" in sql
    assert "DiffStatus = 'POSITIVE_DELTA'" in sql
    assert "RESET_BASELINE_NOT_CREDITED" in sql
    assert "WHEN m.OfficialMatchCount = 1 THEN 'OFFICIAL'" in sql
    assert "OfficialProductionLotID IS NULL" in sql
    assert "Diff IS NULL" in sql
    assert "c.InitialProposedStartTime" in sql
    assert "c.EffectiveStartTime" in sql
    assert "w.OriginalProposedStartTime" in sql


def test_source_timestamp_precision_and_null_timestamp_rows_are_handled_explicitly() -> None:
    sql = MIGRATION.read_text(encoding="utf-8")
    assert "CONVERT(datetime2(7), p._TIMESTAMP) AS RecTime" in sql
    assert "AND p._TIMESTAMP IS NOT NULL" in sql
    assert "p._NAME COLLATE Latin1_General_100_BIN2 = 'OMAG.PRESS.OEE.DropCnt'" in sql
    assert "datetime2(3)" not in sql
    assert "BOUNDARY_INTERVAL_OVERLAP" not in sql
    assert "BETWEEN 0 AND 9223372036854775807" in sql
    assert "LAG(s.CurrentValueValid) OVER (ORDER BY s.RecTime, s.SourceID) AS PreviousValueValid" in sql
    assert "NULL source timestamps are excluded from ordered Diff rows" in sql


def test_lot_allocation_uses_current_sample_time_even_when_previous_sample_is_in_prior_lot() -> None:
    sql = MIGRATION.read_text(encoding="utf-8")
    assert "ON d.RecTime >= w.StartTime" in sql
    assert "(w.EndTime IS NULL OR d.RecTime < w.EndTime)" in sql
    assert "d.PreviousRecTime >= w.StartTime" not in sql
    assert "AND d.PreviousRecTime < w.EndTime" not in sql
    assert "d.RecTime < w.EndTime" in sql
    assert "OfficialMatchCount = 1 AND c.CandidateMatchCount > 0 THEN 'ALLOCATED_OFFICIAL_PRECEDENCE'" in sql
    assert "WHEN c.OfficialMatchCount > 1 THEN 'AMBIGUOUS_OFFICIAL_OVERLAP'" in sql
    assert "WHEN c.CandidateMatchCount > 1 THEN 'AMBIGUOUS_CANDIDATE_OVERLAP'" in sql
    assert "WHEN c.CandidateMatchCount = 1 THEN 'ALLOCATED_CANDIDATE'" in sql


def test_quality_never_gates_diff_and_counter_statuses_cover_increase_duplicate_and_reset() -> None:
    sql = MIGRATION.read_text(encoding="utf-8")
    patch = QUALITY_INDEPENDENT_PATCH.read_text(encoding="utf-8")
    daily_view = sql.split("CREATE OR ALTER VIEW omagmes.v_PressDailyDiff", 1)[1].split("\nGO", 1)[0]
    patch_view = patch.split("CREATE OR ALTER VIEW omagmes.v_PressDailyDiff", 1)[1].split("\nGO", 1)[0]
    for view_definition in (daily_view, patch_view):
        assert "PressDiffQualityPolicy" not in view_definition
        assert "QUALITY_POLICY_MISSING" not in view_definition
        assert "PREVIOUS_QUALITY_POLICY_MISSING" not in view_definition
        assert "WHEN d.CounterValue < d.PreviousCounterValue THEN 'RESET_BASELINE_NOT_CREDITED'" in view_definition
        assert "WHEN d.CounterValue = d.PreviousCounterValue THEN 'UNCHANGED'" in view_definition
        assert "WHEN c.DiffStatus = 'POSITIVE_DELTA'" in view_definition
        assert "THEN CONVERT(bigint, 0)" in view_definition
    assert "CREATE OR ALTER VIEW omagmes.v_PressDailyDiff" in patch
    assert "CREATE OR ALTER VIEW omagmes.v_PressLotDiff" not in patch
    assert re.search(r"^\s*DROP\s+TABLE\b", patch, re.IGNORECASE | re.MULTILINE) is None
    assert re.search(r"^\s*DELETE\s+FROM\b", patch, re.IGNORECASE | re.MULTILINE) is None
    assert re.search(r"^\s*(CREATE|ALTER)\s+TABLE\b", patch, re.IGNORECASE | re.MULTILINE) is None
    assert re.search(r"^\s*(INSERT|UPDATE)\s+", patch, re.IGNORECASE | re.MULTILINE) is None
    assert patch.count("CREATE OR ALTER VIEW") == 1
    assert "dbo.PRESS" in patch
    assert "SET IsAccepted" not in patch


def test_preflight_and_post_deployment_validator_are_select_only() -> None:
    for path in (PREFLIGHT, VALIDATOR):
        sql = path.read_text(encoding="utf-8")
        assert re.search(r"^\s*(INSERT|UPDATE|DELETE|CREATE|ALTER|DROP)\b", sql, re.IGNORECASE | re.MULTILINE) is None
    preflight = PREFLIGHT.read_text(encoding="utf-8")
    assert "MIGRATION_004_NAME_COLLISION" in preflight
    assert "ProductionLot" in preflight
    assert "REQUIRED_COLUMN_AND_TYPE" in preflight
    assert "LotStartedAt" in preflight
    assert "LotEndedAt" in preflight
    assert "compatibility_level" in preflight
    validator = VALIDATOR.read_text(encoding="utf-8")
    assert "DECLARE @required" not in validator
    assert "INSERT INTO @required" not in validator
    assert "still depends on PressDiffQualityPolicy" in validator


def test_destructive_rollback_refuses_any_policy_or_candidate_data() -> None:
    sql = ROLLBACK.read_text(encoding="utf-8")
    assert "IF EXISTS (SELECT 1 FROM omagmes.PressDiffQualityPolicy)" in sql
    assert "OR EXISTS (SELECT 1 FROM omagmes.AutoLotCandidateWindow)" in sql
    assert "OR EXISTS (SELECT 1 FROM omagmes.AutoLotCandidateWindowHistory)" in sql
    assert "Rollback refused because policy/candidate/audit rows exist" in sql


def test_review_migration_keeps_candidate_data_in_application_schema_and_audits_edits() -> None:
    sql = MIGRATION.read_text(encoding="utf-8")
    assert "CREATE TABLE omagmes.AutoLotCandidateWindow (" in sql
    assert "CREATE TABLE omagmes.AutoLotCandidateWindowHistory (" in sql
    assert "id bigint IDENTITY(1,1)" in sql
    assert "Rectime datetime NOT NULL" in sql
    assert "CandidateKey nvarchar(200)" in sql
    assert "OperatorTimeOverride bit" in sql
    assert "OfficialProductionLotID bigint NULL" in sql
    assert "CREATE TABLE dbo." not in sql
    assert "UPDATE OMAG.dbo.PRESS" not in sql
    assert "INSERT INTO OMAG.dbo.PRESS" not in sql


def test_legacy_quality_policy_table_is_unseeded_and_migration_is_review_only() -> None:
    sql = MIGRATION.read_text(encoding="utf-8")
    assert "REVIEW-ONLY DRAFT" in sql
    assert "_QUALITY is informational and never gates Diff" in sql
    assert "INSERT omagmes.PressDiffQualityPolicy" not in sql


def test_migration_grants_view_reads_only_not_candidate_or_policy_writes() -> None:
    sql = MIGRATION.read_text(encoding="utf-8")
    grants = re.findall(r"^\s*GRANT\b[^;]+;", sql, re.IGNORECASE | re.MULTILINE)
    assert grants
    assert all(re.search(r"\b(INSERT|UPDATE|DELETE|ALTER|CONTROL)\b", grant, re.IGNORECASE) is None for grant in grants)
    assert all("OBJECT::omagmes.v_" in grant for grant in grants)


def test_migration_transaction_covers_all_view_creation_and_grants() -> None:
    sql = MIGRATION.read_text(encoding="utf-8")
    begin = sql.index("BEGIN TRANSACTION;")
    first_view = sql.index("CREATE OR ALTER VIEW omagmes.v_PressDailyDiff")
    last_view = sql.index("CREATE VIEW omagmes.v_PressLotSummary")
    commit = sql.index("COMMIT TRANSACTION;")
    assert begin < first_view < last_view < commit
    assert sql.index("GRANT SELECT ON OBJECT::omagmes.v_PressDiffReconciliation") < commit


def test_optional_grants_separate_grafana_readers_from_gated_candidate_writes() -> None:
    reader = READER_GRANTS.read_text(encoding="utf-8")
    candidate = CANDIDATE_GRANTS.read_text(encoding="utf-8")
    assert re.search(r"\bGRANT\s+SELECT\b", reader, re.IGNORECASE)
    assert "OMAGMES_GRAFANA" in reader
    assert re.search(r"\b(INSERT|UPDATE|DELETE|ALTER|CONTROL)\b", reader, re.IGNORECASE) is None
    assert "GRANT SELECT, INSERT, UPDATE ON OBJECT::omagmes.AutoLotCandidateWindow" in candidate
    assert "GRANT SELECT, INSERT ON OBJECT::omagmes.AutoLotCandidateWindowHistory" in candidate
    assert "OMAGMES_AUTOLOT_SYNC_ENABLED" not in candidate
    assert "ProductionLot" not in candidate
    assert "PressDiffQualityPolicy" not in candidate
    assert not re.search(r"\bGRANT\s+DELETE\b", candidate, re.IGNORECASE)
