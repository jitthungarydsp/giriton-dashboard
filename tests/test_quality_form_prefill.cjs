const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const context = vm.createContext({URL});
vm.runInContext(fs.readFileSync(require('node:path').join(__dirname, '../pwa/quality_form_test.js'), 'utf8'), context);
const complaint = {courier_id:'1234', courier_name:'Árvíz & Teszt', route_id:'NEW-ROUTE', license_plate:'ABC-123',
  description:'JITT reklamáció: complaint-1\nDátum: 2026-11-09\nSaját indoklás & részletek?\nRoute 10 · 15 perc'};
const fields = {
  'Túra alatti késés':[1629541155,139333198,1757898114],
  'Futárbüntetés':[229683135,2026925449,727698089],
  'Pénztárca/tankolás':[1148502456,1198182622,688354749],
  'Elszámolás':[1609979400,275666129,949548968],
  'Jármű':[null,null,179972591],
  'Műszak':[871178890,1494998302,2121626944]
};
test('all category branches preserve complaint data and editable route/plate overrides without side effects', () => {
  const before = JSON.stringify(complaint);
  for (const [category,[id,name,description]] of Object.entries(fields)) {
    const url = new URL(context.qualityComplaintFormUrlFromPayload({...complaint,category}));
    assert.equal(url.pathname.endsWith('/viewform'),true);
    assert.equal(url.searchParams.get('entry.493012323'),'Just in Time Kft.');
    if (id) {
      assert.equal(url.searchParams.get(`entry.${id}`),'1234');
      assert.equal(url.searchParams.get(`entry.${name}`),complaint.courier_name);
    }
    assert.equal(url.searchParams.get(`entry.${description}`),complaint.description);
    if (category === 'Túra alatti késés') assert.equal(url.searchParams.get('entry.584723978'),'NEW-ROUTE');
    if (category === 'Jármű') assert.equal(url.searchParams.get('entry.1445819589'),'ABC-123');
  }
  assert.equal(JSON.stringify(complaint),before);
});
test('missing required fields prevent opening an incomplete form', () => {
  assert.throws(()=>context.qualityComplaintFormUrlFromPayload({...complaint,category:'Túra alatti késés',route_id:''}));
  assert.throws(()=>context.qualityComplaintFormUrlFromPayload({...complaint,category:'Jármű',license_plate:''}));
  assert.throws(()=>context.qualityComplaintFormUrlFromPayload({...complaint,category:'invalid'}));
  assert.throws(()=>context.qualityComplaintFormUrlFromPayload({...complaint,category:'Műszak',courier_name:''}));
});
