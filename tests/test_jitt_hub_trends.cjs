const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const root=path.resolve(__dirname,'..');
const c={URL,Request,Response,fetch,TextEncoder,TextDecoder,console};
vm.createContext(c);vm.runInContext(fs.readFileSync(path.join(root,'jitt_hub/worker.js'),'utf8').replace('export default','const worker ='),c);

(async()=>{
  assert.equal(Array.from(c.trendMonths('2026-01-01')).join(','),'2025-11-01,2025-12-01,2026-01-01');
  const real=c.supabaseFetch;
  const calls=[];
  c.supabaseFetch=async(_env,_schema,table,params)=>{
    calls.push({table,params});
    if(table==='monthly_process_metric_summary')return [
      {period_start:'2026-08-01',complaint_total:10,response_average_hours:0,source_counts:{response_timed_count:0,courier_month_count:1}},
      {period_start:'2026-09-01',complaint_total:12,response_average_hours:0.02,source_counts:{response_timed_count:2,courier_month_count:1}},
    ];
    if(table==='rpc/pwa_dashboard_latest_finance_snapshots')return params.p_period_start==='2026-10-01'?[]:[{id:'f',courier_id:'1',version:1}];
    if(table==='courier_finance_snapshot_item'){
      assert.equal(params.section,'eq.finance');assert.equal(params.amount_kind,'eq.huf');
      assert.ok(!params.select.includes('note'));assert.ok(!params.item_key.includes('base'));
      return [['bonus_malus',500],['kiflis_bonus_malus',-100],['delay_bonus',20]].map(([item_key,amount_value])=>({snapshot_id:'f',section:'finance',item_key,amount_value,amount_kind:'huf'}));
    }
    return [];
  };
  const payload=await(await c.settlementTrends(new Request('https://hub.test/api/settlement-trends?month=2026-10'),{})).json();
  assert.equal(payload.months.length,3);
  assert.equal(payload.months[0].responseAverageHours,null,'Untimed responses must not be a zero-duration answer');
  assert.equal(payload.months[1].responseAverageHours,0.02);
  assert.equal(payload.months[0].bonusHuf,520);
  assert.equal(payload.months[0].malusHuf,100);
  assert.equal(payload.months[2].complaintCount,null,'No stored month is not zero complaints');
  assert.equal(payload.months[2].bonusHuf,null);
  assert.equal(calls.filter(row=>row.table==='courier_salary_advance_plan').length,1,'Three months share one advance query');
  assert.equal(calls.filter(row=>row.table==='courier_salary_advance_request').length,1);
  assert.equal(calls.filter(row=>row.table==='courier_finance_snapshot').length,0,'Use latest versions without loading the history');
  const readCount=calls.length;
  await Promise.all([c.settlementTrends(new Request('https://hub.test/api/settlement-trends?month=2026-10'),{}),c.settlementTrends(new Request('https://hub.test/api/settlement-trends?month=2026-10'),{})]);
  assert.equal(calls.length,readCount,'Warm requests use the short cache');
  vm.runInContext('settlementTrendCache.clear()',c);
  await Promise.all([c.settlementTrends(new Request('https://hub.test/api/settlement-trends?month=2026-10'),{}),c.settlementTrends(new Request('https://hub.test/api/settlement-trends?month=2026-10'),{})]);
  assert.equal(calls.length,readCount*2,'Concurrent requests share one query set');
  vm.runInContext('for(const entry of settlementTrendCache.values())entry.expiresAt=0',c);
  await c.settlementTrends(new Request('https://hub.test/api/settlement-trends?month=2026-10'),{});
  assert.equal(calls.length,readCount*3,'Expired results reload');
  const fixtureFetch=c.supabaseFetch;
  c.supabaseFetch=async()=>{throw Error('HTTP 500 database unavailable')};
  vm.runInContext('settlementTrendCache.clear()',c);
  await assert.rejects(c.settlementTrends(new Request('https://hub.test/api/settlement-trends?month=2026-10'),{}),/HTTP 500/);
  assert.equal(vm.runInContext('settlementTrendCache.size',c),0,'Errors are evicted, never shown as zero data');
  c.supabaseFetch=fixtureFetch;
  const worker=vm.runInContext('worker',c);
  assert.equal((await worker.fetch(new Request('https://hub.test/api/settlement-trends?month=2026-10'),{})).status,401);
  assert.equal((await worker.fetch(new Request('https://hub.test/api/settlement-trends',{method:'POST'}),{})).status,405);
  console.log('Trend values, narrow reads, shared advances, cache expiry, concurrent reads, errors and access checks OK');
  if(process.argv.includes('--live')){
    c.supabaseFetch=real;
    const text=fs.readFileSync(path.join(root,'.streamlit/secrets.toml'),'utf8');
    const setting=name=>text.match(new RegExp('^'+name+'\\s*=\\s*"([^"]+)"','m'))?.[1];
    const data=await(await c.settlementTrends(new Request('https://hub.test/api/settlement-trends?month=2026-10'),{SUPABASE_URL:setting('SUPABASE_URL'),SUPABASE_SERVICE_ROLE_KEY:setting('SUPABASE_SERVICE_ROLE_KEY')})).json();
    assert.equal(data.months.length,3);
    assert.deepEqual(data.months.map(r=>r.complaintCount),[78,103,49]);
    console.log(JSON.stringify(data.months));
  }
})().catch(e=>{console.error(e.message);process.exitCode=1;});
