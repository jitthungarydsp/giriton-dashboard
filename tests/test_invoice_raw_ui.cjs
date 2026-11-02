const test=require('node:test');const assert=require('node:assert/strict');
const fs=require('node:fs');const path=require('node:path');const vm=require('node:vm');
const root=path.join(__dirname,'..');
const app=fs.readFileSync(path.join(root,'pwa/app.js'),'utf8');
test('upload entrypoint mounts only Phase 1 and fails closed if its module is missing',()=>{
 const source=app.slice(app.indexOf('function renderSettlementImportConfig()'),app.indexOf('function renderLegacySettlementImportConfig()'));
 let mounted=0,shown=0;const target={innerHTML:''};
 const ctx={window:{JittInvoiceRaw:{mount:()=>mounted++,show:()=>shown++}},$:()=>target,api:()=>{throw Error('legacy import must not run')},
  escapeHtml:String,formatCount:String,formatMonthLabel:String,state:{},previousLocalMonth:()=> '2026-09'};
 vm.runInNewContext(source,ctx);ctx.renderSettlementImportConfig();assert.equal(mounted,1);assert.equal(shown,1);
 delete ctx.window.JittInvoiceRaw;ctx.renderSettlementImportConfig();assert.ok(target.innerHTML.includes('nem töltődött be'));
});

const runtime=path.join(require('node:os').homedir(),'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
test('four workbooks, monthly listing, partial failure retry with same ID, no calculation and mobile layout',{skip:!fs.existsSync(runtime)},async()=>{
 const {chromium}=require(runtime);const browser=await chromium.launch({channel:'chrome',headless:true});
 try{
  const page=await browser.newPage({viewport:{width:390,height:844}});const errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  const rows=[{id:'old-october',session_id:'JITT_2026_10_111111',settlement_month:'2026-10-01',source_file_name:'October.xlsx',sheet_count:3,raw_row_count:20,status:'saved',created_at:'2026-11-02T09:00:00Z'}];
  const requests=[];let failOnce=true;
  await page.route('http://localhost/',route=>route.fulfill({contentType:'text/html',body:`<meta name="viewport" content="width=device-width,initial-scale=1"><style>${fs.readFileSync(path.join(root,'pwa/styles.css'),'utf8')}</style><main class="app-shell"><section class="card"><div id="raw"></div></section></main>`}));
  await page.goto('http://localhost/');
  await page.addScriptTag({path:path.join(root,'pwa/invoice_raw.js')});
  await page.exposeFunction('testApi',async request=>{
    requests.push(request);
    assert.ok(request.url.startsWith('/api/admin/pwa-invoice/raw'));
    if(request.method==='POST'){
      if(request.name==='c.xlsx' && failOnce){failOnce=false;return {error:'Hálózati hiba, próbáld újra.'};}
      let row=rows.find(row=>row.id===request.id);
      if(!row){row={id:request.id,session_id:`JITT_${request.month.replace('-','_')}_${100000+rows.length}`,settlement_month:`${request.month}-01`,source_file_name:request.name,sheet_count:10,raw_row_count:2300,status:'saved',created_at:'2026-11-02T10:00:00Z'};rows.unshift(row);}
      return {ok:true,upload:row};
    }
    const month=new URL(request.url,'http://localhost').searchParams.get('month');
    return {month,items:rows.filter(row=>row.settlement_month===`${month}-01`),hasMore:false};
  });
  await page.evaluate(()=>{
    JittInvoiceRaw.mount({target:document.querySelector('#raw'),initialMonth:'2026-09',escapeHtml:s=>String(s).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('"','&quot;'),formatCount:String,formatMonthLabel:String,
      api:async(url,options={})=>{
        const request={url,method:options.method||'GET'};
        if(options.body){request.id=options.body.get('request_id');request.month=options.body.get('month');request.name=options.body.get('excel_file').name;}
        const result=await testApi(request);if(result.error)throw Error(result.error);return result;
      }});JittInvoiceRaw.show();
  });
  await page.locator('[data-invoice-raw-action="next"]').click();
  await page.getByText('Ehhez a hónaphoz még nincs elmentett Excel.').waitFor();
  await page.locator('#invoice-raw-files').setInputFiles(['a.xlsx','b.xlsx','c.xlsx','d.xlsx'].map(name=>({name,mimeType:'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',buffer:Buffer.from('fixture')})));
  await page.locator('[data-invoice-raw-action="upload"]').click();
  await page.getByText(/RAW mentve: 3 fájl/).waitFor();
  assert.equal(await page.locator('.invoice-raw-table tbody tr').count(),3);
  assert.equal(await page.locator('.invoice-raw-queue > div').count(),1);
  assert.equal(await page.getByText('Excel fájlok feltöltése',{exact:true}).count(),1);
  assert.equal(requests.filter(r=>r.method==='POST').length,4);
  const firstFailedId=requests.find(r=>r.method==='POST'&&r.name==='c.xlsx').id;
  await page.locator('[data-invoice-raw-action="upload"]').click();
  await page.waitForFunction(()=>document.querySelectorAll('.invoice-raw-table tbody tr').length===4);
  assert.equal(requests.filter(r=>r.method==='POST'&&r.name==='c.xlsx').at(-1).id,firstFailedId);
  assert.equal(rows.length,5); // Four September workbooks and the separate October upload.
  assert.equal(await page.locator('.invoice-raw-queue > div').count(),0);
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+2),true);
  if(process.env.INVOICE_RAW_SCREENSHOT)await page.screenshot({path:process.env.INVOICE_RAW_SCREENSHOT,fullPage:true});
  await page.locator('[data-invoice-raw-action="back"]').click();
  await page.locator('#invoice-raw-month').fill('2026-10');
  await page.locator('[data-invoice-raw-action="next"]').click();
  await page.getByText('October.xlsx',{exact:true}).waitFor();
  assert.equal(await page.locator('.invoice-raw-table tbody tr').count(),1);
  assert.deepEqual(errors,[]);
 }finally{await browser.close()}
});
