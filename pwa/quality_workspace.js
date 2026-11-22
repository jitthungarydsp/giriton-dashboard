/* Admin complaint workspace. All source text is escaped before rendering. */
const qualityOutreachTopics = {
  lateShift: "Műszakkésés",
  uncleanedTimeWindowLate: "Nem mentesített címkésés",
  noShow: "No-show",
};

const qualityOutreachStates = {
  not_complained: "Még nincs reklamáció",
  complained: "Reklamáció rögzítve",
  in_progress: "Továbbítás folyamatban",
  forwarded: "Továbbítva",
  closed: "Lezárva",
};

function applyQualityOutreachFilter(value) {
  const filter = document.querySelector("#quality-complaints-filter");
  filter.value = `outreach-${value}`;
  filter.dispatchEvent(new Event("change"));
  filter.focus({ preventScroll: true });
}

function renderQualityOutreachSummary(root, rows) {
  const complained = rows.filter(row => row.complaint_id || row.state === "forwarded").length;
  const pending = rows.length - complained;
  const share = rows.length ? complained / rows.length * 100 : 0;
  const slice = (count, kind, className, length, offset) => count ? `<circle cx="70" cy="70" r="51" pathLength="100"
    class="${className}" stroke-dasharray="${length} ${100 - length}" stroke-dashoffset="${-offset}" data-outreach-filter="${kind}" />` : "";
  root.innerHTML = `<h3>Minőségi jelzések reklamációs aránya</h3>
    <div class="quality-outreach-chart">
      <svg viewBox="0 0 140 140" aria-hidden="true">
        <circle class="quality-outreach-track" cx="70" cy="70" r="51" />
        ${slice(pending, "not-complained", "quality-outreach-pending", 100 - share, share)}
        ${slice(complained, "complained", "quality-outreach-complained", share, 0)}
        <text x="70" y="75">${formatCount(rows.length)}</text>
      </svg>
      <div class="quality-outreach-breakdown">
        <div class="quality-outreach-actions">
          <button type="button" class="secondary" data-outreach-filter="complained">Reklamált · ${formatCount(complained)}</button>
          <button type="button" class="secondary" data-outreach-filter="not-complained">Még nincs reklamáció · ${formatCount(pending)}</button>
        </div>
        <dl>${Object.entries(qualityOutreachTopics).map(([topic, label]) => {
          const items = rows.filter(row => row.topic === topic);
          const filed = items.filter(row => row.complaint_id || row.state === "forwarded").length;
          return `<div><dt>${label}</dt><dd>${formatCount(filed)} / ${formatCount(items.length)} reklamált</dd></div>`;
        }).join("")}</dl>
      </div>
    </div>`;
  root.querySelectorAll("[data-outreach-filter]").forEach(control => {
    control.addEventListener("click", () => applyQualityOutreachFilter(control.dataset.outreachFilter));
  });
}

async function loadQualityOutreach(isCurrent) {
  const root = document.querySelector("#quality-outreach-summary");
  if (!root) return { items: [] };
  root.setAttribute("aria-busy", "true");
  try {
    const result = await api("/api/quality/outreach", { silentLoading: true });
    if (isCurrent()) renderQualityOutreachSummary(root, result.items);
    return result;
  } catch (error) {
    if (isCurrent()) root.textContent = "A minőségi összesítő most nem érhető el.";
    return { error: error.message };
  } finally {
    if (isCurrent()) root.removeAttribute("aria-busy");
  }
}

