/* Monthly status details. Opening the dialog never changes financial/workflow data. */
let statusDialogSequence=0;
let statusDialogPayload=null;
let statusDialogComplaintId=null;
const statusDialogTabs=[['workflow','Elszámolási folyamat'],['complaints','Reklamáció'],['finance','Pénzügyi hatás'],['payment','Ellenőrzés és utalás'],['history','Előzmények'],['documents','Dokumentumok']];
function statusDialogKind(status){
  if(status==='Reklamáció')return 'complaints';
  if(/számla.*ellenőrz/i.test(status))return 'invoice';
  if(/kifizet/i.test(status))return 'payment';
  return 'workflow';
}
function statusDialogDocuments(p,invoiceOnly=false){
  const documents=(p.documents||[]).filter(d=>!invoiceOnly||['invoice','cash_invoice','kp_invoice'].includes(d.document_type));
  return `<h3>${invoiceOnly?'Feltöltött számlák':'Havi dokumentumok'}</h3>${c360Table(['Dokumentum','Feltöltés','Megnyitás'],documents.map(d=>[
    esc(d.title||d.file_name||d.document_type),c360Date(d.uploaded_at),
    `<a class="c360-button" href="/api/courier360-document?courier=${encodeURIComponent(p.courier.id)}&id=${encodeURIComponent(d.id)}" target="_blank" rel="noopener">Megnyitás ↗</a>`]))}`;
}
function statusDialogWorkflow(p,keys){
  const labels={settlement:'Elszámolás elfogadása',tig:'Teljesítés-összesítő',invoice_submit:'Számlafeltöltés',invoice_check:'Számlaellenőrzés',invoice_payment:'Kifizetés'};
  return c360Table(['Lépés','Állapot','Időpont','Megjegyzés'],keys.map(key=>{
    const row=(p.workflowStates||{})[key];
    return [labels[key],row?esc(row.status==='done'?'Kész':row.status==='open'?'Folyamatban':row.status):'Nincs rögzítve',c360Date(row?.updated_at),esc(row?.status_note||'—')];
  }));
}
function paymentDocumentLink(p,document){
  return document?`<a class="payment-document" href="/api/courier360-document?courier=${encodeURIComponent(p.courier.id)}&id=${encodeURIComponent(document.id)}" target="_blank" rel="noopener">${esc(document.title||document.file_name||'Dokumentum')} ↗</a>`:'<span class="payment-muted">Nincs feltöltött számla</span>';
}
function paymentInvoiceCard(p,title,item={}){
  const known=value=>value!==null&&value!==undefined;
  const messages={match:'✓ Az összegek egyeznek',mismatch:'Eltér a teljesítésigazolástól',missing:'Hiányzik a számla',unknown:'Az összeg nem ellenőrizhető',not_required:'KP-s számla nem szükséges'};
  return `<section class="payment-invoice"><h3>${esc(title)}</h3>
    <dl class="payment-values"><div><dt>Igazolás szerinti összeg</dt><dd>${known(item.expectedHuf)?huf(item.expectedHuf):'Nincs mentett bontás'}</dd></div>
    <div><dt>Rögzített számlaösszeg</dt><dd>${known(item.actualHuf)?huf(item.actualHuf):'Nincs rögzítve'}</dd></div></dl>
    <div class="payment-match ${esc(item.result||'unknown')}"><span>${messages[item.result]||messages.unknown}</span>${known(item.differenceHuf)?`<span>${huf(item.differenceHuf)} eltérés</span>`:''}</div>
    <div class="payment-file">${paymentDocumentLink(p,item.document)}${item.document?`<small>Feltöltve: ${c360Date(item.document.uploaded_at)} · ${esc(item.document.uploaded_by||'Ismeretlen feltöltő')}</small>`:''}</div>
    <p class="payment-meta">${item.check?`${item.check.status==='done'?'Jóváhagyva':'Ellenőrzés nyitott'}: ${esc(item.check.updated_by||'Ismeretlen')} · ${c360Date(item.check.updated_at)}`:item.result==='not_required'?'A mentett KP-s rész 0 Ft.':'Az aktuális számla jóváhagyása nincs rögzítve.'}</p></section>`;
}
function paymentHistory(payment){
  return `<p class="payment-muted payment-caption">A rögzített események és az állapotok utolsó módosításai. Korábbi állapotváltásokat a rendszer nem következtet ki.</p><ol class="payment-timeline">${(payment.events||[]).map(row=>`<li class="${row.kind==='complaint'?'is-complaint':''}"><div class="payment-event-title">${esc(row.label)}${row.kind==='current_state'?'<span class="payment-state-tag">Utolsó állapotmódosítás</span>':''}</div><div class="payment-meta">${c360Date(row.at)} · ${esc(row.actor||'Nincs rögzített felhasználó')}</div>${row.detail?`<p>${esc(row.detail)}</p>`:''}</li>`).join('')||'<li>Nincs rögzített esemény.</li>'}</ol>`;
}
function statusDialogPayment(p){
  const payment=p.payment||{amountHuf:p.finance?.payable,transfer:{},cash:{},blockingReasons:['A kifizetési részletek nem érhetők el.'],events:[]},states=p.workflowStates||{};
  const steps=[['settlement','Elszámolás'],['tig','Teljesítésigazolás'],['invoice_check','Számlák'],['invoice_payment','Kifizetés']];
  const amount=payment.amountHuf!==null&&payment.amountHuf!==undefined?huf(payment.amountHuf):'Nincs mentett összeg';
  const field=(label,value,copy=false)=>`<div><dt>${label}</dt><dd>${esc(value||'Nincs rögzítve')}${copy&&value?`<button type="button" class="payment-copy" data-payment-copy="${esc(value)}" aria-label="${label} másolása">Másolás</button>`:''}</dd></div>`;
  return `<section class="payment-view" aria-label="Havi kifizetési ellenőrzőlap">
    <div class="payment-heading"><span class="payment-state ${payment.closed?'is-paid':''}">${payment.closed?'✓ Kifizetve':'Kifizetésre vár'}</span><span class="payment-meta">${payment.snapshotVersion!==null&&payment.snapshotVersion!==undefined?`Pénzügyi mentés: ${esc(payment.snapshotVersion)}. verzió`:'Nincs pénzügyi mentés'}</span></div>
    <ol class="payment-steps">${steps.map(([action,label])=>`<li class="${states[action]?.status==='done'?'is-done':''}"><span>${states[action]?.status==='done'?'✓':'○'}</span> ${label}</li>`).join('')}</ol>
    <div id="payment-overview">
      <div class="payment-section-heading"><h3>Teljesítésigazolás és számlák</h3></div>
      <div class="payment-invoices">${paymentInvoiceCard(p,'Átutalásos számla',payment.transfer)}${paymentInvoiceCard(p,'KP-s számla',payment.cash)}</div>
      <p class="payment-caption payment-muted">Az összevetés a feltöltéskor rögzített számlaösszeget használja; nem végez új PDF-ellenőrzést. A számlák a fenti hivatkozásokkal nyithatók meg.</p>
      <details class="payment-tig"><summary>Teljesítésigazolás részletei</summary>${(payment.tigDocuments||[]).map(d=>paymentDocumentLink(p,d)).join('<br>')}${c360Table(['Tétel','Nettó','ÁFA','Bruttó'],(payment.tigBreakdown?.rows||[]).map(row=>[esc(row.label||row.key),row.netHuf==null?'—':huf(row.netHuf),row.vatHuf==null?'—':huf(row.vatHuf),row.grossHuf==null?'—':huf(row.grossHuf)]))}</details>
      <section class="payment-bank"><div class="payment-section-heading"><h3>Utalási adatok</h3><span class="payment-meta">${payment.closed?'Lezáráskor rögzített adatok':'Aktuális számlázási adatok'}</span></div><dl class="payment-bank-grid">${field('Kedvezményezett',payment.recipientName,true)}${field('Bankszámlaszám',payment.bankAccount,true)}${field('Közlemény',payment.paymentNote,true)}${field('Számla sorszáma',payment.invoiceNumber)}</dl>
      ${!payment.bankAccount&&!payment.closed?`<form class="payment-bank-form"><label for="payment-bank-account">Hiányzó bankszámlaszám megadása</label><div class="payment-bank-input"><input id="payment-bank-account" name="bankAccount" type="text" inputmode="numeric" autocomplete="off" maxlength="40" required placeholder="12345678-12345678-12345678"><button type="submit" class="payment-primary">Bankszámlaszám mentése</button></div><p class="payment-meta">16, 24 vagy 32 számjegy. A futár törzsadatába mentjük, a későbbi kifizetésekhez is. Ez nem rögzít kifizetést.</p><p class="payment-save-message" role="alert"></p></form>`:''}
      <div class="payment-transfer-total"><div><h3>${payment.closed?'Rögzített kifizetés':Number(payment.amountHuf)<0?'Elszámolási egyenleg':'Átutalandó összeg'}</h3><p>A KP-s számla külön elszámolva</p></div><strong>${amount}</strong></div>
      <p class="payment-meta">Kifizetendő a havi pénzügyi mentés szerint: ${p.finance?huf(p.finance.payable):'Nincs rögzítve'}</p></section>
      ${payment.closed?`<div class="payment-ready is-paid">✓ Kifizetés rögzítve: ${c360Date(payment.closedAt)} · ${esc(payment.closedBy||'Ismeretlen rögzítő')}<small>Adminisztrátori rögzítés; banki visszaigazolást nem tartalmaz.</small></div>`:payment.blockingReasons?.length?`<ul class="payment-blockers">${payment.blockingReasons.map(reason=>`<li>${esc(reason)}</li>`).join('')}</ul>`:'<p class="payment-ready">✓ A kifizetés adminisztrátori rögzítésének feltételei rendelkezésre állnak.</p>'}
      <div class="payment-footer"><span class="payment-muted">A rögzítés nem indít banki utalást.</span>${!payment.closed?`<button type="button" class="payment-primary" data-payment-record ${payment.canClose?'':'disabled'}>${payment.amountHuf!=null&&Number(payment.amountHuf)<=0?'Havi folyamat lezárása':'Kifizetés rögzítése'}</button>`:''}</div>
      <form class="payment-record-form" hidden><h3>Kifizetés rögzítése</h3><p>${amount} · ${esc(payment.recipientName||'Hiányzó kedvezményezett')}</p><label for="payment-close-note">Lezárási megjegyzés (kötelező, az összeggel)</label><textarea id="payment-close-note" name="note" rows="3" maxlength="2000" required>${esc(`Kifizetve: ${amount}`)}</textarea><p class="payment-meta">A rögzítés időpontját és a bejelentkezett felhasználót a rendszer automatikusan menti. Az utalás dátumát és hivatkozását a megjegyzésben adhatod meg.</p><div class="payment-form-actions"><button type="button" class="c360-button" data-payment-cancel>Mégse</button><button type="submit" class="payment-primary">Rögzítés véglegesítése</button></div><p class="payment-save-message" role="alert"></p></form>
    </div>
    <p id="payment-copy-result" class="payment-meta" aria-live="polite"></p>
  </section>`;
}
function complaintStatusLabel(row){return ({new:'Új',open:row?.admin_response?'Megválaszolt · nyitott':'Nyitott',in_progress:'Vizsgálat alatt',resolved:'Megoldva',closed:'Lezárva'})[row?.status]||row?.status||'Ismeretlen';}
function complaintActionLabel(type){return ({settlement:'Elszámolás',tig:'Teljesítésigazolás',invoice:'Számla',invoice_submit:'Számlafeltöltés',invoice_check:'Számlaellenőrzés',invoice_payment:'Kifizetés'})[String(type||'').split(':').at(-1)]||type||'Nincs rögzítve';}
function statusDialogComplaintCase(p){
  const rows=p.complaints||[],row=rows.find((r,i)=>String(r.id||i)===String(statusDialogComplaintId))||rows[0];
  if(!row)return '<div class="empty">Ehhez a futárhoz és hónaphoz nincs rögzített reklamáció.</div>';
  statusDialogComplaintId=String(row.id||rows.indexOf(row));
  const closed=['resolved','closed'].includes(row.status),noteAvailable=!(p.sources||[]).some(s=>s.table==='peopleforce_complaint_notes'&&!s.available),editable=/^[0-9a-f-]{36}$/i.test(row.id||'')&&noteAvailable;
  const related=(p.documents||[]).filter(d=>row.id&&(d.note||'').includes(row.id)||(row.id&&(d.title||'').includes(row.id)));
  return `<div class="complaint-case" data-complaint-id="${esc(row.id||'')}"><div class="complaint-context"><span class="complaint-badge ${closed?'is-closed':''}">${esc(complaintStatusLabel(row))}</span><span class="payment-meta">Ügy: ${esc(row.id||'Azonosító nem érhető el')} · ${c360Date(row.created_at)}</span></div>
    <div class="complaint-grid"><article class="complaint-card"><h3>Futár bejelentése</h3><p class="payment-meta">${esc(row.created_by||p.courier.name)} · ${c360Date(row.created_at)}</p><blockquote>${esc(row.message||'Nincs rögzített bejelentésszöveg.')}</blockquote><h4>Az ügyhöz kapcsolt dokumentumok</h4>${related.length?related.map(d=>paymentDocumentLink(p,d)).join('<br>'):'<p class="payment-meta">Nincs az ügyazonosítóhoz kapcsolt dokumentum. Az összes havi irat a Dokumentumok fülön elérhető.</p>'}</article>
    <article class="complaint-card"><h3>Adminisztrátori vizsgálat</h3><dl class="complaint-facts"><div><dt>Érintett lépés</dt><dd>${esc(complaintActionLabel(row.document_type))}</dd></div><div><dt>Utolsó válaszadó</dt><dd>${esc(row.responded_by||'Még nincs rögzítve')}</dd></div><div><dt>Válasz időpontja</dt><dd>${c360Date(row.responded_at)}</dd></div><div><dt>Havi pénzügyi mentés</dt><dd>${p.financeSnapshot?`${esc(p.financeSnapshot.version)}. verzió`:'Nincs rögzítve'}</dd></div></dl><button type="button" class="complaint-link" data-status-open="finance">Mentett pénzügyi változások megtekintése →</button></article></div>
    ${row.admin_response?`<article class="complaint-answer"><h3>Legutóbbi rögzített válasz</h3><p>${esc(row.admin_response)}</p></article>`:''}
    ${editable?`<div class="complaint-controls">${closed?'<button type="button" class="c360-button" data-complaint-action="reopen">Ügy visszanyitása</button>':`${row.status!=='in_progress'?'<button type="button" class="c360-button" data-complaint-action="start">Vizsgálat megkezdése</button>':''}<button type="button" class="c360-button" data-complaint-action="respond">Válasz megadása</button><button type="button" class="payment-primary" data-complaint-action="close">Válasz és lezárás</button>`}</div>
    <form class="complaint-response-form" hidden><h3 class="complaint-form-title">Válasz</h3><input type="hidden" name="action" value="respond"><div class="complaint-close-fields" hidden><label>Eredmény<select name="decision"><option value="accepted">Elfogadva</option><option value="partial">Részben elfogadva</option><option value="rejected">Elutasítva</option></select></label><label class="complaint-review"><input type="checkbox" name="financeReviewed">Ellenőriztem a pénzügyi hatást; a szükséges javítást külön elvégeztem, vagy javítás nem szükséges.</label></div><label for="complaint-response">Futárnak szóló válasz / indoklás</label><textarea id="complaint-response" name="response" rows="4" maxlength="5000" required></textarea><p class="payment-meta">A mentett választ a futár a saját folyamatában látja. A lezárás nem módosítja a pénzügyi mentést.</p><div class="payment-form-actions"><button type="button" class="c360-button" data-complaint-cancel>Mégse</button><button type="submit" class="payment-primary">Megerősítés és mentés</button></div><p class="complaint-feedback" role="alert"></p></form>`:'<p class="notice">'+(noteAvailable?'Az ügy mentéséhez nem érhető el érvényes azonosító.':'Az ügykezeléshez szükséges belső naplóforrás jelenleg nem érhető el.')+'</p>'}
    <details class="complaint-internal"><summary>Havi belső megjegyzés és ügyintézési napló · a futár nem látja</summary><p class="payment-meta">A kiválasztott futár teljes hónapjához tartozó közös belső megjegyzés. Az ügykezelési bejegyzések itt is megőrződnek.</p>${noteAvailable&&editable?`<form class="complaint-note-form"><label for="complaint-note">Havi belső megjegyzés</label><textarea id="complaint-note" name="note" rows="6" maxlength="20000">${esc(p.complaintNote?.note||'')}</textarea><button class="c360-button" type="submit">Belső megjegyzés mentése</button><p class="complaint-feedback" role="alert"></p></form>`:'<p class="notice">A belső megjegyzés jelenleg nem érhető el.</p>'}<p class="payment-meta">${esc(p.complaintNote?.updated_by||'')} ${p.complaintNote?.updated_at?'· '+c360Date(p.complaintNote.updated_at):''}</p></details><p class="complaint-action-message" role="alert"></p></div>`;
}
function statusDialogComplaints(p){
  const rows=p.complaints||[];
  const selected=rows.find(row=>String(row.id)===statusDialogComplaintId)||rows.find(row=>!['closed','resolved'].includes(row.status))||rows[0];statusDialogComplaintId=selected?String(selected.id||rows.indexOf(selected)):null;
  return `<section class="complaint-view" aria-label="Reklamációs ügyintézés">${rows.length?`<label class="complaint-picker">Reklamáció kiválasztása<select id="complaint-selector">${rows.map((row,i)=>`<option value="${esc(row.id||i)}" ${String(row.id||i)===statusDialogComplaintId?'selected':''}>${esc(complaintStatusLabel(row))} · ${esc(complaintActionLabel(row.document_type))} · ${esc((row.message||'').slice(0,90))}</option>`).join('')}</select></label>`:''}<div id="complaint-selected-case">${statusDialogComplaintCase(p)}</div></section>`;
}
function statusDialogFinance(p){
  const comparison=p.financeComparison;
  return `<section class="complaint-finance"><h3>Mentett pénzügyi változások</h3><p class="payment-meta">A legutóbbi mentés és a hozzá hivatkozott előző változat összevetése. Ez nem bizonyítja, hogy a változást a kiválasztott reklamáció okozta.</p>${comparison?.available?`<div class="complaint-context"><span>Előtte: ${esc(comparison.before.version)}. verzió · ${c360Date(comparison.before.createdAt)}</span><span>Utána: ${esc(comparison.after.version)}. verzió · ${c360Date(comparison.after.createdAt)}</span></div>${comparison.rows.length?c360Table(['Tétel','Előtte','Utána','Változás'],comparison.rows.map(row=>[esc(row.label),row.beforeHuf===null?'Nem szerepel a mentésben':huf(row.beforeHuf),row.afterHuf===null?'Nem szerepel a mentésben':huf(row.afterHuf),row.differenceHuf===null?'Nem számolható':huf(row.differenceHuf)])):'<div class="empty">A két mentés pénzügyi tételei nem változtak.</div>'}`:'<div class="empty">Nincs két összekapcsolt, elérhető pénzügyi mentés az összehasonlításhoz. Hiányzó adatot nem mutatunk 0 Ft-ként.</div>'}<p class="payment-meta">A reklamáció megválaszolása és lezárása nem indít új pénzügyi elszámolást.</p></section>`;
}
function selectStatusDialogTab(name){
  const root=$('#status-dialog-body');root.querySelectorAll('[data-status-tab]').forEach(button=>{const selected=button.dataset.statusTab===name;button.setAttribute('aria-selected',String(selected));root.querySelector('#status-panel-'+button.dataset.statusTab).hidden=!selected;});
}
function statusDialogHistory(p){
  const events=[...(p.payment?.events||p.eventLog||[])];
  const add=event=>{if(event.at&&!events.some(row=>row.at===event.at&&row.label===event.label&&row.detail===event.detail))events.push(event);};
  for(const row of p.complaints||[]){add({at:row.created_at,label:'Reklamáció érkezett',detail:row.message,actor:row.created_by,kind:'complaint'});add({at:row.responded_at,label:'Reklamáció megválaszolva',detail:row.admin_response,actor:row.responded_by,kind:'complaint'});}
  if(p.complaintNote?.note)add({at:p.complaintNote.updated_at,label:'Havi belső ügyintézési napló és megjegyzés',detail:p.complaintNote.note,actor:p.complaintNote.updated_by,kind:'internal_note'});
  for(const saved of [p.financeComparison?.before,p.financeComparison?.after])if(saved)add({at:saved.createdAt,label:`Pénzügyi mentés · ${saved.version}. verzió`,detail:'Mentett pénzügyi változat; a reklamációval való okozati kapcsolat nincs megállapítva.',actor:saved.createdBy});
  events.sort((a,b)=>String(b.at).localeCompare(String(a.at)));return paymentHistory({events});
}
function statusDialogBody(p,kind){
  const failed=(p.sources||[]).filter(s=>s.available===false&&['peopleforce_complaints','peopleforce_documents','peopleforce_card_statuses','courier_finance_snapshot'].includes(s.table));
  const warning=failed.length?'<div class="notice" role="alert">Egyes adatok nem tölthetők be. A hiányzó adat nem jelent lezárt vagy kifizetett állapotot.</div>':'';
  const active=kind==='invoice'?'payment':kind,contents={workflow:()=>statusDialogWorkflow(p,['settlement','tig','invoice_submit','invoice_check','invoice_payment']),complaints:()=>statusDialogComplaints(p),finance:()=>statusDialogFinance(p),payment:()=>statusDialogPayment(p),history:()=>statusDialogHistory(p),documents:()=>statusDialogDocuments(p)};
  return warning+`<div class="status-workspace"><nav class="payment-tabs status-workspace-tabs" role="tablist" aria-label="Havi elszámolás menü">${statusDialogTabs.map(([name,label])=>`<button type="button" role="tab" id="status-tab-${name}" aria-controls="status-panel-${name}" aria-selected="${name===active}" data-status-tab="${name}">${label}</button>`).join('')}</nav>${statusDialogTabs.map(([name])=>`<div role="tabpanel" id="status-panel-${name}" aria-labelledby="status-tab-${name}" ${name===active?'':'hidden'}>${contents[name]()}</div>`).join('')}</div>`;
}
function closeStatusDialog(){statusDialogSequence++;statusDialogPayload=null;$('#courier-status-dialog').close();}
async function openStatusDialog(courierId,status,complaintId=null){
  const dialog=$('#courier-status-dialog'),body=$('#status-dialog-body'),month=$('#month').value;
  const sequence=++statusDialogSequence;
  statusDialogPayload=null;
  statusDialogComplaintId=complaintId;
  const courier=(data?.couriers||[]).find(r=>String(r.courierId)===String(courierId));
  const kind=statusDialogKind(status);
  const title={complaints:'Reklamáció',invoice:'Számlaellenőrzés',payment:'Kifizetés',workflow:'Elszámolási folyamat'}[kind];
  $('#status-dialog-title').textContent=`${title} · ${courier?.courierName||courierId}`;
  $('#status-dialog-context').textContent=`#${courierId} · ${monthLabel(month)} · ${status}`;
  body.innerHTML='<div class="empty" role="status">Havi adatok betöltése…</div>';
  if(!dialog.open)dialog.showModal();
  try{
    const today=new Intl.DateTimeFormat('en-CA',{timeZone:'Europe/Budapest',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date());
    const p=await api(`/api/courier360?courier=${encodeURIComponent(courierId)}&month=${encodeURIComponent(month)}&date=${encodeURIComponent(today)}`);
    if(sequence!==statusDialogSequence||!dialog.open)return;
    if(String(p.courier?.id)!==String(courierId)||p.periodStart!==month+'-01')throw new Error('A kapott adatok nem a kiválasztott futárhoz és hónaphoz tartoznak.');
    statusDialogPayload=p;body.innerHTML=statusDialogBody(p,kind);dialog.scrollTop=0;
  }catch(error){if(sequence===statusDialogSequence&&dialog.open)body.innerHTML=`<div class="notice" role="alert">Az adatok nem tölthetők be: ${esc(error.message)}</div><button type="button" class="c360-button" data-status-retry="${esc(courierId)}" data-status-label="${esc(status)}">Újrapróbálás</button>`;}
}
document.addEventListener('click',event=>{
  const statusTab=event.target.closest('[data-status-tab],[data-status-open]');
  if(statusTab){selectStatusDialogTab(statusTab.dataset.statusTab||statusTab.dataset.statusOpen);return;}
  const complaintAction=event.target.closest('[data-complaint-action]');
  if(complaintAction){const action=complaintAction.dataset.complaintAction;
    if(action==='start'){saveStatusComplaintAction(action,{},complaintAction.closest('.complaint-case'));return;}
    const form=$('.complaint-response-form');form.hidden=false;form.elements.action.value=action;form.querySelector('.complaint-close-fields').hidden=action!=='close';form.elements.financeReviewed.required=action==='close';form.querySelector('.complaint-form-title').textContent=action==='close'?'Válasz és lezárás':action==='reopen'?'Visszanyitás indoklása':'Válasz a futárnak';form.querySelector('textarea').focus();return;
  }
  if(event.target.closest('[data-complaint-cancel]')){$('.complaint-response-form').hidden=true;return;}
  const tab=event.target.closest('[data-payment-tab]');
  if(tab){const view=tab.closest('.payment-view');view.querySelectorAll('[data-payment-tab]').forEach(button=>{const selected=button===tab;button.setAttribute('aria-selected',String(selected));view.querySelector('#'+button.dataset.paymentTab).hidden=!selected});return;}
  const copy=event.target.closest('[data-payment-copy]');
  if(copy){const output=$('#payment-copy-result');if(!navigator.clipboard){output.textContent='Jelöld ki és másold az adatot.';return;}navigator.clipboard.writeText(copy.dataset.paymentCopy).then(()=>{output.textContent='Adat a vágólapra másolva.'}).catch(()=>{output.textContent='A másolás nem sikerült. Jelöld ki és másold az adatot.'});return;}
  if(event.target.closest('[data-payment-record]')){const form=$('.payment-record-form');form.hidden=false;form.querySelector('textarea').focus();return;}
  if(event.target.closest('[data-payment-cancel]')){$('.payment-record-form').hidden=true;return;}
  const button=event.target.closest('[data-status-courier],[data-status-retry]');
  if(button){event.stopPropagation();openStatusDialog(button.dataset.statusCourier||button.dataset.statusRetry,button.dataset.statusLabel,button.dataset.statusComplaint||null);return;}
  if(event.target.closest('[data-status-close]'))closeStatusDialog();
  if(event.target.id==='courier-status-dialog'){
    const box=event.target.getBoundingClientRect();
    if(event.clientX<box.left||event.clientX>box.right||event.clientY<box.top||event.clientY>box.bottom)closeStatusDialog();
  }
},true);
document.addEventListener('keydown',event=>{
  const statusTab=event.target.closest('[data-status-tab]');
  if(statusTab&&['ArrowLeft','ArrowRight','Home','End'].includes(event.key)){event.preventDefault();const tabs=[...statusTab.parentElement.querySelectorAll('[data-status-tab]')],i=tabs.indexOf(statusTab),next=event.key==='Home'?0:event.key==='End'?tabs.length-1:(i+(event.key==='ArrowRight'?1:-1)+tabs.length)%tabs.length;tabs[next].click();tabs[next].focus();return;}
  const tab=event.target.closest('[data-payment-tab]');if(!tab||!['ArrowLeft','ArrowRight','Home','End'].includes(event.key))return;
  event.preventDefault();const tabs=[...tab.parentElement.querySelectorAll('[data-payment-tab]')],index=tabs.indexOf(tab),next=event.key==='Home'?0:event.key==='End'?tabs.length-1:(index+(event.key==='ArrowRight'?1:-1)+tabs.length)%tabs.length;tabs[next].click();tabs[next].focus();
});
document.addEventListener('change',event=>{
  if(event.target.id!=='complaint-selector')return;
  const dirty=$('.complaint-response-form:not([hidden])'),note=$('.complaint-note-form textarea');if((dirty&&dirty.elements.response.value.trim()||note&&note.value!==(statusDialogPayload?.complaintNote?.note||''))&&!window.confirm('A nem mentett válasz vagy belső megjegyzés elvész. Másik ügyre váltasz?')){event.target.value=statusDialogComplaintId;return;}
  statusDialogComplaintId=event.target.value;$('#complaint-selected-case').innerHTML=statusDialogComplaintCase(statusDialogPayload);
});
async function saveStatusComplaintAction(action,fields,container){
  const p=statusDialogPayload,row=(p?.complaints||[]).find(row=>String(row.id)===statusDialogComplaintId),sequence=statusDialogSequence;
  if(!p||!row||container.dataset.saving)return;
  const message=container.matches('.complaint-case')?container.querySelector('.complaint-action-message'):container.querySelector('.complaint-feedback');container.dataset.saving='true';container.querySelectorAll('button').forEach(button=>button.disabled=true);message.textContent='Mentés folyamatban…';
  try{
    const result=await api('/api/courier360-complaint',{method:'POST',body:JSON.stringify({courierId:p.courier.id,month:p.periodStart.slice(0,7),complaintId:row.id,action,expected:{status:row.status,adminResponse:row.admin_response??null,respondedAt:row.responded_at??null},expectedNote:p.complaintNote?.note||'',snapshotId:p.financeSnapshot?.id||'',...fields})});
    if(sequence===statusDialogSequence&&$('#courier-status-dialog').open){await openStatusDialog(p.courier.id,'Reklamáció',row.id);const output=$('.complaint-action-message');if(output)output.textContent=result.warning||'Az ügy módosítása mentve.';}
    if(action!=='note'&&typeof load==='function')await load();
  }catch(error){if(sequence===statusDialogSequence){message.textContent=error.message;delete container.dataset.saving;container.querySelectorAll('button').forEach(button=>button.disabled=false);}}
}
document.addEventListener('submit',async event=>{
  if(event.target.matches('.complaint-response-form,.complaint-note-form')){
    event.preventDefault();const form=event.target;
    if(form.matches('.complaint-note-form'))await saveStatusComplaintAction('note',{note:form.elements.note.value},form);
    else await saveStatusComplaintAction(form.elements.action.value,{response:form.elements.response.value,decision:form.elements.decision.value,financeReviewed:form.elements.financeReviewed.checked},form);
    return;
  }
  if(event.target.matches('.payment-bank-form')){
    event.preventDefault();const p=statusDialogPayload,sequence=statusDialogSequence,form=event.target,submit=form.querySelector('[type="submit"]'),message=form.querySelector('.payment-save-message');
    if(!p||submit.disabled)return;
    submit.disabled=true;message.textContent='Bankszámlaszám mentése…';
    try{
      const result=await api('/api/courier360-bank-account',{method:'POST',body:JSON.stringify({courierId:p.courier.id,bankAccount:form.elements.bankAccount.value})});
      if(sequence===statusDialogSequence&&$('#courier-status-dialog').open){await openStatusDialog(p.courier.id,'Kifizetésre vár');const output=$('#payment-copy-result');if(output)output.textContent=result.warning||'Bankszámlaszám mentve. A kifizetési feltételeket újra ellenőriztük.';}
    }catch(error){if(sequence===statusDialogSequence){message.textContent=error.message;submit.disabled=false;}}
    return;
  }
  if(!event.target.matches('.payment-record-form'))return;
  event.preventDefault();const p=statusDialogPayload,sequence=statusDialogSequence,form=event.target,submit=form.querySelector('[type="submit"]'),message=form.querySelector('.payment-save-message');
  if(!p?.payment?.canClose||submit.disabled)return;
  submit.disabled=true;message.textContent='Rögzítés folyamatban…';
  try{
    await api('/api/courier360-payment-close',{method:'POST',body:JSON.stringify({courierId:p.courier.id,month:p.periodStart.slice(0,7),snapshotId:p.payment.snapshotId,note:form.elements.note.value})});
    if(sequence===statusDialogSequence&&$('#courier-status-dialog').open)await openStatusDialog(p.courier.id,'Kifizetve');
    if(typeof load==='function')await load();
  }catch(error){if(sequence===statusDialogSequence){message.textContent=error.message;submit.disabled=false;}}
});
document.addEventListener('cancel',event=>{if(event.target.id==='courier-status-dialog')statusDialogSequence++;},true);
