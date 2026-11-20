const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict'),{chromium}=require('playwright');
const source=fs.readFileSync('pwa/app.js','utf8'),html=fs.readFileSync('pwa/index.html','utf8');
const section=html.slice(html.indexOf('<div id="quality-complaints-content"'),html.indexOf('<div id="today-workers-content"')).replace('class="hidden"','');
(async()=>{
  const browser=await chromium.launch({headless:true,channel:'msedge'});
  try{
    const page=await browser.newPage({viewport:{width:1200,height:950}}),errors=[];
    page.on('pageerror',e=>errors.push(e.message));
    await page.setContent(`<meta name="viewport" content="width=device-width,initial-scale=1"><style>${fs.readFileSync('pwa/styles.css','utf8')}</style><main style="max-width:1050px;margin:24px auto;padding:12px">${section}</main>`);
    await page.evaluate(()=>{
      window.$=selector=>document.querySelector(selector);
      window.state={user:{role:'admin'},qualityComplaintFocus:'c0',qualityWorkspaceCourier:'stale-filter',qualityWorkspaceDay:'2026-11-01'};
      window.shortDateTime=value=>String(value||'').slice(0,16).replace('T',' ');
      window.escapeHtml=value=>String(value??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;');
      window.renderComplaintShiftDetails=()=>'';
      window.reads=[];window.writes=[];window.converted=false;window.duplicateClosed=false;
      window.api=async(url,options)=>{
        if(options?.method==='POST'){
          writes.push(url);converted=true;return {ok:true,item:{id:'converted'}};
        }
        reads.push(url);
        const offset=Number(new URL('http://test'+url).searchParams.get('offset'));
        if(url.includes('/complaints?'))return {items:offset===0?Array.from({length:50},(_,i)=>({id:'c'+i,courier_id:i,courier_name:i===0?'Hegedüs Dávid':'Futár '+i,status:i===1?'closed':'open',created_at:'2026-11-19T11:00:00Z',message:i===0?'Egyik címen feltartottak.':'Bejelentés',affected_items:[{date:'2026-11-06'}]})):[{id:'last',courier_name:'Utolsó oldali futár',status:'forwarded',created_at:'2026-11-18T11:00:00Z'},...(converted?[{id:'converted',courier_id:99,courier_name:'Automata Futár',status:'open',created_at:'2026-11-20T12:00:00Z',message:'Automatikus késés',affected_items:[{signalKind:'route',signalId:'99',signalOrigin:'automatic'}]}]:[])],canManage:true,hasMore:offset===0};
        return {alerts:offset===0?[{id:99,courier_id:99,courier_name:'Automata Futár',status:'auto',alert_type:'delay',created_at:'2026-11-20T12:00:00Z',message:'Automatikus késés',...(converted?{complaint:{id:'converted',status:'open'}}:{})},{id:98,courier_id:98,courier_name:'<img src=x onerror="window.injected=1">',alert_type:'problem',status:'new',message:'<script>Hibás cím</script>',created_at:'2026-11-20T11:00:00Z',...(duplicateClosed?{resolution:{reason:'duplicate'}}:{})}]:[],shifts:[],hasMore:false};
      };
    });
    await page.addScriptTag({content:source.slice(source.indexOf('function qualityComplaintStatus('),source.indexOf('async function openQualityInboxAction('))});
    await page.addScriptTag({content:source.split('\n').find(line=>line.startsWith('$("#quality-complaints-filter").addEventListener'))});
    await page.evaluate(()=>loadQualityComplaints());
    assert.equal(await page.locator('.quality-inbox-item').count(),52);
    assert.ok((await page.locator('#quality-complaints-status').innerText()).includes('52 jelzés'));
    assert.equal(await page.getByText('Utolsó oldali futár',{exact:true}).count(),0);
    assert.equal(await page.locator('[data-complaint-id="c0"]').getAttribute('open'),'');
    assert.ok((await page.locator('[data-complaint-id="c1"] > summary').innerText()).includes('Lezárt'));
    assert.equal(await page.locator('#quality-complaints-content select').count(),1);
    assert.equal(await page.locator('#quality-complaints-content img').count(),0);
    assert.equal(await page.evaluate(()=>window.injected),undefined);
    await page.selectOption('#quality-complaints-filter','automatic');
    await page.waitForFunction(()=>document.querySelectorAll('.quality-inbox-item').length===1);
    assert.ok((await page.locator('.quality-inbox-item').innerText()).includes('Automata Futár'));
    await page.locator('.quality-inbox-item summary').click();
    await page.getByRole('button',{name:'Reklamáció kezelése / Google-űrlap'}).click();
    await page.waitForSelector('[data-complaint-id="converted"]');
    assert.equal(await page.locator('.quality-inbox-item').count(),1);
    assert.equal(await page.evaluate(()=>writes.length),1);
    assert.ok((await page.locator('[data-complaint-id="converted"]').innerText()).includes('Automatikus jelzés'));
    await page.selectOption('#quality-complaints-filter','courier');
    await page.waitForFunction(()=>document.querySelectorAll('.quality-inbox-item').length===51);
    assert.equal(await page.getByText('Automata Futár',{exact:true}).count(),0);
    await page.selectOption('#quality-complaints-filter','all');
    await page.waitForFunction(()=>document.querySelectorAll('.quality-inbox-item').length===52);
    assert.ok((await page.locator('#quality-complaints-status').innerText()).includes('minden találat egy oldalon'));
    assert.ok(await page.evaluate(()=>reads.every(x=>!x.includes('courier=')&&!x.includes('complaint='))));
    await page.setViewportSize({width:390,height:844});
    await page.locator('[data-complaint-id="c0"] > summary').click();
    await page.screenshot({path:path.join('tmp','quality-unified-inbox-mobile.png'),fullPage:false});
    assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'Mobile layout must fit');
    assert.deepEqual(errors,[]);
    await page.evaluate(()=>{
      const previous=window.api;
      window.api=async(url,options)=>{
        const result=await previous(url,options);
        if(result.items)result.items=result.items.map(item=>item.id==='c0'?{...item,status:'forwarded'}:item);
        return result;
      };
      return loadQualityComplaints();
    });
    assert.equal(await page.locator('[data-complaint-id="c0"]').count(),0);
    assert.equal(await page.locator('.quality-inbox-item').count(),51);
    assert.ok((await page.locator('#quality-complaints-status').innerText()).includes('51 jelzés'));
    await page.selectOption('#quality-complaints-filter','forwarded');
    await page.waitForFunction(()=>document.querySelectorAll('.quality-inbox-item').length===2);
    assert.equal(await page.locator('[data-complaint-id="c0"]').count(),1);
    assert.equal(await page.locator('[data-complaint-id="last"]').count(),1);
    assert.ok((await page.locator('#quality-complaints-status').innerText()).includes('2 továbbított jelzés'));
    await page.selectOption('#quality-complaints-filter','all');
    await page.waitForFunction(()=>document.querySelectorAll('.quality-inbox-item').length===51);
    await page.evaluate(()=>{
      const previous=window.api;
      window.duplicateAttempts=0;window.failDuplicate=true;
      window.api=async(url,options)=>{
        if(url.endsWith('/route/98/complaint'))return {ok:true,alreadyExists:true,item:{id:'c0',status:'forwarded'}};
        if(url.endsWith('/close-duplicate')){
          duplicateAttempts++;
          if(failDuplicate){failDuplicate=false;throw Error('Teszt mentési hiba');}
          await new Promise(resolve=>setTimeout(resolve,30));
          duplicateClosed=true;
          return {ok:true,resolution:{reason:'duplicate'}};
        }
        return previous(url,options);
      };
    });
    const raw=page.locator('[data-signal-id="signal:route:98"]');
    await raw.evaluate(card=>{card.open=true;});
    await raw.getByRole('button',{name:'Reklamáció kezelése / Google-űrlap'}).click();
    await page.waitForFunction(()=>document.querySelector('#quality-complaints-filter').value==='forwarded');
    assert.equal(await page.locator('[data-complaint-id="c0"]').getAttribute('open'),'');
    await page.selectOption('#quality-complaints-filter','all');
    await page.waitForSelector('[data-signal-id="signal:route:98"]');
    await raw.evaluate(card=>{card.open=true;});
    await raw.getByRole('button',{name:'Lezárás duplikációként'}).click();
    await page.getByRole('button',{name:'Mégsem',exact:true}).click();
    assert.equal(await page.evaluate(()=>duplicateAttempts),0);
    await raw.getByRole('button',{name:'Lezárás duplikációként'}).click();
    await page.locator('[data-duplicate-confirm]').click();
    await page.waitForFunction(()=>document.querySelector('[data-duplicate-status]').textContent==='Teszt mentési hiba');
    assert.equal(await raw.count(),1);
    await page.evaluate(()=>{document.querySelector('[data-duplicate-confirm]').click();document.querySelector('[data-duplicate-confirm]').click();});
    await page.waitForFunction(()=>!document.querySelector('dialog'));
    await page.waitForFunction(()=>document.querySelectorAll('.quality-inbox-item').length===50);
    assert.equal(await raw.count(),0);
    assert.equal(await page.evaluate(()=>duplicateAttempts),2);
    await page.evaluate(()=>loadQualityComplaints());
    assert.equal(await raw.count(),0);
    assert.ok((await page.locator('#quality-complaints-status').innerText()).includes('50 jelzés'));
    assert.deepEqual(errors,[]);
    // Realistic route identities: two reports from one submitted tour, plus a
    // separate tour on the same day. Show IDs even with the cards collapsed.
    await page.evaluate(()=>{
      window.api=async url=>url.includes('/complaints?') ? {items:[{id:'juhasz-sent',courier_id:'9460',courier_name:'Juhász József',topic:'uncleanedTimeWindowLate',status:'forwarded',message:'Beküldött reklamáció',created_at:'2026-11-20T11:20:10Z',affected_items:[{date:'2026-11-20',routeId:'1612799'}],delivery:{state:'sent',route_id:'1612799'}}],hasMore:false,canManage:true} : {alerts:[{id:112,courier_id:9460,courier_name:'Juhász József',route_id:'1612799',alert_type:'problem',message:'Második jelzés',created_at:'2026-11-20T10:16:13Z'},{id:114,courier_id:9460,courier_name:'Juhász József',route_id:'1612800',alert_type:'problem',message:'Másik túra',created_at:'2026-11-20T12:16:13Z'}],shifts:[],hasMore:false};
      document.querySelector('#quality-complaints-filter').value='all';
      return loadQualityComplaints();
    });
    const same=page.locator('[data-signal-id="signal:route:112"]'),other=page.locator('[data-signal-id="signal:route:114"]');
    assert.ok((await same.locator('summary').innerText()).includes('Route ID: 1612799'));
    assert.ok((await other.locator('summary').innerText()).includes('Route ID: 1612800'));
    await same.locator('summary').click();
    assert.ok((await same.innerText()).includes('Ehhez a Route ID-hoz már van reklamáció: Továbbított'));
    assert.equal(await same.getByRole('button',{name:'Meglévő reklamáció megnyitása'}).count(),1);
    assert.equal(await other.getByRole('button',{name:'Meglévő reklamáció megnyitása'}).count(),0);
    await page.selectOption('#quality-complaints-filter','unrecorded');
    assert.equal(await page.locator('.quality-inbox-item').count(),1);
    assert.ok((await page.locator('.quality-inbox-item > summary').innerText()).includes('1612800'));
    assert.ok((await page.locator('#quality-complaints-status').innerText()).includes('1 külön túra'));
    await page.selectOption('#quality-complaints-filter','pending-forward');
    assert.equal(await page.locator('.quality-inbox-item').count(),0);
    // A new case must remain visible after conversion from the unrecorded filter.
    await page.evaluate(()=>{
      const previous=window.api;
      window.convertedRoute=false;
      const created={id:'created-route',courier_id:'9460',courier_name:'Juhász József',topic:'uncleanedTimeWindowLate',status:'open',created_at:'2026-11-20T13:00:00Z',message:'Másik túra',affected_items:[{date:'2026-11-20',routeId:'1612800',signalKind:'route',signalId:'114'}]};
      window.api=async(url,options)=>{
        if(url.endsWith('/route/114/complaint')&&options?.method==='POST'){convertedRoute=true;return {ok:true,item:created};}
        const result=await previous(url,options);
        if(convertedRoute&&result.items)result.items.push(created);
        return result;
      };
    });
    await page.selectOption('#quality-complaints-filter','unrecorded');
    await page.locator('[data-signal-id="signal:route:114"] > summary').click();
    await page.locator('[data-signal-id="signal:route:114"]').getByRole('button',{name:'Reklamáció kezelése / Google-űrlap'}).click();
    await page.locator('[data-complaint-id="created-route"][open]').waitFor();
    assert.equal(await page.locator('#quality-complaints-filter').inputValue(),'pending-forward');
    assert.equal(await page.locator('[data-complaint-id="created-route"]').getByRole('button',{name:'Továbbítás',exact:true}).isEnabled(),true);
    await page.selectOption('#quality-complaints-filter','forwarded');
    assert.ok((await page.locator('[data-complaint-id="juhasz-sent"] > summary').innerText()).includes('Beküldött Route ID: 1612799'));
    await page.setViewportSize({width:390,height:844});
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+2),true);
    if(process.env.QUALITY_ROUTE_SCREENSHOT)await page.screenshot({path:process.env.QUALITY_ROUTE_SCREENSHOT});
    console.log('Unified inbox UI passed: source and forwarded filters, existing daily case navigation, duplicate confirmation/cancel/retry, persisted closure, accurate counts, mobile layout.');
  }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
