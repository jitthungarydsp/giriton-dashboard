import fs from "node:fs/promises";
import path from "node:path";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const outputDir = "C:/Giriton/giriton-dashboard/outputs/shift-template-mapping";
const outputPath = path.join(outputDir, "bud1-bud2-shift-templatek.xlsx");

const sources = [
  {
    hub: "BUD1",
    path: "C:/Users/GurzóBalázs/.codex/attachments/da3d9ac5-acb5-4c55-a283-9fed190a2f45/Beillesztett szöveg.txt",
  },
  {
    hub: "BUD2",
    path: "C:/Users/GurzóBalázs/.codex/attachments/639cdd58-32a5-4953-b69e-cfc419847211/Beillesztett szöveg.txt",
  },
];

function time5(value) {
  if (!value) return "";
  return String(value).slice(0, 5);
}

function endTime(value) {
  if (!value) return "";
  return String(value).slice(-8, -3);
}

function dateOnly(value) {
  return value ? String(value).slice(0, 10) : "";
}

function shiftLabel(row) {
  return `${time5(row.slotFrom)}-${endTime(row.occupancyTo)}`;
}

function freePlaces(row) {
  return Number(row.opened || 0) - Number(row.assigned || 0);
}

function dedupeTemplates(hub, rows) {
  const byTemplate = new Map();
  for (const row of rows) {
    const templateId = row.shiftTemplateId;
    if (!byTemplate.has(templateId)) {
      byTemplate.set(templateId, {
        hub,
        shiftTemplateId: templateId,
        readableShift: shiftLabel(row),
        slotFrom: time5(row.slotFrom),
        slotTo: time5(row.slotTo),
        occupancyFrom: String(row.occupancyFrom || ""),
        occupancyTo: String(row.occupancyTo || ""),
        plannedEnd: endTime(row.occupancyTo),
        warehouseId: row.warehouseId,
        layerId: row.layerId,
        dspCompanyId: row.dspCompanyId,
        sampleBlockKey: row.blockKey,
        sourceDates: new Set(),
        sampleCount: 0,
      });
    }
    const item = byTemplate.get(templateId);
    item.sourceDates.add(row.date);
    item.sampleCount += 1;
  }
  return [...byTemplate.values()]
    .map((row) => ({ ...row, sourceDates: [...row.sourceDates].sort().join(", ") }))
    .sort((a, b) => a.slotFrom.localeCompare(b.slotFrom) || a.shiftTemplateId - b.shiftTemplateId);
}

function rawRows(hub, rows) {
  return rows
    .map((row) => ({
      hub,
      date: row.date,
      blockKey: row.blockKey,
      shiftTemplateId: row.shiftTemplateId,
      readableShift: shiftLabel(row),
      slotFrom: time5(row.slotFrom),
      slotTo: time5(row.slotTo),
      occupancyFrom: row.occupancyFrom,
      occupancyTo: row.occupancyTo,
      status: row.status,
      assigned: Number(row.assigned || 0),
      opened: Number(row.opened || 0),
      freePlaces: freePlaces(row),
      capacityPublished: Boolean(row.capacityPublished),
      subscribeLocked: Boolean(row.subscribeLocked),
      warehouseId: row.warehouseId,
      layerId: row.layerId,
      dspCompanyId: row.dspCompanyId,
      subscribedCouriers: (row.assignments || [])
        .map((assignment) => assignment?.courier?.name)
        .filter(Boolean)
        .join(", "),
    }))
    .sort((a, b) => (
      a.hub.localeCompare(b.hub)
      || String(a.date).localeCompare(String(b.date))
      || a.slotFrom.localeCompare(b.slotFrom)
      || Number(a.shiftTemplateId) - Number(b.shiftTemplateId)
    ));
}

function writeMatrix(sheet, startRow, startCol, rows) {
  if (!rows.length) return;
  const headers = Object.keys(rows[0]);
  const matrix = [
    headers,
    ...rows.map((row) => headers.map((header) => row[header] ?? "")),
  ];
  sheet.getRangeByIndexes(startRow, startCol, matrix.length, headers.length).values = matrix;
  const used = sheet.getRangeByIndexes(startRow, startCol, matrix.length, headers.length);
  used.format.font = { name: "Arial", size: 10 };
  sheet.getRangeByIndexes(startRow, startCol, 1, headers.length).format.font = { color: "#000000", bold: true, name: "Arial", size: 10 };
  used.format.autofitColumns();
  sheet.getRangeByIndexes(startRow, startCol, matrix.length, headers.length).format.rowHeight = 18;
  for (let column = startCol; column < startCol + headers.length; column += 1) {
    const header = headers[column - startCol];
    if (header.toLowerCase().includes("blockkey")) {
      sheet.getRangeByIndexes(startRow, column, matrix.length, 1).format.columnWidth = 28;
    } else if (header.toLowerCase().includes("warehouselayerdsp")) {
      sheet.getRangeByIndexes(startRow, column, matrix.length, 1).format.columnWidth = 16;
    } else if (header.toLowerCase().includes("readableshift")) {
      sheet.getRangeByIndexes(startRow, column, matrix.length, 1).format.columnWidth = 14;
    }
  }
}

function renameRows(rows, mapping) {
  return rows.map((row) => Object.fromEntries(
    Object.entries(mapping).map(([sourceKey, label]) => [label, row[sourceKey] ?? ""])
  ));
}

