const financeBreakdownCache = new WeakMap();

function financeTotalComponents(field, row) {
  const labels = {
    base:'Alapdíj', tip:'Borravaló', delay:'Késedelmi díj', compliance:'Túramegfelelés',
    otherBonus:'Szerződésen kívüli bónusz', importedBonus:'Kifli bónusz', jittBonus:'JITT bónusz',
    customerRating:'Ügyfélértékelési bónusz', loyalty:'Lojalitás', importedMalus:'Kifli malusz',
    jittMalus:'JITT malusz', correctionDeduction:'Korrekció −', atm:'ATM / KP',
    salaryAdvance:'Fizetéselőleg', reserve:'Céltartalék', insurance:'Biztosítás',
    income:'Jóváírások összesen', deductionImpact:'Levonások összesen', correctionIncome:'Korrekció +',
  };
  const keys = {
    income:['base','tip','delay','compliance','otherBonus','importedBonus','jittBonus','customerRating','loyalty'],
    deductionImpact:['importedMalus','jittMalus','correctionDeduction','atm','salaryAdvance','reserve','insurance'],
    payable:['income','deductionImpact','correctionIncome'],
  }[field];
  if (!keys) return null;
  const rows = keys.map(key => ({label:labels[key], amount:(field === 'payable' && key === 'deductionImpact' ? -1 : 1) * (Number(row[key]) || 0)}));
  if (field === 'deductionImpact') {
    const expenses = (Number(row.otherDeduction) || 0) - (Number(row.correctionDeduction) || 0);
    if (expenses > 0) rows.push({label:'Egyéb levonás', amount:expenses});
  }
  return rows.filter(item => item.amount);
}

function financeBreakdownItems(field, value, items) {
  const sum = rows => rows.reduce((total, row) => total + row.amount, 0);
  if (field === 'tip' && items.tipByRoute?.length) return items.tipByRoute;
  const rows = (items[field] || []).filter(row => row.amount || row.note);
  const deductions = ['importedMalus','jittMalus','correctionDeduction','atm','salaryAdvance','reserve','insurance'];
  const sign = deductions.includes(field) && rows.some(row => row.amount < 0) ? -1 : 1;
  const displayed = rows.map(row => ({...row, amount:row.amount * sign}));
  if (['importedBonus','jittBonus','correctionIncome','importedMalus','jittMalus','correctionDeduction'].includes(field)) {
    const matchingSign = displayed.filter(row => row.amount > 0);
    if (sum(displayed) === value) return displayed;
    if (!value || sum(matchingSign) === value) return value ? matchingSign : [];
  }
  return displayed;
}

async function openFinanceBreakdown(button) {
  const row = data?.couriers?.find(item => String(item.courierId) === button.dataset.financeCourier);
  if (!row) return;
  const dialog = $('#courier-finance-dialog');
  const body = $('#courier-finance-body');
  const field = button.dataset.financeField;
  const value = Number(row[field]) || 0;
  const month = $('#month').value;
  const selection = {};
  dialog.financeSelection = selection;
  $('#courier-finance-title').textContent = button.dataset.financeLabel;
  $('#courier-finance-context').textContent = `${row.courierName} · #${row.courierId} · ${monthLabel(month)}`;
  $('#courier-finance-total').textContent = huf(value);
  body.textContent = 'Bontás betöltése…';
  if (!dialog.open) dialog.showModal();

  function render(items, source) {
    const sum = items.reduce((total, item) => total + item.amount, 0);
    body.innerHTML = `${source ? `<p class="muted">${esc(source)}</p>` : ''}${items.length ? `<ul class="finance-breakdown-items">${items.map(item =>
      `<li><span>${esc(item.label)}${item.note ? `<small>${esc(item.note)}</small>` : ''}</span><b>${huf(item.amount)}</b></li>`).join('')}</ul>
      ${sum !== value ? `<p class="notice">A megjeleníthető tételek összege ${huf(sum)}. A kártya összegéhez képest ${huf(value - sum)} eltéréshez nincs egyező bontás.</p>` : ''}`
      : '<p class="muted">Ehhez az összeghez nincs mentett részlettétel.</p>'}`;
  }

  const total = financeTotalComponents(field, row);
  if (total) { render(total, 'A havi futárkártyán szereplő tételek alapján.'); return; }
  const isAdvance = field === 'salaryAdvanceAdded';
  if (!isAdvance && !row.financeSnapshotId) { render([], 'Havi összesítő alapján.'); return; }
  const cacheKey = isAdvance ? 'advance' : 'snapshot';
  let cached = financeBreakdownCache.get(row);
  if (!cached) financeBreakdownCache.set(row, cached = new Map());
  const params = new URLSearchParams({courier:row.courierId, month});
  if (isAdvance) params.set('kind','advance');
  else params.set('snapshot',row.financeSnapshotId);
  if (!cached.has(cacheKey)) cached.set(cacheKey, api(`/api/courier-finance-breakdown?${params}`).catch(error => { cached.delete(cacheKey); throw error; }));
  try {
    const result = await cached.get(cacheKey);
    if (!dialog.open || dialog.financeSelection !== selection) return;
    render(isAdvance ? result.items : financeBreakdownItems(field, value, result.items),
      isAdvance ? 'A havi előlegnyilvántartás alapján.' : `Mentett elszámolás · v${result.snapshot.version}`);
  } catch (error) {
    if (dialog.open && dialog.financeSelection === selection) body.textContent = error.message;
  }
}

document.addEventListener('click', event => {
  const button = event.target.closest('[data-finance-field]');
  if (button) openFinanceBreakdown(button);
  if (event.target.closest('[data-finance-close]')) {
    const dialog = $('#courier-finance-dialog');
    dialog.financeSelection = null;
    dialog.close();
  }
});
