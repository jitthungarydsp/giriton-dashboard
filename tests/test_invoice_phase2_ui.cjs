const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const root=path.join(__dirname,'..');
const runtime=path.join(require('node:os').homedir(),'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
async function setup(browser){
 const page=await browser.newPage({viewport:{width:390,height:844}});const errors=[];page.on('pageerror',error=>errors.push(error.message));
 const rows=['a','b','c'].map((name,i)=>({id:crypto.randomUUID(),source_file_name:`${name}.xlsx`,session_id:`JITT_2026_09_${100000+i}`,settlement_month:'2026-09-01',sheet_count:2,raw_row_count:2,status:'saved',created_at:'2026-11-02T10:00:00Z'}));
 const calls=[];let working=null,failSave=false;
 await page.route('http://localhost/',route=>route.fulfill({contentType:'text/html',body:`<meta name="viewport" content="width=device-width,initial-scale=1"><style>${fs.readFileSync(path.join(root,'pwa/styles.css'),'utf8')}</style><main class="app-shell"><section class="card"><div id="raw"></div></section></main>`}));
 await page.goto('http://localhost/');
 await page.exposeFunction('fakeApi',async req=>{
  calls.push(req);assert.ok(req.url.startsWith('/api/admin/pwa-invoice/'));assert.ok(!req.url.includes('settlement-imports'));
  const url=new URL(req.url,'http://localhost');
  if(req.method==='GET'&&url.pathname.endsWith('/raw'))return {items:rows.filter(row=>!row.deleted),hasMore:false};
  if(url.pathname.endsWith('/working')){
   if(req.method==='POST'){
    if(failSave)return {error:'A hónap munkapéldánya közben megváltozott.'};
    assert.equal(req.data.expected_id,working?.id||null);
    const source=rows.find(row=>row.id===req.data.source_id);
    working={...source,id:req.data.request_id,session_id:`WORK_${req.data.request_id}`,source_upload_id:source.id,source_session_id:source.session_id};
   }
   const data=working?structuredClone(working):null;
   if(data&&url.searchParams.has('working_id')){
    assert.equal(url.searchParams.get('working_id'),data.id);
    data.sheets=[{name:'Adatok-JITT',rowCount:2},{name:'Üres-KIFLI',rowCount:0}];
    if(url.searchParams.has('sheet'))data.preview={sheet:url.searchParams.get('sheet'),rows:[{sourceRowNo:2,cells:[{column:1,type:'s',value:'Ádám'},{column:2,type:'n',value:5000}]}],hasMore:false};
   }
   return {ok:true,working:data};
  }
  if(url.pathname.endsWith('/compare'))return {ok:true,primaryId:req.data.primary_id,comparisons:req.data.selected_ids.filter(id=>id!==req.data.primary_id).map(id=>({uploadId:id,fileName:rows.find(row=>row.id===id).source_file_name,sheets:[{name:'Adatok-JITT',status:'changed',identicalRows:1,changedRows:1,removedRows:0,addedRows:0,movedRows:0,total:1,warning:'Javasolt párosítás – ellenőrizendő',changes:[{kind:'changed',beforeRow:2,afterRow:2,match:'suggested',cells:[{columnName:'B',before:{value:5000,type:'n'},after:{value:6000,type:'n'},delta:'1000'}]}]}]}))};
  if(url.pathname.endsWith('/delete')){for(const row of rows)if(req.data.selected_ids.includes(row.id))row.deleted=true;return {ok:true,deletedCount:req.data.selected_ids.length};}
  throw Error('Unexpected endpoint');
 });
 await page.addScriptTag({path:path.join(root,'pwa/invoice_raw.js')});
 await page.evaluate(()=>{
  JittInvoiceRaw.mount({target:document.querySelector('#raw'),initialMonth:'2026-09',escapeHtml:s=>String(s).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;'),formatCount:String,formatMonthLabel:String,
    api:async(url,options={})=>{const result=await fakeApi({url,method:options.method||'GET',data:options.body?JSON.parse(options.body):null});if(result.error)throw Error(result.error);return result;}});JittInvoiceRaw.show();
 });
 await page.locator('[data-invoice-raw-action="next"]').click();await page.locator('[data-invoice-row]').first().waitFor();
 return {page,rows,calls,errors,fail:()=>{failSave=true;}};
}

test('one file skips comparison; several compare, preserve selection on back, switch primary and replace only after confirmation',{skip:!fs.existsSync(runtime)},async()=>{
 const browser=await require(runtime).chromium.launch({channel:'chrome',headless:true});
 try{
  const {page,rows,calls,errors}=await setup(browser);
  assert.equal(await page.locator('[data-invoice-raw-action="proceed"]').isDisabled(),true);
  await page.locator('[data-invoice-check]').first().check();
  assert.equal(await page.locator('.invoice-primary').count(),1);
  await page.locator('[data-invoice-raw-action="proceed"]').click();
  await page.getByText('A hónap aktív munkapéldánya',{exact:true}).waitFor();
  await page.locator('.invoice-preview-row').waitFor();
  assert.equal(calls.filter(req=>req.url.endsWith('/compare')).length,0);
  assert.equal(calls.filter(req=>req.url.endsWith('/working')&&req.method==='POST').length,1);
  await page.locator('[data-invoice-raw-action="work-back"]').click();
  await page.locator('[data-invoice-check]').nth(1).check();await page.locator('[data-invoice-check]').nth(2).check();
  await page.locator('[data-invoice-raw-action="proceed"]').click();
  await page.locator('.invoice-diff-file').first().waitFor();assert.equal(await page.locator('.invoice-diff-file').count(),2);
  await page.locator(`[data-invoice-primary="${rows[2].id}"]`).click();
  await page.waitForFunction(()=>document.querySelectorAll('.invoice-diff-file').length===2 && !document.querySelector('[data-invoice-raw-action="prepare"]').disabled);
  assert.equal(calls.filter(req=>req.url.endsWith('/compare')).at(-1).data.primary_id,rows[2].id);
  await page.locator('[data-invoice-detail]').first().click();await page.locator('.invoice-cell-diff').waitFor();
  assert.match(await page.locator('.invoice-before').textContent(),/5000/);assert.match(await page.locator('.invoice-after').textContent(),/6000/);
  await page.locator('[data-invoice-key-columns]').fill('A,C');await page.locator('[data-invoice-raw-action="apply-keys"]').click();
  await page.waitForFunction(()=>!document.querySelector('[data-invoice-raw-action="prepare"]').disabled);
  assert.deepEqual(calls.filter(req=>req.url.endsWith('/compare')).at(-1).data.key_columns['Adatok-JITT'],[1,3]);
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),true,JSON.stringify(await page.evaluate(()=>[...document.querySelectorAll('*')].filter(el=>el.getBoundingClientRect().right>innerWidth+1).map(el=>({tag:el.tagName,cls:el.className,width:el.getBoundingClientRect().width})).slice(0,15))));
  if(process.env.INVOICE_PHASE2_SCREENSHOT)await page.screenshot({path:process.env.INVOICE_PHASE2_SCREENSHOT,fullPage:true});
  await page.setViewportSize({width:360,height:800});
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),true);
  await page.setViewportSize({width:1440,height:1000});
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),true);
  if(process.env.INVOICE_PHASE2_SCREENSHOT)await page.screenshot({path:process.env.INVOICE_PHASE2_SCREENSHOT.replace('-mobile','-desktop'),fullPage:true});
  await page.locator('[data-invoice-raw-action="compare-back"]').click();assert.equal(await page.locator('[data-invoice-check]:checked').count(),3);
  await page.locator('[data-invoice-raw-action="proceed"]').click();await page.locator('.invoice-diff-file').first().waitFor();
  await page.locator('[data-invoice-raw-action="prepare"]').click();await page.locator('.invoice-confirm-dialog[open]').waitFor();
  await page.locator('[data-cancel]').click();assert.equal(calls.filter(req=>req.url.endsWith('/working')&&req.method==='POST').length,1);
  await page.locator('[data-invoice-raw-action="prepare"]').click();await page.locator('[data-confirm]').click();
  await page.locator('.invoice-preview-row').waitFor();
  assert.equal(calls.filter(req=>req.url.endsWith('/working')&&req.method==='POST').length,2);
  assert.equal(calls.filter(req=>req.url.endsWith('/working')&&req.method==='POST').at(-1).data.source_id,rows[2].id);
  assert.deepEqual(errors,[]);
 }finally{await browser.close();}
});

