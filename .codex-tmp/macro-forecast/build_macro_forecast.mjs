import fs from "node:fs/promises";
import path from "node:path";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const workspace = "/Users/cjwork/holodeck-archive";
const inputPath = path.join(workspace, "macro forecast.xlsx");
const outputDir = path.join(workspace, "outputs", "01a0a8d5-e41c-7cd1-8fca-c36962c30d1e");
const outputPath = path.join(outputDir, "macro-forecast-12-month.xlsx");
const previewDir = path.join(workspace, ".codex-tmp", "macro-forecast", "output-previews");

function colLetter(n) {
  let value = n;
  let result = "";
  while (value > 0) {
    const remainder = (value - 1) % 26;
    result = String.fromCharCode(65 + remainder) + result;
    value = Math.floor((value - 1) / 26);
  }
  return result;
}

function addMonths(year, month, amount) {
  const date = new Date(Date.UTC(year, month - 1 + amount, 1));
  return {
    year: date.getUTCFullYear(),
    month: date.getUTCMonth() + 1,
  };
}

const workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(inputPath));
const sheet = workbook.worksheets.getItem("macro forecast");

const lastActualCol = "AQ";
const firstForecastColNumber = 44;
const forecastMonths = 12;
const lastForecastCol = colLetter(firstForecastColNumber + forecastMonths - 1);

const lastHeader = String(sheet.getRange(`${lastActualCol}1`).values[0][0]);
const [lastYear, lastMonth] = lastHeader.split("-").map(Number);
const forecastHeaders = [];
for (let monthIndex = 1; monthIndex <= forecastMonths; monthIndex += 1) {
  const next = addMonths(lastYear, lastMonth, monthIndex);
  forecastHeaders.push(`${next.year}-${String(next.month).padStart(2, "0")}`);
}
sheet.getRange(`AR1:${lastForecastCol}1`).values = [forecastHeaders];

const continuousRows = [2, 3, 4, 5, 6, 7, 9, 10, 12, 13, 14, 15, 16, 17];
for (const row of continuousRows) {
  const trend = `AVERAGE($AQ${row}-$AP${row},$AP${row}-$AO${row},$AO${row}-$AN${row},$AN${row}-$AM${row},$AM${row}-$AL${row},$AL${row}-$AK${row})`;
  for (let monthIndex = 0; monthIndex < forecastMonths; monthIndex += 1) {
    const col = colLetter(firstForecastColNumber + monthIndex);
    const priorCol = monthIndex === 0 ? "$AQ" : colLetter(firstForecastColNumber + monthIndex - 1);
    sheet.getRange(`${col}${row}`).formulas = [[`=MAX(0,${priorCol}${row}+${trend})`]];
  }
}

for (let monthIndex = 0; monthIndex < forecastMonths; monthIndex += 1) {
  const col = colLetter(firstForecastColNumber + monthIndex);
  sheet.getRange(`${col}8`).formulas = [[`=${col}2+($AQ8-$AQ2)`]];
  sheet.getRange(`${col}11`).formulas = [[`=${col}5+($AQ11-$AQ5)`]];
  sheet.getRange(`${col}18`).formulas = [[`=${col}5-${col}3`]];
  sheet.getRange(`${col}19`).formulas = [[`=${col}5-${col}7`]];
}

sheet.getRange(`AR20:${lastForecastCol}24`).values = Array.from({ length: 5 }, () => Array(forecastMonths).fill(""));

for (const row of [20, 21]) {
  const quarterlyTrend = `AVERAGE($AP${row}-$AM${row},$AM${row}-$AJ${row},$AJ${row}-$AG${row},$AG${row}-$AD${row})`;
  const reportCols = ["AS", "AV", "AY", "BB"];
  for (let reportIndex = 0; reportIndex < reportCols.length; reportIndex += 1) {
    const col = reportCols[reportIndex];
    const priorCol = reportIndex === 0 ? "$AP" : reportCols[reportIndex - 1];
    sheet.getRange(`${col}${row}`).formulas = [[`=MAX(0,${priorCol}${row}+${quarterlyTrend})`]];
  }
}

for (const row of [22, 23, 24]) {
  const quarterlyTrend = `AVERAGE($AO${row}-$AL${row},$AL${row}-$AI${row},$AI${row}-$AF${row},$AF${row}-$AC${row})`;
  const reportCols = ["AR", "AU", "AX", "BA"];
  for (let reportIndex = 0; reportIndex < reportCols.length; reportIndex += 1) {
    const col = reportCols[reportIndex];
    const priorCol = reportIndex === 0 ? "$AO" : reportCols[reportIndex - 1];
    sheet.getRange(`${col}${row}`).formulas = [[`=MAX(0,${priorCol}${row}+${quarterlyTrend})`]];
  }
}

