const test=require('node:test');const assert=require('node:assert/strict');
const fs=require('node:fs');const path=require('node:path');
const root=path.join(__dirname,'..');const source=fs.readFileSync(path.join(root,'pwa/app.js'),'utf8');
const functions=source.slice(source.indexOf('function showQualitySubmissionProgress('),source.indexOf('function routeStoryDistance('));
const runtime=path.join(require('node:os').homedir(),'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');

async function setup(browser){
 const page=await browser.newPage({viewport:{width:390,height:844}});
 await page.route('http://localhost/',route=>route.fulfill({contentType:'text/html',body:`<meta name="viewport" content="width=device-width,initial-scale=1"><style>${fs.readFileSync(path.join(root,'pwa/styles.css'),'utf8')}</style><main class="app-shell">Futárportál</main>`}));
 await page.goto('http://localhost/');
 await page.evaluate(()=>{
  window.$=selector=>document.querySelector(selector);
  window.escapeHtml=value=>String(value??'').replaceAll('&','&amp;').replaceAll('<','&lt;');
  window.qualityShiftTimes=()=>'';window.pastQualityDetails=rows=>rows;
  window.previewCourierValue=()=>'';
  window.state={statistics:{month:'2026-10',qualitySummary:{details:{uncleanedTimeWindowLate:[{date:'2026-10-09',label:'Route 1566147',note:'1 cím · 6 perc'}]}}}};
  window.requests=[];window.pending=[];
  window.api=(url,options)=>{requests.push({url,silentLoading:options.silentLoading});return new Promise((resolve,reject)=>pending.push({resolve,reject}))};
  window.refreshCourierQualityComplaints=async()=>{throw Error('A listafrissítés hibája nem változtathatja sikertelenné a mentést')};
 });
 await page.addScriptTag({content:functions+'\nopenQualityReclamation("uncleanedTimeWindowLate");'});
 await page.locator('[data-quality-reclamation-note]').fill('Teszt reklamáció');
 return page;
}

test('submission opens a top-layer loading modal immediately; confirmed save shows success and prevents duplicate posts',{skip:!fs.existsSync(runtime)},async()=>{
 const {chromium}=require(runtime);const browser=await chromium.launch({channel:'chrome',headless:true});
 try{
  const page=await setup(browser);
  assert.ok(await page.locator('[data-quality-reclamation-submit]').evaluate(node=>node.classList.contains('primary')));
  await page.locator('[data-quality-reclamation-submit]').click();
  await page.locator('#quality-submission-dialog[open]').waitFor();
  assert.equal(await page.locator('#quality-submission-dialog').getAttribute('aria-busy'),'true');
  assert.equal(await page.evaluate(()=>{const card=document.querySelector('#quality-submission-dialog').getBoundingClientRect();return Boolean(document.elementFromPoint(card.x+card.width/2,card.y+card.height/2)?.closest('#quality-submission-dialog'))}),true);
  await page.keyboard.press('Escape');assert.equal(await page.locator('#quality-submission-dialog').evaluate(node=>node.open),true);
  await page.evaluate(()=>document.querySelector('[data-quality-reclamation-submit]').dispatchEvent(new MouseEvent('click',{bubbles:true})));
  assert.equal(await page.evaluate(()=>requests.length),1);
  if(process.env.QUALITY_LOADING_SCREENSHOT)await page.screenshot({path:process.env.QUALITY_LOADING_SCREENSHOT});
  await page.evaluate(()=>pending.shift().resolve({ok:true,id:'11111111-1111-4111-8111-111111111111'}));
  await page.getByText('Sikeres beküldés',{exact:true}).waitFor();
  assert.equal(await page.locator('#quality-submission-dialog').getAttribute('aria-busy'),'false');
  assert.equal(await page.locator('[data-quality-submission-spinner]').isVisible(),false);
  assert.equal(await page.evaluate(()=>requests.every(request=>request.silentLoading===true)),true);
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+2),true);
  if(process.env.QUALITY_SUCCESS_SCREENSHOT)await page.screenshot({path:process.env.QUALITY_SUCCESS_SCREENSHOT});
  await page.locator('[data-quality-submission-close]').click();
  await page.waitForFunction(()=>!document.querySelector('#quality-reclamation-dialog').open);
 }finally{await browser.close()}
});

test('partial photo upload never reports success; retry resumes without creating another complaint',{skip:!fs.existsSync(runtime)},async()=>{
 const {chromium}=require(runtime);const browser=await chromium.launch({channel:'chrome',headless:true});
 try{
  const page=await setup(browser);
  await page.locator('[data-quality-reclamation-photos]').setInputFiles(['a.png','b.png'].map(name=>({name,mimeType:'image/png',buffer:Buffer.from('fixture')})));
  await page.locator('[data-quality-reclamation-submit]').click();
  await page.evaluate(()=>pending.shift().resolve({ok:true,id:'photo-complaint'}));
  await page.waitForFunction(()=>requests.length===2);await page.evaluate(()=>pending.shift().resolve({ok:true}));
  await page.waitForFunction(()=>requests.length===3);await page.evaluate(()=>pending.shift().reject(Error('Képfeltöltési hiba')));
  await page.getByText('A beküldés nem fejeződött be',{exact:true}).waitFor();
  assert.equal(await page.getByText('Sikeres beküldés',{exact:true}).count(),0);
  await page.locator('[data-quality-submission-close]').click();
  assert.equal(await page.locator('#quality-reclamation-dialog').evaluate(node=>node.open),true);
  assert.equal(await page.locator('[data-quality-reclamation-note]').inputValue(),'Teszt reklamáció');
  await page.locator('[data-quality-reclamation-submit]').click();
  await page.waitForFunction(()=>requests.length===4);
  assert.equal(await page.evaluate(()=>requests.filter(request=>request.url==='/api/quality/complaints').length),1);
  await page.evaluate(()=>pending.shift().resolve({ok:true}));
  await page.getByText('Sikeres beküldés',{exact:true}).waitFor();
  assert.match(await page.locator('#quality-submission-message').textContent(),/2 képet/);
 }finally{await browser.close()}
});

test('an unconfirmed response is an error and keeps the draft editable',{skip:!fs.existsSync(runtime)},async()=>{
 const {chromium}=require(runtime);const browser=await chromium.launch({channel:'chrome',headless:true});
 try{
  const page=await setup(browser);await page.locator('[data-quality-reclamation-submit]').click();
  await page.evaluate(()=>pending.shift().resolve({ok:true}));
  await page.getByText('A beküldés nem fejeződött be',{exact:true}).waitFor();
  await page.locator('[data-quality-submission-close]').click();
  assert.equal(await page.locator('[data-quality-reclamation-note]').isEnabled(),true);
  assert.equal(await page.locator('[data-quality-reclamation-submit]').isEnabled(),true);
 }finally{await browser.close()}
});
