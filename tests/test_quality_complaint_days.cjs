const assert = require('node:assert/strict');
const { test } = require('node:test');
const fs = require('node:fs');
const vm = require('node:vm');
const { randomUUID } = require('node:crypto');
const source = fs.readFileSync(require('node:path').join(__dirname, '../pwa/app.js'), 'utf8');
function setup(api) {
  const storage = new Map();
  const context = {state: {user: {username: 'courier'}}, crypto: {randomUUID}, api,
    FormData: class { append() {} }, localStorage: {setItem: (key, value) => storage.set(key, value)}};
  vm.createContext(context);
  vm.runInContext(source.slice(source.indexOf('function qualityComplaintDraftKey('), source.indexOf('function ensureQualityReclamationDialog(')), context);
  return {context, storage};
}
function draft(context) {
  const days = context.qualityComplaintDays([
    {date:'2026-10-17',routeId:'1'}, {date:'2026-10-17',routeId:'2'}, {date:'2026-10-10',routeId:'3'},
  ]);
  days.forEach((day, i) => Object.assign(day, {selected:true, message:`Indoklás ${i}`}));
  return {days, courier:'', month:'2026-10', topic:'uncleanedTimeWindowLate', draftKey:'draft'};
}
test('each Route ID forms a separate complaint even on the same day', async () => {
  const calls=[]; const {context}=setup(async (url, options) => {
    calls.push(JSON.parse(options.body)); return {ok:true,id:String(calls.length)};
  });
  const ctx=draft(context);
  assert.equal(await context.submitQualityComplaintDays(ctx),3);
  assert.equal(calls.length,3);
  assert.equal(calls[0].items.length,1);
  assert.equal(calls[1].items[0].routeId,'2');
  assert.equal(calls[0].message,'Indoklás 0');assert.equal(calls[1].message,'Indoklás 1');
  assert.equal(calls[0].category,'Túra alatti késés');
  assert.notEqual(calls[0].request_id,calls[1].request_id);
});
test('notes and selections survive closing/rebuilding, isolated by courier, month and topic', () => {
  const {context,storage}=setup();const ctx=draft(context);
  ctx.days[0].expanded=true;ctx.days[1].selected=false;
  ctx.days[0].category='Jármű';
  context.rememberQualityComplaintDays(ctx);
  const saved=JSON.parse(storage.get('draft'));
  const restored=context.qualityComplaintDays(ctx.days.flatMap(day=>day.rows),saved);
  assert.equal(restored[0].message,'Indoklás 0');assert.equal(restored[0].selected,true);
  assert.equal(restored[1].selected,false);assert.equal(restored[0].requestId,ctx.days[0].requestId);
  assert.equal(restored[0].category,'Jármű');
  assert.notEqual(context.qualityComplaintDraftKey('1','2026-10','lateShift'),context.qualityComplaintDraftKey('2','2026-10','lateShift'));
});

test('all six categories are selectable, sent per day, with shift defaults for shift complaints', async () => {
  const calls=[];const {context}=setup(async(url,options)=>{
    calls.push(JSON.parse(options.body));return {ok:true,id:String(calls.length)};
  });
  assert.equal(context.qualityComplaintCategories().length,6);
  for(const category of context.qualityComplaintCategories()){
    const ctx=draft(context);ctx.days.slice(1).forEach(day=>day.selected=false);ctx.days[0].category=category;
    await context.submitQualityComplaintDays(ctx);assert.equal(calls.at(-1).category,category);
  }
  assert.equal(context.qualityComplaintDays([{date:'2026-10-17'}],{},'Műszak')[0].category,'Műszak');
});
test('failed second day retries only that day with the same request identity', async () => {
  const calls=[];let fail=true;
  const {context}=setup(async (url,options)=>{
    const body=JSON.parse(options.body);calls.push(body);
    if(body.items[0].date==='2026-10-10'&&fail){fail=false;throw new Error('Interrupted');}
    return {ok:true,id:body.request_id};
  });
  const ctx=draft(context);
  await assert.rejects(context.submitQualityComplaintDays(ctx));
  assert.equal(ctx.days[0].saved,true);assert.equal(ctx.days[1].saved,true);assert.equal(ctx.days[2].saved,false);
  await context.submitQualityComplaintDays(ctx);
  assert.equal(calls.length,4);assert.equal(calls[2].request_id,calls[3].request_id);
});
test('unselected and invalid days are never posted', async () => {
  const {context}=setup(()=>assert.fail('No API call expected'));
  const ctx=draft(context);ctx.days[2].message='';
  await assert.rejects(context.submitQualityComplaintDays(ctx),/2026-10-10/);
  ctx.days.forEach(day=>day.selected=false);
  await assert.rejects(context.submitQualityComplaintDays(ctx),/Jelöld/);
});
test('photo retry resumes the saved case without duplicating the database complaint', async () => {
  const calls=[];let fail=true;
  const {context}=setup(async(url,options)=>{
    calls.push(url);
    if(url.endsWith('/photos')&&fail){fail=false;throw new Error('Interrupted photo');}
    return {ok:true,id:'saved-case'};
  });
  const ctx=draft(context);ctx.days.slice(1).forEach(day=>day.selected=false);
  ctx.days[0].photos=[{size:100}];
  await assert.rejects(context.submitQualityComplaintDays(ctx));
  await context.submitQualityComplaintDays(ctx);
  assert.equal(calls.filter(url=>url==='/api/quality/complaints').length,1);
  assert.equal(ctx.days[0].saved,true);
});

test('lost response retries the exact same payload and request ID after restoring the draft', async () => {
  const calls=[];
  const {context,storage}=setup(async(url,options)=>{
    calls.push(JSON.parse(options.body));
    if(calls.length===1) throw new Error('Response lost');
    return {ok:true,id:'existing-case'};
  });
  let ctx=draft(context);ctx.days.slice(1).forEach(day=>day.selected=false);
  await assert.rejects(context.submitQualityComplaintDays(ctx));
  ctx.days=context.qualityComplaintDays(ctx.days.flatMap(day=>day.rows),JSON.parse(storage.get('draft')));
  ctx.days[0].message='Changed locally';
  await context.submitQualityComplaintDays(ctx);
  assert.deepEqual(calls[0],calls[1]);
});

test('legacy multi-route day draft keeps text but never reuses its request or selection',()=>{
 const {context}=setup();
 const days=context.qualityComplaintDays([{date:'2026-11-20',routeId:'1'},{date:'2026-11-20',routeId:'2'}],
  {'2026-11-20':{message:'Régi szöveg',selected:true,requestId:'old',submittedPayload:{items:[]}}});
 assert.equal(days.length,2);assert.equal(days[0].message,'Régi szöveg');
 assert.equal(days[0].selected,false);assert.equal(days[0].submittedPayload,null);
 assert.notEqual(days[0].requestId,'old');assert.notEqual(days[0].requestId,days[1].requestId);
});

test('several entries of one route remain one case; shift days still group by date',()=>{
 const {context}=setup();const rows=[{date:'2026-11-20',routeId:'1'},{date:'2026-11-20',routeId:'1'}];
 assert.equal(context.qualityComplaintDays(rows).length,1);
 assert.equal(context.qualityComplaintDays([...rows,{date:'2026-11-20',routeId:'2'}],{},'Műszak').length,1);
});
