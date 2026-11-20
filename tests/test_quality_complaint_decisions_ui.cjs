const fs=require('node:fs'),assert=require('node:assert/strict'),{chromium}=require('playwright');
const source=fs.readFileSync('pwa/app.js','utf8');
(async()=>{
  const browser=await chromium.launch({headless:true,channel:'msedge'});
  try{
    const page=await browser.newPage({viewport:{width:390,height:844}}),errors=[];
    page.on('pageerror',error=>errors.push(error.message));
    await page.setContent(`<meta name="viewport" content="width=device-width,initial-scale=1"><style>${fs.readFileSync('pwa/styles.css','utf8')}</style><main style="max-width:800px;margin:auto;padding:12px"><div id="result"></div></main>`);
    await page.evaluate(()=>{
      window.state={user:{},statisticsMonth:'2026-11'};
      window.escapeHtml=value=>String(value??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;');
      window.shortDateTime=value=>String(value||'').slice(0,16).replace('T',' ');
      window.cases=[{id:'roland',topic:'uncleanedTimeWindowLate',status:'closed',admin_response:'Duplikáció',message:'Baleset az M1/M7 bevezetőjén.',created_at:'2026-11-10T10:50:00Z',affected_items:[{signalKind:'route',signalId:'73',date:'2026-11-10'}],partnerDecision:{status:'accepted',reason:'Elfogadva',reference:'P-261112-999',respondedAt:'2026-11-19T18:11:24Z'}}];
    });
    await page.addScriptTag({content:source.slice(source.indexOf('function qualityComplaintStatus('),source.indexOf('async function loadQualityComplaints('))});
    await page.addScriptTag({content:source.slice(source.indexOf('function renderCourierRouteSignals('),source.indexOf('function qualityShiftTimes('))});
    await page.evaluate(()=>document.querySelector('#result').innerHTML=renderCourierQualityComplaints({qualityComplaints:cases,routeSignals:{alerts:[{id:73,route_id:'1600493',message:'Baleset'}],shifts:[]}}));
    assert.equal(await page.locator('.courier-complaint-top .courier-complaint-badge').innerText(),'Kifli elfogadta');
    assert.equal(await page.locator('.partner-decision').count(),2);
    assert.ok((await page.locator('.partner-decision').first().innerText()).includes('P-261112-999'));
    assert.ok(!(await page.locator('#result').innerText()).includes('Duplikáció'));
    await page.locator('.courier-complaint-card > details > summary').click();
    assert.ok((await page.locator('#result').innerText()).includes('Korábbi adminválasz: Duplikáció'));
    await page.locator('.courier-complaint-card > details > summary').click();
    assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
    await page.screenshot({path:'tmp/partner-decision-mobile.png',fullPage:true});
    await page.evaluate(()=>{
      cases=[{...cases[0],partnerDecision:{status:'rejected',reason:'<img src=x onerror="window.injected=1">',respondedAt:'2026-11-20T12:00:00Z'}},
             {...cases[0],id:'partial',partnerDecision:{status:'partially_accepted',reason:'Egy cím elfogadva.',respondedAt:'2026-11-20T12:00:00Z'}},
             {...cases[0],id:'pending',status:'forwarded',partnerDecision:null,admin_response:''}];
      document.querySelector('#result').innerHTML=renderCourierQualityComplaintCards({qualityComplaints:cases,partnerDecisionsAvailable:false});
    });
    assert.deepEqual(await page.locator('.courier-complaint-badge').allTextContents(),['Kifli elutasította','Kifli részben elfogadta','Továbbított']);
    assert.equal(await page.locator('#result img').count(),0);
    assert.equal(await page.evaluate(()=>window.injected),undefined);
    assert.ok((await page.locator('#result').innerText()).includes('A Kifli-válaszok most nem érhetők el'));
    assert.equal(await page.locator('[data-complaint-action]').count(),0);
    assert.deepEqual(errors,[]);
    console.log('Courier decision UI passed: accepted/rejected/partial, original history, linked raw signal, response time/reference, escaping, error state, mobile layout.');
  }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
