const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),assert=require('node:assert/strict');
const root=path.resolve(__dirname,'..');
const c={URL,Request,Response,fetch,TextEncoder,TextDecoder,Intl,Date,atob,console};vm.createContext(c);
vm.runInContext(fs.readFileSync(path.join(root,'jitt_hub/worker.js'),'utf8').replace('export default','const worker ='),c);
const now=new Date('2026-11-16T10:00:00Z'),date='2026-11-16';
const base={date,now,monitor:[{route_id:'42',status:'ON_ROUTE',fetched_at:'2026-11-16T09:59:00Z',courier_json:{plannedStartAt:'2026-11-16T05:00:00Z'}}],detail:[{route_id:'42',fetched_at:'2026-11-16T09:59:00Z',response_json:{routeId:'42',stops:[{sequence:1,state:'COMPLETED',address:'First'},{sequence:2,state:'PENDING',address:'Next'}]}}],bookings:[{work_date:date,slot_from:'12:00',active:false},{work_date:'2026-11-17',slot_from:'05:00',active:true}],attendance:[]};
(async()=>{
  let result=c.courier360BuildOperational(base);
  assert.equal(result.currentWorking,true);assert.equal(result.route.nextStop.address,'Next');assert.equal(result.nextShift.date,'2026-11-17');assert.equal(result.shifts.length,1);
  result=c.courier360BuildOperational({...base,now:new Date('2026-11-16T13:00:00Z')});assert.equal(result.currentWorking,null);assert.equal(result.route.nextStop,null);assert.equal(result.route.lastKnownNextStop.address,'Next');
  result=c.courier360BuildOperational({...base,detail:[{...base.detail[0],route_id:'41',response_json:{routeId:'41',stops:[{address:'Another route'}]}}]});assert.equal(result.route.id,'42');assert.equal(result.route.stops.length,0);assert.equal(result.route.nextStop,null);
  result=c.courier360BuildOperational({...base,detail:[{...base.detail[0],fetched_at:'2026-11-16T08:00:00Z'}]});assert.equal(result.route.active,true);assert.equal(result.route.nextStop,null);assert.equal(result.route.lastKnownNextStop.address,'Next');
  result=c.courier360BuildOperational({...base,monitor:[{...base.monitor[0],courier_json:{plannedStartAt:'2026-11-15T05:00:00Z'}}],detail:[]});assert.equal(result.route.active,false);
  result=c.courier360BuildOperational({...base,monitor:[],detail:[],attendance:[{updated_at:'2026-11-16T09:59:00Z',checkin_start:'04:30:00',checkin_end:'10:55:00'}]});assert.equal(result.currentWorking,false);
  assert.equal(c.budapestMidnightUtc('2026-07-01'),'2026-06-30T22:00:00.000Z');assert.equal(c.budapestMidnightUtc('2026-11-16'),'2026-11-15T23:00:00.000Z');
  assert.throws(()=>c.courier360Identity(new Request('https://test/api/courier360?courier=x')));
  const worker=vm.runInContext('worker',c);
  for(const endpoint of ['courier360','courier360-document'])assert.equal((await worker.fetch(new Request('https://test/api/'+endpoint),{})).status,401);
  const actualFetch=c.supabaseFetch,documentId='00000000-0000-0000-0000-000000000001';
  c.supabaseFetch=async(env,schema,table,params)=>{assert.equal(table,'peopleforce_documents');assert.equal(params.id,'eq.'+documentId);assert.equal(params.courier_id,'eq.6959');return [{file_name:'invoice.pdf',mime_type:'application/pdf',file_size:5,file_content_base64:'JVBERi0='}]};
  let document=await c.courier360Document(new Request(`https://test/api/courier360-document?courier=6959&id=${documentId}`),{});assert.equal(document.status,200);assert.equal(await document.text(),'%PDF-');assert.equal(document.headers.get('cache-control'),'no-store');
  c.supabaseFetch=async()=>[];document=await c.courier360Document(new Request(`https://test/api/courier360-document?courier=6958&id=${documentId}`),{});assert.equal(document.status,404);c.supabaseFetch=actualFetch;
  console.log('Freshness, route-day isolation, next stop, cancelled shifts, checkout, DST and admin access OK');
  if(process.argv.includes('--live')){
    const text=fs.readFileSync(path.join(root,'.streamlit/secrets.toml'),'utf8');const setting=name=>text.match(new RegExp('^'+name+'\\s*=\\s*"([^"]+)"','m'))?.[1];
    const env={SUPABASE_URL:setting('SUPABASE_URL'),SUPABASE_SERVICE_ROLE_KEY:setting('SUPABASE_SERVICE_ROLE_KEY')};
    const response=await c.courier360Data(new Request('https://test/api/courier360?courier=6959&date=2026-11-16&month=2026-10'),env);
    const p=await response.json();assert.equal(response.status,200);assert.equal(p.courier.id,'6959');assert.ok(p.financeSnapshot);assert.ok(!p.operational.route?.active||p.operational.fresh);
    assert.equal(p.payment.snapshotId,p.financeSnapshot.id);
    console.log(JSON.stringify({courier:p.courier,working:p.operational.currentWorking,label:p.operational.label,snapshotVersion:p.financeSnapshot.version,payable:p.finance.payable,complaints:p.complaints.length,documents:p.documents.length,shifts:p.operational.shifts.length,unavailable:p.sources.filter(s=>!s.available).map(s=>s.table),payment:{transferResult:p.payment.transfer.result,cashResult:p.payment.cash.result,hasBankAccount:Boolean(p.payment.bankAccount),hasSavedTig:p.payment.transfer.expectedHuf!==null,canClose:p.payment.canClose,blockingReasons:p.payment.blockingReasons,eventCount:p.payment.events.length}}));
  }
})().catch(e=>{console.error(e.stack);process.exitCode=1});
