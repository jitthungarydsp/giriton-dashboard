/* Monthly status details. Opening the dialog never changes financial/workflow data. */
let statusDialogSequence=0;
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
function statusDialogBody(p,kind){
  const failed=(p.sources||[]).filter(s=>s.available===false&&['peopleforce_complaints','peopleforce_documents','peopleforce_card_statuses','courier_finance_snapshot'].includes(s.table));
  const warning=failed.length?'<div class="notice" role="alert">Egyes adatok nem tölthetők be. A hiányzó adat nem jelent lezárt vagy kifizetett állapotot.</div>':'';
  let body;
  if(kind==='complaints')body=c360Complaints({...p,complaints:p.complaints||[]});
  else if(kind==='invoice')body=statusDialogWorkflow(p,['invoice_submit','invoice_check','invoice_payment'])+statusDialogDocuments(p,true)+
    `<h3>Számlához tartozó bejelentések</h3>`+c360Complaints({...p,complaints:(p.complaints||[]).filter(c=>/invoice/.test(c.document_type))});
  else if(kind==='payment')body=`<div class="status-dialog-total"><span>Kifizetendő a havi pénzügyi mentés szerint</span><strong>${p.finance?huf(p.finance.payable):'Nincs rögzített pénzügyi adat'}</strong></div>`+
    statusDialogWorkflow(p,['invoice_check','invoice_payment'])+statusDialogDocuments(p,true);
  else body=statusDialogWorkflow(p,['settlement','tig','invoice_submit','invoice_check','invoice_payment'])+statusDialogDocuments(p);
  return warning+body;
}
function closeStatusDialog(){statusDialogSequence++;$('#courier-status-dialog').close();}
async function openStatusDialog(courierId,status){
  const dialog=$('#courier-status-dialog'),body=$('#status-dialog-body'),month=$('#month').value;
  const sequence=++statusDialogSequence;
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
    body.innerHTML=statusDialogBody(p,kind);
  }catch(error){if(sequence===statusDialogSequence&&dialog.open)body.innerHTML=`<div class="notice" role="alert">Az adatok nem tölthetők be: ${esc(error.message)}</div><button type="button" class="c360-button" data-status-retry="${esc(courierId)}" data-status-label="${esc(status)}">Újrapróbálás</button>`;}
}
document.addEventListener('click',event=>{
  const button=event.target.closest('[data-status-courier],[data-status-retry]');
  if(button){event.stopPropagation();openStatusDialog(button.dataset.statusCourier||button.dataset.statusRetry,button.dataset.statusLabel);return;}
  if(event.target.closest('[data-status-close]'))closeStatusDialog();
  if(event.target.id==='courier-status-dialog'){
    const box=event.target.getBoundingClientRect();
    if(event.clientX<box.left||event.clientX>box.right||event.clientY<box.top||event.clientY>box.bottom)closeStatusDialog();
  }
},true);
document.addEventListener('cancel',event=>{if(event.target.id==='courier-status-dialog')statusDialogSequence++;},true);
