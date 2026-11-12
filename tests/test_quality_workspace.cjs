const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../pwa/quality_workspace.js'),'utf8');
test('accent-free names, ID search and typed dated cards',()=>{
 const context={state:{qualityWorkspaceType:'noShow'},document:{addEventListener(){}}};
 vm.runInNewContext(source,context);
 assert.equal(context.qualityWorkspaceText('Ákos 8185'),'akos 8185');
 const days=context.qualityWorkspaceDays({days:[{date:'2026-10-01',items:[{category:'noShow'},{category:'lateShift'}]},{date:'2026-10-02',items:[{category:'lateShift'}]}]});
 assert.equal(days.length,1);assert.equal(days[0].date,'2026-10-01');assert.equal(days[0].items.length,1);
 context.state.qualityWorkspaceType='all';
 assert.equal(context.qualityWorkspaceDays({days:[{date:'2026-10-02',items:[{category:'lateShift'}]}]}).length,1);
});
