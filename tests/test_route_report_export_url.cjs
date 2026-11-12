const assert=require('node:assert/strict');
const test=require('node:test');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../pwa/app.js'),'utf8');
function reportContext(selected) {
  const ctx={state:{routeDetailsReportFields:selected},renderRouteReportBuilder(){},renderRouteDetails(){}};
  vm.runInNewContext(source.slice(source.indexOf('const ROUTE_REPORT_FIELDS'),source.indexOf('const QUEUE_STORAGE_KEY'))+source.slice(source.indexOf('function routeReportFieldsByKey('),source.indexOf('function renderRouteReportBuilder(')),ctx);
  return ctx;
}
test('Route ID is mandatory for old and empty report selections',()=>{
  for(const selection of [[],['tip','courierName'],['routeId','orders']]) {
    const ctx=reportContext(selection);
    const keys=Array.from(ctx.routeReportSelectedFields(),field=>field.key);
    assert.equal(keys.filter(key=>key==='routeId').length,1);
    ctx.routeReportMoveField('routeId','available');
    assert.ok(ctx.routeReportSelectedFields().some(field=>field.key==='routeId'));
  }
});
test('URL includes required Route ID with an older selection',()=>{
  const ctx=reportContext(['tip','courierName']);
  Object.assign(ctx,{URLSearchParams,$:()=>null});ctx.state.statisticsMonth='2026-10';
  vm.runInNewContext(source.slice(source.indexOf('function routeDetailsExcelUrl('),source.indexOf('function monthlyShiftRouteReportExcelUrl(')),ctx);
  assert.equal(new URL(ctx.routeDetailsExcelUrl(),'https://example.test').searchParams.get('columns'),'routeId,tip,courierName');
});
test('Excel URL carries selected columns in order along with row filters',()=>{
  const ctx={URLSearchParams,state:{statisticsMonth:'2026-10',routeDetailsQuery:'Teszt',routeDetailsType:'normal'},
    $:()=>null,routeReportSelectedFields:()=>[{key:'tip'},{key:'courierName'},{key:'orders'}]};
  vm.runInNewContext(source.slice(source.indexOf('function routeDetailsExcelUrl('),source.indexOf('function monthlyShiftRouteReportExcelUrl(')),ctx);
  const url=new URL(ctx.routeDetailsExcelUrl(),'https://example.test');
  assert.equal(url.searchParams.get('columns'),'tip,courierName,orders');
  assert.equal(url.searchParams.get('month'),'2026-10');
  assert.equal(url.searchParams.get('q'),'Teszt');
  assert.equal(url.searchParams.get('route_type'),'normal');
});
