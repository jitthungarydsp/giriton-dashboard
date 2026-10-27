const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const test = require("node:test");
const source = fs.readFileSync(path.join(__dirname, "../pwa/app.js"), "utf8");
const start = source.indexOf("async function statisticsApi(");
const end = source.indexOf("\nasync function loadFinancialStatistics", start);
const tick = () => new Promise(setImmediate);

function fixture() {
  const calls = [], timers = [];
  const panel = { innerHTML: "" };
  const month = { value: "2026-10" };
  const state = { adminStatisticsMonth: month.value, adminStatisticsWarehouse: "all", adminStatisticsRequestSeq: 0 };
  const context = {
    state, URLSearchParams, AbortController,
    $: (selector) => selector === "#admin-statistics-month" ? month : panel,
    previousMonthValue: () => "2026-09",
    escapeHtml: (text) => text.replaceAll("<", "&lt;"),
    bindAdminStatisticsFilters() {},
    renderAdminStatisticsPanel: (current, previous, report) => `CURRENT:${current.month};PREVIOUS:${previous?.month || "missing"};REPORT:${report?.month || "missing"}`,
    setTimeout(fn, ms) { const timer = { fn, ms }; timers.push(timer); return timer; },
    clearTimeout(timer) { timer.cleared = true; },
    api(url, { signal }) {
      return new Promise((resolve, reject) => {
        calls.push({ url, resolve, reject });
        signal.addEventListener("abort", () => reject(new Error("aborted")), { once: true });
      });
    },
  };
  vm.runInNewContext(source.slice(start, end), context);
  return { calls, timers, panel, month, state, load: context.loadAdminStatistics };
}

test("current statistics appear while comparison and shift report are still pending", async () => {
  const f = fixture(); const done = f.load();
  f.calls[0].resolve({ month: "2026-10" }); await tick();
  assert.match(f.panel.innerHTML, /CURRENT:2026-10/);
  assert.match(f.panel.innerHTML, /Műszakfoglalás összevetése betöltése/);
  f.calls[1].resolve({ month: "2026-09" });
  f.calls[2].reject(new Error("report failed")); await done;
  assert.match(f.panel.innerHTML, /CURRENT:2026-10;PREVIOUS:2026-09/);
  assert.match(f.panel.innerHTML, /report failed/);
  assert.equal(f.state.adminStatistics.shiftReport, null);
});

test("a failed previous month does not hide current statistics or invent zero totals", async () => {
  const f = fixture(); const done = f.load();
  f.calls[1].reject(new Error("comparison failed"));
  f.calls[2].resolve({ month: "report" });
  f.calls[0].resolve({ month: "2026-10" }); await done;
  assert.match(f.panel.innerHTML, /CURRENT:2026-10;PREVIOUS:missing;REPORT:report/);
  assert.match(f.panel.innerHTML, /comparison failed/);
});

test("timed out requests leave a visible retry message and clear timers", async () => {
  const f = fixture(); const done = f.load();
  for (const timer of f.timers) { assert.equal(timer.ms, 30000); timer.fn(); }
  await done;
  assert.match(f.panel.innerHTML, /30 másodperces időkorlátot/);
  assert.doesNotMatch(f.panel.innerHTML, /betöltése/);
  assert.equal(f.state.adminStatistics, null);
  assert.ok(f.timers.every((timer) => timer.cleared));
});

test("responses from an older month cannot overwrite the latest selection", async () => {
  const f = fixture(); const first = f.load();
  f.month.value = "2026-08"; const second = f.load();
  f.calls.slice(3).forEach((call) => call.resolve({ month: "2026-08" })); await second;
  const latest = f.panel.innerHTML;
  f.calls.slice(0, 3).forEach((call) => call.resolve({ month: "2026-10" })); await first;
  assert.equal(f.panel.innerHTML, latest);
  assert.equal(f.state.adminStatistics.current.month, "2026-08");
});

test("missing comparison data is displayed as unavailable, while a real zero stays zero", () => {
  const card = source.slice(source.indexOf("function adminDonutCard("), source.indexOf("function adminMoneyDonutCard("));
  const context = { escapeHtml: String, formatCount: String, adminDelta: () => ({ text: "delta", className: "neutral" }) };
  vm.runInNewContext(card, context);
  assert.match(context.adminDonutCard("Összes kör", "", 15, undefined), /Összehasonlítás nem érhető el/);
  assert.match(context.adminDonutCard("Összes kör", "", 15, 0), /<b>0<\/b>/);
});
