import { useEffect, useState, type FormEvent } from 'react';

type ShiftPeriod = { id?: number | null; start_time: string; end_time: string; display_order: number; active: boolean };
type ShiftDefinition = {
  id?: number;
  shift_code: string;
  shift_name: string;
  start_time: string;
  end_time: string;
  display_order: number;
  active: boolean;
  periods: ShiftPeriod[];
};
type ScheduleVersion = {
  id: number;
  effective_from: string;
  effective_to_exclusive: string | null;
  created_at: string;
  created_by: string;
  change_reason: string;
  shifts: ShiftDefinition[];
};
export type ShiftScheduleContext = {
  production_date: string;
  time_zone: string;
  applicable_version_id: number;
  applicable_version: ScheduleVersion;
  resolved_shifts: (ShiftDefinition & { period_order: number; start_at: string; end_at: string; interval_semantics: string })[];
  unassigned_gaps: { start_time: string; end_time: string }[];
  schedule_versions: ScheduleVersion[];
  cutoff_version_id: number;
  periods_enabled?: boolean;
  production_day?: { start_at: string; end_at_exclusive: string; duration_seconds: number; time_zone: string; interval_semantics: string };
};

function nextDate(value: string) {
  const [year, month, day] = value.split('-').map(Number);
  const result = new Date(Date.UTC(year, month - 1, day + 1));
  return `${result.getUTCFullYear()}-${String(result.getUTCMonth() + 1).padStart(2, '0')}-${String(result.getUTCDate()).padStart(2, '0')}`;
}
function blankPeriod(displayOrder: number): ShiftPeriod {
  return { start_time: '', end_time: '', display_order: displayOrder, active: true };
}

