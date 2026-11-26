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
    const paidBox=page.locator('.courier-status-box').filter({has:page.getByRole('button',{name:/^Kifizetve/})});
    await page.evaluate(()=>{
      for(let i=10;i<=20;i++)data.couriers.push({courierId:String(i),courierName:'Teszt '+i,status:'Kifizetve'});
      renderCouriers();
    });
    assert.equal(await paidBox.locator('.courier-box-person').count(),10);
    await paidBox.getByRole('button',{name:/^Kifizetve/}).click();
    assert.equal(await page.locator('#courier-rows tr[data-index]').count(),13);
    assert.equal(await page.locator('#courier-detail').isVisible(),false);
    await page.locator('#courier-rows tr[data-index]').first().locator('td').first().click();
    assert.equal(await page.locator('#courier-detail').isVisible(),true);
    await page.getByRole('button',{name:'← Állapotok'}).click();
    await page.evaluate(()=>{data.couriers=data.couriers.slice(0,5);renderCouriers()});
    await page.getByRole('button',{name:'Teljes futárlista'}).click();
    const filter=page.getByRole('combobox',{name:'Szűrés elszámolási állapot szerint'});
    assert.match(await filter.textContent(),/Kifizetve \(2\)/);
    assert.equal(await page.locator('#courier-rows tr[data-index]').count(),5);
    await page.evaluate(()=>{data.couriers.push({courierId:'6',courierName:'Elfogadásra váró futár',status:'Elszámolás elfogadásra vár'});renderCouriers()});
    const statusHeader=page.getByRole('button',{name:/^Állapot/});
    const topStatus=page.locator('#courier-rows [data-status-courier]').first();
    for(const status of ['Kifizetve','Elszámolás elfogadásra vár','Számla ellenőrzésre vár','Reklamáció','—','Kifizetve']){
      await statusHeader.click();
      const expected=status==='—'?'–':status;
      assert.equal(await topStatus.textContent(),expected);
      assert.equal(await page.locator('#courier-rows tr[data-index]').count(),6);
    }
    assert.match(await page.locator('#courier-count').textContent(),/Elöl: Kifizetve/);
    assert.equal(await statusHeader.locator('..').getAttribute('aria-sort'),'other');
    await page.evaluate(()=>{
      window.refreshRequests=[];
      window.fetch=async url=>{
        refreshRequests.push(String(url));
        return new Promise(resolve=>{window.finishRefresh=()=>resolve({ok:true,json:async()=>data});});
      };
    });
    const refresh=page.getByRole('button',{name:'Futárlista frissítése'});
    await refresh.click();
    assert.equal(await refresh.isDisabled(),true);
    await page.evaluate(()=>finishRefresh());
    await page.waitForFunction(()=>!document.querySelector('#courier-refresh').disabled);
    assert.deepEqual(await page.evaluate(()=>refreshRequests),['/api/settlement-dashboard?month=2026-10&limit=500']);
    assert.equal(await topStatus.textContent(),'Kifizetve');
    await filter.selectOption('Kifizetve');
    assert.equal(await page.locator('#courier-rows tr[data-index]').count(),2);
    await page.locator('#search').fill('Rácz');
    assert.equal(await page.locator('#courier-rows tr[data-index]').count(),1);
    assert.equal(await page.locator('.courier-filters input[type="number"]').count(),0);
    await page.locator('#search').fill('nincs ilyen futár');
    assert.equal(await page.locator('#courier-rows tr[data-index]').count(),0);
    assert.match(await page.locator('#courier-detail').textContent(),/Válassz futárt/);
    await page.locator('#search').fill('');
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
    await page.evaluate(()=>{data={couriers:[{courierId:'1',courierName:'Folyamatban levő ügy',status:'Reklamáció / Folyamatban',complaintAssignee:'Bagoly Zoltán'},{courierId:'2',courierName:'Új ügy',status:'Reklamáció',complaintAssignee:'Gurzó Balázs'}]};renderCouriers()});
    await filter.selectOption('Reklamáció');assert.equal(await page.locator('#courier-rows tr[data-index]').count(),2,'Complaint family filter retains in-progress cases');
    await filter.selectOption('Reklamáció / Folyamatban');assert.equal(await page.locator('#courier-rows tr[data-index]').count(),1);
    assert.equal(await page.getByRole('columnheader',{name:'Felelős',exact:true}).count(),1);
    assert.match(await page.locator('#courier-rows .courier-assignee').textContent(),/Bagoly Zoltán/);
    assert.equal(await page.locator('#courier-rows tr td').count(),6);
    if(process.env.HUB_STATUS_SCREENSHOT)await page.screenshot({path:process.env.HUB_STATUS_SCREENSHOT});
    assert.deepEqual(errors,[]);
    console.log('Status filter: counts, combined search, empty detail, unknown status and monthly refresh verified');
  }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
