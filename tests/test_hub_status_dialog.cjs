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
    const errors=[];page.on('pageerror',e=>errors.push(e.message));
    const payload={courier:{id:'8863',name:'Vidák Krisztofer'},periodStart:'2026-10-01',
      finance:{payable:295990},documents:[{id:'invoice-1',document_type:'invoice',file_name:'Szamla.pdf',uploaded_at:'2026-11-17T13:00:00Z'}],
      complaints:[{document_type:'invoice_check',status:'new',message:'Teszt számlaeltérés',created_at:'2026-11-17T12:00:00Z'}],
      workflowStates:{invoice_check:{status:'open',updated_at:'2026-11-17T13:00:00Z',status_note:'Ellenőrzés szükséges'},invoice_payment:{status:'open'}},sources:[]};
    const setup=`const $=s=>document.querySelector(s);const nf=new Intl.NumberFormat('hu-HU');
      const esc=s=>String(s??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('"','&quot;');
      const huf=v=>nf.format(v)+' Ft';const hours=String;const monthLabel=String;
      const data={couriers:[{courierId:'8863',courierName:'Vidák Krisztofer'}]};
      window.calls=[];window.payload=${JSON.stringify(payload)};window.fail=false;
      const api=async url=>{calls.push(url);if(window.fail)throw Error('Teszt kapcsolat');return structuredClone(window.payload)};
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
    await page.getByText('Teszt számlaeltérés',{exact:true}).waitFor({state:'attached'});
    assert.equal(await modal.evaluate(d=>d.open),true);
    assert.equal(await page.evaluate(()=>rowClicks),0,'Status click must not rerender the list');
    assert.equal(await page.locator('.status.Reklamáció').evaluate(e=>getComputedStyle(e).color),'rgb(180, 35, 50)');
    await page.keyboard.press('Escape');assert.equal(await modal.evaluate(d=>d.open),false);
    await page.getByRole('button',{name:'Számla ellenőrzésre vár',exact:true}).click();
    await modal.getByText('Szamla.pdf',{exact:true}).waitFor();
    assert.match(await modal.locator('a').first().getAttribute('href'),/courier=8863&id=invoice-1/);
    await page.getByRole('button',{name:'Ablak bezárása'}).click();
    await page.getByRole('button',{name:'Kifizetésre vár',exact:true}).click();
    await modal.getByText('Kifizetendő a havi pénzügyi mentés szerint').waitFor();
    assert.match(await modal.textContent(),/295.?990 Ft/);
    await page.screenshot({path:path.join(root,'tmp/status-dialog-preview.png')});
    await page.getByRole('button',{name:'Ablak bezárása'}).click();
    await page.evaluate(()=>window.fail=true);
    await page.getByRole('button',{name:'Reklamáció',exact:true}).click();
    await modal.getByRole('alert').waitFor();
    await page.evaluate(()=>window.fail=false);
    await modal.getByRole('button',{name:'Újrapróbálás'}).click();
    await modal.getByText('Teszt számlaeltérés',{exact:true}).waitFor({state:'attached'});
    assert((await page.evaluate(()=>calls)).every(u=>u.includes('courier=8863')&&u.includes('month=2026-10')));
    assert.deepEqual(errors,[]);
    console.log('Status modal: complaint, invoice, payment, month/identity, Escape, close, retry, row isolation and red status verified');
  }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
