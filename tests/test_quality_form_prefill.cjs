const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const context = vm.createContext({URL});
vm.runInContext(fs.readFileSync(require('node:path').join(__dirname, '../pwa/quality_form_test.js'), 'utf8'), context);
const complaint = {id:'complaint-1', courier_id:'1234', courier_name:'Árvíz & Teszt', message:'Saját indoklás & részletek?',
  affected_items:[{date:'2026-11-09', label:'Route 10', note:'15 perc'}]};
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
    const url = new URL(context.qualityComplaintFormUrl(complaint,category,'NEW-ROUTE','abc-123'));
    assert.equal(url.pathname.endsWith('/viewform'),true);
    assert.equal(url.searchParams.get('entry.493012323'),'Just in Time Kft.');
    if (id) {
      assert.equal(url.searchParams.get(`entry.${id}`),'1234');
      assert.equal(url.searchParams.get(`entry.${name}`),complaint.courier_name);
    }
    const text = url.searchParams.get(`entry.${description}`);
    for (const expected of ['complaint-1','2026-11-09',complaint.message,complaint.courier_name,'Route 10 · 15 perc']) assert.ok(text.includes(expected));
    if (category === 'Túra alatti késés') assert.equal(url.searchParams.get('entry.584723978'),'NEW-ROUTE');
    if (category === 'Jármű') assert.equal(url.searchParams.get('entry.1445819589'),'ABC-123');
  }
  assert.equal(JSON.stringify(complaint),before);
});
test('missing required fields and multiple dates prevent opening an incomplete form', () => {
  assert.throws(()=>context.qualityComplaintFormUrl(complaint,'Túra alatti késés'));
  assert.throws(()=>context.qualityComplaintFormUrl(complaint,'Jármű'));
  assert.throws(()=>context.qualityComplaintFormUrl(complaint,'invalid'));
  assert.throws(()=>context.qualityComplaintFormUrl({...complaint,courier_name:''},'Műszak'));
  assert.throws(()=>context.qualityComplaintFormUrl({...complaint,affected_items:[...complaint.affected_items,{date:'2026-11-10'}]},'Műszak'));
});
