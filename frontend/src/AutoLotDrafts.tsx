import { useCallback, useEffect, useState } from 'react';
import type { ShiftScheduleContext } from './ShiftSchedule';
import { loadProductionPlans, type ProductionPlan } from './productionPlans';

export type ResetCandidate = {
  id: string;
  source_tag: string;
  production_date: string | null;
  shift_id: number | null;
  shift_assignment: string;
  shift_code: string | null;
  configuration_attribution: string;
  before_sample: { source_id: string; timestamp: string; value: number };
  decrease_sample: { source_id: string; timestamp: string; value: number };
  reset_time_interval: { earliest_exclusive: string; latest_inclusive: string };
  restart_sample: { source_id: string; timestamp: string; value: number } | null;
  timestamp_basis: string;
  candidate_status: string;
  proposed_scg_lot_number?: string | null;
  official_lot_id: null;
  warnings: string[];
};
type CandidateResponse = {
  available: boolean;
  status?: string;
  source_timezone_confirmed?: boolean;
  candidates: unknown[];
  reset_candidates?: ResetCandidate[];
  reset_analysis_warnings?: string[];
  warnings: string[];
  quality_counts_observed?: Record<string, number>;
  sql_access?: {
    server?: string;
    instance?: string;
    database?: string;
    sql_login?: string;
    database_user?: string;
    sysadmin_member?: boolean;
    read_only_permissions_verified?: boolean;
    write_capabilities_present?: string[];
    source_queries_select_only_enforced?: boolean;
  };
  production_day_window?: { start_at: string; end_at_exclusive: string; time_zone: string; interval_semantics: string };
  cutoff_version_id: number;
  review_storage?: string;
};
type SqlLotSummary = {
  LotIdentityType: 'OFFICIAL' | 'CANDIDATE';
  LotIdentityID: number;
  OfficialProductionLotID: number | null;
  CandidateWindowID: number | null;
  LotNumber: string | null;
  LotStatus: string;
  LotName: string | null;
  ProductID: number | null;
  ColorCode: string | null;
  StartTime: string;
  EndTime: string | null;
  OriginalProposedStartTime: string | null;
  OriginalProposedEndTime: string | null;
  CurrentProposedStartTime: string | null;
  CurrentProposedEndTime: string | null;
  OperatorTimeOverride: boolean;
  ProductionDate: string | null;
  ShiftID: number | null;
  CalculatedPressQty: number;
  LatestLotACC: number;
  LatestDiffAt: string | null;
  AmbiguousEventCount: number;
  BoundaryOverlapEventCount: number;
  QualityWarningCount: number;
  ResetEventCount: number;
  HasDataWarnings: boolean;
};
type AutoCandidate = {
  id: number;
  CandidateKey: string;
  CandidateKind: string;
  CandidateStatus: string;
  ProductionDate: string | null;
  EffectiveStartTime: string;
  EffectiveEndTime: string | null;
  OperatorBoundaryConfirmed: boolean;
  ProductID: number | null;
  ColorCode: string | null;
  PlanSourceKey: string | null;
  PlanSnapshotJson: string | null;
  PlanMaterialCode: string | null;
  PlanMatchStatus: string | null;
  OperatorTimeOverride: boolean;
};
type CandidateHistory = { id: number; ActionCode: string; ChangedBy: string; ChangedAt: string; ChangeReason: string; PreviousStateJson: string | null; NewStateJson: string | null };
type SqlWindowEdit = { startAt: string; endAt: string; startEdited: boolean; endEdited: boolean; operatorId: string; reason: string; splitAt: string; mergeId: string };

async function call<T>(path: string, method = 'GET', body?: unknown): Promise<T> {
  const response = await fetch(path, {
    method,
    headers: { 'Content-Type': 'application/json' },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  });
  if (!response.ok) {
    const result = await response.json().catch(() => null) as { detail?: string } | null;
    throw new Error(result?.detail ?? `Candidate request failed (${response.status})`);
  }
  return response.json() as Promise<T>;
}

