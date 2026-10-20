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

function render(flags, options = {}) {
  const panel = { innerHTML: "" };
  const context = {
    state: { settlementDashboardStatusFilter: options.filter || "", settlementDashboard: { month: "2026-09", summary: options.summary || {}, rows: options.rows || [
      { courierId: "6686", courierName: "Teszt Futár", flags },
    ] } },
    $: () => panel, escapeHtml: String, formatMonthLabel: String,
    shortDateTime: () => "", formatHuf: String, formatCount: String,
    renderOpsSummary: () => { throw new Error("Duplicate summary cards must not render"); },
    renderSettlementDashboardFlags: () => "", renderSettlementDashboardStatus: () => "",
    renderDashboardInvoiceIssue: () => "", renderSettlementDashboardExpanded: () => "",
  };
  vm.runInNewContext(functionSource("settlementImportRuleText") + "\n" +
    functionSource("settlementDashboardStatusOptions") + "\n" + functionSource("renderSettlementStatusFilters") + "\n" +
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

test("overview counts match row statuses and include payment waiting", () => {
  const rows = [
    { courierId: "1", courierName: "Fizetett A", status: { label: "Kifizetve" } },
    { courierId: "2", courierName: "Fizetett B", status: { label: "Kifizetve" } },
    { courierId: "3", courierName: "Fizetésre váró", status: { label: "Kifizetésre vár" } },
  ];
  for (const filter of ["", "Kifizetve"]) {
    const html = render([], {rows, filter, summary: {statusCounts: {"Kifizetve": 99}}});
    assert.match(html, /data-settlement-status-filter="Kifizetve"[^>]*>[\s\S]*?<small>2 db<\/small>/);
    assert.match(html, /data-settlement-status-filter="Kifizetésre vár"[^>]*>[\s\S]*?<small>1 db<\/small>/);
    assert.doesNotMatch(html, /99 db|Nincs felső státuszszűrés/);
    assert.equal((html.match(/class="settlement-dashboard-row\s/g) || []).length, filter ? 2 : 3);
  }
});
