/* Read-only courier detail. Operational day and settlement month are independent. */
const courier360State={id:null,tab:'live',date:null,month:null,payload:null,sequence:0,previousScroll:0,backLabel:'Vissza a futárlistához'};
const c360Tabs=[['live','Élő helyzet'],['shifts','Műszakok'],['routes','Túrák és címek'],['finance','Pénzügy'],['complaints','Reklamációk'],['logs','Dokumentumok és napló']];
function c360Date(value,time=true){if(!value)return 'Nincs rögzítve';if(/^\d{2}:\d{2}/.test(value))return value.slice(0,5);const d=new Date(value);return Number.isFinite(d.getTime())?d.toLocaleString('hu-HU',{timeZone:'Europe/Budapest',year:'numeric',month:'2-digit',day:'2-digit',...(time?{hour:'2-digit',minute:'2-digit'}:{})}):esc(value)}
function c360Time(value){if(!value)return '—';if(/^\d{2}:\d{2}/.test(value))return value.slice(0,5);const d=new Date(value);return Number.isFinite(d.getTime())?d.toLocaleTimeString('hu-HU',{timeZone:'Europe/Budapest',hour:'2-digit',minute:'2-digit'}):'—'}
function c360Missing(text='Nincs rögzített adat'){return `<div class="empty">${esc(text)}</div>`}
function c360Table(headers,rows){return `<div class="c360-table-wrap"><table class="table"><thead><tr>${headers.map(h=>`<th>${esc(h)}</th>`).join('')}</tr></thead><tbody>${rows.length?rows.map(cells=>`<tr>${cells.map(cell=>`<td>${cell}</td>`).join('')}</tr>`).join(''):`<tr><td colspan="${headers.length}">Nincs rögzített adat.</td></tr>`}</tbody></table></div>`}
function c360Pair(label,value){return `<div class="c360-pair"><span>${esc(label)}</span><b>${value}</b></div>`}
function c360Source(source,at){return `<p class="c360-source">${esc(source)} · frissítés: ${c360Date(at)}</p>`}
function c360Go(tab,label){return `<button type="button" class="c360-button" data-c360-go="${tab}">${esc(label)}</button>`}
function c360Timeline(logs){return logs.length?`<ol class="c360-timeline">${logs.map(row=>`<li><time>${c360Date(row.at)}</time><div><strong>${esc(row.label||'Esemény')}</strong><p>${esc(row.detail||'')}</p><small>${esc(row.source||'')}${row.actor?' · '+esc(row.actor):''}</small></div></li>`).join('')}</ol>`:c360Missing('A kiválasztott naphoz nincs rögzített esemény.')}
function c360Route(route){
  if(!route)return c360Missing('A kiválasztott naphoz nincs azonosítható túra.');
  const currentNext=Boolean(route.active&&route.stopsFresh),next=currentNext?route.nextStop:route.lastKnownNextStop;
  return `<div class="panel-head"><div><h3>Túra #${esc(route.id)}</h3><p>${esc(route.warehouse||'Raktár nincs rögzítve')}</p></div><span class="badge">${route.active?'Friss túrajelzés':'Utolsó ismert túraadat'}</span></div>
    <div class="c360-route-stats">${c360Pair('Teljesített / összes cím',`${nf.format(route.completedStops??0)} / ${route.totalStops==null?'—':nf.format(route.totalStops)}`)}${c360Pair('Raktári indulás',c360Time(route.departedAt))}${c360Pair('Tervezett visszaérkezés',c360Time(route.plannedReturn))}${c360Pair('Visszaérkezés',c360Time(route.returnedAt))}</div>
    <div class="c360-next"><span class="c360-label">${currentNext?'KÖVETKEZŐ NEM TELJESÍTETT CÍM':'UTOLSÓ ISMERT NEM TELJESÍTETT CÍM'}</span><h3>${esc(next?.address||'Nincs címinformáció')}</h3><p>Időablak: ${c360Time(next?.windowFrom)}–${c360Time(next?.windowTo)} · érkezés: ${c360Time(next?.estimatedArrival||next?.plannedArrival)}</p>${next?.note?`<p>${esc(next.note)}</p>`:''}${c360Source('Címadatok',route.stopsUpdatedAt)}${c360Go('routes','Túra és címlista megnyitása ↗')}</div>
    ${c360Pair('Jármű rendszáma',esc(route.vehiclePlate||'Nincs rögzítve'))}${c360Source('Hub',route.updatedAt)}`;
}
const c360Weekday = new Intl.DateTimeFormat('hu-HU', {weekday:'short', timeZone:'UTC'});
function c360Week(date) {
  const selected = new Date(date + 'T12:00:00Z');
  const monday = selected.getUTCDate() - (selected.getUTCDay() + 6) % 7;
  return `<div class="c360-week" role="group" aria-label="A kiválasztott hét napjai">${Array.from({length:7}, (_, offset) => {
    const day = new Date(selected);
    day.setUTCDate(monday + offset);
    const value = day.toISOString().slice(0, 10);
    return `<button type="button" data-c360-day="${value}" aria-pressed="${value === date}" aria-label="${c360Date(value, false)}"><span>${c360Weekday.format(day)}</span><b>${day.getUTCDate()}</b></button>`;
  }).join('')}</div>`;
}