sheet.getRange("A26").values = [["Forecast method: monthly series extend the average monthly change from the latest six actual months. Prime and mortgage rates hold their June 2025 spread to the applicable benchmark."]];
sheet.getRange("A27").values = [["Quarterly series retain their historical reporting months and extend the average change from the latest four reported quarters. Forecast period is July 2025 through June 2026."]];

sheet.getRange(`AR1:${lastForecastCol}1`).format = {
  fill: "#4472C4",
  font: { name: "Aptos Narrow", size: 11, bold: true, color: "#FFFFFF" },
  horizontalAlignment: "center",
  verticalAlignment: "center",
  borders: { bottom: { style: "thin", color: "#2F5597" } },
};
sheet.getRange(`AR2:${lastForecastCol}24`).format.fill = "#EAF2F8";
sheet.getRange(`AR2:${lastForecastCol}24`).format.font = { name: "Aptos Narrow", size: 11, color: "#000000" };
sheet.getRange("AR1:AR24").format.borders = { left: { style: "medium", color: "#2F5597" } };
sheet.getRange("A26:A27").format.font = { name: "Aptos Narrow", size: 9, italic: true, color: "#666666" };
sheet.getRange("A26:A27").format.rowHeight = 18;

sheet.getRange("A:A").format.columnWidth = 36;
sheet.getRange(`AR:${lastForecastCol}`).format.columnWidth = 10;
sheet.getRange(`AR2:${lastForecastCol}13`).format.numberFormat = "0.00";
sheet.getRange(`AR14:${lastForecastCol}14`).format.numberFormat = "#,##0";
sheet.getRange(`AR15:${lastForecastCol}24`).format.numberFormat = "0.00";
sheet.freezePanes.freezeRows(1);
sheet.freezePanes.freezeColumns(1);

workbook.recalculate();

const forecastInspect = await workbook.inspect({
  kind: "table",
  range: `macro forecast!AK1:${lastForecastCol}24`,
  include: "values,formulas",
  tableMaxRows: 30,
  tableMaxCols: 25,
  maxChars: 24000,
});
console.log("FORECAST");
console.log(forecastInspect.ndjson);

const notesInspect = await workbook.inspect({
  kind: "table",
  range: "macro forecast!A26:A27",
  include: "values,formulas",
  tableMaxRows: 4,
  tableMaxCols: 2,
  maxChars: 3000,
});
console.log("NOTES");
console.log(notesInspect.ndjson);

const errors = await workbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!",
  options: { useRegex: true, maxResults: 300 },
  summary: "final formula error scan",
});
console.log("ERRORS");
console.log(errors.ndjson);

await fs.mkdir(outputDir, { recursive: true });
await fs.mkdir(previewDir, { recursive: true });

const preview = await workbook.render({
  sheetName: "macro forecast",
  range: `AH1:${lastForecastCol}27`,
  scale: 1.5,
  format: "png",
});
const previewPath = path.join(previewDir, "macro-forecast-12-month.png");
await fs.writeFile(previewPath, new Uint8Array(await preview.arrayBuffer()));

const leftPreview = await workbook.render({
  sheetName: "macro forecast",
  range: "A1:H27",
  scale: 1.5,
  format: "png",
});
const leftPreviewPath = path.join(previewDir, "macro-forecast-labels-and-notes.png");
await fs.writeFile(leftPreviewPath, new Uint8Array(await leftPreview.arrayBuffer()));

const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(outputPath);

const reopened = await SpreadsheetFile.importXlsx(await FileBlob.load(outputPath));
reopened.recalculate();
const reopenedSheet = reopened.worksheets.getItem("macro forecast");
const firstForecastBefore = reopenedSheet.getRange("AR2").values[0][0];
const lastActualBefore = reopenedSheet.getRange("AQ2").values[0][0];
reopenedSheet.getRange("AQ2").values = [[lastActualBefore + 0.12]];
reopened.recalculate();
const firstForecastAfter = reopenedSheet.getRange("AR2").values[0][0];
const reopenedErrors = await reopened.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!",
  options: { useRegex: true, maxResults: 300 },
  summary: "reopened workbook formula error scan",
});

console.log(JSON.stringify({
  outputPath,
  previewPath,
  leftPreviewPath,
  recalculationTest: {
    firstForecastBefore,
    firstForecastAfter,
    changed: firstForecastBefore !== firstForecastAfter,
  },
  reopenedErrors: reopenedErrors.ndjson,
}, null, 2));
