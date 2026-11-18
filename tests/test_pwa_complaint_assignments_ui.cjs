const fs=require('node:fs'),assert=require('node:assert/strict'),{chromium}=require('playwright');
const id='00000000-0000-0000-0000-000000000001';
(async()=>{
  const browser=await chromium.launch({headless:true,channel:'msedge'});
  try{
    const page=await browser.newPage({viewport:{width:1100,height:1000}}),errors=[];page.on('pageerror',e=>errors.push(e.message));
    await page.setContent(`<style>${fs.readFileSync('pwa/complaint_assignments.css','utf8')}</style><div id="complaint-assignments-content"></div><button type="button" data-pwa-complaint-assignment="${id}">Kijelölés</button>`);
    await page.addScriptTag({content:fs.readFileSync('pwa/complaint_assignments.js','utf8')});
    await page.evaluate(id=>{
      window.user={username:'Admin',courierId:'0',role:'admin'};window.writes=[];
      window.item={id,courier_id:'8764',courier_name:'Teszt Futár',document_month:'2026-10-01',document_type:'settlement',status:'new',message:'Hiányzó bónusz <img src=x onerror=alert(1)>'};
      window.people=[{key:'pwa:Bagoly Zoltán',profileKey:'pwa:Bagoly Zoltán',username:'Bagoly Zoltán',name:'Bagoly Zoltán',courierId:'12345',email:'zoltan.bagoly@jitt.hu'},{key:'pwa:Gurzó Balázs',username:'Gurzó Balázs',name:'Gurzó Balázs',courierId:'7644'}];
      const api=async(url,options={})=>{
        const manager=user.role==='admin';
        if(url.includes('assignment-profiles'))return {profiles:people};
        if(options.method==='POST'){
          const body=JSON.parse(options.body);writes.push({url,body});await new Promise(resolve=>setTimeout(resolve,30));
          if(url.endsWith('/assign'))item.assignment={assignmentId:body.operationId,notesRevision:body.operationId,assignee:people.find(p=>p.key===body.profileKey),assignedBy:user.username,notification:{status:'pending'},notes:body.note?[{id:body.operationId,text:body.note,author:user.username,at:'2026-11-18T12:00:00Z'}]:[]};
          if(url.endsWith('/notes')){item.assignment.notes.push({id:body.operationId,text:body.text,author:user.username,at:'2026-11-18T12:30:00Z'});item.assignment.notesRevision=body.operationId}
          if(url.endsWith('/start'))item.status='in_progress';
          return {ok:true,assignment:structuredClone(item.assignment)};
        }
        const params=new URL(url,'https://test').searchParams,access=manager&&params.get('scope')==='all'||item.assignment?.assignee?.username===user.username;
        if(params.get('complaint')&&!access)throw Error('Ez az ügy nincs a profilodhoz rendelve.');
        return {items:access?[structuredClone(item)]:[],canManage:manager,hasMore:false};
      };
      JittComplaintAssignments.configure({api,getUser:()=>user,navigate(){}});
      JittComplaintAssignments.mount(document.querySelector('#complaint-assignments-content'));
    },id);
    await page.getByText('Ebben a nézetben nincs reklamáció.',{exact:true}).waitFor();
    await page.locator('[data-task-scope]').selectOption('all');await page.locator('[data-task-list] article').waitFor();
    await page.getByRole('button',{name:'Kijelölés',exact:true}).click();
    await page.getByLabel('Felelős PWA-profil').selectOption('pwa:Bagoly Zoltán');
    await page.getByLabel('Megjegyzés a kijelölt kollégának').fill('Kérlek, nézd meg a műszakokat.');
    await page.locator('[data-task-assign]').evaluate(form=>{form.requestSubmit();form.requestSubmit()});
    await page.locator('.task-notes').getByText('Kérlek, nézd meg a műszakokat.',{exact:true}).waitFor();
    assert.equal(await page.evaluate(()=>writes.length),1);assert.equal(await page.locator('#complaint-task-dialog img').count(),0);
    await page.evaluate(()=>{JittComplaintAssignments.reset();user={username:'Bagoly Zoltán',courierId:'12345',role:'user'};JittComplaintAssignments.mount(document.querySelector('#complaint-assignments-content'))});
    await page.locator('[data-task-open]').click();await page.getByLabel('Új közös megjegyzés').waitFor();
    assert.equal(await page.locator('[data-task-assign]').count(),0,'Assignee gets personal access, not admin assignment powers');
    assert.match(await page.locator('.task-notes').textContent(),/Kérlek, nézd meg/);
    await page.getByLabel('Új közös megjegyzés').fill('Megnéztem, egyeztettem a futárral.');await page.getByRole('button',{name:'Megjegyzés mentése',exact:true}).click();
    await page.locator('.task-notes').getByText('Megnéztem, egyeztettem a futárral.',{exact:true}).waitFor();
    await page.getByRole('button',{name:'Vizsgálat megkezdése',exact:true}).click();await page.locator('#complaint-task-dialog').getByText(/Reklamáció \/ Folyamatban/).waitFor();
    await page.setViewportSize({width:390,height:844});assert(await page.locator('#complaint-task-dialog').evaluate(d=>d.scrollWidth<=d.clientWidth+1));
    await page.evaluate(()=>{JittComplaintAssignments.reset();user={username:'Másik profil',courierId:'88',role:'user'};JittComplaintAssignments.mount(document.querySelector('#complaint-assignments-content'))});
    await page.getByText('Ebben a nézetben nincs reklamáció.',{exact:true}).waitFor();
    assert.deepEqual(errors,[]);console.log('PWA profiles, assignee-only access, shared notes, investigation start, single submit, escaping, session reset and mobile layout OK');
  }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
