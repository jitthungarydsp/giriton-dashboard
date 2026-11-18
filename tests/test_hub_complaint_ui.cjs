const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict'),{chromium}=require('playwright');
const root=path.join(__dirname,'..'),read=file=>fs.readFileSync(path.join(root,file),'utf8');
const html=read('jitt_hub/index.html'),dialog=html.match(/<dialog[\s\S]*?<\/dialog>/)[0],inlineStyle=html.match(/<style>([\s\S]*?)<\/style>/)[1];
const first='00000000-0000-0000-0000-000000000001',second='00000000-0000-0000-0000-000000000002';
(async()=>{
 const browser=await chromium.launch({headless:true,channel:'msedge'});
 try{
  const page=await browser.newPage({viewport:{width:1400,height:1100}});page.setDefaultTimeout(7000);const errors=[];page.on('pageerror',e=>errors.push(e.message));
  const fixture={courier:{id:'1234',name:'Teszt Futár'},periodStart:'2026-10-01',finance:{payable:831020},financeSnapshot:{id:'snapshot-11',version:11,items:[]},sources:[],documents:[],workflowStates:{},
   complaintNote:{note:'Belső megjegyzés',updated_by:'Admin',updated_at:'2026-11-18T10:00:00Z'},
   complaints:[{id:first,document_type:'settlement',status:'new',message:'Hiányzó bónusz <img src=x onerror=alert(1)>',created_by:'Teszt Futár',created_at:'2026-11-18T09:00:00Z'},
    {id:second,document_type:'invoice_check',status:'closed',message:'Második ügy',admin_response:'Korábbi ügy válasza',responded_at:'2026-11-18T08:00:00Z',responded_by:'Admin'}],
   financeComparison:{available:true,before:{version:10},after:{version:11},rows:[{label:'Bónusz',beforeHuf:0,afterHuf:31020,differenceHuf:31020}]}};
  const setup=`const $=s=>document.querySelector(s),nf=new Intl.NumberFormat('hu-HU'),huf=x=>nf.format(x)+' Ft',monthLabel=String;
   const esc=x=>String(x??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('"','&quot;');
   const data={couriers:[{courierId:'1234',courierName:'Teszt Futár'}]};window.fixture=${JSON.stringify(fixture)};window.writes=[];window.fail=false;
   const api=async(url,options={})=>{if(options.method==='POST'){const body=JSON.parse(options.body);writes.push(body);await new Promise(resolve=>setTimeout(resolve,40));if(fail)throw Error('Mentési hiba');const row=fixture.complaints.find(r=>r.id===body.complaintId);if(body.action==='start')row.status='in_progress';if(body.action==='close'){row.status='closed';row.admin_response=body.response;row.responded_at='2026-11-18T11:00:00Z';row.responded_by='Admin';}if(body.action==='reopen'){row.status='open';row.admin_response=null;row.responded_at=null;}if(body.action==='note')fixture.complaintNote.note=body.note;return {ok:true};}return structuredClone(fixture);};`;
  const c360=read('jitt_hub/courier360.js'),helpers=c360.slice(c360.indexOf('function c360Date'),c360.indexOf('function c360Go'));
  await page.setContent(`<style>${inlineStyle}${read('jitt_hub/courier360.css')}${read('jitt_hub/status-dialog.css')}</style><select id="month"><option>2026-10</option></select>${['Reklamáció','Számla ellenőrzésre vár','Kifizetésre vár','Elszámolás elfogadására vár'].map(status=>`<button data-status-courier="1234" data-status-label="${status}">${status}</button>`).join('')}${dialog}<script>${setup}${helpers}${read('jitt_hub/status-dialog.js')}</script>`);
  const modal=page.locator('dialog'),expectedTabs=['Elszámolási folyamat','Reklamáció','Pénzügyi hatás','Ellenőrzés és utalás','Előzmények','Dokumentumok'];
  for(const [status,active] of [['Reklamáció','Reklamáció'],['Számla ellenőrzésre vár','Ellenőrzés és utalás'],['Kifizetésre vár','Ellenőrzés és utalás'],['Elszámolás elfogadására vár','Elszámolási folyamat']]){
   await page.getByRole('button',{name:status,exact:true}).click();await modal.getByRole('tab',{name:active,exact:true}).waitFor();
   assert.deepEqual(await modal.getByRole('tab').allTextContents(),expectedTabs);assert.equal(await modal.getByRole('tab',{name:active,exact:true}).getAttribute('aria-selected'),'true');
   await page.getByRole('button',{name:'Ablak bezárása'}).click();
  }
  assert.equal(await page.evaluate(()=>writes.length),0,'Opening statuses and switching menus must never write');
  await page.getByRole('button',{name:'Reklamáció',exact:true}).click();await modal.locator('.complaint-card blockquote').waitFor();
  assert.equal(await modal.locator('.complaint-card img').count(),0);await page.screenshot({path:path.join(root,'tmp/complaint-dialog-desktop.png')});
  await modal.getByRole('tab',{name:'Pénzügyi hatás',exact:true}).click();assert.match(await modal.locator('#status-panel-finance').textContent(),/31.?020 Ft/);
  await modal.getByRole('tab',{name:'Reklamáció',exact:true}).click();await modal.getByRole('button',{name:'Vizsgálat megkezdése',exact:true}).click();await modal.getByText('Vizsgálat alatt',{exact:true}).waitFor();
  await modal.getByRole('button',{name:'Válasz és lezárás',exact:true}).click();await modal.getByLabel('Futárnak szóló válasz / indoklás').fill('A javítást ellenőriztem.');
  await modal.getByRole('tab',{name:'Pénzügyi hatás',exact:true}).click();await modal.getByRole('tab',{name:'Reklamáció',exact:true}).click();assert.equal(await modal.getByLabel('Futárnak szóló válasz / indoklás').inputValue(),'A javítást ellenőriztem.','Tab changes must retain the draft');
  assert.equal(await modal.locator('.complaint-response-form').evaluate(f=>f.checkValidity()),false,'Closing requires a financial review confirmation');
  await modal.locator('[name="financeReviewed"]').check();await modal.locator('.complaint-response-form').evaluate(f=>{f.requestSubmit();f.requestSubmit()});await modal.getByText('Lezárva',{exact:true}).waitFor();
  assert.equal(await page.evaluate(()=>writes.filter(x=>x.action==='close').length),1);assert.equal(await page.evaluate(()=>writes.find(x=>x.action==='close').snapshotId),'snapshot-11');
  await modal.getByLabel('Reklamáció kiválasztása').selectOption(second);await modal.getByText('Második ügy',{exact:true}).waitFor();await modal.getByRole('button',{name:'Ügy visszanyitása',exact:true}).click();await modal.getByLabel('Futárnak szóló válasz / indoklás').fill('Új bizonyíték');await modal.getByRole('button',{name:'Megerősítés és mentés',exact:true}).click();await modal.getByText('Nyitott',{exact:true}).waitFor();assert.equal(await page.evaluate(()=>writes.at(-1).complaintId),second);
  await modal.getByText('Havi belső megjegyzés és ügyintézési napló · a futár nem látja',{exact:true}).click();await modal.getByLabel('Havi belső megjegyzés',{exact:true}).fill('Belső kiegészítés');await modal.getByRole('button',{name:'Belső megjegyzés mentése',exact:true}).click();await modal.getByText('Az ügy módosítása mentve.',{exact:true}).waitFor();await page.waitForFunction(()=>fixture.complaintNote.note==='Belső kiegészítés');assert.equal(await page.evaluate(()=>fixture.complaintNote.note),'Belső kiegészítés');
  await page.setViewportSize({width:390,height:844});assert(await modal.evaluate(el=>el.scrollWidth<=el.clientWidth+1),'Unified tabs and complaint cards must fit mobile');await page.screenshot({path:path.join(root,'tmp/complaint-dialog-mobile.png')});
  assert.deepEqual(errors,[]);console.log('Complaint UI: identical menus/default tabs, real case selection, escaped text, financial review guard, retained drafts, single save, reopening, internal note and mobile layout verified');
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