export default function ShiftScheduleSettings({ schedule, productionDate, onReload }: {
  schedule: ShiftScheduleContext | null;
  productionDate: string;
  onReload: () => Promise<void>;
}) {
  const [shifts, setShifts] = useState<ShiftDefinition[]>([]);
  const [effectiveFrom, setEffectiveFrom] = useState('');
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState('');
  const [changeReason, setChangeReason] = useState('');
  const versions = schedule?.schedule_versions ?? [];
  const latest = versions[versions.length - 1];

  useEffect(() => {
    if (!latest) return;
    setShifts(latest.shifts.map((shift) => ({
      ...shift,
      periods: (shift.periods?.length ? shift.periods : [{ start_time: shift.start_time, end_time: shift.end_time, display_order: 1, active: shift.active }]).map((period, index) => ({ ...period, display_order: period.display_order || index + 1 })),
    })));
    const boundary = productionDate > latest.effective_from ? productionDate : latest.effective_from;
    setEffectiveFrom(nextDate(boundary));
  }, [latest?.id, productionDate]);

  function updateShift(index: number, patch: Partial<ShiftDefinition>) {
    setShifts((current) => current.map((shift, rowIndex) => rowIndex === index ? { ...shift, ...patch } : shift));
  }
  function updatePeriod(shiftIndex: number, periodIndex: number, patch: Partial<ShiftPeriod>) {
    setShifts((current) => current.map((shift, index) => index === shiftIndex ? {
      ...shift,
      periods: shift.periods.map((period, itemIndex) => itemIndex === periodIndex ? { ...period, ...patch } : period),
    } : shift));
  }

  async function save(event: FormEvent) {
    event.preventDefault();
    if (!latest) return;
    setSaving(true);
    setMessage('');
    try {
      const response = await fetch('/api/shift-period-schedule/versions', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ effective_from: effectiveFrom, reviewed_through_date: productionDate, base_version_id: latest.id, change_reason: changeReason, shifts }),
      });
      if (!response.ok) {
        const body = await response.json().catch(() => null) as { detail?: string } | null;
        throw new Error(body?.detail ?? `Schedule save failed (${response.status})`);
      }
      await onReload();
      setChangeReason('');
      setMessage('Shift and Period changes were committed in one SQL transaction with immutable version and audit history. Existing versions remain unchanged.');
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Schedule save failed.');
    } finally {
      setSaving(false);
    }
  }

  return <section className="card top-gap" aria-label="Shift Periods">
    <div className="card-head"><div><span className="eyebrow">SHIFT PERIODS</span><h3>Effective-dated Shift Period configuration</h3></div><span className="tag blue">SELECTED DATE · {productionDate || '—'}</span></div>
    {!schedule || !latest ? <div className="notice-box" role="status">SQL-backed Shift Period configuration is unavailable. No default factory hours or mock values are presented.</div> : <>
      <p className="subtle">Schedule v{schedule.applicable_version_id} · Cutoff v{schedule.cutoff_version_id} · {schedule.time_zone}. Periods use half-open intervals [start, end); overnight periods resolve to the next Bangkok calendar day.</p>
      <div className="table-wrap"><table><thead><tr><th>SHIFT</th><th>SHIFT ID</th><th>PERIOD</th><th>PRODUCTION-DATE INTERVAL</th></tr></thead><tbody>
        {schedule.resolved_shifts.map((period) => <tr key={`${period.id}-${period.period_order}`}><td>{period.shift_name} · {period.shift_code}</td><td>#{period.id}</td><td>{period.period_order}</td><td>{period.start_at.replace('T', ' ')} → {period.end_at.replace('T', ' ')}</td></tr>)}
        {!schedule.resolved_shifts.length && <tr><td colSpan={4}>No active periods apply to this Production Date.</td></tr>}
      </tbody></table></div>
      <div className="gap-summary"><strong>Explicitly unassigned:</strong> {schedule.unassigned_gaps.length ? schedule.unassigned_gaps.map((gap) => `${gap.start_time}–${gap.end_time}`).join(' · ') : 'No daily gaps'}</div>
      {schedule.periods_enabled ? <form className="shift-period-editor top-gap" onSubmit={(event) => void save(event)}>
        <div className="grid two-col">
          <label className="field"><span>Effective from Production Date</span><input type="date" value={effectiveFrom} min={nextDate(productionDate > latest.effective_from ? productionDate : latest.effective_from)} onChange={(event) => setEffectiveFrom(event.target.value)} required /><small className="field-hint">Must be after the selected Production Date and latest configuration version.</small></label>
          <label className="field"><span>Change reason</span><input value={changeReason} onChange={(event) => setChangeReason(event.target.value)} maxLength={500} required /></label>
        </div>
        <div className="shift-period-shifts">{shifts.map((shift, shiftIndex) => <section className="shift-period-card" key={shift.id ?? `new-${shiftIndex}`}>
          <div className="shift-period-heading"><strong>{shift.id ? `Shift ID #${shift.id}` : 'New Shift'}</strong><button className="text-button" type="button" onClick={() => setShifts((current) => current.filter((_, index) => index !== shiftIndex))}>Remove Shift</button></div>
          <div className="grid three-col">
            <label className="field"><span>Shift Name</span><input value={shift.shift_name} onChange={(event) => updateShift(shiftIndex, { shift_name: event.target.value })} maxLength={100} required /></label>
            <label className="field"><span>Shift Code</span><input value={shift.shift_code} onChange={(event) => updateShift(shiftIndex, { shift_code: event.target.value })} maxLength={40} required /></label>
            <label className="field"><span>Display Order</span><input type="number" min="1" value={shift.display_order} onChange={(event) => updateShift(shiftIndex, { display_order: Number(event.target.value) })} required /></label>
          </div>
          <label className="shift-active"><input type="checkbox" checked={shift.active} onChange={(event) => updateShift(shiftIndex, { active: event.target.checked, periods: shift.periods.map((period) => ({ ...period, active: event.target.checked && period.active })) })} /> Active Shift</label>
          <div className="table-wrap"><table><thead><tr><th>PERIOD ORDER</th><th>START · BANGKOK</th><th>END · BANGKOK</th><th>ACTIVE</th><th></th></tr></thead><tbody>
            {shift.periods.map((period, periodIndex) => <tr key={`${shift.id ?? shiftIndex}-period-${periodIndex}`}>
              <td><input aria-label={`${shift.shift_name || `Shift ${shiftIndex + 1}`} period order ${periodIndex + 1}`} type="number" min="1" value={period.display_order} onChange={(event) => updatePeriod(shiftIndex, periodIndex, { display_order: Number(event.target.value) })} required /></td>
              <td><input aria-label={`${shift.shift_name || `Shift ${shiftIndex + 1}`} period ${periodIndex + 1} start`} type="time" value={period.start_time} onChange={(event) => updatePeriod(shiftIndex, periodIndex, { start_time: event.target.value })} required /></td>
              <td><input aria-label={`${shift.shift_name || `Shift ${shiftIndex + 1}`} period ${periodIndex + 1} end`} type="time" value={period.end_time} onChange={(event) => updatePeriod(shiftIndex, periodIndex, { end_time: event.target.value })} required /></td>
              <td><input aria-label={`${shift.shift_name || `Shift ${shiftIndex + 1}`} period ${periodIndex + 1} active`} type="checkbox" checked={period.active} disabled={!shift.active} onChange={(event) => updatePeriod(shiftIndex, periodIndex, { active: event.target.checked })} /></td>
              <td><button className="text-button" type="button" onClick={() => updateShift(shiftIndex, { periods: shift.periods.filter((_, index) => index !== periodIndex).map((item, index) => ({ ...item, display_order: index + 1 })) })}>Remove</button></td>
            </tr>)}
            {!shift.periods.length && <tr><td colSpan={5}>Add at least one period for this Shift.</td></tr>}
          </tbody></table></div>
          <button className="button secondary" type="button" onClick={() => updateShift(shiftIndex, { periods: [...shift.periods, blankPeriod(shift.periods.length + 1)] })}>＋ ADD PERIOD</button>
        </section>)}</div>
        <div className="form-footer"><button className="button secondary" type="button" onClick={() => setShifts((current) => [...current, { shift_code: '', shift_name: '', start_time: '', end_time: '', display_order: current.length + 1, active: true, periods: [blankPeriod(1)] }])}>＋ ADD SHIFT</button><button className="button primary" type="submit" disabled={saving || !effectiveFrom || !changeReason.trim() || shifts.length === 0}>{saving ? 'Saving…' : 'SAVE SHIFT / PERIOD VERSION →'}</button></div>
      </form> : <div className="notice-box top-gap" role="status">Shift Period storage is not deployed. Existing whole-Shift intervals remain viewable; editing is disabled until the prepared additive migration is approved and applied by the database owner.</div>}
    </>}
    {message && <div className="notice-box top-gap" role="status">{message}</div>}
  </section>;
}
