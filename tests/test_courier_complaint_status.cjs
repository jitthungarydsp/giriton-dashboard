const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const test = require('node:test');
const source = fs.readFileSync(require('node:path').join(__dirname, '../pwa/app.js'), 'utf8');
function setup() {
  const node = {};
  const context = { state: { statistics: { month: '2026-10' }, user: {} }, $: () => node,
    URLSearchParams, encodeURIComponent, shortDateTime: String,
    escapeHtml: value => String(value || '').replaceAll('<', '&lt;').replaceAll('>', '&gt;') };
  vm.runInNewContext(source.slice(source.indexOf('function qualityComplaintStatus('), source.indexOf('async function loadQualityComplaints(')), context);
  vm.runInNewContext(source.slice(source.indexOf('function renderCourierQualityComplaints('), source.indexOf('function qualityShiftTimes(')), context);
  return { context, node };
}
test('all statuses, dates and escaped admin response shown inside monthly quality summary', () => {
  const { context } = setup();
  const html = context.renderCourierQualityComplaints({ qualityComplaints: [
    { id: 'a', topic: 'lateShift', status: 'open', created_at: '2026-10-29' },
    { id: 'b', topic: 'noShow', status: 'forwarded', forwarded_at: '2026-10-30' },
    { id: 'c', status: 'closed', closed_at: '2026-10-31', admin_response: '<script>Válasz</script>' },
  ] });
  for (const label of ['Nyitott', 'Továbbított', 'Lezárt', '2026-10-30', '2026-10-31', '&lt;script&gt;Válasz']) assert.ok(html.includes(label));
  assert.ok(!html.includes('data-complaint-action'));
});
test('load errors are distinct from no submitted complaint', () => {
  const { context } = setup();
  assert.match(context.renderCourierQualityComplaints({ qualityComplaintsError: true }), /nem sikerült lekérni/);
  assert.match(context.renderCourierQualityComplaints({ qualityComplaints: [] }), /nincs beküldött/);
});
test('an old month response cannot overwrite current month data', async () => {
  const { context, node } = setup();
  let resolve;
  context.api = () => new Promise(done => { resolve = done; });
  const pending = context.refreshCourierQualityComplaints();
  context.state.statistics = { month: '2026-11' };
  resolve({ items: [{ id: 'old' }] });
  await pending;
  assert.equal(context.state.statistics.qualityComplaints, undefined);
  assert.equal(node.innerHTML, undefined);
});
