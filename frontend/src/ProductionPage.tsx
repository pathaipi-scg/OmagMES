import { useCallback, useEffect, useMemo, useState } from 'react';
import './auto-lot-actions.css';

type Assignment = {
  plan_key: string;
  plan_name: string | null;
  material_code: string | null;
  material_name: string | null;
  product_id: number | null;
  product_code: string | null;
  product_name: string | null;
  mould_id: number | null;
  mould_code: string | null;
  mould_name: string | null;
};
type AutoLotViewRow = {
  ProdDate: string;
  ShiftType: number | string | null;
  LotNo: string;
  rw: number | null;
  LotStart: string | null;
  LotStop: string | null;
  ShiftNo: string | null;
  StartTime: string | null;
  StopTime: string | null;
  pDropCnt: number | null;
  DropCnt: number | null;
  auto_lot_id?: number | null;
  assignment?: Assignment | null;
};
type ProductMatch = {
  status: 'MATCHED' | 'AMBIGUOUS' | 'PRODUCT NOT FOUND';
  product_id: number | null;
  product_code: string | null;
  product_name: string | null;
  product_name_thai: string | null;
};
type Plan = {
  plan_key: string;
  duplicate_count: number;
  plan_name: string | null;
  material_code: string | null;
  material_name: string | null;
  planned_start: string | null;
  plan_count: string | number | null;
  machine: string | null;
  shift: string | null;
  product_match: ProductMatch;
};
type Mould = { id: number; product_id: number; code: string; name: string | null; status: string };
type ProductionOverview = {
  production_date: string;
  source: string;
  auto_lots: AutoLotViewRow[];
  press_available: boolean;
  press_error: string | null;
  press_warnings: string[];
  auto_lot_status: string;
  assignment_available: boolean;
  assignment_error: string | null;
};
type PlanResponse = { plans: Plan[]; warnings: string[]; truncated: boolean; assignment_available: boolean };
type Props = { productionDate: string; reloadKey: number };

async function getJson<T>(url: string): Promise<T> {
  const response = await fetch(url, { headers: { 'Content-Type': 'application/json' } });
  if (!response.ok) {
    const body = await response.json().catch(() => null) as { detail?: string } | null;
    throw new Error(body?.detail ?? `Request failed (${response.status})`);
  }
  return response.json() as Promise<T>;
}

async function postJson<T>(url: string, value: unknown): Promise<T> {
  const response = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(value),
  });
  if (!response.ok) {
    const body = await response.json().catch(() => null) as { detail?: string } | null;
    throw new Error(body?.detail ?? `Request failed (${response.status})`);
  }
  return response.json() as Promise<T>;
}

function rowKey(row: AutoLotViewRow, index: number) {
  return `${row.LotStart ?? ''}|${row.LotNo}|${index}`;
}

function displayTime(value: string | null | undefined) {
  if (!value) return '';
  const match = value.match(/(?:T|\s)(\d{2}:\d{2})/);
  return match?.[1] ?? value.slice(0, 5);
}

function planLabel(plan: Plan) {
  const identity = [plan.plan_name, plan.material_name, plan.material_code]
    .filter((value): value is string => Boolean(value?.trim()))
    .join(' · ');
  const schedule = [plan.planned_start, plan.machine, plan.shift]
    .filter((value): value is string => Boolean(value?.trim()))
    .join(' · ');
  return [identity, schedule, plan.duplicate_count > 1 ? `duplicate ×${plan.duplicate_count}` : '']
    .filter(Boolean)
    .join(' — ');
}