function c360Ring(label, value, total, tone) {
  const ratio = Number(total) > 0 && value != null ? Math.min(100, Math.max(0, Math.round(100 * value / total))) : null;
  const name = `${label}, ${ratio == null ? 'nincs adat' : `${nf.format(value)} / ${nf.format(total)} · ${ratio}%`}`;
  return `<div class="c360-ring c360-ring-${tone}" role="img" aria-label="${esc(name)}" style="--ring-value:${ratio ?? 0}%"><div aria-hidden="true"><strong>${ratio == null ? '—' : `${ratio}%`}</strong><small>${esc(label)}</small></div></div>`;
}

function c360Live(p) {
  const op = p.operational, route = op.route, next = op.nextShift;
  const today = op.shifts.filter(row => row.date === p.date);
  const open = p.complaints.filter(row => ['new','open','in_progress'].includes(String(row.status).trim().toLowerCase())).length;
  const answered = p.complaints.filter(c360ComplaintAnswered).length;
  const name = p.courier.name || 'Futár';
  const initials = name.trim().split(/\s+/).slice(0, 2).map(part => part[0]).join('').toLocaleUpperCase('hu');
  const presence = op.currentWorking === true ? 'Műszakban' : op.currentWorking === false ? 'Nincs aktív jelenléti jelzés' : 'Nem állapítható meg';
  const nextAddress = route?.active && route.stopsFresh ? route.nextStop : route?.lastKnownNextStop;
  return `<div class="c360-dashboard">
    <div class="c360-main">
      <section aria-label="Napi mutatók" class="c360-metrics">
        <div><span>Napi beosztások</span><strong>${nf.format(today.length)}</strong><small>${today.length ? today.map(row => c360Time(row.start)).join(' · ') : 'A kiválasztott napon'}</small></div>
        <div><span>Teljesített címek</span><strong>${route?.completedStops == null ? '—' : nf.format(route.completedStops)}${route?.totalStops != null ? `<small> / ${nf.format(route.totalStops)}</small>` : ''}</strong><small>${route ? `Túra #${esc(route.id)}` : 'Nincs túraadat'}</small></div>
        <div><span>Nyitott reklamációk</span><strong>${nf.format(open)}</strong><small>${esc(monthLabel(p.periodStart.slice(0, 7)))}</small></div>
      </section>
      <section class="c360-route-strip" aria-labelledby="c360-brief-title">
        <div class="c360-route-mark" aria-hidden="true">↗</div>
        <div><h3 id="c360-brief-title">${route ? `Túra #${esc(route.id)}` : 'Túra a kiválasztott napon'}</h3>
          <p>${route ? `${esc(route.warehouse || 'Raktár nincs rögzítve')} · ${route.active ? 'Friss túrajelzés' : 'Utolsó ismert túraadat'}` : 'Nincs azonosítható túra.'}</p>
          ${nextAddress?.address ? `<p>${route.active && route.stopsFresh ? 'Következő cím' : 'Utolsó ismert cím'} · ${esc(nextAddress.address)}</p>` : ''}</div>
        ${route ? c360Go('routes', 'Túra részletei ↗') : ''}
      </section>
      <section class="c360-agenda" aria-labelledby="c360-agenda-title">
        <div class="c360-section-head"><div><h3 id="c360-agenda-title">Műszakok és események</h3><p>${c360Date(p.date, false)}</p></div>${c360Go('shifts','Műszakadatok ↗')}</div>
        ${c360Week(p.date)}
        ${today.length ? `<ul class="c360-agenda-shifts">${today.map(row => `<li><time>${c360Time(row.start)}</time><div><strong>${esc(row.label || 'Műszak')}</strong><small>${[row.warehouse, row.source].filter(Boolean).map(esc).join(' · ')}</small></div></li>`).join('')}</ul>` : ''}
        ${c360Timeline(op.logs.slice(-8).reverse())}
      </section>
    </div>
    <aside class="c360-profile" aria-label="Futárprofil és teljesítés">
      <section class="c360-profile-section" aria-labelledby="c360-profile-title">
        <h3 id="c360-profile-title">Futárprofil</h3>
        <div class="c360-profile-person"><span class="c360-initials" aria-hidden="true">${esc(initials)}</span><strong>${esc(name)}</strong><small>#${esc(p.courier.id)} · ${esc(p.courier.warehouse || '—')}</small></div>
        <div class="c360-presence" data-active="${op.currentWorking === true}"><i></i>${esc(presence)}</div>
        ${c360Pair('Jelenlét', esc(op.attendance?.activity_status || 'Nincs egyező adat'))}
        ${c360Pair('Belépés / kilépés', `${c360Time(op.attendance?.checkin_start)} / ${c360Time(op.attendance?.checkin_end)}`)}
        ${c360Pair('Következő műszak', next ? `${c360Date(next.date, false)} · ${c360Time(next.start)}${next.warehouse ? ` · ${esc(next.warehouse)}` : ''}` : 'Nincs rögzítve')}
        ${c360Source(op.attendanceFresh ? 'Giriton' : 'Hub', op.attendanceFresh ? op.attendance?.updated_at : op.lastSourceAt)}
      </section>
      <section class="c360-profile-section" aria-labelledby="c360-progress-title">
        <h3 id="c360-progress-title">Teljesítés</h3>
        ${c360Ring('Címek teljesítve', route?.completedStops, route?.totalStops, 'route')}
        ${c360Ring('Válaszolt vagy lezárt ügyek', answered, p.complaints.length, 'cases')}
      </section>
    </aside>
  </div>`;
}

function c360Shifts(p){
  const op=p.operational;
  return `<article class="panel"><h3>Aktív beosztások · a kiválasztott naptól 31 napig</h3><p>A Hub rövid idősávja jelentkezési / kezdési idősáv lehet; nem kezeljük teljes műszakhosszként.</p>${c360Table(['Nap','Raktár','Kezdés','Vége / idősáv vége','Típus','Forrás frissítése'],op.shifts.map(row=>[c360Date(row.date,false),esc(row.warehouse||'—'),c360Time(row.start),c360Time(row.end),esc(row.source)+(row.isArrivalSlot?' · kezdési idősáv':''),c360Date(row.updatedAt)]))}</article>
    <div class="c360-two"><article class="panel"><h3>Tényleges napi jelenlét</h3>${c360Pair('Giriton-belépés',c360Time(op.attendance?.checkin_start))}${c360Pair('Giriton-kijelentkezés',c360Time(op.attendance?.checkin_end))}${c360Pair('Jelenléti állapot',esc(op.attendance?.activity_status||'Nincs rögzítve'))}${c360Table(['Túra','Sorbaállás','Tényleges kezdés','Indulás','Visszaérkezés'],op.dayStatistics.map(row=>[esc(row.route_id),c360Time(row.queue_started_at),c360Time(row.actual_shift_start_at),c360Time(row.departed_at),c360Time(row.returned_at)]))}</article><article class="panel"><h3>Napi idővonal</h3>${c360Timeline(op.logs)}</article></div>`;
}
function c360Routes(p){const route=p.operational.route;return `<article class="panel">${c360Route(route)}</article><article class="panel c360-gap"><h3>Címek és rendelésazonosítók</h3>${c360Table(['Sorrend','Cím','Állapot','Időablak','Tervezett / becsült','Tényleges érkezés','Rendelés'],(route?.stops||[]).map(row=>[String(row.position),esc(row.address||'Cím nincs rögzítve'),esc(({COMPLETED:'Teljesítve',CURRENT:'Aktuális',PENDING:'Hátralévő',UNKNOWN:'Nem ismert',REJECTED:'Elutasítva'})[row.state]||row.state),c360Time(row.windowFrom)+'–'+c360Time(row.windowTo),c360Time(row.estimatedArrival||row.plannedArrival),c360Time(row.actualArrival),esc(row.orderId||'—')]))}</article>`}
function c360Finance(p){
  const f=p.finance,snapshot=p.financeSnapshot;if(!f||!snapshot)return c360Missing('Ehhez a hónaphoz nem érhető el mentett pénzügyi változat.');
  const allowed=new Set(['base','tip','delay_bonus','compliance_bonus','address_bonus_kifli','customer_rating','loyalty_bonus','kiflis_bonus_malus','bonus_malus','atm_effect','salary_advance','reserve','insurance_fee','other_expense','correction']);
  // Aggregate aliases are represented once; do not sum their detail aliases again.
  const rows=snapshot.items.filter(row=>row.section==='finance'&&row.amount_kind==='huf'&&allowed.has(row.item_key));
  return `<div class="c360-summary-grid"><article class="panel"><label class="c360-label">KIFIZETENDŐ</label><b class="c360-value">${huf(f.payable)}</b><p>${esc(f.status)}</p></article><article class="panel"><label class="c360-label">LEVONÁSOK ÖSSZESEN</label><b class="c360-value">${huf(f.deductionImpact)}</b><p>A mentett pénzügyi adatokból.</p></article><article class="panel"><label class="c360-label">MENTETT VÁLTOZAT</label><b class="c360-value">v${esc(snapshot.version)}</b><p>${c360Date(snapshot.createdAt)}</p></article></div><div class="c360-two"><article class="panel"><h3>Mentett pénzügyi tételek</h3>${c360Table(['Tétel','Indoklás / megjegyzés','Összeg'],rows.map(row=>[esc(row.item_label||row.item_key),esc(row.note||'—'),huf(row.amount_value)]))}${c360Pair('Hozzáadott fizetési előleg',huf(f.salaryAdvanceAdded))}<details class="c360-details"><summary>Összes mentett részlettétel</summary>${c360Table(['Tétel','Megjegyzés','Összeg'],snapshot.items.filter(row=>row.section==='finance'&&row.amount_kind==='huf').map(row=>[esc(row.item_label||row.item_key),esc(row.note||'—'),huf(row.amount_value)]))}</details></article>
    <article class="panel"><h3>Elfogadások és kifizetés</h3>${c360Table(['Dokumentum / folyamat','Elfogadás','Elfogadott összeg'],p.acceptances.map(row=>[esc(row.action_key)+(row.process_id?' · '+esc(row.process_id):''),c360Date(row.accepted_at),row.payable_huf!=null||row.tig_final_total_huf!=null?huf(row.payable_huf??row.tig_final_total_huf):'Nincs rögzítve']))}${c360Pair('Kifizetés állapota',esc(p.closure?.status||p.workflowStates.invoice_payment?.status||'Nincs rögzítve'))}${c360Pair('Kifizetés ideje',c360Date(p.closure?.closed_at))}${c360Pair('Kifizetett összeg',p.closure?.payable_huf!=null?huf(p.closure.payable_huf):'Nincs rögzítve')}${c360Go('logs','Számlák és dokumentumok')}</article></div><article class="panel c360-gap"><h3>Havi elszámolási folyamatidők</h3>${c360Table(['Szakasz','Eltelt idő'],[['Megnyitás → elszámolás elfogadása','opening_to_settlement_hours'],['Elszámolás → teljesítés-összesítő elfogadása','settlement_to_tig_hours'],['Teljesítés-összesítő → számlafeltöltés','tig_to_invoice_hours'],['Számlafeltöltés → kifizetés','invoice_to_paid_hours'],['Megnyitás → kifizetés','opening_to_paid_hours']].map(([label,key])=>[label,p.processMetric?.[key]!=null?hours(p.processMetric[key]):'Nem mérhető']))}<p>Az adott futár és hónap mentett mutatói. Hiányzó időbélyegből nem számolunk nulla órát.</p></article>`;
}
function c360ComplaintAnswered(row) {
  return ['closed','resolved'].includes(String(row.status).trim().toLowerCase()) || row.responded_at || String(row.admin_response||'').trim();
}
function c360Complaints(p){
  const answered=p.complaints.filter(c360ComplaintAnswered);
  const durations=answered.map(row=>(Date.parse(row.responded_at)-Date.parse(row.created_at))/3600000).filter(value=>Number.isFinite(value)&&value>=0);
  return `<div class="c360-summary-grid"><article class="panel"><label class="c360-label">REKLAMÁCIÓK A HÓNAPBAN</label><b class="c360-value">${p.complaints.length} db</b><p>Minden nem törölt reklamációtípus.</p></article><article class="panel"><label class="c360-label">MEGVÁLASZOLT / LEZÁRT</label><b class="c360-value">${answered.length} db</b><p>Állapot vagy rögzített válasz alapján.</p></article><article class="panel"><label class="c360-label">ÁTLAGOS VÁLASZIDŐ</label><b class="c360-value">${durations.length?hours(durations.reduce((a,b)=>a+b,0)/durations.length):'Nem mérhető'}</b><p>${durations.length} időbélyeges válasz alapján.</p></article></div><article class="panel"><h3>Ügyek, beküldések és válaszok</h3>${p.complaints.length?p.complaints.map(row=>`<details class="c360-details"><summary>${esc(row.document_type)} · ${esc(row.status)} · ${c360Date(row.created_at)}</summary><p class="c360-message">${esc(row.message||'Nincs rögzített szöveg')}</p><button type="button" class="c360-button" data-status-courier="${esc(p.courier.id)}" data-status-label="Reklamáció" data-status-complaint="${esc(row.id||'')}">Reklamáció ügyintézése</button><div class="c360-answer"><strong>Válasz</strong><p class="c360-message">${esc(row.admin_response||'Nincs rögzített válaszszöveg')}</p><small>${esc(row.responded_by||'—')} · ${c360Date(row.responded_at)}</small></div></details>`).join(''):c360Missing('Ehhez a hónaphoz nincs rögzített reklamáció.')}</article>`;
}
function c360Logs(p){return `<div class="c360-two"><article class="panel"><h3>Havi dokumentumok</h3>${c360Table(['Dokumentum','Feltöltés','Megnyitás'],p.documents.map(row=>[esc(row.title||row.file_name||row.document_type)+'<br><small>'+esc(row.document_type)+'</small>',c360Date(row.uploaded_at)+'<br><small>'+esc(row.uploaded_by||'—')+'</small>',`<a class="c360-button" href="/api/courier360-document?courier=${encodeURIComponent(p.courier.id)}&id=${encodeURIComponent(row.id)}" target="_blank" rel="noopener">Megnyitás ↗</a>`]))}</article><article class="panel"><h3>Forrásadatok elérhetősége</h3>${c360Table(['Forrás','Állapot'],p.sources.map(row=>[esc(row.table),row.available?`${row.count} sor`:'Nem elérhető']))}</article></div><article class="panel c360-gap"><h3>Operatív nap és havi elszámolás eseménynaplója</h3>${c360Timeline(p.eventLog)}</article>`}
function renderCourier360(){
  const p=courier360State.payload;if(!p)return;
  const root=$('#courier360-page');
  root.innerHTML=`<div class="c360-head"><button type="button" class="c360-button" data-c360-close>← ${esc(courier360State.backLabel)}</button><button type="button" class="c360-button" data-c360-refresh>Frissítés</button></div>
    <header class="c360-identity"><div><p class="crumb">FUTÁR 360°</p><h2>${esc(p.courier.name)}</h2></div>
      <div class="c360-controls"><label>Operatív nap <input type="date" id="c360-date" value="${esc(courier360State.date)}"></label><label>Elszámolási hónap <input type="month" id="c360-month" value="${esc(courier360State.month)}"></label></div></header>
    <nav class="c360-tabs" aria-label="Futáradatok">${c360Tabs.map(([key,label])=>`<button type="button" class="c360-tab ${courier360State.tab===key?'active':''}" aria-pressed="${courier360State.tab===key}" data-c360-go="${key}">${label}</button>`).join('')}</nav>
    ${p.sources.some(s=>!s.available)?'<div class="notice">Egyes források nem érhetők el. A hiányzó adatokat külön jelöljük; részletek a Dokumentumok és napló fülön.</div>':''}
    ${!p.operational.fresh&&courier360State.tab==='live'?'<div class="c360-notice">Nincs 20 percen belüli Hub-jelzés. A régebbi túra- és címadatok utolsó ismert állapotot jelentenek.</div>':''}
    <div class="c360-content">${({live:c360Live,shifts:c360Shifts,routes:c360Routes,finance:c360Finance,complaints:c360Complaints,logs:c360Logs})[courier360State.tab](p)}</div>`;
}
async function openCourier360(id,{date,month,tab,backLabel='Vissza a futárlistához'}={}){
  const isNew=courier360State.id!==String(id);
  courier360State.previousScroll=window.scrollY;
  courier360State.id=String(id);if(isNew){courier360State.tab='live';courier360State.date=new Intl.DateTimeFormat('en-CA',{timeZone:'Europe/Budapest',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date())}
  courier360State.month=month||$('#month').value;
  if(date)courier360State.date=date;
  if(tab)courier360State.tab=tab;
  courier360State.backLabel=backLabel;
  $('#courier360-page').hidden=false;$('#app').classList.add('courier360-open');window.scrollTo(0,0);
  await loadCourier360();
}
async function loadCourier360(){
  const sequence=++courier360State.sequence;
  $('#courier360-page').innerHTML='<div class="empty">Futáradatok betöltése…</div>';
  try{
    const p=await api(`/api/courier360?courier=${encodeURIComponent(courier360State.id)}&date=${encodeURIComponent(courier360State.date)}&month=${encodeURIComponent(courier360State.month)}`);
    if(sequence!==courier360State.sequence)return;
    courier360State.payload=p;renderCourier360();
  }catch(error){if(sequence!==courier360State.sequence)return;$('#courier360-page').innerHTML=`<button type="button" class="c360-button" data-c360-close>← ${esc(courier360State.backLabel)}</button><div class="notice">${esc(error.message)}</div><button type="button" class="c360-button" data-c360-refresh>Újrapróbálás</button>`}
}
function closeCourier360(){courier360State.sequence++;$('#courier360-page').hidden=true;$('#app').classList.remove('courier360-open');window.scrollTo(0,courier360State.previousScroll)}
document.addEventListener('click',event=>{
  const open=event.target.closest('[data-open-courier]');if(open){openCourier360(open.dataset.openCourier);return}
  if(event.target.closest('[data-c360-close]')){closeCourier360();return}
  if(event.target.closest('[data-c360-refresh]')){loadCourier360();return}
  const day=event.target.closest('[data-c360-day]');
  if(day){
    courier360State.date=day.dataset.c360Day;
    loadCourier360().then(()=>$('#courier360-page [data-c360-day][aria-pressed="true"]')?.focus());
    return;
  }
  const tab=event.target.closest('[data-c360-go]');if(tab){courier360State.tab=tab.dataset.c360Go;renderCourier360()}
});
document.addEventListener('change',event=>{if(event.target.id==='c360-date'){courier360State.date=event.target.value;loadCourier360()}if(event.target.id==='c360-month'){courier360State.month=event.target.value;loadCourier360()}});
