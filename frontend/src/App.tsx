import { useCallback, useEffect, useMemo, useState, type FormEvent } from 'react';

type Product = { id: number; code: string; name: string; family: string; standard_pieces_per_drop: number | null; standard_cycle_time_sec: number | null };
type Lot = { id: number; run_id: number; product_id: number; color: string; lot_name: string; started_at: string };
type Reason = { code: string; label: string };
type Mould = { id: number; code: string; product_id: number; status: string; current_age_drops: number; lifetime_age_drops: number; recondition_cycle: number };
type RecordRow = Record<string, unknown>;
type Bootstrap = { mode: string; products: Product[]; lots: Lot[]; reject_reasons: Reason[]; production_entries: RecordRow[]; reject_entries: RecordRow[]; run_events: RecordRow[]; curing_entries: RecordRow[]; depal_entries: RecordRow[]; moulds: Mould[]; mould_history: RecordRow[] };
type AutoCal = { mode: string; suggested_actual_drops: number | null; suggested_wet_good_pieces: number | null; suggested_wet_rejects: Record<string, number | null>; reject_total?: number | null; source_notes: string[]; source_errors?: Record<string, string> };
type Oee = { mode: string; window: string; availability: number; performance: number; quality: number; oee: number; actual_drops: number; wet_good_pieces: number; standard_status: string; notes: string[] };
type SourceMode = 'MOCK' | 'LIVE READ-ONLY' | 'UNKNOWN';
type SourceHealth = { mode: string; connected: boolean; server: string | null; instance: string | null; database: string | null; read_only_permissions_verified: boolean; error: string | null };
type SourceDashboard = { mode: string; connected: boolean; wet_status: { status: string; observation: RecordRow | null } | null; press_counter: RecordRow | null; wet_camera_pieces: number | null; wet_reject_counts: Record<string, number | null>; last_observation_at: string | null; warnings: string[]; source_errors: Record<string, string> };

type Page = 'Production' | 'Wet Reject' | 'Wet Run Log' | 'Wet OEE' | 'Curing' | 'Depallet' | 'Mould' | 'Settings';
const pages: { name: Page; icon: string; group: string }[] = [
  { name: 'Production', icon: '◫', group: 'Production' },
  { name: 'Wet Run Log', icon: '◷', group: 'Production' },
  { name: 'Wet Reject', icon: '◈', group: 'Production' },
  { name: 'Wet OEE', icon: '◌', group: 'Production' },
  { name: 'Curing', icon: '▤', group: 'Production' },
  { name: 'Depallet', icon: '▦', group: 'Depallet' },
  { name: 'Mould', icon: '▰', group: 'Setting' },
  { name: 'Settings', icon: '⚙', group: 'Setting' },
];
const fallback: Bootstrap = {
  mode: 'MOCK ONLY — API not connected',
  products: [
    { id: 1, code: 'DEMO-BLOCK-001', name: 'Demo Block — 6 cm', family: 'Block', standard_pieces_per_drop: null, standard_cycle_time_sec: null },
    { id: 2, code: 'DEMO-FENCE-001', name: 'Demo Fence Panel', family: 'Fence', standard_pieces_per_drop: null, standard_cycle_time_sec: null },
    { id: 3, code: 'DEMO-CURB-001', name: 'Demo Curb — Grey', family: 'Block', standard_pieces_per_drop: null, standard_cycle_time_sec: null },
  ],
  lots: [
    { id: 501, run_id: 101, product_id: 1, color: 'Grey', lot_name: 'DEMO-LOT-A', started_at: '2026-11-08T07:00:00+07:00' },
    { id: 502, run_id: 102, product_id: 2, color: 'Natural', lot_name: 'DEMO-LOT-B', started_at: '2026-11-08T08:30:00+07:00' },
  ],
  reject_reasons: [{ code: 'cntR1', label: 'Edge damage' }, { code: 'cntR2', label: 'Surface defect' }, { code: 'cntR3', label: 'Dimension / shape' }],
  production_entries: [], reject_entries: [], run_events: [], curing_entries: [], depal_entries: [],
  moulds: [
    { id: 71, code: 'DEMO-MOULD-01', product_id: 1, status: 'ACTIVE', current_age_drops: 18420, lifetime_age_drops: 126550, recondition_cycle: 0 },
    { id: 72, code: 'DEMO-MOULD-02', product_id: 2, status: 'RECONDITION', current_age_drops: 3250, lifetime_age_drops: 88400, recondition_cycle: 1 },
  ], mould_history: [],
};

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, { ...init, headers: { 'Content-Type': 'application/json', ...init?.headers } });
  if (!response.ok) {
    const body = await response.json().catch(() => null) as { detail?: string } | null;
    throw new Error(body?.detail ?? `Request failed (${response.status})`);
  }
  return response.json() as Promise<T>;
}

