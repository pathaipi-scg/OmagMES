import { useCallback, useEffect, useMemo, useState, type FormEvent } from 'react';
import { type ShiftScheduleContext } from './ShiftSchedule';
import AutoLotDrafts, { type ResetCandidate } from './AutoLotDrafts';
import OfficialLotSave from './OfficialLotSave';
import EditLog from './EditLog';
import ProductionPage from './ProductionPage';
import SettingPage from './SettingPage';
import { type WorkTimeShiftSetting, type WorkTimeShiftStatus } from './DailyShiftSettings';

type Product = { id: number; code: string; name: string; name_thai?: string | null; family: string; standard_pieces_per_drop: number | null; standard_cycle_time_sec: number | null };
type Lot = { id: number; run_id: number; product_id: number; color: string; lot_name: string; lot_number?: string; started_at: string; lot_start_production_date?: string; lot_start_shift_id?: number; is_open?: boolean };
type Reason = { code: string; label: string };
type Mould = { id: number; code: string; name?: string; product_id: number; status: string; current_age_drops: number; lifetime_age_drops: number; recondition_cycle: number };
type RecordRow = Record<string, unknown>;
type Bootstrap = { mode: string; products: Product[]; lots: Lot[]; reject_reasons: Reason[]; production_entries: RecordRow[]; reject_entries: RecordRow[]; run_events: RecordRow[]; curing_entries: RecordRow[]; depal_entries: RecordRow[]; moulds: Mould[]; mould_history: RecordRow[] };
type AutoCal = { mode: string; suggested_actual_drops: number | null; suggested_wet_good_pieces: number | null; suggested_wet_rejects: Record<string, number | null>; reject_total?: number | null; source_notes: string[]; source_errors?: Record<string, string> };
type Oee = { mode: string; window: string; availability: number; performance: number; quality: number; oee: number; actual_drops: number; wet_good_pieces: number; standard_status: string; notes: string[] };
type SourceMode = 'MOCK' | 'LIVE READ-ONLY' | 'UNKNOWN';
type SourceHealth = { mode: string; connected: boolean; server: string | null; instance: string | null; database: string | null; sql_login?: string; database_user?: string; sysadmin_member?: boolean; permission_checks?: Record<string, Record<string, boolean>>; select_access_verified?: boolean; read_only_permissions_verified: boolean; write_capabilities_present?: string[]; source_queries_select_only_enforced?: boolean; error: string | null };
type SourceDashboard = { mode: string; connected: boolean; wet_status: { status: string; observation: RecordRow | null } | null; press_counter: RecordRow | null; wet_camera_pieces: number | null; wet_reject_counts: Record<string, number | null>; last_observation_at: string | null; warnings: string[]; source_errors: Record<string, string> };
type CurrentProductionDate = { calendar_date: string; calendar_timestamp: string; production_date: string; cutoff_time: string; cutoff_version_id: number; time_zone: string };
type ShiftTypeNumber = 1 | 2 | 3;
type ShiftConfigurationStatus = 'LOADING' | 'UNAVAILABLE' | 'SAVED' | 'DEFAULT' | 'NOT_SAVED';
type ProductionShiftType = { production_date: string; selected_type: ShiftTypeNumber; type_code: string; status: 'SAVED' | 'DEFAULT'; record_id: number | null; update_time: string | null };
type WorkTimeShiftSettingsResponse = { source: string; schedule_view: string; rows: WorkTimeShiftSetting[]; latest_update_time: string | null; status?: 'SAVED' | 'NO_CHANGES'; inserted_count?: number; update_time?: string | null };
type SettingTab = 'PRODUCT MASTER' | 'MOULD' | 'SHIFT';

type Page = 'Production' | 'Edit Log' | 'Wet Reject' | 'Wet Run Log' | 'Wet OEE' | 'Curing' | 'Depallet' | 'Mould' | 'Settings' | 'Shift Time' | 'Setting';
const DATE_STORAGE_KEY = 'omagmes.production-date.v1';
const knownPages: Page[] = ['Production', 'Edit Log', 'Wet Reject', 'Wet Run Log', 'Wet OEE', 'Curing', 'Depallet', 'Mould', 'Settings', 'Shift Time', 'Setting'];

function readProductionDate() {
  const queryDate = new URLSearchParams(window.location.search).get('production_date');
  const savedDate = window.localStorage.getItem(DATE_STORAGE_KEY);
  const isValidDate = (candidate: string | null): candidate is string => {
    if (!candidate || !/^\d{4}-\d{2}-\d{2}$/.test(candidate)) return false;
    const [year, month, day] = candidate.split('-').map(Number);
    const parsed = new Date(Date.UTC(year, month - 1, day));
    return parsed.getUTCFullYear() === year && parsed.getUTCMonth() === month - 1 && parsed.getUTCDate() === day;
  };
  if (isValidDate(queryDate)) return queryDate;
  if (isValidDate(savedDate)) return savedDate;
  return '';
}

function bangkokDateTimeInput(value = new Date()) {
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Bangkok', year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', hourCycle: 'h23',
  }).formatToParts(value);
  const part = (type: string) => parts.find((item) => item.type === type)?.value ?? '';
  return `${part('year')}-${part('month')}-${part('day')}T${part('hour')}:${part('minute')}`;
}

function bangkokDateTimeIso(value: string) {
  return `${value}:00+07:00`;
}

function readPage(): Page {
  const candidate = new URLSearchParams(window.location.search).get('page') as Page | null;
  if (candidate === 'Mould' || candidate === 'Settings' || candidate === 'Shift Time') return 'Setting';
  return candidate && knownPages.includes(candidate) ? candidate : 'Production';
}

function updateLocation(page: Page, productionDate: string, replace = false) {
  const url = new URL(window.location.href);
  url.searchParams.set('page', page);
  url.searchParams.set('production_date', productionDate);
  if (replace) window.history.replaceState({}, '', url);
  else window.history.pushState({}, '', url);
}

