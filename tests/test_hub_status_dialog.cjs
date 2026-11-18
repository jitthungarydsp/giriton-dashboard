const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {chromium}=require('playwright');
(async()=>{
  const root=path.join(__dirname,'..');
  const html=fs.readFileSync(path.join(root,'jitt_hub/index.html'),'utf8');
  const inlineStyle=html.match(/<style>([\s\S]*?)<\/style>/)[1];
  const dialog=html.match(/<dialog[\s\S]*?<\/dialog>/)[0];
  const browser=await chromium.launch({headless:true,channel:'msedge'});
  try{
    const page=await browser.newPage({viewport:{width:1400,height:1000}});
    page.setDefaultTimeout(7000);
    const errors=[];page.on('pageerror',e=>errors.push(e.message));
    const payload={courier:{id:'8863',name:'Vidák Krisztofer'},periodStart:'2026-10-01',
      finance:{payable:295990},documents:[{id:'invoice-1',document_type:'invoice',file_name:'Szamla.pdf',uploaded_at:'2026-11-17T13:00:00Z'}],
      complaints:[{document_type:'invoice_check',status:'new',message:'Teszt számlaeltérés',created_at:'2026-11-17T12:00:00Z'}],
      workflowStates:{invoice_check:{status:'open',updated_at:'2026-11-17T13:00:00Z',status_note:'Ellenőrzés szükséges'},invoice_payment:{status:'open'}},sources:[]};
    payload.payment={snapshotId:'00000000-0000-0000-0000-000000000001',snapshotVersion:3,amountHuf:295990,recipientName:'Teszt EV',bankAccount:'11111111-22222222-33333333',invoiceNumber:'TESZT-24',paymentNote:'8863-TESZT-24',closed:false,canClose:true,blockingReasons:[],
      transfer:{expectedHuf:295990,actualHuf:295990,differenceHuf:0,result:'match',document:payload.documents[0],check:{status:'done',updated_at:'2026-11-17T13:05:00Z',updated_by:'Teszt Admin'}},
      cash:{expectedHuf:34656,actualHuf:34656,differenceHuf:0,result:'match',document:{id:'cash-1',document_type:'invoice',title:'KP számla TESZT-KP-08',uploaded_at:'2026-11-17T13:00:00Z'}},
      tigBreakdown:{rows:[{label:'Szolgáltatás',netHuf:295990,vatHuf:0,grossHuf:295990}]},events:[{at:'2026-11-17T13:05:00Z',label:'Számlaellenőrzés · Kész',actor:'Teszt Admin',detail:'<img src=x onerror=alert(1)>',kind:'current_state'}]};
    const setup=`const $=s=>document.querySelector(s);const nf=new Intl.NumberFormat('hu-HU');
      const esc=s=>String(s??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('"','&quot;');
      const huf=v=>nf.format(v)+' Ft';const hours=String;const monthLabel=String;
      const data={couriers:[{courierId:'8863',courierName:'Vidák Krisztofer'}]};
      window.calls=[];window.payload=${JSON.stringify(payload)};window.fail=false;
      window.writes=[];window.bankWrites=[];
      const api=async (url,options={})=>{calls.push(url);if(window.fail)throw Error('Teszt kapcsolat');if(options.method==='POST'&&url==='/api/courier360-bank-account'){const value=JSON.parse(options.body);bankWrites.push(value);await new Promise(resolve=>setTimeout(resolve,50));window.payload.payment.bankAccount=value.bankAccount;window.payload.payment.blockingReasons=[];window.payload.payment.canClose=true;return {ok:true};}if(options.method==='POST'){writes.push(JSON.parse(options.body));await new Promise(resolve=>setTimeout(resolve,50));window.payload.payment.closed=true;window.payload.payment.closedAt='2026-11-18T12:00:00Z';window.payload.payment.closedBy='Teszt Admin';return {ok:true};}return structuredClone(window.payload)};
      window.rowClicks=0;`;
    const script=fs.readFileSync(path.join(root,'jitt_hub/status-dialog.js'),'utf8');
    const c360=fs.readFileSync(path.join(root,'jitt_hub/courier360.js'),'utf8');
    const c360Helpers=c360.slice(c360.indexOf('function c360Date'),c360.indexOf('function c360Go'));
    const complaintFn=c360.slice(c360.indexOf('function c360Complaints'),c360.indexOf('function c360Logs'));
    await page.setContent(`<style>${inlineStyle}${fs.readFileSync(path.join(root,'jitt_hub/courier360.css'),'utf8')}${fs.readFileSync(path.join(root,'jitt_hub/status-dialog.css'),'utf8')}</style>
      <select id="month"><option>2026-10</option></select><div id="row" onclick="rowClicks++"><button class="status status-button Reklamáció" data-status-courier="8863" data-status-label="Reklamáció">Reklamáció</button>
      <button class="status status-button" data-status-courier="8863" data-status-label="Számla ellenőrzésre vár">Számla ellenőrzésre vár</button>
      <button class="status status-button" data-status-courier="8863" data-status-label="Kifizetésre vár">Kifizetésre vár</button></div>${dialog}<script>${setup}${c360Helpers}${complaintFn}${script}</script>`);
    const modal=page.locator('dialog');
    await page.getByRole('button',{name:'Reklamáció',exact:true}).click();
    await modal.locator('#status-panel-complaints').getByText('Teszt számlaeltérés',{exact:true}).waitFor();
    assert.equal(await modal.evaluate(d=>d.open),true);
    assert.equal(await page.evaluate(()=>rowClicks),0,'Status click must not rerender the list');
    assert.equal(await page.locator('.status.Reklamáció').evaluate(e=>getComputedStyle(e).color),'rgb(180, 35, 50)');
    await page.keyboard.press('Escape');assert.equal(await modal.evaluate(d=>d.open),false);
    await page.getByRole('button',{name:'Számla ellenőrzésre vár',exact:true}).click();
    await modal.locator('#status-panel-payment').getByRole('link',{name:'Szamla.pdf ↗',exact:true}).waitFor();
    assert.match(await modal.locator('a').first().getAttribute('href'),/courier=8863&id=invoice-1/);
    await page.getByRole('button',{name:'Ablak bezárása'}).click();
    await page.getByRole('button',{name:'Kifizetésre vár',exact:true}).click();
    await modal.getByText('Kifizetendő a havi pénzügyi mentés szerint').waitFor();
    assert.match(await modal.textContent(),/295.?990 Ft/);
    assert.equal(await modal.locator('.payment-invoice').count(),2);
    assert.equal(await modal.locator('.payment-match.match').count(),2);
    await modal.getByRole('tab',{name:/Előzmények/}).click();
    await modal.getByText('Utolsó állapotmódosítás',{exact:true}).waitFor();
    assert.equal(await modal.locator('.payment-timeline img').count(),0,'Audit content must be escaped');
    await page.keyboard.press('ArrowLeft');
    assert.equal(await modal.getByRole('tab',{name:'Ellenőrzés és utalás'}).getAttribute('aria-selected'),'true');
    await modal.getByText('Teljesítésigazolás részletei',{exact:true}).click();
    await modal.getByText('Szolgáltatás',{exact:true}).waitFor();
    await page.screenshot({path:path.join(root,'tmp/payment-dialog-desktop.png')});
    await modal.getByRole('button',{name:'Kifizetés rögzítése',exact:true}).click();
    await modal.getByRole('button',{name:'Mégse',exact:true}).click();
    assert.equal(await page.evaluate(()=>writes.length),0,'Opening and cancelling must not write');
    await modal.getByRole('button',{name:'Kifizetés rögzítése',exact:true}).click();
    await modal.getByLabel('Lezárási megjegyzés (kötelező, az összeggel)').fill('Kifizetve: 295 990 Ft; banki hivatkozás: TESZT');
    await modal.locator('.payment-record-form').evaluate(form=>{form.requestSubmit();form.requestSubmit()});
    await modal.getByText('✓ Kifizetve',{exact:true}).waitFor();
    assert.equal(await page.evaluate(()=>writes.length),1,'Duplicate submit must be ignored');
    assert.equal((await page.evaluate(()=>writes[0])).snapshotId,payload.payment.snapshotId);
    await page.setViewportSize({width:390,height:844});
    assert(await modal.evaluate(el=>el.scrollWidth<=el.clientWidth+1),'Payment view must fit mobile width');
    await page.screenshot({path:path.join(root,'tmp/status-dialog-preview.png')});
    await page.getByRole('button',{name:'Ablak bezárása'}).click();
    await page.evaluate(()=>{Object.assign(payload.payment,{bankAccount:'',amountHuf:null,canClose:false,closed:false,blockingReasons:['Hiányzik a bankszámlaszám.'],transfer:{expectedHuf:null,actualHuf:null,result:'unknown'},cash:{expectedHuf:null,actualHuf:null,result:'unknown'}})});
    await page.getByRole('button',{name:'Kifizetésre vár',exact:true}).click();
    await modal.getByText('Hiányzik a bankszámlaszám.',{exact:true}).waitFor();
    assert.equal(await modal.getByText('Nincs mentett bontás',{exact:true}).count(),2);
    assert.equal(await modal.locator('.payment-match.match').count(),0);
    assert.equal(await modal.getByRole('button',{name:'Kifizetés rögzítése',exact:true}).isDisabled(),true);
    await modal.getByLabel('Hiányzó bankszámlaszám megadása').fill('11111111-22222222-33333333');
    await modal.locator('.payment-bank-form').evaluate(form=>{form.requestSubmit();form.requestSubmit()});
    await modal.getByText('Bankszámlaszám mentve. A kifizetési feltételeket újra ellenőriztük.',{exact:true}).waitFor();
    assert.equal(await page.evaluate(()=>bankWrites.length),1);
    assert.equal(await page.evaluate(()=>writes.length),1,'Bank save must not record a payment');
    assert.equal(await modal.locator('.payment-bank-form').count(),0);
    assert.equal(await modal.getByRole('button',{name:'Kifizetés rögzítése',exact:true}).isEnabled(),true);
    await page.getByRole('button',{name:'Ablak bezárása'}).click();
    await page.evaluate(()=>window.fail=true);
    await page.getByRole('button',{name:'Reklamáció',exact:true}).click();
    await modal.getByRole('alert').waitFor();
    await page.evaluate(()=>window.fail=false);
    await modal.getByRole('button',{name:'Újrapróbálás'}).click();
    await modal.locator('#status-panel-complaints').getByText('Teszt számlaeltérés',{exact:true}).waitFor();
    assert((await page.evaluate(()=>calls)).filter(u=>!['/api/courier360-payment-close','/api/courier360-bank-account'].includes(u)).every(u=>u.includes('courier=8863')&&u.includes('month=2026-10')));
    assert.deepEqual(errors,[]);
    console.log('Status modal: complaint, invoice, payment, month/identity, Escape, close, retry, row isolation and red status verified');
  }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
