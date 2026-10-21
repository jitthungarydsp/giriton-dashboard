import fs from "node:fs/promises";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const root = "C:/Giriton/giriton-dashboard";
const data = JSON.parse(await fs.readFile(`${root}/tmp/giriton-september-work-time.json`, "utf8"));
const outputDir = `${root}/outputs/giriton-september`;
await fs.mkdir(outputDir, { recursive: true });

const workbook = Workbook.create();
const sheet = workbook.worksheets.add("Futáronként");
sheet.showGridLines = false;
sheet.tabColor = "#1B5E3A";
const font = "Arial";

sheet.getRange("A1:I1").merge();
sheet.getRange("A1").values = [["Giriton munkaidő lista · 2026. szeptember"]];
sheet.getRange("A1:I1").format = {
  font: { name: font, size: 15, bold: true, color: "#173126" },
  verticalAlignment: "center",
};
sheet.getRange("A2:I2").merge();
sheet.getRange("A2").values = [["A lista alapja a public.giriton_attendance_raw tábla. Hiányzó Giriton kijelentkezésnél a raktári visszaérkezés szerepel végidőként."]];
sheet.getRange("A2:I2").format = { font: { name: font, size: 10, italic: true, color: "#56665C" }, wrapText: true };

const summaryStart = 4;
const summaryHeaders = ["Futár", "Napok", "Ledolgozott napok", "Összes idő (óra)", "Összes idő (perc)", "Átlagos nap (perc)", "Raktári visszaérkezésből", "Hiányzó végidő", "Hiányzás"];
const summaryRows = data.summary.map((row) => [
  row.courier,
  row.days,
  row.worked_days,
  row.total_hours,
  row.total_minutes,
  row.average_minutes,
  row.fallback_days,
  row.missing_end_days,
  row.no_show_days,
]);
sheet.getRange(`A${summaryStart}:I${summaryStart + summaryRows.length}`).values = [summaryHeaders, ...summaryRows];
sheet.getRange(`A${summaryStart}:I${summaryStart}`).format = {
  fill: "#173126",
  font: { name: font, size: 10, bold: true, color: "#FFFFFF" },
  horizontalAlignment: "center",
  verticalAlignment: "center",
  wrapText: true,
};
sheet.getRange(`A${summaryStart + 1}:I${summaryStart + summaryRows.length}`).format = { font: { name: font, size: 10, color: "#1F2D25" }, verticalAlignment: "center" };
sheet.getRange(`B${summaryStart + 1}:I${summaryStart + summaryRows.length}`).format.horizontalAlignment = "right";
sheet.getRange(`D${summaryStart + 1}:F${summaryStart + summaryRows.length}`).format.numberFormat = "0.00";
sheet.getRange(`G${summaryStart + 1}:I${summaryStart + summaryRows.length}`).format.numberFormat = "0";
sheet.getRange(`A${summaryStart}:I${summaryStart + summaryRows.length}`).format.borders = { preset: "all", style: "thin", color: "#D7E2DA" };
sheet.tables.add(`A${summaryStart}:I${summaryStart + summaryRows.length}`, true, "CourierWorkTimeSummary");

const detailStart = summaryStart + summaryRows.length + 4;
const detailHeaders = ["Dátum", "Futár", "Státusz", "Műszak", "Kezdés", "Vége", "Ledolgozott perc", "Ledolgozott idő", "Végidő forrása"];
const detailRows = data.detail.map((row) => [
  new Date(`${row.date}T00:00:00`),
  row.courier,
  row.status,
  row.shift,
  row.start || null,
  row.end || null,
  row.worked_minutes,
  row.worked_minutes == null ? null : row.worked_minutes / 60,
  row.end_source,
]);
sheet.getRange(`A${detailStart}:I${detailStart + detailRows.length}`).values = [detailHeaders, ...detailRows];
sheet.getRange(`A${detailStart}:I${detailStart}`).format = {
  fill: "#2E6B4A",
  font: { name: font, size: 10, bold: true, color: "#FFFFFF" },
  horizontalAlignment: "center",
  verticalAlignment: "center",
  wrapText: true,
};
sheet.getRange(`A${detailStart + 1}:I${detailStart + detailRows.length}`).format = { font: { name: font, size: 10, color: "#1F2D25" }, verticalAlignment: "center" };
sheet.getRange(`A${detailStart + 1}:A${detailStart + detailRows.length}`).format.numberFormat = "yyyy-mm-dd";
sheet.getRange(`G${detailStart + 1}:G${detailStart + detailRows.length}`).format.numberFormat = "0";
sheet.getRange(`H${detailStart + 1}:H${detailStart + detailRows.length}`).format.numberFormat = "0.00";
sheet.getRange(`A${detailStart}:I${detailStart + detailRows.length}`).format.borders = { preset: "all", style: "thin", color: "#D7E2DA" };
sheet.tables.add(`A${detailStart}:I${detailStart + detailRows.length}`, true, "GiritonAttendanceWorkTime");

sheet.freezePanes.freezeRows(detailStart);
sheet.getRange(`A1:I${detailStart + detailRows.length}`).format.font = { name: font };
sheet.getRange(`A1:I${detailStart + detailRows.length}`).format.verticalAlignment = "center";
sheet.getRange(`A1:I${detailStart + detailRows.length}`).format.autofitColumns();
const widths = [24, 18, 18, 30, 12, 12, 18, 18, 25];
widths.forEach((width, index) => { sheet.getRangeByIndexes(0, index, 1, 1).format.columnWidth = width; });
sheet.getRange("A1:I2").format.rowHeight = 24;
sheet.getRange(`A${summaryStart}:I${summaryStart}`).format.rowHeight = 34;
sheet.getRange(`A${detailStart}:I${detailStart}`).format.rowHeight = 34;

workbook.recalculate();
const inspect = await workbook.inspect({ kind: "table", sheetId: "Futáronként", range: `A1:I${Math.min(detailStart + detailRows.length, detailStart + 8)}`, include: "values,formulas", tableMaxRows: 12, tableMaxCols: 9, maxChars: 12000 });
console.log(inspect.ndjson);
const preview = await workbook.render({ sheetName: "Futáronként", range: `A1:I${Math.min(detailStart + detailRows.length, detailStart + 20)}`, scale: 1, format: "png" });
await fs.writeFile(`${outputDir}/preview.png`, new Uint8Array(await preview.arrayBuffer()));
const xlsx = await SpreadsheetFile.exportXlsx(workbook);
await xlsx.save(`${outputDir}/giriton-szeptember-munkaido.xlsx`);
console.log(JSON.stringify({ output: `${outputDir}/giriton-szeptember-munkaido.xlsx`, summaryRows: summaryRows.length, detailRows: detailRows.length }));
