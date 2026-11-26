let rekiPayload = null;
let rekiMonth = '';
let rekiRequest = 0;
const rekiText = value => String(value ?? '').normalize('NFD').replace(/\p{Diacritic}/gu, '').toLowerCase();
const rekiTopics = {lateShift:'Műszakkésés', noShow:'No-show', uncleanedTimeWindowLate:'Címkésés', cleanedTimeWindowLate:'Címkésés', inTransitDelay:'Menet közben', inTransitBagMissing:'Táskahiány'};
const rekiForwarded = row => Boolean(row.forwarded_at) || row.status === 'forwarded';
const rekiOpen = row => !rekiForwarded(row) && ['open','new','in_review'].includes(row.status);
const rekiRoutes = row => [...new Set((row.affected_items || []).map(item=>String(item.routeId || item.route_id || '')).filter(Boolean))];
function rekiTopic(row){
  if(row.affected_items?.some(item=>item.signalKind==='route'))return 'Menet közben';
  return rekiTopics[row.topic]||row.topic||'Reklamáció';
}
function rekiDuration(start,end){
  const minutes=Math.round((Date.parse(end)-Date.parse(start))/60000);
  return Number.isFinite(minutes)&&minutes>=0?`${Math.floor(minutes/60)} óra ${minutes%60} perc`:'—';
}
function clearReki(){
  rekiRequest++;
  rekiMonth='';
  rekiPayload=null;
  $('#reki-list').replaceChildren();
  if($('#reki-dialog').open)$('#reki-dialog').close();
}
async function loadReki(){
  const month=$('#month').value, sequence=++rekiRequest;
  if(rekiMonth!==month){rekiPayload=null;$('#reki-list').replaceChildren();}
  $('#reki-count').textContent='Reklamációk betöltése…';
  $('#reki-refresh').disabled=true;
  try{
    const payload=await api('/api/courier-reki?month='+encodeURIComponent(month));
    if(sequence!==rekiRequest)return;
    rekiMonth=month;
    rekiPayload=payload;
    renderReki();
  }catch(error){
    if(sequence===rekiRequest)$('#reki-count').textContent=error.message;
  }finally{
    if(sequence===rekiRequest)$('#reki-refresh').disabled=false;
  }
}
function renderReki(){
  if(!rekiPayload)return;
  const {cases,excel,couriers}=rekiPayload;
  const rows=[...cases,...excel.map(row=>({...row,id:'excel:'+row.id,topic:'uncleanedTimeWindowLate',status:'forwarded',forwarded_at:row.submitted_at,affected_items:[{routeId:row.route_id,date:row.work_date}]}))];
  rows.push(...rekiPayload.signals.map(row=>({...row,id:'signal:'+row.kind+':'+row.id,status:'open',
    topic:row.kind==='shift'?'lateShift':row.alert_type==='bag_missing'?'inTransitBagMissing':'inTransitDelay',
    message:row.message||row.shift_name,affected_items:[{routeId:row.route_id}]})));
  const filter=$('#reki-filter').value,query=rekiText($('#reki-search').value.trim());
  const groups=new Map(couriers.map(row=>[String(row.courier_id),{name:row.courier_name,id:row.courier_id,rows:[],open:0,forwarded:0}]));
  rows.forEach(row=>{
    const id=String(row.courier_id);
    if(!groups.has(id))groups.set(id,{name:row.courier_name,id,rows:[],open:0,forwarded:0});
    const group=groups.get(id);
    group.rows.push(row);
    group.open+=Number(rekiOpen(row));
    group.forwarded+=Number(rekiForwarded(row));
  });
  const result=[...groups.values()].map(group=>{
    const matchesCourier=rekiText(group.name+' '+group.id).includes(query);
    const visible=group.rows.filter(row=>{
      if(!matchesCourier&&!rekiRoutes(row).some(route=>route.includes(query)))return false;
      if(filter==='forwarded')return rekiForwarded(row);
      if(!rekiOpen(row))return false;
      if(filter==='time-window')return ['uncleanedTimeWindowLate','cleanedTimeWindowLate'].includes(row.topic)&&!row.affected_items?.some(item=>item.signalKind==='route');
      if(filter==='in-transit')return /^inTransit/.test(row.topic)||row.affected_items?.some(item=>item.signalKind==='route');
      return true;
    }).sort((a,b)=>String(b.forwarded_at||b.created_at).localeCompare(String(a.forwarded_at||a.created_at)));
    return {...group,visible,show:visible.length||(filter==='all'&&matchesCourier)};
  }).filter(group=>group.show).sort((a,b)=>b.open-a.open||a.name?.localeCompare(b.name,'hu')||String(a.id).localeCompare(String(b.id)));
  $('#reki-count').textContent=`${result.length} futár · ${result.reduce((total,group)=>total+group.visible.length,0)} megjelenített ügy`;
  $('#reki-list').innerHTML=result.map(group=>`<details class="compare-card"><summary><strong>${esc(group.name||'Futár')}</strong> · #${esc(group.id)} · ${group.open} nyitott · ${group.forwarded} továbbított</summary>
    ${group.visible.map(row=>`<p><button type="button" class="c360-button" data-reki-case="${esc(row.id)}" aria-haspopup="dialog">${esc(rekiTopic(row))}${rekiRoutes(row).length?' · Route ID '+esc(rekiRoutes(row).join(', ')):''} · ${c360Date(row.forwarded_at||row.created_at)}</button></p>`).join('')||'<p>Nincs megjeleníthető nyitott ügy.</p>'}
  </details>`).join('')||'<div class="empty">Nincs találat.</div>';
  const byId=new Map(rows.map(row=>[String(row.id),row]));
  $('#reki-list').onclick=event=>{
    const button=event.target.closest('[data-reki-case]');
    if(button)openRekiCase(byId.get(button.dataset.rekiCase));
  };
}
function openRekiCase(row){
  const dialog=$('#reki-dialog');
  $('#reki-title').textContent=`${row.courier_name||'Futár'} · #${row.courier_id}`;
  const query=new URLSearchParams({'hub-quality':rekiForwarded(row)?'forwarded':'open'});
  if(String(row.id).startsWith('signal:'))query.set('quality-search',rekiRoutes(row)[0]||row.courier_id);
  else query.set('quality-case',row.id);
  $('#reki-case').innerHTML=`<h3>${esc(rekiTopic(row))}</h3>
    <p>${rekiRoutes(row).length?'Route ID '+esc(rekiRoutes(row).join(', ')):''}</p>
    ${row.message?`<p>${esc(row.message)}</p>`:''}
    <p>${rekiForwarded(row)?'Továbbítva':'Nyitott'}</p>
    <dl><dt>Beküldve</dt><dd>${c360Date(row.created_at)}</dd><dt>Továbbítva</dt><dd>${c360Date(row.forwarded_at)}</dd><dt>Válasz érkezett</dt><dd>${c360Date(row.responded_at)}</dd><dt>Beküldéstől továbbításig</dt><dd>${rekiDuration(row.created_at,row.forwarded_at)}</dd><dt>Továbbítástól válaszig</dt><dd>${rekiDuration(row.forwarded_at,row.responded_at)}</dd></dl>
    ${row.admin_response?`<p>${esc(row.admin_response)}</p>`:''}
    ${String(row.id).startsWith('excel:')?`<p>Excelből továbbítva · ${esc(row.source_filename||'')}${row.source_row?' · '+esc(row.source_row)+'. sor':''}</p>`:`<a class="c360-button" href="https://futar.jitt.hu/?${esc(query.toString())}" target="_blank" rel="noopener">Reklamáció kezelése a PWA-ban ↗</a>`}`;
  dialog.showModal();
}
document.addEventListener('DOMContentLoaded',()=>{
  $('#reki-refresh').onclick=loadReki;
  $('#reki-filter').onchange=renderReki;
  $('#reki-search').oninput=renderReki;
});