const pages: { name: Page; icon: string; group: string }[] = [
  { name: 'Production', icon: '◫', group: 'Production' },
  { name: 'Edit Log', icon: '▤', group: 'Production' },
  { name: 'Wet Run Log', icon: '◷', group: 'Production' },
  { name: 'Wet Reject', icon: '◈', group: 'Production' },
  { name: 'Wet OEE', icon: '◌', group: 'Production' },
  { name: 'Curing', icon: '▤', group: 'Production' },
  { name: 'Depallet', icon: '▦', group: 'Depallet' },
  { name: 'Setting', icon: '⚙', group: 'Setting' },
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
  const [page, setPage] = useState<Page>(readPage);
  const [productionDate, setProductionDate] = useState(readProductionDate);
  const [settingTab, setSettingTab] = useState<SettingTab>('PRODUCT MASTER');
  const [selectedShiftType, setSelectedShiftType] = useState<ShiftTypeNumber>(3);
  const [shiftConfigurationStatus, setShiftConfigurationStatus] = useState<ShiftConfigurationStatus>('LOADING');
  const [shiftConfigurationLoading, setShiftConfigurationLoading] = useState(false);
  const [shiftConfigurationSaving, setShiftConfigurationSaving] = useState(false);
  const [shiftConfigurationError, setShiftConfigurationError] = useState('');
  const [workTimeShiftRows, setWorkTimeShiftRows] = useState<WorkTimeShiftSetting[]>([]);
  const [savedWorkTimeShiftRows, setSavedWorkTimeShiftRows] = useState<WorkTimeShiftSetting[]>([]);
  const [workTimeShiftStatus, setWorkTimeShiftStatus] = useState<WorkTimeShiftStatus>('LOADING');
  const [workTimeShiftLoading, setWorkTimeShiftLoading] = useState(false);
  const [workTimeShiftSaving, setWorkTimeShiftSaving] = useState(false);
  const [workTimeShiftMessage, setWorkTimeShiftMessage] = useState('');
  const [workTimeShiftError, setWorkTimeShiftError] = useState('');
  const [workTimeLatestUpdate, setWorkTimeLatestUpdate] = useState<string | null>(null);
  const [data, setData] = useState<Bootstrap>(fallback);
  const [schedule, setSchedule] = useState<ShiftScheduleContext | null>(null);
  const [connected, setConnected] = useState(false);
  const [productionPageReloadKey, setProductionPageReloadKey] = useState(0);
  const [sourceMode, setSourceMode] = useState<SourceMode>('UNKNOWN');
  const [sourceHealth, setSourceHealth] = useState<SourceHealth | null>(null);
  const [sourceDashboard, setSourceDashboard] = useState<SourceDashboard | null>(null);
  const [currentProductionDate, setCurrentProductionDate] = useState<CurrentProductionDate | null>(null);
  const [liveWindowStart, setLiveWindowStart] = useState('');
  const [liveWindowEnd, setLiveWindowEnd] = useState('');
  const [liveWindowConfirmed, setLiveWindowConfirmed] = useState(false);
  const [notice, setNotice] = useState('');
  const [operatorId, setOperatorId] = useState('');
  const [autoCal, setAutoCal] = useState<AutoCal | null>(null);
  const [oee, setOee] = useState<Oee | null>(null);
  const [selectedLot, setSelectedLot] = useState('501');
  const [drops, setDrops] = useState('');
  const [goodPieces, setGoodPieces] = useState('');
  const [productionAt, setProductionAt] = useState(() => bangkokDateTimeInput());
  const [productionNote, setProductionNote] = useState('');
  const [rejectCounts, setRejectCounts] = useState<Record<string, string>>({});
  const [rejectNote, setRejectNote] = useState('');
  const [eventCategory, setEventCategory] = useState('RUNNING');
  const [eventStart, setEventStart] = useState('');
  const [eventEnd, setEventEnd] = useState('');
  const [eventNote, setEventNote] = useState('');
  const [lifecycleQty, setLifecycleQty] = useState('');
  const [lifecycleNote, setLifecycleNote] = useState('');
  const [newProduct, setNewProduct] = useState('1');
  const [lotTransition, setLotTransition] = useState<'PRODUCT_CHANGE' | 'COLOR_CHANGE'>('PRODUCT_CHANGE');
  const [newColor, setNewColor] = useState('Grey');
  const [newLotName, setNewLotName] = useState('');
  const [selectedResetCandidate, setSelectedResetCandidate] = useState<ResetCandidate | null>(null);
  const [renameTarget, setRenameTarget] = useState<number | null>(null);
  const [renameName, setRenameName] = useState('');
  const [renameReason, setRenameReason] = useState('');
  const [selectedMould, setSelectedMould] = useState('71');
  const [mouldAction, setMouldAction] = useState<'SEND_TO_RECONDITION' | 'APPROVE_RETURN'>('SEND_TO_RECONDITION');
  const [mouldReason, setMouldReason] = useState('');
  const [search, setSearch] = useState('');

  const shiftStatusLabel = shiftConfigurationStatus === 'SAVED' ? 'SAVED'
    : shiftConfigurationStatus === 'DEFAULT' ? 'DEFAULT'
      : shiftConfigurationStatus === 'LOADING' ? 'LOADING'
        : shiftConfigurationStatus === 'UNAVAILABLE' ? 'UNAVAILABLE' : 'NOT SAVED';

  const applyProductionShiftType = useCallback((result: ProductionShiftType) => {
    setSelectedShiftType(result.selected_type);
    setShiftConfigurationStatus(result.status);
    setShiftConfigurationError('');
  }, []);

  const loadProductionShiftType = useCallback(async (selectedDate: string) => {
    if (!selectedDate) return;
    setShiftConfigurationLoading(true);
    setShiftConfigurationStatus('LOADING');
    setShiftConfigurationError('');
    try {
      const query = new URLSearchParams({ production_date: selectedDate });
      const result = await request<ProductionShiftType>(`/api/production/shift-type?${query}`);
      applyProductionShiftType(result);
    } catch (error) {
      setShiftConfigurationStatus('UNAVAILABLE');
      setShiftConfigurationError(error instanceof Error ? error.message : 'Shift Type could not be loaded.');
    } finally {
      setShiftConfigurationLoading(false);
    }
  }, [applyProductionShiftType]);

  const navigateToPage = useCallback((nextPage: Page) => {
    const destination: Page = nextPage === 'Mould' || nextPage === 'Settings' || nextPage === 'Shift Time' ? 'Setting' : nextPage;
    setPage(destination);
    if (productionDate) updateLocation(destination, productionDate);
    setNotice('');
  }, [productionDate]);

  const chooseProductionDate = useCallback((nextDate: string) => {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(nextDate)) return;
    setProductionDate(nextDate);
    window.localStorage.setItem(DATE_STORAGE_KEY, nextDate);
    updateLocation(page, nextDate);
    setNotice('');
  }, [page]);

  useEffect(() => {
    let active = true;
    if (!productionDate) return () => { active = false; };
    setShiftConfigurationLoading(true);
    setShiftConfigurationStatus('LOADING');
    setShiftConfigurationError('');
    const query = new URLSearchParams({ production_date: productionDate });
    void request<ProductionShiftType>(`/api/production/shift-type?${query}`).then((result) => {
      if (active) applyProductionShiftType(result);
    }).catch((error: unknown) => {
      if (!active) return;
      setShiftConfigurationStatus('UNAVAILABLE');
      setShiftConfigurationError(error instanceof Error ? error.message : 'Shift Type could not be loaded.');
    }).finally(() => { if (active) setShiftConfigurationLoading(false); });
    return () => { active = false; };
  }, [applyProductionShiftType, productionDate]);

  async function saveProductionShiftType(nextType: ShiftTypeNumber) {
    if (!productionDate) return;
    const previousType = selectedShiftType;
    setSelectedShiftType(nextType);
    setShiftConfigurationSaving(true);
    setShiftConfigurationStatus('NOT_SAVED');
    setShiftConfigurationError('');
    try {
      const saved = await request<ProductionShiftType>('/api/production/shift-type', {
        method: 'POST',
        body: JSON.stringify({ production_date: productionDate, selected_type: nextType }),
      });
      if (saved.status !== 'SAVED' || saved.selected_type !== nextType || saved.production_date !== productionDate) {
        throw new Error('The saved Shift Type did not match the selected Production Date and Type.');
      }
      applyProductionShiftType(saved);
      setProductionPageReloadKey((version) => version + 1);
    } catch (error) {
      setSelectedShiftType(previousType);
      setShiftConfigurationStatus('NOT_SAVED');
      setShiftConfigurationError(error instanceof Error ? error.message : 'Shift Type was not saved.');
    } finally {
      setShiftConfigurationSaving(false);
    }
  }

  const loadWorkTimeShiftSettings = useCallback(async () => {
    setWorkTimeShiftLoading(true);
    setWorkTimeShiftStatus('LOADING');
    setWorkTimeShiftError('');
    setWorkTimeShiftMessage('');
    try {
      const result = await request<WorkTimeShiftSettingsResponse>('/api/worktime/shift-settings');
      setWorkTimeShiftRows(result.rows);
      setSavedWorkTimeShiftRows(result.rows);
      setWorkTimeLatestUpdate(result.latest_update_time);
      setWorkTimeShiftStatus('LOADED');
    } catch (error) {
      setWorkTimeShiftRows([]);
      setSavedWorkTimeShiftRows([]);
      setWorkTimeLatestUpdate(null);
      setWorkTimeShiftStatus('UNAVAILABLE');
      setWorkTimeShiftError(error instanceof Error ? error.message : 'dbo.WorkTime settings could not be loaded.');
    } finally {
      setWorkTimeShiftLoading(false);
    }
  }, []);

  useEffect(() => {
    if (page === 'Setting' && settingTab === 'SHIFT') void loadWorkTimeShiftSettings();
  }, [loadWorkTimeShiftSettings, page, settingTab]);

  function changeWorkTimeShift(workType: string, shiftNo: string, field: 'start_time' | 'stop_time', value: string) {
    setWorkTimeShiftRows((current) => current.map((row) => row.work_type === workType && row.shift_no === shiftNo
      ? { ...row, [field]: value || null }
      : row));
    setWorkTimeShiftStatus('NOT_SAVED');
    setWorkTimeShiftMessage('');
    setWorkTimeShiftError('');
  }

  async function saveWorkTimeShiftSettings() {
    if (workTimeShiftSaving || workTimeShiftLoading || workTimeShiftStatus === 'UNAVAILABLE') return;
    const savedByKey = new Map(savedWorkTimeShiftRows.map((row) => [`${row.work_type}:${row.shift_no}`, row]));
    const changedRows = workTimeShiftRows.filter((row) => {
      const original = savedByKey.get(`${row.work_type}:${row.shift_no}`);
      return original && (row.start_time !== original.start_time || row.stop_time !== original.stop_time);
    });
    if (!changedRows.length) return;
    if (changedRows.some((row) => !row.start_time || !row.stop_time)) {
      setWorkTimeShiftStatus('NOT_SAVED');
      setWorkTimeShiftError('Both Start and Stop must contain valid SQL time values before saving.');
      return;
    }
    setWorkTimeShiftSaving(true);
    setWorkTimeShiftStatus('NOT_SAVED');
    setWorkTimeShiftMessage('');
    setWorkTimeShiftError('');
    try {
      const result = await request<WorkTimeShiftSettingsResponse>('/api/worktime/shift-settings', {
        method: 'POST',
        body: JSON.stringify({ changes: changedRows.map(({ work_type, shift_no, start_time, stop_time }) => ({ work_type, shift_no, start_time, stop_time })) }),
      });
      setWorkTimeShiftRows(result.rows);
      setSavedWorkTimeShiftRows(result.rows);
      setWorkTimeLatestUpdate(result.latest_update_time);
      setWorkTimeShiftStatus('SAVED');
      setWorkTimeShiftMessage(result.inserted_count
        ? `Saved ${result.inserted_count} changed Shift row${result.inserted_count === 1 ? '' : 's'} to dbo.WorkTime; SQL values reloaded.`
        : 'No changed SQL values; no WorkTime record was inserted.');
      setProductionPageReloadKey((version) => version + 1);
    } catch (error) {
      setWorkTimeShiftStatus('NOT_SAVED');
      setWorkTimeShiftError(error instanceof Error ? error.message : 'Shift settings were not saved. Your edits have been retained.');
    } finally {
      setWorkTimeShiftSaving(false);
    }
  }

  useEffect(() => {
    if (!productionDate) return;
    window.localStorage.setItem(DATE_STORAGE_KEY, productionDate);
  }, [productionDate]);

  useEffect(() => { setSelectedResetCandidate(null); }, [productionDate]);

  useEffect(() => {
    const restoreLocation = () => {
      const restoredPage = readPage();
      const restoredDate = readProductionDate();
      setPage(restoredPage);
      setProductionDate(restoredDate);
      if (restoredDate) {
        window.localStorage.setItem(DATE_STORAGE_KEY, restoredDate);
        if (new URLSearchParams(window.location.search).get('production_date') !== restoredDate) updateLocation(restoredPage, restoredDate, true);
      }
    };
    window.addEventListener('popstate', restoreLocation);
    if (productionDate && new URLSearchParams(window.location.search).get('production_date') !== productionDate) updateLocation(page, productionDate, true);
    return () => window.removeEventListener('popstate', restoreLocation);
  }, [page, productionDate]);

  const refresh = useCallback(async () => {
    try {
      const [boot, status] = await Promise.all([
        request<Bootstrap>('/api/bootstrap'),
        request<{ status: string; mode: SourceMode }>('/api/health'),
      ]);
      setData(boot);
      setProductionPageReloadKey((version) => version + 1);
      setConnected(status.status === 'ok');
      setSourceMode(status.mode === 'MOCK' || status.mode === 'LIVE READ-ONLY' ? status.mode : 'UNKNOWN');
      setSelectedLot((current) => boot.lots.some((lot) => String(lot.id) === current) ? current : String(boot.lots[0]?.id ?? ''));
      let liveDate: CurrentProductionDate | null = null;
      try {
        liveDate = await request<CurrentProductionDate>('/api/production-date/current');
        setCurrentProductionDate(liveDate);
      } catch {
        setCurrentProductionDate(null);
      }
      const contextDate = productionDate || liveDate?.production_date || '';
      if (contextDate && page !== 'Setting') {
        if (!productionDate) {
          setProductionDate(contextDate);
          window.localStorage.setItem(DATE_STORAGE_KEY, contextDate);
          updateLocation(page, contextDate, true);
        }
        const query = new URLSearchParams({ production_date: contextDate });
        try {
          setSchedule(await request<ShiftScheduleContext>(`/api/shift-period-schedule?${query.toString()}`));
        } catch {
          setSchedule(null);
        }
      } else {
        setSchedule(null);
      }
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
  }, [page, productionDate]);

  useEffect(() => { void refresh(); }, [refresh]);
  useEffect(() => {
    if (page === 'Wet OEE' && productionDate) {
      const query = new URLSearchParams({ production_date: productionDate });
      void request<Oee>(`/api/wet-oee/preview?${query.toString()}`).then(setOee).catch(() => setOee(null));
    }
  }, [page, productionDate]);

  const selectedLotData = data.lots.find((lot) => String(lot.id) === selectedLot);
  const selectedProduct = data.products.find((product) => product.id === selectedLotData?.product_id);
  const filteredLots = useMemo(() => data.lots.filter((lot) => {
    const product = data.products.find((item) => item.id === lot.product_id);
    const text = `${lot.id} ${lot.lot_name} ${product?.code ?? ''} ${product?.name ?? ''}`.toLowerCase();
    return text.includes(search.toLowerCase());
  }), [data.lots, data.products, search]);
  const isConfigurationPage = page === 'Setting' || page === 'Shift Time';
  const activeNavigationGroup = pages.find((item) => item.name === page)?.group ?? 'Production';
  const configurationReady = connected && currentProductionDate !== null && schedule !== null;

  async function act<T>(path: string, body?: unknown, method = 'POST'): Promise<T | null> {
    setNotice('');
    try {
      const contextualBody = body && typeof body === 'object' ? { ...(body as Record<string, unknown>), production_date: productionDate || undefined, shift_schedule_version_id: schedule?.applicable_version_id, production_day_cutoff_version_id: schedule?.cutoff_version_id } : body;
      const result = await request<T>(path, body === undefined ? { method } : { method, body: JSON.stringify(contextualBody) });
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
    setNotice('');
    try {
      const result = await request<RecordRow>('/api/production/save', {
        method: 'POST',
        body: JSON.stringify({ lot_id: Number(selectedLot), production_at: bangkokDateTimeIso(productionAt), actual_drops: Number(drops), wet_good_pieces: Number(goodPieces), operator_note: productionNote, operator_id: operatorId, suggested_actual_drops: autoCal?.suggested_actual_drops ?? null, suggested_wet_good_pieces: autoCal?.suggested_wet_good_pieces ?? null }),
      });
      setNotice(result.mode === 'SQL PERSISTED'
        ? `Production entry saved against original Lot #${String(result.lot_id)} for ${String(result.production_date)} · Shift ID ${String(result.shift_id ?? 'unassigned')}.`
        : 'Saved to process-local mock state. The original Lot ID was retained; production time/date/shift are recorded separately.');
      setProductionNote('');
      await refresh();
    } catch (error) {
      setNotice(error instanceof Error ? error.message : 'Production entry was not saved.');
    }
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
    const result = await act(type === 'curing' ? '/api/curing/entries' : '/api/depallet/events', { lot_id: Number(selectedLot), quantity: Number(lifecycleQty || 0), note: lifecycleNote, unit_code: '', operator_id: operatorId });
    if (result) { setLifecycleQty(''); setLifecycleNote(''); }
  }

  async function createLot(event: FormEvent) {
    event.preventDefault();
    if (sourceMode === 'LIVE READ-ONLY') {
      setNotice('Use the Production page explicit official-Lot review panel; the Settings demo form cannot create LIVE Lots.');
      return;
    }
    const result = await act<Lot>('/api/lots', { product_id: Number(newProduct), previous_lot_id: selectedLot ? Number(selectedLot) : null, transition: lotTransition, color: newColor, lot_name: newLotName, operator_id: operatorId });
    if (result) { setNewLotName(''); setSelectedLot(String(result.id)); navigateToPage('Production'); }
  }

  async function saveLotRename(event: FormEvent) {
    event.preventDefault();
    if (renameTarget === null) return;
    const result = await act(`/api/lots/${renameTarget}/rename`, { new_name: renameName, reason: renameReason, operator_id: operatorId });
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
    if (page === 'Production') return <ProductionPage
      productionDate={productionDate}
      reloadKey={productionPageReloadKey}
    />;
    if ((page as Page) === 'Production') return <>
      <div className="hero-row"><div><div className="eyebrow">WET LINE · LIVE WORKSPACE</div><h2>Production entry</h2><p className="subtle">Review AutoCal suggestions, correct them if needed, then save deliberately.</p></div><button className="button secondary" onClick={() => {
        setNewLotName('');
        if (sourceMode === 'LIVE READ-ONLY') document.getElementById('official-lot-save')?.scrollIntoView({ behavior: 'smooth', block: 'center' });
        else navigateToPage('Settings');
      }}>＋ New Run / Lot</button></div>
      <section className="date-context-card"><div><span className="eyebrow">SHARED PRODUCTION CONTEXT</span><strong>{productionDate} · Shift Schedule v{schedule?.applicable_version_id ?? '—'}</strong><small>Production Date is separate from event timestamps, creation timestamps and Lot start/end bounds.</small></div><div className="context-shifts">{schedule?.resolved_shifts.filter((shift) => shift.active).map((shift) => <span className="tag blue" key={shift.id}>{shift.shift_name} · {shift.start_time}–{shift.end_time}</span>)}</div></section>
      <div className="callout"><span className="callout-icon">✦</span><div><strong>AutoCal is suggestion-only</strong><p>{sourceMode === 'LIVE READ-ONLY' ? 'Live source observations remain read-only. Production quantity save is separately write-gated and retains the original Lot ID with actual occurrence context.' : 'PLC and camera values are mocked. Operator edits and explicit SAVE are required.'}</p></div><button className="button dark" onClick={() => void loadAutoCal()}>{sourceMode === 'LIVE READ-ONLY' ? 'Load LIVE AutoCal' : 'Load AutoCal'}</button></div>
      <AutoLotDrafts productionDate={productionDate} schedule={schedule} onSelectReset={setSelectedResetCandidate} />
      {sourceMode === 'LIVE READ-ONLY' && <OfficialLotSave id="official-lot-save" productionDate={productionDate} schedule={schedule} products={data.products} lots={data.lots} resetCandidate={selectedResetCandidate} onSaved={refresh} onContinue={(lotId) => setSelectedLot(String(lotId))} />}
      {liveWindowControls()}
      <div className="grid two-col top-gap">
        <section className="card form-card"><div className="card-head"><div><span className="eyebrow">PRODUCTION RECORD</span><h3>Confirm quantities</h3></div><span className="tag muted">{sourceMode === 'LIVE READ-ONLY' ? 'SQL WRITE GATED' : 'MOCK ENTRY'}</span></div>
          {lotSelector()}
          {selectedLotData && <div className="product-summary"><div className="product-icon">{selectedProduct?.family === 'Fence' ? '▥' : '▦'}</div><div><strong>{selectedProduct?.name ?? 'Unknown Product'}</strong><small>{selectedProduct?.code} · {selectedProduct?.family} · Lot ID #{selectedLotData.id}</small></div><span className={`tag ${selectedLotData.is_open === false ? 'muted' : 'green'}`}>{selectedLotData.is_open === false ? 'CLOSED LOT · HISTORY' : 'OPEN LOT'}</span></div>}
          <form onSubmit={saveProduction}>
            <label className="field"><span>Actual production time · Asia/Bangkok <em>reports to the occurrence date/shift; does not change Lot start context</em></span><input type="datetime-local" value={productionAt} onChange={(event) => setProductionAt(event.target.value)} required /></label>
            <div className="grid two-col"><label className="field"><span>Press Drops <em>Drop count, not Pieces</em></span><input type="number" min="0" value={drops} onChange={(event) => setDrops(event.target.value)} required /></label><label className="field"><span>Wet Good Pieces <em>Camera tray count</em></span><input type="number" min="0" value={goodPieces} onChange={(event) => setGoodPieces(event.target.value)} required /></label></div>
            <label className="field"><span>Operator note / override reason</span><input value={productionNote} onChange={(event) => setProductionNote(event.target.value)} placeholder="Required for a manual override in production" /></label>
            <div className="form-footer"><span className="subtle tiny">Lot # stays original; entry timestamp, Production Date and Shift are resolved independently.</span><button className="button primary" type="submit">Save production entry <span>→</span></button></div>
          </form>
          {autoCal && <details className="source-details"><summary>{autoCal.mode} · AutoCal notes · suggestion not saved</summary><ul>{autoCal.source_notes.map((note) => <li key={note}>{note}</li>)}</ul>{autoCal.source_errors && Object.entries(autoCal.source_errors).map(([source, error]) => <p className="source-error" key={source}>{source}: {error}</p>)}<div className="code-row">Counter suggestions: {Object.entries(autoCal.suggested_wet_rejects).map(([key, value]) => <span key={key}>{key}: {value ?? 'Not verified'}</span>)}</div></details>}
        </section>
        <section className="card"><div className="card-head"><div><span className="eyebrow">CURRENT CONTEXT</span><h3>Run overview</h3></div><span className="status-dot">● RUNNING · DEMO</span></div>
          <div className="context-grid"><div><small>Product</small><strong>{selectedProduct?.code ?? '—'}</strong></div><div><small>Color</small><strong>{selectedLotData?.color ?? '—'}</strong></div><div><small>Run ID</small><strong>#{selectedLotData?.run_id ?? '—'}</strong></div><div><small>Selected Lot ID</small><strong>#{selectedLotData?.id ?? '—'}</strong></div></div>
          <div className="divider"/><div className="standard-warning"><span>ⓘ</span><div><strong>Production standards not loaded</strong><p>Pieces/Drop and seconds/Drop are intentionally blank until standards are factory-approved.</p></div></div>
          <h4 className="section-label">RECENT SAVES</h4>
          {data.production_entries.length ? <div className="record-list">{[...data.production_entries].reverse().slice(0, 4).map((row, i) => <div className="record-row" key={String(row.id ?? i)}><span className="record-mark">✓</span><div><strong>{String(row.actual_drops)} Drops · {String(row.wet_good_pieces)} Pieces</strong><small>Lot #{String(row.lot_id)} · {String(row.production_date ?? 'date unavailable')} · Shift #{String(row.shift_id ?? 'unassigned')} · {String(row.production_at ?? 'time unavailable')}</small></div><span className="tag green">{String(row.mode ?? 'SAVED')}</span></div>)}</div> : <div className="empty-state"><span>◷</span><p>No entries saved in this session.</p><small>Suggestions never save automatically.</small></div>}
        </section>
      </div>
      <section className="card top-gap"><div className="card-head"><div><span className="eyebrow">LOT LOOKUP</span><h3>Traceable production lots</h3></div><label className="search-box"><span>⌕</span><input aria-label="Search lots" placeholder="Search ID, name or product" value={search} onChange={(event) => setSearch(event.target.value)} /></label></div><div className="table-wrap"><table><thead><tr><th>LOT ID</th><th>LOT NAME</th><th>PRODUCT</th><th>COLOR</th><th>RUN</th><th>STARTED</th><th></th></tr></thead><tbody>{filteredLots.map((lot) => { const product = data.products.find((item) => item.id === lot.product_id); return <tr key={lot.id}><td className="id-cell">#{lot.id}</td><td>{lot.lot_name}</td><td><strong>{product?.code}</strong><small className="cell-sub">{product?.name}</small></td><td>{lot.color}</td><td>#{lot.run_id}</td><td>{new Date(lot.started_at).toLocaleString()}</td><td><button className="text-button" onClick={() => { setRenameTarget(lot.id); setRenameName(lot.lot_name); }}>Rename</button></td></tr>; })}</tbody></table></div></section>
    </>;

    if (page === 'Edit Log') return <EditLog productionEntries={data.production_entries} />;

    if (page === 'Wet Reject') return <>
      <PageIntro eyebrow="WET LINE · QUALITY" title="Wet Reject" subtitle="Dynamic counter suggestions are reviewed and explicitly saved per Lot." productionDate={productionDate} />
      <div className="callout"><span className="callout-icon">◈</span><div><strong>Counts use cntR* only</strong><p>Binary R* button states are excluded. {sourceMode === 'LIVE READ-ONLY' ? 'Live counter data is suggestion-only; SAVE remains mock-only.' : 'This screen uses mock counters and a dynamic reason list.'}</p></div><button className="button dark" onClick={() => void loadAutoCal()}>REJECT RECAL · SUGGESTION</button></div>
      <div className="grid two-col top-gap"><section className="card form-card"><div className="card-head"><div><span className="eyebrow">REVIEW & SAVE</span><h3>Reject reason quantities</h3></div><span className="tag muted">MOCK DATA</span></div>{lotSelector()}<form onSubmit={saveReject}><div className="reason-list">{data.reject_reasons.map((reason, index) => <label className="reason-row" key={reason.code}><span className="reason-num">{String(index + 1).padStart(2, '0')}</span><span className="reason-label"><strong>{reason.label}</strong><small>{reason.code}</small></span><input aria-label={`${reason.code} quantity`} type="number" min="0" value={rejectCounts[reason.code] ?? ''} onChange={(event) => setRejectCounts((current) => ({ ...current, [reason.code]: event.target.value }))} placeholder="0" /></label>)}</div><label className="field top-gap"><span>Operator note</span><input value={rejectNote} onChange={(event) => setRejectNote(event.target.value)} placeholder="Optional review context" /></label><div className="form-footer"><span className="subtle tiny">No balancing or auto-classification.</span><button className="button primary" type="submit">Save reject review →</button></div></form></section>
        <section className="card"><span className="eyebrow">SOURCE CHECK</span><h3>Suggestion snapshot</h3><div className="metric-big">{autoCal?.reject_total ?? '—'} <small>mock preview only</small></div><p className="subtle">{sourceMode === 'LIVE READ-ONLY' ? 'Live cntR* tags are separate cumulative counters. They are shown in source notes only and are not mapped to these mock reason fields.' : 'The counter values are displayed as a suggestion. The operator owns the final edited quantities.'}</p><div className="source-lines">{data.reject_reasons.map((reason) => <div key={reason.code}><span>{reason.label}<small>{reason.code}</small></span><strong>{sourceMode === 'LIVE READ-ONLY' ? 'No approved mapping' : autoCal?.suggested_wet_rejects[reason.code] ?? 'Not loaded'}</strong></div>)}</div>
          {autoCal && <details className="source-details"><summary>{autoCal.mode} · source counter suggestions · not saved</summary><ul>{autoCal.source_notes.map((note) => <li key={note}>{note}</li>)}</ul>{Object.entries(autoCal.suggested_wet_rejects).map(([tag, value]) => <div className="saved-chip" key={tag}>{tag}: {value ?? 'Not verified'}</div>)}</details>}
          <div className="notice-box">Reason names are demonstration labels, not an approved Reject Reason Master.</div><h4 className="section-label">SAVED MOCK REVIEWS</h4>{data.reject_entries.length ? data.reject_entries.slice().reverse().map((entry, i) => <div className="saved-chip" key={String(entry.id ?? i)}>Lot #{String(entry.lot_id)} · total {String(entry.total)}</div>) : <div className="empty-state compact">No reject records saved yet.</div>}</section></div>
    </>;

    if (page === 'Wet Run Log') return <>
      <PageIntro eyebrow="WET LINE · OPERATOR CLASSIFICATION" title="Wet Run Log" subtitle="Press + Wet Line is one coupled unit. Classifications remain manual and authoritative." productionDate={productionDate} />
      <div className="notice-box strong-notice">AutoRun is status evidence only. It never writes, replaces, or reclassifies an operator event.</div>
      <div className="grid two-col top-gap"><section className="card form-card"><div className="card-head"><div><span className="eyebrow">MANUAL ENTRY</span><h3>Record time event</h3></div><span className="tag blue">OPERATOR INPUT</span></div><form onSubmit={saveRunEvent}><label className="field"><span>Classification</span><select value={eventCategory} onChange={(event) => setEventCategory(event.target.value)}>{['RUNNING', 'SETUP', 'CHANGEOVER', 'IDLE', 'CLEANING', 'BREAKDOWN', 'SMDT'].map((value) => <option key={value}>{value}</option>)}</select></label><div className="grid two-col"><label className="field"><span>Start time</span><input type="datetime-local" value={eventStart} onChange={(event) => setEventStart(event.target.value)} required /></label><label className="field"><span>End time <em>leave blank if ongoing</em></span><input type="datetime-local" value={eventEnd} onChange={(event) => setEventEnd(event.target.value)} /></label></div><label className="field"><span>Operator note</span><textarea rows={3} value={eventNote} onChange={(event) => setEventNote(event.target.value)} placeholder="Context, cause, or handover note" /></label><div className="form-footer"><span className="subtle tiny">Open events stay open; no synthetic end.</span><button className="button primary" type="submit">Save manual event →</button></div></form></section>
        <section className="card"><div className="card-head"><div><span className="eyebrow">EVENT TIMELINE</span><h3>Wet line intervals</h3></div><span className="tag muted">MANUAL SOURCE</span></div><div className="timeline">{data.run_events.slice().reverse().map((event, index) => <div className="timeline-row" key={String(event.id ?? index)}><span className={`timeline-dot ${event.category === 'RUNNING' ? 'run' : 'stop'}`}/><div><div className="timeline-title"><strong>{String(event.category)}</strong><span className="tag blue">{String(event.source ?? 'DEMO')}</span></div><p>{new Date(String(event.started_at)).toLocaleString()} → {event.ended_at ? new Date(String(event.ended_at)).toLocaleString() : 'OPEN'}</p><small>{String(event.note ?? 'No note')}</small></div></div>)}</div><div className="notice-box top-gap">AutoRun state transitions and operator classifications are stored separately in this prototype.</div></section></div>
    </>;

    if (page === 'Wet OEE') return <>
      <PageIntro eyebrow="WET LINE · PERFORMANCE" title="Wet OEE preview" subtitle="A transparent, simulated view for factory review — not an operational KPI." productionDate={productionDate} />
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

    if (page === 'Setting') return <SettingPage
      products={data.products}
      moulds={data.moulds}
      rejectReasons={data.reject_reasons}
      productionDate={productionDate}
      liveData={connected && sourceMode === 'LIVE READ-ONLY'}
      activeTab={settingTab}
      shiftRows={workTimeShiftRows}
      originalShiftRows={savedWorkTimeShiftRows}
      shiftStatus={workTimeShiftStatus}
      shiftLatestUpdate={workTimeLatestUpdate}
      shiftLoading={workTimeShiftLoading}
      shiftSaving={workTimeShiftSaving}
      shiftMessage={workTimeShiftMessage}
      shiftError={workTimeShiftError}
      onShiftChange={changeWorkTimeShift}
      onSaveShiftSettings={() => void saveWorkTimeShiftSettings()}
    />;

    return <><PageIntro eyebrow="SYSTEM · FACTORY REVIEW" title="Settings & data status" subtitle="Prototype controls and explicit boundaries for factory review."/><div className="simulation-banner"><span>⚠</span><div><strong>{sourceMode === 'LIVE READ-ONLY' ? 'LIVE SOURCES · PRODUCTION WRITES DISABLED' : 'MOCK ONLY — NO DATABASE CONNECTION'}</strong><p>Every API save is process-local and is lost when the backend restarts.</p></div></div><div className="grid two-col top-gap"><section className="card"><span className="eyebrow">DEMO LOT CREATION</span><h3>Start a new Product or Color assignment</h3><p className="subtle">Product change creates a new demo Run and Lot; Color change creates a Lot in the existing Run. Production authorization and standard snapshots require review.</p><form onSubmit={createLot}>{lotSelector()}<label className="field"><span>Transition type</span><select value={lotTransition} onChange={(event) => setLotTransition(event.target.value as 'PRODUCT_CHANGE' | 'COLOR_CHANGE')}><option value="PRODUCT_CHANGE">Product change · new Run + Lot</option><option value="COLOR_CHANGE">Color change · same Run, new Lot</option></select></label><label className="field"><span>Product</span><select value={newProduct} onChange={(event) => setNewProduct(event.target.value)}>{data.products.map((product) => <option key={product.id} value={product.id}>{product.code} · {product.name}</option>)}</select></label><div className="grid two-col"><label className="field"><span>Color</span><input value={newColor} onChange={(event) => setNewColor(event.target.value)} /></label><label className="field"><span>Display LotName</span><input value={newLotName} onChange={(event) => setNewLotName(event.target.value)} placeholder="Duplicate names are allowed" required /></label></div><button className="button primary" type="submit">Create mock Lot →</button></form></section><section className="card"><span className="eyebrow">CONNECTION & APPROVAL GATES</span><h3>Not configured for production</h3><div className="check-list">{['SQL target does not match the current local environment configuration', 'Legacy dbo remains read-only and unmodified', 'No migration has been executed', 'Product standards / reason masters are not approved', 'Authentication and operator audit identity are not configured'].map((item) => <div key={item}><span>!</span>{item}</div>)}</div><div className="notice-box">Credentials are never displayed. The existing SQL identity has elevated database privileges; PRESS source access is permitted only through the repository's SELECT-only query guard. Data interpretation and review policy remain provisional.</div></section></div><div className="grid three-col top-gap"><StatCard label="SQL database" value={sourceHealth?.connected ? 'LIVE · READ ONLY' : sourceMode === 'MOCK' ? 'MOCK MODE' : 'NOT CONNECTED'} tone={sourceHealth?.connected ? 'green' : 'amber'}/><StatCard label="Backend mode" value={sourceMode} tone={sourceMode === 'LIVE READ-ONLY' ? 'blue' : sourceMode === 'MOCK' ? 'green' : 'amber'}/><StatCard label="Write capability" value="MOCK ONLY" tone="blue"/></div></>;
  }

  return <div className={`app-shell ${page === 'Production' ? 'production-shell' : ''}`}>
    <main className="main">
      <header className="omagmes-header" aria-label="OmagMES navigation">
        <div className="omagmes-header-primary">
          <div className="omagmes-date-actions">
            <label className="shared-date-control"><span>Production Date</span><input aria-label="Selected Production Date" type="date" value={productionDate} onChange={(event) => chooseProductionDate(event.target.value)} /></label>
            <label className="shared-shift-control"><span>Shift Type</span><select aria-label="Selected Shift Type" value={selectedShiftType} onChange={(event) => { void saveProductionShiftType(Number(event.target.value) as ShiftTypeNumber); }} disabled={page !== 'Production' || shiftConfigurationLoading || shiftConfigurationSaving}><option value={1}>TYPE 1</option><option value={2}>TYPE 2</option><option value={3}>TYPE 3</option></select><span className={`shared-shift-status ${shiftStatusLabel.toLowerCase().replace(/ /g, '-')}`} title={shiftConfigurationError || undefined}>{shiftStatusLabel}</span></label>
            <button type="button" className="button secondary refresh-button" onClick={() => { void refresh(); if (productionDate) void loadProductionShiftType(productionDate); if (page === 'Setting' && settingTab === 'SHIFT') void loadWorkTimeShiftSettings(); }}>REFRESH</button>
          </div>
          <nav className="fitting-navigation" aria-label="Main navigation">
            <div className="fitting-tabs-main">
              {(['Production', 'Depallet'] as const).map((group) => {
                const groupPages = pages.filter((item) => item.group === group);
                const active = activeNavigationGroup === group;
                return <button key={group} type="button" className={`fitting-group-tab ${active ? 'is-active is-open' : ''}`} aria-current={active ? 'page' : undefined} onClick={() => navigateToPage(groupPages[0]?.name ?? 'Production')}>{group.toUpperCase()}</button>;
              })}
            </div>
            <button type="button" className={`fitting-group-tab setting-group-tab ${activeNavigationGroup === 'Setting' ? 'is-active is-open' : ''}`} aria-current={activeNavigationGroup === 'Setting' ? 'page' : undefined} onClick={() => navigateToPage('Setting')}>SETTING</button>
          </nav>
        </div>
        {activeNavigationGroup === 'Production' && <nav className="fitting-subnav" aria-label="Production navigation">
          {pages.filter((item) => item.group === 'Production').map((item) => <button key={item.name} type="button" className={`fitting-page-tab ${page === item.name ? 'is-current' : ''}`} aria-current={page === item.name ? 'page' : undefined} onClick={() => navigateToPage(item.name)}>{item.name.toUpperCase()}</button>)}
        </nav>}
        {activeNavigationGroup === 'Setting' && <div className="fitting-subnav fitting-setting-subnav" role="tablist" aria-label="Setting sections">
          {(['PRODUCT MASTER', 'MOULD', 'SHIFT'] as const).map((item) => <button key={item} type="button" role="tab" id={`setting-tab-${item.toLowerCase().replace(/ /g, '-')}`} aria-selected={settingTab === item} aria-controls="setting-tab-panel" className={`fitting-page-tab ${settingTab === item ? 'is-current' : ''}`} onClick={() => setSettingTab(item)}>{item}</button>)}
        </div>}
      </header>
      {page !== 'Production' && page !== 'Setting' && <div className="operator-context"><label className="field"><span>Operator ID · self-entered, not authenticated</span><input aria-label="Operator ID" value={operatorId} onChange={(event) => setOperatorId(event.target.value)} maxLength={200} placeholder="Enter operator ID for audit fields" /></label></div>}
      {page !== 'Production' && page !== 'Setting' && sourceMode === 'LIVE READ-ONLY' && <div className="page-wrap"><div className="notice-box strong-notice" role="status">Live Lot records are read from SQL. Only the existing audited LotName rename endpoint is enabled; Lot creation, assignments, ordering, and voiding remain disabled. No action falls back to mock storage.</div></div>}
      <div className="page-wrap">
        {page !== 'Production' && page !== 'Setting' && <div className="review-strip"><span>◉</span> SOURCE MODE: {sourceMode === 'LIVE READ-ONLY' ? 'LIVE · APP SELECT-ONLY' : sourceMode} <i /> {sourceMode === 'LIVE READ-ONLY' ? 'Other prototype pages may still show review/mock context. Source queries are SELECT-only; writes never fall back to mock storage.' : sourceMode === 'MOCK' ? 'Mock sources and process-local saves; do not use for production decisions.' : 'Source mode unavailable; no live values are displayed.'}</div>}
        {isConfigurationPage && !(page === 'Setting' && settingTab === 'SHIFT') ? <section className={`source-mode-panel ${configurationReady ? '' : 'error'}`} aria-label="SQL configuration status" role={configurationReady ? 'status' : 'alert'}><strong>{configurationReady ? 'SQL CONFIGURATION ACTIVE' : 'SQL CONFIGURATION UNAVAILABLE'}</strong><span>{configurationReady ? 'Production Day Cutoff remains in its existing workflow. Daily ShiftType is stored separately in dbo.ProductionDetails; Shift Settings history is maintained in dbo.WorkTime.' : 'The API, Production Date, or existing schedule context could not be loaded. Configuration values are not presented as mock settings.'}</span></section> : page === 'Production' || page === 'Setting' ? null : <SourceStatusPanel mode={sourceMode} health={sourceHealth} dashboard={sourceDashboard} />}
        {notice && <div className={`toast ${notice.startsWith('Saved') || notice.toLowerCase().includes('suggestions loaded') ? 'success' : 'error'}`} role={notice.startsWith('Saved') || notice.toLowerCase().includes('suggestions loaded') ? 'status' : 'alert'} aria-live="polite">{notice}</div>}
        {pageContent()}
        {page !== 'Production' && <footer>{isConfigurationPage ? 'OMAGMES FACTORY CONFIGURATION · SQL-backed settings · Internal factory network' : <>OMAGMES FACTORY REVIEW <span>·</span> {sourceMode} sources <span>·</span> Saves remain process-local mock state</>}</footer>}
      </div>
    </main>
    {renameTarget !== null && <div className="modal-backdrop" role="presentation" onClick={(event) => { if (event.target === event.currentTarget) setRenameTarget(null); }}><section className="card rename-modal" role="dialog" aria-modal="true" aria-labelledby="rename-title"><button className="modal-close" aria-label="Close" onClick={() => setRenameTarget(null)}>×</button><span className="eyebrow">AUDITED LOTNAME CHANGE · MOCK</span><h3 id="rename-title">Rename Lot #{renameTarget}</h3><p className="subtle">Lot ID and downstream links never change. Duplicate LotNames are allowed.</p><form onSubmit={saveLotRename} className="top-gap"><label className="field"><span>New display name</span><input value={renameName} onChange={(event) => setRenameName(event.target.value)} required /></label><label className="field"><span>Change reason</span><textarea rows={3} value={renameReason} onChange={(event) => setRenameReason(event.target.value)} required placeholder="Explain why the display name is changing" /></label><button className="button primary" type="submit">Save rename history →</button></form></section></div>}
  </div>;
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
      <div className="source-live-heading"><div><strong>LIVE SQL SOURCES · REPOSITORY SELECT ONLY</strong><span>Other prototype-page SAVE remains process-local mock state; Production enables only its audited LotName update.</span></div><span className={`tag ${health?.connected && health.read_only_permissions_verified ? 'green' : 'amber'}`}>{health?.connected && health.read_only_permissions_verified ? 'CONNECTED · SELECT ONLY' : health?.connected && health.select_access_verified ? 'CONNECTED · ELEVATED GRANTS · SELECT ENFORCED' : 'SOURCE ERROR'}</span></div>
    {health?.connected && <p className="source-target">Target verified: {health.server} {health.instance ? `· ${health.instance}` : '· default instance'} · {health.database}</p>}
    {health?.connected && <p className="source-warning">SQL identity: {health.sql_login ?? '—'} / {health.database_user ?? '—'}. {health.sysadmin_member ? 'This identity is a SQL sysadmin.' : ''} Effective source rights include: {health.write_capabilities_present?.join(', ') || 'no write capabilities reported'}. The application repository enforces SELECT statements only; database grants remain broader than least privilege.</p>}
    <div className="source-live-metrics">
      <div><small>WET LINE · AUTORUN</small><strong>{dashboard?.wet_status?.status ?? 'UNKNOWN'}</strong><span>{String(statusObservation?._TIMESTAMP ?? 'No observation')}</span></div>
      <div><small>HISTORICAL PRODUCTCNT · NOT AUTO LOT SOURCE</small><strong>{pressObservation?._VALUE === undefined ? '—' : String(pressObservation._VALUE)}</strong><span>{String(pressObservation?._TIMESTAMP ?? 'No observation')} · quality {String(pressObservation?._QUALITY ?? '—')}</span></div>
      <div><small>WET CAMERA PIECES · LOT WINDOW</small><strong>{dashboard?.wet_camera_pieces ?? 'Not verified'}</strong><span>Individual wet-tray counts; dry excluded</span></div>
      <div><small>WET REJECT · LATEST CUMULATIVE COUNTERS</small><strong>{dashboard && Object.keys(dashboard.wet_reject_counts).length ? Object.entries(dashboard.wet_reject_counts).map(([tag, value]) => `${tag.slice(tag.lastIndexOf('.') + 1)}: ${value ?? '—'}`).join(' · ') : 'Not available'}</strong><span>cntR* only; not Lot quantities; R* excluded</span></div>
    </div>
    <p className="source-last-seen">Last source observation: {dashboard?.last_observation_at ?? 'Not available'}</p>
    {Object.entries(errors).map(([source, message]) => <p className="source-error" role="alert" key={source}>{source}: {message}</p>)}
    {dashboard?.warnings.map((warning, index) => <p className="source-warning" key={`${index}-${warning}`}>{warning}</p>)}
  </section>;
}

function PageIntro({ eyebrow, title, subtitle, productionDate }: { eyebrow: string; title: string; subtitle: string; productionDate?: string }) {
  const date = productionDate ?? new URLSearchParams(window.location.search).get('production_date') ?? 'Not resolved';
  return <div className="page-intro"><div><div className="eyebrow">{eyebrow}</div><h2>{title}</h2><p className="subtle">{subtitle}</p></div><div className="date-pill">◷ &nbsp;{date}</div></div>;
}

function StatCard({ label, value, tone }: { label: string; value: string; tone: string }) {
  return <div className="card stat-card"><span>{label}</span><strong className={tone}>{value}</strong></div>;
}

export default App;
