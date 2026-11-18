const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),assert=require('node:assert/strict');
const c={URL,Request,Response,fetch,TextEncoder,TextDecoder,Intl,Date,atob,console};vm.createContext(c);
vm.runInContext(fs.readFileSync(path.join(__dirname,'../jitt_hub/worker.js'),'utf8').replace('export default','const worker ='),c);
const snapshotId='00000000-0000-0000-0000-000000000001';
const invoice=(id,title,note,uploaded_at='2026-11-18T10:00:00Z')=>({id,title,note,document_type:'invoice',uploaded_at,uploaded_by:'Futár'});
const base={courierId:'1234',periodStart:'2026-10-01',profile:{courier_name:'Teszt Futár',company_name:'Teszt EV',bank_account_number:'11111111-22222222-33333333'},
 snapshot:{id:snapshotId,version:3,items:[{section:'finance',item_key:'payable',amount_value:1277772}]},
 paymentSources:[{source_key:'tig_breakdown',payload:{finalTotalHuf:1277772,cashGrossHuf:34656,rows:[]}}],
 documents:[invoice('transfer','Számla TESZT-24','bruttó összesen: 1 277 772 Ft'),invoice('cash','KP számla TESZT-KP-08','Fizetési mód: kp; bruttó összesen: 34 656 Ft')],
 workflowStates:{invoice_check:{status:'done',updated_at:'2026-11-18T11:00:00Z',updated_by:'Admin'}},sources:[]};
