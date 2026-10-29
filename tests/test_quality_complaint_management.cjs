const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const test = require('node:test');
const source = fs.readFileSync(require('node:path').join(__dirname, '../pwa/app.js'), 'utf8');
function setup(role, items) {
  const nodes = new Map();
  const get = key => { if (!nodes.has(key)) nodes.set(key, { value: 'all', querySelectorAll: () => [] }); return nodes.get(key); };
  const context = { state: { user: { role } }, $: get,
    escapeHtml: value => String(value || '').replaceAll('<', '&lt;').replaceAll('>', '&gt;'),
    shortDateTime: String, api: async () => ({ items, canManage: true, hasMore: false }) };
  vm.runInNewContext(source.slice(source.indexOf('function qualityComplaintStatus('), source.indexOf('function ensureQualityReclamationDialog(')), context);
  return { context, get };
}
test('admin sees open actions, closed response and escaped complaint text', async () => {
  const { context, get } = setup('admin', [
    { id: 'a', courier_name: '<script>', topic: 'lateShift', status: 'open', affected_items: [], history: [] },
    { id: 'b', courier_name: 'Futár', status: 'closed', admin_response: 'Kivizsgáltuk.', affected_items: [], history: [] },
  ]);
  await context.loadQualityComplaints();
  const html = get('#quality-complaints-list').innerHTML;
  assert.match(html, /&lt;script&gt;/);
  assert.match(html, /Nyitott/);
  assert.match(html, /Lezárt/);
  assert.match(html, /Kivizsgáltuk/);
  assert.equal((html.match(/data-complaint-action="close"/g) || []).length, 1);
});
test('coordinator cannot load admin complaint UI', async () => {
  const { context } = setup('coordinator', []);
  context.api = () => { throw Error('Unauthorized fetch'); };
  await context.loadQualityComplaints();
});
