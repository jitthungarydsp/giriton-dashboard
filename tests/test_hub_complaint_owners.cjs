const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const c={URL,Request,Response,TextEncoder,TextDecoder,fetch,console};vm.createContext(c);
vm.runInContext(fs.readFileSync('jitt_hub/worker.js','utf8').replace('export default','const worker ='),c);
const assignment=(courier,id,name)=>({courier_id:courier,action_key:'internal_complaint_assignment:'+id,status_note:JSON.stringify({schemaVersion:1,complaintId:id,courierId:courier,assignee:{name}})});
const rows=[{courierId:'1',status:'Reklamáció'},{courierId:'2',status:'Reklamáció'},{courierId:'3',status:'Kifizetve'}];
c.applyCourierComplaintState(rows,[{id:'a',courier_id:'1',status:'in_progress'},{id:'b',courier_id:'1',status:'open'},{id:'c',courier_id:'2',status:'new'},{id:'closed',courier_id:'3',status:'closed'}],[assignment('1','a','Bagoly Zoltán'),assignment('1','b','Gurzó Balázs'),assignment('2','c','Másik felelős'),assignment('3','closed','Lezárt ügy felelőse')]);
assert.equal(rows[0].status,'Reklamáció / Folyamatban');assert.equal(rows[0].complaintAssignee,'Bagoly Zoltán, Gurzó Balázs');
assert.equal(rows[1].status,'Reklamáció');assert.equal(rows[1].complaintAssignee,'Másik felelős');
assert.equal(rows[2].status,'Kifizetve');assert.equal(rows[2].complaintAssignee,'');
c.applyCourierComplaintState(rows,null,null);assert.equal(rows[0].complaintStateAvailable,false);
console.log('Actual in-progress status, multiple current owners, closed-case exclusion and unavailable-source handling OK');
if(process.argv.includes('--live'))(async()=>{
  const config=fs.readFileSync('.streamlit/secrets.toml','utf8'),setting=name=>config.match(new RegExp('^'+name+'\\s*=\\s*"([^"]+)"','m'))?.[1];
  const result=await c.settlementDashboard(new Request('https://hub.test/api/settlement-dashboard?month=2026-10&limit=500'),{SUPABASE_URL:setting('SUPABASE_URL'),SUPABASE_SERVICE_ROLE_KEY:setting('SUPABASE_SERVICE_ROLE_KEY')});
  const payload=await result.json();assert.equal(result.status,200);assert.ok(payload.couriers.length);assert.ok(payload.couriers.every(row=>row.complaintStateAvailable));
  console.log(JSON.stringify({liveReadOnly:true,couriers:payload.couriers.length,inProgress:payload.couriers.filter(row=>row.status==='Reklamáció / Folyamatban').length,withAssignee:payload.couriers.filter(row=>row.complaintAssignee).length}));
})().catch(error=>{console.error(error.message);process.exitCode=1});
