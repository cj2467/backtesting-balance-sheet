import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const sourcePath = "/Users/cjwork/holodeck-archive/outputs/01a0a8d5-e41c-7cd1-8fca-c36962c30d1e/balance-rate-nii-cof-monthly-controlled.xlsx";
const workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(sourcePath));

const sheets = await workbook.inspect({
  kind: "sheet",
  include: "id,name",
  maxChars: 5000,
});
console.log("SHEETS");
console.log(sheets.ndjson);

for (const sheetName of ["Monthly EOP Balance", "Monthly Avg Balance", "Monthly Rate", "Monthly NII"]) {
  const sheet = workbook.worksheets.getItem(sheetName);
  const used = sheet.getUsedRange(true);
  console.log(`USED ${sheetName}: ${used.address}`);
  console.log("HEADERS", JSON.stringify(sheet.getRange("A1:AZ6").values));
  console.log("CREDIT_CARD", JSON.stringify(sheet.getRange("A4:AZ6").values));
}

for (const sheetName of ["Balance", "Rate", "Net Interest Income", "Monthly Checks", "Notes & Sources"]) {
  const check = await workbook.inspect({
    kind: "table",
    range: `${sheetName}!A1:O60`,
    include: "values,formulas",
    tableMaxRows: 60,
    tableMaxCols: 15,
    maxChars: 25000,
  });
  console.log(`TABLE ${sheetName}`);
  console.log(check.ndjson);
}