test('cancelled deletion does nothing; confirmed deletion removes only selected uploads; failed copy never enters step 3',{skip:!fs.existsSync(runtime)},async()=>{
 const browser=await require(runtime).chromium.launch({channel:'chrome',headless:true});
 try{
  const {page,rows,calls,errors,fail}=await setup(browser);
  await page.locator('[data-invoice-check]').nth(1).check();
  await page.locator('[data-invoice-raw-action="delete"]').click();await page.locator('[data-cancel]').click();
  assert.equal(calls.filter(req=>req.url.endsWith('/delete')).length,0);
  await page.locator('[data-invoice-raw-action="delete"]').click();await page.locator('[data-confirm]').click();
  await page.waitForFunction(()=>document.querySelectorAll('[data-invoice-row]').length===2);
  assert.deepEqual(calls.find(req=>req.url.endsWith('/delete')).data.selected_ids,[rows[1].id]);
  await page.locator('[data-invoice-check]').first().check();fail();
  await page.locator('[data-invoice-raw-action="proceed"]').click();
  await page.getByText('A hónap munkapéldánya közben megváltozott.',{exact:true}).waitFor();
  assert.equal(await page.getByText('A hónap aktív munkapéldánya',{exact:true}).count(),0);
  assert.deepEqual(errors,[]);
 }finally{await browser.close();}
});
