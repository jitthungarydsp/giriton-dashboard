const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const root = path.join(__dirname, '..');
const runtime = path.join(require('node:os').homedir(), '.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');

async function setup(browser, configured) {
  const page = await browser.newPage({viewport:{width:390,height:844}});
  await page.route('http://localhost/', r => r.fulfill({contentType:'text/html',body:`<meta name="viewport" content="width=device-width,initial-scale=1"><style>${fs.readFileSync(path.join(root,'pwa/styles.css'),'utf8')}</style><div id="gate-content"></div>`}));
  await page.goto('http://localhost/');
  await page.evaluate(configured => {
    window.calls = [];
    window.configured = configured;
    window.api = async (url, options) => {
      if (url === '/api/admin/gate') return {configured:window.configured,cooldownSeconds:0};
      calls.push({url,options});
      return new Promise((resolve,reject) => {window.complete=resolve;window.fail=reject;});
    };
  }, configured);
  await page.addScriptTag({path:path.join(root,'pwa/gate.js')});
  await page.evaluate(() => JittGate.mount(document.querySelector('#gate-content'),{api}));
  return page;
}

test('gate waits in modal, prevents repeated clicks and reports only accepted calls', {skip:!fs.existsSync(runtime)}, async () => {
  const browser = await require(runtime).chromium.launch({channel:'chrome',headless:true});
  try {
    const page = await setup(browser,true);
    await page.locator('[data-gate-open]').click();
    await page.evaluate(() => document.querySelector('[data-gate-open]').click());
    assert.equal(await page.evaluate(() => calls.length),1);
    const request = await page.evaluate(() => JSON.parse(calls[0].options.body));
    assert.match(request.request_id,/^[a-f0-9-]{36}$/);
    assert.deepEqual(Object.keys(request),['request_id']);
    await page.keyboard.press('Escape');
    assert.equal(await page.locator('.gate-dialog').evaluate(el=>el.open),true);
    await page.evaluate(() => complete({ok:true,callSid:'CA123',cooldownSeconds:60}));
    await page.getByText('Híváskérés elküldve',{exact:true}).waitFor();
    assert.match(await page.locator('.gate-dialog p').textContent(),/helyszínen/);
    await page.getByRole('button',{name:'Rendben',exact:true}).click();
    assert.equal(await page.locator('[data-gate-open]').isDisabled(),true);
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
  } finally {await browser.close();}
});

test('unconfigured gate stays disabled; uncertain failure does not silently retry', {skip:!fs.existsSync(runtime)}, async () => {
  const browser = await require(runtime).chromium.launch({channel:'chrome',headless:true});
  try {
    const page = await setup(browser,false);
    assert.equal(await page.locator('[data-gate-open]').isDisabled(),true);
    await page.evaluate(()=>window.configured=true);
    await page.locator('[data-gate-refresh]').click();
    await page.locator('[data-gate-open]').click();
    await page.evaluate(()=>fail(new Error('Hálózati hiba')));
    await page.getByText('A hívás nem igazolható vissza',{exact:true}).waitFor();
    assert.equal(await page.evaluate(()=>calls.length),1);
    assert.match(await page.locator('.gate-dialog p').textContent(),/Twilio hívásnaplót/);
  } finally {await browser.close();}
});
