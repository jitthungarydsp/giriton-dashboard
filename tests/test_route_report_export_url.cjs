const assert=require('node:assert/strict');
const test=require('node:test');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../pwa/app.js'),'utf8');
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
