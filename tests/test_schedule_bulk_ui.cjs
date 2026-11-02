const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const source=fs.readFileSync(path.join(__dirname,'../pwa/app.js'),'utf8');
const helpers=source.slice(source.indexOf('function scheduleBulkScope('),source.indexOf('function renderScheduleSlotWorker('));
test('active filter matches accents, multi-part names and IDs, hides empty slots, preserves selections',()=>{
 const ctx={state:{coordinatorScheduleDay:'2026-11-04',coordinatorScheduleWarehouse:'BUD2'}};
 vm.runInNewContext(helpers,ctx);
 const slots=[{workers:[{courierName:'Oláh 9336 László',courierId:9336}]},{workers:[{courierName:'Más Futár',courierId:42}]},{workers:[]}];
 for(const query of ['olah laszlo','#9336','LÁSZLÓ'])assert.equal(ctx.scheduleFilteredSlots(slots,query).length,1);
 assert.equal(ctx.scheduleFilteredSlots(slots,'nemletezo').length,0);
 assert.equal(ctx.scheduleFilteredSlots(slots,'').length,3);
 const day={date:'2026-11-04',warehouse:'BUD2'};ctx.scheduleBulkState(day).delete['selected']={courier_id:9336};
 ctx.scheduleBulkState(day).query='mas';ctx.scheduleFilteredSlots(slots,'mas');
 assert.equal(Object.keys(ctx.scheduleBulkState(day).delete).length,1);
 assert.equal(Object.keys(ctx.scheduleBulkState({date:'2026-11-05',warehouse:'BUD2'}).delete).length,0);
});

test('pending batch polling updates status without re-rendering the slot list',async()=>{
 const day={date:'2026-11-04',warehouse:'BUD2'};
 const ctx={state:{section:'coordinator-schedule',coordinatorScheduleView:'day'},selectedScheduleDay:()=>day,
  $:()=>({querySelectorAll:()=>[]}),api:async()=>({status:'running',items:[]}),
  renderCoordinatorSchedule:()=>{throw Error('Polling must not replace the slot DOM')},window:{setTimeout:()=>1}};
 vm.runInNewContext(helpers,ctx);ctx.scheduleBulkState(day).jobs.delete={id:'fixture',action:'delete',status:'queued'};
 await ctx.pollScheduleBulk(day,'delete');assert.equal(ctx.scheduleBulkState(day).jobs.delete.status,'running');
});

