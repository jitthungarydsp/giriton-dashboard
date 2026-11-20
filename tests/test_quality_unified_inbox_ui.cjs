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
      window.reads=[];window.writes=[];window.converted=false;
      window.api=async(url,options)=>{
        if(options?.method==='POST'){
          writes.push(url);converted=true;return {ok:true,item:{id:'converted'}};
        }
        reads.push(url);
        const offset=Number(new URL('http://test'+url).searchParams.get('offset'));
        if(url.includes('/complaints?'))return {items:offset===0?Array.from({length:50},(_,i)=>({id:'c'+i,courier_id:i,courier_name:i===0?'Hegedüs Dávid':'Futár '+i,status:i===1?'closed':'open',created_at:'2026-11-19T11:00:00Z',message:i===0?'Egyik címen feltartottak.':'Bejelentés',affected_items:[{date:'2026-11-06'}]})):[{id:'last',courier_name:'Utolsó oldali futár',status:'forwarded',created_at:'2026-11-18T11:00:00Z'},...(converted?[{id:'converted',courier_id:99,courier_name:'Automata Futár',status:'open',created_at:'2026-11-20T12:00:00Z',message:'Automatikus késés',affected_items:[{signalKind:'route',signalId:'99',signalOrigin:'automatic'}]}]:[])],canManage:true,hasMore:offset===0};
        return {alerts:offset===0?[{id:99,courier_id:99,courier_name:'Automata Futár',status:'auto',alert_type:'delay',created_at:'2026-11-20T12:00:00Z',message:'Automatikus késés',...(converted?{complaint:{id:'converted',status:'open'}}:{})},{id:98,courier_id:98,courier_name:'<img src=x onerror="window.injected=1">',alert_type:'problem',status:'new',message:'<script>Hibás cím</script>',created_at:'2026-11-20T11:00:00Z'}]:[],shifts:[],hasMore:false};
      };
    });
    await page.addScriptTag({content:source.slice(source.indexOf('function qualityComplaintStatus('),source.indexOf('async function openQualityInboxAction('))});
    await page.addScriptTag({content:source.split('\n').find(line=>line.startsWith('$("#quality-complaints-filter").addEventListener'))});
    await page.evaluate(()=>loadQualityComplaints());
    assert.equal(await page.locator('.quality-inbox-item').count(),53);
    assert.ok((await page.locator('#quality-complaints-status').innerText()).includes('53 jelzés'));
    assert.ok(await page.getByText('Utolsó oldali futár',{exact:true}).count());
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
    await page.waitForFunction(()=>document.querySelectorAll('.quality-inbox-item').length===52);
    assert.equal(await page.getByText('Automata Futár',{exact:true}).count(),0);
    await page.selectOption('#quality-complaints-filter','all');
    await page.waitForFunction(()=>document.querySelectorAll('.quality-inbox-item').length===53);
    assert.ok((await page.locator('#quality-complaints-status').innerText()).includes('minden találat egy oldalon'));
    assert.ok(await page.evaluate(()=>reads.every(x=>!x.includes('courier=')&&!x.includes('complaint='))));
    await page.setViewportSize({width:390,height:844});
    await page.locator('[data-complaint-id="c0"] > summary').click();
    await page.screenshot({path:path.join('tmp','quality-unified-inbox-mobile.png'),fullPage:false});
    assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'Mobile layout must fit');
    assert.deepEqual(errors,[]);
    console.log('Unified inbox UI passed: all 53 entries, source filters, closed cases, safe text, signal conversion without duplicate, mobile layout.');
  }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
