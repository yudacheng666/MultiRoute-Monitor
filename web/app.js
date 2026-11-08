(function () {
  'use strict';
  const Core = window.RouteCore;
  const routeGrid = document.getElementById('routes');
  const form = document.getElementById('route-form');
  const dialog = document.getElementById('route-dialog');
  const amapAuthDialog = document.getElementById('amap-auth-dialog');
  const amapAuthForm = document.getElementById('amap-auth-form');
  const formError = document.getElementById('form-error');
  const intervalSelect = document.getElementById('refresh-interval');
  const pauseButton = document.getElementById('pause-toggle');
  const toast = document.getElementById('toast');
  const KEY_ROUTES = 'multi-route-monitor.routes.v1';
  const KEY_INTERVAL = 'multi-route-monitor.interval.v1';
  const COLORS = { '畅通': '#39af88', '缓行': '#e5b959', '拥堵': '#e88a58', '严重拥堵': '#da5b64' };
  const CLASS = { '畅通': 'clear', '缓行': 'slow', '拥堵': 'busy', '严重拥堵': 'heavy' };
  const state = { routes: [], measured: {}, interval: 10, paused: false, timer: null,
    nextAt: null, editing: null, toastTimer: null,
    liveReady: false, liveReadings: {}, liveErrors: {}, liveLoading: {},
    mapEnabled: false, mapKey: null, liveAuto: false, liveBatch: false };

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
    delete state.liveReadings[id];
    sampleRoute(route);
    render();
    showToast('已刷新「' + route.name + '」的模拟数据');
  }
  function persist() {
    putStorage(KEY_ROUTES, JSON.stringify(state.routes));
  }
  function drawRealGeometry(result) {
    const segs = Array.isArray(result.segments) ? result.segments : [];
    const pts = segs.flatMap(function(s) { return Array.isArray(s.points) ? s.points : []; });
    if (!pts.length) return '<div class="geo-empty">高德未返回可绘制的道路坐标</div>';
    const xs=pts.map(p=>p[0]), ys=pts.map(p=>p[1]);
    const minX=Math.min.apply(null,xs), maxX=Math.max.apply(null,xs);
    const minY=Math.min.apply(null,ys), maxY=Math.max.apply(null,ys);
    const spanX=Math.max(0.000001,maxX-minX), spanY=Math.max(0.000001,maxY-minY);
    const scale=Math.min(360/spanX,108/spanY);
    const w=spanX*scale,h=spanY*scale,xOff=(400-w)/2,yOff=(136-h)/2;
    let svg='<svg viewBox="0 0 400 136" role="img" aria-label="高德返回的真实道路坐标线形，未加载底图">';
    for(const seg of segs) {
      if(!Array.isArray(seg.points)||seg.points.length<2)continue;
      const points=seg.points.map(function(p) {
        return (xOff+(p[0]-minX)*scale).toFixed(1)+','+(yOff+(maxY-p[1])*scale).toFixed(1);
      }).join(' ');
      const color=COLORS[seg.status]||'#8b9bab';
      svg+='<polyline points="'+points+'" fill="none" stroke="'+color+'" stroke-width="5" stroke-linecap="round" stroke-linejoin="round"/>';
    }
    return svg+'</svg>';
  }
  function requestReal(id) {
    const route = state.routes.find(function(r){return r.id===id;});
    if (!state.liveReady || !route || !route.origin_coord || !route.destination_coord || state.liveLoading[id])
      return Promise.resolve(false);
    state.liveLoading[id] = true;
    delete state.liveErrors[id];
    render();
    const req = {origin:route.origin_coord,destination:route.destination_coord};
    if(route.waypoint_coord)req.waypoints=[route.waypoint_coord];
    return fetch('/api/amap/drive',{method:'POST',headers:{'Content-Type':'application/json','X-MRM-Request':'1'},
      body:JSON.stringify(req),cache:'no-store'}).then(async function(response) {
        const payload=await response.json();
        if(!response.ok)throw new Error(payload.error || '高德查询失败');
        if(payload.source!=='AMAP')throw new Error('返回的数据来源错误');
        const current=state.routes.find(r=>r.id===id);
        if(current && current.origin_coord===route.origin_coord &&
          current.destination_coord===route.destination_coord &&
          current.waypoint_coord===route.waypoint_coord) {
          state.liveReadings[id]=payload;
        }
        return true;
      }).catch(function(error) {
        delete state.liveReadings[id];
        state.liveErrors[id]=String(error.message||'请求失败').slice(0,90);
        return false;
      }).finally(function() {
        delete state.liveLoading[id];render();
      });
  }
  async function refreshLiveAll(automatic) {
    if (!state.liveReady || state.liveBatch) return;
    const targets=state.routes.filter(function(r){return r.origin_coord && r.destination_coord;});
    if (!targets.length) {
      if(!automatic)showToast('请先编辑路线并填写高德经纬度');
      return;
    }
    state.liveBatch=true;
    const button=document.getElementById('refresh-live-all');
    if(button)button.disabled=true;
    try {
      for(let i=0;i<targets.length;i+=1) {
        if(automatic && (!state.liveAuto || state.paused))break;
        await requestReal(targets[i].id);
        if(i<targets.length-1)await new Promise(resolve=>setTimeout(resolve,2100));
      }
    } finally {
      state.liveBatch=false;
      if(button)button.disabled=false;
      if(!automatic)showToast('高德路线查询批次已完成；请查看各路线结果');
      detectLiveAvailability();
    }
  }
  function render() {
    const data = state.routes.map(function (route) {
      if (!state.measured[route.id]) sampleRoute(route);
      return {route:route, reading:state.measured[route.id]};
    });
    document.getElementById('route-count-pill').textContent = String(data.length).padStart(2,'0');
    document.getElementById('add-route').disabled = data.length >= Core.LIMIT;
    if (!data.length) {
      routeGrid.innerHTML = '<div class="empty-state"><h3>还没有路线</h3><p>点击「添加路线」，创建一条虚构模拟路线。</p></div>';
      return;
    }
    routeGrid.innerHTML = data.map(function (x) {
      const r = x.route, reading = x.reading, m = reading.data;
      const id = escapeHTML(r.id), name = escapeHTML(r.name);
      const live = state.liveReadings[r.id];
      const realButton = state.liveReady && r.origin_coord && r.destination_coord ?
        '<button type="button" data-action="real" data-id="'+id+'"'+(state.liveLoading[r.id]?' disabled':'')+
        ' aria-label="高德手动查询'+name+'">'+(state.liveLoading[r.id]?'查询中…':'高德查询')+'</button>' : '';
      const mapButton = state.mapEnabled && live ?
        '<button type="button" data-action="map" data-id="'+id+'" aria-label="加载高德地图'+name+'">查看高德地图</button>' : '';
      const errorNote = state.liveErrors[r.id] ? '<div class="live-error">'+escapeHTML(state.liveErrors[r.id])+'</div>':'';
      const chart = live ? drawRealGeometry(live) : drawSchematic(r,m);
      const eta = live ? live.eta_minutes : m.duration;
      const source = live ? '分钟 · 高德（单次查询）' : '分钟 · 模拟';
      const detail = live ? (live.distance_km+' 公里 · '+(live.traffic_available?'有分段路况':'路况未知')) :
        ('相对虚构基础时间 +'+m.delay+' 分钟');
      const tag = live ? (live.traffic_available ? '高德路况已返回' : '高德路况未知') : ('模拟'+m.traffic);
      return '<article class="route-card" data-id="' + id + '">' +
        '<div class="card-top"><div><h3 class="route-name">' + name + '</h3>' +
        '<div class="endpoints">' + escapeHTML(r.origin) + '<span class="arrow"> → </span>' + escapeHTML(r.destination) + '</div></div>' +
        '<div class="card-actions"><button class="icon-btn" type="button" data-action="edit" data-id="' + id + '" aria-label="编辑' + name + '" title="编辑">✎</button>' +
        '<button class="icon-btn" type="button" data-action="delete" data-id="' + id + '" aria-label="删除' + name + '" title="删除">×</button></div></div>' +
        '<div class="card-middle"><div><div class="eta"><strong>' + eta + '</strong><span class="unit">'+source+'</span></div>' +
        '<div class="delay">'+detail+'</div></div>' +
        '<span class="traffic-tag '+(live?'clear':CLASS[m.traffic])+'">'+tag+'</span></div>' +
        '<div class="schematic '+(live?'real-geometry':'')+'">' + chart + '</div>' +
        '<div class="card-bottom"><span><span class="sim-chip">'+(live?'AMAP':'MOCK')+'</span>' +
        (live?'手动查询 '+escapeHTML(live.fetched_at||'（时间未知）'):'模拟刷新 '+formatTime(reading.at))+'</span>' +
        '<div class="card-buttons">'+mapButton+realButton+
        '<button type="button" data-action="refresh" data-id="' + id + '" aria-label="刷新' + name + '">↻ 模拟刷新</button></div></div>' +
        errorNote+'</article>';
    }).join('');
    if (window.AMapMap) window.AMapMap.destroyDetached();
  }
  function ticker() {
    document.getElementById('clock').textContent = formatTime(new Date());
    const note = document.getElementById('refresh-note');
    if (state.paused) { note.textContent = '自动刷新已暂停 · 可手动刷新'; return; }
    if (state.nextAt) {
      const remain = Math.max(0, Math.ceil((state.nextAt-Date.now())/1000));
      const prefix=state.liveAuto && state.liveReady ? '下一批高德真实路况查询约 ' :
        (state.liveReady ? '模拟数据刷新；真实路况需手动查询 · 下一次模拟刷新约 ' : '下一次模拟刷新约 ');
      note.textContent = prefix + Math.ceil(remain / 60) + ' 分钟后';
    }
  }
  function setupTimer() {
    if (state.timer) { clearTimeout(state.timer); state.timer = null; }
    const schedule=function() {
      if(state.paused)return;
      state.nextAt=Date.now()+state.interval*60000;
      state.timer=setTimeout(async function() {
        if(state.liveAuto && state.liveReady)await refreshLiveAll(true);
        else refreshAll(true);
        schedule();
      },state.interval*60000);
    };
    if (!state.paused) schedule();
    else state.nextAt = null;
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
    form.elements.namedItem('origin_coord').value = route ? (route.origin_coord||'') : '';
    form.elements.namedItem('destination_coord').value = route ? (route.destination_coord||'') : '';
    form.elements.namedItem('waypoint_coord').value = route ? (route.waypoint_coord||'') : '';
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
      base_minutes: form.elements.namedItem('base_minutes').value,
      origin_coord: form.elements.namedItem('origin_coord').value,
      destination_coord: form.elements.namedItem('destination_coord').value,
      waypoint_coord: form.elements.namedItem('waypoint_coord').value
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
      delete state.liveReadings[id];
      delete state.liveErrors[id];
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
  async function openMap(route) {
    if (!state.mapEnabled || !state.mapKey || !window.AMapMap) return;
    const live=state.liveReadings[route.id];
    if (!live) return;
    const card=Array.from(routeGrid.querySelectorAll('.route-card')).find(
      function(el){return el.getAttribute('data-id')===route.id;});
    if (!card) return;
    const node=card.querySelector('.schematic');
    const btn=card.querySelector('button[data-action="map"]');
    if (!node||!btn||btn.disabled) return;
    btn.disabled=true;btn.textContent='地图加载中…';
    try {
      const gate=await fetch('/api/amap/map-init',{method:'POST',
        headers:{'Content-Type':'application/json','X-MRM-Request':'1'},
        body:JSON.stringify({}),cache:'no-store'});
      const gatePayload=await gate.json();
      if(!gate.ok)throw new Error(gatePayload.error||'地图初始化额度已用完');
      node.classList.add('mapbox-active');
      await window.AMapMap.show(node,live.segments,state.mapKey);
      btn.textContent='高德地图已加载';
    } catch(_) {
      node.classList.remove('mapbox-active');
      node.innerHTML=drawRealGeometry(live);
      btn.disabled=false;btn.textContent='重试地图';
      showToast('地图加载失败，已保留道路示意线；不影响模拟模式');
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
    if (action === 'real') requestReal(id);
    if (action === 'map') openMap(r);
    if (action === 'edit') openDialog(r);
    if (action === 'delete') {
      if (!window.confirm('确认删除模拟路线「' + r.name + '」？')) return;
      state.routes = state.routes.filter(function (x) { return x.id !== id; });
      delete state.measured[id];
      delete state.liveReadings[id];
      delete state.liveErrors[id];
      persist();
      render();
      showToast('已删除模拟路线');
    }
  }
  function detectLiveAvailability() {
    fetch('/api/amap/status',{cache:'no-store'}).then(function(r) {
      if(!r.ok)throw Error('status');
      return r.json();
    }).then(function(x) {
      state.liveReady = x.live_enabled === true;
      if(!state.liveReady)state.liveAuto=false;
      state.mapEnabled = state.liveReady && x.js_map_enabled === true;
      state.mapKey = state.mapEnabled ? x.js_map_key : null;
      const label=document.getElementById('amap-status');
      const batchButton=document.getElementById('refresh-live-all');
      const autoWrap=document.getElementById('live-auto-wrap');
      const autoToggle=document.getElementById('live-auto-refresh');
      batchButton.hidden=!state.liveReady;
      autoWrap.hidden=!state.liveReady;
      autoToggle.checked=state.liveAuto;
      document.getElementById('amap-disable').hidden=!state.liveReady;
      document.getElementById('amap-auth-open').textContent=state.liveReady?'高德接入设置':'高德授权设置';
      label.textContent=state.liveReady ?
        ('高德真实接口已授权 · 今日剩余 '+x.remaining_app_budget+' 次 · 本月剩余 '+x.remaining_monthly_app_budget+
         ' 次 · 地图初始化今日/本月剩余 '+x.remaining_map_initializations+'/'+x.remaining_monthly_map_initializations+
         ' 次 · 未配置坐标路线仍为模拟') :
        '高德实时接口：未授权启用 · 当前仅显示模拟数据';
      if(state.liveReady) {
        document.querySelector('.mock-flag').textContent='高德接入已就绪 · 未查询路线为模拟';
        document.querySelector('footer span:last-child').textContent=
          'M1-B · 高德手动/可选自动刷新 · 地图按需加载';
      } else {
        document.querySelector('.mock-flag').textContent='模拟模式 · 非真实路况';
      }
      render();
    }).catch(function() {
      state.liveReady=false;
      state.mapEnabled=false;
      state.mapKey=null;
      state.liveAuto=false;
      document.getElementById('refresh-live-all').hidden=true;
      document.getElementById('live-auto-wrap').hidden=true;
      document.getElementById('amap-disable').hidden=true;
      document.getElementById('amap-auth-open').textContent='高德授权设置';
      document.getElementById('amap-status').textContent='高德接口状态不可用 · 保持模拟模式';
      document.querySelector('.mock-flag').textContent='模拟模式 · 非真实路况';
      render();
    });
  }

  async function submitAmapAuthorization(event) {
    event.preventDefault();
    const f=amapAuthForm.elements;
    const payload={
      ticket_id:f.namedItem('ticket_id').value.trim(),
      route_quota_remaining:Number(f.namedItem('route_quota_remaining').value),
      map_quota_remaining:Number(f.namedItem('map_quota_remaining').value),
      personal_developer_verified:f.namedItem('personal_developer_verified').checked,
      approved_by_amap:f.namedItem('approved_by_amap').checked,
      quota_verified:f.namedItem('quota_verified').checked,
      account_exclusive:f.namedItem('account_exclusive').checked,
      zero_cost_ack:f.namedItem('zero_cost_ack').checked
    };
    const submit=amapAuthForm.querySelector('button[type="submit"]');
    submit.disabled=true;
    try {
      const response=await fetch('/api/amap/authorize',{method:'POST',
        headers:{'Content-Type':'application/json','X-MRM-Request':'1'},
        body:JSON.stringify(payload),cache:'no-store'});
      const result=await response.json();
      if(!response.ok)throw new Error(result.error||'高德授权设置失败');
      amapAuthDialog.close();
      showToast('本机授权与额度门禁已保存；真实查询现已可用');
      detectLiveAvailability();
    } catch(error) {
      showToast(String(error.message||'保存失败').slice(0,100));
    } finally {
      submit.disabled=false;
    }
  }
  async function disableAmap() {
    if(!window.confirm('停用后将立即停止新的高德路线查询和地图代理请求。确定停用吗？'))return;
    try {
      const response=await fetch('/api/amap/disable',{method:'POST',
        headers:{'Content-Type':'application/json','X-MRM-Request':'1'},
        body:JSON.stringify({}),cache:'no-store'});
      const result=await response.json();
      if(!response.ok)throw new Error(result.error||'停用失败');
      state.liveAuto=false;
      setupTimer();
      showToast('高德真实接口已停用，页面恢复模拟模式');
      detectLiveAvailability();
    } catch(error) {
      showToast(String(error.message||'停用失败').slice(0,100));
    }
  }

  function init() {
    state.routes = Core.loadRoutes(getStorage(KEY_ROUTES));
    state.interval = Core.safeInterval(getStorage(KEY_INTERVAL));
    intervalSelect.value = String(state.interval);
    document.getElementById('add-route').addEventListener('click', function () {openDialog(null);});
    document.getElementById('amap-auth-open').addEventListener('click',function(){amapAuthDialog.showModal();});
    document.getElementById('amap-auth-close').addEventListener('click',function(){amapAuthDialog.close();});
    document.getElementById('amap-auth-cancel').addEventListener('click',function(){amapAuthDialog.close();});
    amapAuthDialog.addEventListener('click',function(e){if(e.target===amapAuthDialog)amapAuthDialog.close();});
    amapAuthForm.addEventListener('submit',submitAmapAuthorization);
    document.getElementById('amap-disable').addEventListener('click',disableAmap);
    document.getElementById('refresh-all').addEventListener('click', function () {refreshAll(false);});
    document.getElementById('refresh-live-all').addEventListener('click', function () {refreshLiveAll(false);});
    document.getElementById('live-auto-refresh').addEventListener('change', function(e) {
      state.liveAuto=!!e.target.checked && state.liveReady;
      setupTimer();
      showToast(state.liveAuto?'已开启高德真实路况自动刷新；将按所选间隔逐条查询':'已关闭高德真实路况自动刷新');
    });
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
    detectLiveAvailability();
    setInterval(ticker,1000);
  }
  init();
})();
