const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const test = require("node:test");
const source = fs.readFileSync(require("node:path").join(__dirname, "../pwa/app.js"), "utf8");
const context = { escapeHtml: String };
vm.runInNewContext(source.slice(source.indexOf("function qualityShiftTimes("), source.indexOf("function renderQualitySummaryDetails(")), context);
test("separate labels show Budapest queue time and attendance clock", () => {
  const html = context.qualityShiftTimes({ giritonLoginAt: "08:39", queueStartedAt: "2026-10-13T07:01:00Z" }, "lateShift");
  assert.match(html, /Giriton-bejelentkezés: 08:39/);
  assert.match(html, /Sorba állás: 09:01/);
});
test("missing events are explicit and unrelated quality topics are unchanged", () => {
  assert.equal((context.qualityShiftTimes({}, "lateShift").match(/Nincs adat/g) || []).length, 2);
  assert.equal(context.qualityShiftTimes({}, "noShow"), "");
});
