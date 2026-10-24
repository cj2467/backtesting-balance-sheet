import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const inputPath = "/Users/cjwork/holodeck-archive/outputs/01a0a8d5-e41c-7cd1-8fca-c36962c30d1e/balance-rate-nii-cof-monthly-controlled.xlsx";
const workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(inputPath));
workbook.recalculate();

for (const name of ["Monthly Avg Balance", "Monthly NII", "Monthly Rate"]) {
  const sheet = workbook.worksheets.getItem(name);
  const dates = sheet.getRange("B4:AQ4").values[0];
  const values = sheet.getRange("B15:AQ15").values[0];
  console.log(name);
  console.log(JSON.stringify(dates.map((date, index) => ({ date, value: values[index] })).filter((row) => String(row.date).slice(0, 4) >= "2024"), null, 2));
}
