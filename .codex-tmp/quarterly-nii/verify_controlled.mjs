import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const outputPath = "/Users/cjwork/holodeck-archive/outputs/01a0a8d5-e41c-7cd1-8fca-c36962c30d1e/balance-rate-nii-cof-monthly-controlled.xlsx";
const workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(outputPath));
workbook.recalculate();

const expectedSheets = [
  "Balance",
  "Rate",
  "Net Interest Income",
  "Notes & Sources",
  "Quarter-End Anchors",
  "Monthly EOP Balance",
  "Monthly Avg Balance",
  "Monthly NII",
  "Monthly Rate",
  "Monthly Checks",
];
const actualSheets = workbook.worksheets.items.map((sheet) => sheet.name);
const missing = expectedSheets.filter((name) => !actualSheets.includes(name));

const checks = workbook.worksheets.getItem("Monthly Checks");
const checkValues = checks.getRange("B6:O46").values.flat().filter((value) => typeof value === "number");
const maxControlDifference = Math.max(0, ...checkValues.map((value) => Math.abs(value)));

const balance = workbook.worksheets.getItem("Balance");
const monthlyEop = workbook.worksheets.getItem("Monthly EOP Balance");
const before = monthlyEop.getRange("C6").values[0][0];
const original = balance.getRange("B6").values[0][0];
balance.getRange("B6").values = [[original + 100]];
workbook.recalculate();
const after = monthlyEop.getRange("C6").values[0][0];

const errors = await workbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!",
  options: { useRegex: true, maxResults: 300 },
  summary: "reopened workbook formula error scan",
});

console.log(JSON.stringify({
  sheetCount: actualSheets.length,
  missingSheets: missing,
  maxControlDifference,
  formulaResponse: { before, after, changed: before !== after },
  errorScan: errors.ndjson,
}, null, 2));