function localDateTime(value: string) {
  return value.slice(0, 16);
}

function bangkokDateTime(value: string) {
  return value ? `${value}:00+07:00` : null;
}

function exactBangkokDateTime(value: string | null) {
  return value ? `${value.replace(' ', 'T')}+07:00` : null;
}

export default function AutoLotDrafts({ productionDate, schedule, onSelectReset }: { productionDate: string; schedule: ShiftScheduleContext | null; onSelectReset?: (candidate: ResetCandidate | null) => void }) {
  const [result, setResult] = useState<CandidateResponse | null>(null);
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);
  const [selectedResetId, setSelectedResetId] = useState('');
  const [sqlLots, setSqlLots] = useState<SqlLotSummary[]>([]);
  const [candidateRows, setCandidateRows] = useState<AutoCandidate[]>([]);
  const [candidateListError, setCandidateListError] = useState('');
  const [plans, setPlans] = useState<ProductionPlan[]>([]);
  const [plansTruncated, setPlansTruncated] = useState(false);
  const [plansWarning, setPlansWarning] = useState('');
  const [planSelections, setPlanSelections] = useState<Record<number, string>>({});
  const [classifications, setClassifications] = useState<Record<number, { productId: string; colorCode: string }>>({});
  const [histories, setHistories] = useState<Record<number, CandidateHistory[]>>({});
  const [sqlLotsError, setSqlLotsError] = useState('');
  const [windowEdits, setWindowEdits] = useState<Record<string, SqlWindowEdit>>({});
  const [newWindow, setNewWindow] = useState<SqlWindowEdit>({ startAt: '', endAt: '', startEdited: false, endEdited: false, operatorId: '', reason: '', splitAt: '', mergeId: '' });
  const timestampLabel = result?.source_timezone_confirmed ? 'Bangkok' : 'raw SQL wall clock · timezone unverified';

  function updateSqlLots(rows: SqlLotSummary[], resetEdits = false) {
    setSqlLots(rows);
    setWindowEdits((current) => {
      const next = { ...current };
      for (const lot of rows) {
        const key = `${lot.LotIdentityType}-${lot.LotIdentityID}`;
        const previous = current[key];
        const times = {
          startAt: localDateTime(lot.StartTime), endAt: lot.EndTime ? localDateTime(lot.EndTime) : '',
          startEdited: false, endEdited: false,
        };
        if (previous && !resetEdits && (previous.startEdited || previous.endEdited)) continue;
        next[key] = { ...times, operatorId: previous?.operatorId ?? '', reason: previous?.reason ?? '', splitAt: previous?.splitAt ?? '', mergeId: previous?.mergeId ?? '' };
      }
      return next;
    });
  }

  const reload = useCallback(async (resetEdits = false) => {
    const params = new URLSearchParams({ production_date: productionDate });
    const [response, summaryResult, candidateResult] = await Promise.all([
      call<CandidateResponse>(`/api/auto-lot/candidates?${params}`),
      call<{ rows: SqlLotSummary[] }>(`/api/press-lots/summary?${new URLSearchParams({ production_date: productionDate })}`).then(
        (value) => ({ value, error: '' }),
        (error: unknown) => ({ value: null, error: error instanceof Error ? error.message : 'SQL Lot summary unavailable.' }),
      ),
      call<{ rows: AutoCandidate[] }>(`/api/press-lots/windows?include_deleted=true`).then(
        (value) => ({ value, error: '' }),
        (error: unknown) => ({ value: null, error: error instanceof Error ? error.message : 'Candidate master unavailable.' }),
      ),
    ]);
    setResult(response);
    setCandidateRows(candidateResult.value?.rows ?? []);
    setCandidateListError(candidateResult.error);
    updateSqlLots(summaryResult.value?.rows ?? [], resetEdits);
    setSqlLotsError(summaryResult.error);
  }, [productionDate]);

  async function syncDetected() {
    setBusy(true); setMessage('');
    try {
      const response = await call<{ synchronized: Array<{ created: boolean }>; rows_seen: number; truncated: boolean }>(`/api/auto-lot/candidates/sync?${new URLSearchParams({ production_date: productionDate })}`, 'POST');
      await reload(true);
      setMessage(`Detection refresh completed: ${response.rows_seen} SQL proposals checked, ${response.synchronized.filter((item) => item.created).length} candidates created.${response.truncated ? ' The source list was truncated; older proposals were not included.' : ''} No official Lots were created.`);
    } catch (error) { setMessage(error instanceof Error ? error.message : 'Detection refresh failed.'); }
    finally { setBusy(false); }
  }

  async function loadPlans() {
    setBusy(true); setPlansWarning('');
    try {
      const response = await loadProductionPlans();
      setPlans(response.plans);
      setPlansTruncated(response.truncated);
      setPlansWarning([...response.warnings, response.truncated ? 'Plan list is truncated; assignment is disabled until narrowed.' : ''].filter(Boolean).join(' '));
    } catch (error) { setPlansWarning(error instanceof Error ? error.message : 'Production Plan source is unavailable.'); }
    finally { setBusy(false); }
  }

  async function assignPlan(candidate: AutoCandidate) {
    const key = `CANDIDATE-${candidate.id}`;
    const edit = windowEdits[key];
    const planKey = planSelections[candidate.id];
    if (!planKey || !edit?.operatorId.trim() || !edit.reason.trim()) { setMessage('Select a Production Plan and enter operator ID and reason.'); return; }
    setBusy(true); setMessage('');
    try {
      await call(`/api/press-lots/windows/${candidate.id}/plan`, 'POST', { plan_key: planKey, operator_id: edit.operatorId.trim(), reason: edit.reason.trim() });
      await reload(); setMessage('Plan snapshot assigned and audited. Product mapping is exact MaterialCode → ProductCode; Color and actual Lot times were not inferred.');
    } catch (error) { setMessage(error instanceof Error ? error.message : 'Plan assignment failed.'); }
    finally { setBusy(false); }
  }

  async function showHistory(candidateId: number) {
    try {
      const response = await call<{ rows: CandidateHistory[] }>(`/api/press-lots/windows/${candidateId}/history`);
      setHistories((current) => ({ ...current, [candidateId]: response.rows }));
    } catch (error) { setMessage(error instanceof Error ? error.message : 'Candidate history is unavailable.'); }
  }

  async function restoreCandidate(candidate: AutoCandidate) {
    const edit = windowEdits[`CANDIDATE-${candidate.id}`];
    if (!edit?.operatorId.trim() || !edit.reason.trim()) { setMessage('Enter operator ID and reason before restoring.'); return; }
    setBusy(true); setMessage('');
    try {
      await call(`/api/press-lots/windows/${candidate.id}/restore`, 'POST', { operator_id: edit.operatorId.trim(), reason: edit.reason.trim() });
      await reload(); setMessage('Candidate restored; its boundaries and history remain intact.');
    } catch (error) { setMessage(error instanceof Error ? error.message : 'Candidate restore failed.'); }
    finally { setBusy(false); }
  }

  async function classifyCandidate(candidate: AutoCandidate) {
    const edit = windowEdits[`CANDIDATE-${candidate.id}`];
    const value = classifications[candidate.id];
    if (!edit?.operatorId.trim() || !edit.reason.trim() || !value?.productId || !value.colorCode.trim()) {
      setMessage('Enter authoritative Product ID, explicit Color, operator ID, and reason.'); return;
    }
    setBusy(true); setMessage('');
    try {
      await call(`/api/press-lots/windows/${candidate.id}/classify`, 'POST', {
        product_id: Number(value.productId), color_code: value.colorCode.trim(),
        operator_id: edit.operatorId.trim(), reason: edit.reason.trim(),
      });
      await reload(); setMessage('Product/Color classification confirmed and audited. No official Lot was created.');
    } catch (error) { setMessage(error instanceof Error ? error.message : 'Candidate classification failed.'); }
    finally { setBusy(false); }
  }

  useEffect(() => {
    setSelectedResetId('');
    void reload().catch((error: unknown) => setMessage(error instanceof Error ? error.message : 'DropCnt candidate data unavailable.'));
    const refresh = window.setInterval(() => {
      void call<{ rows: SqlLotSummary[] }>(`/api/press-lots/summary?${new URLSearchParams({ production_date: productionDate })}`)
        .then((response) => { updateSqlLots(response.rows); setSqlLotsError(''); })
        .catch((error: unknown) => setSqlLotsError(error instanceof Error ? error.message : 'SQL Lot summary unavailable.'));
    }, 30_000);
    return () => window.clearInterval(refresh);
  }, [reload, productionDate]);

  async function saveWindow(lot: SqlLotSummary) {
    const key = `${lot.LotIdentityType}-${lot.LotIdentityID}`;
    const edit = windowEdits[key];
    if (!edit?.operatorId.trim() || !edit.reason.trim()) { setMessage('Operator ID and reason are required to edit a SQL Lot window.'); return; }
    if (!edit.startEdited && !edit.endEdited) { setMessage('No boundary was edited; the original Auto Lot precision remains unchanged.'); return; }
    setBusy(true); setMessage('');
    try {
      await call(`/api/press-lots/windows/${lot.CandidateWindowID ?? lot.OfficialProductionLotID}`, 'PATCH', {
        start_at: edit.startEdited ? bangkokDateTime(edit.startAt) : exactBangkokDateTime(lot.StartTime),
        end_at: edit.endEdited ? bangkokDateTime(edit.endAt) : exactBangkokDateTime(lot.EndTime),
        operator_id: edit.operatorId.trim(), reason: edit.reason.trim(),
      });
      await reload(true); setMessage('Effective Lot window updated to minute precision. SQL Lot ACC was recalculated; the change is audited.');
    } catch (error) { setMessage(error instanceof Error ? error.message : 'Window update failed.'); }
    finally { setBusy(false); }
  }

  async function createWindow() {
    if (!newWindow.startAt || !newWindow.operatorId.trim() || !newWindow.reason.trim()) { setMessage('Start time, operator ID, and reason are required.'); return; }
    setBusy(true); setMessage('');
    try {
      await call('/api/press-lots/windows', 'POST', {
        start_at: bangkokDateTime(newWindow.startAt), end_at: bangkokDateTime(newWindow.endAt),
        operator_id: newWindow.operatorId.trim(), reason: newWindow.reason.trim(),
      });
      setNewWindow({ startAt: '', endAt: '', startEdited: false, endEdited: false, operatorId: newWindow.operatorId, reason: '', splitAt: '', mergeId: '' });
      await reload(true); setMessage('Working Lot window created at minute precision. SQL Lot ACC was recalculated from the shared view.');
    } catch (error) { setMessage(error instanceof Error ? error.message : 'Window creation failed.'); }
    finally { setBusy(false); }
  }

  async function mutateWindow(lot: SqlLotSummary, action: 'split' | 'dismiss' | 'merge') {
    if (lot.CandidateWindowID === null) return;
    const edit = windowEdits[`${lot.LotIdentityType}-${lot.LotIdentityID}`];
    if (!edit?.operatorId.trim() || !edit.reason.trim()) { setMessage('Operator ID and reason are required.'); return; }
    if (action === 'split' && !edit.splitAt) { setMessage('Enter a split timestamp.'); return; }
    if (action === 'merge' && (!edit.mergeId || Number(edit.mergeId) <= 0)) { setMessage('Enter the source candidate window ID to merge.'); return; }
    setBusy(true); setMessage('');
    try {
      const path = `/api/press-lots/windows/${lot.CandidateWindowID}/${action}`;
      const body = action === 'split'
        ? { split_at: bangkokDateTime(edit.splitAt), operator_id: edit.operatorId.trim(), reason: edit.reason.trim() }
        : action === 'merge'
          ? { source_window_id: Number(edit.mergeId), operator_id: edit.operatorId.trim(), reason: edit.reason.trim() }
          : { operator_id: edit.operatorId.trim(), reason: edit.reason.trim() };
      await call(path, 'POST', body);
      await reload(); setMessage(`SQL working window ${action} completed and audited; Lot ACC refreshed.`);
    } catch (error) { setMessage(error instanceof Error ? error.message : `Window ${action} failed.`); }
    finally { setBusy(false); }
  }

  return <section className="card top-gap" aria-label="Auto Lot SQL windows">
    <div className="card-head"><div><span className="eyebrow">AUTO LOT · SQL WINDOWS</span><h3>Press Lot windows · {productionDate}</h3></div><span className="tag amber">PROVISIONAL WINDOWS ARE NOT OFFICIAL LOTS</span></div>
    <p className="notice-box">Reset evidence proposes provisional window boundaries. SQL Server Views calculate Daily Diff, PressQty, and Lot ACC automatically without operator confirmation. Operators edit effective window boundaries here; Product/Color and official Lot creation remain separate actions.</p>
    {schedule && <div className="gap-summary"><strong>Cutoff v{schedule.cutoff_version_id} window:</strong> {schedule.production_day ? `${schedule.production_day.start_at.replace('T', ' ')} → ${schedule.production_day.end_at_exclusive.replace('T', ' ')} · ${schedule.production_day.time_zone} · ${schedule.production_day.interval_semantics}` : 'Unavailable'}</div>}
    {result?.production_day_window && <div className="draft-source-line">Resolved query interval: {result.production_day_window.start_at.replace('T', ' ')} → {result.production_day_window.end_at_exclusive.replace('T', ' ')} · {result.production_day_window.interval_semantics}</div>}
    {result && <div className={`notice-box ${result.available ? '' : 'warning'}`} role="status">
      <strong>{result.available ? (result.status ?? 'LIVE PRESS READ-ONLY') : 'LIVE SOURCE UNAVAILABLE · FAIL-CLOSED'}</strong>
      {result.sql_access && <div>SQL identity: {result.sql_access.sql_login ?? '—'} / {result.sql_access.database_user ?? '—'} · {result.sql_access.server ?? '—'} · {result.sql_access.instance ?? '—'} · {result.sql_access.database ?? '—'}</div>}
      {result.sql_access?.source_queries_select_only_enforced && <div>Repository SQL guard: SELECT statements only · source grants are {result.sql_access.read_only_permissions_verified ? 'SELECT-only' : `broader than SELECT (${result.sql_access.write_capabilities_present?.join(', ') || (result.sql_access.sysadmin_member ? 'sysadmin' : 'additional rights')})`}</div>}
      {result.quality_counts_observed && <div>Observed quality codes/counts: {Object.entries(result.quality_counts_observed).map(([code, count]) => `${code}: ${count}`).join(' · ') || 'No rows in this window'}</div>}
      {result.warnings.map((warning, index) => <div key={`${index}-${warning}`}>{warning}</div>)}
    </div>}
    <div className="draft-card">
      <div className="draft-card-head"><div><strong>SQL Lot PressQty / ACC</strong><span>Same SQL Server views consumed by OmagMES and Grafana · auto-refresh 30 s</span></div><span className="tag blue">SQL AUTHORITY</span></div>
      <div className="draft-actions"><button className="button secondary" type="button" disabled={busy} onClick={() => void syncDetected()}>Refresh detected windows</button><button className="button secondary" type="button" disabled={busy} onClick={() => void loadPlans()}>Load Production Plans</button></div>
      {candidateListError && <div className="notice-box warning">Candidate master is unavailable (Migration 006 may be pending): {candidateListError}. SQL Lot PressQty/ACC remains independently available below.</div>}
      {sqlLotsError && <div className="notice-box warning">SQL views unavailable: {sqlLotsError}. No Python Diff/ACC fallback is used.</div>}
      {sqlLots.map((lot) => <div className="draft-source-line" key={`${lot.LotIdentityType}-${lot.LotIdentityID}`}>
        <strong>{lot.LotNumber ?? `${lot.LotIdentityType} #${lot.LotIdentityID}`}</strong> · {lot.LotStatus} · Effective SQL window: {lot.StartTime} → {lot.EndTime ?? 'OPEN'} · Product {lot.ProductID ?? '—'} / Color {lot.ColorCode ?? '—'} · PressQty {lot.CalculatedPressQty.toLocaleString()} · ACC {lot.LatestLotACC.toLocaleString()}
        {lot.CandidateWindowID !== null && <div className="draft-source-line">Original Auto Lot suggestion: {lot.OriginalProposedStartTime ?? '—'} → {lot.OriginalProposedEndTime ?? 'OPEN'} · {lot.OperatorTimeOverride ? 'operator-edited effective window' : 'suggestion is currently effective'}.</div>}
        {(lot.HasDataWarnings || lot.AmbiguousEventCount > 0 || lot.BoundaryOverlapEventCount > 0 || lot.QualityWarningCount > 0 || lot.ResetEventCount > 0) && <span className="warning"> · Warnings: overlap {lot.AmbiguousEventCount}, boundary {lot.BoundaryOverlapEventCount}, quality {lot.QualityWarningCount}, reset {lot.ResetEventCount}</span>}
        {lot.CandidateWindowID !== null && <div className="draft-edit-grid">
          {(() => { const key = `${lot.LotIdentityType}-${lot.LotIdentityID}`; const edit = windowEdits[key]; if (!edit) return null; return <>
            <label className="field"><span>Effective start · date + HH:mm · {timestampLabel}</span><input type="datetime-local" step={60} value={edit.startAt} onChange={(event) => setWindowEdits((all) => ({ ...all, [key]: { ...edit, startAt: event.target.value, startEdited: true } }))} /></label>
            <label className="field"><span>Effective end · date + HH:mm · blank means open</span><input type="datetime-local" step={60} value={edit.endAt} onChange={(event) => setWindowEdits((all) => ({ ...all, [key]: { ...edit, endAt: event.target.value, endEdited: true } }))} /></label>
            <label className="field"><span>Operator ID</span><input value={edit.operatorId} onChange={(event) => setWindowEdits((all) => ({ ...all, [key]: { ...edit, operatorId: event.target.value } }))} /></label>
            <label className="field"><span>Change reason</span><input value={edit.reason} onChange={(event) => setWindowEdits((all) => ({ ...all, [key]: { ...edit, reason: event.target.value } }))} /></label>
            <button className="button secondary" type="button" disabled={busy || Boolean(candidateListError)} onClick={() => void saveWindow(lot)}>Save effective window</button>
            <label className="field"><span>Split at · date + HH:mm</span><input type="datetime-local" step={60} value={edit.splitAt} onChange={(event) => setWindowEdits((all) => ({ ...all, [key]: { ...edit, splitAt: event.target.value } }))} /></label>
            <button className="button secondary" type="button" disabled={busy || Boolean(candidateListError)} onClick={() => void mutateWindow(lot, 'split')}>Split window</button>
            <label className="field"><span>Merge source window ID</span><input type="number" min="1" value={edit.mergeId} onChange={(event) => setWindowEdits((all) => ({ ...all, [key]: { ...edit, mergeId: event.target.value } }))} /></label>
            <button className="button secondary" type="button" disabled={busy || Boolean(candidateListError)} onClick={() => void mutateWindow(lot, 'merge')}>Merge into this window</button>
            <button className="button secondary" type="button" disabled={busy || Boolean(candidateListError)} onClick={() => void mutateWindow(lot, 'dismiss')}>Remove working window</button>
          </>; })()}
        </div>}
      </div>)}
      <div className="draft-edit-grid top-gap">
        <label className="field"><span>New working Lot start · date + HH:mm</span><input type="datetime-local" step={60} value={newWindow.startAt} onChange={(event) => setNewWindow((current) => ({ ...current, startAt: event.target.value }))} /></label>
        <label className="field"><span>New working Lot end · date + HH:mm · blank means open</span><input type="datetime-local" step={60} value={newWindow.endAt} onChange={(event) => setNewWindow((current) => ({ ...current, endAt: event.target.value }))} /></label>
        <label className="field"><span>Operator ID</span><input value={newWindow.operatorId} onChange={(event) => setNewWindow((current) => ({ ...current, operatorId: event.target.value }))} /></label>
        <label className="field"><span>Reason</span><input value={newWindow.reason} onChange={(event) => setNewWindow((current) => ({ ...current, reason: event.target.value }))} /></label>
        <button className="button primary" type="button" disabled={busy || Boolean(sqlLotsError) || Boolean(candidateListError)} onClick={() => void createWindow()}>Add working Lot window</button>
      </div>
      <div className="draft-source-line">Operator window changes remain provisional and do not reserve a Lot number or create an official Lot. Official Lot ranges take precedence in SQL allocation.</div>
      {!sqlLotsError && sqlLots.length === 0 && <div className="empty-state compact">No SQL Lot windows are available for this Production Date.</div>}
    </div>
    <div className="draft-card">
      <div className="draft-card-head"><div><strong>Candidate master · operator mapping</strong><span>Only AutoLotCandidateWindow is used; dismissed rows are retained and restorable.</span></div><span className="tag amber">PROVISIONAL</span></div>
      {candidateListError && <div className="notice-box warning">Candidate management awaits Migration 006 and verified SELECT access.</div>}
      {plansWarning && <div className="notice-box warning">Production Plan mapping unavailable or limited: {plansWarning}</div>}
      {candidateRows.filter((candidate) => !candidate.ProductionDate || candidate.ProductionDate === productionDate).map((candidate) => {
        const key = `CANDIDATE-${candidate.id}`;
        const edit = windowEdits[key] ?? { startAt: '', endAt: '', startEdited: false, endEdited: false, operatorId: '', reason: '', splitAt: '', mergeId: '' };
        const history = histories[candidate.id];
        return <article className="draft-source-line" key={candidate.id}>
          <strong>Candidate #{candidate.id}</strong> · {candidate.CandidateKind} · {candidate.CandidateStatus} · Boundary {candidate.OperatorBoundaryConfirmed ? 'operator-confirmed' : 'provisional'} · {candidate.EffectiveStartTime} → {candidate.EffectiveEndTime ?? 'OPEN'} · Product {candidate.ProductID ?? '—'} / Color {candidate.ColorCode ?? 'not assigned'} · Plan {candidate.PlanMaterialCode ?? '—'}
          <div className="draft-edit-grid">
            <label className="field"><span>Operator ID</span><input value={edit.operatorId} onChange={(event) => setWindowEdits((all) => ({ ...all, [key]: { ...edit, operatorId: event.target.value } }))} /></label>
            <label className="field"><span>Reason</span><input value={edit.reason} onChange={(event) => setWindowEdits((all) => ({ ...all, [key]: { ...edit, reason: event.target.value } }))} /></label>
            {candidate.CandidateStatus === 'DISMISSED' ? <button className="button secondary" type="button" disabled={busy || Boolean(candidateListError)} onClick={() => void restoreCandidate(candidate)}>Restore candidate</button> : <>
              <label className="field"><span>Production Plan · snapshot fingerprint</span><select value={planSelections[candidate.id] ?? candidate.PlanSourceKey ?? ''} disabled={!plans.length || busy} onChange={(event) => setPlanSelections((all) => ({ ...all, [candidate.id]: event.target.value }))}>
                <option value="">Select a plan…</option>{plans.map((plan) => <option key={plan.plan_key} value={plan.plan_key} disabled={plan.duplicate_count !== 1}>{plan.plan_name ?? 'Plan'} · {plan.material_code ?? 'no material'} · {plan.planned_start ?? 'no planned start'}{plan.duplicate_count > 1 ? ' · duplicate, not assignable' : ''}</option>)}
              </select></label>
              <button className="button secondary" type="button" disabled={busy || Boolean(candidateListError) || !plans.length || plansTruncated} onClick={() => void assignPlan(candidate)}>Assign/change plan</button>
              <label className="field"><span>Authoritative Product ID</span><input type="number" min="1" value={classifications[candidate.id]?.productId ?? ''} onChange={(event) => setClassifications((all) => ({ ...all, [candidate.id]: { productId: event.target.value, colorCode: all[candidate.id]?.colorCode ?? '' } }))} /></label>
              <label className="field"><span>Operator-confirmed Color</span><input value={classifications[candidate.id]?.colorCode ?? candidate.ColorCode ?? ''} onChange={(event) => setClassifications((all) => ({ ...all, [candidate.id]: { productId: all[candidate.id]?.productId ?? '', colorCode: event.target.value } }))} /></label>
              <button className="button secondary" type="button" disabled={busy || Boolean(candidateListError)} onClick={() => void classifyCandidate(candidate)}>Confirm Product / Color</button>
            </>}
            <button className="button secondary" type="button" disabled={busy || Boolean(candidateListError)} onClick={() => void showHistory(candidate.id)}>Show full history</button>
          </div>
          {history && <div className="draft-source-line">{history.map((item) => <div key={item.id}><strong>{item.ActionCode}</strong> · {item.ChangedAt} · {item.ChangedBy} · {item.ChangeReason}<details><summary>Before / after snapshot</summary><pre>{JSON.stringify({ before: item.PreviousStateJson ? JSON.parse(item.PreviousStateJson) : null, after: item.NewStateJson ? JSON.parse(item.NewStateJson) : null }, null, 2)}</pre></details></div>)}</div>}
        </article>;
      })}
    </div>
    {result?.reset_analysis_warnings?.map((warning) => <div className="draft-source-line" key={warning}>⚠ {warning}</div>)}
    {result?.reset_candidates?.map((event) => <article className="draft-card" key={event.id}>
      <div className="draft-card-head"><div><strong>Possible counter decrease · Product-run evidence only</strong><span>{event.candidate_status} · {event.timestamp_basis}</span></div><span className="tag amber">OPERATOR REVIEW</span></div>
      <div className="draft-source-line">{event.source_tag} · pre-reset {event.before_sample.timestamp} = {event.before_sample.value} → decreased sample {event.decrease_sample.timestamp} = {event.decrease_sample.value}</div>
      <div className="draft-source-line">Reset time is only bracketed: ({event.reset_time_interval.earliest_exclusive}, {event.reset_time_interval.latest_inclusive}) · restart {event.restart_sample ? `${event.restart_sample.timestamp} = ${event.restart_sample.value}` : 'not observed'}</div>
      <div className="draft-source-line">SQL Lot window sync is required before this boundary appears in the shared Lot ACC view. Shift: {event.shift_assignment} · Production Date: {event.production_date ?? 'unresolved'} · {event.configuration_attribution}</div>
      <div className="draft-source-line"><strong>SCG Lot number proposal:</strong> {event.proposed_scg_lot_number ?? 'unavailable · valid machine/shift/date context required'}. This is not an official Lot; no Product or Color is inferred.</div>
      {event.warnings.map((warning) => <div className="draft-source-line" key={warning}>⚠ {warning}</div>)}
      <div className="draft-source-line">Official Lot ID: none · Save requires operator-confirmed Product + Color and explicit SAVE.</div>
      <div className="draft-actions"><button className="button secondary" type="button" disabled={!event.production_date || !event.shift_id || !event.shift_code} onClick={() => {
        const selected = selectedResetId === event.id ? null : event;
        setSelectedResetId(selected?.id ?? '');
        onSelectReset?.(selected);
      }}>{selectedResetId === event.id ? 'Unlink reset evidence' : 'Review Product/Color and link to Lot →'}</button></div>
    </article>)}
    {!result && !message && <div className="empty-state compact">Loading exact-tag DropCnt boundary evidence…</div>}
    {message && <div className="notice-box top-gap" role="status">{message}</div>}
  </section>;
}
