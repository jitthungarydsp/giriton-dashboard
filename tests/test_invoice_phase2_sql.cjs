const test=require('node:test'), assert=require('node:assert/strict'), fs=require('node:fs'), path=require('node:path');
const runtime=process.env.PGLITE_TEST_RUNTIME;
test('monthly snapshot is complete, atomic, unique, idempotent, scoped and guarded from stale replacement',{skip:!runtime||!fs.existsSync(runtime)},async()=>{
 const {PGlite}=require(runtime);const db=new PGlite();
 try{
  await db.exec('create role anon;create role authenticated;create role service_role bypassrls;');
  for(const file of ['pwa_invoice_raw_phase1.sql','pwa_invoice_phase2.sql','pwa_invoice_phase2.sql'])await db.exec(fs.readFileSync(path.join(__dirname,'../sql',file),'utf8'));
  const raw={sheets:[{id:crypto.randomUUID(),name:'Adatok-JITT',index:1,rows:[{id:crypto.randomUUID(),sourceRowNo:2,cells:[{column:1,type:'f',value:'=1+1',cachedValue:2}]}]},{id:crypto.randomUUID(),name:'Üres-KIFLI',index:2,rows:[]}]};
  async function upload(month){const id=crypto.randomUUID();await db.query('select public.pwa_invoice_raw_save($1::uuid,$2::date,$3,$4,$5,100,$6::jsonb,$7)',[id,month,'book.xlsx',`pwa-invoice-raw/${id}/original.xlsx`,'a'.repeat(64),JSON.stringify(raw),'admin']);return id;}
  const a=await upload('2026-09-01'),b=await upload('2026-09-01'),oct=await upload('2026-10-01');
  async function choose(source,request,expected=null,month='2026-09-01'){return (await db.query('select public.pwa_invoice_work_select($1::date,$2::uuid,$3::uuid,$4::uuid,$5) result',[month,source,request,expected,'admin'])).rows[0].result;}
  const firstId=crypto.randomUUID();const first=await choose(a,firstId);
  assert.equal(first.id,firstId);assert.equal(first.sheet_count,2);assert.equal(first.raw_data,undefined);
  assert.deepEqual((await db.query('select raw_data from public."PWA_INVOICE_WORK"')).rows[0].raw_data,raw);
  assert.deepEqual(await choose(a,firstId),first);
  assert.equal((await choose(b,crypto.randomUUID())).conflict,true);
  assert.equal((await choose(oct,crypto.randomUUID(),firstId)).missing,true);
  assert.equal((await db.query('select id from public."PWA_INVOICE_WORK"')).rows[0].id,firstId);
  const secondId=crypto.randomUUID();await choose(b,secondId,firstId);
  assert.equal((await choose(a,crypto.randomUUID(),firstId)).conflict,true);
  assert.equal((await db.query('select count(*) n from public."PWA_INVOICE_WORK"')).rows[0].n,1);
  await choose(oct,crypto.randomUUID(),null,'2026-10-01');
  async function remove(ids,month='2026-09-01'){return (await db.query('select public.pwa_invoice_raw_delete($1::date,$2::uuid[]) result',[month,ids])).rows[0].result;}
  assert.equal((await remove([a,b])).activeSource,true);
  assert.equal((await remove([a,oct])).missing,true);
  assert.equal((await remove([a])).deletedCount,1);
  assert.equal((await remove([a])).deletedCount,0);
  assert.equal((await choose(a,crypto.randomUUID(),secondId)).missing,true);
  assert.deepEqual((await db.query('select raw_data from public."PWA_INVOICE_RAW" where id=$1',[a])).rows[0].raw_data,raw);
  await db.exec('set role anon');
  await assert.rejects(db.query('select * from public."PWA_INVOICE_WORK"'),/permission denied/);
  await assert.rejects(choose(b,crypto.randomUUID()),/permission denied/);
  await assert.rejects(remove([a]),/permission denied/);
  await db.exec('reset role');
  await db.close();
 }catch(error){await db.close();throw error;}
});