async function renderQualityOutreachList(pending, filter, target, status, isCurrent) {
  const result = await pending;
  if (!isCurrent()) return;
  if (result.error) {
    status.textContent = result.error;
    return;
  }
  const items = result.items.filter(row => {
    if (filter === "outreach-hub") return row.source === "hub_validated";
    const hasComplaint = Boolean(row.complaint_id) || row.state === "forwarded";
    return filter === "outreach-all" || (filter === "outreach-complained" ? hasComplaint : !hasComplaint);
  });
  status.textContent = `${formatCount(items.length)} minőségi eset`;
  target.innerHTML = items.map(row => `<article class="shift-card quality-outreach-row">
    <div><strong>${escapeHtml(row.courier_name)}</strong>
      ${row.source === "hub_validated" ? '<span class="source quality-outreach-source">Validált HUB adat</span>' : ""}
      <p>${escapeHtml(row.work_date)} · ${escapeHtml(qualityOutreachTopics[row.topic])}
      · ${row.topic === "uncleanedTimeWindowLate" ? "Route ID " : ""}${escapeHtml(row.reference)}
      ${row.item_count > 1 ? ` · ${formatCount(row.item_count)} cím` : ""}</p>
      <p>${escapeHtml(qualityOutreachStates[row.state])} · ${row.last_email_sent_at
        ? `E-mail kiküldve <time datetime="${escapeHtml(row.last_email_sent_at)}">${escapeHtml(new Intl.DateTimeFormat("hu-HU", {
            dateStyle: "short", timeStyle: "short", timeZone: "Europe/Budapest",
          }).format(new Date(row.last_email_sent_at)))}</time>` : "Nincs igazolt e-mail-küldés"}</p></div>
    ${["complained", "not_complained"].includes(row.state) || (row.state === "in_progress" && row.complaint_id)
      ? `<button type="button" class="secondary" data-outreach-form="${escapeHtml(row.id)}">Google-űrlap előkészítése</button>` : ""}
  </article>`).join("") || '<p class="empty-card">Nincs ilyen minőségi eset.</p>';

  target.querySelectorAll("[data-outreach-form]").forEach(button => button.addEventListener("click", async () => {
    const row = items.find(item => item.id === button.dataset.outreachForm);
    button.disabled = true;
    try {
      const id = row.complaint_id || (await api(`/api/quality/outreach/${encodeURIComponent(row.id)}/complaint`, {
        method: "POST", body: "{}",
      })).complaintId;
      const payload = await api(`/api/quality/complaints?complaint=${encodeURIComponent(id)}`);
      if (!isCurrent()) return;
      const item = payload.items?.[0];
      if (!item || item.status !== "open" || ["uncertain", "sent"].includes(item.delivery?.state)) {
        throw new Error("Ehhez az ügyhöz most nem indítható Google-űrlapos továbbítás.");
      }
      await openQualityInboxAction(item, "forward", payload.forwardingEnabled);
    } catch (error) {
      if (isCurrent()) status.textContent = error.message;
    } finally {
      button.disabled = false;
    }
  }));
}

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
  const panel = root.closest('details');
  if (panel && state.qualityComplaintFocus) panel.open = true;
  if (panel && !panel.open && !state.qualityWorkspaceCourier) return true;
  if (state.qualityComplaintFocus && state.qualityWorkspaceFocus !== state.qualityComplaintFocus) {
    try {
      const focused = await api(`/api/quality/complaints?complaint=${encodeURIComponent(state.qualityComplaintFocus)}`);
      const item = focused.items?.[0], day = item?.affected_items?.[0]?.date;
      if (item && day?.slice(0, 7) === QUALITY_COMPLAINT_MONTH) {
        state.qualityWorkspaceCourier = String(item.courier_id);
        state.qualityWorkspaceDay = day;
        state.qualityWorkspaceFocus = state.qualityComplaintFocus;
      }
    } catch(error) { root.textContent = error.message; return false; }
  }
  const month = QUALITY_COMPLAINT_MONTH;
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
      <label>Reklamáció típusa<select id="quality-workspace-type"><option value="all">Összes reklamáció</option>${Object.entries(categories).map(([key,label]) => `<option value="${escapeHtml(key)}" ${state.qualityWorkspaceType === key ? 'selected' : ''}>${escapeHtml(label)}</option>`).join('')}</select></label></div>
      ${(payload.warnings || []).map(text => `<p class="notice error">${escapeHtml(text)}</p>`).join('')}
      ${courier ? `<article class="shift-card"><div class="shift-top"><div><h3>${escapeHtml(courier.courierName)}</h3><p>#${escapeHtml(courier.courierId)} · ${escapeHtml(month)}</p></div><button type="button" class="secondary" id="quality-workspace-back">Vissza a futárlistához</button></div>
        <div class="workflow-tabs">${Object.entries(categories).map(([key,label]) => `<button type="button" class="secondary" data-quality-type="${escapeHtml(key)}">${escapeHtml(label)}</button>`).join('')}</div>
        <div class="shift-list">${qualityWorkspaceDays(courier).map(day => `<button type="button" class="financial-card" data-quality-day="${escapeHtml(day.date)}"><strong>${escapeHtml(day.date)}</strong><span>${escapeHtml([...new Set(day.items.map(item => categories[item.category] || 'Egyéb'))].join(' · '))}</span><small>${day.items.length} ügy vagy jelzés</small></button>`).join('') || '<p class="empty-card">Ebben a hónapban és kategóriában nincs rögzített ügy.</p>'}</div>
        <div id="quality-workspace-day"></div></article>` : `<div class="settlement-quick-search"><label>Gyorskeresés az összes futár között<input id="quality-workspace-search" type="search" value="${escapeHtml(state.qualityWorkspaceQuery || '')}" placeholder="Név vagy futár ID részlete…" autocomplete="off"></label><p>Részleges név- és ID-keresés, ékezet nélkül is.</p></div><div id="quality-workspace-roster"></div>`}`;
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
    const selected = Boolean(courier && state.qualityWorkspaceDay);
    if (!courier) renderQualityRoster();
    if (!selected) return true;
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
  document.querySelector('#quality-workspace-panel')?.addEventListener('toggle', event => {
    if (event.target.open && !state.qualityComplaintFocus) loadQualityComplaints();
  });
  document.querySelector('#quality-route-signals-panel')?.addEventListener('toggle', event => {
    if (event.target.open) loadAdminRouteSignals();
  });
  document.querySelector('#quality-complaints-refresh')?.addEventListener('click', () => {
    state.qualityWorkspace = null;
    if (document.querySelector('#quality-route-signals-panel')?.open) loadAdminRouteSignals();
  }, true);
});
