import { useCallback, useEffect, useMemo, useState, type FormEvent } from 'react';

type Product = { id: number; code: string; name: string; family: string; standard_pieces_per_drop: number | null; standard_cycle_time_sec: number | null };
type Lot = { id: number; run_id: number; product_id: number; color: string; lot_name: string; started_at: string };
type Reason = { code: string; label: string };
type Mould = { id: number; code: string; product_id: number; status: string; current_age_drops: number; lifetime_age_drops: number; recondition_cycle: number };
type RecordRow = Record<string, unknown>;
type Bootstrap = { mode: string; products: Product[]; lots: Lot[]; reject_reasons: Reason[]; production_entries: RecordRow[]; reject_entries: RecordRow[]; run_events: RecordRow[]; curing_entries: RecordRow[]; depal_entries: RecordRow[]; moulds: Mould[]; mould_history: RecordRow[] };
type AutoCal = { mode: string; suggested_actual_drops: number; suggested_wet_good_pieces: number; suggested_wet_rejects: Record<string, number>; reject_total: number; source_notes: string[] };
type Oee = { mode: string; window: string; availability: number; performance: number; quality: number; oee: number; actual_drops: number; wet_good_pieces: number; standard_status: string; notes: string[] };

type Page = 'Production' | 'Wet Reject' | 'Wet Run Log' | 'Wet OEE' | 'Curing' | 'Depallet' | 'Mould' | 'Settings';
const API = import.meta.env.VITE_API_URL ?? 'http://127.0.0.1:8000';
const pages: { name: Page; icon: string; group: string }[] = [
  { name: 'Production', icon: '◫', group: 'OPERATIONS' },
  { name: 'Wet Reject', icon: '◈', group: 'OPERATIONS' },
  { name: 'Wet Run Log', icon: '◷', group: 'OPERATIONS' },
  { name: 'Wet OEE', icon: '◌', group: 'INSIGHTS' },
  { name: 'Curing', icon: '▤', group: 'LIFECYCLE' },
  { name: 'Depallet', icon: '▦', group: 'LIFECYCLE' },
  { name: 'Mould', icon: '▰', group: 'LIFECYCLE' },
  { name: 'Settings', icon: '⚙', group: 'SYSTEM' },
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
  const response = await fetch(`${API}${path}`, { ...init, headers: { 'Content-Type': 'application/json', ...init?.headers } });
  if (!response.ok) {
    const body = await response.json().catch(() => null) as { detail?: string } | null;
    throw new Error(body?.detail ?? `Request failed (${response.status})`);
  }
  return response.json() as Promise<T>;
}

