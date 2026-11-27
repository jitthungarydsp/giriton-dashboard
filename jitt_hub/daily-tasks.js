const dailyTaskGroups = {
  quality: {title: 'Minőségi reklamációk', empty: 'Nincs nyitott minőségi reklamáció.'},
  settlement: {title: 'Elszámolási reklamációk', empty: 'Nincs nyitott elszámolási reklamáció.'},
  shifts: {title: 'Hub–MűszakPro eltérések', empty: 'A mai MűszakPro-foglalásoknál nincs jelzett eltérés.', note: 'Az összevetés a mai MűszakPro-foglalásokból indul ki.'},
  absences: {title: 'Nem jelentek meg', empty: 'A jelenléti adatokban nincs rögzített hiányzás.'},
  payments: {title: 'Kifizetésre várnak', empty: 'Nincs kifizetésre váró elszámolás.'},
  advances: {title: 'Fizetési előlegek', empty: 'Nincs aktív előleg vagy jóváhagyott előlegigény.'},
};
const dailyTaskStatuses = {new: 'Új', open: 'Nyitott', in_review: 'Vizsgálat alatt', in_progress: 'Folyamatban'};
const advanceStatuses = {plan: 'Aktív törlesztési terv', approved: 'Jóváhagyott igény', paid: 'Folyósítva'};
let dailyTasksPayload = null;
let dailyTaskGroup = 'quality';
let dailyTasksSequence = 0;

function clearDailyTasks() {
  dailyTasksSequence++;
  dailyTasksPayload = null;
  dailyTaskGroup = 'quality';
  const list = $('#daily-task-rows');
  list.replaceChildren();
  $('#daily-task-search').value = '';
  $('#daily-task-status').textContent = '';
  $('#daily-task-note').hidden = true;
  $$('[data-daily-group] .daily-task-count').forEach(count => { count.textContent = '—'; });
}

async function loadDailyTasks() {
  const sequence = ++dailyTasksSequence;
  const status = $('#daily-task-status');
  const button = $('#daily-task-refresh');
  button.disabled = true;
  status.textContent = 'Feladatok betöltése…';
  $('#daily-task-rows').setAttribute('aria-busy', 'true');
  try {
    const payload = await api('/api/daily-tasks');
    if (sequence !== dailyTasksSequence) return;
    dailyTasksPayload = payload;
    const date = new Date(payload.date + 'T12:00:00Z');
    const label = date.toLocaleDateString('hu-HU', {timeZone: 'Europe/Budapest', weekday: 'long', year: 'numeric', month: 'long', day: 'numeric'});
    const time = new Date(payload.generatedAt).toLocaleTimeString('hu-HU', {timeZone: 'Europe/Budapest', hour: '2-digit', minute: '2-digit'});
    status.textContent = `${label} · Frissítve ${time}`;
    renderDailyTasks();
  } catch {
    if (sequence !== dailyTasksSequence) return;
    dailyTasksPayload = null;
    status.textContent = 'A napi lista nem tölthető be. Próbáld újra a Frissítés gombbal.';
    renderDailyTasks();
  } finally {
    if (sequence === dailyTasksSequence) {
      button.disabled = false;
      $('#daily-task-rows').setAttribute('aria-busy', 'false');
    }
  }
}

