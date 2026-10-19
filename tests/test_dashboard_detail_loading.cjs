const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const test = require("node:test");

const source = fs.readFileSync(path.join(__dirname, "../pwa/app.js"), "utf8");
const start = source.indexOf("const settlementDashboardDetailRequests = new Map();");
const end = source.indexOf("\nasync function loadSettlementDashboard()", start);

function fixture() {
  const calls = [];
  const state = {
    settlementDashboardMonth: "2026-09", settlementDashboardExpandedTab: "settlement",
    settlementDashboardDetailCache: {},
  };
  const context = { state, URLSearchParams, previousLocalMonth: () => "2026-09",
    renderSettlementDashboard() {},
    api(url) {
      return new Promise((resolve, reject) => calls.push({ url, resolve, reject }));
    },
  };
  vm.runInNewContext(source.slice(start, end) + "\nthis.loadDetail = loadSettlementDashboardCourierDetail;", context);
  return { state, calls, load: context.loadDetail };
}

test("repeated clicks share one API call and reuse the response", async () => {
  const { state, calls, load } = fixture();
  const first = load("8001");
  const second = load("8001");
  assert.equal(calls.length, 1);
  calls[0].resolve({ id: "saved", tigLoaded: false });
  await Promise.all([first, second]);
  await load("8001");
  assert.equal(calls.length, 1);
  assert.equal(state.settlementDashboardDetail.workflow.id, "saved");
});

test("a slow response for the previous courier cannot replace the selected one", async () => {
  const { state, calls, load } = fixture();
  const first = load("8001");
  const second = load("6686");
  calls[1].resolve({ id: "Csilla" });
  await second;
  calls[0].resolve({ id: "Brendon" });
  await first;
  assert.equal(state.settlementDashboardExpandedCourierId, "6686");
  assert.equal(state.settlementDashboardDetail.workflow.id, "Csilla");
  assert.equal(state.settlementDashboardDetailCache["2026-09:8001"].id, "Brendon");
});

test("late basic response cannot discard an already loaded TIG", async () => {
  const { state, calls, load } = fixture();
  const basic = load("8001");
  const tig = load("8001", { includeTig: true });
  assert.equal(calls.length, 2);
  calls[1].resolve({ id: "with-tig", tigLoaded: true });
  await tig;
  calls[0].resolve({ id: "basic", tigLoaded: false });
  await basic;
  assert.equal(state.settlementDashboardDetail.workflow.id, "with-tig");
});

test("failed requests can be retried", async () => {
  const { state, calls, load } = fixture();
  const first = load("8001");
  calls[0].reject(new Error("Network error"));
  await first;
  assert.equal(state.settlementDashboardDetail.error, "Network error");
  const retry = load("8001");
  assert.equal(calls.length, 2);
  calls[1].resolve({ id: "retried" });
  await retry;
  assert.equal(state.settlementDashboardDetail.workflow.id, "retried");
});