function App() {
  const [page, setPage] = useState<Page>('Production');
  const [data, setData] = useState<Bootstrap>(fallback);
  const [connected, setConnected] = useState(false);
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
      const [boot, status] = await Promise.all([request<Bootstrap>('/api/bootstrap'), request<{ status: string }>('/api/health')]);
      setData(boot);
      setConnected(status.status === 'ok');
      setSelectedLot((current) => boot.lots.some((lot) => String(lot.id) === current) ? current : String(boot.lots[0]?.id ?? ''));
    } catch {
      setConnected(false);
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
      setNotice('Saved to mock session. No production database was changed.');
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
      const result = await request<AutoCal>('/api/autocal/preview');
      setAutoCal(result);
      setDrops(String(result.suggested_actual_drops));
      setGoodPieces(String(result.suggested_wet_good_pieces));
      setRejectCounts(Object.fromEntries(Object.entries(result.suggested_wet_rejects).map(([key, value]) => [key, String(value)])));
      setNotice('Suggestions loaded for review. Nothing has been saved.');
    } catch (error) {
      setNotice(error instanceof Error ? error.message : 'Could not load suggestions.');
    }
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
    if (result) { setNewLotName(''); setSelectedLot(String(result.id)); setPage('Production'); }
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

  function pageContent() {
    if (page === 'Production') return <>
      <div className="hero-row"><div><div className="eyebrow">WET LINE · LIVE WORKSPACE</div><h2>Production entry</h2><p className="subtle">Review AutoCal suggestions, correct them if needed, then save deliberately.</p></div><button className="button secondary" onClick={() => { setNewLotName(''); setPage('Settings'); }}>＋ New Run / Lot</button></div>
      <div className="callout"><span className="callout-icon">✦</span><div><strong>AutoCal is suggestion-only</strong><p>PLC and camera values are mocked. Operator edits and explicit SAVE are required.</p></div><button className="button dark" onClick={() => void loadAutoCal()}>Load AutoCal</button></div>
      <div className="grid two-col top-gap">
        <section className="card form-card"><div className="card-head"><div><span className="eyebrow">PRODUCTION RECORD</span><h3>Confirm quantities</h3></div><span className="tag muted">MOCK ENTRY</span></div>
          {lotSelector()}
          {selectedLotData && <div className="product-summary"><div className="product-icon">{selectedProduct?.family === 'Fence' ? '▥' : '▦'}</div><div><strong>{selectedProduct?.name ?? 'Unknown Product'}</strong><small>{selectedProduct?.code} · {selectedProduct?.family} · Lot ID #{selectedLotData.id}</small></div><span className="tag green">ACTIVE LOT</span></div>}
          <form onSubmit={saveProduction}>
            <div className="grid two-col"><label className="field"><span>Press Drops <em>Drop count, not Pieces</em></span><input type="number" min="0" value={drops} onChange={(event) => setDrops(event.target.value)} required /></label><label className="field"><span>Wet Good Pieces <em>Camera tray count</em></span><input type="number" min="0" value={goodPieces} onChange={(event) => setGoodPieces(event.target.value)} required /></label></div>
            <label className="field"><span>Operator note / override reason</span><input value={productionNote} onChange={(event) => setProductionNote(event.target.value)} placeholder="Required for a manual override in production" /></label>
            <div className="form-footer"><span className="subtle tiny">This button saves only to process-local mock state.</span><button className="button primary" type="submit">Save production entry <span>→</span></button></div>
          </form>
          {autoCal && <details className="source-details"><summary>AutoCal source notes · suggestion not saved</summary><ul>{autoCal.source_notes.map((note) => <li key={note}>{note}</li>)}</ul><div className="code-row">Dynamic reject counters: {Object.entries(autoCal.suggested_wet_rejects).map(([key, value]) => <span key={key}>{key}: {value}</span>)}</div></details>}
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
      <div className="callout"><span className="callout-icon">◈</span><div><strong>Counts use cntR* only</strong><p>Binary R* button states are excluded. This screen uses mock counters and a dynamic reason list.</p></div><button className="button dark" onClick={() => void loadAutoCal()}>Refresh suggestions</button></div>
      <div className="grid two-col top-gap"><section className="card form-card"><div className="card-head"><div><span className="eyebrow">REVIEW & SAVE</span><h3>Reject reason quantities</h3></div><span className="tag muted">MOCK DATA</span></div>{lotSelector()}<form onSubmit={saveReject}><div className="reason-list">{data.reject_reasons.map((reason, index) => <label className="reason-row" key={reason.code}><span className="reason-num">{String(index + 1).padStart(2, '0')}</span><span className="reason-label"><strong>{reason.label}</strong><small>{reason.code}</small></span><input aria-label={`${reason.code} quantity`} type="number" min="0" value={rejectCounts[reason.code] ?? ''} onChange={(event) => setRejectCounts((current) => ({ ...current, [reason.code]: event.target.value }))} placeholder="0" /></label>)}</div><label className="field top-gap"><span>Operator note</span><input value={rejectNote} onChange={(event) => setRejectNote(event.target.value)} placeholder="Optional review context" /></label><div className="form-footer"><span className="subtle tiny">No balancing or auto-classification.</span><button className="button primary" type="submit">Save reject review →</button></div></form></section>
        <section className="card"><span className="eyebrow">SOURCE CHECK</span><h3>Suggestion snapshot</h3><div className="metric-big">{autoCal?.reject_total ?? '—'} <small>mock rejects</small></div><p className="subtle">The counter values are displayed as a suggestion. The operator owns the final edited quantities.</p><div className="source-lines">{data.reject_reasons.map((reason) => <div key={reason.code}><span>{reason.label}<small>{reason.code}</small></span><strong>{autoCal?.suggested_wet_rejects[reason.code] ?? 'Not loaded'}</strong></div>)}</div><div className="notice-box">Reason names are demonstration labels, not an approved Reject Reason Master.</div><h4 className="section-label">SAVED MOCK REVIEWS</h4>{data.reject_entries.length ? data.reject_entries.slice().reverse().map((entry, i) => <div className="saved-chip" key={String(entry.id ?? i)}>Lot #{String(entry.lot_id)} · total {String(entry.total)}</div>) : <div className="empty-state compact">No reject records saved yet.</div>}</section></div>
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
      return <><PageIntro eyebrow={`LIFECYCLE · ${isCuring ? 'CURING' : 'DEPALLET'}`} title={`${page} records`} subtitle="Every operation retains the original immutable Production Lot ID."/><div className="notice-box strong-notice">Demo screen only. Event grain and quantity units are not approved; sample values are not source records.</div><div className="grid two-col top-gap"><section className="card form-card"><div className="card-head"><div><span className="eyebrow">NEW MOCK RECORD</span><h3>{isCuring ? 'Add curing entry' : 'Add depallet event'}</h3></div><span className="tag muted">REVIEW ONLY</span></div><form onSubmit={(event) => void saveLifecycle(event, isCuring ? 'curing' : 'depallet')}>{lotSelector()}<label className="field"><span>Quantity <em>placeholder only; unit unresolved</em></span><input type="number" min="0" value={lifecycleQty} onChange={(event) => setLifecycleQty(event.target.value)} placeholder="Leave blank / zero for demo" /></label><label className="field"><span>Note</span><textarea rows={3} value={lifecycleNote} onChange={(event) => setLifecycleNote(event.target.value)} placeholder="Do not enter production data"/></label><div className="form-footer"><span className="subtle tiny">References selected Lot ID #{selectedLot || '—'}.</span><button className="button primary" type="submit">Save mock record →</button></div></form></section><section className="card"><span className="eyebrow">TRACEABILITY</span><h3>Original Lot identity</h3><div className="trace-card"><div className="trace-icon">{isCuring ? '◉' : '▦'}</div><div><small>UPSTREAM PRODUCTION LOT</small><strong>#{selectedLotData?.id ?? '—'} · {selectedLotData?.lot_name ?? 'No lot selected'}</strong><span>{selectedProduct?.code ?? '—'} · {selectedLotData?.color ?? '—'}</span></div></div><div className="divider"/><h4 className="section-label">RECENT {page.toUpperCase()} RECORDS</h4>{entries.length ? entries.slice().reverse().map((entry, index) => <div className="record-row" key={String(entry.id ?? index)}><span className="record-mark">↗</span><div><strong>Lot #{String(entry.lot_id)} · qty {String(entry.quantity)}</strong><small>{String(entry.note ?? 'Demo record')}</small></div><span className="tag amber">MOCK</span></div>) : <div className="empty-state compact">No records in this mock session.</div>}</section></div></>;
    }

    return <><PageIntro eyebrow="SYSTEM · FACTORY REVIEW" title="Settings & data status" subtitle="Prototype controls and explicit boundaries for factory review."/><div className="simulation-banner"><span>⚠</span><div><strong>MOCK ONLY — NO DATABASE CONNECTION</strong><p>Every API save is process-local and is lost when the backend restarts.</p></div></div><div className="grid two-col top-gap"><section className="card"><span className="eyebrow">DEMO LOT CREATION</span><h3>Start a new Product or Color assignment</h3><p className="subtle">Product change creates a new demo Run and Lot; Color change creates a Lot in the existing Run. Production authorization and standard snapshots require review.</p><form onSubmit={createLot}>{lotSelector()}<label className="field"><span>Transition type</span><select value={lotTransition} onChange={(event) => setLotTransition(event.target.value as 'PRODUCT_CHANGE' | 'COLOR_CHANGE')}><option value="PRODUCT_CHANGE">Product change · new Run + Lot</option><option value="COLOR_CHANGE">Color change · same Run, new Lot</option></select></label><label className="field"><span>Product</span><select value={newProduct} onChange={(event) => setNewProduct(event.target.value)}>{data.products.map((product) => <option key={product.id} value={product.id}>{product.code} · {product.name}</option>)}</select></label><div className="grid two-col"><label className="field"><span>Color</span><input value={newColor} onChange={(event) => setNewColor(event.target.value)} /></label><label className="field"><span>Display LotName</span><input value={newLotName} onChange={(event) => setNewLotName(event.target.value)} placeholder="Duplicate names are allowed" required /></label></div><button className="button primary" type="submit">Create mock Lot →</button></form></section><section className="card"><span className="eyebrow">CONNECTION & APPROVAL GATES</span><h3>Not configured for production</h3><div className="check-list">{['SQL target does not match the current local environment configuration', 'Legacy dbo remains read-only and unmodified', 'No migration has been executed', 'Product standards / reason masters are not approved', 'Authentication and operator audit identity are not configured'].map((item) => <div key={item}><span>!</span>{item}</div>)}</div><div className="notice-box">No credentials are displayed or used by the prototype. See the schema implementation gate in project docs.</div></section></div><div className="grid three-col top-gap"><StatCard label="SQL database" value="DISCONNECTED" tone="amber"/><StatCard label="Backend mode" value={connected ? 'MOCK API' : 'OFFLINE'} tone={connected ? 'green' : 'amber'}/><StatCard label="Write capability" value="MOCK ONLY" tone="blue"/></div></>;
  }

  return <div className="app-shell">
    <aside className="sidebar"><div className="brand"><div className="brand-mark">O<span>·</span></div><div><strong>OMAG<span>MES</span></strong><small>FACTORY REVIEW</small></div></div><div className="plant-card"><span className="plant-symbol">⌂</span><div><small>FACILITY</small><strong>OMAG · WET LINE</strong></div><span className="pulse"/></div><nav aria-label="Main navigation">{['OPERATIONS', 'INSIGHTS', 'LIFECYCLE', 'SYSTEM'].map((group) => <div className="nav-group" key={group}><span className="nav-label">{group}</span>{pages.filter((item) => item.group === group).map((item) => <button key={item.name} title={item.name} aria-label={item.name} className={`nav-item ${page === item.name ? 'active' : ''}`} onClick={() => { setPage(item.name); setNotice(''); }}><span className="nav-icon">{item.icon}</span>{item.name}{page === item.name && <span className="nav-arrow">›</span>}</button>)}</div>)}</nav><div className="sidebar-bottom"><div className="mock-badge"><span>●</span><div><strong>Review mode</strong><small>No production writes</small></div></div><div className="user-chip"><div className="avatar">OP</div><div><strong>Demo Operator</strong><small>Factory review</small></div><span>⌄</span></div></div></aside>
    <main className="main"><header className="topbar"><div className="breadcrumbs">OmagMES <span>/</span> <strong>{page}</strong></div><div className="top-actions"><span className={`connection ${connected ? 'on' : ''}`}><i/> {connected ? 'Mock API connected' : 'API offline'}</span><span className="top-date">◷ &nbsp;08 Nov 2026</span><div className="top-avatar">OP</div></div></header><div className="page-wrap"><div className="review-strip"><span>◉</span> FACTORY REVIEW PROTOTYPE <i/> All entries are mock data; do not use for production decisions.</div>{notice && <div className="toast" role="status">{notice}</div>}{pageContent()}<footer>OMAGMES FACTORY REVIEW <span>·</span> Mock-only prototype <span>·</span> No production database writes</footer></div></main>
    {renameTarget !== null && <div className="modal-backdrop" role="presentation" onClick={(event) => { if (event.target === event.currentTarget) setRenameTarget(null); }}><section className="card rename-modal" role="dialog" aria-modal="true" aria-labelledby="rename-title"><button className="modal-close" aria-label="Close" onClick={() => setRenameTarget(null)}>×</button><span className="eyebrow">AUDITED LOTNAME CHANGE · MOCK</span><h3 id="rename-title">Rename Lot #{renameTarget}</h3><p className="subtle">Lot ID and downstream links never change. Duplicate LotNames are allowed.</p><form onSubmit={saveLotRename} className="top-gap"><label className="field"><span>New display name</span><input value={renameName} onChange={(event) => setRenameName(event.target.value)} required /></label><label className="field"><span>Change reason</span><textarea rows={3} value={renameReason} onChange={(event) => setRenameReason(event.target.value)} required placeholder="Explain why the display name is changing" /></label><button className="button primary" type="submit">Save rename history →</button></form></section></div>}
  </div>;
}

function PageIntro({ eyebrow, title, subtitle }: { eyebrow: string; title: string; subtitle: string }) {
  return <div className="page-intro"><div><div className="eyebrow">{eyebrow}</div><h2>{title}</h2><p className="subtle">{subtitle}</p></div><div className="date-pill">◷ &nbsp;08 Nov 2026</div></div>;
}

function StatCard({ label, value, tone }: { label: string; value: string; tone: string }) {
  return <div className="card stat-card"><span>{label}</span><strong className={tone}>{value}</strong></div>;
}

export default App;
