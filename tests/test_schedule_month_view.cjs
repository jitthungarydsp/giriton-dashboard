const test=require('node:test');const assert=require('node:assert/strict');
const fs=require('node:fs');const path=require('node:path');const vm=require('node:vm');
const root=path.join(__dirname,'..');const source=fs.readFileSync(path.join(root,'pwa/app.js'),'utf8');

test('schedule header exposes the month and warehouse selectors',()=>{
 const html=fs.readFileSync(path.join(root,'pwa/index.html'),'utf8');
 const section=html.slice(html.indexOf('id="coordinator-schedule-content"'),html.indexOf('id="registration-admin-content"'));
 assert.ok(section.includes('id="coordinator-schedule-month"'));assert.ok(section.includes('id="coordinator-schedule-warehouse"'));
 assert.ok(section.includes('Összes – következő 5 nap'));assert.ok(!section.includes('<div hidden>'));
});

test('global background refresh does not refetch or redraw the interactive schedule',async()=>{
 const ctx={state:{user:{},section:'coordinator-schedule'},loadCoordinatorSchedule:()=>{throw Error('No timer redraw')},loadCoordinatorScheduleDay:()=>{throw Error('No timer redraw')}};
 vm.runInNewContext(source.slice(source.indexOf('function currentSectionRefresh()'),source.indexOf('function setAdminPreviewStatus(')),ctx);
 await ctx.currentSectionRefresh();
});