const runtime=path.join(require('node:os').homedir(),'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
test('selection makes no request; filtered bulk deletes exact courier slots, bookings stay staged, partial failures remain selectable',{skip:!fs.existsSync(runtime)},async()=>{
 const {chromium}=require(runtime);const browser=await chromium.launch({channel:'chrome',headless:true});
 try {
  const page=await browser.newPage({viewport:{width:390,height:844}});const errors=[];
  page.on('pageerror',error=>errors.push(error.message));
  await page.route('http://localhost/',route=>route.fulfill({contentType:'text/html',body:`<meta name="viewport" content="width=device-width,initial-scale=1"><style>${fs.readFileSync(path.join(__dirname,'../pwa/styles.css'),'utf8')}</style><main class="app-shell"><div id="panel"></div></main>`}));
  await page.goto('http://localhost/');
  await page.evaluate(()=>{
   window.state={user:{username:'TestAdmin'},coordinatorScheduleDay:'2026-11-04',coordinatorScheduleWarehouse:'BUD2'};
   const olah={courierName:'Oláh 9336 László',courierId:9336,hubTone:'ok',hubStatus:'Felvezetve'};
   const other={courierName:'Koncsik Zoltán',courierId:7665,hubTone:'ok',hubStatus:'Felvezetve'};
   window.day={date:'2026-11-04',warehouse:'BUD2',detailsLoaded:true,slots:[
    {date:'2026-11-04',warehouse:'BUD2',start:'05:00',end:'05:15',shiftTemplateId:1,assigned:2,opened:2,workers:[olah,other]},
    {date:'2026-11-04',warehouse:'BUD2',start:'09:00',end:'09:15',shiftTemplateId:2,assigned:1,opened:1,workers:[olah]},
    {date:'2026-11-04',warehouse:'BUD2',start:'10:00',end:'10:15',shiftTemplateId:3,assigned:0,opened:1,workers:[]} ]};
   state.coordinatorSchedule={days:[day]};
   window.selectedScheduleDay=()=>day;window.$=s=>document.querySelector(s);
   window.escapeHtml=s=>String(s??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('"','&quot;');
   window.shortDateTime=s=>s;window.formatCount=String;window.scheduleRecommendedVehicle=()=>null;
   window.scheduleStatusChip=s=>`<span>${escapeHtml(s)}</span>`;window.workerAttendanceLabel=s=>s;
   window.scheduleSlotTone=slot=>slot.assigned<slot.opened?'open':'full';
   window.scheduleBookingCandidates=()=>[{identity:'9245',courierId:9245,courierName:'Balogh Noel',label:'Balogh Noel #9245'}];
   window.renderScheduleSlotCard=(slot,day)=>`<article class="schedule-slot-card" data-test-slot="${slot.start}"><b>${slot.start}</b>${slot.workers.map(worker=>renderScheduleSlotWorker(worker,slot,day)).join('')}${renderScheduleSlotBookingPrep(slot,day)}</article>`;
   window.renderCoordinatorSchedule=()=>{const target=$('#panel');target.innerHTML=renderScheduleBulkPanel(day)+renderScheduleSlots(day)+renderScheduleBulkButtons(day);bindScheduleBulkActions(target)};
   window.refreshes=0;window.loadCoordinatorScheduleDay=async()=>{refreshes++;renderCoordinatorSchedule()};window.confirm=()=>true;
   window.calls=[];window.records={};window.lostOnce=false;
   window.api=async(url,options={})=>{
    calls.push({url,method:options.method||'GET',body:options.body?JSON.parse(options.body):null});
    if(options.method==='POST'){
      const request=JSON.parse(options.body);
      records[request.request_id]={id:request.request_id,action:request.action,status:'completed',items:request.items.map((item,i)=>({...item,status:request.action==='delete'&&i===1?'failed':'succeeded',message:'Fixture result'}))};
      if(lostOnce){lostOnce=false;throw Error('Lost response')}
      return {...records[request.request_id],status:'queued'};
    }
    const id=url.split('/batches/')[1].split('?')[0];return structuredClone(records[id]);
   };
  });
  const worker=source.slice(source.indexOf('function renderScheduleSlotWorker('),source.indexOf('function scheduleRecommendationShiftLabel('));
  const booking=source.slice(source.indexOf('function renderScheduleSlotBookingPrep('),source.indexOf('function renderScheduleSlotDetails('));
  const slots=source.slice(source.indexOf('function renderScheduleSlots('),source.indexOf('function renderScheduleRecommendation('));
  await page.addScriptTag({content:helpers+worker+booking+slots+'\nrenderCoordinatorSchedule();'});
  await page.locator('#schedule-courier-filter').fill('olah laszlo');
  assert.equal(await page.locator('[data-test-slot]').count(),2);
  await page.locator('[data-schedule-bulk-mark-visible]').click();
  assert.deepEqual(await page.evaluate(()=>Object.values(scheduleBulkState(day).delete).map(i=>i.courier_id)),[9336,9336]);
  assert.equal(await page.evaluate(()=>calls.length),0);
  await page.locator('[data-schedule-filter-clear]').click();
  await page.locator('[data-schedule-booking-select]').click();
  assert.equal(await page.evaluate(()=>Object.values(scheduleBulkState(day).book).length),1);
  assert.equal(await page.evaluate(()=>calls.length),0);
  await page.locator('#schedule-courier-filter').fill('Koncsik');
  assert.equal(await page.locator('[data-test-slot]').count(),1);
  assert.equal(await page.evaluate(()=>Object.values(scheduleBulkState(day).delete).length),2);
  if(process.env.SCHEDULE_BULK_SCREENSHOT)await page.screenshot({path:process.env.SCHEDULE_BULK_SCREENSHOT,fullPage:true});
  await page.locator('[data-schedule-bulk-run="delete"]').first().click();
  await page.waitForFunction(()=>Object.values(scheduleBulkState(day).delete).length===1);
  assert.equal(await page.evaluate(()=>calls.filter(c=>c.method==='POST').length),1);
  assert.deepEqual(await page.evaluate(()=>calls.find(c=>c.method==='POST').body.items.map(i=>i.slot_from)),['05:00','09:00']);
  assert.equal(await page.evaluate(()=>Object.values(scheduleBulkState(day).book).length),1);
  // A lost response is resolved by the same request ID, without a second POST.
  await page.evaluate(()=>{lostOnce=true});
  await page.locator('[data-schedule-bulk-run="book"]').first().click();
  await page.waitForFunction(()=>Object.values(scheduleBulkState(day).book).length===0);
  assert.equal(await page.evaluate(()=>calls.filter(c=>c.method==='POST').length),2);
  assert.ok(await page.evaluate(()=>refreshes>=2));
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+2),true);
  assert.deepEqual(errors,[]);
 }finally{await browser.close()}
});
