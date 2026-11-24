import assert from 'node:assert/strict';
import { afterEach, test } from 'node:test';
import { loadProductionPlans } from '../src/productionPlans.ts';

const originalFetch = globalThis.fetch;

afterEach(() => {
  globalThis.fetch = originalFetch;
});

test('shares concurrent plan reads and fetches fresh data on a later refresh', async () => {
  let calls = 0;
  const urls = [];
  let releaseRequest;
  globalThis.fetch = (url) => {
    calls += 1;
    urls.push(String(url));
    return new Promise((resolve) => { releaseRequest = resolve; });
  };

  const first = loadProductionPlans('2026-11-17');
  const concurrent = loadProductionPlans('2026-11-17');
  assert.equal(calls, 1);
  releaseRequest(new Response(JSON.stringify({ plans: [], warnings: [], truncated: false }), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  }));
  await Promise.all([first, concurrent]);
  assert.equal(urls[0], '/api/press-lots/plans?production_date=2026-11-17');

  globalThis.fetch = async () => {
    calls += 1;
    return new Response(JSON.stringify({ plans: [], warnings: [], truncated: false }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    });
  };
  await loadProductionPlans('2026-11-17');
  assert.equal(calls, 2);
});

test('does not share plan requests across different Production Dates', async () => {
  const urls = [];
  globalThis.fetch = async (url) => {
    urls.push(String(url));
    return new Response(JSON.stringify({ plans: [], warnings: [], truncated: false }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    });
  };

  await Promise.all([loadProductionPlans('2026-11-17'), loadProductionPlans('2026-11-18')]);
  assert.deepEqual(urls.sort(), [
    '/api/press-lots/plans?production_date=2026-11-17',
    '/api/press-lots/plans?production_date=2026-11-18',
  ]);
});

test('surfaces the API error detail for the Edit Log to display', async () => {
  globalThis.fetch = async () => new Response(JSON.stringify({ detail: 'PIS plan source is temporarily unavailable.' }), {
    status: 503,
    headers: { 'Content-Type': 'application/json' },
  });

  await assert.rejects(loadProductionPlans(), /PIS plan source is temporarily unavailable\./);
});
