import fs from "node:fs/promises";
import path from "node:path";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const [inputPath, outputPath] = process.argv.slice(2);
if (!inputPath || !outputPath) {
  throw new Error("Usage: node tools/export_correction_report.mjs findings.json correction-report.xlsx");
}

const findings = JSON.parse(await fs.readFile(inputPath, "utf8"));
const workbook = Workbook.create();
const report = workbook.worksheets.add("Correction Report");
const data = workbook.worksheets.add("Audit Data");
for (const sheet of [report, data]) sheet.showGridLines = false;

const columns = ["Caseworker", "PTC", "Participant ID", "Program", "Finding Date", "Document", "Category", "Reported Error", "Recommended Correction", "Source"];
const rows = findings.map(finding => [
  finding.caseworker, finding.ptc, finding.participant_identifier, finding.program || "", finding.finding_date || "", finding.document,
  finding.category, finding.error, finding.recommendation, finding.source,
]);

report.mergeCells("A1:J1");
report.getRange("A1").values = [["Homesteader Correction Report"]];
report.getRange("A1:J1").format = {
  fill: "#0F766E", font: { bold: true, color: "#FFFFFF", size: 16 },
  horizontalAlignment: "center", verticalAlignment: "center",
};
report.getRange("A1:J1").format.rowHeight = 30;
report.getRange("A3:B4").values = [["Generated rows", findings.length], ["Scope", "Local evidence-backed audit findings"]];
report.getRange("A3:A4").format = { font: { bold: true }, fill: "#E6F4F1" };
report.getRange("A3:B4").format.borders = { preset: "outside", style: "thin", color: "#B8C9C4" };
report.getRange("A6:J6").values = [columns];
report.getRange("A6:J6").format = { fill: "#1E3A4C", font: { bold: true, color: "#FFFFFF" }, wrapText: true };
if (rows.length) report.getRange(`A7:J${rows.length + 6}`).values = rows;
report.getRange(`A6:J${Math.max(6, rows.length + 6)}`).format.wrapText = true;
report.getRange(`A6:J${Math.max(6, rows.length + 6)}`).format.borders = { preset: "insideHorizontal", style: "thin", color: "#D7E0DD" };
report.getRange(`A7:J${Math.max(7, rows.length + 6)}`).format.verticalAlignment = "top";
if (rows.length) report.getRange(`A7:J${rows.length + 6}`).format.rowHeight = 44;
const reportLastRow = Math.max(8, rows.length + 6);
const reportWidths = [18, 20, 18, 24, 16, 28, 20, 45, 55, 27];
for (const [index, width] of reportWidths.entries()) {
  const column = String.fromCharCode("A".charCodeAt(0) + index);
  report.getRange(`${column}1:${column}${reportLastRow}`).format.columnWidth = width;
}
report.freezePanes.freezeRows(6);
if (rows.length) {
  report.getRange(`G7:G${rows.length + 6}`).conditionalFormats.add("containsText", {
    text: "Identity", format: { fill: "#FDE68A", font: { color: "#854D0E" } },
  });
}

data.getRange("A1:J1").values = [columns];
data.getRange("A1:J1").format = { fill: "#1E3A4C", font: { bold: true, color: "#FFFFFF" } };
if (rows.length) data.getRange(`A2:J${rows.length + 1}`).values = rows;
data.getRange(`A1:J${Math.max(1, rows.length + 1)}`).format.wrapText = true;
data.getRange(`A1:J${Math.max(1, rows.length + 1)}`).format.autofitColumns();
if (rows.length) data.getRange(`A2:J${rows.length + 1}`).format.rowHeight = 44;
data.freezePanes.freezeRows(1);

await fs.mkdir(path.dirname(outputPath), { recursive: true });
const exported = await SpreadsheetFile.exportXlsx(workbook);
await exported.save(outputPath);

const check = await workbook.inspect({
  kind: "table",
  range: `Correction Report!A1:J${Math.max(8, rows.length + 6)}`,
  include: "values,formulas",
  tableMaxRows: 12,
  tableMaxCols: 10,
});
console.log(check.ndjson);
const preview = await workbook.render({ sheetName: "Correction Report", range: `A1:J${Math.max(8, rows.length + 6)}`, scale: 1.5 });
await fs.writeFile(`${outputPath}.preview.png`, new Uint8Array(await preview.arrayBuffer()));
