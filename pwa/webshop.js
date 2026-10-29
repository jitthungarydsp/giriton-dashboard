/* Webshop UI: no demo products; prices are rechecked by the order transaction. */
window.JittWebshop = (() => {
  let env, root, owner = '', state;
  const labels = { received: 'Beérkezett', processing: 'Feldolgozás alatt', ready: 'Átvehető', fulfilled: 'Teljesítve', rejected: 'Elutasított', withdrawn: 'Visszavont' };
  const money = n => `${Number(n || 0).toLocaleString('hu-HU')} Ft`;
  const esc = value => env.escapeHtml(String(value ?? ''));
  const admin = () => ['admin', 'superadmin'].includes(String(env.getUser()?.role || '').toLowerCase());
  const key = () => `jitt-webshop-cart:${owner}`;
  const total = items => items.reduce((sum, item) => sum + item.price_huf * item.quantity, 0);
  const count = () => state.cart.reduce((sum, item) => sum + item.quantity, 0);
  const q = selector => root.querySelector(selector);
  const uuid = value => /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(value || '');
  function saveCart() {
    try { localStorage.setItem(key(), JSON.stringify({ items: state.cart, requestKey: state.requestKey, note: state.note })); } catch (_) { /* Memory basket still works. */ }
  }
  function resetOwner() {
    const user = env.getUser();
    const next = String(user?.courierId || user?.username || '');
    if (owner === next && state) return;
    owner = next;
    state = { products: [], attributes: [], cart: [], requestKey: crypto.randomUUID(), note: '', tab: 'products', mode: 'courier', query: '', category: '', orders: [], orderOffset: 0, orderStatus: 'all', loading: false, saving: false, error: '', message: '', sequence: 0 };
    try {
      const stored = JSON.parse(localStorage.getItem(key()) || '{}');
      if (Array.isArray(stored.items)) state.cart = stored.items.slice(0, 50).filter(i => uuid(i.variant_id) && typeof i.name === 'string' && Number.isInteger(i.quantity) && i.quantity > 0 && i.quantity <= 99 && Number.isInteger(i.price_huf) && i.price_huf >= 0);
      if (uuid(stored.requestKey)) state.requestKey = stored.requestKey;
      state.note = String(stored.note || '').slice(0, 2000);
    } catch (_) { /* Ignore invalid local drafts. */ }
  }
  function dirty() { state.requestKey = crypto.randomUUID(); saveCart(); }
  function status(value) { return `<span class="ws-badge ${value === 'received' ? 'waiting' : ''}">${esc(labels[value] || value)}</span>`; }
  function variantLabel(v) { return [v.size, v.type, ...Object.entries(v.attributes || {}).map(([name, value]) => `${name}: ${value}`)].filter(Boolean).join(' · '); }
  async function load() {
    resetOwner();
    const current = state;
    const sequence = ++state.sequence;
    state.loading = true; state.error = ''; render();
    try {
      if (state.tab === 'orders') {
        const result = await env.api(`/api/webshop/requests?admin=${state.mode === 'admin'}&offset=${state.orderOffset}&status=${state.orderStatus}`);
        if (current !== state || sequence !== state.sequence) return;
        state.orders = result.items; state.moreOrders = result.hasMore;
      } else {
        const result = await env.api(`/api/webshop/products?admin=${state.mode === 'admin'}`);
        if (current !== state || sequence !== state.sequence) return;
        state.products = result.items; state.attributes = result.attributes; state.moreProducts = result.hasMore;
      }
    } catch (error) { if (current === state && sequence === state.sequence) state.error = error.message; }
    finally { if (current === state && sequence === state.sequence) { state.loading = false; render(); } }
  }
  function catalog() {
    const products = state.products.filter(p => (!state.category || p.category === state.category) && [p.name, ...(p.variants || []).map(v => v.sku)].join(' ').toLocaleLowerCase('hu').includes(state.query.toLocaleLowerCase('hu')));
    return `<div class="ws-filters"><input data-ws-search aria-label="Termék keresése" placeholder="Termék neve vagy cikkszáma…" value="${esc(state.query)}"><select data-ws-category aria-label="Kategória"><option value="">Minden kategória</option>${[...new Set(state.products.map(p => p.category).filter(Boolean))].map(c => `<option value="${esc(c)}" ${state.category === c ? 'selected' : ''}>${esc(c)}</option>`).join('')}</select></div>
    <div class="ws-products">${products.map(p => {
      const variants = (p.variants || []).filter(v => v.active);
      const first = variants[0];
      return `<article class="ws-product" data-ws-product="${esc(p.id)}"><div class="ws-photo">${p.image_url ? `<img src="${esc(p.image_url)}" alt="${esc(p.name)}" loading="lazy">` : '<span>Termékkép feltöltés alatt</span>'}</div><div class="ws-product-body"><small class="ws-category">${esc(p.category)}</small><h3>${esc(p.name)}</h3><p class="ws-description">${esc(p.description)}</p>
      ${state.mode === 'admin' ? `<div class="ws-row"><strong class="ws-price">${money(first?.price_huf)}</strong><span class="ws-badge ${p.active ? '' : 'waiting'}">${p.active ? 'Aktív' : 'Inaktív'}</span></div><p class="muted">${variants.length} rendelhető változat</p><button type="button" class="secondary" data-ws-edit="${esc(p.id)}">Szerkesztés</button>` : `<label>Változat — méret és típus<select data-ws-variant>${variants.map(v => `<option value="${esc(v.id)}">${esc(variantLabel(v))}</option>`).join('')}</select></label><p class="ws-sku" data-ws-sku>${esc(first?.sku || '')}</p><strong class="ws-price" data-ws-price>${money(first?.price_huf)}</strong><button type="button" data-ws-add="${esc(p.id)}" ${!first ? 'disabled' : ''}>Kosárba</button>`}</div></article>`;
    }).join('') || `<div class="empty-card">${state.products.length ? 'Nincs a keresésnek megfelelő termék.' : 'Még nincs felvett termék.'}</div>`}</div>
    ${state.moreProducts ? '<button type="button" class="secondary" data-ws-more-products>További termékek</button>' : ''}
    ${state.mode === 'courier' ? `<div class="ws-cartbar"><div><strong>${count()} termék a kosárban</strong><p>Ellenőrizd a méreteket és a típusokat beküldés előtt.</p></div><strong class="ws-price">${money(total(state.cart))}</strong><button type="button" data-ws-tab="cart">Kosár megnyitása</button></div>` : ''}`;
  }
  function basket() {
    if (!state.cart.length) return '<div class="empty-card">A kosarad még üres. A terméklistából adhatsz hozzá felszerelést.</div>';
    return `<section class="ws-surface"><h3>Kosár ellenőrzése</h3>${state.cart.map((i, index) => `<div class="ws-cart-item"><div><strong>${esc(i.name)}</strong><small>${esc(variantLabel(i))}</small><small>${esc(i.sku)} · ${money(i.price_huf)} / db</small></div><label>Darab<input type="number" min="1" max="99" value="${i.quantity}" data-ws-quantity="${index}"></label><strong>${money(i.price_huf * i.quantity)}</strong><button class="secondary" type="button" data-ws-remove="${index}" aria-label="${esc(i.name)} törlése">×</button></div>`).join('')}
    <div class="ws-total">Összesen <strong>${money(total(state.cart))}</strong></div><label>Megjegyzés<textarea maxlength="2000" data-ws-note placeholder="Például: BUD2-ben szeretném átvenni.">${esc(state.note)}</textarea></label><p class="notice">Az igény adminisztrátori feldolgozásra kerül. Beküldéskor nincs online fizetés.</p><div class="ws-actions"><button type="button" class="secondary" data-ws-reprice>Árak és elérhetőség frissítése</button><button type="button" data-ws-submit ${env.preview() ? 'disabled' : ''}>Igény elküldése · ${money(total(state.cart))}</button></div>${env.preview() ? '<p class="muted">Admin előnézetből nem küldhető igény a futár nevében.</p>' : ''}</section>`;
  }
  function orders() {
    return `<label>Státusz<select data-ws-order-filter><option value="all">Összes</option>${Object.entries(labels).map(([v, text]) => `<option value="${v}" ${state.orderStatus === v ? 'selected' : ''}>${text}</option>`).join('')}</select></label>${state.orders.map(o => `<details class="ws-order"><summary><div><strong>Igény #${esc(o.id.slice(0, 8).toUpperCase())}</strong><small>${state.mode === 'admin' ? `${esc(o.courier_name)} · #${esc(o.courier_id)} · ` : ''}${esc(new Date(o.created_at).toLocaleString('hu-HU'))}</small></div><div class="ws-row"><strong>${money(o.total_huf)}</strong>${status(o.status)}</div></summary><div class="ws-order-body">${o.items.map(i => `<div class="ws-minirow"><div><strong>${esc(i.product_name)}</strong><p>${esc(variantLabel(i))} · ${i.quantity} db</p><small>${esc(i.sku)} · ${money(i.unit_price_huf)} / db</small></div><strong>${money(i.unit_price_huf * i.quantity)}</strong></div>`).join('')}<p class="ws-description">Megjegyzés: ${esc(o.note || '—')}</p>${o.admin_response ? `<div class="notice ws-description"><strong>Admin válasza</strong><p>${esc(o.admin_response)}</p></div>` : ''}
    <details><summary>Előzmények</summary>${(o.events || []).sort((a,b) => a.created_at.localeCompare(b.created_at)).map(e => `<p class="ws-description">${esc(new Date(e.created_at).toLocaleString('hu-HU'))} · ${esc(labels[e.status] || e.status)}<br>${esc(e.message)}</p>`).join('')}</details>
    ${state.mode === 'admin' && !['fulfilled', 'rejected', 'withdrawn'].includes(o.status) ? `<div class="ws-formgrid"><label>Státusz<select data-ws-order-status="${esc(o.id)}">${({received:['received','processing','ready','rejected'],processing:['processing','ready','rejected'],ready:['ready','fulfilled','rejected']}[o.status] || []).map(v => `<option value="${v}">${labels[v]}</option>`).join('')}</select></label><label>Válasz a futárnak<textarea maxlength="5000" data-ws-order-reply="${esc(o.id)}">${esc(o.admin_response)}</textarea></label></div><button type="button" data-ws-save-order="${esc(o.id)}">Változások mentése</button>` : ''}
    ${state.mode === 'courier' && o.status === 'received' ? `<button type="button" class="secondary" data-ws-withdraw="${esc(o.id)}">Igény visszavonása</button>` : ''}<p data-ws-order-message role="status"></p></div></details>`).join('') || '<div class="empty-card">Nincs ilyen státuszú igény.</div>'}<div class="ws-actions"><button type="button" class="secondary" data-ws-prev ${state.orderOffset === 0 ? 'disabled' : ''}>Előző</button><button type="button" class="secondary" data-ws-next ${!state.moreOrders ? 'disabled' : ''}>Következő</button></div>`;
  }
  function attributes() {
    return `<div class="ws-row"><h3>Tulajdonságok és értékek</h3><button type="button" data-ws-new-attribute>+ Új tulajdonság</button></div>${state.attributes.map(a => `<section class="ws-surface"><h3>${esc(a.name)}</h3><div class="source-row">${a.values.map(v => `<span class="source">${esc(v)}</span>`).join('')}</div><p class="muted">${a.required ? 'Kötelező minden termékváltozatnál' : 'Opcionális'}</p><button type="button" class="secondary" data-ws-edit-attribute="${esc(a.id)}">Értékek szerkesztése / bővítése</button></section>`).join('')}`;
  }
  function render() {
    const tabs = state.mode === 'admin' ? [['products', 'Termékek'], ['orders', 'Beérkezett igények'], ['attributes', 'Tulajdonságok']] : [['products', 'Termékek'], ['cart', `Kosár (${count()})`], ['orders', 'Saját igényeim']];
    root.innerHTML = `<section class="section-heading"><div><p class="eyebrow">${state.mode === 'admin' ? 'ADMINISZTRÁCIÓ' : 'FELSZERELÉS'}</p><h2>${state.mode === 'admin' ? 'Webshop kezelése' : 'Webshop'}</h2><p class="muted">${state.mode === 'admin' ? 'Termékek, tulajdonságok és beérkezett igények.' : 'Minden, amire a munkádhoz szükséged lehet.'}</p></div><div class="ws-actions"><button type="button" class="secondary" data-ws-refresh>Frissítés</button>${admin() ? `<button type="button" class="secondary" data-ws-mode>${state.mode === 'admin' ? 'Futárnézet' : 'Admin kezelőfelület'}</button>` : ''}</div></section><nav class="ws-tabs" aria-label="Webshop nézetek">${tabs.map(([value, text]) => `<button type="button" class="${state.tab === value ? 'active' : 'secondary'}" data-ws-tab="${value}" aria-pressed="${state.tab === value}">${text}</button>`).join('')}${state.mode === 'admin' && state.tab === 'products' ? '<button type="button" data-ws-new-product>+ Új termék</button>' : ''}</nav><p data-ws-message role="status" aria-live="polite" class="${state.error ? 'notice error' : 'muted'}">${esc(state.error || state.message)}</p><div data-ws-body>${state.loading ? '<div class="notice">Webshop betöltése…</div>' : state.error ? '<div class="empty-card">A webshop adatai nem érhetők el. Próbáld újra a Frissítés gombbal.</div>' : state.tab === 'products' ? catalog() : state.tab === 'cart' ? basket() : state.tab === 'orders' ? orders() : attributes()}</div>`;
    bind();
  }
  function variantRow(v = {}) {
    return `<div class="ws-variant-row" data-ws-variant-row data-id="${esc(v.id || '')}"><div class="ws-formgrid"><label>Cikkszám<input maxlength="100" data-v-sku value="${esc(v.sku || '')}" required></label><label>Egységár (Ft)<input type="number" min="0" max="10000000" step="1" data-v-price value="${v.price_huf ?? ''}" required></label><label>Méret<input maxlength="100" data-v-size value="${esc(v.size || '')}" placeholder="M / Univerzális" required></label><label>Típus<input maxlength="100" data-v-type value="${esc(v.type || '')}" placeholder="Rövid ujjú / Normál" required></label>${state.attributes.map(a => `<label>${esc(a.name)}${a.required ? ' *' : ''}<select data-v-attribute="${esc(a.name)}" ${a.required ? 'required' : ''}><option value="">Nincs megadva</option>${a.values.map(value => `<option value="${esc(value)}" ${(v.attributes || {})[a.name] === value ? 'selected' : ''}>${esc(value)}</option>`).join('')}</select></label>`).join('')}</div><button type="button" class="text-button" data-ws-remove-variant>Változat eltávolítása</button></div>`;
  }
  function editProduct(id) {
    const p = state.products.find(item => item.id === id) || { name: '', description: '', category: '', active: true, variants: [] };
    const body = q('[data-ws-body]');
    body.innerHTML = `<form class="ws-surface" data-ws-product-form><h3>${id ? 'Termék szerkesztése' : 'Új termék'}</h3><div class="ws-formgrid"><label>Termék neve<input data-p-name maxlength="200" required value="${esc(p.name)}"></label><label>Kategória<input data-p-category maxlength="100" value="${esc(p.category)}"></label><label class="ws-full">Leírás<textarea data-p-description maxlength="5000">${esc(p.description)}</textarea></label><label>Termékkép<input data-p-photo type="file" accept="image/jpeg,image/png,image/webp"></label><label class="checkbox-line"><input type="checkbox" data-p-active ${p.active ? 'checked' : ''}> Igényelhető termék</label></div><h4>Rendelhető változatok</h4><p class="muted">Minden méret–típus kombinációnak saját cikkszáma és ára van. Ahol nincs méret, használd az „Univerzális” értéket.</p><div data-ws-variants>${(p.variants.filter(v => v.active).length ? p.variants.filter(v => v.active) : [{}]).map(variantRow).join('')}</div><button type="button" class="secondary" data-ws-add-variant>+ Új változat</button><p data-ws-form-message role="status"></p><div class="ws-actions"><button type="button" class="secondary" data-ws-cancel>Mégsem</button><button type="submit">Termék mentése</button></div></form>`;
    const form = body.querySelector('form');
    form.querySelector('[data-ws-add-variant]').onclick = () => form.querySelector('[data-ws-variants]').insertAdjacentHTML('beforeend', variantRow());
    form.addEventListener('click', event => { if (event.target.closest('[data-ws-remove-variant]')) event.target.closest('[data-ws-variant-row]').remove(); });
    form.querySelector('[data-ws-cancel]').onclick = render;
    form.onsubmit = async event => {
      event.preventDefault();
      const variants = [...form.querySelectorAll('[data-ws-variant-row]')].map(row => ({ id: row.dataset.id || null, sku: row.querySelector('[data-v-sku]').value.trim(), price_huf: Number(row.querySelector('[data-v-price]').value), size: row.querySelector('[data-v-size]').value.trim(), type: row.querySelector('[data-v-type]').value.trim(), attributes: Object.fromEntries([...row.querySelectorAll('[data-v-attribute]')].filter(el => el.value).map(el => [el.dataset.vAttribute, el.value])) }));
      if (!variants.length) { form.querySelector('[data-ws-form-message]').textContent = 'Legalább egy változat szükséges.'; return; }
      const photo = form.querySelector('[data-p-photo]').files[0];
      if (photo?.size > 8 * 1024 * 1024) { form.querySelector('[data-ws-form-message]').textContent = 'A termékkép legfeljebb 8 MB lehet.'; return; }
      if (state.saving) return;
      state.saving = true;
      const values = { id: id || null, name: form.querySelector('[data-p-name]').value, description: form.querySelector('[data-p-description]').value, category: form.querySelector('[data-p-category]').value, active: form.querySelector('[data-p-active]').checked, variants };
      const controls = form.querySelectorAll('button'); controls.forEach(b => b.disabled = true);
      let savedId = '';
      try {
        const result = await env.api('/api/webshop/products', { method: 'POST', body: JSON.stringify(values) });
        if (!result.ok || !uuid(result.id)) throw Error('A termék mentése nem igazolható.');
        savedId = result.id;
        if (photo) {
          const data = new FormData(); data.append('photo', photo);
          await env.api(`/api/webshop/products/${result.id}/photo`, { method: 'POST', body: data });
        }
        state.message = 'A terméket elmentettük.'; await load();
      } catch (error) {
        if (savedId) {
          // Keep the saved product ID for retrying a failed photo upload.
          id = savedId;
          const rows = await env.api(`/api/webshop/products?admin=true&product_id=${savedId}`).catch(() => null);
          const saved = rows?.items.find(item => item.id === savedId);
          if (saved) [...form.querySelectorAll('[data-ws-variant-row]')].forEach(row => { row.dataset.id = saved.variants.find(v => v.sku === row.querySelector('[data-v-sku]').value.trim())?.id || ''; });
        }
        form.querySelector('[data-ws-form-message]').textContent = `${savedId ? 'A termék elmentve, a képfeltöltés nem sikerült. ' : ''}${error.message}`;
        controls.forEach(b => b.disabled = false);
      } finally { state.saving = false; }
    };
  }
  function editAttribute(id) {
    const a = state.attributes.find(item => item.id === id) || { name: '', values: [], required: false };
    q('[data-ws-body]').innerHTML = `<form class="ws-surface" data-ws-attribute-form><h3>${id ? 'Értékek szerkesztése' : 'Új tulajdonság'}</h3><label>Név<input maxlength="100" name="name" required value="${esc(a.name)}" ${id ? 'readonly' : ''}></label><label>Választható értékek — soronként egy<textarea name="values" required>${esc(a.values.join('\n'))}</textarea></label><label class="checkbox-line"><input name="required" type="checkbox" ${a.required ? 'checked' : ''}> Minden termékváltozatnál kötelező</label><p data-ws-form-message role="status"></p><div class="ws-actions"><button type="button" class="secondary" data-ws-cancel>Mégsem</button><button type="submit">Mentés</button></div></form>`;
    const form = q('[data-ws-attribute-form]'); form.querySelector('[data-ws-cancel]').onclick = render;
    form.onsubmit = async event => {
      event.preventDefault(); if (state.saving) return; state.saving = true;
      try {
        const result = await env.api('/api/webshop/attributes', { method: 'POST', body: JSON.stringify({ id: id || null, name: form.elements.name.value.trim(), values: form.elements.values.value.split('\n'), required: form.elements.required.checked }) });
        if (!result.ok) throw Error('A mentés nem igazolható.');
        state.message = 'A tulajdonságot elmentettük.'; await load();
      } catch (error) { form.querySelector('[data-ws-form-message]').textContent = error.message; }
      finally { state.saving = false; }
    };
  }
  async function submitOrder() {
    if (env.preview() || state.saving) return;
    const current = state;
    state.saving = true;
    q('[data-ws-submit]').disabled = true;
    try {
      const result = await env.api('/api/webshop/requests', { method: 'POST', body: JSON.stringify({ request_key: state.requestKey, note: state.note, items: state.cart.map(i => ({ variant_id: i.variant_id, quantity: i.quantity, expected_price_huf: i.price_huf })) }) });
      if (current !== state) return;
      if (!result.ok || !uuid(result.id)) throw Error('Az igény mentése nem igazolható.');
      state.cart = []; state.note = ''; state.requestKey = crypto.randomUUID(); saveCart();
      state.tab = 'orders'; state.orderOffset = 0; state.orderStatus = 'all';
      state.message = `Igényedet elmentettük: #${result.id.slice(0, 8).toUpperCase()}.`; await load();
    } catch (error) { if (current === state) { state.error = ''; state.message = `${error.message} A kosarad megmaradt.`; render(); } }
    finally { current.saving = false; }
  }
  async function reprice() {
    state.message = ''; state.error = '';
    try {
      // Fetch the specific basket IDs so products on later catalog pages are included.
      const data = await env.api('/api/webshop/basket', { method: 'POST', body: JSON.stringify({ ids: state.cart.map(i => i.variant_id) }) });
      const items = [];
      for (const old of state.cart) {
        const v = data.items.find(item => item.id === old.variant_id);
        if (!v) { state.message += `${old.name} már nem igényelhető; eltávolítottuk. `; continue; }
        items.push({ ...old, name: v.product.name, sku: v.sku, size: v.size, type: v.type, attributes: v.attributes, price_huf: v.price_huf });
      }
      state.cart = items; dirty(); state.message += 'Az árak és az elérhetőség frissült. Ellenőrizd a végösszeget, majd küldd el az igényt.'; render();
    } catch (error) { q('[data-ws-message]').textContent = error.message; }
  }
  function bind() {
    root.querySelectorAll('[data-ws-tab]').forEach(b => b.onclick = () => { if (state.saving) return; state.tab = b.dataset.wsTab; state.message = ''; state.error = ''; if (state.tab === 'cart') render(); else load(); });
    q('[data-ws-refresh]').onclick = load;
    q('[data-ws-mode]')?.addEventListener('click', () => { if (state.saving) return; state.mode = state.mode === 'admin' ? 'courier' : 'admin'; state.tab = 'products'; state.message = ''; state.orderOffset = 0; load(); });
    q('[data-ws-new-product]')?.addEventListener('click', () => editProduct(''));
    root.querySelectorAll('[data-ws-edit]').forEach(b => b.onclick = () => editProduct(b.dataset.wsEdit));
    root.querySelectorAll('[data-ws-new-attribute]').forEach(b => b.onclick = () => editAttribute(''));
    root.querySelectorAll('[data-ws-edit-attribute]').forEach(b => b.onclick = () => editAttribute(b.dataset.wsEditAttribute));
    q('[data-ws-search]')?.addEventListener('input', e => { state.query = e.target.value; const position = e.target.selectionStart; render(); q('[data-ws-search]').focus(); q('[data-ws-search]').setSelectionRange(position, position); });
    q('[data-ws-category]')?.addEventListener('change', e => { state.category = e.target.value; render(); });
    root.querySelectorAll('[data-ws-variant]').forEach(el => el.onchange = () => { const card = el.closest('[data-ws-product]'), p = state.products.find(item => item.id === card.dataset.wsProduct), v = p.variants.find(item => item.id === el.value); card.querySelector('[data-ws-sku]').textContent = v.sku; card.querySelector('[data-ws-price]').textContent = money(v.price_huf); });
    root.querySelectorAll('[data-ws-add]').forEach(b => b.onclick = () => {
      const p = state.products.find(item => item.id === b.dataset.wsAdd), id = b.closest('[data-ws-product]').querySelector('select').value, v = p.variants.find(item => item.id === id), existing = state.cart.find(item => item.variant_id === id);
      if (!v || (!existing && state.cart.length >= 50) || existing?.quantity >= 99) { state.message = 'A kosár legfeljebb 50 tételt, tételenként 99 darabot tartalmazhat.'; render(); return; }
      if (existing) existing.quantity++; else state.cart.push({ variant_id: v.id, name: p.name, sku: v.sku, size: v.size, type: v.type, attributes: v.attributes, price_huf: v.price_huf, quantity: 1 });
      dirty(); state.message = `${p.name} a kosárba került.`; render();
    });
    root.querySelectorAll('[data-ws-quantity]').forEach(el => el.onchange = () => { if (state.saving) return; state.cart[Number(el.dataset.wsQuantity)].quantity = Math.max(1, Math.min(99, Math.trunc(Number(el.value) || 1))); dirty(); render(); });
    root.querySelectorAll('[data-ws-remove]').forEach(b => b.onclick = () => { if (state.saving) return; state.cart.splice(Number(b.dataset.wsRemove), 1); dirty(); render(); });
    q('[data-ws-note]')?.addEventListener('input', e => { state.note = e.target.value; saveCart(); });
    q('[data-ws-submit]')?.addEventListener('click', submitOrder);
    q('[data-ws-reprice]')?.addEventListener('click', reprice);
    q('[data-ws-order-filter]')?.addEventListener('change', e => { state.orderStatus = e.target.value; state.orderOffset = 0; load(); });
    q('[data-ws-prev]')?.addEventListener('click', () => { state.orderOffset = Math.max(0, state.orderOffset - 50); load(); });
    q('[data-ws-next]')?.addEventListener('click', () => { state.orderOffset += 50; load(); });
    root.querySelectorAll('[data-ws-save-order], [data-ws-withdraw]').forEach(b => b.onclick = async () => {
      if (state.saving) return;
      const id = b.dataset.wsSaveOrder || b.dataset.wsWithdraw, body = b.closest('.ws-order-body'), error = body.querySelector('[data-ws-order-message]');
      const values = b.dataset.wsSaveOrder ? { status: body.querySelector('[data-ws-order-status]').value, response: body.querySelector('[data-ws-order-reply]').value.trim() } : null;
      if (values?.status === 'rejected' && values.response.length < 5) { error.textContent = 'Elutasításhoz legalább 5 karakteres indoklás szükséges.'; return; }
      state.saving = true; b.disabled = true;
      try { const result = await env.api(`/api/webshop/requests/${id}/${values ? 'actions' : 'withdraw'}`, { method: 'POST', ...(values ? { body: JSON.stringify(values) } : {}) }); if (!result.ok) throw Error('A mentés nem igazolható.'); state.message = 'Az igény frissült.'; await load(); }
      catch (err) { error.textContent = err.message; b.disabled = false; }
      finally { state.saving = false; }
    });
    q('[data-ws-more-products]')?.addEventListener('click', async e => {
      const button = e.currentTarget; button.disabled = true;
      const sequence = state.sequence;
      try { const result = await env.api(`/api/webshop/products?admin=${state.mode === 'admin'}&offset=${state.products.length}`); if (sequence !== state.sequence) return; state.products.push(...result.items); state.moreProducts = result.hasMore; render(); }
      catch (error) { q('[data-ws-message]').textContent = error.message; button.disabled = false; }
    });
  }
  return { mount(options) { env = options; root = document.querySelector('#webshop-content'); }, load };
})();
