const assert = require("assert");
const fs = require("fs");
const source = fs.readFileSync("pwa/app.js", "utf8");

function extract(startName, endName) {
  const start = source.indexOf(`function ${startName}(`);
  const end = source.indexOf(`function ${endName}(`, start);
  assert(start >= 0 && end > start, `${startName} source not found`);
  return source.slice(start, end);
}

const state = {
  workflow: {
    settlementAcceptanceEnabled: false,
    viewerReadOnly: false,
    financialBreakdown: { available: true, cards: [], complaints: {} },
  },
  workflowMonth: "2026-10",
};
const escapeHtml = String;
const formatHuf = (value) => `${value || 0} Ft`;
const renderFinancialSnapshotRestore = () => "";
const renderFinancialCardActions = () => "";
const financialDetailRows = () => "";
const qualityDetailAttributes = () => "";
const qualityDetailsPlaceholder = () => "";
const hasOpenComplaint = () => false;
const complaintList = () => "";
const financialComplaintOptions = () => "";
const documentList = () => "";

eval(extract("renderFinancialBreakdown", "financialEditorPayload"));
eval(extract("renderLegacySettlementDocumentPanel", "renderLegacyTigDocumentPanel"));

let html = renderFinancialBreakdown(false, false, false);
assert(!html.includes('id="accept-settlement"'));
assert(html.includes("csak áttekinthető"));
html = renderLegacySettlementDocumentPanel([{ id: "document" }], [], false, false, false, false);
assert(!html.includes('id="accept-settlement"'));

state.workflow.settlementAcceptanceEnabled = true;
html = renderFinancialBreakdown(false, false, false);
assert(html.includes('id="accept-settlement"'));
html = renderLegacySettlementDocumentPanel([{ id: "document" }], [], false, false, false, false);
assert(html.includes('id="accept-settlement"'));

console.log("settlement visibility tests passed");
