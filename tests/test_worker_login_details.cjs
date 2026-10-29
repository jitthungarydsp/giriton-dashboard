const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const test = require('node:test');
const source = fs.readFileSync(require('node:path').join(__dirname, '../pwa/app.js'), 'utf8');
const context = { detailRow: (label, value) => `${label}: ${value}`, timelineTime: value => value || '-', minutesText: String, renderTimeline: () => '' };
vm.runInNewContext(source.slice(source.indexOf('function renderWorkerLoginDetails('), source.indexOf('function ensureWorkerSignalDialog(')), context);
test('Giriton login and queue event remain separate', () => {
  const html = context.renderWorkerLoginDetails({ giritonLoginTime: '04:21', queueEventAt: '04:28' });
  assert.match(html, /Giriton-bejelentkezés: 04:21/);
  assert.match(html, /Sorba állt: 04:28/);
});
test('missing Giriton login is explicit and never inferred from queue', () => {
  const html = context.renderWorkerLoginDetails({ queueEventAt: '04:28' });
  assert.match(html, /Giriton-bejelentkezés: Nincs adat/);
});