function App() {
  const [page, setPage] = useState<Page>('Production');
  const [openNavGroup, setOpenNavGroup] = useState('Production');
  const [data, setData] = useState<Bootstrap>(fallback);
  const [connected, setConnected] = useState(false);
  const [sourceMode, setSourceMode] = useState<SourceMode>('UNKNOWN');
  const [sourceHealth, setSourceHealth] = useState<SourceHealth | null>(null);
  const [sourceDashboard, setSourceDashboard] = useState<SourceDashboard | null>(null);
  const [liveWindowStart, setLiveWindowStart] = useState('');
  const [liveWindowEnd, setLiveWindowEnd] = useState('');
  const [liveWindowConfirmed, setLiveWindowConfirmed] = useState(false);
  const [notice, setNotice] = useState('');
  const [autoCal, setAutoCal] = useState<AutoCal | null>(null);
  const [oee, setOee] = useState<Oee | null>(null);
  const [selectedLot, setSelectedLot] = useState('501');
  const [drops, setDrops] = useState('');
  const [goodPieces, setGoodPieces] = useState('');
  const [productionNote, setProductionNote] = useState('');
  const [rejectCounts, setRejectCounts] = useState<Record<string, string>>({});
  const [rejectNote, setRejectNote] = useState('');
  const [eventCategory, setEventCategory] = useState('RUNNING');
  const [eventStart, setEventStart] = useState('2026-11-08T07:00');
  const [eventEnd, setEventEnd] = useState('');
  const [eventNote, setEventNote] = useState('');
  const [lifecycleQty, setLifecycleQty] = useState('');
  const [lifecycleNote, setLifecycleNote] = useState('');
  const [newProduct, setNewProduct] = useState('1');
  const [lotTransition, setLotTransition] = useState<'PRODUCT_CHANGE' | 'COLOR_CHANGE'>('PRODUCT_CHANGE');
  const [newColor, setNewColor] = useState('Grey');
  const [newLotName, setNewLotName] = useState('');
  const [renameTarget, setRenameTarget] = useState<number | null>(null);
  const [renameName, setRenameName] = useState('');
  const [renameReason, setRenameReason] = useState('');
  const [selectedMould, setSelectedMould] = useState('71');
  const [mouldAction, setMouldAction] = useState<'SEND_TO_RECONDITION' | 'APPROVE_RETURN'>('SEND_TO_RECONDITION');
  const [mouldReason, setMouldReason] = useState('');
  const [search, setSearch] = useState('');

  const refresh = useCallback(async () => {
    try {
      const [boot, status] = await Promise.all([request<Bootstrap>('/api/bootstrap'), request<{ status: string; mode: SourceMode }>('/api/health')]);
      setData(boot);
      setConnected(status.status === 'ok');
      setSourceMode(status.mode === 'MOCK' || status.mode === 'LIVE READ-ONLY' ? status.mode : 'UNKNOWN');
      setSelectedLot((current) => boot.lots.some((lot) => String(lot.id) === current) ? current : String(boot.lots[0]?.id ?? ''));
      if (status.mode === 'LIVE READ-ONLY') {
        try {
          const health = await request<SourceHealth>('/api/sources/health');
          setSourceHealth(health);
          if (health.connected) {
            const now = Date.now();
            const query = new URLSearchParams({ start_at: new Date(now - 86_400_000).toISOString(), end_at: new Date(now).toISOString() });
            setSourceDashboard(await request<SourceDashboard>(`/api/sources/dashboard?${query.toString()}`));
          } else {
            setSourceDashboard(null);
          }
        } catch (error) {
          setSourceHealth({ mode: 'LIVE READ-ONLY', connected: false, server: null, instance: null, database: null, read_only_permissions_verified: false, error: error instanceof Error ? error.message : 'Source health is unavailable.' });
          setSourceDashboard(null);
        }
      } else {
        setSourceHealth(null);
        setSourceDashboard(null);
      }
    } catch {
      setConnected(false);
      setSourceMode('UNKNOWN');
      setSourceHealth({ mode: 'UNKNOWN', connected: false, server: null, instance: null, database: null, read_only_permissions_verified: false, error: 'API unavailable; active source mode cannot be verified.' });
      setSourceDashboard(null);
    }
  }, []);

  useEffect(() => { void refresh(); }, [refresh]);
  useEffect(() => {
    if (page === 'Wet OEE') void request<Oee>('/api/wet-oee/preview').then(setOee).catch(() => setOee(null));
  }, [page]);

  const selectedLotData = data.lots.find((lot) => String(lot.id) === selectedLot);
  const selectedProduct = data.products.find((product) => product.id === selectedLotData?.product_id);
  const filteredLots = useMemo(() => data.lots.filter((lot) => {
    const product = data.products.find((item) => item.id === lot.product_id);
    const text = `${lot.id} ${lot.lot_name} ${product?.code ?? ''} ${product?.name ?? ''}`.toLowerCase();
    return text.includes(search.toLowerCase());
  }), [data.lots, data.products, search]);

  async function act<T>(path: string, body?: unknown, method = 'POST'): Promise<T | null> {
    setNotice('');
    try {
      const result = await request<T>(path, body === undefined ? { method } : { method, body: JSON.stringify(body) });
      setNotice('Saved to process-local mock state. No production SQL was changed.');
      await refresh();
      return result;
    } catch (error) {
      setNotice(error instanceof Error ? error.message : 'Request failed.');
      return null;
    }
  }

  async function loadAutoCal() {
    setNotice('');
    try {
      const result = await request<AutoCal>(autocalPath());
      setAutoCal(result);
      if (result.suggested_actual_drops !== null) setDrops(String(result.suggested_actual_drops));
      if (result.suggested_wet_good_pieces !== null) setGoodPieces(String(result.suggested_wet_good_pieces));
      if (result.mode !== 'LIVE READ-ONLY') {
        const availableRejects = Object.fromEntries(Object.entries(result.suggested_wet_rejects).filter(([, value]) => value !== null).map(([key, value]) => [key, String(value)]));
        if (Object.keys(availableRejects).length) setRejectCounts((current) => ({ ...current, ...availableRejects }));
      }
      setNotice(`${result.mode} suggestions loaded for review. Nothing has been saved.`);
    } catch (error) {
      setNotice(error instanceof Error ? error.message : 'Could not load suggestions.');
    }
  }

  function autocalPath() {
    if (sourceMode !== 'LIVE READ-ONLY') return '/api/autocal/preview';
    if (!selectedLotData) throw new Error('Select a Lot before requesting LIVE READ-ONLY AutoCal.');
    if (!liveWindowConfirmed || !liveWindowStart || !liveWindowEnd) throw new Error('Enter and confirm the selected Lot time window before requesting live AutoCal.');
    if (Intl.DateTimeFormat().resolvedOptions().timeZone !== 'Asia/Bangkok') throw new Error('Set the workstation timezone to Asia/Bangkok before selecting the Lot window.');
    const query = new URLSearchParams({ lot_id: String(selectedLotData.id), start_at: new Date(liveWindowStart).toISOString(), end_at: new Date(liveWindowEnd).toISOString(), window_confirmed: 'true' });
    return `/api/autocal/preview?${query.toString()}`;
  }

  async function saveProduction(event: FormEvent) {
    event.preventDefault();
    const result = await act('/api/production/save', { lot_id: Number(selectedLot), actual_drops: Number(drops), wet_good_pieces: Number(goodPieces), operator_note: productionNote });
    if (result) setProductionNote('');
  }

  async function saveReject(event: FormEvent) {
    event.preventDefault();
    const quantities = Object.fromEntries(data.reject_reasons.map((reason) => [reason.code, Number(rejectCounts[reason.code] ?? 0)]));
    const result = await act('/api/wet-reject/save', { lot_id: Number(selectedLot), quantities, operator_note: rejectNote });
    if (result) setRejectNote('');
  }

  async function saveRunEvent(event: FormEvent) {
    event.preventDefault();
    const result = await act('/api/wet-run-log/events', { category: eventCategory, started_at: new Date(eventStart).toISOString(), ended_at: eventEnd ? new Date(eventEnd).toISOString() : null, note: eventNote });
    if (result) { setEventNote(''); setEventEnd(''); }
  }

  async function saveLifecycle(event: FormEvent, type: 'curing' | 'depallet') {
    event.preventDefault();
    const result = await act(type === 'curing' ? '/api/curing/entries' : '/api/depallet/events', { lot_id: Number(selectedLot), quantity: Number(lifecycleQty || 0), note: lifecycleNote });
    if (result) { setLifecycleQty(''); setLifecycleNote(''); }
  }

  async function createLot(event: FormEvent) {
    event.preventDefault();
    const result = await act<Lot>('/api/lots', { product_id: Number(newProduct), previous_lot_id: Number(selectedLot), transition: lotTransition, color: newColor, lot_name: newLotName });
    if (result) { setNewLotName(''); setSelectedLot(String(result.id)); setPage('Production'); setOpenNavGroup('Production'); }
  }

  async function saveLotRename(event: FormEvent) {
    event.preventDefault();
    if (renameTarget === null) return;
    const result = await act(`/api/lots/${renameTarget}/rename`, { new_name: renameName, reason: renameReason });
    if (result) { setRenameTarget(null); setRenameName(''); setRenameReason(''); }
  }

  async function saveMouldTransition(event: FormEvent) {
    event.preventDefault();
    const action = mouldAction;
    const mould = data.moulds.find((item) => String(item.id) === selectedMould);
    const label = action === 'SEND_TO_RECONDITION' ? 'send to recondition' : 'approve return from recondition';
    if (!window.confirm(`Confirm ${label} for ${mould?.code ?? `Mould #${selectedMould}`}?`)) return;
    const result = await act(`/api/moulds/${selectedMould}/transition`, { action, reason: mouldReason });
    if (result) {
      setMouldReason('');
      setMouldAction(action === 'SEND_TO_RECONDITION' ? 'APPROVE_RETURN' : 'SEND_TO_RECONDITION');
    }
  }

  function lotSelector() {
    return <label className="field"><span>Production Lot · select by immutable ID</span><select value={selectedLot} onChange={(event) => setSelectedLot(event.target.value)}>{data.lots.map((lot) => {
      const product = data.products.find((item) => item.id === lot.product_id);
      return <option key={lot.id} value={lot.id}>#{lot.id} · {lot.lot_name} · {product?.code ?? 'Unknown'} · {lot.color}</option>;
    })}</select></label>;
  }

  function liveWindowControls() {
    if (sourceMode !== 'LIVE READ-ONLY') return null;
    return <section className="source-window-entry" aria-label="Confirm Lot time window"><strong>Lot-window confirmation required</strong><p>Lot records remain mock-only. Use the verified production start/end for this Lot; unconfirmed windows will not produce live suggestions.</p><div className="grid two-col"><label className="field"><span>Lot window start · Asia/Bangkok</span><input type="datetime-local" value={liveWindowStart} onChange={(event) => { setLiveWindowStart(event.target.value); setLiveWindowConfirmed(false); }} /></label><label className="field"><span>Lot window end · Asia/Bangkok</span><input type="datetime-local" value={liveWindowEnd} onChange={(event) => { setLiveWindowEnd(event.target.value); setLiveWindowConfirmed(false); }} /></label></div><label className="source-confirm-check"><input type="checkbox" checked={liveWindowConfirmed} onChange={(event) => setLiveWindowConfirmed(event.target.checked)} /><span>I verified this time window for the selected Lot. This does not save quantities.</span></label></section>;
  }

  function pageContent() {
    if (page === 'Production') return <>
      <div className="hero-row"><div><div className="eyebrow">WET LINE · LIVE WORKSPACE</div><h2>Production entry</h2><p className="subtle">Review AutoCal suggestions, correct them if needed, then save deliberately.</p></div><button className="button secondary" onClick={() => { setNewLotName(''); setPage('Settings'); }}>＋ New Run / Lot</button></div>
      <div className="callout"><span className="callout-icon">✦</span><div><strong>AutoCal is suggestion-only</strong><p>{sourceMode === 'LIVE READ-ONLY' ? 'Live source observations remain read-only. Enter and confirm the Lot time window; explicit SAVE remains mock-only.' : 'PLC and camera values are mocked. Operator edits and explicit SAVE are required.'}</p></div><button className="button dark" onClick={() => void loadAutoCal()}>{sourceMode === 'LIVE READ-ONLY' ? 'Load LIVE AutoCal' : 'Load AutoCal'}</button></div>
      {liveWindowControls()}
      <div className="grid two-col top-gap">
        <section className="card form-card"><div className="card-head"><div><span className="eyebrow">PRODUCTION RECORD</span><h3>Confirm quantities</h3></div><span className="tag muted">MOCK ENTRY</span></div>
          {lotSelector()}
          {selectedLotData && <div className="product-summary"><div className="product-icon">{selectedProduct?.family === 'Fence' ? '▥' : '▦'}</div><div><strong>{selectedProduct?.name ?? 'Unknown Product'}</strong><small>{selectedProduct?.code} · {selectedProduct?.family} · Lot ID #{selectedLotData.id}</small></div><span className="tag green">ACTIVE LOT</span></div>}
          <form onSubmit={saveProduction}>
            <div className="grid two-col"><label className="field"><span>Press Drops <em>Drop count, not Pieces</em></span><input type="number" min="0" value={drops} onChange={(event) => setDrops(event.target.value)} required /></label><label className="field"><span>Wet Good Pieces <em>Camera tray count</em></span><input type="number" min="0" value={goodPieces} onChange={(event) => setGoodPieces(event.target.value)} required /></label></div>
            <label className="field"><span>Operator note / override reason</span><input value={productionNote} onChange={(event) => setProductionNote(event.target.value)} placeholder="Required for a manual override in production" /></label>
            <div className="form-footer"><span className="subtle tiny">This button saves only to process-local mock state.</span><button className="button primary" type="submit">Save production entry <span>→</span></button></div>
          </form>
          {autoCal && <details className="source-details"><summary>{autoCal.mode} · AutoCal notes · suggestion not saved</summary><ul>{autoCal.source_notes.map((note) => <li key={note}>{note}</li>)}</ul>{autoCal.source_errors && Object.entries(autoCal.source_errors).map(([source, error]) => <p className="source-error" key={source}>{source}: {error}</p>)}<div className="code-row">Counter suggestions: {Object.entries(autoCal.suggested_wet_rejects).map(([key, value]) => <span key={key}>{key}: {value ?? 'Not verified'}</span>)}</div></details>}
        </section>
        <section className="card"><div className="card-head"><div><span className="eyebrow">CURRENT CONTEXT</span><h3>Run overview</h3></div><span className="status-dot">● RUNNING · DEMO</span></div>
          <div className="context-grid"><div><small>Product</small><strong>{selectedProduct?.code ?? '—'}</strong></div><div><small>Color</small><strong>{selectedLotData?.color ?? '—'}</strong></div><div><small>Run ID</small><strong>#{selectedLotData?.run_id ?? '—'}</strong></div><div><small>Selected Lot ID</small><strong>#{selectedLotData?.id ?? '—'}</strong></div></div>
          <div className="divider"/><div className="standard-warning"><span>ⓘ</span><div><strong>Production standards not loaded</strong><p>Pieces/Drop and seconds/Drop are intentionally blank until standards are factory-approved.</p></div></div>
          <h4 className="section-label">RECENT SAVES</h4>
          {data.production_entries.length ? <div className="record-list">{[...data.production_entries].reverse().slice(0, 4).map((row, i) => <div className="record-row" key={String(row.id ?? i)}><span className="record-mark">✓</span><div><strong>{String(row.actual_drops)} Drops · {String(row.wet_good_pieces)} Pieces</strong><small>Lot #{String(row.lot_id)} · Mock session</small></div><span className="tag green">SAVED</span></div>)}</div> : <div className="empty-state"><span>◷</span><p>No entries saved in this session.</p><small>Suggestions never save automatically.</small></div>}
        </section>
      </div>
      <section className="card top-gap"><div className="card-head"><div><span className="eyebrow">LOT LOOKUP</span><h3>Traceable production lots</h3></div><label className="search-box"><span>⌕</span><input aria-label="Search lots" placeholder="Search ID, name or product" value={search} onChange={(event) => setSearch(event.target.value)} /></label></div><div className="table-wrap"><table><thead><tr><th>LOT ID</th><th>LOT NAME</th><th>PRODUCT</th><th>COLOR</th><th>RUN</th><th>STARTED</th><th></th></tr></thead><tbody>{filteredLots.map((lot) => { const product = data.products.find((item) => item.id === lot.product_id); return <tr key={lot.id}><td className="id-cell">#{lot.id}</td><td>{lot.lot_name}</td><td><strong>{product?.code}</strong><small className="cell-sub">{product?.name}</small></td><td>{lot.color}</td><td>#{lot.run_id}</td><td>{new Date(lot.started_at).toLocaleString()}</td><td><button className="text-button" onClick={() => { setRenameTarget(lot.id); setRenameName(lot.lot_name); }}>Rename</button></td></tr>; })}</tbody></table></div></section>
    </>;

    if (page === 'Wet Reject') return <>
      <PageIntro eyebrow="WET LINE · QUALITY" title="Wet Reject" subtitle="Dynamic counter suggestions are reviewed and explicitly saved per Lot." />
      <div className="callout"><span className="callout-icon">◈</span><div><strong>Counts use cntR* only</strong><p>Binary R* button states are excluded. {sourceMode === 'LIVE READ-ONLY' ? 'Live counter data is suggestion-only; SAVE remains mock-only.' : 'This screen uses mock counters and a dynamic reason list.'}</p></div><button className="button dark" onClick={() => void loadAutoCal()}>REJECT RECAL · SUGGESTION</button></div>
      <div className="grid two-col top-gap"><section className="card form-card"><div className="card-head"><div><span className="eyebrow">REVIEW & SAVE</span><h3>Reject reason quantities</h3></div><span className="tag muted">MOCK DATA</span></div>{lotSelector()}<form onSubmit={saveReject}><div className="reason-list">{data.reject_reasons.map((reason, index) => <label className="reason-row" key={reason.code}><span className="reason-num">{String(index + 1).padStart(2, '0')}</span><span className="reason-label"><strong>{reason.label}</strong><small>{reason.code}</small></span><input aria-label={`${reason.code} quantity`} type="number" min="0" value={rejectCounts[reason.code] ?? ''} onChange={(event) => setRejectCounts((current) => ({ ...current, [reason.code]: event.target.value }))} placeholder="0" /></label>)}</div><label className="field top-gap"><span>Operator note</span><input value={rejectNote} onChange={(event) => setRejectNote(event.target.value)} placeholder="Optional review context" /></label><div className="form-footer"><span className="subtle tiny">No balancing or auto-classification.</span><button className="button primary" type="submit">Save reject review →</button></div></form></section>
        <section className="card"><span className="eyebrow">SOURCE CHECK</span><h3>Suggestion snapshot</h3><div className="metric-big">{autoCal?.reject_total ?? '—'} <small>mock preview only</small></div><p className="subtle">{sourceMode === 'LIVE READ-ONLY' ? 'Live cntR* tags are separate cumulative counters. They are shown in source notes only and are not mapped to these mock reason fields.' : 'The counter values are displayed as a suggestion. The operator owns the final edited quantities.'}</p><div className="source-lines">{data.reject_reasons.map((reason) => <div key={reason.code}><span>{reason.label}<small>{reason.code}</small></span><strong>{sourceMode === 'LIVE READ-ONLY' ? 'No approved mapping' : autoCal?.suggested_wet_rejects[reason.code] ?? 'Not loaded'}</strong></div>)}</div>
          {autoCal && <details className="source-details"><summary>{autoCal.mode} · source counter suggestions · not saved</summary><ul>{autoCal.source_notes.map((note) => <li key={note}>{note}</li>)}</ul>{Object.entries(autoCal.suggested_wet_rejects).map(([tag, value]) => <div className="saved-chip" key={tag}>{tag}: {value ?? 'Not verified'}</div>)}</details>}
          <div className="notice-box">Reason names are demonstration labels, not an approved Reject Reason Master.</div><h4 className="section-label">SAVED MOCK REVIEWS</h4>{data.reject_entries.length ? data.reject_entries.slice().reverse().map((entry, i) => <div className="saved-chip" key={String(entry.id ?? i)}>Lot #{String(entry.lot_id)} · total {String(entry.total)}</div>) : <div className="empty-state compact">No reject records saved yet.</div>}</section></div>
    </>;

    if (page === 'Wet Run Log') return <>
      <PageIntro eyebrow="WET LINE · OPERATOR CLASSIFICATION" title="Wet Run Log" subtitle="Press + Wet Line is one coupled unit. Classifications remain manual and authoritative." />
      <div className="notice-box strong-notice">AutoRun is status evidence only. It never writes, replaces, or reclassifies an operator event.</div>
      <div className="grid two-col top-gap"><section className="card form-card"><div className="card-head"><div><span className="eyebrow">MANUAL ENTRY</span><h3>Record time event</h3></div><span className="tag blue">OPERATOR INPUT</span></div><form onSubmit={saveRunEvent}><label className="field"><span>Classification</span><select value={eventCategory} onChange={(event) => setEventCategory(event.target.value)}>{['RUNNING', 'SETUP', 'CHANGEOVER', 'IDLE', 'CLEANING', 'BREAKDOWN', 'SMDT'].map((value) => <option key={value}>{value}</option>)}</select></label><div className="grid two-col"><label className="field"><span>Start time</span><input type="datetime-local" value={eventStart} onChange={(event) => setEventStart(event.target.value)} required /></label><label className="field"><span>End time <em>leave blank if ongoing</em></span><input type="datetime-local" value={eventEnd} onChange={(event) => setEventEnd(event.target.value)} /></label></div><label className="field"><span>Operator note</span><textarea rows={3} value={eventNote} onChange={(event) => setEventNote(event.target.value)} placeholder="Context, cause, or handover note" /></label><div className="form-footer"><span className="subtle tiny">Open events stay open; no synthetic end.</span><button className="button primary" type="submit">Save manual event →</button></div></form></section>
        <section className="card"><div className="card-head"><div><span className="eyebrow">EVENT TIMELINE</span><h3>Wet line intervals</h3></div><span className="tag muted">MANUAL SOURCE</span></div><div className="timeline">{data.run_events.slice().reverse().map((event, index) => <div className="timeline-row" key={String(event.id ?? index)}><span className={`timeline-dot ${event.category === 'RUNNING' ? 'run' : 'stop'}`}/><div><div className="timeline-title"><strong>{String(event.category)}</strong><span className="tag blue">{String(event.source ?? 'DEMO')}</span></div><p>{new Date(String(event.started_at)).toLocaleString()} → {event.ended_at ? new Date(String(event.ended_at)).toLocaleString() : 'OPEN'}</p><small>{String(event.note ?? 'No note')}</small></div></div>)}</div><div className="notice-box top-gap">AutoRun state transitions and operator classifications are stored separately in this prototype.</div></section></div>
    </>;

    if (page === 'Wet OEE') return <>
      <PageIntro eyebrow="WET LINE · PERFORMANCE" title="Wet OEE preview" subtitle="A transparent, simulated view for factory review — not an operational KPI." />
      <div className="simulation-banner"><span>◉</span><div><strong>SIMULATED DATA · DO NOT USE FOR PRODUCTION DECISIONS</strong><p>Illustrative values only. Product standards are not loaded or approved.</p></div></div>
      {oee ? <><div className="oee-hero card"><div><span className="eyebrow">DEMO WINDOW</span><h3>{oee.window}</h3><span className="tag amber">{oee.standard_status}</span></div><div className="oee-score"><small>SIMULATED OEE</small><strong>{(oee.oee * 100).toFixed(1)}<em>%</em></strong></div></div><div className="grid three-col top-gap">{[['Availability', oee.availability], ['Performance', oee.performance], ['Quality', oee.quality]].map(([label, value]) => <div className="card metric-card" key={String(label)}><span>{label}</span><strong>{(Number(value) * 100).toFixed(1)}<em>%</em></strong><div className="meter"><i style={{ width: `${Number(value) * 100}%` }}/></div></div>)}</div><div className="grid two-col top-gap"><div className="card"><span className="eyebrow">ALIGNED INPUTS · SIMULATED</span><h3>Source preview</h3><div className="source-lines"><div><span>Actual Drops<small>ProductCnt accumulator</small></span><strong>{oee.actual_drops.toLocaleString()}</strong></div><div><span>Wet Good Pieces<small>IP Camera · line='wet'</small></span><strong>{oee.wet_good_pieces.toLocaleString()}</strong></div><div><span>Dry Line / Depallet<small>Excluded from Wet OEE</small></span><strong>Excluded</strong></div></div></div><div className="card"><span className="eyebrow">REVIEW NOTES</span><h3>Calculation boundaries</h3><ul className="clean-list">{oee.notes.map((note) => <li key={note}>{note}</li>)}</ul><div className="formula">OEE = Availability × Performance × Quality</div></div></div></> : <div className="card empty-state">OEE preview API is not available. Start the mock backend to view its labeled simulation.</div>}
    </>;

    if (page === 'Mould') {
      const mould = data.moulds.find((item) => String(item.id) === selectedMould);
      const mouldProduct = data.products.find((item) => item.id === mould?.product_id);
      return <><PageIntro eyebrow="LIFECYCLE · TOOLING" title="Mould management" subtitle="Each physical Mould belongs to exactly one Product; age uses Press Drops, not Pieces."/><div className="simulation-banner"><span>⚠</span><div><strong>SIMULATED MOULD REGISTER</strong><p>Age values and tools are demo records. Counter-boundary attribution is not production evidence.</p></div></div><div className="grid two-col top-gap"><section className="card"><span className="eyebrow">MOCK TOOL REGISTER</span><h3>Product-specific Moulds</h3><div className="table-wrap top-gap"><table><thead><tr><th>MOULD ID</th><th>PRODUCT</th><th>STATUS</th><th>CURRENT AGE · DROPS</th><th>LIFETIME · DROPS</th></tr></thead><tbody>{data.moulds.map((item) => { const product = data.products.find((value) => value.id === item.product_id); return <tr key={item.id} className={selectedMould === String(item.id) ? 'selected-row' : ''}><td><button className="text-button" onClick={() => { setSelectedMould(String(item.id)); setMouldAction(item.status === 'RECONDITION' ? 'APPROVE_RETURN' : 'SEND_TO_RECONDITION'); }}>#{item.id} · {item.code}</button></td><td><strong>{product?.code}</strong><small className="cell-sub">{product?.name}</small></td><td><span className={`tag ${item.status === 'ACTIVE' ? 'green' : 'amber'}`}>{item.status}</span></td><td>{item.current_age_drops.toLocaleString()}</td><td>{item.lifetime_age_drops.toLocaleString()}</td></tr>; })}</tbody></table></div><div className="notice-box">Mould-to-Product assignment is fixed in this demo. Color does not affect Mould eligibility or age.</div></section><section className="card form-card"><span className="eyebrow">RECONDITION HISTORY · MOCK</span><h3>Controlled lifecycle transition</h3><div className="trace-card"><div className="trace-icon">▰</div><div><small>SELECTED MOULD #{mould?.id ?? '—'}</small><strong>{mould?.code ?? '—'} · {mouldProduct?.code ?? '—'}</strong><span>Cycle {mould?.recondition_cycle ?? 0} · Current age {mould?.current_age_drops.toLocaleString() ?? '—'} drops</span></div></div><form onSubmit={saveMouldTransition} className="top-gap"><label className="field"><span>Transition</span><select value={mouldAction} onChange={(event) => setMouldAction(event.target.value as 'SEND_TO_RECONDITION' | 'APPROVE_RETURN')}><option value="SEND_TO_RECONDITION" disabled={mould?.status !== 'ACTIVE'}>Send to recondition</option><option value="APPROVE_RETURN" disabled={mould?.status !== 'RECONDITION'}>Approve return from recondition</option></select></label><label className="field"><span>Reason / approval note</span><textarea rows={3} value={mouldReason} onChange={(event) => setMouldReason(event.target.value)} required placeholder="Demo action reason" /></label><div className="notice-box">Approved return resets Current Age to zero. Lifetime Age remains unchanged. This control is simulated, not authenticated.</div><button className="button primary top-gap" type="submit">Save mock transition →</button></form></section></div><section className="card top-gap"><div className="card-head"><div><span className="eyebrow">AUDIT TRAIL</span><h3>Recent Mould transitions</h3></div><span className="tag amber">MOCK</span></div>{data.mould_history.length ? data.mould_history.slice().reverse().map((entry, index) => <div className="record-row" key={String(entry.id ?? index)}><span className="record-mark">↻</span><div><strong>{String(entry.action)} · Mould #{String(entry.mould_id)}</strong><small>{String(entry.reason)} · Current {String(entry.current_age_drops)} / Lifetime {String(entry.lifetime_age_drops)} Drops</small></div></div>) : <div className="empty-state compact">No recondition transitions recorded in this session.</div>}</section></>;
    }

    if (page === 'Curing' || page === 'Depallet') {
      const isCuring = page === 'Curing';
      const entries = isCuring ? data.curing_entries : data.depal_entries;
      return <><PageIntro eyebrow={`LIFECYCLE · ${isCuring ? 'CURING' : 'DEPALLET'}`} title={`${page} records`} subtitle="Every operation retains the original immutable Production Lot ID."/><div className="notice-box strong-notice">Demo screen only. Event grain and quantity units are not approved; sample values are not source records.</div><div className="grid two-col top-gap"><section className="card form-card"><div className="card-head"><div><span className="eyebrow">NEW MOCK RECORD</span><h3>{isCuring ? 'Add curing entry' : 'Add depallet event'}</h3></div><span className="tag muted">REVIEW ONLY</span></div><form onSubmit={(event) => void saveLifecycle(event, isCuring ? 'curing' : 'depallet')}>{lotSelector()}
<label className="field"><span>Quantity <em>placeholder only; unit unresolved</em></span><input type="number" min="0" value={lifecycleQty} onChange={(event) => setLifecycleQty(event.target.value)} placeholder="Leave blank / zero for demo" /></label><label className="field"><span>Note</span><textarea rows={3} value={lifecycleNote} onChange={(event) => setLifecycleNote(event.target.value)} placeholder="Do not enter production data"/></label><div className="form-footer"><span className="subtle tiny">References selected Lot ID #{selectedLot || '—'}.</span><button className="button primary" type="submit">Save mock record →</button></div></form></section><section className="card"><span className="eyebrow">TRACEABILITY</span><h3>Original Lot identity</h3><div className="trace-card"><div className="trace-icon">{isCuring ? '◉' : '▦'}</div><div><small>UPSTREAM PRODUCTION LOT</small><strong>#{selectedLotData?.id ?? '—'} · {selectedLotData?.lot_name ?? 'No lot selected'}</strong><span>{selectedProduct?.code ?? '—'} · {selectedLotData?.color ?? '—'}</span></div></div><div className="divider"/><h4 className="section-label">RECENT {page.toUpperCase()} RECORDS</h4>{entries.length ? entries.slice().reverse().map((entry, index) => <div className="record-row" key={String(entry.id ?? index)}><span className="record-mark">↗</span><div><strong>Lot #{String(entry.lot_id)} · qty {String(entry.quantity)}</strong><small>{String(entry.note ?? 'Demo record')}</small></div><span className="tag amber">MOCK</span></div>) : <div className="empty-state compact">No records in this mock session.</div>}</section></div></>;
    }

    return <><PageIntro eyebrow="SYSTEM · FACTORY REVIEW" title="Settings & data status" subtitle="Prototype controls and explicit boundaries for factory review."/><div className="simulation-banner"><span>⚠</span><div><strong>{sourceMode === 'LIVE READ-ONLY' ? 'LIVE READ-ONLY SOURCES · MOCK SAVES' : 'MOCK ONLY — NO DATABASE CONNECTION'}</strong><p>Every API save is process-local and is lost when the backend restarts.</p></div></div><div className="grid two-col top-gap"><section className="card"><span className="eyebrow">DEMO LOT CREATION</span><h3>Start a new Product or Color assignment</h3><p className="subtle">Product change creates a new demo Run and Lot; Color change creates a Lot in the existing Run. Production authorization and standard snapshots require review.</p><form onSubmit={createLot}>{lotSelector()}<label className="field"><span>Transition type</span><select value={lotTransition} onChange={(event) => setLotTransition(event.target.value as 'PRODUCT_CHANGE' | 'COLOR_CHANGE')}><option value="PRODUCT_CHANGE">Product change · new Run + Lot</option><option value="COLOR_CHANGE">Color change · same Run, new Lot</option></select></label><label className="field"><span>Product</span><select value={newProduct} onChange={(event) => setNewProduct(event.target.value)}>{data.products.map((product) => <option key={product.id} value={product.id}>{product.code} · {product.name}</option>)}</select></label><div className="grid two-col"><label className="field"><span>Color</span><input value={newColor} onChange={(event) => setNewColor(event.target.value)} /></label><label className="field"><span>Display LotName</span><input value={newLotName} onChange={(event) => setNewLotName(event.target.value)} placeholder="Duplicate names are allowed" required /></label></div><button className="button primary" type="submit">Create mock Lot →</button></form></section><section className="card"><span className="eyebrow">CONNECTION & APPROVAL GATES</span><h3>Not configured for production</h3><div className="check-list">{['SQL target does not match the current local environment configuration', 'Legacy dbo remains read-only and unmodified', 'No migration has been executed', 'Product standards / reason masters are not approved', 'Authentication and operator audit identity are not configured'].map((item) => <div key={item}><span>!</span>{item}</div>)}</div><div className="notice-box">Credentials are never displayed. Live access remains blocked until the approved endpoint, instance, SELECT-only permissions, source metadata, and timestamp policies are explicitly verified.</div></section></div><div className="grid three-col top-gap"><StatCard label="SQL database" value={sourceHealth?.connected ? 'LIVE · READ ONLY' : sourceMode === 'MOCK' ? 'MOCK MODE' : 'NOT CONNECTED'} tone={sourceHealth?.connected ? 'green' : 'amber'}/><StatCard label="Backend mode" value={sourceMode} tone={sourceMode === 'LIVE READ-ONLY' ? 'blue' : sourceMode === 'MOCK' ? 'green' : 'amber'}/><StatCard label="Write capability" value="MOCK ONLY" tone="blue"/></div></>;
  }

  return <div className="app-shell">
    <main className="main">
      <header className="topbar">
        <div className="topbar-identity"><span className="brand-mark">O<span>·</span></span><div><div className="breadcrumbs">OMAGMES <span>/</span> <strong>{page}</strong></div><small>FACTORY REVIEW · WET LINE</small></div></div>
        <div className="top-actions"><span className={`source-mode-badge ${sourceMode === 'LIVE READ-ONLY' ? 'live' : sourceMode === 'MOCK' ? 'mock' : 'unknown'}`} role="status">{sourceMode}</span><span className={`connection ${connected ? 'on' : ''}`}><i />{connected ? 'API connected' : 'API offline'}</span><span className="top-date">Production Date&nbsp; 08 Nov 2026</span><div className="top-avatar" aria-label="Demo operator">OP</div></div>
      </header>
      <div className="page-wrap">
        <nav className="fitting-navigation" aria-label="Main navigation">
          <div className="fitting-tabs-main">
            {['Production', 'Depallet', 'Setting'].map((group) => {
              const groupPages = pages.filter((item) => item.group === group);
              const active = groupPages.some((item) => item.name === page);
              return <button key={group} type="button" className={`fitting-group-tab ${active ? 'is-active' : ''} ${openNavGroup === group ? 'is-open' : ''}`} aria-expanded={openNavGroup === group} onClick={() => {
                if (openNavGroup === group) setOpenNavGroup('');
                else {
                  setOpenNavGroup(group);
                  if (!active && groupPages[0]) setPage(groupPages[0].name);
                }
                setNotice('');
              }}>{group.toUpperCase()}</button>;
            })}
          </div>
          {openNavGroup && <div className="fitting-subnav" aria-label={`${openNavGroup} navigation`}>
            {pages.filter((item) => item.group === openNavGroup).map((item) => <button key={item.name} type="button" className={`fitting-page-tab ${page === item.name ? 'is-current' : ''}`} aria-current={page === item.name ? 'page' : undefined} onClick={() => { setPage(item.name); setNotice(''); }}>{item.name.toUpperCase()}</button>)}
          </div>}
        </nav>
        <div className="review-strip"><span>◉</span> SOURCE MODE: {sourceMode} <i /> {sourceMode === 'LIVE READ-ONLY' ? 'SQL reads are live/read-only; displayed Lots, reject reasons, and entry forms remain mock context. SAVE is mock-only; no Lot attribution or reason mapping is verified.' : sourceMode === 'MOCK' ? 'Mock sources and process-local saves; do not use for production decisions.' : 'Source mode unavailable; no live values are displayed.'}</div>
        <SourceStatusPanel mode={sourceMode} health={sourceHealth} dashboard={sourceDashboard} />
        {notice && <div className={`toast ${notice.startsWith('Saved') || notice.toLowerCase().includes('suggestions loaded') ? 'success' : 'error'}`} role={notice.startsWith('Saved') || notice.toLowerCase().includes('suggestions loaded') ? 'status' : 'alert'} aria-live="polite">{notice}</div>}
        {pageContent()}
        {page === 'Settings' && <MasterDataReview products={data.products} rejectReasons={data.reject_reasons} />}
        <footer>OMAGMES FACTORY REVIEW <span>·</span> {sourceMode} sources <span>·</span> Saves remain process-local mock state</footer>
      </div>
    </main>
    {renameTarget !== null && <div className="modal-backdrop" role="presentation" onClick={(event) => { if (event.target === event.currentTarget) setRenameTarget(null); }}><section className="card rename-modal" role="dialog" aria-modal="true" aria-labelledby="rename-title"><button className="modal-close" aria-label="Close" onClick={() => setRenameTarget(null)}>×</button><span className="eyebrow">AUDITED LOTNAME CHANGE · MOCK</span><h3 id="rename-title">Rename Lot #{renameTarget}</h3><p className="subtle">Lot ID and downstream links never change. Duplicate LotNames are allowed.</p><form onSubmit={saveLotRename} className="top-gap"><label className="field"><span>New display name</span><input value={renameName} onChange={(event) => setRenameName(event.target.value)} required /></label><label className="field"><span>Change reason</span><textarea rows={3} value={renameReason} onChange={(event) => setRenameReason(event.target.value)} required placeholder="Explain why the display name is changing" /></label><button className="button primary" type="submit">Save rename history →</button></form></section></div>}
  </div>;
}

function MasterDataReview({ products, rejectReasons }: { products: Product[]; rejectReasons: Reason[] }) {
  return <section className="card top-gap" aria-label="OmagMES master data review">
    <div className="card-head"><div><span className="eyebrow">SETTING · MASTER REVIEW</span><h3>OmagMES reference data</h3></div><span className="tag amber">READ ONLY · NOT APPROVED</span></div>
    <p className="notice-box">Demo labels only. No source master was imported; Product standards and reject-reason approval remain pending.</p>
    <div className="grid two-col top-gap">
      <section aria-label="Product master review"><h4 className="section-label">PRODUCT MASTER & STANDARDS</h4><div className="table-wrap"><table><thead><tr><th>CODE</th><th>PRODUCT</th><th>FAMILY</th><th>PIECES / DROP</th><th>SECONDS / DROP</th><th>STATUS</th></tr></thead><tbody>{products.map((product) => <tr key={product.id}><td className="id-cell">{product.code}</td><td>{product.name}</td><td>{product.family}</td><td>{product.standard_pieces_per_drop ?? 'Not approved'}</td><td>{product.standard_cycle_time_sec ?? 'Not approved'}</td><td><span className="tag amber">DEMO ONLY</span></td></tr>)}</tbody></table></div></section>
      <section aria-label="Wet reject counter review"><h4 className="section-label">WET REJECT COUNTERS</h4><div className="table-wrap"><table><thead><tr><th>COUNTER</th><th>DEMO LABEL</th><th>SOURCE RULE</th><th>STATUS</th></tr></thead><tbody>{rejectReasons.map((reason) => <tr key={reason.code}><td className="id-cell">{reason.code}</td><td>{reason.label}</td><td>Dynamic cntR* quantity</td><td><span className="tag amber">UNAPPROVED</span></td></tr>)}</tbody></table></div><p className="subtle">Binary R* button states are excluded; counter mappings require owner confirmation.</p></section>
    </div>
  </section>;
}

function SourceStatusPanel({ mode, health, dashboard }: { mode: SourceMode; health: SourceHealth | null; dashboard: SourceDashboard | null }) {
  if (mode === 'MOCK') {
    return <section className="source-mode-panel mock" aria-label="Source mode status"><strong>MOCK SOURCES ACTIVE</strong><span>Live SQL is not queried. SAVE remains process-local mock state.</span></section>;
  }
  if (mode === 'UNKNOWN') {
    return <section className="source-mode-panel error" role="alert" aria-label="Source mode unavailable"><strong>SOURCE MODE UNKNOWN</strong><span>{health?.error ?? 'API unavailable; live data is not displayed and no fallback was made.'}</span></section>;
  }

  const statusObservation = dashboard?.wet_status?.observation;
  const pressObservation = dashboard?.press_counter;
  const errors = { ...(health?.error ? { connection: health.error } : {}), ...(dashboard?.source_errors ?? {}) };
  return <section className="source-live-panel" aria-label="Live read-only source status" aria-live="polite">
    <div className="source-live-heading"><div><strong>LIVE READ-ONLY SOURCES</strong><span>Operator SAVE remains process-local mock state.</span></div><span className={`tag ${health?.connected ? 'green' : 'amber'}`}>{health?.connected && health.read_only_permissions_verified ? 'CONNECTED · SELECT ONLY' : 'SOURCE ERROR'}</span></div>
    {health?.connected && <p className="source-target">Target verified: {health.server} {health.instance ? `· ${health.instance}` : '· default instance'} · {health.database}</p>}
    <div className="source-live-metrics">
      <div><small>WET LINE · AUTORUN</small><strong>{dashboard?.wet_status?.status ?? 'UNKNOWN'}</strong><span>{String(statusObservation?._TIMESTAMP ?? 'No observation')}</span></div>
      <div><small>LATEST PRODUCTCNT</small><strong>{pressObservation?._VALUE === undefined ? '—' : String(pressObservation._VALUE)}</strong><span>{String(pressObservation?._TIMESTAMP ?? 'No observation')} · quality {String(pressObservation?._QUALITY ?? '—')}</span></div>
      <div><small>WET CAMERA PIECES · LOT WINDOW</small><strong>{dashboard?.wet_camera_pieces ?? 'Not verified'}</strong><span>Individual wet-tray counts; dry excluded</span></div>
      <div><small>WET REJECT · LATEST CUMULATIVE COUNTERS</small><strong>{dashboard && Object.keys(dashboard.wet_reject_counts).length ? Object.entries(dashboard.wet_reject_counts).map(([tag, value]) => `${tag.slice(tag.lastIndexOf('.') + 1)}: ${value ?? '—'}`).join(' · ') : 'Not available'}</strong><span>cntR* only; not Lot quantities; R* excluded</span></div>
    </div>
    <p className="source-last-seen">Last source observation: {dashboard?.last_observation_at ?? 'Not available'}</p>
    {Object.entries(errors).map(([source, message]) => <p className="source-error" role="alert" key={source}>{source}: {message}</p>)}
    {dashboard?.warnings.map((warning, index) => <p className="source-warning" key={`${index}-${warning}`}>{warning}</p>)}
  </section>;
}

function PageIntro({ eyebrow, title, subtitle }: { eyebrow: string; title: string; subtitle: string }) {
  return <div className="page-intro"><div><div className="eyebrow">{eyebrow}</div><h2>{title}</h2><p className="subtle">{subtitle}</p></div><div className="date-pill">◷ &nbsp;08 Nov 2026</div></div>;
}

function StatCard({ label, value, tone }: { label: string; value: string; tone: string }) {
  return <div className="card stat-card"><span>{label}</span><strong className={tone}>{value}</strong></div>;
}

export default App;
