/* Admin complaint workspace. All source text is escaped before rendering. */
function qualityWorkspaceText(value) {
  return String(value || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();
}
function qualityWorkspaceDays(courier) {
  const type = state.qualityWorkspaceType || 'all';
  return (courier.days || []).map(day => ({...day, items: day.items.filter(item => type === 'all' || item.category === type)})).filter(day => day.items.length);
}
function renderQualityRoster() {
  const target = document.querySelector('#quality-workspace-roster');
  if (!target) return;
  const query = qualityWorkspaceText(state.qualityWorkspaceQuery);
  const rows = (state.qualityWorkspace?.couriers || []).filter(row =>
    qualityWorkspaceText(`${row.courierName} ${row.courierId}`).includes(query) &&
    ((state.qualityWorkspaceType || 'all') === 'all' || qualityWorkspaceDays(row).length));
  target.innerHTML = `<div class="settlement-dashboard-toolbar"><strong>Futárok</strong><span>${rows.length} futár</span></div>
    <div class="settlement-dashboard-table">${rows.map(row => `<div class="settlement-dashboard-row"><button class="settlement-dashboard-row-main" type="button" data-quality-courier="${escapeHtml(row.courierId)}">
      <div><strong>${escapeHtml(row.courierName)}</strong><small>#${escapeHtml(row.courierId)} · ${escapeHtml(row.warehouse || '')}</small></div>
      <span>${qualityWorkspaceDays(row).length} érintett nap</span><strong>Reklamációk megnyitása</strong></button></div>`).join('') || '<div class="empty-card">Nincs találat.</div>'}</div>`;
  target.querySelectorAll('[data-quality-courier]').forEach(button => button.onclick = () => {
    state.qualityWorkspaceCourier = button.dataset.qualityCourier;
    state.qualityWorkspaceDay = ''; state.qualityComplaintFocus = ''; state.qualityComplaintOffset = 0;
    loadQualityComplaints();
  });
}
async function prepareQualityWorkspace() {
  const root = document.querySelector('#quality-workspace');
  if (!root) return true;
  if (state.qualityComplaintFocus && state.qualityWorkspaceFocus !== state.qualityComplaintFocus) {
    try {
      const focused = await api(`/api/quality/complaints?complaint=${encodeURIComponent(state.qualityComplaintFocus)}`);
      const item = focused.items?.[0], day = item?.affected_items?.[0]?.date;
      if (item && day) {
        state.qualityWorkspaceCourier = String(item.courier_id);
        state.qualityWorkspaceDay = day; state.qualityWorkspaceMonth = day.slice(0, 7);
        state.qualityWorkspaceFocus = state.qualityComplaintFocus;
      }
    } catch(error) { root.textContent = error.message; return false; }
  }
  const month = state.qualityWorkspaceMonth || state.workflowMonth || state.statisticsMonth || new Date().toISOString().slice(0, 7);
  const request = (state.qualityWorkspaceRequest || 0) + 1;
  state.qualityWorkspaceRequest = request;
  try {
    if (!state.qualityWorkspace || state.qualityWorkspace.month !== month) {
      root.textContent = 'Futárok és havi reklamációk betöltése…';
      const payload = await api(`/api/quality/workspace?month=${encodeURIComponent(month)}`);
      if (request !== state.qualityWorkspaceRequest) return false;
      state.qualityWorkspace = payload;
    }
    const payload = state.qualityWorkspace;
    const courier = payload.couriers.find(row => row.courierId === state.qualityWorkspaceCourier);
    const categories = payload.categories || {};
    root.innerHTML = `<div class="settlement-dashboard-filter-grid">
      <label>Hónap<input id="quality-workspace-month" type="month" value="${escapeHtml(month)}"></label>
      <label>Reklamáció típusa<select id="quality-workspace-type"><option value="all">Összes reklamáció</option>${Object.entries(categories).map(([key,label]) => `<option value="${escapeHtml(key)}" ${state.qualityWorkspaceType === key ? 'selected' : ''}>${escapeHtml(label)}</option>`).join('')}</select></label></div>
      ${(payload.warnings || []).map(text => `<p class="notice error">${escapeHtml(text)}</p>`).join('')}
      ${courier ? `<article class="shift-card"><div class="shift-top"><div><h3>${escapeHtml(courier.courierName)}</h3><p>#${escapeHtml(courier.courierId)} · ${escapeHtml(month)}</p></div><button type="button" class="secondary" id="quality-workspace-back">Vissza a futárlistához</button></div>
        <div class="workflow-tabs">${Object.entries(categories).map(([key,label]) => `<button type="button" class="secondary" data-quality-type="${escapeHtml(key)}">${escapeHtml(label)}</button>`).join('')}</div>
        <div class="shift-list">${qualityWorkspaceDays(courier).map(day => `<button type="button" class="financial-card" data-quality-day="${escapeHtml(day.date)}"><strong>${escapeHtml(day.date)}</strong><span>${escapeHtml([...new Set(day.items.map(item => categories[item.category] || 'Egyéb'))].join(' · '))}</span><small>${day.items.length} ügy vagy jelzés</small></button>`).join('') || '<p class="empty-card">Ebben a hónapban és kategóriában nincs rögzített ügy.</p>'}</div>
        <div id="quality-workspace-day"></div></article>` : `<div class="settlement-quick-search"><label>Gyorskeresés az összes futár között<input id="quality-workspace-search" type="search" value="${escapeHtml(state.qualityWorkspaceQuery || '')}" placeholder="Név vagy futár ID részlete…" autocomplete="off"></label><p>Részleges név- és ID-keresés, ékezet nélkül is.</p></div><div id="quality-workspace-roster"></div>`}`;
    document.querySelector('#quality-workspace-month').onchange = event => {
      state.qualityWorkspaceMonth = event.target.value; state.qualityWorkspace = null;
      state.qualityWorkspaceDay = ''; state.qualityComplaintFocus = ''; loadQualityComplaints();
    };
    document.querySelector('#quality-workspace-type').onchange = event => {
      state.qualityWorkspaceType = event.target.value; state.qualityWorkspaceDay = ''; state.qualityComplaintFocus = ''; loadQualityComplaints();
    };
    document.querySelector('#quality-workspace-search')?.addEventListener('input', event => {
      state.qualityWorkspaceQuery = event.target.value; renderQualityRoster();
    });
    document.querySelector('#quality-workspace-back')?.addEventListener('click', () => {
      state.qualityWorkspaceCourier = ''; state.qualityWorkspaceDay = ''; state.qualityComplaintFocus = ''; loadQualityComplaints();
    });
    root.querySelectorAll('[data-quality-type]').forEach(button => button.onclick = () => {
      state.qualityWorkspaceType = button.dataset.qualityType; state.qualityWorkspaceDay = ''; loadQualityComplaints();
    });
    root.querySelectorAll('[data-quality-day]').forEach(button => button.onclick = () => {
      state.qualityWorkspaceDay = button.dataset.qualityDay; state.qualityComplaintFocus = ''; state.qualityComplaintOffset = 0; loadQualityComplaints();
    });
    document.querySelector('#admin-route-signals')?.closest('section')?.classList.add('hidden');
    const selected = Boolean(courier && state.qualityWorkspaceDay);
    document.querySelector('#quality-complaints-list')?.classList.toggle('hidden', !selected);
    document.querySelector('#quality-complaints-prev')?.parentElement.classList.toggle('hidden', !selected);
    if (!courier) renderQualityRoster();
    if (!selected) { document.querySelector('#quality-complaints-status').textContent = 'Válassz futárt, majd dátumot az ügyekhez és a teljes napi bizonyítékokhoz.'; return false; }
    const day = qualityWorkspaceDays(courier).find(item => item.date === state.qualityWorkspaceDay);
    const detail = document.querySelector('#quality-workspace-day');
    const sourceLabels = {complaint:'Futár reklamáció', route:'Menet közbeni jelzés', shift:'Műszakjelzés', google:'Google-űrlapos ügy'};
    detail.innerHTML = `<h3>${escapeHtml(state.qualityWorkspaceDay)} · Napi ügyek és adatok</h3>${(day?.items || []).map(item => `<div class="shift-card"><strong>${escapeHtml(sourceLabels[item.source] || item.source)} · ${escapeHtml(categories[item.category] || '')}</strong><p>${escapeHtml(item.message)}</p><small>${item.routeId ? `Route ${escapeHtml(item.routeId)} · ` : ''}${escapeHtml(item.status || '')}${item.source === 'google' ? ' · A beküldés nem jelent Kifli-elfogadást.' : ''}</small>${['route','shift'].includes(item.source) ? `<button type="button" class="secondary" data-quality-convert="${escapeHtml(item.id)}" data-kind="${escapeHtml(item.source)}">Reklamáció készítése a jelzésből</button>` : ''}</div>`).join('')}<div id="quality-workspace-evidence" role="status">Teljes napi adatok betöltése…</div>`;
    detail.querySelectorAll('[data-quality-convert]').forEach(button => button.onclick = async () => {
      button.disabled = true;
      try {
        await api(`/api/quality/route-signals/${button.dataset.kind}/${encodeURIComponent(button.dataset.qualityConvert)}/complaint`, {method:'POST', body:'{}'});
        state.qualityWorkspace = null; await loadQualityComplaints();
      } catch(error) { button.disabled = false; document.querySelector('#quality-complaints-status').textContent = error.message; }
    });
    const cid = courier.courierId, date = state.qualityWorkspaceDay;
    api(`/api/quality/workspace/day?courier=${encodeURIComponent(cid)}&work_date=${encodeURIComponent(date)}`, {silentLoading:true}).then(evidence => {
      if (state.qualityWorkspaceRequest !== request) return;
      document.querySelector('#quality-workspace-evidence').innerHTML = `<p class="muted">Mentett adatbázisadatok, budapesti idő szerint.</p>${(evidence.warnings || []).map(text => `<p class="notice error">${escapeHtml(text)}</p>`).join('')}${(evidence.sections || []).map(section => `<section class="complaint-shift-details"><h4>${escapeHtml(section.title)}</h4>${(section.rows || []).map(row => `<div class="stat-row"><span>${escapeHtml(row.label)}</span><strong>${escapeHtml(row.value)}</strong></div>`).join('')}<small>Forrás: ${escapeHtml(section.source)} · ${escapeHtml(shortDateTime(section.updatedAt))}</small></section>`).join('')}`;
    }).catch(error => { if (state.qualityWorkspaceRequest === request) document.querySelector('#quality-workspace-evidence').textContent = error.message; });
    return true;
  } catch(error) { if (state.qualityWorkspaceRequest === request) root.textContent = error.message; return false; }
}
document.addEventListener('DOMContentLoaded', () => {
  document.querySelector('#quality-complaints-refresh')?.addEventListener('click', () => { state.qualityWorkspace = null; }, true);
});
