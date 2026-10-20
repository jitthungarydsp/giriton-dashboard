// Isolated PostgreSQL integration tests; never connects to production.
const {PGlite}=require('@electric-sql/pglite');
const {readFileSync}=require('node:fs');
const {resolve}=require('node:path');
const {spawnSync}=require('node:child_process');
const assert=require('node:assert/strict');
(async()=>{
 const py=spawnSync('python',['-c',`import sys,json
sys.path.insert(0,'tests')
from test_bonus_malus_refresh import snapshot,adjustment
from resources.bonus_malus_snapshot_refresh import prepare_bonus_malus_refresh
s=snapshot();print(json.dumps({'snapshot':s,'adjustment':adjustment(),'result':prepare_bonus_malus_refresh(s,[adjustment()])}))`],{cwd:resolve(__dirname,'..'),encoding:'utf8'});
 assert.equal(py.status,0,py.stderr);const fixture=JSON.parse(py.stdout);
 const db=new PGlite();
 try{
  await db.exec(`create role anon;create role authenticated;create role service_role;create schema settlement;
    create table settlement.courier_monthly_closure(courier_id text,period_start date,status text);
    create table public.peopleforce_card_statuses(courier_id text,document_month date,action_key text,status text);
    create table settlement.courier_settlement_adjustment(id uuid primary key default gen_random_uuid(),courier_id text,
      adjustment_type text,amount_huf numeric,note text,effective_date date,valid_from date,valid_to date,
      is_active boolean default true,deleted_at timestamptz,created_at timestamptz default now(),updated_at timestamptz default now());`);
  await db.exec(readFileSync(resolve(__dirname,'../sql/settlement_courier_finance_snapshot.sql'),'utf8'));
  const s=fixture.snapshot;
  await db.query(`insert into settlement.courier_finance_snapshot(id,courier_id,period_start,version,fingerprint,metadata)
   values($1,'7440','2026-09-01',16,'old',$2),('dddddddd-dddd-4ddd-8ddd-dddddddddddd','other','2026-09-01',2,'other','{}')`,[s.id,JSON.stringify(s.metadata)]);
  for(const i of s.items)await db.query(`insert into settlement.courier_finance_snapshot_item(snapshot_id,section,item_key,item_label,amount_value,amount_kind)
   values($1,$2,$3,$4,$5,$6)`,[s.id,i.section,i.item_key,i.item_label,i.amount_value,i.amount_kind]);
  const sql=readFileSync(resolve(__dirname,'../sql/bonus_malus_snapshot_refresh.sql'),'utf8');
  await db.exec(sql);await db.exec(sql);
  const queue=async(cid='7440',month='2026-09-01')=>(await db.query('select * from settlement.bonus_malus_refresh_queue where courier_id=$1 and period_start=$2',[cid,month])).rows[0];
  const a=fixture.adjustment;
  await db.query(`insert into settlement.courier_settlement_adjustment(id,courier_id,adjustment_type,amount_huf,note,effective_date,valid_from,valid_to)
   values($1,'7440','bonus',12371,$2,'2026-09-30','2026-09-30','2026-09-30')`,[a.id,a.note]);
  let q=await queue();assert.equal(q.state,'pending');assert.equal(await queue('other'),undefined);
  const rev=q.revision;
  await db.query('update settlement.courier_settlement_adjustment set updated_at=now() where id=$1',[a.id]);
  assert.equal((await queue()).revision,rev,'timestamp-only updates do not enqueue');
  const publish=async(prepared=fixture.result.prepared,revision=null,base=s.id)=>{
   if(revision===null)revision=(await queue()).revision;
   return (await db.query('select settlement.publish_bonus_malus_refresh($1,$2,$3,$4,$5,$6) as result',
    ['7440','2026-09-01',revision,base,fixture.result.fingerprint,prepared===null?null:JSON.stringify(prepared)])).rows[0].result;
  };
  await assert.rejects(publish(fixture.result.prepared,0),/forrástételek/);
  const invalid=structuredClone(fixture.result.prepared);invalid.metadata.payable_total++;
  await assert.rejects(publish(invalid),/összesítések/);
  const editedBase=structuredClone(fixture.result.prepared);editedBase.items.find(i=>i.item_key==='base').amount_value++;
  await assert.rejects(publish(editedBase),/más pénzügyi/);
  assert.equal((await db.query("select count(*)::int n from settlement.courier_finance_snapshot where courier_id='7440'")).rows[0].n,1);
  const result=await publish();assert.equal(result.version,17);assert.equal(Number(result.payable),675562);
  assert.equal((await queue()).state,'done');
  assert.equal((await db.query("select max(version) v from settlement.courier_finance_snapshot where courier_id='other'")).rows[0].v,2);
  assert.equal((await db.query('select count(*)::int n from settlement.courier_finance_snapshot_source where snapshot_id=$1',[result.snapshotId])).rows[0].n,fixture.result.prepared.sources.length);
  await assert.rejects(publish(),/verziója/); // stale publication cannot duplicate the financial version
  const unchanged=await publish(null,(await queue()).revision,result.snapshotId);assert.equal(unchanged.unchanged,true);
  // A type/date/courier change queues both affected scopes, not a session batch.
  await db.query("update settlement.courier_settlement_adjustment set valid_from='2026-10-01',effective_date='2026-10-01',valid_to='2026-10-31' where id=$1",[a.id]);
  assert.equal((await queue()).state,'pending');assert.equal((await queue('7440','2026-10-01')).state,'pending');
  await db.exec("insert into public.peopleforce_card_statuses values ('7440','2026-09-01','invoice_payment','done')");
  assert.equal((await publish(null,(await queue()).revision,result.snapshotId)).protected,true);
  assert.equal((await queue()).state,'protected');
  await db.query('delete from settlement.courier_settlement_adjustment where id=$1',[a.id]);
  assert.equal((await queue('7440','2026-10-01')).state,'pending');
  // No base snapshot: record this condition; inserting one requeues this month.
  const missing=(await db.query(`select settlement.publish_bonus_malus_refresh('7440','2026-10-01',$1,null,null,null) as r`,[(await queue('7440','2026-10-01')).revision])).rows[0].r;
  assert.equal(missing.missingSnapshot,true);
  await db.exec("insert into settlement.courier_finance_snapshot(courier_id,period_start,version,fingerprint,metadata) values('7440','2026-10-01',1,'new','{}')");
  assert.equal((await queue('7440','2026-10-01')).state,'pending');
  // Public roles cannot publish financial records.
  assert.equal((await db.query("select has_function_privilege('authenticated','settlement.publish_bonus_malus_refresh(text,date,bigint,uuid,text,jsonb)','execute') allowed")).rows[0].allowed,false);
  console.log('PASS: queue scopes, actual-change detection, atomic snapshot + sources, stale/revision guards, unchanged idempotency, payment protection, moved/deleted records, missing snapshot retry, permissions');
 }finally{await db.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
