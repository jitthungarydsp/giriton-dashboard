const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const test = require('node:test');
const runtime = process.env.PLAYWRIGHT_TEST_RUNTIME || path.join(os.homedir(), '.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
test('webshop basket, uncertain submission retry, admin editor and mobile layout', { skip: !fs.existsSync(runtime) }, async () => {
  const { chromium } = require(runtime);
  const browser = await chromium.launch({ channel:'chrome', headless:true });
  try {
    const page = await browser.newPage({ viewport:{width:760,height:1000} });
    const errors = [];
    page.on('pageerror', e => errors.push(e.message));
    const repo = path.join(__dirname,'..');
    await page.route('http://localhost/**', route => route.fulfill({ contentType:'text/html',body:`<style>${fs.readFileSync(path.join(repo,'pwa/styles.css'),'utf8')}${fs.readFileSync(path.join(repo,'pwa/webshop.css'),'utf8')}</style><main class="app-shell"><div id="webshop-content"></div></main>` }));
    await page.goto('http://localhost/');
    await page.addScriptTag({ path:path.join(repo,'pwa/webshop.js') });
    await page.evaluate(async () => {
      window.fixture = { user:{role:'courier',courierId:'6498',username:'Futár'},keys:[],failOnce:true,orders:[],attributes:[],products:[{id:'11111111-1111-4111-8111-111111111111',name:'Futárpóló',description:'Pamut póló.',category:'Ruházat',active:true,variants:[{id:'22222222-2222-4222-8222-222222222222',sku:'POLO-M',size:'M',type:'Rövid ujjú',price_huf:4500,attributes:{},active:true}]}] };
      const f=window.fixture;
      window.webshopEnv={getUser:()=>f.user,preview:()=>false,escapeHtml:s=>String(s).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('"','&quot;'),api:async (url,options={})=>{
        const data=options.body ? JSON.parse(options.body) : null;
        if(url==='/api/webshop/requests'&&options.method==='POST') {
          f.keys.push(data.request_key);
          if(!f.orders.length) f.orders=[{id:'33333333-3333-4333-8333-333333333333',courier_name:'Futár',courier_id:'6498',status:'received',created_at:'2026-10-29T08:00:00Z',total_huf:9000,note:data.note,items:[{product_name:'Futárpóló',size:'M',type:'Rövid ujjú',sku:'POLO-M',unit_price_huf:4500,quantity:2}],events:[]}];
          if(f.failOnce){f.failOnce=false;throw Error('Elveszett válasz.');}
          return {ok:true,id:f.orders[0].id};
        }
        if(url==='/api/webshop/products'&&options.method==='POST') {
          f.products.push({...data,id:'44444444-4444-4444-8444-444444444444',variants:data.variants.map(v=>({...v,id:crypto.randomUUID(),active:true}))});
          return {ok:true,id:'44444444-4444-4444-8444-444444444444'};
        }
        if(url.startsWith('/api/webshop/products'))return {items:f.products,attributes:f.attributes,hasMore:false};
        if(url.startsWith('/api/webshop/requests'))return {items:f.orders,hasMore:false};
        if(url==='/api/webshop/attributes') {f.attributes.push({...data,id:crypto.randomUUID()});return {ok:true};}
        throw Error('Unexpected API '+url);
      }};
      window.JittWebshop.mount(window.webshopEnv);await window.JittWebshop.load();
    });
    assert.equal(await page.locator('[data-ws-mode]').count(),0);
    await page.locator('[data-ws-add]').click();
    await page.locator('.ws-tabs [data-ws-tab="cart"]').click();
    await page.locator('[data-ws-quantity]').fill('2');
    await page.locator('[data-ws-quantity]').dispatchEvent('change');
    await page.locator('[data-ws-note]').fill('BUD2 átvétel');
    await page.locator('[data-ws-submit]').click();
    await page.waitForFunction(()=>document.querySelector('[data-ws-message]').textContent.includes('Elveszett'));
    assert.equal(await page.locator('[data-ws-quantity]').inputValue(),'2');
    await page.locator('[data-ws-submit]').click();
    await page.waitForSelector('.ws-order');
    const keys=await page.evaluate(()=>window.fixture.keys);
    assert.equal(keys.length,2); assert.equal(keys[0],keys[1]);
    assert.match(await page.locator('.ws-tabs').textContent(),/Kosár \(0\)/);
    await page.evaluate(async()=>{window.fixture.user={role:'admin',username:'Admin'};await window.JittWebshop.load();});
    await page.locator('[data-ws-mode]').click();
    await page.locator('[data-ws-new-product]').click();
    await page.locator('[data-p-name]').fill('Telefontartó');
    await page.locator('[data-v-sku]').fill('TARTO-1');
    await page.locator('[data-v-price]').fill('3900');
    await page.locator('[data-v-size]').fill('Univerzális');
    await page.locator('[data-v-type]').fill('Műszerfalra');
    await page.locator('[data-ws-product-form] button[type="submit"]').click();
    await page.waitForSelector('[data-ws-product="44444444-4444-4444-8444-444444444444"]');
    await page.locator('[data-ws-tab="attributes"]').click();
    await page.locator('[data-ws-new-attribute]').click();
    await page.locator('[data-ws-attribute-form] input[name="name"]').fill('Szín');
    await page.locator('[data-ws-attribute-form] textarea').fill('Zöld\nFekete\nKék');
    await page.locator('[data-ws-attribute-form] button[type="submit"]').click();
    await page.waitForSelector('[data-ws-edit-attribute]');
    await page.locator('[data-ws-tab="products"]').click();
    for(const width of [760,360,320]) {
      await page.setViewportSize({width,height:1000});
      assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,`Overflow ${width}`);
    }
    await page.screenshot({path:path.join(repo,'tmp/webshop-live-mobile.png'),fullPage:true});
    assert.deepEqual(errors,[]);
  } finally { await browser.close(); }
});
