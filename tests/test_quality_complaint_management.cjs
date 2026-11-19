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

test('three incoming types show up in compact rows and reveal the JITT identifier', async () => {
  const {context,get} = setup('admin', [
    {id:'a',topic:'noShow',status:'open',courier_name:'Futár',jitt_internal_id:'1000000000001234'},
    {id:'b',topic:'uncleanedTimeWindowLate',status:'open'},
    {id:'c',topic:'uncleanedTimeWindowLate',status:'open',affected_items:[{signalKind:'route'}]},
  ]);
  await context.loadQualityComplaints();
  const html = get('#quality-complaints-list').innerHTML;
  assert.equal((html.match(/name="quality-inbox"/g)||[]).length,3);
  for (const text of ['No-show','Címkésési panasz','Menet közben','1000000000001234']) assert.ok(html.includes(text));
});

const runtime = require('node:path').join(require('node:os').homedir(),'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
test('forward keeps edited text and records status only after the admin confirms', {skip:!fs.existsSync(runtime)}, async () => {
  const {chromium} = require(runtime);
  const browser = await chromium.launch({channel:'chrome',headless:true});
  try {
    const page = await browser.newPage({viewport:{width:390,height:844}});
    await page.route('http://localhost/', route => route.fulfill({contentType:'text/html',body:'<meta name="viewport" content="width=device-width,initial-scale=1">'}));
    await page.goto('http://localhost/');
    await page.evaluate(() => {
      window.escapeHtml = value => String(value || '');
      window.qualityComplaintCategories = () => ['Műszak'];
      window.state = {};
      window.requests = [];
      window.loadQualityComplaints = async () => {};
      window.popup = {location:{replace:url => {popup.url=url;}},close:() => {popup.closed=true;}};
      window.open = () => popup;
      const base = {courier_name:'Futár',courier_id:'1234',category:'Műszak',description:'Eredeti szöveg',license_plate:'',route_id:''};
      window.api = async (path, options) => {
        const body = options?.body ? JSON.parse(options.body) : null;
        requests.push({path,body});
        if (path.endsWith('/actions')) return {ok:true};
        if (path.endsWith('/evidence')) return {formDefaults:{}};
        return {formPayload:{...base,...body}};
      };
      window.qualityComplaintFormUrlFromPayload = ({description}) => 'https://docs.google.com/forms/test/viewform?text='+encodeURIComponent(description);
    });
    await page.addScriptTag({content:source.slice(source.indexOf('async function openQualityInboxAction('),source.indexOf('function showQualitySubmissionProgress('))});
    await page.evaluate(() => openQualityInboxAction({id:'a',courier_name:'Futár',courier_id:'1234'},'forward'));
    await page.locator('[data-inbox-description]').fill('Szerkesztett szöveg');
    await page.getByRole('button',{name:'Google-űrlap megnyitása'}).click();
    assert.match(await page.evaluate(() => decodeURIComponent(popup.url)), /Szerkesztett szöveg/);
    assert.equal(await page.evaluate(() => requests.filter(r=>r.path.endsWith('/actions')).length),0);
    await page.getByRole('button',{name:'Beküldtem a Google-űrlapot'}).click();
    await page.waitForFunction(() => popup.closed && !document.querySelector('dialog'));
    assert.equal(await page.evaluate(() => requests.find(r=>r.path.endsWith('/actions')).body.action),'forward');
  } finally { await browser.close(); }
});