const runtime=path.join(require('node:os').homedir(),'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
test('warehouse selects full month; all/menu restores five days; redraw preserves scroll, open slots, choice and focus',{skip:!fs.existsSync(runtime)},async()=>{
 const {chromium}=require(runtime);const browser=await chromium.launch({channel:'chrome',headless:true});
 try{
  const page=await browser.newPage({viewport:{width:900,height:800}});const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.setContent(`<style>${fs.readFileSync(path.join(root,'pwa/styles.css'),'utf8')}</style><main class="app-shell"><button id="nav-coordinator-schedule">Beosztás</button><h2 id="coordinator-schedule-title"></h2><p id="coordinator-schedule-description"></p><input id="coordinator-schedule-month" type="month" value="2026-11"><select id="coordinator-schedule-warehouse"><option value="">Összes</option><option>BUD1</option><option>BUD2</option></select><div id="coordinator-schedule-panel"></div></main>`);
  await page.evaluate(()=>{
   window.state={user:{role:'admin'},section:'coordinator-schedule',coordinatorScheduleView:'calendar',coordinatorScheduleRequestSeq:0,scheduleOpenVehiclePanels:new Set()};
   window.$=s=>document.querySelector(s);window.escapeHtml=s=>String(s??'');window.localDate=()=> '2026-11-02';window.formatCount=String;window.shortDateTime=s=>s;
   window.resumeScheduleHubRefresh=()=>{};window.scheduleCoverageText=()=> '80%';window.scheduleSlotText=()=> '8/10';
   window.renderOpsSummary=()=>'';window.renderScheduleCalendarDays=days=>days.map(day=>`<button data-schedule-day="${day.date}">${day.date}</button>`).join('');
   window.selectedScheduleDay=payload=>payload?.days?.find(day=>day.date===state.coordinatorScheduleDay)||payload?.days?.[0];
   window.renderCoordinatorCapacity=()=>{$('#coordinator-schedule-panel').innerHTML=Array.from({length:5},(_,i)=>`<div data-five-day>${i+1}</div>`).join('')};
   window.loadScheduleVehicleConfigurations=async()=>{};window.adjacentScheduleDay=()=>null;
   window.renderCoordinatorScheduleDayDetail=()=>`<button data-schedule-back>Vissza</button><input id="schedule-courier-filter" value="${state.testFilter||''}"><div>${[1,2,3].map(i=>`<details class="schedule-slot-card" data-schedule-slot="slot-${i}"><summary>Slot ${i}</summary><div style="height:650px"><select data-schedule-booking-courier><option value="a">Anna</option><option value="b">Béla</option></select></div></details>`).join('')}</div>`;
   window.bindSchedulePrepActions=target=>{target.querySelector('#schedule-courier-filter')?.addEventListener('input',e=>{state.testFilter=e.target.value})};
   window.calls=[];window.api=async url=>{
     calls.push(url);if(url==='/api/coordinator/schedule-capacity')return{days:Array.from({length:5},()=>({}))};
     const params=new URL(url,'http://localhost').searchParams,month=params.get('month'),day=params.get('day');
     const days=day?[{date:day,detailsLoaded:true,workers:[]}]:Array.from({length:new Date(Number(month.slice(0,4)),Number(month.slice(5)),0).getDate()},(_,i)=>({date:`${month}-${String(i+1).padStart(2,'0')}`,capacityKnown:true}));
     return {month,days,summary:{requiredSlots:100,bookedSlots:80,freeSlots:20,coveragePercent:80}};
   };
   window.showSection=section=>{state.section=section;loadCoordinatorSchedule()};
  });
  const header=source.slice(source.indexOf('function scheduleMonthlyMode('),source.indexOf('function renderCoordinatorSchedule()'));
  const render=source.slice(source.indexOf('function renderCoordinatorSchedule()'),source.indexOf('function mergeCoordinatorScheduleDay('));
  const merge=source.slice(source.indexOf('function mergeCoordinatorScheduleDay('),source.indexOf('async function loadCoordinatorSchedule()'));
  const loaders=source.slice(source.indexOf('async function loadCoordinatorSchedule()'),source.indexOf('function coordinatorItems('));
  const monthStart=source.indexOf('$("#coordinator-schedule-month")?.addEventListener("change"');
  const listeners=source.slice(monthStart,source.indexOf('$("#nav-coordinator").addEventListener',monthStart));
  await page.addScriptTag({content:header+render+merge+loaders+listeners+'\ndocument.querySelector("#nav-coordinator-schedule").addEventListener("click",openCoordinatorSchedule);openCoordinatorSchedule();'});
  await page.waitForSelector('[data-five-day]');assert.equal(await page.locator('[data-five-day]').count(),5);
  await page.locator('#coordinator-schedule-warehouse').selectOption('BUD1');
  await page.waitForSelector('[data-schedule-day]');assert.equal(await page.locator('[data-schedule-day]').count(),30);
  assert.equal(await page.locator('#coordinator-schedule-title').textContent(),'Havi beosztás');
  assert.ok(await page.evaluate(()=>calls.at(-1).includes('warehouse=BUD1')));
  await page.locator('#coordinator-schedule-month').fill('2026-12');
  await page.waitForFunction(()=>document.querySelectorAll('[data-schedule-day]').length===31);
  await page.locator('[data-schedule-day="2026-12-03"]').click();
  await page.waitForSelector('[data-schedule-slot]');
  await page.evaluate(()=>{
    const cards=document.querySelectorAll('[data-schedule-slot]');cards.forEach(card=>card.open=true);
    cards[1].querySelector('select').value='b';window.scrollTo(0,cards[1].getBoundingClientRect().top+scrollY-100);
    const filter=document.querySelector('#schedule-courier-filter');filter.value='Béla';state.testFilter='Béla';filter.focus({preventScroll:true});filter.setSelectionRange(2,2);
  });
  const before=await page.evaluate(()=>scrollY);await page.evaluate(()=>renderCoordinatorSchedule());
  assert.ok(Math.abs((await page.evaluate(()=>scrollY))-before)<3);
  assert.equal(await page.locator('[data-schedule-slot="slot-2"] select').inputValue(),'b');
  assert.equal(await page.evaluate(()=>document.querySelectorAll('[data-schedule-slot][open]').length),3);
  assert.deepEqual(await page.evaluate(()=>[document.activeElement.id,document.activeElement.selectionStart]),['schedule-courier-filter',2]);
  await page.locator('[data-schedule-back]').click();
  assert.equal(await page.locator('[data-schedule-day]').count(),31);
  await page.locator('#coordinator-schedule-warehouse').selectOption('');await page.waitForSelector('[data-five-day]');
  await page.locator('#coordinator-schedule-warehouse').selectOption('BUD2');await page.waitForSelector('[data-schedule-day]');
  assert.ok(await page.evaluate(()=>calls.at(-1).includes('warehouse=BUD2')));
  await page.locator('#nav-coordinator-schedule').click();await page.waitForSelector('[data-five-day]');
  assert.equal(await page.locator('#coordinator-schedule-warehouse').inputValue(),'');
  assert.deepEqual(errors,[]);
 }finally{await browser.close()}
});
