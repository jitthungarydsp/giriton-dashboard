const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),assert=require('node:assert/strict');
const c={URL,Request,Response,fetch,TextEncoder,TextDecoder,Intl,Date,atob,console};vm.createContext(c);
vm.runInContext(fs.readFileSync(path.join(__dirname,'../jitt_hub/worker.js'),'utf8').replace('export default','const worker ='),c);
const complaintId='00000000-0000-0000-0000-000000000001',snapshotId='00000000-0000-0000-0000-000000000002';
const env={SUPABASE_URL:'https://db.test',SUPABASE_SERVICE_ROLE_KEY:'test-only'},user={username:'Admin'};
let row={id:complaintId,status:'new',admin_response:null,responded_at:null},note=null,calls=[],race=false,noteFail=false;
const body=(action,extra={})=>({courierId:'1234',month:'2026-10',complaintId,action,expected:{status:row.status,adminResponse:row.admin_response,respondedAt:row.responded_at},snapshotId,...extra});
const request=(value,origin='https://test')=>new Request('https://test/api/courier360-complaint',{method:'POST',headers:{origin,'content-type':'application/json'},body:JSON.stringify(value)});
c.supabaseFetch=async(_env,schema,table,params)=>{
 assert.equal(schema,'public');assert.equal(params.courier_id,'eq.1234');
 if(table==='peopleforce_complaints'){assert.equal(params.document_month,'eq.2026-10-01');return params.id===`eq.${complaintId}`?[structuredClone(row)]:[];}
 assert.equal(table,'peopleforce_complaint_notes');return note?[structuredClone(note)]:[];
};
c.loadLatestFinanceSnapshots=async()=>[{id:snapshotId}];
c.fetch=async(url,options)=>{
 const target=new URL(url),data=JSON.parse(options.body);calls.push({table:target.pathname.split('/').at(-1),data});
 if(target.pathname.endsWith('/peopleforce_complaint_notes')){
   if(noteFail)return new Response('[]',{status:500});
   if(options.method==='PATCH')assert.equal(target.searchParams.get('updated_at'),'eq.'+note.updated_at);
   note=data;return new Response(JSON.stringify([note]));
 }
 assert.match(target.pathname,/peopleforce_complaints$/);assert.equal(options.method,'PATCH');
 assert.equal(target.searchParams.get('id'),'eq.'+complaintId);assert.equal(target.searchParams.get('courier_id'),'eq.1234');assert.equal(target.searchParams.get('document_month'),'eq.2026-10-01');assert.equal(target.searchParams.get('status'),'eq.'+row.status);
 assert.equal(target.searchParams.get('admin_response'),row.admin_response==null?'is.null':'eq.'+row.admin_response);
 if(race)return new Response('[]');Object.assign(row,data);return new Response(JSON.stringify([row]));
};
(async()=>{
 assert.equal((await c.courier360ComplaintAction(request(body('start'),'https://evil.test'),env,user)).status,403);
 assert.equal((await c.courier360ComplaintAction(request(body('close',{response:'OK',decision:'accepted'})),env,user)).status,422);
 assert.equal((await c.courier360ComplaintAction(request(body('close',{response:'OK',decision:'accepted',financeReviewed:true,snapshotId:'stale'})),env,user)).status,409);
 assert.equal((await c.courier360ComplaintAction(request(body('respond',{response:''})),env,user)).status,422);assert.equal(calls.length,0);
 let response=await c.courier360ComplaintAction(request(body('start')),env,user);assert.equal(response.status,200);assert.equal(row.status,'in_progress');assert.equal(row.responded_at,null,'Starting an investigation is not an answer');
 const stale=body('respond',{response:'old request'});await c.courier360ComplaintAction(request(body('respond',{response:'Új válasz'})),env,user);assert.equal(row.admin_response,'Új válasz');assert.equal(row.responded_by,'Admin');
 const count=calls.length;assert.equal((await c.courier360ComplaintAction(request(stale),env,user)).status,409);assert.equal(calls.length,count);
 response=await c.courier360ComplaintAction(request(body('close',{response:'Javítás külön ellenőrizve.',decision:'accepted',financeReviewed:true})),env,user);
 assert.equal(response.status,200);assert.equal(row.status,'closed');assert.match(row.admin_response,/Elfogadva/);assert.match(note.note,/Korábbi válasz megőrizve: Új válasz/);
 response=await c.courier360ComplaintAction(request(body('reopen',{response:'Új bizonyíték érkezett.'})),env,user);assert.equal(response.status,200);assert.equal(row.status,'open');assert.equal(row.admin_response,null);assert.equal(row.responded_at,null);assert.match(note.note,/Javítás külön ellenőrizve/,'Prior answer must survive reopening');
 const beforeRow=structuredClone(row);assert.equal((await c.courier360ComplaintAction(request(body('note',{expectedNote:'stale',note:'overwrite'})),env,user)).status,409);
 assert.equal((await c.courier360ComplaintAction(request(body('note',{expectedNote:note.note,note:note.note+'\nBelső kiegészítés'})),env,user)).status,200);assert.deepEqual(row,beforeRow);
 noteFail=true;const before=calls.length;assert.equal((await c.courier360ComplaintAction(request(body('start')),env,user)).status,409);assert.equal(calls.slice(before).some(x=>x.table==='peopleforce_complaints'),false);noteFail=false;
 race=true;response=await c.courier360ComplaintAction(request(body('respond',{response:'Nem írhat felül másik választ.'})),env,user);assert.equal(response.status,409);assert.deepEqual(row,beforeRow);race=false;
 assert(calls.every(call=>['peopleforce_complaints','peopleforce_complaint_notes'].includes(call.table)),'Complaint actions must never write financial snapshots, items, closures or workflow states');
 const comparison=c.courier360FinanceComparison({id:'new',version:11,items:[{section:'finance',amount_kind:'huf',item_key:'bonus',amount_value:31020},{section:'finance',amount_kind:'huf',item_key:'payable',amount_value:831020}]},{id:'old',version:10},[{item_key:'bonus',amount_value:0},{item_key:'payable',amount_value:800000}]);
 assert.equal(comparison.rows[0].differenceHuf,31020);assert.equal(comparison.rows[1].differenceHuf,31020);
 assert.equal(c.courier360FinanceComparison(null,null).available,false);
 assert.equal(c.courier360FinanceComparison({items:[]},{id:'old'},[{item_key:'bonus',amount_value:31020}]).rows[0].afterHuf,null,'Missing is not zero');
 const worker=vm.runInContext('worker',c);assert.equal((await worker.fetch(request(body('start')),env)).status,401);assert.equal((await worker.fetch(new Request('https://test/api/courier360-complaint'),env)).status,405);
 console.log('Complaint actions: owned month/ID, auth/origin, stale response and finance guards, preserved answers, note concurrency, audit-before-change and no financial writes verified (mocked writes only)');
})().catch(e=>{console.error(e);process.exitCode=1});
