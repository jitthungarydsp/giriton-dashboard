const test=require('node:test');const assert=require('node:assert/strict');
const fs=require('node:fs');const path=require('node:path');const vm=require('node:vm');
const source=fs.readFileSync(path.join(__dirname,'../pwa/app.js'),'utf8');
const functions=source.slice(source.indexOf('function renderScheduleHubRefreshState('),source.indexOf('function renderCoordinatorCapacity('));
function setup(conclusion='success'){
 const elements={button:{},status:{classList:{toggle(){}},append(){}}};const calls=[];let reloads=0;
 const ctx={state:{user:{username:'Admin'},section:'coordinator-schedule',coordinatorScheduleView:'calendar'},
  $:id=>id.endsWith('-status')?elements.status:elements.button,crypto:{randomUUID:()=> 'fixture-id'},
  localStorage:{setItem(){},removeItem(){},getItem:()=>null},window:{setTimeout:()=>1},
  scheduleMonthlyMode:()=>false,loadCoordinatorSchedule:async()=>{reloads++},loadCoordinatorScheduleDay:async()=>{reloads++},
  api:async(url,options={})=>{calls.push({url,options});return options.method==='POST'?{status:'queued',startDate:'2026-11-02',endDate:'2026-11-06',warehouses:['BUD1','BUD2']}:{status:'completed',conclusion}}};
 vm.runInNewContext(functions,ctx);return{ctx,calls,elements,reloads:()=>reloads};
}
test('dedicated Hub request completes before automatic overview reload',async()=>{
 const {ctx,calls,elements,reloads}=setup();await ctx.startScheduleHubRefresh();
 await new Promise(resolve=>setImmediate(resolve));
 assert.equal(calls[0].url,'/api/coordinator/schedule/hub-refresh');
 assert.deepEqual(JSON.parse(calls[0].options.body),{request_id:'fixture-id',work_date:'',month:'',warehouse:''});
 assert.equal(reloads(),1);assert.equal(elements.button.disabled,false);assert.match(elements.status.textContent,/Hub-adatok frissítve/);
});
test('failure does not claim fresh data or reload the view',async()=>{
 const {ctx,elements,reloads}=setup('failure');await ctx.startScheduleHubRefresh();await new Promise(resolve=>setImmediate(resolve));
 assert.equal(reloads(),0);assert.match(elements.status.textContent,/sikertelen/);assert.equal(elements.button.disabled,false);
});
test('daily refresh passes precise selected day/warehouse and disables duplicate dispatch',async()=>{
 const {ctx,calls}=setup();ctx.state.coordinatorScheduleView='day';ctx.state.coordinatorScheduleDay='2026-11-04';ctx.state.coordinatorScheduleWarehouse='BUD2';
 await ctx.startScheduleHubRefresh();await new Promise(resolve=>setImmediate(resolve));
 const data=JSON.parse(calls[0].options.body);assert.equal(data.work_date,'2026-11-04');assert.equal(data.warehouse,'BUD2');
 ctx.state.scheduleHubRefresh.status='in_progress';await ctx.startScheduleHubRefresh();
 assert.equal(calls.filter(call=>call.options.method==='POST').length,1);
});