export default function ProductionPage({ productionDate, reloadKey }: Props) {
  const [overview, setOverview] = useState<ProductionOverview | null>(null);
  const [plans, setPlans] = useState<Plan[]>([]);
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const [selectedPlanKey, setSelectedPlanKey] = useState('');
  const [selectedMouldId, setSelectedMouldId] = useState('');
  const [moulds, setMoulds] = useState<Mould[]>([]);
  const [loading, setLoading] = useState(false);
  const [plansLoading, setPlansLoading] = useState(false);
  const [mouldsLoading, setMouldsLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [plansError, setPlansError] = useState('');
  const [mouldsError, setMouldsError] = useState('');
  const [notice, setNotice] = useState('');

  const loadOverview = useCallback(async () => {
    if (!productionDate) return;
    setLoading(true);
    setError('');
    let reconciliationError = '';
    try {
      try {
        await postJson('/api/auto-lots/reconcile', { production_date: productionDate });
      } catch (cause) {
        reconciliationError = cause instanceof Error ? cause.message : 'AutoLot identity synchronization failed.';
      }
      const result = await getJson<ProductionOverview>(
        `/api/production/overview?production_date=${encodeURIComponent(productionDate)}`,
      );
      if (reconciliationError) {
        result.assignment_available = false;
        result.assignment_error = `AutoLot identity synchronization failed; assignments are disabled. ${reconciliationError}`;
      }
      setOverview(result);
      if (result.press_error) setError(result.press_error);
    } catch (cause) {
      setOverview(null);
      setError(cause instanceof Error ? cause.message : 'Auto Lots could not be loaded.');
    } finally {
      setLoading(false);
    }
  }, [productionDate]);

  const loadPlans = useCallback(async () => {
    if (!productionDate) return;
    setPlansLoading(true);
    setPlansError('');
    try {
      const result = await getJson<PlanResponse>(
        `/api/press-lots/plans?production_date=${encodeURIComponent(productionDate)}`,
      );
      setPlans(result.plans);
      if (!result.assignment_available) setPlansError('Plan assignments are disabled because the source result is incomplete.');
    } catch (cause) {
      setPlans([]);
      setPlansError(cause instanceof Error ? cause.message : 'Production Plans could not be loaded.');
    } finally {
      setPlansLoading(false);
    }
  }, [productionDate]);

  useEffect(() => {
    setSelectedKey(null);
    setSelectedPlanKey('');
    setSelectedMouldId('');
    setMoulds([]);
    setNotice('');
    void loadPlans();
  }, [loadPlans]);
  useEffect(() => { void loadOverview(); }, [loadOverview, reloadKey]);

  const rows = overview?.auto_lots ?? [];
  const selectedIndex = rows.findIndex((row, index) => rowKey(row, index) === selectedKey);
  const selectedRow = selectedIndex >= 0 ? rows[selectedIndex] : null;
  const selectedAssignment = selectedRow?.assignment ?? null;
  const selectedPlan = plans.find((plan) => plan.plan_key === selectedPlanKey) ?? null;
  const productMatch = selectedPlan?.product_match ?? null;
  const validPlan = Boolean(selectedPlan && selectedPlan.duplicate_count === 1);
  const resolvedProductId = productMatch?.status === 'MATCHED'
    ? productMatch.product_id
    : selectedAssignment?.plan_key === selectedPlanKey ? selectedAssignment.product_id : null;
  const resolvedProductName = productMatch?.status === 'MATCHED'
    ? productMatch.product_name
    : selectedAssignment?.plan_key === selectedPlanKey ? selectedAssignment.product_name : null;
  const selectedAutoLotId = selectedRow?.auto_lot_id ?? null;
  const canEditAssignment = Boolean(selectedRow);
  const canSave = Boolean(
    canEditAssignment && selectedAutoLotId && overview?.assignment_available
    && validPlan && productMatch?.status === 'MATCHED'
    && resolvedProductId && selectedMouldId && moulds.some((mould) => String(mould.id) === selectedMouldId),
  );

  useEffect(() => {
    let cancelled = false;
    if (!resolvedProductId) {
      setMoulds([]);
      setMouldsError('');
      return () => { cancelled = true; };
    }
    setMouldsLoading(true);
    setMouldsError('');
    void getJson<{ moulds: Mould[] }>(`/api/products/${resolvedProductId}/active-moulds`)
      .then((result) => {
        if (!cancelled) setMoulds(result.moulds);
      })
      .catch((cause: unknown) => {
        if (!cancelled) {
          setMoulds([]);
          setMouldsError(cause instanceof Error ? cause.message : 'Compatible Moulds could not be loaded.');
        }
      })
      .finally(() => { if (!cancelled) setMouldsLoading(false); });
    return () => { cancelled = true; };
  }, [resolvedProductId, selectedKey]);

  const selectedPlanLabel = useMemo(() => {
    if (selectedPlan) return planLabel(selectedPlan);
    if (selectedAssignment?.plan_key === selectedPlanKey) {
      return [selectedAssignment.plan_name, selectedAssignment.material_name, selectedAssignment.material_code]
        .filter(Boolean).join(' · ');
    }
    return '';
  }, [selectedPlan, selectedAssignment, selectedPlanKey]);

  function selectLot(row: AutoLotViewRow, index: number) {
    setSelectedKey(rowKey(row, index));
    setSelectedPlanKey(row.assignment?.plan_key ?? '');
    setSelectedMouldId(row.assignment?.mould_id ? String(row.assignment.mould_id) : '');
    setMouldsError('');
    setNotice('');
  }

  async function saveAssignment() {
    if (!selectedAutoLotId || !selectedPlanKey || !selectedMouldId || !canSave) return;
    setSaving(true);
    setNotice('');
    setError('');
    try {
      await postJson(`/api/auto-lots/${selectedAutoLotId}/assignment`, {
        plan_key: selectedPlanKey,
        mould_id: Number(selectedMouldId),
      });
      setNotice(`Assignment saved for ${selectedRow?.LotNo ?? 'the selected Lot'}.`);
      await loadOverview();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Assignment was not saved.');
    } finally {
      setSaving(false);
    }
  }

  function handlePlanChange(value: string) {
    setSelectedPlanKey(value);
    setSelectedMouldId('');
    setMoulds([]);
    setMouldsError('');
    setNotice('');
  }

  return <section className="om-production om-auto-assignment" aria-label="Production Lots">
    {error && <div className="om-production-alert error" role="alert">{error}</div>}
    {overview?.press_warnings.map((warning) => <p className="om-production-table-note" key={warning} role="status">{warning}</p>)}
    {loading && <div className="om-production-table-note" role="status">Loading Lots directly from the SQL view…</div>}

    <h3 className="om-auto-lot-heading">PRODUCTION LOT · {rows.length}</h3>
    <div className="om-production-table-wrap">
      <table className="om-production-table om-auto-lot-table">
        <thead><tr>
          <th className="om-select-col">Select</th><th>Lot No.</th><th>Plan</th><th>Product</th>
          <th>Mould</th><th>Shift</th><th>Start</th><th>End</th><th>Counter</th>
        </tr></thead>
        <tbody>
          {rows.map((row, index) => {
            const key = rowKey(row, index);
            const assignment = row.assignment;
            return <tr key={key} className={selectedKey === key ? 'is-selected' : ''} onClick={() => selectLot(row, index)}>
              <td className="om-select-col"><input
                aria-label={`Select Lot ${row.LotNo}`}
                type="radio"
                name="selected-auto-lot"
                checked={selectedKey === key}
                onChange={() => selectLot(row, index)}
              /></td>
              <td><strong>{row.LotNo}</strong></td>
              <td>{assignment?.plan_name ?? ''}</td>
              <td>{assignment?.product_name ?? ''}</td>
              <td>{assignment?.mould_name || assignment?.mould_code || ''}</td>
              <td>{row.ShiftNo ?? ''}</td>
              <td>{displayTime(row.LotStart)}</td>
              <td>{displayTime(row.LotStop)}</td>
              <td>{row.DropCnt ?? ''}</td>
            </tr>;
          })}
          {!rows.length && !loading && !error && <tr><td colSpan={9} className="om-production-empty">No Auto Lots for this Production Date.</td></tr>}
        </tbody>
      </table>
    </div>

    <section className="om-assign-lot-panel" aria-label="Assign Production Plan and Mould">
      <h3>ASSIGN LOT <span>{selectedRow?.LotNo ?? ''}</span></h3>
      {overview?.assignment_error && <p className="om-assignment-note" role="status">{overview.assignment_error}</p>}
      {plansError && <p className="om-assignment-warning" role="alert">Production Plans unavailable: {plansError}</p>}
      {selectedPlan && selectedPlan.duplicate_count > 1 && <p className="om-assignment-warning" role="alert">This Plan appears more than once in the source and cannot be assigned safely.</p>}
      {selectedPlan && productMatch?.status !== 'MATCHED' && <p className="om-assignment-warning" role="alert">No unique active Product matches this Plan MaterialCode. SAVE is disabled; no Product will be created or guessed.</p>}
      {mouldsError && <p className="om-assignment-warning" role="alert">{mouldsError}</p>}
      {notice && <p className="om-assignment-success" role="status">{notice}</p>}
      <div className="om-assign-grid" aria-label="Lot assignment fields">
        <label className="om-assign-field"><span>Production Plan</span><div className="om-assign-plan-control">
          <select aria-label="Production Plan" value={selectedPlanKey} disabled={!canEditAssignment || plansLoading || saving} onChange={(event) => handlePlanChange(event.target.value)}>
            <option value="">Select a plan</option>
            {selectedAssignment?.plan_key && !plans.some((plan) => plan.plan_key === selectedAssignment.plan_key) && <option value={selectedAssignment.plan_key}>{selectedPlanLabel}</option>}
            {plans.map((plan) => <option key={plan.plan_key} value={plan.plan_key}>{planLabel(plan)}</option>)}
          </select>
          <button type="button" className="button secondary" disabled={!canEditAssignment || plansLoading || saving} onClick={() => void loadPlans()}>{plansLoading ? 'LOADING…' : 'PLAN REFRESH'}</button>
        </div></label>
        <div className="om-assign-field"><span>Product</span><div className="om-assign-product">{resolvedProductName ?? ''}</div></div>
        <label className="om-assign-field"><span>Mould</span><select
          aria-label="Mould"
          value={selectedMouldId}
          disabled={!canEditAssignment || !resolvedProductId || mouldsLoading || saving}
          onChange={(event) => { setSelectedMouldId(event.target.value); setNotice(''); }}
        >
          <option value="">Select ACTIVE Mould</option>
          {selectedMouldId && !moulds.some((mould) => String(mould.id) === selectedMouldId) && selectedAssignment?.mould_id === Number(selectedMouldId) && <option value={selectedMouldId}>{selectedAssignment.mould_name || selectedAssignment.mould_code}</option>}
          {moulds.map((mould) => <option key={mould.id} value={mould.id}>{mould.code}{mould.name ? ` · ${mould.name}` : ''}</option>)}
        </select></label>
        <div className="om-assign-field"><span>Action</span><button type="button" className="button primary" disabled={!canSave || saving} onClick={() => void saveAssignment()}>{saving ? 'SAVING…' : 'SAVE'}</button></div>
      </div>
      {selectedPlanKey && productMatch?.status === 'MATCHED' && !mouldsLoading && !moulds.length && <p className="om-assignment-warning" role="status">No active Mould is registered to this Product.</p>}
      {selectedPlanKey && validPlan && productMatch?.status === 'MATCHED' && <span className="om-assignment-plan-detail">{selectedPlanLabel}</span>}
    </section>
  </section>;
}
