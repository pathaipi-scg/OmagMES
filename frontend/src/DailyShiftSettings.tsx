import type { ChangeEvent } from 'react';
import './daily-shift-settings.css';

export type WorkTimeShiftStatus = 'LOADING' | 'UNAVAILABLE' | 'LOADED' | 'SAVED' | 'NOT_SAVED';

export type WorkTimeShiftSetting = {
  record_id: number;
  rec_time: string | null;
  work_type: string;
  shift_no: string;
  start_time: string | null;
  stop_time: string | null;
  speed: number | null;
  rw: number;
  active: boolean;
};

type Props = {
  rows: WorkTimeShiftSetting[];
  originalRows: WorkTimeShiftSetting[];
  status: WorkTimeShiftStatus;
  latestUpdateTime: string | null;
  loading: boolean;
  saving: boolean;
  message: string;
  error: string;
  onChange: (workType: string, shiftNo: string, field: 'start_time' | 'stop_time', value: string) => void;
  onSave: () => void;
};

const workTypes = [
  { value: '1', label: 'TYPE 1' },
  { value: '2', label: 'TYPE 2' },
  { value: '3', label: 'TYPE 3' },
];

function TimeCell({
  row, field, label, disabled, onChange,
}: {
  row: WorkTimeShiftSetting;
  field: 'start_time' | 'stop_time';
  label: string;
  disabled: boolean;
  onChange: (event: ChangeEvent<HTMLInputElement>) => void;
}) {
  return <td><input
    aria-label={label}
    className="daily-shift-time"
    type="time"
    step={1}
    value={row[field] ?? ''}
    disabled={disabled || !row.active}
    onChange={onChange}
  /></td>;
}

function ShiftCells({ row, loading, saving, onChange }: {
  row?: WorkTimeShiftSetting;
  loading: boolean;
  saving: boolean;
  onChange: Props['onChange'];
}) {
  if (!row) return <><td>Not configured in SQL</td><td>—</td><td>—</td></>;
  const inactive = !row.active;
  const unavailable = loading || saving || inactive;
  return <>
    <td>{`Shift ${row.shift_no}${inactive ? ' · INACTIVE' : ''}`}</td>
    <TimeCell row={row} field="start_time" label={`Type ${row.work_type} Shift ${row.shift_no} Start`} disabled={unavailable} onChange={(event) => onChange(row.work_type, row.shift_no, 'start_time', event.target.value)} />
    <TimeCell row={row} field="stop_time" label={`Type ${row.work_type} Shift ${row.shift_no} Stop`} disabled={unavailable} onChange={(event) => onChange(row.work_type, row.shift_no, 'stop_time', event.target.value)} />
  </>;
}

export default function DailyShiftSettings({
  rows, originalRows, status, latestUpdateTime, loading, saving, message, error, onChange, onSave,
}: Props) {
  const originalByKey = new Map(originalRows.map((row) => [`${row.work_type}:${row.shift_no}`, row]));
  const dirty = rows.some((row) => {
    const original = originalByKey.get(`${row.work_type}:${row.shift_no}`);
    return original && (row.start_time !== original.start_time || row.stop_time !== original.stop_time);
  });
  const statusText = loading || status === 'LOADING' ? 'LOADING FROM SQL'
    : status === 'UNAVAILABLE' ? 'SQL UNAVAILABLE'
      : saving ? 'SAVING'
        : dirty ? 'UNSAVED CHANGES'
          : status === 'SAVED' ? 'SAVED'
            : 'LOADED FROM dbo.WorkTime';

  return <section className="daily-shift-settings" aria-label="Shift Settings">
    <div className="daily-shift-settings-heading">
      <h2>Shift Settings</h2>
      <span className={`daily-shift-status ${status.toLowerCase().replace('_', '-')}`}>{statusText}</span>
    </div>
    <p className="subtle">Current values are the latest SQL record for each WorkType and ShiftNo. Saving appends history to dbo.WorkTime; settings are not specific to a Production Date.</p>
    {latestUpdateTime && <p className="field-hint">Latest SQL configuration timestamp: {latestUpdateTime.replace('T', ' ')}</p>}
    {loading ? <div className="notice-box" role="status">Loading Shift Settings from dbo.WorkTime…</div> : <div className="daily-shift-table-wrap">
      <table className="daily-shift-table">
        <thead><tr><th>TYPE</th><th>FIRST SHIFT</th><th>START</th><th>STOP</th><th>SECOND SHIFT</th><th>START</th><th>STOP</th></tr></thead>
        <tbody>{workTypes.map((workType) => {
          const shifts = rows.filter((row) => row.work_type === workType.value);
          const rowCount = Math.max(1, Math.ceil(shifts.length / 2));
          return Array.from({ length: rowCount }, (_, pairIndex) => {
            const first = shifts[pairIndex * 2];
            const second = shifts[pairIndex * 2 + 1];
            return <tr key={`${workType.value}-${pairIndex}`}>
              <th scope="row">{pairIndex === 0 ? workType.label : ''}</th>
              <ShiftCells row={first} loading={loading} saving={saving} onChange={onChange} />
              <ShiftCells row={second} loading={loading} saving={saving} onChange={onChange} />
            </tr>;
          });
        })}</tbody>
      </table>
    </div>}
    {error && <div className="daily-shift-message error" role="alert">{error}</div>}
    <div className="daily-shift-settings-footer">
      <span>Source: dbo.WorkTime · latest per WorkType / ShiftNo</span>
      <button className="button primary" type="button" disabled={loading || saving || status === 'UNAVAILABLE' || !dirty} onClick={onSave}>{saving ? 'Saving…' : 'SAVE SHIFT SETTINGS'}</button>
    </div>
    {message && <div className={`daily-shift-message ${status === 'SAVED' && !dirty ? 'success' : 'error'}`} role={status === 'SAVED' && !dirty ? 'status' : 'alert'}>{message}</div>}
  </section>;
}