(async()=>{
 let p=c.courier360Payment(base);
 assert.equal(p.transfer.result,'match');assert.equal(p.cash.result,'match');assert.equal(p.amountHuf,1277772,'Cash must not be added to the bank transfer');assert.equal(p.canClose,true);
 assert.equal(p.paymentNote,'1234-TESZT-24');assert.equal(p.events.filter(e=>e.kind==='current_state').length,1);
 p=c.courier360Payment({...base,documents:[...base.documents,invoice('new','Számla TESZT-25','bruttó összesen: 1 277 000 Ft','2026-11-18T12:00:00Z')]});
 assert.equal(p.transfer.document.id,'new');assert.equal(p.transfer.result,'mismatch');assert.equal(p.transfer.check,null);assert.equal(p.canClose,false);
 p=c.courier360Payment({...base,documents:[...base.documents,{...invoice('advance','Számla ADV-1','bruttó összesen: 100 Ft','2026-11-18T13:00:00Z'),document_type:'process:advance_1:invoice'},invoice('expense','Számla EXP-1','Folyamat azonosító: expense_1; bruttó összesen: 200 Ft','2026-11-18T14:00:00Z')]});
 assert.equal(p.transfer.document.id,'transfer','Other processes must not replace monthly invoices');assert.equal(p.events.some(e=>e.detail.includes('ADV-1')||e.detail.includes('EXP-1')),false);
 p=c.courier360Payment({...base,paymentSources:[],documents:[invoice('transfer','Számla TESZT-24','Nincs összeg') ]});
 assert.equal(p.transfer.expectedHuf,null);assert.equal(p.transfer.actualHuf,null);assert.equal(p.cash.expectedHuf,null);assert.equal(p.transfer.result,'unknown');
 p=c.courier360Payment({...base,paymentSources:[{source_key:'tig_breakdown',payload:{finalTotalHuf:1277772,cashGrossHuf:0}}],documents:[base.documents[0]]});assert.equal(p.cash.result,'not_required');
 p=c.courier360Payment({...base,documents:[base.documents[0]]});assert.equal(p.cash.result,'missing');assert.equal(p.canClose,false);
 const replacement={...invoice('kp-new','KP számla NEW-KP','Fizetési mód: kp; bruttó összesen: 34 656 Ft','2026-11-18T12:00:00Z'),document_type:'process:kp_invoice_202610:invoice'};
 p=c.courier360Payment({...base,documents:[...base.documents,replacement]});assert.equal(p.cash.document.id,'kp-new');assert.equal(p.cash.check,null);assert.equal(p.canClose,false);
 p=c.courier360Payment({...base,documents:[...base.documents,replacement],processStates:[{action_key:'process:kp_invoice_202610:invoice_check',status:'done',updated_at:'2026-11-18T13:00:00Z'}]});assert.equal(p.cash.check.status,'done');assert.equal(p.canClose,true);
 p=c.courier360Payment({...base,sources:[{table:'courier_finance_snapshot_source',available:false}]});assert.equal(p.canClose,false);
 p=c.courier360Payment({...base,profile:{}});assert.equal(p.canClose,false);
 p=c.courier360Payment({...base,snapshot:{...base.snapshot,items:[{section:'finance',item_key:'payable',amount_value:0}]}});assert.equal(p.amountHuf,0);
 p=c.courier360Payment({...base,closure:{status:'done',payable_huf:100,bank_account_number:'saved-bank',recipient_name:'Saved name',closed_at:'2026-11-17T12:00:00Z',closed_by:'Old admin'}});
 assert.equal(p.amountHuf,100);assert.equal(p.bankAccount,'saved-bank');assert.equal(p.recipientName,'Saved name');assert.equal(p.closed,true);assert.equal(p.canClose,false);
 assert.equal(c.paymentDocumentAmount({note:'bruttó összesen: 1.277.772,00 Ft'}),1277772);
 assert.equal(c.paymentDocumentAmount({note:'Összeg: 0 Ft'}),0);
 const worker=vm.runInContext('worker',c);
 assert.equal((await worker.fetch(new Request('https://test/api/courier360-payment-close',{method:'POST'}),{})).status,401);
 assert.equal((await worker.fetch(new Request('https://test/api/courier360-payment-close'),{})).status,405);
 const body={courierId:'1234',month:'2026-10',snapshotId,note:'Kifizetve: 1 277 772 Ft'};
 const request=(value=body,origin='https://test')=>new Request('https://test/api/courier360-payment-close',{method:'POST',headers:{origin,'content-type':'application/json'},body:JSON.stringify(value)});
 let calls=0;c.fetch=async(url,options)=>{calls++;assert.match(url,/rpc\/pwa_close_monthly_payment$/);const value=JSON.parse(options.body);assert.equal(value.p_actor,'Admin');assert.equal(value.p_snapshot_id,snapshotId);assert.equal(value.p_invoice_number,'TESZT-24');return new Response(JSON.stringify({ok:true}));};
 const payment=c.courier360Payment(base);c.courier360Data=async()=>new Response(JSON.stringify({payment}));
 assert.equal((await c.courier360ClosePayment(request(body,'https://evil.test'),{},{})).status,403);
 assert.equal((await c.courier360ClosePayment(request({...body,snapshotId:'bad'}),{},{})).status,400);
 assert.equal((await c.courier360ClosePayment(request({...body,note:'Paid'}),{},{})).status,422);
 assert.equal((await c.courier360ClosePayment(request({...body,snapshotId:'00000000-0000-0000-0000-000000000002'}),{},{})).status,409);
 assert.equal(calls,0,'No writes before a validated explicit action');
 let response=await c.courier360ClosePayment(request(),{SUPABASE_URL:'https://db.test',SUPABASE_SERVICE_ROLE_KEY:'test-only'}, {username:'Admin'});
 assert.equal(response.status,200);assert.equal(calls,1);
 c.courier360Data=async()=>new Response(JSON.stringify({payment:{...payment,closed:true}}));
 response=await c.courier360ClosePayment(request(),{},{});assert.equal((await response.json()).alreadyClosed,true);assert.equal(calls,1);
 c.courier360Data=async()=>new Response(JSON.stringify({payment:{...payment,canClose:false,blockingReasons:['Hiányzó adat']}}));
 assert.equal((await c.courier360ClosePayment(request(),{},{})).status,409);assert.equal(calls,1);
 console.log('Payment detail: latest monthly invoices, cash separation, missing vs zero, saved closure, fresh approval, origin/auth, stale snapshot and atomic RPC verified (mocked writes only)');
})().catch(e=>{console.error(e);process.exitCode=1});
