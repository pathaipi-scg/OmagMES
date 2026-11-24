import { useCallback, useEffect, useState, type FormEvent } from 'react';

type CutoffVersion = {
  id: number;
  effective_from: string;
  effective_to_exclusive: string | null;
  cutoff_time: string;
  time_zone: string;
  created_at: string;
  created_by: string;
  change_reason: string;
};
type CutoffContext = {
  production_date: string;
  time_zone: string;
  applicable_version: CutoffVersion;
  versions: CutoffVersion[];
  window: {
    start_at: string;
    end_at_exclusive: string;
    duration_seconds: number;
    interval_semantics: string;
  };
};
type CurrentDate = {
  production_date: string;
  calendar_date: string;
  cutoff_time: string;
  cutoff_version_id: number;
  time_zone: string;
};

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(path);
  if (!response.ok) {
    const body = await response.json().catch(() => null) as { detail?: string } | null;
    throw new Error(body?.detail ?? `Configuration read failed (${response.status})`);
  }
  return response.json() as Promise<T>;
}

async function postJson<T>(path: string, body: unknown): Promise<T> {
  const response = await fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    const result = await response.json().catch(() => null) as { detail?: string } | null;
    throw new Error(result?.detail ?? `Configuration save failed (${response.status})`);
  }
  return response.json() as Promise<T>;
}

function addDays(value: string, days: number) {
  const [year, month, day] = value.split('-').map(Number);
  const result = new Date(Date.UTC(year, month - 1, day + days));
  return `${result.getUTCFullYear()}-${String(result.getUTCMonth() + 1).padStart(2, '0')}-${String(result.getUTCDate()).padStart(2, '0')}`;
}

