const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const source=fs.readFileSync(path.join(__dirname,'../pwa/app.js'),'utf8');
const render=source.slice(source.indexOf('function renderCoordinatorCapacity('),source.indexOf('function renderCoordinatorSchedule('));
const payload={days:[{date:'2026-11-02',warehouses:[{warehouse:'BUD1',capacityKnown:true,coveragePercent:80,bookedSlots:8,requiredSlots:10,freeSlots:2},{warehouse:'BUD2',capacityKnown:false}]}]};
test('shows percentage, actual free slots, missing data and warehouse-specific detail link',()=>{
 const panel={innerHTML:'',querySelectorAll:()=>[]};
 const ctx={state:{coordinatorCapacity:payload},$:()=>panel,localDate:()=> '2026-11-02',shortDateTime:s=>s,formatCount:String,escapeHtml:s=>String(s??'')};
 vm.runInNewContext(render,ctx);ctx.renderCoordinatorCapacity();
 assert.match(panel.innerHTML,/80%/);assert.match(panel.innerHTML,/>2<\/b> szabad műszakhely/);
 assert.match(panel.innerHTML,/Nincs kapacitásadat/);assert.match(panel.innerHTML,/data-capacity-warehouse="BUD2"/);
 assert.doesNotMatch(panel.innerHTML,/>0%</);
});
test('overview requests one five-day summary instead of monthly worker details',async()=>{
 const ctx={state:{coordinatorScheduleRequestSeq:0},$:()=>null,api:async url=>{assert.equal(url,'/api/coordinator/schedule-capacity');return payload},renderCoordinatorSchedule:()=>{}};
 vm.runInNewContext(source.slice(source.indexOf('async function loadCoordinatorSchedule()'),source.indexOf('async function loadCoordinatorScheduleDay(')),ctx);
 await ctx.loadCoordinatorSchedule();assert.equal(ctx.state.coordinatorCapacity,payload);
});

test('coordinator daily detail keeps the warehouse chosen on the capacity card',async()=>{
 const ctx={state:{user:{role:'coordinator'},coordinatorScheduleRequestSeq:0,coordinatorScheduleWarehouse:'BUD2'},
  $:selector=>selector==='#coordinator-schedule-month'?{value:'2026-11'}:selector==='#coordinator-schedule-warehouse'?{value:'BUD2'}:null,
  api:async url=>{assert.ok(url.includes('warehouse=BUD2'));return{days:[]}},renderCoordinatorSchedule(){},mergeCoordinatorScheduleDay(){},preserveScrollAfterRender(){}};
 vm.runInNewContext(source.slice(source.indexOf('async function loadCoordinatorScheduleDay('),source.indexOf('function coordinatorItems(')),ctx);
 await ctx.loadCoordinatorScheduleDay('2026-11-04',{full:true});
});

const runtime=path.join(require('node:os').homedir(),'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
test('five-day cards fit mobile and open the exact warehouse/day including month rollover',{skip:!fs.existsSync(runtime)},async()=>{
 const {chromium}=require(runtime);const browser=await chromium.launch({channel:'chrome',headless:true});
 try {
  const page=await browser.newPage({viewport:{width:390,height:844}});
  await page.setContent(`<meta name="viewport" content="width=device-width,initial-scale=1"><style>${fs.readFileSync(path.join(__dirname,'../pwa/styles.css'),'utf8')}</style><main class="app-shell"><input id="coordinator-schedule-month" type="hidden"><select id="coordinator-schedule-warehouse" hidden><option>BUD1</option><option>BUD2</option></select><div id="coordinator-schedule-panel"></div></main>`);
  await page.evaluate(()=>{
   window.state={coordinatorCapacity:{days:Array.from({length:5},(_,i)=>({date:`2026-12-0${i+1}`,warehouses:[{warehouse:'BUD1',capacityKnown:true,coveragePercent:80,bookedSlots:80,requiredSlots:100,freeSlots:20},{warehouse:'BUD2',capacityKnown:true,coveragePercent:100,bookedSlots:60,requiredSlots:60,freeSlots:0}]}))}};
   window.$=s=>document.querySelector(s);window.escapeHtml=s=>String(s??'');window.formatCount=String;
   window.localDate=()=> '2026-12-01';window.shortDateTime=s=>s;window.loadCoordinatorScheduleDay=day=>{window.openedDay=day};
  });
  await page.addScriptTag({content:render+'\nrenderCoordinatorCapacity();'});
  assert.equal(await page.locator('.capacity-day').count(),5);assert.equal(await page.locator('.capacity-warehouse').count(),10);
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+2),true);
  if(process.env.CAPACITY_SCREENSHOT)await page.screenshot({path:process.env.CAPACITY_SCREENSHOT,fullPage:true});
  await page.locator('[data-capacity-date="2026-12-03"][data-capacity-warehouse="BUD2"]').click();
  assert.deepEqual(await page.evaluate(()=>[openedDay,state.coordinatorScheduleWarehouse,document.querySelector('#coordinator-schedule-month').value]),['2026-12-03','BUD2','2026-12']);
 }finally{await browser.close()}
});
