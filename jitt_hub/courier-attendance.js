const attendanceBoard = $('[data-view="attendance"]');
$('#attendance-courier-search').innerHTML = c360SearchControls('attendance-c360-search', 'Futárnév, azonosító, műszakkezdés vagy státusz');
const attendanceSearch = $('#attendance-c360-search-input');
const attendanceWarehouse = $('#attendance-warehouse');
const attendanceRows = $('#attendance-rows');
const attendanceRefresh = $('#attendance-refresh');
const attendanceStatus = $('#attendance-status');
const attendanceClock = new Intl.DateTimeFormat('hu-HU',{timeZone:'Europe/Budapest',hour:'2-digit',minute:'2-digit'});
const attendanceFilters = {
  all:'Összes futár', arrived:'Belépett', upcoming:'Várható', missing:'Nincs belépés',
};
const attendanceLabels = {
  arrived:'Belépett a Giritonba', upcoming:'Várható', due:'30 percen belül kezd · nincs belépés',
  overdue:'Elkezdődött a műszak · nincs belépés', unknown:'Jelenlét nem ellenőrizhető',
};
let attendanceData = null;
let attendanceRequest = null;
let attendanceTimer = null;
let attendanceFilter = 'all';

function renderAttendance() {
  const query = c360SearchText(attendanceSearch.value).replace(/^#/,'');
  const liveFilter = c360ActiveQuery(query);
  const liveIds = liveFilter ? new Set(c360SearchState(attendanceSearch.form).liveRows.map(row=>String(row.courierId))) : null;
  const warehouse = attendanceWarehouse.value;
  const couriers = (attendanceData?.couriers || []).filter(row =>
    (!warehouse || row.shifts.some(shift=>shift.warehouse===warehouse)) &&
    (liveIds ? liveIds.has(String(row.courierId)) :
      c360SearchText([row.courierName,row.courierId,...row.shifts.map(shift=>shift.start)].join(' ')).includes(query)));
  const group = row=>['due','overdue'].includes(row.status)?'missing':row.status;
  for (const button of attendanceBoard.querySelectorAll('[data-attendance-filter]')) {
    const filter = button.dataset.attendanceFilter;
    const count = filter === 'all' ? couriers.length : couriers.filter(row=>group(row)===filter).length;
    button.setAttribute('aria-pressed',String(filter===attendanceFilter));
    button.textContent = attendanceFilters[filter] + (attendanceData ? ' · '+count : '');
  }
  if (!attendanceData) {
    attendanceRows.innerHTML='';
    return;
  }
  const rows = couriers.filter(row=>attendanceFilter==='all'||group(row)===attendanceFilter);
  attendanceRows.innerHTML = rows.map(row=>{
    const name = esc(row.courierName || ('Futár #'+row.courierId));
    const profile = row.courierId
      ? '<button type="button" class="attendance-profile" data-attendance-courier="'+esc(row.courierId)+'">'+name+'</button>'
      : '<strong>'+name+'</strong>';
    const starts = row.shifts.map(shift=>esc(shift.start)+(shift.warehouse?' · '+esc(shift.warehouse):'')).join('<br>');
    return '<tr data-attendance-status="'+esc(row.status)+'"><td>'+profile+
      (row.courierId?'<small>#'+esc(row.courierId)+'</small>':'')+
      '</td><td>'+ (starts || '—') +'</td><td><span class="attendance-state">'+esc(attendanceLabels[row.status])+
      '</span></td><td>'+esc(row.checkin || '—')+'</td><td>'+esc(row.checkout || '—')+'</td></tr>';
  }).join('') || '<tr><td colspan="5" class="attendance-empty">Nincs futár ebben a nézetben.</td></tr>';
}

async function loadAttendance() {
  if (attendanceRequest) return;
  const controller = new AbortController();
  attendanceRequest = controller;
  attendanceRefresh.disabled = true;
  if (!attendanceData) attendanceStatus.textContent = 'A mai jelenlét betöltése…';
  try {
    const data = await api('/api/courier-attendance',{signal:controller.signal,cache:'no-store'});
    if (attendanceRequest !== controller) return;
    attendanceData = data;
    $('#attendance-date').textContent = new Intl.DateTimeFormat('hu-HU',{timeZone:'UTC',dateStyle:'full'})
      .format(new Date(data.date+'T00:00:00Z'));
    const sync = data.syncedAt ? attendanceClock.format(new Date(data.syncedAt)) : '';
    attendanceStatus.textContent = [
      sync ? 'Giriton utolsó szinkronja '+sync : 'Ma még nincs Giriton-szinkron.',
      sync && !data.attendanceFresh ? 'A jelenléti adatok elavultak.' : '',
      data.partial ? 'Egyes adatforrások hiányosak.' : '',
      data.unmatchedShifts ? 'Azonosítatlan műszakok: '+data.unmatchedShifts : '',
    ].filter(Boolean).join(' · ');
    if (c360ActiveQuery(attendanceSearch.value)) c360RenderSearch(attendanceSearch,{expand:false});
    else renderAttendance();
  } catch {
    if (attendanceRequest !== controller) return;
    attendanceData = null;
    renderAttendance();
    attendanceStatus.textContent = 'A jelenléti frissítés sikertelen. Próbáld újra a Frissítés gombbal.';
  } finally {
    if (attendanceRequest === controller) {
      attendanceRequest = null;
      attendanceRefresh.disabled = false;
    }
  }
}

function openAttendance() {
  loadAttendance();
  attendanceTimer ||= setInterval(()=>{
    if (!document.hidden && !$('#app').classList.contains('courier360-open')) loadAttendance();
  },30000);
}

function closeAttendance() {
  clearInterval(attendanceTimer);
  attendanceTimer = null;
  attendanceRequest?.abort();
  attendanceRequest = null;
  attendanceData = null;
  const searchState = c360SearchState(attendanceSearch.form);
  searchState.sequence++;
  searchState.liveRows = [];
  c360DismissSearch(attendanceSearch.form);
  attendanceRefresh.disabled = false;
  renderAttendance();
}

function attendanceSearchOptions() {
  return (attendanceData?.couriers || []).map(row=>({...row,searchTerms:row.shifts.map(shift=>shift.start).join(' ')}));
}

function openAttendanceCourier(id) {
  return openCourier360(id,{
    date:attendanceData?.date || c360Today(),tab:'live',backLabel:'Vissza a mai jelenléthez',
  });
}

attendanceSearch.form.addEventListener('c360-search-change',renderAttendance);
attendanceWarehouse.addEventListener('change',renderAttendance);
attendanceRefresh.addEventListener('click',loadAttendance);
attendanceBoard.addEventListener('click',event=>{
  const filter = event.target.closest('[data-attendance-filter]');
  if (filter) {
    attendanceFilter = filter.dataset.attendanceFilter;
    renderAttendance();
  }
  const courier = event.target.closest('[data-attendance-courier]');
  if (courier) openAttendanceCourier(courier.dataset.attendanceCourier);
});
