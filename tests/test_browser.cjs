/* Chromium smoke/E2E: real Python local server, no provider networking. */
'use strict';
const assert = require('node:assert/strict');
const {spawn} = require('node:child_process');
const net = require('node:net');
const path = require('node:path');
const {chromium} = require('playwright');
async function freePort() {
  return new Promise((resolve,reject)=>{
    const s=net.createServer();s.on('error',reject);
    s.listen(0,'127.0.0.1',()=>{const p=s.address().port;s.close(()=>resolve(p));});
  });
}
async function waitServer(origin) {
  for(let i=0;i<60;i++){
    try {const r=await fetch(origin+'/api/status'); if(r.ok)return;}catch(_){}
    await new Promise(r=>setTimeout(r,150));
  }
  throw Error('Local server startup timed out');
}
async function main() {
  const port=await freePort(), origin='http://127.0.0.1:'+port;
  const py=process.env.PYTHON || (process.platform==='win32' ? 'python' : 'python3');
  const child=spawn(py,['app.py','--port',String(port)],{cwd:path.resolve(__dirname,'..'),stdio:'pipe'});
  let browser;
  try {
    await waitServer(origin);
    browser=await chromium.launch({headless:true});
    const page=await browser.newPage({viewport:{width:1440,height:900}});
    const external=[];
    page.on('request', req=>{if(!req.url().startsWith(origin+'/'))external.push(req.url());});
    await page.goto(origin+'/',{waitUntil:'networkidle'});
    assert.equal(await page.locator('.summary').count(),0,'no redundant statistics section');
    assert.equal(await page.locator('.summary-tile').count(),0);
    assert.equal(await page.locator('#stat-count, #stat-avg, #stat-congested').count(),0);
    assert.equal(await page.locator('#route-count-pill').innerText(),'04');
    const top = await page.locator('.route-card').first().boundingBox();
    assert.ok(top && top.y < 390,'route cards should be prioritized above the fold');
    assert.equal(await page.locator('.route-card').count(),4);
    assert.match(await page.locator('.mock-flag').innerText(),/模拟模式/);
    assert.match(await page.locator('.intro').innerText(),/虚构模拟/);
    assert.equal(await page.locator('.sim-chip').count(),4);
    assert.equal(await page.locator('.schematic svg').count(),4);

    await page.getByRole('button',{name:'刷新全部'}).click();
    assert.match(await page.locator('#toast').innerText(),/已刷新 4 条模拟路线/);

    await page.getByRole('button',{name:'添加路线'}).click();
    await page.locator('[name=name]').fill('<img src=x onerror=alert(1)>');
    await page.locator('[name=origin]').fill('虚构地点甲');
    await page.locator('[name=destination]').fill('虚构地点乙');
    await page.locator('[name=base_minutes]').fill('31');
    await page.locator('#dialog-save').click();
    assert.equal(await page.locator('.route-card').count(),5);
    assert.equal(await page.locator('img').count(),0,'HTML user input must be escaped');
    assert.match(await page.locator('.route-card').last().innerText(),/<img src=x/);

    await page.reload({waitUntil:'networkidle'});
    assert.equal(await page.locator('.route-card').count(),5,'route settings should persist');
    await page.locator('.route-card').last().getByRole('button',{name:/编辑/}).click();
    await page.locator('[name=name]').fill('本地配置测试');
    await page.locator('#dialog-save').click();
    assert.match(await page.locator('.route-card').last().innerText(),/本地配置测试/);

    await page.locator('#refresh-interval').selectOption('5');
    assert.equal(await page.locator('#refresh-interval').inputValue(),'5');
    await page.locator('#pause-toggle').click();
    assert.equal(await page.locator('#pause-toggle').getAttribute('aria-pressed'),'true');
    await page.locator('#pause-toggle').click();
    await page.reload();
    assert.equal(await page.locator('#refresh-interval').inputValue(),'5');

    page.once('dialog', d=>d.accept());
    await page.locator('.route-card').last().getByRole('button',{name:/删除/}).click();
    assert.equal(await page.locator('.route-card').count(),4);
    assert.deepEqual(external,[],'mock-only page must not fetch external assets/API');

    await page.setViewportSize({width:390,height:844});
    await page.reload();
    assert.equal(await page.locator('.route-card').count(),4);
    const width=await page.evaluate(()=>document.documentElement.scrollWidth);
    assert.ok(width<=390,'mobile view should not have horizontal overflow: '+width);
    // Intercept browser traffic in local Chromium: never contact the real provider.
    const localLive=await browser.newPage({viewport:{width:1440,height:900}});
    let realCalls=0;
    await localLive.route('**/api/amap/status',r=>r.fulfill({
      status:200,contentType:'application/json',
      body:JSON.stringify({live_enabled:true,mode:'live_ready',remaining_app_budget:3,
        remaining_monthly_app_budget:30,js_map_enabled:false})
    }));
    await localLive.route('**/api/amap/drive',r=>{
      realCalls+=1;
      const req=r.request().postDataJSON();
      assert.equal(req.origin,'116.1,39.9');
      assert.equal(req.destination,'116.2,39.91');
      return r.fulfill({status:200,contentType:'application/json',body:JSON.stringify({
        source:'AMAP',eta_minutes:23,distance_km:12.5,traffic_available:true,
        fetched_at:'2026-11-02T21:00:00+08:00',
        segments:[
          {status:'畅通',points:[[116.1,39.9],[116.15,39.905]]},
          {status:'拥堵',points:[[116.15,39.905],[116.2,39.91]]}
        ]
      })});
    });
    await localLive.goto(origin+'/',{waitUntil:'networkidle'});
    assert.equal(realCalls,0,'no automatic real queries even if backend is enabled');
    await localLive.getByRole('button',{name:'编辑示例路线 A'}).click();
    await localLive.locator('[name=origin_coord]').fill('116.1,39.9');
    await localLive.locator('[name=destination_coord]').fill('116.2,39.91');
    await localLive.locator('#dialog-save').click();
    await localLive.getByRole('button',{name:'高德查询全部'}).click();
    await localLive.locator('.route-card').first().locator('.sim-chip').getByText('AMAP').waitFor();
    const first=await localLive.locator('.route-card').first().innerText();
    assert.match(first,/23/);
    assert.match(first,/12.5 公里/);
    assert.match(first,/高德（单次查询）/);
    assert.equal(await localLive.locator('.route-card').first().locator('.real-geometry polyline').count(),2);
    assert.equal(realCalls,1);
    assert.equal(await localLive.locator('.route-card').nth(1).locator('.sim-chip').innerText(),'MOCK');
    await localLive.close();

    console.log('Browser E2E PASS: gated AMap HTTP fixture, no summary cards, prioritized routes, cards, labels, CRUD, XSS, persistence, pause, interval, mobile, zero external requests');
  } finally {
    if(browser) await browser.close();
    child.kill();
  }
}
main().catch(err=>{console.error(err);process.exitCode=1;});
