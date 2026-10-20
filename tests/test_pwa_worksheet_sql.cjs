// Isolated transaction test; requires @electric-sql/pglite on NODE_PATH.
const {PGlite} = require('@electric-sql/pglite');
const {readFileSync} = require('node:fs');
const {resolve} = require('node:path');
const {spawnSync} = require('node:child_process');
const assert = require('node:assert/strict');

(async () => {
  const fixture = spawnSync('python', ['-c', `import sys,json
sys.path.insert(0,'tests')
from test_pwa_finance_worksheet import snapshot,manual
from resources.pwa_finance_worksheet import prepare_worksheet
s=snapshot();s['id']='11111111-1111-4111-8111-111111111111'
print(json.dumps(prepare_worksheet(s,[],[manual()],'SQL test')))`], {cwd: resolve(__dirname, '..'), encoding:'utf8'});
  assert.equal(fixture.status, 0, fixture.stderr);
  const prepared = JSON.parse(fixture.stdout).prepared;
  const db = new PGlite();
  try {
    await db.exec(`create role anon;create role authenticated;create role service_role;create schema settlement;
      create table settlement.courier_monthly_closure(courier_id text,period_start date,status text);
      create table public.peopleforce_card_statuses(courier_id text,document_month date,action_key text,status text);`);
    await db.exec(readFileSync(resolve(__dirname, '../sql/settlement_courier_finance_snapshot.sql'), 'utf8'));
    const migration=readFileSync(resolve(__dirname, '../sql/pwa_finance_worksheet_pilot.sql'), 'utf8');
    await db.exec(migration);await db.exec(migration);
    const original='11111111-1111-4111-8111-111111111111';
    await db.query(`insert into settlement.courier_finance_snapshot(id,courier_id,period_start,version,fingerprint,metadata,courier_name)
      values ($1,'12345','2026-09-01',10,'original','{}','Bagoly Zoltán'),
      ('22222222-2222-4222-8222-222222222222','6909','2026-09-01',10,'other','{}','Other'),
      ('44444444-4444-4444-8444-444444444444','7767','2026-10-01',10,'october','{}','Kanyó Krisztián')`,[original]);
    const call=async({courier='12345',month='2026-09-01',base=original,hash='new',data=prepared}={}) =>
      (await db.query(`select settlement.pwa_commit_worksheet_pilot($1,$2,$3,$4,'admin',$5) as result`,[courier,month,base,hash,JSON.stringify(data)])).rows[0].result;
    await assert.rejects(call({courier:''}),/futár és/);
    await assert.rejects(call({month:'2026-10-02'}),/futár és/);
    await assert.rejects(call({courier:'6909'}),/Hiányzó mentési/); // prepared data belongs to a different target
    await assert.rejects(call({month:'2026-10-01'}),/Hiányzó mentési/);
    await assert.rejects(call({base:'33333333-3333-4333-8333-333333333333'}),/verziója megváltozott/);
    const invalid=structuredClone(prepared);invalid.metadata.payable_total++;
    await assert.rejects(call({data:invalid}),/nem egyeznek/);
    const result=await call();assert.equal(result.version,11);
    const saved=(await db.query('select * from settlement.courier_finance_snapshot where id=$1',[result.snapshotId])).rows[0];
    assert.equal(saved.previous_snapshot_id,original);
    assert.equal(saved.metadata.payable_total,138000);
    const values=(await db.query('select item_key,amount_value from settlement.courier_finance_snapshot_item where snapshot_id=$1 and section=\'finance\'',[result.snapshotId])).rows;
    assert.equal(Number(values.find(i=>i.item_key==='manual_bonus').amount_value),3500);
    assert.equal((await call()).unchanged,true);
    const failing=structuredClone(prepared);failing.sources.push(failing.sources[0]);
    await assert.rejects(call({base:result.snapshotId,hash:'failed',data:failing}),/unique/);
    assert.equal((await db.query("select count(*)::int as n from settlement.courier_finance_snapshot where courier_id='12345'")).rows[0].n,2);
    await assert.rejects(call({hash:'stale'}),/verziója megváltozott/);
    await db.exec("insert into settlement.courier_monthly_closure values('12345','2026-09-01','done')");
    await assert.rejects(call({base:result.snapshotId,hash:'closed'}),/kifizetés lezárt/);
    assert.equal((await db.query("select count(*)::int as n from settlement.courier_finance_snapshot where courier_id='6909'")).rows[0].n,1);
    const other=structuredClone(prepared);
    other.metadata.worksheet_courier_id='7767';other.metadata.worksheet_period_start='2026-10-01';
    const otherSaved=await call({courier:'7767',month:'2026-10-01',base:'44444444-4444-4444-8444-444444444444',hash:'other-new',data:other});
    assert.equal(otherSaved.version,11);
    const otherScope=(await db.query('select courier_id,period_start::text from settlement.courier_finance_snapshot where id=$1',[otherSaved.snapshotId])).rows[0];
    assert.deepEqual(otherScope,{courier_id:'7767',period_start:'2026-10-01'});
    await db.exec("insert into public.peopleforce_card_statuses values('7767','2026-10-01','invoice_payment','done')");
    await assert.rejects(call({courier:'7767',month:'2026-10-01',base:otherSaved.snapshotId,hash:'paid',data:other}),/kifizetés lezárt/);
    assert.equal((await db.query("select has_function_privilege('authenticated','settlement.pwa_commit_worksheet_pilot(text,date,uuid,text,text,jsonb)','execute') as allowed")).rows[0].allowed,false);
    console.log('Worksheet SQL passed: multiple couriers/months, target isolation, atomic snapshots, consistent totals, retry, stale version, rollback, closure/payment guards and service-role permissions.');
  } finally { await db.close(); }
})().catch(e=>{console.error(e);process.exitCode=1;});
