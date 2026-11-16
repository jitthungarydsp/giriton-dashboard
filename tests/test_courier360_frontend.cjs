const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const root=path.resolve(__dirname,'..'),elements=new Map(),events={};
function element(selector){if(!elements.has(selector)){const classes=new Set();elements.set(selector,{value:selector==='#month'?'2026-10':'',innerHTML:'',hidden:false,textContent:'',dataset:{},classList:{contains:c=>classes.has(c),add:c=>classes.add(c),remove:c=>classes.delete(c),toggle(){}},querySelector:s=>element(selector+' '+s),setAttribute(){}})}return elements.get(selector)}
const payload={courier:{id:'6959',name:'Bárándi Bendegúz',warehouse:'BUD2'},date:'2026-11-16',periodStart:'2026-10-01',generatedAt:'2026-11-16T10:00:00Z',
  operational:{currentWorking:null,label:'Nincs friss adat',fresh:false,lastSourceAt:null,attendance:null,shifts:[],nextShift:null,route:null,logs:[],dayStatistics:[]},
  finance:{payable:1184532,deductionImpact:115000,status:'Számla ellenőrzésre vár',salaryAdvanceAdded:0},financeSnapshot:{id:'f',version:10,createdAt:'2026-11-10T09:00:00Z',items:[]},
  complaints:[{document_type:'settlement',message:'<script>unsafe</script>',status:'new',created_at:'2026-11-15T11:00:00Z'}],documents:[{id:'00000000-0000-0000-0000-000000000001',file_name:'invoice.pdf',document_type:'invoice',uploaded_at:'2026-11-10T10:00:00Z'}],workflowStates:{},acceptances:[],eventLog:[],sources:[],closure:null};
const c={console,Intl,Date,window:{scrollY:72,scrollTo(){}},document:{querySelector:element,querySelectorAll:()=>[],addEventListener:(type,f)=>events[type]=f},fetch:async url=>({ok:url.startsWith('/api/courier360?'),status:401,json:async()=>url.startsWith('/api/courier360?')?payload:{error:'login'}})};
vm.createContext(c);vm.runInContext(fs.readFileSync(path.join(root,'jitt_hub/courier360.js'),'utf8'),c);
const html=fs.readFileSync(path.join(root,'jitt_hub/index.html'),'utf8');vm.runInContext(html.match(/<script>([\s\S]*?)<\/script>/)[1],c);
(async()=>{
  c.detail({courierId:'6959',courierName:'Bárándi Bendegúz'});assert.ok(element('#courier-detail').innerHTML.includes('data-open-courier="6959"'));
  await c.openCourier360('6959');assert.ok(element('#app').classList.contains('courier360-open'));assert.ok(element('#courier360-page').innerHTML.includes('Nem állapítható meg'));
  for(const tab of ['shifts','routes','finance','complaints','logs']){events.click({target:{closest:s=>s==='[data-c360-go]'?{dataset:{c360Go:tab}}:null}});const rendered=element('#courier360-page').innerHTML;assert.ok(!rendered.includes('undefined'));assert.ok(!rendered.includes('<script>unsafe</script>'));}
  assert.ok(element('#courier360-page').innerHTML.includes('/api/courier360-document?courier=6959'));
  c.closeCourier360();assert.equal(element('#app').classList.contains('courier360-open'),false);assert.equal(element('#courier360-page').hidden,true);
  console.log('Open button, all six real-data views, escaped complaints, document links and return to list OK');
})().catch(e=>{console.error(e.stack);process.exitCode=1});
