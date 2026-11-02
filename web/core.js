/* Core data model for mock-only board. No external network or API keys. */
(function (root, factory) {
  'use strict';
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  if (root) root.RouteCore = api;
})(typeof window !== 'undefined' ? window : null, function () {
  'use strict';
  const LIMIT = 6;
  const INTERVALS = [5, 10, 15, 30];
  const DEFAULT_ROUTES = [
    { id: 'example-a', name: '示例路线 A', origin: '虚构起点 A', destination: '虚构终点 A', base_minutes: 32 },
    { id: 'example-b', name: '示例路线 B', origin: '虚构起点 B', destination: '虚构终点 B', base_minutes: 18 },
    { id: 'example-c', name: '示例路线 C', origin: '虚构起点 C', destination: '虚构终点 C', base_minutes: 46 },
    { id: 'example-d', name: '示例路线 D', origin: '虚构起点 D', destination: '虚构终点 D', base_minutes: 55 }
  ];
  function text(value, max) {
    const v = typeof value === 'string' ? value.trim().replace(/\s+/g, ' ') : '';
    if (!v || v.length > max) throw new Error('请输入1至' + max + '个字符');
    return v;
  }
  function normalizeRoute(value, id) {
    if (!value || typeof value !== 'object') throw new Error('路线格式错误');
    const base = Number(value.base_minutes);
    if (!Number.isInteger(base) || base < 5 || base > 240) throw new Error('基础时间应为5至240分钟');
    const name = text(value.name, 36);
    const origin = text(value.origin, 60);
    const destination = text(value.destination, 60);
    if (origin === destination) throw new Error('起点和终点不能相同');
    const safeId = typeof id === 'string' && /^[a-zA-Z0-9_-]{1,80}$/.test(id) ? id : null;
    if (!safeId) throw new Error('无效的路线编号');
    return { id: safeId, name: name, origin: origin, destination: destination, base_minutes: base };
  }
  function loadRoutes(json) {
    if (typeof json !== 'string') return DEFAULT_ROUTES.map(function (r) { return normalizeRoute(r, r.id); });
    try {
      const parsed = JSON.parse(json);
      if (!Array.isArray(parsed) || parsed.length > LIMIT) throw new Error('bad route list');
      const ids = new Set();
      const routes = parsed.map(function (r) {
        const result = normalizeRoute(r, r.id);
        if (ids.has(result.id)) throw new Error('duplicate');
        ids.add(result.id);
        return result;
      });
      return routes;
    } catch (_) {
      return DEFAULT_ROUTES.map(function (r) { return normalizeRoute(r, r.id); });
    }
  }
  function hash(value) {
    let h = 2166136261;
    for (let i = 0; i < value.length; i += 1) {
      h ^= value.charCodeAt(i);
      h = Math.imul(h, 16777619);
    }
    return h >>> 0;
  }
  function category(delay, baseMinutes) {
    const ratio = delay / baseMinutes;
    if (ratio >= 0.34) return '严重拥堵';
    if (ratio >= 0.19) return '拥堵';
    if (ratio >= 0.08) return '缓行';
    return '畅通';
  }
  function mockMetrics(route, slot) {
    const value = normalizeRoute(route, route.id);
    const tick = Number.isFinite(Number(slot)) ? Math.floor(Number(slot)) : 0;
    const seed = hash(value.id + ':' + tick);
    const delay = seed % Math.max(4, Math.ceil(value.base_minutes * 0.48));
    const duration = value.base_minutes + delay;
    const traffic = category(delay, value.base_minutes);
    const sections = Array.from({length: 7}, function (_, i) {
      const t = (hash(value.id + ':segment:' + i + ':' + tick) % 5);
      return ['畅通', '畅通', '缓行', '拥堵', '严重拥堵'][t];
    });
    return { duration: duration, delay: delay, traffic: traffic,
      sections: sections, source: 'SIMULATED' };
  }
  function budgetEstimate(count, interval, hours) {
    if (!Number.isInteger(count) || count < 0 || count > LIMIT ||
        !INTERVALS.includes(interval) || !Number.isFinite(hours) || hours < 0 || hours > 24)
      throw new Error('无效的预算参数');
    return Math.ceil(count * 60 / interval * hours);
  }
  function safeInterval(value) {
    const v = Number(value);
    return INTERVALS.includes(v) ? v : 10;
  }
  return { LIMIT: LIMIT, INTERVALS: INTERVALS, DEFAULT_ROUTES: DEFAULT_ROUTES,
    normalizeRoute: normalizeRoute, loadRoutes: loadRoutes, mockMetrics: mockMetrics,
    budgetEstimate: budgetEstimate, safeInterval: safeInterval };
});
