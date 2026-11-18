const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),assert=require('node:assert/strict');
const c={URL,Request,Response,fetch,TextEncoder,TextDecoder,Intl,Date,atob,console};vm.createContext(c);
vm.runInContext(fs.readFileSync(path.join(__dirname,'../jitt_hub/worker.js'),'utf8').replace('export default','const worker ='),c);
const env={SUPABASE_URL:'https://db.test',SUPABASE_SERVICE_ROLE_KEY:'test-only'},user={username:'Admin'};
const body={courierId:'1234',bankAccount:'11111111 22222222 33333333'};
const request=(value=body,origin='https://test')=>new Request('https://test/api/courier360-bank-account',{method:'POST',headers:{origin,'content-type':'application/json'},body:JSON.stringify(value)});
(async()=>{
 assert.equal(c.normalizePaymentBankAccount(body.bankAccount),'11111111-22222222-33333333');
 for(const value of ['', '12345','12345678-abcdefgh','HU1111111122222222'])assert.equal(c.normalizePaymentBankAccount(value),null);
 assert.equal(c.normalizePaymentBankAccount('1111111122222222'),'11111111-22222222');
 let profile={courier_id:'1234',bank_account_number:null},calls=[],race=false,auditFail=false,patchFail=false;
 c.supabaseFetch=async(_env,schema,table,params)=>{assert.equal(table,'courier_master');assert.equal(params.courier_id,'eq.1234');return profile?[profile]:[]};
 c.fetch=async(url,options)=>{
   calls.push({url:String(url),options});const value=JSON.parse(options.body);
   if(options.method==='PATCH'){
     const query=new URL(url);assert.equal(query.searchParams.get('courier_id'),'eq.1234');assert.equal(query.searchParams.get('bank_account_number'),profile.bank_account_number==null?'is.null':`eq.${profile.bank_account_number}`);
     assert.equal(value.bank_account_number,'11111111-22222222-33333333');assert.equal(value.billing_data_source,'jitt_hub_admin');
     assert.equal('courier_name' in value,false,'Other profile fields must stay unchanged');
     return new Response(JSON.stringify(race?[]:[{courier_id:'1234'}]),{status:patchFail?403:200});
   }
   assert.equal(options.method,'POST');assert.match(String(url),/courier_profile_change_log$/);assert.equal(value.changed_by,'Admin');assert.equal(value.changed_fields.bank_account_number.new,'11111111-22222222-33333333');
   return new Response(null,{status:auditFail?500:201});
 };
 assert.equal((await c.courier360SaveBankAccount(request(body,'https://evil.test'),env,user)).status,403);
 assert.equal((await c.courier360SaveBankAccount(request({...body,bankAccount:'bad'}),env,user)).status,422);
 assert.equal((await c.courier360SaveBankAccount(request({...body,courierId:'1234&x=y'}),env,user)).status,400);assert.equal(calls.length,0);
 assert.equal((await c.courier360SaveBankAccount(request(),env,user)).status,200);assert.equal(calls.length,2);
 profile.bank_account_number='  ';calls=[];assert.equal((await c.courier360SaveBankAccount(request(),env,user)).status,200);
 profile.bank_account_number='99999999-99999999';calls=[];assert.equal((await c.courier360SaveBankAccount(request(),env,user)).status,409);assert.equal(calls.length,0);
 profile.bank_account_number='11111111-22222222-33333333';assert.equal((await (await c.courier360SaveBankAccount(request(),env,user)).json()).alreadySaved,true);assert.equal(calls.length,0);
 profile.bank_account_number=null;race=true;assert.equal((await c.courier360SaveBankAccount(request(),env,user)).status,409);assert.equal(calls.length,1,'No audit claiming a change when another writer won');
 race=false;calls=[];auditFail=true;const result=await (await c.courier360SaveBankAccount(request(),env,user)).json();assert.equal(result.ok,true);assert.ok(result.warning);
 patchFail=true;calls=[];assert.equal((await c.courier360SaveBankAccount(request(),env,user)).status,502);assert.equal(calls.length,1);
 profile=null;assert.equal((await c.courier360SaveBankAccount(request(),env,user)).status,404);
 const worker=vm.runInContext('worker',c);assert.equal((await worker.fetch(request(),env)).status,401);assert.equal((await worker.fetch(new Request('https://test/api/courier360-bank-account'),env)).status,405);
 console.log('Manual bank account: validation, admin/origin checks, persistent profile/audit, concurrent edit protection, idempotency and error handling verified (mocked writes only)');
})().catch(e=>{console.error(e);process.exitCode=1});
