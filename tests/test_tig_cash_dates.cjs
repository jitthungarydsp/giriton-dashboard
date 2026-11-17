const fs=require('node:fs');
const vm=require('node:vm');
const assert=require('node:assert/strict');
const source=fs.readFileSync(require('node:path').join(__dirname,'../pwa/app.js'),'utf8');
const start=source.indexOf('function renderTigBreakdown(');
const end=source.indexOf('\nfunction ',start+1);
const ctx={state:{workflowMonth:'2026-10'},escapeHtml:String,tigValue:String,workflowTigDownloadUrl:()=>'/test.pdf'};
vm.createContext(ctx);vm.runInContext(source.slice(start,end),ctx);
const tig={available:true,finalTotalHuf:100000,buyer:{name:'Vevő',performanceDate:'2026-11-25',paymentDueDate:'2026-11-25'},
  seller:{name:'Eladó'},cashDocumentMeta:{performanceDate:'2026-11-17',paymentDueDate:'2026-11-17'},
  rows:[{key:'cash_service',label:'KP',netHuf:34656,grossHuf:34656,performanceDate:'2026-11-17',paymentDueDate:'2026-11-17'}]};
const html=ctx.renderTigBreakdown(tig);
const cash=html.split('<section class="tig-cash-invoice">')[1];
assert(cash.includes('Teljesítés: 2026-11-17'));
assert(cash.includes('Fizetési határidő: 2026-11-17'));
assert(!cash.includes('2026-11-25'));
assert(html.split('<section class="tig-cash-invoice">')[0].includes('2026-11-25'));
assert.equal(tig.buyer.performanceDate,'2026-11-25');
console.log('Cash buyer, line dates and unchanged transfer dates verified');
