import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';

const productionPage = await readFile(new URL('../src/ProductionPage.tsx', import.meta.url), 'utf8');
const app = await readFile(new URL('../src/App.tsx', import.meta.url), 'utf8');
const shiftSettings = await readFile(new URL('../src/DailyShiftSettings.tsx', import.meta.url), 'utf8');

test('Production AutoLots stay SQL-owned and render the compact selectable assignment table', () => {
  assert.match(productionPage, /\/api\/production\/overview\?production_date=/);
  for (const column of ['Select', 'Lot No.', 'Plan', 'Product', 'Mould', 'Shift', 'Start', 'End', 'Counter']) {
    assert.match(productionPage, new RegExp(`<th[^>]*>${column}<\\/th>`));
  }
  assert.match(productionPage, /type="radio"/);
  assert.match(productionPage, /is-selected/);
  assert.match(productionPage, /\/api\/press-lots\/plans\?production_date=/);
  assert.match(productionPage, /PLAN REFRESH/);
  assert.match(productionPage, /\/api\/products\/\$\{resolvedProductId\}\/active-moulds/);
  assert.match(productionPage, /\/api\/auto-lots\/\$\{selectedAutoLotId\}\/assignment/);
  assert.match(productionPage, /\/api\/auto-lots\/reconcile/);
  assert.doesNotMatch(productionPage, /Existing Official Production Lots/);
  assert.doesNotMatch(productionPage, /EDIT LOT|modal|dialog/);
});

test('Production ShiftType loads from existing view and saves selection to ProductionDetails', () => {
  assert.match(app, /\/api\/production\/shift-type\?\$\{query\}/);
  assert.match(app, /useState<ShiftTypeNumber>\(3\)/);
  assert.match(app, /status: 'SAVED' \| 'DEFAULT'/);
  assert.match(app, /\/api\/production\/shift-type'/);
  assert.match(app, /method: 'POST'/);
  assert.match(app, /production_date: productionDate, selected_type: nextType/);
  assert.match(app, /setProductionPageReloadKey\(\(version\) => version \+ 1\)/);
  assert.doesNotMatch(app, /\/api\/shift-configuration/);
});

test('Setting Shift loads latest WorkTime rows and saves only changed values', () => {
  assert.match(app, /\/api\/worktime\/shift-settings/);
  assert.match(app, /changedRows\.map\(\(\{ work_type, shift_no, start_time, stop_time \}\)/);
  assert.match(app, /page === 'Setting' && settingTab === 'SHIFT'[\s\S]*?loadWorkTimeShiftSettings/);
  assert.match(shiftSettings, /row\.shift_no/);
  assert.match(shiftSettings, /row\.active/);
  assert.match(shiftSettings, /disabled=\{loading \|\| saving \|\| status === 'UNAVAILABLE' \|\| !dirty\}/);
  assert.match(shiftSettings, /Shift Settings/);
  assert.doesNotMatch(shiftSettings, /Shift times · \$\{productionDate\}/);
});
