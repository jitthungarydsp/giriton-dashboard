/* Monthly status details. Opening the dialog never changes financial/workflow data. */
let statusDialogSequence=0;
let statusDialogPayload=null;
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
    <div class="payment-tabs" role="tablist" aria-label="Kifizetés részletei"><button type="button" id="payment-overview-tab" role="tab" aria-controls="payment-overview" aria-selected="true" data-payment-tab="payment-overview">Ellenőrzés és utalás</button><button type="button" id="payment-history-tab" role="tab" aria-controls="payment-history" aria-selected="false" data-payment-tab="payment-history">Előzmények · ${(payment.events||[]).length}</button></div>
    <div id="payment-overview" role="tabpanel" aria-labelledby="payment-overview-tab">
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
    <div id="payment-history" role="tabpanel" aria-labelledby="payment-history-tab" hidden>${paymentHistory(payment)}</div>
    <p id="payment-copy-result" class="payment-meta" aria-live="polite"></p>
  </section>`;
}
function statusDialogBody(p,kind){
  const failed=(p.sources||[]).filter(s=>s.available===false&&['peopleforce_complaints','peopleforce_documents','peopleforce_card_statuses','courier_finance_snapshot'].includes(s.table));
  const warning=failed.length?'<div class="notice" role="alert">Egyes adatok nem tölthetők be. A hiányzó adat nem jelent lezárt vagy kifizetett állapotot.</div>':'';
  let body;
  if(kind==='complaints')body=c360Complaints({...p,complaints:p.complaints||[]});
  else if(kind==='invoice')body=statusDialogWorkflow(p,['invoice_submit','invoice_check','invoice_payment'])+statusDialogDocuments(p,true)+
    `<h3>Számlához tartozó bejelentések</h3>`+c360Complaints({...p,complaints:(p.complaints||[]).filter(c=>/invoice/.test(c.document_type))});
  else if(kind==='payment')body=statusDialogPayment(p);
  else body=statusDialogWorkflow(p,['settlement','tig','invoice_submit','invoice_check','invoice_payment'])+statusDialogDocuments(p);
  return warning+body;
}
function closeStatusDialog(){statusDialogSequence++;statusDialogPayload=null;$('#courier-status-dialog').close();}
async function openStatusDialog(courierId,status){
  const dialog=$('#courier-status-dialog'),body=$('#status-dialog-body'),month=$('#month').value;
  const sequence=++statusDialogSequence;
  statusDialogPayload=null;
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
  const tab=event.target.closest('[data-payment-tab]');
  if(tab){const view=tab.closest('.payment-view');view.querySelectorAll('[data-payment-tab]').forEach(button=>{const selected=button===tab;button.setAttribute('aria-selected',String(selected));view.querySelector('#'+button.dataset.paymentTab).hidden=!selected});return;}
  const copy=event.target.closest('[data-payment-copy]');
  if(copy){const output=$('#payment-copy-result');if(!navigator.clipboard){output.textContent='Jelöld ki és másold az adatot.';return;}navigator.clipboard.writeText(copy.dataset.paymentCopy).then(()=>{output.textContent='Adat a vágólapra másolva.'}).catch(()=>{output.textContent='A másolás nem sikerült. Jelöld ki és másold az adatot.'});return;}
  if(event.target.closest('[data-payment-record]')){const form=$('.payment-record-form');form.hidden=false;form.querySelector('textarea').focus();return;}
  if(event.target.closest('[data-payment-cancel]')){$('.payment-record-form').hidden=true;return;}
  const button=event.target.closest('[data-status-courier],[data-status-retry]');
  if(button){event.stopPropagation();openStatusDialog(button.dataset.statusCourier||button.dataset.statusRetry,button.dataset.statusLabel);return;}
  if(event.target.closest('[data-status-close]'))closeStatusDialog();
  if(event.target.id==='courier-status-dialog'){
    const box=event.target.getBoundingClientRect();
    if(event.clientX<box.left||event.clientX>box.right||event.clientY<box.top||event.clientY>box.bottom)closeStatusDialog();
  }
},true);
document.addEventListener('keydown',event=>{
  const tab=event.target.closest('[data-payment-tab]');if(!tab||!['ArrowLeft','ArrowRight','Home','End'].includes(event.key))return;
  event.preventDefault();const tabs=[...tab.parentElement.querySelectorAll('[data-payment-tab]')],index=tabs.indexOf(tab),next=event.key==='Home'?0:event.key==='End'?tabs.length-1:(index+(event.key==='ArrowRight'?1:-1)+tabs.length)%tabs.length;tabs[next].click();tabs[next].focus();
});
document.addEventListener('submit',async event=>{
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
