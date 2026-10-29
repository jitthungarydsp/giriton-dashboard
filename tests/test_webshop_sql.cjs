const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const runtime = process.env.PGLITE_TEST_RUNTIME || path.join(__dirname, '../tmp/webshop-test-runtime/package');
test('webshop migration, authoritative pricing, snapshots, retries, status transitions and permissions', { skip: !fs.existsSync(runtime) }, async () => {
  const { PGlite } = require(runtime);
  const db = new PGlite();
  try {
    await db.exec('create role anon; create role authenticated; create role service_role bypassrls;');
    const migration = fs.readFileSync(path.join(__dirname, '../sql/pwa_webshop.sql'), 'utf8');
    await db.exec(migration);
    await db.exec(migration); // Re-running the migration must preserve data and functions.
    const product = { name: 'Futárpóló', description: 'Minta', category: 'Ruházat', active: true };
    const variant = { sku: 'POLO-M', price_huf: 4500, size: 'M', type: 'Rövid ujjú', attributes: { Szín: 'Zöld' } };
    const save = async (p, variants) => (await db.query('select public.pwa_save_webshop_product($1::jsonb,$2::jsonb) as id', [JSON.stringify(p), JSON.stringify(variants)])).rows[0].id;
    const pid = await save(product, [variant]);
    const vid = (await db.query('select id from webshop_variants where product_id=$1', [pid])).rows[0].id;
    const items = [{ variant_id: vid, quantity: 2, expected_price_huf: 4500 }];
    const create = async (key, courier='6498', values=items) => (await db.query('select public.pwa_create_webshop_request($1,$2,$3,$4,$5::jsonb) as id', [key, courier, 'Futár', 'BUD2', JSON.stringify(values)])).rows[0].id;
    const key = crypto.randomUUID();
    const rid = await create(key);
    assert.equal(await create(key), rid);
    assert.equal(Number((await db.query('select total_huf from webshop_requests where id=$1',[rid])).rows[0].total_huf), 9000);
    await save({ ...product, id: pid }, [{ ...variant, id: vid, price_huf: 5000 }]);
    assert.equal((await db.query('select unit_price_huf from webshop_request_items where request_id=$1',[rid])).rows[0].unit_price_huf, 4500);
    await assert.rejects(create(crypto.randomUUID()), /Megváltozott az ár/);
    await assert.rejects(create(crypto.randomUUID(), '6498', [...items, ...items]), /Ismétlődő/);
    assert.equal((await db.query('select count(*)::int as n from webshop_requests')).rows[0].n, 1);
    await assert.rejects(save({ ...product, name: 'Duplicate' }, [variant]), /unique/i);
    assert.equal((await db.query('select count(*)::int as n from webshop_products')).rows[0].n, 1);
    const manage = (status, response='') => db.query('select * from public.pwa_manage_webshop_request($1,$2,$3,$4)',[rid,status,response,'admin']);
    await assert.rejects(manage('fulfilled'), /Nem megengedett/);
    await assert.rejects(manage('rejected'), /indoklás/);
    await manage('processing', 'Feldolgozzuk.'); await manage('ready', 'Átvehető BUD2-ben.'); await manage('fulfilled', 'Átadva.');
    await assert.rejects(manage('ready'), /lezárt/);
    assert.equal((await db.query('select count(*)::int as n from webshop_request_events where request_id=$1',[rid])).rows[0].n, 4);
    const second = await create(crypto.randomUUID(), '7440', [{...items[0], expected_price_huf:5000}]);
    await assert.rejects(db.query('select * from public.pwa_withdraw_webshop_request($1,$2)',[second,'6498']), /nem található/);
    await db.query('select * from public.pwa_withdraw_webshop_request($1,$2)',[second,'7440']);
    assert.equal((await db.query('select status from webshop_requests where id=$1',[second])).rows[0].status,'withdrawn');
    const attr = (await db.query("select public.pwa_save_webshop_attribute($1::jsonb) as id",[JSON.stringify({name:'Szín',values:['Zöld','Fekete'],required:false})])).rows[0].id;
    await assert.rejects(db.query('select public.pwa_save_webshop_attribute($1::jsonb)',[JSON.stringify({id:attr,name:'Szín',values:['Fekete'],required:false})]), /nem törölhető/);
    await save({ ...product, id: pid, active: false }, [{ ...variant, id: vid, price_huf: 5000 }]);
    await assert.rejects(create(crypto.randomUUID(),'6498',[{...items[0],expected_price_huf:5000}]), /nem igényelhető/);
    assert.equal((await db.query("select has_table_privilege('anon','webshop_requests','select') as ok")).rows[0].ok,false);
    assert.equal((await db.query("select has_function_privilege('authenticated','pwa_create_webshop_request(uuid,text,text,text,jsonb)','execute') as ok")).rows[0].ok,false);
  } finally { await db.close(); }
});
