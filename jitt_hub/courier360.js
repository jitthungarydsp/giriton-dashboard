/* Read-only courier detail. Operational day and settlement month are independent. */
const courier360State={id:null,tab:'live',date:null,month:null,payload:null,sequence:0,previousScroll:0,backLabel:'Vissza a futárlistához'};
const c360Today = () => new Intl.DateTimeFormat('en-CA',{timeZone:'Europe/Budapest',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date());
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
function c360Calendar(date) {
  const month = courier360State.calendarMonth || date.slice(0,7);
  const first = new Date(month + '-01T12:00:00Z');
  const offset = (first.getUTCDay() + 6) % 7;
  const count = new Date(Date.UTC(first.getUTCFullYear(),first.getUTCMonth()+1,0)).getUTCDate();
  const today = c360Today();
  const label = monthLabel(month);
  return `<div class="c360-calendar">
      <div class="c360-calendar-head"><strong>${esc(label)}</strong><div role="group" aria-label="Naptárhónap">
        <button type="button" class="c360-button" data-c360-month-step="-1" aria-label="Előző hónap">‹</button>
        <button type="button" class="c360-button" data-c360-month-step="0">Ma</button>
        <button type="button" class="c360-button" data-c360-month-step="1" aria-label="Következő hónap">›</button>
      </div></div>
      <div class="c360-calendar-grid" role="group" aria-label="${esc(label)} napjai">
        ${['H','K','Sze','Cs','P','Szo','V'].map(day=>`<span class="c360-weekday" aria-hidden="true">${day}</span>`).join('')}
        ${'<span aria-hidden="true"></span>'.repeat(offset)}
        ${Array.from({length:count},(_,index)=>{
          const value = month+'-'+String(index+1).padStart(2,'0');
          return `<button type="button" data-c360-day="${value}" aria-haspopup="dialog" ${value === today ? 'aria-current="date"' : ''}
            data-operational-day="${value === date}" aria-label="${c360Date(value,false)}">${index+1}</button>`;
        }).join('')}
      </div>
      <div class="c360-calendar-legend"><span><i aria-hidden="true"></i>Van műszak</span><small id="c360-calendar-status" role="status"></small></div>
    </div>`;
}

let c360CalendarShifts;
function c360MarkCalendar() {
  const status = $('#c360-calendar-status');
  if (!status) return;
  const entry = c360CalendarShifts;
  status.textContent = !entry ? '' : entry.error || (entry.loading ? 'Műszakok betöltése…' : entry.partial ? 'Részleges műszakadat' : '');
  $$('.c360-calendar-grid [data-c360-day]').forEach(button=>{
    const date = button.dataset.c360Day;
    const hasShift = entry?.dates?.has(date);
    button.setAttribute('data-has-shift',String(Boolean(hasShift)));
    button.setAttribute('aria-label',c360Date(date,false)+(hasShift ? ' · van műszak' : ''));
  });
}

async function c360LoadCalendar() {
  const {id,calendarMonth:month} = courier360State;
  if (!$('#c360-calendar-status') || !id || !month) return;
  if (c360CalendarShifts?.id === id && c360CalendarShifts.month === month && !c360CalendarShifts.error) {
    c360MarkCalendar();
    return;
  }
  const entry = c360CalendarShifts = {id,month,loading:true};
  c360MarkCalendar();
  try {
    const data = await api('/api/courier360?' + new URLSearchParams({courier:id,date:month+'-01',scope:'calendar'}));
    if (String(data.courierId) !== id || data.month !== month) throw Error('Eltérő naptáradat érkezett.');
    entry.dates = new Set(data.dates);
    entry.partial = data.partial;
  } catch {
    entry.error = 'A havi műszakok nem érhetők el.';
  } finally {
    entry.loading = false;
    if (c360CalendarShifts === entry) c360MarkCalendar();
  }
}

function c360ShiftList(shifts) {
  return shifts.length ? `<ul class="c360-agenda-shifts">${shifts.map(row=>`<li><time>${c360Time(row.start)}</time><div><strong>${esc(row.label || 'Műszak')}</strong><small>${[row.warehouse,row.source].filter(Boolean).map(esc).join(' · ')}</small></div></li>`).join('')}</ul>` :
    c360Missing('Nincs rögzített műszak.');
}

function c360Ring(label, value, total, tone) {
  const ratio = Number(total) > 0 && value != null ? Math.min(100, Math.max(0, Math.round(100 * value / total))) : null;
  const name = `${label}, ${ratio == null ? 'nincs adat' : `${nf.format(value)} / ${nf.format(total)} · ${ratio}%`}`;
  return `<div class="c360-ring c360-ring-${tone}" role="img" aria-label="${esc(name)}" style="--ring-value:${ratio ?? 0}%"><div aria-hidden="true"><strong>${ratio == null ? '—' : `${ratio}%`}</strong><small>${esc(label)}</small></div></div>`;
}

function c360CompletedRoutes(p) {
  const {route,dayStatistics=[]}=p.operational;
  const completed=new Map();
  for (const row of dayStatistics) {
    if (row.route_id==null || !Number.isFinite(Date.parse(row.returned_at))) continue;
    const id=String(row.route_id);
    if (id===String(route?.id) && route.active) continue;
    if (!completed.has(id) || Date.parse(row.returned_at)>Date.parse(completed.get(id).returned_at)) completed.set(id,row);
  }
  if (route?.id!=null && !route.active && Number.isFinite(Date.parse(route.returnedAt)) && !completed.has(String(route.id))) {
    completed.set(String(route.id),{route_id:route.id,warehouse_code:route.warehouse,departed_at:route.departedAt,returned_at:route.returnedAt});
  }
  const rows=[...completed.values()].sort((a,b)=>Date.parse(b.returned_at)-Date.parse(a.returned_at));
  const unavailable=p.sources?.some(source=>source.table==='courier_hub_route_statistics' && source.available===false);
  return `<section class="c360-agenda" aria-labelledby="c360-completed-title">
    <div class="c360-section-head"><h3 id="c360-completed-title">Kifutott túrák · ${nf.format(rows.length)}</h3></div>
    ${rows.length ? c360Table(['Túra','Raktár','Indulás','Visszaérkezés'],rows.map(row=>[
      '#'+esc(row.route_id),esc(row.warehouse_code||'—'),c360Time(row.departed_at),c360Time(row.returned_at)
    ])) : ''}
    ${unavailable ? c360Missing('A napi túrastatisztika jelenleg nem érhető el.') : rows.length ? '' : c360Missing('A kiválasztott napon nincs rögzített visszaérkezés.')}
  </section>`;
}

function c360Live(p) {
  const op = p.operational, route = op.route;
  const today = op.shifts.filter(row => row.date === p.date);
  const open = p.complaints.filter(row => ['new','open','in_progress'].includes(String(row.status).trim().toLowerCase())).length;
  const delay = op.liveDelay != null ? ` · késés ${op.liveDelay > 0 ? '+' : ''}${nf.format(op.liveDelay)} perc` : '';
  const nextAddress = route?.active && route.stopsFresh ? route.nextStop : route?.lastKnownNextStop;
  return `<div class="c360-main">
      <section aria-label="Napi mutatók" class="c360-metrics">
        <div><span>Napi beosztások</span><strong>${nf.format(today.length)}</strong><small>${today.length ? today.map(row => c360Time(row.start)).join(' · ') : 'A kiválasztott napon'}</small></div>
        <div><span>Teljesített címek</span><strong>${route?.completedStops == null ? '—' : nf.format(route.completedStops)}${route?.totalStops != null ? `<small> / ${nf.format(route.totalStops)}</small>` : ''}</strong><small>${route ? `Túra #${esc(route.id)}` : 'Nincs túraadat'}</small></div>
        <div><span>Nyitott reklamációk</span><strong>${nf.format(open)}</strong><small>${esc(monthLabel(p.periodStart.slice(0, 7)))}</small></div>
      </section>
      <section class="c360-route-strip" aria-labelledby="c360-brief-title">
        <div class="c360-route-mark" aria-hidden="true">↗</div>
        <div><h3 id="c360-brief-title">${route ? `Túra #${esc(route.id)}` : 'Túra a kiválasztott napon'}</h3>
          <p>${route ? `${esc(route.warehouse || 'Raktár nincs rögzítve')} · ${route.active ? 'Friss túrajelzés' : 'Utolsó ismert túraadat'}` : 'Nincs azonosítható túra.'}${delay}</p>
          ${nextAddress?.address ? `<p>${route.active && route.stopsFresh ? 'Következő cím' : 'Utolsó ismert cím'} · ${esc(nextAddress.address)}</p>` : ''}</div>
        ${route ? c360Go('routes', 'Túra részletei ↗') : ''}
      </section>
      ${c360CompletedRoutes(p)}
      <section class="c360-agenda" aria-labelledby="c360-agenda-title">
        <div class="c360-section-head"><h3 id="c360-agenda-title">Műszakok és események</h3>${c360Go('shifts','Műszakadatok ↗')}</div>
        ${c360Calendar(p.date)}
      </section>
    </div>`;
}

function c360Profile(p) {
  const op = p.operational, route = op.route, next = op.nextShift;
  const open = p.complaints.filter(row => ['new','open','in_progress'].includes(String(row.status).trim().toLowerCase())).length;
  const answered = p.complaints.filter(c360ComplaintAnswered).length;
  const name = p.courier.name || 'Futár';
  const initials = name.trim().split(/\s+/).slice(0, 2).map(part => part[0]).join('').toLocaleUpperCase('hu');
  const presence = op.liveStatus || (op.currentWorking === true ? 'Műszakban' : op.currentWorking === false ? 'Nincs aktív jelenléti jelzés' : 'Nem állapítható meg');
  return `      <section class="c360-profile-section" aria-labelledby="c360-profile-title">
        <h3 id="c360-profile-title">Futárprofil</h3>
        <button type="button" class="c360-profile-person" data-c360-profile aria-haspopup="dialog" aria-label="${esc(name)} adatlapja">
          <span class="c360-initials" aria-hidden="true">${esc(initials)}</span><strong>${esc(name)}</strong>
          <small>#${esc(p.courier.id)} · ${esc(p.courier.warehouse || '—')}</small><span class="c360-profile-action">Adatlap megnyitása ↗</span>
        </button>
        <div class="c360-presence" data-active="${op.currentWorking === true}"><i></i>${esc(presence)}</div>
        ${c360Pair('Jelenlét', esc(op.attendance?.activity_status || 'Nincs egyező adat'))}
        ${c360Pair('Belépés / kilépés', `${c360Time(op.attendance?.checkin_start)} / ${c360Time(op.attendance?.checkin_end)}`)}
        ${c360Pair('Következő műszak', next ? `${c360Date(next.date, false)} · ${c360Time(next.start)}${next.warehouse ? ` · ${esc(next.warehouse)}` : ''}` : 'Nincs rögzítve')}
        ${c360Source(op.liveSource || (op.attendanceFresh ? 'Giriton' : 'Hub'), op.liveAt || (op.attendanceFresh ? op.attendance?.updated_at : op.lastSourceAt))}
      </section>
      <section class="c360-profile-section" aria-labelledby="c360-progress-title">
        <h3 id="c360-progress-title">Teljesítés</h3>
        ${c360Ring('Címek teljesítve', route?.completedStops, route?.totalStops, 'route')}
        ${c360Ring('Válaszolt vagy lezárt ügyek', answered, p.complaints.length, 'cases')}
      </section>`;
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
function c360SearchControls(id, placeholder = 'Futárnév, azonosító vagy Túrán') {
  return `<form class="c360-search" id="${id}" role="search" aria-label="Futár keresése">
    <input type="search" id="${id}-input" placeholder="${esc(placeholder)}" aria-label="${esc(placeholder)}" aria-controls="${id}-results" autocomplete="off">
    <div id="${id}-results" class="c360-search-results" hidden></div>
    <p id="${id}-status" class="c360-search-status" role="status"></p>
  </form>
  <div class="c360-live-tools" role="group" aria-label="Élő státuszszűrők">
    ${['Túrán','Nem jelent meg','Csúszik','Tétlen','Rakodik'].map(label=>`<button type="button" class="c360-button" data-c360-live-filter="${label}" aria-pressed="false">${label}</button>`).join('')}
  </div>`;
}

function c360Header(loading = false) {
  return `<div class="c360-head" data-c360-search-area>
    <button type="button" class="c360-button" data-c360-close>← ${esc(courier360State.backLabel)}</button>
    ${c360SearchControls('c360-search')}
    <button type="button" class="c360-button c360-refresh" data-c360-refresh ${loading ? 'disabled' : ''}>Frissítés</button>
  </div>`;
}

const c360ProfileGroups = [
  ['Futár adatai', [['Futár ID', 'courier_id'], ['Futár neve', 'courier_name'], ['Telefonszám', 'phone_number'], ['Preferált raktár', 'warehouse_name']]],
  ['Számlázási adatok', [['Vállalkozás neve', 'company_name'], ['Vállalkozás székhelye', 'company_address'], ['Adószám', 'tax_number'], ['Bankszámlaszám', 'bank_account_number'], ['Számlázási e-mail', 'billing_email']]],
];
let c360ProfileSequence = 0;

async function openCourierProfile() {
  const courier = courier360State.payload?.courier;
  const dialog = $('#c360-profile-dialog');
  if (!courier || !dialog?.isConnected || dialog.open) return;
  const sequence = ++c360ProfileSequence;
  const body = $('#c360-profile-data');
  $('#c360-profile-dialog-title').textContent = `${courier.name || 'Futár'} · adatlap`;
  body.innerHTML = '<p role="status">Adatlap betöltése…</p>';
  dialog.addEventListener('close', () => {
    if (!dialog.open) body.replaceChildren();
  }, {once: true});
  dialog.showModal();
  try {
    const {profile} = await api('/api/courier360-profile?courier=' + encodeURIComponent(courier.id));
    if (sequence !== c360ProfileSequence || !dialog.open || !dialog.isConnected) return;
    if (String(profile?.courier_id) !== String(courier.id)) throw new Error('A kapott adatlap másik futárhoz tartozik.');
    body.innerHTML = c360ProfileGroups.map(([title, fields]) => `<section><h3>${title}</h3><dl>${fields.map(([label, field]) =>
      `<div><dt>${label}</dt><dd>${esc(profile[field] || 'Nincs megadva')}</dd></div>`).join('')}</dl></section>`).join('') +
      (profile.billing_data_updated_at ? `<p class="c360-source">Számlázási adatok frissítve · ${c360Date(profile.billing_data_updated_at)}</p>` : '');
  } catch (error) {
    if (sequence === c360ProfileSequence && dialog.open && dialog.isConnected) {
      body.innerHTML = `<p role="alert">${esc(error.message)}</p>`;
    }
  }
}

const c360SearchText = text => String(text ?? '').normalize('NFD').replace(/\p{Diacritic}/gu, '').toLowerCase().trim();
function c360ActiveQuery(value) {
  const query = c360SearchText(value).replace(/\s+/g,' ');
  if (/^(turan|turan van|dolgozik|muszakban)$/.test(query)) return 'active';
  if (query === 'nem jelent meg') return 'Nem jelent meg';
  if (query === 'csuszik') return 'Csúszik';
  if (/^(tetlen|tetel)$/.test(query)) return 'Tétlen';
  if (query === 'rakodik') return 'Rakodik';
  return '';
}
const c360SearchStates = new WeakMap();
let c360ActiveRequest;
let c360LiveTimer;

function c360ReadLive() {
  c360ActiveRequest ||= api('/api/courier360-active?scope=all').finally(() => { c360ActiveRequest = null; });
  return c360ActiveRequest;
}

function c360SearchMatches(value, form) {
  const query = c360SearchText(value).replace(/^#(?=\d+$)/, '');
  if (!query) return [];
  const daily = form?.id === 'attendance-c360-search' ? attendanceSearchOptions() : [];
  const matches = new Map();
  for (const row of [...daily,...(data?.couriers || [])]) {
    if (!/^\d{1,12}$/.test(row.courierId)) continue;
    if (!c360SearchText([row.courierName,row.courierId,row.searchTerms].join(' ')).includes(query)) continue;
    const id = String(row.courierId);
    if (!matches.has(id)) matches.set(id,row);
  }
  return [...matches.values()].sort((a,b)=>Number(String(b.courierId)===query)-Number(String(a.courierId)===query));
}

function c360SearchRows(results, rows, active = false) {
  results.innerHTML = rows.map(row => `<button type="button" data-c360-switch="${esc(row.courierId)}">
    <span>${esc(row.courierName || 'Futár')}${active ? `<small class="c360-search-courier-status" data-status="${esc(row.status)}">${row.stale ? 'Utolsó ismert: ' : ''}${esc(row.status)}${row.warehouse ? ' · '+esc(row.warehouse) : ''}${row.stale && row.at ? ' · '+c360Date(row.at) : ''}</small>` : ''}</span><small>#${esc(row.courierId)}</small>
  </button>`).join('');
  results.hidden = !rows.length;
}

function c360SearchState(form) {
  if (!c360SearchStates.has(form)) c360SearchStates.set(form,{sequence:0,expanded:false,filter:'',liveRows:[]});
  return c360SearchStates.get(form);
}

function c360DismissSearch(form) {
  const state = c360SearchState(form);
  state.expanded = false;
  form.querySelector('.c360-search-results').hidden = true;
  form.querySelector('.c360-search-status').textContent = '';
  delete form.querySelector('input').dataset.liveSearch;
}

function c360DismissOtherSearches(target) {
  for (const form of $$('.c360-search')) {
    if (!form.contains(target)) c360DismissSearch(form);
  }
}

function c360ShowLiveSearch(form, couriers, partial, filter) {
  const rows = couriers.filter(row=>filter === 'active' ? row.working : row.status === filter)
    .sort((a,b)=>Number(Boolean(a.stale))-Number(Boolean(b.stale)));
  const state = c360SearchState(form);
  state.liveRows = rows;
  form.dispatchEvent(new Event('c360-search-change'));
  if (!state.expanded) return;
  c360SearchRows(form.querySelector('.c360-search-results'),rows,true);
  form.querySelector('.c360-search-status').textContent = rows.length ? `${rows.length} futár${partial ? ' · Részleges adat' : ''}.`
    : partial ? 'A rendelkezésre álló forrásokban nincs friss találat.' : 'Nincs friss találat erre az állapotra.';
}

async function c360RenderSearch(input, {expand = true} = {}) {
  const form = input.form;
  const state = c360SearchState(form);
  const sequence = ++state.sequence;
  if (expand) state.expanded = true;
  const results = form.querySelector('.c360-search-results');
  const status = form.querySelector('.c360-search-status');
  const filter = c360ActiveQuery(input.value);
  const changed = state.filter !== filter;
  if (changed) state.liveRows = [];
  state.filter = filter;
  form.closest('[data-c360-search-area]').querySelectorAll('[data-c360-live-filter]').forEach(button=>
    button.setAttribute('aria-pressed',String(c360ActiveQuery(button.dataset.c360LiveFilter) === filter)));
  form.dispatchEvent(new Event('c360-search-change'));
  if (filter) {
    if (state.expanded) {
      input.dataset.liveSearch = 'true';
      if (changed || !state.liveRows.length) {
        results.hidden = true;
        status.textContent = 'Élő futárstátuszok betöltése…';
      }
    }
    try {
      const {couriers, partial} = await c360ReadLive();
      if (sequence !== state.sequence || !input.isConnected) return;
      c360ShowLiveSearch(form,couriers,partial,filter);
    } catch (error) {
      if (sequence !== state.sequence || !input.isConnected) return;
      state.liveRows = [];
      form.dispatchEvent(new Event('c360-search-change'));
      if (state.expanded) {
        results.hidden = true;
        status.textContent = error.message;
      }
    }
    return;
  }
  delete input.dataset.liveSearch;
  if (!state.expanded) return;
  const matches = c360SearchMatches(input.value,form);
  c360SearchRows(results, matches.slice(0, 8));
  status.textContent = !input.value.trim() ? '' : matches.length
    ? `${matches.length} találat${matches.length > 8 ? ', az első 8 látható' : ''}.`
    : /^#?\d{1,12}$/.test(input.value.trim()) ? 'Enter a futárazonosító megnyitásához.' : 'Nincs találat a betöltött futárlistában.';
}

async function c360RefreshLive() {
  const p = courier360State.payload;
  if (!p || document.hidden || $('#courier360-page').hidden || p.date !== c360Today() || courier360State.tab !== 'live') return;
  const sequence = courier360State.sequence;
  const indicator = $('#c360-live-checked');
  if (!indicator) return;
  try {
    const {couriers, partial} = await c360ReadLive();
    if (sequence !== courier360State.sequence || courier360State.tab !== 'live' || !indicator?.isConnected) return;
    const input = $('#c360-search-input');
    const statusFilter = c360ActiveQuery(input.value);
    if (statusFilter && input.dataset.liveSearch && document.activeElement === input) {
      c360ShowLiveSearch(input.form,couriers,partial,statusFilter);
    }
    const row = couriers.find(row=>String(row.courierId) === String(p.courier.id));
    const op = p.operational, oldRoute = op.route;
    if (row?.at) {
      const notice = $('#c360-freshness-note');
      op.fresh = !row.stale && row.source.startsWith('Kifli Hub');
      if (notice) notice.hidden = op.fresh;
      indicator.textContent = (row.stale ? 'Utolsó ismert · ' : '')+row.source+' · '+c360Date(row.at);
      Object.assign(op,{liveStatus:row.stale ? 'Utolsó ismert: '+row.status : row.status,
        currentWorking:row.stale ? null : row.working,liveSource:row.source,liveAt:row.at,liveDelay:row.stale ? null : row.delayMinutes});
      if (row.routeId) {
        const same = oldRoute?.id === row.routeId;
        op.route = {...(same ? oldRoute : {stops:[]}),id:row.routeId,warehouse:row.warehouse,active:!row.stale && row.routeActive,updatedAt:row.at,
          completedStops:row.completedStops ?? (same ? oldRoute.completedStops : null),totalStops:row.totalStops ?? (same ? oldRoute.totalStops : null),
          stopsFresh:Boolean(!row.stale && same && oldRoute.stopsFresh && row.completedStops === oldRoute.completedStops && Date.now()-Date.parse(oldRoute.stopsUpdatedAt)<1200000)};
      } else if (oldRoute) op.route = {...oldRoute,active:false,stopsFresh:false};
    } else {
      const absent = !op.attendance?.checkin_start && /didn.t come|absent|nem érkezett/i.test(op.attendance?.activity_status || '');
      indicator.textContent = absent ? 'Giriton · rögzített hiányzás · '+c360Date(op.attendance.updated_at)
        : partial ? 'A friss futáradat részlegesen érhető el.' : 'A futárról nincs friss státusz.';
      Object.assign(op,{liveStatus:absent ? 'Giriton: nem jelent meg' : 'Nincs friss státusz',currentWorking:absent ? false : null,liveDelay:null});
      if (absent) Object.assign(op,{liveSource:'Giriton',liveAt:op.attendance.updated_at});
      if (oldRoute) op.route = {...oldRoute,active:false,stopsFresh:false};
    }
    c360RefreshView(p);
  } catch {
    if (sequence !== courier360State.sequence || courier360State.tab !== 'live' || !indicator?.isConnected) return;
    indicator.textContent = 'Frissítés sikertelen · utolsó ismert adatok';
    p.operational.liveStatus = 'Nincs ellenőrzött friss státusz';
    p.operational.currentWorking = null;
    p.operational.liveDelay = null;
    if (p.operational.route) Object.assign(p.operational.route,{active:false,stopsFresh:false});
    c360RefreshView(p);
  }
}

function c360RefreshView(p) {
  if ($('#c360-profile-dialog')?.open || $('#c360-day-dialog')?.open) return;
  const content = $('#courier360-page .c360-content');
  const profile = $('#c360-profile-rail');
  if (profile && !profile.contains(document.activeElement)) profile.innerHTML = c360Profile(p);
  if (content && !content.contains(document.activeElement)) {
    content.innerHTML = c360Live(p);
    c360MarkCalendar();
  }
}

let c360DayRequest = 0;
let c360DayOpener;
function c360CloseDay() {
  $('#c360-day-dialog').close();
  if (c360DayOpener?.isConnected) c360DayOpener.focus();
  c360DayOpener = null;
}

async function c360OpenDay(button) {
  const dialog = $('#c360-day-dialog');
  const body = $('#c360-day-data');
  const {c360Day:date} = button.dataset;
  const {id,month} = courier360State;
  const sequence = ++c360DayRequest;
  c360DayOpener = button;
  $('#c360-day-title').textContent = c360Date(date,false);
  body.innerHTML = '<p role="status">Napi adatok betöltése…</p>';
  if (!dialog.open) dialog.show();
  dialog.querySelector('[data-c360-close-day]').focus();
  try {
    const payload = await api('/api/courier360?' + new URLSearchParams({courier:id,date,month,scope:'day'}));
    if (sequence !== c360DayRequest || !dialog.open || !dialog.isConnected) return;
    if (payload.date !== date || String(payload.courier?.id) !== id) throw Error('A kapott adatok másik futárhoz vagy naphoz tartoznak.');
    const op = payload.operational;
    const shifts = op.shifts.filter(row=>row.date===date);
    const routes = op.dayStatistics || [];
    body.innerHTML = `<section><h3>Műszakok</h3>${c360ShiftList(shifts)}</section>
      <section><h3>Jelenlét és túrák</h3>
        ${c360Pair('Jelenlét',esc(op.attendance?.activity_status || 'Nincs rögzítve'))}
        ${c360Pair('Belépés / kilépés',`${c360Time(op.attendance?.checkin_start)} / ${c360Time(op.attendance?.checkin_end)}`)}
        ${routes.length ? c360Table(['Túra','Indulás','Visszaérkezés'],routes.map(row=>[esc(row.route_id),c360Time(row.departed_at),c360Time(row.returned_at)]))
          : op.route?.id ? c360Pair('Túra',esc(op.route.id)) : ''}
      </section>
      <section><h3>Napi események</h3>${c360Timeline(op.logs)}</section>`;
  } catch (error) {
    if (sequence === c360DayRequest && dialog.open && dialog.isConnected) body.innerHTML = `<p role="alert">${esc(error.message)}</p>`;
  }
}

async function c360SwitchCourier(id, form) {
  if (form?.id === 'attendance-c360-search') return openAttendanceCourier(id);
  courier360State.id = String(id);
  await loadCourier360();
  if (!$('#courier360-page').hidden && courier360State.id === String(id) && document.activeElement === document.body) {
    $('#c360-search-input').focus();
  }
}

const c360TabContent = {live:c360Live,shifts:c360Shifts,routes:c360Routes,finance:c360Finance,complaints:c360Complaints,logs:c360Logs};

function c360SelectTab(tab) {
  if (!Object.hasOwn(c360TabContent,tab) || !courier360State.payload) return;
  $('#c360-day-dialog')?.close();
  c360DayOpener=null;
  courier360State.tab=tab;
  const p=courier360State.payload;
  $$('.c360-tabs button').forEach(button=>{
    const active = button.dataset.c360Go === tab;
    button.classList.toggle('active',active);
    button.setAttribute('aria-pressed',String(active));
  });
  $('#c360-live-checked').hidden = tab !== 'live' || p.date !== c360Today();
  $('#c360-freshness-note').hidden = tab !== 'live' || p.operational.fresh;
  $('#courier360-page .c360-content').innerHTML = c360TabContent[tab](p);
  if (tab === 'live') {
    c360LoadCalendar();
    c360RefreshLive();
  }
}

function renderCourier360(){
  const p=courier360State.payload;if(!p)return;
  const root=$('#courier360-page');
  root.innerHTML=`${c360Header()}
    <header class="c360-identity"><div><p class="crumb">FUTÁR 360°</p><h2>${esc(p.courier.name)}</h2></div>
      <div class="c360-controls"><label>Operatív nap <input type="date" id="c360-date" value="${esc(courier360State.date)}"></label><label>Elszámolási hónap <input type="month" id="c360-month" value="${esc(courier360State.month)}"></label></div></header>
    <nav class="c360-tabs" aria-label="Futáradatok">${c360Tabs.map(([key,label])=>`<button type="button" class="c360-tab ${courier360State.tab===key?'active':''}" aria-pressed="${courier360State.tab===key}" data-c360-go="${key}">${label}</button>`).join('')}</nav>
    <small id="c360-live-checked" aria-live="polite" ${courier360State.tab==='live' && p.date===c360Today() ? '' : 'hidden'}></small>
    ${p.sources.some(s=>!s.available)?'<div class="notice">Egyes források nem érhetők el. A hiányzó adatokat külön jelöljük; részletek a Dokumentumok és napló fülön.</div>':''}
    <div class="c360-notice" id="c360-freshness-note" ${courier360State.tab==='live'&&!p.operational.fresh ? '' : 'hidden'}>A régebbi túra- és címadatok az utolsó ismert állapotot mutatják.</div>
    <div class="c360-dashboard">
      <div class="c360-content">${c360TabContent[courier360State.tab](p)}</div>
      <aside class="c360-profile" id="c360-profile-rail" aria-label="Futárprofil és teljesítés">${c360Profile(p)}</aside>
    </div>
    <dialog id="c360-day-dialog" class="c360-profile-dialog c360-day-dialog" aria-labelledby="c360-day-title">
      <header><div><h2 id="c360-day-title"></h2><p>${esc(p.courier.name)} · #${esc(p.courier.id)}</p></div>
        <button type="button" class="c360-button" data-c360-close-day>Bezárás</button></header>
      <div id="c360-day-data"></div>
    </dialog>
    <dialog id="c360-profile-dialog" class="c360-profile-dialog" aria-labelledby="c360-profile-dialog-title">
      <header><h2 id="c360-profile-dialog-title">Futár adatlapja</h2><form method="dialog"><button class="c360-button" autofocus>Bezárás</button></form></header>
      <div id="c360-profile-data"></div>
    </dialog>`;
  if (courier360State.tab === 'live') c360LoadCalendar();
}
async function openCourier360(id,{date,month,tab,backLabel='Vissza a futárlistához'}={}){
  const isNew=courier360State.id!==String(id);
  courier360State.previousScroll=window.scrollY;
  courier360State.id=String(id);if(isNew){courier360State.tab='live';courier360State.date=c360Today()}
  courier360State.month=month||$('#month').value;
  if(date)courier360State.date=date;
  courier360State.calendarMonth=courier360State.date.slice(0,7);
  if(tab)courier360State.tab=tab;
  courier360State.backLabel=backLabel;
  $('#courier360-page').hidden=false;$('#app').classList.add('courier360-open');window.scrollTo(0,0);
  if (!c360LiveTimer) c360LiveTimer=setInterval(c360RefreshLive,30000);
  await loadCourier360();
}
async function loadCourier360(){
  const sequence=++courier360State.sequence;
  c360CalendarShifts=null;
  $('#courier360-page').innerHTML=`${c360Header(true)}<div class="empty" role="status">Futáradatok betöltése…</div>`;
  try{
    const p=await api(`/api/courier360?courier=${encodeURIComponent(courier360State.id)}&date=${encodeURIComponent(courier360State.date)}&month=${encodeURIComponent(courier360State.month)}`);
    if(sequence!==courier360State.sequence)return;
    courier360State.payload=p;renderCourier360();c360RefreshLive();
  }catch(error){if(sequence!==courier360State.sequence)return;$('#courier360-page').innerHTML=`${c360Header()}<div class="notice" role="alert">${esc(error.message)}</div>`}
}
function closeCourier360(){courier360State.sequence++;clearInterval(c360LiveTimer);c360LiveTimer=null;c360CalendarShifts=null;c360DayOpener=null;$('#c360-day-dialog')?.close();$('#courier360-page').hidden=true;$('#app').classList.remove('courier360-open');window.scrollTo(0,courier360State.previousScroll)}
document.addEventListener('click',event=>{
  const open=event.target.closest('[data-open-courier]');if(open){openCourier360(open.dataset.openCourier);return}
  if(event.target.closest('[data-c360-close]')){closeCourier360();return}
  if(event.target.closest('[data-c360-refresh]')){loadCourier360();return}
  if(event.target.closest('[data-c360-profile]')){openCourierProfile();return}
  if(event.target.closest('[data-c360-close-day]')){c360CloseDay();return}
  const filter = event.target.closest('[data-c360-live-filter]');
  if (filter) {
    const input = filter.closest('[data-c360-search-area]').querySelector('.c360-search input');
    const active = filter.getAttribute('aria-pressed') === 'true';
    input.value = active && input.form.id === 'attendance-c360-search' ? '' : filter.dataset.c360LiveFilter;
    if (document.activeElement === input) c360RenderSearch(input);
    else input.focus();
    return;
  }
  const selected = event.target.closest('[data-c360-switch]');
  if (selected) {
    const form = selected.closest('.c360-search');
    c360DismissSearch(form);
    c360SwitchCourier(selected.dataset.c360Switch,form);
    return;
  }
  c360DismissOtherSearches(event.target);
  const day=event.target.closest('[data-c360-day]');
  if(day){c360OpenDay(day);return}
  const monthStep=event.target.closest('[data-c360-month-step]');
  if (monthStep) {
    const step=Number(monthStep.dataset.c360MonthStep);
    const cursor=new Date(courier360State.calendarMonth+'-01T12:00:00Z');
    cursor.setUTCMonth(cursor.getUTCMonth()+step);
    courier360State.calendarMonth=step ? cursor.toISOString().slice(0,7) : c360Today().slice(0,7);
    $('.c360-calendar').outerHTML=c360Calendar(courier360State.date);
    c360LoadCalendar();
    $(`[data-c360-month-step="${step}"]`)?.focus();
    return;
  }
  const tab=event.target.closest('[data-c360-go]');if(tab)c360SelectTab(tab.dataset.c360Go);
});
document.addEventListener('input', event => {
  if (event.target.matches('.c360-search input')) c360RenderSearch(event.target);
});
document.addEventListener('focusin', event => {
  c360DismissOtherSearches(event.target);
  if (event.target.matches('.c360-search input')) c360RenderSearch(event.target);
});
document.addEventListener('submit', event => {
  const form = event.target;
  if (!form.matches('.c360-search')) return;
  event.preventDefault();
  const input = form.querySelector('input');
  if (c360ActiveQuery(input.value)) { c360RenderSearch(input); return; }
  const id = input.value.trim().replace(/^#/, '');
  const matches = c360SearchMatches(input.value,form);
  if (/^\d{1,12}$/.test(id) || matches.length === 1) {
    c360DismissSearch(form);
    c360SwitchCourier(/^\d{1,12}$/.test(id) ? id : matches[0].courierId,form);
  } else c360RenderSearch(input);
});
document.addEventListener('keydown', event => {
  if (event.key === 'Escape' && $('#c360-day-dialog')?.open) {
    event.preventDefault();
    c360CloseDay();
    return;
  }
  const form = event.target.closest('.c360-search');
  if (!form) return;
  const input = form.querySelector('input');
  if (event.key === 'Escape') {
    event.preventDefault();
    input.focus();
    c360DismissSearch(form);
  } else if (event.key === 'ArrowDown' && event.target === input) {
    const first = form.querySelector('.c360-search-results:not([hidden]) button');
    if (first) { event.preventDefault(); first.focus(); }
  }
});
document.addEventListener('change',event=>{if(event.target.id==='c360-date'&&event.target.value){courier360State.date=event.target.value;courier360State.calendarMonth=event.target.value.slice(0,7);loadCourier360()}if(event.target.id==='c360-month'&&event.target.value){courier360State.month=event.target.value;loadCourier360()}});
document.addEventListener('visibilitychange',()=>{if(!document.hidden)c360RefreshLive()});
