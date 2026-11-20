// Run with @electric-sql/pglite on NODE_PATH. Uses an isolated PostgreSQL WASM database.
const {PGlite}=require('@electric-sql/pglite');
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const read=name=>fs.readFileSync(path.join(__dirname,'../sql',name),'utf8');
(async()=>{
 const db=new PGlite();
 try{
  await db.exec('create role anon; create role authenticated; create role service_role;');
  for(const file of ['pwa_quality_complaints.sql','pwa_quality_complaint_management.sql','pwa_quality_complaint_forwarding.sql','pwa_quality_complaint_browser_approval.sql']) await db.exec(read(file));
  const add=async(route,date='2026-11-20',courier='9460',topic='uncleanedTimeWindowLate')=>(await db.query(`insert into public.pwa_quality_complaints(request_id,courier_id,courier_name,topic,work_month,message,affected_items,created_by)
    values(gen_random_uuid(),$1,'Test courier',$2,'2026-11-01','Test reason',$3::jsonb,'test') returning id`,[courier,topic,JSON.stringify([{date,routeId:route}])])).rows[0].id;
  const old=await add('1612799');
  const sent=await add('1612799');
  await db.query("insert into pwa_quality_complaint_deliveries(complaint_id,payload,state,approved_by) values($1,$2::jsonb,'sent','test')",[sent,JSON.stringify({route_id:'1612799'})]);
  const noShow=await add('','2026-11-18','9460','noShow');
  await db.exec(read('pwa_quality_complaint_daily_limit.sql'));
  const before=(await db.query('select * from pwa_quality_complaints order by id')).rows;
  const deliveryBefore=(await db.query('select * from pwa_quality_complaint_deliveries')).rows;
  await db.exec(read('pwa_quality_complaint_route_limit.sql'));
  assert.deepEqual((await db.query('select * from pwa_quality_complaints order by id')).rows,before);
  assert.deepEqual((await db.query('select * from pwa_quality_complaint_deliveries')).rows,deliveryBefore);
  assert.equal((await db.query("select complaint_id from pwa_quality_complaint_route_claims where route_id='1612799'")).rows[0].complaint_id,sent);
  assert.equal((await db.query("select id from pwa_find_quality_route_complaint('1612799','9460')")).rows[0].id,sent);
  assert.equal((await db.query("select id from pwa_find_quality_route_complaint('1612799','different-courier')")).rows.length,0);
  await assert.rejects(add('1612799'),e=>e.code==='PZ001');
  await assert.rejects(add('1612799','2026-11-21','another-courier'),e=>e.code==='PZ001');
  const other=await add('another-route'); // same courier, same day succeeds
  await assert.rejects(add(''),e=>e.code==='22023');
  await assert.rejects(add('1,2'),e=>e.code==='22023');
  await assert.rejects(add('','2026-11-18','9460','noShow'),e=>e.code==='PZ001');
  await add('','2026-11-19','9460','noShow');
  await add('','2026-11-18','other-courier','noShow');
  const deliver=(id,route)=>db.query("insert into pwa_quality_complaint_deliveries(complaint_id,payload,state,approved_by) values($1,$2::jsonb,'prepared','test')",[id,JSON.stringify({route_id:route})]);
  await assert.rejects(deliver(old,'1612799'),e=>e.code==='PZ001'); // historical sibling cannot forward
  await assert.rejects(deliver(other,'wrong-route'),e=>e.code==='22023');
  await deliver(other,'another-route');
  await assert.rejects(db.query("update pwa_quality_complaints set affected_items='[{\"date\":\"2026-11-20\",\"routeId\":\"changed\"}]' where id=$1",[other]),e=>e.code==='22023');
  await db.query("update pwa_quality_complaints set status='closed',admin_response='Resolved' where id=$1",[other]);
  await assert.rejects(add('another-route'),e=>e.code==='PZ001'); // closure does not release the tour
  const parallel=await Promise.allSettled([add('parallel-route'),add('parallel-route')]);
  assert.equal(parallel.filter(x=>x.status==='fulfilled').length,1);
  assert.equal(parallel.find(x=>x.status==='rejected').reason.code,'PZ001');
  await db.exec(read('pwa_quality_complaint_route_limit.sql')); // safe re-run
  assert.equal((await db.query('select id from pwa_quality_complaints where id=$1',[noShow])).rows.length,1);
  console.log('PostgreSQL Route ID migration passed: preserved history, same-day independent tours, global duplicate protection, competing inserts, submission guard, no-show rules, idempotent migration.');
 }finally{await db.close()}
})().catch(error=>{console.error(error);process.exitCode=1});
