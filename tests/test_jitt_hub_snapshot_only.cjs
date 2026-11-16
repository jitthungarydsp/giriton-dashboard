const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const root = path.resolve(__dirname, '..');
const context = { URL, Request, Response, fetch, TextEncoder, TextDecoder, console };
vm.createContext(context);
vm.runInContext(fs.readFileSync(path.join(root, 'jitt_hub/worker.js'), 'utf8').replace('export default', 'const worker ='), context);

const item = (key, value) => ({snapshot_id:'latest', section:'finance', item_key:key, amount_value:value, amount_kind:'huf'});
const fixture = {
  vw_courier_month_profile_snapshot: [],
  pwa_users: [],
  courier_master: [{courier_id:7644, courier_name:'Gurzó Balázs'}],
  courier_finance_snapshot: [{id:'latest',courier_id:'7644',courier_name:'Gurzó Balázs',version:20,metadata:{payable_total:402825}}],
  courier_finance_snapshot_item: [item('payable',402825),item('bonus_malus',400000),item('manual_bonus',0),item('correction',2225),item('correction_income',2225),item('income',0)],
  courier_monthly_closure: [{courier_id:'7644',status:'done',payable_huf:402825}],
  courier_monthly_process_metric: [{courier_metric_id:'metric',courier_id:'7644',courier_name:'Gurzó Balázs',financial_complaint_count:2}],
  vw_admin_settlement_dashboard_fast: [{courier_id:'7644',dashboard_status_label:'Elszámolás elfogadásra vár'}],
  peopleforce_card_statuses: [{courier_id:'7644',action_key:'invoice_payment',status:'done'},{courier_id:'7644',action_key:'settlement',status:'open'}],
  monthly_process_metric_summary: [{period_start:'2026-09-01'}],
  courier_salary_advance_plan: [{id:'plan-1',courier_id:'7644',courier_name:'Gurzó Balázs',status:'open',start_date:'2026-09-01',requested_amount_huf:300000}],
  courier_salary_advance_request: [
    {id:'request-1',plan_id:'plan-1',courier_id:'7644',status:'closed',start_date:'2026-09-01',requested_amount_huf:300000},
    {id:'request-2',courier_id:'7644',status:'approved',start_date:'2026-09-01',requested_amount_huf:100000},
    {id:'request-3',courier_id:'7644',status:'requested',start_date:'2026-09-01',requested_amount_huf:50000},
    {id:'request-4',courier_id:'7644',status:'approved',start_date:'2026-08-01',requested_amount_huf:25000},
  ],
};

(async()=>{
  const realFetchRows = context.supabaseFetch;
  context.supabaseFetch = async (_env,_schema,table) => fixture[table] || [];
  const fixtureData = await (await context.settlementDashboard(new Request('https://hub.test/api/settlement-dashboard?month=2026-09'),{})).json();
  const row = fixtureData.couriers.find(r=>r.courierId==='7644');
  assert.ok(row, 'A courier without import row or active PWA user must still be included');
  assert.equal(row.payable,402825);
  assert.equal(row.jittBonus,400000,'The saved aggregate overrides the zero detail alias');
  assert.equal(row.correctionIncome,2225);
  assert.equal(row.status,'Kifizetve');
  assert.equal(row.snapshotIsPublished,true);
  assert.equal(row.processMetric.hasData,true);
  assert.equal(row.salaryAdvanceAdded,400000,'Linked plan/request counted once; pending and other months excluded');
  const malusRow = context.buildCourierRow({courier_id:'7226'},null,null,null,{items:[item('bonus_malus',-75000),item('manual_malus',0)]},null);
  assert.equal(malusRow.jittMalus,75000,'Saved negative aggregate overrides the zero detail alias');
  assert.equal(context.statusForRow({workflowStates:{settlement:{status:'open',updated_by:'finance-snapshot-refresh'},invoice_payment:{status:'done'}}},{status:'done'}),'Elszámolás elfogadásra vár');
  assert.equal(context.statusForRow({dashboardStatus:'Reklamáció',workflowStates:{invoice_payment:{status:'done'}}},{status:'done'}),'Reklamáció');
  console.log('Snapshot-only courier, saved aggregate and workflow regression checks OK');
  if(process.argv.includes('--live')) {
    context.supabaseFetch = realFetchRows;
    const secrets = fs.readFileSync(path.join(root,'.streamlit/secrets.toml'),'utf8');
    const setting = name => secrets.match(new RegExp('^'+name+'\\s*=\\s*"([^"]+)"','m'))?.[1];
    const env={SUPABASE_URL:setting('SUPABASE_URL'),SUPABASE_SERVICE_ROLE_KEY:setting('SUPABASE_SERVICE_ROLE_KEY')};
    assert.ok(env.SUPABASE_URL && env.SUPABASE_SERVICE_ROLE_KEY);
    const data = await (await context.settlementDashboard(new Request('https://hub.test/api/settlement-dashboard?month=2026-09&limit=500'),env)).json();
    const live = data.couriers.find(r=>r.courierId==='7644');
    assert.ok(live);
    assert.equal(live.payable,402825);
    assert.equal(live.jittBonus,400000);
    assert.equal(live.correctionIncome,2225);
    assert.equal(live.status,'Kifizetve');
    assert.equal(live.snapshotIsPublished,true);
    assert.equal(live.processMetric.hasData,true);
    console.log(JSON.stringify({courierId:live.courierId,courierName:live.courierName,status:live.status,payable:live.payable,jittBonus:live.jittBonus,correctionIncome:live.correctionIncome,hasProcessMetric:live.processMetric.hasData,liveReadVerified:true}));
  }
})().catch(error=>{console.error(error.message);process.exitCode=1;});
