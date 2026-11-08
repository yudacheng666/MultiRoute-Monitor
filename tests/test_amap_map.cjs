'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
const api=require('../web/amap_map.js');

test('map segments validate coordinates and never trust arbitrary traffic colors',()=>{
  const data=[{status:'畅通',points:[[116,39],[116.5,39.3]]},
    {status:'恶意状态',points:[[116,39],[116.5,39.3]]},
    {status:'拥堵',points:[['116',39],[117,40]]},
    {status:'缓行',points:[[999,40],[116,39]]}];
  const lines=api.validPoints(data);
  assert.equal(lines.length,2);
  assert.equal(lines[0].color,'#36b586');
  assert.equal(lines[1].color,'#9ba7b6');
});
test('official map overlays use provider geometry, not invented points',()=>{
  const instances=[];
  class FakeMap {
    constructor(container, opts){this.container=container;this.opts=opts;instances.push(this);}
    add(xs){this.lines=xs;}
    setFitView(xs){this.fit=xs;}
    destroy(){this.destroyed=true;}
  }
  class FakeLine {constructor(opts){Object.assign(this,opts);}}
  const map=api.draw({Map:FakeMap,Polyline:FakeLine},{node:true},[
    {status:'严重拥堵',points:[[116,39],[117,39.2]]}
  ]);
  assert.equal(instances.length,1);
  assert.equal(map.lines.length,1);
  assert.equal(map.lines[0].strokeColor,'#d94c5c');
  assert.deepEqual(map.lines[0].path,[[116,39],[117,39.2]]);
  assert.deepEqual(map.fit,map.lines);
});
test('invalid key cannot load any external script',async()=>{
  let used=0;
  const w={location:{origin:'http://127.0.0.1:8876'}};
  const d={createElement(){used++;return {};},head:{appendChild(){used++;}}};
  await assert.rejects(api.load('invalid key',w,d));
  assert.equal(used,0);
});

test('JS API loader sets the same-origin security proxy before appending the official script',async()=>{
  const events=[];
  const w={location:{origin:'http://127.0.0.1:8876'}};
  let script;
  const d={
    createElement(name){
      assert.equal(name,'script');
      script={async:false,onload:null,onerror:null,remove(){}};
      Object.defineProperty(script,'src',{
        set(value){this._src=value;events.push('src');},
        get(){return this._src;}
      });
      return script;
    },
    head:{appendChild(el){
      events.push('append');
      assert.deepEqual(w._AMapSecurityConfig,{
        serviceHost:'http://127.0.0.1:8876/_AMapService'
      });
      w.AMap={Map:function FakeMap(){}};
      el.onload();
    }}
  };
  const loaded=await api.load('PUBLIC_JS_KEY_123',w,d);
  assert.equal(loaded,w.AMap);
  assert.deepEqual(events,['src','append']);
  assert.match(script.src,/^https:\/\/webapi\.amap\.com\/maps\?v=2\.0&key=PUBLIC_JS_KEY_123$/);
  assert.equal(Object.hasOwn(w._AMapSecurityConfig,'securityJsCode'),false);
});
