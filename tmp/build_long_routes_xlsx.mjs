import fs from "node:fs/promises";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const root = "C:/Giriton/giriton-dashboard";
const data = JSON.parse(await fs.readFile(`${root}/tmp/long-routes-aug-sep-2026.json`, "utf8"));
const outputDir = `${root}/outputs/long-routes-aug-sep-2026`;
await fs.mkdir(outputDir, { recursive: true });
const workbook = Workbook.create();
const sheet = workbook.worksheets.add("Route ID lista");
sheet.showGridLines = false;
sheet.tabColor = "#1B5E3A";
const font = "Arial";

sheet.getRange("A1:N1").merge();
sheet.getRange("A1").values = [["5 óra 1 percnél hosszabb túrák · 2026. augusztus–szeptember"]];
sheet.getRange("A1:N1").format = { font: { name: font, size: 15, bold: true, color: "#173126" }, verticalAlignment: "center" };
sheet.getRange("A2:N2").merge();
sheet.getRange("A2").values = [["Csak konkrét Route ID-k. A teljes idő bepakolással együtt értendő, a regionális túrák kizárva."]];
sheet.getRange("A2:N2").format = { font: { name: font, size: 10, italic: true, color: "#56665C" }, wrapText: true };

const headers = ["Dátum", "Route ID", "Futár ID", "Futár", "Raktár", "Túra típus", "Indulás", "Visszaérkezés", "Bepakolás perc", "Túraidő perc", "Teljes idő perc", "Teljes idő óra:perc", "Rendelések", "Címek"];
const rows = data.rows.map((r) => [
  new Date(`${r.dátum}T00:00:00`), r.route_id, r.futár_id, r.futár, r.raktár, r.túra_típus,
  r.indulás, r.visszaérkezés, r.bepakolás_perc, r.túraidő_perc, r.összes_idő_perc, r.összes_idő_óra_perc,
  r.rendelések, r.címek,
]);
const start = 4;
sheet.getRange(`A${start}:N${start + rows.length}`).values = [headers, ...rows];
sheet.getRange(`A${start}:N${start}`).format = { fill: "#173126", font: { name: font, size: 10, bold: true, color: "#FFFFFF" }, horizontalAlignment: "center", verticalAlignment: "center", wrapText: true };
sheet.getRange(`A${start + 1}:N${start + rows.length}`).format = { font: { name: font, size: 10, color: "#1F2D25" }, verticalAlignment: "center" };
sheet.getRange(`A${start + 1}:A${start + rows.length}`).format.numberFormat = "yyyy-mm-dd";
sheet.getRange(`B${start + 1}:C${start + rows.length}`).format.numberFormat = "0";
sheet.getRange(`I${start + 1}:K${start + rows.length}`).format.numberFormat = "0";
sheet.getRange(`M${start + 1}:N${start + rows.length}`).format.numberFormat = "0";
sheet.getRange(`A${start}:N${start + rows.length}`).format.borders = { preset: "all", style: "thin", color: "#D7E2DA" };
sheet.tables.add(`A${start}:N${start + rows.length}`, true, "LongRouteDetailsOver330");
sheet.freezePanes.freezeRows(start);
sheet.getRange(`A1:N${start + rows.length}`).format.font = { name: font };
sheet.getRange(`A1:N${start + rows.length}`).format.verticalAlignment = "center";
sheet.getRange(`A1:N${start + rows.length}`).format.autofitColumns();
[12, 12, 12, 26, 12, 16, 19, 19, 16, 15, 16, 22, 12, 10].forEach((width, index) => { sheet.getRangeByIndexes(0, index, 1, 1).format.columnWidth = width; });
sheet.getRange("A1:N2").format.rowHeight = 24;
sheet.getRange(`A${start}:N${start}`).format.rowHeight = 34;

workbook.recalculate();
const inspect = await workbook.inspect({ kind: "table", sheetId: "Route ID lista", range: `A1:N${Math.min(start + rows.length, start + 10)}`, include: "values,formulas", tableMaxRows: 14, tableMaxCols: 14, maxChars: 12000 });
console.log(inspect.ndjson);
const preview = await workbook.render({ sheetName: "Route ID lista", range: `A1:N${Math.min(start + rows.length, start + 18)}`, scale: 1, format: "png" });
await fs.writeFile(`${outputDir}/preview.png`, new Uint8Array(await preview.arrayBuffer()));
const xlsx = await SpreadsheetFile.exportXlsx(workbook);
await xlsx.save(`${outputDir}/hosszu-turak-5-01-felett.xlsx`);
console.log(JSON.stringify({ output: `${outputDir}/hosszu-turak-5-01-felett.xlsx`, routes: rows.length }));
