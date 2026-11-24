import DailyShiftSettings from './DailyShiftSettings';
import type { WorkTimeShiftSetting, WorkTimeShiftStatus } from './DailyShiftSettings';

type Product = {
  id: number;
  code: string;
  name: string;
  name_thai?: string | null;
  family: string;
  standard_pieces_per_drop: number | null;
  standard_cycle_time_sec: number | null;
};
type Mould = {
  id: number;
  code: string;
  name?: string;
  product_id: number;
  status: string;
  current_age_drops: number;
  lifetime_age_drops: number;
  recondition_cycle: number;
};
type Reason = { code: string; label: string };
type Tab = 'PRODUCT MASTER' | 'MOULD' | 'SHIFT';

export default function SettingPage({
  products,
  moulds,
  rejectReasons,
  productionDate,
  liveData,
  activeTab,
  shiftRows,
  originalShiftRows,
  shiftStatus,
  shiftLatestUpdate,
  shiftLoading,
  shiftSaving,
  shiftMessage,
  shiftError,
  onShiftChange,
  onSaveShiftSettings,
}: {
  products: Product[];
  moulds: Mould[];
  rejectReasons: Reason[];
  productionDate: string;
  liveData: boolean;
  activeTab: Tab;
  shiftRows: WorkTimeShiftSetting[];
  originalShiftRows: WorkTimeShiftSetting[];
  shiftStatus: WorkTimeShiftStatus;
  shiftLatestUpdate: string | null;
  shiftLoading: boolean;
  shiftSaving: boolean;
  shiftMessage: string;
  shiftError: string;
  onShiftChange: (workType: string, shiftNo: string, field: 'start_time' | 'stop_time', value: string) => void;
  onSaveShiftSettings: () => void;
}) {
  if (activeTab === 'SHIFT') return <section className="setting-page" aria-label="Setting">
    <DailyShiftSettings
      rows={shiftRows}
      originalRows={originalShiftRows}
      status={shiftStatus}
      latestUpdateTime={shiftLatestUpdate}
      loading={shiftLoading}
      saving={shiftSaving}
      message={shiftMessage}
      error={shiftError}
      onChange={onShiftChange}
      onSave={onSaveShiftSettings}
    />
  </section>;

  return <section className="setting-page" aria-label="Setting">
    <header className="page-intro">
      <div><span className="eyebrow">OMAGMES · CONFIGURATION</span><h2>SETTING</h2><p className="subtle">Product and Mould reference data.</p></div>
      <span className="tag blue">PRODUCTION DATE · {productionDate || '—'}</span>
    </header>
    <div id="setting-tab-panel" role="tabpanel" aria-labelledby={`setting-tab-${activeTab.toLowerCase().replace(/ /g, '-')}`}>
      {activeTab === 'PRODUCT MASTER' && <ProductMaster products={liveData ? products : []} rejectReasons={liveData ? rejectReasons : []} liveData={liveData} />}
      {activeTab === 'MOULD' && <MouldMaster products={liveData ? products : []} moulds={liveData ? moulds : []} liveData={liveData} />}
    </div>
  </section>;
}

function ProductMaster({ products, rejectReasons, liveData }: { products: Product[]; rejectReasons: Reason[]; liveData: boolean }) {
  return <>
    <section className="card top-gap" aria-label="Product Master">
      <div className="card-head"><div><span className="eyebrow">PRODUCT MASTER</span><h3>Production products</h3></div><span className={`tag ${liveData ? 'blue' : 'amber'}`}>{liveData ? 'LIVE SQL · READ ONLY' : 'LIVE DATA UNAVAILABLE'}</span></div>
      <p className="subtle">Rows use the existing OmagMES Product IDs. No create/edit API or approved Product Standard write workflow is available, so this page does not offer unsupported writes.</p>
      <div className="table-wrap"><table><thead><tr><th>PRODUCT ID</th><th>PRODUCT CODE</th><th>PRODUCT NAME · EN</th><th>PRODUCT NAME · TH</th><th>FAMILY</th><th>PIECES / DROP</th><th>SECONDS / DROP</th></tr></thead><tbody>
        {products.map((product) => <tr key={product.id}><td className="id-cell">#{product.id}</td><td><strong>{product.code}</strong></td><td>{product.name}</td><td>{product.name_thai || '—'}</td><td>{product.family || '—'}</td><td>{product.standard_pieces_per_drop ?? 'Not approved'}</td><td>{product.standard_cycle_time_sec ?? 'Not approved'}</td></tr>)}
        {!products.length && <tr><td colSpan={7}>{liveData ? 'No live Product rows are available.' : 'Live Product rows are unavailable; mock fallback rows are intentionally hidden.'}</td></tr>}
      </tbody></table></div>
      <p className="field-hint">Product Standard values are shown only when an approved effective revision exists.</p>
    </section>
    <section className="card top-gap" aria-label="Wet reject reference data">
      <div className="card-head"><div><span className="eyebrow">REFERENCE DATA</span><h3>Wet Reject reasons</h3></div><span className="tag muted">READ ONLY</span></div>
      <div className="table-wrap"><table><thead><tr><th>REASON ID</th><th>COUNTER CODE</th><th>DESCRIPTION</th><th>STATUS</th></tr></thead><tbody>
        {rejectReasons.map((reason) => <tr key={reason.code}><td>—</td><td className="id-cell">{reason.code}</td><td>{reason.label}</td><td><span className="tag amber">MAPPING NOT APPROVED</span></td></tr>)}
        {!rejectReasons.length && <tr><td colSpan={4}>{liveData ? 'No active reasons are available.' : 'Live reference rows are unavailable.'}</td></tr>}
      </tbody></table></div>
    </section>
  </>;
}

function MouldMaster({ products, moulds, liveData }: { products: Product[]; moulds: Mould[]; liveData: boolean }) {
  return <section className="card top-gap" aria-label="Mould master">
    <div className="card-head"><div><span className="eyebrow">MOULD</span><h3>Product-specific Mould register</h3></div><span className={`tag ${liveData ? 'blue' : 'amber'}`}>{liveData ? 'LIVE SQL · READ ONLY' : 'LIVE DATA UNAVAILABLE'}</span></div>
    <p className="subtle">Mould-to-Product assignment and counters are read from the existing omagmes.Mould master. Recondition transitions are disabled because no approved persistence API is available.</p>
    <div className="table-wrap"><table><thead><tr><th>MOULD ID</th><th>MOULD CODE</th><th>MOULD NAME</th><th>PRODUCT ID</th><th>PRODUCT</th><th>STATUS</th><th>CURRENT AGE · DROPS</th><th>LIFETIME · DROPS</th></tr></thead><tbody>
      {moulds.map((mould) => { const product = products.find((item) => item.id === mould.product_id); return <tr key={mould.id}><td className="id-cell">#{mould.id}</td><td><strong>{mould.code}</strong></td><td>{mould.name || '—'}</td><td>#{mould.product_id}</td><td>{product?.code ?? 'Unknown'}{product ? ` · ${product.name}` : ''}</td><td><span className={`tag ${mould.status === 'ACTIVE' ? 'green' : 'amber'}`}>{mould.status}</span></td><td>{mould.current_age_drops.toLocaleString()}</td><td>{mould.lifetime_age_drops.toLocaleString()}</td></tr>; })}
      {!moulds.length && <tr><td colSpan={8}>{liveData ? 'No active Mould rows are available.' : 'Live Mould rows are unavailable; mock fallback rows are intentionally hidden.'}</td></tr>}
    </tbody></table></div>
  </section>;
}
