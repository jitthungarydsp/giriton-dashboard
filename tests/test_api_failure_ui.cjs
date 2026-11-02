const test=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs'),path=require('node:path');
const app=fs.readFileSync(path.join(__dirname,'../pwa/app.js'),'utf8');
const source=app.slice(app.indexOf('function apiFailureMessage('),app.indexOf('function previewCourierValue('));
test('empty proxy 502/503/504 errors explain missing application response, preserve reference and never retry writes',async()=>{
 for(const status of [502,503,504]){
  let calls=0,started=0,ended=0;
  const ctx={state:{},FormData:class{},beginLoading:()=>started++,endLoading:()=>ended++,
   fetch:async()=>{calls++;return {ok:false,status,headers:{get:name=>name==='rndr-id'?'render-ref':null},json:async()=>{throw Error('empty response')}};}};
  vm.runInNewContext(source,ctx);
  await assert.rejects(ctx.api('/api/admin/pwa-invoice/raw/compare',{method:'POST',body:'{}'}),error=>error.status===status && error.message.includes('nem adott alkalmazásválaszt') && error.message.includes('render-ref'));
  assert.equal(calls,1);assert.equal(started,1);assert.equal(ended,1);
 }
});
test('real application details stay intact and Cloudflare challenge is distinguished',()=>{
 const ctx={};vm.runInNewContext(source,ctx);
 assert.equal(ctx.apiFailureMessage({status:503},{detail:'A Phase 2 tároló még nincs telepítve.'}),'A Phase 2 tároló még nincs telepítve.');
 const response={status:429,headers:{get:name=>name==='cf-mitigated'?'challenge':null}};
 assert.match(ctx.apiFailureMessage(response,{}),/biztonsági ellenőrzést kér/);
});