export default function ProductionDayCutoff({ productionDate, onReload, showHistory = true }: {
  productionDate: string;
  onReload: () => Promise<void>;
  showHistory?: boolean;
}) {
  const [context, setContext] = useState<CutoffContext | null>(null);
  const [current, setCurrent] = useState<CurrentDate | null>(null);
  const [cutoffTime, setCutoffTime] = useState('07:00');
  const [effectiveFrom, setEffectiveFrom] = useState('');
  const [reason, setReason] = useState('');
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);

  const reload = useCallback(async () => {
    if (!productionDate) return;
    const query = new URLSearchParams({ production_date: productionDate });
    const [selected, live] = await Promise.all([
      getJson<CutoffContext>(`/api/production-day-cutoff?${query}`),
      getJson<CurrentDate>('/api/production-date/current'),
    ]);
    setContext(selected);
    setCurrent(live);
    const latest = selected.versions[selected.versions.length - 1];
    setCutoffTime(latest.cutoff_time);
    const safeDate = addDays(live.production_date, 2);
    const afterSelected = addDays(productionDate, 1);
    setEffectiveFrom(safeDate > afterSelected ? safeDate : afterSelected > latest.effective_from ? afterSelected : addDays(latest.effective_from, 1));
  }, [productionDate]);

  useEffect(() => {
    if (!productionDate) return;
    void reload().then(() => setMessage('')).catch((error: unknown) => {
      setContext(null);
      setMessage(error instanceof Error ? error.message : 'SQL configuration is unavailable.');
    });
  }, [reload]);

  async function save(event: FormEvent) {
    event.preventDefault();
    if (!context || !current) return;
    setBusy(true);
    setMessage('');
    try {
      await postJson('/api/production-day-cutoff/versions', {
        effective_from: effectiveFrom,
        cutoff_time: cutoffTime,
        time_zone: 'Asia/Bangkok',
        reviewed_through_date: productionDate,
        base_version_id: context.versions[context.versions.length - 1].id,
        change_reason: reason,
      });
      await onReload();
      await reload();
      setReason('');
      setMessage('SAVE CUTOFF committed a new SQL version and audit event. Existing Production Date facts were not changed.');
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Cutoff save failed.');
    } finally {
      setBusy(false);
    }
  }

  const latest = context?.versions[context.versions.length - 1];
  const minimumEffective = current ? addDays(current.production_date, 2) : '';

  return <section className="card top-gap cutoff-settings" aria-label="Production Day Cutoff settings">
    <div className="card-head"><div><span className="eyebrow">SETTING · PRODUCTION DAY</span><h3>Production Day Cutoff</h3></div><span className="tag blue">INDEPENDENT CONFIGURATION</span></div>
    <p className="subtle">This cutoff determines the factory Production Date, independently of Shift Time. All timestamps use {context?.time_zone ?? 'Asia/Bangkok'}; configuration versions are append-only and stored in SQL Server.</p>
    {!productionDate ? <div className="notice-box" role="status">Waiting for the backend to resolve the current Production Date. Choose a date only if reviewing historical records.</div> : context && current && latest ? <>
      <div className="context-grid cutoff-current-grid">
        <div><small>Calendar Date · server clock</small><strong>{current.calendar_date}</strong></div>
        <div><small>Current live Production Date</small><strong>{current.production_date} · v{current.cutoff_version_id}</strong></div>
        <div><small>Selected Production Date</small><strong>{productionDate}{productionDate !== current.production_date ? ' · historical selection' : ' · current'}</strong></div>
        <div><small>Selected cutoff</small><strong>{context.applicable_version.cutoff_time} · v{context.applicable_version.id}</strong></div>
      </div>
      <div className="gap-summary cutoff-window"><strong>Operational window:</strong> {context.window.start_at.replace('T', ' ')} → {context.window.end_at_exclusive.replace('T', ' ')} ({context.window.interval_semantics})</div>
      {showHistory && <div className="table-wrap top-gap"><table><thead><tr><th>VERSION</th><th>EFFECTIVE PRODUCTION DATE</th><th>CUTOFF</th><th>CREATED · UTC</th><th>REASON / ACTOR</th></tr></thead><tbody>
        {context.versions.slice().reverse().map((version) => <tr key={version.id}><td className="id-cell">v{version.id}</td><td>{version.effective_from}{version.effective_to_exclusive ? ` → before ${version.effective_to_exclusive}` : ' → open-ended'}</td><td>{version.cutoff_time}</td><td>{version.created_at}</td><td>{version.change_reason}<small className="cell-sub">{version.created_by}</small></td></tr>)}
      </tbody></table></div>}
      <form className="cutoff-editor top-gap" onSubmit={(event) => void save(event)}>
        <div className="card-head"><div><span className="eyebrow">IMMUTABLE VERSION HISTORY</span><h4>Create the next cutoff version</h4></div><span className="tag muted">BASED ON LATEST v{latest.id}</span></div>
        <div className="grid two-col">
          <label className="field"><span>New cutoff time · Asia/Bangkok</span><input type="time" value={cutoffTime} onChange={(event) => setCutoffTime(event.target.value)} required /></label>
          <label className="field"><span>Effective from Production Date</span><input type="date" value={effectiveFrom} min={minimumEffective} onChange={(event) => setEffectiveFrom(event.target.value)} required /><small className="field-hint">Must be at least {minimumEffective} to protect started Production Days.</small></label>
        </div>
        <label className="field"><span>Change reason</span><input value={reason} onChange={(event) => setReason(event.target.value)} maxLength={500} required /></label>
        <div className="notice-box">A cutoff version takes effect at its calendar-date boundary. The prior day ends at that boundary, so intervals remain contiguous; started Production Days cannot be changed.</div>
        <div className="form-footer"><span className="subtle tiny">This setting does not move or edit Shift boundaries.</span><button className="button primary" type="submit" disabled={busy || !effectiveFrom || !reason.trim()}>{busy ? 'Saving…' : 'SAVE CUTOFF →'}</button></div>
      </form>
    </> : <div className="notice-box" role="status">{message || 'SQL-backed cutoff configuration is not available. No mock/local save is offered.'} Initial configuration target: 07:00 Asia/Bangkok; a DBA-approved database bootstrap is required before operation.</div>}
    {context && message && <div className="notice-box top-gap" role="status">{message}</div>}
  </section>;
}
