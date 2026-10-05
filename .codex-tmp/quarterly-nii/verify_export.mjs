import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const file = "/Users/cjwork/holodeck-archive/outputs/01a0a8d5-e41c-7cd1-8fca-c36962c30d1e/balance-rate-nii-cof-monthly-imputed.xlsx";
const workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(file));

const sheets = await workbook.inspect({ kind: "sheet", include: "id,name", maxChars: 4000 });
console.log("SHEETS");
console.log(sheets.ndjson);

const before = workbook.worksheets.getItem("Monthly Balance").getRange("C6").values[0][0];
const source = workbook.worksheets.getItem("Balance").getRange("B6");
const original = source.values[0][0];
source.values = [[original + 120]];
workbook.recalculate();
const after = workbook.worksheets.getItem("Monthly Balance").getRange("C6").values[0][0];
console.log(`RECALC_TEST_BEFORE=${before}`);
console.log(`RECALC_TEST_AFTER=${after}`);
console.log(`RECALC_DELTA=${after - before}`);

const errors = await workbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!",
  options: { useRegex: true, maxResults: 300 },
  summary: "saved workbook formula error scan",
});
console.log("SAVED_ERROR_SCAN");
console.log(errors.ndjson);
