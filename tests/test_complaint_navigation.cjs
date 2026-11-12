const assert=require('node:assert/strict');
const test=require('node:test');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../pwa/app.js'),'utf8');

test('background refresh never reloads an interactive complaint view',async()=>{
  let calls=0;
  const context={state:{user:{role:'admin'},section:'quality-complaints',qualityComplaintFocus:'selected'},Promise,
    loadQualityComplaints:()=>{calls++;}};
  const start=source.indexOf('function currentSectionRefresh(');
  const end=source.indexOf('\nasync function ',start);
  vm.runInNewContext(source.slice(start,end),context);
  await context.currentSectionRefresh();
  assert.equal(calls,0);
});

test('opening a complaint retains focus and avoids layout changes above it',async()=>{
  let signals=0,opened=false,scrolled=false;
  const card={dataset:{complaintId:'selected'},querySelector:()=>({set open(v){opened=v;}}),scrollIntoView:()=>{scrolled=true;}};
  const list={innerHTML:'',querySelectorAll:selector=>selector==='[data-complaint-id]'?[card]:[]};
  const status={textContent:'',append:()=>{}};
  const context={state:{user:{role:'admin'},qualityComplaintFocus:'selected'}, prepareQualityWorkspace:async()=>true,
    loadAdminRouteSignals:()=>{signals++;},
    $:selector=>selector==='#quality-complaints-list'?list:selector==='#quality-complaints-status'?status:{value:'all'},
    api:async()=>({items:[],hasMore:false}),
    document:{createElement:()=>({addEventListener:()=>{}})},encodeURIComponent};
  const start=source.indexOf('async function loadQualityComplaints(');
  const end=source.indexOf('function showQualitySubmissionProgress(',start);
  vm.runInNewContext(source.slice(start,end),context);
  await context.loadQualityComplaints();
  assert.equal(signals,0);
  assert.equal(context.state.qualityComplaintFocus,'selected');
  assert.equal(opened,true);
  assert.equal(scrolled,true);
});
