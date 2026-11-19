const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const test = require('node:test');
const source = fs.readFileSync(require('node:path').join(__dirname, '../pwa/app.js'), 'utf8');
function setup(role, items) {
  const nodes = new Map();
  const get = key => { if (!nodes.has(key)) nodes.set(key, { value: 'all', querySelectorAll: () => [] }); return nodes.get(key); };
  const context = { state: { user: { role } }, $: get, prepareQualityWorkspace: async () => true,
    escapeHtml: value => String(value || '').replaceAll('<', '&lt;').replaceAll('>', '&gt;'),
    shortDateTime: String, renderComplaintShiftDetails: () => '', api: async () => ({ items, canManage: true, hasMore: false }) };
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

test('one click saves approval before opening the validated form', async () => {
  const item = {id:'a', courier_name:'Futár', topic:'lateShift', status:'open'};
  const {context, get} = setup('admin', [item]);
  const events = [];
  const result = {};
  const tab = {location:{replace:url => events.push(['navigate',url])}};
  const inputs = new Map([
    ['[data-complaint-result]', result], ['[data-complaint-category]', {value:'Műszak'}],
    ['[data-complaint-route]', {value:'route'}], ['[data-complaint-plate]', {value:'ABC-123'}],
  ]);
  const card = {dataset:{complaintId:'a'},querySelector:selector => inputs.get(selector)};
  const button = {dataset:{complaintAction:'approve'},closest:() => card,
    addEventListener:(_, handler) => { button.click = handler; }};
  get('#quality-complaints-list').querySelectorAll = selector => selector === '[data-complaint-action]' ? [button] : [];
  context.window = {open:() => tab};
  const approved = {category:'Műszak',courier_id:'1234',courier_name:'Futár',description:'Mentett indoklás'};
  context.api = async (path, options) => {
    if (!options) return {items:[item],canManage:true,hasMore:false};
    events.push(['approve',path,JSON.parse(options.body)]);
    return {ok:true,formPayload:approved};
  };
  context.qualityComplaintFormUrlFromPayload = payload => {
    assert.equal(payload, approved);
    return 'https://docs.google.com/forms/test/viewform';
  };
  await context.loadQualityComplaints();
  await button.click();
  assert.deepEqual(events, [
    ['approve','/api/quality/complaints/a/prepare-form',{category:'Műszak',route_id:'route',license_plate:'ABC-123'}],
    ['navigate','https://docs.google.com/forms/test/viewform'],
  ]);
  assert.equal(tab.opener, null);
});
