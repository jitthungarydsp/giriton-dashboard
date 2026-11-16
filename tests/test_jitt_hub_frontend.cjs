const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),assert=require('node:assert/strict');
const root=path.resolve(__dirname,'..');
const elements=new Map();
function element(selector){
  if(!elements.has(selector))elements.set(selector,{value:selector==='#month'?'2026-10':'',hidden:false,innerHTML:'',textContent:'',dataset:{},
    classList:{toggle(){},contains(){return false}},setAttribute(){},closest(){return element('th '+selector)},querySelector(s){return element(selector+' '+s)}});
  return elements.get(selector);
}
const sortButtons=['deductionImpact','payable'].map(key=>Object.assign(element(key),{dataset:{courierSort:key,sortLabel:key}}));
const navigation=['overview','trends','couriers'].map(key=>Object.assign(element('nav '+key),{dataset:{board:key}}));
const boardElements=navigation.map(n=>Object.assign(element('.board '+n.dataset.board),{dataset:{view:n.dataset.board}}));
const rows=['2026-08','2026-09','2026-10'].map((month,i)=>({month,complaintCount:78+i,bonusHuf:1000,malusHuf:100,responseAverageHours:i?0.02:null,responseTimedCount:i?2:0,advanceCount:0,advanceAmountHuf:0,financeCoveredCouriers:1,courierCount:1}));
const context={console,Intl,Date,document:{querySelector:element,querySelectorAll(selector){
  return selector==='[data-courier-sort]'?sortButtons:selector==='.nav button'?navigation:selector==='.board'?boardElements:[];
}},fetch:async url=>({ok:url.includes('settlement-trends'),status:401,json:async()=>({months:rows})})};
vm.createContext(context);
vm.runInContext(fs.readFileSync(path.join(root,'jitt_hub/trends.js'),'utf8'),context);
const html=fs.readFileSync(path.join(root,'jitt_hub/index.html'),'utf8');
vm.runInContext(html.match(/<script>([\s\S]*?)<\/script>/)[1],context);
(async()=>{
  assert.equal(typeof sortButtons[0].onclick,'function','Sort headers bind without a single-element forEach crash');
  navigation.find(b=>b.dataset.board==='trends').onclick();
  await new Promise(resolve=>setImmediate(resolve));
  const rendered=element('#trend-body').innerHTML;
  assert.ok(rendered.includes('Reklamációk darabszáma'));
  assert.ok(rendered.includes('Hozzáadott fizetési előlegek száma'));
  assert.equal((rendered.match(/<svg /g)||[]).length,4);
  assert.ok(!rendered.includes('NaN'));
  assert.ok(rendered.includes('0,02'));
  assert.ok(rendered.includes('—'));
  assert.equal(element('#trend-status').textContent,'3 hónap · adatbázisból');
  console.log('Full frontend initialization, trend navigation and four-chart rendering OK');
})().catch(e=>{console.error(e);process.exitCode=1});
