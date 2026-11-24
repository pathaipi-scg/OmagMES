/*
OPTIONAL, REVIEW-ONLY Grafana view-reader grant. Separate from all write gates.
Run only after the owner approves a dedicated OMAGMES_GRAFANA principal.
No database user is created and no raw dbo.PRESS rights are granted.
*/
SET NOCOUNT ON;
IF DB_NAME() <> N'OMAG'
    THROW 53430, 'Optional Migration 004 reader grants only apply to OMAG.', 1;
IF DATABASE_PRINCIPAL_ID(N'OMAGMES_GRAFANA') IS NULL
    THROW 53431, 'Create/review the dedicated OMAGMES_GRAFANA principal before granting view access.', 1;
IF OBJECT_ID(N'omagmes.v_PressDailyDiff', N'V') IS NULL
   OR OBJECT_ID(N'omagmes.v_PressLotDiff', N'V') IS NULL
   OR OBJECT_ID(N'omagmes.v_PressLotACC', N'V') IS NULL
   OR OBJECT_ID(N'omagmes.v_PressDiffReconciliation', N'V') IS NULL
   OR OBJECT_ID(N'omagmes.v_PressLotSummary', N'V') IS NULL
    THROW 53432, 'Migration 004 views must exist before optional reader grants.', 1;
GRANT SELECT ON OBJECT::omagmes.v_PressDailyDiff TO [OMAGMES_GRAFANA];
GRANT SELECT ON OBJECT::omagmes.v_PressLotDiff TO [OMAGMES_GRAFANA];
GRANT SELECT ON OBJECT::omagmes.v_PressLotACC TO [OMAGMES_GRAFANA];
GRANT SELECT ON OBJECT::omagmes.v_PressDiffReconciliation TO [OMAGMES_GRAFANA];
GRANT SELECT ON OBJECT::omagmes.v_PressLotSummary TO [OMAGMES_GRAFANA];
GO
