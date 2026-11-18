const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const c={URL,Request,Response,fetch,Intl,Date,TextEncoder,TextDecoder,console};vm.createContext(c);
vm.runInContext(fs.readFileSync('jitt_hub/worker.js','utf8').replace('export default','const worker ='),c);
const realSupabase=c.supabaseFetch;
const complaintId='00000000-0000-0000-0000-000000000001',first='10000000-0000-0000-0000-000000000001',second='20000000-0000-0000-0000-000000000001';
let stored=null,closed=false,writes=0,race=false;
const env={SUPABASE_URL:'https://db.test',SUPABASE_SERVICE_ROLE_KEY:'test'},user={username:'Admin'};
c.supabaseFetch=async(_env,schema,table,params)=>{
  assert.equal(schema,'public');
  if(table==='pwa_users'){assert.equal(params.active,'eq.true');return [{role:'admin',email:'gurzo@example.test'}]}
  assert.equal(params.courier_id,'eq.1234');assert.equal(params.document_month,'eq.2026-10-01');
  if(table==='peopleforce_complaints')return [{id:complaintId,status:closed?'closed':'open',courier_name:'Teszt Futár',message:'Bónusz eltérés'}];
  assert.equal(table,'peopleforce_card_statuses');return stored?[structuredClone(stored)]:[];
};
c.fetch=async(url,options)=>{
  assert.equal(new URL(url).pathname,'/rest/v1/peopleforce_card_statuses');writes++;
  if(race)return new Response('[]');
  if(stored){assert.equal(options.method,'PATCH');assert.equal(new URL(url).searchParams.get('updated_at'),'eq.'+stored.updated_at)}
  else assert.equal(options.method,'POST');
  stored=JSON.parse(options.body);return new Response(JSON.stringify([stored]));
};
const body=(extra={})=>({courierId:'1234',month:'2026-10',complaintId,action:'assign',assigneeKey:'bagoly_zoltan',expectedAssignmentId:'',operationId:first,...extra});
const req=value=>new Request('https://hub.test/api/courier360-complaint',{method:'POST',headers:{origin:'https://hub.test','content-type':'application/json'},body:JSON.stringify(value)});
(async()=>{
  let response=await c.courier360ComplaintAction(req(body({assigneeKey:'unknown'})),env,user);assert.equal(response.status,422);assert.equal(writes,0);
  response=await c.courier360ComplaintAction(req(body({email:'attacker@example.test'})),env,user);assert.equal(response.status,200);
  let assignment=JSON.parse(stored.status_note);assert.equal(assignment.assignee.email,'zoltan.bagoly@jitt.hu');assert.equal(assignment.notification.status,'pending');
  assert.equal(assignment.assignedBy,'Admin');assert.ok(assignment.hubUrl.includes('complaint='+complaintId));
  const count=writes;
  assert.equal((await c.courier360ComplaintAction(req(body()),env,user)).status,200);assert.equal(writes,count,'Repeating the same operation must not enqueue another email');
  assert.equal((await c.courier360ComplaintAction(req(body({operationId:second,assigneeKey:'gurzo_balazs'})),env,user)).status,409,'Stale assignment cannot overwrite a newer assignee');
  response=await c.courier360ComplaintAction(req(body({operationId:second,assigneeKey:'gurzo_balazs',expectedAssignmentId:first})),env,user);assert.equal(response.status,200);
  assignment=JSON.parse(stored.status_note);assert.equal(assignment.assignee.email,'gurzo@example.test');assert.equal(assignment.history[0].assignee.name,'Bagoly Zoltán');
  const next={operationId:first,expectedAssignmentId:second};
  assignment.notification.status='sending';stored.status_note=JSON.stringify(assignment);
  assert.equal((await c.courier360ComplaintAction(req(body(next)),env,user)).status,409,'Do not reassign during SMTP delivery');
  assignment.notification.status='failed';stored.status_note=JSON.stringify(assignment);race=true;
  assert.equal((await c.courier360ComplaintAction(req(body(next)),env,user)).status,409);race=false;
  closed=true;assert.equal((await c.courier360ComplaintAction(req(body(next)),env,user)).status,409);
  const worker=vm.runInContext('worker',c);assert.equal((await worker.fetch(req(body()),env)).status,401);
  console.log('Complaint assignment: named recipients, protected email lookup, durable queue, month/ID scope, concurrency, repeat protection, history and admin access OK (mocked writes only)');
  if(process.argv.includes('--live')){
    c.supabaseFetch=realSupabase;
    c.fetch=fetch;
    const text=fs.readFileSync('.streamlit/secrets.toml','utf8'),setting=name=>text.match(new RegExp('^'+name+'\\s*=\\s*"([^"]+)"','m'))?.[1];
    const people=await c.complaintAssignees({SUPABASE_URL:setting('SUPABASE_URL'),SUPABASE_SERVICE_ROLE_KEY:setting('SUPABASE_SERVICE_ROLE_KEY')});
    assert.equal(people[0].email,'zoltan.bagoly@jitt.hu');assert.ok(people[1].email);
    console.log('Live recipient lookup verified for both Bagoly Zoltán and Gurzó Balázs (read-only).');
  }
})().catch(error=>{console.error(error);process.exitCode=1});
