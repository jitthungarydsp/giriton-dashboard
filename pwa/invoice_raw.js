/* Isolated RAW upload, comparison and working copy; no legacy settlement calculation. */
(() => {
  let env, mountedTarget;
  const state = {step:1,month:"",items:[],queue:[],loading:false,uploading:false,loadedMonth:"",hasMore:false,seq:0,listError:"",message:"",selected:new Set(),primary:"",working:null,diff:null,detail:null,keys:{},busy:false,pendingWork:null};
  const esc = value => env.escapeHtml(String(value ?? ""));
  const count = value => env.formatCount(value || 0);
  const when = value => value ? new Date(value).toLocaleString("hu-HU") : "–";

  function renderList() {
    return `<section class="invoice-raw-saved"><div class="device-history-head"><strong>A hónap feltöltött Exceljei</strong><span>${esc(env.formatMonthLabel(state.month))}</span></div>
      <button class="secondary" type="button" data-invoice-raw-action="reload" ${state.loading ? "disabled" : ""}>${state.loading ? "Lista betöltése…" : "Lista frissítése"}</button>
      ${state.listError ? `<p class="notice error" role="alert">${esc(state.listError)}</p>` : ""}
      ${state.items.length ? `<div class="invoice-raw-table-wrap"><table class="invoice-raw-table"><thead><tr><th>Kijelölés</th><th>Fájlnév</th><th>Sessionazonosító</th><th>Feltöltés ideje</th><th>Munkalapok</th><th>RAW sorok</th><th>Mentés állapota</th></tr></thead><tbody>
        ${state.items.map(item => `<tr data-invoice-row="${esc(item.id)}" class="${state.selected.has(item.id) ? "invoice-selected" : ""} ${state.primary===item.id ? "invoice-primary" : ""}"><td data-label="Kijelölés"><input type="checkbox" data-invoice-check="${esc(item.id)}" aria-label="${esc(item.source_file_name)} kijelölése" ${state.selected.has(item.id) ? "checked" : ""} ${state.busy ? "disabled" : ""} /></td><td data-label="Fájlnév"><span>${esc(item.source_file_name)}</span><button type="button" class="secondary invoice-primary-button" data-invoice-primary="${esc(item.id)}" ${state.busy ? "disabled" : ""}>${state.primary===item.id ? "✓ Elsődleges forrás" : "Legyen elsődleges"}</button></td><td data-label="Sessionazonosító">${esc(item.session_id)}</td><td data-label="Feltöltés ideje">${esc(when(item.created_at))}</td><td data-label="Munkalapok">${esc(count(item.sheet_count))}</td><td data-label="RAW sorok">${esc(count(item.raw_row_count))}</td><td data-label="Mentés állapota"><span class="invoice-raw-status">RAW mentve</span></td></tr>`).join("")}
      </tbody></table></div>` : !state.loading && !state.listError ? `<div class="empty-card">Ehhez a hónaphoz még nincs elmentett Excel.</div>` : ""}
      ${state.hasMore ? `<button class="secondary" type="button" data-invoice-raw-action="more" ${state.loading ? "disabled" : ""}>További feltöltések</button>` : ""}
      <p class="muted">${state.selected.size} fájl kijelölve. Egy fájl közvetlenül az előszobába kerül; több fájlt előbb összehasonlítunk.</p>
      ${state.working ? `<div class="notice">Aktív előszoba: <strong>${esc(state.working.source_file_name)}</strong> · ${esc(state.working.session_id)}<button type="button" class="secondary" data-invoice-raw-action="resume" ${state.busy ? "disabled" : ""}>Előszoba megnyitása</button></div>` : ""}
      <div class="settlement-import-actions"><button type="button" class="secondary" data-invoice-raw-action="delete" ${state.busy || state.uploading || !state.selected.size ? "disabled" : ""}>Kijelöltek törlése</button><button type="button" class="primary" data-invoice-raw-action="proceed" ${state.busy || state.loading || state.uploading || !state.selected.size ? "disabled" : ""}>${state.busy ? "Feldolgozás…" : state.selected.size>1 ? `Tovább – összehasonlítás (${state.selected.size})` : "Tovább – előszoba"}</button></div>
    </section>`;
  }

  function render() {
    if (!env?.target) return;
    if (state.step === "2a") { renderComparison(); return; }
    if (state.step === 3) { renderWorking(); return; }
    const steps = [[1,"Hónap","Elszámolási hónap kiválasztása"],[2,"Excel","Feltöltés és RAW mentés"],[3,"Előszoba","Elkülönített munkapéldány"],[4,"Validálás","Későbbi lépés"]];
    env.target.innerHTML = `<div class="settlement-import-stepper">${steps.map(([n,title,description]) => `<div class="settlement-import-step ${n === state.step ? "active" : n < state.step ? "done" : ""}" ${n > 3 ? 'aria-disabled="true"' : ""}><span>${n}</span><strong>${title}</strong><small>${description}</small></div>`).join("")}</div>
      <section class="settlement-import-panel invoice-raw-panel"><div class="settlement-import-copy"><p class="eyebrow">${state.step}. lépés · Phase 2</p>
        <h3>${state.step === 1 ? "Válaszd ki az elszámolási hónapot" : "Excel fájlok feltöltése"}</h3>
        <p class="muted">${state.step === 1 ? "Ehhez a hónaphoz gyűjtjük a feltöltött Excel-fájlokat." : "Több Excel is kiválasztható. Minden fájlt az összes munkalapjával, külön RAW feltöltésként mentünk el. Számítás nem indul."}</p></div>
        ${state.step === 1 ? `<label>Elszámolási hónap<input id="invoice-raw-month" type="month" value="${esc(state.month)}" /></label><div class="settlement-import-actions"><button class="primary" type="button" data-invoice-raw-action="next">Tovább</button></div>` : `
          <label>Excel fájlok<input id="invoice-raw-files" type="file" multiple accept=".xlsx,.xlsm,.xls" ${state.uploading || state.busy ? "disabled" : ""} /></label>
          <small class="muted">Legfeljebb 10 MB fájlonként. A feltöltött fájlok nem írják felül egymást.</small>
          ${state.queue.length ? `<div class="invoice-raw-queue" aria-live="polite">${state.queue.map(item => `<div><strong>${esc(item.file.name)}</strong><span>${item.status === "uploading" ? "Mentés folyamatban…" : item.status === "error" ? "Nem igazolt mentés" : "Feltöltésre vár"}</span>${item.error ? `<p class="notice error">${esc(item.error)}</p>` : ""}</div>`).join("")}</div>` : ""}
          <div class="settlement-import-actions"><button class="secondary" type="button" data-invoice-raw-action="back" ${state.uploading || state.busy ? "disabled" : ""}>Vissza</button><button class="primary" type="button" data-invoice-raw-action="upload" ${state.uploading || !state.queue.length ? "disabled" : ""}>${state.uploading ? "RAW mentés folyamatban…" : state.queue.some(item => item.status === "error") ? "Feltöltés / újrapróbálás" : "Excel fájlok feltöltése"}</button></div>
          ${state.message ? `<div class="notice ${state.queue.some(item => item.status === "error") ? "error" : ""}" role="status">${esc(state.message)}</div>` : ""}
          ${renderList()}
        `}
      </section>`;
  }

  async function loadList(append=false) {
    const month=state.month, seq=++state.seq, offset=append?state.items.length:0;
    state.loading=true;state.listError="";render();
    try {
      const [data, work]=await Promise.all([
        env.api(`/api/admin/pwa-invoice/raw?month=${encodeURIComponent(month)}&offset=${offset}&limit=50`,{silentLoading:true}),
        env.api(`/api/admin/pwa-invoice/working?month=${encodeURIComponent(month)}`,{silentLoading:true})]);
      if(seq!==state.seq || month!==state.month)return;
      const rows=data.items || [];
      state.items=append ? [...state.items,...rows.filter(row=>!state.items.some(existing=>existing.id===row.id))] : rows;
      state.working=work.working || null;
      state.selected=new Set([...state.selected].filter(id=>state.items.some(item=>item.id===id)));
      if(!state.selected.has(state.primary))state.primary=[...state.selected][0] || "";
      state.hasMore=Boolean(data.hasMore);state.loadedMonth=month;
    } catch(error) {
      if(seq!==state.seq || month!==state.month)return;
      state.listError=error.message || "A hónap feltöltései nem olvashatók.";
    } finally {
      if(seq===state.seq && month===state.month){state.loading=false;render();}
    }
  }

  async function upload() {
    if(state.uploading || !state.queue.length)return;
    const month=state.month;
    state.uploading=true;state.message="";let saved=0,failed=0;
    for(const item of state.queue) {
      if(item.status === "saved")continue;
      item.status="uploading";item.error="";render();
      const form=new FormData();form.set("month",month);form.set("request_id",item.id);form.set("excel_file",item.file);
      try {
        const result=await env.api("/api/admin/pwa-invoice/raw/excel",{method:"POST",body:form,loadingMessage:`RAW mentés: ${item.file.name}`});
        const row=result.upload;
        if(!result.ok || !row || row.id!==item.id || row.status!=="saved")throw Error("A fájl mentése nem igazolható. Próbáld ugyanazt a feltöltést újra.");
        item.status="saved";saved++;
        state.items=[row,...state.items.filter(existing=>existing.id!==row.id)];
      } catch(error) {
        item.status="error";item.error=error.message || "A mentés nem sikerült.";failed++;
      }
      render();
    }
    state.queue=state.queue.filter(item=>item.status!=="saved");
    state.uploading=false;state.message=`RAW mentve: ${saved} fájl.${failed ? ` Nem igazolt mentés: ${failed} fájl. A hibás fájlok külön újrapróbálhatók.` : " Az Excel-fájlok a kiválasztott hónap listájában láthatók."}`;
    render();await loadList(); // Stay on step 2, ready for additional workbooks.
  }

  const selectedItems = () => state.items.filter(item=>state.selected.has(item.id));
  function toggleSelection(id, selected) {
    if(state.busy || state.uploading)return false;
    if(selected && !state.selected.has(id) && state.selected.size>=10){state.message="Legfeljebb 10 fájl hasonlítható össze egyszerre.";render();return false;}
    if(selected)state.selected.add(id);else state.selected.delete(id);
    if(!state.selected.has(state.primary))state.primary=[...state.selected][0] || "";
    state.pendingWork=null;state.message="";render();return true;
  }
  function parseColumn(text) {
    if(!/^[A-Za-z]{1,3}$/.test(text))throw Error("A kulcsoszlop formátuma például A vagy A,C legyen.");
    const number=[...text.toUpperCase()].reduce((sum,char)=>sum*26+char.charCodeAt(0)-64,0);
    if(number>16384)throw Error("A kulcsoszlop legfeljebb XFD lehet.");
    return number;
  }
  function col(number) {let text="";while(number){number--;text=String.fromCharCode(65+number%26)+text;number=Math.floor(number/26);}return text;}
  function value(cell) {
    if(!cell)return "∅ (nincs cella)";
    const text=typeof cell.value==="object" ? JSON.stringify(cell.value) : String(cell.value ?? "");
    return `${text}${cell.type==="f" ? ` [mentett érték: ${cell.cachedValue ?? "nincs"}]` : ""} · ${cell.type || "érték"}`;
  }
  async function confirmAction(title, text) {
    const dialog=document.createElement("dialog");dialog.className="invoice-confirm-dialog";
    dialog.innerHTML=`<h3></h3><p></p><div class="settlement-import-actions"><button type="button" class="secondary" data-cancel>Megszakítás</button><button type="button" class="primary" data-confirm>Tovább</button></div>`;
    dialog.querySelector("h3").textContent=title;dialog.querySelector("p").textContent=text;
    document.body.append(dialog);
    return new Promise(resolve=>{
      let accepted=false;
      dialog.querySelector("[data-cancel]").onclick=()=>dialog.close();
      dialog.querySelector("[data-confirm]").onclick=()=>{accepted=true;dialog.close();};
      dialog.addEventListener("close",()=>{dialog.remove();resolve(accepted);},{once:true});
      dialog.showModal();
    });
  }
  const post = (url, data) => env.api(url,{method:"POST",body:JSON.stringify(data),loadingMessage:"Excel-adatok feldolgozása…"});
  async function loadComparison(detailsOnly=false) {
    if(state.busy || state.selected.size<2)return;
    state.busy=true;state.message="";render();
    try{
      const request={month:state.month,selected_ids:[...state.selected],primary_id:state.primary,key_columns:state.keys};
      if(!detailsOnly)state.diff=await post("/api/admin/pwa-invoice/raw/compare",request);
      if(state.detail){
        const result=await post("/api/admin/pwa-invoice/raw/compare",{...request,detail_upload_id:state.detail.id,detail_sheet:state.detail.sheet,offset:state.detail.offset,limit:50});
        state.detail.data=result.comparisons.find(item=>item.uploadId===state.detail.id)?.sheets.find(item=>item.name===state.detail.sheet);
      }
    }catch(error){state.message=error.message;state.diff=null;if(state.detail)state.detail.data=null;}
    finally{state.busy=false;render();}
  }
  function renderComparison() {
    const disabled=state.busy ? "disabled" : "";
    const sheet=state.detail?.data;
    env.target.innerHTML=`<section class="settlement-import-panel invoice-raw-panel"><p class="eyebrow">2a. lépés · Összehasonlítás</p><h3>Excel-fájlok eltérései</h3>
      <p class="muted">Válassz egy elsődleges forrást. Minden eltérés ehhez képest látszik. Az előszobába csak az elsődleges fájl teljes tartalma kerül.</p>
      <div class="invoice-source-grid">${selectedItems().map(item=>`<button type="button" class="secondary invoice-source ${state.primary===item.id ? "invoice-primary" : ""}" data-invoice-primary="${esc(item.id)}" ${disabled}><strong>${esc(item.source_file_name)}</strong><small>${esc(item.session_id)}</small><span>${state.primary===item.id ? "✓ Elsődleges forrás" : "Legyen elsődleges"}</span></button>`).join("")}</div>
      ${state.message ? `<p class="notice error" role="alert">${esc(state.message)}</p><button type="button" class="secondary" data-invoice-raw-action="compare-retry" ${disabled}>Összehasonlítás újrapróbálása</button>` : ""}
      ${state.busy ? `<p role="status">Összehasonlítás betöltése…</p>` : ""}
      ${(state.diff?.comparisons || []).map(comparison=>`<section class="invoice-diff-file"><h4>${esc(comparison.fileName)} – eltérések az elsődlegeshez képest</h4>
        <div class="invoice-raw-table-wrap"><table class="invoice-diff-table"><thead><tr><th>Munkalap</th><th>Állapot</th><th>Egyező</th><th>Módosult</th><th>Hiányzó</th><th>Új</th><th>Áthelyezett</th><th></th></tr></thead><tbody>
          ${comparison.sheets.map(item=>`<tr><td>${esc(item.name)}</td><td>${({added:"Új munkalap",removed:"Hiányzó munkalap",changed:"Eltérő",identical:"Egyező"})[item.status]}</td><td>${count(item.identicalRows)}</td><td>${count(item.changedRows)}</td><td>${count(item.removedRows)}</td><td>${count(item.addedRows)}</td><td>${count(item.movedRows)}</td><td><button type="button" class="secondary" data-invoice-detail="${esc(comparison.uploadId)}" data-sheet="${esc(item.name)}" ${disabled}>Részletek</button></td></tr>`).join("")}
        </tbody></table></div></section>`).join("")}
      ${state.detail ? `<section class="invoice-diff-details"><h4>${esc(state.detail.sheet)} · Sor- és cellaeltérések</h4>
        <label>Egyedi kulcsoszlopok (például A vagy A,C)<input data-invoice-key-columns value="${esc((state.keys[state.detail.sheet] || []).map(col).join(","))}" ${disabled} /></label><button type="button" class="secondary" data-invoice-raw-action="apply-keys" ${disabled}>Párosítás frissítése</button>
        ${sheet?.warning ? `<p class="notice error">${esc(sheet.warning)}</p>` : ""}
        ${sheet && !sheet.total ? `<p class="notice">Nincs eltérő cellatartalom.${sheet.movedRows ? ` ${count(sheet.movedRows)} sor máshová került.` : ""} Munkalap pozíciója: ${esc(sheet.beforeIndex ?? "–")} → ${esc(sheet.afterIndex ?? "–")}</p>` : ""}
        ${sheet ? `<p class="muted">${sheet.total ? `${state.detail.offset+1}–${state.detail.offset+sheet.changes.length} / ${sheet.total} eltérő sor` : "0 eltérő sor"}</p>
          ${sheet.changes.map(row=>`<article class="invoice-diff-row ${row.kind}"><strong>${({changed:"Módosult sor",removed:"Hiányzó sor",added:"Új sor"})[row.kind]} · Elsődleges: ${esc(row.beforeRow ?? "–")}. sor → Másik fájl: ${esc(row.afterRow ?? "–")}. sor</strong>${row.match==="suggested" ? `<p class="notice error">Javasolt párosítás – ellenőrizendő</p>` : ""}
            <div class="invoice-raw-table-wrap"><table class="invoice-cell-diff"><thead><tr><th>Oszlop</th><th>Elsődleges érték</th><th>Másik fájl értéke</th><th>Számérték eltérése</th></tr></thead><tbody>${row.cells.map(cell=>`<tr><td>${esc(cell.columnName)}</td><td class="invoice-before">${esc(value(cell.before))}</td><td class="invoice-after">${esc(value(cell.after))}</td><td>${esc(cell.delta ?? "–")}</td></tr>`).join("")}</tbody></table></div></article>`).join("")}
          <div class="settlement-import-actions">${state.detail.offset ? `<button type="button" class="secondary" data-invoice-raw-action="compare-first" ${disabled}>Első oldal</button>` : ""}${sheet.hasMore ? `<button type="button" class="secondary" data-invoice-raw-action="compare-more" ${disabled}>Következő 50 eltérés</button>` : ""}</div>` : ""}
      </section>` : ""}
      <div class="settlement-import-actions"><button type="button" class="secondary" data-invoice-raw-action="compare-back" ${disabled}>Vissza a fájlokhoz</button><button type="button" class="primary" data-invoice-raw-action="prepare" ${state.busy || !state.diff ? "disabled" : ""}>Tovább – elsődleges fájl az előszobába</button></div>
    </section>`;
  }
  async function prepareWorking() {
    if(state.busy || !state.primary)return;
    state.busy=true;state.message="";render();
    try{
      const result=await env.api(`/api/admin/pwa-invoice/working?month=${encodeURIComponent(state.month)}`,{silentLoading:true});
      const current=result.working;
      if(current?.source_upload_id===state.primary){state.working=current;state.step=3;return;}
      if(current && !await confirmAction("Előszobai munkapéldány cseréje",`Ehhez a hónaphoz már tartozik előszobai munkapéldány: ${current.source_file_name}. Lecseréled a kiválasztott Excel teljes tartalmára? Az eredeti RAW feltöltések megmaradnak.`))return;
      if(!state.pendingWork || state.pendingWork.source_id!==state.primary || state.pendingWork.expected_id!==(current?.id || null)){
        state.pendingWork={month:state.month,source_id:state.primary,request_id:crypto.randomUUID(),expected_id:current?.id || null};
      }
      const saved=await post("/api/admin/pwa-invoice/working",state.pendingWork);
      if(!saved.ok || !saved.working?.id || saved.working.source_upload_id!==state.primary)throw Error("Az előszobai másolat mentése nem igazolható.");
      state.working=saved.working;state.step=3;state.pendingWork=null;
    }catch(error){state.message=error.message;}
    finally{state.busy=false;render();if(state.step===3 && state.working)loadWorking(state.working.id);}
  }
  async function deleteSelected() {
    if(state.busy || !state.selected.size)return;
    state.busy=true;state.message="";render();
    try{
      const names=selectedItems().map(item=>item.source_file_name).join("\n");
      if(!await confirmAction("Kijelölt feltöltések törlése",`${names}\n\nA fájlokat eltávolítjuk a feltöltési listából. Az archivált eredeti és RAW adatok megmaradnak. Az aktív előszoba forrása nem törölhető.`))return;
      const result=await post("/api/admin/pwa-invoice/raw/delete",{month:state.month,selected_ids:[...state.selected]});
      if(!result.ok)throw Error("A törlés nem igazolható.");
      state.message=`${result.deletedCount} feltöltés törölve a listából.`;state.selected.clear();state.primary="";
    }catch(error){state.message=error.message;}
    finally{state.busy=false;render();await loadList();}
  }
  async function loadWorking(id, sheet, offset=0) {
    if(state.busy)return;
    state.busy=true;state.message="";state.step=3;render();
    try{
      const url=`/api/admin/pwa-invoice/working?month=${encodeURIComponent(state.month)}&working_id=${encodeURIComponent(id)}`;
      let result=await env.api(url+(sheet!==undefined ? `&sheet=${encodeURIComponent(sheet)}&offset=${offset}` : ""),{silentLoading:true});
      if(!result.working || result.working.id!==id)throw Error("A munkamenet nem igazolható.");
      if(sheet===undefined && result.working.sheets?.length){sheet=result.working.sheets[0].name;result=await env.api(url+`&sheet=${encodeURIComponent(sheet)}`,{silentLoading:true});}
      if(!result.working || result.working.id!==id)throw Error("A munkamenet nem igazolható.");
      state.working=result.working;state.previewOffset=offset;
    }catch(error){state.message=error.message;state.working=null;}
    finally{state.busy=false;render();}
  }
  function renderWorking() {
    const work=state.working;
    env.target.innerHTML=`<section class="settlement-import-panel invoice-raw-panel"><p class="eyebrow">3. lépés · Előszoba</p><h3>A hónap aktív munkapéldánya</h3>
      <p class="muted">Havonta egy teljes Excel-munkafüzet lehet aktív. Itt kizárólag az elkülönített másolatot olvassuk. Számítás és éles elszámolás nem indul.</p>
      ${state.message ? `<p class="notice error" role="alert">${esc(state.message)}</p>` : ""}${state.busy ? `<p role="status">Munkapéldány betöltése…</p>` : ""}
      ${work ? `<div class="invoice-work-info"><strong>${esc(work.source_file_name)}</strong><p>Munkamenet: ${esc(work.session_id)}</p><p>Eredeti RAW session: ${esc(work.source_session_id)}</p><p>${count(work.sheet_count)} munkalap · ${count(work.raw_row_count)} RAW sor · ${esc(when(work.created_at))}</p></div>
        <div class="invoice-source-grid">${(work.sheets || []).map(sheet=>`<button type="button" class="secondary invoice-source ${work.preview?.sheet===sheet.name ? "invoice-primary" : ""}" data-invoice-preview="${esc(sheet.name)}" ${state.busy ? "disabled" : ""}><strong>${esc(sheet.name)}</strong></button>`).join("")}</div>
        ${work.preview ? `<h4>${esc(work.preview.sheet)} – nyers előnézet</h4><p class="muted">${(state.previewOffset || 0)+1}. sortól, legfeljebb 30 tárolt sor. A képleteket nem számoljuk újra.</p>
          ${work.preview.rows.map(row=>`<article class="invoice-preview-row"><strong>Excel ${esc(row.sourceRowNo)}. sor</strong><dl>${row.cells.map(cell=>`<div><dt>${esc(col(cell.column))}</dt><dd>${esc(value(cell))}</dd></div>`).join("")}</dl></article>`).join("")}
          ${!work.preview.rows.length ? `<div class="empty-card">Üres munkalap.</div>` : ""}${work.preview.hasMore ? `<button class="secondary" type="button" data-invoice-raw-action="preview-more" ${state.busy ? "disabled" : ""}>Következő 30 sor</button>` : ""}` : ""}` : ""}
      <div class="settlement-import-actions"><button type="button" class="secondary" data-invoice-raw-action="work-back" ${state.busy ? "disabled" : ""}>Vissza a feltöltésekhez</button></div>
    </section>`;
  }

  function bind(target) {
    target.addEventListener("change",event=>{
      if(event.target.dataset.invoiceCheck){toggleSelection(event.target.dataset.invoiceCheck,event.target.checked);return;}
      if(event.target.id!=="invoice-raw-files" || state.uploading || state.busy)return;
      for(const file of event.target.files || [])state.queue.push({id:crypto.randomUUID(),file,status:"pending",error:""});
      state.message="";render();
    });
    target.addEventListener("click",event=>{
      if(state.busy || state.uploading)return;
      const primary=event.target.closest("[data-invoice-primary]");
      if(primary){if(!toggleSelection(primary.dataset.invoicePrimary,true))return;state.primary=primary.dataset.invoicePrimary;state.pendingWork=null;state.detail=null;if(state.step==="2a")loadComparison();else render();return;}
      const detail=event.target.closest("[data-invoice-detail]");
      if(detail){state.detail={id:detail.dataset.invoiceDetail,sheet:detail.dataset.sheet,offset:0};loadComparison(true);return;}
      const preview=event.target.closest("[data-invoice-preview]");
      if(preview){loadWorking(state.working.id,preview.dataset.invoicePreview);return;}
      const button=event.target.closest("[data-invoice-raw-action]");
      if(!button){const row=event.target.closest("[data-invoice-row]");if(row && !event.target.closest("input,button,a"))toggleSelection(row.dataset.invoiceRow,!state.selected.has(row.dataset.invoiceRow));return;}
      const action=button.dataset.invoiceRawAction;
      if(action==="proceed"){if(state.selected.size>1){state.step="2a";state.detail=null;loadComparison();}else prepareWorking();return;}
      if(action==="compare-retry"){loadComparison();return;}
      if(action==="compare-back"){state.step=2;state.detail=null;render();return;}
      if(action==="work-back"){state.step=2;render();loadList();return;}
      if(action==="prepare"){prepareWorking();return;}
      if(action==="delete"){deleteSelected();return;}
      if(action==="resume"){if(state.working)loadWorking(state.working.id);return;}
      if(action==="compare-more"){state.detail.offset+=50;loadComparison(true);return;}
      if(action==="compare-first"){state.detail.offset=0;loadComparison(true);return;}
      if(action==="preview-more"){loadWorking(state.working.id,state.working.preview.sheet,(state.previewOffset || 0)+30);return;}
      if(action==="apply-keys"){
        try { const values=target.querySelector("[data-invoice-key-columns]").value.trim();
          state.keys[state.detail.sheet]=values ? values.split(",").map(value=>parseColumn(value.trim())) : [];
          state.detail.offset=0;loadComparison();
        }catch(error){state.message=error.message;render();}return;
      }
      if(action==="next"){
        const month=target.querySelector("#invoice-raw-month")?.value;
        if(!/^\d{4}-(0[1-9]|1[0-2])$/.test(month || ""))return;
        if(month!==state.month){state.month=month;state.items=[];state.queue=[];state.hasMore=false;state.message="";state.loadedMonth="";state.seq++;state.selected.clear();state.primary="";state.diff=null;state.working=null;state.keys={};state.pendingWork=null;}
        state.step=2;render();loadList();
      }else if(action==="back" && !state.uploading){state.step=1;render();}
      else if(action==="reload" && !state.loading)loadList();
      else if(action==="more" && !state.loading)loadList(true);
      else if(action==="upload")upload();
    });
  }

  window.JittInvoiceRaw={
    mount(options){
      env=options;
      if(!state.month)state.month=options.initialMonth;
      if(mountedTarget!==options.target){mountedTarget=options.target;bind(mountedTarget);}
    },
    show(){render();if(state.step===3 && state.working && !state.busy)loadWorking(state.working.id);if(state.step===2 && state.loadedMonth!==state.month && !state.loading)loadList();},
  };
})();
