import { useCallback, useEffect, useState } from 'react';
import { loadProductionPlans, type ProductionPlan } from './productionPlans';

type ProductionEntry = Record<string, unknown>;

function display(value: unknown, fallback = '—') {
  return value === null || value === undefined || value === '' ? fallback : String(value);
}

function displayTime(value: unknown) {
  if (typeof value !== 'string' || !value) return '—';
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString();
}

export default function EditLog({ productionEntries }: { productionEntries: ProductionEntry[] }) {
  const [plans, setPlans] = useState<ProductionPlan[]>([]);
  const [plansTruncated, setPlansTruncated] = useState(false);
  const [plansWarning, setPlansWarning] = useState('');
  const [loadingPlan, setLoadingPlan] = useState(false);

  const refreshPlan = useCallback(async () => {
    setLoadingPlan(true);
    setPlansWarning('');
    try {
      const response = await loadProductionPlans();
      setPlans(response.plans);
      setPlansTruncated(response.truncated);
      setPlansWarning([
        ...response.warnings,
        response.truncated ? 'The plan list is truncated; narrow the source query before relying on this list.' : '',
      ].filter(Boolean).join(' '));
    } catch (error) {
      setPlansWarning(error instanceof Error ? error.message : 'PIS Production Plan is temporarily unavailable.');
    } finally {
      setLoadingPlan(false);
    }
  }, []);

  useEffect(() => { void refreshPlan(); }, [refreshPlan]);

  const orderedEntries = [...productionEntries].sort((left, right) =>
    String(right.production_at ?? '').localeCompare(String(left.production_at ?? '')),
  );

  return <>
    <div className="page-intro">
      <div><div className="eyebrow">PRODUCTION · OPERATOR RECORDS</div><h2>Edit Log</h2><p className="subtle">Saved production entries remain authoritative operator records. PIS plans are displayed separately and are never copied over saved entries.</p></div>
    </div>

    <section className="card top-gap" aria-label="PIS Production Plan">
      <div className="card-head">
        <div><span className="eyebrow">READ-ONLY SOURCE · {`OMAG.dbo.vw_OmagPlan`}</span><h3>PIS Production Plan</h3></div>
        <button className="button secondary" type="button" onClick={() => void refreshPlan()} disabled={loadingPlan}>
          {loadingPlan ? 'Loading Plan…' : 'Refresh Plan'}
        </button>
      </div>
      <p className="subtle">Company SCGLS · Machine OMAG · Plant 3251. Plan refresh does not modify production records.</p>
      {plansWarning && <div className="notice-box warning" role="alert" aria-live="assertive">PIS Production Plan unavailable or limited: {plansWarning}</div>}
      {loadingPlan && plans.length === 0 && <div className="empty-state compact" role="status">Loading the current PIS Production Plan…</div>}
      {plans.length > 0 ? <div className="table-wrap"><table>
        <thead><tr><th>PLAN</th><th>MATERIAL</th><th>PLANNED START</th><th>SHIFT</th><th>COUNT</th><th>IDENTITY</th></tr></thead>
        <tbody>{plans.map((plan) => <tr key={plan.plan_key}>
          <td><strong>{display(plan.plan_name, 'Unnamed plan')}</strong><small className="cell-sub">{display(plan.snapshot.OperationCode, 'No operation')}</small></td>
          <td><strong>{display(plan.material_code)}</strong><small className="cell-sub">{display(plan.material_name, 'No material name')}</small></td>
          <td>{displayTime(plan.planned_start)}</td>
          <td>{display(plan.shift)}</td>
          <td>{display(plan.plan_count)}</td>
          <td>{plan.duplicate_count === 1 ? 'Unique snapshot' : `Duplicate ×${plan.duplicate_count}`}</td>
        </tr>)}</tbody>
      </table></div> : !loadingPlan && !plansWarning && <div className="empty-state compact">No PIS production plans matched Company SCGLS, Machine OMAG, Plant 3251.</div>}
      <small className="subtle">{plansTruncated ? 'Results are limited.' : `${plans.length} plan snapshot${plans.length === 1 ? '' : 's'} loaded.`} Identical snapshots may not be distinguishable.</small>
    </section>

    <section className="card top-gap" aria-label="Saved production entries">
      <div className="card-head"><div><span className="eyebrow">OPERATOR-ENTERED DATA</span><h3>Saved Production Log</h3></div><span className="tag green">PRESERVED ON PLAN REFRESH</span></div>
      {orderedEntries.length ? <div className="table-wrap"><table>
        <thead><tr><th>PRODUCTION TIME</th><th>LOT</th><th>DATE / SHIFT</th><th>PRESS DROPS</th><th>GOOD PIECES</th><th>OPERATOR NOTE</th><th>SOURCE</th></tr></thead>
        <tbody>{orderedEntries.map((entry, index) => <tr key={display(entry.id, String(index))}>
          <td>{displayTime(entry.production_at)}</td>
          <td>#{display(entry.lot_id)}</td>
          <td>{display(entry.production_date)} / #{display(entry.shift_id, 'unassigned')}</td>
          <td>{display(entry.actual_drops)}</td>
          <td>{display(entry.wet_good_pieces)}</td>
          <td>{display(entry.operator_note, '—')}</td>
          <td>{display(entry.mode, 'SAVED')}</td>
        </tr>)}</tbody>
      </table></div> : <div className="empty-state compact">No saved production entries are available.</div>}
    </section>
  </>;
}
