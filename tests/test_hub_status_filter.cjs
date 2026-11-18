const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {chromium}=require('playwright');
(async()=>{
  const root=path.join(__dirname,'..'),html=fs.readFileSync(path.join(root,'jitt_hub/index.html'),'utf8');
  const script=html.match(/<script>([\s\S]*?)<\/script>/)[1];
  const browser=await chromium.launch({headless:true,channel:'msedge'});
  try{
    const page=await browser.newPage({viewport:{width:1450,height:1000}});
    const errors=[];page.on('pageerror',e=>errors.push(e.message));
    const shell=html.replace(/<script[\s\S]*?<\/script>/g,'').replace(/<link[^>]+>/g,'');
    await page.setContent(shell);
    await page.addScriptTag({content:"window.fetch=async()=>({ok:false,status:401,json:async()=>({})});"});
    await page.addScriptTag({content:fs.readFileSync(path.join(root,'jitt_hub/trends.js'),'utf8')});
    await page.addScriptTag({content:script});
    await page.evaluate(()=>{
      showApp();document.querySelectorAll('.board').forEach(el=>el.hidden=el.dataset.view!=='couriers');
      document.querySelector('#month').innerHTML='<option>2026-10</option>';
      data={couriers:[
        {courierId:'1',courierName:'Rácz Csaba',status:'Kifizetve',payable:100000,deductionImpact:0},
        {courierId:'2',courierName:'Hervai Olivér',status:'Kifizetve',payable:200000,deductionImpact:10000},
        {courierId:'3',courierName:'Teszt Futár',status:'Reklamáció',payable:50000,deductionImpact:5000},
        {courierId:'4',courierName:'Másik Futár',status:'Számla ellenőrzésre vár',payable:80000,deductionImpact:0},
        {courierId:'5',courierName:'Hiányzó Állapot',status:'',payable:0,deductionImpact:0}]};
      renderCouriers();
    });
    const filter=page.getByRole('combobox',{name:'Szűrés elszámolási állapot szerint'});
    assert.match(await filter.textContent(),/Kifizetve \(2\)/);
    assert.equal(await page.locator('#courier-rows tr[data-index]').count(),5);
    await filter.selectOption('Kifizetve');
    assert.equal(await page.locator('#courier-rows tr[data-index]').count(),2);
    await page.locator('#search').fill('Rácz');
    assert.equal(await page.locator('#courier-rows tr[data-index]').count(),1);
    await page.locator('#payable-min').fill('150000');
    assert.equal(await page.locator('#courier-rows tr[data-index]').count(),0);
    assert.match(await page.locator('#courier-detail').textContent(),/Válassz futárt/);
    await page.locator('#search').fill('');await page.locator('#payable-min').fill('');
    await filter.selectOption('Reklamáció');
    assert.equal(await page.locator('#courier-rows tr[data-index]').count(),1);
    assert.match(await page.locator('#courier-rows').textContent(),/Teszt Futár/);
    await filter.selectOption('Állapot nem elérhető');
    assert.match(await page.locator('#courier-rows').textContent(),/Hiányzó Állapot/);
    await page.evaluate(()=>{data={couriers:[{courierId:'6',courierName:'Új hónap',status:'Kifizetve'}]};renderCouriers()});
    assert.equal(await filter.inputValue(),'','Unavailable status resets on new monthly data');
    assert.equal(await page.locator('#courier-rows tr[data-index]').count(),1);
    await filter.selectOption('Kifizetve');await page.evaluate(()=>renderCouriers());
    assert.equal(await filter.inputValue(),'Kifizetve','Selected status survives rerender');
    await page.screenshot({path:path.join(root,'tmp/status-filter-preview.png')});
    assert.deepEqual(errors,[]);
    console.log('Status filter: counts, combined search/amount filtering, empty detail, unknown status and monthly refresh verified');
  }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
