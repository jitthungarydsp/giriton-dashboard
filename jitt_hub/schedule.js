const scheduleDate = value => new Date(value + 'T12:00:00Z');
const scheduleToday = () => new Intl.DateTimeFormat('en-CA', {timeZone:'Europe/Budapest', year:'numeric', month:'2-digit', day:'2-digit'}).format(new Date());
const scheduleDayLabel = new Intl.DateTimeFormat('hu-HU', {dateStyle:'full',timeZone:'UTC'});
const scheduleMonthLabel = new Intl.DateTimeFormat('hu-HU', {year:'numeric',month:'long',timeZone:'UTC'});
const scheduleWeekdays = ['H','K','Sze','Cs','P','Szo','V'];
const scheduleState = {day:null, warehouse:'BUD2', query:'', selectedId:null, result:null, loading:false, error:'', sequence:0};

function scheduleShiftDay(value, by) {
  const date = scheduleDate(value);
  date.setUTCDate(date.getUTCDate() + by);
  return date.toISOString().slice(0,10);
}

function scheduleMonday(value) {
  return scheduleShiftDay(value, -((scheduleDate(value).getUTCDay() + 6) % 7));
}

function scheduleVisibleShifts(day) {
  const rows = scheduleState.result?.days?.[day] || [];
  const term = rekiText(scheduleState.query).replace(/^#/, '');
  if (!term) return rows;
  const time = /^\d{1,2}[:.]\d{2}$/.test(term) ? term.replace('.',':').padStart(5,'0') : term;
  return rows.flatMap(row => {
    if (row.time.startsWith(time) || row.time.replace(/^0/,'').startsWith(time)) return [row];
    const people = row.people.filter(person => String(person.id || '').includes(term) || rekiText(person.giritonId).includes(term) || rekiText(person.name).includes(term));
    return people.length ? [{...row, visiblePeople:people}] : [];
  });
}

function scheduleGap(row) {
  if (row.uncertain) return {kind:'unknown', label:'Ellenőrizendő'};
  const hub = row.people.some(person => !person.hub);
  const muszakpro = row.people.some(person => !person.muszakpro);
  if (hub && muszakpro) return {kind:'diff', label:'Eltérő névsor'};
  if (hub) return {kind:'diff', label:'Hiányzik a Hubban'};
  if (muszakpro) return {kind:'diff', label:'Hiányzik a MűszakProban'};
  return {kind:'ok', label:row.people.length ? 'Egyezik' : 'Nincs foglalás'};
}

function scheduleWeekLabel(first,last) {
  const month = value => scheduleMonthLabel.format(scheduleDate(value));
  const day = value => scheduleDate(value).getUTCDate();
  return first.slice(0,7) === last.slice(0,7) ? `${month(first)} ${day(first)}–${day(last)}.` :
    `${month(first)} ${day(first)}. – ${month(last)} ${day(last)}.`;
}

function scheduleRoster(selected) {
  const roster = $('#schedule-roster');
  roster.hidden = !selected;
  const body = $('#schedule-roster-table tbody');
  if (!selected) { body.replaceChildren(); return; }
  const people = selected.visiblePeople || selected.people;
  $('#schedule-roster-title').textContent = `${selected.time || '—'} · Beosztott futárok`;
  const note = $('#schedule-roster-note');
  note.hidden = Boolean(people.length) && !selected.uncertain;
  note.textContent = selected.uncertain ? 'A két forrásból elérhető névsor ellenőrzendő.' : 'Ehhez a műszakhoz nincs rögzített futár.';
  const status = value => value ? '<strong class="shift-ok">Felvezetve</strong>' :
    selected.uncertain ? '<small>Ellenőrizendő</small>' : '<small>Nincs felvezetve</small>';
  body.innerHTML = people.map((person,index) => `<tr><td>
    <button type="button" class="schedule-person" data-person="${index}" aria-haspopup="dialog">${esc(person.name || 'Ismeretlen futár')}</button>
    ${person.id ? `<small>#${esc(person.id)}</small>` : person.giritonId ? `<small>Giriton · ${esc(person.giritonId)}</small>` : ''}</td><td>${status(person.hub)}</td><td>${status(person.muszakpro)}</td></tr>`).join('');
}

function renderSchedule() {
  const {day, warehouse, result, loading, error} = scheduleState;
  if (!day) return;
  const first = scheduleMonday(day);
  $('#schedule-week-title').textContent = scheduleWeekLabel(first,scheduleShiftDay(first,6));
  $$('[data-warehouse]').forEach(button => button.setAttribute('aria-pressed',String(button.dataset.warehouse === warehouse)));
  const source = result ? [result.sheetAvailable ? 'RobotShift · '+warehouse : 'Hub és MűszakPro adatbázis',
    result.logDirect ? 'MűszakPro LOG' : result.logAvailable === false ? 'A MűszakPro naplója nem elérhető' :
      result.logUpdatedAt ? 'MűszakPro napló mentve '+c360Date(result.logUpdatedAt) : ''].filter(Boolean).join(' · ') : '';
  $('#schedule-source-status').textContent = loading ? 'Beosztás betöltése…' : error || source;
  $('.schedule-days').innerHTML = Array.from({length:7},(_,index)=>{
    const date = scheduleShiftDay(first,index);
    const rows = scheduleVisibleShifts(date);
    const diff = rows.filter(row=>scheduleGap(row).kind === 'diff').length;
    const check = rows.filter(row=>scheduleGap(row).kind === 'unknown').length;
    const hint = diff ? diff+' eltérés' : check ? 'Ellenőrizendő' : '';
    return `<button class="schedule-day" type="button" data-date="${date}" aria-pressed="${date === day}"
      aria-label="${scheduleDayLabel.format(scheduleDate(date))}, ${rows.length} műszak, ${diff} eltérés, ${check} ellenőrizendő">
      <span class="schedule-day-small">${scheduleWeekdays[index]}</span><b>${scheduleDate(date).getUTCDate()}</b>
      <span class="schedule-day-small schedule-day-shifts">${result ? rows.length+' műszak' : '—'}</span>
      <span class="schedule-day-alert"><span>${hint}</span><sup aria-hidden="true">${hint ? '●' : ''}</sup></span></button>`;
  }).join('');
  const rows = scheduleVisibleShifts(day);
  const selected = rows.find(row=>row.id === scheduleState.selectedId) || rows.find(row=>row.people.length) || rows[0];
  scheduleState.selectedId = selected?.id || null;
  $('#schedule-day-title').textContent = scheduleDayLabel.format(scheduleDate(day))+' · '+warehouse;
  $('#schedule-day-totals').textContent = rows.length ? `${rows.length} műszak · ${rows.filter(row=>scheduleGap(row).kind === 'diff').length} eltérés` : '';
  $('#schedule-shifts').hidden = !rows.length;
  $('.schedule-empty').hidden = Boolean(rows.length) || loading || Boolean(error) || !result;
  $('.schedule-empty').textContent = scheduleState.query ? 'Erre a napra nincs találat.' : 'Erre a napra nincs műszak.';
  $('#schedule-shifts tbody').innerHTML = rows.map(row => {
    const gap = scheduleGap(row);
    const hubCount = row.people.filter(person=>person.hub).length;
    const msCount = row.people.filter(person=>person.muszakpro).length;
    return `<tr><td><button type="button" class="schedule-shift-select" data-shift="${esc(row.id)}"
      aria-pressed="${row.id === scheduleState.selectedId}">${esc(row.time || '—')}</button><small>${esc(row.name)}</small></td>
      <td>${hubCount} futár</td><td>${msCount} futár</td><td><strong class="shift-${gap.kind}">${gap.label}</strong></td></tr>`;
  }).join('');
  scheduleRoster(selected);
}

async function openSchedule() {
  scheduleState.day ||= scheduleToday();
  const week = scheduleMonday(scheduleState.day);
  const sequence = ++scheduleState.sequence;
  scheduleState.loading = true;
  scheduleState.error = '';
  scheduleState.result = null;
  renderSchedule();
  try {
    const result = await api('/api/schedule-week?' + new URLSearchParams({week,warehouse:scheduleState.warehouse}));
    if (sequence !== scheduleState.sequence) return;
    scheduleState.result = result;
    scheduleSelectFirstMatch();
  } catch (error) {
    if (sequence === scheduleState.sequence) scheduleState.error = error.message;
  } finally {
    if (sequence === scheduleState.sequence) {
      scheduleState.loading = false;
      renderSchedule();
    }
  }
}

function clearSchedule() {
  scheduleState.sequence++;
  Object.assign(scheduleState,{day:null,result:null,selectedId:null,query:'',error:'',loading:false});
  const root = $('#schedule-board');
  if (!root) return;
  const dialog = $('#schedule-booking-log');
  if (dialog.open) dialog.close();
  ['#schedule-shifts tbody','#schedule-roster-table tbody','#schedule-log-title','#schedule-log-context',
    '#schedule-log-hub-time','#schedule-log-actor','#schedule-log-booked-at'].forEach(selector=>$(selector).replaceChildren());
  $('#schedule-search').value = '';
}

function scheduleSelectFirstMatch() {
  const {day,query} = scheduleState;
  if (!query || scheduleVisibleShifts(day).length) return;
  const first = scheduleMonday(day);
  const match = Array.from({length:7},(_,index)=>scheduleShiftDay(first,index)).find(value=>scheduleVisibleShifts(value).length);
  if (match) scheduleState.day = match;
}

function openScheduleLog(index) {
  const row = scheduleVisibleShifts(scheduleState.day).find(row=>row.id === scheduleState.selectedId);
  const person = (row?.visiblePeople || row?.people)?.[index];
  if (!person) return;
  const set = (field,value) => { $('#schedule-log-'+field).textContent = value; };
  const timestamp = value => value && value.includes('T') ? c360Date(value) : value || 'Nincs rögzítve';
  set('title',person.name || 'Ismeretlen futár');
  set('context',[person.id ? '#'+person.id : '',scheduleState.warehouse,
    scheduleDayLabel.format(scheduleDate(scheduleState.day)),row.time].filter(Boolean).join(' · '));
  set('hub-field',person.firstSeenAt ? 'Először látható a Hubban' : 'Felvezetés ideje');
  set('hub-time',person.hub ? timestamp(person.assignedAt || person.firstSeenAt) : row.uncertain ? 'Ellenőrizendő' : 'Nincs felvezetve');
  $('#schedule-log-hub-note').hidden = !person.firstSeenAt;
  set('actor',person.log?.actor || 'Nincs rögzítve');
  set('booked-at',person.log?.at ? timestamp(person.log.at) : scheduleState.result.logAvailable === false ?
    'A napló nem elérhető' : person.muszakpro ? 'Nincs egyező naplóbejegyzés' : row.uncertain ? 'Ellenőrizendő' : 'Nincs foglalás');
  $('#schedule-booking-log').showModal();
}

document.addEventListener('DOMContentLoaded',()=>{
  $('#schedule-search').addEventListener('input',event=>{
    scheduleState.query = event.target.value.trim();
    scheduleSelectFirstMatch();
    renderSchedule();
  });
  $('#schedule-board').addEventListener('click',event=>{
    const button = event.target.closest('button');
    if (!button) return;
    const {warehouse,date,move,shift,person} = button.dataset;
    if (person != null) { openScheduleLog(Number(person)); return; }
    if (warehouse) { scheduleState.warehouse = warehouse; openSchedule(); return; }
    if (move) { scheduleState.day = scheduleShiftDay(scheduleState.day,Number(move)); openSchedule(); return; }
    if (button.hasAttribute('data-today')) { scheduleState.day = scheduleToday(); openSchedule(); return; }
    if (date) scheduleState.day = date;
    else if (shift) scheduleState.selectedId = shift;
    else return;
    renderSchedule();
    if (date) $('.schedule-day[aria-pressed="true"]')?.focus();
    if (shift) $('.schedule-shift-select[aria-pressed="true"]')?.focus();
  });
});
