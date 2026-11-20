const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../pwa/app.js'),'utf8');
const helpers=source.slice(source.indexOf('function qualitySignalOrigin('),source.indexOf('async function loadQualityComplaints('));
function setup(api){const ctx={api,Date,Intl};vm.runInNewContext(helpers,ctx);return ctx;}

test('loads every source page, merges linked cases once and retains original automatic source',async()=>{
  const calls=[];
  const ctx=setup(async url=>{
    calls.push(url);const offset=Number(new URL('http://test'+url).searchParams.get('offset'));
    if(url.includes('/complaints?'))return {items:offset===0?Array.from({length:50},(_,i)=>({id:'c'+i,status:i===0?'closed':'open',created_at:'2026-11-01',affected_items:i===0?[{signalKind:'route',signalId:'auto'}]:[]})):[{id:'c50',status:'forwarded',created_at:'2026-11-03'}],hasMore:offset===0,canManage:true,forwardingEnabled:true};
    return offset===0?{alerts:[{id:'auto',status:'auto',created_at:'2026-11-01',complaint:{id:'c0'}},{id:'raw',status:'auto',created_at:'2026-11-04'}],shifts:[{id:'s1',event_type:'coordinator_shift_late',created_at:'2026-11-02'}],hasMore:true}:{alerts:[],shifts:[{id:'s2',created_at:'2026-11-05'}],hasMore:false};
  });
  const data=await ctx.loadQualityInboxPages();
  assert.equal(data.items.length,54);
  assert.ok(!ctx.filterQualityInbox(data.items,'all').some(x=>x.id==='c50'));
  assert.deepEqual(Array.from(ctx.filterQualityInbox(data.items,'forwarded'),x=>x.id),['c50']);
  assert.equal(data.items[0].id,'signal:shift:s2');
  assert.equal(data.items.find(x=>x.id==='c0').inboxOrigin,'automatic');
  assert.equal(data.items.find(x=>x.id==='c0').status,'closed');
  assert.equal(data.items.filter(x=>x.inboxOrigin==='automatic').length,2);
  assert.equal(data.items.find(x=>x.id==='signal:shift:s1').inboxOrigin,'courier');
  assert.ok(!data.items.some(x=>x.id==='signal:route:auto'));
  assert.equal(calls.length,4);
  assert.ok(calls.every(x=>!x.includes('complaint=')&&!x.includes('courier=')));
  assert.equal(data.canManage,true);
});

test('failed source never produces an apparently complete partial inbox',async()=>{
  const ctx=setup(async url=>{if(url.includes('route-signals'))throw Error('Source unavailable');return {items:[{id:'existing'}]};});
  await assert.rejects(ctx.loadQualityInboxPages(),/Source unavailable/);
});

test('forwarded complaints and linked raw signals stay hidden without dropping open or closed cases',()=>{
  const ctx=setup();
  const complaints=[
    {id:'forwarded',status:'forwarded',affected_items:[{signalKind:'route',signalId:'1'}]},
    {id:'open',status:'open'},
    {id:'closed',status:'closed'},
  ];
  const alerts=[{id:'1',status:'auto',complaint:{id:'forwarded',status:'forwarded'}},
    {id:'2',status:'auto',complaint:{id:'out-of-period',status:'forwarded'}},
    {id:'3',status:'new'}];
  const shifts=[{id:'4',complaint:{id:'shift-case',status:'forwarded'}}];
  const rows=ctx.mergeQualityInbox(complaints,alerts,shifts);
  assert.deepEqual(Array.from(ctx.filterQualityInbox(rows,'all'),x=>x.id).sort(),['closed','open','signal:route:3']);
  assert.equal(ctx.filterQualityInbox(rows,'forwarded').length,3);
  for(const filter of ['automatic','courier'])assert.ok(ctx.filterQualityInbox(rows,filter).every(row=>row.status!=='forwarded'));
  assert.equal(complaints[0].status,'forwarded');
  assert.equal(alerts.length,3);
});

test('cancelled older load stops fetching further pages',async()=>{
  let current=true,calls=0;
  const ctx=setup(async()=>{calls++;current=false;return {items:[{id:'a'}],hasMore:true};});
  assert.equal(await ctx.loadQualityInboxPages(()=>current),null);
  assert.equal(calls,1);
});

test('saved automatic origin survives missing source and repeated pages fail visibly',async()=>{
  const ctx=setup(async()=>({items:[{id:'a'}],hasMore:true}));
  const items=ctx.mergeQualityInbox([{id:'a',affected_items:[{signalOrigin:'automatic'}]}],[],[]);
  assert.equal(items[0].inboxOrigin,'automatic');
  await assert.rejects(ctx.loadQualityInboxPages(),/teljes jelzéslista/);
});

test('duplicate closures hide only resolved raw signals and keep their source records intact',()=>{
  const ctx=setup();
  const raw=[{id:'1',status:'auto',resolution:{reason:'duplicate'}},{id:'2',status:'new'}];
  const result=ctx.mergeQualityInbox([],raw,[{id:'3',resolution:{reason:'duplicate'}}]);
  assert.deepEqual(Array.from(result,row=>row.id),['signal:route:2']);
  assert.equal(raw.length,2);
  assert.equal(raw[0].status,'auto');
});

test('page has only one source filter and a shared list without paging or extra panels',()=>{
  const html=fs.readFileSync(path.join(__dirname,'../pwa/index.html'),'utf8');
  const section=html.slice(html.indexOf('<div id="quality-complaints-content"'),html.indexOf('<div id="today-workers-content"'));
  for(const option of ['all','automatic','courier','forwarded'])assert.ok(section.includes(`value="${option}"`));
  assert.ok(section.includes('quality-complaints-list'));
  for(const removed of ['quality-complaints-prev','quality-complaints-next','quality-route-signals-panel','quality-workspace-panel','quality-form-test'])assert.ok(!section.includes(removed));
});
