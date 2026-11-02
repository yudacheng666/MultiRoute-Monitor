'use strict';
const {test} = require('node:test');
const assert = require('node:assert/strict');
const core = require('../web/core.js');

test('default four routes are explicitly fictional and valid', () => {
  const routes = core.loadRoutes(null);
  assert.equal(routes.length, 4);
  for (const route of routes) {
    assert.match(route.origin, /^虚构/);
    assert.ok(route.id);
  }
});
test('persisted edits and empty routes survive roundtrip', () => {
  assert.deepEqual(core.loadRoutes('[]'), []);
  const edited = [{ id:'custom_1', name:'测试', origin:'甲', destination:'乙', base_minutes:20 }];
  assert.deepEqual(core.loadRoutes(JSON.stringify(edited)), edited);
});
test('damaged storage safely returns mock defaults', () => {
  assert.equal(core.loadRoutes('{bad').length, 4);
  assert.equal(core.loadRoutes(JSON.stringify(Array.from({length:7}, (_,i)=>({id:'a'+i})))) .length, 4);
});
test('input length, id, duration, endpoints and XSS text validation', () => {
  const raw = {name:'<img src=x onerror=alert(1)>',origin:'示例A',destination:'示例B',base_minutes:20};
  const n = core.normalizeRoute(raw, 'abc');
  assert.equal(n.name, raw.name); // render must insert as text, not HTML
  assert.throws(() => core.normalizeRoute({...raw, origin:'same',destination:'same'}, 'abc'));
  assert.throws(() => core.normalizeRoute({...raw, base_minutes:1}, 'abc'));
  assert.throws(() => core.normalizeRoute({...raw, name:'x'.repeat(37)}, 'abc'));
  assert.throws(() => core.normalizeRoute(raw, '../escape'));
});
test('mock is deterministic within time slot and explicitly simulated', () => {
  const route = core.DEFAULT_ROUTES[0];
  const a=core.mockMetrics(route,1234), b=core.mockMetrics(route,1234);
  assert.deepEqual(a,b);
  assert.equal(a.source,'SIMULATED');
  assert.ok(a.duration>=route.base_minutes);
  assert.equal(a.sections.length,7);
});
test('safe interval and daily budget', () => {
  assert.equal(core.safeInterval('bad'),10);
  assert.equal(core.safeInterval('5'),5);
  assert.equal(core.budgetEstimate(6,10,24),864);
  assert.throws(()=>core.budgetEstimate(7,5,24));
});
