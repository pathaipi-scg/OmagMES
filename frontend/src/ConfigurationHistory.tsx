import { useEffect, useState } from 'react';
import type { ShiftScheduleContext } from './ShiftSchedule';

type CutoffVersion = { id: number; effective_from: string; effective_to_exclusive: string | null; cutoff_time: string; time_zone: string; created_at: string; created_by: string; change_reason: string };
type CutoffContext = { versions: CutoffVersion[] };
type ChangeEvent = { id: number; type: string; identity: string; version_id: number; old_value: string | null; new_value: string | null; changed_at: string; changed_by: string; effective_from: string; effective_to_exclusive: string | null; change_reason: string };

function formatValue(value: string | null) {
  if (value === null) return '—';
  try { return JSON.stringify(JSON.parse(value), null, 2); } catch { return value; }
}

export default function ConfigurationHistory({ schedule, productionDate, reloadKey }: { schedule: ShiftScheduleContext | null; productionDate: string; reloadKey: number }) {
  const [cutoffs, setCutoffs] = useState<CutoffVersion[]>([]);
  const [events, setEvents] = useState<ChangeEvent[]>([]);
  const [eventError, setEventError] = useState('');
  const [error, setError] = useState('');
  useEffect(() => {
    if (!productionDate) return;
    const query = new URLSearchParams({ production_date: productionDate });
    void fetch(`/api/production-day-cutoff?${query}`).then(async (response) => {
      if (!response.ok) throw new Error('Production Day configuration history is unavailable.');
      return response.json() as Promise<CutoffContext>;
    }).then((context) => { setCutoffs(context.versions); setError(''); }).catch((reason: unknown) => {
      setCutoffs([]); setError(reason instanceof Error ? reason.message : 'Configuration history is unavailable.');
    });
  }, [productionDate]);
  useEffect(() => {
    void fetch('/api/configuration-history').then(async (response) => {
      if (!response.ok) throw new Error('Configuration change history is unavailable.');
      return response.json() as Promise<{ events: ChangeEvent[] }>;
    }).then((result) => { setEvents(result.events); setEventError(''); }).catch((reason: unknown) => {
      setEvents([]); setEventError(reason instanceof Error ? reason.message : 'Configuration change history is unavailable.');
    });
  }, [productionDate, reloadKey, schedule?.applicable_version_id, schedule?.cutoff_version_id]);

  return <section className="card top-gap" aria-label="Configuration History">
    <div className="card-head"><div><span className="eyebrow">CONFIGURATION HISTORY</span><h3>Immutable effective-date versions</h3></div><span className="tag muted">HISTORICAL RECORDS RETAINED</span></div>
    <section aria-label="Setting change audit history"><h4 className="section-label">SETTING CHANGE AUDIT</h4>
      {events.length ? <div className="table-wrap"><table><thead><tr><th>TYPE</th><th>IDENTITY</th><th>VERSION</th><th>OLD VALUE</th><th>NEW VALUE</th><th>CHANGED AT · UTC</th><th>CHANGED BY</th><th>EFFECTIVE FROM</th><th>EFFECTIVE TO</th><th>REASON</th></tr></thead><tbody>
        {events.map((event) => <tr key={event.id}><td>{event.type}</td><td className="id-cell">{event.identity}</td><td>v{event.version_id}</td><td><pre className="history-value">{formatValue(event.old_value)}</pre></td><td><pre className="history-value">{formatValue(event.new_value)}</pre></td><td>{event.changed_at}</td><td>{event.changed_by}</td><td>{event.effective_from}</td><td>{event.effective_to_exclusive ?? 'Open-ended'}</td><td>{event.change_reason}</td></tr>)}
      </tbody></table></div> : <div className="notice-box">{eventError || 'No new Setting change audit events are recorded yet. Existing schedule and cutoff version history is retained below.'}</div>}
    </section>
    <section aria-label="Shift configuration history"><h4 className="section-label">SHIFT MASTER & PERIOD HISTORY</h4>
      {schedule?.schedule_versions.length ? <div className="table-wrap"><table><thead><tr><th>VERSION</th><th>EFFECTIVE PRODUCTION DATES</th><th>SHIFT PERIODS</th><th>CREATED · ACTOR · REASON</th></tr></thead><tbody>
        {schedule.schedule_versions.slice().reverse().map((version) => <tr key={version.id}><td className="id-cell">v{version.id}</td><td>{version.effective_from} → {version.effective_to_exclusive ? `before ${version.effective_to_exclusive}` : 'open-ended'}</td><td>{version.shifts.map((shift) => `${shift.shift_name} (${shift.shift_code}) · ${(shift.periods?.length ? shift.periods : [{ start_time: shift.start_time, end_time: shift.end_time, active: shift.active }]).map((period) => `${period.start_time}–${period.end_time}${period.active ? '' : ' inactive'}`).join(', ')}`).join(' | ')}</td><td>{version.created_at}<small className="cell-sub">{version.created_by} · {version.change_reason}</small></td></tr>)}
      </tbody></table></div> : <div className="notice-box">{schedule ? 'No Shift Schedule versions are available.' : 'Shift Schedule history is unavailable.'}</div>}
    </section>
    <section className="top-gap" aria-label="Production Date Cutoff history"><h4 className="section-label">PRODUCTION DATE CUTOFF HISTORY</h4>
      {cutoffs.length ? <div className="table-wrap"><table><thead><tr><th>VERSION</th><th>EFFECTIVE PRODUCTION DATES</th><th>CUTOFF</th><th>TIME ZONE</th><th>CREATED · ACTOR · REASON</th></tr></thead><tbody>
        {cutoffs.slice().reverse().map((version) => <tr key={version.id}><td className="id-cell">v{version.id}</td><td>{version.effective_from} → {version.effective_to_exclusive ? `before ${version.effective_to_exclusive}` : 'open-ended'}</td><td>{version.cutoff_time}</td><td>{version.time_zone}</td><td>{version.created_at}<small className="cell-sub">{version.created_by} · {version.change_reason}</small></td></tr>)}
      </tbody></table></div> : <div className="notice-box">{error || 'No cutoff versions available.'}</div>}
    </section>
  </section>;
}
