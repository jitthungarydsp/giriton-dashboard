// Run with the bundled Node runtime (20+) and Playwright/Edge available.
const {chromium} = require('playwright');
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');

(async()=>{
  const source=fs.readFileSync(path.join(__dirname,'../pwa/app.js'),'utf8');
  const helpers=source.slice(source.indexOf('function settlementDashboardEditorRows('),source.indexOf('function settlementDashboardComplaintManager('));
  const handlers=source.slice(source.indexOf('$("#settlement-dashboard-panel")?.addEventListener("input"'),source.indexOf('  const filter = event.target.closest',source.indexOf('$("#settlement-dashboard-panel")?.addEventListener("input"')))+'});';
  const setup=`
    const state={settlementDashboardExpandedCourierId:'12345',settlementDashboardMonth:'2026-09',settlementDashboardEditCourierId:'12345',settlementDashboardDetailCache:{}};
    const $=s=>document.querySelector(s);const escapeHtml=s=>String(s).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('"','&quot;');
    const formatCount=String;const formatHuf=n=>new Intl.NumberFormat('hu-HU').format(n)+' Ft';const previousLocalMonth=()=> '2026-09';
    const pilot={courierId:'12345',courierName:'Bagoly Zoltán',month:'2026-09',snapshotId:'original',version:10,savedTotal:0,rows:[{key:'base',label:'Alapdíj',amountHuf:0,amountKind:'huf'}],manualRows:[],existingManualRows:[]};
    const workflow={worksheetPilot:pilot,editableFinanceRows:pilot.rows,financialBreakdown:{totalPayableHuf:0}};
    const calls=[];window.calls=calls;
    async function api(url,options){const payload=JSON.parse(options.body);calls.push({url,payload});
      if(url.endsWith('/commit')){pilot.snapshotId='saved';pilot.version=11;pilot.savedTotal=10500;pilot.rows=payload.rows.map(r=>({...r,label:'Alapdíj',amountKind:'huf'}));pilot.manualRows=payload.manualRows;return {ok:true,version:11};}
      return {previewHash:'verified',totals:{payable_total:10500},delta:10500,tig:{finalTotalHuf:10500,cashGrossHuf:0},changes:[{label:'Alapdíj',before:0,after:10000}]};
    }
    async function loadSettlementDashboard(){}async function loadSettlementDashboardCourierDetail(){renderSettlementDashboard();}
    function renderSettlementDashboard(){document.getElementById('settlement-dashboard-panel').innerHTML=settlementDashboardFinanceEditor(workflow);}
    window.switchToOther=()=>{state.settlementDashboardExpandedCourierId='7767';state.settlementDashboardMonth='2026-10';Object.assign(pilot,{courierId:'7767',courierName:'Kanyó Krisztián',month:'2026-10',snapshotId:'other-snapshot',manualRows:[]});renderSettlementDashboard();};
    window.mismatchTarget=()=>{state.settlementDashboardExpandedCourierId='6909';renderSettlementDashboard();};
    window.noDataMutation=()=>workflow.editableFinanceRows[0].amountHuf===0;
  `;
  const browser=await chromium.launch({headless:true,channel:'msedge'});
  try {
    const page=await browser.newPage({viewport:{width:780,height:1300}});
    const errors=[];page.on('pageerror',e=>errors.push(e.message));let network=0;page.on('request',()=>network++);
    const css=fs.readFileSync(path.join(__dirname,'../pwa/styles.css'),'utf8');
    await page.setContent('<html lang="hu"><style>'+css+'body{padding:20px}</style><div id="settlement-dashboard-panel"></div><script>'+setup+helpers+'renderSettlementDashboard();'+handlers+'</script>');
    await page.locator('[data-worksheet-key="base"]').fill('10000');
    await page.locator('[data-worksheet-note]').fill('Pilot szerkesztés');
    await page.locator('[data-dashboard-editor-add]').click();
    await page.locator('[data-manual-field="amountHuf"]').fill('500');
    await page.locator('[data-manual-field="note"]').fill('Bónusz teszt');
    await page.locator('[data-worksheet-preview]').click();
    await page.waitForFunction(()=>!document.querySelector('[data-worksheet-commit]').disabled);
    assert.match(await page.locator('[data-worksheet-total]').innerText(),/10\s*500/);
    assert.equal((await page.evaluate(()=>window.calls)).filter(c=>c.url.endsWith('/commit')).length,0);
    await page.locator('[data-manual-field="amountHuf"]').fill('600');
    assert.equal(await page.locator('[data-worksheet-commit]').isDisabled(),true);
    await page.locator('[data-manual-field="amountHuf"]').fill('500');
    await page.locator('[data-worksheet-preview]').click();
    await page.waitForFunction(()=>!document.querySelector('[data-worksheet-commit]').disabled);
    await page.locator('[data-worksheet-commit]').click();
    await page.waitForFunction(()=>document.querySelector('[data-worksheet-message]').textContent.includes('Mentve: v11'));
    const commits=(await page.evaluate(()=>window.calls)).filter(c=>c.url.endsWith('/commit'));
    assert.equal(commits.length,1);assert.equal(commits[0].payload.courierId,'12345');assert.equal(commits[0].payload.month,'2026-09');
    assert.equal(commits[0].payload.snapshotId,'original');assert.equal(commits[0].payload.previewHash,'verified');
    assert.equal(await page.locator('[data-manual-id]').count(),1);
    assert.equal(await page.evaluate(()=>window.noDataMutation()),true);
    await page.setViewportSize({width:360,height:1300});
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
    await page.evaluate(()=>window.switchToOther());
    assert.equal(await page.locator('[data-pilot-worksheet]').count(),1);
    assert.match(await page.locator('.settlement-dashboard-editor-head').first().innerText(),/Kanyó Krisztián/);
    await page.locator('[data-dashboard-editor-add]').click();
    assert.equal(await page.locator('[data-manual-field="validFrom"]').inputValue(),'2026-10-01');
    assert.equal(await page.locator('[data-manual-field="validTo"]').inputValue(),'2026-10-31');
    await page.locator('[data-manual-field="note"]').fill('Másik futár októberi tétele');
    await page.locator('[data-worksheet-note]').fill('Októberi szerkesztés');
    await page.locator('[data-worksheet-preview]').click();
    await page.waitForFunction(()=>!document.querySelector('[data-worksheet-commit]').disabled);
    await page.locator('[data-worksheet-commit]').click();
    await page.waitForFunction(()=>window.calls.filter(c=>c.url.endsWith('/commit')).length===2);
    const last=(await page.evaluate(()=>window.calls)).filter(c=>c.url.endsWith('/commit')).at(-1);
    assert.equal(last.payload.courierId,'7767');assert.equal(last.payload.month,'2026-10');assert.equal(last.payload.snapshotId,'other-snapshot');
    await page.evaluate(()=>window.mismatchTarget());
    assert.equal(await page.locator('[data-pilot-worksheet]').count(),0);
    assert.equal(network,0);assert.deepEqual(errors,[]);
    console.log('Worksheet UI passed: multiple couriers/months, current values, date bounds, preview invalidation, scoped commits, reload, mobile and stale-target protection.');
  } finally { await browser.close(); }
})().catch(e=>{console.error(e);process.exitCode=1;});
