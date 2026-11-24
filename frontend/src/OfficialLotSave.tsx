import { useEffect, useMemo, useState, type FormEvent } from 'react';
import type { ShiftScheduleContext } from './ShiftSchedule';
import type { ResetCandidate } from './AutoLotDrafts';

type Product = { id: number; code: string; name: string; standard_pieces_per_drop: number | null; standard_cycle_time_sec: number | null };
type Lot = { id: number; lot_name: string; lot_number?: string; product_id: number; color: string; started_at: string; lot_start_production_date?: string; lot_start_shift_id?: number; is_open?: boolean };
type SavedLot = Lot & { run_id: number; transition?: string; mode: string };

async function call<T>(path: string, method: string, body?: unknown): Promise<T> {
  const response = await fetch(path, {
    method,
    headers: { 'Content-Type': 'application/json' },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  });
  if (!response.ok) {
    const data = await response.json().catch(() => null) as { detail?: string } | null;
    throw new Error(data?.detail ?? `Request failed (${response.status})`);
  }
  return response.json() as Promise<T>;
}

function bangkokIso(value: string) {
  return `${value}:00+07:00`;
}

export default function OfficialLotSave({
  id,
  productionDate,
  schedule,
  products,
  lots,
  resetCandidate,
  onSaved,
  onContinue,
}: {
  id: string;
  productionDate: string;
  schedule: ShiftScheduleContext | null;
  products: Product[];
  lots: Lot[];
  resetCandidate: ResetCandidate | null;
  onSaved: () => Promise<void>;
  onContinue: (lotId: number) => void;
}) {
  const [productId, setProductId] = useState('');
  const [previousLotId, setPreviousLotId] = useState('');
  const [color, setColor] = useState('');
  const [lotName, setLotName] = useState('');
  const [machineCode, setMachineCode] = useState('');
  const [operatorId, setOperatorId] = useState('');
  const [resetReason, setResetReason] = useState('');
  const [startedAt, setStartedAt] = useState('');
  const [proposal, setProposal] = useState('');
  const [saved, setSaved] = useState<SavedLot | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const selectedProduct = products.find((item) => String(item.id) === productId);
  const openLots = useMemo(() => lots.filter((item) => item.is_open), [lots]);
  const previousLot = openLots.find((item) => String(item.id) === previousLotId);
  const transition = useMemo(() => {
    if (!previousLot || String(previousLot.product_id) !== productId) return 'PRODUCT_CHANGE';
    return previousLot.color === color.trim() ? 'CONTINUE' : 'COLOR_CHANGE';
  }, [previousLot, productId, color]);

  useEffect(() => {
    if (!productId && products.length) setProductId(String(products[0].id));
  }, [productId, products]);
  useEffect(() => {
    if (!openLots.some((item) => String(item.id) === previousLotId)) setPreviousLotId(String(openLots[0]?.id ?? ''));
  }, [previousLotId, openLots]);
  useEffect(() => { setResetReason(''); }, [resetCandidate?.id]);

  async function getProposal() {
    setProposal('');
    setMessage('');
    if (!startedAt || !machineCode) {
      setMessage('Enter the proposed Lot start and select a machine code before requesting a number.');
      return;
    }
    try {
      const query = new URLSearchParams({ production_date: productionDate, started_at: bangkokIso(startedAt), machine_code: machineCode });
      const result = await call<{ proposed_lot_number: string; reserved: boolean; shift_name: string; shift_code: string }>(`/api/lots/number-proposal?${query}`, 'GET');
      setProposal(result.proposed_lot_number);
      setMessage(`${result.shift_name} / code ${result.shift_code}; proposal is not reserved. SAVE reallocates under a SQL lock.`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Number proposal unavailable.');
    }
  }

  async function save(event: FormEvent) {
    event.preventDefault();
    if (transition === 'CONTINUE' && previousLot) {
      onContinue(previousLot.id);
      setMessage(`Continuing original Lot #${previousLot.id} (${previousLot.lot_number ?? 'SCG number unavailable'}). Its start date, Shift, and number are unchanged; select production time and quantities below.`);
      return;
    }
    if (!productId || (openLots.length > 0 && !previousLotId) || !color.trim() || !lotName.trim() || !machineCode || !startedAt || !operatorId.trim() || (resetCandidate && !resetReason.trim())) {
      setMessage('Complete Product, required previous Lot, Color, LotName, machine code, start time, operator ID, and reset confirmation reason (if linked) before SAVE.');
      return;
    }
    if (!window.confirm(`Confirm ${transition === 'PRODUCT_CHANGE' ? 'Product' : 'Color'} change and explicitly SAVE the official Lot for ${productionDate}?`)) return;
    setBusy(true);
    setMessage('');
    try {
      const result = await call<SavedLot>('/api/lots', 'POST', {
        product_id: Number(productId),
        previous_lot_id: previousLotId ? Number(previousLotId) : null,
        transition,
        color: color.trim(),
        lot_name: lotName.trim(),
        machine_code: machineCode,
        operator_id: operatorId.trim(),
        started_at: bangkokIso(startedAt),
        production_date: productionDate,
        shift_schedule_version_id: schedule?.applicable_version_id,
        production_day_cutoff_version_id: schedule?.cutoff_version_id,
        reset_candidate_id: resetCandidate?.id ?? null,
        reset_confirmation_reason: resetCandidate ? resetReason.trim() : '',
      });
      setSaved(result);
      setProposal('');
      setMessage('Official Lot committed and read back from SQL.');
      await onSaved();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Official Lot SAVE failed. No mock fallback was used.');
    } finally {
      setBusy(false);
    }
  }

  return <section id={id} className="card form-card top-gap" aria-label="Official Lot confirmation and save">
    <div className="card-head"><div><span className="eyebrow">OPERATOR REVIEW · OFFICIAL LOT</span><h3>Confirm Product + Color, then explicit SAVE</h3></div><span className="tag amber">RESET NEVER AUTOSAVES</span></div>
    <p className="notice-box">A reset candidate is evidence only. It does not imply a Product or Color change. Select authoritative Product/previous Lot, enter the actual Color and LotName, choose a verified machine code, and explicitly SAVE. Drops and Curing quantities remain separate.</p>
    {resetCandidate && transition !== 'CONTINUE' && <div className="notice-box warning"><strong>Linked reset evidence only · {resetCandidate.id}</strong><div>{resetCandidate.before_sample.timestamp} = {resetCandidate.before_sample.value} → {resetCandidate.decrease_sample.timestamp} = {resetCandidate.decrease_sample.value}; restart sample {resetCandidate.restart_sample?.timestamp ?? 'not observed'}. Press quantity and ACC come only from the SQL Server views; this evidence does not auto-confirm the Lot boundary.</div><label className="field top-gap"><span>Why does the operator associate this reviewed event with the separately confirmed Product/Color change?</span><input value={resetReason} maxLength={500} onChange={(event) => setResetReason(event.target.value)} required /></label></div>}
    <div className="draft-source-line">Selected Production Date: {productionDate} · Shift Schedule v{schedule?.applicable_version_id ?? '—'} · effective Shift is resolved from the entered timestamp; unassigned time is blocked.</div>
    <form onSubmit={save}>
      <div className="grid two-col">
        <label className="field"><span>Product</span><select value={productId} onChange={(event) => { setProductId(event.target.value); setProposal(''); }}><option value="">Select Product</option>{products.map((item) => <option key={item.id} value={item.id}>{item.code} · {item.name}</option>)}</select></label>
        <label className="field"><span>Open official Lot · immutable ID</span><select value={previousLotId} onChange={(event) => { setPreviousLotId(event.target.value); setProposal(''); }}><option value="">{openLots.length ? 'Select open Lot' : 'No open Lot · create initial Lot'}</option>{openLots.map((item) => <option key={item.id} value={item.id}>OPEN · #{item.id} · {item.lot_number ?? 'number unavailable'} · {item.lot_name} · Product #{item.product_id}</option>)}</select></label>
        <label className="field"><span>Color · change creates a Lot</span><input value={color} onChange={(event) => setColor(event.target.value)} required /></label>
        {transition !== 'CONTINUE' && <>
          <label className="field"><span>Editable LotName · duplicates allowed</span><input value={lotName} onChange={(event) => setLotName(event.target.value)} required /></label>
          <label className="field"><span>Lot start · date + HH:mm · Asia/Bangkok</span><input type="datetime-local" step={60} value={startedAt} onChange={(event) => { setStartedAt(event.target.value); setProposal(''); }} required /></label>
          <label className="field"><span>Lot line suffix · confirmed BLOCK code</span><select value={machineCode} onChange={(event) => { setMachineCode(event.target.value); setProposal(''); }} required><option value="">Select confirmed code</option><option value="A">A · BLOCK line suffix (Plant B)</option></select></label>
          <label className="field"><span>Operator ID · self-entered, not authenticated</span><input value={operatorId} onChange={(event) => setOperatorId(event.target.value)} required /></label>
        </>}
      </div>
      <div className="product-summary"><div><strong>{selectedProduct?.code ?? 'No Product selected'}</strong><small>Transition: {transition.replace('_', ' ')} · {selectedProduct?.standard_pieces_per_drop ?? '—'} Pieces/Drop · {selectedProduct?.standard_cycle_time_sec ?? '—'} sec/Drop</small>{transition === 'CONTINUE' && <small>Original Lot #{previousLot?.id} and SCG number are preserved across Shift and Production Date changes.</small>}</div></div>
      <div className="draft-actions">{transition !== 'CONTINUE' && <button className="button secondary" type="button" disabled={busy} onClick={() => void getProposal()}>Preview SCG Lot number</button>}<button className="button primary" type="submit" disabled={busy}>{transition === 'CONTINUE' ? `Use original Lot #${previousLot?.id ?? ''} →` : 'Explicit SAVE new official Lot →'}</button></div>
      {proposal && <div className="notice-box"><strong>Proposed SCG Lot number: {proposal}</strong><div>Not reserved. No official ID/number is assigned until successful SQL commit and read-back.</div></div>}
    </form>
    {saved && <div className="notice-box strong-notice" role="status">Official Lot #{saved.id} · {saved.lot_number ?? 'Lot number unavailable'} · {saved.mode}</div>}
    {message && <div className={`notice-box top-gap ${message.includes('committed') ? '' : 'warning'}`} role="status">{message}</div>}
  </section>;
}
