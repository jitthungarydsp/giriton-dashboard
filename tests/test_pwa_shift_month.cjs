const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const test = require('node:test');
const source = fs.readFileSync(require('node:path').join(__dirname, '../pwa/app.js'), 'utf8');
test('month shows every day and selecting a day uses existing data without API calls', () => {
  const nodes = new Map();
  const node = () => ({ children: [], setAttribute() {}, addEventListener(name, fn) { this[name] = fn; }, appendChild(child) { this.children.push(child); } });
  const get = id => { if (!nodes.has(id)) nodes.set(id, node()); return nodes.get(id); };
  let rendered = 0;
  const context = { Date, Map, state: { shiftMonth: '2026-11', selectedDate: '2026-11-01', data: { items: [{ date: '2026-11-02', status: 'waiting' }] } },
    $: get, localDate: () => '2026-10-29', document: { createElement: node },
    renderShifts() { rendered++; }, renderOpenMuszakproShifts() {}, api() { throw Error('Day selection must not fetch'); } };
  vm.runInNewContext(source.slice(source.indexOf('function renderTabs()'), source.indexOf('function shiftCard')), context);
  context.renderTabs();
  assert.equal(get('#day-tabs').children.length, 30);
  assert.match(get('#day-tabs').children[1].innerHTML, /Eltérés/);
  get('#day-tabs').children[1].click();
  assert.equal(context.state.selectedDate, '2026-11-02');
  assert.equal(rendered, 1);
});
