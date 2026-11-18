/* Authenticated assignment workspace. Personal tasks never grant global admin access. */
window.JittComplaintAssignments=(()=>{
  let context=null,scope='mine',month='',offset=0,sequence=0,dialogSequence=0,handledLink=false;
  let current=null,profiles=[];
  const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const text=value=>String(value||'').normalize('NFD').replace(/\p{Diacritic}/gu,'').toLowerCase();
  const stamp=value=>value?new Date(value).toLocaleString('hu-HU'):'Nincs rögzítve';
  const admin=()=>Boolean(context?.getUser()?.canViewSettlementDashboard)||['admin','superadmin'].includes(context?.getUser()?.role);
  const uuid=()=>crypto.randomUUID?.()||'10000000-1000-4000-8000-100000000000'.replace(/[018]/g,c=>(Number(c)^crypto.getRandomValues(new Uint8Array(1))[0]&15>>Number(c)/4).toString(16));
  const statuses={new:'Reklamáció',open:'Reklamáció',in_progress:'Reklamáció / Folyamatban',resolved:'Lezárva',closed:'Lezárva'};
  function configure(value){context=value}
  function reset(){sequence++;dialogSequence++;current=null;profiles=[];scope='mine';month='';offset=0;handledLink=false;document.querySelector('#complaint-task-dialog')?.remove();const root=document.querySelector('#complaint-assignments-content');if(root)root.innerHTML='';}
  function query(extra={}){return new URLSearchParams({scope,month,offset:String(offset),...extra})}
  async function mount(root){
    root.innerHTML=`<section class="workflow-header"><div><p class="eyebrow">ÜGYINTÉZÉS</p><h2>Reklamációs feladataim</h2><p class="muted">A PWA-profilodhoz rendelt elszámolási reklamációk és közös megjegyzések.</p></div></section><div class="task-toolbar"><label>Nézet<select data-task-scope><option value="mine">Rám osztott ügyek</option>${admin()?'<option value="all">Összes reklamáció</option>':''}</select></label><label>Hónap (üresen minden hónap)<input data-task-month type="month" value="${esc(month)}"></label><button type="button" class="secondary" data-task-refresh>Frissítés</button></div><div data-task-status role="status"></div><div data-task-list></div><div class="task-pagination"><button class="secondary" data-task-prev ${offset===0?'disabled':''}>Előző oldal</button><button class="secondary" data-task-next disabled>Következő oldal</button></div>`;
    root.querySelector('[data-task-scope]').value=scope;
    root.querySelector('[data-task-scope]').onchange=event=>{scope=event.target.value;offset=0;load(root)};
    root.querySelector('[data-task-month]').onchange=event=>{month=event.target.value;offset=0;load(root)};
    root.querySelector('[data-task-refresh]').onclick=()=>load(root);
    root.querySelector('[data-task-prev]').onclick=()=>{offset=Math.max(0,offset-50);load(root)};
    root.querySelector('[data-task-next]').onclick=()=>{offset+=50;load(root)};
    await load(root);
  }
  async function load(root){
    const request=++sequence,status=root.querySelector('[data-task-status]');status.textContent='Ügyek betöltése…';
    root.querySelector('[data-task-list]').innerHTML='';root.querySelector('[data-task-next]').disabled=true;
    try{
      const result=await context.api('/api/complaint-assignments?'+query(),{silentLoading:true});
      if(request!==sequence)return;
      status.textContent=`${result.items.length} ügy ezen az oldalon`;
      root.querySelector('[data-task-list]').innerHTML=result.items.map(item=>`<article class="process-card task-card"><div class="task-heading"><h3>${esc(item.courier_name||'Futár')} · #${esc(item.courier_id)}</h3><span>${esc(statuses[item.status]||item.status)}</span></div><p>${esc(String(item.document_month).slice(0,7))} · ${esc(item.document_type)}</p><p class="task-text">${esc(item.message)}</p><p><strong>Felelős:</strong> ${esc(item.assignment?.assignee?.name||'Nincs kijelölve')}</p><p>${(item.assignment?.notes||[]).length} közös megjegyzés</p><button type="button" class="secondary" data-task-open="${esc(item.id)}">Megnyitás</button></article>`).join('')||'<div class="empty-card">Ebben a nézetben nincs reklamáció.</div>';
      root.querySelectorAll('[data-task-open]').forEach(button=>button.onclick=()=>open(button.dataset.taskOpen));
      root.querySelector('[data-task-next]').disabled=!result.hasMore;root.querySelector('[data-task-prev]').disabled=offset===0;
    }catch(error){if(request===sequence)status.textContent=error.message}
  }
  function profileOptions(selected,search=''){
    return '<option value="">Válassz PWA-profilt</option>'+profiles.filter(person=>text(person.name+' '+person.courierId).includes(text(search))).map(person=>`<option value="${esc(person.key)}" ${person.key===selected?'selected':''}>${esc(person.name)} · #${esc(person.courierId)}${person.email?'':' · nincs e-mail'}</option>`).join('');
  }
  function renderDialog(item,canManage){
    const dialog=document.querySelector('#complaint-task-dialog');current={item,canManage};
    const assigned=item.assignment,closed=['closed','resolved'].includes(item.status),sent={pending:'Küldésre vár',sending:'Küldés folyamatban',sent:'Elküldve',failed:'Sikertelen',uncertain:'Nem igazolt'}[assigned?.notification?.status]||'Nincs értesítés';
    const selected=assigned?.assignee?.profileKey||('pwa:'+(assigned?.assignee?.username||assigned?.assignee?.name||''));
    dialog.innerHTML=`<div class="task-dialog-head"><h2>Reklamáció · ${esc(item.courier_name||'Futár')}</h2><button type="button" class="icon-button" data-task-close aria-label="Ügy bezárása">×</button></div><p>#${esc(item.courier_id)} · ${esc(String(item.document_month).slice(0,7))} · ${esc(statuses[item.status]||item.status)}</p><blockquote class="task-text">${esc(item.message)}</blockquote><p><strong>Felelős:</strong> ${esc(assigned?.assignee?.name||'Nincs kijelölve')}</p>${assigned?`<p class="muted">Kijelölte: ${esc(assigned.assignedBy)} · ${esc(stamp(assigned.assignedAt))}<br>E-mail-értesítés: ${esc(sent)}</p>`:''}
      ${canManage&&!closed?`<form data-task-assign><h3>PWA-profilhoz rendelés</h3><label>Profil keresése<input type="search" data-task-profile-search placeholder="Név vagy azonosító"></label><label>Felelős PWA-profil<select name="profileKey" required>${profileOptions(selected)}</select></label><label>Megjegyzés a kijelölt kollégának<textarea name="note" rows="3" maxlength="5000" placeholder="Mit nézzen meg az ügyben?"></textarea></label><p class="muted">A megjegyzést a kijelölt kolléga és az adminisztrátorok látják.</p><button type="submit" class="primary">Kijelölés és értesítés</button><p data-task-feedback role="status"></p></form>`:''}
      ${!closed&&item.status!=='in_progress'?'<button type="button" class="secondary" data-task-start>Vizsgálat megkezdése</button><p data-task-start-result role="status"></p>':''}
      <section class="task-notes"><h3>Közös megjegyzések</h3>${(assigned?.notes||[]).map(note=>`<article><strong>${esc(note.author)}</strong><small>${esc(stamp(note.at))}</small><p class="task-text">${esc(note.text)}</p></article>`).join('')||'<p class="muted">Még nincs közös megjegyzés.</p>'}${assigned?`<form data-task-note><label>Új közös megjegyzés<textarea name="text" rows="3" maxlength="5000" required></textarea></label><p class="muted">A kijelölt kolléga és az adminisztrátorok látják. Ez nem a futárnak küldött reklamációválasz.</p><button type="submit" class="secondary">Megjegyzés mentése</button><p data-task-feedback role="status"></p></form>`:''}</section>`;
    dialog.querySelector('[data-task-close]').onclick=()=>dialog.close();
    const assignment=dialog.querySelector('[data-task-assign]');
    if(assignment){
      assignment.querySelector('[data-task-profile-search]').oninput=event=>{assignment.elements.profileKey.innerHTML=profileOptions(assignment.elements.profileKey.value,event.target.value)};
      assignment.onsubmit=event=>{event.preventDefault();save(assignment,'assign',{profileKey:assignment.elements.profileKey.value,note:assignment.elements.note.value})};
    }
    const note=dialog.querySelector('[data-task-note]');if(note)note.onsubmit=event=>{event.preventDefault();save(note,'notes',{text:note.elements.text.value})};
    const start=dialog.querySelector('[data-task-start]');if(start)start.onclick=async()=>{
      const revision=dialogSequence;start.disabled=true;
      const noteDraft=dialog.querySelector('[data-task-note]')?.elements.text.value,assignDraft=dialog.querySelector('[data-task-assign]');
      const assignmentDraft=assignDraft?{profile:assignDraft.elements.profileKey.value,note:assignDraft.elements.note.value}:null;
      try{await context.api(`/api/complaint-assignments/${encodeURIComponent(item.id)}/start`,{method:'POST',silentLoading:true,body:'{}'});if(revision===dialogSequence&&dialog.open){renderDialog({...item,status:'in_progress'},canManage);const noteForm=dialog.querySelector('[data-task-note]'),assignmentForm=dialog.querySelector('[data-task-assign]');if(noteForm&&noteDraft!==undefined)noteForm.elements.text.value=noteDraft;if(assignmentForm&&assignmentDraft){assignmentForm.elements.profileKey.value=assignmentDraft.profile;assignmentForm.elements.note.value=assignmentDraft.note}const root=document.querySelector('#complaint-assignments-content');if(root?.querySelector('[data-task-list]'))load(root)}}
      catch(error){if(revision===dialogSequence){start.disabled=false;dialog.querySelector('[data-task-start-result]').textContent=error.message}}
    };
  }
  async function save(form,action,fields){
    if(form.dataset.saving||!current)return;
    const captured=current,revision=dialogSequence,assignment=captured.item.assignment;
    const signature=JSON.stringify(fields);if(form.dataset.signature!==signature){form.dataset.signature=signature;form.dataset.operation=uuid()}
    form.dataset.saving='true';form.querySelectorAll('button').forEach(button=>button.disabled=true);form.querySelector('[data-task-feedback]').textContent='Mentés…';
    try{
      const result=await context.api(`/api/complaint-assignments/${encodeURIComponent(captured.item.id)}/${action}`,{method:'POST',silentLoading:true,body:JSON.stringify({...fields,operationId:form.dataset.operation,expectedAssignmentId:assignment?.assignmentId||'',expectedNotesRevision:assignment?.notesRevision||''})});
      if(revision!==dialogSequence||!document.querySelector('#complaint-task-dialog')?.open)return;
      renderDialog({...captured.item,assignment:result.assignment},captured.canManage);
      const root=document.querySelector('#complaint-assignments-content');if(root?.querySelector('[data-task-list]'))load(root);
    }catch(error){if(revision===dialogSequence){form.querySelector('[data-task-feedback]').textContent=error.message;delete form.dataset.saving;form.querySelectorAll('button').forEach(button=>button.disabled=false)}}
  }
  async function open(id){
    if(!context?.getUser())return;
    let dialog=document.querySelector('#complaint-task-dialog');if(!dialog){dialog=document.createElement('dialog');dialog.id='complaint-task-dialog';dialog.className='task-dialog';document.body.appendChild(dialog);dialog.addEventListener('close',()=>{dialogSequence++;current=null})}
    const request=++dialogSequence;dialog.innerHTML='<p role="status">Reklamáció betöltése…</p>';if(!dialog.open)dialog.showModal();
    try{
      const [result,people]=await Promise.all([context.api('/api/complaint-assignments?'+new URLSearchParams({scope:admin()?'all':'mine',complaint:id}),{silentLoading:true}),admin()?context.api('/api/complaint-assignment-profiles',{silentLoading:true}):Promise.resolve({profiles:[]})]);
      if(request!==dialogSequence||!dialog.open)return;profiles=people.profiles||[];
      if(!result.items[0])throw Error('A reklamáció nem található, vagy már nem hozzád tartozik.');
      renderDialog(result.items[0],result.canManage);
    }catch(error){if(request===dialogSequence&&dialog.open){dialog.innerHTML=`<p role="alert">${esc(error.message)}</p><button class="secondary" type="button" data-task-error-close>Bezárás</button>`;dialog.querySelector('button').onclick=()=>dialog.close()}}
  }
  function openFromLocation(){const id=new URL(location.href).searchParams.get('complaintTask');if(id&&!handledLink&&/^[0-9a-f-]{36}$/i.test(id)){handledLink=true;context.navigate();open(id)}}
  document.addEventListener('click',event=>{const button=event.target.closest('[data-pwa-complaint-assignment]');if(button){event.stopPropagation();open(button.dataset.pwaComplaintAssignment)}},true);
  return {configure,reset,mount,open,openFromLocation};
})();
