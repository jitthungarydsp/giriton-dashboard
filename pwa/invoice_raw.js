/* Phase 1 only. Independent from the existing settlement import/calculation APIs. */
(() => {
  let env, mountedTarget;
  const state = {step:1,month:"",items:[],queue:[],loading:false,uploading:false,loadedMonth:"",hasMore:false,seq:0,listError:"",message:""};
  const esc = value => env.escapeHtml(String(value ?? ""));
  const count = value => env.formatCount(value || 0);
  const when = value => value ? new Date(value).toLocaleString("hu-HU") : "–";

  function renderList() {
    return `<section class="invoice-raw-saved"><div class="device-history-head"><strong>A hónap feltöltött Exceljei</strong><span>${esc(env.formatMonthLabel(state.month))}</span></div>
      <button class="secondary" type="button" data-invoice-raw-action="reload" ${state.loading ? "disabled" : ""}>${state.loading ? "Lista betöltése…" : "Lista frissítése"}</button>
      ${state.listError ? `<p class="notice error" role="alert">${esc(state.listError)}</p>` : ""}
      ${state.items.length ? `<div class="invoice-raw-table-wrap"><table class="invoice-raw-table"><thead><tr><th>Fájlnév</th><th>Sessionazonosító</th><th>Feltöltés ideje</th><th>Munkalapok</th><th>RAW sorok</th><th>Mentés állapota</th></tr></thead><tbody>
        ${state.items.map(item => `<tr><td data-label="Fájlnév">${esc(item.source_file_name)}</td><td data-label="Sessionazonosító">${esc(item.session_id)}</td><td data-label="Feltöltés ideje">${esc(when(item.created_at))}</td><td data-label="Munkalapok">${esc(count(item.sheet_count))}</td><td data-label="RAW sorok">${esc(count(item.raw_row_count))}</td><td data-label="Mentés állapota"><span class="invoice-raw-status">RAW mentve</span></td></tr>`).join("")}
      </tbody></table></div>` : !state.loading && !state.listError ? `<div class="empty-card">Ehhez a hónaphoz még nincs elmentett Excel.</div>` : ""}
      ${state.hasMore ? `<button class="secondary" type="button" data-invoice-raw-action="more" ${state.loading ? "disabled" : ""}>További feltöltések</button>` : ""}
    </section>`;
  }

  function render() {
    if (!env?.target) return;
    const steps = [[1,"Hónap","Elszámolási hónap kiválasztása"],[2,"Excel","Feltöltés és RAW mentés"],[3,"Konfigurátor","Későbbi lépés"],[4,"Validálás","Későbbi lépés"]];
    env.target.innerHTML = `<div class="settlement-import-stepper">${steps.map(([n,title,description]) => `<div class="settlement-import-step ${n === state.step ? "active" : n < state.step ? "done" : ""}" ${n > 2 ? 'aria-disabled="true"' : ""}><span>${n}</span><strong>${title}</strong><small>${description}</small></div>`).join("")}</div>
      <section class="settlement-import-panel invoice-raw-panel"><div class="settlement-import-copy"><p class="eyebrow">${state.step}. lépés · Phase 1</p>
        <h3>${state.step === 1 ? "Válaszd ki az elszámolási hónapot" : "Excel fájlok feltöltése"}</h3>
        <p class="muted">${state.step === 1 ? "Ehhez a hónaphoz gyűjtjük a feltöltött Excel-fájlokat." : "Több Excel is kiválasztható. Minden fájlt az összes munkalapjával, külön RAW feltöltésként mentünk el. Számítás nem indul."}</p></div>
        ${state.step === 1 ? `<label>Elszámolási hónap<input id="invoice-raw-month" type="month" value="${esc(state.month)}" /></label><div class="settlement-import-actions"><button class="primary" type="button" data-invoice-raw-action="next">Tovább</button></div>` : `
          <label>Excel fájlok<input id="invoice-raw-files" type="file" multiple accept=".xlsx,.xlsm,.xls" ${state.uploading ? "disabled" : ""} /></label>
          <small class="muted">Legfeljebb 10 MB fájlonként. A feltöltött fájlok nem írják felül egymást.</small>
          ${state.queue.length ? `<div class="invoice-raw-queue" aria-live="polite">${state.queue.map(item => `<div><strong>${esc(item.file.name)}</strong><span>${item.status === "uploading" ? "Mentés folyamatban…" : item.status === "error" ? "Nem igazolt mentés" : "Feltöltésre vár"}</span>${item.error ? `<p class="notice error">${esc(item.error)}</p>` : ""}</div>`).join("")}</div>` : ""}
          <div class="settlement-import-actions"><button class="secondary" type="button" data-invoice-raw-action="back" ${state.uploading ? "disabled" : ""}>Vissza</button><button class="primary" type="button" data-invoice-raw-action="upload" ${state.uploading || !state.queue.length ? "disabled" : ""}>${state.uploading ? "RAW mentés folyamatban…" : state.queue.some(item => item.status === "error") ? "Feltöltés / újrapróbálás" : "Excel fájlok feltöltése"}</button></div>
          ${state.message ? `<div class="notice ${state.queue.some(item => item.status === "error") ? "error" : ""}" role="status">${esc(state.message)}</div>` : ""}
          ${renderList()}
        `}
      </section>`;
  }

  async function loadList(append=false) {
    const month=state.month, seq=++state.seq, offset=append?state.items.length:0;
    state.loading=true;state.listError="";render();
    try {
      const data=await env.api(`/api/admin/pwa-invoice/raw?month=${encodeURIComponent(month)}&offset=${offset}&limit=50`,{silentLoading:true});
      if(seq!==state.seq || month!==state.month)return;
      const rows=data.items || [];
      state.items=append ? [...state.items,...rows.filter(row=>!state.items.some(existing=>existing.id===row.id))] : rows;
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

  function bind(target) {
    target.addEventListener("change",event=>{
      if(event.target.id!=="invoice-raw-files" || state.uploading)return;
      for(const file of event.target.files || [])state.queue.push({id:crypto.randomUUID(),file,status:"pending",error:""});
      state.message="";render();
    });
    target.addEventListener("click",event=>{
      const button=event.target.closest("[data-invoice-raw-action]");if(!button)return;
      const action=button.dataset.invoiceRawAction;
      if(action==="next"){
        const month=target.querySelector("#invoice-raw-month")?.value;
        if(!/^\d{4}-(0[1-9]|1[0-2])$/.test(month || ""))return;
        if(month!==state.month){state.month=month;state.items=[];state.queue=[];state.hasMore=false;state.message="";state.loadedMonth="";state.seq++;}
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
    show(){render();if(state.step===2 && state.loadedMonth!==state.month && !state.loading)loadList();},
  };
})();
