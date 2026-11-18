const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict'),{chromium}=require('playwright');
const root=path.resolve(__dirname,'..'),target='00000000-0000-0000-0000-000000000002';
(async()=>{
  const browser=await chromium.launch({headless:true,channel:'msedge'});
  try{
    const page=await browser.newPage(),errors=[],detailRequests=[];
    page.on('pageerror',error=>errors.push(error.message));
    await page.route('https://hub.test/**',async route=>{
      const url=new URL(route.request().url());
      if(url.pathname==='/api/me')return route.fulfill({status:401,json:{error:'login'}});
      if(url.pathname==='/api/login')return route.fulfill({json:{user:{role:'admin'}}});
      if(url.pathname==='/api/settlement-dashboard'){
        assert.equal(url.searchParams.get('month'),'2026-09');
        return route.fulfill({json:{couriers:[{courierId:'1234',courierName:'Teszt Futár',status:'Reklamáció'}],availableMonths:['2026-09']}});
      }
      if(url.pathname==='/api/courier360'){
        detailRequests.push(url);return route.fulfill({json:{courier:{id:'1234',name:'Teszt Futár'},periodStart:'2026-09-01',sources:[],documents:[],workflowStates:{},complaints:[
          {id:'00000000-0000-0000-0000-000000000001',status:'open',message:'Másik bejelentés'},
          {id:target,status:'open',message:'A kijelölt bejelentés'}]}});
      }
      const file=path.join(root,'jitt_hub',url.pathname==='/'?'index.html':url.pathname.slice(1));
      if(fs.existsSync(file))return route.fulfill({path:file});
      return route.fulfill({status:404,body:'not found'});
    });
    await page.goto(`https://hub.test/?courier=1234&month=2026-09&complaint=${target}`);
    await page.locator('#login-screen').waitFor({state:'visible'});
    assert.equal(detailRequests.length,0,'The e-mail link still requires login');
    await page.locator('#identity').fill('Admin');await page.locator('#password').fill('test-only');
    await page.locator('#login-form button').click();
    await page.locator('#courier-status-dialog[open] #complaint-selector').waitFor();
    assert.equal(await page.locator('#month').inputValue(),'2026-09');
    assert.equal(await page.locator('#complaint-selector').inputValue(),target);
    assert.equal(detailRequests[0].searchParams.get('courier'),'1234');assert.equal(detailRequests[0].searchParams.get('month'),'2026-09');
    assert.deepEqual(errors,[]);
    console.log('Assignment e-mail link: login required, correct month, courier and exact complaint opened');
  }finally{await browser.close()}
})().catch(error=>{console.error(error);process.exitCode=1});
