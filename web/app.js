(function () {
  'use strict';
  const Core = window.RouteCore;
  const routeGrid = document.getElementById('routes');
  const form = document.getElementById('route-form');
  const dialog = document.getElementById('route-dialog');
  const formError = document.getElementById('form-error');
  const intervalSelect = document.getElementById('refresh-interval');
  const pauseButton = document.getElementById('pause-toggle');
  const toast = document.getElementById('toast');
  const KEY_ROUTES = 'multi-route-monitor.routes.v1';
  const KEY_INTERVAL = 'multi-route-monitor.interval.v1';
  const COLORS = { '畅通': '#39af88', '缓行': '#e5b959', '拥堵': '#e88a58', '严重拥堵': '#da5b64' };
  const CLASS = { '畅通': 'clear', '缓行': 'slow', '拥堵': 'busy', '严重拥堵': 'heavy' };
  const state = { routes: [], measured: {}, interval: 10, paused: false, timer: null,
    nextAt: null, editing: null, toastTimer: null };

  function escapeHTML(value) {
    return String(value).replace(/[&<>"']/g, function (x) {
      return {'&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;'}[x];
    });
  }
  function getStorage(key) {
    try { return window.localStorage.getItem(key); } catch (_) { return null; }
  }
  function putStorage(key, value) {
    try {
      window.localStorage.setItem(key, value);
      return true;
    } catch (_) {
      showToast('浏览器存储不可用，配置仅在此页面暂存');
      return false;
    }
  }
  function formatTime(date) {
    return new Intl.DateTimeFormat('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false }).format(date);
  }
  function showToast(message) {
    toast.textContent = message;
    toast.hidden = false;
    if (state.toastTimer !== null) clearTimeout(state.toastTimer);
    state.toastTimer = setTimeout(function () { toast.hidden = true; state.toastTimer = null; }, 3200);
  }
  function segmentPoints(route) {
    // SVG schematic topology only. NOT geo coordinates and NOT an actual map.
    let s = 7;
    const key = route.id + route.origin + route.destination;
    for (let i = 0; i < key.length; i += 1) s = (Math.imul(s, 33) + key.charCodeAt(i)) >>> 0;
    const points = [];
    for (let i = 0; i <= 7; i += 1) {
      const wave = Math.sin(i * 1.48 + (s % 11) * 0.23) * 23;
      const drift = ((s >>> (i % 20)) & 7) * 2;
      const y = Math.max(22, Math.min(113, 66 + wave + drift - 8));
      points.push([15 + i * 53, Math.round(y)]);
    }
    return points;
  }
  function drawSchematic(route, data) {
    const pts = segmentPoints(route);
    let svg = '<svg viewBox="0 0 400 136" role="img" aria-label="模拟路线示意线，非真实地图">';
    svg += '<defs><pattern id="grid-' + escapeHTML(route.id) + '" width="28" height="28" patternUnits="userSpaceOnUse"><path d="M 28 0 L 0 0 0 28" fill="none" stroke="#476079" stroke-opacity=".15" stroke-width="1"/></pattern></defs>';
    svg += '<rect width="400" height="136" fill="url(#grid-' + escapeHTML(route.id) + ')"/>';
    svg += '<path d="M-10 112 L95 38 L228 92 L416 34" stroke="#41556d" stroke-width="15" opacity=".2" fill="none" stroke-linecap="round"/>';
    svg += '<path d="M0 30 L162 112 L400 68" stroke="#374a61" stroke-width="9" opacity=".25" fill="none"/>';
    for (let i = 0; i < data.sections.length; i += 1) {
      const p = pts[i], q = pts[i + 1];
      const d = 'M ' + p[0] + ' ' + p[1] + ' L ' + q[0] + ' ' + q[1];
      svg += '<path d="' + d + '" fill="none" stroke="#071321" stroke-width="11" stroke-linecap="round"/>';
      svg += '<path d="' + d + '" fill="none" stroke="' + COLORS[data.sections[i]] + '" stroke-width="5" stroke-linecap="round"/>';
    }
    svg += '<circle cx="' + pts[0][0] + '" cy="' + pts[0][1] + '" r="9" fill="#1b3750" stroke="#66c2dc" stroke-width="3"/>';
    svg += '<circle cx="' + pts[7][0] + '" cy="' + pts[7][1] + '" r="9" fill="#2b4c3f" stroke="#8cddad" stroke-width="3"/>';
    svg += '<text x="' + (pts[0][0] - 4) + '" y="' + (pts[0][1] + 3) + '" fill="#e9fdff" font-size="9">起</text>';
    svg += '<text x="' + (pts[7][0] - 4) + '" y="' + (pts[7][1] + 3) + '" fill="#eaffef" font-size="9">终</text>';
    return svg + '</svg>';
  }
  function sampleRoute(route) {
    const now = new Date();
    const slot = Math.floor(now.getTime() / (10 * 60 * 1000));
    state.measured[route.id] = { data: Core.mockMetrics(route, slot), at: now };
  }
  function refreshAll(silent) {
    state.routes.forEach(sampleRoute);
    render();
    if (!silent) showToast('已刷新 ' + state.routes.length + ' 条模拟路线（非真实查询）');
  }
  function refreshSingle(id) {
    const route = state.routes.find(function (x) { return x.id === id; });
    if (!route) return;
    sampleRoute(route);
    render();
    showToast('已刷新「' + route.name + '」的模拟数据');
  }
  function persist() {
    putStorage(KEY_ROUTES, JSON.stringify(state.routes));
  }
  function render() {
    const data = state.routes.map(function (route) {
      if (!state.measured[route.id]) sampleRoute(route);
      return {route:route, reading:state.measured[route.id]};
    });
    document.getElementById('stat-count').textContent = String(data.length);
    document.getElementById('stat-avg').textContent = data.length ?
      String(Math.round(data.reduce(function (sum, x) {return sum+x.reading.data.duration;}, 0)/data.length)) : '—';
    document.getElementById('stat-congested').textContent = String(data.filter(function (x) {
      return x.reading.data.traffic === '拥堵' || x.reading.data.traffic === '严重拥堵';
    }).length);
    document.getElementById('route-count-pill').textContent = String(data.length).padStart(2,'0');
    document.getElementById('add-route').disabled = data.length >= Core.LIMIT;
    if (!data.length) {
      routeGrid.innerHTML = '<div class="empty-state"><h3>还没有路线</h3><p>点击「添加路线」，创建一条虚构模拟路线。</p></div>';
      return;
    }
    routeGrid.innerHTML = data.map(function (x) {
      const r = x.route, reading = x.reading, m = reading.data;
      const id = escapeHTML(r.id), name = escapeHTML(r.name);
      return '<article class="route-card" data-id="' + id + '">' +
        '<div class="card-top"><div><h3 class="route-name">' + name + '</h3>' +
        '<div class="endpoints">' + escapeHTML(r.origin) + '<span class="arrow"> → </span>' + escapeHTML(r.destination) + '</div></div>' +
        '<div class="card-actions"><button class="icon-btn" type="button" data-action="edit" data-id="' + id + '" aria-label="编辑' + name + '" title="编辑">✎</button>' +
        '<button class="icon-btn" type="button" data-action="delete" data-id="' + id + '" aria-label="删除' + name + '" title="删除">×</button></div></div>' +
        '<div class="card-middle"><div><div class="eta"><strong>' + m.duration + '</strong><span class="unit">分钟 · 模拟</span></div>' +
        '<div class="delay">相对虚构基础时间 +' + m.delay + ' 分钟</div></div>' +
        '<span class="traffic-tag ' + CLASS[m.traffic] + '">模拟' + m.traffic + '</span></div>' +
        '<div class="schematic">' + drawSchematic(r, m) + '</div>' +
        '<div class="card-bottom"><span><span class="sim-chip">MOCK</span>刷新 ' + formatTime(reading.at) + '</span>' +
        '<button type="button" data-action="refresh" data-id="' + id + '" aria-label="刷新' + name + '">↻ 刷新此路线</button></div></article>';
    }).join('');
  }
  function ticker() {
    document.getElementById('clock').textContent = formatTime(new Date());
    const note = document.getElementById('refresh-note');
    if (state.paused) { note.textContent = '自动刷新已暂停 · 可手动刷新'; return; }
    if (state.nextAt) {
      const remain = Math.max(0, Math.ceil((state.nextAt-Date.now())/1000));
      note.textContent = '下一次模拟刷新约 ' + Math.ceil(remain / 60) + ' 分钟后';
    }
  }
  function setupTimer() {
    if (state.timer) { clearInterval(state.timer); state.timer = null; }
    if (!state.paused) {
      state.nextAt = Date.now() + state.interval * 60000;
      state.timer = setInterval(function () {
        refreshAll(true);
        state.nextAt = Date.now() + state.interval * 60000;
      }, state.interval * 60000);
    } else state.nextAt = null;
    pauseButton.textContent = state.paused ? '继续' : '暂停';
    pauseButton.setAttribute('aria-pressed', state.paused ? 'true' : 'false');
    ticker();
  }
  function openDialog(route) {
    state.editing = route ? route.id : null;
    document.getElementById('dialog-title').textContent = route ? '编辑模拟路线' : '添加模拟路线';
    form.reset();
    form.elements.namedItem('name').value = route ? route.name : '';
    form.elements.namedItem('origin').value = route ? route.origin : '';
    form.elements.namedItem('destination').value = route ? route.destination : '';
    form.elements.namedItem('base_minutes').value = route ? route.base_minutes : 25;
    formError.hidden = true;
    dialog.showModal();
    form.elements.namedItem('name').focus();
  }
  function closeDialog() { dialog.close(); state.editing = null; }
  function saveFromForm(event) {
    event.preventDefault();
    const input = {
      name: form.elements.namedItem('name').value,
      origin: form.elements.namedItem('origin').value,
      destination: form.elements.namedItem('destination').value,
      base_minutes: form.elements.namedItem('base_minutes').value
    };
    if (!state.editing && state.routes.length >= Core.LIMIT) {
      formError.textContent = '最多只能添加6条路线'; formError.hidden = false; return;
    }
    const id = state.editing || ('route-' + Date.now().toString(36) + '-' + Math.random().toString(36).slice(2,9));
    try {
      const route = Core.normalizeRoute(input, id);
      const index = state.routes.findIndex(function (r) {return r.id === state.editing;});
      if (index >= 0) state.routes[index] = route;
      else state.routes.push(route);
      delete state.measured[id];
      persist();
      sampleRoute(route);
      render();
      closeDialog();
      showToast('路线配置已保存在此浏览器（模拟模式）');
    } catch (error) {
      formError.textContent = error.message;
      formError.hidden = false;
    }
  }
  function handleCardClick(event) {
    const btn = event.target.closest('button[data-action]');
    if (!btn) return;
    const id = btn.getAttribute('data-id');
    const r = state.routes.find(function (x) { return x.id === id; });
    if (!r) return;
    const action = btn.getAttribute('data-action');
    if (action === 'refresh') refreshSingle(id);
    if (action === 'edit') openDialog(r);
    if (action === 'delete') {
      if (!window.confirm('确认删除模拟路线「' + r.name + '」？')) return;
      state.routes = state.routes.filter(function (x) { return x.id !== id; });
      delete state.measured[id];
      persist();
      render();
      showToast('已删除模拟路线');
    }
  }
  function init() {
    state.routes = Core.loadRoutes(getStorage(KEY_ROUTES));
    state.interval = Core.safeInterval(getStorage(KEY_INTERVAL));
    intervalSelect.value = String(state.interval);
    document.getElementById('add-route').addEventListener('click', function () {openDialog(null);});
    document.getElementById('refresh-all').addEventListener('click', function () {refreshAll(false);});
    pauseButton.addEventListener('click', function () {state.paused=!state.paused; setupTimer();});
    intervalSelect.addEventListener('change', function () {
      state.interval = Core.safeInterval(intervalSelect.value);
      putStorage(KEY_INTERVAL, String(state.interval));
      setupTimer();
    });
    routeGrid.addEventListener('click', handleCardClick);
    form.addEventListener('submit', saveFromForm);
    document.getElementById('dialog-close').addEventListener('click', closeDialog);
    document.getElementById('dialog-cancel').addEventListener('click', closeDialog);
    dialog.addEventListener('click', function(e){if(e.target===dialog)closeDialog();});
    refreshAll(true);
    setupTimer();
    setInterval(ticker,1000);
  }
  init();
})();
