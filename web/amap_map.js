/* Optional official AMap JS API overlay. Loaded ONLY after explicit user action.
   This never stores route responses or secret securityJsCode. */
(function (root, factory) {
  'use strict';
  const api = factory();
  if (root) root.AMapMap = api;
  if (typeof module === 'object' && module.exports) module.exports = api;
})(typeof window !== 'undefined' ? window : null, function () {
  'use strict';
  const COLORS = Object.freeze({
    '未知': '#9ba7b6',
    '畅通': '#36b586',
    '缓行': '#e8bd55',
    '拥堵': '#ed8b54',
    '严重拥堵': '#d94c5c',
  });
  let scriptPromise = null;
  const mounted = new Map();

  function validPoints(segments) {
    if (!Array.isArray(segments)) return [];
    return segments.slice(0, 500).map(function (item) {
      if (!item || !Array.isArray(item.points)) return null;
      const path = item.points.filter(function (p) {
        return Array.isArray(p) && p.length === 2 &&
          p.every(function (n) { return typeof n === 'number' && Number.isFinite(n); }) &&
          Math.abs(p[0]) <= 180 && Math.abs(p[1]) <= 90;
      }).slice(0, 1500);
      return path.length >= 2 ? {path:path,color:COLORS[item.status]||COLORS['未知']} : null;
    }).filter(Boolean);
  }

  function draw(AMap, container, segments) {
    if (!AMap || typeof AMap.Map !== 'function' || !container) throw Error('地图引擎不可用');
    const lines = validPoints(segments);
    if (!lines.length) throw Error('高德未提供可展示的线路');
    const map = new AMap.Map(container, {zoom: 12, viewMode: '2D', resizeEnable:true});
    const overlays = lines.map(function (segment) {
      return new AMap.Polyline({
        path:segment.path,strokeColor:segment.color,strokeWeight:6,
        strokeOpacity:0.92,strokeStyle:'solid',lineJoin:'round',lineCap:'round',
      });
    });
    map.add(overlays);
    map.setFitView(overlays,false,[12,12,12,12],16);
    return map;
  }

  function load(jsKey, w, d) {
    if (scriptPromise) return scriptPromise;
    if (typeof jsKey !== 'string' || !/^[a-zA-Z0-9_-]{8,80}$/.test(jsKey))
      return Promise.reject(Error('地图 JS Key 无效'));
    w._AMapSecurityConfig={serviceHost:w.location.origin+'/_AMapService'};
    scriptPromise=new Promise(function(resolve,reject){
      const s=d.createElement('script');
      let settled=false;
      const end=function(error){
        if(settled)return;
        settled=true;clearTimeout(timeout);
        if(error){s.remove();scriptPromise=null;reject(error);}
        else resolve(w.AMap);
      };
      const timeout=setTimeout(()=>end(Error('高德 JS API 加载超时')),12000);
      s.onload=function(){
        if(!w.AMap || typeof w.AMap.Map!=='function')end(Error('高德地图引擎初始化失败'));
        else end(null);
      };
      s.onerror=function(){end(Error('高德地图脚本加载失败'));};
      s.src='https://webapi.amap.com/maps?v=2.0&key='+encodeURIComponent(jsKey);
      s.async=true;
      d.head.appendChild(s);
    });
    return scriptPromise;
  }

  async function show(container, segments, jsKey, w, d) {
    w=w||(typeof window!=='undefined'?window:null);
    d=d||(typeof document!=='undefined'?document:null);
    if(!w||!d||!container||!container.isConnected)throw Error('地图容器不可用');
    const AMap=await load(jsKey,w,d);
    if(!container.isConnected)throw Error('路线窗口已关闭');
    if(mounted.has(container)) {
      try{mounted.get(container).destroy();}catch(_){}
      mounted.delete(container);
    }
    container.replaceChildren();
    const map=draw(AMap,container,segments);
    mounted.set(container,map);
    return map;
  }

  function destroyDetached() {
    for(const [container,map] of mounted) {
      if(!container.isConnected) {
        try{map.destroy();}catch(_){}
        mounted.delete(container);
      }
    }
  }

  return {validPoints:validPoints,draw:draw,load:load,show:show,destroyDetached:destroyDetached};
});
