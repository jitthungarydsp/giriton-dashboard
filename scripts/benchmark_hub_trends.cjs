// Read-only benchmark. Reports sizes/timings, never credentials or courier data.
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const root=path.resolve(__dirname,'..');
const secrets=fs.readFileSync(path.join(root,'.streamlit/secrets.toml'),'utf8');
const setting=name=>secrets.match(new RegExp('^'+name+'\\s*=\\s*"([^"]+)"','m'))?.[1];
const env={SUPABASE_URL:setting('SUPABASE_URL'),SUPABASE_SERVICE_ROLE_KEY:setting('SUPABASE_SERVICE_ROLE_KEY')};
async function benchmark(source){
  const requests=[];
  const measuredFetch=async(url,options)=>{
    const start=performance.now(),response=await fetch(url,options),body=await response.text();
    requests.push({table:new URL(url).pathname.split('/').pop(),ms:Math.round(performance.now()-start),bytes:Buffer.byteLength(body),status:response.status});
    return new Response(body,{status:response.status,headers:response.headers});
  };
  const context={URL,Request,Response,fetch:measuredFetch,TextEncoder,TextDecoder,console};vm.createContext(context);
  vm.runInContext(source.replace('export default','const worker ='),context);
  const start=performance.now();
  const response=await context.settlementTrends(new Request('https://hub.test/api/settlement-trends?month=2026-10'),env);
  const payload=await response.json();
  const elapsedMs=Math.round(performance.now()-start),beforeWarm=requests.length,warmStart=performance.now();
  await context.settlementTrends(new Request('https://hub.test/api/settlement-trends?month=2026-10'),env);
  const warm={elapsedMs:Math.round(performance.now()-warmStart),requests:requests.length-beforeWarm};
  const coldRequests=requests.slice(0,beforeWarm);
  const tables={};for(const row of coldRequests){const item=tables[row.table]??={requests:0,bytes:0,networkMs:0};item.requests++;item.bytes+=row.bytes;item.networkMs+=row.ms;}
  return {status:response.status,elapsedMs,requests:beforeWarm,bytes:coldRequests.reduce((s,r)=>s+r.bytes,0),warm,tables,months:payload.months};
}
(async()=>{
  const baselineRef=process.argv.find(arg=>arg.startsWith('--baseline-ref='))?.slice('--baseline-ref='.length)||'HEAD';
  if(process.argv.includes('--compare')){
    const before=await benchmark(require('node:child_process').execFileSync('git',['show',`${baselineRef}:jitt_hub/worker.js`],{cwd:root,encoding:'utf8'}));
    const after=await benchmark(fs.readFileSync(path.join(root,'jitt_hub/worker.js'),'utf8'));
    require('node:assert/strict').deepEqual(after.months,before.months,'Monthly financial values must be unchanged');
    const summary=({months,tables,...rest})=>rest;
    console.log(JSON.stringify({before:summary(before),after:summary(after),monthlyValuesIdentical:true},null,2));return;
  }
  const source=process.argv.includes('--head')?require('node:child_process').execFileSync('git',['show','HEAD:jitt_hub/worker.js'],{cwd:root,encoding:'utf8'}):fs.readFileSync(path.join(root,'jitt_hub/worker.js'),'utf8');
  const result=await benchmark(source);
  // Aggregate monthly values allow an exact comparison across implementations.
  console.log(JSON.stringify(result,null,2));
})().catch(error=>{console.error(error.message);process.exitCode=1});
