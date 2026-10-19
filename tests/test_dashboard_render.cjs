const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const test = require("node:test");

const source = fs.readFileSync(path.join(__dirname, "../pwa/app.js"), "utf8").replace(/\r\n/g, "\n");
function functionSource(name) {
  const start = source.indexOf(`function ${name}(`);
  assert.ok(start >= 0, `Missing ${name}`);
  return source.slice(start, source.indexOf("\n}\n", start) + 3);
}

function render(flags) {
  const panel = { innerHTML: "" };
  const context = {
    state: { settlementDashboard: { month: "2026-09", rows: [
      { courierId: "6686", courierName: "Teszt Futár", flags },
    ] } },
    $: () => panel, escapeHtml: String, formatMonthLabel: String,
    shortDateTime: () => "", formatHuf: String, formatCount: String,
    renderOpsSummary: () => "", renderSettlementStatusFilters: () => "",
    renderSettlementDashboardFlags: () => "", renderSettlementDashboardStatus: () => "",
    renderDashboardInvoiceIssue: () => "", renderSettlementDashboardExpanded: () => "",
  };
  vm.runInNewContext(functionSource("settlementImportRuleText") + "\n" +
    functionSource("renderSettlementDashboard") + "\nrenderSettlementDashboard();", context);
  return panel.innerHTML;
}

test("dashboard renders and highlights attention flags with Hungarian accents", () => {
  for (const label of ["Kiemelt figyelés", "KIEMELT FIGYELÉS", "kiemelt figyeles"]) {
    const html = render([{ label }]);
    assert.match(html, /settlement-dashboard-row\s+highlighted/);
    assert.match(html, /Teszt Futár/);
    assert.match(html, /data-courier-id="6686"/);
  }
});

test("ordinary, empty and missing flags do not highlight or break the dashboard", () => {
  for (const flags of [[{ label: "Reklamáció" }], [{}], [], undefined]) {
    const html = render(flags);
    assert.match(html, /Teszt Futár/);
    assert.doesNotMatch(html, /settlement-dashboard-row[^"\n]*highlighted/);
  }
});
