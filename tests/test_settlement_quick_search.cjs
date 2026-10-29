const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const test = require('node:test');
const source = fs.readFileSync(require('node:path').join(__dirname, '../pwa/app.js'), 'utf8');
const context = {};
vm.runInNewContext(source.slice(source.indexOf('function settlementDashboardVisibleRows('), source.indexOf('function renderSettlementDashboard()')), context);
const rows = [
  { courierId:'6498', courierName:'Bárándi Bendegúz', status:{label:'Kifizetve'} },
  { courierId:'7440', courierName:'Wasil Futár', status:{label:'Reklamáció'} },
];
test('partial name and ID search ignores status filters and accents', () => {
  for (const query of ['barandi', 'BÁRÁ', 'bende', 'bar ben', '#649']) {
    const found = context.settlementDashboardVisibleRows(rows, query, 'Reklamáció');
    assert.equal(found.length, 1, query);
    assert.equal(found[0].courierId, '6498');
  }
});
test('clearing search restores the selected filter; no match remains empty', () => {
  assert.equal(context.settlementDashboardVisibleRows(rows, '', 'Reklamáció')[0].courierId, '7440');
  assert.equal(context.settlementDashboardVisibleRows(rows, '   ', '').length, 2);
  assert.equal(context.settlementDashboardVisibleRows(rows, 'nincsilyen', '').length, 0);
});
test('typing renders from loaded rows without any API request and keeps cursor', () => {
  const handlers = {};
  const input = { focus() {}, setSelectionRange(start, end) { this.selection = [start,end]; } };
  let renders = 0;
  const ctx = { state:{}, $: selector => selector === '#settlement-dashboard-panel' ? { addEventListener(name, fn) { handlers[name] = fn; } } : input,
    renderSettlementDashboard() { renders++; }, api() { throw Error('Typing must not fetch'); } };
  const start = source.indexOf('$("#settlement-dashboard-panel")?.addEventListener("input"');
  const end = source.indexOf('$("#settlement-import-config-panel")?.addEventListener("change"', start);
  vm.runInNewContext(source.slice(start,end), ctx);
  handlers.input({target:{id:'settlement-dashboard-search', value:'bende', selectionStart:3, selectionEnd:3}});
  assert.equal(ctx.state.settlementDashboardQuery, 'bende');
  assert.deepEqual(input.selection,[3,3]);
  assert.equal(renders,1);
  handlers.click({target:{closest:()=>true}});
  assert.equal(ctx.state.settlementDashboardQuery,'');
});
