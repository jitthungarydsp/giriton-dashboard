const test=require('node:test');const assert=require('node:assert/strict');
const fs=require('node:fs');const path=require('node:path');
const runtime=process.env.PGLITE_TEST_RUNTIME;
test('RAW migration is isolated, session IDs unique, retries immutable and private',{skip:!runtime || !fs.existsSync(runtime)},async()=>{
 const {PGlite}=require(runtime);const db=new PGlite();
 try{
  await db.exec('create role anon; create role authenticated; create role service_role bypassrls;');
  const sql=fs.readFileSync(path.join(__dirname,'../sql/pwa_invoice_raw_phase1.sql'),'utf8');
  await db.exec(sql);await db.exec(sql);
  const raw={formatVersion:1,sheets:[{id:crypto.randomUUID(),name:'Adatok-JITT',rows:[{id:crypto.randomUUID(),sourceRowNo:3,cells:[{column:1,value:'=1+1',cachedValue:2,type:'f'}]}]},{id:crypto.randomUUID(),name:'Üres-KIFLI',rows:[]}]};
  const save=async(id,month='2026-09-01',name='test.xlsx')=>(await db.query('select public.pwa_invoice_raw_save($1::uuid,$2::date,$3,$4,$5,$6::bigint,$7::jsonb,$8) as result',
    [id,month,name,`pwa-invoice-raw/${id}/original.xlsx`,'a'.repeat(64),100,JSON.stringify(raw),'Admin'])).rows[0].result;
  const id=crypto.randomUUID();const first=await save(id);const retry=await save(id);
  assert.equal(first.session_id,retry.session_id);assert.match(first.session_id,/^JITT_2026_09_[1-9]\d{5}$/);
  assert.equal(first.sheet_count,2);assert.equal(first.raw_row_count,1);assert.equal(first.status,'saved');
  assert.equal(first.raw_data,undefined);assert.equal(first.original_storage_path,undefined);
  for(let i=0;i<3;i++)await save(crypto.randomUUID());
  assert.equal(Number((await db.query('select count(*) as n,count(distinct session_id) as unique_n from public."PWA_INVOICE_RAW"')).rows[0].n),4);
  await assert.rejects(save(id,'2026-10-01'),/másik feltöltés/);
  await save(crypto.randomUUID(),'2026-10-01');
  assert.equal((await db.query('select id from public."PWA_INVOICE_RAW" where settlement_month=$1',['2026-09-01'])).rows.length,4);
  const stored=(await db.query('select raw_data from public."PWA_INVOICE_RAW" where id=$1',[id])).rows[0].raw_data;
  assert.equal(stored.sheets[1].name,'Üres-KIFLI');assert.equal(stored.sheets[0].rows[0].cells[0].value,'=1+1');
  await db.exec('set role anon');
  await assert.rejects(db.query('select * from public."PWA_INVOICE_RAW"'),/permission denied/);
  await assert.rejects(save(crypto.randomUUID()),/permission denied/);
  await db.exec('reset role');
  const tables=(await db.query("select tablename from pg_tables where schemaname='public'")).rows.map(row=>row.tablename);
  assert.deepEqual(tables,['PWA_INVOICE_RAW']);
 }finally{await db.close()}
});