function dailyTaskRow(row, index) {
  const id = String(row.courier_id ?? '');
  const hasCourier = /^\d{1,12}$/.test(id);
  const identity = `<strong>${esc(row.courier_name || 'Ismeretlen futár')}</strong>${id ? ` <span class="muted">#${esc(id)}</span>` : ''}`;
  const actionButton = (label, dialog = false) => hasCourier
    ? `<button type="button" class="c360-button" data-daily-row="${index}"${dialog ? ' aria-haspopup="dialog"' : ''}>${label}</button>`
    : '';
  if (dailyTaskGroup === 'shifts') {
    const startTime = time => time ? esc(time.slice(0, 5)) : '—';
    return `<li class="daily-task-row"><div>${identity}<p>${esc(row.comparison_reason)}</p>
      <p>${row.warehouse_code ? esc(row.warehouse_code) + ' · ' : ''}MűszakPro ${startTime(row.muszakpro_shift_start_time)} · Hub ${startTime(row.hub_booking_shift_start_time)}</p></div>
      ${actionButton('Műszakok megnyitása')}</li>`;
  }
  if (dailyTaskGroup === 'absences') {
    const marks = row.attendance.map(shift => [shift.warehouse, shift.start, shift.shift].filter(Boolean).join(' · '));
    const hub = Object.entries(row.hub).map(([warehouse, count]) => `${warehouse} · ${nf.format(count)} műszak`);
    return `<li class="daily-task-row"><div>${identity}
      ${marks.length ? `<p>Rögzített hiányzás – ${esc(marks.join(', '))}</p>` : ''}
      ${hub.length ? `<p>Hub által jelzett no-show – ${esc(hub.join(', '))}</p>` : ''}</div>
      ${actionButton('Műszakok megnyitása')}</li>`;
  }
  if (dailyTaskGroup === 'payments') {
    return `<li class="daily-task-row"><div>${identity}<p>${esc(monthLabel(row.period_start.slice(0, 7)))}${row.warehouse ? ' · ' + esc(row.warehouse) : ''}</p></div>
      <div class="daily-task-actions"><strong>${huf(row.payable_huf)}</strong>${actionButton('Kifizetés részletei', true)}</div></li>`;
  }
  if (dailyTaskGroup === 'advances') {
    const next = row.nextPeriod ? ` · Következő nyitott részlet ${esc(monthLabel(row.nextPeriod.slice(0, 7)))}` : '';
    const remaining = row.remaining != null ? `<p>Hátralévő törlesztés ${huf(row.remaining)}${next}</p>` : '';
    return `<li class="daily-task-row"><div>${identity}<p>${esc(advanceStatuses[row.status])} · Kezdés ${c360Date(row.start_date, false)}</p>${remaining}</div>
      <div class="daily-task-actions"><strong>${huf(row.requested_amount_huf)}</strong>${actionButton('Futár megnyitása')}</div></li>`;
  }

  const isQuality = dailyTaskGroup === 'quality';
  const label = isQuality ? rekiTopic(row) : complaintActionLabel(row.document_type);
  const period = row.document_month ? ` · ${esc(monthLabel(row.document_month.slice(0, 7)))}` : '';
  const created = row.created_at ? ` · Beérkezett ${c360Date(row.created_at)}` : '';
  const query = new URLSearchParams({'hub-quality': 'open', 'quality-case': row.id});
  const action = isQuality
    ? `<a class="c360-button" href="https://futar.jitt.hu/?${esc(query.toString())}" target="_blank" rel="noopener">Kezelés a PWA-ban ↗</a>`
    : hasCourier && row.document_month
      ? actionButton('Reklamáció megnyitása', true)
      : '';
  return `<li class="daily-task-row"><div>${identity}<p>${esc(label)}${period}${created}</p></div>
    <div class="daily-task-actions"><span class="tag">${esc(dailyTaskStatuses[row.status] || row.status)}</span>${action}</div></li>`;
}

function renderDailyTasks() {
  $$('[data-daily-group]').forEach(button => {
    const group = button.dataset.dailyGroup;
    const rows = dailyTasksPayload?.[group]?.rows;
    button.setAttribute('aria-pressed', String(group === dailyTaskGroup));
    button.querySelector('.daily-task-count').textContent = rows ? nf.format(rows.length) : '—';
  });
  const group = dailyTaskGroups[dailyTaskGroup];
  $('#daily-task-heading').textContent = group.title;
  const list = $('#daily-task-rows');
  const section = dailyTasksPayload?.[dailyTaskGroup];
  const note = $('#daily-task-note');
  note.textContent = section?.note || group.note || '';
  note.hidden = !note.textContent;
  if (!section) {
    list.replaceChildren();
    return;
  }
  const query = rekiText($('#daily-task-search').value.trim());
  const rows = (section.rows || []).map((row, index) => (
    rekiText(`${row.courier_name ?? ''} ${row.courier_id ?? ''}`).includes(query) ? dailyTaskRow(row, index) : ''
  )).join('');
  const message = section.error || (section.rows.length ? 'Nincs találat a keresésre.' : section.empty || group.empty);
  list.innerHTML = rows || `<li class="empty">${esc(message)}</li>`;
}

document.addEventListener('DOMContentLoaded', () => {
  $('#daily-task-refresh').onclick = loadDailyTasks;
  $('#daily-task-search').oninput = renderDailyTasks;
  $$('[data-daily-group]').forEach(button => {
    button.onclick = () => {
      dailyTaskGroup = button.dataset.dailyGroup;
      renderDailyTasks();
    };
  });
  $('#daily-task-rows').onclick = event => {
    const button = event.target.closest('[data-daily-row]');
    if (!button) return;
    const row = dailyTasksPayload?.[dailyTaskGroup]?.rows?.[Number(button.dataset.dailyRow)];
    if (!row) return;
    if (dailyTaskGroup === 'settlement') {
      openStatusDialog(row.courier_id, 'Reklamáció', row.id, row.document_month.slice(0, 7));
    } else if (dailyTaskGroup === 'payments') {
      openStatusDialog(row.courier_id, 'Kifizetésre vár', null, row.period_start.slice(0, 7));
    } else {
      const date = dailyTasksPayload.date;
      const advance = dailyTaskGroup === 'advances';
      const month = (advance ? row.nextPeriod || row.start_date : date).slice(0, 7);
      openCourier360(row.courier_id, {date, month, tab: advance ? 'finance' : 'shifts', backLabel: 'Nap feladatok'});
    }
  };
  $('#courier-status-dialog').addEventListener('close', () => {
    if (!$('#app').hidden && !$('[data-view="daily"]').hidden) loadDailyTasks();
  });
});