function setTitle(sheet, title, subtitle = "") {
  sheet.showGridLines = false;
  sheet.getRange("A2").values = [[title]];
  sheet.getRange("A2").format.font = { name: "Arial", size: 14, bold: true };
  if (subtitle) {
    sheet.getRange("A3").values = [[subtitle]];
    sheet.getRange("A3").format.font = { name: "Arial", size: 10, italic: true, color: "#666666" };
  }
}

const loaded = [];
for (const source of sources) {
  const text = await fs.readFile(source.path, "utf8");
  loaded.push({ ...source, rows: JSON.parse(text) });
}

const templatesByHub = Object.fromEntries(
  loaded.map((source) => [source.hub, dedupeTemplates(source.hub, source.rows)])
);
const allRawRows = loaded.flatMap((source) => rawRows(source.hub, source.rows));

const byShift = new Map();
for (const hub of Object.keys(templatesByHub)) {
  for (const row of templatesByHub[hub]) {
    if (!byShift.has(row.readableShift)) {
      byShift.set(row.readableShift, {
        readableShift: row.readableShift,
        slotFrom: row.slotFrom,
        plannedEnd: row.plannedEnd,
        bud1TemplateId: "",
        bud1BlockKey: "",
        bud1WarehouseLayerDsp: "",
        bud2TemplateId: "",
        bud2BlockKey: "",
        bud2WarehouseLayerDsp: "",
        note: "",
      });
    }
    const item = byShift.get(row.readableShift);
    const prefix = hub.toLowerCase();
    item[`${prefix}TemplateId`] = row.shiftTemplateId;
    item[`${prefix}BlockKey`] = row.sampleBlockKey;
    item[`${prefix}WarehouseLayerDsp`] = `${row.warehouseId}/${row.layerId}/${row.dspCompanyId}`;
  }
}
const summaryRows = [...byShift.values()]
  .map((row) => ({
    ...row,
    note: row.bud1TemplateId && row.bud2TemplateId ? "" : "Csak az egyik raktár mintájában szerepel",
  }))
  .sort((a, b) => a.slotFrom.localeCompare(b.slotFrom) || a.readableShift.localeCompare(b.readableShift));

const summaryDisplayRows = renameRows(summaryRows, {
  readableShift: "Műszak",
  slotFrom: "Kezdés",
  plannedEnd: "Vége",
  bud1TemplateId: "BUD1 template",
  bud1BlockKey: "BUD1 blockKey",
  bud1WarehouseLayerDsp: "BUD1 wh/layer/dsp",
  bud2TemplateId: "BUD2 template",
  bud2BlockKey: "BUD2 blockKey",
  bud2WarehouseLayerDsp: "BUD2 wh/layer/dsp",
  note: "Megjegyzés",
});

const templateDisplayMapping = {
  readableShift: "Műszak",
  shiftTemplateId: "Template ID",
  slotFrom: "Kezdés",
  plannedEnd: "Vége",
  sampleBlockKey: "Minta blockKey",
  warehouseId: "warehouseId",
  layerId: "layerId",
  dspCompanyId: "dspCompanyId",
  sourceDates: "Forrás dátumok",
  sampleCount: "Sorok száma",
};

const workbook = Workbook.create();

const summary = workbook.worksheets.add("Összesítő");
setTitle(summary, "BUD1 és BUD2 műszak template lista", "A JSON mintákból kinyert template ID-k és olvasható műszakok.");
writeMatrix(summary, 4, 0, summaryDisplayRows);
summary.freezePanes.freezeRows(5);
summary.tabColor = "#1F4E78";

const bud1 = workbook.worksheets.add("BUD1 templatek");
setTitle(bud1, "BUD1 templatek", "Forrás: warehouseId=8791, layerId=1, dspCompanyId=47.");
writeMatrix(bud1, 4, 0, renameRows(templatesByHub.BUD1, templateDisplayMapping));
bud1.freezePanes.freezeRows(5);

const bud2 = workbook.worksheets.add("BUD2 templatek");
setTitle(bud2, "BUD2 templatek", "Forrás: warehouseId=13000, layerId=4, dspCompanyId=17.");
writeMatrix(bud2, 4, 0, renameRows(templatesByHub.BUD2, templateDisplayMapping));
bud2.freezePanes.freezeRows(5);

const raw = workbook.worksheets.add("Forrás sorok");
setTitle(raw, "Forrás sorok", "A JSON minták teljes blokklistája, a kapacitás és hozzárendelt futárok mezőkkel.");
writeMatrix(raw, 4, 0, allRawRows);
raw.freezePanes.freezeRows(5);

workbook.recalculate();

const check = await workbook.inspect({
  kind: "table",
  sheetId: "Összesítő",
  range: "A5:J20",
  include: "values",
  tableMaxRows: 16,
  tableMaxCols: 10,
});
console.log(check.ndjson);

const errors = await workbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!",
  options: { useRegex: true, maxResults: 100 },
  summary: "final formula error scan",
});
console.log(errors.ndjson);

const preview = await workbook.render({ sheetName: "Összesítő", range: "A1:J25", scale: 1, format: "png" });
await fs.writeFile(path.join(outputDir, "preview.png"), new Uint8Array(await preview.arrayBuffer()));

await fs.mkdir(outputDir, { recursive: true });
const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(outputPath);
console.log(`OUTPUT=${outputPath}`);
